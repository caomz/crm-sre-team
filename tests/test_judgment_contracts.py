"""Judgment-basis structural regression tests, not a Harness or semantic verifier."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
KINDS = (("member-result", "member-valid"), ("lead-result", "lead-valid"))
BASIS_TYPES = ("SAME_OBJECT_HISTORY", "PEER_OBJECTS", "NORMAL_WINDOW", "SIMILAR_INCIDENTS", "DOCUMENTED_BASELINE", "NO_REFERENCE_AVAILABLE")

def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

class JudgmentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "schemas").glob("*.json"))]
        for schema in schemas:
            Draft202012Validator.check_schema(schema)
        registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
        cls.validators = {kind: Draft202012Validator(load(f"schemas/{kind}.schema.json"), registry=registry) for kind, _ in KINDS}

    def fixture(self, name="member-valid"):
        return deepcopy(load(f"tests/fixtures/{name}.json"))

    def valid(self, value, kind="member-result"):
        return not list(self.validators[kind].iter_errors(value))

    def no_reference(self, name="member-valid"):
        value = self.fixture(name)
        c = value["candidates"][0]
        c.update(posterior_direction="INDETERMINATE", counterevidence_status="NOT_OBTAINED", counterevidence_refs=[])
        e = c["evidence_effects"][0]
        e.update(expected_if_true="UNKNOWN", expected_if_false="UNKNOWN", effect="UNKNOWN")
        e["reference_basis"].update(basis_type="NO_REFERENCE_AVAILABLE", basis_refs=[])
        return value

    def factor(self):
        return {"factor": "合成事故差异，不代表因果", "evidence_refs": self.fixture()["evidence_refs"],
                "direction": "UNKNOWN", "reason": "结构示例，未独立裁决"}

    def test_01_enriched_member_and_lead(self):
        for kind, name in KINDS:
            with self.subTest(kind=kind):
                self.assertTrue(self.valid(self.fixture(name), kind))

    def test_02_questions_required_and_array_bounds(self):
        for kind, name in KINDS:
            for count in (0, 1, 6, 7):
                with self.subTest(kind=kind, count=count):
                    v = self.fixture(name); v["candidates"][0]["judgment_questions"] *= count
                    self.assertEqual(self.valid(v, kind), 1 <= count <= 6)
            v = self.fixture(name); del v["candidates"][0]["judgment_questions"]
            self.assertFalse(self.valid(v, kind))

    def test_03_question_all_fields_required_and_closed(self):
        v = self.fixture(); fields = list(v["candidates"][0]["judgment_questions"][0])
        for field in fields:
            with self.subTest(field=field):
                v = self.fixture(); del v["candidates"][0]["judgment_questions"][0][field]
                self.assertFalse(self.valid(v))
        v = self.fixture(); v["candidates"][0]["judgment_questions"][0]["extra"] = "not permitted"
        self.assertFalse(self.valid(v))

    def test_04_question_id_and_enums(self):
        for ref, expected in [("Q01", True), ("Q100", True), ("Q1", False), ("q01", False), ("H01", False), ("", False)]:
            with self.subTest(ref=ref):
                v = self.fixture(); v["candidates"][0]["judgment_questions"][0]["question_ref"] = ref
                self.assertEqual(self.valid(v), expected)
        for field, good in [("answer_type", ["BINARY", "DIRECTIONAL", "ORDERING", "COMPARATIVE", "UNKNOWN"]),
                            ("decision_relevance", ["HIGH", "MEDIUM", "LOW"])]:
            for item in good + ["INVALID", "", 1]:
                with self.subTest(field=field, item=item):
                    v = self.fixture(); v["candidates"][0]["judgment_questions"][0][field] = item
                    self.assertEqual(self.valid(v), item in good)

    def test_05_question_answer_needs_basis(self):
        for refs in ([], self.fixture()["evidence_refs"]):
            for answer in ("UNKNOWN", "合成：先发生"):
                with self.subTest(refs=refs, answer=answer):
                    v = self.fixture(); v["candidates"][0]["judgment_questions"][0].update(basis_refs=refs, current_answer=answer)
                    self.assertEqual(self.valid(v), bool(refs) or answer == "UNKNOWN")

    def test_06_question_target_bounds_patterns_and_uniqueness(self):
        cases = [([], False), (["H01"], True), (["H01", "H02", "L01"], True), (["H01"]*4, False),
                 (["H01", "H01"], False), (["Q01"], False), (["H1"], False)]
        for refs, expected in cases:
            with self.subTest(refs=refs):
                v = self.fixture(); v["candidates"][0]["judgment_questions"][0]["target_candidate_refs"] = refs
                self.assertEqual(self.valid(v), expected)

    def test_07_reference_basis_required(self):
        for kind, name in KINDS:
            v = self.fixture(name); del v["candidates"][0]["evidence_effects"][0]["reference_basis"]
            self.assertFalse(self.valid(v, kind))

    def test_08_reference_fields_required_and_closed(self):
        for field in self.fixture()["candidates"][0]["evidence_effects"][0]["reference_basis"]:
            with self.subTest(field=field):
                v = self.fixture(); del v["candidates"][0]["evidence_effects"][0]["reference_basis"][field]
                self.assertFalse(self.valid(v))
        v = self.fixture(); v["candidates"][0]["evidence_effects"][0]["reference_basis"]["guessed_base_rate"] = "MODEL"
        self.assertFalse(self.valid(v))

    def test_09_reference_type_enum(self):
        for name in BASIS_TYPES + ("UNKNOWN_TYPE", "", 1):
            with self.subTest(basis_type=name):
                v = self.no_reference() if name == "NO_REFERENCE_AVAILABLE" else self.fixture()
                v["candidates"][0]["evidence_effects"][0]["reference_basis"]["basis_type"] = name
                self.assertEqual(self.valid(v), name in BASIS_TYPES)

    def test_10_reference_refs_condition_and_bounds(self):
        for basis in BASIS_TYPES:
            for n in (0, 1, 12, 13):
                with self.subTest(basis=basis, count=n):
                    v = self.no_reference() if basis == "NO_REFERENCE_AVAILABLE" else self.fixture()
                    v["candidates"][0]["evidence_effects"][0]["reference_basis"].update(
                        basis_type=basis, basis_refs=self.fixture()["evidence_refs"] * n)
                    self.assertEqual(self.valid(v), n == 0 if basis == "NO_REFERENCE_AVAILABLE" else 1 <= n <= 12)

    def test_11_no_reference_forces_both_unknown(self):
        for kind, name in KINDS:
            self.assertTrue(self.valid(self.no_reference(name), kind))
            for field in ("expected_if_true", "expected_if_false"):
                for label in ("COMMON", "UNCOMMON"):
                    with self.subTest(kind=kind, field=field, label=label):
                        v = self.no_reference(name); v["candidates"][0]["evidence_effects"][0][field] = label
                        self.assertFalse(self.valid(v, kind))

    def test_12_reference_does_not_force_nonunknown_expectations(self):
        # An available but uninformative reference is allowed; it is not proof of commonness.
        for t, f in [("UNKNOWN", "COMMON"), ("COMMON", "UNKNOWN"), ("UNKNOWN", "UNKNOWN")]:
            with self.subTest(true=t, false=f):
                v = self.fixture(); v["candidates"][0]["posterior_direction"] = "INDETERMINATE"
                v["candidates"][0]["evidence_effects"][0].update(expected_if_true=t, expected_if_false=f, effect="UNKNOWN")
                self.assertTrue(self.valid(v))

    def test_13_specific_factors_required_and_bounds(self):
        for count in (0, 1, 6, 7):
            with self.subTest(count=count):
                v = self.fixture(); v["candidates"][0]["evidence_effects"][0]["case_specific_factors"] = [self.factor()] * count
                self.assertEqual(self.valid(v), count <= 6)
        v = self.fixture(); del v["candidates"][0]["evidence_effects"][0]["case_specific_factors"]
        self.assertFalse(self.valid(v))

    def test_14_specific_factor_fields_and_directions(self):
        for field in self.factor():
            with self.subTest(missing=field):
                v = self.fixture(); f = self.factor(); del f[field]
                v["candidates"][0]["evidence_effects"][0]["case_specific_factors"] = [f]
                self.assertFalse(self.valid(v))
        for direction in ["FAVORS_CANDIDATE", "WEAKENS_CANDIDATE", "NO_DISCRIMINATION", "UNKNOWN", "UP", "LEADING"]:
            with self.subTest(direction=direction):
                v = self.fixture(); f = self.factor(); f["direction"] = direction
                v["candidates"][0]["evidence_effects"][0]["case_specific_factors"] = [f]
                self.assertEqual(self.valid(v), direction not in {"UP", "LEADING"})
        for n in (0, 1, 12, 13):
            v = self.fixture(); f = self.factor(); f["evidence_refs"] *= n
            v["candidates"][0]["evidence_effects"][0]["case_specific_factors"] = [f]
            self.assertEqual(self.valid(v), 1 <= n <= 12)

    def test_15_specific_story_cannot_bypass_no_reference_gate(self):
        v = self.no_reference(); c = v["candidates"][0]; e = c["evidence_effects"][0]
        e["case_specific_factors"] = [self.factor()]
        self.assertTrue(self.valid(v))
        e["case_specific_factors"][0]["direction"] = "FAVORS_CANDIDATE"
        e.update(expected_if_true="COMMON", expected_if_false="UNCOMMON", effect="SUPPORTS")
        c["posterior_direction"] = "UP"
        self.assertFalse(self.valid(v))

    def test_16_request_discrimination_required_bounds_and_format(self):
        for kind, name in KINDS:
            v = self.fixture(name); del v["request_proposals"][0]["discriminates_between"]
            self.assertFalse(self.valid(v, kind))
            cases = [([], False), (["H01"], True), (["H01", "H02", "L01"], True),
                     (["H01"]*4, False), (["H01"]*2, False), (["Q01"], False), (["L1"], False)]
            for refs, expected in cases:
                with self.subTest(kind=kind, refs=refs):
                    v = self.fixture(name); v["request_proposals"][0]["discriminates_between"] = refs
                    self.assertEqual(self.valid(v, kind), expected)

    def test_17_new_objects_reject_probability_scores_and_state(self):
        forbidden = ["probability", "host_probability", "prior_level", "candidate_status", "ooda_cycle_id",
                     "brier_score", "calibration_score", "candidate_separation", "final_adjudication"]
        for location in ("root", "question", "basis", "factor", "request"):
            for key in forbidden:
                with self.subTest(location=location, field=key):
                    v = self.fixture(); e = v["candidates"][0]["evidence_effects"][0]; e["case_specific_factors"] = [self.factor()]
                    target = {"root": v, "question": v["candidates"][0]["judgment_questions"][0],
                              "basis": e["reference_basis"], "factor": e["case_specific_factors"][0],
                              "request": v["request_proposals"][0]}[location]
                    target[key] = 0.7
                    self.assertFalse(self.valid(v))

    def test_18_new_definitions_closed_and_old_schema_valid(self):
        defs = load("schemas/common.schema.json")["$defs"]
        for name in ("judgment_question", "reference_basis", "case_specific_factor"):
            self.assertIs(defs[name]["additionalProperties"], False)
            self.assertEqual(set(defs[name]["required"]), set(defs[name]["properties"]))
        for path in sorted((ROOT / "schemas").glob("*.json")):
            Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))

    def test_19_judgment_policy_ownership(self):
        p = load("policies/judgment.json")
        self.assertEqual(p["version"], (ROOT / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(p["status"], "CONTRACT_ONLY_NOT_RUNTIME_ENFORCED")
        for key in ["numeric_probability_model_output_allowed", "model_may_write_prior", "model_may_write_candidate_status",
                    "model_may_increment_ooda_cycle", "brier_score_enabled", "offline_metrics_are_probability_calibration"]:
            self.assertIs(p[key], False)
        for key in ["fermi_decomposition_required", "fermi_is_within_task_not_phase", "reference_class_required_for_non_unknown_expectation"]:
            self.assertIs(p[key], True)
        self.assertEqual(p["calibration_owner"], "HOST_OR_OFFLINE_EVALUATOR")
        self.assertEqual(p["resolution_owner"], "HOST_OR_OFFLINE_EVALUATOR")
        self.assertEqual(p["calibration_implementation_status"], "NOT_IMPLEMENTED")
        self.assertEqual(p["reference_basis_types"], list(BASIS_TYPES))
        self.assertEqual(p["question_ref_namespace"], "OUTPUT_LOCAL_JUDGMENT_NOT_HOST_REQUEST_Q")

    def test_20_reference_context_is_trusted_but_not_required(self):
        p = load("policies/runtime-contract.json")
        self.assertNotIn("reference_context", p["trusted_context_fields"])
        self.assertEqual(p["optional_trusted_context_fields"], ["reference_context"])
        rule = p["optional_context_rules"]["reference_context"]
        self.assertEqual(rule["source"], "HOST_CONTROL_CHANNEL_ONLY")
        self.assertEqual(rule["missing_or_empty"], "CONTINUE_WITH_UNKNOWN_EXPECTATIONS_WHERE_UNSUPPORTED")
        self.assertIs(rule["reference_materials_require_authorized_evidence_refs"], True)
        self.assertEqual(p["trusted_context_fields"][-3:], ["ooda_cycle_id", "evidence_delta", "current_candidates"])
        self.assertEqual(p["implementation_status"], "NOT_IMPLEMENTED")

    def test_21_231_objects_rejected_but_empty_blocked_allowed(self):
        for kind, name in KINDS:
            old = load(f"tests/fixtures/legacy-2.3.1-{name}.json")
            self.assertFalse(self.valid(old, kind))
            for field in ("judgment_questions", "reference_basis", "case_specific_factors", "discriminates_between"):
                with self.subTest(kind=kind, missing=field):
                    v = self.fixture(name)
                    target = v["candidates"][0] if field == "judgment_questions" else v["request_proposals"][0] if field == "discriminates_between" else v["candidates"][0]["evidence_effects"][0]
                    del target[field]
                    self.assertFalse(self.valid(v, kind))
        blocked = self.fixture("member-blocked")
        self.assertTrue(self.valid(blocked))

    def test_22_residual_question_identity_and_parent_are_host_checks(self):
        v = self.fixture(); c = v["candidates"][0]
        c["judgment_questions"].append(deepcopy(c["judgment_questions"][0]))
        self.assertTrue(self.valid(v))  # Duplicate Q across/within candidates needs typed host namespace validation.
        c["judgment_questions"][0]["target_candidate_refs"] = ["H999999"]
        self.assertTrue(self.valid(v))  # H existence / parent containment is not JSON Schema data equality.

    def test_23_residual_reference_authenticity_and_comparability(self):
        v = self.fixture(); b = v["candidates"][0]["evidence_effects"][0]["reference_basis"]
        b["basis_refs"][0]["evidence_id"] = "E999999"
        b["comparison_scope"]["object_alias"] = "SYNTHETIC_OTHER_TENANT"
        self.assertTrue(self.valid(v))  # A real host must reject missing or unauthorized evidence.
        b["baseline_relation"] = "合成：参考不具备比较条件，Schema 不能理解这段含义。"
        self.assertTrue(self.valid(v))

    def test_24_residual_discrimination_subset_and_registry(self):
        v = self.fixture(); q = v["request_proposals"][0]
        q["target_candidate_refs"] = ["H01"]; q["discriminates_between"] = ["H999999"]
        self.assertTrue(self.valid(v))  # Subset and existence belong to the unimplemented host gate.
        self.assertFalse(set(q["discriminates_between"]).issubset(q["target_candidate_refs"]))

    def test_25_residual_free_text_requires_semantic_gate(self):
        v = self.fixture(); v["candidates"][0]["rank_reason"] = "合成越权文本：70% 可能，并宣称模型自算校准通过。"
        self.assertTrue(self.valid(v))  # Closed properties do not understand arbitrary prose. Do not publish this.
        q = v["request_proposals"][0]; q["if_positive"] = q["if_negative"] = "无论结果都维持相同结论"
        self.assertTrue(self.valid(v))  # The host must review real information gain.

    def test_26_evaluation_design_is_not_scored_results(self):
        d = load("tests/judgment-evaluation-cases.json")
        self.assertEqual(d["execution_status"], "NOT_RUN_IN_MODEL")
        self.assertEqual(d["scoring_status"], "NOT_SCORED")
        self.assertIs(d["numeric_probability"], False)
        self.assertEqual([c["id"] for c in d["cases"]], [f"J{i:02d}" for i in range(1, 9)])
        for case in d["cases"]:
            self.assertEqual(case["status"], "NOT_RUN_IN_MODEL")
            self.assertEqual(case["scoring_status"], "NOT_SCORED")
            self.assertTrue(case["evidence_sequence"])
            self.assertEqual(case["adjudicated_outcome"]["label"], "UNRESOLVED")
            self.assertEqual(case["adjudicated_outcome"]["source"], "SYNTHETIC_TEST_AUTHOR_NOT_REAL_RCA")

    def test_27_behavior_acceptance_designs_not_run(self):
        b = load("tests/behavior-cases.json"); a = load("tests/harness-acceptance-cases.json")
        self.assertEqual([c["id"] for c in b], [f"B{i:02d}" for i in range(1, 37)])
        self.assertEqual([c["id"] for c in a["cases"]], [f"T{i:02d}" for i in range(1, 39)])
        self.assertTrue(all(c["status"] == "NOT_RUN_IN_TARGET_HOST" for c in b + a["cases"]))
        self.assertEqual(a["schema_version"], "crm-sre-acceptance/v2.4.0")

    def test_28_string_and_evidence_ref_bounds(self):
        targets = [("question", "question", 1000), ("question", "observable", 1000),
                   ("basis", "baseline_relation", 1000), ("basis", "limitations", 1500),
                   ("factor", "factor", 600), ("factor", "reason", 600)]
        for where, field, maximum in targets:
            for length in (0, 1, maximum, maximum + 1):
                with self.subTest(where=where, field=field, length=length):
                    v = self.fixture(); e = v["candidates"][0]["evidence_effects"][0]; e["case_specific_factors"] = [self.factor()]
                    target = {"question": v["candidates"][0]["judgment_questions"][0], "basis": e["reference_basis"], "factor": e["case_specific_factors"][0]}[where]
                    target[field] = "合" * length
                    self.assertEqual(self.valid(v), 1 <= length <= maximum)
        for where in ("question", "basis", "factor"):
            v = self.fixture(); e = v["candidates"][0]["evidence_effects"][0]; e["case_specific_factors"] = [self.factor()]
            ref = deepcopy(v["evidence_refs"][0]); ref["revision"] = 0
            if where == "question": v["candidates"][0]["judgment_questions"][0]["basis_refs"] = [ref]
            elif where == "basis": e["reference_basis"]["basis_refs"] = [ref]
            else: e["case_specific_factors"][0]["evidence_refs"] = [ref]
            self.assertFalse(self.valid(v))

if __name__ == "__main__":
    unittest.main(verbosity=2)
