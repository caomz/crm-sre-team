"""Pre-commit gate behavior on a synthetic repo. Never touches the real project.

Covers (F6 semantics): the gate rebuilds the STAGED tree in isolation and
rejects stale build-owned outputs WITHOUT repairing them; a consistent
staged tree commits; working-tree noise and unstaged edits never influence
the verdict; the hook never modifies the working tree.
"""
from __future__ import annotations
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "git-hooks" / "pre-commit"
INSTALLER = ROOT / "tools" / "install_git_hooks.py"

FAKE_BUILD = (
    "import pathlib, sys\n"
    "args = sys.argv[1:]\n"
    "if '--root' in args:\n"
    "    root = pathlib.Path(args[args.index('--root') + 1]).resolve()\n"
    "else:\n"
    "    root = pathlib.Path(__file__).resolve().parents[1]\n"
    "s = (root/'policy-source'/'shared.md').read_text(encoding='utf-8')\n"
    "skill = root/'skills'\n"
    "skill.mkdir(parents=True, exist_ok=True)\n"
    "(skill/'out.md').write_text(s, encoding='utf-8', newline='\\n')\n"
)


def git(repo: Path, *args: str, check: bool = True,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
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


def run_hook(repo: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the hook directly via sh (cwd=repo), bypassing git's hook runner.

    Real-`git commit` coverage lives in test_13 (rejection + HEAD unchanged)
    and the positive commit paths below; direct execution keeps these cases
    hermetic (no dependence on git's hook runner or its exit-code plumbing).
    An earlier claim that this environment's git swallows hook exit codes
    was disproven on 2026-10-08 by minimal-repo reproduction: both git
    2.55.0.windows.3 and 2.49.0.windows.1 propagate a pre-commit hook's
    non-zero exit as a failed `git commit` with HEAD unchanged.
    """
    return subprocess.run(["sh", str(repo / "tools" / "git-hooks" / "pre-commit")],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


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
            FAKE_BUILD, encoding="utf-8", newline="\n")
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
        # V2: record the hook executable in the index (Windows checkouts have
        # core.fileMode=false; without this, POSIX git would ignore the hook
        # and test_13's real-commit rejection would pass vacuously there).
        git(self.repo, "update-index", "--chmod=+x", "tools/git-hooks/pre-commit")
        git(self.repo, "commit", "-m", "baseline")
        git(self.repo, "config", "core.hooksPath", "tools/git-hooks")

    def test_01_hook_and_installer_are_versioned(self):
        self.assertTrue(HOOK.is_file(), "versioned hook missing")
        self.assertTrue(INSTALLER.is_file(), "installer missing")
        # V2: the hook must be recorded executable in the index so POSIX
        # checkouts honor it when core.hooksPath points here.
        listed = git(ROOT, "ls-files", "-s", "tools/git-hooks/pre-commit")
        self.assertTrue(listed.stdout.startswith("100755"),
                        f"hook must be indexed as 100755, got: {listed.stdout!r}")

    def test_02_installer_sets_hooks_path_and_is_idempotent(self):
        proc = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")
        again = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")

    def test_03_installer_uninstall_restores_default(self):
        subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)], check=True,
                       capture_output=True)
        proc = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo), "--uninstall"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        current = git(self.repo, "config", "--get", "core.hooksPath", check=False)
        self.assertNotEqual(current.returncode, 0, "hooksPath should be removed after uninstall")

    def rebuild_and_stage(self):
        """Simulate the documented repair path: rebuild in the repo, re-stage."""
        subprocess.run([sys.executable, str(self.repo / "tools" / "build_bundle.py")],
                       check=True, capture_output=True)
        git(self.repo, "add", "-A")

    @requires_sh
    def test_04_stale_artifact_is_blocked_without_repair(self):
        self.src.write_text("canonical v2\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        blocked = run_hook(self.repo)
        self.assertNotEqual(blocked.returncode, 0, "hook must block a stale build artifact")
        self.assertIn("stale", (blocked.stderr or "").lower())
        # F6: the gate judges the staged tree and never repairs in place.
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n",
                         "hook must not modify the working tree when blocking")

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
        first = run_hook(self.repo)
        self.assertNotEqual(first.returncode, 0, "source edit must not commit a stale artifact")
        self.rebuild_and_stage()
        second = git(self.repo, "commit", "-m", "land rebuild", check=False)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("canonical v3\n", self.gen.read_text(encoding="utf-8"))

    @requires_sh
    def test_07_no_perpetual_blocking_after_rebuild(self):
        """A correct gate must let the follow-up commit through, not deadlock."""
        self.src.write_text("canonical v4\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        run_hook(self.repo)
        self.rebuild_and_stage()
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
                         "--no-verify skips the gate entirely; the working tree stays stale")

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

    @requires_sh
    def test_10_partial_staging_negative_is_blocked(self):
        """F6 key negative: the gate judges the STAGED tree only. Staging a
        new source while the working tree keeps the old source must be
        blocked (the old worktree-based gate would have let it through)."""
        self.src.write_text("canonical v6\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "policy-source/shared.md")
        # Working tree is reverted to the old source; the index keeps v6.
        self.src.write_text("canonical\n", encoding="utf-8", newline="\n")
        blocked = run_hook(self.repo)
        self.assertNotEqual(blocked.returncode, 0,
                            "staged-tree gate must block staged-source/stale-output drift")
        self.assertIn("stale", (blocked.stderr or "").lower())
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n")
        self.assertEqual(self.src.read_text(encoding="utf-8"), "canonical\n",
                         "hook must not touch working-tree files")

    @requires_sh
    def test_11_unstaged_working_tree_noise_is_ignored(self):
        """A consistent staged tree commits even with dirty working-tree
        content: the hook builds the index, not the worktree."""
        tracked = self.repo / "NOISE.md"
        tracked.write_text("staged noise\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "NOISE.md")
        tracked.write_text("dirty worktree noise\n", encoding="utf-8", newline="\n")
        allowed = git(self.repo, "commit", "-m", "clean index, dirty worktree",
                      check=False)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertEqual(tracked.read_text(encoding="utf-8"), "dirty worktree noise\n",
                         "the commit must not touch unstaged working-tree content")

    @requires_sh
    def test_12_hook_never_modifies_working_tree(self):
        """On the blocking path the working tree must stay byte-identical."""
        def snap():
            return {p.relative_to(self.repo).as_posix(): p.read_bytes()
                    for p in sorted(self.repo.rglob("*"))
                    if p.is_file() and ".git" not in p.parts}

        self.src.write_text("canonical v7\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        before = snap()
        run_hook(self.repo)
        self.assertEqual(before, snap(),
                         "hook must leave the working tree untouched even when blocking")

    @requires_sh
    def test_13_real_git_commit_rejects_stale_tree(self):
        """V2: the gate must be provably effective under a REAL `git commit`:
        with the hook executable and stale staged outputs, commit returns
        non-zero and HEAD does not move. This is the evidence that was
        missing since the rejection cases moved to direct hook execution."""
        self.src.write_text("canonical v13\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "-A")
        before = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        blocked = git(self.repo, "commit", "-m", "must be rejected by the gate",
                      check=False)
        self.assertNotEqual(blocked.returncode, 0,
                            "real git commit must fail when staged outputs are stale")
        after = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(before, after,
                         "HEAD must not move when the gate blocks the commit")

    @requires_sh
    def test_14_hook_uses_staged_build_script(self):
        """V2: the hook runs the STAGED tools/build_bundle.py from the export
        dir — an unstaged working-tree edit to the build script must not
        influence the verdict (positive still lands, negative still STALE)."""
        build = self.repo / "tools" / "build_bundle.py"
        original = build.read_text(encoding="utf-8")
        broken = "import sys\nsys.exit(3)\n"
        try:
            # Positive: consistent staged tree commits even though the
            # working-tree build script is broken (unstaged).
            extra = self.repo / "policy-source" / "extra14.md"
            extra.write_text("extra\n", encoding="utf-8", newline="\n")
            self.rebuild_and_stage()
            build.write_text(broken, encoding="utf-8", newline="\n")
            allowed = git(self.repo, "commit",
                          "-m", "consistent staged tree, broken worktree script",
                          check=False)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
            # Negative: stale staged outputs must be rejected as STALE —
            # proof the staged (working) script ran, not the broken copy.
            self.src.write_text("canonical v14\n", encoding="utf-8", newline="\n")
            git(self.repo, "add", "policy-source/shared.md")
            blocked = run_hook(self.repo)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("stale", (blocked.stderr or "").lower(),
                          "must report STALE (staged script ran), not a broken-script failure")
        finally:
            build.write_text(original, encoding="utf-8", newline="\n")

    def hook_environment(self, name: str) -> dict[str, str]:
        env = os.environ.copy()
        temp_root = Path(self.tmp.name) / name
        temp_root.mkdir()
        env["TMPDIR"] = str(temp_root)
        return env

    def interpreter_shims(self, name: str, working: str | None = None) -> Path:
        """Shadow every candidate, including Store aliases, without changing the host."""
        shim_dir = Path(self.tmp.name) / name
        shim_dir.mkdir()
        executable = shlex.quote(Path(sys.executable).as_posix())
        for candidate in ("python3", "python", "py"):
            body = "exit 127\n"
            if candidate == working:
                body = ('[ "$1" = "-3" ] || exit 126\nshift\n' if candidate == "py" else "")
                body += f'exec {executable} "$@"\n'
            shim = shim_dir / candidate
            shim.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
            shim.chmod(0o755)
        return shim_dir

    @requires_sh
    def test_15_no_working_python_rejects_real_commit(self):
        """Unavailable interpreters must fail closed under git's actual hook runner."""
        env = self.hook_environment("no-python-temp")
        shim_dir = self.interpreter_shims("no-python-bin")
        env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
        extra = self.repo / "MARKER.md"
        extra.write_text("pending\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "MARKER.md")
        before_head = git(self.repo, "rev-parse", "HEAD").stdout
        before_index = git(self.repo, "write-tree").stdout
        blocked = git(self.repo, "commit", "-m", "must reject without Python",
                      check=False, env=env)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("no working python3/python/py -3", blocked.stderr)
        self.assertIn("commit aborted", blocked.stderr)
        self.assertNotIn("SKIPPED", blocked.stderr)
        self.assertEqual(before_head, git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual(before_index, git(self.repo, "write-tree").stdout)
        self.assertEqual(extra.read_text(encoding="utf-8"), "pending\n")
        self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [],
                         "missing Python must abort before exporting the staged tree")

    def test_16_hook_never_deletes_recursively(self):
        text = HOOK.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^\s*rm\b[^\n]*(?:\s-[A-Za-z]*[rR]|--recursive)")
        self.assertNotRegex(text, r"(?m)^\s*find\b[^\n]*-delete\b")
        self.assertNotIn("rmtree", text)

    @requires_sh
    def test_17_cleanup_keeps_snapshot_and_unexpected_files(self):
        build = self.repo / "tools" / "build_bundle.py"
        build.write_text(FAKE_BUILD +
                         "(root.parent/'unexpected.txt').write_text('retain me', encoding='utf-8')\n",
                         encoding="utf-8", newline="\n")
        git(self.repo, "add", "tools/build_bundle.py")
        env = self.hook_environment("cleanup-success")
        allowed = run_hook(self.repo, env=env)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        retained = list(Path(env["TMPDIR"]).glob("crm-precommit.*"))
        self.assertEqual(len(retained), 1)
        snapshot = retained[0]
        self.assertIn(snapshot.name, allowed.stderr)
        self.assertIn("retained non-empty staged snapshot", allowed.stderr)
        self.assertEqual((snapshot / "unexpected.txt").read_text(encoding="utf-8"), "retain me")
        self.assertEqual((snapshot / "export" / "skills" / "out.md").read_bytes(),
                         self.gen.read_bytes())
        self.assertFalse((snapshot / "before.txt").exists())
        self.assertFalse((snapshot / "after.txt").exists())

    @requires_sh
    def test_18_cleanup_preserves_build_failure(self):
        build = self.repo / "tools" / "build_bundle.py"
        build.write_text("import sys\nsys.exit(3)\n", encoding="utf-8", newline="\n")
        git(self.repo, "add", "tools/build_bundle.py")
        env = self.hook_environment("cleanup-failure")
        blocked = run_hook(self.repo, env=env)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("staged copy) exited non-zero", blocked.stderr)
        retained = list(Path(env["TMPDIR"]).glob("crm-precommit.*"))
        self.assertEqual(len(retained), 1)
        self.assertTrue((retained[0] / "export" / "tools" / "build_bundle.py").is_file())
        self.assertFalse((retained[0] / "before.txt").exists())
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n")

    @requires_sh
    def test_19_working_python_and_py_launcher_fallbacks(self):
        for candidate in ("python", "py"):
            with self.subTest(interpreter=candidate):
                env = self.hook_environment("fallback-temp-" + candidate)
                shim_dir = self.interpreter_shims("fallback-bin-" + candidate, working=candidate)
                env["PATH"] = str(shim_dir) + os.pathsep + env.get("PATH", "")
                allowed = run_hook(self.repo, env=env)
                self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
