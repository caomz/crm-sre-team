"""Actual isolated ZIP and staged-build tests. Synthetic data only."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_release
import validate_release
import release_rules
spec = importlib.util.spec_from_file_location("tested_builder", ROOT / "tools/build_bundle.py")
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


def _can_symlink() -> bool:
    """Capability probe: real filesystem symlinks (not ZIP metadata)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); t = p / "t"; t.write_bytes(b"x"); link = p / "l"
            link.symlink_to(t)
            return link.is_symlink()
    except OSError:
        return False


requires_real_symlink = unittest.skipUnless(
    _can_symlink(), "SKIPPED_CAPABILITY: real filesystem symlinks unavailable on this host")


def tree_hash(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts}

class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name); self.root = self.base / "crm-sre-team"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", "dist", "reports"))
        self.zip = self.base / "release.zip"

    def test_01_clean_zip_valid(self):
        build_release.build_release(self.root, self.zip)
        self.assertTrue(validate_release.validate(self.root, self.zip)["pass"])

    def test_forbidden_release_categories_are_casefolded_without_renaming_paths(self):
        for rel in ("REPORTS/incident.json", ".GIT/config.json", ".ENV.production.json",
                    "a/.Env.local", "NODE_Modules/p/module.py", "a/__PyCache__/m.py",
                    "DIST/archive.json", "Incident-Evidence/note.md", "ID_RsA.json", "id_ED25519.txt"):
            with self.subTest(path=rel):
                self.assertFalse(release_rules.safe_relative(rel))
        self.assertTrue(release_rules.safe_relative("docs/Guide.JSON"))
        manifest = json.loads((self.root / "release-manifest.json").read_text(encoding="utf-8"))
        original_names = manifest["files"][:]
        self.assertEqual(release_rules.manifest_names(self.root), original_names)

    def test_02_sensitive_workspace_files_never_added(self):
        names = [".env", ".env.local", ".venv/lib/a.py", "incident-evidence/sample.log", "local-copy.bak", "tools/unlisted.py", "skills/stability-director/references/unlisted.md"]
        for name in names:
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("SYNTHETIC_ONLY", encoding="utf-8")
        build_release.build_release(self.root, self.zip)
        with ZipFile(self.zip) as z:
            self.assertTrue(all("crm-sre-team/" + n not in z.namelist() for n in names))

    def test_03_output_in_root_repeated_no_self_inclusion(self):
        output = self.root / "release.zip"
        first = build_release.build_release(self.root, output)
        second = build_release.build_release(self.root, output)
        self.assertEqual(first["sha256"], second["sha256"])
        with ZipFile(output) as z: self.assertNotIn("crm-sre-team/release.zip", z.namelist())

    def test_04_output_in_dist_repeated_is_identical(self):
        p = self.root / "dist/release.zip"
        self.assertEqual(build_release.build_release(self.root, p)["sha256"], build_release.build_release(self.root, p)["sha256"])

    def test_05_output_overlapping_source_rejected(self):
        p = self.root / "individual-packages/oracle-dba/skill.zip"; old = p.read_bytes()
        with self.assertRaises(ValueError): build_release.build_release(self.root, p)
        self.assertEqual(p.read_bytes(), old)

    @requires_real_symlink
    def test_06_symlink_input_rejected(self):
        p = self.root / "README.md"; p.unlink(); p.symlink_to(ROOT / "README.md")
        with self.assertRaises(ValueError): build_release.build_release(self.root, self.zip)

    @requires_real_symlink
    def test_07_symlink_output_rejected(self):
        target = self.base / "other.zip"; target.write_bytes(b"unchanged"); self.zip.symlink_to(target)
        with self.assertRaises(ValueError): build_release.build_release(self.root, self.zip)
        self.assertEqual(target.read_bytes(), b"unchanged")

    def mutate_archive(self, strategy):
        build_release.build_release(self.root, self.zip)
        with ZipFile(self.zip) as z: entries = [(e, z.read(e)) for e in z.infolist()]
        entries = strategy(entries)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(self.zip, "w") as z:
                for e, content in entries: z.writestr(e, content)
        return validate_release.validate(self.root, self.zip)

    def test_08_actual_unsorted_zip_rejected(self):
        r = self.mutate_archive(lambda e:list(reversed(e)))
        self.assertIn("entries_not_sorted", r["errors"])

    def test_09_actual_duplicate_zip_rejected(self):
        r = self.mutate_archive(lambda e:e + [e[0]])
        self.assertIn("duplicate_entries", r["errors"])

    def test_10_zip_missing_entry_rejected(self):
        self.assertIn("file_set_mismatch", self.mutate_archive(lambda e:e[1:])["errors"])

    def test_11_corrupt_content_rejected(self):
        r = self.mutate_archive(lambda e:[(e[0][0], b"SYNTHETIC_WRONG_CONTENT")] + e[1:])
        self.assertTrue(any(n.startswith("content_mismatch:") for n in r["errors"]))

    def test_12_path_traversal_rejected(self):
        def mutate(e):
            info = ZipInfo("crm-sre-team/../escape.txt", release_rules.ZIP_TIME); info.external_attr=0o100644 << 16; info.compress_type=ZIP_DEFLATED
            return e + [(info, b"SYNTHETIC")]
        self.assertTrue(any(n.startswith("unsafe_path:") for n in self.mutate_archive(mutate)["errors"]))

    def test_13_manifest_cannot_allow_secrets(self):
        p = self.root / "release-manifest.json"; value=json.loads(p.read_text(encoding="utf-8"));value["files"].append(".env");value["files"].sort();p.write_text(json.dumps(value),encoding="utf-8")
        with self.assertRaises(ValueError): build_release.build_release(self.root, self.zip)

    def test_14_atomic_release_failure_preserves_old_output(self):
        self.zip.write_bytes(b"old archive sentinel")
        with patch.object(build_release.os,"replace",side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError): build_release.build_release(self.root, self.zip)
        self.assertEqual(self.zip.read_bytes(), b"old archive sentinel")
        self.assertEqual(list(self.base.glob(".crm-release-*")), [])

    def test_15_build_preflight_failure_leaves_tree_unchanged(self):
        p = self.root / "settings.json";p.write_text("[]",encoding="utf-8")
        before = tree_hash(self.root)
        with self.assertRaises(ValueError): builder.build(self.root)
        self.assertEqual(tree_hash(self.root), before)

    def test_16_build_commit_failure_rolls_back_and_reruns(self):
        before=tree_hash(self.root); actual=builder.os.replace; count=[0]
        def fail_once(src,dst):
            count[0]+=1
            if count[0]==3: raise OSError("synthetic third-rename failure")
            return actual(src,dst)
        with patch.object(builder.os,"replace",side_effect=fail_once):
            with self.assertRaises(OSError): builder.build(self.root)
        self.assertEqual(tree_hash(self.root), before)
        builder.build(self.root)
        self.assertEqual(tree_hash(self.root), before)

    def test_17_build_preserves_custom_settings(self):
        p = self.root / "settings.json";p.write_text(json.dumps({"agent":"telecom-crm-sre-team-lead","language":"zh-CN","permissions":{"deny":["SYNTHETIC"]}}),encoding="utf-8")
        before=p.read_bytes();builder.build(self.root);self.assertEqual(p.read_bytes(), before)

    def test_18_build_twice_identical(self):
        builder.build(self.root);first=tree_hash(self.root);builder.build(self.root);self.assertEqual(tree_hash(self.root),first)

    @requires_real_symlink
    def test_19_symlinked_source_parent_rejected(self):
        target=self.base/"external-templates";shutil.move(str(self.root/"policy-source/templates"),target)
        (self.root/"policy-source/templates").symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError): builder.build(self.root)

    def test_20_path_rule_negative_cases(self):
        for name in ["../escape", "/absolute", "a/../b", "a//b", "a\\b", "C:/x", ".env", "a/.env.test", "a/key.pem", "a/id_rsa", "random.zip", "a/.venv/x.py", "reports/report.json", "a/backup.bak", "a/file.md~"]:
            with self.subTest(path=name): self.assertFalse(release_rules.safe_relative(name))

    def test_21_unknown_generated_user_file_is_not_deleted(self):
        p = self.root / "skills/stability-director/private-notes.md"
        p.write_text("SYNTHETIC_USER_NOTES", encoding="utf-8")
        before = tree_hash(self.root)
        with self.assertRaises(ValueError): builder.build(self.root)
        self.assertEqual(tree_hash(self.root), before)

    @requires_real_symlink
    def test_22_unknown_workspace_symlink_not_followed(self):
        # An unlisted data link must neither be staged nor published.
        (self.root / "unlisted-data").symlink_to(self.base / "does-not-exist")
        builder.build(self.root)
        self.assertTrue((self.root / "unlisted-data").is_symlink())

if __name__ == "__main__": unittest.main(verbosity=2)
