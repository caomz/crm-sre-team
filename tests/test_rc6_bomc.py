"""Approved rc6 channel boundary and delivery regression, including mutations."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rc6_checker", ROOT / "tools/check_workbuddy.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def policy():
    return json.loads(read("policies/runtime-contract.json"))


@pytest.mark.parametrize("field,value", [
    ("executor", "telecom-crm-linux-infra"), ("modes", ["MANAGED_HARNESS"]),
    ("authorization", "SESSION_PERSISTENT"), ("authorization_inputs", ["TOOL_OUTPUT"]),
    ("read_only", False), ("max_records", 51), ("max_calls_per_round", 3),
    ("max_retries", 2), ("member_execution", True), ("credential_read_by_agent_or_guard", True),
    ("parameters", ["--config"]), ("guard", "scripts/run_query.py"),
    ("other_production_read", "ALLOWED"), ("authorization_enforcement", "HOST_ENFORCED"),
    ("local_output", "ARBITRARY_PATH_OR_OVERWRITE"),
    ("credential_source", "AGENT_OPENS_SKILL_CONFIG"),
])
def test_channel_privilege_mutations_rejected(field, value):
    changed = policy()
    changed["read_only_boundary"]["production_read_channels"][0][field] = value
    assert "bomc_channel_boundary_changed" in checker.read_only_boundary_errors(changed)


@pytest.mark.parametrize("channels", [[], [deepcopy(checker.BOMC_CHANNEL)] * 2])
def test_exactly_one_channel_required(channels):
    changed = policy()
    changed["read_only_boundary"]["production_read_channels"] = channels
    assert "bomc_channel_boundary_changed" in checker.read_only_boundary_errors(changed)


def test_writes_and_managed_executor_still_closed():
    current = policy()
    assert current["production_executor"] is False and current["production_tools"] == []
    assert current["implementation_status"] == "NOT_IMPLEMENTED"
    assert current["managed_mode"]["implementation_status"] == "NOT_IMPLEMENTED"
    assert current["read_only_boundary"]["production_write"] == "SEPARATE_CHANGE_APPROVAL_REQUIRED"
    assert current["read_only_boundary"]["production_read_channels"] == [checker.BOMC_CHANNEL]
    assert checker.policy_errors(current) == []


@pytest.mark.parametrize("sid,bindings", [
    ("stability-director", ["stability-director"]),
    ("stability-director", ["bomc-alarm-readonly", "stability-director"]),
    ("stability-director", ["stability-director", "bomc-alarm-readonly", "oracle-dba"]),
    ("linux-infra", ["linux-infra", "bomc-alarm-readonly"]),
])
def test_wrong_lead_or_member_binding_rejected(sid, bindings):
    assert checker.skill_binding_errors({"skills": bindings}, sid)


def test_lead_exact_two_skills_and_members_exact_one():
    roles = json.loads(read("policy-source/roles-source.json"))
    assert len(roles) == 8
    for sid, role in roles.items():
        for prefix in ("agents/", "policy-source/prompts/roles/"):
            text = read(prefix + role["agent"] + ".md")
            fm = yaml.safe_load(text.split("---", 2)[1])
            assert checker.skill_binding_errors(fm, sid) == []
            if sid != "stability-director":
                assert "bomc-alarm-readonly" not in fm["skills"]


@pytest.mark.parametrize("marker", checker.BOMC_LEAD_MARKERS)
def test_removing_lead_safety_clause_is_rejected(marker):
    text = read("agents/telecom-crm-sre-team-lead.md").replace(marker, "")
    assert "missing_bomc_lead_rule:" + marker in checker.check_prompt(text, True, runtime=True)


@pytest.mark.parametrize("rel", [
    "policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
    "policy-source/skills/stability-director.md",
    "policy-source/skills/bomc-alarm-readonly.md",
    "agents/telecom-crm-sre-team-lead.md",
    "skills/stability-director/SKILL.md",
    "skills/bomc-alarm-readonly/SKILL.md",
])
@pytest.mark.parametrize("marker,clauses", [
    (checker.BOMC_QUERY_CARD_RULE, (
        "仅在无禁止查询的用户限制、事件进行中、告警快照有助于区分候选且用户本轮未授权时",
        "必须先出查询卡",
        "参数、目的、区分哪些候选、当前快照覆盖时段、数据将进入云端模型的云端处理说明",
        "不得以合成/测试场景或推测告警里没有该主机等理由省略",
        "是否查询由用户决定",
    )),
    (checker.BOMC_QUERY_CARD_SCOPE_RULE, (
        "用户本轮已授权时不要求重复出卡",
        "存在禁止查询的限制或事件已过去时也不要求出卡",
    )),
    (checker.BOMC_COMMAND_QUOTING_RULE, (
        "--alarm-time、--ip、--grade 的值一律放在单引号里",
        "用户原文没加引号也要按模板加",
        "--top 只写数字",
        "Windows PowerShell 与 macOS 一致",
    )),
])
def test_bomc_query_card_and_command_rule_mutations_rejected(rel, marker, clauses):
    text = read(rel)
    assert marker in text and marker in checker.BOMC_LEAD_MARKERS
    mutations = [text.replace(marker, "")]
    for clause in clauses:
        assert clause in marker
        mutations.append(text.replace(clause, "规则已删除"))
    for changed in mutations:
        assert "missing_bomc_lead_rule:" + marker in checker.check_prompt(
            changed, True, runtime=not rel.startswith("policy-source/"))


def test_removing_member_prohibition_is_rejected():
    text = read("agents/telecom-crm-linux-infra.md").replace(checker.BOMC_MEMBER_RULE, "")
    assert "missing_bomc_member_prohibition" in checker.check_prompt(text, False, runtime=True)


def test_plugin_auxiliary_is_unique_and_real_skill_not_shipped():
    plugin = json.loads(read(".codebuddy-plugin/plugin.json"))
    assert len(plugin["skills"]) == 9
    assert plugin["skills"].count("./skills/bomc-alarm-readonly") == 1
    manifest = json.loads(read("release-manifest.json"))["files"]
    assert manifest == sorted(set(manifest))
    assert not any("skills/bomc-alarm-query" in rel for rel in manifest)
    assert not any(rel.endswith("bomc.json") for rel in manifest)
    for rel in ("policy-source/skills/bomc-alarm-readonly.md",
                "policy-source/skills/bomc-alarm-readonly/scripts/bomc_readonly.py",
                "tests/test_bomc_readonly.py", "tests/test_rc6_bomc.py", "docs/15-bomc-readonly.md",
                "tests/fixtures/bomc-synthetic/SKILL.md", "tests/fixtures/bomc-synthetic/scripts/run_query.py"):
        assert rel in manifest
    assert checker.bomc_bundle_errors(ROOT) == []


def test_auxiliary_source_and_guard_are_actually_built_and_locked():
    folder = ROOT / "skills/bomc-alarm-readonly"
    assert (folder / "scripts/bomc_readonly.py").read_bytes() == (
        ROOT / "policy-source/skills/bomc-alarm-readonly/scripts/bomc_readonly.py").read_bytes()
    lock = json.loads((folder / "BUNDLE-LOCK.json").read_text(encoding="utf-8"))
    assert lock["version"] == read("VERSION").strip()
    assert lock["agent_id"] == "telecom-crm-sre-team-lead"
    assert set(lock["files"]) == {"SKILL.md", "scripts/bomc_readonly.py"}


def test_docs_record_authorized_early_observation_and_non_destructive_rollback():
    text = read("docs/14-fde-delivery.md").split("## 9.", 1)[1].split("## 10.", 1)[0]
    for phrase in ("2026-10-19", "未达候选门槛", "观察期", "凭据泄漏", "越权", "注入被执行", "成员执行查询", "bomc.json", "改名", "rc5"):
        assert phrase in text
    guide = read("docs/15-bomc-readonly.md")
    for case in range(1, 10):
        assert f"BRC-{case}" in guide
    assert "BRC-8b" in guide
    assert "本次不执行" in guide and "没有连接 BOMC" in guide
    runbook = read("tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md").split("## rc6 BOMC", 1)[1]
    for phrase in ("CreateNew", "SKILL.md", "Get-FileHash", "不覆盖", "不手工写 cache", "VERIFY", "glm-5.3-flash", ".workbuddy/memory"):
        assert phrase in runbook


def test_bomc_config_failure_host_cases_have_distinct_entry_points():
    guide = read("docs/15-bomc-readonly.md")
    missing = next(line for line in guide.splitlines() if line.startswith("| BRC-8 "))
    invalid = next(line for line in guide.splitlines() if line.startswith("| BRC-8b "))
    for phrase in ("会话外", "精确 bomc.json", "读取配置失败即停止", "未取得证据", "守卫 0 次",
                   "不搜索替代配置", "不使用同目录其他文件", "不直调真实技能", "不改用其他取数", "恢复原名"):
        assert phrase in missing
    for phrase in ("会话外", "独立的合成 bomc.json", "其余字段有效", "不存在的合成绝对路径",
                   "守卫退出 3", "未取得可用证据", "本轮总调用 ≤2", "失败最多重试 1 次",
                   "不读取或探查 skill_config 路径", "不改参数绕过", "恢复原配置"):
        assert phrase in invalid


def test_runbook_preconfiguration_shape_gate_is_read_only_and_does_not_echo_errors():
    text = read("tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md").split("## rc6 BOMC", 1)[1]
    preflight, configuration = text.split("### 真实输出形状核对", 1)[1].split("### 新建插件外配置", 1)
    code = preflight.split("```powershell\n", 1)[1].split("```", 1)[0]
    assert "SHAPE_ACCEPTED" in preflight and "不启用通道" in preflight
    assert "预先独占创建的空文件" in preflight and "返回6" in preflight and "返回7" in preflight
    assert "最多32字符" in preflight and "形如 IP" in preflight
    assert not re.search(r"\b(?:Set-Content|Add-Content|Out-File|New-Item|Remove-Item|Move-Item|Invoke-Expression)\b", code)
    assert "WriteAll" not in code and "Get-Content" not in code
    catch = code.split("} catch {", 1)[1].split("} finally", 1)[0]
    assert "$_" not in catch and "Write-Host 'STOP:" in catch
    assert "Optional absolute real skill config file" in configuration
    assert "if ($BomcSkillConfig) { $Document['skill_config'] = $BomcSkillConfig }" in configuration
