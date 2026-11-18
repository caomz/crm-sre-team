#!/usr/bin/env python3
"""Windows re-verification of crm-sre-team commit 2b4d70d (GitHub HTTPS sync).

Scope: fetches the pinned commit 2b4d70d over anonymous read-only HTTPS from
the public GitHub repository into a NEW work folder, then runs all checks
locally inside it; writes REPORT.md, results.json and an evidence ZIP there.
The only write outside it is a <VERDICT>-<time>.json in the delivery folder
when a gate stops the run before the work folder exists (if the delivery
folder itself exists). It installs nothing, uses no credentials, never pushes,
and never touches WorkBuddy/DSH host profiles, other clones or credentials;
the tests delete only the temporary files they create inside the work folder.
The DSH desktop-host install/VERIFY is out of scope: docs/17 keeps Windows on
hold until the Mac run is accepted; Node is only recorded.

Run it from a normal Windows PowerShell 5.1 window, not from an agent channel
(agent channels have blocked shutil.rmtree, which the tests and builds need).

Exit codes: 0 PASS; 1 FAIL (at least one check failed); 2 BLOCKED (a
precondition was not met and no check failed); 3 ERROR (the driver itself
stopped on an unexpected error or an interrupt, and no check failed). INFO
and N/A never change it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import locale
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
import zlib
from pathlib import Path

EXPECTED_COMMIT = "2b4d70d0e10f25603e85106159c8213279ef759e"
BRANCH = "codex/deepseek-agent-team"
REPO_URL = "https://github.com/caomz/crm-sre-team.git"
LS_REMOTE_TIMEOUT = 60
FETCH_TIMEOUT = 600
MAC_ZIP_SHA256 = "63ed95e1d4816edde109eef9a6a315c8942f7477ecf921a69e6d176f0dafb724"
# inspect_zip(...)["canonical"] of the same Mac ZIP: every byte except the DEFLATE payloads,
# with only compressed sizes and offsets zeroed, plus each entry's inflated data SHA256.
# build_release.py pins entry order (manifest list, string-sorted), names, ZIP_TIME,
# create_system 3, mode 0o100644 and DEFLATE level 9, so this does not depend on the OS.
MAC_ZIP_CANONICAL = "d25645243d9cf2b306bd197a9dd475b97109c349f9b667e19a8838c4e305d5d5"
MAC_ZLIB = "1.2.12"
# Deepest path the Mac run of tests/ and tools/oncall/ touched, in characters below its
# per-step TEMP folder: 193 measured on this commit, plus 16 for names the trace missed.
DEEPEST_TEMP_RELATIVE = 209
WINDOWS_PATH_LIMIT = 259  # MAX_PATH minus the terminator, without LongPathsEnabled
NODE_FLOOR = (24, 9, 0)
PINNED = {"pytest": "9.1.1", "PyYAML": "6.0.3", "jsonschema": "4.26.0", "referencing": "0.37.0"}
PROXY_ENV_NAMES = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
MUST_PASS = (
    "tests/test_dsh.py::DshBuildTests::test_30c_scoped_persona_registry_or_toolfs_drift_detected",
    "tests/test_dsh_integration.py::DshZipTests::test_25_source_free_installed_payload_verified_and_tamper_rejected",
    "tests/test_dsh_integration.py::DshZipTests::test_25b_installed_payload_uses_canonical_order_under_windows_path_comparison",
    "tests/test_git_hooks.py::PreCommitHookTests::test_19_working_python_and_py_launcher_fallbacks",
    "tests/test_git_hooks.py::PreCommitHookTests::test_27_interpreters_are_selected_by_capability_not_name",
    "tests/test_git_hooks.py::PreCommitHookTests::test_28_explicit_interpreter_is_exclusive_and_repo_anchored",
)
MAC_REFERENCE = {
    "pytest tests/": "2117 passed, 1 skipped (POSIX skips the Windows junction test), 2171 subtests passed",
    "pytest tools/oncall/": "100 passed, 269 subtests passed",
    "check_dsh": "102/102",
    "validate_bundle": "183/183 PASS_STATIC_ONLY",
    "tests/test_git_hooks.py": "29 passed, 32 subtests passed (macOS /bin/sh and dash)",
    "DSH ZIP SHA256": MAC_ZIP_SHA256,
    "DSH ZIP canonical digest": MAC_ZIP_CANONICAL,
    "zlib": MAC_ZLIB,
}
WINDOWS = os.name == "nt"
INSTALL_CHECK = """\
import json, sys, zipfile
from pathlib import Path
repo, archive, target = (Path(p) for p in sys.argv[1:4])
sys.path.insert(0, str(repo / "tools"))
import validate_release
with zipfile.ZipFile(archive) as bundle:
    bundle.extractall(target)
report = validate_release.validate_installation(repo, target / "crm-sre-team")
print(json.dumps(report, ensure_ascii=False))
sys.exit(0 if report["pass"] else 1)
"""


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def redact_url_userinfo(text: str) -> str:
    """Mask accidental user:pass@ segments in any proxy or remote URL echoed by git."""
    return re.sub(r"([a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@", r"\1***@", text)


def level9_deflate(data: bytes) -> bytes:
    """What zipfile writes for ZIP_DEFLATED at compresslevel 9 with this interpreter's zlib."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compressor.compress(data) + compressor.flush()


def inspect_zip(path: Path) -> dict:
    """Walk a single-disk, non-ZIP64 archive byte by byte.

    canonical: SHA256 over every byte except the DEFLATE payloads, with only the compressed
    sizes, the local-header offsets and the central-directory offset zeroed, plus each
    entry's inflated data SHA256.
    level9: every payload equals this interpreter's level-9 raw DEFLATE of the entry data.
    Raises ValueError for any byte the walk cannot account for, for any method other than
    DEFLATE, and for ZIP64 (extra field 0x0001 or 0xFFFF/0xFFFFFFFF sentinels).
    """
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        contents = [archive.read(info) for info in infos]
        comment = archive.comment

    def no_zip64(extra: bytes, where: str) -> None:
        at = 0
        while at + 4 <= len(extra):
            field_id, size = struct.unpack_from("<HH", extra, at)
            if field_id == 0x0001:
                raise ValueError(f"ZIP64 extra field in {where}")
            at += 4 + size

    digest, level9, pos = hashlib.sha256(), True, 0
    for info, data in zip(infos, contents):
        if info.header_offset != pos or raw[pos:pos + 4] != b"PK\x03\x04":
            raise ValueError(f"unexpected bytes before {info.orig_filename!r} at offset {pos}")
        if info.flag_bits & 0x08:
            raise ValueError(f"data descriptor in {info.orig_filename!r}")
        if info.compress_type != zipfile.ZIP_DEFLATED:
            raise ValueError(f"{info.orig_filename!r} is not DEFLATE (method {info.compress_type})")
        name_len, extra_len = struct.unpack_from("<HH", raw, pos + 26)
        header = bytearray(raw[pos:pos + 30 + name_len + extra_len])
        no_zip64(bytes(header[30 + name_len:]), f"the local header of {info.orig_filename!r}")
        header[18:22] = bytes(4)  # compressed size
        digest.update(bytes(header) + hashlib.sha256(data).hexdigest().encode("ascii"))
        payload = raw[pos + len(header):pos + len(header) + info.compress_size]
        level9 = level9 and payload == level9_deflate(data)
        pos += len(header) + info.compress_size
    eocd = len(raw) - 22 - len(comment)
    if eocd < pos or raw[eocd:eocd + 4] != b"PK\x05\x06":
        raise ValueError("end-of-central-directory record is not where the comment length puts it")
    disk_entries, entries, cd_size, cd_offset = struct.unpack_from("<HHII", raw, eocd + 8)
    if 0xFFFF in (disk_entries, entries) or 0xFFFFFFFF in (cd_size, cd_offset):
        raise ValueError("ZIP64 sentinel in the end-of-central-directory record")
    if cd_offset != pos or cd_offset + cd_size != eocd or entries != len(infos):
        raise ValueError("central directory does not directly follow the last entry")
    while pos < eocd:
        if raw[pos:pos + 4] != b"PK\x01\x02":
            raise ValueError(f"unexpected bytes in the central directory at offset {pos}")
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", raw, pos + 28)
        record = bytearray(raw[pos:pos + 46 + name_len + extra_len + comment_len])
        no_zip64(bytes(record[46 + name_len:46 + name_len + extra_len]), f"the central directory at {pos}")
        record[20:24] = bytes(4)  # compressed size
        record[42:46] = bytes(4)  # local header offset
        digest.update(bytes(record))
        pos += len(record)
    if pos != eocd:
        raise ValueError("central directory runs past its end record")
    end = bytearray(raw[eocd:])
    end[16:20] = bytes(4)  # central directory offset (its size stays: it does not depend on compression)
    digest.update(bytes(end))
    return {"canonical": digest.hexdigest(), "level9": level9, "entries": len(infos)}


def hook_ran(trace: Path) -> bool:
    """GIT_TRACE shows git starting the versioned pre-commit hook."""
    text = trace.read_text(encoding="utf-8", errors="replace") if trace.exists() else ""
    return bool(re.search(r"(run_command|start_command):.*pre-commit", text))


DROPPED_ENV = {
    "CRM_SRE_PYTHON", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP",
    "PYTHONOPTIMIZE", "PYTHONWARNINGS", "PYTHONPYCACHEPREFIX",
    "PYTHONINSPECT", "PYTHONNOUSERSITE", "PYTHONSAFEPATH",
}


def dropped(key: str) -> bool:
    """Git redirections, pytest flags and inherited Python settings never reach a child process."""
    upper = key.upper()
    return upper in DROPPED_ENV or upper.startswith(("GIT_", "PYTEST_"))


def sanitized_environ() -> dict:
    # CPython upper-cases os.environ keys on Windows, so PATH/TEMP/TMP have one spelling here.
    return {k: v for k, v in os.environ.items() if not dropped(k)}


def long_paths_enabled():
    """Read-only look at the Windows long-path switch; None off Windows."""
    if not WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0]
    except OSError as exc:
        return f"unreadable ({type(exc).__name__})"


def decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def read_text(path: Path) -> str:
    return decode(path.read_bytes()) if path.exists() else ""


def last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def tail(text: str, count: int = 60) -> str:
    return "\n".join(text.splitlines()[-count:])


class Blocked(Exception):
    pass


class Verifier:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.delivery = Path(args.delivery).resolve()
        self.script = Path(__file__).resolve()
        self.stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.work = Path(args.work_root).resolve() / ("w-" + self.stamp)
        self.repo = self.work / "repo"
        self.logs = self.work / "logs"
        self.python = Path(sys.executable)
        self.results: list[dict] = []
        self.env: dict = {"started": now()}
        self.git = None
        self.sh = None
        self.last_stderr = ""
        self.base_env = sanitized_environ()
        self.work_created = False

    # ----------------------------------------------------------------- helpers
    def say(self, message: str) -> None:
        print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)

    def record(self, check_id: str, title: str, status: str, detail: str = "", log: str = "") -> None:
        self.results.append({"id": check_id, "title": title, "status": status,
                             "detail": detail, "log": log})
        self.say(f"{check_id} {status}: {title}" + (f" -- {detail}" if detail else ""))

    def block_gate(self, check_id: str, title: str, message: str, log: str = "") -> None:
        self.record(check_id, title, "BLOCKED", message, log)
        raise Blocked(message)

    def run(self, name: str, argv, *, cwd=None, env=None, timeout: int = 1800) -> dict:
        out, err = self.logs / f"{name}.out.txt", self.logs / f"{name}.err.txt"
        start = time.monotonic()
        try:
            with open(out, "wb") as fout, open(err, "wb") as ferr:
                proc = subprocess.run([str(item) for item in argv], cwd=cwd, env=env or self.base_env,
                                      stdout=fout, stderr=ferr, stdin=subprocess.DEVNULL, timeout=timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = "TIMEOUT"
        except OSError as exc:
            code = "OSERROR"
            err.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        return {"exit": code, "seconds": round(time.monotonic() - start, 1),
                "out": out, "err": err, "log": f"logs/{name}.*.txt"}

    def capture(self, argv, *, cwd=None, env=None, timeout: int = 300) -> tuple[int, str]:
        """Exit code and stripped stdout only (git warnings on stderr must not leak in)."""
        proc = subprocess.run([str(item) for item in argv], cwd=cwd, env=env or self.base_env,
                              capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout)
        self.last_stderr = last_line(decode(proc.stderr))
        return proc.returncode, decode(proc.stdout).strip()

    def git_https_args(self) -> list[str]:
        """Anonymous HTTPS git prefix; longest-match insteadOf beats shorter global rewrites.

        Git picks http.<url>.* values by URL specificity, so the unscoped resets alone lose to any
        URL-scoped extraHeader/cookieFile in global config; the resets scoped to the full repository
        URL are the most specific possible and come last, so they clear those too.
        """
        if not REPO_URL.startswith("https://"):
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"repository URL must use https://, got {redact_url_userinfo(REPO_URL)!r}")
        prefix = REPO_URL.rsplit("/", 1)[0] + "/"
        return [
            self.git,
            "-c", "credential.helper=",
            "-c", "core.askPass=",
            "-c", "http.extraHeader=",
            "-c", "http.cookieFile=",
            "-c", f"http.{REPO_URL}.extraHeader=",
            "-c", f"http.{REPO_URL}.cookieFile=",
            "-c", "protocol.allow=never",
            "-c", "protocol.https.allow=always",
            "-c", f"url.{prefix}.insteadOf={prefix}",
        ]

    def redact_logs(self, paths=None) -> None:
        """Mask URL user:pass@ segments in log files (every log when paths is None) in place."""
        if paths is None:
            paths = sorted(self.logs.iterdir()) if self.logs.is_dir() else []
        for log_file in paths:
            if log_file.is_file():
                raw_txt = read_text(log_file)
                clean_txt = redact_url_userinfo(raw_txt)
                if clean_txt != raw_txt:
                    log_file.write_text(clean_txt, encoding="utf-8")

    def git_net_env(self) -> dict:
        """Non-interactive network environment used only for the read-only GitHub ls-remote/fetch."""
        return {**self.base_env, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}

    def child_env(self, tmp_name: str, *, extra_path=(), override=None) -> tuple[dict, Path]:
        """Own short TEMP per step; this interpreter first on PATH; sanitized base environment."""
        env = dict(self.base_env)
        tmp = self.work / "t" / tmp_name
        tmp.mkdir(parents=True, exist_ok=False)
        for key in ("TMPDIR", "TEMP", "TMP"):
            env[key] = str(tmp)
        parts = [str(p) for p in extra_path] + [str(self.python.parent)]
        env["PATH"] = os.pathsep.join(parts + [env.get("PATH", "")])
        if override is not None:
            env["CRM_SRE_PYTHON"] = override
        return env, tmp

    def sh_paths(self) -> list[Path]:
        if not WINDOWS or not self.sh:
            return []
        shell_dir = Path(self.sh).parent
        root = shell_dir.parent.parent if shell_dir.parent.name.casefold() == "usr" else shell_dir.parent
        return [shell_dir, root / "mingw64" / "bin"]

    def head(self) -> str:
        """HEAD commit, or a non-hex marker naming the git error (never '' on failure)."""
        code, out = self.capture([self.git, "-C", self.repo, "rev-parse", "HEAD"])
        if code == 0 and re.fullmatch(r"[0-9a-f]{40}", out):
            return out
        return f"<rev-parse failed: exit {code}; {self.last_stderr}>"

    def status(self) -> str:
        """Porcelain status, or a non-empty marker naming the git error (never '' on failure)."""
        code, out = self.capture([self.git, "-C", self.repo, "status", "--porcelain"])
        return out if code == 0 else f"<git status failed: exit {code}; {self.last_stderr}>"

    # ------------------------------------------------------------------- gates
    def gates(self) -> None:
        if not self.delivery.is_dir():
            self.block_gate("G1", "delivery folder & script SHA256",
                            f"delivery folder not found: {self.delivery}")
        if not self.script.is_file():
            self.block_gate("G1", "delivery folder & script SHA256",
                            f"verifier script not found: {self.script}")
        script_sha = sha256(self.script)
        self.env["script_sha256"] = script_sha
        self.env["repo_url"] = redact_url_userinfo(REPO_URL)
        self.record("G1", "delivery folder & script SHA256", "PASS", script_sha[:16])

        python_ok = sys.version_info >= (3, 11)
        versions, missing = {}, []
        for dist, module in (("pytest", "pytest"), ("PyYAML", "yaml"),
                             ("jsonschema", "jsonschema"), ("referencing", "referencing")):
            try:
                __import__(module)
                versions[dist] = metadata.version(dist)
            except Exception as exc:  # noqa: BLE001 - report any import failure as missing
                missing.append(f"{dist} ({type(exc).__name__})")
        self.env.update({"python": str(self.python), "python_version": platform.python_version(),
                         "packages": versions})
        deviations = [f"{k} {versions[k]} (pinned {v})" for k, v in PINNED.items()
                      if k in versions and versions[k] != v]
        self.env["package_deviations"] = deviations
        if not python_ok or missing:
            self.block_gate("G2", "Python runtime",
                            f"Python {platform.python_version()} needs >=3.11 with pytest/PyYAML/"
                            f"jsonschema/referencing; missing: {', '.join(missing) or 'none'}")
        self.record("G2", "Python runtime", "PASS",
                    f"{platform.python_version()} {versions}" +
                    (f"; deviations: {deviations}" if deviations else ""))

        self.git = shutil.which("git")
        if not self.git:
            self.block_gate("G3", "GitHub HTTPS remote & branch head", "git not found on PATH")
        self.env["git"] = self.git
        self.env["git_version"] = self.capture([self.git, "--version"])[1]

        # Path budget before network calls or directory creation: longest per-step TEMP id has 3 chars.
        deepest = len(str(self.work / "t" / "c4a")) + 1 + DEEPEST_TEMP_RELATIVE
        self.env.update({"projected_deepest_path": deepest, "long_paths_enabled": long_paths_enabled()})
        if WINDOWS and deepest > WINDOWS_PATH_LIMIT and self.env["long_paths_enabled"] != 1:
            self.block_gate("E2", "path-length budget (checked before network fetch)",
                            f"work folder too deep: the tests would reach about {deepest} characters "
                            f"(limit {WINDOWS_PATH_LIMIT} without LongPathsEnabled); rerun with a shorter "
                            f"--work-root such as D:\\crm-sre-verify")

        safe_url = redact_url_userinfo(REPO_URL)
        https_git = self.git_https_args()
        # A global insteadOf at least as long as ours still wins; refuse to fetch from anywhere but REPO_URL.
        gu_code, effective_url = 1, ""
        try:
            gu_code, effective_url = self.capture([*https_git, "ls-remote", "--get-url", REPO_URL],
                                                  timeout=LS_REMOTE_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError) as exc:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"git ls-remote --get-url did not complete ({type(exc).__name__}: {exc})")
        self.env["effective_url"] = redact_url_userinfo(effective_url)
        if gu_code != 0:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"git ls-remote --get-url failed (exit {gu_code}): "
                            f"{redact_url_userinfo(self.last_stderr or 'no stderr')[:200]}")
        if effective_url != REPO_URL:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"Git configuration rewrites {safe_url} to {redact_url_userinfo(effective_url)!r} "
                            f"(a url.<base>.insteadOf rule); this run fetches only from {safe_url}")
        try:
            ls_code, ls_out = self.capture(
                [*https_git, "ls-remote", REPO_URL, f"refs/heads/{BRANCH}", "HEAD"],
                env=self.git_net_env(), timeout=LS_REMOTE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"GitHub HTTPS ls-remote timed out after {LS_REMOTE_TIMEOUT}s ({safe_url})")
        except OSError as exc:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"GitHub HTTPS ls-remote failed to start ({type(exc).__name__}: {exc})")
        if ls_code != 0:
            err_note = redact_url_userinfo(self.last_stderr or "no stderr")
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"cannot reach GitHub over HTTPS ({safe_url}, exit {ls_code}): {err_note[:200]}")
        refs = {}
        for line in ls_out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
                refs[parts[1].strip()] = parts[0]
        remote_branch_sha = refs.get(f"refs/heads/{BRANCH}")
        self.env["remote_branch_head"] = remote_branch_sha
        self.env["remote_default_head"] = refs.get("HEAD")
        if not refs:
            self.block_gate("G3", "GitHub HTTPS remote & branch head",
                            f"GitHub HTTPS ls-remote returned no valid git refs ({safe_url}): {ls_out[:160]!r}")
        if remote_branch_sha == EXPECTED_COMMIT:
            self.record("G3", "GitHub HTTPS remote & branch head", "PASS",
                        f"{BRANCH} = {EXPECTED_COMMIT[:12]}")
        else:
            shown = remote_branch_sha[:12] if remote_branch_sha else "absent"
            self.record("G3", "GitHub HTTPS remote reachable (branch head moved/absent; G4 fetches pinned SHA)",
                        "INFO", f"{BRANCH} = {shown}; pinned = {EXPECTED_COMMIT[:12]}")

        self.work.mkdir(parents=True, exist_ok=False)
        self.work_created = True
        self.logs.mkdir()
        init = self.run("g4a-init", [self.git, "-c", "init.defaultBranch=main", "-c", "core.autocrlf=false",
                                     "init", "-q", self.repo])
        if init["exit"] != 0:
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"git init failed (exit {init['exit']}): {last_line(read_text(init['err']))[:200]}",
                            init["log"])
        for cfg_cmd in (
            [self.git, "-C", self.repo, "config", "core.autocrlf", "false"],
            [self.git, "-C", self.repo, "remote", "add", "origin", REPO_URL],
            [self.git, "-C", self.repo, "remote", "set-url", "--push", "origin", "no_push"],
        ):
            rc, _ = self.capture(cfg_cmd)
            if rc != 0:
                self.block_gate("G4", "fresh fetch & checkout from GitHub",
                                f"git repo setup failed ({cfg_cmd[3:5]}, exit {rc}): "
                                f"{redact_url_userinfo(self.last_stderr)[:200]}")
        # The new repository's own config (e.g. from an init template) must not redirect origin either.
        origin_rc, origin_url = self.capture([*https_git, "-C", self.repo, "remote", "get-url", "origin"])
        if origin_rc != 0 or origin_url != REPO_URL:
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"origin resolves to {redact_url_userinfo(origin_url)!r} (exit {origin_rc}), "
                            f"not {safe_url}: a url.<base>.insteadOf rule rewrites it")
        fetch = self.run("g4b-fetch", [*https_git, "-C", self.repo, "fetch", "-q", "--no-tags",
                                       "--no-recurse-submodules", "origin",
                                       f"{EXPECTED_COMMIT}:refs/remotes/origin/{BRANCH}"],
                         env=self.git_net_env(), timeout=FETCH_TIMEOUT)
        self.redact_logs((fetch["out"], fetch["err"]))
        if fetch["exit"] != 0:
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"fetch {EXPECTED_COMMIT[:12]} from GitHub failed (exit {fetch['exit']}): "
                            f"{redact_url_userinfo(last_line(read_text(fetch['err'])))[:200]}",
                            fetch["log"])
        self.env["fetched_from"] = safe_url  # set only after a successful fetch of the pinned commit
        checkout = self.run("g4c-checkout", [self.git, "-C", self.repo, "-c", "core.autocrlf=false",
                                             "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process=",
                                             "-c", "filter.lfs.required=false",
                                             "checkout", "-q", "-B", BRANCH, EXPECTED_COMMIT])
        if checkout["exit"] != 0:
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"checkout {EXPECTED_COMMIT[:12]} failed (exit {checkout['exit']}): "
                            f"{last_line(read_text(checkout['err']))[:200]}",
                            checkout["log"])
        up_rc, _ = self.capture([self.git, "-C", self.repo, "branch", "--set-upstream-to",
                                 f"origin/{BRANCH}", BRANCH])
        if up_rc != 0:
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"setting upstream branch failed (exit {up_rc}): {self.last_stderr[:200]}")
        head, dirty = self.head(), self.status()
        sym_rc, symref = self.capture([self.git, "-C", self.repo, "symbolic-ref", "-q", "HEAD"])
        sh_rc, shallow = self.capture([self.git, "-C", self.repo, "rev-parse", "--is-shallow-repository"])
        if (head != EXPECTED_COMMIT or dirty or sym_rc != 0 or symref != f"refs/heads/{BRANCH}"
                or sh_rc != 0 or shallow != "false"):
            self.block_gate("G4", "fresh fetch & checkout from GitHub",
                            f"clone state check failed: HEAD={head}, symref={symref!r} (rc {sym_rc}), "
                            f"shallow={shallow!r} (rc {sh_rc}), status={dirty!r}")
        self.record("G4", "fresh fetch & checkout from GitHub", "PASS",
                    f"HEAD {head[:12]} on {BRANCH}, non-shallow, clean", fetch["log"])

    def environment(self) -> None:
        self.env.update({
            "os_caption": self.args.os_caption or platform.platform(),
            "platform": platform.platform(),
            "windows_build": (sys.getwindowsversion().build if WINDOWS else None),
            "powershell": self.args.ps_version or None,
            "work": str(self.work),
        })
        if WINDOWS:
            for candidate in [Path(self.capture([self.git, "--exec-path"])[1])]:
                for ancestor in [candidate, *candidate.parents]:
                    for sh in (ancestor / "usr" / "bin" / "sh.exe", ancestor / "bin" / "sh.exe"):
                        if sh.is_file() and not self.sh:
                            self.sh = str(sh)
        else:
            self.sh = shutil.which("sh")
        self.env["sh"] = self.sh
        node = shutil.which("node")
        node_version = ""
        if node:
            try:
                node_version = self.capture([node, "--version"])[1]
            except (OSError, subprocess.SubprocessError) as exc:  # record only; never stops the run
                node_version = f"error {type(exc).__name__}"
        match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", node_version)
        if not node:
            node_status = "NODE_MISSING"
        elif not match:
            node_status = "NODE_UNREADABLE"
        elif tuple(int(x) for x in match.groups()) >= NODE_FLOOR:
            node_status = "NODE_OK"
        else:
            node_status = "NODE_BELOW_FLOOR"
        self.env.update({"node": node, "node_version": node_version, "node_status": node_status})
        self.env["zlib"] = f"{zlib.ZLIB_VERSION} (runtime {getattr(zlib, 'ZLIB_RUNTIME_VERSION', '?')})"
        self.env["python_env_vars"] = sorted(k for k in os.environ
                                             if k.upper().startswith(("PYTHON", "PYTEST_")))
        self.env["proxy_env_vars"] = sorted(k for k in os.environ if k.upper() in PROXY_ENV_NAMES)  # names only
        self.env["env_vars_removed"] = sorted(k for k in os.environ if dropped(k))  # names only, never values
        self.env["git_core_longpaths"] = self.capture([self.git, "-C", self.repo, "config", "--get",
                                                      "core.longpaths"])[1] or "unset"
        deepest = self.env["projected_deepest_path"]
        self.record("E1", "environment recorded", "INFO",
                    f"{self.env['os_caption']}; {self.env['git_version']}; sh={self.sh}; "
                    f"node {node_version or 'missing'} ({node_status}, floor 24.9.0, record only); "
                    f"zlib {self.env['zlib']}")
        self.record("E2", "path-length budget (checked before network fetch)", "INFO",
                    f"projected deepest path {deepest} chars; limit {WINDOWS_PATH_LIMIT} "
                    f"(LongPathsEnabled={self.env['long_paths_enabled']}, git core.longpaths="
                    f"{self.env['git_core_longpaths']})" if WINDOWS else
                    f"projected deepest path {deepest} chars (Windows limit {WINDOWS_PATH_LIMIT}; not "
                    f"enforced here)")

    # ------------------------------------------------------------------ checks
    def pytest_step(self, check_id: str, title: str, name: str, args, timeout: int) -> dict:
        env, _ = self.child_env(check_id.lower())
        result = self.run(name, [self.python, "-m", "pytest", *args, "-p", "no:cacheprovider"],
                          cwd=self.repo, env=env, timeout=timeout)
        text = read_text(result["out"])
        summary = last_line(text)
        skips = [line.strip() for line in text.splitlines() if line.startswith("SKIPPED [")]
        status = "PASS" if result["exit"] == 0 else "FAIL"
        self.record(check_id, title, status, f"exit {result['exit']}; {summary}", result["log"])
        return {"text": text, "skips": skips, "result": result}

    def checks(self) -> None:
        must = self.pytest_step("C1", "must-pass Windows regressions (-v)", "c1-must-pass",
                                ["-v", *MUST_PASS], 1800)
        statuses = {}
        for line in must["text"].splitlines():
            found = re.match(r"^(\S+::\S+) (PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)\b", line)
            if found:
                statuses[found.group(1)] = found.group(2)
        self.env["must_pass"] = {node: statuses.get(node, "NOT_FOUND") for node in MUST_PASS}
        bad = {k: v for k, v in self.env["must_pass"].items() if v != "PASSED"}
        self.record("C1b", "each must-pass node PASSED (none skipped)", "FAIL" if bad else "PASS",
                    json.dumps(bad) if bad else f"{len(MUST_PASS)}/{len(MUST_PASS)} PASSED")

        full = self.pytest_step("C2", "full pytest tests/", "c2-pytest-tests",
                                ["tests/", "-q", "-rfEs"], 5400)
        self.env["full_suite_skips"] = full["skips"]
        self.pytest_step("C3", "pytest tools/oncall/", "c3-pytest-oncall",
                         ["tools/oncall/", "-q", "-rfEs"], 3600)

        for check_id, tool in (("C4a", "check_dsh.py"), ("C4b", "validate_bundle.py"),
                               ("C4c", "check_workbuddy.py")):
            env, _ = self.child_env(check_id.lower())
            result = self.run("c4-" + tool, [self.python, self.repo / "tools" / tool],
                              cwd=self.repo, env=env, timeout=1800)
            text = read_text(result["out"])
            keys = re.findall(r'"(pass|result|checks_total|checks_passed)":\s*([^,\n]+)', text)
            detail = ", ".join(f"{k}={v.strip()}" for k, v in keys[:4])
            self.record(check_id, tool, "PASS" if result["exit"] == 0 else "FAIL",
                        f"exit {result['exit']}; {detail}", result["log"])

        self.release_checks()
        self.rebuild_check()

    def release_checks(self) -> None:
        dist = self.work / "dist"
        dist.mkdir()
        archive = dist / "crm-sre-dsh.zip"
        env, _ = self.child_env("c5a")
        built = self.run("c5-build-release", [self.python, self.repo / "tools" / "build_release.py",
                                              "--root", self.repo, "--output", archive],
                         cwd=self.repo, env=env, timeout=1800)
        zip_sha = sha256(archive) if archive.is_file() else ""
        inspected = {"canonical": "", "level9": False, "entries": 0}
        if archive.is_file():
            try:
                inspected = inspect_zip(archive)
            except Exception as exc:  # noqa: BLE001 - any unreadable or non-canonical archive fails C5a
                inspected["canonical"] = f"<unreadable: {type(exc).__name__}: {exc}>"
        canonical = inspected["canonical"]
        self.env.update({"zip_sha256": zip_sha, "zip_canonical_digest": canonical,
                         "zip_level9_deflate": inspected["level9"]})
        content_same = built["exit"] == 0 and canonical == MAC_ZIP_CANONICAL
        self.record("C5a", "build DSH ZIP; every byte except the DEFLATE payloads equals the Mac build",
                    "PASS" if content_same else "FAIL",
                    f"exit {built['exit']}; {inspected['entries']} entries; canonical {canonical[:60] or 'none'} "
                    f"vs mac {MAC_ZIP_CANONICAL[:16]}", built["log"])
        if zip_sha == MAC_ZIP_SHA256:
            byte_status, byte_note = "PASS", ""
        elif content_same and inspected["level9"]:
            byte_status = "INFO"
            byte_note = (f"; only the DEFLATE payloads differ, and each equals this zlib's level-9 output "
                         f"(zlib {self.env['zlib']} here, {MAC_ZLIB} on the Mac); the ZIP is in the evidence")
        elif content_same:
            byte_status = "FAIL"
            byte_note = "; payloads are not this zlib's level-9 DEFLATE of the data (compression changed)"
        else:
            byte_status, byte_note = "FAIL", "; the archive differs beyond the payloads (see C5a)"
        self.record("C5b", "DSH ZIP bytes equal the Mac build (SHA256)", byte_status,
                    f"here {zip_sha[:16] or 'none'} vs mac {MAC_ZIP_SHA256[:16]}{byte_note}")
        env, _ = self.child_env("c5c")
        checked = self.run("c5-validate-release", [self.python, self.repo / "tools" / "validate_release.py",
                                                   "--root", self.repo, "--zip", archive],
                           cwd=self.repo, env=env, timeout=1800)
        self.record("C5c", "validate_release --zip", "PASS" if checked["exit"] == 0 else "FAIL",
                    f"exit {checked['exit']}", checked["log"])
        helper = self.work / "helpers" / "install_check.py"
        helper.parent.mkdir()
        helper.write_text(INSTALL_CHECK, encoding="utf-8", newline="\n")
        env, _ = self.child_env("c5d")
        installed = self.run("c5-installed-payload", [self.python, helper, self.repo, archive,
                                                      self.work / "install"],
                             cwd=self.work, env=env, timeout=600)
        self.record("C5d", "installed payload validates on this filesystem (was test_25 on Windows)",
                    "PASS" if installed["exit"] == 0 else "FAIL",
                    f"exit {installed['exit']}; {last_line(read_text(installed['out']))[:160]}",
                    installed["log"])

    def rebuild_check(self) -> None:
        env, _ = self.child_env("c6")
        rebuilt = self.run("c6-rebuild", [self.python, self.repo / "tools" / "build_bundle.py",
                                          "--root", self.repo], cwd=self.repo, env=env, timeout=1800)
        dirty = self.status()
        self.record("C6", "rebuild leaves the clone byte-identical (git status clean)",
                    "PASS" if rebuilt["exit"] == 0 and not dirty else "FAIL",
                    f"exit {rebuilt['exit']}; status {dirty!r}", rebuilt["log"])

    def hook_case(self, check_id: str, title: str, override, expect_ok: bool, expect_text: str = "") -> None:
        env, tmp = self.child_env(check_id.lower(), extra_path=self.sh_paths(), override=override)
        result = self.run("c7-" + check_id.lower(), [self.sh, "tools/git-hooks/pre-commit"],
                          cwd=self.repo, env=env, timeout=1200)
        err = read_text(result["err"])
        leftovers = sorted(p.name for p in tmp.iterdir())
        if expect_ok:
            ok = result["exit"] == 0 and not leftovers
        else:
            ok = result["exit"] not in (0, "TIMEOUT", "OSERROR") and expect_text in err and not leftovers
        self.record(check_id, title, "PASS" if ok else "FAIL",
                    f"exit {result['exit']}; tmp leftovers {leftovers}; {last_line(err)[:160]}",
                    result["log"])

    def hooks(self) -> None:
        if not self.sh:
            self.record("H0", "hook checks need a POSIX sh", "BLOCKED",
                        "no Git for Windows usr/bin/sh.exe found next to `git --exec-path`")
            return
        posix_python = self.python.as_posix()
        self.hook_case("H1", "hook, no override: PATH discovery picks a capable Python", None, True)
        if WINDOWS:
            self.hook_case("H2", "hook, CRM_SRE_PYTHON = backslash absolute path", str(self.python), True)
        else:
            self.record("H2", "hook, CRM_SRE_PYTHON = backslash absolute path", "N/A", "Windows only")
        self.hook_case("H3", "hook, CRM_SRE_PYTHON = forward-slash absolute path", posix_python, True)
        missing = str(self.work / "no-such-dir" / ("python.exe" if WINDOWS else "python"))
        self.hook_case("H4", "hook, missing CRM_SRE_PYTHON fails closed before export", missing, False,
                       "CRM_SRE_PYTHON does not meet the project runtime")
        shim = self.repo / "win-shim" / "py-shim"
        shim.parent.mkdir()
        shim.write_bytes(f"#!/bin/sh\nexec '{posix_python}' \"$@\"\n".encode("utf-8"))
        shim.chmod(0o755)
        relative = "win-shim\\py-shim" if WINDOWS else "win-shim/py-shim"
        self.hook_case("H5", f"hook, CRM_SRE_PYTHON = repo-relative {relative!r}", relative, True)
        status = self.status()
        self.record("H5b", "hooks left tracked files untouched", "PASS" if status == "?? win-shim/" else "FAIL",
                    f"status {status!r}")

        env, _ = self.child_env("h6i")
        installed = self.run("h6-install-hooks", [self.python, self.repo / "tools" / "install_git_hooks.py",
                                                  "--root", self.repo], cwd=self.repo, env=env, timeout=300)
        hooks_path = self.capture([self.git, "-C", self.repo, "config", "--local", "--get", "core.hooksPath"])[1]
        self.record("H6i", "install_git_hooks.py sets core.hooksPath in the scratch clone",
                    "PASS" if installed["exit"] == 0 and hooks_path == "tools/git-hooks" else "FAIL",
                    f"exit {installed['exit']}; core.hooksPath {hooks_path!r}", installed["log"])
        identity = ["-c", "user.name=win-verify", "-c", "user.email=win-verify@test.invalid",
                    "-c", "commit.gpgsign=false"]
        before = self.head()
        env, _ = self.child_env("h6", override=missing)
        trace6 = self.logs / "h6-commit-reject.git-trace.txt"
        env["GIT_TRACE"] = str(trace6)  # git's own record that it ran tools/git-hooks/pre-commit
        rejected = self.run("h6-commit-reject", [self.git, *identity, "commit", "--allow-empty", "-m",
                                                 "win-verify: gate must reject"], cwd=self.repo, env=env)
        unchanged = self.head() == before
        ran6 = hook_ran(trace6)
        said6 = "CRM_SRE_PYTHON does not meet the project runtime" in read_text(rejected["err"])
        refused = rejected["exit"] not in (0, "TIMEOUT", "OSERROR")
        self.record("H6", "real git commit: the hook runs and rejects a bad CRM_SRE_PYTHON (HEAD unchanged)",
                    "PASS" if refused and unchanged and ran6 and said6 else "FAIL",
                    f"exit {rejected['exit']}; head unchanged {unchanged}; hook ran {ran6}; "
                    f"fail-closed message {said6}", rejected["log"])
        env, _ = self.child_env("h7", override=posix_python)
        trace7 = self.logs / "h7-commit-pass.git-trace.txt"
        env["GIT_TRACE"] = str(trace7)
        landed = self.run("h7-commit-pass", [self.git, *identity, "commit", "--allow-empty", "-m",
                                             "win-verify: gate accepts the explicit interpreter"],
                          cwd=self.repo, env=env)
        after = self.head()
        moved = after != before and bool(re.fullmatch(r"[0-9a-f]{40}", after))
        ran7 = hook_ran(trace7)
        self.record("H7", "real git commit: the hook runs and passes with CRM_SRE_PYTHON (scratch clone only)",
                    "PASS" if landed["exit"] == 0 and moved and ran7 else "FAIL",
                    f"exit {landed['exit']}; head moved {moved}; hook ran {ran7}", landed["log"])

    # ------------------------------------------------------------------ report
    def finish(self, blocked: str = "", error: str = "") -> int:
        self.env["finished"] = now()
        statuses = [r["status"] for r in self.results]
        if "FAIL" in statuses:
            verdict = "FAIL"
        elif error:
            verdict = "ERROR"
        elif blocked or "BLOCKED" in statuses:
            verdict = "BLOCKED"
        else:
            verdict = "PASS"
        code = {"PASS": 0, "FAIL": 1, "BLOCKED": 2, "ERROR": 3}[verdict]
        reason = "; ".join(x for x in (blocked, error) if x)
        payload = {"verdict": verdict, "blocked": blocked, "error": error, "commit": EXPECTED_COMMIT,
                   "environment": self.env, "results": self.results, "mac_reference": MAC_REFERENCE}
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        if not self.work_created:
            self.say(f"VERDICT {verdict}" + (f": {reason}" if reason else ""))
            if self.delivery.is_dir():
                # The single write outside the work folder: the run stopped before the folder existed.
                fallback = self.delivery / f"{verdict}-{self.stamp}.json"
                fallback.write_text(text, encoding="utf-8")
                self.say(f"Report (no work folder was created): {fallback}")
            else:
                self.say(f"Report: none written (delivery folder does not exist: {self.delivery})")
            return code
        (self.work / "results.json").write_text(text, encoding="utf-8")
        if not self.logs.is_dir():
            self.say(f"VERDICT {verdict}" + (f": {reason}" if reason else ""))
            self.say(f"Report (the logs folder could not be created): {self.work / 'results.json'}")
            return code
        self.redact_logs()  # every log, also when a run was interrupted mid-fetch, before reporting/zipping
        safe_url = redact_url_userinfo(REPO_URL)
        source = (f"fetched via anonymous HTTPS from `{self.env['fetched_from']}`" if self.env.get("fetched_from")
                  else f"target `{safe_url}`; NOT fetched in this run, see G3/G4")
        lines = [f"# crm-sre-team Windows re-verification (GitHub sync): {verdict}", "",
                 f"- Commit: `{EXPECTED_COMMIT}` ({BRANCH}, {source})",
                 f"- Started / finished: {self.env.get('started')} / {self.env['finished']}",
                 f"- Work folder: `{self.work}`",
                 "- Scope: read-only anonymous HTTPS fetch of the pinned commit from GitHub, followed by local "
                 "repository checks only. DSH desktop-host install, VERIFY and sessions: NOT_RUN "
                 "(docs/17 holds Windows until the Mac run is accepted).", ""]
        if blocked:
            lines += [f"**BLOCKED:** {blocked}", ""]
        if error:
            lines += [f"**ERROR (driver):** {error}", ""]
        lines += ["## Environment", ""]
        for key in ("os_caption", "windows_build", "powershell", "script_sha256", "repo_url", "effective_url",
                    "remote_branch_head", "python", "python_version", "packages",
                    "package_deviations", "python_env_vars", "proxy_env_vars", "env_vars_removed",
                    "zlib", "git_version", "sh", "long_paths_enabled", "git_core_longpaths",
                    "projected_deepest_path", "node_version", "node_status", "zip_sha256",
                    "zip_canonical_digest", "zip_level9_deflate"):
            lines.append(f"- {key}: `{self.env.get(key)}`")
        lines += ["", "## Checks", "", "| ID | Check | Status | Detail |", "| --- | --- | --- | --- |"]
        for r in self.results:
            detail = str(r["detail"]).replace("|", "/").replace("\n", " ")[:300]
            lines.append(f"| {r['id']} | {r['title']} | {r['status']} | {detail} |")
        if self.env.get("must_pass"):
            lines += ["", "## Must-pass nodes", ""]
            lines += [f"- {status}: `{node}`" for node, status in self.env["must_pass"].items()]
        lines += ["", "## Full-suite skips", ""]
        lines += [f"- {s}" for s in self.env.get("full_suite_skips", [])] or ["- none recorded"]
        lines += ["", "## Mac reference (same commit)", ""]
        lines += [f"- {k}: {v}" for k, v in MAC_REFERENCE.items()]
        failures = [r for r in self.results if r["status"] in ("FAIL", "BLOCKED") and r.get("log")]
        if failures:
            lines += ["", "## Failure excerpts (last 60 lines of each log)", ""]
            for r in failures:
                stem = r["log"].replace("logs/", "").replace(".*.txt", "")
                for suffix in (".out.txt", ".err.txt"):
                    text = redact_url_userinfo(tail(read_text(self.logs / (stem + suffix))))
                    if text:
                        lines += [f"### {r['id']} {stem}{suffix}", "", "```", text, "```", ""]
        report = self.work / "REPORT.md"
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        evidence = self.work / f"evidence-{self.stamp}.zip"
        built_zip = self.work / "dist" / "crm-sre-dsh.zip"  # kept so the Mac side can inspect any C5 result
        with zipfile.ZipFile(evidence, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [report, self.work / "results.json", *sorted(self.logs.iterdir()),
                         *([built_zip] if built_zip.is_file() else [])]:
                archive.write(path, path.relative_to(self.work).as_posix())
        digest = sha256(evidence)
        (self.work / (evidence.name + ".sha256")).write_text(f"{digest}  {evidence.name}\n", encoding="utf-8")
        self.say(f"VERDICT {verdict}" + (f": {reason}" if reason else ""))
        self.say(f"Report:   {report}")
        self.say(f"Evidence: {evidence}  sha256 {digest}")
        return code

    def main(self) -> int:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(errors="replace")  # GBK consoles must not crash on rare characters
        try:
            self.gates()
            self.environment()
            self.checks()
            self.hooks()
        except Blocked as exc:
            return self.finish(blocked=str(exc))
        except KeyboardInterrupt:
            return self.finish(error="interrupted by the operator")
        except Exception as exc:  # noqa: BLE001 - still leave a report behind
            return self.finish(error=f"driver error {type(exc).__name__}: {exc}")
        return self.finish()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delivery", required=True,
                        help="delivery folder holding this script (fallback location if a gate blocks early)")
    parser.add_argument("--work-root", default=r"D:\crm-sre-verify" if WINDOWS else "crm-sre-verify",
                        help="parent for a new timestamped work folder (nothing outside it is written)")
    parser.add_argument("--os-caption", default="", help="Win32_OperatingSystem caption and version")
    parser.add_argument("--ps-version", default="", help="PowerShell version of the calling window")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()  # a usage error exits 2 here: the invocation itself is the unmet precondition
    try:
        sys.exit(Verifier(arguments).main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - even writing the report failed; never exit as FAIL (1)
        print(f"VERDICT ERROR: the driver could not finish ({type(exc).__name__}: {exc})", flush=True)
        sys.exit(3)
