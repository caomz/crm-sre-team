#!/usr/bin/env python3
"""Test build, whole-release-tree, and validation determinism in temporary copies.

The source tree is read-only during comparisons. Only --output (when provided)
is written after the comparisons. Uses the current Python/dependency environment;
this is not an assertion about identical output on all operating systems.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if any(n in path.parts for n in ["__pycache__", ".pytest_cache", ".git", ".venv", "dist", "reports"]) or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink not permitted: {path.relative_to(root)}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def changes(before: dict, after: dict) -> dict:
    return {"added": sorted(set(after)-set(before)), "deleted": sorted(set(before)-set(after)),
            "modified": sorted(k for k in set(before)&set(after) if before[k] != after[k])}

def invoke(root: Path, script: str, *, reverse: bool = False, expect: int = 0) -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="731" if reverse else "23")
    if reverse:
        wrapper = '''from pathlib import Path
import runpy, sys
for name in ("glob", "rglob", "iterdir"):
    original = getattr(Path, name)
    def reversed_iterator(self, *args, _original=original, **kwargs):
        return iter(reversed(list(_original(self, *args, **kwargs))))
    setattr(Path, name, reversed_iterator)
sys.argv = ["tools/validate_bundle.py"]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        command = [sys.executable, "-c", wrapper]
    else:
        command = [sys.executable, script]
    completed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True,
                               encoding="utf-8", timeout=120)
    if completed.returncode != expect:
        raise RuntimeError(f"{script} exit={completed.returncode}, expected={expect}\n{completed.stdout}\n{completed.stderr}")
    return {"exit_code": completed.returncode, "summary": json.loads(completed.stdout)}

def run_checks(root: Path = ROOT) -> dict:
    root = root.resolve()
    original = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="crm-release-determinism-") as temporary:
        copy = Path(temporary) / "release"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".pytest_cache", ".git", ".venv", "dist", "reports"))
        initial = snapshot(copy)
        build1 = invoke(copy, "tools/build_bundle.py")
        first = snapshot(copy)
        build2 = invoke(copy, "tools/build_bundle.py")
        second = snapshot(copy)
        tracked_names = ["prompt-bundles.lock"] + sorted(n for n in first if n.startswith("individual-packages/") and n.endswith("/skill.zip"))
        tracked_equal = all(first[name] == second[name] for name in tracked_names)
        # Capture all reporting outputs, not only static-checks.json.
        normal1 = invoke(copy, "tools/validate_bundle.py")
        validation1 = snapshot(copy)
        normal2 = invoke(copy, "tools/validate_bundle.py")
        validation2 = snapshot(copy)
        reversed_run = invoke(copy, "tools/validate_bundle.py", reverse=True)
        validation3 = snapshot(copy)
        reports = ["tests/static-checks.json", "tests/contract-test-results.txt", "tests/reasoning-matrix-results.json", "tests/judgment-matrix-results.json"]
        # Prove the AST guard catches regression even after rebuilding the changed source.
        validator_path = copy / "tools/validate_bundle.py"
        validator = validator_path.read_text(encoding="utf-8")
        target = 'sorted((root/"templates").glob("*.md"))'
        if target not in validator:
            raise RuntimeError("Sorting-negative-test anchor missing; update the test explicitly.")
        validator_path.write_text(validator.replace(target, '(root/"templates").glob("*.md")', 1), encoding="utf-8", newline="\n")
        invoke(copy, "tools/build_bundle.py")
        guard_run = invoke(copy, "tools/validate_bundle.py", expect=1)
        guard_report = json.loads((copy / "tests/static-checks.json").read_text(encoding="utf-8"))
        guard_errors = [x["id"] for x in guard_report["checks"] if not x["passed"]]
        guard_detected = "validator_sorted_filesystem_traversal" in guard_errors
        result = {
            "scope": "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS",
            "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
            "transient_exclusions": ["__pycache__", "*.pyc", ".DS_Store", ".pytest_cache", ".git", ".venv", "dist", "reports"],
            "checked_files": len(tracked_names), "hashes": {name: first[name] for name in tracked_names},
            "generated_artifacts_deterministic": tracked_equal,
            "release_tree_deterministic": first == second,
            "input_release_already_built": initial == first,
            "release_tree_file_count": len(second),
            "build_input_to_first": changes(initial, first), "build_first_to_second": changes(first, second),
            "validation_output_deterministic": all(validation1[n] == validation2[n] == validation3[n] for n in reports),
            "validation_tree_deterministic": validation1 == validation2 == validation3,
            "validation_first_to_second": changes(validation1, validation2),
            "validation_normal_to_reversed_traversal": changes(validation2, validation3),
            "validation_report_hashes": {name: validation1[name] for name in reports},
            "reversed_filesystem_iterators_tested": ["Path.glob", "Path.rglob", "Path.iterdir"],
            "hash_seeds_tested": ["23", "731"],
            "build_exit_codes": [build1["exit_code"], build2["exit_code"]],
            "validation_exit_codes": [normal1["exit_code"], normal2["exit_code"], reversed_run["exit_code"]],
            "sorting_guard_negative_test": {"exit_code": guard_run["exit_code"], "detected": guard_detected, "failed_check_ids": guard_errors},
            "source_tree_unchanged_during_comparisons": snapshot(root) == original,
            "report_scope_note": "Whole-tree comparisons apply to temporary snapshots around each operation, not to a self-referential hash of this report or the final outer ZIP.",
        }
        result["pass"] = all(result[k] for k in ["generated_artifacts_deterministic", "release_tree_deterministic", "input_release_already_built", "validation_output_deterministic", "validation_tree_deterministic", "source_tree_unchanged_during_comparisons"]) and guard_detected
        return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_checks(args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
