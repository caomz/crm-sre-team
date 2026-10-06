"""T5/M15 native collab regression: roster consistency and rendering.

Static only. It does not prove model or host runtime behavior.
"""
from __future__ import annotations
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


checker = module("ck_native_collab", "tools/check_workbuddy.py")
bb = module("bb_native_collab", "tools/build_bundle.py")


class RosterConsistencyTests(unittest.TestCase):
    def test_01_routing_errors_clean_on_repo(self):
        self.assertEqual(checker.routing_errors(ROOT), [])

    def _mutated_root(self, mutate):
        """Copy the real three-way sources into a temp root, apply mutate(dict),
        and return the temp root path."""
        tmp = Path(tempfile.mkdtemp(prefix="routing-test-"))
        (tmp / "policy-source").mkdir()
        shutil.copyfile(ROOT / "policy-source/roles-source.json", tmp / "policy-source/roles-source.json")
        shutil.copyfile(ROOT / ".codebuddy-plugin/plugin.json", tmp / "plugin.json")
        (tmp / ".codebuddy-plugin").mkdir()
        shutil.move(str(tmp / "plugin.json"), str(tmp / ".codebuddy-plugin/plugin.json"))
        routing = json.loads((ROOT / "policy-source/routing-source.json").read_text(encoding="utf-8"))
        mutate(routing)
        (tmp / "policy-source/routing-source.json").write_text(
            json.dumps(routing, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return tmp

    def test_02_missing_member_key_rejected(self):
        def mutate(r):
            r.pop("telecom-crm-oracle-dba")
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_missing_id:telecom-crm-oracle-dba", errors)

    def test_03_unknown_member_key_rejected(self):
        def mutate(r):
            r["telecom-crm-not-a-member"] = {"route_when": ["x"], "do_not_route_when": ["y"],
                                              "expected_output": "z", "aliases": ["q"]}
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_unknown_id:telecom-crm-not-a-member", errors)

    def test_04_alias_conflict_rejected(self):
        def mutate(r):
            r["telecom-crm-linux-infra"]["aliases"].append("oracle")
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_alias_conflict:oracle", errors)

    def test_05_k8s_dual_condition_rejected_when_removed(self):
        def mutate(r):
            r["telecom-crm-k8s-platform"]["route_when"] = ["材料中仅出现 Pod 字样"]
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_k8s_dual_condition_missing", errors)

    def test_06_k8s_alias_missing_rejected(self):
        def mutate(r):
            r["telecom-crm-k8s-platform"]["aliases"] = ["k8s"]
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_k8s_alias_missing", errors)

    def test_07_empty_field_rejected(self):
        def mutate(r):
            r["telecom-crm-oracle-dba"]["expected_output"] = ""
        errors = checker.routing_errors(self._mutated_root(mutate))
        self.assertIn("routing_empty_field:telecom-crm-oracle-dba:expected_output", errors)

    def test_08_k8s_plugin_zh_deviation_tolerated(self):
        """plugin.json zh='K8s辅助专家' vs title='K8s按需辅助专家' is the recorded
        deviation (hash-locked version_only_json); it must NOT fail."""
        self.assertNotIn("plugin_zh_name_mismatch:telecom-crm-k8s-platform",
                         checker.routing_errors(ROOT))


class RosterRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        cls.routing = json.loads((ROOT / "policy-source/routing-source.json").read_text(encoding="utf-8"))
        cls.roster = bb.render_team_roster(cls.roles, cls.routing)

    def test_01_roster_covers_seven_members_with_ids(self):
        for agent, role in sorted(self.roles.items()):
            if agent == "stability-director":
                continue
            with self.subTest(agent=role["agent"]):
                self.assertIn(role["agent"], self.roster)
                self.assertIn(role["title"], self.roster)

    def test_02_roster_k8s_row_carries_dual_condition(self):
        self.assertIn("部署", self.roster)
        self.assertIn("调度", self.roster)

    def test_03_roster_carries_schema_disclaimer(self):
        self.assertIn("工具名与参数以当前宿主提供的 Schema 为准", self.roster)

    def test_04_roster_not_tool_schema(self):
        """Internal routing fields must not masquerade as host tool parameters."""
        for banned in ["subagent_type", "disallowedTools:", "参数名：", "tools:"]:
            self.assertNotIn(banned, self.roster)

    def test_05_lead_agent_artifact_contains_roster(self):
        text = (ROOT / "agents/telecom-crm-sre-team-lead.md").read_text(encoding="utf-8")
        self.assertIn("成员名册（何时派给谁）", text)
        self.assertIn("telecom-crm-crm-business-flow", text)

    def test_06_member_artifacts_do_not_carry_roster(self):
        text = (ROOT / "agents/telecom-crm-oracle-dba.md").read_text(encoding="utf-8")
        self.assertNotIn("成员名册（何时派给谁）", text)

    def test_07_no_unrendered_roster_placeholder_in_artifacts(self):
        for rel in ["agents/telecom-crm-sre-team-lead.md", "skills/stability-director/SKILL.md",
                    "agents/telecom-crm-oracle-dba.md"]:
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("{{TEAM_ROSTER}}", text, rel)


if __name__ == "__main__":
    unittest.main()
