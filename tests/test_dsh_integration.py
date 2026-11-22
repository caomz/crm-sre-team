"""DSH default-delivery integration: manifest target selection, default build
isolation, total lock freshness, DSH-subset ZIP identity, frozen historical
version identity and the explicit legacy path. Synthetic data only; offline."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import release_rules  # noqa: E402
import build_release  # noqa: E402
import validate_release  # noqa: E402
import release  # noqa: E402

spec = importlib.util.spec_from_file_location("integration_builder", ROOT / "tools/build_bundle.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

DSH_SUBSET = [
    "PROJECT.md",
    "README.md",
    "docs/17-dsh-agent-teams.md",
    "dsh/build-info.json",
    "dsh/cordis.patch.yml",
    "dsh/package.json",
    "policies/runtime-contract.json",
]
ROOT_VERSION = "2.8.0-rc10"
DSH_VERSION = "2.8.0-dsh.1"
WB_DIRS = ("agents", "skills", "templates", "manual-mode", "individual-packages",
           "avatars", ".codebuddy-plugin")


def _load(rel, name):
    loader_spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


def tree_hash(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"), key=lambda q: q.as_posix())
            if p.is_file() and "__pycache__" not in p.parts}


def make_full_fixture(base: Path) -> Path:
    """Copy exactly the manifest-declared files into a disposable root."""
    root = base / "crm-sre-team"
    root.mkdir(parents=True)
    for name in release_rules.manifest_names(ROOT):
        source = ROOT / name
        if not source.is_file():
            continue
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


def make_legacy_fixture(base: Path, version="2.6.1") -> Path:
    """A historical-style project: manifest without any target declaration."""
    root = base / "legacy-project"
    root.mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "settings.json").write_text("{}", encoding="utf-8")
    (root / ".codebuddy-plugin").mkdir()
    (root / ".codebuddy-plugin/plugin.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    (root / "README.md").write_text("# legacy fixture\n", encoding="utf-8")
    (root / "prompt-bundles.lock").write_text(json.dumps({"version": version, "files": {}}), encoding="utf-8")
    names = sorted(["VERSION", "settings.json", ".codebuddy-plugin/plugin.json",
                    "release-manifest.json", "prompt-bundles.lock", "README.md"])
    (root / "release-manifest.json").write_text(
        json.dumps({"schema_version": 1, "scope": "test", "files": names}), encoding="utf-8")
    return root


def manifest_mutated(base: Path, mutate) -> Path:
    root = make_legacy_fixture(base)
    path = root / "release-manifest.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    return root


class ManifestTargetTests(unittest.TestCase):
    def test_01_active_manifest_defaults_to_dsh_with_exact_sorted_subset(self):
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("default_target"), "dsh")
        self.assertEqual(manifest["targets"]["dsh"]["files"], DSH_SUBSET)
        self.assertEqual(release_rules.target_name(ROOT), "dsh")
        self.assertEqual(release_rules.target_name(ROOT, "workbuddy"), "workbuddy")
        self.assertEqual(release_rules.target_name(ROOT, "dsh"), "dsh")
        self.assertEqual(release_rules.target_files(ROOT), DSH_SUBSET)
        self.assertEqual(release_rules.target_files(ROOT), sorted(set(release_rules.target_files(ROOT))))

    def test_02_historical_manifest_without_targets_falls_back_to_workbuddy(self):
        with tempfile.TemporaryDirectory() as td:
            root = make_legacy_fixture(Path(td).resolve(strict=True))
            self.assertEqual(release_rules.target_name(root), "workbuddy")
            self.assertEqual(release_rules.target_files(root), release_rules.manifest_names(root))

    def test_03_unknown_explicit_target_rejected(self):
        with self.assertRaises(ValueError):
            release_rules.target_name(ROOT, "experimental")

    def test_04_invalid_target_declarations_rejected(self):
        cases = {
            "unsorted_subset": lambda v: v.update(targets={"dsh": {"files": [
                "README.md", "PROJECT.md"]}}),
            "subset_escaping_total": lambda v: v.update(targets={"dsh": {"files": [
                "README.md", "undeclared/secret.txt"]}}),
            "unknown_default": lambda v: v.update(default_target="experimental",
                                                   targets={"dsh": {"files": ["README.md"]}}),
            "duplicate_subset": lambda v: v.update(targets={"dsh": {"files": [
                "README.md", "README.md"]}}),
        }
        for label, mutate in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as td:
                root = manifest_mutated(Path(td).resolve(strict=True), mutate)
                with self.assertRaises(ValueError):
                    release_rules.manifest_names(root)
                with self.assertRaises(ValueError):
                    release_rules.target_name(root)


class DefaultBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = make_full_fixture(self.base)

    def frozen_hash(self) -> dict:
        frozen = {name: tree_hash(self.root / name) for name in WB_DIRS if (self.root / name).exists()}
        for rel in ("VERSION", "settings.json"):
            frozen[rel] = hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
        return frozen

    def test_10_default_build_updates_dsh_and_lock_and_leaves_wb_bytes_alone(self):
        before = self.frozen_hash()
        result = builder.build(self.root)
        self.assertEqual(result["target"], "dsh")
        self.assertEqual(result["target_version"], DSH_VERSION)
        self.assertEqual(self.frozen_hash(), before)
        self.assertEqual(sorted(p.name for p in (self.root / "dsh").iterdir()),
                         ["build-info.json", "cordis.patch.yml", "package.json"])
        lock = json.loads((self.root / "prompt-bundles.lock").read_text(encoding="utf-8"))
        self.assertEqual(lock["version"], ROOT_VERSION)
        self.assertEqual(lock["target"], "dsh")
        self.assertEqual(lock["target_version"], DSH_VERSION)
        expected = {p.relative_to(self.root).as_posix() for p in builder.lock_files(self.root)}
        self.assertEqual(set(lock["files"]), expected)
        self.assertTrue(all(
            hashlib.sha256((self.root / name).read_bytes()).hexdigest() == digest
            for name, digest in lock["files"].items()))

    def test_11_default_build_twice_identical(self):
        builder.build(self.root)
        first = {**tree_hash(self.root / "dsh"),
                 "prompt-bundles.lock": hashlib.sha256((self.root / "prompt-bundles.lock").read_bytes()).hexdigest()}
        builder.build(self.root)
        second = {**tree_hash(self.root / "dsh"),
                  "prompt-bundles.lock": hashlib.sha256((self.root / "prompt-bundles.lock").read_bytes()).hexdigest()}
        self.assertEqual(first, second)

    def test_12_missing_generated_outputs_valid_before_first_build(self):
        shutil.rmtree(self.root / "dsh")
        result = builder.build(self.root)
        self.assertEqual(result["target"], "dsh")
        self.assertTrue((self.root / "dsh/package.json").is_file())

    def test_13_missing_declared_source_fails(self):
        (self.root / "docs/07-reproducible-validation.md").unlink()
        with self.assertRaises(ValueError):
            builder.build(self.root)

    def test_14_unknown_file_in_dsh_rejected_and_preserved(self):
        dsh = self.root / "dsh"
        dsh.mkdir(exist_ok=True)
        (dsh / "user-notes.md").write_text("SYNTHETIC_USER_DATA", encoding="utf-8")
        before = tree_hash(dsh)
        with self.assertRaises(ValueError):
            builder.build(self.root)
        self.assertEqual(tree_hash(dsh), before)
        self.assertTrue((dsh / "user-notes.md").exists())

    def test_15_lock_write_failure_restores_previous_dsh(self):
        builder.build(self.root)
        dsh_before = tree_hash(self.root / "dsh")
        lock_before = (self.root / "prompt-bundles.lock").read_bytes()
        original = builder.os.replace
        failed = [False]
        def fail_lock(src, dst):
            if Path(dst) == self.root / "prompt-bundles.lock" and not failed[0]:
                failed[0] = True
                raise OSError("synthetic lock commit failure")
            return original(src, dst)
        with patch.object(builder.os, "replace", side_effect=fail_lock):
            with self.assertRaises(OSError):
                builder.build(self.root)
        self.assertTrue(failed[0], "expected lock-write fault was never injected")
        self.assertEqual(tree_hash(self.root / "dsh"), dsh_before)
        self.assertEqual((self.root / "prompt-bundles.lock").read_bytes(), lock_before)
        builder.build(self.root)
        self.assertEqual(tree_hash(self.root / "dsh"), dsh_before)

    def test_15b_lock_rollback_fault_survives_canonical_root_alias(self):
        # A symlink alias of the fixture root must not change the target of
        # failure injection after build() resolves the root.
        alias = self.base / "fixture-alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink capability unavailable: {exc}")
        builder.build(self.root)
        previous = tree_hash(self.root / "dsh")
        lock_before = (self.root / "prompt-bundles.lock").read_bytes()
        original_replace = builder.os.replace
        failed = [False]

        def fail_lock(src, dst):
            if Path(dst) == self.root / "prompt-bundles.lock" and not failed[0]:
                failed[0] = True
                raise OSError("synthetic lock commit failure through alias")
            return original_replace(src, dst)

        with patch.object(builder.os, "replace", side_effect=fail_lock):
            with self.assertRaises(OSError):
                builder.build(alias)
        self.assertTrue(failed[0], "alias root did not reach expected write fault")
        self.assertEqual(tree_hash(self.root / "dsh"), previous)
        self.assertEqual((self.root / "prompt-bundles.lock").read_bytes(), lock_before)

    def test_16_explicit_workbuddy_target_rebuilds_historical_outputs(self):
        before = tree_hash(self.root / "agents")
        result = builder.build(self.root, target="workbuddy")
        self.assertIn("version", result)
        lock = json.loads((self.root / "prompt-bundles.lock").read_text(encoding="utf-8"))
        self.assertNotIn("target", lock)
        self.assertEqual(lock["version"], ROOT_VERSION)
        # Explicit legacy build regenerates the same historical bytes from the
        # frozen sources: the WB tree stays byte-identical.
        self.assertEqual(tree_hash(self.root / "agents"), before)

    def test_17_change_between_check_and_move_is_preserved(self):
        builder.build(self.root)
        actual = builder.os.replace
        raced = [False]
        proof = self.root / "dsh/package.json"
        changed = proof.read_bytes() + b"\n"
        def concurrent_write(src, dst):
            if Path(src) == self.root / "dsh" and not raced[0]:
                raced[0] = True
                proof.write_bytes(changed)
            return actual(src, dst)
        with patch.object(builder.os, "replace", side_effect=concurrent_write):
            with self.assertRaises(OSError):
                builder.build(self.root)
        self.assertTrue(raced[0])
        self.assertEqual(proof.read_bytes(), changed)


class DshZipTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = make_full_fixture(self.base)
        builder.build(self.root)

    def test_20_dsh_zip_contains_exactly_the_sorted_subset(self):
        output = self.base / "dsh-release.zip"
        result = build_release.build_release(self.root, output)
        self.assertEqual(result["target"], "dsh")
        expected_names = sorted("crm-sre-team/" + rel for rel in DSH_SUBSET)
        with ZipFile(output) as archive:
            names = [entry.filename for entry in archive.infolist()]
        self.assertEqual(names, expected_names)
        report = validate_release.validate(self.root, output)
        self.assertTrue(report["pass"], report["errors"])
        self.assertEqual(report["target"], "dsh")

    def test_20b_release_symlink_output_parent_is_still_rejected(self):
        # Path normalization belongs to the test fixture. Real release code
        # must continue to reject caller-supplied symlinked output parents.
        alias = self.base / "output-alias"
        destination = self.base / "safe-output"
        destination.mkdir()
        try:
            alias.symlink_to(destination, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink capability unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "Symlink output or parent"):
            build_release.build_release(self.root, alias / "not-allowed.zip")
        self.assertFalse((destination / "not-allowed.zip").exists())

    def test_21_dsh_zip_deterministic_across_builds(self):
        first = self.base / "dsh-a.zip"
        second = self.base / "dsh-b.zip"
        sha_a = build_release.build_release(self.root, first)["sha256"]
        sha_b = build_release.build_release(self.root, second)["sha256"]
        self.assertEqual(sha_a, sha_b)

    def test_22_extra_entry_rejected(self):
        output = self.base / "dsh-release.zip"
        build_release.build_release(self.root, output)
        entries = []
        with ZipFile(output) as archive:
            entries = [(info, archive.read(info)) for info in archive.infolist()]
        info = ZipInfo("crm-sre-team/SYNTHETIC-EXTRA.md", release_rules.ZIP_TIME)
        info.compress_type = ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        entries.append((info, b"SYNTHETIC"))
        with ZipFile(output, "w") as archive:
            for entry, data in entries:
                archive.writestr(entry, data)
        report = validate_release.validate(self.root, output)
        self.assertFalse(report["pass"])
        self.assertIn("file_set_mismatch", report["errors"])

    def test_23_unsafe_entry_rejected(self):
        output = self.base / "dsh-release.zip"
        build_release.build_release(self.root, output)
        entries = []
        with ZipFile(output) as archive:
            entries = [(info, archive.read(info)) for info in archive.infolist()]
        info = ZipInfo("crm-sre-team/../escape.txt", release_rules.ZIP_TIME)
        info.compress_type = ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        entries.append((info, b"SYNTHETIC"))
        with ZipFile(output, "w") as archive:
            for entry, data in entries:
                archive.writestr(entry, data)
        report = validate_release.validate(self.root, output)
        self.assertFalse(report["pass"])
        self.assertTrue(any(error.startswith("unsafe_path:") for error in report["errors"]),
                        report["errors"])

    def test_24_explicit_workbuddy_zip_still_builds_and_validates(self):
        output = self.base / "wb-release.zip"
        result = build_release.build_release(self.root, output, target="workbuddy")
        self.assertEqual(result["target"], "workbuddy")
        self.assertGreater(result["files"], len(DSH_SUBSET))
        report = validate_release.validate(self.root, output, target="workbuddy")
        self.assertTrue(report["pass"], report["errors"])

    def test_25_source_free_installed_payload_verified_and_tamper_rejected(self):
        output = self.base / "dsh-install.zip"
        build_release.build_release(self.root, output)
        with ZipFile(output) as archive:
            archive.extractall(self.base / "unpacked")
        installed = self.base / "unpacked/crm-sre-team"
        self.assertFalse((installed / "tools").exists())
        self.assertTrue(validate_release.validate_installation(self.root, installed)["pass"])
        target = installed / "dsh/cordis.patch.yml"
        target.write_bytes(target.read_bytes() + b"\n# synthetic tamper\n")
        report = validate_release.validate_installation(self.root, installed)
        self.assertFalse(report["pass"])
        self.assertIn("installed_content_mismatch:dsh/cordis.patch.yml", report["errors"])


    def test_25b_installed_payload_uses_canonical_order_under_windows_path_comparison(self):
        output = self.base / "windows-order-install.zip"
        build_release.build_release(self.root, output)
        with ZipFile(output) as archive:
            archive.extractall(self.base / "windows-order")
        installed = self.base / "windows-order/crm-sre-team"

        # Model the platform ordering that exposed the real Windows failure.
        # Keep the manifest's case-sensitive POSIX order and byte checks intact.
        def windows_path_less(left, right):
            return left.as_posix().casefold() < right.as_posix().casefold()

        with patch.object(Path, "__lt__", windows_path_less):
            legacy_order = [item.relative_to(installed).as_posix()
                            for item in sorted(installed.rglob("*")) if item.is_file()]
            self.assertNotEqual(legacy_order, DSH_SUBSET)
            self.assertCountEqual(legacy_order, DSH_SUBSET)
            report = validate_release.validate_installation(self.root, installed)
            self.assertTrue(report["pass"], report["errors"])
            target = installed / "dsh/cordis.patch.yml"
            target.write_bytes(target.read_bytes() + b"\n# synthetic Windows-order tamper\n")
            report = validate_release.validate_installation(self.root, installed)
            self.assertFalse(report["pass"])
            self.assertIn("installed_content_mismatch:dsh/cordis.patch.yml", report["errors"])


class IdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = make_full_fixture(self.base)

    def test_30_frozen_root_version_and_active_dsh_identity_separate(self):
        builder.build(self.root)
        self.assertEqual((self.root / "VERSION").read_text(encoding="utf-8").strip(), ROOT_VERSION)
        package = json.loads((self.root / "dsh/package.json").read_text(encoding="utf-8"))
        source = json.loads((self.root / "policy-source/dsh/package-source.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], DSH_VERSION)
        self.assertEqual(source["version"], DSH_VERSION)
        lock = json.loads((self.root / "prompt-bundles.lock").read_text(encoding="utf-8"))
        self.assertEqual((lock["version"], lock["target"], lock["target_version"]),
                         (ROOT_VERSION, "dsh", DSH_VERSION))
        self.assertNotEqual(ROOT_VERSION, DSH_VERSION)


class ValidatorCheckOnlyTests(unittest.TestCase):
    """Git handoff verification must preserve the checkout and prior reports."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = make_full_fixture(self.base)
        builder.build(self.root)
        self.report_path = self.root / "tests/static-checks.json"
        self.report_path.write_bytes(b'{"synthetic_previous_report": true}\n')

    def run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(self.root / "tools/validate_bundle.py"),
             "--root", str(self.root), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
            timeout=60,
        )
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result, json.loads(result.stdout)

    def test_35_check_only_success_preserves_checkout_and_report(self):
        before = tree_hash(self.root)
        result, report = self.run_cli("--check-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["result"], "PASS_STATIC_ONLY")
        self.assertEqual(report["target"], "dsh")
        self.assertEqual(tree_hash(self.root), before)

    def test_36_check_only_tamper_fails_without_rewriting_report(self):
        patch_path = self.root / "dsh/cordis.patch.yml"
        patch_path.write_bytes(patch_path.read_bytes() + b"\n# synthetic handoff tamper\n")
        before = tree_hash(self.root)
        result, report = self.run_cli("--check-only")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(report["result"], "FAIL")
        self.assertTrue(report["errors"])
        self.assertEqual(tree_hash(self.root), before)

    def test_37_default_validation_still_writes_complete_report(self):
        before = tree_hash(self.root)
        result, summary = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["result"], "PASS_STATIC_ONLY")
        self.assertTrue(report["checks"])
        self.assertEqual({k: v for k, v in report.items() if k != "checks"}, summary)
        after = tree_hash(self.root)
        changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
        self.assertEqual(changed, {"tests/static-checks.json"})

    def test_38_workbuddy_check_only_preserves_all_generated_reports(self):
        builder.build(self.root, target="workbuddy")
        for name in ("reasoning-matrix-results.json", "judgment-matrix-results.json",
                     "contract-test-results.txt"):
            (self.root / "tests" / name).write_bytes(b'{"synthetic_previous_report": true}\n')
        before = tree_hash(self.root)
        result, report = self.run_cli("--target", "workbuddy", "--check-only")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(report["result"], "PASS_STATIC_ONLY")
        self.assertEqual(tree_hash(self.root), before)


class PipelineTargetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve(strict=True)
        self.root = make_full_fixture(self.base)
        builder.build(self.root)

    def test_40_preflight_resolves_active_target_from_manifest(self):
        pipeline = release.Pipeline(self.root)
        self.assertIsNone(pipeline.target)
        self.assertTrue(pipeline._step_preflight()["ok"])
        self.assertEqual(pipeline.target, "dsh")

    def test_41_preflight_on_legacy_fixture_resolves_workbuddy(self):
        with tempfile.TemporaryDirectory() as td:
            legacy = make_legacy_fixture(Path(td).resolve(strict=True))
            pipeline = release.Pipeline(legacy)
            self.assertTrue(pipeline._step_preflight()["ok"])
            self.assertEqual(pipeline.target, "workbuddy")

    def test_42_legacy_version_step_keeps_plugin_identity_check(self):
        with tempfile.TemporaryDirectory() as td:
            legacy = make_legacy_fixture(Path(td).resolve(strict=True))
            pipeline = release.Pipeline(legacy)
            pipeline._step_preflight()
            self.assertTrue(pipeline._step_version_validation()["ok"])
            self.assertEqual(pipeline.version, "2.6.1")
            (legacy / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            failed = release.Pipeline(legacy)
            failed._step_preflight()
            result = failed._step_version_validation()
            self.assertFalse(result["ok"])
            self.assertIn("VERSION", result["error"])

    def test_43_dsh_version_step_requires_lock_target_identity(self):
        pipeline = release.Pipeline(self.root)
        pipeline._step_preflight()
        result = pipeline._step_version_validation()
        self.assertTrue(result["ok"], result)
        self.assertEqual(pipeline.version, DSH_VERSION)
        self.assertEqual(pipeline.root_version, ROOT_VERSION)
        lock_path = self.root / "prompt-bundles.lock"
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock.pop("target")
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        failed = release.Pipeline(self.root)
        failed._step_preflight()
        result = failed._step_version_validation()
        self.assertFalse(result["ok"])
        self.assertIn("lock target identity", result["error"])

    def test_44_dsh_report_validators_shape_and_rejections(self):
        good = {"scope": "DSH_STATIC_STRUCTURE_AND_BOUNDARY_CHECKS_NOT_RUNTIME_BEHAVIOR",
                "target": "dsh", "target_version": DSH_VERSION, "result": "PASS_STATIC_ONLY",
                "errors": [], "checks_total": 30, "checks_passed": 30,
                "dsh_checker_checks_total": 91, "dsh_checker_checks_passed": 91,
                "model_or_host_runtime_test_status": "NOT_RUN_IN_TARGET_HOST"}
        self.assertTrue(release.valid_dsh_bundle_report(good, DSH_VERSION))
        for mutation in ({"result": "FAIL"}, {"errors": ["x"]}, {"target": "workbuddy"},
                         {"target_version": "9.9.9"}, {"checks_total": 0},
                         {"checks_passed": 29}, {"dsh_checker_checks_passed": 90},
                         {"model_or_host_runtime_test_status": "PASS"}):
            with self.subTest(mutation=mutation):
                self.assertFalse(release.valid_dsh_bundle_report({**good, **mutation}, DSH_VERSION))
        det_good = {"scope": "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS",
                    "target": "dsh", "version": DSH_VERSION,
                    **dict.fromkeys(["pass", "generated_artifacts_deterministic", "release_tree_deterministic",
                                     "input_release_already_built", "validation_output_deterministic",
                                     "validation_tree_deterministic", "source_tree_unchanged_during_comparisons",
                                     "zip_deterministic"], True),
                    "checked_files": 4, "hashes": {"k": "a" * 64, "l": "b" * 64, "m": "c" * 64, "n": "d" * 64},
                    "release_tree_file_count": 10,
                    "build_exit_codes": [0, 0], "zip_exit_codes": [0, 0], "validate_zip_exit_code": 0,
                    "validation_exit_codes": [0, 0, 0],
                    "sorting_guard_negative_test": {"exit_code": 1, "detected": True,
                                                    "failed_check_ids": ["validator_sorted_filesystem_traversal"]}}
        self.assertTrue(release.valid_dsh_determinism_report(det_good, DSH_VERSION))
        for mutation in ({"zip_deterministic": False}, {"target": "workbuddy"},
                         {"version": ROOT_VERSION}, {"build_exit_codes": [0, 1]},
                         {"validate_zip_exit_code": 1}, {"checked_files": 0},
                         {"sorting_guard_negative_test": {"exit_code": 0, "detected": False,
                                                          "failed_check_ids": []}}):
            with self.subTest(mutation=mutation):
                self.assertFalse(release.valid_dsh_determinism_report({**det_good, **mutation}, DSH_VERSION))


if __name__ == "__main__":
    unittest.main(verbosity=2)
