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
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "tools" / "git-hooks" / "pre-commit"
INSTALLER = ROOT / "tools" / "install_git_hooks.py"
GIT_PATH = str(Path(shutil.which("git")).resolve())

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
    proc = subprocess.run([GIT_PATH, "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stdout}\n{proc.stderr}")
    return proc


def resolve_posix_sh(*, windows: bool = os.name == "nt") -> str | None:
    """Use Git for Windows' own sh first; never substitute a WSL bash launcher."""
    candidates = []
    if windows:
        proc = subprocess.run([GIT_PATH, "--exec-path"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            for ancestor in Path(proc.stdout.strip()).resolve().parents:
                candidates.extend((ancestor / "usr" / "bin" / "sh.exe",
                                   ancestor / "bin" / "sh.exe"))
    on_path = shutil.which("sh")
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if not candidate.is_file():
            continue
        absolute = str(candidate.resolve())
        if Path(absolute).name.casefold() in {"bash.exe", "wsl.exe"}:
            continue
        try:
            probe = subprocess.run([absolute, "-c", "printf '%s' crm-posix-sh"],
                                   capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and probe.stdout == "crm-posix-sh":
            return absolute
    return None


SH_PATH = resolve_posix_sh()


def can_run_sh() -> bool:
    """Capability and execution share the same previously probed absolute path."""
    return SH_PATH is not None


requires_sh = unittest.skipUnless(
    can_run_sh(), "SKIPPED_CAPABILITY: no working POSIX sh in Git for Windows or PATH; WSL is not sh")


def direct_shell_environment() -> dict[str, str]:
    """Supply Git's POSIX tools when sh is launched without the git runner.

    Do not inject HOME/bin or other host directories. Explicit controlled
    environments bypass this helper so fault/interpreter shims stay first.
    """
    env = os.environ.copy()
    if os.name == "nt" and SH_PATH is not None:
        shell_dir = Path(SH_PATH).parent
        git_root = shell_dir.parent.parent if shell_dir.parent.name.casefold() == "usr" else shell_dir.parent
        paths = [str(shell_dir)]
        mingw_bin = git_root / "mingw64" / "bin"
        if mingw_bin.is_dir():
            paths.append(str(mingw_bin))
        if env.get("PATH"):
            paths.append(env["PATH"])
        env["PATH"] = os.pathsep.join(paths)
    return env


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
    return subprocess.run([SH_PATH, str(repo / "tools" / "git-hooks" / "pre-commit")],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env=direct_shell_environment() if env is None else env, timeout=30)


class PreCommitHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hook-tests-", dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.temp_roots: list[Path] = []
        self.env = self.hook_environment("hook-temp")
        self.addCleanup(self.assert_no_temp_snapshots)
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
        self.git(self.repo, "init", "-b", "main")
        self.git(self.repo, "config", "user.email", "hook@test.invalid")
        self.git(self.repo, "config", "user.name", "hook-test")
        self.git(self.repo, "add", "-A")
        # V2: record the hook executable in the index (Windows checkouts have
        # core.fileMode=false; without this, POSIX git would ignore the hook
        # and test_13's real-commit rejection would pass vacuously there).
        self.git(self.repo, "update-index", "--chmod=+x", "tools/git-hooks/pre-commit")
        self.git(self.repo, "commit", "-m", "baseline")
        self.git(self.repo, "config", "core.hooksPath", "tools/git-hooks")

    def test_01_hook_and_installer_are_versioned(self):
        self.assertTrue(HOOK.is_file(), "versioned hook missing")
        self.assertTrue(INSTALLER.is_file(), "installer missing")
        # V2: the hook must be recorded executable in the index so POSIX
        # checkouts honor it when core.hooksPath points here.
        listed = self.git(ROOT, "ls-files", "-s", "tools/git-hooks/pre-commit")
        self.assertTrue(listed.stdout.startswith("100755"),
                        f"hook must be indexed as 100755, got: {listed.stdout!r}")

    def test_02_installer_sets_hooks_path_and_is_idempotent(self):
        proc = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")
        again = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=self.env)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(self.git(self.repo, "config", "--get", "core.hooksPath").stdout.strip(),
                         "tools/git-hooks")

    def test_03_installer_uninstall_restores_default(self):
        subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo)], check=True,
                       capture_output=True, env=self.env)
        proc = subprocess.run([sys.executable, str(INSTALLER), "--root", str(self.repo), "--uninstall"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        current = self.git(self.repo, "config", "--get", "core.hooksPath", check=False)
        self.assertNotEqual(current.returncode, 0, "hooksPath should be removed after uninstall")

    def rebuild_and_stage(self):
        """Simulate the documented repair path: rebuild in the repo, re-stage."""
        subprocess.run([sys.executable, str(self.repo / "tools" / "build_bundle.py")],
                       check=True, capture_output=True, env=self.env)
        self.git(self.repo, "add", "-A")

    @requires_sh
    def test_04_stale_artifact_is_blocked_without_repair(self):
        self.src.write_text("canonical v2\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        blocked = self.run_hook(self.repo)
        self.assertNotEqual(blocked.returncode, 0, "hook must block a stale build artifact")
        self.assertIn("stale", (blocked.stderr or "").lower())
        # F6: the gate judges the staged tree and never repairs in place.
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n",
                         "hook must not modify the working tree when blocking")

    @requires_sh
    def test_05_consistent_tree_commits_cleanly(self):
        extra = self.repo / "policy-source" / "extra.md"
        extra.write_text("extra\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        allowed = self.git(self.repo, "commit", "-m", "source only", check=False)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

    @requires_sh
    def test_06_source_edit_forces_rebuild_then_allows_landing(self):
        self.src.write_text("canonical v3\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        first = self.run_hook(self.repo)
        self.assertNotEqual(first.returncode, 0, "source edit must not commit a stale artifact")
        self.rebuild_and_stage()
        second = self.git(self.repo, "commit", "-m", "land rebuild", check=False)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("canonical v3\n", self.gen.read_text(encoding="utf-8"))

    @requires_sh
    def test_07_no_perpetual_blocking_after_rebuild(self):
        """A correct gate must let the follow-up commit through, not deadlock."""
        self.src.write_text("canonical v4\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        self.run_hook(self.repo)
        self.rebuild_and_stage()
        landed = self.git(self.repo, "commit", "-m", "land", check=False)
        self.assertEqual(landed.returncode, 0, landed.stdout + landed.stderr)
        # A subsequent unrelated commit must not be blocked either.
        marker = self.repo / "MARKER.md"
        marker.write_text("ok\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        after = self.git(self.repo, "commit", "-m", "unrelated", check=False)
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)

    @requires_sh
    def test_08_no_verify_bypasses_the_gate(self):
        self.src.write_text("canonical v5\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        bypass = self.git(self.repo, "commit", "--no-verify", "-m", "bypass", check=False)
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
        self.git(self.repo, "add", "policy-source/shared.md")
        # Working tree is reverted to the old source; the index keeps v6.
        self.src.write_text("canonical\n", encoding="utf-8", newline="\n")
        blocked = self.run_hook(self.repo)
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
        self.git(self.repo, "add", "NOISE.md")
        tracked.write_text("dirty worktree noise\n", encoding="utf-8", newline="\n")
        allowed = self.git(self.repo, "commit", "-m", "clean index, dirty worktree",
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
        self.git(self.repo, "add", "-A")
        before = snap()
        self.run_hook(self.repo)
        self.assertEqual(before, snap(),
                         "hook must leave the working tree untouched even when blocking")

    @requires_sh
    def test_13_real_git_commit_rejects_stale_tree(self):
        """V2: the gate must be provably effective under a REAL `git commit`:
        with the hook executable and stale staged outputs, commit returns
        non-zero and HEAD does not move. This is the evidence that was
        missing since the rejection cases moved to direct hook execution."""
        self.src.write_text("canonical v13\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "-A")
        before = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
        blocked = self.git(self.repo, "commit", "-m", "must be rejected by the gate",
                      check=False)
        self.assertNotEqual(blocked.returncode, 0,
                            "real git commit must fail when staged outputs are stale")
        after = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()
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
            allowed = self.git(self.repo, "commit",
                          "-m", "consistent staged tree, broken worktree script",
                          check=False)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
            # Negative: stale staged outputs must be rejected as STALE —
            # proof the staged (working) script ran, not the broken copy.
            self.src.write_text("canonical v14\n", encoding="utf-8", newline="\n")
            self.git(self.repo, "add", "policy-source/shared.md")
            blocked = self.run_hook(self.repo)
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn("stale", (blocked.stderr or "").lower(),
                          "must report STALE (staged script ran), not a broken-script failure")
        finally:
            build.write_text(original, encoding="utf-8", newline="\n")

    def hook_environment(self, name: str) -> dict[str, str]:
        # setUp, cleanup retries and tool probes all use this prepared baseline.
        env = direct_shell_environment()
        temp_root = Path(self.tmp.name) / name
        temp_root.mkdir()
        self.temp_roots.append(temp_root)
        env["TMPDIR"] = str(temp_root)
        return env

    def git(self, repo: Path, *args: str, check: bool = True,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return git(repo, *args, check=check, env=self.env if env is None else env)

    def run_hook(self, repo: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        return run_hook(repo, env=self.env if env is None else env)

    def assert_no_temp_snapshots(self):
        for temp_root in self.temp_roots:
            self.assertEqual(list(temp_root.glob("crm-precommit.*")), [],
                             f"hook leaked a temporary snapshot in {temp_root}")

    def run_cleanup(self, temp_root: Path, candidate: str, status: int) -> subprocess.CompletedProcess:
        """Exercise the actual cleanup function with controlled path/status inputs."""
        text = HOOK.read_text(encoding="utf-8")
        cleanup = text[text.index("cleanup() {"):text.index("trap cleanup EXIT")]
        # Python supplies Windows paths; normalize them to the hook's shell view.
        script = ('set -eu\ntmp_root=$1\ntmp_base=$2\nrepo_root=$3\n'
                  'if command -v cygpath >/dev/null 2>&1; then\n'
                  '    tmp_root=$(cygpath -u "$tmp_root")\n'
                  '    [ -z "$tmp_base" ] || tmp_base=$(cygpath -u "$tmp_base")\n'
                  '    repo_root=$(cygpath -u "$repo_root")\n'
                  'fi\n'
                  'tmp_root=$(CDPATH= cd -P "$tmp_root" && pwd -P)\n' + cleanup +
                  'trap cleanup EXIT\nexit "$4"\n')
        return subprocess.run([SH_PATH, "-c", script, "cleanup-test", str(temp_root.resolve()),
                               candidate, str(self.repo), str(status)], cwd=self.repo,
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=self.env, timeout=30)

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

    def shell_command_path(self, command: str) -> str:
        if command == "git":
            return GIT_PATH
        # Prefer POSIX utilities beside Git's sh over Windows find.exe.
        beside_sh = Path(SH_PATH).parent / (command + ".exe")
        if os.name == "nt" and beside_sh.is_file():
            return beside_sh.as_posix()
        script = ('p=$(command -v "$1") || exit 1\n'
                  'if command -v cygpath >/dev/null 2>&1; then cygpath -m "$p"; '
                  'else printf "%s\\n" "$p"; fi\n')
        proc = subprocess.run([SH_PATH, "-c", script, "resolve-command", command],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=self.env, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return Path(proc.stdout.strip()).as_posix()

    def controlled_environment(self, env: dict[str, str], shim_dir: Path) -> dict[str, str]:
        """One bin directory, no host Python dirs, and only explicit utilities.

        Existing fault/interpreter shims win. Wrappers work in MSYS without
        symlink privileges; Python uses an absolute path. sh stays off PATH.
        """
        commands = ("git", "mktemp", "mkdir", "find", "sort", "cmp", "diff", "grep", "sed", "rm", "cat")
        for command in commands:
            shim = shim_dir / command
            if not shim.exists():
                real = shlex.quote(self.shell_command_path(command))
                shim.write_text(f'#!/bin/sh\nexec {real} "$@"\n', encoding="utf-8", newline="\n")
                shim.chmod(0o755)
        if os.name == "nt":
            cygpath = shim_dir / "cygpath"
            cygpath.write_text(f'#!/bin/sh\nexec {shlex.quote(self.shell_command_path("cygpath"))} "$@"\n',
                               encoding="utf-8", newline="\n")
            cygpath.chmod(0o755)
        for command in ("python3", "python", "py"):
            shim = shim_dir / command
            if not shim.exists():
                body = f'exec {shlex.quote(Path(sys.executable).as_posix())} "$@"\n' if command == "python3" else "exit 127\n"
                shim.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
                shim.chmod(0o755)
        controlled = env.copy()
        controlled["PATH"] = str(shim_dir)
        return controlled

    def require_git_runner_shims(self, env: dict[str, str], shim_dir: Path, commands) -> None:
        """Probe git's actual hook runner, without committing or running faults."""
        probe_dir = Path(self.tmp.name) / (shim_dir.name + "-probe")
        probe_dir.mkdir()
        script = (f'#!/bin/sh\nexpected={shlex.quote(shim_dir.as_posix())}\n'
                  'if command -v cygpath >/dev/null 2>&1; then expected=$(cygpath -u "$expected"); fi\n')
        for command in commands:
            script += (f'p=$(command -v {command}) || p=MISSING\n'
                       'if [ "$p" != MISSING ] && command -v cygpath >/dev/null 2>&1; then p=$(cygpath -u "$p"); fi\n'
                       f'if [ "$p" != "$expected/{command}" ]; then\n'
                       f'  echo "SKIPPED_CAPABILITY: git hook runner resolves {command} to $p instead of the injected shim" >&2\n'
                       '  exit 78\nfi\n')
        script += 'echo SHIMS_RESOLVED\n'
        probe = probe_dir / "pre-commit"
        probe.write_text(script, encoding="utf-8", newline="\n")
        probe.chmod(0o755)
        result = self.git(self.repo, "-c", f"core.hooksPath={probe_dir}", "hook", "run", "pre-commit",
                          check=False, env=env)
        if result.returncode == 78 and "SKIPPED_CAPABILITY: git hook runner resolves" in result.stderr:
            self.skipTest(result.stderr.strip())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SHIMS_RESOLVED", result.stdout + result.stderr)

    @requires_sh
    def test_15_no_working_python_rejects_real_commit(self):
        """Unavailable interpreters must fail closed under git's actual hook runner."""
        env = self.hook_environment("no-python-temp")
        shim_dir = self.interpreter_shims("no-python-bin")
        env = self.controlled_environment(env, shim_dir)
        extra = self.repo / "MARKER.md"
        extra.write_text("pending\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "MARKER.md")
        before_head = self.git(self.repo, "rev-parse", "HEAD").stdout
        before_index = self.git(self.repo, "write-tree").stdout
        direct = self.run_hook(self.repo, env=env)
        self.assertNotEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        self.assertIn("no working python3/python/py -3", direct.stderr)
        self.assertIn("commit aborted", direct.stderr)
        self.assertEqual(before_head, self.git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual(before_index, self.git(self.repo, "write-tree").stdout)
        self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])
        self.require_git_runner_shims(env, shim_dir, ("python3", "python", "py"))
        blocked = self.git(self.repo, "commit", "-m", "must reject without Python",
                      check=False, env=env)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("no working python3/python/py -3", blocked.stderr)
        self.assertIn("commit aborted", blocked.stderr)
        self.assertNotIn("SKIPPED", blocked.stderr)
        self.assertEqual(before_head, self.git(self.repo, "rev-parse", "HEAD").stdout)
        self.assertEqual(before_index, self.git(self.repo, "write-tree").stdout)
        self.assertEqual(extra.read_text(encoding="utf-8"), "pending\n")
        self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [],
                         "missing Python must abort before exporting the staged tree")

    @requires_sh
    def test_16_cleanup_refuses_invalid_paths_and_preserves_status(self):
        temp_root = Path(self.env["TMPDIR"])
        outside = Path(self.tmp.name) / "guard-data"
        outside.mkdir()
        foreign = outside / "crm-precommit.foreign"
        foreign.mkdir()
        marker = foreign / "keep.txt"
        marker.write_text("outside survives\n", encoding="utf-8")
        wrong_prefix = temp_root / "sentinel-directory"
        wrong_prefix.mkdir()
        regular_file = temp_root / "sentinel-file"
        regular_file.write_text("file survives\n", encoding="utf-8")
        link = outside / "crm-precommit.link"
        try:
            link.symlink_to(foreign, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"SKIPPED_CAPABILITY: cannot create a directory symlink: {exc}")
        candidates = ["", str(temp_root / "missing"), str(regular_file),
                      str(link), str(foreign), str(wrong_prefix)]
        for candidate in candidates:
            for status in (0, 1):
                with self.subTest(path=candidate, status=status):
                    result = self.run_cleanup(temp_root, candidate, status)
                    self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                    self.assertIn("WARNING - cleanup refused", result.stderr)
                    self.assertTrue(foreign.is_dir())
                    self.assertTrue(wrong_prefix.is_dir())
                    self.assertTrue(link.is_symlink())
                    self.assertEqual(marker.read_text(encoding="utf-8"), "outside survives\n")
                    self.assertEqual(regular_file.read_text(encoding="utf-8"), "file survives\n")
        self.assert_no_temp_snapshots()

    @requires_sh
    def test_17_successful_commit_cleans_only_its_own_snapshot(self):
        env = self.hook_environment("cleanup-success")
        temp_root = Path(env["TMPDIR"])
        sentinel = temp_root / "sentinel.txt"
        sentinel.write_text("retain me\n", encoding="utf-8")
        sentinel_dir = temp_root / "sentinel-directory"
        sentinel_dir.mkdir()
        (sentinel_dir / "keep.txt").write_text("directory survives\n", encoding="utf-8")
        outside = Path(self.tmp.name) / "outside-success"
        outside.mkdir()
        (outside / "keep.txt").write_text("external survives\n", encoding="utf-8")
        link = temp_root / "external-link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"SKIPPED_CAPABILITY: cannot create a directory symlink: {exc}")
        build = self.repo / "tools" / "build_bundle.py"
        build.write_text(FAKE_BUILD +
                         "(root.parent/'unexpected.txt').write_text('temporary', encoding='utf-8')\n" +
                         f"(root.parent/'external-link').symlink_to({str(outside)!r}, target_is_directory=True)\n",
                         encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "tools/build_bundle.py")
        before_head = self.git(self.repo, "rev-parse", "HEAD").stdout
        allowed = self.git(self.repo, "commit", "-m", "cleanup success", check=False, env=env)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertNotEqual(self.git(self.repo, "rev-parse", "HEAD").stdout, before_head)
        self.assertNotIn("WARNING", allowed.stderr)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "retain me\n")
        self.assertEqual((sentinel_dir / "keep.txt").read_text(encoding="utf-8"), "directory survives\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), outside.resolve())
        self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "external survives\n")
        self.assertEqual({p.name for p in temp_root.iterdir()},
                         {"sentinel.txt", "sentinel-directory", "external-link"})
        self.assert_no_temp_snapshots()

    @requires_sh
    def test_18_cleanup_preserves_build_failure(self):
        build = self.repo / "tools" / "build_bundle.py"
        build.write_text("import sys\nsys.exit(3)\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "tools/build_bundle.py")
        env = self.hook_environment("cleanup-failure")
        before_head = self.git(self.repo, "rev-parse", "HEAD").stdout
        blocked = self.git(self.repo, "commit", "-m", "cleanup failure", check=False, env=env)
        self.assertEqual(blocked.returncode, 1, blocked.stdout + blocked.stderr)
        self.assertIn("staged copy) exited non-zero", blocked.stderr)
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD").stdout, before_head)
        self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])
        self.assertEqual(self.gen.read_text(encoding="utf-8"), "canonical\n")

    @requires_sh
    def test_19_working_python_and_py_launcher_fallbacks(self):
        for candidate in ("python", "py"):
            with self.subTest(interpreter=candidate):
                env = self.hook_environment("fallback-temp-" + candidate)
                shim_dir = self.interpreter_shims("fallback-bin-" + candidate, working=candidate)
                env = self.controlled_environment(env, shim_dir)
                allowed = self.run_hook(self.repo, env=env)
                self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
                self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])

    @requires_sh
    def test_20_cleanup_failure_warns_without_changing_verdict(self):
        shim_dir = Path(self.tmp.name) / "cleanup-bin"
        shim_dir.mkdir()
        shim = shim_dir / "rm"
        shim.write_text("#!/bin/sh\nexit 71\n", encoding="utf-8", newline="\n")
        shim.chmod(0o755)
        build = self.repo / "tools" / "build_bundle.py"
        for status in (0, 1):
            with self.subTest(verdict=status):
                env = self.hook_environment("rm-failure-" + str(status))
                env = self.controlled_environment(env, shim_dir)
                build.write_text(FAKE_BUILD if status == 0 else "import sys\nsys.exit(3)\n",
                                 encoding="utf-8", newline="\n")
                self.git(self.repo, "add", "tools/build_bundle.py")
                result = self.run_hook(self.repo, env=env)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertIn("WARNING - cleanup failed for temporary directory", result.stderr)
                snapshots = list(Path(env["TMPDIR"]).glob("crm-precommit.*"))
                self.assertEqual(len(snapshots), 1)
                # Retry the hook's guarded cleanup with the real rm, never delete manually.
                retry = self.run_cleanup(Path(env["TMPDIR"]), str(snapshots[0]), status)
                self.assertEqual(retry.returncode, status, retry.stdout + retry.stderr)
                self.assertNotIn("WARNING", retry.stderr)
                self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])

    @requires_sh
    def test_22_hash_and_enumeration_failures_reject_real_commit_without_mutation(self):
        marker = self.repo / "MARKER.md"
        marker.write_text("staged\n", encoding="utf-8", newline="\n")
        lock = self.repo / "prompt-bundles.lock"
        lock.write_text("synthetic lock\n", encoding="utf-8", newline="\n")
        self.git(self.repo, "add", "MARKER.md", "prompt-bundles.lock")
        marker.write_text("unstaged user bytes\n", encoding="utf-8", newline="\n")
        def snapshot():
            return {p.relative_to(self.repo).as_posix(): p.read_bytes()
                    for p in sorted(self.repo.rglob("*")) if p.is_file() and ".git" not in p.parts}
        before_head = self.git(self.repo, "rev-parse", "HEAD").stdout
        before_index = self.git(self.repo, "write-tree").stdout
        before_tree = snapshot()
        # git calls 1/2 hash the generated file/lock before build; 3/4 after build.
        for command, failure_call in [("git", n) for n in (1, 2, 3, 4)] + [(c, n) for c in ("find", "sort") for n in (1, 2)]:
            with self.subTest(command=command, failure_call=failure_call):
                name = f"fault-{command}-{failure_call}"
                env = self.hook_environment(name + "-temp")
                bin_dir = Path(self.tmp.name) / (name + "-bin")
                bin_dir.mkdir()
                counter = Path(self.tmp.name) / (name + "-count")
                real = shlex.quote(self.shell_command_path(command))
                count_file = shlex.quote(counter.as_posix())
                body = "#!/bin/sh\n"
                if command == "git":
                    body += f'case " $* " in *" hash-object "*) ;; *) exec {real} "$@" ;; esac\n'
                body += (f"n=0\n[ ! -f {count_file} ] || n=$(cat {count_file})\n"
                         f"n=$((n + 1))\nprintf '%s\\n' \"$n\" > {count_file}\n"
                         f"[ \"$n\" -ne {failure_call} ] || exit 71\n"
                         f'exec {real} "$@"\n')
                shim = bin_dir / command
                shim.write_text(body, encoding="utf-8", newline="\n")
                shim.chmod(0o755)
                env = self.controlled_environment(env, bin_dir)
                # git prepends its exec-path to hook PATH; put the fault shim there too.
                if command == "git":
                    env["GIT_EXEC_PATH"] = str(bin_dir)
                direct = self.run_hook(self.repo, env=env)
                self.assertNotEqual(direct.returncode, 0, direct.stdout + direct.stderr)
                self.assertIn("FAILED", direct.stderr)
                self.assertEqual(before_head, self.git(self.repo, "rev-parse", "HEAD").stdout)
                self.assertEqual(before_index, self.git(self.repo, "write-tree").stdout)
                self.assertEqual(before_tree, snapshot())
                self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])
                counter.write_text("0\n", encoding="utf-8", newline="\n")
                self.require_git_runner_shims(env, bin_dir, (command,))
                blocked = self.git(self.repo, "commit", "-m", name, check=False, env=env)
                self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
                self.assertIn("FAILED", blocked.stderr)
                self.assertEqual(before_head, self.git(self.repo, "rev-parse", "HEAD").stdout)
                self.assertEqual(before_index, self.git(self.repo, "write-tree").stdout)
                self.assertEqual(before_tree, snapshot())
                self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])

    @requires_sh
    @unittest.skipUnless(os.name == "posix", "SKIPPED_CAPABILITY: POSIX signal delivery required")
    def test_21_interrupts_clean_snapshot_and_exit_nonzero(self):
        build = self.repo / "tools" / "build_bundle.py"
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=signum.name):
                env = self.hook_environment("signal-" + signum.name)
                build.write_text(FAKE_BUILD + "import os, signal\n" +
                                 f"os.kill(os.getppid(), signal.{signum.name})\n",
                                 encoding="utf-8", newline="\n")
                self.git(self.repo, "add", "tools/build_bundle.py")
                result = self.run_hook(self.repo, env=env)
                self.assertEqual(result.returncode, 128 + signum, result.stdout + result.stderr)
                self.assertNotIn("WARNING", result.stderr)
                self.assertEqual(list(Path(env["TMPDIR"]).iterdir()), [])

    @requires_sh
    def test_22_symlinked_temp_root_is_resolved_before_creation(self):
        env = self.hook_environment("physical-root")
        alias = Path(self.tmp.name) / "temp-root-alias"
        try:
            alias.symlink_to(Path(env["TMPDIR"]), target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"SKIPPED_CAPABILITY: cannot create a directory symlink: {exc}")
        env["TMPDIR"] = str(alias)
        result = self.run_hook(self.repo, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("WARNING", result.stderr)
        self.assertTrue(alias.is_symlink())
        self.assert_no_temp_snapshots()


    @requires_sh
    def test_23_absolute_shell_works_without_sh_on_path(self):
        bin_dir = Path(self.tmp.name) / "no-sh-bin"
        bin_dir.mkdir()
        env = self.controlled_environment(self.hook_environment("no-sh-temp"), bin_dir)
        self.assertIsNone(shutil.which("sh", path=env["PATH"]))
        self.assertTrue(Path(SH_PATH).is_absolute())
        result = self.run_hook(self.repo, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_24_windows_shell_resolution_prefers_git_and_falls_back(self):
        install = Path(self.tmp.name) / "Git with spaces"
        exec_path = install / "mingw64" / "libexec" / "git-core"
        exec_path.mkdir(parents=True)
        fallback = Path(self.tmp.name) / "fallback-sh"
        fallback.write_bytes(b"synthetic")
        for location in ("usr/bin/sh.exe", "bin/sh.exe"):
            shell = install / location
            shell.parent.mkdir(parents=True, exist_ok=True)
            shell.write_bytes(b"synthetic")
        for chosen in ("usr/bin/sh.exe", "bin/sh.exe", None):
            with self.subTest(chosen=chosen):
                selected = str((install / chosen).resolve()) if chosen else str(fallback.resolve())
                def probe(args, **kwargs):
                    if args == [GIT_PATH, "--exec-path"]:
                        return subprocess.CompletedProcess(args, 0, str(exec_path) + "\n", "")
                    return subprocess.CompletedProcess(args, 0 if args[0] == selected else 1,
                                                       "crm-posix-sh" if args[0] == selected else "", "")
                with patch("shutil.which", return_value=str(fallback)), patch("subprocess.run", side_effect=probe):
                    self.assertEqual(resolve_posix_sh(windows=True), selected)

    def test_25_wsl_bash_is_never_a_shell_fallback(self):
        with patch("shutil.which", return_value=None) as which, \
             patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            self.assertIsNone(resolve_posix_sh(windows=True))
        which.assert_called_once_with("sh")

    def test_26_windows_direct_shell_path_preserves_controlled_environment(self):
        # Keep the host Path implementation while mocking Windows on macOS.
        host_path = type(Path())
        for index, (layout, has_mingw) in enumerate(
                (("usr/bin", True), ("usr/bin", False), ("bin", True))):
            with self.subTest(layout=layout, mingw64=has_mingw):
                install = Path(self.tmp.name) / f"Git with spaces {index}"
                shell_dir = install / layout
                shell_dir.mkdir(parents=True)
                shell = shell_dir / "sh.exe"
                shell.write_bytes(b"synthetic shell")
                mingw = install / "mingw64" / "bin"
                if has_mingw:
                    mingw.mkdir(parents=True)
                home_bin = Path(self.tmp.name) / "user-home" / "bin"
                original_path = str(install / "cmd") + ";C:/Windows/System32"
                shim_dir = self.interpreter_shims(f"layout-shims-{index}")
                fault = shim_dir / "find"
                fault.write_text("#!/bin/sh\nexit 71\n", encoding="utf-8", newline="\n")
                expected_path = ";".join([str(shell_dir)] +
                                         ([str(mingw)] if has_mingw else []) + [original_path])
                probe = subprocess.CompletedProcess([], 0, str(shell_dir / "probe-tool.exe") + "\n", "")
                with patch("os.name", "nt"), patch("os.pathsep", ";"), \
                     patch(f"{__name__}.Path", host_path), \
                     patch(f"{__name__}.SH_PATH", str(shell)), \
                     patch.dict(os.environ, {"PATH": original_path, "HOME": str(home_bin.parent)}), \
                     patch("subprocess.run", return_value=probe) as run:
                    run_hook(self.repo)
                    default_env = run.call_args.kwargs["env"]
                    self.assertIsNotNone(default_env, "direct hooks must prepare their default PATH")
                    self.assertEqual(default_env["PATH"], expected_path)
                    self.assertNotIn(str(home_bin), default_env["PATH"].split(";"))
                    env = self.hook_environment(f"layout-temp-{index}")
                    self.assertEqual(env["PATH"], expected_path)
                    with patch.object(self, "env", env):
                        self.run_hook(self.repo)
                        self.assertEqual(run.call_args.kwargs["env"]["PATH"], expected_path)
                        self.run_cleanup(Path(env["TMPDIR"]), "", 0)
                        self.assertEqual(run.call_args.kwargs["env"]["PATH"], expected_path)
                        self.shell_command_path("probe-tool")
                        self.assertEqual(run.call_args.kwargs["env"]["PATH"], expected_path)
                    with patch.object(self, "shell_command_path",
                                      side_effect=lambda command: str(shell_dir / (command + ".exe"))):
                        controlled = self.controlled_environment(env, shim_dir)
                    self.assertEqual(controlled["PATH"], str(shim_dir))
                    self.assertEqual(fault.read_text(encoding="utf-8"), "#!/bin/sh\nexit 71\n")
                    for candidate in ("python3", "python", "py"):
                        self.assertEqual((shim_dir / candidate).read_text(encoding="utf-8"),
                                         "#!/bin/sh\nexit 127\n")
                    self.assertIn(shlex.quote(str(shell_dir / "mktemp.exe")),
                                  (shim_dir / "mktemp").read_text(encoding="utf-8"))
                    run_hook(self.repo, env=controlled)
                    self.assertIs(run.call_args.kwargs["env"], controlled)
                    self.assertEqual(os.environ["PATH"], original_path,
                                     "PATH preparation must not modify the host environment")
        with patch("os.name", "posix"):
            self.assertEqual(direct_shell_environment(), os.environ.copy())


if __name__ == "__main__":
    unittest.main(verbosity=2)
