"""Probe build tool tests (F2): version derivation, member/lead marker wording,
zip repack, out-of-repo --out survival, and repo-root immutability.

Builds one probe package into a temp dir (outside the repo) and asserts
on the manifest and artifacts. Static/evidence checks only — no host.
"""
from __future__ import annotations

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import make_probe_build as mpb  # noqa: E402

MARKER_ECHO = "回复开头单独一行原样输出本行（不含行首引用符号）"
OLD_ECHO = "回复开头逐行原样输出所有以 PROBE- 开头的行"


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
                self.assertIn(m["lead_markers"]["marker_ls"], body)
            else:
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

    def test_06_lead_markers_in_manifest_and_bodies(self):
        m = self.manifest
        expected = {
            "marker_la": f"PROBE-LA-{m['marker_suffix']}",
            "marker_ls": f"PROBE-LS-{m['marker_suffix']}",
        }
        self.assertEqual(m["lead_markers"], expected)
        manifest_on_disk = json.loads(
            (self.out / "probe-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest_on_disk["lead_markers"], expected)
        for rel, marker in (
            ("agents/telecom-crm-sre-team-lead.md", expected["marker_la"]),
            ("skills/stability-director/SKILL.md", expected["marker_ls"]),
        ):
            with self.subTest(rel=rel):
                text = (self.out / rel).read_text(encoding="utf-8")
                self.assertIn(f"> {marker}", text)
                self.assertIn(MARKER_ECHO, text)
                self.assertNotIn(OLD_ECHO, text)

    def test_07_disallow_injected_only_into_target_probe_agent(self):
        snapshot = {rel: (ROOT / rel).read_bytes() for rel in json.loads(
            (ROOT / "release-manifest.json").read_text(encoding="utf-8"))["files"]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "restricted-probe"
            manifest = mpb.build_probe(ROOT, output, {}, {"oracle-dba": ["Bash"]})
            self.assertEqual(manifest["overrides"]["disallowedTools"], {"oracle-dba": ["Bash"]})
            for sid, role in _roles().items():
                agent_rel = f"agents/{role['agent']}.md"
                original = yaml.safe_load(snapshot[agent_rel].decode("utf-8").split("---", 2)[1])
                actual = yaml.safe_load((output / agent_rel).read_text(encoding="utf-8").split("---", 2)[1])
                expected = dict(original)
                if sid == "oracle-dba":
                    expected["disallowedTools"] = ["Bash"]
                with self.subTest(sid=sid):
                    self.assertEqual(actual, expected)
                    skill = (output / "skills" / sid / "SKILL.md").read_text(encoding="utf-8")
                    self.assertNotIn("disallowedTools:", skill)
                    with zipfile.ZipFile(output / "individual-packages" / sid / "skill.zip") as archive:
                        self.assertEqual(archive.read(f"{sid}/SKILL.md"), skill.encode("utf-8"))
        self.assertEqual(snapshot, {rel: (ROOT / rel).read_bytes() for rel in snapshot})

    def test_08_invalid_disallow_rejected_before_creating_output(self):
        overrides = [({}, {"stability-director": ["Bash"]}),
                     ({}, {"unknown-member": ["Bash"]}),
                     ({}, {"oracle-dba": []}),
                     ({}, {"oracle-dba": ["Bash;echo"]}),
                     ({"oracle-dba": 1}, {"oracle-dba": ["Bash"]})]
        with tempfile.TemporaryDirectory() as directory:
            for index, (turns, disallow) in enumerate(overrides):
                output = Path(directory) / str(index)
                with self.subTest(turns=turns, disallow=disallow):
                    with self.assertRaises(ValueError):
                        mpb.build_probe(ROOT, output, turns, disallow)
                    self.assertFalse(output.exists())

    def test_09_cli_and_manifest_qualify_probe_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli-probe"
            stream = StringIO()
            with patch.object(sys, "argv", ["make_probe_build.py", "--root", str(ROOT),
                                           "--out", str(output), "--disallow", "oracle-dba=Bash"]):
                with redirect_stdout(stream):
                    mpb.main()
            summary = json.loads(stream.getvalue())
            manifest = json.loads((output / "probe-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["evidence_note"], mpb.PROBE_EVIDENCE_NOTE)
            self.assertIn(mpb.PROBE_EVIDENCE_NOTE, summary["cheat_sheet"])
            self.assertIn("auxiliary only", summary["cheat_sheet"])
            self.assertIn("Missing PROBE output does not imply missing loading", summary["cheat_sheet"])
            self.assertNotIn("=> Agent text loaded", summary["cheat_sheet"])
            self.assertEqual(summary["overrides"]["disallowedTools"], {"oracle-dba": ["Bash"]})

    def test_10_every_probe_line_is_self_contained_and_ends_before_body(self):
        expected_rule = (
            "辅助加载暗号；回复开头单独一行原样输出本行（不含行首引用符号），"
            "保留从暗号到结束标记的全部字符，不增补、不续写、不替换，不拼接后续正文"
        )
        targets = [
            ("agents/telecom-crm-sre-team-lead.md", self.manifest["lead_markers"]["marker_la"]),
            ("skills/stability-director/SKILL.md", self.manifest["lead_markers"]["marker_ls"]),
        ]
        for sid, role in _roles().items():
            if sid != "stability-director":
                markers = self.manifest["markers"][role["agent"]]
                targets += [(f"agents/{role['agent']}.md", markers["marker_c"]),
                            (f"skills/{sid}/SKILL.md", markers["marker_d"])]
        self.assertEqual(len(targets), 16)
        for rel, marker in targets:
            with self.subTest(rel=rel):
                body = (self.out / rel).read_text(encoding="utf-8")
                lines = body.splitlines()
                expected = f"> {marker}｜{expected_rule}｜END"
                self.assertEqual([line for line in lines if line.startswith("> PROBE-")], [expected])
                self.assertEqual(lines[lines.index(expected) + 1], "")
                self.assertIn(mpb.PROBE_COPY_RULE + "\n\n" + expected, body)
                self.assertNotIn(OLD_ECHO, body)
                if rel.startswith("skills/"):
                    self.assertNotIn("此 SKILL.md", expected)
                self.assertIn("Host evidence is authoritative", self.manifest["evidence_note"])

    def test_11_marker_injection_preserves_following_text_verbatim(self):
        following = "此 SKILL.md 的正文不属于暗号。\n后续段落保留原内容。"
        actual = mpb._inject_marker("\n# 测试标题\n\n" + following, "> PROBE-D-a1b2c3d4")
        marker, remaining = actual.split("｜END\n\n", 1)
        self.assertIn(MARKER_ECHO, marker)
        self.assertNotIn("此 SKILL.md", marker)
        self.assertEqual(remaining, following)

if __name__ == "__main__":
    unittest.main()
