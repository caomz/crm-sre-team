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


class T6CollabTextTests(unittest.TestCase):
    """T6/M13+M16: collaboration protocol text checks on built artifacts,
    plus parameterized mutation negatives (runtime artifacts AND source render)."""

    @classmethod
    def setUpClass(cls):
        cls.roles = json.loads((ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        cls.lead_artifact = (ROOT / "agents/telecom-crm-sre-team-lead.md").read_text(encoding="utf-8")
        cls.member_artifact = (ROOT / "agents/telecom-crm-oracle-dba.md").read_text(encoding="utf-8")

    def test_01_evidence_numbering_rules_present(self):
        for text, label in [(self.lead_artifact, "lead"), (self.member_artifact, "member")]:
            with self.subTest(entry=label):
                self.assertIn("不自行编号", text)
                self.assertIn("映射回原编号", text)
                self.assertIn("不是宿主认证编号", text)
                self.assertIn("成员未给出依据", text)

    def test_02_dispatch_five_fields_present(self):
        self.assertIn("派单模板与证据索引", self.lead_artifact)
        for field in ["任务（一个窄域问题）", "范围（对象、时间窗口与已授权边界）",
                      "材料（统一证据编号", "要求（返回格式与关键未知）", "剩余额度"]:
            self.assertIn(field, self.lead_artifact)
        self.assertIn("不写“参考上文”", self.lead_artifact)
        self.assertIn("8000 字符封顶", self.lead_artifact)

    def test_03_refute_rules_present(self):
        self.assertIn("反证派发（REFUTE）", self.lead_artifact)
        self.assertIn("排名第一、至少引用一条支持编号、无并列对手", self.lead_artifact)
        self.assertIn("冲突照实列出", self.lead_artifact)
        self.assertIn("反证派单（REFUTE）", self.member_artifact)
        self.assertIn("若它是错的，这条证据是否仍自然出现", self.member_artifact)

    def test_04_no_material_re_asking(self):
        self.assertIn("不索取已随派单提供的材料", self.member_artifact)
        self.assertIn("随派单已提供的材料不得重复索取", self.lead_artifact)

    def test_05_d18_legacy_quadrant_names_kept(self):
        for q in ["已确认事实", "高概率候选", "待验证", "已排除"]:
            self.assertIn(q, self.member_artifact)

    def test_06_member_role_skill_blocks_verbatim_equal(self):
        """Pairing check, re-asserted at T6: role-source and skill-source blocks byte equal."""
        for sid, role in sorted(self.roles.items()):
            role_src = (ROOT / "policy-source/prompts/roles" / (role["agent"] + ".md")).read_text(encoding="utf-8")
            skill_src = (ROOT / "policy-source/skills" / (sid + ".md")).read_text(encoding="utf-8")
            labels = (["NATIVE_LEAD", "COMPAT_LEAD"] if sid == "stability-director"
                      else ["NATIVE_MEMBER", "COMPAT_MEMBER"])
            for label in labels:
                with self.subTest(sid=sid, label=label):
                    rb = checker.split_modes(role_src)[0]
                    sb = checker.split_modes(skill_src)[0]
                    a = [p for mode, p in rb if mode == label]
                    b = [p for mode, p in sb if mode == label]
                    self.assertTrue(a and a == b, f"{sid}:{label} blocks differ")

    def test_07_mutation_negatives_parameterized(self):
        """M16: negatives must be rejected on BOTH runtime artifacts (runtime=True)
        and source-rendered full text (runtime=False). Managed-marker mutations
        stay source-render only (artifacts have no MANAGED block by design).
        Block-scoped negatives (native_lead_delegation_contradiction) must be
        injected INSIDE the mode block, matching check_workbuddy's scoping."""
        # Shared-area negative: unscoped managed rule appended after the last block.
        for surface in ("artifact", "render_full"):
            with self.subTest(kind="unscoped_managed_rule", surface=surface):
                if surface == "artifact":
                    base = self.lead_artifact
                    poisoned = base + "\nObserve：只读 evidence_delta"
                    ok = checker.check_prompt(poisoned, True, runtime=True)
                else:
                    base = checker.render_full(ROOT, "stability-director", self.roles["stability-director"])
                    poisoned = base + "\nObserve：只读 evidence_delta"
                    ok = checker.check_prompt(poisoned, True, runtime=False)
                self.assertIn("unscoped_managed_rule:Observe：只读 evidence_delta", ok,
                              "wrong or missing error code on " + surface)
        # Block-scoped negative: delegation contradiction inside NATIVE_LEAD.
        for surface in ("artifact", "render_full"):
            with self.subTest(kind="native_lead_delegation_contradiction", surface=surface):
                if surface == "artifact":
                    base = self.lead_artifact
                    poisoned = base.replace("<!-- MODE:NATIVE_LEAD:END -->",
                                            "禁止调用所有成员\n<!-- MODE:NATIVE_LEAD:END -->")
                    ok = checker.check_prompt(poisoned, True, runtime=True)
                else:
                    base = checker.render_full(ROOT, "stability-director", self.roles["stability-director"])
                    poisoned = base.replace("<!-- MODE:NATIVE_LEAD:END -->",
                                            "禁止调用所有成员\n<!-- MODE:NATIVE_LEAD:END -->")
                    ok = checker.check_prompt(poisoned, True, runtime=False)
                self.assertIn("native_lead_delegation_contradiction", ok,
                              "wrong or missing error code on " + surface)


class MemberConventionTests(unittest.TestCase):
    """PD-3: the shared member material/analysis/return convention block must
    stay verbatim-identical across all 7 member role sources and all 7 member
    skill sources, and must stay out of both lead sources. Static only."""

    CONVENTION_HEADING = "## 成员材料—分析—返回约定（原生与兼容共用）"

    def _extract_convention(self, text: str):
        idx = text.find(self.CONVENTION_HEADING)
        if idx == -1:
            return None
        rest = text[idx:]
        nxt = rest.find("\n## ", len(self.CONVENTION_HEADING))
        return rest if nxt == -1 else rest[:nxt]

    def _member_sources(self):
        roles = json.loads(
            (ROOT / "policy-source/roles-source.json").read_text(encoding="utf-8"))
        for sid, role in sorted(roles.items()):
            if sid == "stability-director":
                continue
            yield sid, role

    def test_01_convention_block_identical_across_member_sources(self):
        blocks = {}
        for sid, role in self._member_sources():
            role_text = (ROOT / "policy-source/prompts/roles" /
                         (role["agent"] + ".md")).read_text(encoding="utf-8")
            skill_text = (ROOT / "policy-source/skills" /
                          (sid + ".md")).read_text(encoding="utf-8")
            role_block = self._extract_convention(role_text)
            skill_block = self._extract_convention(skill_text)
            self.assertIsNotNone(role_block, role["agent"])
            self.assertIsNotNone(skill_block, sid)
            blocks["role:" + role["agent"]] = role_block
            blocks["skill:" + sid] = skill_block
        self.assertEqual(len(blocks), 14)
        unique = set(blocks.values())
        self.assertEqual(len(unique), 1,
                         "14 份成员源的约定段必须逐字相同；差异: "
                         + "; ".join(sorted({b[:60] for b in unique}))[:300])

    def test_02_lead_sources_have_no_convention_block(self):
        for rel in ("policy-source/prompts/roles/telecom-crm-sre-team-lead.md",
                    "policy-source/skills/stability-director.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn(self.CONVENTION_HEADING, text, rel)


if __name__ == "__main__":
    unittest.main()
