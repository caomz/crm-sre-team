"""Named judgment-basis matrices with independent expected rules and official Schema results.

These enumerate only listed dimensions. They do not verify reference truth,
request subsets, semantic information gain, or model behavior.
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
BASIS = ("SAME_OBJECT_HISTORY", "PEER_OBJECTS", "NORMAL_WINDOW", "SIMILAR_INCIDENTS", "DOCUMENTED_BASELINE", "NO_REFERENCE_AVAILABLE")
EXPECTATIONS = ("COMMON", "UNCOMMON", "UNKNOWN")
EFFECTS = ("STRONGLY_SUPPORTS", "SUPPORTS", "NEUTRAL", "WEAKENS", "STRONGLY_WEAKENS", "UNKNOWN")

def expected_mapping(t: str, f: str, effect: str) -> bool:
    if "UNKNOWN" in (t, f):
        return effect == "UNKNOWN"
    if t == f:
        return effect == ("NEUTRAL" if t == "COMMON" else "UNKNOWN")
    allowed = ("SUPPORTS", "STRONGLY_SUPPORTS") if t == "COMMON" else ("WEAKENS", "STRONGLY_WEAKENS")
    return effect in allowed

def run_matrix(root: Path = ROOT) -> dict:
    root = root.resolve()
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "schemas").glob("*.json"))]
    for s in schemas:
        Draft202012Validator.check_schema(s)
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
    validators = {name: Draft202012Validator({"$ref": f"urn:crm-sre:schemas:common#/$defs/{name}"}, registry=registry)
                  for name in ("evidence_effect", "reference_basis", "judgment_question", "request")}
    fixture = json.loads((root / "tests/fixtures/member-valid.json").read_text(encoding="utf-8"))
    base_effect = fixture["candidates"][0]["evidence_effects"][0]
    matrices = {}
    def group(name: str, dimensions: dict, isolation: str) -> dict:
        item = {"dimensions": dimensions, "isolation": isolation, "cases": 0, "expected_accepts": 0,
                "expected_rejects": 0, "passed": 0, "mismatches": 0, "results": []}
        matrices[name] = item
        return item
    def record(output: dict, name: str, inputs: dict, value: dict, expected: bool) -> None:
        errors = sorted(validators[name].iter_errors(value), key=lambda e: (str(list(e.absolute_path)), e.message))
        actual = not errors
        item = {"input": inputs, "expected_valid": expected, "actual_valid": actual, "passed": actual == expected}
        if actual != expected:
            item["schema_errors"] = [{"path": list(e.absolute_path), "message": e.message} for e in errors]
        output["results"].append(item); output["cases"] += 1
        output["expected_accepts" if expected else "expected_rejects"] += 1
        output["passed"] += int(actual == expected); output["mismatches"] += int(actual != expected)

    g = group("reference_expectation_effect", {"basis_type": list(BASIS), "expected_if_true": list(EXPECTATIONS),
              "expected_if_false": list(EXPECTATIONS), "effect": list(EFFECTS)},
              "Shared evidence_effect only. Valid refs follow reference availability; no candidate direction or counterevidence masks the gate.")
    for basis, t, f, effect in product(BASIS, EXPECTATIONS, EXPECTATIONS, EFFECTS):
        value = deepcopy(base_effect); value.update(expected_if_true=t, expected_if_false=f, effect=effect)
        value["reference_basis"]["basis_type"] = basis
        if basis == "NO_REFERENCE_AVAILABLE": value["reference_basis"]["basis_refs"] = []
        expected = expected_mapping(t, f, effect) and (basis != "NO_REFERENCE_AVAILABLE" or t == f == "UNKNOWN")
        record(g, "evidence_effect", {"basis_type": basis, "expected_if_true": t, "expected_if_false": f, "effect": effect}, value, expected)

    g = group("reference_ref_count", {"basis_type": list(BASIS), "basis_refs_count": [0, 1, 12, 13]},
              "Shared reference_basis only. Count rule, not reference authenticity or independent evidence count.")
    for basis, n in product(BASIS, (0, 1, 12, 13)):
        value = deepcopy(base_effect["reference_basis"]); value.update(basis_type=basis, basis_refs=fixture["evidence_refs"] * n)
        expected = n == 0 if basis == "NO_REFERENCE_AVAILABLE" else 1 <= n <= 12
        record(g, "reference_basis", {"basis_type": basis, "basis_refs_count": n}, value, expected)

    g = group("question_answer_basis", {"current_answer": ["UNKNOWN", "SYNTHETIC_RESOLVED_ANSWER"], "basis_refs_count": [0, 1, 12, 13]},
              "Answer is structurally supported by nonempty refs, not proven true; unresolved answers may still cite inconclusive evidence.")
    for answer, n in product(("UNKNOWN", "SYNTHETIC_RESOLVED_ANSWER"), (0, 1, 12, 13)):
        value = deepcopy(fixture["candidates"][0]["judgment_questions"][0]); value.update(current_answer=answer, basis_refs=fixture["evidence_refs"] * n)
        expected = n <= 12 and (answer == "UNKNOWN" or n > 0)
        record(g, "judgment_question", {"current_answer": answer, "basis_refs_count": n}, value, expected)

    profiles = [("empty", [], False), ("single", ["H01"], True), ("three", ["H01", "H02", "L01"], True),
                ("four", ["H01", "H02", "H03", "H04"], False), ("duplicate", ["H01", "H01"], False),
                ("question_not_candidate", ["Q01"], False)]
    g = group("discrimination_shape", {"profile": [p[0] for p in profiles]},
              "Shared request only. Dynamic target subset and candidate registry are host checks, not tested as Schema guarantees.")
    for profile, refs, expected in profiles:
        value = deepcopy(fixture["request_proposals"][0]); value["discriminates_between"] = refs
        record(g, "request", {"profile": profile, "discriminates_between": refs}, value, expected)

    return {"version": (root / "VERSION").read_text(encoding="utf-8").strip(),
            "scope": "LISTED_JUDGMENT_STRUCTURE_DIMENSIONS_NOT_HOST_OR_MODEL_ACCEPTANCE",
            "validator": "jsonschema.Draft202012Validator",
            "expected_outcome_source": "Independent documented-rule predicates, not Schema condition introspection",
            "matrices": matrices, "cases_total": sum(g["cases"] for g in matrices.values()),
            "mismatches_total": sum(g["mismatches"] for g in matrices.values())}

class JudgmentMatrixTests(unittest.TestCase):
    REPORT = None
    @classmethod
    def setUpClass(cls):
        if cls.REPORT is None: cls.REPORT = run_matrix()
    def verify_group(self, name):
        for item in self.REPORT["matrices"][name]["results"]:
            with self.subTest(**item["input"]):
                self.assertEqual(item["actual_valid"], item["expected_valid"], item.get("schema_errors"))
    def test_reference_expectation_effect(self): self.verify_group("reference_expectation_effect")
    def test_reference_ref_count(self): self.verify_group("reference_ref_count")
    def test_question_answer_basis(self): self.verify_group("question_answer_basis")
    def test_discrimination_shape(self): self.verify_group("discrimination_shape")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT); parser.add_argument("--report", type=Path)
    args = parser.parse_args(); report = run_matrix(args.root); JudgmentMatrixTests.REPORT = report
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JudgmentMatrixTests))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({"cases_total": report["cases_total"], "mismatches_total": report["mismatches_total"],
                      "matrices": {n: {k: g[k] for k in ["cases", "passed", "mismatches"]} for n, g in report["matrices"].items()}}, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
