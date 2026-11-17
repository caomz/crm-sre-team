"""Shared exact release allowlist and safe-path rules. No recursive workspace packaging."""
from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
import re
import stat

PREFIX = "crm-sre-team"
ZIP_TIME = (2026, 9, 21, 0, 0, 0)
FORBIDDEN_PARTS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "incident-evidence", "reports", "dist", "node_modules"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".bak", ".pem", ".key", ".p12", ".pfx", ".log", ".tmp", ".swp"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".txt", ".png", ".jpg", ".jpeg", ".patch"}


def is_link(path: Path) -> bool:
    """Fail closed on Windows reparse points, including on Python 3.11."""
    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def safe_relative(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in name.split("/")):
        return False
    folded_parts = [p.casefold() for p in path.parts]
    if str(path) != name or any(p in FORBIDDEN_PARTS for p in folded_parts):
        return False
    if any(p == ".env" or p.startswith(".env.") for p in folded_parts):
        return False
    if path.name.casefold().startswith(("id_rsa", "id_ed25519")) or path.name.endswith("~") or path.suffix.casefold() in FORBIDDEN_SUFFIXES:
        return False
    if path.suffix.lower() == ".zip":
        return bool(re.fullmatch(r"individual-packages/[a-z0-9-]+/skill\.zip", name))
    return path.suffix.lower() in ALLOWED_SUFFIXES or path.name in {"VERSION", "prompt-bundles.lock", ".gitignore", "LICENSE"}


def manifest_names(root: Path) -> list[str]:
    manifest_path = root / "release-manifest.json"
    if is_link(manifest_path): raise ValueError("Manifest must not be a link")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(names, list) or not names:
        raise ValueError("Invalid or empty release manifest")
    if not all(safe_relative(n) for n in names):
        raise ValueError("Unsafe or non-release path in manifest")
    if names != sorted(names) or len(names) != len(set(names)) or len({n.casefold() for n in names}) != len(names):
        raise ValueError("Manifest must be sorted and collision-free")
    manifest_targets(manifest, names)
    required = {"VERSION", "settings.json", ".codebuddy-plugin/plugin.json", "release-manifest.json", "prompt-bundles.lock"}
    if not required.issubset(names): raise ValueError("Manifest is missing required entry files")
    return names


TARGETS = ("dsh", "workbuddy")


def manifest_targets(manifest: dict, names: list[str]) -> dict:
    """Validate the optional release-target declaration.

    Historical manifests without any target field return an empty mapping and
    keep the legacy whole-manifest payload. Declared targets are named exactly,
    sorted, duplicate-free exact subsets of the total manifest; default_target,
    when present, must name one of them. This remains an exact allowlist check:
    no directory scans ever substitute for the declared file lists."""
    default_target = manifest.get("default_target")
    targets = manifest.get("targets")
    if default_target is None and targets is None:
        return {}
    if default_target is not None and default_target not in TARGETS:
        raise ValueError("Unknown manifest default_target: " + str(default_target))
    if not isinstance(targets, dict) or not targets:
        raise ValueError("Manifest with a target declaration must define targets as an object")
    all_names = set(names)
    for name, spec in targets.items():
        if name not in TARGETS:
            raise ValueError("Unknown release target: " + str(name))
        if not isinstance(spec, dict):
            raise ValueError("Target spec must be an object: " + str(name))
        files = spec.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("Target must declare a non-empty exact file subset: " + str(name))
        if files != sorted(files) or len(files) != len(set(files)):
            raise ValueError("Target files must be sorted and duplicate-free: " + str(name))
        if not set(files) <= all_names:
            raise ValueError("Target files must be a subset of the total manifest: " + str(name))
    if default_target is not None and default_target not in targets:
        raise ValueError("default_target must be a declared target: " + str(default_target))
    return targets


def target_name(root: Path, target: str | None = None) -> str:
    """Resolve the delivery target. An explicit argument wins; otherwise the
    trusted manifest default_target applies; historical manifests without any
    target declaration fall back to workbuddy so old fixtures keep working."""
    if target is not None:
        if target not in TARGETS:
            raise ValueError("Unknown release target: " + str(target))
        return target
    manifest_path = root / "release-manifest.json"
    if is_link(manifest_path):
        raise ValueError("Manifest must not be a link")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_targets(manifest, manifest.get("files") or [])
    default_target = manifest.get("default_target")
    if default_target is None and (root / "policy-source/dsh").exists():
        raise ValueError("DSH sources require an explicit manifest default_target")
    return default_target if default_target is not None else "workbuddy"


def target_files(root: Path, target: str | None = None) -> list[str]:
    """Exact payload for the resolved target: workbuddy keeps the historical
    whole-manifest allowlist; any declared target returns its exact subset."""
    resolved = target_name(root, target)
    names = manifest_names(root)
    if resolved == "workbuddy":
        return names
    manifest = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
    subset = list(manifest["targets"][resolved]["files"])
    if not set(subset) <= set(names):
        raise ValueError("Target files escaped the total manifest: " + resolved)
    return subset


def release_files(root: Path, *, target: str | None = None) -> list[Path]:
    root = root.resolve(strict=True)
    files = []
    for rel in target_files(root, target):
        p = root / rel
        if is_link(p) or any(is_link(parent) for parent in p.parents if parent.is_relative_to(root)):
            raise ValueError("Symlink release input: " + rel)
        if not p.is_file() or not p.resolve().is_relative_to(root):
            raise ValueError("Missing or escaping release input: " + rel)
        files.append(p)
    return files
