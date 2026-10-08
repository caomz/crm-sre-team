"""Additional offline regression checks for migrated knowledge documentation."""
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

class KnowledgeDocumentationTests(unittest.TestCase):
    def test_reference_basis_documentation_examples_match_schema(self):
        import re
        import yaml
        common=load("schemas/common.schema.json")
        registry=Registry().with_resources([(common["$id"],Resource.from_contents(common))])
        validator=Draft202012Validator({"$ref":common["$id"]+"#/$defs/reference_basis"},registry=registry)
        doc=(ROOT/"policy-source/team-knowledge/02-discipline.md").read_text(encoding="utf-8")
        blocks=re.findall(r"```yaml\n(.*?)\n```",doc,re.S)
        self.assertEqual(len(blocks),2)
        for block in blocks:
            self.assertEqual(list(validator.iter_errors(yaml.safe_load(block))),[])

    def test_knowledge_generated_from_canonical_source(self):
        source=ROOT/"policy-source/team-knowledge"
        target=ROOT/"skills/stability-director/references/team-knowledge"
        self.assertEqual({p.name for p in source.glob("*.md")},{p.name for p in target.glob("*.md")})
        for p in source.glob("*.md"):
            self.assertEqual(p.read_bytes(),(target/p.name).read_bytes())

    def test_docs11_blocked_definition_matches_docs12(self):
        """V1: docs/11 的 Step 0 判定必须与 docs/12 的关口术语一致——
        CAPABILITY_BLOCKED 只在成员完全无回复时成立；有回复无暗号按
        加载/缓存问题处理，不判 CAPABILITY_BLOCKED。"""
        d11=(ROOT/"docs/11-workbuddy-host-acceptance.md").read_text(encoding="utf-8")
        d12=(ROOT/"docs/12-native-vs-single-comparison.md").read_text(encoding="utf-8")
        # 旧规则（缓存造成的暗号缺失会被误判 BLOCKED）必须彻底消失
        self.assertNotIn("选不中带暗号 C 的成员",d11)
        # 两文档统一使用关口结论术语 CAPABILITY_BLOCKED
        self.assertIn("CAPABILITY_BLOCKED",d11)
        self.assertIn("CAPABILITY_BLOCKED",d12)
        # docs/11 的判定句必须要求"无任何回复"这一真实原因
        verdict=[ln for ln in d11.splitlines() if "判定 CAPABILITY_BLOCKED" in ln]
        self.assertTrue(verdict,"docs/11 缺少 CAPABILITY_BLOCKED 判定句")
        self.assertIn("无任何回复","\n".join(verdict))
