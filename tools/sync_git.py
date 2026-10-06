#!/usr/bin/env python3
"""Two-way sync between this working tree and origin, inside the project root only.

Scope and non-claims:
- Grants no privilege. It cannot widen IDE, host, OS, Git or SSH rights. It only
  reads and writes files under --root. Read-only production boundaries in
  policies/runtime-contract.json are untouched by this tool.
- Dry run by default. Nothing is written, staged, committed or pushed without
  --apply plus an explicit --confirm token.
- Every planned write/delete/merge is recorded in an append-only JSONL ledger
  before it happens, and a run that fails mid-apply is rolled back.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import release_rules  # noqa: E402

# Paths that the build owns and regenerates from policy-source. Syncing these
# as ordinary files would let a remote copy overwrite generated truth, so they
# are only ever carried by a build, never applied file-by-file.
GENERATED_PREFIXES = ("agents/", "skills/", "templates/", "manual-mode/", "individual-packages/")
GENERATED_EXACT = {"prompt-bundles.lock"}
LEDGER_DIR = "reports"
PLAN_SUFFIX = ".sync-plan.json"


class SyncError(RuntimeError):
    """Raised for any condition that must abort before or during a write."""


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    return digest_bytes(path.read_bytes())


# --------------------------------------------------------------------------- git

def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["GIT_SSH_COMMAND"] = env.get(
        "GIT_SSH_COMMAND",
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15",
    )
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
    )
    if check and proc.returncode != 0:
        raise SyncError(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def git_bytes(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Binary-safe git. Text mode would corrupt PNG/ZIP payloads via newline translation."""
    env = dict(os.environ)
    env["GIT_SSH_COMMAND"] = env.get(
        "GIT_SSH_COMMAND",
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15",
    )
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, env=env,
    )
    if check and proc.returncode != 0:
        raise SyncError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc


def merge_base(root: Path, local: str, remote: str) -> str | None:
    proc = git(root, "merge-base", local, remote, check=False)
    base = proc.stdout.strip()
    return base or None


def rev_parse(root: Path, ref: str) -> str | None:
    proc = git(root, "rev-parse", "--verify", "--quiet", ref, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def ahead_behind(root: Path, local: str, remote: str) -> tuple[int, int]:
    """Divergence between the two tips, not between a base and one tip.

    `rev-list --left-right --count local...remote` reports local-only commits on
    the left and remote-only commits on the right. Measuring base..local would
    always report the remote side as empty and silently hide real conflicts.
    """
    proc = git(root, "rev-list", "--left-right", "--count", f"{local}...{remote}")
    parts = proc.stdout.split()
    if len(parts) != 2:
        raise SyncError(f"Cannot compute divergence for {local}...{remote}")
    return int(parts[1]), int(parts[0])  # behind, ahead


def dirty_paths(root: Path) -> list[str]:
    out = git(root, "status", "--porcelain=v1", "-z").stdout
    names = []
    for entry in out.split("\0"):
        if len(entry) > 3:
            rel = entry[3:].replace("\\", "/")
            if (root / rel).is_file():
                names.append(rel)
    return sorted(set(names))


def untracked_paths(root: Path) -> list[str]:
    out = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    names = []
    for rel in out.split("\0"):
        if not rel:
            continue
        rel = rel.replace("\\", "/")
        # ls-files reports untracked directories; sync deals in files only.
        if not (root / rel).is_file():
            continue
        names.append(rel)
    return sorted(names)


# ------------------------------------------------------------------- path guards

def is_generated(rel: str) -> bool:
    return rel in GENERATED_EXACT or rel.startswith(GENERATED_PREFIXES)


def is_link_like(path: Path) -> bool:
    """True for symlinks and Windows junctions.

    `Path.is_symlink()` returns False for a directory junction, so a junction
    would pass the walk below and then redirect writes outside the project.
    """
    if path.is_symlink():
        return True
    if os.name == "nt":
        try:
            if hasattr(os.path, "isjunction"):
                return os.path.isjunction(path)
        except OSError:
            return False
    return False


def guard_path(root: Path, rel: str) -> Path:
    """Resolve one repo-relative path and prove it stays inside the project root."""
    if not isinstance(rel, str) or not rel:
        raise SyncError("Empty path")
    if "\\" in rel or "\x00" in rel or ":" in rel or rel.startswith("/"):
        raise SyncError(f"Unsafe path: {rel}")
    pure = PurePosixPath(rel)
    if pure.is_absolute() or any(p in {"", ".", ".."} for p in rel.split("/")):
        raise SyncError(f"Path traversal rejected: {rel}")
    # Case-fold: NTFS is case-insensitive, so `.GIT` is a real `.git` directory.
    forbidden = {p.casefold() for p in release_rules.FORBIDDEN_PARTS}
    if any(p.casefold() in forbidden for p in pure.parts):
        raise SyncError(f"Forbidden path segment: {rel}")
    target = root / pure
    probe = target
    while True:
        if is_link_like(probe):
            raise SyncError(f"Symlink or junction rejected: {rel}")
        if probe == root or root not in probe.parents:
            break
        probe = probe.parent
    resolved_root = root.resolve()
    if target.exists() and not target.resolve().is_relative_to(resolved_root):
        raise SyncError(f"Path escapes project root: {rel}")
    return target


def mergeable_json(root: Path, rel: str) -> bool:
    """Only canonical data files get structural merge; prompts stay whole-file."""
    if not rel.endswith(".json"):
        return False
    try:
        json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return rel in {"release-manifest.json", "source-baseline.json", "source-provenance.json",
                   "policies/limits.json", "policies/runtime-contract.json", "manual-team-config.json"}


# ------------------------------------------------------------------ plan and merge

def build_plan(root: Path, local: str, remote: str) -> dict:
    """Classify every divergence without touching the working tree."""
    base = merge_base(root, local, remote)
    behind, ahead = (ahead_behind(root, local, remote) if base else (0, 0))
    plan = {
        "schema_version": 1,
        "scope": "WORKING_TREE_VS_REMOTE_INSIDE_PROJECT_ROOT_NO_PRIVILEGE_CHANGE",
        "local_ref": local,
        "remote_ref": remote,
        # Tip SHAs bind the plan to exact reviewed bytes. If either ref moves
        # between the dry run and --apply, the confirmation token must not match.
        "local_tip": rev_parse(root, local),
        "remote_tip": rev_parse(root, remote),
        "base_ref": base,
        "behind": behind,
        "ahead": ahead,
        "in_sync": behind == 0 and ahead == 0 and not dirty_paths(root),
        "remote_ahead": [],
        "local_ahead": [],
        "blocked_generated": [],
        "untracked_local": [],
        "conflicts": [],
        "actions": [],
    }
    # `--name-only` silently drops mode-only changes, so collect names from `--raw -z`.
    # With -z the record is NUL separated: a status field, then one path for
    # A/M/D/T and two (src, dst) for R/C. Line splitting would corrupt names that
    # contain tabs, and ignoring the extra field would silently drop renames.
    if not plan["in_sync"]:
        for ref, key in ((local, "local_ahead"), (remote, "remote_ahead")):
            raw = git_bytes(root, "diff", "--raw", "-z", f"{base}..{ref}" if base else ref,
                            check=False).stdout
            fields = [f.decode("utf-8", "surrogateescape") for f in raw.split(b"\0") if f]
            index = 0
            while index < len(fields):
                meta = fields[index].split()
                index += 1
                if not meta:
                    continue
                status = meta[-1]
                paths = 2 if status[:1] in {"R", "C"} else 1
                for rel in fields[index:index + paths]:
                    if rel and rel != base:
                        plan[key].append(rel)
                index += paths
    both = sorted(set(plan["local_ahead"]) & set(plan["remote_ahead"]))
    for rel in both:
        # git show would emit the commit object too; cat-file gives the exact blob.
        local_blob = git_bytes(root, "cat-file", "blob", f"{local}:{rel}", check=False)
        remote_blob = git_bytes(root, "cat-file", "blob", f"{remote}:{rel}", check=False)
        if local_blob.returncode != 0 or remote_blob.returncode != 0:
            plan["conflicts"].append({"path": rel, "reason": "BLOB_UNREADABLE"})
            continue
        # File mode lives outside the blob, so a 100755-vs-100644 split would look
        # identical by bytes alone and silently lose the executable bit.
        local_mode = git(root, "ls-tree", local, "--", rel, check=False).stdout.split()[:1]
        remote_mode = git(root, "ls-tree", remote, "--", rel, check=False).stdout.split()[:1]
        if local_blob.stdout == remote_blob.stdout and local_mode == remote_mode:
            continue  # converged to identical bytes and mode, nothing to reconcile
        reason = "DIVERGED_BOTH_SIDES" if local_blob.stdout != remote_blob.stdout else "MODE_ONLY_DIVERGENCE"
        plan["conflicts"].append({
            "path": rel,
            "reason": reason,
            "strategy": "STRUCTURAL_JSON_MERGE" if rel.endswith(".json") else "EXPLICIT_RESCOLUTION_REQUIRED",
        })
    untracked = set(untracked_paths(root))
    conflicted = {c["path"] for c in plan["conflicts"]}
    # Untracked local files are part of the divergence too; omitting them here
    # would let a plan look clean while new work sat unsynced.
    for rel in sorted(set(plan["local_ahead"]) | set(plan["remote_ahead"])
                      | set(dirty_paths(root)) | untracked):
        if is_generated(rel):
            plan["blocked_generated"].append({"path": rel, "reason": "BUILD_OWNED_OUTPUT_RUN_BUILD_BUNDLE"})
            continue
        target = guard_path(root, rel)
        if target.is_dir():
            # git tracks files; an untracked empty directory carries no bytes to sync.
            continue
        local_sha = digest_file(target)
        if rel in conflicted:
            # Both sides moved and disagree: never auto-resolve, never overwrite.
            action = "BLOCKED_CONFLICT_REQUIRES_RESOLUTION"
        elif rel in untracked and rel not in plan["remote_ahead"]:
            action = "LOCAL_NEW_UNDECLARED"
        elif rel in plan["remote_ahead"] and rel not in plan["local_ahead"]:
            # Remote moved and the local side never diverged: safe to take remote bytes.
            remote_bytes = git_bytes(root, "cat-file", "blob", f"{remote}:{rel}", check=False)
            same = remote_bytes.returncode == 0 and local_sha == digest_bytes(remote_bytes.stdout)
            action = "NOOP_ALREADY_IDENTICAL" if same else "RESTORE_REMOTE_VERSION"
        elif rel in plan["local_ahead"] and rel not in plan["remote_ahead"]:
            action = "KEEP_LOCAL_PUSH_LATER"
        elif rel not in plan["remote_ahead"] and rel not in plan["local_ahead"]:
            action = "REVIEW_DIRTY_WORKTREE"
        else:
            action = "RECONCILE"
        plan["actions"].append({"path": rel, "action": action, "planned_sha256": local_sha})
    plan["untracked_local"] = sorted(n for n in untracked if not is_generated(n))
    for rel in plan["untracked_local"]:
        guard_path(root, rel)
    for rel in sorted(n for n in untracked if is_generated(n)):
        plan["blocked_generated"].append({"path": rel, "reason": "BUILD_OWNED_OUTPUT_RUN_BUILD_BUNDLE"})
    return plan


def three_way_merge_json(base_text: str, local_text: str, remote_text: str) -> tuple[str | None, list[str]]:
    """Recursive dict merge. Lists and scalars are atomic; disagreement is reported."""
    conflicts: list[str] = []
    try:
        base = json.loads(base_text) if base_text else {}
        local = json.loads(local_text)
        remote = json.loads(remote_text)
    except ValueError as exc:
        return None, [f"JSON_PARSE_ERROR:{exc}"]
    if not all(isinstance(v, dict) for v in (base, local, remote)):
        if local == remote:
            return local_text, []
        return None, ["ROOT_NOT_OBJECT"]

    def merge(node_b, node_l, node_r, path):
        if node_l == node_r:
            return node_l
        if node_l == node_b:
            return node_r  # only remote moved
        if node_r == node_b:
            return node_l  # only local moved
        if isinstance(node_l, dict) and isinstance(node_r, dict) and isinstance(node_b, dict):
            out = dict(node_b)
            for key in sorted(set(node_l) | set(node_r) | set(node_b)):
                b, l, r = node_b.get(key), node_l.get(key), node_r.get(key)
                if l == r:
                    out[key] = l
                elif l == b:
                    out[key] = r
                elif r == b:
                    out[key] = l
                elif isinstance(l, dict) and isinstance(r, dict) and isinstance(b, dict):
                    out[key] = merge(b, l, r, f"{path}.{key}")
                else:
                    conflicts.append(f"{path}.{key}" if path else key)
                    out[key] = l
            return out
        conflicts.append(path or "<root>")
        return node_l

    merged = merge(base, local, remote, "")
    if conflicts:
        return None, conflicts
    return json.dumps(merged, ensure_ascii=False, indent=2) + "\n", []


# ------------------------------------------------------------------------ ledger

def ledger_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    return root / LEDGER_DIR / f"sync-ledger-{stamp}.jsonl"


def append_ledger(root: Path, record: dict) -> Path:
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **record}, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
    return path


# ------------------------------------------------------------------------- apply

def apply_plan(root: Path, plan: dict, confirm: str, remote: str, local: str) -> dict:
    if plan["conflicts"]:
        raise SyncError("Unresolved conflicts: " + ",".join(c["path"] for c in plan["conflicts"]))
    blocked = [a["path"] for a in plan["actions"] if a["action"] == "BLOCKED_CONFLICT_REQUIRES_RESOLUTION"]
    if blocked:
        raise SyncError("Blocked paths in plan: " + ",".join(blocked))
    if confirm != plan["plan_id"]:
        raise SyncError("Confirmation token does not match this plan; nothing was written")
    # The dry run reviewed specific bytes at specific tips. If a ref moved since,
    # those bytes are no longer what the operator approved, so refuse outright.
    for label, ref, planned in (("local", local, plan.get("local_tip")),
                                ("remote", remote, plan.get("remote_tip"))):
        current = rev_parse(root, ref)
        if planned and current != planned:
            raise SyncError(
                f"{label} ref moved after planning ({planned} -> {current}); "
                "re-run the dry run and confirm again")
    writable = [a for a in plan["actions"] if a["action"] == "RESTORE_REMOTE_VERSION"]
    if not writable:
        return {"written": [], "rolled_back": False, "note": "NOTHING_TO_WRITE"}
    # Compare against the digest captured at plan time, not a fresh read: reading
    # here would bless whatever is on disk now and defeat the drift check.
    before = {a["path"]: a.get("planned_sha256") for a in writable}
    backup = Path(tempfile.mkdtemp(prefix=".sync-backup-", dir=root))
    done: list[str] = []
    written_digest: dict[str, str | None] = {}
    ledger = None
    try:
        for rel in done_keys(writable):
            target = guard_path(root, rel)
            if digest_file(target) != before[rel]:
                # State changed since planning: this path is no longer the reviewed one.
                raise SyncError(f"{rel} changed on disk after planning; re-run the dry run")
            if target.exists():
                dest = backup / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(target, dest)
            blob = git_bytes(root, "cat-file", "blob", f"{remote}:{rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            # Stage next to the target and rename: a partial write can then only
            # leave a stray temp file, never a half-written file at the real path.
            staging = target.with_name(target.name + ".sync-part")
            staging.write_bytes(blob.stdout)
            os.replace(staging, target)
            done.append(rel)
            written_digest[rel] = digest_bytes(blob.stdout)
            ledger = ledger or append_ledger(root, {"run": plan["plan_id"], "event": "RUN_START",
                                                    "paths": [a["path"] for a in writable]})
            append_ledger(root, {"run": plan["plan_id"], "event": "WRITE", "path": rel,
                                 "sha256_before": before[rel],
                                 "sha256_after": digest_file(target)})
        # No git add/commit/push: staging and publishing stay explicit, separate decisions.
        append_ledger(root, {"run": plan["plan_id"], "event": "RUN_OK", "count": len(done)})
        return {"written": done, "rolled_back": False, "ledger": str(ledger), "staged": False}
    except BaseException as exc:
        # Restore only what this run wrote. A path that was absent at plan time but
        # appeared afterwards is user work, so it is left alone and reported.
        preserved: list[str] = []
        for rel in reversed(done):
            target = guard_path(root, rel)
            saved = backup / rel
            if saved.exists():
                restore = target.with_name(target.name + ".sync-restore")
                restore.write_bytes(saved.read_bytes())
                os.replace(restore, target)
            elif before[rel] is None and target.exists():
                if digest_file(target) == written_digest.get(rel):
                    target.unlink()
                else:
                    preserved.append(rel)
        append_ledger(root, {"run": plan["plan_id"], "event": "ROLLBACK", "error": str(exc),
                             "preserved_user_files": preserved})
        raise SyncError(f"Apply failed and was rolled back: {exc}") from exc
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def done_keys(writable: list[dict]) -> list[str]:
    return [a["path"] for a in writable]


# --------------------------------------------------------------------------- cli

def plan_id_of(plan: dict) -> str:
    body = {k: v for k, v in plan.items() if k != "in_sync"}
    return digest_bytes(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8"))[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--remote", default="origin/main")
    parser.add_argument("--local", default="HEAD")
    parser.add_argument("--apply", action="store_true", help="Perform writes. Without it the run is a dry run.")
    parser.add_argument("--confirm", help="plan_id echoed from the dry run; required with --apply")
    parser.add_argument("--fetch", action="store_true", help="git fetch the remote ref first")
    parser.add_argument("--output", type=Path, help="write the plan JSON here")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    try:
        if args.fetch:
            ref = args.remote
            if "/" in ref:
                remote_name, branch = ref.split("/", 1)
                git(root, "fetch", remote_name, branch)
            else:
                git(root, "fetch", ref)
        plan = build_plan(root, args.local, args.remote)
        plan["plan_id"] = plan_id_of(plan)
        payload = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8", newline="\n")
        print(payload, end="")
        if not args.apply:
            print(json.dumps({"mode": "DRY_RUN", "hint": f"rerun with --apply --confirm {plan['plan_id']}"},
                             ensure_ascii=False), file=sys.stderr)
            return
        result = apply_plan(root, plan, args.confirm or "", args.remote, args.local)
        print(json.dumps({"mode": "APPLY", **result}, ensure_ascii=False, indent=2))
    except (SyncError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"Sync aborted: {exc}") from exc


if __name__ == "__main__":
    main()
