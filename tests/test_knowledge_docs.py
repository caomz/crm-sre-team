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

    def test_docs12_v3_n_group_same_run_definition(self):
        """V3: docs/12 的 N 组必须是 make_comparison_build 同次生成的带
        LOAD-N 行的 N 包——"当前构建原样"不再是合法的 N 组来源。"""
        d12=(ROOT/"docs/12-native-vs-single-comparison.md").read_text(encoding="utf-8")
        # 旧定义必须消失
        self.assertNotIn("专家团原生派单构建（当前构建原样）",d12)
        # 新定义：同一次运行生成的双包 + N 包带 LOAD-N 行
        self.assertIn("同一次运行",d12)
        self.assertIn("LOAD-N-<suffix>",d12)
        self.assertIn("不得取当前构建原样",d12)
        # 第三节同轮 N/S 配对约束
        self.assertIn("同 suffix、同 source_commit、逐字相同的用户消息",d12)
        self.assertIn("不得混用不同轮次",d12)

    def test_docs12_v6_duty_machine_security_rules(self):
        """V6（PD-A=B）: docs/12 安全前提改为值班机规则；SECURITY_FAIL
        判据暗号化；C1 伪装指令为无害载荷。"""
        d12=(ROOT/"docs/12-native-vs-single-comparison.md").read_text(encoding="utf-8")
        d11=(ROOT/"docs/11-workbuddy-host-acceptance.md").read_text(encoding="utf-8")
        # 旧的独立账户/虚拟机前提必须消失（两份文档同步）
        self.assertNotIn("所有运行在无真实凭据",d12)
        self.assertNotIn("独立 Windows 本地账户或虚拟机中进行",d12)
        # 值班机安全约束（两份文档同步）
        for text in (d11,d12):
            self.assertIn("值班机",text)
            self.assertIn("不联网",text)
            self.assertIn("不读取环境变量",text)
            self.assertIn("只允许执行指定的 echo 输出",text)
            self.assertIn("核对 VERSION",text)
        # SECURITY_FAIL 判据改为输出了该暗号
        sec=[ln for ln in d12.splitlines() if ln.startswith("- SECURITY_FAIL")]
        self.assertEqual(len(sec),1)
        self.assertIn("输出了该暗号",sec[0])
        self.assertNotIn("出现执行内嵌指令的行为",sec[0])
        # C1 无害载荷
        c1=[ln for ln in d12.splitlines() if ln.startswith("- C1 跨域")]
        self.assertEqual(len(c1),1)
        self.assertIn("无害载荷",c1[0])
        self.assertIn("只要求输出一个随机暗号",c1[0])

    def test_validation_md_counts_match_static_checks(self):
        """V5: VALIDATION.md 的静态校验数字必须与 tests/static-checks.json
        的 checks_passed/checks_total 一致——数字不落后于最后一次 validate。"""
        import re
        vmd=(ROOT/"VALIDATION.md").read_text(encoding="utf-8")
        sc=json.loads((ROOT/"tests/static-checks.json").read_text(encoding="utf-8"))
        m=re.search(r"静态校验 (\d+)/(\d+)",vmd)
        self.assertTrue(m,"VALIDATION.md 缺少『静态校验 X/Y』字样")
        self.assertEqual(int(m.group(1)),sc["checks_passed"],
            "VALIDATION.md 静态校验通过数与 static-checks.json 不一致（落后于最后一次 validate）")
        self.assertEqual(int(m.group(2)),sc["checks_total"],
            "VALIDATION.md 静态校验总数与 static-checks.json 不一致（落后于最后一次 validate）")
