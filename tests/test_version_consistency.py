"""VERSION is the single source of truth for release version."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VersionConsistencyTests(unittest.TestCase):
    def test_01_version_file_not_empty(self):
        self.assertTrue((ROOT / "VERSION").read_text(encoding="utf-8").strip())

    def test_02_plugin_json_matches_version(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        plugin = json.loads((ROOT / ".codebuddy-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], version)

    def test_03_root_lock_matches_version(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        lock = json.loads((ROOT / "prompt-bundles.lock").read_text(encoding="utf-8"))
        self.assertEqual(lock["version"], version)

    def test_04_all_skill_versions_match(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        for sid in roles:
            skill_version = (ROOT / "skills" / sid / "VERSION").read_text(encoding="utf-8").strip()
            self.assertEqual(skill_version, version, f"skill {sid} VERSION mismatch")

    def test_05_source_provenance_full_bytes_not_mutated(self):
        """Historical provenance file must stay byte-identical across a real build."""
        import shutil
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "w"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".DS_Store", ".pytest_cache", ".git", ".venv", "dist", "reports"))
            prov = work / "source-provenance.json"
            before = prov.read_bytes()
            subprocess.run([sys.executable, "tools/build_bundle.py", "--root", "."],
                           cwd=work, check=True, capture_output=True)
            self.assertEqual(before, prov.read_bytes())


if __name__ == "__main__":
    unittest.main()
