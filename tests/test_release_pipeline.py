#!/usr/bin/env python3
"""Release pipeline scheduling tests -- fake runner, no real subprocess.

Tests step ordering, failure handling, six-point assertions.
Does NOT call release.py CLI (anti-recursion design).
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from release import compute_tree_digest, PIPELINE_STEPS, run_pipeline


def bundle_report():
    counts = ["additional_static_tests", "offline_contract_tests_run", "reasoning_matrix_test_methods",
              "judgment_contract_tests_run", "judgment_matrix_test_methods", "thinking_tool_tests_run"]
    zeros = ["offline_contract_test_failures", "offline_contract_test_errors", "reasoning_matrix_test_failures",
             "reasoning_matrix_test_errors", "reasoning_matrix_mismatches", "judgment_contract_test_failures",
             "judgment_contract_test_errors", "judgment_matrix_test_failures", "judgment_matrix_test_errors",
             "judgment_matrix_mismatches", "thinking_tool_test_failures", "thinking_tool_test_errors"]
    return {"version": "2.6.1", "scope": "STATIC_STRUCTURE_AND_OFFLINE_SCHEMA_POLICY_TESTS_ONLY",
            "result": "PASS_STATIC_ONLY", "errors": [], "checks_total": 1788, "checks_passed": 1788,
            "offline_unit_tests_total": 6, **dict.fromkeys(counts, 1), **dict.fromkeys(zeros, 0)}


def determinism_report():
    flags = ["pass", "generated_artifacts_deterministic", "release_tree_deterministic",
             "input_release_already_built", "validation_output_deterministic", "validation_tree_deterministic",
             "source_tree_unchanged_during_comparisons"]
    return {"version": "2.6.1", "scope": "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS",
            **dict.fromkeys(flags, True), "checked_files": 1, "hashes": {"VERSION": "a" * 64},
            "release_tree_file_count": 1, "build_exit_codes": [0, 0], "validation_exit_codes": [0, 0, 0],
            "sorting_guard_negative_test": {"exit_code": 1, "detected": True, "failed_check_ids": ["synthetic_guard"]}}


# ---------------------------------------------------------------------------
# Fake runner -- returns preset results, creates minimal real ZIP for unpack
# ---------------------------------------------------------------------------

class FakeRunner:
    """Fake runner: no subprocess, no real validate. For scheduling tests."""

    def __init__(self, **overrides):
        self.overrides = overrides
        self.calls = []

    def run_validate_bundle(self, root):
        self.calls.append(("validate_bundle", str(root)))
        root_str = str(root).lower()
        if "unpack" in root_str:
            default = (0, bundle_report())
            return self.overrides.get("validate_bundle_unpack", default)
        default = (0, bundle_report())
        return self.overrides.get("validate_bundle", default)

    def run_unittest(self, root):
        self.calls.append(("unittest", str(root)))
        default = (0, "Ran 182 tests\nOK", "")
        return self.overrides.get("unittest", default)

    def run_determinism(self, root):
        self.calls.append(("determinism", str(root)))
        default = (0, determinism_report())
        return self.overrides.get("determinism", default)

    def build_release(self, root, output):
        self.calls.append(("build_release", str(root), str(output)))
        if "build_release_error" in self.overrides:
            raise self.overrides["build_release_error"]
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w") as z:
            for name, content in [
                ("crm-sre-team/VERSION", b"2.6.1\n"),
                ("crm-sre-team/SKILL.md", b"# skill\n"),
            ]:
                info = ZipInfo(name, (2026, 9, 21, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, content, compress_type=ZIP_DEFLATED, compresslevel=9)
        sha = hashlib.sha256(output.read_bytes()).hexdigest()
        return {"files": 2, "sha256": sha, "archive": str(output), "scope": "MANIFEST_CONTENT_INTEGRITY_NOT_HOST_VERIFICATION"}

    def run_validate_release(self, zip_path):
        self.calls.append(("validate_release", str(zip_path)))
        default = (0, {"pass": True, "errors": [], "scope": "ZIP_INTEGRITY_NOT_RUNTIME",
                       "files_total": 2, "files_checked": 2,
                       "sha256": hashlib.sha256(Path(zip_path).read_bytes()).hexdigest()})
        return self.overrides.get("validate_release", default)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OLD_RELEASE_NAME = "2.6.0-20260901T000000Z"


def make_minimal_project(root):
    """Create a minimal project tree for pipeline testing."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "VERSION").write_text("2.6.1\n", encoding="utf-8")
    (root / ".codebuddy-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".codebuddy-plugin" / "plugin.json").write_text(
        json.dumps({"version": "2.6.1"}), encoding="utf-8")
    (root / "release-manifest.json").write_text(
        json.dumps({"schema_version": 1, "scope": "test",
                    "excluded_generated_reports": [], "files": []}),
        encoding="utf-8")
    (root / "prompt-bundles.lock").write_text(
        json.dumps({"version": "2.6.1", "files": {}}), encoding="utf-8")
    old_release = root / "dist" / "releases" / _OLD_RELEASE_NAME
    old_release.mkdir(parents=True, exist_ok=True)
    (old_release / "crm-sre-team-2.6.0.zip").write_bytes(b"old release zip content")
    (old_release / "validation-report.json").write_text(
        json.dumps({"version": "2.6.0", "ok": True}), encoding="utf-8")
    return root


def assert_six_points(test_case, result, project_root, expected_step,
                      expected_error_contains=None, before_digest=None):
    """Assert the six failure points for a failed pipeline run."""
    # Point 1: failed_step is expected
    test_case.assertEqual(
        result["failed_step"], expected_step,
        "Point 1: failed_step should be " + expected_step)

    # Point 2: error category
    if expected_error_contains:
        test_case.assertIn(
            expected_error_contains, str(result["error"]),
            "Point 2: error should contain " + expected_error_contains)

    # Point 3: subsequent steps not executed
    step_names = [s["name"] for s in result["steps"]]
    expected_idx = PIPELINE_STEPS.index(expected_step)
    actual_after = step_names[expected_idx + 1:]
    test_case.assertEqual(
        actual_after, [],
        "Point 3: steps after " + expected_step + " were executed: " + str(actual_after))

    # Point 4: input candidate not modified (digest unchanged)
    if before_digest is not None:
        after_digest = compute_tree_digest(project_root)
        test_case.assertEqual(
            before_digest, after_digest,
            "Point 4: tree digest changed -- pipeline modified inputs")

    # Point 5: no NEW official artifacts in dist/releases/
    releases_dir = project_root / "dist" / "releases"
    if releases_dir.exists():
        current = set(p.name for p in sorted(releases_dir.iterdir()))
    else:
        current = set()
    test_case.assertEqual(
        current, {_OLD_RELEASE_NAME},
        "Point 5: dist/releases/ has unexpected artifacts: " + str(current - {_OLD_RELEASE_NAME}))

    # Point 6: previous successes unchanged
    old_zip = releases_dir / _OLD_RELEASE_NAME / "crm-sre-team-2.6.0.zip"
    test_case.assertTrue(old_zip.exists(), "Point 6: previous release ZIP missing")
    test_case.assertEqual(
        old_zip.read_bytes(), b"old release zip content",
        "Point 6: previous release ZIP content changed")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class ReleasePipelineTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_minimal_project(Path(self.tmp.name) / "project")

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_full_pipeline_success(self):
        """All 10 steps pass. Promote is last. New release appears in dist/releases/."""
        before = compute_tree_digest(self.root)
        releases_before = set(p.name for p in sorted((self.root / "dist" / "releases").iterdir()))

        runner = FakeRunner()
        result = run_pipeline(self.root, runner=runner)

        self.assertTrue(result["ok"], "Pipeline should succeed: " + str(result.get("error")))
        self.assertEqual(len(result["steps"]), 10)
        self.assertTrue(all(s["ok"] for s in result["steps"]))

        # Promote happened: new release in dist/releases/
        releases_after = set(p.name for p in sorted((self.root / "dist" / "releases").iterdir()))
        new_releases = releases_after - releases_before
        self.assertEqual(len(new_releases), 1, "Expected exactly 1 new release")

        new_dir = self.root / "dist" / "releases" / sorted(new_releases)[0]
        self.assertTrue((new_dir / "crm-sre-team-2.6.1.zip").exists())
        self.assertTrue((new_dir / "validation-report.json").exists())

        report = json.loads((new_dir / "validation-report.json").read_text(encoding="utf-8"))
        self.assertIn("tree_digest", report)
        self.assertIn("release_sha256", report)
        self.assertEqual(report["version"], "2.6.1")
        self.assertEqual(report["scope"], "OFFLINE_BUILD_CONSISTENCY_RELEASE_GATE")

        # Old release still intact (Point 6 for success)
        old_zip = self.root / "dist" / "releases" / _OLD_RELEASE_NAME / "crm-sre-team-2.6.0.zip"
        self.assertEqual(old_zip.read_bytes(), b"old release zip content")

        # No staging dir left behind
        staging = self.root / "dist" / "staging"
        if staging.exists():
            self.assertEqual(list(sorted(staging.iterdir())), [])

    def test_02_version_mismatch_aborts(self):
        """Step 2 fails: VERSION != plugin.json version."""
        (self.root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
        before = compute_tree_digest(self.root)

        result = run_pipeline(self.root, runner=FakeRunner())

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "version_validation",
                          expected_error_contains="VERSION", before_digest=before)

    def test_03_lock_tamper_aborts(self):
        """Step 3 fails: validate_bundle exit_code != 0 (simulating lock tamper)."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(validate_bundle=(1, None))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "input_consistency",
                          expected_error_contains="validate_bundle", before_digest=before)

    def test_04_input_tree_drift_aborts(self):
        """Step 3 fails: tree digest != frozen digest."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner()

        result = run_pipeline(self.root, runner=runner, frozen_digest="0" * 64)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "input_consistency",
                          expected_error_contains="digest mismatch", before_digest=before)

    def test_05_test_failure_aborts(self):
        """Step 4 fails: unittest returns non-zero exit."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(unittest=(1, "Ran 182 tests\nFAILED", "assertion error"))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "tests",
                          expected_error_contains="unittest", before_digest=before)

    def test_06_determinism_failure_aborts(self):
        """Step 5 fails: determinism check returns pass=false."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(determinism=(0, {"pass": False}))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "determinism",
                          expected_error_contains="determinism", before_digest=before)

    def test_07_bundle_validation_failure_aborts(self):
        """Step 3 fails: validate_bundle result=FAIL (simulating corrupt skill ZIP)."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(validate_bundle=(
            0, {"result": "FAIL", "errors": ["individual_zip_crc:stability-director"]}))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "input_consistency",
                          expected_error_contains="result=FAIL", before_digest=before)

    def test_08_release_validation_failure_aborts(self):
        """Step 7 fails: validate_release returns pass=false."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(validate_release=(
            0, {"pass": False, "errors": ["content_mismatch:crm-sre-team/VERSION"]}))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "validate_release",
                          expected_error_contains="validate_release", before_digest=before)

    def test_09_build_staging_failure_aborts(self):
        """Step 6 fails: build_release raises an exception."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(build_release_error=RuntimeError("simulated disk full"))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "build_staging",
                          expected_error_contains="build_release failed", before_digest=before)

    def test_10_unpack_revalidate_failure_aborts(self):
        """Step 8 fails: validate_bundle on unpacked content returns FAIL."""
        before = compute_tree_digest(self.root)
        runner = FakeRunner(validate_bundle_unpack=(
            0, {"result": "FAIL", "errors": ["unpack_revalidate_test_error"]}))

        result = run_pipeline(self.root, runner=runner)

        self.assertFalse(result["ok"])
        assert_six_points(self, result, self.root, "unpack_revalidate",
                          expected_error_contains="unpack revalidate", before_digest=before)

    def test_11_exit_zero_with_empty_or_wrong_scope_reports_is_rejected(self):
        mapping = {"validate_bundle": "input_consistency", "determinism": "determinism",
                   "validate_release": "validate_release", "validate_bundle_unpack": "unpack_revalidate"}
        for override, step in mapping.items():
            for report in (None, {}, [], {"scope": "WRONG", "pass": True, "result": "PASS_STATIC_ONLY"}):
                with self.subTest(step=step, report=report), tempfile.TemporaryDirectory() as td:
                    root = make_minimal_project(Path(td) / "project")
                    before = compute_tree_digest(root)
                    result = run_pipeline(root, runner=FakeRunner(**{override: (0, report)}))
                    self.assertFalse(result["ok"])
                    assert_six_points(self, result, root, step, "invalid report", before)

    def test_12_zero_or_inconsistent_validation_counts_are_rejected(self):
        mutations = [{"checks_total": 0, "checks_passed": 0}, {"checks_passed": 1787},
                     {"checks_total": True, "checks_passed": True}, {"offline_unit_tests_total": 0},
                     {"offline_unit_tests_total": 7}, {"offline_contract_test_errors": 1},
                     {"scope": "WRONG"}, {"errors": ["synthetic"]}]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = make_minimal_project(Path(td) / "project")
                report = {**bundle_report(), **mutation}
                result = run_pipeline(root, runner=FakeRunner(validate_bundle=(0, report)))
                assert_six_points(self, result, root, "input_consistency", "invalid report")

    def test_13_exit_zero_without_nonzero_test_success_is_rejected(self):
        for summary in ("", "OK", "Ran 0 tests\nOK", "Ran 2 tests\nOK (skipped=2)",
                        "Ran 2 tests\nFAILED\nOK", "Ran 2 tests\nOK\nRan 3 tests\nOK"):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as td:
                root = make_minimal_project(Path(td) / "project")
                result = run_pipeline(root, runner=FakeRunner(unittest=(0, "", summary)))
                self.assertFalse(result["ok"])
                assert_six_points(self, result, root, "tests", "unittest")

    def test_14_determinism_report_must_prove_nonzero_checks(self):
        for mutation in ({"checked_files": 0}, {"hashes": {}}, {"validation_exit_codes": [0, 1, 0]},
                         {"release_tree_file_count": 0}, {"validation_output_deterministic": False}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = make_minimal_project(Path(td) / "project")
                result = run_pipeline(root, runner=FakeRunner(determinism=(0, {**determinism_report(), **mutation})))
                assert_six_points(self, result, root, "determinism", "invalid report")

    def test_15_release_report_must_prove_file_count_and_digest(self):
        for mutation in ({"files_total": 0, "files_checked": 0}, {"files_checked": 1},
                         {"files_total": 3, "files_checked": 3}, {"sha256": "0" * 64}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = make_minimal_project(Path(td) / "project")
                class MutatedRunner(FakeRunner):
                    def run_validate_release(self, zip_path):
                        code, report = super().run_validate_release(zip_path)
                        return code, {**report, **mutation}
                result = run_pipeline(root, runner=MutatedRunner())
                assert_six_points(self, result, root, "validate_release", "invalid report")

    def test_16_build_report_must_match_actual_zip(self):
        for mutation in ({"scope": "WRONG"}, {"files": 0}, {"files": 3}, {"sha256": None}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as td:
                root = make_minimal_project(Path(td) / "project")
                class MutatedRunner(FakeRunner):
                    def build_release(self, root, output):
                        return {**super().build_release(root, output), **mutation}
                result = run_pipeline(root, runner=MutatedRunner())
                assert_six_points(self, result, root, "build_staging", "invalid report")


if __name__ == "__main__":
    unittest.main()
