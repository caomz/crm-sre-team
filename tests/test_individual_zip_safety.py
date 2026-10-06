"""Hostile-input tests for validate_individual_zip and its fail-closed wiring in validate_bundle.

Layer 1 scheduling/unit tests: every case builds a minimal synthetic skill tree
plus a crafted ZIP in a temp directory and calls the validator directly.
test_05b is the integration hook: one full-tree copy, one tampered release
input, validate_bundle.run() must fail closed on the legacy check IDs.
Synthetic data only; no production artifact is read or written.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import release_rules
import validate_individual_zip as iv

ZIP_TIME = release_rules.ZIP_TIME
SID = "dummy-skill"
DEFAULT_FILES = {
    "SKILL.md": b"# dummy skill\n",
    "VERSION": b"2.6.1\n",
    "references/runbook.md": b"# runbook\n",
}


def write_skill_tree(root: Path, files=None) -> None:
    files = DEFAULT_FILES if files is None else files
    for rel, data in files.items():
        p = root / "skills" / SID / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def canonical_members(root: Path) -> list:
    """(name, data) pairs in the builder's canonical order.

    deterministic_zip sorts Path objects, whose ordering is case-insensitive on
    Windows; the test mirrors that derivation so a normal ZIP is accepted and
    only the deliberately injected defect fails.
    """
    skill = root / "skills" / SID
    return [(f"{SID}/{p.relative_to(skill).as_posix()}", p.read_bytes())
            for p in sorted(skill.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]


def canonical_info(name: str) -> ZipInfo:
    info = ZipInfo(name, ZIP_TIME)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def write_zip(zpath: Path, members) -> None:
    """members: (name, data) or (name, data, {ZipInfo attr: value}); order preserved."""
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zpath, "w") as z:
        for member in members:
            name, data, meta = (member + ({},)) if len(member) == 2 else member
            info = canonical_info(name)
            for attr, value in meta.items():
                setattr(info, attr, value)
            z.writestr(info, data, compresslevel=9)


def patch_central_flags(zpath: Path, target: str, flag: int) -> None:
    """Set the general-purpose flag field of one central-directory record."""
    data = bytearray(zpath.read_bytes())
    pos = 0
    while True:
        pos = data.find(b"PK\x01\x02", pos)
        if pos < 0:
            break
        name_len = int.from_bytes(data[pos + 28:pos + 30], "little")
        name = bytes(data[pos + 46:pos + 46 + name_len]).decode("utf-8", "replace")
        if name == target:
            data[pos + 8:pos + 10] = flag.to_bytes(2, "little")
        pos += 4
    zpath.write_bytes(bytes(data))


class IndividualZipSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write_skill_tree(self.root)
        self.zpath = self.root / "individual-packages" / SID / "skill.zip"
        write_zip(self.zpath, canonical_members(self.root))

    def report(self):
        return iv.validate(self.root, SID)

    def kinds(self):
        return {e.split(":", 1)[0] for e in self.report()["errors"]}

    def test_01_canonical_zip_passes(self):
        report = self.report()
        self.assertTrue(report["pass"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(len(report["sha256"]), 64)

    def test_02_unsorted_entries(self):
        write_zip(self.zpath, list(reversed(canonical_members(self.root))))
        self.assertIn("entries_not_sorted", self.kinds())
        self.assertFalse(self.report()["pass"])

    def test_03_duplicate_entries(self):
        members = canonical_members(self.root)
        write_zip(self.zpath, members + [members[0]])
        self.assertIn("duplicate_entries", self.kinds())

    def test_04_symlink_metadata_entry(self):
        members = canonical_members(self.root)
        members = [(n, d, {"external_attr": 0o120777 << 16}) if n == f"{SID}/SKILL.md" else (n, d) for n, d in members]
        write_zip(self.zpath, members)
        self.assertIn("non_regular_entry", self.kinds())

    def test_05a_disk_tamper_content_mismatch(self):
        (self.root / "skills" / SID / "VERSION").write_bytes(b"9.9.9\n")
        self.assertEqual(self.report()["errors"], [f"content_mismatch:{SID}/VERSION"])

    def test_05b_validate_bundle_fails_closed(self):
        work = Path(self.tmp.name) / "w"
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".DS_Store", ".pytest_cache", ".git", ".venv", "dist", "reports", "*.tmp.json", "*.tmp.txt"))
        roles = json.loads((work / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        sid, other = sorted(roles)[0], sorted(roles)[1]
        zpath = work / "individual-packages" / sid / "skill.zip"
        with ZipFile(zpath) as z:
            members = [(e.filename, z.read(e.filename)) for e in z.infolist()]
        members = [(name, b"tampered\n" if name == f"{sid}/VERSION" else data) for name, data in members]
        write_zip(zpath, members)
        spec = importlib.util.spec_from_file_location("vb_under_test", work / "tools/validate_bundle.py")
        vb = importlib.util.module_from_spec(spec); spec.loader.exec_module(vb)
        report = vb.run(work)
        joined = "\n".join(report["errors"])
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("individual_zip_content:" + sid, joined)
        self.assertIn("individual_zip_crc:" + sid, joined)
        self.assertIn("individual_zip_file_set:" + sid, joined)
        self.assertIn("individual_zip_strict:" + sid + ":content_mismatch:" + sid + "/VERSION", joined)
        self.assertNotIn("individual_zip_strict:" + other, joined)

    def test_06_case_colliding_entries(self):
        write_zip(self.zpath, canonical_members(self.root) + [(f"{SID}/skill.md", b"# colliding\n")])
        self.assertIn("case_colliding_entries", self.kinds())

    def test_07_encrypted_flag_entry(self):
        patch_central_flags(self.zpath, f"{SID}/VERSION", 1)
        self.assertIn("encrypted_entry", self.kinds())

    def test_08_noncanonical_metadata(self):
        members = canonical_members(self.root)
        members = [(n, d, {"date_time": (2025, 1, 1, 0, 0, 0)}) if n == f"{SID}/VERSION" else (n, d) for n, d in members]
        write_zip(self.zpath, members)
        self.assertIn("noncanonical_metadata", self.kinds())

    def test_09_member_size_limit(self):
        write_skill_tree(self.root, {**DEFAULT_FILES, "references/big.md": b"\x00" * (21 * 1024 * 1024)})
        write_zip(self.zpath, canonical_members(self.root))
        self.assertIn("member_size_limit", self.kinds())

    def test_10_archive_size_limit(self):
        big = b"\x00" * (18 * 1024 * 1024)
        write_skill_tree(self.root, {**DEFAULT_FILES, **{f"references/part{i}.md": big for i in range(6)}})
        write_zip(self.zpath, canonical_members(self.root))
        self.assertIn("archive_size_limit", self.kinds())

    def test_11_compression_ratio_limit(self):
        write_skill_tree(self.root, {**DEFAULT_FILES, "references/dense.md": b"A" * 200_000})
        write_zip(self.zpath, canonical_members(self.root))
        kinds = self.kinds()
        self.assertIn("compression_ratio_limit", kinds)
        self.assertNotIn("member_size_limit", kinds)

    def test_12_unsafe_path_entry(self):
        write_zip(self.zpath, canonical_members(self.root) + [("../escape.md", b"evil\n")])
        self.assertIn("unsafe_path", self.kinds())

    def test_13_not_a_zip(self):
        self.zpath.write_bytes(b"this is not a zip")
        report = self.report()
        self.assertFalse(report["pass"])
        self.assertTrue(any(e.startswith("BadZipFile:") for e in report["errors"]))

    def test_14_required_file_missing(self):
        members = [m for m in canonical_members(self.root) if m[0] != f"{SID}/VERSION"]
        write_zip(self.zpath, members)
        self.assertIn("required_file_missing", self.kinds())

    def test_15_file_set_mismatch(self):
        write_zip(self.zpath, canonical_members(self.root) + [(f"{SID}/extra.md", b"extra\n")])
        self.assertEqual(self.report()["errors"], ["file_set_mismatch"])


if __name__ == "__main__":
    unittest.main()
