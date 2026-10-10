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
import secrets
import shutil
import stat
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


def git_bytes(root: Path, *args: str, check: bool = True,
              input_data: bytes | None = None) -> subprocess.CompletedProcess:
    """Binary-safe git. Text mode would corrupt PNG/ZIP payloads via newline translation."""
    env = dict(os.environ)
    env["GIT_SSH_COMMAND"] = env.get(
        "GIT_SSH_COMMAND",
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15",
    )
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, env=env, input=input_data,
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
    out = git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z").stdout
    names = []
    entries = iter(out.split("\0"))
    for entry in entries:
        if len(entry) <= 3:
            continue
        names.append(entry[3:].replace("\\", "/"))
        if "R" in entry[:2] or "C" in entry[:2]:
            # Porcelain -z renames report destination, then original path.
            original = next(entries, "")
            if original:
                names.append(original.replace("\\", "/"))
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
    """Shared symlink/junction/reparse guard, including Python 3.11 lstat."""
    return release_rules.is_link(path)


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

def tree_entries(root: Path, ref: str) -> dict:
    entries = {}
    for record in git_bytes(root, "ls-tree", "-r", "-z", ref).stdout.split(b"\0"):
        if record:
            meta, name = record.split(b"\t", 1)
            mode, kind, blob = meta.decode("ascii").split()
            entries[name.decode("utf-8", "surrogateescape")] = (mode, kind, blob)
    return entries


def index_entries(root: Path) -> tuple[dict, str]:
    raw = git_bytes(root, "ls-files", "--stage", "-z").stdout
    entries = {}
    for record in raw.split(b"\0"):
        if record:
            meta, name = record.split(b"\t", 1)
            mode, blob, stage = meta.decode("ascii").split()
            rel = name.decode("utf-8", "surrogateescape")
            entries.setdefault(rel, []).append((mode, "blob", blob, stage))
    return entries, digest_bytes(raw)


def blob_state(root: Path, entry) -> dict | None:
    if entry is None:
        return None
    mode, kind, blob = entry[:3]
    if kind != "blob":
        raise SyncError("Non-blob sync input requires manual review")
    return {"mode": mode, "git_blob": blob,
            "sha256": digest_bytes(git_bytes(root, "cat-file", "blob", blob).stdout)}


def assert_supported_normalization(root: Path, paths) -> None:
    """Reject custom conversion before status/hash-object can execute a filter.

    Git's built-in text/eol/autocrlf rules are supported. External filters and
    working-tree encodings need manual review; raw blob restores do not run
    their smudge/re-encoding steps. check-attr itself never runs the filter.
    """
    names = sorted(set(paths))
    if not names:
        return
    raw = git_bytes(root, "check-attr", "-z", "--stdin", "filter", "working-tree-encoding",
                    input_data=b"".join(n.encode("utf-8", "surrogateescape") + b"\0" for n in names)).stdout
    fields = raw.split(b"\0")
    if fields[-1:] != [b""] or len(fields) - 1 != len(names) * 6:
        raise SyncError("Cannot safely read Git normalization attributes")
    for index in range(0, len(fields) - 1, 3):
        name, attribute, value = fields[index:index + 3]
        if value not in (b"unspecified", b"unset"):
            raise SyncError("Unsupported Git normalization: " +
                            name.decode("utf-8", "replace") + " " +
                            attribute.decode("ascii") + " requires manual review")


def working_state(root: Path, rel: str, target: Path,
                  index_state: dict | None, track_mode: bool) -> dict | None:
    if not target.exists():
        return None
    if not target.is_file():
        return {"mode": "directory", "sha256": None}
    mode = "100755" if track_mode and target.stat().st_mode & 0o111 else "100644"
    if not track_mode and index_state:
        mode = index_state["mode"]
    # No -w: dry-run hashes the same normalized bytes as git add without
    # writing an object or staging anything. Keep SHA256 over the disk bytes
    # separately so a later CRLF/LF-only change still invalidates the plan.
    data = target.read_bytes()
    blob = git_bytes(root, "hash-object", f"--path={rel}", "--stdin",
                     input_data=data).stdout.decode("ascii").strip()
    if len(blob) not in (40, 64) or any(c not in "0123456789abcdef" for c in blob):
        raise SyncError(f"Cannot safely normalize working-tree content: {rel}")
    return {"mode": mode, "git_blob": blob, "sha256": digest_bytes(data)}


def same_git_state(left: dict | None, right: dict | None) -> bool:
    if left is None or right is None:
        return left is right
    return (left["mode"], left.get("git_blob")) == (right["mode"], right.get("git_blob"))

def build_plan(root: Path, local: str, remote: str) -> dict:
    """Classify every divergence without touching the working tree."""
    base = merge_base(root, local, remote)
    behind, ahead = (ahead_behind(root, local, remote) if base else (0, 0))
    heads = tree_entries(root, "HEAD")
    remotes = tree_entries(root, remote)
    indices, index_digest = index_entries(root)
    untracked = set(untracked_paths(root))
    assert_supported_normalization(root, set(heads) | set(remotes) | set(indices) | untracked)
    dirty = set(dirty_paths(root))
    filemode = git(root, "config", "--bool", "core.filemode", check=False).stdout.strip() == "true"
    plan = {
        "schema_version": 1,
        "scope": "WORKING_TREE_VS_REMOTE_INSIDE_PROJECT_ROOT_NO_PRIVILEGE_CHANGE",
        "local_ref": local,
        "remote_ref": remote,
        # Tip SHAs bind the plan to exact reviewed bytes. If either ref moves
        # between the dry run and --apply, the confirmation token must not match.
        "local_tip": rev_parse(root, local),
        "head_tip": rev_parse(root, "HEAD"),
        "index_sha256": index_digest,
        "remote_tip": rev_parse(root, remote),
        "base_ref": base,
        "behind": behind,
        "ahead": ahead,
        "in_sync": behind == 0 and ahead == 0 and not dirty,
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
                            check=True).stdout
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
    conflicted = {c["path"] for c in plan["conflicts"]}
    # Untracked local files are part of the divergence too; omitting them here
    # would let a plan look clean while new work sat unsynced.
    for rel in sorted(set(plan["local_ahead"]) | set(plan["remote_ahead"])
                      | dirty | untracked):
        if is_generated(rel):
            plan["blocked_generated"].append({"path": rel, "reason": "BUILD_OWNED_OUTPUT_RUN_BUILD_BUNDLE"})
            continue
        target = guard_path(root, rel)
        if target.is_dir() and rel not in heads and rel not in remotes and rel not in indices:
            continue  # Porcelain may collapse an untracked directory; ls-files lists its files.
        head_state = blob_state(root, heads.get(rel))
        remote_state = blob_state(root, remotes.get(rel))
        stages = indices.get(rel, [])
        index_state = blob_state(root, stages[0]) if len(stages) == 1 and stages[0][3] == "0" else None
        worktree_state = working_state(root, rel, target, index_state, filemode)
        local_sha = worktree_state["sha256"] if worktree_state else None
        # status can retain a stat-dirty marker after an autocrlf/eol change.
        # The index-vs-HEAD and normalized worktree comparisons decide content;
        # untracked files, deletions, staged edits and mode changes still differ.
        has_uncommitted = (len(stages) > 1 or index_state != head_state
                           or not same_git_state(worktree_state, index_state))
        if (rel in plan["remote_ahead"] and rel not in plan["local_ahead"]
                and rel not in conflicted and len(stages) == 1 and stages[0][3] == "0"
                and index_state == head_state and same_git_state(worktree_state, remote_state)):
            # A previous restore leaves HEAD/index untouched. Matching remote
            # bytes AND mode need no further write; staged work still blocks.
            action = "NOOP_ALREADY_IDENTICAL"
        elif has_uncommitted and rel in plan["remote_ahead"]:
            plan["conflicts"].append({"path": rel, "reason": "LOCAL_UNCOMMITTED_CHANGE"})
            action = "BLOCKED_CONFLICT_REQUIRES_RESOLUTION"
        elif rel in conflicted:
            # Both sides moved and disagree: never auto-resolve, never overwrite.
            action = "BLOCKED_CONFLICT_REQUIRES_RESOLUTION"
        elif rel in untracked and rel not in plan["remote_ahead"]:
            action = "LOCAL_NEW_UNDECLARED"
        elif rel in plan["remote_ahead"] and rel not in plan["local_ahead"]:
            same = same_git_state(remote_state, worktree_state)
            action = "NOOP_ALREADY_IDENTICAL" if same else "RESTORE_REMOTE_VERSION"
        elif rel in plan["local_ahead"] and rel not in plan["remote_ahead"]:
            action = "KEEP_LOCAL_PUSH_LATER"
        elif rel not in plan["remote_ahead"] and rel not in plan["local_ahead"]:
            action = "REVIEW_DIRTY_WORKTREE"
        else:
            action = "RECONCILE"
        plan["actions"].append({"path": rel, "action": action, "planned_sha256": local_sha,
                                "head_state": head_state, "index_state": index_state,
                                "worktree_state": worktree_state, "remote_state": remote_state})
    plan["untracked_local"] = sorted(n for n in untracked if not is_generated(n))
    for rel in plan["untracked_local"]:
        guard_path(root, rel)
    for rel in sorted(n for n in untracked if is_generated(n)):
        plan["blocked_generated"].append({"path": rel, "reason": "BUILD_OWNED_OUTPUT_RUN_BUILD_BUNDLE"})
    return plan


def three_way_merge_json(base_text: str, local_text: str, remote_text: str) -> tuple[str | None, list[str]]:
    """Recursive dict merge. Lists and scalars are atomic; disagreement is reported."""
    def equal(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
        if isinstance(left, list):
            return len(left) == len(right) and all(equal(l, r) for l, r in zip(left, right))
        return left == right

    conflicts: list[str] = []
    try:
        base = json.loads(base_text) if base_text else {}
        local = json.loads(local_text)
        remote = json.loads(remote_text)
    except ValueError as exc:
        return None, [f"JSON_PARSE_ERROR:{exc}"]
    if not all(isinstance(v, dict) for v in (base, local, remote)):
        if equal(local, remote):
            return local_text, []
        return None, ["ROOT_NOT_OBJECT"]

    missing = object()  # An absent key is different from an explicit JSON null.

    def merge(node_b, node_l, node_r, path):
        if equal(node_l, node_r):
            return node_l
        if equal(node_l, node_b):
            return node_r  # only remote moved
        if equal(node_r, node_b):
            return node_l  # only local moved
        if isinstance(node_l, dict) and isinstance(node_r, dict) and isinstance(node_b, dict):
            out = {}
            for key in sorted(set(node_l) | set(node_r) | set(node_b)):
                b, l, r = (node.get(key, missing) for node in (node_b, node_l, node_r))
                value = merge(b, l, r, f"{path}.{key}" if path else key)
                if value is not missing:
                    out[key] = value
            return out
        conflicts.append(path or "<root>")
        return node_l

    merged = merge(base, local, remote, "")
    if conflicts:
        return None, conflicts
    return json.dumps(merged, ensure_ascii=False, indent=2) + "\n", []


# ------------------------------------------------------------------------ ledger

def internal_path(root: Path, path: Path) -> Path:
    """Guard tool-owned reports and temporary files without the payload blacklist."""
    if not path.is_relative_to(root):
        raise SyncError("Internal path escapes project root")
    for probe in (path, *path.parents):
        if is_link_like(probe):
            raise SyncError(f"Symlink or junction rejected: {path}")
        if probe == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise SyncError(f"Internal path escapes project root: {path}")
    return path


def atomic_replace(root: Path, rel: str, data: bytes, expected_sha: str | None,
                   git_mode: str | None = None, restore_mode: int | None = None) -> None:
    if git_mode not in (None, "100644", "100755"):
        raise SyncError(f"Unsupported remote file mode: {git_mode}")
    target = guard_path(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = guard_path(root, rel)
    permissions = restore_mode
    if permissions is None and target.exists():
        permissions = stat.S_IMODE(target.stat().st_mode)
    # O_EXCL keeps the unique-file guard; 0666 lets the OS apply the umask
    # for new files without temporarily changing this process's global umask.
    staging = target.with_name(target.name + ".sync-" + secrets.token_hex(16))
    flags = (os.O_CREAT | os.O_EXCL | os.O_WRONLY
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(staging, flags, 0o600 if permissions is not None else 0o666)
    # The exclusive descriptor is the only write handle; never open a fixed name.
    with os.fdopen(fd, "wb") as handle:
        internal_path(root, staging)
        if permissions is None:
            permissions = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
        if git_mode is not None:
            permissions &= 0o666
            if git_mode == "100755":
                permissions |= 0o111
        handle.write(data)
        handle.flush()
        if os.name != "nt":
            os.fchmod(handle.fileno(), permissions)
        os.fsync(handle.fileno())
    target = guard_path(root, rel)
    internal_path(root, staging)
    if digest_file(staging) != digest_bytes(data):
        raise SyncError(f"{rel} staging digest mismatch; temporary file retained: {staging}")
    if digest_file(target) != expected_sha:
        raise SyncError(f"{rel} changed on disk before replacement; temporary file retained: {staging}")
    os.replace(staging, target)

def ledger_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    return root / LEDGER_DIR / f"sync-ledger-{stamp}.jsonl"


def append_ledger(root: Path, record: dict) -> Path:
    path = internal_path(root, ledger_path(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    internal_path(root, path)
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
    if confirm != plan["plan_id"] or plan_id_of(plan) != plan["plan_id"]:
        raise SyncError("Confirmation token does not match this plan; nothing was written")
    # The dry run reviewed specific bytes at specific tips. If a ref moved since,
    # those bytes are no longer what the operator approved, so refuse outright.
    for label, ref, planned in (("local", local, plan.get("local_tip")),
                                ("HEAD", "HEAD", plan.get("head_tip")),
                                ("remote", remote, plan.get("remote_tip"))):
        current = rev_parse(root, ref)
        if planned and current != planned:
            raise SyncError(
                f"{label} ref moved after planning ({planned} -> {current}); "
                "re-run the dry run and confirm again")
    if index_entries(root)[1] != plan.get("index_sha256"):
        raise SyncError("Index changed after planning; re-run the dry run")
    writable = [a for a in plan["actions"] if a["action"] == "RESTORE_REMOTE_VERSION"]
    if not writable:
        return {"written": [], "rolled_back": False, "note": "NOTHING_TO_WRITE"}
    assert_supported_normalization(root, (a["path"] for a in writable))
    # Compare against the digest captured at plan time, not a fresh read: reading
    # here would bless whatever is on disk now and defeat the drift check.
    before = {a["path"]: a.get("planned_sha256") for a in writable}
    remote_modes = {a["path"]: a["remote_state"]["mode"] for a in writable if a["remote_state"]}
    before_modes: dict[str, int] = {}
    backup_parent = internal_path(root, root / LEDGER_DIR)
    backup_parent.mkdir(parents=True, exist_ok=True)
    internal_path(root, backup_parent)
    backup = Path(tempfile.mkdtemp(prefix="sync-backup-", dir=backup_parent))
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
                before_modes[rel] = stat.S_IMODE(target.stat().st_mode)
                dest = internal_path(root, backup / rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                internal_path(root, dest)
                shutil.copyfile(target, dest)
            blob = git_bytes(root, "cat-file", "blob", f"{remote}:{rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_replace(root, rel, blob.stdout, before[rel], remote_modes.get(rel))
            done.append(rel)
            written_digest[rel] = digest_bytes(blob.stdout)
            ledger = ledger or append_ledger(root, {"run": plan["plan_id"], "event": "RUN_START",
                                                    "paths": [a["path"] for a in writable]})
            append_ledger(root, {"run": plan["plan_id"], "event": "WRITE", "path": rel,
                                 "sha256_before": before[rel],
                                 "sha256_after": digest_file(target)})
        # No git add/commit/push: staging and publishing stay explicit, separate decisions.
        append_ledger(root, {"run": plan["plan_id"], "event": "RUN_OK", "count": len(done)})
        return {"written": done, "rolled_back": False, "ledger": str(ledger),
                "backup": str(backup), "staged": False}
    except BaseException as exc:
        # Restore only what this run wrote. A path that was absent at plan time but
        # appeared afterwards is user work, so it is left alone and reported.
        preserved: list[str] = []
        rollback_errors: list[str] = []
        for rel in reversed(done):
            try:
                target = guard_path(root, rel)
                saved = internal_path(root, backup / rel)
                if digest_file(target) != written_digest.get(rel):
                    preserved.append(rel)
                elif saved.exists():
                    atomic_replace(root, rel, saved.read_bytes(), written_digest[rel], None, before_modes[rel])
                elif before[rel] is None and target.exists():
                    target.unlink()
            except (OSError, SyncError) as rollback_exc:
                rollback_errors.append(f"{rel}: {rollback_exc}")
        try:
            append_ledger(root, {"run": plan["plan_id"], "event": "ROLLBACK", "error": str(exc),
                                 "preserved_user_files": preserved, "errors": rollback_errors,
                                 "backup": str(backup)})
        except (OSError, SyncError) as ledger_exc:
            rollback_errors.append(f"ledger: {ledger_exc}")
        verdict = "rollback incomplete" if rollback_errors or preserved else "was rolled back"
        # Backups are retained on success and failure; cleanup is an explicit human task.
        raise SyncError(f"Apply failed and {verdict}: {exc}; backup retained: {backup}; "
                        f"errors={rollback_errors}; preserved={preserved}") from exc


def done_keys(writable: list[dict]) -> list[str]:
    return [a["path"] for a in writable]


# --------------------------------------------------------------------------- cli

def plan_id_of(plan: dict) -> str:
    body = {k: v for k, v in plan.items() if k not in {"in_sync", "plan_id"}}
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
