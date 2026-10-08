"""Comparison build tool tests (F1 tool-side / F4 / F5).

Builds one N/S pair on a full temp copy of the repo (repo tree never
touched), asserts the version derivation, LOAD-line placement, S closure
text, lead normalization equality, the exact difference set, and the F4
wording rule. A negative case mutates the NATIVE_LEAD markers on a second
copy and asserts a non-zero CLI exit with pass:false.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_bundle  # noqa: E402
import make_comparison_build as mcb  # noqa: E402
import check_workbuddy  # noqa: E402

IGNORE = shutil.ignore_patterns(".git", "reports", ".pytest_cache",
                                "__pycache__", "*.pyc")


def _roles():
    return json.loads(
        (ROOT / "policy-source" / "roles-source.json").read_text(encoding="utf-8"))


def _expected_diff_files():
    sids = sorted(_roles())
    return sorted(
        ["agents/telecom-crm-sre-team-lead.md",
         "skills/stability-director/SKILL.md",
         "VERSION", ".codebuddy-plugin/plugin.json"]
        + [f"skills/{sid}/VERSION" for sid in sids]
        + [f"individual-packages/{sid}/skill.zip" for sid in sids])


class ComparisonBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dup = Path(cls.tmp.name) / "repo"
        shutil.copytree(ROOT, cls.dup, ignore=IGNORE)
        cls.manifest = mcb.build_comparison(cls.dup)
        cls.out = Path(cls.manifest["output_dir"])
        if not cls.out.is_absolute():
            cls.out = cls.dup / cls.out

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _arm_lead(self, arm: str, rel: str) -> str:
        return ((self.out / arm / rel).read_text(encoding="utf-8"))

    def test_01_pass_and_exact_difference_set(self):
        m = self.manifest
        self.assertTrue(m["pass"], json.dumps(m, ensure_ascii=False)[:400])
        self.assertEqual(sorted(m["different_files"]), _expected_diff_files())
        self.assertEqual(m["unexpected_diffs"], [])
        self.assertEqual(m["missing_replaced"], [])
        self.assertTrue(m["lead_normalized_equal"])
        self.assertEqual(m["s_replaced_files"],
                         ["agents/telecom-crm-sre-team-lead.md",
                          "skills/stability-director/SKILL.md"])
        self.assertEqual(len(m["repacked_zips"]["N"]), 8)
        self.assertEqual(len(m["repacked_zips"]["S"]), 8)

    def test_02_versions_derived_and_distinct(self):
        m = self.manifest
        srcver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        suffix = re.search(r"-cmp-n\.r([0-9a-f]+)$", m["n_version"])
        self.assertIsNotNone(suffix)
        self.assertEqual(m["n_version"], f"{srcver}-cmp-n.r{suffix.group(1)}")
        self.assertEqual(m["s_version"], f"{srcver}-cmp-s.r{suffix.group(1)}")
        self.assertNotEqual(m["n_version"], m["s_version"])
        for ver in (m["n_version"], m["s_version"]):
            for part in ver.split("-", 1)[1].split("."):
                self.assertFalse(part.isdigit(), part)
        for arm, ver in (("N", m["n_version"]), ("S", m["s_version"])):
            self.assertEqual(
                (self.out / arm / "VERSION").read_text(encoding="utf-8").strip(),
                ver)
            pj = json.loads(
                (self.out / arm / ".codebuddy-plugin" / "plugin.json")
                .read_text(encoding="utf-8"))
            self.assertEqual(pj["version"], ver)
            for v in (self.out / arm).glob("skills/*/VERSION"):
                self.assertEqual(v.read_text(encoding="utf-8").strip(), ver)

    def test_03_load_lines_placement(self):
        m = self.manifest
        for arm, key in (("N", "load_line_n"), ("S", "load_line_s")):
            line = m[key]
            for rel in ("agents/telecom-crm-sre-team-lead.md",
                        "skills/stability-director/SKILL.md"):
                text = self._arm_lead(arm, rel)
                self.assertIn(line, text, f"{arm}/{rel}")
                first_mode = text.find("<!-- MODE:")
                load_pos = text.find(line)
                self.assertGreater(load_pos, 0)
                self.assertLess(load_pos, first_mode,
                                f"LOAD line inside a mode block: {arm}/{rel}")
        # group letter differs, suffix shared
        self.assertEqual(
            m["load_line_n"].replace("LOAD-N-", "LOAD-X-"),
            m["load_line_s"].replace("LOAD-S-", "LOAD-X-"))

    def test_04_s_lead_closure_and_runtime_check(self):
        m = self.manifest
        for rel in ("agents/telecom-crm-sre-team-lead.md",
                    "skills/stability-director/SKILL.md"):
            text = self._arm_lead("S", rel)
            match = mcb._block_re("NATIVE_LEAD").search(text)
            self.assertIsNotNone(match, rel)
            self.assertEqual(match.group(2).strip(),
                             build_bundle.NATIVE_CLOSURE_TEXT.strip())
            self.assertNotEqual(
                match.group(2).strip(),
                mcb._block_re("NATIVE_LEAD")
                .search(self._arm_lead("N", rel)).group(2).strip())
        errors = check_workbuddy.check_prompt(
            self._arm_lead("S", "agents/telecom-crm-sre-team-lead.md"),
            lead=True, runtime=True)
        self.assertEqual(errors, [], errors)

    def test_05_native_closure_text_no_experiment_wording(self):
        text = build_bundle.NATIVE_CLOSURE_TEXT
        for word in ("对照", "实验", "预注册"):
            self.assertNotIn(word, text)

    def test_06_negative_missing_native_lead_exits_nonzero(self):
        tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(tmp2.cleanup)
        dup2 = Path(tmp2.name) / "repo"
        shutil.copytree(ROOT, dup2, ignore=IGNORE)
        for rel in ("agents/telecom-crm-sre-team-lead.md",
                    "skills/stability-director/SKILL.md"):
            p = dup2 / rel
            p.write_text(
                p.read_text(encoding="utf-8")
                .replace("MODE:NATIVE_LEAD:BEGIN", "MODE:NATIVE_LEADX:BEGIN")
                .replace("MODE:NATIVE_LEAD:END", "MODE:NATIVE_LEADX:END"),
                encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "make_comparison_build.py"),
             "--root", str(dup2)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(proc.returncode, 0, proc.stdout[-400:])
        man_path = next(
            (dup2 / "reports" / "comparison-build")
            .glob("*/comparison-manifest.json"))
        man = json.loads(man_path.read_text(encoding="utf-8"))
        self.assertFalse(man["pass"])
        self.assertEqual(man["s_replaced_files"], [])
        self.assertIn("agents/telecom-crm-sre-team-lead.md",
                      man["unexpected_diffs"])
        self.assertIn("skills/stability-director/SKILL.md",
                      man["unexpected_diffs"])


if __name__ == "__main__":
    unittest.main()
