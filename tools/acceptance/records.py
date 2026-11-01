"""Locate explicit IDs, preserve raw bytes, and project allowed event fields."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat

ID = re.compile(r"(?:agent-)?[A-Za-z0-9][A-Za-z0-9-]{0,119}\Z")


def no_links(path: Path) -> bool:
    """Inspect original components, before resolve can erase a link/reparse point."""
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            return False
    return True


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
    if not projects.is_dir() or not no_links(projects):
        raise ValueError("projects must be a real directory")
    pattern = f"*/{identifier}.jsonl" if not identifier.startswith("agent-") else f"*/*/subagents/{identifier}.jsonl"
    matches = [p for p in projects.glob(pattern) if p.is_file() and not p.is_symlink()]
    if len(matches) != 1:
        raise ValueError(f"expected one record for {identifier}, found {len(matches)}")
    path = matches[0]
    if not no_links(path) or not path.resolve().is_relative_to(projects.resolve()):
        raise ValueError("record path escapes projects")
    return path


def project(path: Path) -> dict:
    """Only inspect top-level event fields and explicitly allowed usage keys."""
    data = path.read_bytes()
    result = {"source": str(path), "sha256": sha256(data), "bytes": len(data),
              "events": [], "inputs": [], "messages": [], "models": [], "agents": [],
              "parse_errors": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                                            "total_tokens": 0, "credit": 0}, "usage_rows": 0}
    models, agents, timestamps, seen_events, seen_usage = set(), set(), [], {}, set()
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
            event = {k: row[k] for k in ("type", "name", "callId", "status", "timestamp") if k in row}
            event["line"] = number
            call_id = row.get("callId")
            valid_id = isinstance(call_id, str) and bool(call_id.strip())
            if not valid_id:
                result["parse_errors"].append({"line": number, "error": "callId must be a nonempty string"})
            if not isinstance(row.get("name"), str) or not row["name"].strip():
                result["parse_errors"].append({"line": number, "error": "tool name must be a nonempty string"})
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
            if valid_id:
                identity = (kind, call_id)
                payload = {k: v for k, v in event.items() if k not in ("line", "timestamp")}
                if kind == "function_call_result":
                    # Compare the full result, even when its visible projection is empty.
                    payload["output"] = row.get("output")
                signature = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                prior = seen_events.get(identity)
                if prior is not None:
                    if signature == prior[0]:
                        continue
                    result["parse_errors"].append({"line": number, "first_line": prior[1],
                                                   "error": "conflicting event for the same type and callId"})
                else:
                    seen_events[identity] = (signature, number)
            # Invalid IDs and conflicting duplicates remain visible for review.
            result["events"].append(event)
        elif kind == "message":
            content = row.get("content", [])
            if not isinstance(content, list):
                result["parse_errors"].append({"line": number, "error": "message content is not a list"})
                content = []
            role = row.get("role")
            content_type = "output_text" if role == "assistant" else "input_text"
            chunks = [c.get("text") for c in content if isinstance(c, dict) and c.get("type") == content_type]
            if any(not isinstance(c, str) for c in chunks):
                result["parse_errors"].append({"line": number, "error": "message text is not a string"})
            text = "\n".join(c for c in chunks if isinstance(c, str))
            message_id = row.get("id") or (provider.get("messageId") if isinstance(provider, dict) else None)
            message = {"line": number, "role": role, "text": text,
                       "status": row.get("status"), "status_present": "status" in row,
                       "id": message_id if isinstance(message_id, str) else None,
                       "host_meta": isinstance(provider, dict) and provider.get("isMeta") is True,
                       "host_skip_run": isinstance(provider, dict) and provider.get("skipRun") is True}
            result["messages"].append(message)
            if row.get("role") == "assistant":
                # The host can write errors with no visible text. Metadata, not
                # error words quoted by a model, identifies these rows.
                host_error = isinstance(provider, dict) and bool(provider.get("error")) and (
                    provider.get("skipRun") is True or row.get("status") == "incomplete")
                # Empty messages still carry terminal state and must not vanish.
                result["events"].append({"type": "host_error" if host_error else "assistant_output",
                                        **message})
            elif row.get("role") == "user":
                result["inputs"].append({"line": number, "text": text,
                                         "host_meta": message["host_meta"], "host_skip_run": message["host_skip_run"]})
    calls = [e for e in result["events"] if e["type"] == "function_call"]
    returns = [e for e in result["events"] if e["type"] == "function_call_result"]
    valid_calls = {e["callId"]: e for e in calls
                   if isinstance(e.get("callId"), str) and e["callId"].strip()}
    valid_returns = {e["callId"]: e for e in returns
                     if isinstance(e.get("callId"), str) and e["callId"].strip()}
    call_ids, return_ids = set(valid_calls), set(valid_returns)
    for call_id in sorted(call_ids & return_ids):
        call, returned = valid_calls[call_id], valid_returns[call_id]
        if call.get("name") != returned.get("name"):
            result["parse_errors"].append({"line": returned["line"], "first_line": call["line"],
                                           "error": "call and result tool names differ for the same callId"})
        if returned["line"] < call["line"]:
            result["parse_errors"].append({"line": returned["line"], "error": "result precedes call"})
    result.update(models=sorted(models), agents=sorted(agents),
                  unpaired_calls=sorted(call_ids - return_ids, key=str),
                  unpaired_returns=sorted(return_ids - call_ids, key=str),
                  duration_seconds=(max(timestamps) - min(timestamps)) / 1000 if timestamps else None)
    result.update(completion_state="NO_FINAL_RESPONSE", final_output="", final_line=None)
    last = result["events"][-1] if result["events"] else {}
    last_user = result["inputs"][-1]["line"] if result["inputs"] else 0
    if last_user > last.get("line", 0):
        result["completion_state"] = "AWAITING_RESPONSE"
    elif last.get("type") == "host_error":
        result["completion_state"] = "HOST_ERROR"
    elif last.get("type") == "assistant_output":
        result.update(final_output=last["text"], final_line=last["line"])
        result["completion_state"] = "COMPLETED" if last.get("status") == "completed" else "UNFINISHED_OR_UNKNOWN_STATUS"
        # A different unfinished message is not proven recovered by later text.
        # Same-ID streaming updates can finish; conflicting completed snapshots cannot.
        messages = [m for m in result["messages"] if m["role"] == "assistant" and m["line"] > last_user]
        latest = {}
        for m in messages:
            identity = m["id"] or ("line", m["line"])
            prior = latest.get(identity)
            if prior and prior["status"] == "completed" and (m["status"], m["text"]) != (prior["status"], prior["text"]):
                result["parse_errors"].append({"line": m["line"], "error": "conflicting completed message"})
            latest[identity] = m
        if any(m["status"] != "completed" for m in latest.values()):
            result["completion_state"] = "UNFINISHED_OR_UNKNOWN_STATUS"
    result["complete"] = (result["completion_state"] == "COMPLETED" and not result["parse_errors"]
                          and not result["unpaired_calls"] and not result["unpaired_returns"])
    return result


def request_binding(record: dict, frozen: str | None = None, *, member_prompt: str | None = None) -> dict:
    """Only a single explicit request is automatically scored. Never trim history."""
    inputs = record["inputs"]
    base = {"raw_sha256": record["sha256"], "request_line": None, "final_line": record["final_line"]}
    if member_prompt is not None:
        # WorkBuddy 5.8.3 buildPreloadItem: isMeta + skipRun, before the exact
        # dispatched user message. Enable only after independent member provenance.
        preloaded = []
        while len(inputs) > 1:
            row = inputs[0]
            if not (row.get("host_meta") and row.get("host_skip_run") and re.fullmatch(
                    r'<skill-preloaded name="[^"\r\n]+">\n.*\n</skill-preloaded>', row["text"], re.S)):
                break
            preloaded.append(row["line"])
            inputs = inputs[1:]
        base["host_preload_lines"] = preloaded
    if len(inputs) != 1:
        return {**base, "state": "BLOCKED", "reason": "REQUEST_MISSING_OR_AMBIGUOUS"}
    request = inputs[0]
    base["request_line"] = request["line"]
    if any(e["line"] < request["line"] for e in record["events"]):
        return {**base, "state": "BLOCKED", "reason": "EVIDENCE_PRECEDES_REQUEST"}
    queries = re.findall(r"<user_query>(.*?)</user_query>", request["text"], re.S)
    query = queries[0] if len(queries) == 1 else request["text"]
    normalize = lambda s: re.sub(r"\s+", " ", s.replace("\ufeff", "")).strip()
    base["query_sha256"] = sha256(normalize(query).encode())
    if member_prompt is not None and request["text"] != member_prompt:
        return {**base, "state": "FAIL", "reason": "MEMBER_DISPATCH_INPUT_MISMATCH"}
    if frozen and (len(queries) != 1 or normalize(query) != normalize(frozen)):
        return {**base, "state": "FAIL", "reason": "FROZEN_INPUT_MISMATCH"}
    return {**base, "state": "BOUND", "reason": None}


def agent_bindings(lead: dict) -> list[dict]:
    """Obtain IDs only from paired, completed Agent receipts, never model text."""
    if lead["parse_errors"] or lead["unpaired_calls"] or lead["unpaired_returns"]:
        raise ValueError("Agent receipts require valid paired records")
    calls = {e["callId"]: e for e in lead["events"] if e["type"] == "function_call" and e["name"] == "Agent"}
    bindings = []
    for e in lead["events"]:
        if e["type"] != "function_call_result" or e["name"] != "Agent":
            continue
        ids = re.findall(r"\[Agent ID:\s*(agent-[A-Za-z0-9-]+)\]", e.get("output", ""))
        if e["callId"] not in calls or e.get("status") != "completed" or len(ids) != 1 or not ID.fullmatch(ids[0]):
            raise ValueError("missing, ambiguous or unfinished Agent receipt")
        bindings.append({"call_id": e["callId"], "member_id": ids[0],
                         "call_line": calls[e["callId"]]["line"], "receipt_line": e["line"]})
    if len(bindings) != len(calls) or len({b["member_id"] for b in bindings}) != len(bindings):
        raise ValueError("missing or duplicate Agent member binding")
    return bindings


def collect(projects: Path, session_id: str | None, member_id: str | None, output: Path) -> dict:
    if bool(session_id) == bool(member_id):
        raise ValueError("provide exactly one session_id or member_id")
    first = locate(projects, session_id or member_id)
    bindings = []
    paths = [first]
    if session_id:
        lead = project(first)
        bindings = agent_bindings(lead)
        for identifier in sorted(b["member_id"] for b in bindings):
            path = first.parent / first.stem / "subagents" / (identifier + ".jsonl")
            if not path.is_file() or not no_links(path) or not path.resolve().is_relative_to(projects.resolve()):
                raise ValueError("missing or unsafe member record: " + identifier)
            paths.append(path)
    output.mkdir(parents=True, exist_ok=True)
    if not no_links(output):
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
    if session_id and files[0]["sha256"] != lead["sha256"]:
        raise ValueError("lead changed after receipt projection")
    manifest = {"schema": "workbuddy-collection/v2", "files": files,
                "projects_root": str(projects.resolve()), "lead_id": session_id,
                "bindings": bindings}
    for name, data in (("collection.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
                       ("SHA256SUMS", "".join(f"{f['sha256']}  {Path(f['copy']).name}\n" for f in files))):
        target = output / name
        if target.exists() and (target.is_symlink() or target.read_text() != data):
            raise ValueError("existing collection metadata differs")
        if not target.exists():
            target.write_text(data, encoding="utf-8")
    return manifest


def verify_collection(lead: dict, members: list[dict], manifest_path: Path | None, projects: Path | None) -> dict:
    """Recheck a caller-selected trusted local source. A manifest alone is not provenance."""
    needed = bool(members or any(e.get("name") == "Agent" for e in lead["events"]))
    if not needed:
        return {"state": "NOT_REQUIRED", "bindings": []}
    if manifest_path is None or projects is None:
        return {"state": "BLOCKED", "reason": "MEMBER_PROVENANCE_UNVERIFIED"}
    try:
        if not no_links(manifest_path):
            raise ValueError("linked collection metadata")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("collection must be an object")
        if manifest.get("schema") not in ("workbuddy-collection/v1", "workbuddy-collection/v2"):
            raise ValueError("unsupported collection schema")
        entries = manifest["files"]
        if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
            raise ValueError("collection files must be objects")
        leads = [e for e in entries if e["role"] == "lead"]
        if len(leads) != 1 or len(entries) != len(members) + 1:
            raise ValueError("collection member count mismatch")
        declared_source = Path(leads[0]["source"])
        if not declared_source.resolve().is_relative_to(projects.resolve()) or not no_links(declared_source):
            raise ValueError("unsafe declared lead source")
        if not projects.is_dir() or not declared_source.is_file():
            raise FileNotFoundError("source unavailable")
        source = locate(projects, declared_source.stem)
        if source.resolve() != Path(leads[0]["source"]).resolve():
            raise ValueError("lead source is outside selected projects root")
        bindings = agent_bindings(lead)
        expected = {str(source.resolve()): "lead"}
        for binding in bindings:
            p = source.parent / source.stem / "subagents" / (binding["member_id"] + ".jsonl")
            expected[str(p.resolve())] = "member"
        if len(expected) != len(entries):
            raise ValueError("receipt member set differs from collection")
        records = {str(Path(r["source"]).resolve()): r for r in [lead, *members]}
        if len(records) != len(entries):
            raise ValueError("duplicate supplied record")
        seen_sources, seen_copies = set(), set()
        for entry in entries:
            src, dst = Path(entry["source"]), Path(entry["copy"])
            if not no_links(src) or not no_links(dst):
                raise ValueError("linked record path")
            src_key, dst_key = str(src.resolve()), str(dst.resolve())
            if src_key in seen_sources or dst_key in seen_copies:
                raise ValueError("duplicate collection entry")
            seen_sources.add(src_key); seen_copies.add(dst_key)
            if expected.get(src_key) != entry["role"] or dst_key not in records:
                raise ValueError("record does not belong to this Agent receipt")
            if not (sha256(src.read_bytes()) == sha256(dst.read_bytes()) == entry["sha256"] == records[dst_key]["sha256"]):
                raise ValueError("source/copy/projection hash mismatch")
        if manifest["schema"] == "workbuddy-collection/v2" and (
                manifest.get("bindings") != bindings or manifest.get("lead_id") != source.stem
                or manifest.get("projects_root") != str(projects.resolve())):
            raise ValueError("collection binding metadata mismatch")
        verified_members = [{"record_source": str(Path(e["copy"]).resolve()),
                             "call_id": next(b["call_id"] for b in bindings if b["member_id"] == Path(e["source"]).stem)}
                            for e in entries if e["role"] == "member"]
        return {"state": "VERIFIED", "bindings": bindings, "members": verified_members,
                "manifest_sha256": sha256(manifest_path.read_bytes()), "projects_root": str(projects.resolve()),
                "scope": "TRUSTED_LOCAL_SOURCE_RECHECK_NOT_CRYPTOGRAPHIC_ORIGIN_PROOF"}
    except OSError as exc:
        return {"state": "BLOCKED", "reason": "MEMBER_SOURCE_UNAVAILABLE", "detail": type(exc).__name__}
    except (ValueError, KeyError, TypeError) as exc:
        return {"state": "FAIL", "reason": "MEMBER_BINDING_MISMATCH", "detail": str(exc)}
