"""Static PS contracts and real Mac builder/verifier tests. No PS parse/run.

Run explicitly: python3 -m pytest tools/oncall/test_oncall_updater.py -q
The tests live here to keep this change inside the approved tools/oncall scope.
"""
from pathlib import Path, PureWindowsPath
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
             "tools/oncall/bomc_hashes.py",
             "tools/oncall/runbooks/ONCALL_RUNBOOK.r6.md", "tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md",
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


def rc6_fragment_bytes(name, chunk):
    if name == 'Assert-InstallPaths':
        replacements = [('    $RealRoot = $WorkBuddyRoot', "    $RealRoot = 'C:\\Users\\AI\\.workbuddy'"), ("        if ((Split-Path -Path $BoundRoot -Parent) -ine $Handoff -or (Split-Path -Path $BoundRoot -Leaf) -notmatch '^drill-[A-Za-z0-9][A-Za-z0-9-]*$') { throw '演练根必须是 HandoffRoot 下的 drill-<唯一编号>' }", "        if ($BoundRoot -notmatch '^D:\\\\crm-v36-handoff\\\\drill-[A-Za-z0-9][A-Za-z0-9-]*$') { throw '演练根必须是 D:\\crm-v36-handoff\\drill-<唯一编号>' }")]
        for current, original in replacements:
            if chunk.count(current) != 1:
                raise AssertionError('Unexpected rc7 root substitution')
            chunk = chunk.replace(current, original)
    return chunk


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
        self.assertIn("[string]$PythonExe = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\\Python\\Python312\\python.exe')", self.text)
        self.assertIn('$PythonExe -ieq $DefaultPythonExe', self.text)
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
                self.assertEqual(hashlib.sha256(rc6_fragment_bytes(name, chunk).encode("utf-8")).hexdigest(), FRAGMENT_SHA[name], name)
        # On this Mac, also compare the authorized r2 source itself. On Windows,
        # the fixed fragment hashes above provide the same offline byte check.
        if RUNBOOK.is_file():
            source_raw = RUNBOOK.read_bytes()
            self.assertEqual(hashlib.sha256(source_raw).hexdigest(), RUNBOOK_SHA)
            source = source_raw.decode("utf-8")
            for name, chunk in found:
                self.assertIn(rc6_fragment_bytes(name, chunk), source, name)

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
        self.assertIn("[string]$HandoffRoot = 'D:\\crm-v36-handoff'", self.text)
        self.assertIn("[string]$DevRoot = 'D:\\Dev'", self.text)
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

    def test_rc4_readme_requires_accepted_mac_tests_before_windows_verify(self):
        current = self.readme.split('## rc4 使用流程', 1)[1].split('\n## ', 1)[0]
        for phrase in ('2.8.0-rc4', '全部先在 Mac 运行', '人工复核并验收后',
                       '只做安装/切换 + VERIFY', '来源/缓存完整性、Skill 回执路径', '记录版本',
                       '仅在需确认宿主行为时加一个短会话', '两台都记录实际 WorkBuddy 版本、插件版本和模型',
                       '有差异时值班机检查覆盖差异', '固定 glm-5.3-flash', '逐次记录实际模型',
                       '关口前两台都查看宿主记忆条目', '是否清理或关闭由用户决定'):
            self.assertIn(phrase, current)
        # AGENTS.md is a source-checkout rule file, outside the plugin payload.
        agents = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
        for phrase in ('自检、WB 用例、7A/7B、校准和关口', '全部先在 Mac 运行',
                       'Mac 跑完、返回结果经人工复核并验收后', '安装/切换 + VERIFY',
                       '来源/缓存完整性、Skill 回执路径', '记录版本',
                       '仅在需确认宿主行为时加一个短会话', '两台都记录实际 WorkBuddy 版本、插件版本和模型',
                       '值班机检查必须覆盖差异', '固定 glm-5.3-flash', '逐次记录实际模型',
                       '两台机器都要查看宿主记忆条目', '是否清理或关闭由用户决定',
                       '请求 1 的有效值也是 200', '不是每个成员实际执行 200 轮', 'HOST_LIMIT'):
            self.assertIn(phrase, agents)


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
                        '--zip-sha', cls.zip_sha, '--script-sha', cls.script_sha, '--set-id', cls.set_id, '--dev-root', str(cls.repo.parent.parent),
                        '--handoff-root', str(artifacts.parent), '--workbuddy-root', str(cls.work / 'host')], check=False)

    @classmethod
    def call_select(cls, set_path, set_sha, package, head=None, tag=None, zip_sha=None, script_sha=None, output=None):
        if output is None:
            directory = cls.work / ('update-' + uuid.uuid4().hex)
            directory.mkdir()
            output = directory / 'selection.json'
        result = cls.run_command([sys.executable, str(cls.verifier), 'select', '--set', str(set_path),
                        '--set-sha', set_sha, '--package', package, '--head', head or cls.head,
                        '--tag', tag or cls.tag, '--zip-sha', zip_sha or cls.zip_sha,
                        '--script-sha', script_sha or cls.script_sha, '--output', str(output), '--dev-root', str(cls.repo.parent.parent),
                        '--handoff-root', str(Path(set_path).parent.parent), '--workbuddy-root', str(cls.work / 'host')], check=False)
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
        self.assertEqual(self.document['path_roots'], dict(dev_root=str(self.repo.parent.parent), handoff_root=str(self.artifacts.parent), workbuddy_root=str(self.work / 'host')))
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

    def test_current_rc4_probe_lines_are_accepted_by_existing_experiment_verifier(self):
        # Existing round-trip fixtures use a HEAD clone. Cover the current
        # uncommitted builder separately so rc4 wording is tested before commit.
        output = self.work / ('rc4-probe-' + uuid.uuid4().hex)
        self.run_command([sys.executable, str(ROOT / 'tools/make_probe_build.py'),
                          '--root', str(ROOT), '--out', str(output)])
        manifest = json.loads((output / 'probe-manifest.json').read_text(encoding='utf-8'))
        roles = json.loads((ROOT / 'policy-source/roles-source.json').read_text(encoding='utf-8'))
        targets = [('agents/telecom-crm-sre-team-lead.md', manifest['lead_markers']['marker_la']),
                   ('skills/stability-director/SKILL.md', manifest['lead_markers']['marker_ls'])]
        for sid, role in roles.items():
            if sid != 'stability-director':
                markers = manifest['markers'][role['agent']]
                targets += [('agents/' + role['agent'] + '.md', markers['marker_c']),
                            ('skills/' + sid + '/SKILL.md', markers['marker_d'])]
        self.assertEqual(len(targets), 16)
        self.assertEqual(manifest['source_version'], (ROOT / 'VERSION').read_text().strip())
        for rel, marker in targets:
            with self.subTest(rel=rel):
                self.ns['check_marker'](output, rel, marker)
                lines = (output / rel).read_text(encoding='utf-8').splitlines()
                line = next(line for line in lines if line.startswith('> ' + marker + '｜'))
                self.assertIn('回复开头单独一行原样输出本行', line)
                self.assertIn('不增补、不续写、不替换，不拼接后续正文', line)
                self.assertTrue(line.endswith('｜END'))

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



class PendingRunbookTests(unittest.TestCase):
    """Repository-only runbook contracts; these are not PowerShell execution."""

    @classmethod
    def setUpClass(cls):
        cls.r6 = ROOT / 'tools/oncall/runbooks/ONCALL_RUNBOOK.r6.md'
        cls.r7 = ROOT / 'tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md'
        cls.text = cls.r7.read_text(encoding='utf-8')
        cls.historical = cls.text.split('## rc6 值班机简单检查（2026-10-21）', 1)[0]
        cls.blocks = re.findall(r'```powershell\n(.*?)\n```', cls.historical, re.S)

    def test_preserved_r6_and_three_registered_prompts(self):
        self.assertEqual(hashlib.sha256(self.r6.read_bytes()).hexdigest(),
                         '89e4af06f9601a42db672692bf37465eba06625b96bcf0c9a8cc447dbb5660e7')
        blocks = re.findall(r'```text\n(.*?)\n```', self.historical, re.S)
        self.assertEqual([hashlib.sha256(b.encode()).hexdigest() for b in blocks], [
            '49893af69b52e0b5eb3cf8b44935c12f31500e776af2c0a112a33d3bef6249c6',
            '88db28bff7dc040f2e4d04add9be6ca67a8d3c09221071465fb4bd4d96055b18',
            'b057d3dca04e2760afc84357b3f25d611e81ef30300ca1d4c6762ad9790e3337',
            'c11fc20b0460e8c5d7d09890e571ca6c44e0c19e1b9477255765a3f7d77f014c',
            '426264c5976eb3b67e20f986b2d16d2b23db33de6a78b5d0bc8e4904ae947531'])

    def test_three_verify_blocks_define_identity_and_bootstrap(self):
        blocks = [b for b in self.blocks if '-Mode VERIFY' in b]
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            with self.subTest(block=blocks.index(block)):
                for token in ["$Tag = 'crm-sre-team-2.8.0-rc5'",
                              "$ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'",
                              "$ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'",
                              '$Bootstrap = (Read-Host', '$PlanPath = (Read-Host', '$PlanSha256 = (Read-Host',
                              '$SessionId = (Read-Host', "$Script = Join-Path $Bootstrap 'tools\\oncall\\Update-CrmSreTeam.ps1'",
                              '-SessionId $SessionId']:
                    self.assertIn(token, block)
                pattern = re.search(r"\$Bootstrap -cnotmatch '([^']+)'", block).group(1)
                self.assertRegex(r'D:\crm-v36-handoff\bootstrap-' + 'a' * 32, pattern)
                self.assertIsNone(re.fullmatch(pattern, r'D:\crm-v36-handoff\bootstrap-' + 'a' * 31))
        self.assertIn('-AgentId $AgentId', blocks[-1])
        self.assertIn('$AgentId = (Read-Host', blocks[-1])
        self.assertNotIn('2.8.0-rc4', self.text)
        self.assertEqual(self.text.count('rc3'), 1)

    def test_config_creation_and_query_are_separate(self):
        create = next(b for b in self.blocks if '$ConfigBytes =' in b)
        query = next(b for b in self.blocks if '$SavedOutputEncoding =' in b)
        self.assertLess(create.index('[string]::IsNullOrWhiteSpace($KbRoot)'), create.index('[IO.FileMode]::CreateNew'))
        self.assertIn('$KbRoot = (Read-Host', create)
        self.assertIn('$KbPython = (Read-Host', create)
        self.assertNotIn('CreateNew', query)
        self.assertNotIn('WriteAllBytes', query)
        self.assertIn('[Console]::OutputEncoding = $SavedOutputEncoding', query)
        self.assertIn("& '$KbPython' -X utf8 '$SearchScript' '$KbKeyword' --top 5", query)
        self.assertNotIn('Invoke-Expression', query)
        for token in ['fcntl', 'writer_lock', 'stamp', 'K14', 'K15', '未观察到']:
            self.assertIn(token, self.text)

    def test_tool_only_export_and_repository_only_inventory(self):
        export = next(b for b in self.blocks if '$SelectedRecords =' in b)
        self.assertIn('[IO.FileMode]::CreateNew', export)
        self.assertIn("[IO.File]::Open($Full,'Open','Read','ReadWrite')", export)
        self.assertIn('$Item | ConvertTo-Json', export)
        self.assertNotIn('$Row | ConvertTo-Json', export)
        self.assertNotIn('$Row.providerData', export)
        for forbidden in ['Remove-Item', 'Stop-Process', 'WriteAllBytes', 'Invoke-Expression']:
            self.assertNotIn(forbidden, export)
        manifest = json.loads((ROOT / 'release-manifest.json').read_text())
        for name in ['tools/oncall/runbooks/ONCALL_RUNBOOK.r6.md', 'tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md']:
            self.assertIn(name, manifest['repository_only_files'])
            self.assertNotIn(name, manifest['files'])

    def test_metadata_result_groups_format_separately(self):
        metadata = self.text.split('## ③ ', 1)[1].split('### fcntl', 1)[0]
        block = re.search(r'```powershell\n(.*?)\n```', metadata, re.S).group(1)
        self.assertEqual(block.count('| Format-Table -AutoSize | Out-Host'), 3)
        for group in ['@(', 'Get-ChildItem -LiteralPath $KbRoot -Directory', "if (Test-Path -LiteralPath $KbIndex -PathType Leaf)"]:
            self.assertIn(group, block)
        segments = block.split('| Format-Table -AutoSize | Out-Host')
        for segment, field in zip(segments, ['Check=$_', 'Directory=$_.Name', "Check='search_index'"]):
            self.assertIn(field, segment)

    def test_read_host_blocks_flush_before_first_prompt_and_trim(self):
        for number, block in enumerate(self.blocks):
            if 'Read-Host' not in block:
                continue
            with self.subTest(block=number):
                self.assertEqual(block.count('$Host.UI.RawUI.FlushInputBuffer()'), 1)
                self.assertLess(block.index('$Host.UI.RawUI.FlushInputBuffer()'), block.index('Read-Host'))
                for line in block.splitlines():
                    if 'Read-Host' in line:
                        self.assertRegex(line, r"\$\w+ = \(Read-Host '[^']*'\)\.Trim\(\)$")

    def test_powershell_blocks_ascii_and_config_marker_codepoints(self):
        for number, block in enumerate(self.blocks):
            with self.subTest(block=number):
                self.assertTrue(block.isascii())
        create = next(b for b in self.blocks if '$ConfigBytes =' in b)
        for var, expected in [('$SensitiveMarker', '敏感'), ('$PrivateMarker', '私密')]:
            value = re.search(re.escape(var) + r' = (.*)', create).group(1)
            chars = re.findall(r'\[char\]0x([0-9a-fA-F]+)', value)
            self.assertEqual(''.join(chr(int(c, 16)) for c in chars), expected)
        self.assertIn("exclude_markers=@('private','confidential','secret',$SensitiveMarker,$PrivateMarker)", create)

    def test_git_selection_and_delivered_commit_read_only_view(self):
        selector = '@(Get-Command -Name git -CommandType Application -All -ErrorAction Stop)[0].Source'
        git_blocks = [b for b in self.blocks if '$GitExe =' in b]
        self.assertEqual(len(git_blocks), 4)
        for block in git_blocks:
            self.assertIn('$GitExe = ' + selector, block)
        view = self.blocks[0]
        self.assertIn('rev-parse origin/main', view)
        self.assertIn('$DeliveredCommit = (Read-Host', view)
        self.assertIn('$RunbookCommit.Trim() -ine $DeliveredCommit', view)
        self.assertLess(view.index('$RunbookCommit.Trim() -ine $DeliveredCommit'), view.index('--no-pager show'))
        self.assertIn("($DeliveredCommit + ':tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md')", view)
        for forbidden in ['fetch', 'checkout', 'switch', 'clone', 'push']:
            self.assertIsNone(re.search(r'(?m)^\s*git .*\b' + forbidden + r'\b', view))

    def test_tool_export_reads_shared_stream_and_avoids_args_variable(self):
        export = next(b for b in self.blocks if '$SelectedRecords =' in b)
        self.assertNotIn('$Args', export)
        self.assertIn('$CallArgs = $Row.arguments', export)
        self.assertIn("[IO.File]::Open($Full,'Open','Read','ReadWrite')", export)
        self.assertIn('[IO.StreamReader]::new($ReadStream,$Utf8,$true)', export)
        self.assertIn('while (($Line = $Reader.ReadLine()) -ne $null)', export)
        self.assertRegex(export, r'(?s)\} finally \{\s*if \(\$null -ne \$Reader\) \{ \$Reader\.Dispose\(\); \$Reader = \$null \}\s*if \(\$null -ne \$ReadStream\) \{ \$ReadStream\.Dispose\(\); \$ReadStream = \$null \}')
        self.assertIn('$ReadStream.Dispose()', export)
        self.assertNotIn('[IO.File]::ReadLines', export)

    def test_query_script_hash_and_metadata_only_capture(self):
        query = next(b for b in self.blocks if '$SavedOutputEncoding =' in b)
        self.assertIn('$ExpectedSearchSha256 = (Read-Host', query)
        self.assertIn('(Get-FileHash -LiteralPath $SearchScript -Algorithm SHA256).Hash -ine $ExpectedSearchSha256', query)
        self.assertLess(query.index('SHA256 mismatch'), query.index('$QueryOutput = @(&'))
        self.assertIn('$QueryOutput = @(& $KbPython -X utf8 $SearchScript $KbKeyword --top 5 2>&1)', query)
        self.assertIn('$QueryResult.results', query)
        self.assertIn('$Result.absolute_path', query)
        self.assertIn('ExitCode=$QueryExitCode; Results=$ResultCount; ValidPaths=$ValidPathCount', query)
        self.assertIn('ExitCode=$QueryExitCode; CapturedUtf8Bytes=$QueryByteCount', query)
        self.assertNotIn('snippet', query)
        for line in query.splitlines():
            if 'Write-Host' in line:
                self.assertNotIn('$QueryText', line)
                self.assertNotIn('$QueryOutput', line)

    def test_preflight_model_yes_and_version_normalization(self):
        preflight = self.blocks[1]
        self.assertIn("$HostVersion -notmatch '^[vV]?\\d+\\.\\d+\\.\\d+$'", preflight)
        self.assertIn("$HostVersion = $HostVersion -replace '^[vV]', ''", preflight)
        self.assertIn("$ActualModel -ine 'glm-5.3-flash'", preflight)
        self.assertIn("$PreviousRunComplete -ine 'YES'", preflight)

    def d_section(self, heading):
        found = re.search(r'^' + re.escape(heading) + r'\n(.*?)(?=^#{1,3} |\Z)',
                          self.text, re.M | re.S)
        return found.group(1) if found else ''

    def d_block(self, heading):
        found = re.search(r'```powershell\n(.*?)\n```', self.d_section(heading), re.S)
        return found.group(1) if found else ''

    def assert_d_contracts(self, checks):
        # A missing new section must also fail negative assertions in the C baseline.
        for contract, condition in checks.items():
            with self.subTest(contract=contract):
                self.assertTrue(condition, contract)

    def test_d_appendix_prompt_hashes_and_maintainer_scope(self):
        checks = {}
        for heading, digest in [
                ('### A1 新建 rc5 知识库工具的提示词',
                 'c11fc20b0460e8c5d7d09890e571ca6c44e0c19e1b9477255765a3f7d77f014c'),
                ('### A2 排除已合并存根页的提示词',
                 '426264c5976eb3b67e20f986b2d16d2b23db33de6a78b5d0bc8e4904ae947531')]:
            section = self.d_section(heading)
            found = re.search(r'```text\n(.*?)\n```', section, re.S)
            checks[heading + ': exact bytes'] = bool(found) and hashlib.sha256(
                found.group(1).encode('utf-8')).hexdigest() == digest
            checks[heading + ': not host test'] = '不是 WorkBuddy 被测提示词' in section
        a2 = self.d_section('### A2 排除已合并存根页的提示词')
        checks.update({'A2 not run': '还没运行' in a2,
                       'A2 both hashes change': '脚本和索引的哈希都会变' in a2,
                       'A2 new expectations and evidence': '④b 的期望哈希' in a2 and '记进证据' in a2})
        self.assert_d_contracts(checks)

    def test_d_refresh_session_hygiene_and_plan_lock_recovery(self):
        refresh = self.d_section('### ②b 客户端刷新与回执会话')
        block = self.d_block('### ②b 客户端刷新与回执会话')
        lock = self.d_section('### ②a PLAN 文件占用时的处理')
        checks = {
            'UI refresh only': '技能 → 套件 → my-experts ⋯ → 刷新' in refresh and '绝不点“删除”' in refresh,
            'cache presence gate': bool(block) and "'.workbuddy\\plugins\\cache\\my-experts\\crm-sre-team\\2.8.0-rc5'" in block
                and 'Test-Path -LiteralPath $CachePath -PathType Container' in block and "throw 'Stop: rc5 cache directory missing" in block,
            'memory injection reason': '<工作区>\\.workbuddy\\memory\\' in refresh and '注入后续会话' in refresh,
            'PLAN failure retains update': '保留失败的 update 目录' in lock and '新的 RunId' in lock,
            'PLAN repeated failures stop': '连续失败就停下' in lock and '报错原文' in lock,
            'PLAN no destructive workaround': '不删除、不结束进程、不手动改目录' in lock,
        }
        for heading in ['### ②b 客户端刷新与回执会话', '## ⑤ WorkBuddy知识库冒烟及独立VERIFY',
                        '## ⑥ 版本差异、自检2与带成员VERIFY']:
            section = self.d_section(heading)
            checks[heading + ': clean session'] = '新建的空文件夹' in section and '新会话' in section
            checks[heading + ': explicit model'] = '显式选择 GLM-5.3-Flash' in section
            checks[heading + ': workspace exclusions'] = '插件目录、知识库目录或已有工作区' in section
        self.assert_d_contracts(checks)

    def test_d_verify_extras_and_ior_retry_deferred(self):
        extras = self.d_section('### ②c VERIFY 的 extra path')
        deferred = self.d_section('## 后续事项：IoRetry')
        self.assert_d_contracts({
            'source memory is reviewed and retained': '.workbuddy/memory/*' in extras and '不删' in extras and '人工复核' in extras,
            'cache in-use is normal': '.in_use/<进程号>' in extras and '正常' in extras,
            'other extras reviewed': '其他 extra path' in extras and '人工复核' in extras,
            'IoRetry later': '后续事项' in deferred and '不在本提交' in deferred,
            'updater unchanged': '本提交不改 Update-CrmSreTeam.ps1' in deferred,
        })

    def test_d_discovery_is_metadata_only_and_fallback_has_mac_gate(self):
        section = self.d_section('### ③a 缺脚本或索引：只读发现与分支')
        block = self.d_block('### ③a 缺脚本或索引：只读发现与分支')
        checks = {token + ': discovery': token in block for token in
                  ["'kb_*.py'", "'*search_index*'", 'WikiSubdir=', "'.workbuddy'", "'.obsidian'", "'raw\\.svn'"]}
        checks['discovery does not read content'] = bool(block) and not re.search(
            r'Get-Content|ReadAllText|ReadAllLines|ReadAllBytes|Get-FileHash|WriteAll|CreateNew|Remove-Item', block)
        checks['existing tool discovery and separate tables'] = bool(block) and 'Get-KbMetadataFiles' in block and block.count('| Format-Table -AutoSize | Out-Host') >= 3
        checks['recommend maintainer tool creation'] = '推荐' in section and '附录 A1' in section and 'SHA256' in section and '然后做 ④' in section
        checks['Mac fallback acceptance required'] = 'Mac 上还没测过' in section and 'Mac 补测并验收之前，值班机不得使用' in section
        checks['KB opt-out'] = '跳过 ④⑤' in section and 'KB=NOT_CONFIGURED' in section
        compatibility = self.d_section('### fcntl 兼容性')
        checks['fcntl fallback is gated'] = '同样受 ③a 的 Mac 补测与验收门约束' in compatibility
        self.assert_d_contracts(checks)

    def test_d_query_invalid_keyword_diagnostics_and_new_hashes(self):
        query = next(b for b in self.blocks if '$SavedOutputEncoding =' in b)
        self.assert_d_contracts({
            'invalid keyword character codes': '$KbKeyword.ToCharArray()' in query and "'U+{0:X4}' -f [int]$_" in query,
            'rerun query only': 'rerun step 4b only' in query,
            'index expected SHA256': '$ExpectedIndexSha256 = (Read-Host' in query
                and '(Get-FileHash -LiteralPath $SearchIndex -Algorithm SHA256).Hash -ine $ExpectedIndexSha256' in query,
            'JSON error disqualifies query': "$QueryResult.PSObject.Properties.Name -contains 'error'" in query,
            'successful query marker': "Write-Host 'QUERY_OK'" in query,
        })

    def test_d_smoke_line_numbers_exit_codes_topic_and_stub_quality(self):
        section = self.d_section('### ⑤a 判定补充与主题选择')
        self.assert_d_contracts({
            'Read trailing line allowance': '1 ≤ 起 ≤ 止 ≤ 行数 + 1' in section and '末尾换行' in section,
            'Windows missing exit code not failure': '没有退出码不算失败' in section and 'Exit Code:' in section and 'Mac' in section,
            'JSON and leader report decide': '有 results、没有 error' in section and '团长报告' in section,
            'business topic length': '2–8 个汉字或常用英文缩写' in section,
            'topic exclusions': '问句、标点和停用词' in section and '客户、人员、凭据' in section,
            'query first': '先用 ④b 试跑，确认有结果' in section,
            'stub page is quality issue': '存根页' in section and '质量问题，不算失败' in section and '附录 A2' in section,
        })

    def test_d_console_summary_shared_reads_and_citation_range(self):
        block = self.d_block('## ⑦b 可选：控制台会话摘要')
        checks = {
            'latest three sessions': 'Select-Object -First 3' in block,
            'Enter chooses first': '$SessionId = $RecentSessions[0].BaseName' in block,
            'shared JSONL read': "[IO.File]::Open($RecordPath,'Open','Read','ReadWrite')" in block,
            'shared line-count read': "[IO.File]::Open($CitationPath,'Open','Read','ReadWrite')" in block,
            'flush and trimmed inputs': '$Host.UI.RawUI.FlushInputBuffer()' in block and "$SessionId = (Read-Host 'Smoke session ID (Enter selects the first record)').Trim()" in block,
            'call and result correlation': '$Calls.ContainsKey($CallId)' in block and '$Calls[$CallId] = $CallNumber' in block,
            'status chars first line': 'status={2} chars={3} first={4}' in block and '$FirstLine.Substring(0,160)' in block,
            'no error-like heuristic': bool(block) and 'ERROR-LIKE' not in block and '<tool_use_error>' not in block,
            'skip reasoning before parsing': bool(block) and block.find("if ($Line -match '") < block.find('$Rec = $Line | ConvertFrom-Json') and 'reasoning' in block,
            'no provider data access': bool(block) and 'providerData' not in block and '$Rec | ConvertTo-Json' not in block,
            'console only': bool(block) and not re.search(r'CreateNew|WriteAll|Set-Content|Out-File|Add-Content|StreamWriter|FileAccess\]::Write', block),
            'E-K mentions counted': "[regex]::Matches($FinalText, 'E-K\\d+')" in block,
            'citation existence and wiki': 'Test-Path -LiteralPath $CitationPath -PathType Leaf' in block and '$CitationPath.StartsWith($WikiPrefix,[StringComparison]::OrdinalIgnoreCase)' in block,
            'citation range includes trailing empty line': '$From -ge 1 -and $To -ge $From -and $To -le ($LineCount + 1)' in block,
            'read streams released': '$Reader.Dispose()' in block and '$ReadStream.Dispose()' in block and '$CitationReader.Dispose()' in block and '$CitationStream.Dispose()' in block,
        }
        self.assert_d_contracts(checks)

    def test_d_change_audit_separates_editor_metadata_without_content_reads(self):
        block = self.d_block('### A3 只读改动审计')
        checks = {token + ': audit': token in block for token in
                  ["$Child.Name -ieq '.git'", 'CreationTime -ge $Since', 'LastWriteTime -ge $Since',
                   "'raw\\.svn\\trae-ai-tob\\'", '.obsidian', '.trae', '.workbuddy', '.claude',
                   "Category='TOOL'", "Category='BUSINESS'", 'Group-Object Category,Area', 'Bytes=$File.Length']}
        checks['audit metadata only'] = bool(block) and not re.search(
            r'Get-Content|ReadAll|ReadLine|Get-FileHash|CreateNew|WriteAll|Remove-Item', block)
        checks['audit refuses links'] = bool(block) and 'ReparsePoint' in block
        self.assert_d_contracts(checks)

    def test_d_oncall_record_identity_counts_verdicts_and_deviations(self):
        record = self.d_section('## 10-14 值班机实测记录')
        checks = {token + ': observed fact': token in record for token in [
            'r6 加上对话里的加固块', '不是 r7', 'Windows 未执行',
            '| WorkBuddy | 5.8.2 | 5.8.2 |', '| 模型 | GLM-5.3-Flash | glm-5.3-flash |',
            '4bcddc8f-9012-4c8c-a03a-9a7844f04568', 'd299c0d4-3ddc-432e-9313-8a2f51d516aa',
            'verify-3cc5a55c9a0f4f92b37354ee9055bbba.json', 'verify-733c49acd06e46f09fa959f7c4fc17ca.json',
            'raw-evidence-a40c52bae8394df386b4f32473dd7cc0', 'raw-evidence-c41e67193c654afb924ddbce55f3ef07',
            '132A7393D9F4730A3EC7D4A47AB501CC47A7F36E4001EC2BEF29274FAA9A4EC2',
            '596B2F29C97C2A2CF8531A301D1968D3515D669F701752551C346FC62704FB2E',
            '544/545', '359', '356', '⑤ PASS', '自检 2 未运行', 'D:\\qoder\\test',
            '4 个是 Trae 追踪数据', '2 个是用户在编辑的业务笔记', 'Mac 未审代码']}
        self.assert_d_contracts(checks)

    def test_d_new_headings_difference_and_evidence_checklist(self):
        headings = ['### ②a PLAN 文件占用时的处理', '### ②b 客户端刷新与回执会话',
                    '### ②c VERIFY 的 extra path', '### ③a 缺脚本或索引：只读发现与分支',
                    '### ⑤a 判定补充与主题选择', '## ⑦b 可选：控制台会话摘要',
                    '## 10-14 值班机实测记录', '## 附录 A：知识库维护与审计',
                    '### A1 新建 rc5 知识库工具的提示词', '### A2 排除已合并存根页的提示词',
                    '### A3 只读改动审计', '## 后续事项：IoRetry']
        checks = {heading + ': exists once': self.text.count(heading + '\n') == 1 for heading in headings}
        intro = self.text.split('## 发布身份与只读查看', 1)[0]
        checks['D difference described'] = '提交 D 增加' in intro and '10-14 值班机实测记录' in intro
        evidence = self.d_section('## 带回的证据清单')
        for token in ['⑦b 的控制台输出（可选）', '运行 A2 后的新哈希', '刷新后的缓存存在性',
                      '空文件夹', 'extra path', '只读发现', 'A3', '字符码']:
            checks[token + ': evidence'] = token in evidence
        self.assert_d_contracts(checks)


    def test_d2_smoke_record_distinguishes_observation_from_json_verification(self):
        record = self.d_section('## 10-14 值班机实测记录')
        smoke = next(line for line in record.splitlines() if line.startswith('- **冒烟**：'))
        self.assert_d_contracts({
            'observed stdout first line and character count': '首行是 `{`，共 2613 字符' in smoke
                and '团长据此列出了结果' in smoke,
            'smoke JSON parsing was not verified': '没有对这次结果做过 JSON 解析核对' in smoke,
            'manual query parsing is separate evidence': '同主题的 ④b 人工查询解析通过（QUERY_OK）' in smoke,
            'record does not claim verified smoke JSON': 'JSON 可解析' not in record,
        })

    def test_d2_console_summary_isolates_unresolvable_citation_paths(self):
        block = self.d_block('## ⑦b 可选：控制台会话摘要')
        protected = re.search(
            r'try \{\s*\$CitationPath = \[IO\.Path\]::GetFullPath\(\$Match\.Groups\[1\]\.Value\)'
            r'\s*\} catch \{(?P<handler>.*?)\n\s*\}', block, re.S)
        handler = protected.group('handler') if protected else ''
        self.assert_d_contracts({
            'citation normalization is inside a local try': bool(protected),
            'unresolvable path reports its citation number': bool(protected)
                and "Write-Host ('CITE {0}: path not resolvable' -f $CitationCount)" in handler,
            'unresolvable path continues with the next citation': bool(protected)
                and bool(re.search(r'^\s*continue\s*$', handler, re.M)),
        })

    def test_d2_query_error_object_has_private_diagnostic_and_rerun_branch(self):
        query = next(b for b in self.blocks if '$SavedOutputEncoding =' in b)
        error_branch = re.search(
            r"if \(\$null -ne \$QueryResult -and \$QueryResult\.PSObject\.Properties\.Name -contains 'error'\)"
            r' \{(?P<body>.*?)\n\s*\}', query, re.S)
        body = error_branch.group('body') if error_branch else ''
        writes = [line.strip() for line in body.splitlines() if 'Write-Host' in line]
        self.assert_d_contracts({
            'error object is classified before validating results': bool(error_branch)
                and error_branch.start() < query.index("$QueryResult.PSObject.Properties.Name -notcontains 'results'"),
            'error diagnostic prints no error payload': bool(error_branch) and writes == [
                'Write-Host "ExitCode=$QueryExitCode; query tool returned an error object"',
                "Write-Host 'QUERY_ERROR; retain config; rerun step 4b only'"],
            'error branch exits and leaves unparseable handling separate': bool(error_branch)
                and bool(re.search(r'^\s*return\s*$', body, re.M))
                and "Write-Host 'QUERY_UNPARSEABLE; retain config; rerun step 4b only'" in query,
        })

    def test_d2_intro_attributes_execution_instructions_and_actual_query_outcome(self):
        intro = self.text.split('## 发布身份与只读查看', 1)[0]
        instructions = '此前给出的执行说明为：'
        directives = ['跳过旧「① 前置」', 'UPDATE 到 VERIFY 用同一个窗口',
                      '③④用同一个窗口', '若④遇到 fcntl 错误']
        self.assert_d_contracts({
            'all original directives are attributed to prior instructions': instructions in intro
                and all(token in intro and intro.index(instructions) < intro.index(token) for token in directives),
            'actual run used the compatible tool without fcntl failure':
                '本轮用户的 AI 新建了兼容工具，④查询通过，没有遇到 fcntl 错误' in intro,
        })


class Rc6SimpleCheckTests(unittest.TestCase):
    """Freeze the reviewed handoff without running Windows or a host session."""

    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md').read_bytes()
        heading = '## rc6 值班机简单检查（2026-10-21）'.encode('utf-8')
        cls.historical, separator, tail = cls.raw.partition(heading)
        if not separator:
            raise AssertionError('Missing rc6 simple check')
        cls.section, separator, cls.bomc = tail.partition(b'## rc6 BOMC')
        if not separator:
            raise AssertionError('Missing subsequent rc6 BOMC section')
        cls.text = cls.section.decode('utf-8')
        cls.blocks = re.findall(rb'```powershell\n(.*?)^```', cls.section, re.M | re.S)

    def test_published_identity_and_distinct_runbook_delivery(self):
        for token in [
                'crm-sre-team-2.8.0-rc6', '990b6b666bc484ddcc695976f2cb52f4000e1f15',
                'feb9aae92bb9408bf01bf86379d3e6f65c60b502',
                'efe41732c8c3c9d7a3f2135174cce3b79aca5618e7e212e00b6fae60eac55123',
                'crm-sre-team-2.8.0-rc6.zip；2479908 字节；555 个', '含根 settings.json',
                'd0fad3158a361ebd18a79b06f660e1c8f9f19bed2df4f8f3b2fb5829a289adde',
                '自 58731a9 未改', 'WorkBuddy 5.8.3 / glm-5.3-flash', 'fix9 r1 9/9 PASS',
                '“交付的手册提交”是包含本节的那次提交，与安装身份 ExpectedCommit=',
                '不把交付的手册提交填入 ExpectedCommit', '安装一律以 rc6 标签和上表为准']:
            self.assertIn(token, self.text)
        manifest = json.loads((ROOT / 'release-manifest.json').read_text(encoding='utf-8'))
        # Historical rc6 stays 555 above; current rc8 adds its registered tests.
        self.assertEqual(len(manifest['files']), 556)
        self.assertIn('tests/test_rc8_bomc.py', manifest['files'])
        self.assertIn('settings.json', manifest['files'])
        identity = re.search(r'^\| 更新脚本 SHA256 \| tools/oncall/Update-CrmSreTeam.ps1：([0-9a-f]{64})；', self.text, re.M)
        self.assertIsNotNone(identity)
        self.assertEqual(identity.group(1),
                         'd0fad3158a361ebd18a79b06f660e1c8f9f19bed2df4f8f3b2fb5829a289adde')
        intro = self.historical.decode('utf-8').split('## 发布身份与只读查看', 1)[0]
        for token in ['rc8 候选发布', '已合并 main', 'Windows 未执行', 'NOT_RUN']:
            self.assertIn(token, intro)
        for token in ['Mac fix9 r1 已完成并经人工验收（9/9 PASS',
                      '不能使用上文 rc5 的 Tag/ExpectedCommit/ExpectedZipSha256 安装 rc8']:
            self.assertIn(token, self.bomc.decode('utf-8'))

    def test_four_reference_blocks_only_change_reviewed_identity_lines(self):
        original = re.findall(rb'```powershell\n(.*?)^```', self.historical, re.M | re.S)[1:5]
        self.assertEqual(len(self.blocks), 4)
        self.assertEqual(len(original), 4)
        replacements = [
            (b'crm-sre-team-2.8.0-rc5', b'crm-sre-team-2.8.0-rc6'),
            (b'58682ff17dd9e3f9f6be0c681f2b110a758fad9a', b'feb9aae92bb9408bf01bf86379d3e6f65c60b502'),
            (b'7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e',
             b'efe41732c8c3c9d7a3f2135174cce3b79aca5618e7e212e00b6fae60eac55123'),
            (b'crm-sre-team\\2.8.0-rc5', b'crm-sre-team\\2.8.0-rc6'),
            (b'Stop: local rc5 tag points elsewhere', b'Stop: local rc6 tag points elsewhere'),
            (b'Stop: rc5 cache directory missing', b'Stop: rc6 cache directory missing'),
            (b'Bootstrap is not the published rc5 commit', b'Bootstrap is not the published rc6 commit'),
        ]
        digests = [
            '56aef7304b9fb854d046e1e26d1795320f4a2ccee61fde57a5301961b38be265',
            'caac9339af4f956c3e713d68c3a116df7ea653df1cce528577328de06cc6bc51',
            '2a09ed2292357affe15e3407bb99d233b0c3e36ee80b313deb4e1f93f9ae578b',
            '9c0d046f1371c9daa8a8b162fdd2b81b4d6919d21d2f54143e91eb6d46bfb2b4',
        ]
        for number, (old, actual, digest) in enumerate(zip(original, self.blocks, digests), 1):
            with self.subTest(block=number):
                for before, after in replacements:
                    old = old.replace(before, after)
                self.assertEqual(actual, old)
                self.assertTrue(actual.isascii())
                self.assertEqual(hashlib.sha256(actual).hexdigest(), digest)

    def test_install_verify_message_bytes_and_target_receipts(self):
        messages = re.findall(rb'```text\n(.*?)\n```', self.section, re.S)
        self.assertEqual(len(messages), 1)
        self.assertEqual(hashlib.sha256(messages[0]).hexdigest(),
                         'ebb50a6f6e371f146c31fdbd34653710e3b74b17f8601ae1fd8e19c107b4391e')
        for token in ['显式选择 GLM-5.3-Flash', '不点“召唤”', '不委派成员',
                      'skill-receipts.json', 'stability-director 与 bomc-alarm-readonly 两条',
                      'updater 实际只要求至少一条', '缺任一条，本次检查未完成',
                      'PASS_DECLARED_FILES_ONLY', 'host_acceptance=HUMAN_REVIEW_REQUIRED',
                      '554/555, root settings.json missing (host-managed)',
                      '555/555, root settings.json matches package']:
            self.assertIn(token, self.text)

    def test_simple_scope_failure_handling_and_private_evidence(self):
        for token in ['不做本文 r7 的 ③～⑦', '不跑全套', '普通 Windows PowerShell 5.1',
                      '先带回原输出，不继续', '由用户正常退出 WorkBuddy',
                      'PLAN→展示计划→用户核对后输入一次 YES→APPLY', '②a PLAN 文件占用',
                      'ZIP 哈希不符或其他报错', '绝不点“删除”', '.workbuddy/memory/*',
                      '.in_use/<进程号>', '只记名称和数量，不删', 'SHA256SUMS',
                      '会话 ID 和本机路径只带回给 Claude，不写进仓库', 'bomc.json 本次不建',
                      '按 BRC-8 停下并写明证据缺口', '先做真实输出形状核对',
                      'bomc.json 必须填 skill_config', 'scripts_sha256 在值班机上计算',
                      '短会话默认不做', '先带回版本号，再决定是否加',
                      '用客户端“刷新”切回 rc5，再 VERIFY', '不覆盖旧备份']:
            self.assertIn(token, self.text)
        self.assertNotRegex(self.text, r'/Volumes/|/Users/|\b\d{1,3}(?:\.\d{1,3}){3}\b')
        self.assertNotRegex(self.text, r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b')


class Rc7SimpleCheckTests(unittest.TestCase):
    """Freeze the rc7 handoff independently of external archives or Windows."""

    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md').read_bytes()
        heading = '## rc7 值班机简单检查（2026-10-21）'.encode('utf-8')
        cls.previous, separator, cls.section = cls.raw.partition(heading)
        if not separator:
            raise AssertionError('Missing rc7 simple check')
        cls.section = cls.section.split(
            '## rc8 值班机简单检查（2026-10-22）'.encode('utf-8'), 1)[0]
        cls.historical, cls.rc6 = cls.previous.split(
            '## rc6 值班机简单检查（2026-10-21）'.encode('utf-8'), 1)
        cls.rc6, cls.bomc = cls.rc6.split(b'## rc6 BOMC', 1)
        cls.text = cls.section.decode('utf-8')
        cls.blocks = re.findall(rb'```powershell\n(.*?)^```', cls.section, re.M | re.S)

    def test_release_identity_defaults_and_current_entrypoints(self):
        for token in [
                '27371e65d7e7eb4910d66e8a30a8c366df7eb652',
                '15cee1b54c83f60fa6b9b46c3b9957830abe2768',
                '2847ba65bef63b79e1bb7ea32a32bf8bdd3a02ff0e236440bdc26ec79495de04',
                'crm-sre-team-2.8.0-rc7.zip；2502889 字节；555 个', '含根 settings.json',
                'fix10（a49547a）起改动', '-DevRoot、-HandoffRoot、-WorkBuddyRoot',
                r'DevRoot=D:\Dev', r'HandoffRoot=D:\crm-v36-handoff',
                r'PythonExe=%LOCALAPPDATA%\Programs\Python\Python312\python.exe',
                'WorkBuddy 5.8.3 / glm-5.3-flash；fix11 r1 14/14 PASS',
                '“交付的手册提交”是包含本节的那次提交，与安装身份 ExpectedCommit=',
                '不把交付的手册提交填入 ExpectedCommit', '安装一律以 rc7 标签和上表为准',
                '生成带 path_roots 的新计划与独立备份', '不复用 rc5 旧计划']:
            self.assertIn(token, self.text)
        digest = '342fd92b64ca403cc22a59c776bd5b2f3ff35075f2d03c5ff5df6ceddfd4691e'
        self.assertEqual(hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), digest)
        self.assertIn('tools/oncall/Update-CrmSreTeam.ps1：' + digest, self.text)
        intro, view = self.raw.decode('utf-8').split('## 发布身份与只读查看', 1)
        self.assertTrue(intro.startswith('# 值班机手册 r7 · rc8 候选发布（已合并 main，Windows 未执行）\n'))
        self.assertIn('rc8 值班机简单检查（2026-10-22）', intro)
        self.assertIn('本次 rc8 安装身份见“rc8 值班机简单检查（2026-10-22）”',
                      view.split('## ①', 1)[0])
        for token in ['已被“rc8 值班机简单检查（2026-10-22）”取代', 'Windows 未执行', '保留为历史']:
            self.assertIn(token, self.rc6.decode('utf-8'))
        for token in ['随 rc8 候选发布沿用', '守卫 VERSION 现为 2.8.0-rc8',
                      '按“rc8 值班机简单检查（2026-10-22）”身份表', '同一 rc8 目录', '此次 rc8 的 -Tag']:
            self.assertIn(token, self.bomc.decode('utf-8'))

    def test_historical_code_blocks_remain_byte_identical(self):
        for section, count, digest in [
                (self.historical, 19, '1ef6aa1bc37da78fdb61512526b62391aa3acc1ea11e8a4d5b3c28b18e092223'),
                (self.rc6, 5, '7fc5d25671a4ebbedb66efc7697246b1fc2c20525e2133caabca112b7b223025')]:
            blocks = re.findall(rb'^```[^\n]*\n.*?^```\n', section, re.M | re.S)
            self.assertEqual(len(blocks), count)
            self.assertEqual(hashlib.sha256(b''.join(blocks)).hexdigest(), digest)

    def test_four_frozen_blocks_only_change_rc6_identity_lines(self):
        original = re.findall(rb'```powershell\n(.*?)^```', self.rc6, re.M | re.S)
        replacements = [
            (b'crm-sre-team-2.8.0-rc6', b'crm-sre-team-2.8.0-rc7'),
            (b'feb9aae92bb9408bf01bf86379d3e6f65c60b502', b'15cee1b54c83f60fa6b9b46c3b9957830abe2768'),
            (b'efe41732c8c3c9d7a3f2135174cce3b79aca5618e7e212e00b6fae60eac55123',
             b'2847ba65bef63b79e1bb7ea32a32bf8bdd3a02ff0e236440bdc26ec79495de04'),
            (b'crm-sre-team\\2.8.0-rc6', b'crm-sre-team\\2.8.0-rc7'),
            (b'Stop: local rc6 tag points elsewhere', b'Stop: local rc7 tag points elsewhere'),
            (b'Stop: rc6 cache directory missing', b'Stop: rc7 cache directory missing'),
            (b'Bootstrap is not the published rc6 commit', b'Bootstrap is not the published rc7 commit'),
        ]
        digests = [
            'e8ec0e3b1d96fa0248c1684f72b0a8af8b3d0119f3bc8900ac5ed81535b5421f',
            'aa72c091d1d6f0f74ed96671b3cfe5b039b2ce1daee2b3dc31e98b59396d2ff4',
            'a8e4fb6a3f1c3fc7cd995fc1ef1587549c0fddce8485a872c47b2170972b710a',
            '81da32bb31cd221a8e381c132e6e99f7e10be502872d602b543c36abbb1f2d54',
        ]
        self.assertEqual(len(original), 4)
        self.assertEqual(len(self.blocks), 4)
        for number, (old, actual, digest) in enumerate(zip(original, self.blocks, digests), 1):
            with self.subTest(block=number):
                for before, after in replacements:
                    old = old.replace(before, after)
                self.assertEqual(actual, old)
                self.assertEqual(hashlib.sha256(actual).hexdigest(), digest)
                self.assertTrue(actual.isascii())
                for option in [b'-DevRoot', b'-HandoffRoot', b'-WorkBuddyRoot', b'-PythonExe', b'-RunPytest']:
                    self.assertNotIn(option, actual)
        self.assertNotIn(b'-PlanPath', self.blocks[1])
        self.assertIn(b'-PlanPath $PlanPath -PlanSha256 $PlanSha256 -SessionId $SessionId', self.blocks[3])

    def test_install_verify_receipts_scope_and_private_evidence(self):
        messages = re.findall(rb'```text\n(.*?)\n```', self.section, re.S)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages, re.findall(rb'```text\n(.*?)\n```', self.rc6, re.S))
        self.assertEqual(hashlib.sha256(messages[0]).hexdigest(),
                         'ebb50a6f6e371f146c31fdbd34653710e3b74b17f8601ae1fd8e19c107b4391e')
        for token in ['预期 rc5', '只做本节步骤 1～5', 'rc6 简单检查已被本节取代，不再执行',
                      '不做本文 r7 的 ③～⑦', '不跑全套', '普通 Windows PowerShell 5.1',
                      '先带回原输出，不继续', '由用户正常退出 WorkBuddy',
                      'PLAN→展示计划→用户核对后输入一次 YES→APPLY', '②a PLAN 文件占用',
                      'ZIP 哈希不符或其他报错', '绝不点“删除”', '新建一个空文件夹并开新会话',
                      '显式选择 GLM-5.3-Flash', '不点“召唤”',
                      r'...\plugins\cache\my-experts\crm-sre-team\2.8.0-rc7\skills' + '\\',
                      'stability-director 与 bomc-alarm-readonly 两条 2.8.0-rc7 缓存路径',
                      'updater 实际只要求至少一条', '缺任一条，本次检查未完成',
                      '554/555, root settings.json missing (host-managed)',
                      '555/555, root settings.json matches package', '.workbuddy/memory/*',
                      '.in_use/<进程号>', '只记名称和数量，不删', 'PASS_DECLARED_FILES_ONLY',
                      'host_acceptance=HUMAN_REVIEW_REQUIRED', 'SHA256SUMS',
                      '未运行的成员记 NOT_RUN', '会话 ID 和本机路径只带回给 Claude，不写进仓库',
                      'bomc.json 本次不建', '按 BRC-8 停下并写明证据缺口',
                      '先做真实输出形状核对', 'bomc.json 必须填 skill_config',
                      'scripts_sha256 在值班机上计算', '短会话默认不做',
                      '先带回版本号，再决定是否加', '用客户端“刷新”切回 rc5，再 VERIFY',
                      '不把 rc5 旧计划交给 rc7 更新器', '不覆盖旧备份']:
            self.assertIn(token, self.text)
        self.assertNotRegex(self.text, r'/Volumes/|/Users/|\b\d{1,3}(?:\.\d{1,3}){3}\b')
        self.assertNotRegex(self.text, r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b')


class Rc8SimpleCheckTests(unittest.TestCase):
    """Freeze the rc8 handoff and its deployment boundary without a host run."""

    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md').read_bytes()
        heading = '## rc8 值班机简单检查（2026-10-22）'.encode('utf-8')
        cls.previous, separator, cls.section = cls.raw.partition(heading)
        if not separator or heading in cls.section:
            raise AssertionError('Expected exactly one rc8 simple check')
        cls.rc7 = cls.previous.split('## rc7 值班机简单检查（2026-10-21）'.encode('utf-8'), 1)[1]
        cls.bomc = cls.previous.split(b'## rc6 BOMC', 1)[1].split(
            '## rc7 值班机简单检查（2026-10-21）'.encode('utf-8'), 1)[0].decode('utf-8')
        cls.text = cls.section.decode('utf-8')
        cls.blocks = re.findall(rb'```powershell\n(.*?)^```', cls.section, re.M | re.S)

    def test_release_identity_and_runbook_delivery_are_distinct(self):
        for token in [
                'crm-sre-team-2.8.0-rc8', '986f8fda4ca6ceb20584a6980aecf9dde1f357af',
                '6a92117244ec6d85530fd11ef245d7cf22329c7e',
                '1790790fa9a8734e2565b08f73fb91469c43dbb15d90ade658f0fd7a1fca2380',
                'crm-sre-team-2.8.0-rc8.zip；2562364 字节；556 个', '含根 settings.json',
                'fix10（a49547a）起改动', 'rc8 未再改，与 rc7 相同',
                r'DevRoot=D:\Dev', r'HandoffRoot=D:\crm-v36-handoff',
                r'PythonExe=%LOCALAPPDATA%\Programs\Python\Python312\python.exe',
                'WorkBuddy 5.8.3 / glm-5.3-flash；fix15 r1 宿主 8/8 PASS',
                '会话外通道冒烟 6/6 PASS，已人工验收',
                '“交付的手册提交”是包含本节的那次提交，与安装身份 ExpectedCommit=',
                '安装一律以 rc8 标签和上表为准', '不把交付的手册提交填入 ExpectedCommit',
                '生成带 path_roots 的新计划与独立备份', '不复用 rc5 旧计划']:
            self.assertIn(token, self.text)
        digest = '342fd92b64ca403cc22a59c776bd5b2f3ff35075f2d03c5ff5df6ceddfd4691e'
        self.assertEqual(hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), digest)
        self.assertIn('tools/oncall/Update-CrmSreTeam.ps1：' + digest, self.text)
        self.assertIn('已被“rc8 值班机简单检查（2026-10-22）”取代', self.rc7.decode('utf-8'))

    def test_four_frozen_blocks_only_change_twelve_reviewed_rc7_lines(self):
        original = re.findall(rb'```powershell\n(.*?)^```', self.rc7, re.M | re.S)
        replacements = [
            (b'crm-sre-team-2.8.0-rc7', b'crm-sre-team-2.8.0-rc8'),
            (b'15cee1b54c83f60fa6b9b46c3b9957830abe2768', b'6a92117244ec6d85530fd11ef245d7cf22329c7e'),
            (b'2847ba65bef63b79e1bb7ea32a32bf8bdd3a02ff0e236440bdc26ec79495de04',
             b'1790790fa9a8734e2565b08f73fb91469c43dbb15d90ade658f0fd7a1fca2380'),
            (rb'crm-sre-team\2.8.0-rc7', rb'crm-sre-team\2.8.0-rc8'),
            (b'Stop: local rc7 tag points elsewhere', b'Stop: local rc8 tag points elsewhere'),
            (b'Stop: rc7 cache directory missing', b'Stop: rc8 cache directory missing'),
            (b'Bootstrap is not the published rc7 commit', b'Bootstrap is not the published rc8 commit'),
        ]
        digests = [
            '7877fc9c7dc57630c77ecf095f1715227e76f06a893d98114c0cba97e1480451',
            '7b277ab212c0a50afe3ac235ce98b8798d29d8d757dc3e8b67c5aebf02df8300',
            'd96e61bd463e33b7be73a24ec6ffb1793871b792f184b35e9bb18655479f455e',
            'f767d9702ac866035311469069e86422035ae31286f0c6a5227073f20428a67c',
        ]
        self.assertEqual(len(original), 4)
        self.assertEqual(len(self.blocks), 4)
        for old, actual, digest, changed in zip(original, self.blocks, digests, [3, 3, 2, 4]):
            with self.subTest(digest=digest):
                old_lines, actual_lines = old.splitlines(), actual.splitlines()
                self.assertEqual(len(old_lines), len(actual_lines))
                self.assertEqual(sum(a != b for a, b in zip(old_lines, actual_lines)), changed)
                for before, after in replacements:
                    old = old.replace(before, after)
                self.assertEqual(actual, old)
                self.assertEqual(hashlib.sha256(actual).hexdigest(), digest)
                self.assertTrue(actual.isascii())
                for option in [b'-DevRoot', b'-HandoffRoot', b'-WorkBuddyRoot', b'-PythonExe', b'-RunPytest']:
                    self.assertNotIn(option, actual)
        fences = re.findall(rb'^```[^\n]*\n.*?^```\n', self.rc7, re.M | re.S)
        self.assertEqual(len(fences), 5)
        self.assertEqual(hashlib.sha256(b''.join(fences)).hexdigest(),
                         '179bf80a01349cb325348eb36eb1ee782670f477fdae8aa6ddbac96a3ddd51e2')

    def test_receipts_integrity_counts_and_scoped_handoff(self):
        messages = re.findall(rb'```text\n(.*?)\n```', self.section, re.S)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages, re.findall(rb'```text\n(.*?)\n```', self.rc7, re.S))
        self.assertEqual(hashlib.sha256(messages[0]).hexdigest(),
                         'ebb50a6f6e371f146c31fdbd34653710e3b74b17f8601ae1fd8e19c107b4391e')
        manifest = json.loads((ROOT / 'release-manifest.json').read_bytes())
        count = len(manifest['files'])
        self.assertEqual(count, 556)
        self.assertIn('settings.json', manifest['files'])
        for token in [f'{count - 1}/{count}, root settings.json missing (host-managed)',
                      f'{count}/{count}, root settings.json matches package',
                      '预期 rc5', '直接 UPDATE 到 rc8', '只做本节步骤 1～5',
                      'rc6、rc7 两节简单检查已被本节取代，不再执行', '不做本文 r7 的 ③～⑦', '不跑全套',
                      '普通 Windows PowerShell 5.1', '先带回原输出，不继续', '由用户正常退出 WorkBuddy',
                      'PLAN→展示计划→用户核对后输入一次 YES→APPLY', '②a PLAN 文件占用',
                      'ZIP 哈希不符或其他报错', '绝不点“删除”', '新建一个空文件夹并开新会话',
                      '显式选择 GLM-5.3-Flash', '不点“召唤”',
                      r'...\plugins\cache\my-experts\crm-sre-team\2.8.0-rc8\skills' + '\\',
                      'stability-director 与 bomc-alarm-readonly 两条 2.8.0-rc8 缓存路径', 'version 为 2.8.0-rc8',
                      'updater 实际只要求至少一条', '缺任一条，本次检查未完成',
                      '.workbuddy/memory/*', '.in_use/<进程号>', '只记名称和数量，不删',
                      'PASS_DECLARED_FILES_ONLY', 'host_acceptance=HUMAN_REVIEW_REQUIRED',
                      'SHA256SUMS', '插件 VERSION（应为 2.8.0-rc8）', '未运行的成员记 NOT_RUN',
                      '会话 ID 和本机路径只带回给 Claude，不写进仓库', '短会话默认不做',
                      '先带回版本号，再决定是否加', '用客户端“刷新”切回 rc5，再 VERIFY',
                      '不把 rc5 旧计划交给 rc8 更新器', '不覆盖旧备份']:
            self.assertIn(token, self.text)
        self.assertNotRegex(self.text, r'/Volumes/|/Users/|\b\d{1,3}(?:\.\d{1,3}){3}\b')
        self.assertNotRegex(self.text, r'\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b')

    def test_job_machine_checks_precede_bomc_configuration(self):
        gate = self.bomc.split('4. 在 Windows 上部署插件外 BOMC 配置之前，必须先完成', 1)[1]
        gate = gate.split('\n5. VERIFY', 1)[0]
        for token in ['挂起分配失败、超时、取消、领头结束、后代、venv 转发器与嵌套 Job',
                      '当前均为 NOT_RUN', '具体实测步骤待用户决定部署时另行准备',
                      '本次简单检查不建 bomc.json，不启动上游，不触及 Job 路径',
                      '全部通过后才用脚本新建插件外 bomc.json']:
            self.assertIn(token, gate)
        self.assertLess(self.bomc.index('必须先完成 Windows Job 实机项目'),
                        self.bomc.index('### 新建插件外配置'))
        for token in ['不并入“rc8 值班机简单检查', '配置只随 rc8 部署',
                      'code_sha256 = $CodeHash', 'skill_config 为可选输入',
                      '只在 Windows Job 实机项目、“真实输出形状核对”和“部署前补充核查”全部通过后']:
            self.assertIn(token, self.bomc)
        for token in ['bomc.json 本次不建', '按 BRC-8 停下并写明证据缺口', '必填 code_sha256',
                      '配置只随 rc8 部署', '守卫 VERSION 现为 2.8.0-rc8', '不设独立 VERSION 文件',
                      '简单检查不建 bomc.json，守卫不会启动上游，不触及 Job 路径',
                      '必须在 Windows 上部署 BOMC 配置之前先完成，当前均为 NOT_RUN']:
            self.assertIn(token, self.text)
        excluded = self.text.split('### 不在本次\n', 1)[1].split('\n### ', 1)[0]
        self.assertIn('bomc.json 必须填 skill_config', excluded)
        self.assertNotIn('skill_config 按真实技能凭据接口决定', excluded)


class ConfigurableRootTests(unittest.TestCase):
    """Static PS 5.1 contracts and executable embedded-verifier path checks."""
    @classmethod
    def setUpClass(cls):
        cls.text = decode_script(SCRIPT.read_bytes())
        cls.ns = {'__name__': 'root_validation_tests'}
        exec(compile(extracted_verifier(cls.text), '<embedded-verifier>', 'exec'), cls.ns)

    def test_ai_d_drive_defaults_equal_every_original_path(self):
        header = self.text.split("$ErrorActionPreference = 'Stop'", 1)[0]
        defaults = dict(re.findall(r"\[string\]\$(DevRoot|HandoffRoot) = '([^']+)'", header))
        profile = PureWindowsPath(r'C:\Users\AI')
        appdata = profile / 'AppData/Local'
        self.assertIn("GetFolderPath('UserProfile')) '.workbuddy'", header)
        self.assertIn(r"GetFolderPath('LocalApplicationData')) 'Programs\Python\Python312\python.exe'", header)
        host = profile / '.workbuddy'
        actual = {
            'dev': PureWindowsPath(defaults['DevRoot']),
            'handoff': PureWindowsPath(defaults['HandoffRoot']),
            'host': host,
            'market': host / 'plugins/marketplaces/my-experts',
            'cache': host / 'plugins/cache/my-experts/crm-sre-team',
            'projects': host / 'projects',
            'python': appdata / 'Programs/Python/Python312/python.exe',
        }
        expected = {
            'dev': r'D:\Dev', 'handoff': r'D:\crm-v36-handoff', 'host': r'C:\Users\AI\.workbuddy',
            'market': r'C:\Users\AI\.workbuddy\plugins\marketplaces\my-experts',
            'cache': r'C:\Users\AI\.workbuddy\plugins\cache\my-experts\crm-sre-team',
            'projects': r'C:\Users\AI\.workbuddy\projects',
            'python': r'C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe',
        }
        for name, value in expected.items():
            with self.subTest(path=name):
                self.assertEqual(str(actual[name]), value)
        self.assertNotIn(r'C:\Users\AI', self.text)
        for name in ('Prepare-InstallContext', 'Assert-PlanLayout', 'Show-RecentSessionMetadata', 'Collect-SessionEvidence'):
            self.assertIn('$WorkBuddyRoot', function_body(self.text, name))
        self.assertNotIn('D:/', extracted_verifier(self.text))

    def test_custom_root_normalization_and_invalid_windows_paths(self):
        normalize = self.ns['normalize_windows_root']
        for value, expected in [(r'E:\Ops\Dev\\', r'E:\Ops\Dev'),
                                (r'F:\handoff\stage', r'F:\handoff\stage'),
                                (r'C:\Users\Operator\.workbuddy', r'C:\Users\Operator\.workbuddy')]:
            with self.subTest(path=value):
                self.assertEqual(normalize(value), expected)
        for value in ['', 'relative', r'E:relative', r'\rooted', r'\\host\share',
                      r'\\?\E:\Dev', 'E:\\', r'E:\a\..\Dev', r'E:\Dev:stream',
                      r'E:\bad?root', r'E:\bad*root', r'E:\bad|root', 'E:\\bad.\\next', 'E:\\bad ']:
            with self.subTest(invalid=value), self.assertRaises(ValueError):
                normalize(value)

    def test_ps_roots_validated_before_all_modes_and_plan_roots_checked(self):
        validation = function_body(self.text, 'Get-ConfiguredRoot')
        for token in ('Get-InstallFullPath $Value', '[IO.DriveInfo]::new',
                      '[IO.DriveType]::Fixed', '[IO.DriveType]::Removable',
                      'Assert-NoInstallReparse $Full', "-PathType Container", 'throw'):
            self.assertIn(token, validation)
        initialized = function_body(self.text, 'Initialize-PathRoots')
        for name in ('DevRoot', 'HandoffRoot', 'WorkBuddyRoot'):
            self.assertIn('Get-ConfiguredRoot $' + name, initialized)
        self.assertIn('must not overlap WorkBuddyRoot', initialized)
        dispatch = self.text.rsplit('\ntry {', 1)[1]
        self.assertLess(dispatch.index('. Initialize-PathRoots'), dispatch.index('Get-NativeProgram'))
        self.assertLess(dispatch.index('. Initialize-PathRoots'), dispatch.index('Assert-UpdaterIdentity'))
        match = function_body(self.text, 'Assert-PathRootsMatch')
        self.assertIn('Assert-PathSetEqual', match)
        self.assertIn('Get-ConfiguredRoot $Recorded.$Key', match)
        self.assertIn('-ine $PathRoots.$Key', match)
        for name, field in [('Assert-PlanLayout', '$Document.path_roots'), ('Load-ExperimentSet', '$Set.path_roots')]:
            self.assertIn('Assert-PathRootsMatch ' + field, function_body(self.text, name))
        for name in ('Invoke-SwitchPlan', 'Invoke-OncallMode'):
            self.assertIn('path_roots=$PathRoots', function_body(self.text, name))
        command = function_body(self.text, 'Get-VerifyCommand')
        for token in ("@('DevRoot',$DevRoot)", "@('HandoffRoot',$Handoff)", "@('WorkBuddyRoot',$WorkBuddyRoot)"):
            self.assertIn(token, command)
        drill = function_body(self.text, 'Assert-InstallPaths')
        self.assertIn('-Parent) -ine $Handoff', drill)
        self.assertIn("'^drill-[A-Za-z0-9][A-Za-z0-9-]*$'", drill)
        self.assertIn('$Full.StartsWith($RealPrefix', drill)

    def test_experiment_recorded_roots_and_mismatch_stop_before_package_reads(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'], prefix='fix10-roots-') as directory:
            root = Path(directory).resolve()
            roots = dict(dev_root=str(root / 'dev'), handoff_root=str(root / 'handoff'),
                         workbuddy_root=str(root / 'host'))
            set_id = 'a' * 32
            artifacts = Path(roots['handoff_root']) / ('experiment-' + set_id)
            repo = Path(roots['dev_root']) / ('crm-oncall-' + set_id) / 'repo'
            document = dict(set_id=set_id, artifacts=str(artifacts), repo=str(repo),
                            zip=str(artifacts / 'release.zip'), path_roots=roots)
            path = artifacts / 'experiment-set.json'
            self.assertEqual(self.ns['set_layout'](document, path, roots)[:2], (artifacts, repo))
            for key in roots:
                with self.subTest(root=key):
                    changed = dict(roots, **{key: str(root / 'different')})
                    with self.assertRaisesRegex(ValueError, 'Roots differ'):
                        self.ns['set_layout'](document, path, changed)
                    tampered = dict(document, path_roots=changed)
                    with self.assertRaisesRegex(ValueError, 'Roots differ'):
                        self.ns['set_layout'](tampered, path, roots)
            for bad in (None, {}, dict(roots, extra='x'), dict(roots, dev_root='relative'),
                        dict(roots, handoff_root=str(root / '..' / 'escape'))):
                with self.subTest(invalid_roots=bad), self.assertRaises(ValueError):
                    self.ns['set_layout'](dict(document, path_roots=bad), path, roots)
            for field, value in [('artifacts', str(root / ('experiment-' + set_id))),
                                 ('repo', str(root / ('crm-oncall-' + set_id) / 'repo'))]:
                changed = dict(document, **{field: value})
                with self.subTest(layout=field), self.assertRaises(ValueError):
                    self.ns['set_layout'](changed, path, roots)


if __name__ == "__main__":
    unittest.main(verbosity=2)
