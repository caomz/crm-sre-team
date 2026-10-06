#!/usr/bin/env python3
"""Audit a 2.3.0 -> 2.3.1 patch against a real, separately extracted baseline.

Generated artifacts may differ, but semantic source contracts may not. This is
not a signature check; supply an authenticated baseline independently.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ("agents/", "skills/", "templates/", "manual-mode/", "individual-packages/")
REPORTS = {"tests/static-checks.json", "tests/contract-test-results.txt", "tests/rebuild-check.json",
           "tests/validator-negative-test.json", "tests/prompt-patch-check.json", "tests/upgrade-audit.json",
           "tests/reasoning-matrix-results.json", "tests/release-diff-check.json"}
EDITABLE = {"README.md", "MIGRATION.md", "CHANGELOG.md", "MODIFICATIONS.md", "VALIDATION.md",
            "tools/README.md", "tools/validate_bundle.py", "tools/build_bundle.py", "tests/test_contracts.py",
            "docs/06-ooda-reasoning.md"}
ADDITIONS = {"tools/check_determinism.py", "tools/check_release_diff.py", "tests/test_reasoning_matrix.py",
             "tests/test_validation_determinism.py", "docs/07-reproducible-validation.md",
             "docs/prompts-2.3.0-to-2.3.1.patch"}
VERSION_ONLY = {"VERSION", "tests/behavior-cases.md", "tests/harness-acceptance-checklist.md",
                "docs/01-diagnosis-resolution.md"}
ARCHIVES = {
    f"docs/history/{Path(p).stem}-2.3.0{Path(p).suffix}": p
    for p in ["README.md", "MIGRATION.md", "MODIFICATIONS.md", "VALIDATION.md", "CHANGELOG.md",
              "tests/static-checks.json", "tests/upgrade-audit.json", "tests/rebuild-check.json",
              "tests/validator-negative-test.json", "tests/prompt-patch-check.json", "tests/contract-test-results.txt"]
}
HISTORY_PREFIX = "历史记录，非 2.3.1 结论；其中迁移概括及矩阵数字请以当前文档为准。\n\n"

def manifest(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Symlink not allowed: {path.relative_to(root)}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def audit(baseline: Path, root: Path = ROOT) -> dict:
    baseline, root = baseline.resolve(), root.resolve()
    old, new = manifest(baseline), manifest(root)
    added, deleted = sorted(set(new)-set(old)), sorted(set(old)-set(new))
    modified = sorted(n for n in set(old)&set(new) if old[n] != new[n])
    violations = []
    def ensure(ok: bool, name: str, detail: str):
        if not ok: violations.append({"path": name, "reason": detail})
    ensure((baseline/"VERSION").read_text(encoding="utf-8").strip() == "2.3.0", "VERSION", "Baseline is not 2.3.0")
    ensure((root/"VERSION").read_text(encoding="utf-8").strip() == "2.3.1", "VERSION", "Release is not 2.3.1")
    for name in deleted: ensure(False, name, "File deletion is forbidden")
    for name in added:
        ensure(name in ADDITIONS or name in REPORTS or name in ARCHIVES, name, "Unexpected added path")
        if name in ARCHIVES:
            src = ARCHIVES[name]
            expected = (baseline/src).read_bytes()
            if name.endswith(".md"): expected = HISTORY_PREFIX.encode("utf-8") + expected
            ensure((root/name).read_bytes() == expected, name, "Historical copy differs from baseline")
    for name in modified:
        old_bytes, new_bytes = (baseline/name).read_bytes(), (root/name).read_bytes()
        if name.startswith(GENERATED) or name == "prompt-bundles.lock" or name in REPORTS or name in EDITABLE:
            continue
        if name.startswith("policy-source/") or name in VERSION_ONLY:
            ensure(new_bytes.replace(b"2.3.1", b"2.3.0") == old_bytes, name, "Only release-version stamps may change")
        elif name.startswith("policies/") or name in {".codebuddy-plugin/plugin.json", "manual-team-config.json"}:
            a, b = json.loads(old_bytes), json.loads(new_bytes)
            ensure(b.get("version") == "2.3.1", name, "Version not upgraded")
            a.pop("version", None); b.pop("version", None)
            ensure(a == b, name, "Policy or metadata semantics changed")
        elif name == "tests/harness-acceptance-cases.json":
            a, b = json.loads(old_bytes), json.loads(new_bytes)
            ensure(b.get("schema_version") == "crm-sre-acceptance/v2.3.1", name, "Acceptance version not upgraded")
            a.pop("schema_version", None); b.pop("schema_version", None)
            ensure(a == b, name, "Acceptance scenario semantics changed")
        else:
            ensure(False, name, "Not in the patch source-diff allowlist")
    # A broad editable-source allowance never authorizes changing original tests or build mechanics.
    def functions(path: Path) -> dict:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old_functions, new_functions = functions(baseline/"tests/test_contracts.py"), functions(root/"tests/test_contracts.py")
    for name, value in old_functions.items():
        ensure(new_functions.get(name) == value, "tests/test_contracts.py:"+name, "Pre-existing function AST changed")
    original_tests = [name for name in old_functions if name.startswith("test_")]
    schemas_unchanged = all(n in new and old[n] == new[n] for n in old if n.startswith("schemas/"))
    ensure(schemas_unchanged, "schemas/", "All Schema bytes must remain unchanged")
    old_builder = (baseline/"tools/build_bundle.py").read_text(encoding="utf-8")
    new_builder = (root/"tools/build_bundle.py").read_text(encoding="utf-8")
    extra = '    paths.extend(p for p in (root/"tests").glob("*.py"))  # Test sources only; generated reports stay outside locks.\n'
    ensure(new_builder.replace(extra, "", 1) == old_builder, "tools/build_bundle.py", "Only test-source lock coverage may change")
    ensure("settings.json" not in new, "settings.json", "Deferred setting must not be created")
    return {"scope": "PATCH_SOURCE_ALLOWLIST_AND_UNCHANGED_CONTRACTS_NOT_HOST_ACCEPTANCE",
            "original_version": "2.3.0", "revised_version": "2.3.1", "pass": not violations,
            "files": {"original": len(old), "release": len(new), "added": len(added), "modified": len(modified),
                      "deleted": len(deleted), "unchanged": len(set(old)&set(new))-len(modified)},
            "added": added, "modified": modified, "deleted": deleted,
            "schema_bytes_unchanged": schemas_unchanged, "original_test_functions_preserved": len(original_tests),
            "original_helper_functions_preserved": len(old_functions)-len(original_tests),
            "violations": violations}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.baseline, args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
