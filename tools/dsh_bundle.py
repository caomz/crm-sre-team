#!/usr/bin/env python3
"""Offline deterministic DSH domain bundle renderer/builder.

Generates ONLY the dsh/ configuration pack (package.json, cordis.patch.yml,
build-info.json) from a precise whitelist of policy-source inputs. The patch
holds exactly four records: the two original global overrides, the registry
default override and one bare-inserted dedicated CRM SRE preset whose scoped
persona carries the same full lead rules. No network,
no models, no JS runtime, no broad workspace collection. Build stages outputs
in isolation and atomically replaces ONLY the owned dsh/ tree with rollback on
ordinary failure; WorkBuddy trees, root VERSION and user data are never touched.

Static tooling: generating configuration and prompts is not a runtime or
permission boundary, and does not verify model or host behavior.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import yaml

DSH_DIR = "dsh"
DSH_VERSION = "2.8.0-dsh.1"
PACKAGE_NAME = "crm-sre-dsh-team"
SYSTEM_PROMPT_PLUGIN = "@deepseek-ai/dsh-system-prompt"
AGENT_TEAMS_PLUGIN = "@nanmicoder/dsh-agent-teams"
PROFILE = "crm-sre"
CAPTAIN_AGENT = "telecom-crm-sre-team-lead"
TOOL_POLICY_ID = "crm-sre-member-coordination"
MEMBER_TOOLS = [
    "agent_teams_claim_task",
    "agent_teams_update_task",
    "agent_teams_send_message",
    "agent_teams_status",
]
MEMBER_KEYS = ("name", "role", "tool_policy", "executionPrompt")
AGENT_TEAMS_CONFIG_KEYS = ("maxMembers", "memberMaxDepth", "memberProvider", "profiles", "stateDir", "toolPolicies")
PROFILE_CONFIG_KEYS = ("members", "protocol", "taskPlanning")
SYSTEM_PROMPT_CONFIG_KEYS = ("includeHarnessIdentity", "includeRuntimeContext", "personaPrefix", "personaSuffix")
# Captain preset fix (0.2.2-rc.1): the DSH standard agent preset scopes its own
# @deepseek-ai/dsh-persona row ("You are a coding agent ..."), and a scoped
# persona SHADOWS the global deployment persona-prefix — so the global
# system-prompt override alone never reached real captain sessions. The patch
# therefore keeps the two global overrides (indices 0/1), overrides the
# existing agent-preset-registry default (index 2) and bare-inserts one
# dedicated preset entry (index 3) whose scoped persona carries the same full
# lead rules. Include patches cannot reach nested preset plugin rows, so the
# scoped persona must ship inside the new entry, not as a global edit.
PERSONA_PLUGIN = "@deepseek-ai/dsh-persona"
TIME_CONTEXT_PLUGIN = "@deepseek-ai/dsh-time-context"
TOOL_FS_PLUGIN = "@deepseek-ai/dsh-tool-fs"
AGENT_PRESET_PLUGIN = "@deepseek-ai/dsh-agent-preset"
PRESET_REGISTRY_PLUGIN = "@deepseek-ai/dsh-agent-preset-registry"
REGISTRY_OVERRIDE_ID = "agent-preset-registry"
PRESET_ENTRY_ID = "preset-crm-sre"
PRESET_ID = "crm-sre"
PRESET_NAME = "CRM SRE"
PRESET_DESCRIPTION = ("CRM SRE 授权脱敏材料分析与团队会诊：完整团长规则与 crm-sre 名册；"
                       "文件只读，无生产取数通道，仅用于专用宿主 profile 的新会话。")
PERSONA_CONFIG_KEYS = ("prefix", "suffix", "complete", "includeRuntimeContext")
TOOL_FS_CONFIG_KEYS = ("read", "readImage", "write", "edit", "applyPatch")
PRESET_CONFIG_KEYS = ("id", "name", "description", "order", "plugins")
REGISTRY_OVERRIDE_CONFIG_KEYS = ("default",)
PRESET_PLUGIN_NAMES = (PERSONA_PLUGIN, TIME_CONTEXT_PLUGIN, TOOL_FS_PLUGIN)
CAPTAIN_TOOL_FS = {"read": True, "readImage": False, "write": False, "edit": False, "applyPatch": False}
STATE_DIR = ".agent-teams"
MAX_MEMBERS = 7
MAX_MEMBERS_PER_BATCH = 3
MAX_USER_REQUESTS_PER_ROUND = 3
MAX_MEMBER_REQUESTS_PER_LOGICAL_TASK = 2
PROTOCOL_MAX_UTF16_UNITS = 240
ROLE_MAX_UTF16_UNITS = 40
DSH_SOURCES = ("lead-rules.md", "package-source.json", "protocol-summary.md", "shared-discipline.md")
GENERATED_FILES = ("build-info.json", "cordis.patch.yml", "package.json")
MODE_BLOCK_RE = re.compile(
    r"<!-- MODE:(?P<name>[A-Z_]+):BEGIN -->(?P<body>.*?)<!-- MODE:(?P=name):END -->\n?",
    re.DOTALL,
)
FOOTER_PREFIX = "使用绑定 Skill："
COMMON_PLACEHOLDER = "{{COMMON_CONTRACT}}"
ROSTER_PLACEHOLDER = "{{TEAM_ROSTER}}"


def _safe_file(root: Path, rel: str) -> Path:
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel or "\x00" in rel:
        raise ValueError("Unsafe DSH input path")
    if Path(rel).is_absolute() or any(p in {"", ".", ".."} for p in rel.split("/")):
        raise ValueError("Unsafe DSH input path: " + rel)
    p = root / rel
    for item in [p, *p.parents]:
        if not item.is_relative_to(root):
            continue
        if item.is_symlink() or getattr(item, "is_junction", lambda: False)():
            raise ValueError("Symlink input: " + rel)
        if getattr(item.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Reparse input: " + rel)
    if not p.is_file() or not p.resolve(strict=True).is_relative_to(root):
        raise ValueError("Missing or escaping DSH input: " + rel)
    return p


def _load_module(root: Path, rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _safe_file(root, rel))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(root: Path, rel: str) -> str:
    return _safe_file(root, rel).read_text(encoding="utf-8")


def runtime_policy(root: Path) -> dict:
    policy = json.loads(_read(root, "policies/runtime-contract.json"))
    if (policy.get("production_executor") is not False
            or policy.get("production_tools") != []
            or policy.get("implementation_status") != "NOT_IMPLEMENTED"
            or policy.get("read_only_boundary", {}).get("production_write") != "SEPARATE_CHANGE_APPROVAL_REQUIRED"):
        raise ValueError("Canonical production/managed boundary changed")
    return policy


def utf16_units(text: str) -> int:
    """JavaScript string.length semantics: count UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def input_rels(roles: dict) -> list[str]:
    """Exact input whitelist for one render; nothing outside this list is read."""
    rels = [
        "policy-source/dsh/package-source.json",
        "policy-source/dsh/lead-rules.md",
        "policy-source/dsh/shared-discipline.md",
        "policy-source/dsh/protocol-summary.md",
        "policy-source/roles-source.json",
        "policy-source/routing-source.json",
        "tools/build_bundle.py",
        "tools/dsh_bundle.py",
        "tools/release_rules.py",
        "policies/runtime-contract.json",
    ]
    for sid, role in sorted(roles.items()):
        if role["agent"] == CAPTAIN_AGENT:
            continue
        if not role.get("runbook"):
            raise ValueError("Domain role without canonical runbook: " + sid)
        rels.append("policy-source/prompts/roles/" + role["agent"] + ".md")
        rels.append("policy-source/references/" + role["runbook"])
    return rels


def _assert_inputs_safe(root: Path, roles: dict) -> None:
    """Fail closed on links, reparse points and unexpected DSH source files
    before anything is rendered or written."""
    rules = _load_module(root, "tools/release_rules.py", "dsh_safe_path_rules")
    for rel in input_rels(roles):
        if not rules.safe_relative(rel):
            raise ValueError("Unsafe DSH input: " + rel)
        _safe_file(root, rel)
        p = root / rel
        if not p.is_file():
            raise ValueError("Missing DSH input: " + rel)
        if rules.is_link(p) or any(rules.is_link(a) for a in p.parents if a.is_relative_to(root)):
            raise ValueError("Symlink or reparse point in DSH inputs: " + rel)
    source_dir = root / "policy-source/dsh"
    if not source_dir.is_dir() or rules.is_link(source_dir):
        raise ValueError("DSH source directory missing or is a link")
    expected = set(DSH_SOURCES)
    for p in sorted(source_dir.iterdir(), key=lambda q: q.as_posix()):
        if p.name not in expected or not p.is_file() or rules.is_link(p):
            raise ValueError("Unexpected entry in policy-source/dsh; keep the DSH source set exact: " + p.name)


def strip_role_body(text: str, agent_id: str) -> str:
    """Extract the mode-independent professional body of a WorkBuddy role
    source: drop frontmatter, the common-contract placeholder, ALL explicit
    MODE blocks and the obsolete bound-Skill footer. Fails closed on residue;
    never rewrites tool names or other content."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("Role source must start with frontmatter: " + agent_id)
    closings = [i for i in range(1, len(lines)) if lines[i].strip() == "---"]
    if not closings:
        raise ValueError("Unclosed frontmatter: " + agent_id)
    body = "\n".join(lines[closings[0] + 1:])
    body = MODE_BLOCK_RE.sub("", body)
    placeholders = [l for l in body.split("\n") if l.strip() == COMMON_PLACEHOLDER]
    footers = [l for l in body.split("\n") if l.strip().startswith(FOOTER_PREFIX)]
    if len(placeholders) != 1:
        raise ValueError("Expected exactly one common-contract placeholder: " + agent_id)
    if len(footers) != 1:
        raise ValueError("Expected exactly one bound-Skill footer: " + agent_id)
    keep = [l for l in body.split("\n")
            if l.strip() != COMMON_PLACEHOLDER and not l.strip().startswith(FOOTER_PREFIX)]
    stripped = "\n".join(keep).strip()
    for residue in ("<!-- MODE:", "MODE:", COMMON_PLACEHOLDER, FOOTER_PREFIX):
        if residue in stripped:
            raise ValueError("Mode-block, placeholder or footer residue in: " + agent_id)
    return stripped


def lead_persona_prefix(lead_rules: str, roster: str) -> str:
    if lead_rules.count(ROSTER_PLACEHOLDER) != 1:
        raise ValueError("Lead rules must contain exactly one roster placeholder")
    text = lead_rules.replace(ROSTER_PLACEHOLDER, roster.strip()).strip()
    if "{{" in text:
        raise ValueError("Unresolved placeholder remains in lead rules")
    return text


def preset_plugin_rows(persona_prefix: str) -> list[dict]:
    """Scoped rows of the dedicated CRM SRE captain preset, exactly three:
    a persona row shadowing the deployment persona with the same full lead
    rules while keeping the harness identity and runtime context, the upstream
    time-context row at its own defaults (no config override), and a read-only
    tool-fs row. No agent-instructions, skills, bash, web, plugins, jobs,
    schedule or general delegation row: global team tools and the global
    subagent service stay native, and this config is a model-visibility limit,
    not an OS sandbox."""
    return [
        {"name": PERSONA_PLUGIN,
         "config": {"prefix": persona_prefix, "suffix": "", "complete": False,
                    "includeRuntimeContext": True}},
        {"name": TIME_CONTEXT_PLUGIN},
        {"name": TOOL_FS_PLUGIN, "config": dict(CAPTAIN_TOOL_FS)},
    ]


def member_execution_prompt(discipline: str, role_body: str, runbook_name: str, runbook: str) -> str:
    parts = [
        "你是 CRM SRE 团队的一名领域成员，由团长通过 DSH Agent Teams 引擎派生。"
        "以下三部分内容是你的完整工作规则；与团长派单冲突时，以用户限制和更严格的边界为准。",
        "",
        "## DSH 成员共用纪律",
        "",
        discipline.strip(),
        "",
        "## 领域专业内容（来自角色定义源，已去除 WorkBuddy 专属模式块与绑定 Skill 页脚）",
        "",
        role_body,
        "",
        "## 领域 Runbook（完整内嵌：references/" + runbook_name + "；这是领域方法，不是本次现场证据）",
        "",
        runbook.strip(),
        "",
    ]
    return "\n".join(parts)


def render_members(root: Path, roles: dict, discipline: str) -> list[dict]:
    """Seven domain members (captain excluded), sorted by registered id, each
    embedding the full shared discipline, its own professional body and its
    full canonical domain runbook."""
    members = []
    for sid, role in sorted(roles.items()):
        if role["agent"] == CAPTAIN_AGENT:
            continue
        body = strip_role_body(_read(root, "policy-source/prompts/roles/" + role["agent"] + ".md"), role["agent"])
        runbook = _read(root, "policy-source/references/" + role["runbook"])
        members.append({
            "name": role["agent"],
            "role": role["title"],
            "tool_policy": TOOL_POLICY_ID,
            "executionPrompt": member_execution_prompt(discipline, body, role["runbook"], runbook),
        })
    members.sort(key=lambda m: m["name"])
    if len(members) != MAX_MEMBERS:
        raise ValueError("Expected exactly seven domain members, got %d" % len(members))
    for m in members:
        if utf16_units(m["role"]) > ROLE_MAX_UTF16_UNITS:
            raise ValueError("Member role identity too long: " + m["name"])
    return members


def _check_package_source(package_source: dict) -> None:
    expected = {
        "name": PACKAGE_NAME,
        "version": DSH_VERSION,
        "bundle_patch": "./cordis.patch.yml",
        "profile": PROFILE,
        "system_prompt_plugin": SYSTEM_PROMPT_PLUGIN,
        "upstream_plugin": AGENT_TEAMS_PLUGIN,
        "upstream_install": "EXPLICIT_SEPARATE_INSTALL_REQUIRED_NOT_AUTO_DISCOVERED",
    }
    if not isinstance(package_source, dict) or set(package_source) != set(expected) | {"description"}:
        raise ValueError("package-source.json keys must be exactly the pinned set plus description")
    for key, value in expected.items():
        if package_source.get(key) != value:
            raise ValueError("package-source.json field changed: " + key)
    if not isinstance(package_source.get("description"), str) or not package_source["description"].strip():
        raise ValueError("package-source.json description must be a non-empty string")


class _LiteralDumper(yaml.SafeDumper):
    """Safe dumper that emits multi-line strings as literal block scalars so
    prompts stay readable and the output stays byte-deterministic."""


def _repr_str(dumper: yaml.SafeDumper, data: str) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|" if "\n" in data else None)


_LiteralDumper.add_representer(str, _repr_str)


def _dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _dump_yaml(value) -> str:
    return yaml.dump(value, Dumper=_LiteralDumper, sort_keys=False, allow_unicode=True,
                     width=1000000, default_flow_style=False)


def render(root: Path) -> dict[str, str]:
    """Deterministically render the three dsh/ files as in-memory strings.
    Reads only whitelisted inputs; writes nothing; raises before any output
    exists if the whitelist, sources or limits are violated."""
    root = Path(root).resolve(strict=True)
    roles = json.loads(_read(root, "policy-source/roles-source.json"))
    _assert_inputs_safe(root, roles)
    package_source = json.loads(_read(root, "policy-source/dsh/package-source.json"))
    _check_package_source(package_source)
    policy = runtime_policy(root)
    lead_rules = _read(root, "policy-source/dsh/lead-rules.md")
    discipline = _read(root, "policy-source/dsh/shared-discipline.md")
    protocol = _read(root, "policy-source/dsh/protocol-summary.md").strip()
    if not protocol or "\n" in protocol:
        raise ValueError("protocol-summary.md must be a single non-empty line")
    if utf16_units(protocol) > PROTOCOL_MAX_UTF16_UNITS:
        raise ValueError("profile.protocol exceeds %d UTF-16 code units: %d"
                         % (PROTOCOL_MAX_UTF16_UNITS, utf16_units(protocol)))
    if COMMON_PLACEHOLDER in lead_rules or MODE_BLOCK_RE.search(lead_rules) or "MANAGED_HARNESS" not in lead_rules:
        raise ValueError("lead-rules.md must be free of WorkBuddy mode blocks and state the managed boundary")
    routing = json.loads(_read(root, "policy-source/routing-source.json"))
    roster_renderer = _load_module(root, "tools/build_bundle.py", "dsh_roster_renderer")
    roster = roster_renderer.render_team_roster(roles, routing)
    persona_prefix = lead_persona_prefix(lead_rules, roster)
    members = render_members(root, roles, discipline)
    for m in members:
        if m["name"] == CAPTAIN_AGENT:
            raise ValueError("Captain must not appear as a member entry")
        if set(m) != set(MEMBER_KEYS) or m["tool_policy"] != TOOL_POLICY_ID:
            raise ValueError("Member shape violated: " + m["name"])
    package = {
        "name": package_source["name"],
        "version": package_source["version"],
        "description": package_source["description"],
        "dsh": {"bundle": {"patch": package_source["bundle_patch"]}},
    }
    patch = [
        {
            "id": "system-prompt",
            "name": SYSTEM_PROMPT_PLUGIN,
            "config": {
                "includeHarnessIdentity": True,
                "includeRuntimeContext": True,
                "personaPrefix": persona_prefix,
                "personaSuffix": "",
            },
        },
        {
            "id": "agent-teams",
            "name": AGENT_TEAMS_PLUGIN,
            "config": {
                "stateDir": STATE_DIR,
                "memberProvider": "spawn",
                "memberMaxDepth": 0,
                "maxMembers": MAX_MEMBERS,
                "toolPolicies": {TOOL_POLICY_ID: {"allow": list(MEMBER_TOOLS)}},
                "profiles": {
                    PROFILE: {
                        "taskPlanning": "captain",
                        "protocol": protocol,
                        "members": members,
                    }
                },
            },
        },
        {
            "id": REGISTRY_OVERRIDE_ID,
            "name": PRESET_REGISTRY_PLUGIN,
            "config": {"default": PRESET_ID},
        },
        {
            "insert": [{
                "id": PRESET_ENTRY_ID,
                "name": AGENT_PRESET_PLUGIN,
                "config": {
                    "id": PRESET_ID,
                    "name": PRESET_NAME,
                    "description": PRESET_DESCRIPTION,
                    "order": 0,
                    "plugins": preset_plugin_rows(persona_prefix),
                },
            }],
        },
    ]
    package_text = _dump_json(package)
    patch_text = _dump_yaml(patch)
    build_info = {
        "version": DSH_VERSION,
        "package": PACKAGE_NAME,
        "scope": "CONFIGURATION_AND_PROMPTS_ONLY_NO_JS_RUNTIME",
        "upstream_plugin": AGENT_TEAMS_PLUGIN,
        "upstream_install": package_source["upstream_install"],
        "profile": PROFILE,
        "managed_harness": policy["implementation_status"],
        "production_executor": policy["production_executor"],
        "production_tools": policy["production_tools"],
        "members": len(members),
        "member_tool_allow": list(MEMBER_TOOLS),
        "captain_preset": {
            "preset": PRESET_ID,
            "composition_entry": PRESET_ENTRY_ID,
            "registry_default_override": REGISTRY_OVERRIDE_ID,
            "scoped_plugins": list(PRESET_PLUGIN_NAMES),
            "tool_fs": dict(CAPTAIN_TOOL_FS),
        },
        "source_files": {rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
                         for rel in input_rels(roles)},
        "outputs": {
            "package.json": hashlib.sha256(package_text.encode("utf-8")).hexdigest(),
            "cordis.patch.yml": hashlib.sha256(patch_text.encode("utf-8")).hexdigest(),
        },
    }
    rendered = {
        "dsh/package.json": package_text,
        "dsh/cordis.patch.yml": patch_text,
        "dsh/build-info.json": _dump_json(build_info),
    }
    if set(rendered) != {DSH_DIR + "/" + n for n in GENERATED_FILES}:
        raise ValueError("Rendered dsh file set mismatch")
    return rendered


def build(root: Path) -> dict:
    """Build in isolation and atomically replace ONLY dsh/ with rollback on
    ordinary failure. Never modifies canonical sources, WorkBuddy generated
    trees, root VERSION or Git state; never deletes anything outside its own
    disposable staging outputs. A crash or power loss is not a filesystem
    transaction: backups are removed only after a clean swap."""
    root = Path(root).resolve(strict=True)
    destination = root / DSH_DIR
    expected_names = set(GENERATED_FILES)
    rules = _load_module(root, "tools/release_rules.py", "dsh_build_safe_path_rules")
    if rules.is_link(destination):
        raise ValueError("Owned output path is a link: " + DSH_DIR)
    if destination.exists():
        if not destination.is_dir():
            raise ValueError("Owned output path is not a directory: " + DSH_DIR)
        for p in sorted(destination.rglob("*"), key=lambda q: q.as_posix()):
            rel = p.relative_to(root).as_posix()
            if rules.is_link(p) or not p.is_file():
                raise ValueError("Nonregular owned output: " + rel)
            if p.name not in expected_names or p.parent != destination:
                raise ValueError("Unknown file in owned dsh output; move user data outside before building: " + rel)
    def output_fingerprint(directory: Path):
        if not directory.exists():
            return None
        result = {}
        for item in sorted(directory.iterdir()):
            if rules.is_link(item) or not item.is_file():
                raise ValueError("Concurrent nonregular output preserved")
            result[item.name] = hashlib.sha256(item.read_bytes()).hexdigest()
        return result
    original_output = output_fingerprint(destination)
    rendered = render(root)
    temporary = Path(tempfile.mkdtemp(prefix=".dsh-build-", dir=root.parent))
    moved_old = False
    committed = False
    keep_backup = False
    try:
        staged = temporary / "staged" / DSH_DIR
        staged.mkdir(parents=True)
        for name in GENERATED_FILES:
            (staged / name).write_bytes(rendered[DSH_DIR + "/" + name].encode("utf-8"))
        backup = temporary / "backup"
        backup.mkdir()
        try:
            if destination.exists():
                os.replace(destination, backup / DSH_DIR)
                moved_old = True
                if output_fingerprint(backup / DSH_DIR) != original_output:
                    raise OSError("Concurrent output change captured in backup")
            os.replace(staged, destination)
            committed = True
            if moved_old and output_fingerprint(backup / DSH_DIR) != original_output:
                raise OSError("Concurrent backup change")
        except BaseException:
            try:
                if committed:
                    if output_fingerprint(destination) != {name: hashlib.sha256(rendered[DSH_DIR + "/" + name].encode("utf-8")).hexdigest() for name in GENERATED_FILES}:
                        raise RuntimeError("Concurrent new output preserved; manual recovery required")
                    os.replace(destination, temporary / "discarded-dsh")
                if moved_old:
                    os.replace(backup / DSH_DIR, destination)
            except BaseException as rollback_error:
                keep_backup = True
                raise RuntimeError(f"Rollback incomplete; preserve {backup / DSH_DIR}") from rollback_error
            raise
        patch_data = yaml.safe_load(rendered["dsh/cordis.patch.yml"])
        member_count = len(patch_data[1]["config"]["profiles"][PROFILE]["members"])
        return {
            "version": DSH_VERSION,
            "package": PACKAGE_NAME,
            "profile": PROFILE,
            "captain_preset": PRESET_ID,
            "files": len(GENERATED_FILES),
            "members": member_count,
            "scope": "OFFLINE_DETERMINISTIC_CONFIG_BUILD_ONLY",
        }
    finally:
        if not keep_backup:
            shutil.rmtree(temporary, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.root), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"DSH build failed: {exc}") from exc


if __name__ == "__main__":
    main()
