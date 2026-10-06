"""Named, exhaustive-within-listed-dimensions offline matrices; not host/model tests.

Run directly to execute unittest; use --report PATH to write a stable, per-case
JSON report. Expected outcomes are calculated from the documented rules, not
from Schema condition nodes or policy.effect_rules. The official jsonschema
validator supplies actual outcomes. The matrix tests the shared candidate def.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
EXPECTATIONS = ("COMMON", "UNCOMMON", "UNKNOWN")
EFFECTS = ("STRONGLY_SUPPORTS", "SUPPORTS", "NEUTRAL", "WEAKENS", "STRONGLY_WEAKENS", "UNKNOWN")
DIRECTIONS = ("UP", "DOWN", "UNCHANGED", "INDETERMINATE")
POSITIVE = {"SUPPORTS", "STRONGLY_SUPPORTS"}
NEGATIVE = {"WEAKENS", "STRONGLY_WEAKENS"}
PROFILES = {"positive": "SUPPORTS", "negative": "WEAKENS", "neutral": "NEUTRAL", "unknown": "UNKNOWN"}
REFERENCES = ("H01", "H99", "L01", "L12", "X01", "H1", "h01", "L1")
VALID_REFERENCES = {"H01", "H99", "L01", "L12"}
VALID_EXPECTATION_PAIR = {
    "SUPPORTS": ("COMMON", "UNCOMMON"), "STRONGLY_SUPPORTS": ("COMMON", "UNCOMMON"),
    "WEAKENS": ("UNCOMMON", "COMMON"), "STRONGLY_WEAKENS": ("UNCOMMON", "COMMON"),
    "NEUTRAL": ("COMMON", "COMMON"), "UNKNOWN": ("UNKNOWN", "COMMON"),
}

def expected_effect(true: str, false: str, effect: str) -> bool:
    """Independent small oracle with ANY_UNKNOWN explicitly expressed as OR."""
    if true == "UNKNOWN" or false == "UNKNOWN":
        return effect == "UNKNOWN"
    if true == false:
        return effect == ("NEUTRAL" if true == "COMMON" else "UNKNOWN")
    return effect in (POSITIVE if true == "COMMON" else NEGATIVE)

def run_matrix(root: Path = ROOT) -> dict:
    root = root.resolve()
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "schemas").glob("*.json"))]
    for schema in schemas:
        Draft202012Validator.check_schema(schema)
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    validator = Draft202012Validator(
        {"$ref": "urn:crm-sre:schemas:common#/$defs/candidate"}, registry=registry)
    fixture = json.loads((root / "tests/fixtures/member-valid.json").read_text(encoding="utf-8"))
    base = fixture["candidates"][0]
    support_ref = deepcopy(base["support_refs"][0])
    counter_ref = deepcopy(support_ref)
    counter_ref["evidence_id"] = "E002"  # Separate synthetic counterevidence; no real ledger claim.

    def candidate(effects: tuple[str, ...], direction: str = "INDETERMINATE") -> dict:
        value = deepcopy(base)
        value.update(candidate_ref="H01", posterior_direction=direction)
        value["support_refs"] = [deepcopy(support_ref)]  # Required by existing candidate contract.
        weakening = any(effect in NEGATIVE for effect in effects)
        value["counterevidence_status"] = "PRESENT" if weakening else "NOT_OBTAINED"
        value["counterevidence_refs"] = [deepcopy(counter_ref)] if weakening else []
        value["evidence_effects"] = []
        for effect in effects:
            true, false = VALID_EXPECTATION_PAIR[effect]
            value["evidence_effects"].append({
                "evidence_ref": deepcopy(counter_ref if effect in NEGATIVE else support_ref),
                "effect": effect, "expected_if_true": true, "expected_if_false": false,
                "reason": "合成矩阵；只检查结构条件，不证明证据真实。",
                "reference_basis": deepcopy(base["evidence_effects"][0]["reference_basis"]),
                "case_specific_factors": [],
            })
        return value

    matrices = {}
    def group(name: str, dimensions: dict, isolation: str) -> dict:
        value = {"dimensions": dimensions, "isolation": isolation, "cases": 0,
                 "expected_accepts": 0, "expected_rejects": 0, "passed": 0,
                 "mismatches": 0, "results": []}
        matrices[name] = value
        return value

    def record(output: dict, inputs: dict, value: dict, expected: bool) -> None:
        errors = sorted(validator.iter_errors(value), key=lambda e:(str(list(e.absolute_path)), e.message))
        actual = not errors
        item = {"input": inputs, "expected_valid": expected, "actual_valid": actual, "passed": actual == expected}
        if actual != expected:
            item["schema_errors"] = [{"path": list(e.absolute_path), "message": e.message} for e in errors]
        output["results"].append(item)
        output["cases"] += 1
        output["expected_accepts" if expected else "expected_rejects"] += 1
        output["passed"] += int(actual == expected)
        output["mismatches"] += int(actual != expected)

    output = group("effect_mapping", {"expected_if_true": list(EXPECTATIONS), "expected_if_false": list(EXPECTATIONS), "effect": list(EFFECTS)},
                   "H01/INDETERMINATE; counterevidence status and refs follow effect, isolating expectation mapping.")
    for true, false, effect in product(EXPECTATIONS, EXPECTATIONS, EFFECTS):
        value = candidate((effect,))
        value["evidence_effects"][0].update(expected_if_true=true, expected_if_false=false)
        record(output, {"expected_if_true": true, "expected_if_false": false, "effect": effect}, value, expected_effect(true, false, effect))

    output = group("direction_minimum_evidence", {"posterior_direction": list(DIRECTIONS), "effect_profile": list(PROFILES)},
                   "H01; expectation pairs and counterevidence refs/status are consistent. Implication is not equivalence.")
    for direction, profile in product(DIRECTIONS, PROFILES):
        effect = PROFILES[profile]
        expected = (direction not in {"UP", "DOWN"} or
                    direction == "UP" and effect in POSITIVE or
                    direction == "DOWN" and effect in NEGATIVE)
        record(output, {"posterior_direction": direction, "effect_profile": profile}, candidate((effect,), direction), expected)

    output = group("candidate_reference", {"candidate_ref": list(REFERENCES), "posterior_direction": list(DIRECTIONS)},
                   "Both SUPPORTS and WEAKENS are present so direction minimum-evidence gates do not mask ref rules. Existence remains host-owned.")
    for ref, direction in product(REFERENCES, DIRECTIONS):
        value = candidate(("SUPPORTS", "WEAKENS"), direction)
        value["candidate_ref"] = ref
        expected = ref in VALID_REFERENCES and (not ref.startswith("L") or direction == "INDETERMINATE")
        record(output, {"candidate_ref": ref, "posterior_direction": direction}, value, expected)

    output = group("counterevidence_consistency", {"counterevidence_status": ["PRESENT", "NOT_OBTAINED"], "effect_profile": list(PROFILES)},
                   "H01/INDETERMINATE; counterevidence_refs follows status so the old refs constraint does not mask the new effect constraint.")
    for status, profile in product(("PRESENT", "NOT_OBTAINED"), PROFILES):
        effect = PROFILES[profile]
        value = candidate((effect,))
        value.update(counterevidence_status=status, counterevidence_refs=[deepcopy(counter_ref)] if status == "PRESENT" else [])
        expected = (status == "PRESENT") == (effect in NEGATIVE)
        record(output, {"counterevidence_status": status, "effect_profile": profile}, value, expected)

    output = group("mixed_evidence_direction", {"posterior_direction": list(DIRECTIONS), "effect_profile": ["SUPPORTS+WEAKENS"]},
                   "Both signs satisfy the respective minima; conservative UNCHANGED/INDETERMINATE is allowed, not forced to pick a sign.")
    for direction in DIRECTIONS:
        record(output, {"posterior_direction": direction, "effect_profile": "SUPPORTS+WEAKENS"}, candidate(("SUPPORTS", "WEAKENS"), direction), True)

    return {"version": (root / "VERSION").read_text(encoding="utf-8").strip(),
            "scope": "LISTED_DIMENSIONS_SHARED_CANDIDATE_SCHEMA_ONLY_NOT_HOST_SEMANTICS",
            "validator": "jsonschema.Draft202012Validator", "expected_outcome_source": "Independent documented-rule functions; not Schema condition introspection",
            "matrices": matrices, "cases_total": sum(g["cases"] for g in matrices.values()),
            "mismatches_total": sum(g["mismatches"] for g in matrices.values())}

class MatrixTests(unittest.TestCase):
    REPORT = None
    @classmethod
    def setUpClass(cls):
        if cls.REPORT is None:
            cls.REPORT = run_matrix()
    def verify_group(self, name: str) -> None:
        for item in self.REPORT["matrices"][name]["results"]:
            with self.subTest(**item["input"]):
                self.assertEqual(item["actual_valid"], item["expected_valid"], item.get("schema_errors"))
    def test_effect_mapping(self): self.verify_group("effect_mapping")
    def test_direction_minimum_evidence(self): self.verify_group("direction_minimum_evidence")
    def test_candidate_reference(self): self.verify_group("candidate_reference")
    def test_counterevidence_consistency(self): self.verify_group("counterevidence_consistency")
    def test_mixed_evidence_direction(self): self.verify_group("mixed_evidence_direction")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_matrix(args.root)
    MatrixTests.REPORT = report
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MatrixTests))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({"cases_total": report["cases_total"], "mismatches_total": report["mismatches_total"],
                      "matrices": {name: {k: g[k] for k in ["cases", "passed", "mismatches"]} for name, g in report["matrices"].items()}}, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
