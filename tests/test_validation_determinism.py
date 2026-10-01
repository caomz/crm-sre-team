"""Integration test. Run separately; intentionally not invoked by validate_bundle.

It invokes the validator in temporary copies, so nesting it inside the validator
would recurse. This is one integration test, not one of the Schema test methods.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ValidationDeterminismTests(unittest.TestCase):
    def test_static_checks_order_is_deterministic(self):
        spec = importlib.util.spec_from_file_location("determinism_checker", ROOT / "tools/check_determinism.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        report = tool.run_checks(ROOT)
        for key in ["generated_artifacts_deterministic", "release_tree_deterministic",
                    "input_release_already_built", "validation_output_deterministic",
                    "validation_tree_deterministic", "source_tree_unchanged_during_comparisons", "pass"]:
            with self.subTest(check=key):
                self.assertTrue(report[key], report)
        self.assertTrue(report["sorting_guard_negative_test"]["detected"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
