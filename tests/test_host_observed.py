"""Lock host-observed-v3.4 rules: roster in lead SKILL, dispatch marker,
parameter realism, COMPAT scoping. Static text checks only; no model or host calls."""
from __future__ import annotations
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

MEMBER_SIDS = [
    "crm-business-flow", "java-runtime", "linux-infra", "oracle-dba",
    "observability-diagnosis", "change-capacity-dr", "k8s-platform",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> str:
    """Return the frontmatter description field value."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    fm = yaml.safe_load(parts[1])
    return fm.get("description", "")


class LeadSkillRosterTests(unittest.TestCase):
    """1. 团长 SKILL.md 自带名册（主会话只加载 SKILL.md）"""

    def test_01_lead_skill_contains_roster(self):
        text = _read(ROOT / "skills/stability-director/SKILL.md")
        self.assertIn("## 成员名册（何时派给谁）", text)

    def test_02_lead_skill_no_unrendered_placeholders(self):
        text = _read(ROOT / "skills/stability-director/SKILL.md")
        self.assertNotIn("{{TEAM_ROSTER}}", text)
        self.assertNotIn("{{COMMON_CONTRACT}}", text)

    def test_03_member_skills_do_not_carry_roster(self):
        for sid in MEMBER_SIDS:
            with self.subTest(sid=sid):
                text = _read(ROOT / "skills" / sid / "SKILL.md")
                self.assertNotIn("## 成员名册", text)

    def test_04_lead_skill_description_guides_loading(self):
        src = _read(ROOT / "policy-source/skills/stability-director.md")
        desc = _split_frontmatter(src)
        self.assertTrue(desc.startswith("处理任何电信CRM稳定性、故障、告警或会诊请求时，先加载本技能再作答。"))


class DispatchMarkerTests(unittest.TestCase):
    """2. 成员识别派单标记"""

    def test_05_common_md_contains_marker_rule(self):
        text = _read(ROOT / "policy-source/prompts/common.md")
        self.assertIn('任务文本第一行是“【团长派单】”', text)
        self.assertIn('不输出“单模型分析，未进行多专家委派”这类兼容声明', text)

    def test_06_member_compat_blocks_scoped(self):
        for sid in MEMBER_SIDS:
            for rel in [
                f"policy-source/skills/{sid}.md",
                f"policy-source/prompts/roles/telecom-crm-{sid}.md",
            ]:
                with self.subTest(rel=rel):
                    text = _read(ROOT / rel)
                    self.assertIn("只有用户直接打开本角色对话时才按本段回答", text)

    def test_07_lead_native_lead_contains_marker_template(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn('每次派单的第一行固定写"【团长派单】派单标记：', text)

    def test_08_member_native_member_contains_marker_recognition(self):
        for sid in MEMBER_SIDS:
            for rel in [
                f"policy-source/skills/{sid}.md",
                f"policy-source/prompts/roles/telecom-crm-{sid}.md",
            ]:
                with self.subTest(rel=rel):
                    text = _read(ROOT / rel)
                    self.assertIn('任务文本第一行是"【团长派单】"时，按本段工作并把报告返回团长', text)


class DispatchParameterTests(unittest.TestCase):
    """3. 派单参数写实（NATIVE_LEAD 块）"""

    def test_09_native_lead_contains_subagent_type_rule(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("subagent_type 填成员注册 ID", text)
                self.assertIn("name 可填该成员中文名（只作标签", text)

    def test_10_native_lead_bans_bypass_permissions(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("不使用 mode=bypassPermissions", text)

    def test_11_native_lead_mentions_max_turns(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("max_turns", text)

    def test_12_native_lead_retains_host_tool_fallback(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("以当前宿主实际工具定义为准", text)

    def test_13_roster_note_mentions_subagent_type(self):
        text = _read(ROOT / "tools/build_bundle.py")
        self.assertIn("派单时 subagent_type 填注册 ID", text)


class ModeBlockConsistencyTests(unittest.TestCase):
    """4. NATIVE_LEAD 块两源一致 + 成员 NATIVE_MEMBER/COMPAT_MEMBER 两源一致"""

    def _extract_mode_block(self, text: str, label: str) -> str:
        begin = f"<!-- MODE:{label}:BEGIN -->"
        end = f"<!-- MODE:{label}:END -->"
        i = text.find(begin)
        j = text.find(end)
        if i == -1 or j == -1:
            return ""
        return text[i + len(begin):j]

    def test_14_lead_native_lead_blocks_identical(self):
        skill_src = _read(ROOT / "policy-source/skills/stability-director.md")
        role_src = _read(ROOT / "policy-source/prompts/roles/telecom-crm-sre-team-lead.md")
        self.assertEqual(
            self._extract_mode_block(skill_src, "NATIVE_LEAD"),
            self._extract_mode_block(role_src, "NATIVE_LEAD"),
        )

    def test_15_member_native_member_blocks_identical(self):
        for sid in MEMBER_SIDS:
            with self.subTest(sid=sid):
                skill_src = _read(ROOT / f"policy-source/skills/{sid}.md")
                role_src = _read(ROOT / f"policy-source/prompts/roles/telecom-crm-{sid}.md")
                self.assertEqual(
                    self._extract_mode_block(skill_src, "NATIVE_MEMBER"),
                    self._extract_mode_block(role_src, "NATIVE_MEMBER"),
                )

    def test_16_member_compat_member_blocks_identical(self):
        for sid in MEMBER_SIDS:
            with self.subTest(sid=sid):
                skill_src = _read(ROOT / f"policy-source/skills/{sid}.md")
                role_src = _read(ROOT / f"policy-source/prompts/roles/telecom-crm-{sid}.md")
                self.assertEqual(
                    self._extract_mode_block(skill_src, "COMPAT_MEMBER"),
                    self._extract_mode_block(role_src, "COMPAT_MEMBER"),
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
