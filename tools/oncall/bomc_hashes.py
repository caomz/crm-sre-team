#!/usr/bin/env python3
"""Offline operator helper: print BOMC integrity pins; never query or write files."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def load_guard():
    # Compile the canonical implementation directly: no import cache/.pyc writes.
    source = Path(__file__).resolve().parents[2] / "policy-source/skills/bomc-alarm-readonly/scripts/bomc_readonly.py"
    namespace = {"__name__": "bomc_hash_helper_guard", "__file__": str(source)}
    saved = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        exec(compile(source.read_bytes(), str(source), "exec"), namespace)
    finally:
        sys.dont_write_bytecode = saved
    return namespace


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0].startswith("-"):
        print("Usage: bomc_hashes.py <absolute-skill-root>", file=sys.stderr)
        return 2
    guard = load_guard()
    try:
        root = guard["checked_config_path"](argv[0], True, "skill_root")
        skill_md = guard["checked_config_path"](str(root / "SKILL.md"), False, "SKILL.md")
        result = {
            "skill_md_sha256": guard["hashlib"].sha256(guard["read_config_bytes"](skill_md, "SKILL.md")).hexdigest(),
            "scripts_sha256": guard["scripts_sha256"](root),
        }
        print(json.dumps(result))
        return 0
    except guard["GuardError"] as exc:
        print(f"BOMC_GUARD_ERROR {exc.code}: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
