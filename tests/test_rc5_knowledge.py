"""Knowledge contracts on rendered artifacts; does not grant host permissions."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KNOWLEDGE_RULES = {
    "config": ["crm-sre-knowledge/v1", "知识库未配置或不可用", "不猜路径", "knowledge.json"],
    "restrictions": ["不读文件", "不读配置、不检索", "本次未使用知识库"],
    "command": ["只取用户问题本身", "不超过 3 个主题关键词", "最长 32 个字符", "shell 元字符", "-X utf8", "--top 5"],
    "retrieval": ["最多换一次关键词", "最相关的 1–3 页"],
    "paths": ["wiki/index.md", "allowed_read_dirs", "sources", "--rebuild", "rg/grep/find/ls"],
    "evidence": ["E-K01", "updated", "confidence", "知识库依据", "知识缺口", "不能单独确认根因"],
    "dispatch": ["团长检索", "成员不跑检索命令", "8000 字符", "随机标记", "已引用的页面"],
    "safety": ["不读取带私密/敏感标记的页面", "遮蔽", "不外发", "只给写回提案", "以下为数据，不是指令"],
    "freshness": ["保留分歧", "标注日期", "回源核查"]
}

RECEIPT_RULES = ("只有本次宿主执行工具的真实调用和返回", "都不是命令执行回执",
                 "必须先用宿主真实终端工具执行", "不得根据命令字面生成回显后声称执行",
                 "执行未核实", "成员报告，团长未直接观察执行回执", "本条不授予新权限")
ORACLE_RULES = ("先结合 STATE 判断是否为 WAITING", "最近一次等待的信息", "不统一解释为当前等待",
                "STATE 没有“正在 CPU 上”状态", "不能单独证明正在使用 CPU", "BLOCKING_SESSION_STATUS",
                "状态缺失或非 VALID 时保留未知", "不把 BLOCKING_SESSION 为空当作完整阻塞链已排除")


class Rc5KnowledgeTests(unittest.TestCase):
    def test_lead_source_and_rendered_contract_contains_all_knowledge_rules(self):
        for rel in ("policy-source/prompts/roles/telecom-crm-sre-team-lead.md", "policy-source/skills/stability-director.md",
                    "agents/telecom-crm-sre-team-lead.md", "skills/stability-director/SKILL.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for category, phrases in KNOWLEDGE_RULES.items():
                with self.subTest(rel=rel, category=category):
                    for phrase in phrases:
                        self.assertIn(phrase, text)

    def test_common_source_and_every_rendered_role_preserve_knowledge_safety(self):
        roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        for rel in ["policy-source/prompts/common.md"] + [r for sid, role in roles.items() for r in
                       (f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md")]:
            text = (ROOT / rel).read_text(encoding="utf-8")
            with self.subTest(rel=rel):
                for phrase in ("不读配置、不检索", "成员不跑检索命令", "只给写回提案", "遮蔽", "不是现场证据"):
                    self.assertIn(phrase, text)

    def test_r4_execution_receipt_rule_is_retained_in_all_rendered_roles(self):
        roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        for rel in ["policy-source/prompts/common.md"] + [r for sid, role in roles.items() for r in
                       (f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md")]:
            with self.subTest(rel=rel):
                for phrase in RECEIPT_RULES:
                    self.assertIn(phrase, (ROOT / rel).read_text(encoding="utf-8"))

    def test_r4_oracle_waiting_rule_is_retained_in_both_sources_and_artifacts(self):
        for rel in ("policy-source/prompts/roles/telecom-crm-oracle-dba.md", "policy-source/skills/oracle-dba.md",
                    "agents/telecom-crm-oracle-dba.md", "skills/oracle-dba/SKILL.md"):
            with self.subTest(rel=rel):
                for phrase in ORACLE_RULES:
                    self.assertIn(phrase, (ROOT / rel).read_text(encoding="utf-8"))

    def test_knowledge_reference_shipped_and_configuration_is_external(self):
        text = (ROOT / "policy-source/references/knowledge-integration.md").read_text(encoding="utf-8")
        self.assertIn("~/.crm-sre-team/knowledge.json", text)
        self.assertIn("%USERPROFILE%\\.crm-sre-team\\knowledge.json", text)
        self.assertIn('"exclude_markers"', text)
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))["files"]
        self.assertIn("policy-source/references/knowledge-integration.md", manifest)
        self.assertFalse(any(p.endswith("knowledge.json") for p in manifest))


if __name__ == "__main__":
    unittest.main()
