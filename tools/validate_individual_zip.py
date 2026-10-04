#!/usr/bin/env python3
"""Strict validator for individual skill ZIPs, aligned with release ZIP checks.

Ordering contract: metadata-only structure and resource checks run first;
no archive content is decompressed until all of them pass. Every content read
(CRC, byte comparison, final hashing) is budget-bounded streaming, so a hostile
archive cannot force unbounded reads even if it passes metadata checks.
"""
from __future__ import annotations
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import stat
import sys
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_rules import ZIP_TIME, safe_relative

ROOT = Path(__file__).resolve().parents[1]
MAX_FILES = 5000
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_ZIP_FILE_BYTES = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
READ_CHUNK = 1 << 16
HASH_CHUNK = 1 << 20


class BudgetExceeded(RuntimeError):
    """A bounded read hit its declared budget; treated as a structured error."""


def expected_files(root: Path, sid: str) -> dict:
    skill = root / "skills" / sid
    return {f"{sid}/{p.relative_to(skill).as_posix()}": p for p in sorted(skill.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def sha256_file_bounded(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK), b""):
            total += len(chunk)
            if total > MAX_ZIP_FILE_BYTES:
                raise BudgetExceeded(f"zip file exceeds {MAX_ZIP_FILE_BYTES} bytes")
            digest.update(chunk)
    return digest.hexdigest()


def stream_member_compare(z: ZipFile, name: str, disk_path: Path):
    """Bounded streaming compare of one member against its disk source.

    Returns the CRC32 of the member content when identical, None when the
    bytes differ. Raises BudgetExceeded if the declared size is exceeded.
    """
    crc = 0
    read = 0
    with z.open(name) as member, disk_path.open("rb") as disk:
        while True:
            a = member.read(READ_CHUNK)
            b = disk.read(READ_CHUNK)
            if a != b:
                return None
            if not a:
                return crc
            read += len(a)
            if read > MAX_MEMBER_BYTES:
                raise BudgetExceeded(f"member exceeds budget: {name}")
            crc = binascii.crc32(a, crc)


def validate(root: Path, sid: str) -> dict:
    errors = []
    sha = None
    zip_path = root / "individual-packages" / sid / "skill.zip"
    try:
        expected = expected_files(root, sid)
        if not expected:
            errors.append("skill_source_missing:" + sid)
        with ZipFile(zip_path) as z:
            entries = z.infolist()
            names = [e.filename for e in entries]
            # Order must match the canonical build order derived from the disk
            # tree: deterministic_zip sorts Path objects, whose ordering is
            # case-insensitive on Windows, so sorting name strings here would
            # flag every archive this builder produces. Only meaningful when
            # the file set itself is correct.
            if set(names) == set(expected) and names != list(expected): errors.append("entries_not_sorted")
            if len(names) != len(set(names)): errors.append("duplicate_entries")
            if len({n.casefold() for n in names}) != len(names): errors.append("case_colliding_entries")
            if len(names) > MAX_FILES or sum(e.file_size for e in entries) > MAX_TOTAL_BYTES:
                errors.append("archive_size_limit")
            if set(names) != set(expected): errors.append("file_set_mismatch")
            for required in (f"{sid}/VERSION", f"{sid}/SKILL.md"):
                if required not in names: errors.append("required_file_missing:" + required)
            for entry in entries:
                name = entry.filename
                if not safe_relative(name): errors.append("unsafe_path:" + name)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or entry.is_dir():
                    errors.append("non_regular_entry:" + name)
                if entry.flag_bits & 1: errors.append("encrypted_entry:" + name)
                if entry.date_time != ZIP_TIME or entry.compress_type != ZIP_DEFLATED or mode != 0o100644:
                    errors.append("noncanonical_metadata:" + name)
                if entry.file_size > MAX_MEMBER_BYTES: errors.append("member_size_limit:" + name)
                if entry.file_size > MAX_COMPRESSION_RATIO * max(entry.compress_size, 1):
                    errors.append("compression_ratio_limit:" + name)
            # Content phase: metadata checks must all pass first; reads stay bounded.
            if not errors:
                for entry in entries:
                    crc = stream_member_compare(z, entry.filename, expected[entry.filename])
                    if crc is None: errors.append("content_mismatch:" + entry.filename)
                    elif crc != entry.CRC: errors.append("crc:" + entry.filename)
        sha = sha256_file_bounded(zip_path)
    except (OSError, ValueError, KeyError, BadZipFile, RuntimeError, BudgetExceeded) as exc:
        errors.append(type(exc).__name__ + ":" + str(exc))
    return {"pass": not errors, "errors": errors, "scope": "INDIVIDUAL_ZIP_INTEGRITY", "sha256": sha}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--sid", required=True)
    args = parser.parse_args()
    report = validate(args.root.resolve(), args.sid)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["pass"] else 1)
