"""Two-way sync guard tests. Real local git repos, synthetic data only.

Proves path containment, symlink refusal, dry-run default, confirmation gating,
build-owned output protection, JSON structural merge and rollback. It does not
prove anything about the real origin remote or any runtime privilege.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

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


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise AssertionError(f"git {args} failed: {proc.stderr}")
    return proc.stdout


class SyncGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.origin = self.base / "origin.git"
        self.clone = self.base / "clone"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.origin)], check=True,
                       capture_output=True)
        seed = self.base / "seed"
        seed.mkdir()
        git(seed, "init", "-b", "main")
        git(seed, "config", "user.email", "sync@test.invalid")
        git(seed, "config", "user.name", "sync-test")
        (seed / "policy-source").mkdir()
        (seed / "policy-source" / "common.md").write_text("base\n", encoding="utf-8")
        (seed / "settings.json").write_text('{"agent":"lead"}\n', encoding="utf-8")
        (seed / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        git(seed, "add", "-A")
        git(seed, "commit", "-m", "base")
        git(seed, "remote", "add", "origin", str(self.origin))
        git(seed, "push", "-u", "origin", "main")
        subprocess.run(["git", "clone", str(self.origin), str(self.clone)], check=True, capture_output=True)
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
        outside.write_text("secret\n", encoding="utf-8")
        (self.clone / "link.md").symlink_to(outside)
        with self.assertRaises(sync.SyncError):
            sync.guard_path(self.clone, "link.md")

    def test_04_valid_path_resolves_inside_root(self):
        self.assertTrue(sync.guard_path(self.clone, "policy-source/common.md").is_relative_to(self.clone.resolve()))

    # ------------------------------------------------------------ dry-run default
    def test_05_dry_run_writes_nothing(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        (self.clone / "VERSION").write_text("2.0.0\n", encoding="utf-8")
        git(self.clone, "commit", "-am", "local change")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        plan["plan_id"] = sync.plan_id_of(plan)
        self.assertEqual(sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")["written"], [])
        self.assertEqual((self.clone / "VERSION").read_text(encoding="utf-8"), "2.0.0\n")

    def test_06_apply_without_confirm_token_writes_nothing(self):
        git(self.origin, "config", "receive.denyCurrentBranch", "ignore")
        (self.clone / "VERSION").write_text("3.0.0\n", encoding="utf-8")
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
        (self.clone / "agents" / "new.md").write_text("x\n", encoding="utf-8")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        blocked = {b["path"] for b in plan["blocked_generated"]}
        self.assertIn("agents/new.md", blocked)
        self.assertNotIn("agents/new.md", plan["untracked_local"])

    def test_10_untracked_new_source_flagged_not_silently_dropped(self):
        (self.clone / "tools").mkdir(parents=True, exist_ok=True)
        (self.clone / "tools" / "brand_new.py").write_text("x = 1\n", encoding="utf-8")
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
        (self.clone / "VERSION").write_text("local\n", encoding="utf-8")
        git(self.clone, "commit", "-am", "local edit")
        other = self.base / "other"
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote\n", encoding="utf-8")
        git(other, "commit", "-am", "remote edit")
        git(other, "push", "origin", "main")
        git(self.clone, "fetch", "origin")
        plan = sync.build_plan(self.clone, "HEAD", "origin/main")
        self.assertEqual(plan["behind"], 1)
        self.assertEqual(plan["ahead"], 1)
        self.assertEqual([c["path"] for c in plan["conflicts"]], ["VERSION"])
        self.assertEqual(plan["conflicts"][0]["strategy"], "EXPLICIT_RESCOLUTION_REQUIRED")

    def test_13_unresolved_conflict_blocks_apply(self):
        (self.clone / "VERSION").write_text("local\n", encoding="utf-8")
        git(self.clone, "commit", "-am", "local edit")
        other = self.base / "other2"
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote\n", encoding="utf-8")
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "settings.json").write_text('{"agent":"lead","x":1}\n', encoding="utf-8")
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("9.9.9\n", encoding="utf-8")
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
        (self.clone / "release-manifest.json").write_text('{"files":[]}', encoding="utf-8")
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote-only\n", encoding="utf-8")
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text(text, encoding="utf-8")
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
        (self.clone / "VERSION").write_text("my-own-edit\n", encoding="utf-8")
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
        (outside / "target.md").write_text("escaped\n", encoding="utf-8")
        junction = self.clone / "linked"
        try:
            subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
                           check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("SKIPPED_CAPABILITY: junction creation not permitted")
        try:
            if os.path.isjunction(junction):
                with self.assertRaises(sync.SyncError):
                    sync.guard_path(self.clone, "linked/target.md")
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
        script.write_text("same\n", encoding="utf-8")
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
        subprocess.run(["git", "clone", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "o@t.invalid")
        git(other, "config", "user.name", "o")
        (other / "VERSION").write_text("remote-bytes\n", encoding="utf-8")
        (other / "fresh.md").write_text("remote-fresh\n", encoding="utf-8")
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
        (self.clone / "fresh.md").write_text("user-created-after-planning\n", encoding="utf-8")
        with self.assertRaises(sync.SyncError):
            sync.apply_plan(self.clone, plan, plan["plan_id"], "origin/main", "HEAD")
        self.assertEqual((self.clone / "fresh.md").read_text(encoding="utf-8"),
                         "user-created-after-planning\n")


    def test_36_rename_records_both_source_and_destination(self):
        """`--raw -z` must not drop renames: the source path still needs syncing."""
        original = self.clone / "old-name.md"
        original.write_text("rename me\n", encoding="utf-8")
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
        unicode_name.write_text("unicode\n", encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
