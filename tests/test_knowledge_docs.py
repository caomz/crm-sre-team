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
