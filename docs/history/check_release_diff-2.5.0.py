#!/usr/bin/env python3
"""Audit 2.4.0 -> 2.5.0 against a real baseline; no runtime assertions."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
GENERATED=("agents/","skills/","templates/","manual-mode/","individual-packages/")
REPORTS={"tests/static-checks.json","tests/contract-test-results.txt","tests/rebuild-check.json","tests/validator-negative-test.json",
         "tests/prompt-patch-check.json","tests/release-diff-check.json","tests/upgrade-audit.json","tests/reasoning-matrix-results.json","tests/judgment-matrix-results.json"}
EDITABLE={"VERSION",".codebuddy-plugin/plugin.json","manual-team-config.json","README.md","MIGRATION.md","MODIFICATIONS.md","CHANGELOG.md","VALIDATION.md",
          "tools/README.md","tools/build_bundle.py","tools/validate_bundle.py","tools/check_release_diff.py","docs/07-reproducible-validation.md","prompt-bundles.lock"}
ADDED={"policies/thinking-tools.json","policy-source/thinking-tools/user-excerpt.json","policy-source/thinking-tools/baseline-contract.json",
       "policy-source/references/thinking-tools.md","tools/check_thinking_tools.py","tests/test_thinking_tools.py","tests/thinking-tools-cases.json",
       "docs/09-thinking-tools-assignment.md","docs/10-thinking-tools-acceptance.md","docs/prompts-2.4.0-to-2.5.0.patch"}
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot(r):return {p.relative_to(r).as_posix():sha(p) for p in sorted(r.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.name!=".DS_Store"}
def norm_version(d):d=dict(d);d.pop("version",None);return d

def run(root,baseline):
    old=snapshot(baseline);new=snapshot(root);errors=[]
    def ensure(ok,rel,why):
        if not ok:errors.append(rel+": "+why)
    ensure((baseline/"VERSION").read_text(encoding="utf-8").strip()=="2.4.0","VERSION","Expected real 2.4.0 baseline")
    ensure((root/"VERSION").read_text(encoding="utf-8").strip()=="2.5.0","VERSION","Expected 2.5.0 output")
    added=sorted(set(new)-set(old));deleted=sorted(set(old)-set(new));modified=sorted(k for k in set(old)&set(new) if old[k]!=new[k])
    ensure(not deleted,"file_set","No original files may be deleted")
    for rel in added:ensure(rel in ADDED or rel.startswith(GENERATED) or rel.startswith("docs/history/"),rel,"Unexpected new source")
    for rel in modified:
        permitted=rel in EDITABLE or rel in REPORTS or rel.startswith(GENERATED) or rel.startswith("policy-source/") or rel.startswith("policies/")
        ensure(permitted,rel,"Unexpected source modification")
    # File-level protection is checked directly against the real baseline, not only a self-declared fingerprint.
    preserved=[]
    for rel in old:
        immutable=rel.startswith(("schemas/","avatars/","tests/fixtures/")) or (rel.startswith("tests/") and rel.endswith(".py"))
        immutable=immutable or rel in {"policy-source/roles-source.json","requirements-build.txt","tests/behavior-cases.json","tests/behavior-cases.md",
            "tests/harness-acceptance-cases.json","tests/harness-acceptance-checklist.md","tests/judgment-evaluation-cases.json","tools/check_determinism.py"}
        if immutable:ensure(old[rel]==new.get(rel),rel,"Protected baseline bytes changed");preserved.append(rel)
        if rel.startswith("policies/") or rel in {".codebuddy-plugin/plugin.json","manual-team-config.json"}:
            ensure(norm_version(read(baseline/rel))==norm_version(read(root/rel)),rel,"Existing authority/metadata changed beyond version")
    # Strip only newly added sections and current-version markers; old prompt boundaries must remain verbatim.
    for rel in old:
        if not rel.startswith("policy-source/") or not rel.endswith(".md"):continue
        before=(baseline/rel).read_text(encoding="utf-8")
        after=(root/rel).read_text(encoding="utf-8")
        if rel=="policy-source/prompts/common.md":after=after.split("\n## 思考工具选择（课程概念，不是执行工具）",1)[0].rstrip()+"\n"
        if rel.startswith(("policy-source/prompts/roles/","policy-source/skills/")):
            after=re.sub(r"## 思考工具分工（按材料触发）\n.*?(?=## )","",after,count=1,flags=re.S)
            suffix="\n按需参考：[思考工具与数据判断](references/thinking-tools.md)。只读对应分工，不全量加载课程。\n"
            after=after.removesuffix(suffix)
        if rel.startswith("policy-source/manual/"):
            after=re.sub(r"思考工具分工：.*?(?=## 已排除)","",after,count=1,flags=re.S)
        if rel=="policy-source/references/source-index.md":
            after=after.split("\n## 本版用户提供的思考工具来源",1)[0]
            after=re.sub(r"\d{4}-\d{2}-\d{2} 本次仅修订本地包","2026-09-21 本次仅修订本地包",after,count=1)
        after=after.replace("· 2.5.0","· 2.4.0").replace("版本：2.5.0","版本：2.4.0").replace("同为 2.5.0","同为 2.4.0")
        ensure(before.rstrip()==after.rstrip(),rel,"Pre-existing prompt/reference content changed beyond additive sections/version")
    return {"scope":"REAL_BASELINE_SOURCE_AUDIT_NOT_MODEL_OR_HOST_ACCEPTANCE","original_version":"2.4.0","revised_version":"2.5.0","pass":not errors,
            "files":{"original":len(old),"release":len(new),"added":len(added),"modified":len(modified),"deleted":len(deleted),"unchanged":len(set(old)&set(new))-len(modified)},
            "added":added,"modified":modified,"deleted":deleted,"immutable_files_checked":len(preserved),"schemas_byte_identical":all(old[k]==new.get(k) for k in old if k.startswith("schemas/")),
            "old_test_sources_byte_identical":all(old[k]==new.get(k) for k in old if k.startswith("tests/") and k.endswith(".py")),"errors":sorted(errors)}
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=ROOT);parser.add_argument("--baseline",type=Path,required=True);parser.add_argument("--output",type=Path);args=parser.parse_args()
    report=run(args.root.resolve(),args.baseline.resolve())
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(report,ensure_ascii=False,indent=2));raise SystemExit(0 if report["pass"] else 1)
