"""Two-way sync guard tests. Real local git repos, synthetic data only.

Proves path containment, symlink refusal, dry-run default, confirmation gating,
build-owned output protection, JSON structural merge and rollback. It does not
prove anything about the real origin remote or any runtime privilege.
"""
from __future__ import annotations
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_git_under_test", ROOT / "tools/sync_git.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def _can_symlink() -> bool:
    try:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            t = p / "t"
            t.write_bytes(b"x")
            link = p / "l"
            link.symlink_to(t)
            return link.is_symlink()
    except OSError:
        return False


requires_real_symlink = unittest.skipUnless(
    _can_symlink(), "SKIPPED_CAPABILITY: real filesystem symlinks unavailable on this host")
requires_posix_mode = unittest.skipUnless(
    os.name == "posix", "SKIPPED_CAPABILITY: Windows does not implement POSIX executable bits/umask")


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


class SyncGuardTests(unittest.TestCase):
    def setUp(self):
        # Synthetic repositories must not inherit the host's line endings,
        # signing, hooks, filters or URL rewrites. Never inspect credentials.
        self.git_config = patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_COUNT": "0",
            "GIT_ATTR_NOSYSTEM": "1", "GIT_CONFIG_PARAMETERS": "",
        })
        self.git_config.start()
        self.addCleanup(self.git_config.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.origin = self.base / "origin.git"
        self.clone = self.base / "clone"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.origin)], check=True,
                       capture_output=True)
        git(self.origin, "config", "core.autocrlf", "false")
        seed = self.base / "seed"
        seed.mkdir()
        git(seed, "init", "-b", "main")
        git(seed, "config", "core.autocrlf", "false")
        git(seed, "config", "user.email", "sync@test.invalid")
        git(seed, "config", "user.name", "sync-test")
        (seed / "policy-source").mkdir()
        (seed / "policy-source" / "common.md").write_text("base\n", encoding="utf-8", newline="\n")
        (seed / "settings.json").write_text('{"agent":"lead"}\n', encoding="utf-8", newline="\n")
        (seed / "VERSION").write_text("1.0.0\n", encoding="utf-8", newline="\n")
        git(seed, "add", "-A")
        git(seed, "commit", "-m", "base")
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-u", "origin", "main")
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(self.clone)], check=True, capture_output=True)
        git(self.clone, "config", "user.email", "sync@test.invalid")
        git(self.clone, "config", "user.name", "sync-test")

    # --------------------------------------------------------- path containment
    def test_01_traversal_and_absolute_paths_rejected(self):
        for bad in ("../escape.md", "/etc/passwd", "a/../../b.md", "..\\win.md", "", "C:/x.md"):
            with self.subTest(path=bad), self.assertRaises(sync.SyncError):
                sync.guard_path(self.clone, bad)

    def test_02_forbidden_segments_rejected(self):
        for bad in (".git/config", "a/__pycache__/x.pyc", "reports/out.txt", "node_modules/p/i.js"):
            with self.subTest(path=bad), self.assertRaises(sync.SyncError):
                sync.guard_path(self.clone, bad)

    @requires_real_symlink
    def test_03_symlink_target_rejected(self):
        outside = self.base / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8", newline="\n")
        (self.clone / "link.md").symlink_to(outside)
        with self.assertRaises(sync.SyncError):
            sync.guard_path(self.clone, "link.md")

    def test_04_valid_path_resolves_inside_root(self):
        self.assertTrue(sync.guard_path(self.clone, "policy-source/common.md").is_relative_to(self.clone.resolve()))

    # ------------------------------------------------------------ dry-run default
    def test_05_dry_run_writes_nothing(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        (self.clone / "VERSION").write_text("2.0.0\n", encoding="utf-8", newline="\n")
        git(self.clone, "commit", "-am", "local change")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        self.assertEqual(sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")["written"], [])
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "2.0.0\n")

    def test_06_apply_without_confirm_token_writes_nothing(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        (self.clone / "VERSION").write_text("3.0.0\n", encoding="utf-8", newline="\n")
        git(self.clone, "commit", "-am", "local change")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, "wrong-token", "origin/main", "HEAD")
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "3.0.0\n")

    def test_07_wrong_confirm_token_writes_nothing(self):
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, "deadbeef", "origin/main", "HEAD")

    # ------------------------------------------------------ build-owned outputs
    def test_08_generated_outputs_never_planned_for_sync(self):
        for rel in ("agents/lead.md", "skills/x/SKILL.md", "templates/t.md",
                    "manual-mode/README.md", "individual-packages/x/skill.zip", "prompt-bundles.lock"):
            with self.subTest(path=rel):
                self.assertTrue(sync.is_generated(rel))
        self.assertFalse(sync.is_generated("policy-source/prompts/common.md"))
        self.assertFalse(sync.is_generated("tools/sync_git.py"))

    def test_09_untracked_generated_file_is_blocked(self):
        (self.clone / "agents").mkdir()
        (self.clone / "agents" / "new.md").write_text("x\n", encoding="utf-8", newline="\n")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        blocked = {b["path"] for b in plan["blocked_generated"]}
        self.assertIn("agents/new.md", blocked)
        self.assertNotIn("agents/new.md", plan["untracked_local"])

    def test_10_untracked_new_source_flagged_not_silently_dropped(self):
        (self.clone / "tools").mkdir(parents=True, exist_ok=True)
        (self.clone / "tools" / "brand_new.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertIn("tools/brand_new.py", plan["untracked_local"])
        actions = {a["path"]: a["action"] for a in plan["actions"]}
        self.assertEqual(actions.get("tools/brand_new.py"), "LOCAL_NEW_UNDECLARED")
        # The parent directory is not itself a syncable path.
        self.assertNotIn("tools/", actions)

    # ------------------------------------------------------------- plan accuracy
    def test_11_identical_trees_report_in_sync(self):
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertTrue(plan["in_sync"])
        self.assertEqual(plan["conflicts"], [])
        self.assertEqual(plan["behind"], 0)
        self.assertEqual(plan["ahead"], 0)

    def test_12_divergence_counts_and_diverged_conflict(self):
        (self.clone / "VERSION").write_text("local\n", encoding="utf-8", newline="\n")
        git(self.clone, "commit", "-am", "local edit")
        other = self.base / "other"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote\n", encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote edit")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["behind"], 1)
        self.assertEqual(plan["ahead"], 1)
        self.assertEqual([c["path"] for c in plan["conflicts"]], ["VERSION"])
        self.assertEqual(plan["conflicts"][0]["strategy"], "EXPLICIT_RESCOLUTION_REQUIRED")

    def test_13_unresolved_conflict_blocks_apply(self):
        (self.clone / "VERSION").write_text("local\n", encoding="utf-8", newline="\n")
        git(self.clone, "commit", "-am", "local edit")
        other = self.base / "other2"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote\n", encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote edit")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "local\n")

    def test_14_binary_payload_survives_restore(self):
        payload = bytes(range(256)) * 8
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        other = self.base / "other3"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "logo.png").write_bytes(payload)
        git(other, "add", "-A")
        git(other, "commit", "-m", "add binary")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        git(self.clone, "reset", "--hard", "HEAD")
        git(self.clone, "clean", "-fd")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["conflicts"], [])
        self.assertIn("logo.png", plan["remote_ahead"])
        plan["plan_id"] = sync.plan_id_of(plan)
        result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertIn("logo.png", result["written"])
        self.assertEqual((self.clone / "logo.png").read_bytes(), payload)

    def test_15_apply_does_not_stage_anything(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        other = self.base / "other4"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "settings.json").write_text('{"agent":"lead","x":1}\n', encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote settings")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertFalse(result["staged"])
        self.assertEqual(git(self.clone, "diff", "--cached", "--name-only").strip(), "")
        self.assertEqual(json.loads((self.clone / "settings.json").read_text(encoding="utf-8"))["x"], 1)

    def test_16_ledger_records_every_write(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        other = self.base / "other5"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("9.9.9\n", encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote version")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        records = [json.loads(l) for l in Path(result["ledger"]).read_text(encoding="utf-8").splitlines() if l]
        kinds = [r["event"] for r in records]
        self.assertIn("RUN_START", kinds)
        self.assertIn("WRITE", kinds)
        self.assertIn("RUN_OK", kinds)
        write = next(r for r in records if r["event"] == "WRITE")
        self.assertEqual(write["path"], "VERSION")
        self.assertEqual(write["sha256_after"], sync.digest_bytes(b"9.9.9\n"))

    def test_17_ledger_dir_is_excluded_from_release(self):
        self.assertIn("reports", sync.release_rules.FORBIDDEN_PARTS)

    # --------------------------------------------------------------- json merge
    def test_18_three_way_json_merge_disjoint_keys(self):
        merged, conflicts = sync.three_way_merge_json(
            '{"a":1,"b":2}', '{"a":1,"b":2,"local":true}', '{"a":1,"b":2,"remote":true}')
        self.assertEqual(conflicts, [])
        self.assertEqual(json.loads(merged), {"a": 1, "b": 2, "local": True, "remote": True})

    def test_19_three_way_json_merge_same_key_conflicts(self):
        merged, conflicts = sync.three_way_merge_json(
            '{"a":1}', '{"a":2}', '{"a":3}')
        self.assertIsNone(merged)
        self.assertEqual(conflicts, ["a"])

    def test_20_three_way_json_merge_is_idempotent_on_equal_sides(self):
        merged, conflicts = sync.three_way_merge_json('{"a":1}', '{"a":9}', '{"a":9}')
        self.assertEqual(conflicts, [])
        self.assertEqual(json.loads(merged), {"a": 9})

    def test_21_json_merge_rejects_non_object_root(self):
        merged, conflicts = sync.three_way_merge_json('[1]', '[2]', '[3]')
        self.assertIsNone(merged)
        self.assertEqual(conflicts, ["ROOT_NOT_OBJECT"])

    def test_22_json_merge_reports_parse_error(self):
        merged, conflicts = sync.three_way_merge_json('{"a":1}', "{broken", '{"a":1}')
        self.assertIsNone(merged)
        self.assertTrue(conflicts[0].startswith("JSON_PARSE_ERROR"))

    def test_23_prompt_files_are_not_structurally_merged(self):
        self.assertFalse(sync.mergeable_json(self.clone, "VERSION"))
        (self.clone / "release-manifest.json").write_text('{"files":[]}', encoding="utf-8", newline="\n")
        self.assertTrue(sync.mergeable_json(self.clone, "release-manifest.json"))

    # ---------------------------------------------------------- plan_id integrity
    def test_24_plan_id_changes_when_plan_changes(self):
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        first = sync.plan_id_of(plan)
        plan["actions"].append({"path": "x.md", "action": "RECONCILE"})
        self.assertNotEqual(first, sync.plan_id_of(plan))

    def test_25_rollback_restores_previous_bytes_on_failure(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        other = self.base / "other6"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote-only\n", encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote version")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        before = (self.clone / "VERSION").read_text(encoding="utf-8")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        original = sync.git_bytes

        def exploding_git_bytes(root, *args, **kwargs):
            if args and args[0] == "cat-file" and args[-1].endswith("VERSION"):
                raise sync.SyncError("simulated transport failure")
            return original(root, *args, **kwargs)

        sync.git_bytes = exploding_git_bytes
        self.addCleanup(setattr, sync, "git_bytes", original)
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), before)

    def test_26_scope_declares_no_privilege_change(self):
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertIn("NO_PRIVILEGE_CHANGE", plan["scope"])

    def test_27_readonly_boundary_policy_is_not_a_sync_target(self):
        policy = ROOT / "policies" / "runtime-contract.json"
        self.assertTrue(policy.is_file())
        self.assertFalse(sync.is_generated("policies/runtime-contract.json"))
        data = json.loads(policy.read_text(encoding="utf-8"))
        self.assertEqual(data["read_only_boundary"]["production_write"], "SEPARATE_CHANGE_APPROVAL_REQUIRED")
        self.assertEqual(data["production_tools"], [])
        self.assertFalse(data["production_executor"])

    # ------------------------------------------------- tip binding after planning
    def _remote_edit(self, name: str, text: str, message: str = "remote edit"):
        other = self.base / name
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text(text, encoding="utf-8", newline="\n")
        git(other, "commit", "-am", message)
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        return other

    def test_28_plan_records_both_tip_shas(self):
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["local_tip"], git(self.clone, "rev-parse", "HEAD").strip())
        self.assertEqual(plan["remote_tip"], git(self.clone, "rev-parse", "origin/main").strip())

    def test_29_apply_refuses_when_remote_tip_moved_after_planning(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        self._remote_edit("tipmove", "remote-v1\n", "first")
        git(self.clone, "reset", "--hard", "HEAD")
        git(self.clone, "clean", "-fd")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        stale_tip = plan["remote_tip"]
        # Someone else pushes again after the operator reviewed the dry run.
        self._remote_edit("tipmove2", "remote-v2\n", "second")
        with self.assertRaises(sync.SyncError) as ctx:
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertIn("moved after planning", str(ctx.exception))
        self.assertNotIn("remote-v2", (self.clone / "VERSION").read_text(encoding="utf-8"))
        self.assertNotEqual(stale_tip, sync.rev_parse(self.clone, "origin/main"))

    def test_30_apply_refuses_when_file_changed_on_disk_after_planning(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        self._remote_edit("diskchange", "remote-bytes\n", "remote change")
        git(self.clone, "reset", "--hard", "HEAD")
        git(self.clone, "clean", "-fd")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        # The operator edits the very file the plan intends to overwrite.
        (self.clone / "VERSION").write_text("my-own-edit\n", encoding="utf-8", newline="\n")
        with self.assertRaises(sync.SyncError) as ctx:
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertIn("changed on disk", str(ctx.exception))
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "my-own-edit\n")

    # ------------------------------------------------------ windows / case issues
    def test_31_forbidden_segment_match_is_case_insensitive(self):
        for bad in (".GIT/config", "a/Reports/out.txt", "DIST/x.zip", "A/__PyCache__/m.pyc"):
            with self.subTest(path=bad), self.assertRaises(sync.SyncError):
                sync.guard_path(self.clone, bad)

    @unittest.skipUnless(os.name == "nt", "POSIX: no junction concept")
    def test_32_windows_junction_rejected(self):
        outside = self.base / "outside_dir"
        outside.mkdir()
        (outside / "target.md").write_text("escaped\n", encoding="utf-8", newline="\n")
        junction = self.clone / "linked"
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                           check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("SKIPPED_CAPABILITY: junction creation not permitted")
        try:
            self.assertTrue(junction.is_dir(), "mklink succeeded but junction is absent")
            self.assertTrue(sync.release_rules.is_link(junction), "junction was not identified as a reparse point")
            for rel in ("linked/target.md", "linked/nonexistent.md"):
                with self.subTest(path=rel), self.assertRaises(sync.SyncError):
                    sync.guard_path(self.clone, rel)
        finally:
            if junction.is_dir():
                junction.rmdir()

    # ------------------------------------------------------------- mode divergence
    def test_33_mode_only_divergence_is_reported_as_conflict(self):
        # A Windows checkout normalizes 100755 to 100644, so a mode-only split
        # cannot be reproduced from a real clone on this host. Drive the detector
        # directly instead: the planner compares ls-tree mode, and this pins that
        # a mode difference is classified as a conflict rather than silently ignored.
        root = self.clone
        payload = b"#!/bin/sh\necho hi\n"
        script = root / "run.sh"
        script.write_bytes(payload)
        git(root, "add", "run.sh")
        git(root, "commit", "-m", "add script")
        blob = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:run.sh"],
                              capture_output=True, check=True).stdout.decode().strip()
        base = git(root, "rev-parse", "HEAD").strip()
        base_mode = git(root, "ls-tree", base, "--", "run.sh").split()[0]

        def tree_with(mode: str) -> str:
            subprocess.run(["git", "-C", str(root), "read-tree", base], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "update-index", "--add", "--cacheinfo",
                            f"{mode},{blob},run.sh"], check=True, capture_output=True)
            return subprocess.run(["git", "-C", str(root), "write-tree"], capture_output=True,
                                  check=True).stdout.decode().strip()

        # Git has exactly two file modes, so a symmetric two-sided mode split cannot
        # be constructed: with both sides flipped they agree, and with one side
        # flipped it is an ordinary one-sided pull, not a conflict. What matters and
        # is asserted here is that a mode-only change is still surfaced as a
        # divergence (remote_ahead), and that byte-identical sides are not.
        flipped = "100755" if base_mode == "100644" else "100644"
        for label, local_mode, remote_mode in (("mode only", flipped, base_mode),
                                               ("identical", base_mode, base_mode)):
            with self.subTest(case=label):
                local_commit = git(root, "commit-tree", tree_with(local_mode), "-p", base,
                                   "-m", "local").strip()
                remote_commit = git(root, "commit-tree", tree_with(remote_mode), "-p", base,
                                    "-m", "remote").strip()
                plan = sync.build_plan(root, local_commit, remote_commit)
                divergent = set(plan["local_ahead"]) | set(plan["remote_ahead"])
                if label == "mode only":
                    self.assertIn("run.sh", divergent,
                                  f"mode-only change was not reported as a divergence: {plan}")
                else:
                    self.assertNotIn("run.sh", divergent, f"unexpected divergence: {plan}")
                    self.assertEqual([c["path"] for c in plan["conflicts"]], [])

    def test_34_identical_bytes_and_identical_mode_are_not_a_conflict(self):
        script = self.clone / "run.sh"
        script.write_text("same\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "run.sh")
        git(self.clone, "commit", "-m", "add run.sh")
        git(self.clone, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual([c["path"] for c in plan["conflicts"]], [])

    # --------------------------------------------------- rollback keeps user work
    def test_35_rollback_does_not_delete_file_created_after_planning(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        other = self.base / "rb1"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote-bytes\n", encoding="utf-8", newline="\n")
        (other / "fresh.md").write_text("remote-fresh\n", encoding="utf-8", newline="\n")
        git(other, "add", "-A")
        git(other, "commit", "-m", "remote adds two")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        original = sync.git_bytes
        calls = {"n": 0}

        def fail_on_second_blob(root, *args, **kwargs):
            if args and args[0] == "cat-file":
                calls["n"] += 1
                if calls["n"] > 1:
                    raise sync.SyncError("simulated failure on the second file")
            return original(root, *args, **kwargs)

        sync.git_bytes = fail_on_second_blob
        self.addCleanup(setattr, sync, "git_bytes", original)
        # The operator creates this file after planning; rollback must not touch it.
        (self.clone / "fresh.md").write_text("user-created-after-planning\n", encoding="utf-8", newline="\n")
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual((self.clone / "fresh.md").read_text(encoding="utf-8"),
                         "user-created-after-planning\n")


    def test_36_rename_records_both_source_and_destination(self):
        """`--raw -z` must not drop renames: the source path still needs syncing."""
        original = self.clone / "old-name.md"
        original.write_text("rename me\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "old-name.md")
        git(self.clone, "commit", "-m", "add old name")
        git(self.clone, "mv", "old-name.md", "new-name.md")
        git(self.clone, "commit", "-m", "rename it")
        plan = sync.build_plan(self.clone, "HEAD", "HEAD~1")
        divergent = set(plan["local_ahead"]) | set(plan["remote_ahead"])
        self.assertIn("new-name.md", divergent)
        self.assertIn("old-name.md", divergent)

    def test_37_non_ascii_path_is_parsed_correctly(self):
        """Byte-level -z parsing must survive names that are not plain ASCII."""
        unicode_name = self.clone / "配置说明.md"
        unicode_name.write_text("unicode\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-m", "add unicode name")
        plan = sync.build_plan(self.clone, "HEAD", "HEAD~1")
        divergent = set(plan["local_ahead"]) | set(plan["remote_ahead"])
        self.assertIn("配置说明.md", divergent)

    def test_38_write_is_atomic_leaving_no_partial_file(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        self._remote_edit("atomic", "remote-atomic\n", "remote atomic")
        git(self.clone, "reset", "--hard", "HEAD")
        git(self.clone, "clean", "-fd")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertIn("VERSION", result["written"])
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "remote-atomic\n")
        # No staging or restore residue may survive a successful run.
        leftovers = [p.name for p in self.clone.rglob("*.sync-*")]
        self.assertEqual(leftovers, [], f"staging residue left behind: {leftovers}")

    def test_39_confirm_token_cannot_be_forged_for_a_stale_plan(self):
        """A token computed for one plan must not authorize a different write set."""
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        self._remote_edit("forge", "remote-forge\n", "remote forge")
        git(self.clone, "reset", "--hard", "HEAD")
        git(self.clone, "clean", "-fd")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        # Forge a token over a plan whose planned_sha256 blesses the clobber.
        forged = json.loads(json.dumps(plan))
        forged["actions"] = [{"path": "VERSION", "action": "RESTORE_REMOTE_VERSION",
                              "planned_sha256": sync.digest_file(self.clone / "VERSION")}]
        forged["conflicts"] = []
        forged_id = sync.plan_id_of(forged)
        self.assertNotEqual(forged_id, plan["plan_id"])
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, forged, forged_id, "origin/main", "HEAD")
        self.assertNotEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "remote-forge\n")

    def test_40_plain_directory_is_not_treated_as_link_like(self):
        """The guard must consult os.path.isjunction without flagging ordinary dirs."""
        self.assertFalse(sync.is_link_like(self.clone))
        self.assertFalse(sync.is_link_like(self.base))
        self.assertFalse(sync.is_link_like(self.clone / "policy-source"))

    def assert_uncommitted_remote_conflict(self, rel):
        head = git(self.clone, "rev-parse", "HEAD")
        index = git(self.clone, "write-tree")
        before = {p.relative_to(self.clone).as_posix(): p.read_bytes()
                  for p in sorted(self.clone.rglob("*")) if p.is_file() and ".git" not in p.parts}
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        self.assertIn({"path": rel, "reason": "LOCAL_UNCOMMITTED_CHANGE"}, plan["conflicts"])
        action = next(a for a in plan["actions"] if a["path"] == rel)
        self.assertEqual(action["action"], "BLOCKED_CONFLICT_REQUIRES_RESOLUTION")
        for field in ("head_state", "index_state", "worktree_state", "remote_state"):
            self.assertIn(field, action)
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(head, git(self.clone, "rev-parse", "HEAD"))
        self.assertEqual(index, git(self.clone, "write-tree"))
        self.assertEqual(before, {p.relative_to(self.clone).as_posix(): p.read_bytes()
                                 for p in sorted(self.clone.rglob("*")) if p.is_file() and ".git" not in p.parts})

    def test_41_remote_change_blocks_existing_unstaged_modification(self):
        self._remote_edit("dirty-remote", "remote\n")
        (self.clone / "VERSION").write_text("user work\n", encoding="utf-8", newline="\n")
        self.assert_uncommitted_remote_conflict("VERSION")

    def test_42_deleted_worktree_path_is_dirty_and_blocks_remote_restore(self):
        self._remote_edit("deleted-remote", "remote\n")
        target = self.clone / "VERSION"
        self.assertTrue(target.is_file())
        target.unlink()  # Synthetic deletion input, never the real project.
        self.assertIn("VERSION", sync.dirty_paths(self.clone))
        self.assert_uncommitted_remote_conflict("VERSION")

    def test_43_untracked_same_name_as_new_remote_file_is_blocked(self):
        other = self._remote_edit("untracked-remote", "remote\n")
        (other / "new.md").write_text("remote new\n", encoding="utf-8", newline="\n")
        git(other, "add", "new.md")
        git(other, "commit", "-m", "remote new file")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        (self.clone / "new.md").write_text("user new\n", encoding="utf-8", newline="\n")
        self.assert_uncommitted_remote_conflict("new.md")

    def test_44_staged_change_blocks_even_if_worktree_matches_head(self):
        self._remote_edit("staged-remote", "remote\n")
        target = self.clone / "VERSION"
        before = target.read_bytes()
        target.write_text("staged user work\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "VERSION")
        target.write_bytes(before)
        self.assert_uncommitted_remote_conflict("VERSION")

    def test_45_index_change_after_plan_blocks_apply_without_clobber(self):
        self._remote_edit("index-drift", "remote\n")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        target = self.clone / "VERSION"
        before = target.read_bytes()
        target.write_text("staged only\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "VERSION")
        target.write_bytes(before)
        index = git(self.clone, "write-tree")
        with self.assertRaisesRegex(sync.SyncError, "Index changed after planning"):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(git(self.clone, "write-tree"), index)

    def test_46_fixed_staging_and_restore_names_are_never_overwritten(self):
        self._remote_edit("fixed-files", "remote\n")
        sentinels = [self.clone / "VERSION.sync-part", self.clone / "VERSION.sync-restore"]
        for target in sentinels:
            target.write_bytes(b"user sentinel")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual((self.clone / "VERSION").read_bytes(), b"remote\n")
        for target in sentinels:
            self.assertEqual(target.read_bytes(), b"user sentinel")

    @requires_real_symlink
    def test_47_fixed_staging_links_created_after_plan_cannot_escape(self):
        self._remote_edit("fixed-links", "remote\n")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        outside = self.base / "outside-sentinel"
        outside.write_bytes(b"outside unchanged")
        for name in ("VERSION.sync-part", "VERSION.sync-restore"):
            (self.clone / name).symlink_to(outside)
        sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(outside.read_bytes(), b"outside unchanged")
        self.assertTrue((self.clone / "VERSION.sync-part").is_symlink())

    def test_48_incomplete_rollback_preserves_original_backup(self):
        other = self._remote_edit("rollback-fault", "remote\n")
        (other / "settings.json").write_text('{"remote":true}\n', encoding="utf-8", newline="\n")
        git(other, "commit", "-am", "remote settings")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        before = (self.clone / "VERSION").read_bytes()
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        original = sync.atomic_replace
        calls = []
        def fail_after_first(*args):
            calls.append(args[1])
            if len(calls) >= 2:
                raise OSError("synthetic disk failure on apply and restore")
            return original(*args)
        with patch.object(sync, "atomic_replace", side_effect=fail_after_first):
            with self.assertRaisesRegex(sync.SyncError, "rollback incomplete.*backup retained"):
                sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        backups = list((self.clone / "reports").glob("sync-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "VERSION").read_bytes(), before)
        self.assertEqual(calls, ["VERSION", "settings.json", "VERSION"])

    def test_49_python_311_reparse_fallback_rejects_missing_descendant(self):
        junction = self.clone / "reparse"
        junction.mkdir()
        original = Path.lstat
        def lstat(path, *args, **kwargs):
            if path == junction:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return original(path, *args, **kwargs)
        with patch.object(Path, "is_junction", return_value=False, create=True), patch.object(Path, "lstat", lstat):
            self.assertTrue(sync.is_link_like(junction))
            with self.assertRaises(sync.SyncError):
                sync.guard_path(self.clone, "reparse/nonexistent.md")

    def test_50_json_missing_keys_are_distinct_from_null(self):
        cases = [
            ({"a": 1, "b": 2}, {"b": 2}, {"a": 1, "b": 3}, {"b": 3}, []),
            ({"a": 1}, {}, {"a": None}, None, ["a"]),
            ({"a": None}, {}, {"a": None}, {}, []),
            ({"a": 1}, {}, {"a": 2}, None, ["a"]),
            ({"a": 1}, {}, {}, {}, []),
            ({}, {"a": None}, {}, {"a": None}, []),
            ({}, {"a": None}, {"a": 1}, None, ["a"]),
            ({"outer": {"a": None, "b": 1}}, {"outer": {"b": 1}},
             {"outer": {"a": None, "b": 2}}, {"outer": {"b": 2}}, []),
        ]
        for base, local, remote, expected, errors in cases:
            for left, right in ((local, remote), (remote, local)):
                with self.subTest(base=base, local=left, remote=right):
                    merged, conflicts = sync.three_way_merge_json(*(json.dumps(v) for v in (base, left, right)))
                    self.assertEqual(conflicts, errors)
                    if errors:
                        self.assertIsNone(merged)
                    else:
                        self.assertEqual(json.loads(merged), expected)

    def test_51_dirty_rename_includes_original_and_destination(self):
        git(self.clone, "mv", "VERSION", "RENAMED.md")
        self.assertIn("VERSION", sync.dirty_paths(self.clone))
        self.assertIn("RENAMED.md", sync.dirty_paths(self.clone))

    @requires_posix_mode
    def test_52_atomic_replace_preserves_existing_read_write_bits(self):
        target = self.clone / "VERSION"
        for before, remote, expected in ((0o755, "100755", 0o755),
                                         (0o644, "100644", 0o644),
                                         (0o640, "100755", 0o751),
                                         (0o775, "100644", 0o664)):
            with self.subTest(before=oct(before), remote=remote):
                target.chmod(before)
                sync.atomic_replace(self.clone, "VERSION", b"restored\n", sync.digest_file(target), remote)
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), expected)
                self.assertEqual(target.read_bytes(), b"restored\n")

    @requires_posix_mode
    def test_53_new_file_permissions_follow_umask(self):
        for mask, expected in ((0o022, 0o644), (0o027, 0o640), (0o077, 0o600)):
            with self.subTest(umask=oct(mask)):
                old_mask = os.umask(mask)
                try:
                    rel = f"new-{mask}.txt"
                    sync.atomic_replace(self.clone, rel, b"new\n", None, "100644")
                finally:
                    os.umask(old_mask)
                self.assertEqual(stat.S_IMODE((self.clone / rel).stat().st_mode), expected)

    @requires_posix_mode
    def test_54_remote_mode_only_restore_converges_without_staging(self):
        # Match this project's reports/ exclusion in the synthetic repository.
        with (self.clone / ".git/info/exclude").open("a", encoding="utf-8") as handle:
            handle.write("\n/reports/\n")
        other = self.base / "mode-remote"
        subprocess.run(["git", "clone", "-c", "core.autocrlf=false", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "mode@test.invalid")
        git(other, "config", "user.name", "mode-test")
        git(self.clone, "config", "core.filemode", "true")
        git(other, "update-index", "--chmod=+x", "VERSION")
        git(other, "commit", "-m", "remote executable bit only")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        (self.clone / "VERSION").chmod(0o644)
        index = git(self.clone, "write-tree")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(result["written"], ["VERSION"])
        self.assertEqual(stat.S_IMODE((self.clone / "VERSION").stat().st_mode), 0o755)
        self.assertEqual(index, git(self.clone, "write-tree"))
        again = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(again["conflicts"], [])
        self.assertEqual(next(a["action"] for a in again["actions"] if a["path"] == "VERSION"),
                         "NOOP_ALREADY_IDENTICAL")
        again["plan_id"] = sync.plan_id_of(again)
        self.assertEqual(sync.apply_plan(self.clone, again, again["plan_id"], "origin/main", "HEAD")["written"], [])

    @requires_posix_mode
    def test_55_remote_nonexecutable_mode_removes_execute_bits(self):
        target = self.clone / "VERSION"
        target.chmod(0o755)
        git(self.clone, "add", "VERSION")
        git(self.clone, "commit", "-m", "executable baseline")
        git(self.clone, "push", "origin", "main")
        other = self._remote_edit("nonexec-remote", "new remote\n")
        git(other, "update-index", "--chmod=-x", "VERSION")
        git(other, "commit", "-m", "remote removes executable bit")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)
        self.assertEqual(target.read_bytes(), b"new remote\n")

    @requires_posix_mode
    def test_56_failed_apply_restores_original_permissions_and_bytes(self):
        other = self._remote_edit("mode-rollback", "remote\n")
        git(other, "update-index", "--chmod=+x", "VERSION")
        (other / "settings.json").write_text('{"remote":true}\n', encoding="utf-8", newline="\n")
        git(other, "add", "settings.json")
        git(other, "commit", "-m", "mode and settings")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        target = self.clone / "VERSION"
        target.chmod(0o640)
        before = target.read_bytes()
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        original = sync.atomic_replace
        calls = []
        def fail_on_second(*args):
            calls.append(args[1])
            if len(calls) == 2:
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o751)
                raise OSError("synthetic second-file failure")
            return original(*args)
        with patch.object(sync, "atomic_replace", side_effect=fail_on_second):
            with self.assertRaisesRegex(sync.SyncError, "was rolled back"):
                sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(calls, ["VERSION", "settings.json", "VERSION"])
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_57_json_type_changes_conflict_recursively(self):
        for before, left, right, key in (
            ({"a": 1}, {"a": True}, {"a": 2}, "a"),
            ({"a": 1}, {"a": 1.0}, {"a": 2}, "a"),
            ({"a": 0}, {"a": True}, {"a": 1}, "a"),
            ({"a": 0}, {"a": 1.0}, {"a": 1}, "a"),
            ({"a": {"b": 1}}, {"a": {"b": True}}, {"a": {"b": 2}}, "a.b"),
            ({"a": [{"b": 1}]}, {"a": [{"b": 1.0}]}, {"a": [{"b": 2}]}, "a"),
        ):
            for local, remote in ((left, right), (right, left)):
                with self.subTest(base=before, local=local, remote=remote):
                    merged, conflicts = sync.three_way_merge_json(*(json.dumps(v) for v in (before, local, remote)))
                    self.assertIsNone(merged)
                    self.assertEqual(conflicts, [key])

    def test_58_json_one_sided_type_change_is_preserved(self):
        for value in (True, 1.0):
            for local, remote in ((value, 1), (1, value)):
                with self.subTest(local=local, remote=remote):
                    merged, conflicts = sync.three_way_merge_json(
                        '{"a":1}', json.dumps({"a": local}), json.dumps({"a": remote}))
                    self.assertEqual(conflicts, [])
                    self.assertIs(type(json.loads(merged)["a"]), type(value))

    def test_59_json_nonobject_roots_use_strict_equality(self):
        for left, right in (("true", "1"), ("1.0", "1"), ("[true]", "[1]"), ("[{\"a\":1.0}]", "[{\"a\":1}]")):
            with self.subTest(left=left, right=right):
                self.assertEqual(sync.three_way_merge_json("[]", left, right), (None, ["ROOT_NOT_OBJECT"]))
        self.assertEqual(sync.three_way_merge_json("[]", "[true]", "[true]"), ("[true]", []))

    def test_60_matching_remote_does_not_bypass_staged_conflict(self):
        self._remote_edit("identical-staged", "remote\n")
        (self.clone / "VERSION").write_text("remote\n", encoding="utf-8", newline="\n")
        git(self.clone, "add", "VERSION")
        self.assert_uncommitted_remote_conflict("VERSION")

    def test_61_atomic_replace_uses_binary_exclusive_nofollow_flags(self):
        target = self.clone / "VERSION"
        native_open = os.open
        native_binary = getattr(os, "O_BINARY", 0)
        native_nofollow = getattr(os, "O_NOFOLLOW", 0)
        # Exercise optional flags even on hosts that do not expose both of them.
        for emulate in (False, True):
            with self.subTest(emulate_missing_flags=emulate):
                binary = native_binary or ((1 << 28) if emulate else 0)
                nofollow = native_nofollow or ((1 << 29) if emulate else 0)
                synthetic = (binary if not native_binary else 0) | (nofollow if not native_nofollow else 0)

                def open_native(path, flags, mode):
                    return native_open(path, flags & ~synthetic, mode)

                with patch.object(sync.os, "O_BINARY", binary, create=True), \
                     patch.object(sync.os, "O_NOFOLLOW", nofollow, create=True), \
                     patch.object(sync.os, "open", side_effect=open_native) as opened:
                    sync.atomic_replace(self.clone, "VERSION", b"new\n", sync.digest_file(target))
                opened.assert_called_once()
                staging, flags, _ = opened.call_args.args
                self.assertEqual(staging.parent, target.parent)
                for required in (os.O_CREAT, os.O_EXCL, os.O_WRONLY, binary, nofollow):
                    self.assertEqual(flags & required, required)

    def test_62_corrupted_staging_is_retained_without_replacing_target(self):
        data = b"first\nsecond\n" + bytes(range(256)) * 8
        native_fdopen = os.fdopen
        for label, corrupted in (("crlf", data.replace(b"\n", b"\r\n")),
                                 ("truncated", data[:-1]),
                                 ("changed", b"X" + data[1:])):
            for exists in (False, True):
                with self.subTest(corruption=label, existing_target=exists):
                    rel = f"payload-{label}-{exists}.bin"
                    target = self.clone / rel
                    before = b"original\n"
                    if exists:
                        target.write_bytes(before)

                    @contextmanager
                    def corrupt_fdopen(fd, mode):
                        with native_fdopen(fd, mode) as handle:
                            native_write = handle.write
                            with patch.object(handle, "write", side_effect=lambda _: native_write(corrupted)):
                                yield handle

                    with patch.object(sync.os, "fdopen", side_effect=corrupt_fdopen), \
                         patch.object(sync.os, "replace", wraps=os.replace) as replaced:
                        with self.assertRaisesRegex(sync.SyncError, "digest mismatch.*temporary file retained"):
                            sync.atomic_replace(self.clone, rel, data, sync.digest_file(target))
                    replaced.assert_not_called()
                    if exists:
                        self.assertEqual(target.read_bytes(), before)
                    else:
                        self.assertFalse(target.exists())
                    staging = list(self.clone.glob(rel + ".sync-*"))
                    self.assertEqual(len(staging), 1)
                    self.assertEqual(staging[0].read_bytes(), corrupted)

    def test_63_atomic_replace_preserves_exact_payload_bytes(self):
        for index, data in enumerate((b"", b"LF\nCRLF\r\n\x1a\x00\xff", bytes(range(256)) * 8)):
            for exists in (False, True):
                with self.subTest(payload=index, existing_target=exists):
                    rel = f"exact-{index}-{exists}.bin"
                    target = self.clone / rel
                    if exists:
                        target.write_bytes(b"original\n")
                    sync.atomic_replace(self.clone, rel, data, sync.digest_file(target))
                    self.assertEqual(target.read_bytes(), data)
                    self.assertEqual(list(self.clone.glob(rel + ".sync-*")), [])

    def test_64_clean_crlf_is_not_a_local_change(self):
        self._remote_edit("crlf-clean", "remote\n")
        (self.clone / ".git" / "info" / "exclude").write_text(
            "reports/\n", encoding="utf-8", newline="\n")
        target = self.clone / "VERSION"
        for autocrlf, attributes in (("true", None), ("input", None),
                                    ("false", "VERSION text eol=lf\n"),
                                    ("false", "VERSION text eol=crlf\n")):
            with self.subTest(autocrlf=autocrlf, attributes=attributes):
                git(self.clone, "config", "core.autocrlf", autocrlf)
                if attributes:
                    (self.clone / ".gitattributes").write_text(
                        attributes, encoding="utf-8", newline="\n")
                target.write_bytes(b"1.0.0\r\n")
                head = git(self.clone, "rev-parse", "HEAD")
                index = git(self.clone, "write-tree")
                plan = sync.build_plan(self.clone, "HEAD", "origin/main")
                self.assertEqual(plan["conflicts"], [])
                action = next(a for a in plan["actions"] if a["path"] == "VERSION")
                self.assertEqual(action["action"], "RESTORE_REMOTE_VERSION")
                self.assertEqual(action["planned_sha256"], sync.digest_bytes(b"1.0.0\r\n"))
                self.assertEqual(target.read_bytes(), b"1.0.0\r\n")
                plan["plan_id"] = sync.plan_id_of(plan)
                result = sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
                self.assertEqual(result["written"], ["VERSION"])
                self.assertEqual(target.read_bytes(), b"remote\n")
                self.assertEqual(head, git(self.clone, "rev-parse", "HEAD"))
                self.assertEqual(index, git(self.clone, "write-tree"))

    def test_65_crlf_real_local_change_still_blocks(self):
        self._remote_edit("crlf-dirty", "remote\n")
        for autocrlf in ("true", "input"):
            with self.subTest(autocrlf=autocrlf):
                git(self.clone, "config", "core.autocrlf", autocrlf)
                (self.clone / "VERSION").write_bytes(b"real user edit\r\n")
                self.assert_uncommitted_remote_conflict("VERSION")

    def test_66_crlf_raw_disk_drift_after_plan_still_blocks(self):
        self._remote_edit("crlf-drift", "remote\n")
        git(self.clone, "config", "core.autocrlf", "true")
        target = self.clone / "VERSION"
        target.write_bytes(b"1.0.0\r\n")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["conflicts"], [])
        plan["plan_id"] = sync.plan_id_of(plan)
        # Git-equivalent bytes are still a different reviewed disk snapshot.
        target.write_bytes(b"1.0.0\n")
        with self.assertRaisesRegex(sync.SyncError, "changed on disk after planning"):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(target.read_bytes(), b"1.0.0\n")

    def test_67_custom_filter_is_rejected_before_execution(self):
        self._remote_edit("filter-reject", "remote\n")
        (self.clone / ".gitattributes").write_text(
            "VERSION filter=unsafe\n", encoding="utf-8", newline="\n")
        git(self.clone, "config", "filter.unsafe.clean", "exit 71")
        git(self.clone, "config", "filter.unsafe.required", "true")
        original = sync.git
        def no_status_before_guard(root, *args, **kwargs):
            self.assertNotIn("status", args, "status could execute the custom filter")
            return original(root, *args, **kwargs)
        with patch.object(sync, "git", side_effect=no_status_before_guard):
            with self.assertRaisesRegex(sync.SyncError, "Unsupported Git normalization.*filter"):
                sync.build_plan(self.clone, "HEAD", "origin/main")

    def test_68_encoding_requires_manual_review(self):
        self._remote_edit("encoding-reject", "remote\n")
        (self.clone / ".gitattributes").write_text(
            "VERSION working-tree-encoding=UTF-16\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(sync.SyncError, "Unsupported Git normalization.*working-tree-encoding"):
            sync.build_plan(self.clone, "HEAD", "origin/main")

    def test_69_plan_binds_the_bytes_that_were_normalized(self):
        self._remote_edit("normalization-race", "remote\n")
        git(self.clone, "config", "core.autocrlf", "true")
        target = self.clone / "VERSION"
        target.write_bytes(b"1.0.0\r\n")
        original = sync.git_bytes
        def change_after_hash(root, *args, **kwargs):
            result = original(root, *args, **kwargs)
            if args[:2] == ("hash-object", "--path=VERSION"):
                target.write_bytes(b"user edit during planning\r\n")
            return result
        with patch.object(sync, "git_bytes", side_effect=change_after_hash):
            plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["conflicts"], [])
        action = next(a for a in plan["actions"] if a["path"] == "VERSION")
        self.assertEqual(action["planned_sha256"], sync.digest_bytes(b"1.0.0\r\n"))
        plan["plan_id"] = sync.plan_id_of(plan)
        with self.assertRaisesRegex(sync.SyncError, "changed on disk after planning"):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual(target.read_bytes(), b"user edit during planning\r\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
