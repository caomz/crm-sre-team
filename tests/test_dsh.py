"""DSH domain bundle: deterministic render, structural/boundary invariants,
tamper detection and failure-recovery tests. Synthetic data only; offline."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dsh_bundle = _load("tools/dsh_bundle.py", "tested_dsh_bundle")
check_dsh = _load("tools/check_dsh.py", "tested_dsh_checker")
release_rules = _load("tools/release_rules.py", "tested_dsh_release_rules")

GENERATED_RELS = {"dsh/package.json", "dsh/cordis.patch.yml", "dsh/build-info.json"}
PACKAGE_JSON_KEYS = {"name", "version", "description", "dsh"}
QUADRANTS = "已确认事实／高概率候选／待验证／已排除"


def tree_hash(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"), key=lambda q: q.as_posix())
            if p.is_file() and "__pycache__" not in p.parts}


def _can_symlink() -> bool:
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            t = p / "t"
            t.write_bytes(b"x")
            link = p / "l"
            link.symlink_to(t)
            return link.is_symlink()
    except OSError:
        return False


requires_real_symlink = unittest.skipUnless(
    _can_symlink(), "SKIPPED_CAPABILITY: real filesystem symlinks unavailable on this host")


class DshRenderTests(unittest.TestCase):
    """Pure render invariants on the real repository sources (read-only)."""

    @classmethod
    def setUpClass(cls):
        cls.rendered = dsh_bundle.render(ROOT)
        cls.package = json.loads(cls.rendered["dsh/package.json"])
        cls.patch = yaml.safe_load(cls.rendered["dsh/cordis.patch.yml"])
        cls.info = json.loads(cls.rendered["dsh/build-info.json"])
        cls.sys_cfg = cls.patch[0]["config"]
        cls.team_cfg = cls.patch[1]["config"]
        cls.registry_cfg = cls.patch[2]["config"]
        cls.preset_row = cls.patch[3]["insert"][0]
        cls.preset_cfg = cls.preset_row["config"]
        cls.preset_plugins = cls.preset_cfg["plugins"]
        cls.preset_persona_cfg = cls.preset_plugins[0]["config"]
        cls.captain_fs_cfg = cls.preset_plugins[2]["config"]
        cls.profile = cls.team_cfg["profiles"]["crm-sre"]
        cls.members = cls.profile["members"]
        cls.roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))

    def test_01_render_keys_deterministic(self):
        self.assertEqual(set(self.rendered), GENERATED_RELS)
        self.assertEqual(dsh_bundle.render(ROOT), self.rendered)

    def test_02_package_json_pins_no_runtime_no_dependencies(self):
        self.assertEqual(set(self.package), PACKAGE_JSON_KEYS)
        self.assertEqual(self.package["name"], "crm-sre-dsh-team")
        self.assertEqual(self.package["version"], "2.8.0-dsh.1")
        self.assertEqual(self.package["dsh"], {"bundle": {"patch": "./cordis.patch.yml"}})
        self.assertFalse({"main", "scripts", "dependencies", "peerDependencies",
                          "optionalDependencies", "devDependencies"} & set(self.package))
        self.assertIn("显式单独安装", self.package["description"])

    def test_03_patch_four_records_overrides_then_registry_then_preset_insert(self):
        self.assertEqual(len(self.patch), 4)
        self.assertEqual([e["id"] for e in self.patch[:3]],
                         ["system-prompt", "agent-teams", "agent-preset-registry"])
        self.assertEqual([e["name"] for e in self.patch[:3]],
                         ["@deepseek-ai/dsh-system-prompt", "@nanmicoder/dsh-agent-teams",
                          "@deepseek-ai/dsh-agent-preset-registry"])
        # Records 0/1 keep the original global overrides.
        self.assertTrue(self.sys_cfg["includeHarnessIdentity"] is True)
        self.assertTrue(self.sys_cfg["includeRuntimeContext"] is True)
        self.assertEqual(self.sys_cfg["personaSuffix"], "")
        self.assertEqual(self.team_cfg["stateDir"], ".agent-teams")
        self.assertEqual(self.team_cfg["memberProvider"], "spawn")
        self.assertEqual(self.team_cfg["memberMaxDepth"], 0)
        self.assertEqual(self.team_cfg["maxMembers"], 7)
        self.assertEqual(self.profile["taskPlanning"], "captain")
        # Record 2 overrides the existing registry default so NEW sessions run
        # the CRM SRE preset (dedicated host profile only).
        self.assertEqual(set(self.patch[2]), {"id", "name", "config"})
        self.assertEqual(set(self.registry_cfg), {"default"})
        self.assertEqual(self.registry_cfg["default"], "crm-sre")
        # Record 3 is a bare id-less insert of exactly one dedicated preset entry.
        self.assertEqual(set(self.patch[3]), {"insert"})
        self.assertEqual(len(self.patch[3]["insert"]), 1)
        self.assertEqual(set(self.preset_row), {"id", "name", "config"})
        self.assertEqual(self.preset_row["id"], "preset-crm-sre")
        self.assertEqual(self.preset_row["name"], "@deepseek-ai/dsh-agent-preset")

    def test_03b_captain_preset_closed_shape_scopes_persona_time_context_readonly_fs(self):
        self.assertEqual(set(self.preset_cfg), {"id", "name", "description", "order", "plugins"})
        self.assertEqual(self.preset_cfg["id"], "crm-sre")
        self.assertEqual(self.preset_cfg["name"], "CRM SRE")
        self.assertEqual(self.preset_cfg["order"], 0)
        self.assertTrue(self.preset_cfg["description"].strip())
        self.assertEqual([r["name"] for r in self.preset_plugins],
                         ["@deepseek-ai/dsh-persona", "@deepseek-ai/dsh-time-context",
                          "@deepseek-ai/dsh-tool-fs"])
        # The scoped persona row shadows the deployment persona with the SAME
        # full lead+roster text as the global override — the original failure
        # was the standard preset persona shadowing the global prefix, so the
        # captain session lost the CRM lead identity entirely.
        self.assertEqual(set(self.preset_persona_cfg),
                         {"prefix", "suffix", "complete", "includeRuntimeContext"})
        self.assertEqual(self.preset_persona_cfg["prefix"], self.sys_cfg["personaPrefix"])
        self.assertEqual(self.preset_persona_cfg["suffix"], "")
        self.assertFalse(self.preset_persona_cfg["complete"])
        self.assertTrue(self.preset_persona_cfg["includeRuntimeContext"])
        # time-context rides on upstream defaults: a bare row without config.
        self.assertEqual(set(self.preset_plugins[1]), {"name"})
        # tool-fs is exactly read-only: no mutation path, no extra cap overrides.
        self.assertEqual(self.captain_fs_cfg,
                         {"read": True, "readImage": False, "write": False,
                          "edit": False, "applyPatch": False})
        banned = ("shell", "bash", "web", "skill", "job", "schedule", "instruction", "delegat")
        for row in self.preset_plugins:
            with self.subTest(plugin=row["name"]):
                lowered = row["name"].lower()
                self.assertFalse(any(f in lowered for f in banned))

    def test_04_member_roster_identity_sorted_captain_excluded(self):
        expected = sorted(r["agent"] for sid, r in self.roles.items() if sid != "stability-director")
        self.assertEqual(len(self.members), 7)
        self.assertEqual([m["name"] for m in self.members], expected)
        self.assertNotIn("telecom-crm-sre-team-lead", {m["name"] for m in self.members})
        for m in self.members:
            with self.subTest(member=m["name"]):
                self.assertEqual(set(m), {"name", "role", "tool_policy", "executionPrompt"})
                self.assertEqual(m["role"], self.roles[[s for s, r in self.roles.items() if r["agent"] == m["name"]][0]]["title"])
                self.assertLessEqual(dsh_bundle.utf16_units(m["role"]), dsh_bundle.ROLE_MAX_UTF16_UNITS)
                self.assertEqual(m["tool_policy"], "crm-sre-member-coordination")

    def test_05_tool_policy_allow_list_is_exactly_four_coordination_tools(self):
        policies = self.team_cfg["toolPolicies"]
        self.assertEqual(set(policies), {"crm-sre-member-coordination"})
        self.assertEqual(policies["crm-sre-member-coordination"]["allow"],
                         ["agent_teams_claim_task", "agent_teams_update_task",
                          "agent_teams_send_message", "agent_teams_status"])
        banned = {"read", "glob", "grep", "shell", "bash", "write", "edit", "webfetch"}
        patch_text = self.rendered["dsh/cordis.patch.yml"]
        for tool in banned:
            self.assertNotIn('"' + tool + '"', patch_text)
        # The captain preset adds no mutation surface: the only tool-suite row
        # is the read-only tool-fs config asserted in test_03b.
        for flag, expected in (("read", "true"), ("readImage", "false"), ("write", "false"),
                               ("edit", "false"), ("applyPatch", "false")):
            with self.subTest(tool_fs_flag=flag):
                self.assertIn(flag + ": " + expected, patch_text)
        self.assertNotIn("write: true", patch_text)
        self.assertNotIn("edit: true", patch_text)
        self.assertNotIn("readImage: true", patch_text)
        self.assertNotIn("applyPatch: true", patch_text)

    def test_06_member_prompts_embed_discipline_body_and_full_runbook(self):
        discipline = (ROOT / "policy-source/dsh/shared-discipline.md").read_text(encoding="utf-8")
        for m in self.members:
            with self.subTest(member=m["name"]):
                prompt = m["executionPrompt"]
                self.assertTrue(prompt.rstrip().endswith(discipline.strip()))
                self.assertIn(QUADRANTS, prompt)
                for tool in dsh_bundle.MEMBER_TOOLS:
                    self.assertIn(tool, prompt)
                role = self.roles[[s for s, r in self.roles.items() if r["agent"] == m["name"]][0]]
                body = dsh_bundle.strip_role_body(
                    (ROOT / "policy-source/prompts/roles" / (role["agent"] + ".md")).read_text(encoding="utf-8"),
                    role["agent"])
                self.assertIn(body, prompt)
                runbook = (ROOT / "policy-source/references" / role["runbook"]).read_text(encoding="utf-8")
                self.assertIn(runbook.strip(), prompt)
                self.assertNotIn("使用绑定 Skill", prompt)
                self.assertNotIn("<!-- MODE:", prompt)

    def test_07_persona_prefix_is_full_lead_rules_with_roster(self):
        prefix = self.sys_cfg["personaPrefix"]
        lead_rules = (ROOT / "policy-source/dsh/lead-rules.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", prefix)
        stripped_lead = lead_rules.replace(dsh_bundle.ROSTER_PLACEHOLDER, "").strip()
        self.assertGreater(len(prefix), len(stripped_lead))
        self.assertIn("## 成员名册", prefix)
        self.assertIn("| 注册 ID |", prefix)
        for sid, role in self.roles.items():
            if sid == "stability-director":
                continue
            self.assertIn(role["agent"], prefix)
            self.assertIn(role["title"], prefix)

    def test_07a_dsh_dispatch_preserves_roster_without_workbuddy_parameters(self):
        renderer = _load("tools/build_bundle.py", "tested_roster_host_contracts")
        routing = json.loads((ROOT / "policy-source/routing-source.json").read_text(encoding="utf-8"))
        legacy_roster = renderer.render_team_roster(self.roles, routing)
        frozen_lead = (ROOT / "agents/telecom-crm-sre-team-lead.md").read_text(encoding="utf-8")
        # The default renderer must still match the frozen WorkBuddy artifact.
        self.assertIn(legacy_roster, frozen_lead)
        self.assertIn(routing["_dispatch_note"], legacy_roster)
        domain_rows = [line for line in legacy_roster.splitlines() if line.startswith("|")]
        for prefix in (self.sys_cfg["personaPrefix"], self.preset_persona_cfg["prefix"]):
            self.assertEqual([line for line in prefix.splitlines() if line.startswith("|")], domain_rows)
            self.assertIn("派单对象采用 profile 名册中的真实成员 name。", prefix)
            self.assertNotIn("subagent_type", prefix)
            self.assertNotIn("日常不传 name", prefix)

    def test_08_protocol_within_utf16_limit_and_honest(self):
        protocol = self.profile["protocol"]
        self.assertLessEqual(dsh_bundle.utf16_units(protocol), 240)
        self.assertNotIn("运行时硬守卫已实现", protocol)
        self.assertIn("不是运行时硬守卫", protocol)
        self.assertIn("跨attempt累计", protocol)
        self.assertIn("一项只写一份独立材料，零余量的待验证只写机制。", protocol)
        self.assertEqual(dsh_bundle.utf16_units("😀"), 2)
        self.assertEqual(dsh_bundle.utf16_units("a"), 1)

    def test_09_strip_role_body_removes_frontmatter_modes_footer(self):
        for sid, role in self.roles.items():
            if sid == "stability-director":
                continue  # The DSH captain has its own canonical rules, not a legacy-body conversion.
            with self.subTest(role=role["agent"]):
                source = (ROOT / "policy-source/prompts/roles" / (role["agent"] + ".md")).read_text(encoding="utf-8")
                body = dsh_bundle.strip_role_body(source, role["agent"])
                self.assertNotIn("maxTurns", body)
                self.assertNotIn("displayName", body)
                self.assertNotIn("<!-- MODE:", body)
                self.assertNotIn("MODE:", body)
                self.assertNotIn("{{COMMON_CONTRACT}}", body)
                self.assertNotIn("使用绑定 Skill", body)
                self.assertIn(QUADRANTS, body)

    def test_10_generated_text_carries_no_wb_harness_and_no_seed_tasks(self):
        for rel, text in self.rendered.items():
            with self.subTest(file=rel):
                self.assertNotIn("WORKBUDDY", text)
                self.assertNotIn("<!-- MODE:", text)
                self.assertNotIn("使用绑定 Skill", text)
                self.assertNotIn("{{", text)
        patch_payload = json.dumps(self.patch, ensure_ascii=False)
        self.assertIn(check_dsh.MANAGED_SENTENCE, self.sys_cfg["personaPrefix"])
        self.assertIn("仍未实现（NOT_IMPLEMENTED）", patch_payload)
        self.assertNotIn("WORKBUDDY", patch_payload)
        self.assertNotIn("seedTasks", patch_payload)
        self.assertNotIn("fallback", patch_payload)
        self.assertEqual(self.info["managed_harness"], "NOT_IMPLEMENTED")
        self.assertFalse(self.info["production_executor"])
        self.assertEqual(self.info["production_tools"], [])

    def test_10b_build_info_records_captain_preset_facts(self):
        self.assertEqual(self.info["captain_preset"],
                         {"preset": "crm-sre", "composition_entry": "preset-crm-sre",
                          "registry_default_override": "agent-preset-registry",
                          "scoped_plugins": ["@deepseek-ai/dsh-persona", "@deepseek-ai/dsh-time-context",
                                             "@deepseek-ai/dsh-tool-fs"],
                          "tool_fs": {"read": True, "readImage": False, "write": False,
                                      "edit": False, "applyPatch": False}})

    def test_11_no_production_channel_fragments_in_rendered_pack(self):
        all_text = "".join(self.rendered.values())
        for fragment in check_dsh.BANNED_FRAGMENTS:
            self.assertNotIn(fragment, all_text)

    def test_12_new_files_enrolled_sorted_in_release_manifest(self):
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(manifest, sorted(set(manifest)))
        for rel in check_dsh.REQUIRED_ENROLLMENT:
            self.assertIn(rel, manifest)
        self.assertTrue(all(release_rules.safe_relative(rel) for rel in check_dsh.REQUIRED_ENROLLMENT))

    def test_13_dsh_version_separate_from_root_version(self):
        root_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertNotEqual(root_version, dsh_bundle.DSH_VERSION)
        self.assertEqual(self.package["version"], dsh_bundle.DSH_VERSION)


class DshCheckerTests(unittest.TestCase):
    def test_20_checker_passes_on_generated_repo(self):
        report = check_dsh.run(ROOT)
        self.assertTrue(report["pass"], report["errors"])


class DshBuildTests(unittest.TestCase):
    """Build, recovery and tamper behavior on a disposable copy of the repo."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # tempfile may return a /var/... alias to /private/var/... on macOS.
        # Builders resolve the input root before os.replace; use the physical
        # directory here so failure-injection comparisons reach the same path.
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = self.base / "crm-sre-team"
        self.root.mkdir()
        for name in release_rules.manifest_names(ROOT):
            source = ROOT / name
            if not source.is_file():
                continue
            if release_rules.is_link(source):
                raise ValueError("Linked fixture input: " + name)
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def test_21_build_creates_only_dsh_outputs_and_preserves_wb_trees(self):
        sentinel = (self.root / "agents" / "telecom-crm-oracle-dba.md").read_bytes()
        result = dsh_bundle.build(self.root)
        self.assertEqual(result["version"], "2.8.0-dsh.1")
        self.assertEqual(sorted(p.name for p in (self.root / "dsh").iterdir()),
                         ["build-info.json", "cordis.patch.yml", "package.json"])
        self.assertEqual((self.root / "agents" / "telecom-crm-oracle-dba.md").read_bytes(), sentinel)
        self.assertEqual((self.root / "VERSION").read_text(encoding="utf-8").strip(), "2.8.0-rc10")

    def test_22_build_twice_identical_and_matches_render(self):
        dsh_bundle.build(self.root)
        first = tree_hash(self.root / "dsh")
        dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh"), first)
        for rel, text in dsh_bundle.render(self.root).items():
            self.assertEqual((self.root / rel).read_bytes(), text.encode("utf-8"))

    def test_23_unknown_user_file_in_dsh_rejected_and_preserved(self):
        dsh = self.root / "dsh"
        dsh.mkdir(exist_ok=True)
        (dsh / "user-notes.md").write_text("SYNTHETIC_USER_DATA", encoding="utf-8")
        before = tree_hash(dsh)
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(dsh), before)
        self.assertTrue((dsh / "user-notes.md").exists())

    def test_24_commit_failure_rolls_back_then_rebuilds_identically(self):
        dsh_bundle.build(self.root)
        before = tree_hash(self.root / "dsh")
        actual = dsh_bundle.os.replace
        count = [0]

        def fail_second_rename(src, dst):
            count[0] += 1
            if count[0] == 2:
                raise OSError("synthetic second-rename failure")
            return actual(src, dst)

        with patch.object(dsh_bundle.os, "replace", side_effect=fail_second_rename):
            with self.assertRaises(OSError):
                dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh"), before)
        self.assertEqual(list(self.base.glob(".dsh-build-*")), [])
        dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh"), before)

    def test_25_render_failure_before_swap_leaves_dsh_unchanged(self):
        dsh_bundle.build(self.root)
        before = tree_hash(self.root / "dsh")
        source = self.root / "policy-source/dsh/lead-rules.md"
        original = source.read_text(encoding="utf-8")
        source.write_text(original.replace("{{TEAM_ROSTER}}", ""), encoding="utf-8")
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh"), before)
        source.write_text(original, encoding="utf-8")

    def test_26_tampered_artifact_detected_then_recovered(self):
        dsh_bundle.build(self.root)
        target = self.root / "dsh/cordis.patch.yml"
        target.write_bytes(target.read_bytes().replace(b"stateDir", b"stateDirT", 1))
        report = check_dsh.run(self.root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("render_artifact_equality" in e or "build_info_output_hashes" in e
                            for e in report["errors"]), report["errors"])
        dsh_bundle.build(self.root)
        self.assertTrue(check_dsh.run(self.root)["pass"])

    def test_27_tampered_source_detected(self):
        dsh_bundle.build(self.root)
        source = self.root / "policy-source/dsh/shared-discipline.md"
        source.write_text(source.read_text(encoding="utf-8") + "\n未审核的附加行\n", encoding="utf-8")
        report = check_dsh.run(self.root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("render_artifact_equality" in e or "build_info_source_hashes" in e
                            for e in report["errors"]), report["errors"])

    def test_28_extra_or_missing_output_detected(self):
        dsh_bundle.build(self.root)
        (self.root / "dsh/extra.md").write_text("SYNTHETIC", encoding="utf-8")
        self.assertFalse(check_dsh.run(self.root)["pass"])
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        (self.root / "dsh/extra.md").unlink()
        self.assertTrue(check_dsh.run(self.root)["pass"])

    def test_29_protocol_over_limit_rejected_before_any_write(self):
        before = tree_hash(self.root / "dsh") if (self.root / "dsh").exists() else {}
        source = self.root / "policy-source/dsh/protocol-summary.md"
        source.write_text("超" * 241, encoding="utf-8")
        with self.assertRaises(ValueError):
            dsh_bundle.render(self.root)
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh") if (self.root / "dsh").exists() else {}, before)

    def test_30_member_tool_or_route_override_rejected_by_structure(self):
        dsh_bundle.build(self.root)
        patch_path = self.root / "dsh/cordis.patch.yml"
        data = yaml.safe_load(patch_path.read_text(encoding="utf-8"))
        data[1]["config"]["profiles"]["crm-sre"]["members"][0]["model"] = "SYNTHETIC"
        patch_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        report = check_dsh.run(self.root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("member_prompt_full_composition" in e or "render_artifact_equality" in e
                            for e in report["errors"]), report["errors"])

    def test_30b_missing_preset_insert_reproduces_standard_persona_shadow_failure(self):
        # Original confirmed failure: with only the two global overrides, the
        # standard agent preset's scoped persona shadowed the global lead
        # prefix, so real captain sessions carried no CRM lead persona. A pack
        # missing the dedicated preset insert must be rejected, not counted as
        # fixed.
        dsh_bundle.build(self.root)
        patch_path = self.root / "dsh/cordis.patch.yml"
        data = yaml.safe_load(patch_path.read_text(encoding="utf-8"))
        del data[3]
        patch_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        report = check_dsh.run(self.root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("patch_top_level_four_records" in e or "render_artifact_equality" in e
                            for e in report["errors"]), report["errors"])

    def test_30c_scoped_persona_registry_or_toolfs_drift_detected(self):
        dsh_bundle.build(self.root)
        patch_path = self.root / "dsh/cordis.patch.yml"
        # Keep the original as bytes: text-mode restore on Windows would turn
        # LF into CRLF and the raw artifact hash would rightly reject it.
        original_bytes = patch_path.read_bytes()

        def mutate_scoped_persona(data):
            data[3]["insert"][0]["config"]["plugins"][0]["config"]["prefix"] = "你是编码助手"

        def mutate_registry_default(data):
            data[2]["config"]["default"] = "SYNTHETIC-OTHER-PRESET"

        def mutate_tool_fs_write(data):
            data[3]["insert"][0]["config"]["plugins"][2]["config"]["write"] = True

        for label, mutate in (("scoped_persona_diverges_from_global_lead", mutate_scoped_persona),
                              ("registry_default_not_crm_sre", mutate_registry_default),
                              ("captain_tool_fs_write_enabled", mutate_tool_fs_write)):
            with self.subTest(case=label):
                data = yaml.safe_load(original_bytes.decode("utf-8"))
                mutate(data)
                patch_path.write_bytes(yaml.dump(data, allow_unicode=True).encode("utf-8"))
                self.assertFalse(check_dsh.run(self.root)["pass"], label)
        patch_path.write_bytes(original_bytes)
        self.assertEqual(patch_path.read_bytes(), original_bytes)
        self.assertTrue(check_dsh.run(self.root)["pass"])

    def test_30d_malformed_preset_rows_and_config_are_reported_without_crashing(self):
        dsh_bundle.build(self.root)
        path = self.root / "dsh/cordis.patch.yml"
        original = path.read_text(encoding="utf-8")
        for bad in (None, "not-a-row", True, []):
            with self.subTest(row=bad):
                data = yaml.safe_load(original)
                data[3]["insert"][0]["config"]["plugins"][0] = bad
                path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
                report = check_dsh.run(self.root)
                self.assertFalse(report["pass"])
                self.assertTrue(any("preset_plugins_three_scoped_rows" in e for e in report["errors"]))
        for index in (0, 1, 2):
            with self.subTest(config=index):
                data = yaml.safe_load(original)
                data[index]["config"] = "not-an-object"
                path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
                self.assertFalse(check_dsh.run(self.root)["pass"])
        data = yaml.safe_load(original)
        data[3]["insert"][0]["config"]["order"] = False
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        report = check_dsh.run(self.root)
        self.assertTrue(any("preset_identity_pins" in e for e in report["errors"]))

    def test_31_missing_checker_registration_detected(self):
        manifest_path = self.root / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].remove("tools/dsh_bundle.py")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = check_dsh.run(self.root)
        self.assertFalse(report["pass"])
        self.assertTrue(any("dsh_enrollment_exact" in e for e in report["errors"]), report["errors"])

    def test_legacy_dispatch_reintroduction_fails_even_after_rebuild(self):
        source = self.root / "policy-source/dsh/lead-rules.md"
        original = source.read_bytes()
        for instruction in ("派单时 subagent_type 填注册 ID。", "日常不传 name。"):
            with self.subTest(instruction=instruction):
                source.write_bytes(original + ("\n" + instruction + "\n").encode("utf-8"))
                dsh_bundle.build(self.root)
                report = check_dsh.run(self.root)
                checks = {row["id"]: row["passed"] for row in report["checks"]}
                self.assertTrue(checks["render_artifact_equality"])
                self.assertFalse(checks["no_legacy_dispatch_parameters"])
                self.assertFalse(report["pass"])
        source.write_bytes(original)

    def test_logical_task_retry_bound_removal_fails_even_after_rebuild(self):
        # These checks protect the prompt contract, not runtime enforcement.
        source = self.root / "policy-source/dsh/lead-rules.md"
        original = source.read_text(encoding="utf-8")
        for fragment in (
            "每个逻辑任务失败后累计至多重派一次；重派后的 attempt 仍失败就停止并报告受阻，不再自动重派。",
            "不得通过新建任务、改名或重新派单重置重派次数或补证额度。",
            "重派上限是团长核对的协议约束，不是运行时硬守卫。",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, original)
                source.write_bytes(original.replace(fragment, "", 1).encode("utf-8"))
                dsh_bundle.build(self.root)
                report = check_dsh.run(self.root)
                checks = {row["id"]: row["passed"] for row in report["checks"]}
                self.assertTrue(checks["render_artifact_equality"])
                self.assertFalse(checks["lead_boundary_sentences"])
                self.assertFalse(report["pass"])
        source.write_bytes(original.encode("utf-8"))

    def test_evidence_ack_gate_embeds_in_both_personas_and_all_members(self):
        dsh_bundle.build(self.root)
        data = yaml.safe_load((self.root / "dsh/cordis.patch.yml").read_text(encoding="utf-8"))
        personas = (
            data[0]["config"]["personaPrefix"],
            data[3]["insert"][0]["config"]["plugins"][0]["config"]["prefix"],
        )
        for persona in personas:
            with self.subTest(persona=persona[:30]):
                self.assertIn("材料缺失型失败先等待用户提供所缺的新授权材料正文", persona)
                self.assertIn("控制性接收 ACK", persona)
                self.assertIn("确认该接收轮次已结束后", persona)
                self.assertIn("新 attempt 必须核对引擎真实 attempt_id", persona)
        members = data[1]["config"]["profiles"]["crm-sre"]["members"]
        self.assertEqual(len(members), 7)
        for member in members:
            with self.subTest(member=member["name"]):
                prompt = member["executionPrompt"]
                self.assertIn("原失败 attempt 收到团长明确的补充材料接收请求时", prompt)
                self.assertIn("真正重派后只使用引擎新返回的 attempt_id", prompt)
                self.assertIn("在 output、发给团长的消息和成员会话答复中使用同一组已选材料", prompt)

    def test_missing_evidence_gate_rebuild_still_fails_independent_checker(self):
        # A regenerated YAML may equal an invalid rule source: pin the policy
        # independently of the renderer, not only through artifact hashes.
        cases = (
            ("lead-rules.md", (
                "材料缺失型失败先等待用户提供所缺的新授权材料正文；仅出现 E 编号、口头承诺或空材料时不得调用 agent_teams_reassign_task",
                "取得原成员针对真实失败 task/attempt 的控制性接收 ACK",
                "确认该接收轮次已结束后，才对同一 task_id 与原成员执行唯一一次 agent_teams_reassign_task",
                "新 attempt 必须核对引擎真实 attempt_id 与当前会话是否含新材料正文",
            ), "lead_boundary_sentences"),
            ("shared-discipline.md", (
                "原失败 attempt 收到团长明确的补充材料接收请求时，只通过 agent_teams_send_message 向团长发送一次控制性 ACK",
                "真正重派后只使用引擎新返回的 attempt_id",
                "在 output、发给团长的消息和成员会话答复中使用同一组已选材料",
            ), "discipline_boundary_sentences"),
        )
        for name, fragments, expected_check in cases:
            source = self.root / "policy-source/dsh" / name
            original = source.read_text(encoding="utf-8")
            for fragment in fragments:
                with self.subTest(name=name, fragment=fragment[:30]):
                    self.assertIn(fragment, original)
                    source.write_text(original.replace(fragment, "", 1), encoding="utf-8")
                    dsh_bundle.build(self.root)
                    report = check_dsh.run(self.root)
                    checks = {item["id"]: item["passed"] for item in report["checks"]}
                    self.assertTrue(checks["render_artifact_equality"])
                    self.assertFalse(checks[expected_check])
                    self.assertFalse(report["pass"])
                    source.write_text(original, encoding="utf-8")
        dsh_bundle.build(self.root)
        self.assertTrue(check_dsh.run(self.root)["pass"])

    def test_quota_rule_removal_still_fails_after_rebuild(self):
        for name, fragment in [
            ("lead-rules.md", 'SQL 执行统计摘要与执行计划是两份独立材料，分别占用名额；不得写成一项“摘要与计划”。同一份既有活动会话采样导出可含多列字段，但不能搭配另一份独立报告或计划。名额外不以“仅记缺口”“转交建议”暗列材料名，只说明现有证据无法区分的机制。'),
            ("shared-discipline.md", 'SQL 执行统计摘要与执行计划是两份独立材料，分别占用名额；不得写成一项“摘要与计划”。同一份既有活动会话采样导出可含多列字段，但不能搭配另一份独立报告或计划。名额外不以“仅记缺口”“转交建议”暗列材料名，只说明现有证据无法区分的机制。'),
            ("lead-rules.md", "向用户展示的待验证、建议采集、后续材料清单同样计入本轮 3 项，转述成员请求也计数；不得以“未新增”“仅转述”“额度未动用”绕过。"),
            ("lead-rules.md", "成员合计超过 3 项时只选择最多 3 项展示，其余不在其他段落暗列。一个编号不能捆绑可分别提供的多份材料。"),
            ("shared-discipline.md", "每项只指一份可独立提供的材料，不把多个指标时序、线程栈和基线捆成一项。"),
            ("lead-rules.md", "先把成员回执中的合并项按独立材料拆开计数，再按各任务的可用额度和团长预留筛选"),
            ("lead-rules.md", "成员回执未齐时，向用户只报告进度和数量，不提前列材料名称。"),
            ("lead-rules.md", "零配额派单省略这项要求。"),
            ("lead-rules.md", "不写被舍弃的材料名称或列表，含核对说明、括注和收尾。"),
            ("lead-rules.md", "全队本轮可用名额为 0 时，省略该清单，且在“待验证”、转交建议、局限和收尾中均不得暗列新增材料。"),
            ("lead-rules.md", "零配额派单只要求成员给出候选机制与证据边界。"),
            ("lead-rules.md", "句号后结束该条；不附理由、缺失项或括注。"),
            ("shared-discipline.md", "JDBC 获取连接的等待时长时序和连接借出后的占用时长时序是两项。"),
            ("shared-discipline.md", "当前任务剩余名额为 0 时省略该清单，且在“待验证”、转交建议和局限中均不得暗列新增材料"),
            ("shared-discipline.md", "不要另设“机制差异说明”去回答需要哪些证据。"),
            ("shared-discipline.md", "到句号即止，不附理由、缺失项或括注。"),
            ("shared-discipline.md", "在提交 agent_teams_update_task 的 output、agent_teams_send_message 的 content 或任何会话回复前，逐项检查实际正文。"),
            ("shared-discipline.md", "每条使用“材料名称｜一个采集时窗｜能区分的机制”，只留一个可交付对象。"),
            ("shared-discipline.md", "成员的任务输出、发给团长的消息和成员自己的会话回复，如需列材料，只能列同一组已选项"),
            ("shared-discipline.md", "零配额只写机制，不引用材料清单。"),
            ("shared-discipline.md", "故障时窗的采样与另一个正常时窗的基线分别计数。"),
            ("shared-discipline.md", "条件性追加也占额，未获名额的材料不得在“若异常再获取”“本轮暂不用”等表述里点名。"),
        ]:
            with self.subTest(source=name):
                source = self.root / "policy-source/dsh" / name
                original = source.read_text(encoding="utf-8")
                self.assertIn(fragment, original)
                source.write_text(original.replace(fragment, "", 1), encoding="utf-8")
                dsh_bundle.build(self.root)
                self.assertFalse(check_dsh.run(self.root)["pass"])
                source.write_text(original, encoding="utf-8")

    def test_concurrent_direct_build_edit_is_restored(self):
        dsh_bundle.build(self.root)
        actual = dsh_bundle.os.replace
        raced = [False]
        proof = self.root / "dsh/package.json"
        changed = proof.read_bytes() + b"\n"
        def concurrent_write(src, dst):
            if Path(src) == self.root / "dsh" and not raced[0]:
                raced[0] = True
                proof.write_bytes(changed)
            return actual(src, dst)
        with patch.object(dsh_bundle.os, "replace", side_effect=concurrent_write):
            with self.assertRaises(OSError):
                dsh_bundle.build(self.root)
        # Asserting only an exception can give a false result if some unrelated
        # os.replace failure occurs before the intended injection.
        self.assertTrue(raced[0], "concurrent edit was never injected")
        self.assertEqual(proof.read_bytes(), changed)

    @requires_real_symlink
    def test_31b_alias_root_keeps_rollback_failure_injection_targeted(self):
        # Regression for /var vs /private/var style aliases. Do not weaken
        # input/output symlink rejection: the root is canonicalized by build().
        dsh_bundle.build(self.root)
        alias = self.base / "crm-sre-team-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.assertNotEqual(alias / "dsh", self.root / "dsh")
        self.assertEqual((alias / "dsh").resolve(strict=True),
                         (self.root / "dsh").resolve(strict=True))
        actual = dsh_bundle.os.replace
        raced = [False]
        proof = self.root / "dsh/package.json"
        changed = proof.read_bytes() + b"\n"

        def concurrent_write(src, dst):
            if Path(src) == self.root / "dsh" and not raced[0]:
                raced[0] = True
                proof.write_bytes(changed)
            return actual(src, dst)

        with patch.object(dsh_bundle.os, "replace", side_effect=concurrent_write):
            with self.assertRaises(OSError):
                dsh_bundle.build(alias)
        self.assertTrue(raced[0], "root alias must not bypass the fault injection")
        self.assertEqual(proof.read_bytes(), changed)

    @requires_real_symlink
    def test_32_symlink_in_dsh_output_rejected(self):
        dsh = self.root / "dsh"
        dsh.mkdir(exist_ok=True)
        outside = self.base / "outside"
        outside.mkdir()
        existing = dsh / "build-info.json"
        if existing.exists():
            existing.unlink()
        existing.symlink_to(outside / "x.json")
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        self.assertTrue((dsh / "build-info.json").is_symlink())

    @requires_real_symlink
    def test_33_symlinked_dsh_input_rejected_before_render(self):
        before = tree_hash(self.root / "dsh") if (self.root / "dsh").exists() else {}
        target = self.base / "external-lead-rules.md"
        source = self.root / "policy-source/dsh/lead-rules.md"
        shutil.move(str(source), target)
        source.symlink_to(target)
        with self.assertRaises(ValueError):
            dsh_bundle.render(self.root)
        with self.assertRaises(ValueError):
            dsh_bundle.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh") if (self.root / "dsh").exists() else {}, before)



def test_mac_t04c_t05_receive_end_visibility_static_contract_only():
    """Prompt text regression, not actual Harness 0.1.30 event scheduling."""
    lead = (ROOT / "policy-source/dsh/lead-rules.md").read_text(encoding="utf-8")
    member = (ROOT / "policy-source/dsh/shared-discipline.md").read_text(encoding="utf-8")
    rendered = yaml.safe_load((ROOT / "dsh/cordis.patch.yml").read_text(encoding="utf-8"))
    captain = [lead, rendered[0]["config"]["personaPrefix"],
               rendered[3]["insert"][0]["config"]["plugins"][0]["config"]["prefix"]]
    for text in captain:
        for item in (
            "团长模型决策输入中已经可见",
            "其他等价可信的结束证据均可",
            "通知已生成或入队",
            "后台日志已记录",
            "旧轮次、错任务/attempt",
            "重复通知时一律不重派",
            "原任务保持 failed，后继任务保持 pending",
            "t1 真正 completed 前不得释放 t2",
            "不是可阻止并发竞态的上游原子工具门禁",
            "每个逻辑任务失败后累计至多重派一次",
        ):
            assert item in text, item
    members = rendered[1]["config"]["profiles"]["crm-sre"]["members"]
    assert len(members) == 7
    for text in [member, *(m["executionPrompt"] for m in members)]:
        for item in (
            "ACK 只证实该成员确已接收相关材料",
            "团长在其当前模型决策输入中核对可信宿主/引擎结束证据",
            "通知只在队列或后台日志中不构成团长已消费",
        ):
            assert item in text, item


def test_mac_t06_request_specific_action_review_static_contract_only():
    """Does not assert that either original T06 model response passed."""
    lead = (ROOT / "policy-source/dsh/lead-rules.md").read_text(encoding="utf-8")
    rendered = yaml.safe_load((ROOT / "dsh/cordis.patch.yml").read_text(encoding="utf-8"))
    for text in [lead, rendered[0]["config"]["personaPrefix"],
                 rendered[3]["insert"][0]["config"]["plugins"][0]["config"]["prefix"]]:
        for item in (
            "逐项定位原始请求中真正提到的动作与对象",
            "对每项分别核对目标、版本/范围",
            "多个不同目标不得用一张笼统的卡片代替逐项审查",
            "只写“需审批”“注意风险”或仅有栏目标题",
            "标 UNKNOWN/INCOMPLETE",
            "不得用本条新增细则追溯改变此前验收契约",
            "不输出可复制执行的命令",
        ):
            assert item in text, item


if __name__ == "__main__":
    unittest.main(verbosity=2)
