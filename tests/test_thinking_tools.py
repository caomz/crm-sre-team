"""Static assignment regression and mutation tests, not executed behavior cases."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
ROOT=Path(__file__).resolve().parents[1]
def load(rel):return json.loads((ROOT/rel).read_text(encoding="utf-8"))
spec=importlib.util.spec_from_file_location("assignment_checker_under_test",ROOT/"tools/check_thinking_tools.py")
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
class ThinkingToolTests(unittest.TestCase):
    def setUp(self):
        self.p=load("policies/thinking-tools.json");self.source=load("policy-source/thinking-tools/user-excerpt.json")
        self.roles=load("policy-source/roles-source.json");self.defs=load("schemas/common.schema.json")["$defs"]
    def errors(self):
        return [c["id"] for c in checker.validate_policy(self.p,self.source,self.roles,self.defs,(ROOT/"VERSION").read_text(encoding="utf-8").strip()) if not c["passed"]]
    def test_01_assignment_valid(self):self.assertEqual(self.errors(),[])
    def test_02_unknown_course_id_rejected(self):
        self.p["catalog"][0]["id"]="T999";self.assertTrue(self.errors())
    def test_03_source_name_not_silently_changed(self):
        self.p["catalog"][0]["name"]="RENAMED";self.assertTrue(self.errors())
    def test_04_source_summary_not_silently_changed(self):
        self.p["catalog"][0]["source_summary"]="ALTERED";self.assertTrue(self.errors())
    def test_05_missing_role_rejected(self):
        self.p["roles"].pop(next(iter(self.p["roles"])));self.assertTrue(self.errors())
    def test_06_wrong_skill_binding_rejected(self):
        next(iter(self.p["roles"].values()))["skill_id"]="wrong";self.assertTrue(self.errors())
    def test_07_unassigned_flow_tool_rejected(self):
        next(iter(self.p["roles"].values()))["flows"][0]["tools"]=["T999"];self.assertTrue(self.errors())
    def test_08_more_than_three_selected_rejected(self):
        next(iter(self.p["roles"].values()))["flows"][0]["tools"]=["T091","T005","T096","T032"];self.assertTrue(self.errors())
    def test_09_no_forced_tool_checklist(self):
        self.p["selection"]["min_tools_per_task"]=1;self.assertTrue(self.errors())
    def test_10_missing_material_rejected(self):
        self.p["catalog"][0]["minimum_material"]="  ";self.assertTrue(self.errors())
    def test_11_missing_uncertainty_fallback_rejected(self):
        self.p["catalog"][0]["when_insufficient"]="";self.assertTrue(self.errors())
    def test_12_every_bound_cannot_be_enabled(self):
        original=deepcopy(self.p)
        for key in checker.BOUNDS:
            with self.subTest(bound=key):
                self.p=deepcopy(original);self.p["bounds"][key]=True;self.assertTrue(self.errors())
    def test_13_unknown_output_field_rejected(self):
        self.p["catalog"][0]["existing_output_target"]="candidates.probability";self.assertTrue(self.errors())
    def test_14_catalog_verification_not_claimed(self):
        self.source["catalog_file_provided"]=True;self.assertTrue(self.errors())
    def test_15_declared_runtime_gap_cannot_disappear(self):
        self.p["known_runtime_gaps"].pop();self.assertTrue(self.errors())
    def test_16_duplicate_assignment_rejected(self):
        r=next(iter(self.p["roles"].values()));r["secondary_tools"].append(r["primary_tools"][0]);self.assertTrue(self.errors())
    def test_17_all_static_protection_checks(self):
        self.assertEqual(checker.run_checks(ROOT)["errors"],[])
    def test_18_manual_keeps_four_quadrants_and_caveat(self):
        for sid in self.roles:
            text=(ROOT/"policy-source/manual"/(sid+".md")).read_text(encoding="utf-8")
            with self.subTest(role=sid):
                self.assertEqual([l for l in text.splitlines() if l.startswith("## ")],["## 已确认事实","## 高概率候选","## 待验证","## 已排除"])
                self.assertIn("不是自动闭环",text)
    def test_19_tools_are_not_extra_model_fields(self):
        schemas=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT/"schemas").glob("*.json"))]
        registry=Registry().with_resources((s["$id"],Resource.from_contents(s)) for s in schemas)
        for kind,fixture in [("member-result","member-valid"),("lead-result","lead-valid")]:
            validator=Draft202012Validator(load("schemas/"+kind+".schema.json"),registry=registry)
            value=load("tests/fixtures/"+fixture+".json");self.assertTrue(validator.is_valid(value))
            for field in ["thinking_tools","decision_score","kelly_fraction","brier_score"]:
                with self.subTest(kind=kind,field=field):
                    mutated=deepcopy(value);mutated[field]="SYNTHETIC";self.assertFalse(validator.is_valid(mutated))
    def test_20_case_specs_have_no_fabricated_results(self):
        cases=load("tests/thinking-tools-cases.json")
        self.assertEqual(cases["execution_status"],"NOT_RUN_IN_TARGET_HOST")
        for case in cases["cases"]:
            self.assertIsNone(case["observed_output"]);self.assertEqual(case["verdict"],"NOT_SCORED")
    def test_21_schema_cannot_verify_reasoning_quality(self):
        # Explicit residual risk: empty jargon can fit a free-text field. No claim of semantic enforcement.
        schemas=[json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT/"schemas").glob("*.json"))]
        registry=Registry().with_resources((s["$id"],Resource.from_contents(s)) for s in schemas)
        validator=Draft202012Validator(load("schemas/member-result.schema.json"),registry=registry)
        value=load("tests/fixtures/member-valid.json")
        value["candidates"][0]["rank_reason"]="course:T036 says so, without explaining the comparison"
        self.assertTrue(validator.is_valid(value))
if __name__=="__main__":unittest.main(verbosity=2)
