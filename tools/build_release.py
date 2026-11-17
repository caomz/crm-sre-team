#!/usr/bin/env python3
"""Build an atomic, deterministic ZIP from the checked-in exact release manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_rules
from release_rules import PREFIX, ZIP_TIME, release_files, is_link

ROOT = Path(__file__).resolve().parents[1]


def build_release(root: Path, output: Path, *, target: str | None = None) -> dict:
    root = root.resolve(strict=True)
    # Reject the link itself and symlinked parents before resolving the output.
    output = output.absolute()
    if is_link(output) or any(is_link(p) for p in output.parents):
        raise ValueError("Symlink output or parent is not permitted")
    output = output.resolve()
    if output.suffix.lower() != ".zip": raise ValueError("Output must end with .zip")
    # Default payload resolves from the manifest: the DSH exact subset when the
    # manifest declares default_target dsh, otherwise the historical whole allowlist.
    files = release_files(root, target=target)
    resolved = release_rules.target_name(root, target)
    if output in {(root / rel).resolve() for rel in release_rules.manifest_names(root)}:
        raise ValueError("Output overlaps a declared source input")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".crm-release-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temp = Path(temporary)
    try:
        with ZipFile(temp, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for p in files:
                info = ZipInfo(PREFIX + "/" + p.relative_to(root).as_posix(), ZIP_TIME)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, p.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
        with ZipFile(temp) as archive:
            if archive.testzip() is not None: raise ValueError("Generated ZIP failed CRC verification")
        checksum = hashlib.sha256(temp.read_bytes()).hexdigest()
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return {"files": len(files), "sha256": checksum, "archive": str(output),
            "target": resolved, "scope": "MANIFEST_CONTENT_INTEGRITY_NOT_HOST_VERIFICATION"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=["dsh", "workbuddy"], default=None,
                        help="Override the manifest default_target (default: dsh)")
    args = parser.parse_args()
    try:
        print(json.dumps(build_release(args.root, args.output, target=args.target), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        raise SystemExit("Release failed: " + str(exc)) from exc
