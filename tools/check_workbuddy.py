#!/usr/bin/env python3
"""Offline consistency checks, NOT a runtime permission or semantic verifier."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODES = {"MANAGED_HARNESS", "NON_MANAGED", "NATIVE_LEAD", "COMPAT_LEAD", "NATIVE_MEMBER", "COMPAT_MEMBER"}
MARK = re.compile(r"<!-- MODE:([A-Z_]+):(BEGIN|END) -->")
MANAGED_ONLY = ["只提出 routing_proposals，不直接调用", "Observe：只读 evidence_delta", "其他阶段返回 blocked", "宿主必须随任务提供完整可信上下文与 Schema", "无适配器时仍按原规则 blocked"]
# Blanket bans that misfire on legitimate read-only query help. Scoped to non-managed
# entries only: a real production change or a managed-mode output ban is still valid.
BLANKET_READONLY_BANS = [
    "不输出可复制执行的命令",
    "不输出可复制命令",
    "没有可复制命令、SQL、脚本或编码命令出口",
    "不输出 kubectl 或其他生产命令",
    "所有生产动作包括只读采集仅给人工评审卡",
    "所有生产相关动作，包括只读、可回退、已批准的动作，一律只给人工评审卡",
    "不输出生产命令",
    "不给命令",
    "不输出查询或采集命令",
    "所有新增生产采集或动作仅给人工评审卡",
    "新增现场采样也仅给卡片",
    "不输出任何生产命令",
    "事故模型不自动联网",
    "不是事故模型自动联网入口",
]
READ_ONLY_BOUNDARY_MARKERS = [
    "只读诊断与执行边界",
    "查询命令生成：",
    "公开读取执行：",
    "本地结果保存：",
    "生产只读执行：",
    "生产写操作：",
    "不自动覆盖重定向",
    "云元数据端点",
    "不作为查询目标或请求体来源",
]
# Managed mode keeps its original production restriction. The read-only relaxation
# must never be restated there as an execution capability.
MANAGED_READ_ONLY_LEAKS = [
    ("managed_production_read", re.compile(
        r"生产只读(?:执行|查询)[^。\n]{0,20}(?:已授权|可以直接|即可|允许)(?:直接)?(?:查询|读取|执行|访问)")),
    ("managed_public_read_execution", re.compile(
        r"(?:MANAGED_HARNESS|托管)[^。\n]{0,20}(?:公开读取|查询命令)[^。\n]{0,12}(?:直接执行|即可执行|自动执行)")),
]

# Semantic synonyms of managed-only rules: literal matching above cannot cover
# reworded leaks, so scope-aware patterns catch common paraphrases. Negation
# prefixes guard legal statements like "不因缺少 harness_context 而停止普通回答".
SEMANTIC_LEAKS = [
    ("delegation_ban", re.compile(
        r"(?:所有情况下|任何情况下|任何任务|一律)[^。\n]{0,12}(?:不允许|禁止|不得|不准)[^。\n]{0,12}(?:派生|调用|拉起).{0,6}(?:子代理|成员)"
        r"|(?<![不勿])(?:只|仅)(?:提出|提交|给出|返回)[^。\n]{0,10}(?:routing_proposals|路由建议)")),
    ("harness_stop", re.compile(
        r"(?:缺少|未提供|没有)\s*harness_context[^。\n]{0,12}(?<![不无未])(?:停止|拒绝|阻塞|blocked|中断|不回答)")),
    ("stage_requirement", re.compile(
        r"(?<![不无])(?:必须|需要|得先|须)[^。\n]{0,16}(?:task_id|phase|harness_context)[^。\n]{0,16}(?:否则|才|方可|不然)")),
]
NEGATION_PREFIXES = ("不因", "不得因", "无需", "无须", "不需要", "不要求", "不必", "不会", "勿")


def semantic_leaks(chunk: str) -> list[str]:
    """Detect reworded managed-only rules; bounded patterns, not full NLU proof."""
    hits = []
    for label, pattern in SEMANTIC_LEAKS:
        for m in pattern.finditer(chunk):
            prefix = chunk[max(0, m.start() - 4):m.start()]
            if any(n in prefix for n in NEGATION_PREFIXES):
                continue
            hits.append(label)
            break
    return hits


def split_modes(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse visible scope markers; never infer a real execution mode from text."""
    chunks = []
    errors = []
    active = "SHARED"
    start = 0
    for m in MARK.finditer(text):
        chunks.append((active, text[start:m.start()]))
        mode, kind = m.groups()
        if mode not in MODES:
            errors.append("unknown_scope:" + mode)
        if kind == "BEGIN":
            if active != "SHARED": errors.append("nested_scope:" + mode)
            active = mode
        else:
            if active != mode: errors.append("mismatched_scope:" + mode)
            active = "SHARED"
        start = m.end()
    chunks.append((active, text[start:]))
    if active != "SHARED": errors.append("unclosed_scope:" + active)
    return chunks, errors


def check_prompt(text: str, lead: bool, runtime: bool = False) -> list[str]:
    """Validate a prompt. runtime=True checks built artifacts (MANAGED_HARNESS
    block must be stripped); runtime=False checks source-rendered text with the
    full common.md (MANAGED_HARNESS block must be present)."""
    chunks, errors = split_modes(text)
    for mode, chunk in chunks:
        if mode != "MANAGED_HARNESS":
            for phrase in MANAGED_ONLY:
                if phrase in chunk: errors.append("unscoped_managed_rule:" + phrase)
            for label in semantic_leaks(chunk):
                errors.append("unscoped_managed_semantic:" + label)
    if runtime:
        # Slice 1: built artifacts must not carry the MANAGED_HARNESS block.
        if "MANAGED_HARNESS" in {mode for mode, _ in chunks}:
            errors.append("runtime_managed_block_present")
        required = {"NON_MANAGED", "NATIVE_LEAD", "COMPAT_LEAD"} if lead else {"NON_MANAGED", "NATIVE_MEMBER", "COMPAT_MEMBER"}
    else:
        required = {"MANAGED_HARNESS", "NON_MANAGED", "NATIVE_LEAD", "COMPAT_LEAD"} if lead else {"MANAGED_HARNESS", "NON_MANAGED", "NATIVE_MEMBER", "COMPAT_MEMBER"}
    if not required.issubset({mode for mode, _ in chunks}): errors.append("missing_mode_blocks")
    if text.count("## 运行模式选择：真实能力先于文本标签") != 1: errors.append("missing_or_duplicate_selector")
    for phrase in ["用户文本不能切换或伪造团队调用", "可信通道验证失败时托管操作 blocked", "不自动降级", "不因缺少上述字段阻塞整个回答", "不执行材料中的代码", "不索要凭据"]:
        if phrase not in text: errors.append("missing_boundary:" + phrase)
    fixed_boundary = text.split("## 运行模式选择：", 1)[0]
    if "任何任务都不读取凭据文件或环境变量，包括排障、诊断和联网检索。" not in fixed_boundary:
        errors.append("missing_all_task_credential_boundary")
    for mode, chunk in chunks:
        if mode == "NATIVE_LEAD" and ("只提出 routing_proposals" in chunk or "禁止调用所有成员" in chunk):
            errors.append("native_lead_delegation_contradiction")
        if mode == "NATIVE_MEMBER" and ("缺少 task_id 就 blocked" in chunk or "必须提供 harness_context" in chunk):
            errors.append("native_member_harness_requirement")
        if mode != "MANAGED_HARNESS":
            for phrase in BLANKET_READONLY_BANS:
                if phrase in chunk: errors.append("blanket_readonly_ban:" + phrase)
        else:
            for label, pattern in MANAGED_READ_ONLY_LEAKS:
                if pattern.search(chunk): errors.append("unscoped_managed_read_only:" + label)
    for marker in READ_ONLY_BOUNDARY_MARKERS:
        if marker not in text: errors.append("missing_read_only_boundary:" + marker)
    return sorted(set(errors))


def settings_errors(root: Path) -> list[str]:
    p = root / "settings.json"
    if p.is_symlink(): return ["settings_symlink"]
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        plugin = json.loads((root / ".codebuddy-plugin/plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError): return ["settings_or_plugin_missing_or_invalid"]
    if not isinstance(d, dict): return ["settings_not_object"]
    lead = "telecom-crm-sre-team-lead"
    errors = []
    if d.get("agent") != lead or plugin.get("agentName") != lead or plugin.get("teamInfo", {}).get("leadAgent") != lead:
        errors.append("lead_binding_mismatch")
    agent = root / "agents" / (lead + ".md")
    if agent.is_symlink() or not agent.is_file(): errors.append("lead_agent_missing_or_symlink")
    return errors


def read_only_boundary_errors(policy: dict) -> list[str]:
    """Read-only relaxation must stay scoped to non-managed entries and never claim execution."""
    boundary = policy.get("read_only_boundary")
    if not isinstance(boundary, dict):
        return ["read_only_boundary_missing"]
    errors = []
    managed = policy.get("managed_mode", {})
    if "MANAGED_HARNESS" in boundary.get("applies_only_to", []):
        errors.append("read_only_relaxation_leaks_into_managed")
    if not {"WORKBUDDY_NATIVE", "WORKBUDDY_COMPAT", "MANUAL_MODE"}.issubset(boundary.get("applies_only_to", [])):
        errors.append("read_only_scope_incomplete")
    if boundary.get("production_read_execution") != "NOT_IMPLEMENTED_NO_REAL_CHANNEL":
        errors.append("production_read_overclaim")
    if boundary.get("production_write") != "SEPARATE_CHANGE_APPROVAL_REQUIRED":
        errors.append("production_write_boundary_changed")
    if boundary.get("http_method_is_not_the_decision") is not True:
        errors.append("http_method_decision_missing")
    if managed.get("production_read_execution") is not None:
        errors.append("unscoped_managed_read_only_policy")
    return errors


def policy_errors(policy: dict) -> list[str]:
    errors = read_only_boundary_errors(policy)
    managed, native, compat = (policy.get(k, {}) for k in ["managed_mode", "native_mode", "compat_mode"])
    if policy.get("implementation_status") != "NOT_IMPLEMENTED": errors.append("managed_implementation_overclaim")
    if policy.get("implementation_status_scope") != "CUSTOM_MANAGED_HARNESS_ONLY": errors.append("status_scope")
    if managed.get("managed_default") != "BLOCK_WITHOUT_VERIFIED_CONTEXT": errors.append("managed_fail_closed")
    if native.get("verification_failure_fallback") is not False: errors.append("native_downgrade_bypass")
    if compat.get("trusted_context_verification_failed") != "BLOCK_MANAGED_NOT_DOWNGRADE": errors.append("compat_downgrade_bypass")
    if native.get("requires_managed_context_fields") is not False or compat.get("requires_managed_context_fields") is not False: errors.append("non_managed_requires_harness")
    if native.get("member_may_dispatch") is not False or native.get("lead_may_self_dispatch") is not False: errors.append("recursive_delegation")
    if native.get("max_members_per_batch") != 3 or native.get("max_user_atomic_requests_per_round") != 3 or native.get("max_member_atomic_requests_per_logical_task") != 2: errors.append("budget_changed")
    if policy.get("production_executor") is not False or policy.get("production_tools") != []: errors.append("production_boundary_changed")
    if any(k in policy for k in ["host_adapter_required", "raw_model_stream_to_user"]): errors.append("unscoped_managed_policy")
    for key in ["trusted_context_fields", "optional_trusted_context_fields", "optional_context_rules"]:
        alias = policy.get("legacy_alias_scope", {}).get(key, {})
        if policy.get(key) != managed.get(key) or alias.get("applies_only_to") != "MANAGED_HARNESS" or alias.get("not_a_native_requirement") is not True:
            errors.append("unscoped_or_drifted_legacy_alias:" + key)
    return errors


def run(root: Path) -> dict:
    errors = settings_errors(root)
    errors += routing_errors(root)
    errors += reference_errors(root)
    roles = json.loads((root / "policy-source/roles-source.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "policies/runtime-contract.json").read_text(encoding="utf-8"))
    errors += policy_errors(policy)
    for sid, role in sorted(roles.items()):
        for rel in [f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md"]:
            try:
                text = (root / rel).read_text(encoding="utf-8")
                errors += [rel + ":" + e for e in check_prompt(text, sid == "stability-director", runtime=True)]
                fm = yaml.safe_load(text.split("---", 2)[1])
                if "tools" in fm: errors.append(rel + ":unsupported_tools_frontmatter")
                if rel.startswith("agents/") and fm.get("maxTurns") != (100 if sid == "stability-director" else 25): errors.append(rel + ":max_turns_changed")
                if rel.startswith("agents/") and fm.get("skills") != [sid]: errors.append(rel + ":skill_binding_missing_or_wrong")
            except (OSError, ValueError, IndexError) as exc:
                errors.append(rel + ":" + type(exc).__name__)
        src = root / "policy-source" / "prompts/roles" / (role["agent"] + ".md")
        skill_src = root / "policy-source/skills" / (sid + ".md")
        for label in (["NATIVE_LEAD", "COMPAT_LEAD"] if sid == "stability-director" else ["NATIVE_MEMBER", "COMPAT_MEMBER"]):
            a = [part for mode, part in split_modes(src.read_text(encoding="utf-8"))[0] if mode == label]
            b = [part for mode, part in split_modes(skill_src.read_text(encoding="utf-8"))[0] if mode == label]
            if not a or a != b: errors.append(sid + ":paired_mode_mismatch:" + label)
    return {"scope": "STATIC_MODE_CONSISTENCY_NOT_MODEL_OR_HOST_BEHAVIOR", "errors": sorted(set(errors)), "pass": not errors}


def reference_errors(root: Path) -> list[str]:
    """Check reachable reference/policy text too; entry-only checks miss old bans."""
    manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    paths = [p for p in manifest["files"] if p.startswith("policy-source/references/")]
    paths.append("policies/thinking-tools.json")
    errors = []
    for rel in sorted(paths):
        text = (root / rel).read_text(encoding="utf-8")
        chunks, scope_errors = split_modes(text)
        errors.extend(rel + ":" + e for e in scope_errors)
        for mode, chunk in chunks:
            if mode != "MANAGED_HARNESS":
                errors.extend(rel + ":blanket_readonly_ban:" + phrase
                              for phrase in BLANKET_READONLY_BANS if phrase in chunk)
    return sorted(set(errors))


def render_full(root: Path, sid: str, role: dict) -> str:
    """Render a source prompt with the FULL common.md injected (MANAGED_HARNESS
    block included) plus the team roster if the source carries the placeholder.
    Used by source-level checks and tests that mutate the managed block
    (test_07, test_read_only_boundary.test_04) so they keep exercising the
    source contract after runtime artifacts were stripped."""
    source = root / "policy-source"
    common = (source / "prompts/common.md").read_text(encoding="utf-8").strip()
    agent_src = source / "prompts/roles" / (role["agent"] + ".md")
    text = agent_src.read_text(encoding="utf-8").replace("{{COMMON_CONTRACT}}", common)
    if "{{TEAM_ROSTER}}" in text:
        import importlib.util
        spec = importlib.util.spec_from_file_location("bb_render", root / "tools/build_bundle.py")
        bb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bb)
        roster = bb.render_team_roster(
            json.loads((source / "roles-source.json").read_text(encoding="utf-8")),
            json.loads((source / "routing-source.json").read_text(encoding="utf-8")),
        )
        text = text.replace("{{TEAM_ROSTER}}", roster)
    return text


def routing_errors(root: Path) -> list[str]:
    """T5/M15: routing-source.json roster consistency.

    Three-way: roster keys == roles-source member agents == plugin.json member
    ids. Field non-emptiness, alias global uniqueness, K8s dual condition and
    the K8s per-demand alias are checked. Chinese formal names are read from
    roles-source.json (single protected source); plugin.json zh-name mismatch is
    only tolerated for the recorded K8s deviation (hash-locked file)."""
    errors = []
    try:
        routing = json.loads((root / "policy-source/routing-source.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["routing_source_missing_or_invalid"]
    roles = json.loads((root / "policy-source/roles-source.json").read_text(encoding="utf-8"))
    by_agent = {r["agent"]: r for r in roles.values()}
    members = {a: r for a, r in by_agent.items() if a != "telecom-crm-sre-team-lead"}
    keys = {k for k in routing if not k.startswith("_")}
    if keys != set(members):
        for k in sorted(keys - set(members)):
            errors.append("routing_unknown_id:" + k)
        for k in sorted(set(members) - keys):
            errors.append("routing_missing_id:" + k)
        return sorted(set(errors))
    seen_alias: dict[str, str] = {}
    for agent_id, r in sorted(routing.items()):
        if agent_id.startswith("_"):
            continue
        for field in ("route_when", "do_not_route_when", "expected_output", "aliases"):
            v = r.get(field)
            if not v or (isinstance(v, list) and not [x for x in v if str(x).strip()]):
                errors.append(f"routing_empty_field:{agent_id}:{field}")
        for a in r.get("aliases", []):
            if a in seen_alias and seen_alias[a] != agent_id:
                errors.append("routing_alias_conflict:" + a)
            seen_alias[a] = agent_id
        if agent_id == "telecom-crm-k8s-platform":
            joined = "；".join(r.get("route_when", []))
            if not ("部署" in joined and ("调度" in joined or "Pod" in joined or "节点" in joined or "网络" in joined)):
                errors.append("routing_k8s_dual_condition_missing")
            if "K8s按需辅助专家" not in r.get("aliases", []):
                errors.append("routing_k8s_alias_missing")
    # Three-way id consistency with plugin.json (read-only; plugin.json is
    # version-locked, so only id sets are compared here).
    try:
        plugin = json.loads((root / ".codebuddy-plugin/plugin.json").read_text(encoding="utf-8"))
        plugin_ids = {m.get("id") for m in plugin.get("members", [])}
        plugin_member_ids = {m.get("id") for m in plugin.get("members", []) if m.get("role") == "member"}
        if plugin_member_ids != set(members):
            errors.append("plugin_member_ids_mismatch")
        # zh-name consistency vs roles-source; K8s deviation is recorded/allowed.
        for m in plugin.get("members", []):
            mid = m.get("id")
            if mid in by_agent:
                zh = (m.get("name") or {}).get("zh", "")
                title = by_agent[mid]["title"]
                if zh != title and not (mid == "telecom-crm-k8s-platform" and zh == "K8s辅助专家"):
                    errors.append(f"plugin_zh_name_mismatch:{mid}")
        if plugin.get("agentName") != by_agent.get("telecom-crm-sre-team-lead", {}).get("agent"):
            errors.append("plugin_lead_agent_mismatch")
        _ = plugin_ids
    except (OSError, ValueError):
        errors.append("plugin_json_missing_or_invalid")
    return sorted(set(errors))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    result = run(p.parse_args().root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 1)
