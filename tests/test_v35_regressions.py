"""Safety regressions found while reviewing main through v3.4.1. No host claims."""
import json
import hashlib
import re
import ast
from pathlib import Path
import sys
import subprocess
import tempfile
import zipfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import check_workbuddy
import experimental_build
import make_probe_build
import make_comparison_build
import build_release
import release_rules


class V35Regressions(unittest.TestCase):
    def small_root(self, base):
        root = base / "repo"
        root.mkdir()
        names = ["VERSION", "settings.json", ".codebuddy-plugin/plugin.json",
                 "release-manifest.json", "prompt-bundles.lock"]
        for rel in names:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")
        (root / "release-manifest.json").write_text(json.dumps({
            "schema_version": 1, "files": sorted(names)}), encoding="utf-8")
        return root

    def test_exact_manifest_excludes_unknown_files_and_hashes_actual_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = self.small_root(base)
            # Unknown data beside a declared input must not enter an experiment.
            (root / ".codebuddy-plugin/private.txt").write_text("SYNTHETIC-UNKNOWN", encoding="utf-8")
            out, files, digest = experimental_build.prepare_output(root, base / "out")
            experimental_build.copy_inputs(root, files, out)
            self.assertFalse((out / ".codebuddy-plugin/private.txt").exists())
            self.assertEqual(len(list(p for p in out.rglob("*") if p.is_file())), 5)
            (root / "VERSION").write_text("changed", encoding="utf-8")
            _, _, changed = experimental_build.prepare_output(root, base / "other")
            self.assertNotEqual(digest, changed)

    def test_existing_output_never_overwritten_by_either_api(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "existing"
            out.mkdir()
            marker = out / "keep.txt"
            marker.write_text("KEEP", encoding="utf-8")
            for build in (lambda: make_probe_build.build_probe(ROOT, out, {}, {}),
                          lambda: make_comparison_build.build_comparison(ROOT, out)):
                with self.subTest(build=build), self.assertRaises(ValueError):
                    build()
                self.assertEqual(marker.read_text(encoding="utf-8"), "KEEP")
                self.assertEqual(list(out.iterdir()), [marker])

    def test_source_overlap_rejected_before_creating_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.small_root(Path(td))
            for output in (root, root.parent, root / "skills/probe", root / "new"):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    experimental_build.prepare_output(root, output)
            self.assertFalse((root / "skills").exists())
            self.assertFalse((root / "new").exists())
            allowed, _, _ = experimental_build.prepare_output(root, root / "reports/probe")
            self.assertTrue(allowed.is_dir())

    def test_symlink_output_parent_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = self.small_root(base)
            target = base / "target"
            target.mkdir()
            link = base / "link"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError:
                self.skipTest("Symlink creation unavailable")
            with self.assertRaises(ValueError):
                experimental_build.prepare_output(root, link / "out")
            self.assertEqual(list(target.iterdir()), [])

    def test_missing_manifest_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = self.small_root(base)
            p = root / "release-manifest.json"
            v = json.loads(p.read_text(encoding="utf-8"))
            v["files"] = sorted(v["files"] + ["missing.txt"])
            p.write_text(json.dumps(v), encoding="utf-8")
            with self.assertRaises(ValueError):
                experimental_build.prepare_output(root, base / "out")
            self.assertFalse((base / "out").exists())

    def test_junction_guards_for_experimental_and_release_paths(self):
        # Simulate Windows junction metadata here; real junction coverage runs on Windows.
        class Python311ReparsePath:
            def is_symlink(self):
                return False
            def lstat(self):
                return SimpleNamespace(st_file_attributes=1024)
        self.assertTrue(release_rules.is_link(Python311ReparsePath()))
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root = self.small_root(base)
            junction = base / "junction"
            junction.mkdir()
            with patch.object(Path, "is_junction", lambda p: p == junction, create=True):
                with self.assertRaises(ValueError):
                    experimental_build.prepare_output(root, junction / "out")
                with self.assertRaises(ValueError):
                    build_release.build_release(root, junction / "out.zip")
            declared_parent = root / ".codebuddy-plugin"
            with patch.object(Path, "is_junction", lambda p: p == declared_parent, create=True):
                with self.assertRaises(ValueError):
                    release_rules.release_files(root)
            self.assertEqual(list(junction.iterdir()), [])

    def test_invalid_probe_overrides_have_no_output(self):
        invalid = [({"oracle-dba": 0}, {}), ({"unknown": 1}, {}),
                   ({"stability-director": 1}, {}), ({}, {"oracle-dba": []}),
                   ({}, {"oracle-dba": ["WebFetch\nother: true"]}),
                   ({"oracle-dba": 1}, {"oracle-dba": ["WebFetch"]})]
        with tempfile.TemporaryDirectory() as td:
            for i, (turns, disallow) in enumerate(invalid):
                out = Path(td) / str(i)
                with self.subTest(overrides=i), self.assertRaises(ValueError):
                    make_probe_build.build_probe(ROOT, out, turns, disallow)
                self.assertFalse(out.exists())

    def test_reference_bans_rejected_but_scoped_managed_ban_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.small_root(Path(td))
            rel = "policy-source/references/example.md"
            p = root / rel
            p.parent.mkdir(parents=True)
            manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
            manifest["files"] = sorted(manifest["files"] + [rel])
            (root / "release-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            policy = root / "policies/thinking-tools.json"
            policy.parent.mkdir()
            policy.write_text("{}", encoding="utf-8")
            for ban in ("所有新增生产采集或动作仅给人工评审卡", "事故模型不自动联网"):
                p.write_text(ban, encoding="utf-8")
                self.assertTrue(check_workbuddy.reference_errors(root))
            p.write_text("<!-- MODE:MANAGED_HARNESS:BEGIN -->\n不输出生产命令\n"
                         "<!-- MODE:MANAGED_HARNESS:END -->", encoding="utf-8")
            self.assertEqual(check_workbuddy.reference_errors(root), [])

    def test_current_reference_contracts_and_all_policy_versions(self):
        self.assertEqual(check_workbuddy.reference_errors(ROOT), [])
        source_index = (ROOT / "policy-source/references/source-index.md").read_text(encoding="utf-8")
        self.assertIn("以根 VERSION 为唯一版本源", source_index)
        self.assertNotIn("同为 2.5.0", source_index)
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        for path in (ROOT / "policies").glob("*.json"):
            with self.subTest(policy=path.name):
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], version)

    def test_synthetic_gate_inputs_have_no_gold_in_input_and_keep_safety(self):
        data = json.loads((ROOT / "policy-source/acceptance/oncall-cases.json").read_text(encoding="utf-8"))
        self.assertEqual(data["execution_status"], "NOT_RUN_IN_TARGET_HOST")
        self.assertTrue(data["synthetic_only"])
        self.assertEqual([c["id"] for c in data["cases"]], ["C1", "C2", "C3", "T02"])
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["input"].startswith("先加载 stability-director 技能，再分析下面的材料\n"))
                for marker in ("不读、不列、不搜文件", "不读取环境变量", "不写文件", "不联网"):
                    self.assertIn(marker, case["input"])
                self.assertNotIn("gold", case["input"])
                self.assertRegex(case['gold_sha256'], r'^[0-9a-f]{64}$')

    def test_release_manifest_rejects_private_scoring_fields(self):
        fields = ['go' + 'ld', 'critical_' + 'truths', 'allowed_' + 'uncertainty',
                  'forbidden_' + 'overclaims', 'expected_member_' + 'set',
                  'expected_next_discriminating_' + 'checks', 'routing_' + 'deviation',
                  'calibration_' + 'anchors', 'quality_6_' + 'example', 'quality_0_' + 'example']
        pattern = re.compile(r'["\'](?:' + '|'.join(fields) + r')["\']\s*:')
        manifest = json.loads((ROOT / 'release-manifest.json').read_text(encoding='utf-8'))
        commitments = json.loads((ROOT / 'policy-source/acceptance/oncall-cases.json').read_text(encoding='utf-8'))['private_content_sha256']
        for rel in manifest['files']:
            raw = (ROOT / rel).read_bytes()
            payloads = [raw]
            if rel.endswith('.zip'):
                with zipfile.ZipFile(ROOT / rel) as archive:
                    payloads += [archive.read(n) for n in archive.namelist()]
            for payload in payloads:
                self.assertIsNone(pattern.search(payload.decode('utf-8', errors='replace')), rel)
                text = payload.decode('utf-8', errors='replace')
                candidates = text.splitlines()
                for match in re.finditer(r'"(?:[^"\\]|\\.)*"', text):
                    try: candidates.append(json.loads(match.group()))
                    except (ValueError, TypeError): pass
                for candidate in candidates:
                    self.assertNotIn(hashlib.sha256(candidate.encode('utf-8')).hexdigest(), commitments, rel)

        for field in fields:
            self.assertIsNotNone(pattern.search(json.dumps({field: ['synthetic']})))

    def test_external_scoring_commitments_and_content_boundary(self):
        data = json.loads((ROOT / 'policy-source/acceptance/oncall-cases.json').read_text(encoding='utf-8'))
        self.assertEqual(data['commitment_algorithm'], 'SHA256')
        commitments = {c['id'] + '.json': c['gold_sha256'] for c in data['cases']}
        commitments.update({'scoring-protocol.md': data['scoring_protocol_sha256'],
                            'routing-assertions.txt': data['routing_assertions_sha256']})
        for digest in commitments.values():
            self.assertRegex(digest, r'^[0-9a-f]{64}$')
        private = ROOT.parent / 'crm-v35-handoff/gate-gold'
        if not private.exists():
            self.skipTest('Executor scoring directory absent; commitment format and release field boundary checked independently')
        sums = dict(line.split('  ', 1)[::-1] for line in (private / 'SHA256SUMS').read_text(encoding='utf-8').splitlines())
        self.assertEqual(sums, commitments)
        snippets = []
        def collect(value):
            if isinstance(value, str) and len(value) >= 12 and not value.startswith('telecom-crm-'):
                snippets.append(value)
            elif isinstance(value, dict):
                for child in value.values(): collect(child)
            elif isinstance(value, list):
                for child in value: collect(child)
        for name, digest in commitments.items():
            raw = (private / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest, name)
            if name.endswith('.json'):
                value = json.loads(raw)
                self.assertTrue(value['critical_' + 'truths'])
                self.assertLessEqual(len(value['expected_next_discriminating_' + 'checks']), 3)
                self.assertEqual(raw, (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8'))
                collect(value)
        protocol = (private / 'scoring-protocol.md').read_text(encoding='utf-8')
        decision = protocol.split('## 五、', 1)[1].split('## 六、', 1)[0]
        # Retain the earlier routing regression assertions in the executor package.
        tree = ast.parse((private / 'routing-assertions.txt').read_text(encoding='utf-8').strip().replace('\n        ', '\n'))
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                needle = ast.literal_eval(node.value.args[0])
                self.assertIn(needle, decision)
        manifest = json.loads((ROOT / 'release-manifest.json').read_text(encoding='utf-8'))
        for rel in manifest['files']:
            raw = (ROOT / rel).read_bytes()
            payloads = [raw]
            if rel.endswith('.zip'):
                with zipfile.ZipFile(ROOT / rel) as archive:
                    payloads += [archive.read(n) for n in archive.namelist()]
            for payload in payloads:
                text = payload.decode('utf-8', errors='replace')
                for snippet in snippets:
                    self.assertNotIn(snippet, text, rel)

    def test_clean_release_first_validation_and_wrong_doc_counts_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive = base / "release.zip"
            build_release.build_release(ROOT, archive)
            with zipfile.ZipFile(archive) as z:
                z.extractall(base / "unpack")
            root = base / "unpack/crm-sre-team"
            self.assertFalse((root / "tests/static-checks.json").exists())
            def validate():
                proc = subprocess.run([sys.executable, str(root / "tools/validate_bundle.py")],
                                      capture_output=True, text=True, encoding="utf-8", timeout=120)
                return proc, json.loads(proc.stdout)
            proc, report = validate()
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(report["errors"], [])
            p = root / "VALIDATION.md"
            text = p.read_text(encoding="utf-8")
            expected = f"静态校验 {report['checks_passed']}/{report['checks_total']}"
            self.assertIn(expected, text)
            p.write_text(text.replace(expected, "静态校验 1/1", 1), encoding="utf-8")
            # Rebuild integrity locks so a documentation regression cannot hide behind stale locks.
            subprocess.run([sys.executable, str(root / "tools/build_bundle.py")],
                           capture_output=True, check=True, timeout=120)
            proc, report = validate()
            self.assertNotEqual(proc.returncode, 0)
            self.assertTrue(any(e.startswith("static_regression:test_knowledge_docs") for e in report["errors"]))

    def test_gate_routing_conditions_and_failed_prerequisites_are_explicit(self):
        d12 = (ROOT / "docs/12-native-vs-single-comparison.md").read_text(encoding="utf-8")
        self.assertIn('scoring-protocol.md', d12)
        self.assertIn("该 N/S 配对不成立", d12.split("## 六、", 1)[1])
        d11 = (ROOT / "docs/11-workbuddy-host-acceptance.md").read_text(encoding="utf-8")
        self.assertIn("WB07 或 WB09H 未 PASS（包括 FAIL/BLOCKED/NOT_RUN", d11)
        self.assertIn("只出现 D 模式", d11)


if __name__ == "__main__":
    unittest.main()
