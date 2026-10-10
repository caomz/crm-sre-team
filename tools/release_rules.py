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
    required = {"VERSION", "settings.json", ".codebuddy-plugin/plugin.json", "release-manifest.json", "prompt-bundles.lock"}
    if not required.issubset(names): raise ValueError("Manifest is missing required entry files")
    return names


def release_files(root: Path) -> list[Path]:
    root = root.resolve(strict=True)
    files = []
    for rel in manifest_names(root):
        p = root / rel
        if is_link(p) or any(is_link(parent) for parent in p.parents if parent.is_relative_to(root)):
            raise ValueError("Symlink release input: " + rel)
        if not p.is_file() or not p.resolve().is_relative_to(root):
            raise ValueError("Missing or escaping release input: " + rel)
        files.append(p)
    return files
