"""Safe, exact-manifest input copying for probe and comparison packages."""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil

from release_rules import release_files, is_link


def prepare_output(root: Path, output: Path) -> tuple[Path, list[Path], str]:
    root = root.resolve(strict=True)
    output = output if output.is_absolute() else root / output
    output = output.absolute()
    if is_link(output) or any(is_link(p) for p in output.parents):
        raise ValueError("Symlink output or parent is not permitted")
    output = output.resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError("Output overlaps source root")
    if output.is_relative_to(root) and not output.is_relative_to(root / "reports"):
        raise ValueError("In-repository experimental output must be under reports/")
    if output.exists():
        raise ValueError("Output exists, refusing to overwrite: " + str(output))
    # Validate all exact inputs before creating anything; never copy unknown data.
    files = release_files(root)
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    output.mkdir(parents=True, exist_ok=False)
    return output, files, digest.hexdigest()


def copy_inputs(root: Path, files: list[Path], target: Path) -> None:
    for path in files:
        dest = target / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
