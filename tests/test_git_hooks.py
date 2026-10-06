"""Pre-commit gate behavior on a synthetic repo. Never touches the real project.

Covers: stale build output is blocked and rebuilt, a consistent tree commits, and
a source edit forces a rebuild+stage cycle instead of drifting silently.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "git-hooks" / "pre-commit"
INSTALLER = ROOT / "tools" / "install_git_hooks.py"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stdout}\n{proc.stderr}")
    return proc


def can_run_sh() -> bool:
    """The hook is a POSIX sh script; git for Windows supplies it, bare shells may not."""
    for candidate in ("sh", "bash"):
        if shutil.which(candidate):
            return True
    return False


requires_sh = unittest.skipUnless(can_run_sh(), "SKIPPED_CAPABILITY: no sh/bash on PATH")


class PreCommitHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "synthetic"
        (self.repo / "policy-source").mkdir(parents=True)
        (self.repo / "tools").mkdir()
        (self.repo / "skills").mkdir()
        self.src = self.repo / "policy-source" / "shared.md"
        self.gen = self.repo / "skills" / "out.md"
        self.src.write_text("canonical\n", encoding="utf-8", newline="\n")
        self.gen.write_text("canonical\n", encoding="utf-8", newline="\n")
        (self.repo / "tools" / "build_bundle.py").write_text(
            "import pathlib\n"
            "root = pathlib.Path(__file__).resolve().parents[1]\n"
            "s = (root/'policy-source'/'shared.md').read_text(encoding='utf-8')\n"
            "(root/'skills'/'out.md').write_text(s, encoding='utf-8', newline='\\n')\n",
            encoding="utf-8", newline="\n")
        (self.repo / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8", newline="\n")
        hooks = self.repo / "tools" / "git-hooks"
        hooks.mkdir(parents=True)
        shutil.copyfile(HOOK, hooks / "pre-commit")
        try:
            (hooks / "pre-commit").chmod(0o755)
        except OSError:
            pass
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "hook@test.invalid")
        git(self.repo, "config", "user.name", "hook-test")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "baseline")
        git(self.repo, "config", "core.hooksPath", "tools/git-hooks")

    def test_01_hook_and_installer_are_versioned(self):
        self.assertTrue(HOOK.is_file(), "versioned hook missing")
        self.assertTrue(INSTALLER.is_file(), "installer missing")

    def test_02_installer_sets_hooks_path_and_is_idempotent(self):
        proc = subprocess.run(["python3", str(INSTALLER), "--root", str(self.repo)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")
        again = subprocess.run(["python3", str(INSTALLER), "--root", str(self.repo)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")

    def test_03_installer_uninstall_restores_default(self):
        subprocess.run(["python3", str(INSTALLER), "--root", str(self.repo)], check=True,
                       capture_output=True)
        proc = subprocess.run(["python3", str(INSTALLER), "--root", str(self.repo), "--uninstall"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        current = git(self.repo, "config", "--get", "core.hooksPath", check=False)
        self.assertNotEqual(current.returncode, 0, "hooksPath should be removed after uninstall")

    @requires_sh
    def test_04_stale_artifact_is_blocked_and_rebuilt(self):
        self.src.write_text("canonical v2\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        blocked = git(self.repo, "commit", "-m", "drift", check=False)
        self.assertNotEqual(blocked.returncode, 0, "hook must block a stale build artifact")
        self.assertIn("stale", (blocked.stderr or "").lower())
        # Blocking is only useful if it also repaired the artifact.
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical v2\n")

    @requires_sh
    def test_05_consistent_tree_commits_cleanly(self):
        extra = self.repo / "policy-source" / "extra.md"
        extra.write_text("extra\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        allowed = git(self.repo, "commit", "-m", "source only", check=False)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    @requires_sh
    def test_06_source_edit_forces_rebuild_then_allows_landing(self):
        self.src.write_text("canonical v3\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        first = git(self.repo, "commit", "-m", "edit source", check=False)
        self.assertNotEqual(first.returncode, 0, "source edit must not commit a stale artifact")
        git(self.repo, "add", "-A")
        second = git(self.repo, "commit", "-m", "land rebuild", check=False)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("canonical v3\n", self.gen.read_text(encoding="utf-8"))

    @requires_sh
    def test_07_no_perpetual_blocking_after_rebuild(self):
        """A correct gate must let the follow-up commit through, not deadlock."""
        self.src.write_text("canonical v4\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-m", "edit", check=False)
        git(self.repo, "add", "-A")
        landed = git(self.repo, "commit", "-m", "land", check=False)
        self.assertEqual(landed.returncode, 0, landed.stdout + landed.stderr)
        # A subsequent unrelated commit must not be blocked either.
        marker = self.repo / "MARKER.md"
        marker.write_text("ok\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        after = git(self.repo, "commit", "-m", "unrelated", check=False)
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

    @requires_sh
    def test_08_no_verify_bypasses_the_gate(self):
        self.src.write_text("canonical v5\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        bypass = git(self.repo, "commit", "--no-verify", "-m", "bypass", check=False)
        self.assertEqual(bypass.returncode, 0, bypass.stdout + bypass.stderr)
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n",
                         "--no-verify should leave the artifact stale, proving the gate is what rebuilt it")

    def test_09_extensionless_tools_stay_out_of_release_manifest(self):
        """Neither the extensionless hook nor AGENTS.md is release payload."""
        manifest = (ROOT / "release-manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("git-hooks/pre-commit", manifest,
                         "extensionless hook must stay out of the release allowlist")
        self.assertNotIn('"AGENTS.md"', manifest,
                         "AGENTS.md has no extension and is not release payload")
        # The .py files added alongside them are ordinary source and must ship.
        self.assertIn("tools/install_git_hooks.py", manifest)
        self.assertIn("tools/sync_git.py", manifest)
        self.assertIn("tests/test_git_hooks.py", manifest)
        self.assertIn("tests/test_git_sync.py", manifest)


if __name__ == "__main__":
    unittest.main(verbosity=2)
