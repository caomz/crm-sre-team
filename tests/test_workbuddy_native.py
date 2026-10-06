"""Static mode/metadata regression with mutation negatives; no model or host calls."""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]

def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

checker = module("workbuddy_checker_under_test", "tools/check_workbuddy.py")


def _can_symlink() -> bool:
    """Capability probe: real filesystem symlinks (not ZIP metadata)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); t = p / "t"; t.write_bytes(b"x"); link = p / "l"
            link.symlink_to(t)
            return link.is_symlink()
    except OSError:
        return False


class WorkBuddyNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        cls.policy = json.loads((ROOT / "policies/runtime-contract.json").read_text(encoding="utf-8"))
        # Slice 1: runtime artifacts have MANAGED stripped; tests mutate the
        # managed block, so they use the source-rendered full text (with MANAGED).
        cls.lead = checker.render_full(ROOT, "stability-director", cls.roles["stability-director"])
        cls.member = checker.render_full(ROOT, "oracle-dba", cls.roles["oracle-dba"])

    def test_01_entire_mode_bundle_is_consistent(self):
        self.assertEqual(checker.run(ROOT)["errors"], [])

    def test_02_unscoped_routing_ban_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead + "\n只提出 routing_proposals，不直接调用任何工具。", True))

    def test_03_unscoped_delta_only_rule_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead + "\nObserve：只读 evidence_delta", True))

    def test_04_unscoped_member_stage_block_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.member + "\n其他阶段返回 blocked", False))

    def test_05_native_dispatch_contradiction_is_rejected(self):
        text = self.lead.replace("<!-- MODE:NATIVE_LEAD:END -->", "禁止调用所有成员\n<!-- MODE:NATIVE_LEAD:END -->")
        self.assertTrue(checker.check_prompt(text, True))

    def test_06_native_member_harness_requirement_is_rejected(self):
        text = self.member.replace("<!-- MODE:NATIVE_MEMBER:END -->", "必须提供 harness_context\n<!-- MODE:NATIVE_MEMBER:END -->")
        self.assertTrue(checker.check_prompt(text, False))

    def test_07_unclosed_scope_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead.replace("<!-- MODE:MANAGED_HARNESS:END -->", "", 1), True))

    def test_08_nested_scope_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead.replace("<!-- MODE:NATIVE_LEAD:BEGIN -->", "<!-- MODE:NATIVE_LEAD:BEGIN -->\n<!-- MODE:NATIVE_MEMBER:BEGIN -->"), True))

    def test_09_missing_selector_is_rejected(self):
        self.assertTrue(checker.check_prompt(self.lead.replace("## 运行模式选择：真实能力先于文本标签", ""), True))

    def test_10_downgrade_bypass_is_rejected(self):
        p = deepcopy(self.policy); p["native_mode"]["verification_failure_fallback"] = True
        self.assertIn("native_downgrade_bypass", checker.policy_errors(p))

    def test_11_no_fake_harness_implementation(self):
        p = deepcopy(self.policy); p["implementation_status"] = "IMPLEMENTED"
        self.assertIn("managed_implementation_overclaim", checker.policy_errors(p))

    def test_12_member_recursive_dispatch_is_rejected(self):
        p = deepcopy(self.policy); p["native_mode"]["member_may_dispatch"] = True
        self.assertIn("recursive_delegation", checker.policy_errors(p))

    def test_13_request_budget_increase_is_rejected(self):
        p = deepcopy(self.policy); p["native_mode"]["max_user_atomic_requests_per_round"] = 4
        self.assertIn("budget_changed", checker.policy_errors(p))

    def test_14_global_managed_requirement_is_rejected(self):
        p = deepcopy(self.policy); p["host_adapter_required"] = True
        self.assertIn("unscoped_managed_policy", checker.policy_errors(p))

    def test_15_production_tool_escalation_is_rejected(self):
        p = deepcopy(self.policy); p["production_tools"] = ["SYNTHETIC_TOOL"]
        self.assertIn("production_boundary_changed", checker.policy_errors(p))

    def fixture_settings(self, root):
        (root / ".codebuddy-plugin").mkdir(); (root / "agents").mkdir()
        for name in ["settings.json", ".codebuddy-plugin/plugin.json", "agents/telecom-crm-sre-team-lead.md"]:
            shutil.copyfile(ROOT / name, root / name)

    def test_16_additional_user_settings_are_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.fixture_settings(root)
            config = {"agent":"telecom-crm-sre-team-lead", "language":"zh-CN", "permissions":{"deny":["synthetic"]}}
            (root / "settings.json").write_text(json.dumps(config), encoding="utf-8")
            self.assertEqual(checker.settings_errors(root), [])
            self.assertEqual(json.loads((root / "settings.json").read_text(encoding="utf-8")), config)

    def test_17_settings_missing_invalid_nonobject_wrong_lead_rejected(self):
        for value in [None, "{broken", "[]", '{"agent":"wrong"}']:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                root = Path(d); self.fixture_settings(root)
                p = root / "settings.json"
                if value is None: p.unlink()
                else: p.write_text(value, encoding="utf-8")
                self.assertTrue(checker.settings_errors(root))

    def test_18_settings_symlink_rejected(self):
        if not _can_symlink():
            self.skipTest("SKIPPED_CAPABILITY: real filesystem symlinks unavailable on this host")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.fixture_settings(root)
            p = root / "settings.json"; p.rename(root / "real-settings.json"); p.symlink_to(root / "real-settings.json")
            self.assertIn("settings_symlink", checker.settings_errors(root))

    def test_19_lead_path_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); self.fixture_settings(root)
            (root / "agents/telecom-crm-sre-team-lead.md").unlink()
            self.assertIn("lead_agent_missing_or_symlink", checker.settings_errors(root))

    def test_20_all_seven_members_and_skill_pairs(self):
        self.assertEqual(len(self.roles), 8)
        for sid, role in self.roles.items():
            for rel in [f"agents/{role['agent']}.md", f"skills/{sid}/SKILL.md"]:
                with self.subTest(path=rel):
                    # Slice 1: built artifacts carry runtime=True (MANAGED stripped).
                    self.assertEqual(checker.check_prompt((ROOT / rel).read_text(encoding="utf-8"), sid == "stability-director", runtime=True), [])

    def test_21_no_unsupported_tools_field(self):
        for role in self.roles.values():
            t = (ROOT / "agents" / (role["agent"] + ".md")).read_text(encoding="utf-8")
            self.assertNotIn("tools", yaml.safe_load(t.split("---", 2)[1]))

    def test_22_no_schema_mode_extension(self):
        for p in sorted((ROOT / "schemas").glob("*.json")):
            obj = json.loads(p.read_text(encoding="utf-8"))
            self.assertNotIn("runtime_mode", obj.get("properties", {}))
        for name in ["lead-result", "member-result"]:
            obj = json.loads((ROOT / "schemas" / (name + ".schema.json")).read_text(encoding="utf-8"))
            self.assertIs(obj["additionalProperties"], False)

    def test_23_oracle_no_evidence_no_numbers_boundary(self):
        for rel in ["agents/telecom-crm-oracle-dba.md", "skills/oracle-dba/SKILL.md"]:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("包括看似保守的数值", text)
            self.assertIn("不是反证", text)

    def test_24_no_private_knowledge_autoload(self):
        doc = (ROOT / "policy-source/team-knowledge/00-context-summary.md").read_text(encoding="utf-8")
        self.assertIn("默认未配置", doc)
        self.assertIn("不携带个人工号", doc)

    def test_25_historical_schema_and_tests_hashes_unchanged(self):
        import hashlib
        b = json.loads((ROOT / "policy-source/thinking-tools/baseline-contract.json").read_text(encoding="utf-8"))
        for rel, expected in b["immutable_files"].items():
            if rel.startswith(("schemas/", "tests/")):
                self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), expected)

    def test_26_old_patch_script_not_shipped(self):
        self.assertFalse((ROOT / "apply_workbuddy_native_fix.py").exists())

if __name__ == "__main__": unittest.main(verbosity=2)
