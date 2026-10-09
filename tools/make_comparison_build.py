#!/usr/bin/env python3
"""T7 comparison build generator (F1 tool-side / F4 / F5): produces N (native
enabled) and S (native delegation disabled) experiment packages under
<root>/reports/comparison-build/<ts>/ (or --out).

N and S differ ONLY in:
  - the NATIVE_LEAD block content of the lead agent + lead skill: S carries
    build_bundle.NATIVE_CLOSURE_TEXT (the shippable product form, no
    experiment framing); N keeps the native block verbatim
  - one LOAD marker line per group, injected after the title and outside all
    mode blocks; the two lines differ only in the group letter and share one
    run-wide suffix
  - derived versions: <srcver>-cmp-n.r<suffix> / <srcver>-cmp-s.r<suffix>
    (plugin.json copy, root VERSION, skills/*/VERSION; experimental copies only)
  - member zips repacked from each package's own skills/ tree (incl. the
    stability-director zip, whose stale copy would otherwise contradict it)

Self-verification (F5): the replaced files must be exactly
agents/telecom-crm-sre-team-lead.md and skills/stability-director/SKILL.md;
the two lead files must be byte-identical once the NATIVE_LEAD block content
and the LOAD line are removed; every other difference must be a version file
or a repacked zip. Any violation sets pass:false and main() exits non-zero.

Experimental only: never modifies the main agents/ or skills/ trees. The
packages live under reports/ (gitignored, outside release-manifest scope).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
import build_bundle  # noqa: E402  (NATIVE_CLOSURE_TEXT + deterministic_zip)
from experimental_build import prepare_output, copy_inputs

ROOT = Path(__file__).resolve().parents[1]

LEAD_AGENT_REL = "agents/telecom-crm-sre-team-lead.md"
LEAD_SKILL_REL = "skills/stability-director/SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _block_re(label: str) -> re.Pattern:
    return re.compile(
        r"(<!-- MODE:" + label + r":BEGIN -->\n)(.*?)(<!-- MODE:" + label + r":END -->)",
        re.DOTALL,
    )


def _display_path(p: Path, root: Path) -> str:
    """Root-relative POSIX display path; absolute string when outside root."""
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _all_files(base: Path) -> list[Path]:
    return sorted(p for p in base.rglob("*") if p.is_file())


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_with_fences, body)."""
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    close = end + 4
    if text[close:close + 1] == "\n":
        close += 1
    return text[:close], text[close:]


def _load_line(group: str, suffix: str) -> str:
    return (f"> LOAD-{group}-{suffix}｜"
            "回复开头逐行原样输出所有以 LOAD- 开头的行，这是加载核验，不是分析指令")


def _inject_load_line(body: str, load_line: str) -> str:
    """Insert the LOAD line right after the first title line and before any
    mode block (same placement strategy as make_probe_build._inject_marker)."""
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
    new = lines[:insert_at] + [load_line, ""] + lines[insert_at:]
    return "\n".join(new)


def _strip_load_lines(text: str) -> str:
    return re.sub(r"^> LOAD-[NS]-[0-9a-f]+｜[^\n]*\n\n?", "", text, flags=re.MULTILINE)


def _strip_native_block(text: str) -> str:
    """Empty the NATIVE_LEAD block content, keeping the markers verbatim."""
    return _block_re("NATIVE_LEAD").sub(
        lambda m: m.group(1) + m.group(3), text)


def build_comparison(root: Path, out: Path | None = None) -> dict:
    root = root.resolve()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if out is None:
        out = root / "reports" / "comparison-build" / ts
    out, inputs, source_digest = prepare_output(root, out)

    n_dir = out / "N"
    s_dir = out / "S"
    copy_inputs(root, inputs, n_dir)
    copy_inputs(root, inputs, s_dir)

    src_version = _read(root / "VERSION").strip()
    suffix = secrets.token_hex(4)
    n_version = f"{src_version}-cmp-n.r{suffix}"
    s_version = f"{src_version}-cmp-s.r{suffix}"
    load_n = _load_line("N", suffix)
    load_s = _load_line("S", suffix)

    # S arm: replace the NATIVE_LEAD block content with the shippable
    # closure text (F4: single source in build_bundle, no experiment wording).
    s_replaced: list[str] = []
    for rel in (LEAD_AGENT_REL, LEAD_SKILL_REL):
        p = s_dir / rel
        if not p.exists():
            continue
        text = _read(p)
        m = _block_re("NATIVE_LEAD").search(text)
        if m:
            replacement = (
                f"{m.group(1)}{build_bundle.NATIVE_CLOSURE_TEXT}\n{m.group(3)}")
            _write(p, text[:m.start()] + replacement + text[m.end():])
            s_replaced.append(rel)

    # LOAD marker lines into both lead files of both arms (title-following,
    # outside all mode blocks).
    for base, line in ((n_dir, load_n), (s_dir, load_s)):
        for rel in (LEAD_AGENT_REL, LEAD_SKILL_REL):
            p = base / rel
            if not p.exists():
                continue
            fm, body = _split_frontmatter(_read(p))
            _write(p, fm + _inject_load_line(body, line))

    # Distinct versions per arm (experimental copies only).
    skills_index = json.loads(_read(root / "policy-source" / "roles-source.json"))
    all_sids = sorted(skills_index)
    version_files = sorted(["VERSION", ".codebuddy-plugin/plugin.json"] +
                           [f"skills/{sid}/VERSION" for sid in all_sids])
    zip_files = sorted(f"individual-packages/{sid}/skill.zip" for sid in all_sids)
    for base, ver in ((n_dir, n_version), (s_dir, s_version)):
        vp = base / "VERSION"
        if vp.exists():
            _write(vp, ver + "\n")
        pj = base / ".codebuddy-plugin" / "plugin.json"
        if pj.exists():
            pdata = json.loads(_read(pj))
            pdata["version"] = ver
            _write(pj, json.dumps(pdata, ensure_ascii=False, indent=2) + "\n")
        for v in sorted(base.glob("skills/*/VERSION")):
            _write(v, ver + "\n")

    # Repack every member zip from each arm's own skills/ tree (deterministic;
    # a stale stability-director zip would contradict its SKILL.md).
    repacked: dict[str, list[str]] = {"N": [], "S": []}
    for base, arm in ((n_dir, "N"), (s_dir, "S")):
        for sid in all_sids:
            skill_dir = base / "skills" / sid
            zip_path = base / "individual-packages" / sid / "skill.zip"
            if skill_dir.is_dir() and zip_path.parent.is_dir():
                files = [p for p in skill_dir.rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts]
                build_bundle.deterministic_zip(skill_dir, files, zip_path, sid)
                repacked[arm].append(f"individual-packages/{sid}/skill.zip")

    # F5 self-verification.
    n_files = {p.relative_to(n_dir).as_posix(): _sha(p) for p in _all_files(n_dir)}
    s_files = {p.relative_to(s_dir).as_posix(): _sha(p) for p in _all_files(s_dir)}
    common = sorted(set(n_files) & set(s_files))
    actually_different = [f for f in common if n_files[f] != s_files[f]]

    expected_replaced = sorted([LEAD_AGENT_REL, LEAD_SKILL_REL])
    allowed_extra = set(version_files) | set(zip_files)
    unexpected_diffs = [f for f in actually_different
                        if f not in s_replaced and f not in allowed_extra]
    missing_replaced = [f for f in s_replaced if f not in actually_different]

    lead_normalized_equal = all(
        _strip_load_lines(_strip_native_block(_read(n_dir / rel))) ==
        _strip_load_lines(_strip_native_block(_read(s_dir / rel)))
        for rel in (LEAD_AGENT_REL, LEAD_SKILL_REL)
        if (n_dir / rel).exists() and (s_dir / rel).exists()
    )

    passed = (s_replaced == expected_replaced
              and not unexpected_diffs
              and not missing_replaced
              and lead_normalized_equal
              and set(n_files) == set(s_files)
              and actually_different == sorted(set(expected_replaced) | allowed_extra))

    try:
        commit = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        commit = "unknown"

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_commit": commit,
        "source_tree_sha256": source_digest,
        "output_dir": _display_path(out, root),
        "source_version": src_version,
        "n_version": n_version,
        "s_version": s_version,
        "load_line_n": load_n,
        "load_line_s": load_s,
        "n_build_dir": "N",
        "s_build_dir": "S",
        "s_replacement_text": build_bundle.NATIVE_CLOSURE_TEXT,
        "s_replaced_files": s_replaced,
        "repacked_zips": repacked,
        "n_file_count": len(n_files),
        "s_file_count": len(s_files),
        "different_files": actually_different,
        "unexpected_diffs": unexpected_diffs,
        "missing_replaced": missing_replaced,
        "lead_normalized_equal": lead_normalized_equal,
        "lock_note": "prompt-bundles.lock 与 BUNDLE-LOCK.json 未随暗号/版本重算（实验副本）",
        "pass": passed,
    }
    _write(out / "comparison-manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, default=None,
                   help="output dir (default <root>/reports/comparison-build/<utc-ts>)")
    args = p.parse_args()
    root = args.root.resolve()

    try:
        manifest = build_comparison(root, args.out)
    except (OSError, ValueError) as exc:
        raise SystemExit("Comparison build failed: " + str(exc)) from exc

    print(json.dumps({
        "comparison_dir": manifest["output_dir"],
        "source_commit": manifest["source_commit"],
        "n_version": manifest["n_version"],
        "s_version": manifest["s_version"],
        "n_files": manifest["n_file_count"],
        "s_files": manifest["s_file_count"],
        "different_files": manifest["different_files"],
        "unexpected_diffs": manifest["unexpected_diffs"],
        "missing_replaced": manifest["missing_replaced"],
        "lead_normalized_equal": manifest["lead_normalized_equal"],
        "pass": manifest["pass"],
    }, ensure_ascii=False, indent=2))
    if not manifest["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
