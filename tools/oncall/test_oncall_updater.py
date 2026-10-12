"""Static PS contracts and real Mac builder/verifier tests. No PS parse/run.

Run explicitly: python3 -m pytest tools/oncall/test_oncall_updater.py -q
The tests live here to keep this change inside the approved tools/oncall scope.
"""
from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import uuid
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
        if text.startswith("@'\n", i) or text.startswith('@"\n', i):
            quote = text[i + 1]
            end = re.search(r"(?m)^" + re.escape(quote + "@") + r"[ \t]*(?:\n|$)", text[i + 3:])
            if not end:
                raise ValueError("Unterminated here-string")
            i += 3 + end.end()
            result.append("''")
            continue
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

    def test_native_exit_code_uses_global_scope_without_local_shadowing(self):
        native = function_body(self.text, "Invoke-Native")
        assignments = re.findall(r"\$(?:(\w+):)?LASTEXITCODE\s*(?:[+*/%\-]?=|\+\+|--)",
                                 self.code, re.I)
        self.assertEqual([scope.lower() for scope in assignments], ["global"])
        self.assertIn("$global:LASTEXITCODE = $null", native)
        self.assertIn("$Code = $global:LASTEXITCODE", native)
        call = "$Captured = @(& $Program @Arguments 2>&1)"
        self.assertLess(native.index("$global:LASTEXITCODE = $null"), native.index(call))
        self.assertLess(native.index(call), native.index("$Code = $global:LASTEXITCODE"))
        self.assertNotRegex(native, r"\$Code\s*=\s*\$(?:local:|script:|private:)?LASTEXITCODE\b")

    def test_post_check_clone_identity_excludes_only_exact_generated_reports(self):
        identity = function_body(self.text, "Assert-CloneIdentity")
        self.assertIn("[switch]$AfterChecks", identity)
        self.assertIn("if ($AfterChecks) {", identity)
        after_checks = identity.split("if ($AfterChecks) {", 1)[1].split(
            "    $Dirty = Invoke-Native", 1)[0]
        self.assertIn("$StatusArgs += @('--','.')", after_checks)
        self.assertIn("foreach ($Report in @($Manifest.excluded_generated_reports))", after_checks)
        self.assertIn("'^tests/[A-Za-z0-9][A-Za-z0-9._-]*\\.(json|txt)$'", after_checks)
        self.assertIn("$Manifest.files -contains $Report", after_checks)
        self.assertIn("$StatusArgs += (':(top,literal,exclude)' + $Report)", after_checks)
        self.assertEqual(identity.count("literal,exclude"), 1)
        self.assertIn("$Dirty = Invoke-Native $Git $StatusArgs $null", identity)
        self.assertIn("'--untracked-files=all','--ignore-submodules=none'", identity)
        self.assertIn("$Head -cne $ExpectedCommit -or $TagCommit -cne $ExpectedCommit -or $Dirty", identity)
        plan = self.text.split("function Invoke-OncallMode", 1)[1].split("# R2-BEGIN stage-17", 1)[0]
        strict = plan.index("\n        Assert-CloneIdentity\n")
        final = plan.index("Assert-CloneIdentity -AfterChecks")
        hashes = plan.rindex("Assert-HashesEqual $Before (Get-ManifestHashes $Repo)")
        self.assertLess(strict, plan.index("'tools/build_bundle.py'"))
        self.assertTrue(plan.index("'tools/validate_release.py'") < hashes < final)
        self.assertEqual(plan.count("Assert-HashesEqual $Before (Get-ManifestHashes $Repo)"), 2)

    def test_skill_receipt_call_ids_use_ordinal_case_sensitive_keys(self):
        evidence = function_body(self.text, "Collect-SessionEvidence")
        comparer = "$SkillIds = [System.Collections.Hashtable]::new([StringComparer]::Ordinal)"
        self.assertIn(comparer, evidence)
        self.assertNotIn("$SkillIds = @{}", evidence)
        self.assertNotIn("OrdinalIgnoreCase", evidence)
        self.assertLess(evidence.index(comparer), evidence.index("foreach ($Line"))
        self.assertIn("$SkillIds[[string]$ToolNode.callId] = $true", evidence)
        self.assertIn("$SkillIds.ContainsKey([string]$ToolNode.callId)", evidence)

    def test_eight_modes_required_release_inputs_and_pinned_lengths(self):
        self.assertIn("[ValidateSet('PLAN','APPLY','VERIFY','ROLLBACK','DRILL','UPDATE','EXPBUILD','SWITCH')]", self.text)
        self.assertIn("[string]$Mode = 'PLAN'", self.text)
        for name, length in [("ExpectedCommit", 40), ("ExpectedZipSha256", 64)]:
            self.assertRegex(self.text, rf"\[Parameter\(Mandatory=\$true\)\]\[ValidatePattern\('[^']*\{{{length}\}}[^']*'\)\]\[string\]\${name}")
        self.assertIn("[Parameter(Mandatory=$true)]", self.text.split("[string]$Tag")[0])
        for mode in ["PLAN", "APPLY", "VERIFY", "ROLLBACK", "DRILL", "UPDATE", "EXPBUILD", "SWITCH"]:
            self.assertIn(f"$Mode -ceq '{mode}'", self.text)
        for name in ["PlanPath", "PlanSha256", "RunPytest", "SessionId", "AgentId", "Drill", "ExpectedScriptSha256", "ExperimentSet", "ExperimentSetSha256", "Package"]:
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

    def test_market_entry_version_is_optional_but_invalid_present_value_stops(self):
        entry = function_body(self.text, "Assert-MarketEntry")
        for token in ["$Entries.Count -ne 1", "$Entries[0].name -cne 'crm-sre-team'",
                      "$Entries[0].source -isnot [string]",
                      "(Get-InstallFullPath $EntryPath) -ine (Get-InstallFullPath $InstallSource)"]:
            self.assertIn(token, entry)
        guard = ("if ($Entries[0].PSObject.Properties.Name -contains 'version' -and "
                 "($Entries[0].version -isnot [string] -or "
                 "[string]::IsNullOrWhiteSpace($Entries[0].version)))")
        self.assertRegex(entry, re.escape(guard) + r"\s*\{\s*throw 'Marketplace entry has an invalid version field; human review required'\s*\}")
        self.assertNotIn("-notcontains 'version'", entry)
        self.assertNotIn("needs an explicit version field", entry)
        self.assertEqual(entry.count("throw "), 3)

    def test_optional_market_version_plan_notice_and_installed_client_steps(self):
        plan = self.text.split("        $InstallMode = 'REAL'\n", 1)[1].split("        $OldSnapshot", 1)[0]
        self.assertIn(". Prepare-InstallContext", plan)
        notice = ("if ($Entries[0].PSObject.Properties.Name -notcontains 'version') {\n"
                  "            Write-Host 'PLAN: Marketplace entry has no version field; marketplace.json will not be modified (same as the 10-11 rc2 installation).'\n"
                  "        }")
        self.assertIn(notice, plan)
        self.assertLess(plan.index(". Prepare-InstallContext"), plan.index(notice))
        apply = self.text.split("        if ($Mode -ceq 'APPLY') {", 1)[1].split("        } elseif ($Mode -ceq 'VERIFY')", 1)[0]
        installed = ("INSTALLED. StatePath=$StatePath. Open client, refresh the marketplace and update to $Version, "
                     "then start a NEW session, paste Self-check 1, and run VERIFY.")
        self.assertIn('Write-Host "' + installed + '"', apply)
        self.assertLess(apply.index("# R2-END block-20"), apply.index(installed))
        self.assertIn("`version` 字段可省略", self.readme)
        self.assertIn("非空、非纯空白字符串", self.readme)
        self.assertIn("刷新市场并更新到计划的 `$Version`", self.readme)

    def test_optional_market_version_preserves_original_install_and_rollback(self):
        for name in ["block-20", "block-22"]:
            blocks = [body for key, body in fragments(self.text) if key == name]
            self.assertEqual(len(blocks), 2)
            for block in blocks:
                self.assertEqual(hashlib.sha256(block.encode("utf-8")).hexdigest(), FRAGMENT_SHA[name])
                guard = ("if ($Entries[0].PSObject.Properties.Name -contains 'version')"
                         if name == "block-20" else "if ($MarketWriteStarted)")
                self.assertIn(guard, block)
        drill = self.text.split("} elseif ($Mode -ceq 'DRILL')", 1)[1]
        self.assertIn("source=$SyntheticSource; version='0.0.0-drill'", drill)

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
        evidence = function_body(self.text, "Collect-SessionEvidence")
        self.assertNotIn("-Recurse", evidence)
        self.assertIn("$Located.Count -ne 1", evidence)
        self.assertIn("$SessionId -cne $Located[0].SessionId", evidence)
        self.assertIn("$SkillIds.ContainsKey([string]$ToolNode.callId)", evidence)
        self.assertIn("$Version + '\\skills\\'", evidence)
        self.assertLess(evidence.index("'SHA256SUMS'"), evidence.index("$SkillIds ="))
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
        for mode in ["PLAN", "APPLY", "VERIFY", "ROLLBACK", "DRILL", "UPDATE", "EXPBUILD", "SWITCH"]:
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

    def test_readme_bootstrap_checks_local_commit_before_clone_without_network(self):
        block = self.bootstrap
        for name, value in [("Tag", "<tag>"), ("ExpectedCommit", "<40-hex>"),
                            ("ExpectedZipSha256", "<64-hex>"),
                            ("SourceRepo", r"D:\python_code\github_my\crm-sre-team")]:
            self.assertEqual(block.count(f"${name} = '{value}'"), 1)
            self.assertLess(block.index(f"${name} = '{value}'"), block.index("try {"))
        self.assertIn("Fill the three verified release values first", block)
        check = "git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}') 2>$null"
        clone = "git -c core.hooksPath=NUL clone -q --no-local --no-checkout "
        clone += "--config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap"
        self.assertIn(check, block)
        self.assertIn(clone, block)
        self.assertLess(block.index(check), block.index("$Bootstrap ="))
        self.assertLess(block.index(check), block.index(clone))
        self.assertIn("Local project does not contain the target commit yet; update it first, then rerun", block)
        for pattern in [r"(?i)fetch\s+origin\b", r"(?i)https?://", r"(?i)\bssh\b",
                        r"(?i)\bgithub\.com\b", r"\$RefSpec\b", r"\$SourceCommit\b"]:
            self.assertNotRegex(block, pattern)
        self.assertIn("(no network)", block)
        source_commands = [line.strip() for line in block.splitlines()
                           if line.strip().startswith("git -C $SourceRepo ")]
        self.assertEqual(source_commands, [check])
        self.assertNotIn("refs/tags/", block)
        self.assertNotIn("--branch", block)

    def test_readme_bootstrap_copies_local_refs_and_binds_tag_in_new_bootstrap(self):
        block = self.bootstrap
        fetch = "git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo "
        fetch += "'+refs/remotes/*:refs/crm-source-remotes/*'"
        resolve = "git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')"
        tag = "git -C $Bootstrap -c core.hooksPath=NUL tag -f $Tag $ExpectedCommit"
        checkout = "git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag"
        for command in [fetch, resolve, tag, checkout]:
            self.assertIn(command, block)
        self.assertTrue(block.index("clone -q --no-local --no-checkout") < block.index(fetch)
                        < block.index(resolve) < block.index(tag) < block.index(checkout)
                        < block.index("$Script = Join-Path $Bootstrap"))
        self.assertEqual(block.count(" fetch "), 1)
        self.assertEqual(block.count(" tag -f "), 1)
        self.assertIn("不访问网络", self.readme)
        self.assertIn("本地项目须由用户自行更新到包含 `ExpectedCommit`", self.readme)
        self.assertIn("来源仓库的分支、工作树、索引、标签和远程配置都不改", self.readme)
        self.assertIn("不依赖来源仓库里的标签", self.readme)
        self.assertIn("提交仅在远程跟踪引用上", self.readme)
        self.assertIn("完整性依靠 `ExpectedCommit` 与插件 ZIP SHA256", self.readme)
        self.assertIn("仅用于没有本地项目的机器", self.readme)

    def test_readme_bootstrap_local_clone_and_update_stop_after_each_native_failure(self):
        block = self.bootstrap
        self.assertIn("$Bootstrap = 'D:\\crm-v36-handoff\\bootstrap-' + [guid]::NewGuid().ToString('N')", block)
        collision = "if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'Bootstrap path already exists' }"
        self.assertIn(collision, block)
        self.assertLess(block.index(collision), block.index(" clone "))
        update = "powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE "
        update += "-Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -RunPytest"
        self.assertIn(update, block)
        self.assertLess(block.index(" checkout "), block.index("$Script = Join-Path $Bootstrap"))
        self.assertLess(block.index("$Script = Join-Path $Bootstrap"), block.index(update))
        for commands, count in [(block, 7), (self.github_bootstrap, 2)]:
            self.assertTrue(commands.startswith(". {\n"))
            self.assertNotRegex(commands, r"-Command\s+\{")
            self.assertIn(update, [line.strip() for line in commands.splitlines()])
            lines = commands.splitlines()
            native_count = 0
            for index, line in enumerate(lines):
                if line.strip().startswith(("git ", "powershell ")):
                    native_count += 1
                    self.assertTrue(lines[index + 1].strip().startswith("if ($LASTEXITCODE -ne 0) {"))
            self.assertEqual(native_count, count)
        update_line = next(line.strip() for line in block.splitlines() if line.strip().startswith("powershell "))
        self.assertNotRegex(update_line, r">|\||Out-Null|\$null")

    def test_readme_local_bootstrap_restores_error_preference_in_finally(self):
        block = self.bootstrap
        self.assertIn("$SavedErrorActionPreference = $ErrorActionPreference", block.split("try {", 1)[0])
        self.assertIn("$ErrorActionPreference = $SavedErrorActionPreference", block.split("} finally {", 1)[1])
        self.assertLess(block.index("$ErrorActionPreference = 'Continue'"), block.index("cat-file -e"))
        self.assertNotRegex(block, r"\$env:|GetEnvironmentVariable|SetEnvironmentVariable")
        self.assertNotRegex(mask_literals(block), r"\bexit\b")

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


def extracted_verifier(text):
    matches = re.findall(r"\$ExperimentVerifierCode = @'\n(.*?)\n'@", text, re.S)
    if len(matches) != 1:
        raise AssertionError('Expected ONE embedded verifier')
    return matches[0] + '\n'


class ExperimentStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = decode_script(SCRIPT.read_bytes())
        cls.code = mask_literals(cls.text)
        cls.readme = (ROOT / 'tools/oncall/README.md').read_text(encoding='utf-8')

    def test_expbuild_shares_formal_checks_and_exits_before_host_context(self):
        main = function_body(self.text, 'Invoke-OncallMode')
        prepare = main.split('# R2-END stage-17', 1)[0]
        self.assertIn("if ($Mode -ceq 'PLAN' -or $Mode -ceq 'EXPBUILD')", prepare)
        for token in ['Assert-CloneIdentity', "'tools/build_bundle.py'", "'tools/check_workbuddy.py'",
                      "'tools/validate_bundle.py'", 'if ($RunPytest)', "'tools/build_release.py'",
                      "-ine $ExpectedZipSha256", "'tools/validate_release.py'", '# R2-BEGIN stage-17']:
            self.assertIn(token, prepare)
        tail = main.split('# R2-END stage-17', 1)[1]
        self.assertLess(tail.index('. Invoke-ExperimentBuild; return'), tail.index('. Prepare-InstallContext'))
        builders = function_body(self.text, 'Invoke-ExperimentBuild')
        self.assertLess(builders.index('Assert-CloneIdentity -AfterChecks'), builders.index("'tools/make_probe_build.py'"))
        self.assertIn('Assert-HashesEqual $Before (Get-ManifestHashes $Repo)', builders)
        self.assertIn("'tools/make_comparison_build.py'", builders)
        for tool in ['WebFetch', 'Bash', 'PowerShell']:
            self.assertIn("'" + tool + "'", builders)
        self.assertNotIn('--max-turns', builders)
        dispatch = self.text.rsplit('\ntry {', 1)[1]
        local_gate = "if ($Mode -cin @('EXPBUILD','SWITCH') -and -not $VerifiedWorkTree)"
        self.assertIn(local_gate, dispatch)
        self.assertLess(dispatch.index('Assert-UpdaterIdentity'), dispatch.index(local_gate))
        self.assertLess(dispatch.index(local_gate), dispatch.index('. Invoke-SwitchPlan'))

    def test_switch_guards_and_plan_hash_before_one_yes_and_original_writes(self):
        switch = function_body(self.text, 'Invoke-SwitchPlan')
        order = ['Assert-ClientStopped', '$Set = Load-ExperimentSet', 'New-SafeDirectory $Artifacts',
                 "'select','--set'", 'Copy-Item -LiteralPath $Selected.root', '. Prepare-InstallContext',
                 'Assert-HashesEqual (ConvertTo-HashTable $Selected.hashes)', 'Write-NewJson $PlanPath',
                 '$PlanSha256 =', 'SWITCH PLAN ready.']
        indices = [switch.index(token) for token in order]
        self.assertEqual(indices, sorted(indices))
        loader = function_body(self.text, 'Load-ExperimentSet')
        self.assertLess(loader.index('$Read.Sha -ine $ExperimentSetSha256'), loader.index('ConvertFrom-Json'))
        for name in ['tag', 'commit', 'zip_sha256', 'script_sha256']:
            self.assertIn('$Set.' + name, loader)
        dispatch = self.text.rsplit("} elseif ($Mode -ceq 'SWITCH')", 1)[1]
        self.assertLess(dispatch.index('. Invoke-SwitchPlan'), dispatch.index('Test-SuccessfulDrill'))
        self.assertLess(dispatch.index("'DRILL' -FromUpdate"), dispatch.index("'APPLY' -FromUpdate"))
        self.assertNotIn('Confirm-Yes', switch + dispatch)
        self.assertIn('Copy-Item -LiteralPath $Set.zip -Destination $ReleaseZip', switch)
        self.assertLess(switch.index('Copied formal ZIP differs'), switch.index('Write-NewJson $PlanPath'))
        apply = function_body(self.text, 'Invoke-OncallMode').split("if ($Mode -ceq 'APPLY')", 1)[1].split("} elseif ($Mode -ceq 'VERIFY')", 1)[0]
        self.assertEqual(apply.count('Confirm-Yes'), 1)
        self.assertLess(apply.index('Confirm-Yes'), apply.index('# R2-BEGIN block-20'))
        self.assertLess(apply.index('$null = Load-Plan'), apply.index('# R2-BEGIN block-20'))
        self.assertIn('Package kind=$PackageKind', apply)

    def test_metadata_plan_binding_and_per_plan_rollback_guard(self):
        header = self.text.split("$ErrorActionPreference = 'Stop'", 1)[0]
        self.assertIn("[ValidateSet('formal','probe','cmp-n','cmp-s','probe-webfetch-denied','probe-bash-denied','probe-powershell-denied')][string]$Package", header)
        self.assertIn("[ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExperimentSetSha256", header)
        for token in ['operation=\'SWITCH\'', 'experiment_set_sha256=', 'source_tree_sha256=',
                      'builder_manifest=', 'metadata_names=', 'expected_markers=']:
            self.assertIn(token, function_body(self.text, 'Invoke-SwitchPlan'))
        self.assertIn('@($InstallMetadataNames)', function_body(self.text, 'Assert-Package'))
        for name in ['Import-PlanContext', 'Invoke-OncallMode']:
            self.assertIn('$InstallMetadataNames = @($Document.metadata_names)', function_body(self.text, name))
        self.assertIn('-ContextMetadataNames $InstallMetadataNames', function_body(self.text, 'Invoke-OncallMode'))
        self.assertIn("$Names += 'probe-manifest.json'", function_body(self.text, 'Get-SourceSnapshot'))
        rollback = function_body(self.text, 'Invoke-OncallMode').split("} elseif ($Mode -ceq 'ROLLBACK')", 1)[1].split("} elseif ($Mode -ceq 'DRILL')", 1)[0]
        self.assertEqual(rollback.count('Assert-RollbackCurrentPackage'), 2)
        self.assertLess(rollback.index('Assert-RollbackCurrentPackage'), rollback.index('Confirm-Yes'))
        self.assertTrue(rollback.index('$null = Load-Plan') < rollback.rindex('Assert-RollbackCurrentPackage') < rollback.index('# R2-BEGIN block-22'))
        self.assertIn('Test-InstalledDeclaredFiles $InstallSource', function_body(self.text, 'Assert-RollbackCurrentPackage'))
        self.assertIn('roll back the newest plan first, or SWITCH to the wanted package', self.text)

    def test_rollback_current_package_guard_only_for_imported_installed_stage(self):
        rollback = function_body(self.text, 'Invoke-OncallMode').split("} elseif ($Mode -ceq 'ROLLBACK')", 1)[1].split("} elseif ($Mode -ceq 'DRILL')", 1)[0]
        guard = "if ($InstallStage -ceq 'INSTALLED') { Assert-RollbackCurrentPackage }"
        self.assertEqual(rollback.count(guard), 2)
        self.assertNotIn('Assert-RollbackCurrentPackage', rollback.replace(guard, ''))
        self.assertLess(rollback.index('. Import-InstallState'), rollback.index(guard))
        self.assertLess(rollback.index(guard), rollback.index('Confirm-Yes'))
        self.assertTrue(rollback.index('$null = Load-Plan') < rollback.rindex(guard) < rollback.index('# R2-BEGIN block-22'))
        stages = re.findall(r"if \(\$InstallStage -ceq '([^']+)'\) \{ Assert-RollbackCurrentPackage \}", rollback)
        self.assertEqual(stages, ['INSTALLED', 'INSTALLED'])
        self.assertTrue(set(stages).isdisjoint({'PLANNED', 'MARKET_BACKUP', 'SOURCE_MOVE', 'COPY', 'VERIFY', 'MARKET_WRITE'}))

    def test_verifier_files_bypass_native_stdout_and_powershell_reserialization(self):
        build = function_body(self.text, 'Invoke-ExperimentBuild')
        switch = function_body(self.text, 'Invoke-SwitchPlan')
        for token in ('ConvertFrom-Json', 'ConvertTo-Json', 'Write-NewJson'):
            self.assertNotIn(token, build)
        self.assertIn('$ExperimentSetSha256 = (Get-FileHash -LiteralPath $ExperimentSet -Algorithm SHA256)', build)
        self.assertIn("Write-Utf8Lf (Join-Path $Artifacts 'experiment-set.sha256')", build)
        self.assertIn("$SelectionPath = Join-Path $Artifacts 'selection.json'", switch)
        self.assertIn("'--output',$SelectionPath", switch)
        read = '$Selection = (ReadShared $SelectionPath).Text | ConvertFrom-Json'
        self.assertEqual(switch.count('ConvertFrom-Json'), 1)
        self.assertIn(read, switch)
        self.assertLess(switch.index("'select','--set'"), switch.index(read))
        self.assertLess(switch.index(read), switch.index('Copy-Item -LiteralPath $Selected.root'))
        self.assertNotIn('ConvertTo-Json', switch)
        self.assertEqual(re.findall(r'(?m)^[ \t]*Write-NewJson[^\n]*', switch), ['    Write-NewJson $PlanPath $Document'])
        for pattern in (r'\$(?:Set|Selection|Selected|Json)\s*\|\s*ConvertTo-Json',
                        r'Write-NewJson[ \t]+\$(?:ExperimentSet|SelectionPath)\b',
                        r'Write-NewJson[ \t]+[^\n]+[ \t]+\$(?:Set|Selection|Selected)\b'):
            self.assertNotRegex(self.text, pattern)
        calls = [line.strip() for line in self.text.splitlines() if 'Invoke-Native $Python @($VerifierPath,' in line]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(line.startswith('$null = Invoke-Native') for line in calls))
        verifier = extracted_verifier(self.text)
        self.assertIn('ensure_ascii=True, sort_keys=True', verifier)
        self.assertIn("with path.open('xb') as output:", verifier)
        self.assertIn("print('PASS_' + args.action.upper())", verifier)
        self.assertNotIn('print(json.dumps(result', verifier)

    def test_source_snapshot_probe_version_read_is_leaf_guarded_and_formal_body_unchanged(self):
        snapshot = function_body(self.text, 'Get-SourceSnapshot')
        probe = re.search(r"    if \(Test-Path -LiteralPath \(Join-Path \$Root 'VERSION'\) -PathType Leaf\) \{\n"
                          r"        \$SnapshotVersion = [^\n]+\n"
                          r"        if \([^\n]+\) \{ \$Names \+= 'probe-manifest.json' \}\n"
                          r"    \}\n", snapshot)
        self.assertIsNotNone(probe)
        self.assertIn("[IO.File]::ReadAllText((Join-Path $Root 'VERSION'), $Utf8NoBom)", probe.group())
        self.assertLessEqual(probe.end(), snapshot.index('    foreach ($Rel in $Names)'))
        formal = snapshot[:probe.start()] + snapshot[probe.end():]
        self.assertEqual(hashlib.sha256(formal.encode('utf-8')).hexdigest(),
                         '16d9a76bbe7c1476be76cdd69384452524cb6ed66c56c7b5188e2a22037920a1')

    def test_readme_failed_apply_recovery_and_t02_user_confirmed_recommendation(self):
        failure = self.readme.split('## 失败恢复', 1)[1].split('## PowerShell', 1)[0]
        for token in ('部分或失败 APPLY', '非 INSTALLED', '-Mode ROLLBACK', 'runbook 5C',
                      '失败 APPLY 后，必须先恢复它（ROLLBACK 或 5C），再进行任何新的 SWITCH/UPDATE'):
            self.assertIn(token, failure)
        row = next(line for line in self.readme.splitlines() if line.startswith('| ROLLBACK |'))
        self.assertIn('仅 INSTALLED', row)
        self.assertIn('失败 APPLY 的其他阶段沿原块 22 恢复', row)
        t02 = next(line for line in self.readme.splitlines() if line.startswith('| T02 校准 x2 |'))
        self.assertIn('两次不计分', t02)
        self.assertIn('建议 cmp-n、cmp-s 各一次（先 N 后 S），开跑前由用户确认并记录；不改变评分口径', t02)
        self.assertNotIn('本流程预先采用', t02)

    def test_marker_counts_are_raw_aid_before_receipt_verdict(self):
        evidence = function_body(self.text, 'Collect-SessionEvidence')
        self.assertLess(evidence.index("'SHA256SUMS'"), evidence.index('Get-RawMarkerCounts'))
        self.assertLess(evidence.index("'marker-counts.json'"), evidence.index('$SkillIds ='))
        self.assertIn('RAW_OCCURRENCES_LOCATION_UNKNOWN_NOT_A_VERDICT', evidence)
        self.assertIn('$Snapshot.Data.Text $ExpectedMarkers', evidence)
        counts = function_body(self.text, 'Get-RawMarkerCounts')
        self.assertIn('[regex]::Matches($Text, [regex]::Escape($Marker)).Count', counts)
        self.assertNotIn('OrdinalIgnoreCase', counts)
        self.assertIn('$ExpectedMarkers = @($Document.expected_markers)', function_body(self.text, 'Import-PlanContext'))

    def test_ps51_framework_native_argument_and_output_lesson_scan(self):
        for pattern in [r'(?i)\b(?:Remove-Item|Stop-Process|Set-ExecutionPolicy|Clear-Content|rm|rmdir|del)\b',
                        r'(?i)\[.*?(?:File|Directory)\]::Delete\b',
                        r'(?i)\b(?:GetRelativePath|EnumerateFileSystemEntries|ToHexString|HashData|ReadAllBytesAsync)\b',
                        r'(?i)ConvertFrom-Json[ \t]+[^\n]*(?:-AsHashtable|-Depth)',
                        r'(?i)ConvertTo-Json[ \t]+[^\n]*-EscapeHandling',
                        r'(?i)\b(?:ForEach-Object\s+-Parallel|Start-ThreadJob)\b',
                        r'\b(?:&&|\|\||\?\?|\?\.)']:
            self.assertNotRegex(self.code, pattern)
        self.assertNotRegex(self.code, r'\b(?:ArrayList|List\[.*?\])[^\n]*\.Add\(')
        writer = function_body(self.text, 'Write-ExperimentVerifier')
        self.assertIn('if (Test-Path -LiteralPath $Path)', writer)
        compile(extracted_verifier(self.text), '<embedded verifier>', 'exec')
        # Native Python code is written to a .py; the sole Python -c is unchanged
        # and contains no embedded double quote. New args are array elements.
        calls = [line for line in self.text.splitlines() if 'Invoke-Native $Python' in line]
        inline = [line for line in calls if "@('-c'," in line]
        self.assertEqual(len(inline), 1)
        self.assertIn("'import sys; assert sys.version_info >= (3,10)'", inline[0])
        self.assertNotIn('"', inline[0])

    def test_readme_local_expbuild_and_whole_gate_round(self):
        section = self.readme.split('## 实验集合与切包（NOT RUN ON WINDOWS）', 1)[1]
        bootstrap = re.search(r'```powershell\n(.*?)\n```', section, re.S).group(1)
        self.assertIn('-Mode EXPBUILD', bootstrap)
        self.assertNotIn('-Mode UPDATE', bootstrap)
        self.assertNotRegex(bootstrap, r'https?://|fetch\s+origin\b')
        self.assertIn("fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'", bootstrap)
        for index, line in enumerate(bootstrap.splitlines()):
            if line.strip().startswith(('git ', 'powershell ')):
                self.assertTrue(bootstrap.splitlines()[index + 1].strip().startswith('if ($global:LASTEXITCODE -ne 0)'))
        for token in ['WB09H', 'PROBE-LA/LS/C/D', '7A', '7B', 'WB14', 'WB17', 'PowerShell',
                      'T02', 'C1', 'C2', 'C3', '一套', '-Package formal', '-SessionId', '-AgentId',
                      'update-effac22650784f529d6274dd570d511c', '05225a8e', '预发布', '本机']:
            self.assertIn(token, section)
        for name in ['formal', 'probe', 'cmp-n', 'cmp-s', 'probe-webfetch-denied',
                     'probe-bash-denied', 'probe-powershell-denied']:
            self.assertIn('`' + name + '`', section)


@unittest.skipIf(os.name == 'nt', 'Mac functional fixtures use temporary synthetic paths; PS 5.1/host execution is a separate NOT_RUN check')
class ExperimentFunctionalTests(unittest.TestCase):
    """Real HEAD clone/builders, retained temp directories; never PS execution."""
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix='crm-oncall-functional-')).resolve()
        cls.set_id = uuid.uuid4().hex
        cls.repo = cls.work / ('crm-oncall-' + cls.set_id) / 'repo'
        cls.artifacts = cls.work / ('experiment-' + cls.set_id)
        cls.artifacts.mkdir()
        cls.repo.parent.mkdir()
        cls.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
                       GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_TERMINAL_PROMPT='0', TMPDIR=str(cls.work))
        cls.head = cls.run_command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).stdout.strip()
        cls.tag = 'test-oncall-offline'
        cls.script_sha = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        cls.run_command(['git', '-c', 'core.hooksPath=' + os.devnull, 'clone', '-q', '--no-local',
                 '--no-checkout', '--config', 'core.autocrlf=false', '--config',
                 'core.hooksPath=' + os.devnull, str(ROOT), str(cls.repo)])
        cls.run_command(['git', '-C', str(cls.repo), 'checkout', '-q', '--detach', cls.head])
        cls.names = json.loads((cls.repo / 'release-manifest.json').read_text())['files']
        cls.before = {name: hashlib.sha256((cls.repo / name).read_bytes()).hexdigest() for name in cls.names}
        cls.verifier = cls.work / 'experiment-verifier.py'
        source = extracted_verifier(decode_script(SCRIPT.read_bytes()))
        cls.verifier.write_text(source, encoding='utf-8', newline='\n')
        cls.ns = {'__name__': 'extracted_experiment_verifier'}
        exec(compile(source, str(cls.verifier), 'exec'), cls.ns)
        cls.run_command([sys.executable, str(cls.repo / 'tools/build_release.py'), '--root', str(cls.repo),
                 '--output', str(cls.artifacts / 'release.zip')])
        cls.zip_sha = hashlib.sha256((cls.artifacts / 'release.zip').read_bytes()).hexdigest()
        with ZipFile(cls.artifacts / 'release.zip') as archive:
            archive.extractall(cls.artifacts / 'install-clean')
        for name, tool in [('probe', None), ('probe-webfetch-denied', 'WebFetch'),
                           ('probe-bash-denied', 'Bash'), ('probe-powershell-denied', 'PowerShell')]:
            args = [sys.executable, str(cls.repo / 'tools/make_probe_build.py'), '--root', str(cls.repo),
                    '--out', str(cls.artifacts / name)]
            if tool:
                args += ['--disallow', 'oracle-dba=' + tool]
            cls.run_command(args)
        cls.run_command([sys.executable, str(cls.repo / 'tools/make_comparison_build.py'), '--root', str(cls.repo),
                 '--out', str(cls.artifacts / 'comparison')])
        result = cls.call_build(cls.artifacts)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.set_path = cls.artifacts / 'experiment-set.json'
        if result.stdout != 'PASS_BUILD\n':
            raise AssertionError('Unexpected verifier stdout: ' + result.stdout)
        cls.document = json.loads(cls.set_path.read_bytes())
        cls.set_sha = hashlib.sha256(cls.set_path.read_bytes()).hexdigest()

    @classmethod
    def run_command(cls, args, check=True):
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', env=cls.env)
        if check and result.returncode:
            raise AssertionError('Command failed: ' + repr(args) + '\n' + result.stdout + result.stderr)
        return result

    @classmethod
    def call_build(cls, artifacts):
        return cls.run_command([sys.executable, str(cls.verifier), 'build', '--repo', str(cls.repo),
                        '--artifacts', str(artifacts), '--head', cls.head, '--tag', cls.tag,
                        '--zip-sha', cls.zip_sha, '--script-sha', cls.script_sha, '--set-id', cls.set_id], check=False)

    @classmethod
    def call_select(cls, set_path, set_sha, package, head=None, tag=None, zip_sha=None, script_sha=None, output=None):
        if output is None:
            directory = cls.work / ('update-' + uuid.uuid4().hex)
            directory.mkdir()
            output = directory / 'selection.json'
        result = cls.run_command([sys.executable, str(cls.verifier), 'select', '--set', str(set_path),
                        '--set-sha', set_sha, '--package', package, '--head', head or cls.head,
                        '--tag', tag or cls.tag, '--zip-sha', zip_sha or cls.zip_sha,
                        '--script-sha', script_sha or cls.script_sha, '--output', str(output)], check=False)
        return result, output

    @classmethod
    def copy_artifacts(cls):
        base = Path(tempfile.mkdtemp(prefix='negative-', dir=cls.work))
        target = base / cls.artifacts.name
        # Leave the verifier's result absent so negatives test the intended fault,
        # rather than the independent refuse-existing-output guard. No deletion.
        shutil.copytree(cls.artifacts, target,
                        ignore=lambda directory, names: ['experiment-set.json'] if Path(directory) == cls.artifacts else [])
        return target

    def test_real_seven_packages_source_digest_versions_zips_and_records(self):
        self.assertEqual([p['name'] for p in self.document['packages']], list(self.ns['PACKAGE_NAMES']))
        self.assertEqual(len(self.document['builder_manifests']), 5)
        roles = json.loads((self.repo / 'policy-source/roles-source.json').read_text())
        digest = hashlib.sha256()
        for name in self.names:
            digest.update(name.encode('utf-8') + b'\0')
            digest.update(hashlib.sha256((self.repo / name).read_bytes()).digest())
        self.assertEqual(self.document['source_tree_sha256'], digest.hexdigest())
        self.assertEqual(self.document['source_version'], (self.repo / 'VERSION').read_text().strip())
        self.assertEqual(self.before, {name: hashlib.sha256((self.repo / name).read_bytes()).hexdigest() for name in self.names})
        for package in self.document['packages']:
            root = Path(package['root'])
            extra = ['probe-manifest.json'] if package['name'].startswith('probe') else []
            self.assertEqual(set(package['expected_names']), set(self.names + extra))
            self.assertEqual(package['extra_metadata_names'], extra)
            self.assertEqual(package['hashes'], self.ns['file_map'](root))
            self.ns['check_zips'](root, roles)
        self.assertEqual(len(roles) * 2, 16)
        self.assertEqual(len(roles) + 2, 10)
        self.assertEqual(len(roles), 8)
        n, s = [next(p for p in self.document['packages'] if p['name'] == name) for name in ('cmp-n', 'cmp-s')]
        self.assertEqual(n['markers']['suffix'], s['markers']['suffix'])
        self.assertNotEqual(n['version'], s['version'])
        self.assertNotIn(b'\xef\xbb\xbf', self.set_path.read_bytes()[:3])
        self.assertNotIn(b'\r', self.set_path.read_bytes())
        canonical = (json.dumps(self.document, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8')
        self.assertEqual(self.set_path.read_bytes(), canonical)
        self.assertTrue(self.set_path.read_bytes().isascii())

    def test_select_each_package_rechecks_set_identity_and_bytes(self):
        for name in self.ns['PACKAGE_NAMES']:
            with self.subTest(package=name):
                result, path = self.call_select(self.set_path, self.set_sha, name)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'PASS_SELECT\n')
                selection = json.loads(path.read_bytes())
                self.assertEqual(set(selection), {'experiment', 'selected'})
                self.assertEqual(set(selection['experiment']),
                                 {'set_id', 'artifacts', 'repo', 'zip', 'source_tree_sha256', 'source_version'})
                fields = {'root', 'version', 'expected_names', 'hashes', 'markers', 'disallow', 'builder_manifest'}
                self.assertEqual(set(selection['selected']), fields)
                package = next(p for p in self.document['packages'] if p['name'] == name)
                self.assertEqual(selection['selected'], {key: package[key] for key in fields})
                self.assertEqual(selection['experiment'], {key: self.document[key] for key in selection['experiment']})
                self.assertEqual(path.read_bytes(),
                                 (json.dumps(selection, sort_keys=True, ensure_ascii=True, separators=(',', ':')) + '\n').encode('utf-8'))
                self.assertTrue(path.read_bytes().isascii())
                self.assertNotIn(b'\r', path.read_bytes())

    def test_verifier_refuses_existing_set_and_selection_outputs_without_overwrite(self):
        before = self.set_path.read_bytes()
        result = self.call_build(self.artifacts)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Verifier output already exists', result.stderr)
        self.assertEqual(self.set_path.read_bytes(), before)
        result, path = self.call_select(self.set_path, self.set_sha, 'cmp-n')
        self.assertEqual(result.returncode, 0, result.stderr)
        before = path.read_bytes()
        result, _ = self.call_select(self.set_path, self.set_sha, 'cmp-s', output=path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Verifier output already exists', result.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_structure_negative_tamper_version_marker_extra_disallow_and_comparison(self):
        cases = [
            ('tampered-file', 'probe/README.md', lambda p: p.write_bytes(p.read_bytes() + b'altered\n')),
            ('wrong-version', 'probe/skills/oracle-dba/VERSION', lambda p: p.write_text('0.0.0-wrong\n')),
            ('missing-marker', 'probe/skills/oracle-dba/SKILL.md', lambda p: p.write_text(re.sub(r'^> PROBE-D-[^\n]*\n', '', p.read_text(), flags=re.M))),
            ('extra-file', 'probe/extra.txt', lambda p: p.write_text('unexpected\n')),
            ('wrong-disallow', 'probe-webfetch-denied/agents/telecom-crm-oracle-dba.md', lambda p: p.write_text(p.read_text().replace('  - WebFetch', '  - Bash'))),
            ('plain-disallow', 'probe/agents/telecom-crm-oracle-dba.md', lambda p: p.write_text(p.read_text().replace('---\n', '---\ndisallowedTools: [Bash]\n', 1))),
            ('missing-load', 'comparison/N/skills/stability-director/SKILL.md', lambda p: p.write_text(re.sub(r'^> LOAD-N-[^\n]*\n', '', p.read_text(), flags=re.M))),
            ('unexpected-ns-diff', 'comparison/S/README.md', lambda p: p.write_bytes(p.read_bytes() + b'altered\n')),
            ('stale-skill-zip', 'probe/individual-packages/oracle-dba/skill.zip', lambda p: p.write_bytes((self.repo / 'individual-packages/oracle-dba/skill.zip').read_bytes())),
        ]
        for label, rel, mutate in cases:
            with self.subTest(case=label):
                artifacts = self.copy_artifacts()
                mutate(artifacts / rel)
                result = self.call_build(artifacts)
                self.assertNotEqual(result.returncode, 0, label)
                self.assertIn('error', result.stderr)

    def test_provenance_and_comparison_manifest_negative_cases(self):
        for key, value in [('source_commit', 'unknown'), ('source_commit', 'ffffffff'),
                           ('source_tree_sha256', '0' * 64), ('source_version', '2.8.0-rc2')]:
            with self.subTest(field=key, value=value):
                artifacts = self.copy_artifacts()
                path = artifacts / 'probe/probe-manifest.json'
                data = json.loads(path.read_text())
                data[key] = value
                path.write_text(json.dumps(data))
                self.assertNotEqual(self.call_build(artifacts).returncode, 0)
        for key, value in [('pass', False), ('lead_normalized_equal', False), ('different_files', []),
                           ('s_replaced_files', []), ('unexpected_diffs', ['README.md'])]:
            with self.subTest(field=key):
                artifacts = self.copy_artifacts()
                path = artifacts / 'comparison/comparison-manifest.json'
                data = json.loads(path.read_text())
                data[key] = value
                path.write_text(json.dumps(data))
                self.assertNotEqual(self.call_build(artifacts).returncode, 0)

    def test_selection_rejects_identity_drift_tamper_and_bad_hash(self):
        args = [self.set_path, self.set_sha, 'probe', self.head, self.tag, self.zip_sha, self.script_sha]
        for index, value in [(1, '0' * 64), (2, 'PROBE'), (3, '0' * 40), (4, 'wrong-tag'),
                             (5, '0' * 64), (6, '0' * 64)]:
            with self.subTest(arg=index):
                changed_args = list(args)
                changed_args[index] = value
                result, output = self.call_select(*changed_args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('error', result.stderr)
                self.assertFalse(output.exists())
        artifacts = self.copy_artifacts()
        # Generate a new valid record for the independent copy, then tamper.
        result = self.call_build(artifacts)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = artifacts / 'selected-set.json'
        # Even with the correct bytes/hash, an alias filename must be refused.
        shutil.copyfile(artifacts / 'experiment-set.json', path)
        result, output = self.call_select(path, hashlib.sha256(path.read_bytes()).hexdigest(), *args[2:])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set path mismatch', result.stderr)
        self.assertFalse(output.exists())
        path = artifacts / 'experiment-set.json'
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        (artifacts / 'probe/README.md').write_text('tampered after set\n')
        result, output = self.call_select(path, checksum, *args[2:])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Selected package bytes changed', result.stderr)
        self.assertFalse(output.exists())

    def test_rollback_equivalent_host_settings_exception_runtime_extras_newer_plan(self):
        package = next(p for p in self.document['packages'] if p['name'] == 'probe')
        root = Path(tempfile.mkdtemp(prefix='installed-', dir=self.work)) / 'source'
        origin = Path(package['root'])
        # Omit only the host-managed ROOT file during copy, without deletion.
        shutil.copytree(origin, root, ignore=lambda directory, names: ['settings.json'] if Path(directory) == origin else [])
        (root / '.in_use').mkdir()
        (root / '.in_use/12345').write_text('runtime\n')
        extras = self.ns['installed_matches'](root, package['expected_names'], package['hashes'])
        self.assertEqual(extras, ['.in_use/12345'])
        (root / 'VERSION').write_text('newer-switch\n')
        with self.assertRaisesRegex(ValueError, 'newest plan first'):
            self.ns['installed_matches'](root, package['expected_names'], package['hashes'])
        for rel in ['skills/oracle-dba/VERSION', 'probe-manifest.json', 'settings.json']:
            with self.subTest(mismatch=rel):
                target = Path(tempfile.mkdtemp(prefix='rollback-mismatch-', dir=self.work)) / 'source'
                shutil.copytree(origin, target)
                (target / rel).write_text('tampered\n')
                with self.assertRaises(ValueError):
                    self.ns['installed_matches'](target, package['expected_names'], package['hashes'])

    def test_unexpected_paths_and_runtime_markers_are_not_read(self):
        package = next(p for p in self.document['packages'] if p['name'] == 'probe')
        target = Path(tempfile.mkdtemp(prefix='inventory-', dir=self.work)) / 'source'
        shutil.copytree(package['root'], target)
        (target / '.in_use').mkdir()
        marker = target / '.in_use/9876'
        marker.write_text('runtime content must not be read\n')
        original = self.ns['sha']

        def spy(path):
            if Path(path) == marker:
                raise AssertionError('Unexpected/runtime content was read')
            return original(path)

        self.ns['sha'] = spy
        try:
            with self.assertRaisesRegex(ValueError, 'inventory before byte reads'):
                self.ns['file_map'](target, package['expected_names'])
            self.assertEqual(self.ns['installed_matches'](target, package['expected_names'], package['hashes']), ['.in_use/9876'])
        finally:
            self.ns['sha'] = original

    def test_raw_marker_count_equivalent_counts_locations_without_verdict(self):
        for package in self.document['packages']:
            markers = package['markers']['expected']
            text = json.dumps({'prompt': markers, 'result': markers}, ensure_ascii=False)
            actual = self.ns['raw_marker_counts'](text, markers)
            for marker in markers:
                self.assertEqual(actual[marker], 2)
            self.assertEqual(self.ns['raw_marker_counts']('unrelated', markers), {marker: 0 for marker in markers})



if __name__ == "__main__":
    unittest.main(verbosity=2)
