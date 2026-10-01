#!/usr/bin/env python3
"""Validate ZIP order, uniqueness, path safety, exact manifest set, metadata and bytes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_rules import PREFIX, ZIP_TIME, release_files, safe_relative

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 5000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 20 * 1024 * 1024


def validate(root: Path, archive: Path) -> dict:
    errors = []
    try:
        expected = {PREFIX + "/" + p.relative_to(root.resolve()).as_posix(): p for p in release_files(root)}
        with ZipFile(archive) as z:
            entries = z.infolist()
            # Preserve actual archive order. Sorting before comparison would hide the defect.
            names = [entry.filename for entry in entries]
            if names != sorted(names): errors.append("entries_not_sorted")
            if len(names) != len(set(names)): errors.append("duplicate_entries")
            if len({n.casefold() for n in names}) != len(names): errors.append("case_colliding_entries")
            if len(names) > MAX_FILES or sum(e.file_size for e in entries) > MAX_TOTAL_BYTES:
                errors.append("archive_size_limit")
            if set(names) != set(expected): errors.append("file_set_mismatch")
            for entry in entries:
                name = entry.filename
                relative = name[len(PREFIX) + 1:] if name.startswith(PREFIX + "/") else ""
                if not safe_relative(relative): errors.append("unsafe_path:" + name)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or entry.is_dir(): errors.append("non_regular_entry:" + name)
                if entry.flag_bits & 1: errors.append("encrypted_entry:" + name)
                if entry.date_time != ZIP_TIME or entry.compress_type != ZIP_DEFLATED or mode != 0o100644: errors.append("noncanonical_metadata:" + name)
                if entry.file_size > MAX_MEMBER_BYTES: errors.append("member_size_limit:" + name)
            # Do not decompress oversized or structurally hostile packages.
            if not errors:
                bad_crc = z.testzip()
                if bad_crc is not None: errors.append("crc:" + bad_crc)
                for entry in entries:
                    if z.read(entry) != expected[entry.filename].read_bytes(): errors.append("content_mismatch:" + entry.filename)
    except (OSError, ValueError, BadZipFile, RuntimeError) as exc:
        errors.append(type(exc).__name__ + ":" + str(exc))
    return {"pass": not errors, "errors": errors, "scope": "ZIP_INTEGRITY_NOT_RUNTIME", "sha256": hashlib.sha256(archive.read_bytes()).hexdigest() if archive.is_file() else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.root.resolve(), args.zip)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
