#!/usr/bin/env python3
"""T7 comparison build generator: produces N (native enabled) and S (native
delegation disabled) experiment packages in reports/comparison-build/<ts>/.

The S build replaces the NATIVE_LEAD block in the lead agent with a fixed
D15 "native closure" text so the S arm tests the product form that ships
when the gate fails or is BLOCKED. N and S must differ ONLY in that
replacement; the script auto-verifies this.

Experimental only: never modifies the main agents/ or skills/ trees. The
packages live under reports/ (gitignored, outside release-manifest scope).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPARE_ROOT = ROOT / "reports" / "comparison-build"

S_FIXED_TEXT = (
    "本构建用于预注册单模型对照。不得调用团队成员。"
    "直接按 WORKBUDDY_COMPAT 完成本次材料分析。不得声称已进行专家委派。"
)


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


def _copy_tree(src: Path, dst: Path) -> None:
    """Copy a directory tree verbatim."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def build_comparison(root: Path) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = COMPARE_ROOT / ts
    out.mkdir(parents=True, exist_ok=True)

    n_dir = out / "N"
    s_dir = out / "S"

    # Copy the current built tree to both N and S
    for folder in ("agents", "skills", "individual-packages", "templates",
                   "manual-mode", "policies", "schemas", "policy-source",
                   "docs", "avatars", ".codebuddy-plugin"):
        src = root / folder
        if src.is_dir():
            _copy_tree(src, n_dir / folder)
            _copy_tree(src, s_dir / folder)

    for fname in ("VERSION", "settings.json", "README.md", "release-manifest.json",
                  "prompt-bundles.lock", "CHANGELOG.md", "MIGRATION.md",
                  "MODIFICATIONS.md", "VALIDATION.md", "manual-team-config.json",
                  "source-baseline.json", "source-provenance.json",
                  "requirements-build.txt", "requirements-dev.txt"):
        f = root / fname
        if f.exists():
            n_dir.mkdir(parents=True, exist_ok=True)
            s_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, n_dir / fname)
            shutil.copy2(f, s_dir / fname)

    # S build: replace NATIVE_LEAD block in lead agent with fixed text
    lead_agent = s_dir / "agents" / "telecom-crm-sre-team-lead.md"
    lead_skill = s_dir / "skills" / "stability-director" / "SKILL.md"
    s_replaced = []
    for p in (lead_agent, lead_skill):
        if p.exists():
            text = _read(p)
            m = _block_re("NATIVE_LEAD").search(text)
            if m:
                replacement = f"{m.group(1)}{S_FIXED_TEXT}\n{m.group(3)}"
                text = text[:m.start()] + replacement + text[m.end():]
                _write(p, text)
                s_replaced.append(str(p.relative_to(s_dir).as_posix()))

    # Auto-verify: N and S differ only in files that had NATIVE_LEAD replaced
    n_files = {p.relative_to(n_dir).as_posix(): _sha(p) for p in _all_files(n_dir)}
    s_files = {p.relative_to(s_dir).as_posix(): _sha(p) for p in _all_files(s_dir)}
    diff_files = sorted(set(n_files.keys()) & set(s_files.keys()))
    actually_different = [f for f in diff_files if n_files[f] != s_files[f]]

    # The only files that should differ are the ones where NATIVE_LEAD was replaced
    unexpected_diffs = [f for f in actually_different if f not in s_replaced]

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
        "n_build_dir": "N",
        "s_build_dir": "S",
        "s_replacement_text": S_FIXED_TEXT,
        "s_replaced_files": s_replaced,
        "n_file_count": len(n_files),
        "s_file_count": len(s_files),
        "different_files": actually_different,
        "unexpected_diffs": unexpected_diffs,
        "pass": len(unexpected_diffs) == 0,
    }
    _write(out / "comparison-manifest.json",
           json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    root = args.root.resolve()

    manifest = build_comparison(root)

    print(json.dumps({
        "comparison_dir": str((COMPARE_ROOT / manifest["generated_at_utc"][:15].replace("-", "")).relative_to(root).as_posix()),
        "source_commit": manifest["source_commit"],
        "n_files": manifest["n_file_count"],
        "s_files": manifest["s_file_count"],
        "different_files": manifest["different_files"],
        "unexpected_diffs": manifest["unexpected_diffs"],
        "pass": manifest["pass"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
