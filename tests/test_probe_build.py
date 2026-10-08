"""Probe build tool tests (F2): version derivation, marker wording, zip
repack, out-of-repo --out survival, and repo-root immutability.

Builds one probe package into a temp dir (outside the repo) and asserts
on the manifest and artifacts. Static/evidence checks only — no host.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_probe_build as mpb  # noqa: E402

MARKER_ECHO = "回复开头逐行原样输出所有以 PROBE- 开头的行"
OLD_ECHO = "回复首行原样输出本行暗号"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "mpb_under_test", ROOT / "tools/make_probe_build.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _roles():
    return json.loads(
        (ROOT / "policy-source" / "roles-source.json").read_text(encoding="utf-8"))


class ProbeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "probe-out"
        cls.snap = cls._snapshot()
        cls.manifest = mpb.build_probe(ROOT, cls.out, {}, {})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _snapshot(cls):
        out = {}
        for sub in ("agents", "skills"):
            for p in sorted((ROOT / sub).rglob("*")):
                if p.is_file():
                    out[p.as_posix()] = p.read_bytes()
        return out

    def test_01_versions_derived_and_semver_safe(self):
        m = self.manifest
        srcver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        pv = m["probe_version"]
        suffix = m["marker_suffix"]
        self.assertEqual(pv, f"{srcver}-probe.r{suffix}")
        prerelease = pv.split("-", 1)[1]
        for part in prerelease.split("."):
            self.assertFalse(part.isdigit(), f"numeric prerelease id: {part}")
        pj = json.loads(
            (self.out / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(pj["version"], pv)
        self.assertEqual(
            (self.out / "VERSION").read_text(encoding="utf-8").strip(), pv)
        for v in sorted((self.out / "skills").glob("*/VERSION")):
            self.assertEqual(v.read_text(encoding="utf-8").strip(), pv)
        self.assertIn("probe_version", m)
        self.assertEqual(
            m["lock_note"],
            "prompt-bundles.lock 与 BUNDLE-LOCK.json 未随暗号/版本重算（实验副本）")

    def test_02_marker_wording_per_member(self):
        m = self.manifest
        self.assertEqual(len(m["markers"]), 7)
        for sid, role in _roles().items():
            if sid == "stability-director":
                continue
            agent = (self.out / "agents" / (role["agent"] + ".md")).read_text(
                encoding="utf-8")
            self.assertIn(m["markers"][role["agent"]]["marker_c"], agent)
            self.assertIn(MARKER_ECHO, agent)
            self.assertNotIn(OLD_ECHO, agent)
            skill = (self.out / "skills" / sid / "SKILL.md").read_text(
                encoding="utf-8")
            self.assertIn(m["markers"][role["agent"]]["marker_d"], skill)
            self.assertIn(MARKER_ECHO, skill)
            self.assertNotIn(OLD_ECHO, skill)

    def test_03_member_zips_repacked_with_markers(self):
        m = self.manifest
        # V4: all 8 zips (including stability-director) are repacked from
        # the probe skills/ tree, and each zip's VERSION must equal
        # probe_version.
        self.assertEqual(len(m["repacked_zips"]), 8)
        for sid, role in _roles().items():
            zp = self.out / "individual-packages" / sid / "skill.zip"
            with zipfile.ZipFile(zp) as z:
                names = z.namelist()
                version = z.read(f"{sid}/VERSION").decode("utf-8").strip()
                body = z.read(f"{sid}/SKILL.md").decode("utf-8")
            self.assertIn(f"individual-packages/{sid}/skill.zip",
                          m["repacked_zips"])
            self.assertEqual(version, m["probe_version"],
                             f"{sid} zip VERSION != probe_version")
            self.assertIn(f"{sid}/BUNDLE-LOCK.json", names)
            if sid == "stability-director":
                continue  # 团长不注入暗号，仅核 VERSION 与重打包
            self.assertIn(m["markers"][role["agent"]]["marker_d"], body)
            self.assertIn(MARKER_ECHO, body)

    def test_04_out_of_repo_out_survives(self):
        m = self.manifest
        self.assertTrue((self.out / "probe-manifest.json").exists())
        # out dir is a temp dir outside the repo root: display path is absolute
        displayed = Path(m["probe_package_dir"])
        self.assertTrue(displayed.is_absolute(), m["probe_package_dir"])
        self.assertTrue((displayed / "probe-manifest.json").exists())

    def test_05_repo_root_agents_skills_untouched(self):
        self.assertEqual(self.snap, self._snapshot())


if __name__ == "__main__":
    unittest.main()
