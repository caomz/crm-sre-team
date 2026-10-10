"""Offline schema/policy tests only; NOT target-model or production tests."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT=Path(__file__).resolve().parents[1]

def load(path: str): return json.loads((ROOT/path).read_text(encoding="utf-8"))

class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schemas=[json.loads(p.read_text(encoding="utf-8")) for p in (ROOT/"schemas").glob("*.json")]
        for schema in schemas: Draft202012Validator.check_schema(schema)
        registry=Registry().with_resources((s["$id"],Resource.from_contents(s)) for s in schemas)
        cls.validators={kind:Draft202012Validator(load(f"schemas/{kind}.schema.json"),registry=registry) for kind in ["member-result","lead-result","feedback"]}
    def valid(self,kind,value): return not list(self.validators[kind].iter_errors(value))
    def fixture(self,name="member-valid"): return deepcopy(load(f"tests/fixtures/{name}.json"))
    def test_01_valid_member(self): self.assertTrue(self.valid("member-result",self.fixture()))
    def test_02_valid_lead(self): self.assertTrue(self.valid("lead-result",self.fixture("lead-valid")))
    def test_03_valid_blocked(self): self.assertTrue(self.valid("member-result",self.fixture("member-blocked")))
    def test_04_valid_feedback(self): self.assertTrue(self.valid("feedback",self.fixture("feedback-valid")))
    def test_05_authority_fields_rejected(self):
        for field in ["result_id","receipt","approved","executed","next_phase"]:
            with self.subTest(field=field):
                v=self.fixture();v[field]="MODEL_VALUE"
                self.assertFalse(self.valid("member-result",v))
    def test_06_four_quadrants_required(self):
        for field in ["facts","candidates","pending","excluded"]:
            with self.subTest(field=field):
                v=self.fixture();del v[field]
                self.assertFalse(self.valid("member-result",v))
    def test_07_member_max_two(self):
        v=self.fixture();v["request_proposals"]*=3
        self.assertFalse(self.valid("member-result",v))
    def test_08_lead_max_three(self):
        v=self.fixture("lead-valid");v["request_proposals"]*=4
        self.assertFalse(self.valid("lead-result",v))
    def test_09_nested_command_field_rejected(self):
        v=self.fixture();v["facts"][0]["command"]="SYNTHETIC_FORBIDDEN_FIELD"
        self.assertFalse(self.valid("member-result",v))
    def test_10_fact_requires_reference(self):
        v=self.fixture();v["facts"][0]["evidence_refs"]=[]
        self.assertFalse(self.valid("member-result",v))
    def test_11_invalid_e_id_format(self):
        v=self.fixture();v["evidence_refs"][0]["evidence_id"]="MADE_UP"
        self.assertFalse(self.valid("member-result",v))
    def test_12_revision_positive(self):
        v=self.fixture();v["evidence_refs"][0]["revision"]=0
        self.assertFalse(self.valid("member-result",v))
    def test_13_counterevidence_status_required(self):
        v=self.fixture();del v["candidates"][0]["counterevidence_status"]
        self.assertFalse(self.valid("member-result",v))
    def test_14_present_requires_counterevidence(self):
        v=self.fixture();v["candidates"][0]["counterevidence_status"]="PRESENT"
        self.assertFalse(self.valid("member-result",v))
    def test_15_not_obtained_cannot_have_counterevidence(self):
        v=self.fixture();v["candidates"][0]["counterevidence_refs"]=v["evidence_refs"]
        self.assertFalse(self.valid("member-result",v))
    def test_16_falsification_required(self):
        v=self.fixture();del v["candidates"][0]["falsification_condition"]
        self.assertFalse(self.valid("member-result",v))
    def test_17_alternative_not_empty(self):
        v=self.fixture();v["candidates"][0]["critical_alternatives"]=[]
        self.assertFalse(self.valid("member-result",v))
    def test_18_exclusion_requires_scope(self):
        v=self.fixture();v["excluded"]=[{"hypothesis":"合成排除","domain":"java","evidence_refs":v["evidence_refs"],"reason":"合成理由","cannot_exclude":"其他范围","basis_claim_ids":[]}]
        self.assertFalse(self.valid("member-result",v))
    def test_19_blocked_cannot_have_facts(self):
        v=self.fixture("member-blocked");v["facts"]=self.fixture()["facts"]
        self.assertFalse(self.valid("member-result",v))
    def test_20_ok_requires_task_id(self):
        v=self.fixture();v["task_id"]=None
        self.assertFalse(self.valid("member-result",v))
    def test_21_self_route_not_in_enum(self):
        v=self.fixture("lead-valid");v["routing_proposals"]=[{"agent_id":"telecom-crm-sre-team-lead","reason":"self","pointing_evidence_refs":[],"explicit_narrow_task":None}]
        self.assertFalse(self.valid("lead-result",v))
    def test_22_routing_max_three(self):
        v=self.fixture("lead-valid");v["routing_proposals"]=[{"agent_id":"telecom-crm-oracle-dba","reason":"synthetic","pointing_evidence_refs":v["evidence_refs"],"explicit_narrow_task":None}]*4
        self.assertFalse(self.valid("lead-result",v))
    def test_23_feedback_cannot_write_approved(self):
        v=self.fixture("feedback-valid");v["approved"]=True
        self.assertFalse(self.valid("feedback",v))
    def test_24_action_report_requires_revision_when_bound(self):
        v=self.fixture("feedback-valid");v.update(feedback_type="APPROVAL_REPORT",action_id="A01",action_revision=None)
        self.assertFalse(self.valid("feedback",v))
    def test_25_policy_declares_no_executor(self):
        p=load("policies/runtime-contract.json")
        self.assertFalse(p["production_executor"]);self.assertEqual(p["production_tools"],[])
        self.assertEqual(p["implementation_status"],"NOT_IMPLEMENTED")
    def test_26_policy_declares_no_p2_to_p5(self):
        p=load("policies/workflows.json")
        self.assertEqual(len(p["phases"]),8)
        self.assertNotIn("P5",p["allowed_edges"]["P2"])
        self.assertFalse(p["emergency_reminder_changes_diagnostic_phase"])
    def test_27_policy_declares_k8s_both_conditions(self):
        p=load("policies/roles.json")["roles"]["telecom-crm-k8s-platform"]
        self.assertEqual(set(p["prerequisites"]),{"K8S_DEPLOYMENT_CONFIRMED","PLATFORM_EVIDENCE_RELEVANT"})
    def test_28_policy_declares_limits_not_bypassed(self):
        p=load("policies/limits.json")
        self.assertEqual((p["max_specialists_per_batch"],p["max_member_requests_per_logical_task"],p["max_user_requests_per_collection_round"]),(3,2,3))
        self.assertFalse(p["quotas_reset_on_model_retry"])
    def test_29_schema_alone_does_not_enforce_role_semantics(self):
        # Important residual risk: this is structurally valid but must be rejected by a real role gate.
        v=self.fixture();v["candidates"][0]["domain"]="oracle"
        self.assertTrue(self.valid("member-result",v))
    def test_30_schema_alone_does_not_prove_evidence_exists(self):
        # A syntactically valid ID can still be absent from the real incident ledger.
        v=self.fixture();v["evidence_refs"][0]["evidence_id"]="E999999"
        self.assertTrue(self.valid("member-result",v))

    def _reasoning_fixture(self, name="member-valid", effect="SUPPORTS", direction="UP"):
        value = self.fixture(name)
        c = value["candidates"][0]
        t, f = {
            "SUPPORTS": ("COMMON", "UNCOMMON"),
            "STRONGLY_SUPPORTS": ("COMMON", "UNCOMMON"),
            "WEAKENS": ("UNCOMMON", "COMMON"),
            "STRONGLY_WEAKENS": ("UNCOMMON", "COMMON"),
            "NEUTRAL": ("COMMON", "COMMON"),
            "UNKNOWN": ("UNKNOWN", "UNKNOWN"),
        }[effect]
        e = c["evidence_effects"][0]
        e.update(effect=effect, expected_if_true=t, expected_if_false=f)
        c["posterior_direction"] = direction
        weakening = effect in {"WEAKENS", "STRONGLY_WEAKENS"}
        c["counterevidence_status"] = "PRESENT" if weakening else "NOT_OBTAINED"
        c["counterevidence_refs"] = [deepcopy(e["evidence_ref"])] if weakening else []
        return value

    def test_31_new_fields_valid(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            with self.subTest(kind=kind):
                v = self.fixture(name)
                self.assertTrue(self.valid(kind, v))
                self.assertEqual(v["candidates"][0]["evidence_effects"][0]["evidence_ref"], v["candidates"][0]["support_refs"][0])
                self.assertEqual(v["request_proposals"][0]["target_candidate_refs"], ["H01"])

    def test_32_posterior_direction_required_and_enum(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for bad in [None, "HIGHER", "up", "", 1]:
                with self.subTest(kind=kind, bad=bad):
                    v = self.fixture(name)
                    if bad is None:
                        del v["candidates"][0]["posterior_direction"]
                    else:
                        v["candidates"][0]["posterior_direction"] = bad
                    self.assertFalse(self.valid(kind, v))
            for direction in ["UP", "DOWN", "UNCHANGED", "INDETERMINATE"]:
                with self.subTest(kind=kind, direction=direction):
                    v = self._reasoning_fixture(name, "WEAKENS" if direction == "DOWN" else "SUPPORTS", direction)
                    self.assertTrue(self.valid(kind, v))

    def test_33_candidate_ref_required_and_pattern(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for bad in [None, "X01", "H1", "h01", "L1", "", 1]:
                with self.subTest(kind=kind, bad=bad):
                    v = self.fixture(name)
                    if bad is None:
                        del v["candidates"][0]["candidate_ref"]
                    else:
                        v["candidates"][0]["candidate_ref"] = bad
                    self.assertFalse(self.valid(kind, v))
            for ref in ["H01", "H001", "H12345", "L01"]:
                with self.subTest(kind=kind, ref=ref):
                    v = self.fixture(name)
                    v["candidates"][0].update(candidate_ref=ref, posterior_direction="INDETERMINATE")
                    self.assertTrue(self.valid(kind, v))

    def test_34_local_candidate_direction(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for direction in ["UP", "DOWN", "UNCHANGED", "INDETERMINATE"]:
                with self.subTest(kind=kind, direction=direction):
                    v = self._reasoning_fixture(name, "WEAKENS" if direction == "DOWN" else "SUPPORTS", direction)
                    v["candidates"][0]["candidate_ref"] = "L01"
                    self.assertEqual(self.valid(kind, v), direction == "INDETERMINATE")

    def test_35_direction_requires_corresponding_effect(self):
        cases = [("UP", "NEUTRAL", False), ("DOWN", "SUPPORTS", False),
                 ("UP", "SUPPORTS", True), ("UP", "STRONGLY_SUPPORTS", True),
                 ("DOWN", "WEAKENS", True), ("DOWN", "STRONGLY_WEAKENS", True)]
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for direction, effect, accepted in cases:
                with self.subTest(kind=kind, direction=direction, effect=effect):
                    self.assertEqual(self.valid(kind, self._reasoning_fixture(name, effect, direction)), accepted)

    def test_36_effect_rules_positive_and_negative(self):
        # Exhaust all expected-value pairs and effects, including either-side UNKNOWN.
        levels = ["COMMON", "UNCOMMON", "UNKNOWN"]
        effects = ["STRONGLY_SUPPORTS", "SUPPORTS", "NEUTRAL", "WEAKENS", "STRONGLY_WEAKENS", "UNKNOWN"]
        known = {("COMMON", "COMMON"): {"NEUTRAL"},
                 ("UNCOMMON", "COMMON"): {"WEAKENS", "STRONGLY_WEAKENS"},
                 ("COMMON", "UNCOMMON"): {"SUPPORTS", "STRONGLY_SUPPORTS"},
                 ("UNCOMMON", "UNCOMMON"): {"UNKNOWN"}}
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for t in levels:
                for f in levels:
                    allowed = {"UNKNOWN"} if "UNKNOWN" in (t, f) else known[(t, f)]
                    for effect in effects:
                        with self.subTest(kind=kind, expected_if_true=t, expected_if_false=f, effect=effect):
                            v = self._reasoning_fixture(name, effect, "UNCHANGED")
                            v["candidates"][0]["evidence_effects"][0].update(expected_if_true=t, expected_if_false=f)
                            self.assertEqual(self.valid(kind, v), effect in allowed)

    def test_37_evidence_effects_bounds_and_closed_items(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for mutation in ["missing", "empty", "too_many", "extra", "bad_id", "bad_revision", "missing_locator"]:
                with self.subTest(kind=kind, mutation=mutation):
                    v = self.fixture(name); c = v["candidates"][0]
                    if mutation == "missing": del c["evidence_effects"]
                    elif mutation == "empty": c["evidence_effects"] = []
                    elif mutation == "too_many": c["evidence_effects"] *= 13
                    elif mutation == "extra": c["evidence_effects"][0]["extra"] = True
                    elif mutation == "bad_id": c["evidence_effects"][0]["evidence_ref"]["evidence_id"] = "X001"
                    elif mutation == "bad_revision": c["evidence_effects"][0]["evidence_ref"]["revision"] = 0
                    else: del c["evidence_effects"][0]["evidence_ref"]["locator"]
                    self.assertFalse(self.valid(kind, v))
            for field in ["evidence_ref", "effect", "expected_if_true", "expected_if_false", "reason"]:
                with self.subTest(kind=kind, missing=field):
                    v = self.fixture(name); del v["candidates"][0]["evidence_effects"][0][field]
                    self.assertFalse(self.valid(kind, v))
            for length in [0, 1, 600, 601]:
                with self.subTest(kind=kind, reason_length=length):
                    v = self.fixture(name); v["candidates"][0]["evidence_effects"][0]["reason"] = "合" * length
                    self.assertEqual(self.valid(kind, v), 1 <= length <= 600)
            for field in ["effect", "expected_if_true", "expected_if_false"]:
                with self.subTest(kind=kind, enum_field=field):
                    v = self.fixture(name); v["candidates"][0]["evidence_effects"][0][field] = "INVALID_ENUM"
                    self.assertFalse(self.valid(kind, v))
            v = self.fixture(name); v["candidates"][0]["evidence_effects"] *= 12
            self.assertTrue(self.valid(kind, v))

    def test_38_host_owned_fields_rejected(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for field in ["prior_level", "candidate_status", "status", "probability"]:
                with self.subTest(kind=kind, candidate_field=field):
                    v = self.fixture(name); v["candidates"][0][field] = "MODEL_VALUE"
                    self.assertFalse(self.valid(kind, v))
            for field in ["prior_level", "candidate_status", "ooda_cycle_id", "probability"]:
                with self.subTest(kind=kind, root_field=field):
                    v = self.fixture(name); v[field] = "MODEL_VALUE"
                    self.assertFalse(self.valid(kind, v))
            self.assertTrue(self.valid(kind, self.fixture(name)))  # Existing task status stays valid.

    def test_39_request_required_fields_and_bounds(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for field in ["target_candidate_refs", "if_positive", "if_negative"]:
                with self.subTest(kind=kind, missing=field):
                    v = self.fixture(name); del v["request_proposals"][0][field]
                    self.assertFalse(self.valid(kind, v))
            for refs in [[], ["H01"] * 4, ["X01"], ["H1"], ["h01"], [1]]:
                with self.subTest(kind=kind, refs=refs):
                    v = self.fixture(name); v["request_proposals"][0]["target_candidate_refs"] = refs
                    self.assertFalse(self.valid(kind, v))
            v = self.fixture(name); v["request_proposals"][0]["target_candidate_refs"] = ["H01", "H02", "L01"]
            self.assertTrue(self.valid(kind, v))  # Existence is deliberately not a Schema check.
            for field in ["if_positive", "if_negative"]:
                for length in [0, 1, 1000, 1001]:
                    with self.subTest(kind=kind, field=field, length=length):
                        v = self.fixture(name); v["request_proposals"][0][field] = "合" * length
                        self.assertEqual(self.valid(kind, v), 1 <= length <= 1000)

    def test_40_reasoning_policy_and_context(self):
        p = load("policies/reasoning.json")
        self.assertEqual(p["version"], (ROOT/"VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(p["status"], "CONTRACT_ONLY_NOT_RUNTIME_ENFORCED")
        self.assertIs(p["ooda_is_within_task_not_phase"], True)
        self.assertEqual(p["ooda_cycle_id_source"], "HOST_COUNTER")
        for key in ["model_may_increment_ooda_cycle", "model_may_write_candidate_status", "model_may_write_prior", "model_may_output_numeric_probability"]:
            self.assertIs(p[key], False)
        self.assertEqual(p["host_candidate_status_values"], ["LEADING", "PLAUSIBLE", "WEAKENED", "PENDING", "EXCLUDED_WITH_SCOPE"])
        self.assertEqual(p["prior_values"], ["UNKNOWN", "LOW", "MEDIUM", "HIGH"])
        self.assertEqual(p["first_cycle_prior"], "UNKNOWN")
        self.assertEqual(p["prior_from_previous_status"], {"LEADING":"HIGH", "PLAUSIBLE":"MEDIUM", "WEAKENED":"LOW", "PENDING":"UNKNOWN", "EXCLUDED_WITH_SCOPE":"LOW"})
        self.assertEqual(p["candidate_ref_pattern"], "^[HL][0-9]{2,}$")
        self.assertEqual(p["evidence_delta_keys"], ["added", "revised", "invalidated", "requests_satisfied", "requests_unobtainable", "new_accepted_claim_ids", "conflicts_opened"])
        self.assertEqual(p["current_candidates_item_keys"], ["candidate_ref", "status", "prior"])
        expected_rules = [("ANY_UNKNOWN", "ANY_UNKNOWN", {"UNKNOWN"}),
                          ("COMMON", "COMMON", {"NEUTRAL"}),
                          ("UNCOMMON", "COMMON", {"WEAKENS", "STRONGLY_WEAKENS"}),
                          ("COMMON", "UNCOMMON", {"SUPPORTS", "STRONGLY_SUPPORTS"}),
                          ("UNCOMMON", "UNCOMMON", {"UNKNOWN"})]
        self.assertEqual(len(p["effect_rules"]), len(expected_rules))
        for rule, (t, f, effects) in zip(p["effect_rules"], expected_rules):
            self.assertEqual(set(rule), {"expected_if_true", "expected_if_false", "allowed_effects"})
            self.assertEqual((rule["expected_if_true"], rule["expected_if_false"], set(rule["allowed_effects"])), (t, f, effects))
        self.assertEqual(set(p["stop_events_host_owned"]), {"NO_INFORMATION_GAIN", "BLOCKED", "RECOVERY_ONLY", "CONFIRMED"})
        self.assertIn("limits.max_no_gain_completed_rounds", p["stop_events_host_owned"]["NO_INFORMATION_GAIN"])
        self.assertEqual(p["host_checks"], ["H##存在于本任务 current_candidates", "L##在输出内唯一", "target_candidate_refs 只指向本任务 H## 或本输出 L##", "evidence_ref 存在且属于授权集合", "SUPPORTS 类 effect 的 E 须在 support_refs，WEAKENS 类须在 counterevidence_refs", "UP/DOWN 须至少一项对应 effect 的 E 在本轮 evidence_delta 的 added 或 revised 中", "evidence_delta 为空时只接受 UNCHANGED 或 INDETERMINATE", "同一 E 的重复支持只计一次", "状态与先验只由宿主写"])
        r = load("policies/runtime-contract.json")
        self.assertEqual(r["trusted_context_fields"][-3:], ["ooda_cycle_id", "evidence_delta", "current_candidates"])
        self.assertEqual(r["implementation_status"], "NOT_IMPLEMENTED")

    def test_41_schema_cannot_resolve_candidate_registry(self):
        # Residual risk, not approval: only the host has current_candidates and incident identity.
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            with self.subTest(kind=kind, risk="unknown_H"):
                v = self.fixture(name); v["candidates"][0]["candidate_ref"] = "H999999"
                self.assertTrue(self.valid(kind, v))
            with self.subTest(kind=kind, risk="duplicate_L"):
                v = self.fixture(name); v["candidates"][0].update(candidate_ref="L01", posterior_direction="INDETERMINATE")
                v["candidates"].append(deepcopy(v["candidates"][0]))
                self.assertTrue(self.valid(kind, v))
            for missing_target in ["H999999", "L999999"]:
                with self.subTest(kind=kind, risk="unresolved_target", target=missing_target):
                    v = self.fixture(name); v["request_proposals"][0]["target_candidate_refs"] = [missing_target]
                    self.assertTrue(self.valid(kind, v))

    def test_42_schema_cannot_prove_expectations_or_delta(self):
        # The synthetic host facts below never enter the model-result Schema.
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for direction, effect in [("UP", "SUPPORTS"), ("DOWN", "WEAKENS")]:
                for host_delta in [{"added": [], "revised": []}, {"added": ["E999"], "revised": []}]:
                    with self.subTest(kind=kind, direction=direction, host_delta=host_delta):
                        v = self._reasoning_fixture(name, effect, direction)
                        self.assertTrue(self.valid(kind, v))  # A real host must reject the stale E001 trigger.
            with self.subTest(kind=kind, risk="invented_expectation"):
                v = self.fixture(name)
                self.assertTrue(self.valid(kind, v))  # No Schema can prove the COMMON/UNCOMMON labels true.

    def test_43_counterevidence_effect_consistency(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            for effect in ["WEAKENS", "STRONGLY_WEAKENS"]:
                with self.subTest(kind=kind, weakening=effect):
                    v = self._reasoning_fixture(name, effect, "DOWN")
                    self.assertTrue(self.valid(kind, v))
                    v["candidates"][0].update(counterevidence_status="NOT_OBTAINED", counterevidence_refs=[])
                    self.assertFalse(self.valid(kind, v))
            for effect in ["SUPPORTS", "STRONGLY_SUPPORTS", "NEUTRAL", "UNKNOWN"]:
                with self.subTest(kind=kind, nonweakening=effect):
                    v = self._reasoning_fixture(name, effect, "UNCHANGED")
                    self.assertTrue(self.valid(kind, v))
                    c = v["candidates"][0]
                    c.update(counterevidence_status="PRESENT", counterevidence_refs=[deepcopy(c["evidence_effects"][0]["evidence_ref"])])
                    self.assertFalse(self.valid(kind, v))


    def test_44_legacy_nonempty_candidate_requires_new_fields(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            with self.subTest(kind=kind):
                value = self.fixture(name)
                value["request_proposals"] = []  # Isolate candidate migration, not request migration.
                for field in ["candidate_ref", "posterior_direction", "evidence_effects"]:
                    del value["candidates"][0][field]
                self.assertFalse(self.valid(kind, value))

    def test_45_legacy_nonempty_request_requires_new_fields(self):
        for kind, name in [("member-result", "member-valid"), ("lead-result", "lead-valid")]:
            with self.subTest(kind=kind):
                value = self.fixture(name)  # Candidate retains its valid current shape.
                for field in ["target_candidate_refs", "if_positive", "if_negative"]:
                    del value["request_proposals"][0][field]
                self.assertFalse(self.valid(kind, value))

    def test_46_empty_candidate_blocked_shape_remains_schema_compatible(self):
        value = self.fixture("member-blocked")
        self.assertEqual(value["status"], "blocked")
        self.assertEqual(value["candidates"], [])
        self.assertEqual(value["request_proposals"], [])
        self.assertTrue(self.valid("member-result", value))


if __name__=="__main__": unittest.main(verbosity=2)
