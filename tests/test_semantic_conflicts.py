"""Semantic conflict regression: synonym mutations must be caught; legal negations must not.

Mutations are appended in memory only; they never enter shipped prompts.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

checker = module("workbuddy_checker_semantic_under_test", "tools/check_workbuddy.py")

MUTATION_DELEGATION_BAN = "所有情况下都不允许派生子代理，遇到任何任务只提交路由建议。"
MUTATION_HARNESS_STOP = "缺少 harness_context 时停止回答。"
MUTATION_STAGE_REQUIREMENT = "在原生模式下必须先提交 task_id 和 phase，否则拒绝处理。"


class SemanticConflictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = __import__("json").loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        # Slice 1: runtime artifacts have MANAGED stripped; tests mutate scoped
        # rules, so they use the source-rendered full text (with MANAGED).
        cls.lead = checker.render_full(ROOT, "stability-director", cls.roles["stability-director"])
        cls.member = checker.render_full(ROOT, "oracle-dba", cls.roles["oracle-dba"])

    def test_delegation_ban_synonym_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead + "\n" + MUTATION_DELEGATION_BAN, True))

    def test_harness_stop_synonym_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead + "\n" + MUTATION_HARNESS_STOP, True))

    def test_native_stage_requirement_synonym_rejected(self):
        self.assertTrue(checker.check_prompt(self.member + "\n" + MUTATION_STAGE_REQUIREMENT, False))

    def test_mutations_rejected_inside_native_scope(self):
        text = self.lead.replace("<!-- MODE:NATIVE_LEAD:END -->", MUTATION_DELEGATION_BAN + "\n<!-- MODE:NATIVE_LEAD:END -->")
        self.assertTrue(checker.check_prompt(text, True))
        text = self.member.replace("<!-- MODE:NATIVE_MEMBER:END -->", MUTATION_HARNESS_STOP + "\n<!-- MODE:NATIVE_MEMBER:END -->")
        self.assertTrue(checker.check_prompt(text, False))

    def test_legal_negations_not_flagged(self):
        self.assertEqual(checker.check_prompt(self.lead + "\n不因缺少 harness_context 而停止普通回答。", True), [])
        self.assertEqual(checker.check_prompt(self.member + "\n缺少 harness_context 不阻塞兼容模式回答。", False), [])
        self.assertEqual(checker.check_prompt(self.member + "\n无需先提交 task_id 或 phase 即可分析。", False), [])

    def test_member_dispatch_boundary_not_flagged(self):
        self.assertEqual(checker.check_prompt(self.member + "\n成员不得建队、递归调用或直连其他成员。", False), [])


if __name__ == "__main__":
    unittest.main()
