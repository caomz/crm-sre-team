"""Delivery checklist must be complete and remain a specification, not claims."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = ["FDE 差距表、集成登记与放弃清单", "价值度量规格", "现场自观察与反馈模板", "四层知识与维护信息",
            "知识沉淀四步", "上线六项清单", "五类风险与两列责任", "控制权清单", "自主等级与放权规则",
            "失败模式预警与止损", "版本纪律", "rc1–rc4 五步复盘与项目沉淀清单"]


class FdeDeliveryTests(unittest.TestCase):
    def test_twelve_fixed_sections_evidence_and_no_placeholders(self):
        text = (ROOT / "docs/14-fde-delivery.md").read_text(encoding="utf-8")
        for n, title in enumerate(HEADINGS, 1):
            heading = f"## {n}. {title}"
            with self.subTest(section=n):
                self.assertEqual(text.count(heading), 1)
                section = text.split(heading, 1)[1].split(f"\n## {n + 1}.", 1)[0]
                self.assertTrue(any(s in section for s in ("docs/", "schemas/", "tools/", "policy-source/", "templates/", "VERSION", "无证据，待用户")))
        for word in ("TO" + "DO", "TB" + "D", "待" + "补", "/Users/", "/Volumes/", "FAKE-KB-SECRET-"):
            self.assertNotIn(word, text)
        self.assertIn("本轮不采集真实数据", text)
        self.assertIn("停止团队模式投入", text)
        self.assertIn("schemas/feedback.schema.json", text)
        self.assertIn("第二次交付", text)

    def test_doc_and_tests_declared_and_readme_indexed(self):
        files = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))["files"]
        self.assertEqual(files, sorted(set(files)))
        self.assertIn("docs/14-fde-delivery.md", files)
        self.assertIn("tests/test_fde_delivery.py", files)
        self.assertIn("docs/14-fde-delivery.md", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
