"""python3 -m tools.acceptance {collect,audit,report,ledger}; local only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from jsonschema.exceptions import ValidationError

from .audit import audit
from .ledger import append
from .records import collect


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("output cannot be a symlink")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def report(paths: list[Path], output: Path) -> dict:
    audits = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    rows = ["# WorkBuddy 验收汇总", "", "仅机械取证；语义与人工复核另记。", "",
            "| 用例 | 结论 | 关键失败 | 证据 |", "|---|---|---|---|"]
    for path, data in zip(paths, audits):
        rows.append(f"| {data['case']} | {data['result']} | {data['critical_failure']} | {path} |")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("output cannot be a symlink")
    output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return {"cases": len(audits), "critical_failures": sum(a["critical_failure"] for a in audits), "report": str(output)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("collect")
    c.add_argument("--projects", type=Path, default=Path.home() / ".workbuddy/projects")
    ids = c.add_mutually_exclusive_group(required=True)
    ids.add_argument("--session-id")
    ids.add_argument("--member-id")
    c.add_argument("--output", type=Path, required=True)
    a = commands.add_parser("audit")
    a.add_argument("--lead", type=Path, required=True)
    a.add_argument("--member", type=Path, action="append", default=[])
    a.add_argument("--spec", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    r = commands.add_parser("report")
    r.add_argument("audits", type=Path, nargs="+")
    r.add_argument("--output", type=Path, required=True)
    l = commands.add_parser("ledger")
    l.add_argument("--ledger", type=Path, required=True)
    l.add_argument("--run", type=Path, required=True)
    l.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[2] / "schemas/eval-ledger.schema.json")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            result = collect(args.projects, args.session_id, args.member_id, args.output)
        elif args.command == "audit":
            result = audit(args.lead, args.member, json.loads(args.spec.read_text(encoding="utf-8")))
            write_json(args.output, result)
        elif args.command == "report":
            result = report(args.audits, args.output)
        else:
            result = append(args.ledger, json.loads(args.run.read_text(encoding="utf-8")), args.schema)
        print(json.dumps(result if args.command != "audit" else
                         {k: result[k] for k in ("case", "result", "critical_failure", "critical_findings", "quality_findings", "review_required")},
                         ensure_ascii=False, indent=2))
        return 1 if args.command == "audit" and result["result"] == "FAIL" or args.command == "ledger" and not result["ratchet"]["ok"] else 0
    except (OSError, ValueError, KeyError, ValidationError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
