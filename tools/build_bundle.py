#!/usr/bin/env python3
"""Local build only. Does not call models, networks, production tools, or installers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import os
import tempfile
import importlib.util
import yaml
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ZIP_TIME=(2026,9,21,0,0,0)

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8", newline="\n")

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)

def lock_files(root: Path) -> list[Path]:
    """Exact release manifest, excluding content locks and generated ZIPs/reports."""
    manifest = read_json(root / "release-manifest.json")
    excluded = {"prompt-bundles.lock"}
    names = [n for n in manifest["files"] if n not in excluded and not n.startswith("individual-packages/")]
    return sorted(root / name for name in names)

def deterministic_zip(base: Path, files: list[Path], output: Path, prefix: str) -> None:
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,"w",compression=ZIP_DEFLATED,compresslevel=9) as z:
        for path in sorted(files):
            if path.is_symlink():
                raise ValueError(f"Symlink not allowed in release: {path}")
            name=f"{prefix}/{path.relative_to(base).as_posix()}"
            info=ZipInfo(name,ZIP_TIME)
            info.compress_type=ZIP_DEFLATED
            info.create_system=3
            info.external_attr=0o100644 << 16
            z.writestr(info,path.read_bytes(),compress_type=ZIP_DEFLATED,compresslevel=9)

def _build_in_place(root: Path) -> dict:
    root=root.resolve()
    source=root/"policy-source"
    roles=read_json(source/"roles-source.json")
    common=(source/"prompts/common.md").read_text(encoding="utf-8").strip()
    version=(root/"VERSION").read_text(encoding="utf-8").strip()
    # Generated trees are owned outputs; reconstruct them from canonical sources only.
    for folder in ["agents", "skills", "templates", "manual-mode", "individual-packages"]:
        shutil.rmtree(root / folder, ignore_errors=True)
        (root / folder).mkdir(parents=True)
    domain_names={r["runbook"] for r in roles.values() if r["runbook"]}
    canonical_refs={p.name:p for p in (source/"references").glob("*.md")}
    canonical_templates=list((source/"templates").glob("*.md"))
    for sid,role in roles.items():
        agent_source=source/"prompts/roles"/(role["agent"]+".md")
        agent_text=agent_source.read_text(encoding="utf-8").replace("{{COMMON_CONTRACT}}",common)
        (root/"agents"/(role["agent"]+".md")).write_text(agent_text,encoding="utf-8", newline="\n")
        skill=root/"skills"/sid
        skill.mkdir(parents=True,exist_ok=True)
        skill_text=(source/"skills"/(sid+".md")).read_text(encoding="utf-8").replace("{{COMMON_CONTRACT}}",common)
        (skill/"SKILL.md").write_text(skill_text,encoding="utf-8", newline="\n")
        (skill/"VERSION").write_text(version+"\n",encoding="utf-8", newline="\n")
        copy(source/"manual"/(sid+".md"),skill/"MANUAL-MODE.md")
        write_yaml = yaml.safe_dump({"interface": role["interface"]}, allow_unicode=True, sort_keys=False)
        (skill / "agents").mkdir(parents=True, exist_ok=True)
        (skill / "agents/openai.yaml").write_text(write_yaml, encoding="utf-8", newline="\n")
        allowed=set(canonical_refs) if sid=="stability-director" else (set(canonical_refs)-domain_names)|{role["runbook"]}
        for name in sorted(allowed): copy(canonical_refs[name],skill/"references"/name)
        for path in canonical_templates: copy(path,skill/"assets/templates"/path.name)
        for path in (root/"schemas").glob("*.json"): copy(path,skill/"schemas"/path.name)
        if sid=="stability-director":
            for name in ["behavior-cases.md","behavior-cases.json","harness-acceptance-cases.json","harness-acceptance-checklist.md"]:
                copy(root/"tests"/name,skill/"tests"/name)
        if sid == "stability-director":
            for path in sorted((source / "team-knowledge").glob("*.md")):
                copy(path, skill / "references/team-knowledge" / path.name)
        skill_hashes={p.relative_to(skill).as_posix():digest(p) for p in sorted(skill.rglob("*")) if p.is_file() and p.name!="BUNDLE-LOCK.json" and "__pycache__" not in p.parts}
        write_json(skill/"BUNDLE-LOCK.json",{"version":version,"skill_id":sid,"agent_id":role["agent"],"verification_scope":"CONTENT_INTEGRITY_NOT_RUNTIME_BEHAVIOR","files":skill_hashes})
    for path in canonical_templates: copy(path,root/"templates"/path.name)
    manual=(source/"manual/stability-director.md").read_text(encoding="utf-8").replace("](references/","](../skills/stability-director/references/")
    (root/"manual-mode").mkdir(exist_ok=True)
    (root/"manual-mode/single-model.md").write_text(manual,encoding="utf-8", newline="\n")
    manual_index="# 无 Harness 的人工入口\n\n必须由用户显式选择，不与托管提示词同时加载。不具备自动账本、调用回执、阶段或发布门。\n\n"
    manual_index+="\n".join(f"- [{r['title']}](../skills/{sid}/MANUAL-MODE.md)" for sid,r in roles.items())+"\n"
    (root/"manual-mode/README.md").write_text(manual_index,encoding="utf-8", newline="\n")
    for sid in roles:
        skill=root/"skills"/sid
        files=[p for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        deterministic_zip(skill,files,root/"individual-packages"/sid/"skill.zip",sid)
    hashes={p.relative_to(root).as_posix():digest(p) for p in lock_files(root)}
    write_json(root/"prompt-bundles.lock",{"version":version,"algorithm":"sha256","scope":"INTEGRITY_ONLY_NOT_AUTHENTICITY_OR_RUNTIME_PROOF","files":hashes})
    return {"version":version,"agents":len(roles),"skills":len(roles),"individual_packages":len(roles),"locked_files":len(hashes)}

OWNED = ("agents", "skills", "templates", "manual-mode", "individual-packages", "prompt-bundles.lock")


def build(root: Path) -> dict:
    """Build in isolation and replace owned outputs with rollback on write failure.

    Does not modify canonical source, root settings, user permissions or Git state.
    A crash/power loss is not a filesystem transaction: retain backups if recovery
    itself fails. Normal Python exceptions trigger rollback of every replaced tree.
    """
    root = root.resolve(strict=True)
    settings = read_json(root / "settings.json")
    roles = read_json(root / "policy-source/roles-source.json")
    if not isinstance(settings, dict) or settings.get("agent") != roles["stability-director"]["agent"]:
        raise ValueError("settings.json must bind the registered lead; other user settings are preserved")
    # Reject symlinks in all declared inputs and their parents before any modification.
    manifest = read_json(root / "release-manifest.json")
    rule_spec = importlib.util.spec_from_file_location("isolated_release_rules", root / "tools/release_rules.py")
    rule_module = importlib.util.module_from_spec(rule_spec)
    rule_spec.loader.exec_module(rule_module)
    from_paths = rule_module.manifest_names(root)
    if len(from_paths) != len(set(from_paths)):
        raise ValueError("Duplicate manifest input")
    for rel in from_paths:
        q = Path(rel)
        if q.is_absolute() or ".." in q.parts or "\\" in rel:
            raise ValueError("Unsafe manifest input: " + rel)
        p = root / q
        if p.is_symlink() or any(a.is_symlink() for a in p.parents if a.is_relative_to(root)):
            raise ValueError("Symlink input: " + rel)
        if not p.exists() and not any(rel == n or rel.startswith(n + "/") for n in OWNED):
            raise ValueError("Missing canonical input: " + rel)
    declared = set(from_paths)
    for folder in OWNED[:-1]:
        directory = root / folder
        if directory.is_symlink(): raise ValueError("Symlink generated directory: " + folder)
        if directory.exists():
            for p in sorted(directory.rglob("*")):
                if "__pycache__" in p.parts or p.suffix == ".pyc": continue
                if p.is_symlink(): raise ValueError("Symlink generated output: " + str(p))
                if p.is_file() and p.relative_to(root).as_posix() not in declared:
                    raise ValueError("Unknown file in generated directory; move user data outside before building: " + str(p))
    temporary = Path(tempfile.mkdtemp(prefix=".crm-build-", dir=root.parent))
    committed = []
    backed_up = []
    keep_backup = False
    try:
        staged = temporary / "staged"
        staged.mkdir()
        # Never traverse/copy unknown workspace data, even into a temporary build.
        for rel in from_paths:
            if any(rel == n or rel.startswith(n + "/") for n in OWNED):
                continue
            source_path = root / rel
            target_path = staged / rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)
        result = _build_in_place(staged)
        # Generate every output before touching the input tree.
        backup = temporary / "backup"
        backup.mkdir()
        try:
            for rel in OWNED:
                destination = root / rel
                if destination.exists():
                    os.replace(destination, backup / rel)
                    backed_up.append(rel)
                os.replace(staged / rel, destination)
                committed.append(rel)
        except BaseException:
            try:
                for rel in reversed(committed):
                    q = root / rel
                    if q.is_dir(): shutil.rmtree(q)
                    elif q.exists(): q.unlink()
                for rel in reversed(backed_up):
                    os.replace(backup / rel, root / rel)
            except BaseException as rollback_error:
                keep_backup = True
                raise RuntimeError(f"Rollback incomplete; preserve {backup}") from rollback_error
            raise
        return result
    finally:
        if not keep_backup:
            shutil.rmtree(temporary, ignore_errors=True)

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    try:
        print(json.dumps(build(args.root),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError) as exc:
        raise SystemExit(f"Build failed: {exc}") from exc

if __name__=="__main__": main()
