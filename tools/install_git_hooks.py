#!/usr/bin/env python3
"""Install the versioned git hooks by pointing core.hooksPath at tools/git-hooks.

Local development setup only: touches .git/config, never tracked files, never
the network. Idempotent.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = "tools/git-hooks"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--uninstall", action="store_true", help="restore the default .git/hooks path")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    try:
        if args.uninstall:
            subprocess.run(["git", "-C", str(root), "config", "--unset", "core.hooksPath"], check=False)
            print("core.hooksPath removed; git falls back to .git/hooks")
            return
        hooks = root / HOOKS_DIR
        if not hooks.is_dir() or not (hooks / "pre-commit").is_file():
            raise SystemExit(f"Missing hook: {hooks / 'pre-commit'}")
        subprocess.run(["git", "-C", str(root), "config", "core.hooksPath", HOOKS_DIR], check=True)
        # git on Windows resolves the shebang through sh; make it executable where honored.
        try:
            (hooks / "pre-commit").chmod(0o755)
        except OSError:
            pass
        current = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"],
                                 capture_output=True, text=True, check=True).stdout.strip()
        print(f"core.hooksPath = {current}")
        print("pre-commit gate active: build-owned outputs are rebuilt and verified on every commit")
        print("bypass deliberately with: git commit --no-verify")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Hook install failed: {exc}") from exc


if __name__ == "__main__":
    main()
