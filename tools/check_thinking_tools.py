#!/usr/bin/env python3
"""Check thinking-tool assignments and unchanged contracts locally; not a model router."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDS = {f"T{i:03d}" for i in range(23,39)} | {"T091","T005","T096","T021","T053","T087","T076"}
BOUNDS = {"new_output_fields","new_data_access","new_agent_permissions","model_numeric_probability",
          "model_prior_or_status_write","course_text_is_evidence","kelly_allocation_calculation","model_self_scoring"}
TARGET_DEFS = {"facts":"fact","candidates":"candidate","pending":"pending","request_proposals":"request",
               "review_needs":"review_need","reference_basis":"reference_basis"}

def load(path: Path): return json.loads(path.read_text(encoding="utf-8"))
def sha(path: Path): return hashlib.sha256(path.read_bytes()).hexdigest()
def normalized(value):
    value = dict(value); value.pop("version", None)
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def validate_policy(policy: dict, source: dict, role_source: dict, defs: dict, version: str) -> list[dict]:
    """Return stable structural findings. This does not judge a model's tool choice."""
    checks=[]
    def check(name, ok, detail=""):
        checks.append({"id":"thinking_tools:"+name,"passed":bool(ok),"detail":detail})
    check("version",policy.get("version")==version)
    check("not_runtime",policy.get("status")=="PROMPT_ROUTING_ONLY_NOT_RUNTIME_ENFORCED")
    check("namespace",policy.get("namespace")=="course_tools" and policy.get("display_prefix")=="course:")
    check("result_schema_unchanged",policy.get("result_schema_contract")=="UNCHANGED_FROM_2.4.0")
    ps=policy.get("source",{})
    check("source_provenance",ps.get("numbering_independently_verified") is False and ps.get("sre_assignment_is_engineering_adaptation") is True
          and source.get("provenance")=="USER_PROVIDED_EXCERPT" and source.get("catalog_file_provided") is False
          and source.get("course_full_text_provided") is False and source.get("numbering_independently_verified") is False)
    limits=policy.get("selection",{})
    check("selective_not_checklist",limits.get("min_tools_per_task")==0 and limits.get("max_tools_per_task")==3 and bool(limits.get("rule")))
    bounds=policy.get("bounds",{})
    for key in sorted(BOUNDS):check("bound:"+key,key in bounds and bounds[key] is False)
    tools=policy.get("catalog",[]); ids=[t.get("id") for t in tools]
    check("catalog_ids",set(ids)==EXPECTED_IDS and len(ids)==len(set(ids)))
    original={t["id"]:t for t in source.get("tools",[])}
    check("source_ids",set(original)==EXPECTED_IDS)
    for t in tools:
        tid=t.get("id",""); baseline=original.get(tid,{})
        check("source_name_summary:"+tid,all(t.get(k)==baseline.get(k) for k in ["name","source_summary"]))
        fields=["name","source_summary","trigger","minimum_material","judgment_question","existing_output_target","when_insufficient","adaptation_boundary"]
        check("material_and_fallback:"+tid,all(isinstance(t.get(k),str) and bool(t[k].strip()) for k in fields))
        target=t.get("existing_output_target","").split(".",1)
        correct=len(target)==2 and target[0] in TARGET_DEFS and target[1] in defs[TARGET_DEFS[target[0]]]["properties"]
        check("existing_output_target:"+tid,correct,t.get("existing_output_target", ""))
    expected_roles={v["agent"]:k for k,v in role_source.items()}
    assigned=policy.get("roles",{})
    check("role_ids",set(assigned)==set(expected_roles))
    coverage=set(); triggered=set()
    for agent,role in sorted(assigned.items()):
        primary=role.get("primary_tools",[]); secondary=role.get("secondary_tools",[]); all_ids=primary+secondary
        coverage.update(all_ids)
        check("skill_binding:"+agent,role.get("skill_id")==expected_roles.get(agent))
        check("assigned_ids:"+agent,bool(primary) and set(all_ids)<=EXPECTED_IDS and len(all_ids)==len(set(all_ids)))
        flows=role.get("flows",[])
        check("flows_exist:"+agent,bool(flows))
        for index,flow in enumerate(flows):
            selected=flow.get("tools",[]);triggered.update(selected)
            check(f"flow_ids:{agent}:{index}",1<=len(selected)<=3 and len(selected)==len(set(selected)) and set(selected)<=set(all_ids))
            check(f"flow_material:{agent}:{index}",all(isinstance(flow.get(k),str) and flow[k].strip() for k in ["trigger","material","judgment"]))
    check("all_tools_assigned",coverage==EXPECTED_IDS)
    check("all_tools_triggered",triggered==EXPECTED_IDS)
    check("runtime_gaps_preserved",set(policy.get("known_runtime_gaps",[]))=={
        "HARNESS_NOT_IMPLEMENTED","INVALIDATED_ONLY_REEVALUATION_NOT_IMPLEMENTED","NO_CANDIDATE_INTAKE_REQUEST_PATH_NOT_IMPLEMENTED",
        "STALE_RESULT_ADMISSION_NOT_IMPLEMENTED","EFFECTIVE_HOST_TOOL_PERMISSIONS_NOT_VERIFIED"})
    return sorted(checks,key=lambda c:c["id"])

def run_checks(root: Path = ROOT) -> dict:
    policy=load(root/"policies/thinking-tools.json")
    source=load(root/"policy-source/thinking-tools/user-excerpt.json")
    roles=load(root/"policy-source/roles-source.json")
    version=(root/"VERSION").read_text(encoding="utf-8").strip()
    checks=validate_policy(policy,source,roles,load(root/"schemas/common.schema.json")["$defs"],version)
    def add(name,ok,detail=""):checks.append({"id":"thinking_tools:"+name,"passed":bool(ok),"detail":detail})
    baseline=load(root/"policy-source/thinking-tools/baseline-contract.json")
    # Historical baseline stays byte-identical. Narrow, reviewed exceptions are
    # independently named and still hash-checked; schemas and old tests cannot opt out.
    add("historical_baseline_unchanged", sha(root/"policy-source/thinking-tools/baseline-contract.json") == "79e6b15abdc4f96a42f91fc9e9d8459360adc9a5478a9d4506a2f234a5713eb4")
    allowed=load(root/"policy-source/thinking-tools/workbuddy-allowed-changes.json")
    permitted={"immutable_files":{"policy-source/roles-source.json","tools/check_determinism.py"},
               "version_only_json":{"policies/runtime-contract.json",".codebuddy-plugin/plugin.json"}}
    add("allowed_change_version", allowed.get("version")==version)
    for scope in ["immutable_files","version_only_json"]:
        exceptions=allowed.get(scope,{})
        add("allowed_change_scope:"+scope, set(exceptions)==permitted[scope])
        for rel,h in sorted(baseline[scope].items()):
            actual=sha(root/rel) if scope=="immutable_files" else normalized(load(root/rel))
            exemption=exceptions.get(rel)
            if exemption:
                valid=rel in permitted[scope] and exemption.get("baseline_sha256")==h and bool(exemption.get("reason")) and actual==exemption.get("revised_sha256")
                add("reviewed_change:"+rel,valid)
            else:
                add("unchanged:"+rel, actual==h)
    for sid,role in sorted(roles.items()):
        snippets=[]
        for rel in [f"policy-source/prompts/roles/{role['agent']}.md",f"policy-source/skills/{sid}.md"]:
            text=(root/rel).read_text(encoding="utf-8")
            heading="## 思考工具分工（按材料触发）\n"
            snippet=text.split(heading,1)[1].split("\n## ",1)[0] if heading in text else ""
            snippets.append(snippet)
        add("paired_role_guidance:"+sid,bool(snippets[0]) and snippets[0]==snippets[1])
        expected=policy["roles"][role["agent"]]
        add("assigned_labels_present:"+sid,all("course:"+tid in snippets[0] for tid in expected["primary_tools"]+expected["secondary_tools"]))
    cases=load(root/"tests/thinking-tools-cases.json")
    add("case_status",cases.get("execution_status")=="NOT_RUN_IN_TARGET_HOST" and cases.get("scoring_status")=="NOT_SCORED"
        and all(c.get("status")=="NOT_RUN_IN_TARGET_HOST" and c.get("observed_output") is None and c.get("verdict")=="NOT_SCORED" for c in cases["cases"]))
    add("case_ids",[c["id"] for c in cases["cases"]]==[f"TT{i:02d}" for i in range(1,21)])
    case_tools=set()
    for case in cases["cases"]:
        selected=case["course_tools"]; case_tools.update(selected)
        role=policy["roles"].get(case["role"],{})
        add("case_assignment:"+case["id"],len(selected)<=3 and set(selected)<=set(role.get("primary_tools",[])+role.get("secondary_tools",[])))
    add("case_coverage",case_tools==EXPECTED_IDS)
    checks.sort(key=lambda c:c["id"])
    failures=[c["id"] for c in checks if not c["passed"]]
    return {"version":version,"scope":"STATIC_ASSIGNMENT_AND_CONTRACT_PRESERVATION_ONLY","result":"PASS_STATIC_ONLY" if not failures else "FAIL",
            "course_tools":len(policy["catalog"]),"roles":len(policy["roles"]),"case_specs":len(cases["cases"]),"checks_total":len(checks),
            "checks_passed":sum(c["passed"] for c in checks),"errors":failures,"checks":checks}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--root",type=Path,default=ROOT);args=parser.parse_args()
    result=run_checks(args.root.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(1 if result["errors"] else 0)
