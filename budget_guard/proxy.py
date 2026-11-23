"""Loopback-only OpenAI-shaped SYNTHETIC receiver with a durable budget gate.

There is deliberately NO live-provider forwarding implementation here. All
responses are labelled synthetic, and TOKEN_COST_HARD_CAP remains BLOCKED.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from budget_guard.ledger import (
    BudgetError, BudgetExceeded, DuplicateRequest, InvalidRequest,
    Ledger,
)

MAX_BODY_BYTES = 1024 * 1024
HOST = "127.0.0.1"


class SyntheticFailure(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)


class SyntheticReceiver:
    """Counts calls actually reaching the synthetic sink; zero external I/O."""

    def __init__(self):
        self._lock = threading.Lock()
        self._received: list[str] = []

    def receive(self, request_id: str, model: str,
                fingerprint: str, fault: str | None = None) -> bytes:
        with self._lock:
            self._received.append(request_id)
        # A 429, timeout, or broken body occurs AFTER synthetic receipt.
        if fault in {"429", "timeout", "disconnect", "broken-stream"}:
            raise SyntheticFailure("synthetic post-receipt " + fault)
        return json.dumps(
            {
                "id": "synthetic-" + request_id,
                "object": "chat.completion",
                "model": model,
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": "SYNTHETIC_ONLY_NO_VENDOR_REQUEST"
                }, "finish_reason": "stop"}],
                "synthetic": True,
                "usage": None,
                "request_fingerprint": fingerprint,
            }, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def received(self) -> list[str]:
        with self._lock:
            return list(self._received)


def _validate_chat(body: bytes, model: str, max_output: int) -> tuple[dict[str, Any], int]:
    try:
        obj = json.loads(body)
    except (UnicodeError, ValueError) as exc:
        raise InvalidRequest("invalid UTF-8 JSON") from exc
    if not isinstance(obj, dict):
        raise InvalidRequest("JSON object required")
    allowed = {"model", "messages", "max_tokens", "max_completion_tokens",
               "stream", "temperature", "n"}
    if set(obj) - allowed:
        raise InvalidRequest("unsupported fields; no silent protocol fallback")
    if obj.get("model") != model:
        raise InvalidRequest("model route not approved")
    messages = obj.get("messages")
    if not isinstance(messages, list) or not messages:
        raise InvalidRequest("at least one message is required")
    if len(messages) > 512:
        raise InvalidRequest("too many messages")
    for msg in messages:
        if (not isinstance(msg, dict) or set(msg) != {"role", "content"}
            or msg["role"] not in {"system", "user", "assistant", "tool"}
            or not isinstance(msg["content"], str)):
            raise InvalidRequest("only text-only role/content messages supported")
    if obj.get("stream", False) is not False:
        raise InvalidRequest("streaming not implemented; fail closed")
    if type(obj.get("n", 1)) is not int or obj.get("n", 1) != 1:
        raise InvalidRequest("multi-choice output not supported")
    has_old = "max_tokens" in obj
    has_new = "max_completion_tokens" in obj
    if has_old == has_new:
        raise InvalidRequest("supply exactly one output limit")
    output = obj["max_tokens"] if has_old else obj["max_completion_tokens"]
    if type(output) is not int or output <= 0:
        raise InvalidRequest("output cap must be a positive integer")
    if output > max_output:
        raise BudgetExceeded("requested output exceeds per-request ceiling")
    if "temperature" in obj and (
        type(obj["temperature"]) not in (int, float) or
        not 0 <= obj["temperature"] <= 2
    ):
        raise InvalidRequest("invalid temperature")
    return obj, output


def make_handler(ledger: Ledger, receiver: SyntheticReceiver,
                 auth_token: str) -> type[BaseHTTPRequestHandler]:
    if not isinstance(auth_token, str) or len(auth_token) < 24:
        raise InvalidRequest("required local bearer secret is too short")
    # An audit/SQLite exception anywhere in a request freezes the in-process
    # gateway too. Crash recovery marks unfinished sends UNKNOWN on restart.
    persistence_failed = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "CrmBudgetSynthetic/0.1"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:
            # Never emit raw headers, prompt, bearer token or response body.
            pass

        def _reply(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def _authorized(self) -> bool:
            value = self.headers.get("Authorization", "")
            return hmac.compare_digest(value.encode("utf-8", errors="replace"),
                                       ("Bearer " + auth_token).encode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return self._reply(401, {"error": "authentication required"})
            if self.path != "/health":
                return self._reply(404, {"error": "unknown route"})
            return self._reply(200, {
                "mode": "SYNTHETIC_OFFLINE_ONLY",
                "real_provider_sends": 0,
                "synthetic_sink_receipts": len(receiver.received()),
                "stage_frozen_due_to_persistence_failure": persistence_failed.is_set(),
                "token_cost_hard_cap": "BLOCKED",
            })

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return self._reply(401, {"error": "authentication required"})
            if persistence_failed.is_set():
                return self._reply(503, {"error": "stage frozen after ledger failure"})
            if self.path != "/v1/chat/completions":
                return self._reply(404, {"error": "unsupported route"})
            if self.headers.get("Transfer-Encoding"):
                return self._reply(400, {"error": "chunked input not supported"})
            try:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None or not raw_length.isdigit():
                    raise InvalidRequest("Content-Length required")
                length = int(raw_length)
                if not 0 < length <= MAX_BODY_BYTES:
                    raise InvalidRequest("payload length out of bounds")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise InvalidRequest("truncated request")
                obj, output = _validate_chat(
                    body, ledger.limits.model,
                    ledger.limits.max_output_per_request,
                )
                request_id = self.headers.get("X-CRM-SRE-Request-ID", "")
                role = self.headers.get("X-CRM-SRE-Role", "")
                session_id = self.headers.get("X-CRM-SRE-Session-ID")
                agent_attempt_id = self.headers.get("X-CRM-SRE-Agent-Attempt-ID")
                digest = hashlib.sha256(body).hexdigest()
                # Offline-only pessimistic synthetic accounting. This is NOT a
                # verified model tokenizer or final-provider request upper bound.
                synthetic_input_bound = len(body) * 4 + 256
                ledger.reserve(request_id, digest, obj["model"], role,
                               synthetic_input_bound, output,
                               session_id=session_id,
                               agent_attempt_id=agent_attempt_id)
                ledger.begin_dispatch(request_id)
                try:
                    fault = self.headers.get("X-CRM-SRE-Synthetic-Fault")
                    response = receiver.receive(request_id, obj["model"], digest,
                                                fault=fault)
                except Exception:
                    # If dispatch reached the sink, 429 / timeout / broken
                    # response still occupies the slot. No automatic retries.
                    ledger.mark_unknown(request_id)
                    return self._reply(502, {
                        "error": "synthetic delivery outcome unknown; no retry",
                        "state": "UNKNOWN",
                    })
                # A failed confirmation cannot undo the prior transmission.
                ledger.confirm(request_id, response)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.send_header("X-CRM-SRE-Synthetic", "true")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(response)
                self.close_connection = True
            except DuplicateRequest:
                self._reply(409, {"error": "duplicate request; replay denied"})
            except BudgetExceeded as exc:
                self._reply(429, {"error": str(exc)})
            except (BudgetError, ValueError, TypeError) as exc:
                self._reply(400, {"error": str(exc)})
            except Exception:
                # Database or audit failure must never fall through to sink,
                # and must freeze every subsequent request on this instance.
                persistence_failed.set()
                self._reply(503, {"error": "persistent gate unavailable; stage frozen"})

    return Handler


def make_server(ledger: Ledger, receiver: SyntheticReceiver, auth_token: str,
                port: int = 0) -> ThreadingHTTPServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise InvalidRequest("port is not valid")
    server = ThreadingHTTPServer((HOST, port),
                                 make_handler(ledger, receiver, auth_token))
    server.daemon_threads = True
    return server
