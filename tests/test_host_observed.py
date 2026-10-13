"""Lock host-observed-v3.4 rules: roster in lead SKILL, dispatch marker,
parameter realism, COMPAT scoping. Static text checks only; no model or host calls."""
from __future__ import annotations
import json
from pathlib import Path
import re
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

MEMBER_SIDS = [
    "crm-business-flow", "java-runtime", "linux-infra", "oracle-dba",
    "observability-diagnosis", "change-capacity-dr", "k8s-platform",
]

WB16_GATE_KEY_PHRASES = (
    "p95", "JDBC", "active/max", "waiting", "elapsed", "成功率", "慢",
    "连接池", "SQL", "HTTP", "技术恢复", "业务恢复",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> str:
    """Return the frontmatter description field value."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    fm = yaml.safe_load(parts[1])
    return fm.get("description", "")


def _extract_mode_block(text: str, label: str) -> str:
    begin = f"<!-- MODE:{label}:BEGIN -->"
    end = f"<!-- MODE:{label}:END -->"
    i = text.find(begin)
    j = text.find(end)
    if i == -1 or j == -1:
        return ""
    return text[i + len(begin):j]


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
        self.assertIn('任务文本第一行以“【团长派单】”开头时', text)
        native = next(line for line in text.splitlines() if line.startswith('2. WORKBUDDY_NATIVE'))
        self.assertIn('保持成员身份，省略兼容路径的首次模式声明', native)
        self.assertNotIn('单模型分析，未进行多专家委派', native)
        self.assertIn('首次进入或模式变化时说明“单模型分析，未进行多专家委派”', text)

    def test_06_member_compat_blocks_scoped(self):
        for sid in MEMBER_SIDS:
            for rel in [
                f"policy-source/skills/{sid}.md",
                f"policy-source/prompts/roles/telecom-crm-{sid}.md",
            ]:
                with self.subTest(rel=rel):
                    text = _read(ROOT / rel)
                    self.assertIn("只有用户直接打开本角色对话时才按本段回答", text)
                    self.assertIn('任务文本第一行以“【团长派单】”开头时改按原生成员段工作', text)

    def test_07_lead_native_lead_contains_marker_template(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                template = '每次派单的第一行固定写“【团长派单】派单标记：<随机标记>”'
                self.assertIn(template, text)
                self.assertIn(template, _extract_mode_block(text, "NATIVE_LEAD"))

    def test_08_member_native_member_contains_marker_recognition(self):
        for sid in MEMBER_SIDS:
            for rel in [
                f"policy-source/skills/{sid}.md",
                f"policy-source/prompts/roles/telecom-crm-{sid}.md",
            ]:
                with self.subTest(rel=rel):
                    text = _read(ROOT / rel)
                    self.assertIn('任务文本第一行以“【团长派单】”开头时，按本段工作并把报告返回团长', text)


class DispatchParameterTests(unittest.TestCase):
    """3. 派单参数写实（NATIVE_LEAD 块）"""

    def test_09_native_lead_contains_subagent_type_rule(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
            "skills/stability-director/SKILL.md",
            "agents/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("subagent_type 填成员注册 ID", text)
                self.assertIn("日常不传 name", text)
                self.assertIn("WorkBuddy 5.7.7 带 name 会走队员通道：自动建队、经邮箱回报，TaskOutput 不等待队员", text)
                self.assertNotIn("只作标签", text)
                self.assertNotIn("name 标签", text)

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
                self.assertIn("日常派单不传 max_turns，用宿主默认轮数；只有用户明确要求限制轮数时才传 max_turns", text)

    def test_12_native_lead_retains_host_tool_fallback(self):
        for rel in [
            "policy-source/skills/stability-director.md",
            "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
        ]:
            with self.subTest(rel=rel):
                text = _read(ROOT / rel)
                self.assertIn("以当前宿主实际工具定义为准", text)

    def test_13_roster_note_mentions_subagent_type(self):
        routing = json.loads(_read(ROOT / "policy-source/routing-source.json"))
        text = routing["_dispatch_note"]
        self.assertIn("派单时 subagent_type 填注册 ID", text)
        self.assertIn("日常不传 name", text)
        self.assertNotIn("name 标签", text)
        for rel in ["agents/telecom-crm-sre-team-lead.md", "skills/stability-director/SKILL.md"]:
            with self.subTest(rel=rel):
                self.assertIn(text, _read(ROOT / rel))


class ModeBlockConsistencyTests(unittest.TestCase):
    """4. NATIVE_LEAD 块两源一致 + 成员 NATIVE_MEMBER/COMPAT_MEMBER 两源一致"""

    def test_14_lead_native_lead_blocks_identical(self):
        skill_src = _read(ROOT / "policy-source/skills/stability-director.md")
        role_src = _read(ROOT / "policy-source/prompts/roles/telecom-crm-sre-team-lead.md")
        self.assertEqual(
            _extract_mode_block(skill_src, "NATIVE_LEAD"),
            _extract_mode_block(role_src, "NATIVE_LEAD"),
        )
        for rel in ["agents/telecom-crm-sre-team-lead.md", "skills/stability-director/SKILL.md"]:
            with self.subTest(rel=rel):
                self.assertEqual(_extract_mode_block(skill_src, "NATIVE_LEAD"),
                                 _extract_mode_block(_read(ROOT / rel), "NATIVE_LEAD"))

    def test_15_member_native_member_blocks_identical(self):
        for sid in MEMBER_SIDS:
            with self.subTest(sid=sid):
                skill_src = _read(ROOT / f"policy-source/skills/{sid}.md")
                role_src = _read(ROOT / f"policy-source/prompts/roles/telecom-crm-{sid}.md")
                self.assertEqual(
                    _extract_mode_block(skill_src, "NATIVE_MEMBER"),
                    _extract_mode_block(role_src, "NATIVE_MEMBER"),
                )

    def test_16_member_compat_member_blocks_identical(self):
        for sid in MEMBER_SIDS:
            with self.subTest(sid=sid):
                skill_src = _read(ROOT / f"policy-source/skills/{sid}.md")
                role_src = _read(ROOT / f"policy-source/prompts/roles/telecom-crm-{sid}.md")
                self.assertEqual(
                    _extract_mode_block(skill_src, "COMPAT_MEMBER"),
                    _extract_mode_block(role_src, "COMPAT_MEMBER"),
                )


class Rc3HostAcceptanceDocumentationTests(unittest.TestCase):
    def test_577_host_limits_and_channels_are_documented_as_handoff_facts(self):
        text = _read(ROOT / "docs/11-workbuddy-host-acceptance.md")
        for phrase in ("交接事实，不是 rc3 PASS", "resolveSubagentMaxTurns", "Math.max(请求值, 200)",
                       "CODEBUDDY_CODE_SUBAGENT_MAX_TURNS 同样被钳到 ≥200",
                       "Mac 实测不带 name、max_turns=1 时成员 2 轮正常完成", "值班机块 27 已证实该下限",
                       "spawnTeammate", "<name>@_auto_<会话ID>", "TaskList/SendMessage", "TaskOutput 不等待队员",
                       "Not in a team", "日常不传 name，走同步子代理，结果直接作为 Agent 工具返回",
                       "主会话 jsonl 的 agent=cli，团长职责来自 stability-director Skill",
                       "切换日志只证明宿主发出了切换请求"):
            self.assertIn(phrase, text)
        self.assertNotIn("切换日志证明会话绑定", text)
        self.assertNotIn("name 标签", text)

    def test_desktop_binding_and_host_managed_settings_are_distinct(self):
        readme = _read(ROOT / "README.md")
        migration = _read(ROOT / "MIGRATION.md")
        for text in (readme, migration):
            self.assertIn("teamInfo.leadAgent", text)
            self.assertIn("settings.json", text)
            self.assertIn("宿主管理", text)
            self.assertIn("516/517", text)
            self.assertNotIn("根目录入口为 `settings.json`", text)
        self.assertIn("构建和静态校验", readme)
        self.assertIn("不是桌面绑定入口或加载证据", readme)

    def test_loading_evidence_and_rc2_observations_do_not_claim_rc3_pass(self):
        text = _read(ROOT / "docs/11-workbuddy-host-acceptance.md")
        for phrase in ("2.8.0-rc4 场景验收 NOT_RUN", "宿主层为准", "Skill 调用回执的路径和版本",
                       "subagent_type", "SessionPluginSwitcher", "没输出不等于没加载",
                       "正式包没有 PROBE 定义", "模型自拟的 PROBE 行不算证据",
                       "229ad198 / 329b9d20", "未独立读取原始日志", "不是 rc3 已验证"):
            self.assertIn(phrase, text)
        self.assertNotIn("成员加载了什么，只认 PROBE", text)
        self.assertNotIn("PROBE-LS → 团长 SKILL.md 已加载", text)
        for sid in ["stability-director"] + MEMBER_SIDS:
            self.assertNotIn("> PROBE-", _read(ROOT / "skills" / sid / "SKILL.md"))

    def test_new_host_cases_not_run_with_echo_only_safety(self):
        text = _read(ROOT / "docs/11-workbuddy-host-acceptance.md")
        section = text.split("## rc4 验收", 1)[1].split("K8s 三写法判定表", 1)[0]
        for phrase in ("WB16 / WB17 均 NOT_RUN", "不提醒加载技能", "错误加载声明",
                       "echo 随机暗号", "不联网、不读写文件、不读环境变量", "--disallow oracle-dba=Bash",
                       "只由模型拒绝、没有尝试或没有回执记 BLOCKED", "不叠加 maxTurns"):
            self.assertIn(phrase, text if phrase == "不提醒加载技能" else section)
        data = json.loads(_read(ROOT / "tests/workbuddy-host-cases.json"))
        for cid in ("WB16", "WB17"):
            cases = [case for case in data["cases"] if case["id"] == cid]
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0]["status"], "NOT_RUN_IN_TARGET_HOST")
            self.assertIsNone(cases[0]["observed_output"])

    def _wb16_input(self):
        text = _read(ROOT / "docs/11-workbuddy-host-acceptance.md")
        inputs = re.findall(r"WB16 普通入口：[^\n]*直接输入“([^”]+)”", text)
        self.assertEqual(len(inputs), 1, "WB16 must document exactly one ordinary input")
        return inputs[0]

    def _assert_wb16_input_isolated(self, ordinary):
        self.assertRegex(ordinary, r"CRM\s+(?:服务开通|订单开通|批处理|组件|容器|受理|数据库|连接池)",
                         "WB16 must describe a specific CRM business or component")
        numbers = set(re.findall(r"\d+(?:\.\d+)?", ordinary))
        metrics = set(re.findall(
            r"\b[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z][A-Za-z0-9_]*)*(?=\s*=)|\bp\d+(?:\.\d+)?\b",
            ordinary,
        ))
        objects = set(re.findall(r"\b[a-z]+(?:-[a-z]+)*\.invalid\b", ordinary))
        self.assertTrue(numbers, "WB16 needs concrete synthetic observations")
        self.assertTrue(metrics, "WB16 needs metric markers to verify isolation")
        cases = json.loads(_read(ROOT / "policy-source/acceptance/oncall-cases.json"))["cases"]
        overlaps = {
            case["id"]: sorted(feature for feature in numbers | metrics | objects
                               if feature.casefold() in case["input"].casefold())
            for case in cases
        }
        self.assertEqual({cid: hits for cid, hits in overlaps.items() if hits}, {})
        self.assertTrue(objects, "WB16 needs a distinct synthetic object")
        for phrase in WB16_GATE_KEY_PHRASES:
            self.assertNotIn(phrase.casefold(), ordinary.casefold(),
                             "WB16 reuses a gate key phrase: " + phrase)
        self.assertNotRegex(ordinary, r"(?i)skill|stability-director")
        for phrase in ("离线合成故障", "不联网", "不读写文件", "不读取环境变量", "不执行终端命令"):
            self.assertIn(phrase, ordinary)

    def test_wb16_numeric_and_metric_features_are_absent_from_every_gate_input(self):
        ordinary = self._wb16_input()
        self._assert_wb16_input_isolated(ordinary)
        self.assertIn("CRM 服务开通队列", ordinary)
        text = _read(ROOT / "docs/11-workbuddy-host-acceptance.md")
        self.assertIn("关口前运行的宿主用例不得复用关口材料或其数值特征", text)
        self.assertIn("与 C1/C2/C3/T02 的故障场景/子领域、对象、数值和指标类标记保持隔离", text)
        self.assertIn("WB16 仍须是 CRM 运维故障，否则测不到普通入口", text)
        self.assertIn("WB16/WB17 会话与关口会话分开", text)
        case = next(case for case in json.loads(_read(ROOT / "tests/workbuddy-host-cases.json"))["cases"]
                    if case["id"] == "WB16")
        self.assertIn("CRM 服务开通队列 provisioning-queue.invalid", case["scenario"])
        self.assertIn("故障场景/子领域", case["scenario"])

    def test_wb16_rejects_previous_overlapping_and_out_of_domain_inputs(self):
        old = (
            "本次为离线合成故障：CRM 受理 p95 从 180ms 升到 1800ms；"
            "同窗 JDBC active/max=40/40、waiting=35，数据库等待与业务终态未知。"
            "请给当前判断与最小区分性验证。不联网、不读写文件、不读取环境变量，不执行终端命令。"
        )
        weather = (
            "本次为离线合成故障：园区气象接收站 wx-receiver.invalid 出现数据帧解码失败；"
            "同窗 crc_faults=7316、missing_frames=8462、decoded_frames=5729，"
            "接收链路噪声与固件变更记录未知。请给当前判断与最小区分性验证。"
            "不联网、不读写文件、不读取环境变量，不执行终端命令。"
        )
        for label, ordinary in (("old-C1-overlap", old), ("out-of-domain", weather),
                                ("out-of-domain-with-CRM-label", "CRM " + weather)):
            with self.subTest(label=label):
                with self.assertRaises(AssertionError):
                    self._assert_wb16_input_isolated(ordinary)

    def test_wb16_rejects_gate_features_and_key_phrases(self):
        ordinary = self._wb16_input()
        self._assert_wb16_input_isolated(ordinary)
        for phrase in WB16_GATE_KEY_PHRASES:
            with self.subTest(key_phrase=phrase):
                with self.assertRaises(AssertionError):
                    self._assert_wb16_input_isolated(ordinary + "附注：" + phrase)
        for original, replacement in (
            ("6197", "180"), ("6197", "2400"), ("6197", "99.9"),
            ("queued_activations", "rows"), ("queued_activations", "source"),
            ("provisioning-queue.invalid", "app-a.invalid"),
            ("provisioning-queue.invalid", "db-b.invalid"),
            ("provisioning-queue.invalid", "app-c.invalid"),
        ):
            with self.subTest(feature=replacement):
                self.assertIn(original, ordinary)
                with self.assertRaises(AssertionError):
                    self._assert_wb16_input_isolated(ordinary.replace(original, replacement))

    def test_scoring_and_final_zip_records_have_persistent_delivery_paths(self):
        materials = _read(ROOT / "docs/13-oncall-gate-materials.md")
        validation = _read(ROOT / "VALIDATION.md").split("## v3.6.4", 1)[0]
        delivery = "/Volumes/WorkSSD/Downloads/crm-sre-team-v3.7/"
        self.assertEqual(re.findall(r"Mac 路径 `([^`]+)`", materials),
                         [delivery + "仅评分人/gate-gold/"])
        self.assertIn(delivery + "SHA256SUMS", validation)
        self.assertIn("517 个 manifest 文件，字节/权限 0 差异", validation)
        self.assertIn("build_release 两次均为 517 项、SHA256 一致", validation)
        self.assertIn("validate_release 两份均 517/517", validation)
        self.assertIn("私有特征与 gold 文件条目均 0 命中", validation)
        self.assertIn("最终外层包自身哈希不写入载荷", validation)
        self.assertIn("持久路径声明不代表复制已完成", validation)

    def test_rc4_migration_accepts_mac_results_before_windows_11_verify(self):
        current = _read(ROOT / "MIGRATION.md").split("## 历史迁移记录", 1)[0]
        self.assertIn("预发布后缀、加载和提示词测试先在 Mac 验收", current)
        self.assertIn("Mac 跑完、返回结果经人工复核并验收后", current)
        self.assertIn("只做安装/切换 + VERIFY", current)
        self.assertIn("仅在需确认宿主行为时加一个短会话", current)
        self.assertIn("家庭版 23H2，10.0.22631", current)
        self.assertNotIn("Windows 10 宿主", current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
