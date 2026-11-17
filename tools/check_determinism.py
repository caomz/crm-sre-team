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
sys.path.insert(0, str(ROOT / "tools"))
import release_rules  # noqa: E402

def declared_comparison_files(root: Path) -> list[str]:
    manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    names = release_rules.manifest_names(root)
    reports = manifest.get("excluded_generated_reports", [])
    if not isinstance(reports, list) or not all(
            isinstance(n, str) and n.startswith("tests/") and release_rules.safe_relative(n)
            for n in reports):
        raise ValueError("Unsafe generated-report declaration")
    return sorted(set(names) | set(reports))


def comparison_file(root: Path, name: str) -> Path:
    path = root / name
    if release_rules.is_link(path) or any(
            release_rules.is_link(p) for p in path.parents if p.is_relative_to(root)):
        raise ValueError("Linked comparison input: " + name)
    if path.exists() and not path.is_file():
        raise ValueError("Nonregular comparison input: " + name)
    return path


def copy_declared(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in declared_comparison_files(root):
        source = comparison_file(root, name)
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for name in declared_comparison_files(root):
        path = comparison_file(root, name)
        if path.is_file():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def changes(before: dict, after: dict) -> dict:
    return {"added": sorted(set(after)-set(before)), "deleted": sorted(set(before)-set(after)),
            "modified": sorted(k for k in set(before)&set(after) if before[k] != after[k])}

def invoke(root: Path, script: str, args: tuple = (), *, reverse: bool = False, expect: int = 0) -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="731" if reverse else "23")
    if reverse:
        wrapper = '''from pathlib import Path
import runpy, sys
for name in ("glob", "rglob", "iterdir"):
    original = getattr(Path, name)
    def reversed_iterator(self, *args, _original=original, **kwargs):
        return iter(reversed(list(_original(self, *args, **kwargs))))
    setattr(Path, name, reversed_iterator)
sys.argv = ["tools/validate_bundle.py", *sys.argv[1:]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
        command = [sys.executable, "-c", wrapper, *args]
    else:
        command = [sys.executable, script, *args]
    completed = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True,
                               encoding="utf-8", timeout=120)
    if completed.returncode != expect:
        raise RuntimeError(f"{script} exit={completed.returncode}, expected={expect}\n{completed.stdout}\n{completed.stderr}")
    return {"exit_code": completed.returncode, "summary": json.loads(completed.stdout)}

def _negative_sorting_guard(copy: Path, target: str | None = None) -> dict:
    """Prove the AST guard catches regression even after rebuilding the changed
    source. The anchor lives in the retained workbuddy branch but the traversal
    guard itself is target-independent."""
    validator_path = copy / "tools/validate_bundle.py"
    validator = validator_path.read_text(encoding="utf-8")
    target_args = ("--target", target) if target else ()
    target = 'sorted((root/"templates").glob("*.md"))'
    if target not in validator:
        raise RuntimeError("Sorting-negative-test anchor missing; update the test explicitly.")
    validator_path.write_text(validator.replace(target, '(root/"templates").glob("*.md")', 1), encoding="utf-8", newline="\n")
    invoke(copy, "tools/build_bundle.py", target_args)
    guard_run = invoke(copy, "tools/validate_bundle.py", target_args, expect=1)
    guard_report = json.loads((copy / "tests/static-checks.json").read_text(encoding="utf-8"))
    guard_errors = [x["id"] for x in guard_report["checks"] if not x["passed"]]
    guard_detected = "validator_sorted_filesystem_traversal" in guard_errors
    return {"exit_code": guard_run["exit_code"], "detected": guard_detected, "failed_check_ids": guard_errors}

def _run_checks_dsh(root: Path) -> dict:
    """Active DSH determinism: repeated dsh outputs + total lock, repeated DSH
    ZIP bytes, and deterministic DSH validation in isolated copies. It never
    runs the WorkBuddy gate as DSH evidence."""
    root = root.resolve()
    original = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="crm-release-determinism-") as temporary:
        copy = Path(temporary) / "release"
        copy_declared(root, copy)
        initial = snapshot(copy)
        build1 = invoke(copy, "tools/build_bundle.py")
        first = snapshot(copy)
        build2 = invoke(copy, "tools/build_bundle.py")
        second = snapshot(copy)
        tracked_names = ["prompt-bundles.lock"] + sorted(n for n in first if n.startswith("dsh/"))
        tracked_equal = all(first[name] == second[name] for name in tracked_names)
        zip1 = invoke(copy, "tools/build_release.py", ("--output", "dist/determinism-zip-a.zip"))
        zip2 = invoke(copy, "tools/build_release.py", ("--output", "dist/determinism-zip-b.zip"))
        zip_a = copy / "dist/determinism-zip-a.zip"
        zip_b = copy / "dist/determinism-zip-b.zip"
        zip_sha = hashlib.sha256(zip_a.read_bytes()).hexdigest()
        zip_deterministic = zip_sha == hashlib.sha256(zip_b.read_bytes()).hexdigest()
        validate_zip = invoke(copy, "tools/validate_release.py", ("--zip", "dist/determinism-zip-a.zip"))
        normal1 = invoke(copy, "tools/validate_bundle.py")
        validation1 = snapshot(copy)
        normal2 = invoke(copy, "tools/validate_bundle.py")
        validation2 = snapshot(copy)
        reversed_run = invoke(copy, "tools/validate_bundle.py", reverse=True)
        validation3 = snapshot(copy)
        reports = ["tests/static-checks.json"]
        guard = _negative_sorting_guard(copy)
        result = {
            "scope": "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS",
            "target": "dsh",
            "version": json.loads((root / "policy-source/dsh/package-source.json").read_text(encoding="utf-8")).get("version"),
            "transient_exclusions": ["__pycache__", "*.pyc", ".DS_Store", ".pytest_cache", ".git", ".venv", "dist", "reports"],
            "checked_files": len(tracked_names), "hashes": {name: first[name] for name in tracked_names},
            "generated_artifacts_deterministic": tracked_equal,
            "release_tree_deterministic": first == second,
            "input_release_already_built": initial == first,
            "zip_deterministic": zip_deterministic,
            "zip_sha256": zip_sha,
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
            "zip_exit_codes": [zip1["exit_code"], zip2["exit_code"]],
            "validate_zip_exit_code": validate_zip["exit_code"],
            "validation_exit_codes": [normal1["exit_code"], normal2["exit_code"], reversed_run["exit_code"]],
            "sorting_guard_negative_test": guard,
            "source_tree_unchanged_during_comparisons": snapshot(root) == original,
            "report_scope_note": "Whole-tree comparisons apply to temporary snapshots around each operation, not to a self-referential hash of this report or the final outer ZIP. DSH determinism compares the dsh outputs, the total lock and repeated DSH ZIP bytes; it does not run WorkBuddy gates as DSH evidence.",
        }
        result["pass"] = all(result[k] for k in ["generated_artifacts_deterministic", "release_tree_deterministic", "input_release_already_built", "zip_deterministic", "validation_output_deterministic", "validation_tree_deterministic", "source_tree_unchanged_during_comparisons"]) and guard["detected"]
        return result

def _run_checks_workbuddy(root: Path) -> dict:
    root = root.resolve()
    original = snapshot(root)
    with tempfile.TemporaryDirectory(prefix="crm-release-determinism-") as temporary:
        copy = Path(temporary) / "release"
        copy_declared(root, copy)
        initial = snapshot(copy)
        build1 = invoke(copy, "tools/build_bundle.py", ("--target", "workbuddy"))
        first = snapshot(copy)
        build2 = invoke(copy, "tools/build_bundle.py", ("--target", "workbuddy"))
        second = snapshot(copy)
        tracked_names = ["prompt-bundles.lock"] + sorted(n for n in first if n.startswith("individual-packages/") and n.endswith("/skill.zip"))
        tracked_equal = all(first[name] == second[name] for name in tracked_names)
        # Capture all reporting outputs, not only static-checks.json. The branch
        # pins --target workbuddy so an explicit legacy run stays self-consistent
        # even on a manifest whose default_target is dsh.
        normal1 = invoke(copy, "tools/validate_bundle.py", ("--target", "workbuddy"))
        validation1 = snapshot(copy)
        normal2 = invoke(copy, "tools/validate_bundle.py", ("--target", "workbuddy"))
        validation2 = snapshot(copy)
        reversed_run = invoke(copy, "tools/validate_bundle.py", ("--target", "workbuddy"), reverse=True)
        validation3 = snapshot(copy)
        reports = ["tests/static-checks.json", "tests/contract-test-results.txt", "tests/reasoning-matrix-results.json", "tests/judgment-matrix-results.json"]
        guard = _negative_sorting_guard(copy, target="workbuddy")
        result = {
            "scope": "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS",
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
            "sorting_guard_negative_test": guard,
            "source_tree_unchanged_during_comparisons": snapshot(root) == original,
            "report_scope_note": "Whole-tree comparisons apply to temporary snapshots around each operation, not to a self-referential hash of this report or the final outer ZIP.",
        }
        result["pass"] = all(result[k] for k in ["generated_artifacts_deterministic", "release_tree_deterministic", "input_release_already_built", "validation_output_deterministic", "validation_tree_deterministic", "source_tree_unchanged_during_comparisons"]) and guard["detected"]
        result["version"] = (root / "VERSION").read_text(encoding="utf-8").strip()
        return result

def run_checks(root: Path = ROOT, *, target: str | None = None) -> dict:
    resolved = release_rules.target_name(Path(root), target)
    if resolved == "dsh":
        return _run_checks_dsh(Path(root).resolve())
    if resolved == "workbuddy":
        return _run_checks_workbuddy(Path(root).resolve())
    raise ValueError("Unknown release target: " + str(resolved))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target", choices=["dsh", "workbuddy"], default=None,
                        help="Override the manifest default_target (default: dsh)")
    args = parser.parse_args()
    report = run_checks(args.root, target=args.target)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
