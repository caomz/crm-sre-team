#!/usr/bin/env python3
"""Release integration tests -- function-level API, no pipeline, no CLI.

Tests real build_release.build_release(), validate_release.validate(),
unpack file-set consistency, and compute_tree_digest determinism.
Does NOT call release.py CLI (anti-recursion design).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_release import build_release
from release import compute_tree_digest


class ReleaseIntegrationTests(unittest.TestCase):
    """Function-level integration tests using the real working copy."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_01_build_release_produces_valid_zip(self):
        """build_release creates a ZIP with correct scope and sha256."""
        output = self.tmpdir / "test-release.zip"
        result = build_release(ROOT, output)

        self.assertTrue(output.exists(), "Output ZIP was not created")
        self.assertTrue(output.is_file(), "Output is not a regular file")
        self.assertIn("sha256", result)
        self.assertEqual(len(result["sha256"]), 64, "sha256 should be 64 hex chars")
        self.assertEqual(result["scope"], "MANIFEST_CONTENT_INTEGRITY_NOT_HOST_VERIFICATION")
        self.assertGreater(result["files"], 100, "Release should contain >100 files")

    def test_02_release_zip_file_set_matches_manifest(self):
        """Unpacked ZIP file set exactly matches release-manifest.json files list."""
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        expected = set(manifest["files"])

        output = self.tmpdir / "fileset-check.zip"
        build_release(ROOT, output)

        unpack_dir = self.tmpdir / "unpack"
        unpack_dir.mkdir()
        with ZipFile(output) as z:
            z.extractall(unpack_dir)

        prefix = "crm-sre-team/"
        actual = set()
        for p in sorted((unpack_dir / "crm-sre-team").rglob("*")):
            if p.is_file():
                actual.add(p.relative_to(unpack_dir / "crm-sre-team").as_posix())

        missing = expected - actual
        extra = actual - expected
        self.assertEqual(missing, set(), "Manifest files missing from ZIP: " + str(sorted(missing)[:10]))
        self.assertEqual(extra, set(), "Extra files in ZIP not in manifest: " + str(sorted(extra)[:10]))

    def test_03_validate_release_passes_on_clean_zip(self):
        """validate_release returns pass=True on a freshly built ZIP."""
        from validate_release import validate
        output = self.tmpdir / "validate-check.zip"
        build_release(ROOT, output)

        result = validate(ROOT, output)
        self.assertTrue(result["pass"], "validate_release failed: " + str(result.get("errors", [])[:5]))
        self.assertEqual(result["scope"], "ZIP_INTEGRITY_NOT_RUNTIME")
        self.assertEqual(len(result["sha256"]), 64)

    def test_04_compute_tree_digest_is_deterministic(self):
        """compute_tree_digest returns the same value on repeated calls."""
        d1 = compute_tree_digest(ROOT)
        d2 = compute_tree_digest(ROOT)
        self.assertEqual(d1, d2, "Tree digest is non-deterministic")
        self.assertEqual(len(d1), 64, "Digest should be 64 hex chars")

    def test_05_release_zip_contains_individual_skill_zips(self):
        """Release ZIP includes all 8 individual skill.zip files from manifest."""
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        skill_zips = [f for f in manifest["files"] if f.startswith("individual-packages/") and f.endswith("skill.zip")]
        self.assertEqual(len(skill_zips), 8, "Manifest should list 8 skill.zip files")

        output = self.tmpdir / "skill-zip-check.zip"
        build_release(ROOT, output)

        with ZipFile(output) as z:
            names = set(z.namelist())
        for sz in skill_zips:
            entry = "crm-sre-team/" + sz
            self.assertIn(entry, names, "Missing in release ZIP: " + entry)

    def test_06_release_zip_sha256_matches_readback(self):
        """SHA-256 recorded by build_release matches independent readback."""
        import hashlib
        output = self.tmpdir / "sha-check.zip"
        result = build_release(ROOT, output)

        independent = hashlib.sha256(output.read_bytes()).hexdigest()
        self.assertEqual(result["sha256"], independent, "Recorded sha256 != independent readback")

    # Hard-coded list of modules required for build/validate/release.
    # NOT derived from the manifest itself -- prevents "manifest and lock both
    # miss the same module" from passing self-consistently.
    REQUIRED_BUILD_VALIDATE_RELEASE_MODULES = [
        "tools/build_bundle.py",
        "tools/build_release.py",
        "tools/check_determinism.py",
        "tools/check_workbuddy.py",
        "tools/release.py",
        "tools/release_rules.py",
        "tools/validate_bundle.py",
        "tools/validate_individual_zip.py",
        "tools/validate_release.py",
        "tests/test_individual_zip_safety.py",
        "tests/test_release_integration.py",
        "tests/test_release_pipeline.py",
        "tests/test_version_consistency.py",
    ]

    def test_07_required_modules_in_manifest(self):
        """Build/validate/release modules must be in release manifest.

        Hard-coded list, not derived from manifest -- catches the case where
        manifest and lock both miss the same module but pass self-consistently.
        """
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        manifest_files = set(manifest["files"])
        missing = [f for f in self.REQUIRED_BUILD_VALIDATE_RELEASE_MODULES
                   if f not in manifest_files]
        self.assertEqual(
            missing, [],
            "Required modules missing from release-manifest.json: " + str(missing))


if __name__ == "__main__":
    unittest.main()
