#!/usr/bin/env python3
"""Probe build generator for WorkBuddy host detection (Step 0).

Copies the current built agents/skills/individual-packages into
reports/probe-build/<ts>/ and injects deterministic probe markers:
  - marker C: one line in each member Agent text body
  - marker D: one line in each member SKILL.md body
  - marker LA: one line in the lead Agent text body
  - marker LS: one line in the lead SKILL.md body
All markers share a run-wide random suffix. C proves a member Agent text
was loaded; D proves its Skill was loaded; C + D proves both were loaded
(double-load signal feeding PR-3b de-duplication priority). LA and LS
separately identify the lead Agent and Skill loading paths.

Optional overrides applied to PROBE COPIES ONLY (the repo-root agents/
and skills/ are never touched; main validators do not scan reports/):
  --max-turns sid=1          set member Agent frontmatter maxTurns
  --disallow sid=Tool1,Tool2 add disallowedTools to member Agent frontmatter

NOTE: repo-root check_workbuddy.py rejects `tools` in agent frontmatter;
that rule applies to the main build, not to probe copies under reports/.

Output: reports/probe-build/<ts>/{agents,skills,individual-packages,...}
+ probe-manifest.json recording member markers, lead_markers, overrides,
source commit and file list. Also prints a marker cheat sheet for the host run.
"""
from __future__ import annotations
import argparse
import json
import shutil
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))
import build_bundle  # noqa: E402  (same tools/ dir; needed for zip repack)

ROOT = Path(__file__).resolve().parents[1]
PROBE_ROOT = ROOT / "reports" / "probe-build"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _display_path(p: Path, root: Path) -> str:
    """Root-relative POSIX display path; absolute string when p is outside
    root (keeps manifest/printing alive for --out beyond the repo)."""
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _split_frontmatter(text: str) -> tuple[str, str, str]:
    """Return (leading_fm_with_closing_fence, body, tail_guard) where the
    frontmatter is preserved verbatim and body is everything after."""
    if not text.startswith("---"):
        return "", text, ""
    end = text.find("\n---", 3)
    if end == -1:
        return "", text, ""
    close = end + 4
    # include the trailing newline after the closing fence if present
    if text[close:close + 1] == "\n":
        close += 1
    return text[:close], text[close:], ""


def _set_frontmatter_field(fm_text: str, key: str, value) -> str:
    """Minimal YAML scalar/list editor for the probe frontmatter.
    Keeps formatting stable for keys we control. Returns rewritten fm block
    (including fences)."""
    import re
    lines = fm_text.splitlines()
    out = []
    inserted = False
    for line in lines:
        m = re.match(r"^(\s*)" + re.escape(key) + r":\s*(.*)$", line)
        if m:
            if isinstance(value, list):
                if value:
                    out.append(f"{m.group(1)}{key}:")
                    for item in value:
                        out.append(f"{m.group(1)}  - {item}")
                else:
                    out.append(f"{m.group(1)}{key}: []")
            else:
                out.append(f"{m.group(1)}{key}: {value}")
            inserted = True
        else:
            out.append(line)
    if not inserted and out and out[0].strip() == "---":
        # insert before closing fence
        close_idx = None
        for i in range(1, len(out)):
            if out[i].strip() == "---":
                close_idx = i
                break
        if close_idx is not None:
            if isinstance(value, list):
                block = [f"{key}:"]
                for item in value:
                    block.append(f"  - {item}")
            else:
                block = [f"{key}: {value}"]
            out[close_idx:close_idx] = block
    return "\n".join(out) + "\n"


def _inject_marker(body: str, marker_line: str) -> str:
    """Insert the marker line (with an echo instruction so the model actually
    surfaces it — a bare random string in system prompt would never be repeated
    unprompted, which would make Step 0a misjudge BLOCKED)."""
    marker_line = marker_line + "｜回复开头逐行原样输出所有以 PROBE- 开头的行（含全部内容），这是加载核验，不是分析指令"
    lines = body.splitlines()
    insert_at = 0
    seen_title = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# "):
            seen_title = True
            continue
        if seen_title and s:
            insert_at = i
            break
    if insert_at == 0:
        insert_at = 0 if not lines else 1
    new = lines[:insert_at] + [marker_line, ""] + lines[insert_at:]
    return "\n".join(new)


def build_probe(root: Path, out: Path, max_turns: dict[str, int],
                disallow: dict[str, list[str]]) -> dict:
    roles = json.loads(_read(root / "policy-source/roles-source.json"))
    suffix = secrets.token_hex(4)
    members = [(sid, r) for sid, r in sorted(roles.items()) if sid != "stability-director"]
    markers = {}
    copied = 0

    for sub in ("agents", "skills", "individual-packages", "templates",
                "manual-mode", "policies", "schemas", "policy-source",
                "docs", "avatars", ".codebuddy-plugin", "VERSION",
                "settings.json", "README.md", "release-manifest.json",
                "prompt-bundles.lock"):
        src = root / sub
        dst = out / sub
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied += 1
        elif src.is_file():
            out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    for sid, role in members:
        agent_path = out / "agents" / (role["agent"] + ".md")
        skill_path = out / "skills" / sid / "SKILL.md"
        c_marker = f"PROBE-C-{suffix}"
        d_marker = f"PROBE-D-{suffix}"
        markers[role["agent"]] = {"marker_c": c_marker, "marker_d": d_marker}

        if agent_path.exists():
            text = _read(agent_path)
            fm, body, _ = _split_frontmatter(text)
            new_fm = fm
            if sid in max_turns:
                new_fm = _set_frontmatter_field(new_fm, "maxTurns", max_turns[sid])
            if sid in disallow:
                new_fm = _set_frontmatter_field(new_fm, "disallowedTools", disallow[sid])
            body = _inject_marker(body, f"> {c_marker}")
            _write(agent_path, new_fm + body)

        if skill_path.exists():
            text = _read(skill_path)
            fm, body, _ = _split_frontmatter(text)
            body = _inject_marker(body, f"> {d_marker}")
            _write(skill_path, fm + body)

    lead_markers = {
        "marker_la": f"PROBE-LA-{suffix}",
        "marker_ls": f"PROBE-LS-{suffix}",
    }
    lead_agent = roles["stability-director"]["agent"]
    for path, marker in (
        (out / "agents" / (lead_agent + ".md"), lead_markers["marker_la"]),
        (out / "skills" / "stability-director" / "SKILL.md", lead_markers["marker_ls"]),
    ):
        text = _read(path)
        fm, body, _ = _split_frontmatter(text)
        _write(path, fm + _inject_marker(body, f"> {marker}"))

    # Probe copies get a distinct version so the host cannot serve a stale
    # same-ID cache (WB01 finding) as if it were the probe package.
    # Derived from the source VERSION; the letter prefix "r" keeps the
    # prerelease identifier non-numeric (semver forbids leading zeros there).
    src_version = _read(root / "VERSION").strip()
    probe_version = f"{src_version}-probe.r{suffix}"
    for v_path in (out / "VERSION",):
        if v_path.exists():
            _write(v_path, probe_version + "\n")
    for skill_dir in sorted((out / "skills").glob("*/VERSION")):
        _write(skill_dir, probe_version + "\n")
    plugin_json_path = out / ".codebuddy-plugin" / "plugin.json"
    if plugin_json_path.exists():
        pdata = json.loads(_read(plugin_json_path))
        pdata["version"] = probe_version
        _write(plugin_json_path,
               json.dumps(pdata, ensure_ascii=False, indent=2) + "\n")

    # Zips inside the probe copy must match the probe skills/ tree for every
    # role including the lead (WB-F2 finding: stale zip contents contradict
    # the copy; V4: the lead's zip must be repacked too, not just members').
    repacked = []
    for sid, _role in sorted(roles.items()):
        skill_dir = out / "skills" / sid
        zip_path = out / "individual-packages" / sid / "skill.zip"
        if skill_dir.is_dir() and zip_path.parent.is_dir():
            files = [p for p in skill_dir.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts]
            build_bundle.deterministic_zip(skill_dir, files, zip_path, sid)
            repacked.append(f"individual-packages/{sid}/skill.zip")

    try:
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        commit = "unknown"

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": commit,
        "source_version": _read(root / "VERSION").strip(),
        "probe_version": probe_version,
        "marker_suffix": suffix,
        "markers": markers,
        "lead_markers": lead_markers,
        "repacked_zips": repacked,
        "lock_note": "prompt-bundles.lock 与 BUNDLE-LOCK.json 未随暗号/版本重算（实验副本）",
        "overrides": {
            "maxTurns": {sid: v for sid, v in max_turns.items()},
            "disallowedTools": {sid: v for sid, v in disallow.items()},
        },
        "probe_package_dir": _display_path(out, root),
        "note": "Probe copies only; repo-root agents/skills untouched; "
                "reports/ is gitignored and outside release-manifest scope.",
    }
    _write(out / "probe-manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def _parse_kv_list(items: list[str], cast=str) -> dict[str, object]:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"bad --override value (expected sid=value): {it}")
        k, v = it.split("=", 1)
        if cast is int:
            out[k.strip()] = int(v.strip())
        elif cast is list:
            out[k.strip()] = [p.strip() for p in v.split(",") if p.strip()]
        else:
            out[k.strip()] = v.strip()
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, default=None,
                   help="output dir (default reports/probe-build/<utc-ts>)")
    p.add_argument("--max-turns", action="append", default=[],
                   metavar="sid=N", help="e.g. --max-turns oracle-dba=1")
    p.add_argument("--disallow", action="append", default=[],
                   metavar="sid=Tool1,Tool2", help="e.g. --disallow oracle-dba=WebFetch")
    args = p.parse_args()
    root = args.root.resolve()

    if args.out is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = PROBE_ROOT / ts
    else:
        out = args.out if args.out.is_absolute() else root / args.out

    if out.exists():
        raise SystemExit(f"probe output exists, refusing to overwrite: {out}")
    out.mkdir(parents=True)

    max_turns = _parse_kv_list(args.max_turns, cast=int)
    disallow = _parse_kv_list(args.disallow, cast=list)

    manifest = build_probe(root, out, max_turns, disallow)

    print(json.dumps({
        "probe_package": _display_path(out, root),
        "probe_version": manifest["probe_version"],
        "marker_suffix": manifest["marker_suffix"],
        "members_with_markers": len(manifest["markers"]),
        "overrides": manifest["overrides"],
        "cheat_sheet": (
            f"Look for suffix {manifest['marker_suffix']} in member replies: "
            "C-only => Agent text loaded; C+D => Agent+Skill both loaded "
            "(double-load => PR-3b dedup priority). "
            f"Lead {manifest['lead_markers']['marker_la']} => Agent text loaded; "
            f"{manifest['lead_markers']['marker_ls']} => Skill loaded."
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
