"""External evaluation ledger: schema validation, idempotency and ratchet."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from jsonschema import Draft202012Validator


def validate(data: dict, schema: Path) -> None:
    Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(data)
    ids = [r["run_id"] for r in data["runs"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate run IDs")
    for run in data["runs"]:
        for group in run["sets"].values():
            if sum(group[k] for k in ("passed", "failed", "not_run", "host_limit")) != len(group["cases"]):
                raise ValueError("set counts do not match cases")
            if group.get("results"):
                if set(group["results"]) != set(group["cases"]):
                    raise ValueError("case outcomes do not match case IDs")
                categories = {"passed": {"PASS", "PASS_WITH_KNOWN_ISSUES"}, "failed": {"FAIL", "BLOCKED"},
                              "not_run": {"NOT_RUN"}, "host_limit": {"HOST_LIMIT"}}
                if any(sum(v in values for v in group["results"].values()) != group[k] for k, values in categories.items()):
                    raise ValueError("case outcomes do not match counts")


def ratchet(runs: list[dict], candidate: dict) -> dict:
    """Compare matching host/model/criteria and matching case sets only."""
    previous = [r for r in runs if r["version"] != candidate["version"]
                and all(r[k] == candidate[k] for k in ("host_version", "model", "criteria_version"))]
    results = {}
    for category in ("golden", "safety"):
        current = candidate["sets"][category]
        comparisons = []
        for run in previous:
            old = run["sets"][category]
            if old["cases"] == current["cases"]:
                comparisons.append({"run_id": run["run_id"], "cases": old["cases"], "floor": old["passed"], "passed": current["passed"]})
            elif old["cases"] and set(old["cases"]) <= set(current["cases"]) and current.get("results"):
                passed = sum(current["results"][c] in ("PASS", "PASS_WITH_KNOWN_ISSUES") for c in old["cases"])
                comparisons.append({"run_id": run["run_id"], "cases": old["cases"], "floor": old["passed"], "passed": passed})
        floor = max((r["floor"] for r in comparisons), default=None)
        results[category] = {"floor": floor, "passed": current["passed"], "comparisons": comparisons,
                             "result": "NO_COMPARABLE_BASELINE" if floor is None else
                                       "PASS" if all(r["passed"] >= r["floor"] for r in comparisons) else "FAIL"}
    return {"ok": all(v["result"] != "FAIL" for v in results.values()), "sets": results,
            "exceptional": "RECORDED_WITHOUT_FLOOR"}


def append(path: Path, run: dict, schema: Path) -> dict:
    """Refuse duplicate changed IDs and symlinks. Data never enters the release."""
    if path.is_symlink():
        raise ValueError("ledger cannot be a symlink")
    before = path.read_bytes() if path.exists() else None
    data = json.loads(before) if before is not None else {"schema": "crm-sre-eval-ledger/v1", "runs": []}
    validate({"schema": data["schema"], "runs": [run]}, schema)
    validate(data, schema)
    existing = next((r for r in data["runs"] if r["run_id"] == run["run_id"]), None)
    if existing is not None:
        if existing != run:
            raise ValueError("run ID exists with different evidence")
        return {"appended": False, "ratchet": ratchet(data["runs"], run)}
    outcome = ratchet(data["runs"], run)
    data["runs"].append(run)
    validate(data, schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Append results even on regression; a failed run must not disappear.
    staging = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp.json")
    with staging.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    if (path.read_bytes() if path.exists() else None) != before or path.is_symlink():
        raise ValueError("ledger changed before replacement; staging retained")
    if before is not None:
        history = path.parent / (path.name + ".history")
        history.mkdir(exist_ok=True)
        with (history / (uuid.uuid4().hex + ".json")).open("xb") as stream:
            stream.write(before)
    os.replace(staging, path)
    return {"appended": True, "ratchet": outcome}
