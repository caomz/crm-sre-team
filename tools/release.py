#!/usr/bin/env python3
"""Release pipeline: 10-step serial, fail-stop, staging->promote-last.

No input rebuild. No test recursion. No official artifacts before promote.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Tree digest (matches F3 scope: transient + generated-report exclusions)
# ---------------------------------------------------------------------------

_TRANSIENT_DIRS = {"__pycache__", ".pytest_cache", ".git", ".venv", "dist", "reports"}
_TRANSIENT_SUFFIXES = {".pyc", ".tmp.json", ".tmp.txt"}
_TRANSIENT_FILES = {".DS_Store"}


def _load_generated_reports(root: Path) -> set:
    """Load excluded_generated_reports from release-manifest.json."""
    manifest_path = root / "release-manifest.json"
    if not manifest_path.exists():
        return set()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return set(manifest.get("excluded_generated_reports", []))
    except (json.JSONDecodeError, OSError):
        return set()


def compute_tree_digest(root: Path) -> str:
    """SHA-256 digest of the project tree (transient + generated excluded)."""
    root = Path(root).resolve()
    generated = _load_generated_reports(root)
    h = hashlib.sha256()
    files = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        rel = p.relative_to(root).as_posix()
        if set(rel_parts) & _TRANSIENT_DIRS:
            continue
        if p.name in _TRANSIENT_FILES:
            continue
        if p.suffix in _TRANSIENT_SUFFIXES:
            continue
        if rel in generated:
            continue
        files.append(rel)
    for rel in files:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update((root / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Runner abstraction (default=real subprocess, fake=for pipeline tests)
# ---------------------------------------------------------------------------

class StepRunner:
    """Default runner: real subprocess + function calls."""

    _PROJECT_ROOT = ROOT

    def run_validate_bundle(self, root: Path):
        """Returns (exit_code, result_dict_or_None)."""
        script = self._PROJECT_ROOT / "tools" / "validate_bundle.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(root)],
            cwd=str(root), capture_output=True, timeout=300)
        result = None
        try:
            result = json.loads(proc.stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return proc.returncode, result

    def run_unittest(self, root: Path):
        """Returns (exit_code, stdout_str, stderr_str)."""
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "tests", "-v"],
            cwd=str(root), capture_output=True, timeout=600)
        return (proc.returncode,
                proc.stdout.decode("utf-8", errors="replace"),
                proc.stderr.decode("utf-8", errors="replace"))

    def run_determinism(self, root: Path):
        """Returns (exit_code, result_dict_or_None)."""
        script = self._PROJECT_ROOT / "tools" / "check_determinism.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(root)],
            cwd=str(root), capture_output=True, timeout=300)
        result = None
        try:
            result = json.loads(proc.stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return proc.returncode, result

    def build_release(self, root: Path, output: Path) -> dict:
        """Calls build_release.build_release directly."""
        tools_dir = Path(__file__).resolve().parent
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))
        from build_release import build_release as _build
        return _build(root, output)

    def run_validate_release(self, zip_path: Path):
        """Returns (exit_code, result_dict_or_None)."""
        script = self._PROJECT_ROOT / "tools" / "validate_release.py"
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(self._PROJECT_ROOT), "--zip", str(zip_path)],
            capture_output=True, timeout=120)
        result = None
        try:
            result = json.loads(proc.stdout.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return proc.returncode, result


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

PIPELINE_STEPS = [
    "preflight",
    "version_validation",
    "input_consistency",
    "tests",
    "determinism",
    "build_staging",
    "validate_release",
    "unpack_revalidate",
    "generate_report",
    "promote",
]


def positive_count(value):
    return type(value) is int and value > 0


def valid_bundle_report(report, version):
    if not isinstance(report, dict):
        return False
    counts = ["additional_static_tests", "offline_contract_tests_run", "reasoning_matrix_test_methods",
              "judgment_contract_tests_run", "judgment_matrix_test_methods", "thinking_tool_tests_run"]
    zeros = ["offline_contract_test_failures", "offline_contract_test_errors",
             "reasoning_matrix_test_failures", "reasoning_matrix_test_errors", "reasoning_matrix_mismatches",
             "judgment_contract_test_failures", "judgment_contract_test_errors",
             "judgment_matrix_test_failures", "judgment_matrix_test_errors", "judgment_matrix_mismatches",
             "thinking_tool_test_failures", "thinking_tool_test_errors"]
    return (report.get("scope") == "STATIC_STRUCTURE_AND_OFFLINE_SCHEMA_POLICY_TESTS_ONLY"
            and report.get("version") == version and report.get("result") == "PASS_STATIC_ONLY"
            and report.get("errors") == [] and positive_count(report.get("checks_total"))
            and type(report.get("checks_passed")) is int
            and report["checks_passed"] == report["checks_total"]
            and positive_count(report.get("offline_unit_tests_total"))
            and all(positive_count(report.get(k)) for k in counts)
            and sum(report[k] for k in counts) == report["offline_unit_tests_total"]
            and all(type(report.get(k)) is int and report[k] == 0 for k in zeros))


def valid_determinism_report(report, version):
    if not isinstance(report, dict):
        return False
    flags = ["pass", "generated_artifacts_deterministic", "release_tree_deterministic",
             "input_release_already_built", "validation_output_deterministic",
             "validation_tree_deterministic", "source_tree_unchanged_during_comparisons"]
    guard = report.get("sorting_guard_negative_test")
    return (report.get("scope") == "TEMPORARY_RELEASE_COPY_SAME_ENVIRONMENT_NO_MODEL_OR_HOST_CALLS"
            and report.get("version") == version and all(report.get(k) is True for k in flags)
            and positive_count(report.get("checked_files")) and isinstance(report.get("hashes"), dict)
            and len(report["hashes"]) == report["checked_files"]
            and all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in report["hashes"].values())
            and positive_count(report.get("release_tree_file_count"))
            and report["release_tree_file_count"] >= report["checked_files"]
            and report.get("build_exit_codes") == [0, 0] and report.get("validation_exit_codes") == [0, 0, 0]
            and isinstance(guard, dict) and guard.get("exit_code") == 1
            and guard.get("detected") is True and bool(guard.get("failed_check_ids")))


class Pipeline:
    """10-step serial pipeline. Fail-stop. Staging->promote-last."""

    def __init__(self, root, runner=None, frozen_digest=None):
        self.root = Path(root).resolve()
        self.runner = runner or StepRunner()
        self.frozen_digest = frozen_digest
        self.dist = self.root / "dist"
        self.staging_base = self.dist / "staging"
        self.releases_dir = self.dist / "releases"
        self.failed_dir = self.dist / "failed"
        self.steps_executed = []
        self.staging_dir = None
        self.release_zip = None
        self.release_sha256 = None
        self.tree_digest = None
        self.version = None
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def run(self):
        """Execute all steps. Returns structured result dict."""
        for step_name in PIPELINE_STEPS:
            method = getattr(self, "_step_" + step_name)
            try:
                result = method()
            except Exception as exc:
                result = {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}
            self.steps_executed.append({
                "name": step_name,
                "ok": result.get("ok", False),
                "error": result.get("error"),
                "exit_code": result.get("exit_code"),
            })
            if not result.get("ok"):
                self._handle_failure(step_name, result)
                return self._build_result()
        return self._build_result()

    def _build_result(self):
        failed = next((s for s in self.steps_executed if not s["ok"]), None)
        release_dir = None
        if self.staging_dir and self.staging_dir.exists():
            release_dir = str(self.staging_dir)
        return {
            "ok": failed is None,
            "failed_step": failed["name"] if failed else None,
            "error": failed["error"] if failed else None,
            "steps": list(self.steps_executed),
            "staging_dir": str(self.staging_dir) if self.staging_dir else None,
            "release_dir": release_dir,
            "version": self.version,
            "tree_digest": self.tree_digest,
            "release_sha256": self.release_sha256,
        }

    def _handle_failure(self, step_name, result):
        """Move staging to failed/. Always write log."""
        if self.staging_dir and self.staging_dir.exists():
            failed_target = self.failed_dir / (self.timestamp + "-" + step_name)
            self.failed_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(self.staging_dir), str(failed_target))
            except OSError:
                pass
        log_dir = self.failed_dir / self.timestamp
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "log.txt"
        log_path.write_text(
            "Step " + step_name + " failed: " + str(result.get("error", "unknown")) + "\n",
            encoding="utf-8")

    # --- 10 steps ---

    def _step_preflight(self):
        required = [
            "VERSION",
            ".codebuddy-plugin/plugin.json",
            "release-manifest.json",
            "prompt-bundles.lock",
        ]
        for name in required:
            if not (self.root / name).exists():
                return {"ok": False, "error": "missing required file: " + name}
        if sys.version_info < (3, 10):
            return {"ok": False, "error": "Python >= 3.10 required, got " + str(sys.version_info)}
        self.staging_base.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True}

    def _step_version_validation(self):
        version = (self.root / "VERSION").read_text(encoding="utf-8").strip()
        plugin = json.loads(
            (self.root / ".codebuddy-plugin/plugin.json").read_text(encoding="utf-8"))
        if version != plugin.get("version"):
            return {"ok": False, "error": "VERSION=" + repr(version) + " != plugin.json version=" + repr(plugin.get("version"))}
        self.version = version
        return {"ok": True}

    def _step_input_consistency(self):
        exit_code, result = self.runner.run_validate_bundle(self.root)
        if exit_code != 0:
            return {"ok": False, "error": "validate_bundle exit_code=" + str(exit_code), "exit_code": exit_code}
        if not valid_bundle_report(result, self.version):
            label = result.get("result") if isinstance(result, dict) else None
            return {"ok": False, "error": "validate_bundle invalid report, result=" + str(label), "exit_code": exit_code}
        self.tree_digest = compute_tree_digest(self.root)
        if self.frozen_digest and self.tree_digest != self.frozen_digest:
            return {"ok": False, "error": "tree digest mismatch: current=" + self.tree_digest[:16] + "... frozen=" + self.frozen_digest[:16] + "..."}
        return {"ok": True, "exit_code": exit_code}

    def _step_tests(self):
        exit_code, stdout, stderr = self.runner.run_unittest(self.root)
        if exit_code != 0:
            tail = stderr[-200:] if stderr else stdout[-200:]
            return {"ok": False, "error": "unittest exit_code=" + str(exit_code) + ": " + tail, "exit_code": exit_code}
        output = stdout + "\n" + stderr
        summaries = re.findall(r"^Ran (\d+) tests?(?: in [^\r\n]+)?\s*$", output, re.MULTILINE)
        success = re.search(r"^OK(?: \(skipped=(\d+)\))?\s*\Z", output, re.MULTILINE)
        if len(summaries) != 1 or not positive_count(int(summaries[0])) or success is None:
            return {"ok": False, "error": "unittest missing valid nonzero success summary", "exit_code": exit_code}
        tests_run = int(summaries[0])
        skipped = int(success.group(1) or 0)
        if skipped >= tests_run or re.search(r"^FAILED\b", output, re.MULTILINE):
            return {"ok": False, "error": "unittest inconsistent passed/test counts", "exit_code": exit_code}
        return {"ok": True, "exit_code": exit_code, "tests_run": tests_run, "tests_passed": tests_run - skipped}

    def _step_determinism(self):
        exit_code, result = self.runner.run_determinism(self.root)
        if exit_code != 0:
            return {"ok": False, "error": "determinism exit_code=" + str(exit_code), "exit_code": exit_code}
        if not valid_determinism_report(result, self.version):
            return {"ok": False, "error": "determinism invalid report", "exit_code": exit_code}
        return {"ok": True, "exit_code": exit_code}

    def _step_build_staging(self):
        staging_name = self.version + "-" + self.timestamp
        self.staging_dir = self.staging_base / staging_name
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        zip_name = "crm-sre-team-" + self.version + ".zip"
        self.release_zip = self.staging_dir / zip_name
        try:
            build_result = self.runner.build_release(self.root, self.release_zip)
            self.release_sha256 = build_result.get("sha256")
        except Exception as exc:
            return {"ok": False, "error": "build_release failed: " + type(exc).__name__ + ": " + str(exc)}
        if not self.release_zip.exists():
            return {"ok": False, "error": "build_release did not produce output ZIP"}
        with ZipFile(self.release_zip) as archive:
            files = len(archive.infolist())
        if (not isinstance(build_result, dict)
                or build_result.get("scope") != "MANIFEST_CONTENT_INTEGRITY_NOT_HOST_VERIFICATION"
                or not positive_count(build_result.get("files")) or build_result["files"] != files
                or build_result.get("archive") != str(self.release_zip)
                or self.release_sha256 != hashlib.sha256(self.release_zip.read_bytes()).hexdigest()):
            return {"ok": False, "error": "build_release invalid report"}
        return {"ok": True}

    def _step_validate_release(self):
        exit_code, result = self.runner.run_validate_release(self.release_zip)
        if exit_code != 0:
            return {"ok": False, "error": "validate_release exit_code=" + str(exit_code), "exit_code": exit_code}
        with ZipFile(self.release_zip) as archive:
            entries = len(archive.infolist())
        if (not isinstance(result, dict) or result.get("scope") != "ZIP_INTEGRITY_NOT_RUNTIME"
                or result.get("pass") is not True or result.get("errors") != []
                or not positive_count(result.get("files_total"))
                or type(result.get("files_checked")) is not int
                or result["files_checked"] != result["files_total"] or entries != result["files_total"]
                or result.get("sha256") != hashlib.sha256(self.release_zip.read_bytes()).hexdigest()):
            return {"ok": False, "error": "validate_release invalid report", "exit_code": exit_code}
        return {"ok": True, "exit_code": exit_code}

    def _step_unpack_revalidate(self):
        unpack_dir = self.staging_dir / "unpack-check"
        unpack_dir.mkdir(parents=True, exist_ok=True)
        exit_code = None
        try:
            with ZipFile(self.release_zip) as z:
                z.extractall(unpack_dir)
            unpacked_root = unpack_dir / "crm-sre-team"
            if not unpacked_root.exists():
                return {"ok": False, "error": "unpacked ZIP does not contain crm-sre-team/ prefix"}
            exit_code, result = self.runner.run_validate_bundle(unpacked_root)
            if exit_code != 0:
                return {"ok": False, "error": "unpack revalidate exit_code=" + str(exit_code), "exit_code": exit_code}
            if not valid_bundle_report(result, self.version):
                return {"ok": False, "error": "unpack revalidate invalid report", "exit_code": exit_code}
        except Exception as exc:
            return {"ok": False, "error": "unpack failed: " + type(exc).__name__ + ": " + str(exc)}
        finally:
            shutil.rmtree(unpack_dir, ignore_errors=True)
        return {"ok": True, "exit_code": exit_code}

    def _step_generate_report(self):
        report = {
            "version": self.version,
            "timestamp": self.timestamp,
            "tree_digest": self.tree_digest,
            "release_zip": self.release_zip.name if self.release_zip else None,
            "release_sha256": self.release_sha256,
            "steps": list(self.steps_executed),
            "scope": "OFFLINE_BUILD_CONSISTENCY_RELEASE_GATE",
        }
        report_path = self.staging_dir / "validation-report.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        lines = [
            "# Release Validation Report -- " + str(self.version),
            "",
            "- Timestamp: " + self.timestamp,
            "- Tree digest: `" + str(self.tree_digest) + "`" if self.tree_digest else "- Tree digest: (not computed)",
            "- Release ZIP: `" + str(self.release_zip.name) + "`" if self.release_zip else "- Release ZIP: (not built)",
            "- Release SHA-256: `" + str(self.release_sha256) + "`" if self.release_sha256 else "- Release SHA-256: (not computed)",
            "",
            "## Steps",
            "",
        ]
        for s in self.steps_executed:
            status = "PASS" if s["ok"] else "FAIL"
            err = s.get("error") or "ok"
            lines.append("- [" + status + "] **" + s["name"] + "** -- " + err)
        lines.extend([
            "",
            "## Scope",
            "",
            "OFFLINE_BUILD_CONSISTENCY_RELEASE_GATE",
            "WorkBuddy host acceptance remains unfinished.",
        ])
        (self.staging_dir / "validation-report.md").write_text(
            "\n".join(lines), encoding="utf-8")
        return {"ok": True}

    def _step_promote(self):
        """Move staging to releases/ -- the ONLY write to dist/releases/."""
        target = self.releases_dir / self.staging_dir.name
        if target.exists():
            return {"ok": False, "error": "release target already exists: " + target.name}
        shutil.move(str(self.staging_dir), str(target))
        self.staging_dir = target
        return {"ok": True}


# ---------------------------------------------------------------------------
# Public API + CLI
# ---------------------------------------------------------------------------

def run_pipeline(root, runner=None, frozen_digest=None):
    """Execute the 10-step release pipeline. Returns structured result dict."""
    pipe = Pipeline(root, runner=runner, frozen_digest=frozen_digest)
    return pipe.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Release pipeline: 10-step serial, fail-stop")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--frozen-digest", type=str, default=None,
                        help="Frozen candidate tree digest from finalize (hex)")
    args = parser.parse_args()
    result = run_pipeline(args.root, frozen_digest=args.frozen_digest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result["ok"] else 1)
