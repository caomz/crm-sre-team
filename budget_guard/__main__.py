"""Run the isolated SYNTHETIC budget gateway; never forwards to a provider.

Example:
python -m budget_guard serve \
  --policy budget_guard/policy.synthetic.json \
  --ledger /Volumes/WorkSSD/Archives/claude-tests/budget-0b/ledger.sqlite3 \
  --token-file /Volumes/WorkSSD/Archives/claude-tests/budget-0b/token \
  --port 43183
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import stat
import sys
from pathlib import Path

from budget_guard.ledger import InvalidRequest, Ledger, Limits
from budget_guard.proxy import SyntheticReceiver, make_server


def _check_state_path(path: Path) -> Path:
    if not path.is_absolute():
        raise InvalidRequest("state path must be absolute")
    if str(path).startswith(("/tmp/", "/private/tmp/", "/var/folders/")):
        raise InvalidRequest("persistent ledger cannot be in ephemeral temp")
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise InvalidRequest("state path must not traverse symbolic links")
    return path


def _read_bearer(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise InvalidRequest("token file missing or symlink")
    st = path.stat()
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise InvalidRequest("token file must be accessible only to owner")
    content = path.read_text(encoding="utf-8").strip()
    if len(content) < 24 or "\n" in content:
        raise InvalidRequest("token file content invalid")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="start synthetic-only loopback receiver")
    serve.add_argument("--policy", type=Path, required=True)
    serve.add_argument("--ledger", type=Path, required=True)
    serve.add_argument("--token-file", type=Path, required=True)
    serve.add_argument("--port", type=int, default=43183)
    args = parser.parse_args(argv)
    if args.command != "serve":
        return 2
    try:
        path = _check_state_path(args.ledger)
        payload = json.loads(args.policy.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise InvalidRequest("policy must be JSON object")
        limits = Limits(**payload)
        token = _read_bearer(args.token_file)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock_path = path.with_suffix(path.suffix + ".instance.lock")
        # POSIX advisory lock prevents two gateway instances from recovering
        # each other's in-flight reservations. macOS and Linux supported.
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a+b", buffering=0) as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InvalidRequest("ledger already has an active gateway") from exc
            ledger = Ledger(path, limits)
            recovered = ledger.recover_unknown()
            server = make_server(ledger, SyntheticReceiver(), token, args.port)
            print(json.dumps({
                "event": "SYNTHETIC_GATE_READY",
                "mode": "SYNTHETIC_OFFLINE_ONLY",
                "bind": "127.0.0.1",
                "port": server.server_address[1],
                "recovered_unknown": recovered,
                "token_cost_hard_cap": "BLOCKED",
                "real_provider_sends": 0,
            }), flush=True)
            try:
                server.serve_forever(poll_interval=0.2)
            finally:
                server.server_close()
        return 0
    except (InvalidRequest, OSError, ValueError, TypeError) as exc:
        print("FAIL_CLOSED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
