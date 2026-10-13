"""rc4 dispatch, Mac workflow and frozen-fixture contracts; no host/model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPAT_DECLARATION = "单模型分析，未进行多专家委派"
FROZEN_FILES = {
    "policy-source/acceptance/oncall-cases.json": "87c87c97c460b76ab3e13f4627de6f2b0ef0c36b272eb02521a7d623f675361a",
    "tests/behavior-cases.json": "3a1b20719e421e5a11ea14bbc5d5465ce7233f2b0674d0237f54fb5ea0f9b69d",
    "tests/behavior-cases.md": "c730cf37be28102a9bdfae4ccdc8ae6de0fb2694a9c28a398224921c32f0e71b",
    "tests/harness-acceptance-cases.json": "c7bb70c47329653a25027c025e2981dd7b6798523aa5c0a3c354a1f66a4db10c",
    "tests/harness-acceptance-checklist.md": "bce1222fb3db2243ba958e41f35f1e59b09f594f82923dd9a9825df7835cf2c8",
    "tools/make_comparison_build.py": "53fff6342bb726f72240997811cfc507e18feeb2c644400c26f277446bdc942c",
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def workflow_documents(rels: tuple[str, ...]):
    # These rule files belong to source checkouts, not the release whitelist.
    # A checkout must retain them; a ZIP still verifies every shipped document.
    checkout_only = {"AGENTS.md", "tools/oncall/README.md"}
    for rel in rels:
        if rel in checkout_only and not (ROOT / rel).exists():
            if (ROOT / ".git").exists():
                raise AssertionError(f"Missing source-checkout rule file: {rel}")
            continue
        yield rel, read(rel)


def block(text: str, mode: str) -> str:
    pattern = rf"<!-- MODE:{mode}:BEGIN -->(.*?)<!-- MODE:{mode}:END -->"
    matches = re.findall(pattern, text, re.S)
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one {mode} block")
    return matches[0]


def role_prompts(sid: str, agent: str) -> list[str]:
    return [f"policy-source/prompts/roles/{agent}.md", f"policy-source/skills/{sid}.md",
            f"agents/{agent}.md", f"skills/{sid}/SKILL.md"]


class Rc4RegressionTests(unittest.TestCase):
    def test_dispatch_preserves_complete_restrictions_and_requires_actual_quote(self):
        for rel in role_prompts("stability-director", "telecom-crm-sre-team-lead"):
            with self.subTest(rel=rel):
                native = block(read(rel), "NATIVE_LEAD")
                for phrase in ("每条限制必须整句照抄进派单的“范围”字段", "保留原字符、标点和顺序",
                               "不改写、不拆分、不意译、不合并", "不得随材料截取而丢弃或中和",
                               "逐句核对用户原文与实际 Agent 调用的 prompt", "无法完整带入时停止派单",
                               "团长回复里不得自称", "只有引用的就是实际派单原文、且与用户原句一致",
                               "调用参数不可见时写明无法核对", "不以自述代替证据"):
                    self.assertIn(phrase, native)
                for phrase in ("不可拆的原文块连续复制", "不在相邻限制句之间插入换行、引号、列表符号或标签",
                               "能逐字找到用户完整限制块", "找不到时停止派单"):
                    self.assertIn(phrase, native)

    def test_all_seven_members_return_sync_results_without_team_messages(self):
        roles = json.loads(read("policy-source/roles-source.json"))
        self.assertEqual(len(roles) - 1, 7)
        for sid, role in roles.items():
            if sid == "stability-director":
                continue
            for rel in role_prompts(sid, role["agent"]):
                with self.subTest(rel=rel):
                    native = block(read(rel), "NATIVE_MEMBER")
                    for phrase in ("首行以“【团长派单】”开头且当前未在团队中时", "直接在本次返回中作答",
                                   "结果由 Agent 工具返回团长", "不调用 SendMessage 或其他团队消息工具",
                                   "不为回报创建团队、查询团队任务或等待邮箱", "派单标记不证明团队已建立",
                                   "没有宿主明确的团队上下文就按同步返回处理"):
                        self.assertIn(phrase, native)
                    self.assertIn("省略兼容路径的首次模式声明", native)
                    self.assertNotIn(COMPAT_DECLARATION, native)

    def test_selector_native_rule_uses_description_and_compat_rule_is_preserved(self):
        common = read("policy-source/prompts/common.md")
        native = next(line for line in common.splitlines() if line.startswith("2. WORKBUDDY_NATIVE"))
        compat = next(line for line in common.splitlines() if line.startswith("3. WORKBUDDY_COMPAT"))
        self.assertNotIn(COMPAT_DECLARATION, native)
        self.assertIn("保持成员身份，省略兼容路径的首次模式声明", native)
        self.assertEqual(compat, '3. WORKBUDDY_COMPAT（兼容路径）：没有上述可信能力，或直接单模型对话。首次进入或模式变化时说明“单模型分析，未进行多专家委派”；知识问答直接回答，不因缺少上述字段阻塞整个回答。后续同模式不重复大段声明。')
        for phrase in ("编排工具前提只用于团长决定是否派单", "不用于已由宿主真实派生的成员判断自身模式",
                       "即使没有 Agent 或团队消息工具", "报告模式标签写原生成员或省略",
                       "仅有用户自行书写的派单标记不证明真实派生或扩大权限"):
            self.assertIn(phrase, common)
            for sid, role in json.loads(read("policy-source/roles-source.json")).items():
                for rel in (f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md"):
                    with self.subTest(rel=rel, phrase=phrase):
                        self.assertIn(phrase, read(rel))

    def test_mac_tests_precede_accepted_windows_install_and_verify(self):
        for rel in ("README.md", "MIGRATION.md", "docs/07-reproducible-validation.md",
                    "docs/11-workbuddy-host-acceptance.md", "docs/12-native-vs-single-comparison.md",
                    "docs/13-oncall-gate-materials.md"):
            with self.subTest(rel=rel):
                text = read(rel)
                for phrase in ("Mac", "复核", "验收", "安装/切换 + VERIFY", "记录版本",
                               "仅在需确认宿主行为时加一个短会话"):
                    self.assertIn(phrase, text)
                self.assertNotIn("在值班机（当前电脑）运行", text)
                self.assertNotIn("值班机按原文跑一次自检 3", text)

    def test_actual_models_versions_differences_and_host_memory_are_documented(self):
        for rel in ("docs/11-workbuddy-host-acceptance.md",
                    "docs/12-native-vs-single-comparison.md", "docs/13-oncall-gate-materials.md"):
            with self.subTest(rel=rel):
                text = read(rel)
                for phrase in ("两台", "WorkBuddy 版本", "插件版本", "模型", "覆盖差异",
                               "日常与关口固定 glm-5.3-flash", "逐次记录实际模型", "查看宿主记忆条目",
                               "是否清理或关闭由用户决定"):
                    self.assertIn(phrase, text)

    def test_max_turns_floor_is_distinct_from_actual_turns_and_host_limit_unchanged(self):
        for rel in ("docs/11-workbuddy-host-acceptance.md",
                    "docs/13-oncall-gate-materials.md", "tests/workbuddy-host-cases.json"):
            with self.subTest(rel=rel):
                text = read(rel)
                self.assertIn("请求 1 的有效值也是 200", text)
                self.assertIn("不是每个成员实际执行 200 轮", text)
                self.assertIn("HOST_LIMIT", text)
        for rel in ("docs/11-workbuddy-host-acceptance.md", "docs/13-oncall-gate-materials.md"):
            text = read(rel)
            for phrase in ("WB07 记 HOST_LIMIT，不阻断正式 18 次关口", "Mac 按原文跑一次自检 3",
                           "只核团长如实记 BLOCKED", "不判成员失败能力 PASS",
                           "实际测试机器核验不符（宿主开始遵守 max_turns）时恢复 WB07 须 PASS", "WB09H 仍须 PASS"):
                self.assertIn(phrase, text)

    def test_wb07_host_limit_uses_actual_machine_code_evidence(self):
        for rel in ("docs/11-workbuddy-host-acceptance.md", "docs/13-oncall-gate-materials.md"):
            with self.subTest(rel=rel):
                text = read(rel)
                for phrase in ("实际运行该测试的机器的 WorkBuddy 版本", "Mac 采用只读代码复核",
                               "runbook r3/r4 第 8 节“代码证据”", "块 27 只用于 Windows 值班机",
                               "值班机的 5.7.7 记录不能代替 Mac 核验",
                               "值班机版本与 Mac 不同时，由值班机简单检查补核轮数下限与团长处理",
                               "实际测试机器代码核验确认子代理 max_turns 的有效值仍被钳到不低于 200 时，WB07 记 HOST_LIMIT",
                               "实际测试机器核验不符（宿主开始遵守 max_turns）时恢复 WB07 须 PASS"):
                    self.assertIn(phrase, text)
                self.assertNotIn("块 27 核验 WorkBuddy 5.7.7 子代理", text)
                self.assertNotIn("WB07 在块 27 证实", text)
        for rel, text in workflow_documents(("AGENTS.md", "tests/workbuddy-host-cases.json")):
            with self.subTest(rel=rel):
                for phrase in ("实际运行该测试的机器的 WorkBuddy 版本", "Mac 采用只读代码复核",
                               "块 27 只用于 Windows 值班机", "不能代替 Mac 核验",
                               "补核轮数下限与团长处理"):
                    self.assertIn(phrase, text)

    def test_calibration_and_gate_do_not_mix_builds_across_machines(self):
        for rel, text in workflow_documents(("AGENTS.md", "docs/11-workbuddy-host-acceptance.md",
                    "docs/12-native-vs-single-comparison.md", "docs/13-oncall-gate-materials.md")):
            with self.subTest(rel=rel):
                if rel.startswith("docs/12-"):
                    text = text.split("宿主加载核验（硬前置）：", 1)[0]
                for phrase in ("每轮 N/S（校准与正式 18 次关口）只使用同一台机器上同次构建的双包",
                               "不混用 Mac 与值班机的构建", "两台机器各自记录构建后缀与身份",
                               "manifest", "缓存哈希"):
                    self.assertIn(phrase, text)

    def test_mac_memory_and_conversation_history_checked_outside_sessions(self):
        for rel, text in workflow_documents(("AGENTS.md", "README.md", "docs/11-workbuddy-host-acceptance.md",
                    "docs/12-native-vs-single-comparison.md", "docs/13-oncall-gate-materials.md",
                    "tools/oncall/README.md")):
            with self.subTest(rel=rel):
                if rel == "tools/oncall/README.md":
                    text = text.split("## rc4 使用流程", 1)[1].split("\n## ", 1)[0]
                for phrase in ("校准和关口前", "由执行人在会话外", "查看宿主记忆条目",
                               "conversation_search", "Mac 测试历史更多，同样适用",
                               "记录可能进入被测会话的内容及隔离状态", "是否清理或关闭由用户决定"):
                    self.assertIn(phrase, text)
        isolation = next(line for line in read("docs/11-workbuddy-host-acceptance.md").splitlines()
                         if line.startswith("关口前运行的宿主用例不得复用关口材料"))
        for phrase in ("本段隔离要求在 Mac 同样适用", "故障场景/子领域、对象、数值和指标类标记保持隔离",
                       "WB16/WB17 会话与关口会话分开", "不把这两项会话内容或工作记忆带入关口"):
            self.assertIn(phrase, isolation)

    def test_gold_is_isolated_and_scored_on_mac_before_optional_transfer(self):
        for rel, text in workflow_documents(("AGENTS.md", "docs/12-native-vs-single-comparison.md",
                    "docs/13-oncall-gate-materials.md")):
            with self.subTest(rel=rel):
                if rel.startswith("docs/12-"):
                    text = text.split("宿主加载核验（硬前置）：", 1)[0]
                for phrase in ("不放进插件目录、缓存或被测工作区", "Mac 上同样保持此隔离",
                               "直接在 Mac 评分", "如需交到值班机",
                               "只在 Mac 运行结束、结果返回并验收接受后进行"):
                    self.assertIn(phrase, text)
        d13 = read("docs/13-oncall-gate-materials.md")
        for phrase in ("评分前必须核对 SHA256", "绝不粘贴进被测会话", "不放进 git，不上传外部服务",
                       "T02 先在 Mac 跑两次不计分校准"):
            self.assertIn(phrase, d13)

    def test_frozen_inputs_comparison_and_entire_gate_protocol_remain_byte_identical(self):
        for rel, expected in FROZEN_FILES.items():
            with self.subTest(rel=rel):
                self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), expected)
        gate_tail = (ROOT / "docs/12-native-vs-single-comparison.md").read_bytes().split(
            "宿主加载核验（硬前置）：".encode(), 1)[1]
        self.assertEqual(hashlib.sha256(gate_tail).hexdigest(),
                         "ee192a70caae58ed4c5419496bf95c64c309ce743290551339faab9529eecf23")
        ordinary = re.findall(r"WB16 普通入口：[^\n]*直接输入“([^”]+)”", read("docs/11-workbuddy-host-acceptance.md"))
        self.assertEqual(len(ordinary), 1)
        self.assertEqual(hashlib.sha256(ordinary[0].encode()).hexdigest(),
                         "fd8b3cba2006278f0efc2378e646393b95b29676f5e6f44f36f5555ba2b0f8dd")

    def test_current_version_is_rc4_and_frozen_acceptance_version_is_explicit(self):
        self.assertEqual(read("VERSION").strip(), "2.8.0-rc4")
        self.assertEqual(json.loads(read("policy-source/acceptance/oncall-cases.json"))["version"], "2.8.0-rc3")
        for rel in ("README.md", "docs/12-native-vs-single-comparison.md", "docs/13-oncall-gate-materials.md"):
            with self.subTest(rel=rel):
                text = read(rel)
                self.assertIn("oncall-cases.json 保留 2.8.0-rc3", text)
                self.assertIn("Mac 执行流程", text)
        manifest = json.loads(read("release-manifest.json"))["files"]
        self.assertEqual(manifest, sorted(set(manifest)))
        self.assertIn("tests/test_rc4_regressions.py", manifest)


if __name__ == "__main__":
    unittest.main()
