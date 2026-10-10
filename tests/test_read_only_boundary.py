"""Read-only boundary static regression: positive markers and mutation negatives.

Text-level only. It does not prove model or host runtime behavior.
"""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


checker = module("workbuddy_checker_read_only_under_test", "tools/check_workbuddy.py")


class ReadOnlyBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        cls.policy = json.loads((ROOT / "policies/runtime-contract.json").read_text(encoding="utf-8"))
        # Slice 1: runtime artifacts have MANAGED stripped; tests mutate the
        # managed block, so they use the source-rendered full text (with MANAGED).
        cls.lead = checker.render_full(ROOT, "stability-director", cls.roles["stability-director"])
        cls.member = checker.render_full(ROOT, "oracle-dba", cls.roles["oracle-dba"])

    def test_01_every_entry_declares_read_only_boundary(self):
        for sid, role in self.roles.items():
            for rel, lead in [(f"agents/{role['agent']}.md", sid == "stability-director"),
                              (f"skills/{sid}/SKILL.md", sid == "stability-director")]:
                with self.subTest(path=rel):
                    # Slice 1: built artifacts carry runtime=True (MANAGED stripped).
                    self.assertEqual(checker.check_prompt((ROOT / rel).read_text(encoding="utf-8"), lead, runtime=True), [])

    def test_02_manual_entries_declare_read_only_boundary(self):
        for sid in self.roles:
            with self.subTest(skill=sid):
                text = (ROOT / f"skills/{sid}/MANUAL-MODE.md").read_text(encoding="utf-8")
                self.assertIn("只读诊断与执行边界", text)
                for phrase in checker.BLANKET_READONLY_BANS:
                    self.assertNotIn(phrase, text)

    def test_03_shared_contract_scopes_relaxation_to_non_managed(self):
        self.assertIn("## 只读诊断与执行边界", self.lead)
        for marker in checker.READ_ONLY_BOUNDARY_MARKERS:
            self.assertIn(marker, self.lead)

    def test_04_read_only_boundary_rejected_in_managed_scope(self):
        text = self.lead.replace(
            "<!-- MODE:MANAGED_HARNESS:BEGIN -->",
            "<!-- MODE:MANAGED_HARNESS:BEGIN -->\n生产只读执行：宿主已授权即可直接查询生产。")
        self.assertTrue(checker.check_prompt(text, True))

    def test_05_missing_read_only_section_rejected(self):
        text = self.member
        for marker in checker.READ_ONLY_BOUNDARY_MARKERS:
            text = text.replace(marker, "")
        self.assertTrue(any(e.startswith("missing_read_only_boundary:") for e in checker.check_prompt(text, False)))

    def test_06_policy_read_only_block_valid(self):
        self.assertEqual(checker.read_only_boundary_errors(self.policy), [])

    def test_07_relaxation_leaking_into_managed_rejected(self):
        p = deepcopy(self.policy)
        p["read_only_boundary"]["applies_only_to"].append("MANAGED_HARNESS")
        self.assertIn("read_only_relaxation_leaks_into_managed", checker.read_only_boundary_errors(p))

    def test_08_production_read_overclaim_rejected(self):
        p = deepcopy(self.policy)
        p["read_only_boundary"]["production_read_execution"] = "ENABLED"
        self.assertIn("production_read_overclaim", checker.read_only_boundary_errors(p))

    def test_09_production_write_boundary_change_rejected(self):
        p = deepcopy(self.policy)
        p["read_only_boundary"]["production_write"] = "ALLOWED_WITH_QUERY_APPROVAL"
        self.assertIn("production_write_boundary_changed", checker.read_only_boundary_errors(p))

    def test_10_missing_read_only_block_rejected(self):
        p = deepcopy(self.policy)
        p.pop("read_only_boundary")
        self.assertIn("read_only_boundary_missing", checker.read_only_boundary_errors(p))

    def test_11_unscoped_managed_read_only_rejected(self):
        p = deepcopy(self.policy)
        p["managed_mode"]["production_read_execution"] = "ALLOWED"
        self.assertIn("unscoped_managed_read_only_policy", checker.read_only_boundary_errors(p))

    def test_12_http_method_keyword_decision_required(self):
        p = deepcopy(self.policy)
        p["read_only_boundary"]["http_method_is_not_the_decision"] = False
        self.assertIn("http_method_decision_missing", checker.read_only_boundary_errors(p))

    def test_13_production_tools_still_empty(self):
        self.assertEqual(self.policy["production_tools"], [])
        self.assertFalse(self.policy["production_executor"])

    def test_14_exfiltration_primitives_absent_from_every_entry(self):
        """Negative assertion: exfiltration primitives may only appear inside a prohibition clause."""
        recipes = ["169.254.169.254/latest/meta-data", "curl -X POST -d @", "--data-binary @",
                   "--upload-file", "-T /etc/", "$(cat ", "~/.aws/credentials", "-K ~/.curlrc"]
        negation = ("不作为", "不放行", "不因", "不属于", "不自动", "不得", "不能", "非")
        targets = [ROOT / f"agents/{role['agent']}.md" for role in self.roles.values()]
        targets += [ROOT / f"skills/{sid}/SKILL.md" for sid in self.roles]
        targets += [ROOT / f"skills/{sid}/MANUAL-MODE.md" for sid in self.roles]
        targets += [ROOT / f"skills/{sid}/references/{name}" for sid in self.roles
                    for name in ("offline-contract.md", "risk-and-command-gates.md")]
        for path in sorted(set(targets)):
            text = path.read_text(encoding="utf-8")
            for recipe in recipes:
                for line in text.splitlines():
                    if recipe not in line:
                        continue
                    with self.subTest(path=path.relative_to(ROOT).as_posix(), recipe=recipe):
                        self.assertTrue(any(word in line for word in negation),
                                        f"{recipe} appears outside a prohibition clause: {line.strip()[:120]}")

    def test_15_redirect_and_metadata_limits_present(self):
        for marker in ("不自动覆盖重定向", "云元数据端点", "不作为查询目标或请求体来源"):
            self.assertIn(marker, self.lead)
        for sid in self.roles:
            with self.subTest(skill=sid):
                self.assertIn("不自动覆盖重定向", (ROOT / f"skills/{sid}/MANUAL-MODE.md").read_text(encoding="utf-8"))

    def test_16_removing_all_boundary_markers_is_rejected(self):
        """A vacuous text that satisfies no marker set must not pass the checker."""
        self.assertTrue(any(e.startswith("missing_read_only_boundary:") or e == "missing_mode_blocks"
                            for e in checker.check_prompt("# 空文档\n", True)))

    def test_17_all_tasks_including_non_search_diagnosis_forbid_credentials(self):
        clause = "任何任务都不读取凭据文件或环境变量，包括排障、诊断和联网检索。"
        for sid, role in self.roles.items():
            paths = [f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md",
                     f"skills/{sid}/MANUAL-MODE.md", "manual-mode/single-model.md"]
            for rel in paths:
                with self.subTest(entry=rel):
                    text = (ROOT / rel).read_text(encoding="utf-8")
                    self.assertIn(clause, text)
                    self.assertNotIn("不为检索去读取", text)
            full = checker.render_full(ROOT, sid, role)
            with self.subTest(source=sid):
                self.assertIn(clause, full.split("## 运行模式选择：", 1)[0])

    def test_18_search_only_prohibition_cannot_cover_non_search_diagnosis(self):
        clause = "任何任务都不读取凭据文件或环境变量，包括排障、诊断和联网检索。"
        scenario = "\n合成非检索排障：检查本地凭据文件和环境变量以定位身份问题。\n"
        for sid, role in self.roles.items():
            runtime = (ROOT / f"skills/{sid}/SKILL.md").read_text(encoding="utf-8")
            for text, is_runtime in [(runtime, True), (checker.render_full(ROOT, sid, role), False)]:
                with self.subTest(role=sid, runtime=is_runtime):
                    self.assertEqual(checker.check_prompt(text + scenario, sid == "stability-director", runtime=is_runtime), [])
                    weakened = text.replace(clause, "仅联网检索时不读取凭据文件或环境变量。", 1)
                    self.assertIn("missing_all_task_credential_boundary",
                                  checker.check_prompt(weakened + scenario, sid == "stability-director", runtime=is_runtime))


if __name__ == "__main__":
    unittest.main(verbosity=2)
