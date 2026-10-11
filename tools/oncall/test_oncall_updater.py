"""Static updater contracts. Not a PowerShell parser or Windows runtime test.

Run explicitly: python3 -m pytest tools/oncall/test_oncall_updater.py -q
The tests live here to keep this change inside the approved tools/oncall scope.
"""
from pathlib import Path
import hashlib
import json
import re
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/oncall/Update-CrmSreTeam.ps1"
RUNBOOK = Path("/Volumes/HDD/download/v364-runbook-r2/ONCALL_RUNBOOK.md")
RUNBOOK_SHA = "50ed48a24dcdd9a06705c4475acbe8596d74e1b4b639fe89b696d6202d068f77"
FRAGMENT_SHA = {
    "Write-Utf8Lf": "787a6524dce97cfb7867a347ff52d7270a374762c727d2332e2a5584ef6c9dac",
    "Protect-Output": "3452005a15a008929b6c3d281680c9444625417a7d5a6e298dbb9fbb02b4e33e",
    "Get-ManifestHashes": "900ccad16d170aa5342f5952f85073a29f45165c6ff377948e978e62a44d0be9",
    "Assert-HashesEqual": "73a7b4e3c21309629ec03efb21eeba8d5076baeecef4cf9222ed726be51d01d9",
    "Assert-PathSetEqual": "3a455289237138a073d667bbca2173672769089cdd10942e1b44226d9ab35248",
    "Get-PackageFiles": "035038b65e69cf51f1f754dc981f479b0515811ea61e6bbdf2539374b7d366ca",
    "Get-InstallFullPath": "ab798a6242531d63e910de7fef93b86243fd696512bed2ecc91136cd0e88f11a",
    "Assert-NoInstallReparse": "d210694c8c14688a6bef0dfc286cb63d184ad81a94380f5e7685628a38f8ef8d",
    "Assert-InstallPaths": "aaf2d28fe23fcaa755a0ca154b79fd81acb7c37604d9f4cd8a7f5ab47b5b51e0",
    "Get-SelectedPackageHashes": "2180a782c2515ba98cfe32858b0ebb03988b45d53c1ad199905f3c9f43837ea1",
    "Invoke-IoRetry": "b92c6f10125a66657e79e81866cb03fe2e56a5ac6bae35fe58e5dbd6e29e6bd4",
    "Save-InstallState": "1b1901965fe73ee92eee29d196de550db511c58b21c10293c3c5d2ed66dc02aa",
    "ReadShared": "c9e628d6b56de22a05b5dd41c258c603a1b5d00c3b454be13f0e23c588eaf773",
    "Assert-NoEvidenceReparse": "d69977fe164aaf1351c432ce7f9121507a4883af39a87434c33cd77916d99ba9",
    "block-20": "5b0d3710558af44aeac59e8d7a73b6d61521bb42ef7db38f84e1d7beea0dc431",
    "block-22": "1774e3b4d40e778caad99946079a43a55690e81175aa9c47dabaa3a22cdaddad",
    "stage-17": "320a89cd94c2c53a553df95ea53ebe647bf27255fd9cb5cfab3f66a2a5be5c66",
}
REPO_ONLY = ["tools/oncall/README.md", "tools/oncall/Update-CrmSreTeam.ps1",
             "tools/oncall/test_oncall_updater.py"]


def decode_script(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8")
        if "\ufeff" in text:
            raise ValueError("Unexpected embedded BOM")
        return text
    return raw.decode("ascii")


def fragments(text):
    return re.findall(r"^# R2-BEGIN ([\w-]+)\n(.*?)^# R2-END \1\n", text, re.M | re.S)


def function_body(text, name):
    """Select one top-level function for bounded static contract checks."""
    found = re.search(rf"^function {re.escape(name)}\b.*?(?=^function |^# Main orchestration\.|\Z)",
                      text, re.M | re.S)
    if not found:
        raise AssertionError(f"Missing function: {name}")
    return found.group()


def mask_literals(text):
    """Conservative quote/comment masker for token checks, not a PS parser."""
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "#":
            end = text.find("\n", i)
            if end < 0:
                break
            result.append("\n")
            i = end + 1
            continue
        if char in {"'", '"'}:
            quote = char
            i += 1
            while i < len(text):
                if quote == '"' and text[i] == "`":
                    i += 2
                    continue
                if text[i] == quote:
                    if i + 1 < len(text) and text[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            else:
                raise ValueError("Unterminated literal")
            result.append("''")
            continue
        result.append(char)
        i += 1
    return "".join(result)


class OncallUpdaterStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SCRIPT.read_bytes()
        cls.text = decode_script(cls.raw)
        cls.code = mask_literals(cls.text)
        cls.readme = (ROOT / "tools/oncall/README.md").read_text(encoding="utf-8")
        update_section = cls.readme.split("## 一次完整更新的命令序列\n", 1)[1]
        cls.bootstrap = re.search(r"```powershell\n(.*?)\n```", update_section, re.S).group(1)
        alternative = update_section.split("### 没有现成来源仓库时：GitHub 直接 clone 备选\n", 1)[1]
        cls.github_bootstrap = re.search(r"```powershell\n(.*?)\n```", alternative, re.S).group(1)

    def test_encoding_is_utf8_bom_and_lf(self):
        self.assertTrue(self.raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", self.raw)
        with self.assertRaises(UnicodeDecodeError):
            decode_script("中文".encode("utf-8"))
        with self.assertRaises(ValueError):
            decode_script(b"\xef\xbb\xbf\xef\xbb\xbf")
        self.assertIn("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8", self.text)
        self.assertIn("$OutputEncoding = [System.Text.Encoding]::UTF8", self.text)

    def test_static_ps51_tokens_and_balanced_delimiters(self):
        self.assertIn("#requires -Version 5.1", self.text)
        for pattern in [r"\?\?=?", r"\?\.", r"&&", r"\|\|", r"ForEach-Object\s+-Parallel",
                        r"\$(?:IsWindows|IsLinux|IsMacOS|PSStyle)\b", r"(?m)^\s*(?:using|class)\b"]:
            self.assertNotRegex(self.code, pattern)
        self.assertNotIn("?", self.code, "PS7 ternary/null operators are disallowed outside literals")
        stack = []
        pairs = {")": "(", "]": "[", "}": "{"}
        for char in self.code:
            if char in "([{":
                stack.append(char)
            elif char in ")]}":
                self.assertTrue(stack, f"Unmatched {char}")
                self.assertEqual(stack.pop(), pairs[char])
        self.assertEqual(stack, [])

    def test_six_modes_required_release_inputs_and_pinned_lengths(self):
        self.assertIn("[ValidateSet('PLAN','APPLY','VERIFY','ROLLBACK','DRILL','UPDATE')]", self.text)
        self.assertIn("[string]$Mode = 'PLAN'", self.text)
        for name, length in [("ExpectedCommit", 40), ("ExpectedZipSha256", 64)]:
            self.assertRegex(self.text, rf"\[Parameter\(Mandatory=\$true\)\]\[ValidatePattern\('[^']*\{{{length}\}}[^']*'\)\]\[string\]\${name}")
        self.assertIn("[Parameter(Mandatory=$true)]", self.text.split("[string]$Tag")[0])
        for mode in ["PLAN", "APPLY", "VERIFY", "ROLLBACK", "DRILL", "UPDATE"]:
            self.assertIn(f"$Mode -ceq '{mode}'", self.text)
        for name in ["PlanPath", "PlanSha256", "RunPytest", "SessionId", "AgentId", "Drill", "ExpectedScriptSha256"]:
            self.assertIn("$" + name, self.text)
        optional_hash = re.search(r"(?m)^\s*([^\n]*\$ExpectedScriptSha256[^\n]*)$", self.text).group(1)
        self.assertIn("{64}", optional_hash)
        self.assertNotIn("Mandatory", optional_hash)
        self.assertIn("[switch]$Drill", self.text)

    def test_bootstrap_checks_identity_before_dispatch_and_raw_blob(self):
        check = function_body(self.text, "Assert-UpdaterIdentity")
        self.assertIn("$ExpectedScriptSha256 -and", check)
        self.assertIn("-ine $ExpectedScriptSha256", check)
        self.assertIn("Join-Path $Probe '.git'", check)
        self.assertIn("if (-not $WorkTree)", check)
        self.assertIn("'--no-optional-locks'", check)
        self.assertIn("'--is-inside-work-tree'", check)
        self.assertIn("$Head -cne $ExpectedCommit -or $Dirty", check)
        self.assertIn("'--untracked-files=all'", check)
        self.assertIn("$ExpectedCommit + ':' + $Relative", check)
        self.assertIn("'hash-object','--no-filters','--',$PSCommandPath", check)
        self.assertIn("if ($CommitBlob -cne $DiskBlob) { throw", check)
        self.assertLess(check.index("if ($CommitBlob -cne $DiskBlob)"), check.index("return $WorkTree"))
        standalone = check.split("if (-not $WorkTree)", 1)[1].split("\n", 1)[0]
        self.assertIn("return }", standalone)
        self.assertNotIn("-Recurse", check)
        self.assertNotIn("ReadShared", check)
        dispatch = self.text.rsplit("\ntry {", 1)[1]
        self.assertIn("$VerifiedWorkTree = Assert-UpdaterIdentity", dispatch)
        self.assertLess(dispatch.index("Assert-UpdaterIdentity"), dispatch.index("$Mode -ceq 'UPDATE'"))
        self.assertLess(dispatch.index("Assert-UpdaterIdentity"), dispatch.index(". Invoke-OncallMode 'PLAN'"))

    def test_plan_clones_verified_worktree_and_only_standalone_uses_github(self):
        plan = self.text.split("function Invoke-OncallMode", 1)[1].split("# R2-BEGIN stage-17", 1)[0]
        self.assertRegex(plan, r"if \(\$VerifiedWorkTree\) \{ \$CloneSource = \$VerifiedWorkTree \}\s*"
                              r"else \{ \$CloneSource = \$RepoUrl \}")
        self.assertEqual(self.code.count("$CloneSource ="), 2)
        clone = next(line for line in plan.splitlines() if "'clone'" in line)
        for token in ["'clone','--no-local'", "'--branch',$Tag,'--single-branch'",
                      "'--config','core.autocrlf=false'", "'--config','core.hooksPath=NUL'",
                      "'credential.helper='", "'credential.interactive=never'", "'core.askPass='",
                      "'http.extraHeader='", "$CloneSource,$Repo"]:
            self.assertIn(token, clone)
        self.assertNotIn("$RepoUrl", clone)
        self.assertLess(plan.index("$CloneSource = $VerifiedWorkTree"), plan.index(clone.strip()))
        self.assertLess(plan.index(clone.strip()), plan.index("Assert-CloneIdentity"))
        self.assertIn("Use the updater from this tag, not a different release", plan)
        self.assertEqual(plan.count("Assert-CloneIdentity"), 2)
        identity = function_body(self.text, "Assert-CloneIdentity")
        self.assertIn("'refs/tags/' + $Tag + '^{commit}'", identity)
        self.assertIn("$Head -cne $ExpectedCommit -or $TagCommit -cne $ExpectedCommit -or $Dirty", identity)
        self.assertIn("NOT RUN ON WINDOWS", self.text.split("[CmdletBinding()]", 1)[0])

    def test_clone_source_is_visible_in_terminal_and_log_even_on_failure(self):
        plan = self.text.split("function Invoke-OncallMode", 1)[1].split("# R2-BEGIN stage-17", 1)[0]
        self.assertIn("$CloneSourceMessage = 'Clone source: ' + $CloneSource", plan)
        self.assertIn("Write-Host (Protect-Output $CloneSourceMessage)", plan)
        clone = next(line for line in plan.splitlines() if "'clone'" in line)
        self.assertIn("(Join-Path $Artifacts 'clone.txt') $CloneSourceMessage", clone)
        native = function_body(self.text, "Invoke-Native")
        self.assertIn("[string]$LogHeader = ''", native)
        self.assertIn("if ($LogHeader) { $LogText = (Protect-Output $LogHeader)", native)
        self.assertLess(native.index("Write-Utf8Lf $Log $LogText"), native.index("if ($Code -ne 0)"))

    def test_default_python_is_verified_python312_without_alias_fallback(self):
        default = r"C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe"
        self.assertIn(f"[string]$PythonExe = '{default}'", self.text)
        plan = self.text.split("function Invoke-OncallMode")[1].split("# R2-BEGIN stage-17")[0]
        self.assertIn("Test-Path -LiteralPath $PythonExe -PathType Leaf", plan)
        self.assertIn("pass -PythonExe with the verified real interpreter path", plan)
        self.assertLess(plan.index("Test-Path -LiteralPath $PythonExe"), plan.index("New-SafeDirectory $CloneRoot"))
        self.assertNotIn("$PythonExe = 'python3'", self.text)
        self.assertIn("*\\WindowsApps\\*", function_body(self.text, "Get-NativeProgram"))

    def test_update_keeps_plan_in_process_drills_before_one_real_confirmation(self):
        dispatch = self.text.rsplit("\ntry {", 1)[1]
        plan = dispatch.index(". Invoke-OncallMode 'PLAN' -FromUpdate")
        gate = dispatch.index("if ($Drill -or -not (Test-SuccessfulDrill))")
        drill = dispatch.index(". Invoke-OncallMode 'DRILL' -FromUpdate")
        apply = dispatch.index(". Invoke-OncallMode 'APPLY' -FromUpdate")
        self.assertTrue(plan < gate < drill < apply)
        self.assertIn("$PlanPath -or $PlanSha256 -or $SessionId -or $AgentId", dispatch)
        self.assertIn("exit 1", dispatch)
        self.assertNotIn("catch", dispatch[:apply])
        self.assertNotIn("Confirm-Yes", dispatch)
        main = self.text.split("# Main orchestration.")[1]
        drill_body = main.split("} elseif ($Mode -ceq 'DRILL')")[1].split("\ntry {", 1)[0]
        self.assertIn("if (-not $FromUpdate) { Confirm-Yes", drill_body)
        self.assertEqual(drill_body.count("Confirm-Yes"), 1)
        apply_body = main.split("$Mode -ceq 'APPLY'")[1].split("$Mode -ceq 'VERIFY'")[0]
        self.assertEqual(apply_body.count("Confirm-Yes"), 1)
        self.assertLess(apply_body.index("Write-Host ($Document | ConvertTo-Json"), apply_body.index("Confirm-Yes"))
        reuse = function_body(self.text, "Test-SuccessfulDrill")
        for token in ["-Directory -Filter 'drill-*'", "'drill-report.json'", "'PASS_APPLY_ROLLBACK_ONLY'",
                      "'NOT_ACCESSED_BY_DRILL'", "$DrillState.mode -ceq 'DRILL'", "$DrillState.fault -ceq 'NONE'",
                      "$DrillState.stage -ceq 'ROLLED_BACK'", "Assert-Under $Report.state $Directory.FullName"]:
            self.assertIn(token, reuse)
        self.assertNotIn("-Recurse", reuse)
        self.assertNotIn("Confirm-Yes", reuse)

    def test_printed_verify_command_has_filled_plan_and_release_arguments(self):
        command = function_body(self.text, "Get-VerifyCommand")
        for token in ["Quote-PowerShellArgument $PSCommandPath", "' -Mode VERIFY'", "@('Tag',$Tag)",
                      "@('ExpectedCommit',$ExpectedCommit)", "@('ExpectedZipSha256',$ExpectedZipSha256)",
                      "@('PlanPath',$PlanPath)", "@('PlanSha256',$PlanSha256)", "@('GitExe',$Git)"]:
            self.assertIn(token, command)
        self.assertIn("if ($ExpectedScriptSha256)", command)
        self.assertIn("if ($SelectedSessionId)", command)
        self.assertNotRegex(command, r"<[^>]+>")
        self.assertIn("$Value.Replace(\"'\",\"''\")", function_body(self.text, "Quote-PowerShellArgument"))
        apply = self.text.split("$Mode -ceq 'APPLY'")[1].split("$Mode -ceq 'VERIFY'")[0]
        self.assertIn("Write-Host (Get-VerifyCommand)", apply)

    def test_verify_without_ids_lists_recent_lead_metadata_then_stops(self):
        metadata = function_body(self.text, "Show-RecentSessionMetadata")
        self.assertEqual(metadata.count("Get-ChildItem"), 2)
        self.assertIn("Get-ChildItem -LiteralPath $Projects -Directory -Force", metadata)
        self.assertIn("Get-ChildItem -LiteralPath $Project.FullName -File -Filter '*.jsonl'", metadata)
        self.assertIn("$Lead.LastWriteTimeUtc -le $CompletedUtc", metadata)
        for token in ["$Lead.BaseName", "$Lead.Length", "$Lead.CreationTimeUtc", "$Lead.LastWriteTimeUtc",
                      "Assert-NoEvidenceReparse $Lead.FullName", "Get-VerifyCommand $Candidate.session_id"]:
            self.assertIn(token, metadata)
        for token in ["-Recurse", "ReadShared", "Get-Content", "ReadAll", "Get-FileHash", "Write-NewJson", "subagents"]:
            self.assertNotIn(token, metadata)
        verify = self.text.split("} elseif ($Mode -ceq 'VERIFY')")[1].split("} elseif ($Mode -ceq 'ROLLBACK')")[0]
        no_id = verify.split("if (-not $SessionId -and -not $AgentId) {")[1].split("}", 1)[0]
        self.assertIn("Show-RecentSessionMetadata (Get-ApplyCompletedUtc)", no_id)
        self.assertIn("return", no_id)
        self.assertLess(verify.index("Show-RecentSessionMetadata"), verify.index("Test-InstalledDeclaredFiles"))
        self.assertLess(verify.index("Show-RecentSessionMetadata"), verify.index("Collect-SessionEvidence"))
        self.assertIn("completed_utc=$AppliedUtc.ToString('o')", self.text)
        completion = function_body(self.text, "Get-ApplyCompletedUtc")
        self.assertIn("'apply-report.json'", completion)
        self.assertIn("$ApplyReport.plan_sha256 -ine $PlanSha256", completion)
        self.assertIn("ParseExact", completion)
        evidence = function_body(self.text, "Collect-SessionEvidence")
        lead_only = evidence.split("if (-not $HasAgentId) {")[1].split("continue", 1)[0]
        self.assertIn("Member=$null", lead_only)
        self.assertIn("if ($HasAgentId) { $Files +=", evidence)

    def test_verbatim_r2_fragments_have_fixed_hashes_and_multiplicity(self):
        found = fragments(self.text)
        self.assertEqual({name for name, _ in found}, set(FRAGMENT_SHA))
        for name in FRAGMENT_SHA:
            chunks = [body for key, body in found if key == name]
            self.assertEqual(len(chunks), 2 if name in {"block-20", "block-22"} else 1)
            for chunk in chunks:
                self.assertEqual(hashlib.sha256(chunk.encode("utf-8")).hexdigest(), FRAGMENT_SHA[name], name)
        # On this Mac, also compare the authorized r2 source itself. On Windows,
        # the fixed fragment hashes above provide the same offline byte check.
        if RUNBOOK.is_file():
            source_raw = RUNBOOK.read_bytes()
            self.assertEqual(hashlib.sha256(source_raw).hexdigest(), RUNBOOK_SHA)
            source = source_raw.decode("utf-8")
            for name, chunk in found:
                self.assertIn(chunk, source, name)

    def test_original_post_copy_verify_remains_before_market_write(self):
        for name, block in fragments(self.text):
            if name != "block-20":
                continue
            copy = block.index("Copy-Item -LiteralPath $PackageRoot -Destination $InstallSource -Recurse")
            paths = block.index("Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $InstallSource)")
            hashes = block.index("Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $InstallSource)")
            market = block.index("$InstallStage = 'MARKET_WRITE'")
            self.assertTrue(copy < paths < hashes < market)
            self.assertNotIn("Test-InstalledDeclaredFiles", block)

    def test_no_delete_kill_network_download_policy_or_git_publish(self):
        for token in [r"\bRemove-Item\b", r"\bStop-Process\b", r"\bSet-ExecutionPolicy\b",
                      r"\b(?:Invoke-WebRequest|Invoke-RestMethod|Start-BitsTransfer)\b",
                      r"\b(?:curl|wget|setx|rmdir|del|rm)\b"]:
            self.assertNotRegex(self.code, token)
        self.assertNotRegex(self.text, r"(?i)['\"](?:push|reset|rebase|merge|fetch|pull|checkout)['\"]")
        self.assertIn("'credential.helper='", self.text)
        self.assertIn("'--config','core.autocrlf=false'", self.text)
        self.assertIn("'--config','core.hooksPath=NUL'", self.text)
        for name in ["GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE"]:
            self.assertIn(f"$env:{name} =", self.text)
        env_lines = [line.strip() for line in self.code.splitlines() if "$env:" in line]
        for line in env_lines:
            self.assertRegex(line, r"^\$env:[A-Za-z0-9_]+\s*=")
        for name in ["TEMP", "TMP", "TMPDIR"]:
            self.assertIn(f"$env:{name} = $TaskTemp", self.text)
        self.assertIn("$env:PYTHONDONTWRITEBYTECODE = '1'", self.text)

    def test_plan_hash_paths_and_confirmation_gates(self):
        self.assertIn("if ($Read.Sha -ine $PlanSha256)", self.text)
        self.assertIn("-PlanPath and -PlanSha256", self.text)
        self.assertIn("Assert-PlanLayout $Document", self.text)
        self.assertIn("$Document.script_sha256 -ine", self.text)
        self.assertIn("Assert-InstallPaths -RequirePlan", self.text)
        self.assertIn("-cne 'YES'", self.text)
        self.assertIn("$Handoff = 'D:\\crm-v36-handoff'", self.text)
        self.assertIn("$DevRoot = 'D:\\Dev'", self.text)
        self.assertIn("$Repo = Join-Path $CloneRoot 'repo'", self.text)
        main = self.text.split("# Main orchestration.")[1]
        apply = main.split("$Mode -ceq 'APPLY'")[1].split("$Mode -ceq 'VERIFY'")[0]
        self.assertLess(apply.index("Assert-ClientStopped"), apply.index("Confirm-Yes"))
        self.assertLess(apply.index("Confirm-Yes"), apply.index("# R2-BEGIN block-20"))
        self.assertLess(apply.index("$null = Load-Plan"), apply.index("# R2-BEGIN block-20"))
        self.assertIn("Assert-OldSource $InstallSource $Document.old_source", apply)

    def test_drill_uses_synthetic_context_and_state_reload(self):
        main = self.text.split("# Main orchestration.")[1]
        hydration = main.split("$Document = Load-Plan")[1].split("$Mode -ceq 'APPLY'")[0]
        self.assertIn("} else { . Import-PlanContext $Document }", hydration)
        self.assertIn("if ($Mode -ceq 'DRILL')", hydration)
        drill = main.split("} elseif ($Mode -ceq 'DRILL')")[1]
        self.assertIn("$DrillRoot = Join-Path $Handoff ('drill-' + $RunId)", drill)
        self.assertIn("$InstallMode = 'DRILL'", drill)
        self.assertIn("SYNTHETIC OLD SOURCE", drill)
        self.assertIn(". Import-InstallState", drill)
        self.assertNotIn("Get-SourceSnapshot", drill)
        self.assertNotIn(".workbuddy", drill)
        layout = self.text.split("function Assert-PlanLayout")[1].split("function Load-Plan")[0]
        self.assertIn("if ($Mode -cne 'DRILL') { Assert-NoInstallReparse", layout)

    def test_verify_only_settings_exception_dynamic_count_and_receipt_evidence(self):
        verify = self.text.split("function Test-InstalledDeclaredFiles")[1].split("function Assert-Package")[0]
        self.assertIn("$Total = @($InstallExpectedNames).Count", verify)
        self.assertIn("$Rel -ceq 'settings.json' -and -not (Test-Path", verify)
        self.assertIn("root settings.json missing (host-managed)", verify)
        self.assertIn("if ($Actual -cne $PackageHashes[$Rel]) { throw", verify)
        self.assertNotRegex(self.text, r"\b(?:516|517)\b")
        evidence = self.text.split("function Collect-SessionEvidence")[1].split("# Main orchestration.")[0]
        self.assertNotIn("-Recurse", evidence)
        self.assertIn("$Located.Count -ne 1", evidence)
        self.assertIn("$SessionId -cne $Located[0].SessionId", evidence)
        self.assertIn("$SkillIds.ContainsKey([string]$ToolNode.callId)", evidence)
        self.assertIn("$Version + '\\skills\\'", evidence)
        self.assertLess(evidence.index("'SHA256SUMS'"), evidence.index("$SkillIds = @{}"))
        self.assertIn("Agent body loading is not proved", evidence)

    def test_repository_only_registration_sorted_unique_safe_and_excluded(self):
        manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
        names = manifest["repository_only_files"]
        self.assertEqual(names, REPO_ONLY)
        self.assertEqual(names, sorted(set(names)))
        self.assertFalse(set(names) & set(manifest["files"]))
        for name in names:
            path = ROOT / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
        sys.path.insert(0, str(ROOT / "tools"))
        from release_rules import manifest_names
        self.assertEqual(manifest_names(ROOT), manifest["files"])
        from build_release import build_release
        # Retain this isolated artifact: no cleanup/delete operations in this test.
        archive = Path(tempfile.mkdtemp(prefix="crm-oncall-static-")).resolve() / "release.zip"
        report = build_release(ROOT, archive)
        with ZipFile(archive) as zipped:
            actual = zipped.namelist()
        self.assertEqual(report["files"], len(manifest["files"]))
        self.assertEqual(actual, ["crm-sre-team/" + name for name in manifest["files"]])
        for name in names:
            self.assertNotIn("crm-sre-team/" + name, actual)

    def test_readme_describes_execution_and_unrun_windows_limits(self):
        readme = self.readme
        self.assertIn("未在 Windows 实跑", readme)
        self.assertIn("powershell -NoProfile -ExecutionPolicy Bypass -File", readme)
        for mode in ["PLAN", "APPLY", "VERIFY", "ROLLBACK", "DRILL", "UPDATE"]:
            self.assertIn("-Mode " + mode, readme)
        for token in ["git -c credential.helper=", "clone --config core.autocrlf=false", "core.hooksPath=NUL",
                      "bootstrap-", "tools\\oncall\\Update-CrmSreTeam.ps1", "-ExpectedScriptSha256", "-Drill",
                      r"C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe",
                      "一次大写 `YES`", "不代表 VERIFY 验收完成"]:
            self.assertIn(token, readme)
        self.assertNotIn("人工放到", readme)
        self.assertIn("python3 tools/release.py", readme)
        self.assertIn("标签注释", readme)
        self.assertIn("repository_only_files", readme)

    def test_readme_bootstrap_fetches_one_tag_with_normal_source_config(self):
        block = self.bootstrap
        for name, value in [("Tag", "<tag>"), ("ExpectedCommit", "<40-hex>"),
                            ("ExpectedZipSha256", "<64-hex>"),
                            ("SourceRepo", r"D:\python_code\github_my\crm-sre-team")]:
            self.assertEqual(block.count(f"${name} = '{value}'"), 1)
            self.assertLess(block.index(f"${name} = '{value}'"), block.index("try {"))
        self.assertIn("$RefSpec = 'refs/tags/' + $Tag + ':refs/tags/' + $Tag", block)
        fetch = next(line.strip() for line in block.splitlines() if " fetch " in line)
        self.assertEqual(fetch, "$FetchOutput = (git -C $SourceRepo -c core.hooksPath=NUL fetch "
                               "--no-tags --no-recurse-submodules origin $RefSpec 2>&1 | "
                               "ForEach-Object { $_.ToString() }) -join \"`n\"")
        self.assertEqual(block.count(" fetch "), 1)
        self.assertNotIn("credential.helper", fetch)
        self.assertNotIn("$Tag:refs", block)
        self.assertNotIn("https://", block)
        self.assertNotRegex(block, r"\$env:GIT_CONFIG_[A-Za-z0-9_]+\s*=")
        self.assertNotRegex(block, r"SetEnvironmentVariable\(['\"]GIT_CONFIG_")
        self.assertNotRegex(block, r"(?m)^\s*git\s+(?:-C\s+\$SourceRepo\s+)?(?:-c\s+\S+\s+)*"
                                  r"(?:pull|checkout|reset|merge|push|remote|config)\b")
        self.assertIn("refs/tags/", block)
        resolve = "rev-parse --verify ('refs/tags/' + $Tag + '^{commit}') 2>$null"
        self.assertIn(resolve, block)
        match = "$SourceCommit.Count -ne 1 -or $SourceCommit[0].ToLowerInvariant() -cne $ExpectedCommit.ToLowerInvariant()"
        self.assertIn(match, block)
        self.assertLess(block.index(fetch), block.index(resolve))
        self.assertLess(block.index(resolve), block.index(match))
        self.assertLess(block.index(match), block.index("clone --no-local"))

    def test_readme_fetch_failure_prints_redacted_diagnostics_and_success_is_silent(self):
        block = self.bootstrap
        fetch = next(line.strip() for line in block.splitlines() if " fetch " in line)
        self.assertLess(block.index("$ErrorActionPreference = 'Continue'"), block.index(fetch))
        failure = re.search(r"if \(\$LASTEXITCODE -ne 0\) \{\n(.*?)\n        \}", block, re.S).group(1)
        replacements = re.findall(
            r"\[regex\]::Replace\(\$FetchOutput, '((?:''|[^'])*)', '([^']*)'\)", failure)
        self.assertEqual(len(replacements), 2)
        self.assertEqual([replacement for _, replacement in replacements], ["$1***@", "***"])
        printed = "Write-Host $FetchOutput"
        self.assertEqual(block.count(printed), 1)
        self.assertIn(printed, failure)
        self.assertLess(failure.rindex("[regex]::Replace"), failure.index(printed))
        self.assertLess(failure.index(printed), failure.index("throw "))
        outside_failure = block.replace(failure, "", 1)
        self.assertEqual(outside_failure.count("$FetchOutput"), 1)
        self.assertNotRegex(outside_failure, r"(?i)Write-(?:Host|Output|Error|Warning).*\b(?:origin|https?://)\b")

        # Exercise the documented regexes with synthetic diagnostics in Python.
        # This does not parse or execute PowerShell; ToString/stream behavior
        # still requires Windows PS 5.1 verification.
        cases = [
            ("fatal: unable to access 'https://operator:secret@example.invalid/team.git/': "
             "Could not resolve proxy: proxy.invalid",
             "fatal: unable to access 'https://***@example.invalid/team.git/': "
             "Could not resolve proxy: proxy.invalid"),
            ("fatal: SSH://operator:secret@example.invalid/team.git: Permission denied",
             "fatal: SSH://***@example.invalid/team.git: Permission denied"),
            ("fatal: detected dubious ownership in repository at 'D:\\repos\\team'",
             "fatal: detected dubious ownership in repository at 'D:\\repos\\team'"),
            (" ! [rejected] release -> release (would clobber existing tag)",
             " ! [rejected] release -> release (would clobber existing tag)"),
            ("fatal: couldn't find remote ref refs/tags/release",
             "fatal: couldn't find remote ref refs/tags/release"),
        ]
        for token in ["github_pat_FAKE_123", "ghp_FAKE123", "gho_FAKE123", "ghu_FAKE123",
                      "ghs_FAKE123", "ghr_FAKE123", "glpat-FAKE_123-abc", "GHP_FAKE123"]:
            cases.append((f"fatal: invalid credential {token}", "fatal: invalid credential ***"))
        for diagnostic, expected in cases:
            with self.subTest(diagnostic=diagnostic):
                redacted = diagnostic
                for pattern, replacement in replacements:
                    def replace(match):
                        return replacement.replace("$1", match.group(1)) if "$1" in replacement else replacement
                    redacted = re.sub(pattern.replace("''", "'"), replace, redacted)
                self.assertEqual(redacted, expected)

    def test_readme_bootstrap_local_clone_and_update_stop_after_each_native_failure(self):
        block = self.bootstrap
        self.assertIn("$Bootstrap = 'D:\\crm-v36-handoff\\bootstrap-' + [guid]::NewGuid().ToString('N')", block)
        collision = "if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'Bootstrap path already exists' }"
        self.assertIn(collision, block)
        self.assertLess(block.index(collision), block.index(" fetch "))
        clone = "clone --no-local --branch $Tag --single-branch --config core.autocrlf=false "
        clone += "--config core.hooksPath=NUL $SourceRepo $Bootstrap"
        self.assertIn(clone, block)
        clone_line = next(line.strip() for line in block.splitlines() if " clone " in line)
        self.assertNotRegex(clone_line, r">|\||Out-Null|\$null")
        update = "powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE "
        update += "-Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -RunPytest"
        self.assertIn(update, block)
        self.assertLess(block.index(clone), block.index("$Script = Join-Path $Bootstrap"))
        self.assertLess(block.index("$Script = Join-Path $Bootstrap"), block.index(update))
        native_prefixes = ("git ", "$FetchOutput = (git ", "$SourceCommit = @(git ", "powershell ")
        for commands, count in [(block, 4), (self.github_bootstrap, 2)]:
            self.assertTrue(commands.startswith(". {\n"))
            self.assertNotRegex(commands, r"-Command\s+\{")
            self.assertIn(update, [line.strip() for line in commands.splitlines()])
            lines = commands.splitlines()
            native_count = 0
            for index, line in enumerate(lines):
                if line.strip().startswith(native_prefixes):
                    native_count += 1
                    self.assertTrue(lines[index + 1].strip().startswith("if ($LASTEXITCODE -ne 0) {"))
            self.assertEqual(native_count, count)

    def test_readme_bootstrap_restores_original_prompt_environment_in_finally(self):
        block = self.bootstrap
        for name, saved in [("GIT_TERMINAL_PROMPT", "SavedGitTerminalPrompt"),
                            ("GCM_INTERACTIVE", "SavedGcmInteractive")]:
            snapshot = f"${saved} = [Environment]::GetEnvironmentVariable('{name}', 'Process')"
            self.assertIn(snapshot, block)
            self.assertLess(block.index(snapshot), block.index("try {"))
            restore = f"[Environment]::SetEnvironmentVariable('{name}', ${saved}, 'Process')"
            self.assertIn(restore, block.split("} finally {", 1)[1])
        # GetEnvironmentVariable returns null when absent; restoring null removes it.
        self.assertIn("原值不存在时移除变量", self.readme)
        self.assertIn("$ErrorActionPreference = $SavedErrorActionPreference", block.split("} finally {", 1)[1])
        env_assignments = re.findall(r"\$env:([A-Za-z0-9_]+)\s*=", block)
        self.assertEqual(env_assignments, ["GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE"])

    def test_readme_github_alternative_uses_dot_sourcing_and_visible_clone_errors(self):
        block = self.github_bootstrap
        self.assertTrue(block.startswith(". {\n"))
        self.assertNotRegex(block, r"-Command\s+\{")
        self.assertIn("--branch $Tag --single-branch https://github.com/caomz/crm-sre-team.git $Bootstrap", block)
        clone = next(line.strip() for line in block.splitlines() if " clone " in line)
        self.assertTrue(clone.startswith("git "))
        self.assertNotRegex(clone, r">|\||Out-Null|\$null")
        self.assertIn("if ($LASTEXITCODE -ne 0) { throw 'GitHub bootstrap clone failed' }", block)
        self.assertIn("$Script = Join-Path $Bootstrap 'tools\\oncall\\Update-CrmSreTeam.ps1' -ErrorAction Stop", block)
        self.assertLess(block.index("$Script = Join-Path $Bootstrap"), block.index("powershell -NoProfile"))
        self.assertIn("if ($LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }", block)
        self.assertNotRegex(mask_literals(block), r"\bexit\b")
        self.assertIn("`$Script` 保留在会话里供单独模式使用", self.readme)
        self.assertNotIn("单独模式需将 `$Script` 填为", self.readme)

    def test_readme_github_alternative_restores_all_seven_git_variables_before_update(self):
        block = self.github_bootstrap
        saved_variables = [
            ("GIT_CONFIG_NOSYSTEM", "SavedGitConfigNoSystem"),
            ("GIT_CONFIG_GLOBAL", "SavedGitConfigGlobal"),
            ("GIT_CONFIG_COUNT", "SavedGitConfigCount"),
            ("GIT_TERMINAL_PROMPT", "SavedGitTerminalPrompt"),
            ("GCM_INTERACTIVE", "SavedGcmInteractive"),
            ("GIT_ASKPASS", "SavedGitAskPass"),
            ("SSH_ASKPASS", "SavedSshAskPass"),
        ]
        clone_scope = block.split("        try {\n", 1)[1].split("        } finally {\n", 1)[0]
        restored = block.split("        } finally {\n", 1)[1].split("        }\n", 1)[0]
        self.assertIn(" clone ", clone_scope)
        self.assertNotIn("powershell ", clone_scope)
        for name, saved in saved_variables:
            snapshot = f"${saved} = [Environment]::GetEnvironmentVariable('{name}', 'Process')"
            self.assertIn(snapshot, block)
            self.assertLess(block.index(snapshot), block.index("try {"))
            self.assertIn(f"$env:{name} =", clone_scope)
            restore = f"[Environment]::SetEnvironmentVariable('{name}', ${saved}, 'Process')"
            self.assertIn(restore, restored)
            self.assertLess(block.index(restore), block.index("$Script = Join-Path $Bootstrap"))
        self.assertEqual(re.findall(r"\$env:([A-Za-z0-9_]+)\s*=", block),
                         [name for name, _ in saved_variables])
        self.assertEqual(restored.count("SetEnvironmentVariable("), 7)
        # A saved null removes the process variable; neither User nor Machine is written.
        self.assertNotRegex(block, r"SetEnvironmentVariable\([^\n]*'(?:User|Machine)'\)")
        self.assertIn("$SavedErrorActionPreference = $ErrorActionPreference", block.split("try {", 1)[0])
        self.assertIn("$ErrorActionPreference = $SavedErrorActionPreference", block.rsplit("} finally {", 1)[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
