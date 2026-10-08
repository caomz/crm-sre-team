#!/usr/bin/env python3
"""Prompt measurement for the crm-sre-team plugin.

FILE-LEVEL ONLY. Character counts are NOT token counts and do not predict
context occupancy, cost, or model behavior. When real model input
statistics are unavailable (the default here), this report is a file-level
measurement only.

Scopes:
  source    measure policy-source/ prompts (roles/*.md, skills/*.md, common.md)
  generated measure built artifacts (agents/*.md, skills/*/SKILL.md)
  all       both

Per role + summary, emits:
  - body chars/lines (frontmatter stripped)
  - per MODE block line/char share (parses <!-- MODE:X:BEGIN/END --> markers;
    parsing only, no validation)
  - common-contract share (common.md body length / role body length)
  - Agent<->Skill duplicate (stripped-line multiset intersection: lines, chars, ratio)
  - common_contract_copies = 16 and total duplicated chars
  - lead routing_table_present flag (false at 2.7.0 baseline; flips after T5)

Outputs JSON + human-readable Markdown. Pure stdlib; never reads outside --root.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAVEAT = ("字符数不等于 token 数；不同分词器差异可达数倍。本报告不得用于推断上下文占用、"
          "成本或模型实际行为。未接入真实模型输入统计时，本文件为文件级测量。")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    close = end + 4
    if text[close:close + 1] == "\n":
        close += 1
    return text[:close], text[close:]


def _load_split_modes(root: Path):
    spec = importlib.util.spec_from_file_location("ckwb", root / "tools" / "check_workbuddy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.split_modes


def _mode_blocks(text: str, split_modes) -> dict[str, dict]:
    """Return per-mode {lines, chars} for a prompt text. SHARED content is
    attributed to a synthetic 'SHARED' bucket."""
    chunks, _ = split_modes(text)
    out: dict[str, dict] = {}
    for mode, chunk in chunks:
        body = chunk
        lines = [l for l in body.splitlines() if l.strip()]
        out.setdefault(mode, {"lines": 0, "chars": 0})
        out[mode]["lines"] += len(lines)
        out[mode]["chars"] += len(body)
    return out


def _line_multiset(text: str) -> Counter:
    return Counter(l.strip() for l in text.splitlines() if l.strip())


def _dup_stats(agent_body: str, skill_body: str) -> dict:
    a = _line_multiset(agent_body)
    b = _line_multiset(skill_body)
    common = a & b
    dup_chars = sum(len(line) * n for line, n in common.items())
    agent_chars = sum(len(l) for l in agent_body.splitlines() if l.strip())
    return {
        "dup_lines": sum(common.values()),
        "dup_line_ratio_agent": round(sum(common.values()) / sum(a.values()), 4) if sum(a.values()) else 0,
        "dup_chars": dup_chars,
        "dup_char_ratio_agent": round(dup_chars / agent_chars, 4) if agent_chars else 0,
    }


def measure_role(root: Path, sid: str, role: dict, scope: str, split_modes,
                 common_body: str) -> dict:
    agent_src = root / "policy-source" / "prompts" / "roles" / (role["agent"] + ".md")
    skill_src = root / "policy-source" / "skills" / (sid + ".md")
    agent_gen = root / "agents" / (role["agent"] + ".md")
    skill_gen = root / "skills" / sid / "SKILL.md"

    entry = {"skill_id": sid, "agent": role["agent"], "title": role["title"]}
    sources = []

    def measure_one(label: str, path: Path) -> dict | None:
        if not path.exists():
            return None
        text = _read(path)
        fm, body = _strip_frontmatter(text)
        modes = _mode_blocks(text, split_modes)
        managed = modes.get("MANAGED_HARNESS", {"lines": 0, "chars": 0})
        non_managed = modes.get("NON_MANAGED", {"lines": 0, "chars": 0})
        body_chars = sum(m["chars"] for m in modes.values())
        return {
            "label": label,
            "path": str(path.relative_to(root).as_posix()),
            "frontmatter_chars": len(fm),
            "body_chars": body_chars,
            "body_lines": sum(m["lines"] for m in modes.values()),
            "managed_harness_chars": managed["chars"],
            "managed_harness_ratio": round(managed["chars"] / body_chars, 4) if body_chars else 0,
            "non_managed_chars": non_managed["chars"],
            "non_managed_ratio": round(non_managed["chars"] / body_chars, 4) if body_chars else 0,
            "common_contract_chars": len(common_body),
            "common_contract_ratio": round(len(common_body) / body_chars, 4) if body_chars else 0,
            "mode_blocks": {k: v for k, v in modes.items()},
        }

    if scope in ("source", "all"):
        a = measure_one("source_agent", agent_src)
        s = measure_one("source_skill", skill_src)
        if a:
            sources.append(a)
        if s:
            sources.append(s)
    if scope in ("generated", "all"):
        a = measure_one("generated_agent", agent_gen)
        s = measure_one("generated_skill", skill_gen)
        if a:
            sources.append(a)
        if s:
            sources.append(s)

    entry["measurements"] = sources

    # duplicate stats for generated agent vs skill (the 97% overlap signal)
    if scope in ("generated", "all") and agent_gen.exists() and skill_gen.exists():
        af, ab = _strip_frontmatter(_read(agent_gen))
        sf, sb = _strip_frontmatter(_read(skill_gen))
        entry["generated_dup"] = _dup_stats(ab, sb)
    if scope in ("source", "all") and agent_src.exists() and skill_src.exists():
        af, ab = _strip_frontmatter(_read(agent_src))
        sf, sb = _strip_frontmatter(_read(skill_src))
        entry["source_dup"] = _dup_stats(ab, sb)

    if sid == "stability-director":
        # routing table flag: checks for the placeholder or the rendered roster
        # title in source or generated form (placeholder replaced at build time).
        for src_path in (agent_src, agent_gen):
            if src_path.exists():
                t = _read(src_path)
                entry["routing_table_present"] = (
                    "{{TEAM_ROSTER}}" in t
                    or "{{ROUTING_TABLE}}" in t
                    or "成员名册" in t
                    or "成员路由表" in t
                )
                break
                break
    return entry


def run(root: Path, scope: str) -> dict:
    roles = json.loads(_read(root / "policy-source" / "roles-source.json"))
    split_modes = _load_split_modes(root)
    common_body_full = _strip_frontmatter(_read(root / "policy-source" / "prompts" / "common.md"))[1]
    # N12: runtime artifacts receive the STRIPPED common (Slice 1), so per-copy
    # size must use the stripped length, not the full source length.
    _spec = importlib.util.spec_from_file_location("bb_measure", root / "tools" / "build_bundle.py")
    _bb = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_bb)
    common_body = _bb.strip_managed(common_body_full)

    per_role = [measure_role(root, sid, r, scope, split_modes, common_body)
                for sid, r in sorted(roles.items())]

    # summary
    copies = 16  # 8 agent + 8 skill
    total_common_chars = len(common_body) * copies
    summary = {
        "roles": len(per_role),
        "common_contract_copies": copies,
        "common_contract_chars_per_copy": len(common_body),
        "common_contract_total_chars_across_copies": total_common_chars,
        "scope": scope,
        "managed_ratio_range_generated_agent": _range(per_role, "generated_agent"),
        "managed_ratio_range_generated_skill": _range(per_role, "generated_skill"),
        "dup_char_ratio_range_generated": _dup_range(per_role),
    }

    return {
        "measurement_scope": "FILE_LEVEL_ONLY",
        "token_source": "NOT_AVAILABLE_NO_MODEL_INPUT_STATISTICS",
        "model_behavior": "NOT_RUN",
        "host_run": "NOT_RUN",
        "caveat": CAVEAT,
        "version": _read(root / "VERSION").strip(),
        "generated_by": "tools/measure_prompts.py",
        "summary": summary,
        "roles": per_role,
    }


def _range(per_role: list, label: str) -> dict | None:
    vals = []
    for r in per_role:
        for m in r.get("measurements", []):
            if m["label"] == label:
                vals.append(m["managed_harness_ratio"])
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals)}


def _dup_range(per_role: list) -> dict | None:
    vals = [r["generated_dup"]["dup_char_ratio_agent"] for r in per_role if "generated_dup" in r]
    if not vals:
        return None
    return {"min": min(vals), "max": max(vals)}


def render_md(report: dict) -> str:
    lines = [
        "# 提示词测量基线",
        "",
        f"> {report['caveat']}",
        f"> scope={report['summary']['scope']} | version={report['version']} | "
        f"MODEL_BEHAVIOR={report['model_behavior']} | WORKBUDDY_HOST={report['host_run']}",
        "",
        "## 汇总",
        "",
        f"- 公共契约副本数：{report['summary']['common_contract_copies']}（8 Agent + 8 SKILL.md）",
        f"- 每副本字符数：{report['summary']['common_contract_chars_per_copy']}",
        f"- 跨副本合计：{report['summary']['common_contract_total_chars_across_copies']}",
        "",
    ]
    mr_a = report["summary"].get("managed_ratio_range_generated_agent")
    mr_s = report["summary"].get("managed_ratio_range_generated_skill")
    dr = report["summary"].get("dup_char_ratio_range_generated")
    if mr_a:
        lines.append(f"- 生成 Agent 正文 MANAGED 段占比范围：{mr_a['min']}–{mr_a['max']}")
    if mr_s:
        lines.append(f"- 生成 SKILL.md 正文 MANAGED 段占比范围：{mr_s['min']}–{mr_s['max']}")
    if dr:
        lines.append(f"- 生成 Agent↔SKILL.md 重复字符占比范围：{dr['min']}–{dr['max']}")
    lines += ["", "## 每角色明细", "",
              "| 角色 | 入口 | 正文字符 | MANAGED 占比 | 契约占比 | 重复行占比(A↔S) |",
              "| --- | --- | --- | --- | --- | --- |"]
    for r in report["roles"]:
        for m in r.get("measurements", []):
            dup = r.get("generated_dup", {}).get("dup_line_ratio_agent", "") if m["label"].startswith("generated") else r.get("source_dup", {}).get("dup_line_ratio_agent", "")
            lines.append(f"| {r['title']} | {m['label']} | {m['body_chars']} | "
                         f"{m['managed_harness_ratio']} | {m['common_contract_ratio']} | {dup} |")
    lines += ["", "## 团长路由表基线", ""]
    for r in report["roles"]:
        if "routing_table_present" in r:
            lines.append(f"- {r['title']}: routing_table_present = {r['routing_table_present']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--scope", choices=["source", "generated", "all"], default="all")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--md-out", type=Path, default=None)
    args = p.parse_args()
    root = args.root.resolve()
    report = run(root, args.scope)

    def _display_path(p: Path) -> str:
        """Root-relative POSIX display path; absolute string when outside root."""
        try:
            return p.resolve().relative_to(root).as_posix()
        except ValueError:
            return str(p)

    if args.json_out:
        out = args.json_out if args.json_out.is_absolute() else root / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(f"json -> {_display_path(out)}")
    if args.md_out:
        out = args.md_out if args.md_out.is_absolute() else root / args.md_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_md(report), encoding="utf-8", newline="\n")
        print(f"md   -> {_display_path(out)}")
    if not args.json_out and not args.md_out:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
