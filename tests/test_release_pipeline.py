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
            default = (0, {"result": "PASS", "checks_total": 1788, "checks_passed": 1788})
            return self.overrides.get("validate_bundle_unpack", default)
        default = (0, {"result": "PASS", "checks_total": 1788, "checks_passed": 1788})
        return self.overrides.get("validate_bundle", default)

    def run_unittest(self, root):
        self.calls.append(("unittest", str(root)))
        default = (0, "Ran 182 tests\nOK", "")
        return self.overrides.get("unittest", default)

    def run_determinism(self, root):
        self.calls.append(("determinism", str(root)))
        default = (0, {"pass": True})
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
        return {"files": 2, "sha256": sha, "archive": str(output), "scope": "FAKE"}

    def run_validate_release(self, zip_path):
        self.calls.append(("validate_release", str(zip_path)))
        default = (0, {"pass": True, "errors": [], "scope": "ZIP_INTEGRITY_NOT_RUNTIME"})
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


if __name__ == "__main__":
    unittest.main()
