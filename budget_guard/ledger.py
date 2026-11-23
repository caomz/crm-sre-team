"""Crash-conservative, SQLite-backed reservation ledger for offline CRM/SRE budget tests.

This package does NOT authorize real provider traffic or certify billed token counts.
Every reservation is never refunded automatically; exceptions keep the slot occupied.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BudgetError(Exception):
    """Base for fail-closed budget rejections."""


class InvalidRequest(BudgetError):
    pass


class BudgetExceeded(BudgetError):
    pass


class DuplicateRequest(BudgetError):
    pass


class InvalidTransition(BudgetError):
    pass


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{5,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ROLES = frozenset({"captain", "member", "helper"})


def _positive_int(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidRequest(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise InvalidRequest(f"{name} must be a nonnegative integer")
    return value


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Limits:
    """Synthetic policy. Rates are micro-yuan per million tokens."""

    model: str
    max_requests: int
    max_reserved_tokens: int
    max_cost_micro_yuan: int
    max_output_per_request: int
    input_rate_micro_yuan_per_million: int
    output_rate_micro_yuan_per_million: int
    price_version: str

    def __post_init__(self) -> None:
        if not self.model or not isinstance(self.model, str):
            raise InvalidRequest("model must be non-empty")
        if not self.price_version or not isinstance(self.price_version, str):
            raise InvalidRequest("price_version required")
        # A zero quota is a valid fail-closed configuration: it must never
        # create a receipt, even when the synthetic service is running.
        for name in ("max_requests", "max_reserved_tokens", "max_cost_micro_yuan"):
            _nonnegative_int(getattr(self, name), name)
        for name in ("max_output_per_request", "input_rate_micro_yuan_per_million",
                     "output_rate_micro_yuan_per_million"):
            _positive_int(getattr(self, name), name)

    def cost_reserve(self, input_upper: int, output_upper: int) -> int:
        # Round up *each request* to ensure rounding never under-reserves.
        numerator = (input_upper * self.input_rate_micro_yuan_per_million
                     + output_upper * self.output_rate_micro_yuan_per_million)
        return (numerator + 999_999) // 1_000_000


class Ledger:
    """One SQLite transaction per state change; independent processes share WAL.

    Assumes a locally trusted filesystem which implements durable fsync. Do not
    place the live state directory on /tmp, an NFS share, or a symlink path.
    Storage failure is a hard rejection, not permission to send.
    """

    def __init__(self, db_path: str | Path, limits: Limits):
        self.path = Path(db_path)
        self.limits = limits
        if not self.path.is_absolute():
            raise InvalidRequest("ledger path must be absolute")
        if self.path.exists() and self.path.is_symlink():
            raise InvalidRequest("ledger must not be a symlink")
        if self.path.parent.is_symlink():
            raise InvalidRequest("ledger parent must not be a symlink")
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not self.path.parent.is_dir():
            raise InvalidRequest("ledger parent is not directory")
        if self.path.exists() and not stat.S_ISREG(self.path.stat().st_mode):
            raise InvalidRequest("ledger must be a regular file")

        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""CREATE TABLE IF NOT EXISTS reservations (
                request_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                model TEXT NOT NULL,
                role TEXT NOT NULL,
                session_id TEXT,
                agent_attempt_id TEXT,
                input_upper INTEGER NOT NULL CHECK(input_upper > 0),
                output_upper INTEGER NOT NULL CHECK(output_upper > 0),
                reserved_cost_micro INTEGER NOT NULL CHECK(reserved_cost_micro > 0),
                status TEXT NOT NULL CHECK(status IN
                  ('RESERVED','DISPATCHING','CONFIRMED','UNKNOWN')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                response_hash TEXT
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""")
            # Changing policy against an existing ledger is forbidden.
            policy_sha = hashlib.sha256(repr(limits).encode("utf-8")).hexdigest()
            old = conn.execute("SELECT value FROM meta WHERE key='policy_sha'").fetchone()
            if old and old[0] != policy_sha:
                raise InvalidRequest("persistent ledger policy changed; stop")
            if not old:
                conn.execute("INSERT INTO meta(key,value) VALUES('policy_sha',?)",
                             (policy_sha,))
            conn.commit()
        if self.path.exists():
            self.path.chmod(0o600)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @staticmethod
    def _event(conn: sqlite3.Connection, request_id: str,
               phase: str, note: str = "") -> None:
        conn.execute("INSERT INTO events(request_id,phase,created_at,note) "
                     "VALUES(?,?,?,?)", (request_id, phase, _utc(), note))

    def reserve(self, request_id: str, fingerprint: str, model: str, role: str,
                input_upper: int, output_upper: int,
                session_id: str | None = None,
                agent_attempt_id: str | None = None) -> dict[str, int]:
        if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
            raise InvalidRequest("request_id needs 6..128 safe ASCII characters")
        if not isinstance(fingerprint, str) or not _HEX64.fullmatch(fingerprint):
            raise InvalidRequest("fingerprint must be SHA256 hex")
        if model != self.limits.model or role not in _ROLES:
            raise InvalidRequest("model or caller role is not allowed")
        input_upper = _positive_int(input_upper, "input_upper")
        output_upper = _positive_int(output_upper, "output_upper")
        if output_upper > self.limits.max_output_per_request:
            raise BudgetExceeded("per-request output ceiling")
        for key, value in (("session_id", session_id), ("agent_attempt_id", agent_attempt_id)):
            if value is not None and (not isinstance(value, str) or
                                      len(value) > 128 or not _ID.fullmatch(value)):
                raise InvalidRequest(f"invalid {key}")
        total = input_upper + output_upper
        cost = self.limits.cost_reserve(input_upper, output_upper)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM reservations WHERE request_id=?",
                            (request_id,)).fetchone():
                raise DuplicateRequest("request id already consumed; never replay")
            used = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_upper + output_upper),0), "
                "COALESCE(SUM(reserved_cost_micro),0) FROM reservations"
            ).fetchone()
            if (used[0] + 1 > self.limits.max_requests or
                used[1] + total > self.limits.max_reserved_tokens or
                used[2] + cost > self.limits.max_cost_micro_yuan):
                raise BudgetExceeded("shared persistent capacity exhausted")
            now = _utc()
            conn.execute("""INSERT INTO reservations
                (request_id,fingerprint,model,role,session_id,agent_attempt_id,
                 input_upper,output_upper,reserved_cost_micro,status,
                 created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,'RESERVED',?,?)""",
                 (request_id, fingerprint, model, role, session_id,
                  agent_attempt_id, input_upper, output_upper, cost, now, now))
            self._event(conn, request_id, "RESERVED")
            conn.commit()  # reservation durable BEFORE any transport activity
            return {"input_upper": input_upper, "output_upper": output_upper,
                    "reserved_cost_micro": cost}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def begin_dispatch(self, request_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                "UPDATE reservations SET status='DISPATCHING',updated_at=? "
                "WHERE request_id=? AND status='RESERVED'", (_utc(), request_id)
            ).rowcount
            if changed != 1:
                raise InvalidTransition("not an unused reservation")
            self._event(conn, request_id, "DISPATCHING")
            conn.commit()  # single dispatch right recorded BEFORE transport call
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def confirm(self, request_id: str, response_bytes: bytes) -> None:
        if not isinstance(response_bytes, bytes):
            raise InvalidRequest("response must be bytes")
        digest = hashlib.sha256(response_bytes).hexdigest()
        self._transition(request_id, "CONFIRMED", digest)

    def mark_unknown(self, request_id: str) -> None:
        self._transition(request_id, "UNKNOWN", None)

    def _transition(self, request_id: str, target: str,
                    response_hash: str | None) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            changed = conn.execute(
                "UPDATE reservations SET status=?,updated_at=?,response_hash=? "
                "WHERE request_id=? AND status='DISPATCHING'",
                (target, _utc(), response_hash, request_id)
            ).rowcount
            if changed != 1:
                raise InvalidTransition("request is not actively dispatching")
            self._event(conn, request_id, target)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def recover_unknown(self) -> int:
        """Reopening after a process crash: no refunds, no automatic resends."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            candidates = [row[0] for row in conn.execute(
                "SELECT request_id FROM reservations WHERE status IN "
                "('RESERVED','DISPATCHING') ORDER BY created_at"
            )]
            for request_id in candidates:
                conn.execute("UPDATE reservations SET status='UNKNOWN',updated_at=? "
                             "WHERE request_id=?", (_utc(), request_id))
                self._event(conn, request_id, "UNKNOWN", "crash/recovery fail closed")
            conn.commit()
            return len(candidates)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def snapshot(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            count, tokens, cost = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(input_upper+output_upper),0), "
                "COALESCE(SUM(reserved_cost_micro),0) FROM reservations"
            ).fetchone()
            status = dict(conn.execute(
                "SELECT status,COUNT(*) FROM reservations GROUP BY status"
            ).fetchall())
            return {"reservations": count, "reserved_tokens": tokens,
                    "reserved_cost_micro_yuan": cost, "by_status": status,
                    "max_requests": self.limits.max_requests,
                    "hard_token_cost_certified": False}
        finally:
            conn.close()

    def get(self, request_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT request_id,fingerprint,role,input_upper,output_upper,"
                "reserved_cost_micro,status,response_hash,session_id,"
                "agent_attempt_id FROM reservations WHERE request_id=?",
                (request_id,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def events(self, request_id: str) -> list[str]:
        conn = self._connect()
        try:
            return [row[0] for row in conn.execute(
                "SELECT phase FROM events WHERE request_id=? ORDER BY event_id",
                (request_id,)
            )]
        finally:
            conn.close()
