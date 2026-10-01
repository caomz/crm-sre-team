#!/usr/bin/env python3
"""Audit this local repaired branch against the exact original 2.5.0 upload.

This does not claim that the upload is the current GitHub HEAD. A missing or
mismatching baseline is a failure, never synthesized or reported as PASS.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ("agents/", "skills/", "templates/", "manual-mode/", "individual-packages/")
EDITABLE_ROOT = {"VERSION", "README.md", "MIGRATION.md", "MODIFICATIONS.md", "CHANGELOG.md", "VALIDATION.md", "manual-team-config.json", "prompt-bundles.lock", ".codebuddy-plugin/plugin.json"}


def read(p: Path): return json.loads(p.read_text(encoding="utf-8"))
def sha(p: Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(root: Path):
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*")) if p.is_file() and not any(n in p.parts for n in ["__pycache__", ".pytest_cache", ".git", ".venv", "dist", "reports"]) and p.suffix != ".pyc" and p.name != ".DS_Store"}


def run(root: Path, baseline: Path) -> dict:
    expected = read(root / "source-baseline.json")["files"]
    errors = []
    if not (baseline / "VERSION").is_file():
        return {"pass": False, "errors": ["BASELINE_MISSING"], "scope": "BASELINE_NOT_RUN"}
    old, new = snapshot(baseline), snapshot(root)
    if old != expected: errors.append("BASELINE_DOES_NOT_MATCH_ORIGINAL_UPLOAD")
    if (baseline / "VERSION").read_text(encoding="utf-8").strip() != "2.5.0": errors.append("BASELINE_VERSION_MISMATCH")
    added = sorted(set(new) - set(old))
    deleted = sorted(set(old) - set(new))
    modified = sorted(n for n in set(old) & set(new) if old[n] != new[n])
    omitted_reports=set(read(root / "release-manifest.json").get("excluded_generated_reports", []))
    unexpected_deleted=[n for n in deleted if n not in omitted_reports]
    if unexpected_deleted: errors.append("ORIGINAL_FILES_DELETED:" + ",".join(unexpected_deleted))
    protected = []
    for name in old:
        if name.startswith(("schemas/", "avatars/", "tests/fixtures/")) or (name.startswith("tests/") and name.endswith(".py")) or name == "requirements-build.txt":
            protected.append(name)
            if new.get(name) != old[name]: errors.append("PROTECTED_BYTES_CHANGED:" + name)
    for name in modified:
        permitted = name in EDITABLE_ROOT or name.startswith(GENERATED + ("policy-source/", "policies/", "tools/", "docs/")) or (name.startswith("tests/") and not name.endswith(".py"))
        if not permitted: errors.append("UNREVIEWED_MODIFICATION:" + name)
    manifest = set(read(root / "release-manifest.json")["files"])
    for name in added:
        if name not in manifest: errors.append("UNDECLARED_ADDITION:" + name)
    return {"pass": not errors, "scope": "ORIGINAL_UPLOAD_TO_LOCAL_REPAIR_NOT_GITHUB_HEAD", "protected_files": len(protected), "added": added, "modified": modified, "deleted": deleted, "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run(args.root.resolve(), args.baseline.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    raise SystemExit(0 if result["pass"] else 1)
