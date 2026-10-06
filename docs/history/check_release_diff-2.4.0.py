#!/usr/bin/env python3
"""Audit the 2.3.1 -> 2.4.0 contract extension against a real extracted baseline.

Allows only the enumerated additions and source edits. Projects the new common
Schema back to the old contract to prove prior conditions were not weakened.
This is an offline source audit, not authentication, a Harness or host acceptance.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ("agents/", "skills/", "templates/", "manual-mode/", "individual-packages/")
REPORTS = {"tests/static-checks.json", "tests/contract-test-results.txt", "tests/rebuild-check.json",
           "tests/validator-negative-test.json", "tests/prompt-patch-check.json", "tests/upgrade-audit.json",
           "tests/reasoning-matrix-results.json", "tests/judgment-matrix-results.json", "tests/release-diff-check.json"}
EDITABLE = {"README.md", "MIGRATION.md", "CHANGELOG.md", "MODIFICATIONS.md", "VALIDATION.md", "tools/README.md",
            "tools/validate_bundle.py", "tools/build_bundle.py", "tools/check_determinism.py", "tools/check_release_diff.py",
            "tests/test_reasoning_matrix.py", "tests/behavior-cases.md", "tests/harness-acceptance-checklist.md",
            "docs/01-diagnosis-resolution.md", "docs/03-integration-contract.md", "docs/06-ooda-reasoning.md",
            "docs/07-reproducible-validation.md", "schemas/common.schema.json", "tests/behavior-cases.json",
            "tests/harness-acceptance-cases.json", "policies/runtime-contract.json",
            "tests/fixtures/member-valid.json", "tests/fixtures/lead-valid.json"}
ADDITIONS = {"policies/judgment.json", "policy-source/references/judgment-basis.md", "docs/08-judgment-basis.md",
             "tests/test_judgment_contracts.py", "tests/test_judgment_matrix.py", "tests/judgment-evaluation-cases.json",
             "tests/fixtures/legacy-2.3.1-member-valid.json", "tests/fixtures/legacy-2.3.1-lead-valid.json",
             "docs/prompts-2.3.1-to-2.4.0.patch"}
PROMPT_EDITABLE = {"policy-source/prompts/common.md", "policy-source/references/evidence-protocol.md",
                   "policy-source/references/harness-contract.md", "policy-source/references/output-templates.md",
                   "policy-source/templates/evidence-request.md"}
ARCHIVE_SOURCES = ["README.md", "MIGRATION.md", "MODIFICATIONS.md", "VALIDATION.md", "CHANGELOG.md",
                   "tests/static-checks.json", "tests/contract-test-results.txt", "tests/reasoning-matrix-results.json",
                   "tests/rebuild-check.json", "tests/validator-negative-test.json", "tests/prompt-patch-check.json",
                   "tests/upgrade-audit.json", "tests/release-diff-check.json", "tools/check_release_diff.py"]
ARCHIVES = {f"docs/history/{Path(p).stem}-2.3.1{Path(p).suffix}": p for p in ARCHIVE_SOURCES}
HISTORY_PREFIX = "历史记录，非 2.4.0 结论。\n\n"

def read(root: Path, rel: str):
    return json.loads((root / rel).read_text(encoding="utf-8"))

def manifest(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if "__pycache__" in path.parts or path.name == ".DS_Store" or path.suffix == ".pyc":
            continue
        if path.is_symlink(): raise ValueError(f"Symlink not allowed: {path.relative_to(root)}")
        if path.is_file(): result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result

def functions(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: ast.dump(node, include_attributes=False) for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

def audit(baseline: Path, root: Path = ROOT) -> dict:
    baseline, root = baseline.resolve(), root.resolve()
    old, new = manifest(baseline), manifest(root)
    added, deleted = sorted(set(new)-set(old)), sorted(set(old)-set(new))
    modified = sorted(n for n in set(old)&set(new) if old[n] != new[n])
    violations = []
    def ensure(ok: bool, path: str, reason: str):
        if not ok: violations.append({"path": path, "reason": reason})
    ensure((baseline / "VERSION").read_text(encoding="utf-8").strip() == "2.3.1", "VERSION", "Baseline must be 2.3.1")
    ensure((root / "VERSION").read_text(encoding="utf-8").strip() == "2.4.0", "VERSION", "Release must be 2.4.0")
    for name in deleted: ensure(False, name, "File deletion is forbidden")
    for name in added:
        ensure(name in ADDITIONS or name in ARCHIVES or name in REPORTS or name.startswith(GENERATED), name, "Unexpected added source")
        if name in ARCHIVES:
            expected = (baseline / ARCHIVES[name]).read_bytes()
            if name.endswith(".md"): expected = HISTORY_PREFIX.encode("utf-8") + expected
            ensure((root / name).read_bytes() == expected, name, "History not an exact archival copy")
    for name in modified:
        if name.startswith(GENERATED) or name == "prompt-bundles.lock" or name in REPORTS or name in EDITABLE or name in PROMPT_EDITABLE:
            continue
        if name.startswith(("policy-source/prompts/roles/", "policy-source/skills/", "policy-source/manual/")):
            continue
        if name == "VERSION" or name.startswith("policy-source/"):
            ensure((root / name).read_bytes().replace(b"2.4.0", b"2.3.1") == (baseline / name).read_bytes(), name, "Only current version stamps may change outside the prompt allowlist")
        elif name.startswith("policies/") or name in {".codebuddy-plugin/plugin.json", "manual-team-config.json"}:
            a, b = read(baseline, name), read(root, name)
            ensure(b.get("version") == "2.4.0", name, "Wrong version")
            a.pop("version", None); b.pop("version", None)
            ensure(a == b, name, "Unplanned metadata or policy semantic change")
        else:
            ensure(False, name, "Not in the source-diff allowlist")
    # Prove preservation of all old definitions, properties, conditions, and required entries.
    original = read(baseline, "schemas/common.schema.json")
    projected = deepcopy(read(root, "schemas/common.schema.json"))
    defs = projected["$defs"]
    added_defs = {"judgment_question", "reference_basis", "case_specific_factor"}
    ensure(set(defs) == set(original["$defs"]) | added_defs, "schemas/common.schema.json", "Unexpected definition set")
    try:
        for name in added_defs: del defs[name]
        for name, fields in {"candidate": ["judgment_questions"], "evidence_effect": ["reference_basis", "case_specific_factors"], "request": ["discriminates_between"]}.items():
            for field in fields:
                del defs[name]["properties"][field]; defs[name]["required"].remove(field)
        old_conditions = original["$defs"]["evidence_effect"]["allOf"]
        ensure(len(defs["evidence_effect"]["allOf"]) == len(old_conditions)+1, "schemas/common.schema.json", "Expected one new no-reference condition")
        defs["evidence_effect"]["allOf"] = defs["evidence_effect"]["allOf"][:len(old_conditions)]
        schema_extension_only = projected == original
    except (KeyError, ValueError):
        schema_extension_only = False
    ensure(schema_extension_only, "schemas/common.schema.json", "Old contract projection changed; possible weakened constraint")
    unchanged_result_schemas = all((baseline / f"schemas/{name}.schema.json").read_bytes() == (root / f"schemas/{name}.schema.json").read_bytes()
                                   for name in ("member-result", "lead-result", "feedback"))
    ensure(unchanged_result_schemas, "schemas/", "Outer result or feedback Schema changed")
    # Original tests and helpers cannot be edited to make new rules pass.
    a, b = functions(baseline / "tests/test_contracts.py"), functions(root / "tests/test_contracts.py")
    for name, value in a.items(): ensure(b.get(name) == value, "tests/test_contracts.py:"+name, "Original function AST changed")
    old_tests = [name for name in a if name.startswith("test_")]
    # Only supplement matrix fixture fields, not expected outcomes or dimensions.
    matrix_new = (root / "tests/test_reasoning_matrix.py").read_text(encoding="utf-8")
    matrix_extra = '                "reference_basis": deepcopy(base["evidence_effects"][0]["reference_basis"]),\n                "case_specific_factors": [],\n'
    matrix_preserved = matrix_new.replace(matrix_extra, "", 1) == (baseline / "tests/test_reasoning_matrix.py").read_text(encoding="utf-8")
    ensure(matrix_preserved, "tests/test_reasoning_matrix.py", "Old matrix changed beyond new required fixture fields")
    # Old contexts/controls are identical; only the optional extension is allowed.
    ar, br = read(baseline, "policies/runtime-contract.json"), read(root, "policies/runtime-contract.json")
    ar.pop("version"); br.pop("version")
    ensure(br.pop("optional_trusted_context_fields", None) == ["reference_context"], "policies/runtime-contract.json", "Optional context must be explicit and not required")
    extension = br.pop("optional_context_rules", None)
    ensure(isinstance(extension, dict) and set(extension) == {"reference_context"}, "policies/runtime-contract.json", "Unexpected optional context rules")
    ensure(ar == br, "policies/runtime-contract.json", "Existing required context, roles or controls changed")
    for rel in (".codebuddy-plugin/plugin.json", "manual-team-config.json", "policies/roles.json", "policies/limits.json", "policies/workflows.json", "policies/reasoning.json", "policies/review-card-catalog.json"):
        av, bv = read(baseline, rel), read(root, rel); av.pop("version", None); bv.pop("version", None)
        ensure(av == bv, rel, "Existing authority, policy or metadata changed")
    # Preserve agent/skill frontmatter, role IDs and all avatars exactly.
    for name in old:
        if name.startswith("avatars/"): ensure(new.get(name) == old[name], name, "Avatar modified")
        if name.startswith("policy-source/prompts/roles/") or name.startswith("policy-source/skills/"):
            av, bv = (baseline / name).read_text(encoding="utf-8"), (root / name).read_text(encoding="utf-8")
            ensure(yaml.safe_load(av.split("---", 2)[1]) == yaml.safe_load(bv.split("---", 2)[1]), name, "Frontmatter/permissions modified")
    ensure(new.get("policy-source/roles-source.json") == old.get("policy-source/roles-source.json"), "policy-source/roles-source.json", "Role bindings changed")
    # Enriched fixtures must project exactly to their old nonempty examples.
    for name in ("member-valid", "lead-valid"):
        rel = f"tests/fixtures/{name}.json"; av, bv = read(baseline, rel), deepcopy(read(root, rel))
        for c in bv["candidates"]:
            c.pop("judgment_questions", None)
            for e in c["evidence_effects"]: e.pop("reference_basis", None); e.pop("case_specific_factors", None)
        for q in bv["request_proposals"]: q.pop("discriminates_between", None)
        ensure(av == bv, rel, "Old fixture changed beyond new required fields")
        legacy = f"tests/fixtures/legacy-2.3.1-{name}.json"
        ensure((root / legacy).read_bytes() == (baseline / rel).read_bytes(), legacy, "Legacy input must be exact baseline")
    for rel, count, total in [("tests/behavior-cases.json", 28, 36), ("tests/harness-acceptance-cases.json", 30, 38)]:
        av, bv = read(baseline, rel), read(root, rel)
        if isinstance(av, dict):
            aa, bb = deepcopy(av), deepcopy(bv); av, bv = av["cases"], bv["cases"]
            aa.pop("cases"); bb.pop("cases"); aa.pop("schema_version"); bb.pop("schema_version")
            ensure(aa == bb, rel, "Existing execution/description metadata changed")
        ensure(len(bv) == total and bv[:count] == av, rel, "Original B/T scenarios changed or count incorrect")
        ensure(all(c["status"] == "NOT_RUN_IN_TARGET_HOST" for c in bv), rel, "Target behavior overclaimed")
    old_builder = (baseline / "tools/build_bundle.py").read_text(encoding="utf-8")
    new_builder = (root / "tools/build_bundle.py").read_text(encoding="utf-8")
    ensure(new_builder.replace(',"tests/judgment-evaluation-cases.json"', '', 1) == old_builder, "tools/build_bundle.py", "Only evaluation-source lock coverage may change")
    old_det = (baseline / "tools/check_determinism.py").read_text(encoding="utf-8")
    new_det = (root / "tools/check_determinism.py").read_text(encoding="utf-8")
    ensure(new_det.replace(', "tests/judgment-matrix-results.json"', '', 1) == old_det, "tools/check_determinism.py", "Old determinism checks modified")
    ensure("settings.json" not in new, "settings.json", "Deferred setting was created")
    return {"scope": "CONTRACT_EXTENSION_SOURCE_AUDIT_NOT_MODEL_OR_HOST_ACCEPTANCE", "original_version": "2.3.1", "revised_version": "2.4.0",
            "pass": not violations, "files": {"original": len(old), "release": len(new), "added": len(added), "modified": len(modified), "deleted": len(deleted),
                                               "unchanged": len(set(old)&set(new))-len(modified)},
            "added": added, "modified": modified, "deleted": deleted,
            "schema_extension_only": schema_extension_only, "outer_result_schema_bytes_unchanged": unchanged_result_schemas,
            "original_test_functions_preserved": len(old_tests), "original_helper_functions_preserved": len(a)-len(old_tests),
            "original_reasoning_matrix_only_fixture_extended": matrix_preserved, "violations": violations}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True); parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); report = audit(args.baseline, args.root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
