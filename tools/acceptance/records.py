"""Locate explicit IDs, preserve raw bytes, and project allowed event fields."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ID = re.compile(r"(?:agent-)?[A-Za-z0-9][A-Za-z0-9-]{0,119}\Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def visible(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(visible(v) for v in value)
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return ""


def locate(projects: Path, identifier: str) -> Path:
    if not ID.fullmatch(identifier):
        raise ValueError("invalid session/member ID")
    if not projects.is_dir() or projects.is_symlink():
        raise ValueError("projects must be a real directory")
    pattern = f"*/{identifier}.jsonl" if not identifier.startswith("agent-") else f"*/*/subagents/{identifier}.jsonl"
    matches = [p for p in projects.glob(pattern) if p.is_file() and not p.is_symlink()]
    if len(matches) != 1:
        raise ValueError(f"expected one record for {identifier}, found {len(matches)}")
    path = matches[0]
    if not path.resolve().is_relative_to(projects.resolve()):
        raise ValueError("record path escapes projects")
    return path


def project(path: Path) -> dict:
    """Only inspect top-level event fields and explicitly allowed usage keys."""
    data = path.read_bytes()
    result = {"source": str(path), "sha256": sha256(data), "bytes": len(data),
              "events": [], "inputs": [], "models": [], "agents": [],
              "parse_errors": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                                            "total_tokens": 0, "credit": 0}, "usage_rows": 0}
    models, agents, timestamps, seen_events, seen_usage = set(), set(), [], set(), set()
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                raise ValueError("record is not an object")
        except ValueError as exc:
            result["parse_errors"].append({"line": number, "error": str(exc)})
            continue
        timestamp = row.get("timestamp")
        if type(timestamp) in (int, float):
            timestamps.append(timestamp)
        provider = row.get("providerData")
        if isinstance(provider, dict):
            if isinstance(provider.get("model"), str):
                models.add(provider["model"])
            if isinstance(provider.get("agent"), str):
                agents.add(provider["agent"])
            usage = provider.get("rawUsage")
            # A streamed generation can be repeated in multiple event rows.
            identity = provider.get("messageId") or row.get("id") or (number,)
            if isinstance(usage, dict) and identity not in seen_usage:
                seen_usage.add(identity)
                result["usage_rows"] += 1
                for key in result["usage"]:
                    value = usage.get(key)
                    if type(value) in (int, float) and value >= 0:
                        result["usage"][key] += value
        if isinstance(row.get("agent"), str):
            agents.add(row["agent"])
        kind = row.get("type")
        if kind in ("function_call", "function_call_result"):
            identity = (kind, row.get("callId"))
            if identity in seen_events:
                continue
            seen_events.add(identity)
            event = {k: row[k] for k in ("type", "name", "callId", "status", "timestamp") if k in row}
            event["line"] = number
            if kind == "function_call":
                try:
                    args = row.get("arguments", {})
                    event["arguments"] = json.loads(args) if isinstance(args, str) else args
                    if not isinstance(event["arguments"], dict):
                        raise ValueError("arguments are not an object")
                except ValueError as exc:
                    event["arguments"] = {}
                    result["parse_errors"].append({"line": number, "error": str(exc)})
            else:
                event["output"] = visible(row.get("output"))
            result["events"].append(event)
        elif kind == "message":
            content = row.get("content", [])
            if not isinstance(content, list):
                continue
            if row.get("role") == "assistant":
                text = "\n".join(c.get("text", "") for c in content
                                 if isinstance(c, dict) and c.get("type") == "output_text")
                if text:
                    # The host writes connection errors in assistant-shaped rows.
                    # Metadata, not error words quoted by a model, identifies them.
                    host_error = isinstance(provider, dict) and bool(provider.get("error")) and (
                        provider.get("skipRun") is True or row.get("status") == "incomplete")
                    result["events"].append({"type": "host_error" if host_error else "assistant_output",
                                             "line": number, "text": text})
            elif row.get("role") == "user":
                text = "\n".join(c.get("text", "") for c in content
                                 if isinstance(c, dict) and c.get("type") == "input_text")
                result["inputs"].append({"line": number, "text": text})
    calls = [e for e in result["events"] if e["type"] == "function_call"]
    returns = [e for e in result["events"] if e["type"] == "function_call_result"]
    call_ids, return_ids = {e.get("callId") for e in calls}, {e.get("callId") for e in returns}
    result.update(models=sorted(models), agents=sorted(agents),
                  unpaired_calls=sorted(call_ids - return_ids, key=str),
                  unpaired_returns=sorted(return_ids - call_ids, key=str),
                  duration_seconds=(max(timestamps) - min(timestamps)) / 1000 if timestamps else None)
    result["complete"] = bool(result["events"] and result["events"][-1]["type"] in ("assistant_output", "host_error")
                              and not result["unpaired_calls"] and not result["unpaired_returns"])
    return result


def collect(projects: Path, session_id: str | None, member_id: str | None, output: Path) -> dict:
    if bool(session_id) == bool(member_id):
        raise ValueError("provide exactly one session_id or member_id")
    first = locate(projects, session_id or member_id)
    paths = [first]
    if session_id:
        lead = project(first)
        ids = sorted(set(re.findall(r"\[Agent ID:\s*(agent-[\w-]+)\]", "\n".join(
            e.get("output", "") for e in lead["events"] if e.get("name") == "Agent"))))
        for identifier in ids:
            path = first.parent / first.stem / "subagents" / (identifier + ".jsonl")
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(projects.resolve()):
                raise ValueError("missing or unsafe member record: " + identifier)
            paths.append(path)
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("evidence directory cannot be a symlink")
    files = []
    for path in paths:
        data = path.read_bytes()
        destination = output / path.name
        if destination.exists():
            if destination.is_symlink() or destination.read_bytes() != data:
                raise ValueError("existing evidence differs; refusing overwrite: " + str(destination))
        else:
            with destination.open("xb") as stream:
                stream.write(data)
        if path.read_bytes() != data or destination.read_bytes() != data:
            raise ValueError("source changed during collection")
        files.append({"role": "member" if path.stem.startswith("agent-") else "lead",
                      "source": str(path), "copy": str(destination), "sha256": sha256(data)})
    manifest = {"schema": "workbuddy-collection/v1", "files": files}
    for name, data in (("collection.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
                       ("SHA256SUMS", "".join(f"{f['sha256']}  {Path(f['copy']).name}\n" for f in files))):
        target = output / name
        if target.exists() and (target.is_symlink() or target.read_text() != data):
            raise ValueError("existing collection metadata differs")
        if not target.exists():
            target.write_text(data, encoding="utf-8")
    return manifest
