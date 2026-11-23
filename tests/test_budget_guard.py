"""No-network budget-gateway regression suite.  Real Harness is NOT exercised."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from budget_guard.__main__ import _check_state_path, _read_bearer
from budget_guard.ledger import (
    BudgetExceeded, DuplicateRequest, InvalidRequest, InvalidTransition,
    Ledger, Limits,
)
from budget_guard.proxy import SyntheticReceiver, make_server


SECRET = "local-synthetic-token-very-long-and-private"
MODEL = "glm-5.3-flash"
PAYLOAD = {"model": MODEL, "messages": [{"role": "user",
            "content": "synthetic DEMO_DB 2026-11-21 E402"}],
           "max_tokens": 8, "stream": False}


def policy(**changes):
    config = dict(model=MODEL, max_requests=35,
                  max_reserved_tokens=445040, max_cost_micro_yuan=1250000,
                  max_output_per_request=128,
                  input_rate_micro_yuan_per_million=800000,
                  output_rate_micro_yuan_per_million=2800000,
                  price_version="SYNTHETIC_NOT_VERIFIED")
    config.update(changes)
    return Limits(**config)


def reserve(ledger, n=1, role="captain", input_upper=10, output_upper=10):
    return ledger.reserve(f"req-{n:06d}", hashlib.sha256(str(n).encode()).hexdigest(),
                          MODEL, role, input_upper, output_upper)


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "budget.sqlite3", policy())


@contextmanager
def server_session(tmp_path, limits=None):
    local_ledger = Ledger(tmp_path / "shared.sqlite3", limits or policy())
    receiver = SyntheticReceiver()
    server = make_server(local_ledger, receiver, SECRET, port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield local_ledger, receiver, server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def request(server, n=1, role="captain", payload=None, fault=None,
            token=SECRET, request_id=None, headers=None):
    body = json.dumps(payload if payload is not None else PAYLOAD,
                      sort_keys=True, separators=(",", ":")).encode()
    base = {"Authorization": "Bearer " + token,
            "X-CRM-SRE-Request-ID": request_id or f"req-{n:06d}",
            "X-CRM-SRE-Role": role,
            "Content-Type": "application/json"}
    if fault:
        base["X-CRM-SRE-Synthetic-Fault"] = fault
    base.update(headers or {})
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1],
                                      timeout=5)
    try:
        conn.request("POST", "/v1/chat/completions", body=body, headers=base)
        resp = conn.getresponse()
        contents = resp.read()
        return resp.status, json.loads(contents), dict(resp.getheaders())
    finally:
        conn.close()


def test_policy_rejects_nonpositive_limits():
    for name in ("max_requests", "max_reserved_tokens", "max_cost_micro_yuan",
                 "max_output_per_request", "input_rate_micro_yuan_per_million",
                 "output_rate_micro_yuan_per_million"):
        with pytest.raises(InvalidRequest):
            policy(**{name: 0})
        with pytest.raises(InvalidRequest):
            policy(**{name: True})


def test_policy_drift_refused_on_same_database(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    Ledger(path, policy())
    with pytest.raises(InvalidRequest, match="policy changed"):
        Ledger(path, policy(max_requests=36))


def test_ledger_permissions_private(ledger):
    assert stat.S_IMODE(ledger.path.stat().st_mode) == 0o600


def test_ledger_rejects_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(InvalidRequest, match="absolute"):
        Ledger("relative.sqlite3", policy())


def test_ledger_rejects_symlink_database(tmp_path):
    backing = tmp_path / "target"
    backing.write_text("not a sqlite database")
    alias = tmp_path / "alias.sqlite3"
    alias.symlink_to(backing)
    with pytest.raises(InvalidRequest, match="symlink"):
        Ledger(alias, policy())


def test_reject_invalid_request_identifiers(ledger):
    for bad in ("x", "contains spaces", "../abc", "", "not@ascii"):
        with pytest.raises(InvalidRequest):
            ledger.reserve(bad, "a"*64, MODEL, "captain", 5, 5)
    assert ledger.snapshot()["reservations"] == 0


def test_reject_invalid_fingerprint_model_and_role(ledger):
    for fingerprint, model, role in [
        ("xyz", MODEL, "captain"), ("a"*64, "other", "captain"),
        ("a"*64, MODEL, "unknown"),
    ]:
        with pytest.raises(InvalidRequest):
            ledger.reserve("req-bad000", fingerprint, model, role, 5, 5)


def test_reject_bool_or_zero_token_claims(ledger):
    for a, b in ((True, 5), (0, 5), (5, True), (5, 0)):
        with pytest.raises(InvalidRequest):
            ledger.reserve("req-bad000", "a"*64, MODEL, "captain", a, b)


def test_invalid_correlation_fields_are_rejected(ledger):
    with pytest.raises(InvalidRequest):
        ledger.reserve("req-bad000", "a"*64, MODEL, "captain", 5, 5,
                       session_id="../bad")


def test_exactly_35_capacity_and_request_36_rejected(ledger):
    for n in range(1, 36):
        reserve(ledger, n)
    with pytest.raises(BudgetExceeded):
        reserve(ledger, 36)
    assert ledger.snapshot()["reservations"] == 35


def test_captain_member_helper_share_same_ledger(ledger):
    for n in range(1, 36):
        reserve(ledger, n, role=("captain", "member", "helper")[n % 3])
    with pytest.raises(BudgetExceeded):
        reserve(ledger, 36, role="helper")


def test_concurrent_50_compete_for_35_slots(ledger):
    def attempt(n):
        try:
            reserve(ledger, n)
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=20) as pool:
        answers = list(pool.map(attempt, range(1, 51)))
    assert sum(answers) == 35
    assert ledger.snapshot()["reservations"] == 35


def test_token_budget_atomic_ceiling(tmp_path):
    led = Ledger(tmp_path / "l.sqlite", policy(max_reserved_tokens=30))
    reserve(led, 1, input_upper=10, output_upper=10)
    with pytest.raises(BudgetExceeded):
        reserve(led, 2, input_upper=10, output_upper=10)
    assert led.snapshot()["reserved_tokens"] == 20


def test_cost_budget_fails_closed(tmp_path):
    led = Ledger(tmp_path / "l.sqlite", policy(max_cost_micro_yuan=1))
    with pytest.raises(BudgetExceeded):
        reserve(led, 1, input_upper=1, output_upper=1)
    assert led.snapshot()["reservations"] == 0


def test_per_request_output_cap(tmp_path):
    led = Ledger(tmp_path / "l.sqlite", policy(max_output_per_request=4))
    with pytest.raises(BudgetExceeded):
        reserve(led, 1, input_upper=1, output_upper=5)


def test_duplicate_request_is_never_reused(ledger):
    reserve(ledger, 1)
    with pytest.raises(DuplicateRequest):
        reserve(ledger, 1)
    assert ledger.snapshot()["reservations"] == 1


def test_duplicate_request_is_never_reused_across_ledger_reopen(ledger):
    reserve(ledger, 1)
    reopened = Ledger(ledger.path, ledger.limits)
    with pytest.raises(DuplicateRequest):
        reserve(reopened, 1)


def test_dispatch_is_one_way(ledger):
    reserve(ledger, 1)
    ledger.begin_dispatch("req-000001")
    with pytest.raises(InvalidTransition):
        ledger.begin_dispatch("req-000001")
    assert ledger.get("req-000001")["status"] == "DISPATCHING"


def test_response_confirmed_with_hash_not_raw_content(ledger):
    reserve(ledger, 1)
    ledger.begin_dispatch("req-000001")
    ledger.confirm("req-000001", b"synthetic reply")
    row = ledger.get("req-000001")
    assert row["response_hash"] == hashlib.sha256(b"synthetic reply").hexdigest()
    assert row["status"] == "CONFIRMED"
    assert ledger.events("req-000001") == ["RESERVED", "DISPATCHING", "CONFIRMED"]


def test_second_confirmation_fails(ledger):
    reserve(ledger, 1)
    ledger.begin_dispatch("req-000001")
    ledger.confirm("req-000001", b"synthetic")
    with pytest.raises(InvalidTransition):
        ledger.confirm("req-000001", b"another")


def test_unknown_never_releases_slot(tmp_path):
    led = Ledger(tmp_path / "l.sqlite", policy(max_requests=1))
    reserve(led, 1)
    led.begin_dispatch("req-000001")
    led.mark_unknown("req-000001")
    with pytest.raises(BudgetExceeded):
        reserve(led, 2)
    assert led.get("req-000001")["status"] == "UNKNOWN"


def test_recovery_marks_unfinished_reservation_unknown(ledger):
    reserve(ledger, 1)
    reopened = Ledger(ledger.path, ledger.limits)
    assert reopened.recover_unknown() == 1
    assert reopened.get("req-000001")["status"] == "UNKNOWN"
    with pytest.raises(DuplicateRequest):
        reserve(reopened, 1)


def test_recovery_marks_dispatching_unknown_and_no_replay(ledger):
    reserve(ledger, 1)
    ledger.begin_dispatch("req-000001")
    reopened = Ledger(ledger.path, ledger.limits)
    assert reopened.recover_unknown() == 1
    assert reopened.get("req-000001")["status"] == "UNKNOWN"
    with pytest.raises(InvalidTransition):
        reopened.begin_dispatch("req-000001")


def test_recovery_is_idempotent(ledger):
    reserve(ledger, 1)
    assert ledger.recover_unknown() == 1
    assert ledger.recover_unknown() == 0


def test_recovery_keeps_confirmed_status(ledger):
    reserve(ledger, 1)
    ledger.begin_dispatch("req-000001")
    ledger.confirm("req-000001", b"response")
    assert ledger.recover_unknown() == 0


def test_ledger_does_not_store_raw_prompt(ledger):
    secret = b"synthetic confidential-only-no-real-customer-data"
    ledger.reserve("req-prompt001", hashlib.sha256(secret).hexdigest(),
                   MODEL, "member", 40, 10)
    assert secret not in ledger.path.read_bytes()


def test_synthetic_accounting_cannot_claim_billing_certification(ledger):
    assert ledger.snapshot()["hard_token_cost_certified"] is False


def test_request_body_strict_json_only(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        for obj in ({"model": MODEL, "max_tokens": 8, "messages": []},
                    dict(PAYLOAD, stream=True),
                    dict(PAYLOAD, tools=[]),
                    dict(PAYLOAD, n=2),
                    dict(PAYLOAD, model="unknown"),
                    dict(PAYLOAD, max_completion_tokens=8)):
            code, _, _ = request(server, n=100 + len(receiver.received()), payload=obj)
            assert code == 400
        assert receiver.received() == []
        assert led.snapshot()["reservations"] == 0


def test_loopback_bind_and_health_explicitly_block_live(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        assert server.server_address[0] == "127.0.0.1"
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        try:
            conn.request("GET", "/health", headers={"Authorization": "Bearer " + SECRET})
            response = conn.getresponse()
            payload = json.loads(response.read())
            assert response.status == 200
            assert payload["mode"] == "SYNTHETIC_OFFLINE_ONLY"
            assert payload["real_provider_sends"] == 0
            assert payload["token_cost_hard_cap"] == "BLOCKED"
        finally:
            conn.close()


def test_unauthorized_request_never_reaches_ledger_or_sink(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        code, _, _ = request(server, token="wrong")
        assert code == 401
        assert receiver.received() == []
        assert led.snapshot()["reservations"] == 0


def test_successful_synthetic_receipt_has_no_usage_claim(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        code, payload, headers = request(server, n=1)
        assert code == 200
        assert headers["X-CRM-SRE-Synthetic"] == "true"
        assert payload["synthetic"] is True
        assert payload["usage"] is None
        assert receiver.received() == ["req-000001"]
        assert led.get("req-000001")["status"] == "CONFIRMED"


@pytest.mark.parametrize("fault", ["429", "timeout", "disconnect", "broken-stream"])
def test_fault_after_receipt_is_unknown_without_retries(tmp_path, fault):
    with server_session(tmp_path) as (led, receiver, server):
        code, response, _ = request(server, 1, fault=fault)
        assert code == 502
        assert response["state"] == "UNKNOWN"
        assert receiver.received() == ["req-000001"]
        assert led.get("req-000001")["status"] == "UNKNOWN"
        replay_code, _, _ = request(server, 1)
        assert replay_code == 409
        assert receiver.received() == ["req-000001"]


def test_pre_reservation_disk_failure_yields_zero_receipts(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        with patch.object(led, "reserve", side_effect=sqlite3.OperationalError("disk full")):
            code, _, _ = request(server, 1)
        assert code == 503
        assert receiver.received() == []
        assert led.snapshot()["reservations"] == 0


def test_pre_dispatch_persistence_failure_yields_zero_receipts(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        with patch.object(led, "begin_dispatch",
                          side_effect=sqlite3.OperationalError("disk full")):
            code, _, _ = request(server, 1)
        assert code == 503
        assert receiver.received() == []
        assert led.snapshot()["reservations"] == 1


def test_confirmation_disk_failure_cannot_trigger_repeat_send(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        with patch.object(led, "confirm",
                          side_effect=sqlite3.OperationalError("disk full")):
            code, _, _ = request(server, 1)
        assert code == 503
        assert receiver.received() == ["req-000001"]
        assert led.get("req-000001")["status"] == "DISPATCHING"
        assert led.recover_unknown() == 1
        assert led.get("req-000001")["status"] == "UNKNOWN"
        assert request(server, 1)[0] == 409
        assert len(receiver.received()) == 1


def test_proxy_competing_for_last_slot_and_36th_rejected(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        for n in range(1, 35):
            assert request(server, n, role="member" if n % 2 else "helper")[0] == 200
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda n: request(server, n, role="captain")[0],
                                  (35, 36)))
        assert sorted(codes) == [200, 429]
        assert request(server, 37)[0] == 429
        assert led.snapshot()["reservations"] == 35
        assert len(receiver.received()) == 35


def test_duplicate_request_under_concurrency_received_once(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(lambda _: request(server, 1)[0], range(8)))
        assert codes.count(200) == 1
        assert codes.count(409) == 7
        assert receiver.received() == ["req-000001"]


def test_unknown_consumes_slot_after_restart_without_refund(tmp_path):
    path = tmp_path / "state.sqlite3"
    led = Ledger(path, policy(max_requests=1))
    reserve(led, 1)
    led.begin_dispatch("req-000001")
    recovered = Ledger(path, policy(max_requests=1))
    assert recovered.recover_unknown() == 1
    with pytest.raises(BudgetExceeded):
        reserve(recovered, 2)


def test_unsupported_streaming_refused_before_reservation(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        code, _, _ = request(server, 1, payload=dict(PAYLOAD, stream=True))
        assert code == 400
        assert led.snapshot()["reservations"] == 0
        assert receiver.received() == []


def test_unrecognized_upstream_route_never_forwards(tmp_path):
    with server_session(tmp_path) as (led, receiver, server):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        try:
            conn.request("POST", "/v1/responses", b"{}",
                         {"Authorization": "Bearer " + SECRET})
            result = conn.getresponse()
            assert result.status == 404
            result.read()
        finally:
            conn.close()
        assert receiver.received() == []


def test_ephemeral_ledger_path_rejected_at_cli_boundary():
    for name in ("/tmp/test.sqlite3", "/private/tmp/ledger.db",
                 "/var/folders/demo/ledger.sqlite3"):
        with pytest.raises(InvalidRequest):
            _check_state_path(Path(name))


def test_cli_rejects_symlink_ancestor(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "alias"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(InvalidRequest):
        _check_state_path(link / "ledger.sqlite3")


def test_token_file_requires_private_permissions(tmp_path):
    tokenfile = tmp_path / "bearer"
    tokenfile.write_text(SECRET)
    tokenfile.chmod(0o644)
    with pytest.raises(InvalidRequest):
        _read_bearer(tokenfile)
    tokenfile.chmod(0o600)
    assert _read_bearer(tokenfile) == SECRET
