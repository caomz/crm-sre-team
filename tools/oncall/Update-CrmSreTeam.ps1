#requires -Version 5.1
# Approved design: pinned tag -> verified local clone -> offline checks -> hashed PLAN;
# UPDATE carries PLAN/hash in-process; optional synthetic DRILL; one YES -> APPLY.
# Git bootstrap checks HEAD, clean tree and raw script blob before any mode.
# PLAN uses that verified worktree as clone source; standalone uses GitHub.
# NEW ORCHESTRATION: NOT RUN ON WINDOWS. UTF-8 BOM preserves verbatim r2 text.
[CmdletBinding()]
param(
    [ValidateSet('PLAN','APPLY','VERIFY','ROLLBACK','DRILL','UPDATE')][string]$Mode = 'PLAN',
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')][string]$Tag,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedZipSha256,
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedScriptSha256,
    [string]$PlanPath,
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$PlanSha256,
    [string]$PythonExe = 'C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe',
    [string]$GitExe = 'git',
    [switch]$RunPytest,
    [switch]$Drill,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9-]*$')][string]$SessionId,
    [ValidatePattern('^agent-[A-Za-z0-9-]+$')][string]$AgentId
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Mode = $Mode.ToUpperInvariant()
$ExpectedCommit = $ExpectedCommit.ToLowerInvariant()
$ExpectedZipSha256 = $ExpectedZipSha256.ToLowerInvariant()
$RepoUrl = 'https://github.com/caomz/crm-sre-team.git'
$Handoff = 'D:\crm-v36-handoff'
$DevRoot = 'D:\Dev'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1 -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Use Windows PowerShell 5.1. New orchestration has NOT RUN ON WINDOWS.'
}

# R2-BEGIN Write-Utf8Lf
function Write-Utf8Lf([string]$Path, [string]$Text) {
    $Normalized = $Text.Replace("`r`n", "`n").Replace("`r", "`n")
    [IO.File]::WriteAllText($Path, $Normalized, [Text.UTF8Encoding]::new($false))
}
# R2-END Write-Utf8Lf

# R2-BEGIN Protect-Output
function Protect-Output([string]$Text) {
    $Text = [regex]::Replace($Text, '(?i)([A-Za-z][A-Za-z0-9+.-]*://)[^/\s<>"'']*@', '$1***@')
    $Text = [regex]::Replace($Text, '(?i)\b[^\s/@:]+@([A-Za-z0-9.-]+):', '***@$1:')
    $Text = [regex]::Replace($Text, '([?&][^=\s&<>"'']+=)[^&\s<>"'']+', '$1***')
    $Text = [regex]::Replace($Text, '(?i)(github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|glpat-[A-Za-z0-9_-]+)', '***')
    $Text = [regex]::Replace($Text, '([A-Za-z][A-Za-z0-9+.-]*://[^\s<>"'']*#)[^\s<>"'']*', '$1***')
    return $Text
}
# R2-END Protect-Output

# R2-BEGIN Get-ManifestHashes
function Get-ManifestHashes([string]$Root) {
    $Manifest = Get-Content -LiteralPath (Join-Path $Root 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $Names = @($Manifest.files)
    if ($Names.Count -ne @($Names | Sort-Object -Unique).Count) { throw 'manifest 重复' }
    $Hashes = @{}
    foreach ($Rel in $Names) {
        $FilePath = Join-Path $Root ($Rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) { throw "缺文件：$Rel" }
        $Hashes[$Rel] = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $Hashes
}
# R2-END Get-ManifestHashes

# R2-BEGIN Assert-HashesEqual
function Assert-HashesEqual($Before, $After) {
    if ($Before.Count -ne $After.Count) { throw '文件集合变了' }
    foreach ($Rel in $Before.Keys) {
        if (-not $After.ContainsKey($Rel) -or $Before[$Rel] -cne $After[$Rel]) { throw "字节差异：$Rel" }
    }
}
# R2-END Assert-HashesEqual

# R2-BEGIN Assert-PathSetEqual
function Assert-PathSetEqual($Expected, $Actual) {
    if (@($Expected).Count -ne @($Actual).Count -or @(Compare-Object -ReferenceObject @($Expected) -DifferenceObject @($Actual) -CaseSensitive).Count -ne 0) {
        throw '文件/差异集合不符'
    }
}
# R2-END Assert-PathSetEqual

# R2-BEGIN Get-PackageFiles
function Get-PackageFiles([string]$Root) {
    $Prefix = $Root.TrimEnd('\') + '\'
    return @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Prefix.Length).Replace('\','/') } | Sort-Object)
}
# R2-END Get-PackageFiles

# R2-BEGIN Get-InstallFullPath
function Get-InstallFullPath([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value -notmatch '^[A-Za-z]:\\' -or $Value.Substring(2).Contains(':')) { throw "路径必须为盘符绝对路径：$Value" }
    return [IO.Path]::GetFullPath($Value).TrimEnd('\')
}
# R2-END Get-InstallFullPath

# R2-BEGIN Assert-NoInstallReparse
function Assert-NoInstallReparse([string]$Value) {
    $Probe = $Value
    while ($Probe) {
        if (Test-Path -LiteralPath $Probe) {
            $Item = Get-Item -LiteralPath $Probe -Force -ErrorAction Stop
            if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "拒绝链接/junction：$Probe" }
        }
        $Parent = Split-Path -Path $Probe -Parent
        if ($Parent -eq $Probe) { break }
        $Probe = $Parent
    }
}
# R2-END Assert-NoInstallReparse

# R2-BEGIN Assert-InstallPaths
function Assert-InstallPaths([switch]$RequirePlan) {
    if (-not (Get-Variable -Name InstallMode -ErrorAction SilentlyContinue) -or $InstallMode -cnotin @('REAL','DRILL')) { throw '未设置有效安装模式' }
    if (-not (Get-Variable -Name InstallFault -ErrorAction SilentlyContinue) -or $InstallFault -cnotin @('NONE','COPY_FAILURE','VERIFY_FAILURE','MARKET_PARTIAL')) { throw '未设置有效故障模式' }
    $RealRoot = 'C:\Users\AI\.workbuddy'
    $RealPrefix = $RealRoot + '\'
    if ($InstallMode -ceq 'DRILL') {
        $BoundRoot = Get-InstallFullPath $DrillRoot
        if ($BoundRoot -notmatch '^D:\\crm-v36-handoff\\drill-[A-Za-z0-9][A-Za-z0-9-]*$') { throw '演练根必须是 D:\crm-v36-handoff\drill-<唯一编号>' }
    } else {
        if ($InstallFault -cne 'NONE') { throw 'REAL 禁止故障注入' }
        $BoundRoot = $RealRoot
    }
    $BoundPrefix = $BoundRoot + '\'
    # 逐一检查实际读写的七个路径，另把 cache 纳入同一边界。
    foreach ($PathName in @('MarketRoot','InstallSource','Marketplace','BackupRoot','OldSource','MarketplaceBackup','StatePath','CacheRoot')) {
        $Variable = Get-Variable -Name $PathName -ErrorAction SilentlyContinue
        if (-not $Variable) { throw "缺实际路径：$PathName" }
        $Full = Get-InstallFullPath ([string]$Variable.Value)
        if (-not $Full.StartsWith($BoundPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "$PathName 越过 $InstallMode 边界：$Full" }
        if ($InstallMode -ceq 'DRILL' -and ($Full -ieq $RealRoot -or $Full.StartsWith($RealPrefix, [StringComparison]::OrdinalIgnoreCase))) { throw "$PathName 指向真实 WorkBuddy 根" }
        Assert-NoInstallReparse $Full
        if ($RequirePlan) {
            if (-not $InstallPlan -or $Full -ine $InstallPlan.paths.$PathName) { throw "$PathName 与已审阅计划不符" }
        }
    }
    $FullPackage = Get-InstallFullPath $PackageRoot
    if ($InstallMode -ceq 'DRILL' -and -not $FullPackage.StartsWith($BoundPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw '演练候选包不在演练根内' }
    Assert-NoInstallReparse $FullPackage
    if ($RequirePlan) {
        if ($InstallMode -cne $InstallPlan.mode -or $InstallFault -cne $InstallPlan.fault -or $BoundRoot -ine $InstallPlan.bound_root -or $FullPackage -ine $InstallPlan.package) { throw '模式、故障参数或包来源自计划后变更' }
    }
}
# R2-END Assert-InstallPaths

# R2-BEGIN Get-SelectedPackageHashes
function Get-SelectedPackageHashes([string]$Root) {
    $Hashes = Get-ManifestHashes $Root
    foreach ($Extra in $InstallMetadataNames) {
        $Hashes[$Extra] = (Get-FileHash -LiteralPath (Join-Path $Root $Extra) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $Hashes
}
# R2-END Get-SelectedPackageHashes

# R2-BEGIN Invoke-IoRetry
function Invoke-IoRetry([scriptblock]$Action, [string]$What) {
    $Attempt = 0
    while ($true) {
        $Attempt++
        try { & $Action; return }
        catch {
            $Cause = $_.Exception
            if ($Cause -is [System.Management.Automation.MethodInvocationException] -and $Cause.InnerException) { $Cause = $Cause.InnerException }
            if (-not ($Cause -is [System.IO.IOException] -or $Cause -is [System.UnauthorizedAccessException]) -or $Attempt -ge 20) { throw }
            Write-Host "$What 遇到文件占用，250 毫秒后第 $Attempt 次重试：$($Cause.Message)"
            Start-Sleep -Milliseconds 250
        }
    }
}
# R2-END Invoke-IoRetry

# R2-BEGIN Save-InstallState
function Save-InstallState {
    if ($StatePath) {
        $State = [ordered]@{ install_plan=$InstallPlan; mode=$InstallMode; fault=$InstallFault; drill_root=$DrillRoot; market_root=$MarketRoot; marketplace=$Marketplace; old_source=$OldSource; marketplace_backup=$MarketplaceBackup; state_path=$StatePath; cache_root=$CacheRoot; label=$InstallLabel; version=$Version; stage=$InstallStage; source=$InstallSource; package=$PackageRoot; backup=$BackupRoot; move_started=$MoveStarted; old_source_moved=$OldSourceMoved; copy_started=$CopyStarted; copy_complete=$CopyComplete; source_verified=$SourceVerified; market_backup_complete=$MarketBackupComplete; market_write_started=$MarketWriteStarted; market_write_complete=$MarketWriteComplete; market_before_hash=$MarketBeforeHash; market_after_hash=$MarketAfterHash; market_failure_hash=$MarketFailureHash; market_failure_captured=$MarketFailureCaptured }
        $StateJson = ($State | ConvertTo-Json -Depth 10) + "`n"
        Invoke-IoRetry { Write-Utf8Lf $StatePath $StateJson } '安装状态写入'
    }
}
# R2-END Save-InstallState

# R2-BEGIN ReadShared
function ReadShared([string]$p) {
    $fs = [System.IO.File]::Open($p, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
    $ms = New-Object System.IO.MemoryStream
    try { $fs.CopyTo($ms); $b = $ms.ToArray() } finally { $ms.Dispose(); $fs.Dispose() }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = -join ($sha.ComputeHash($b) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
    [pscustomobject]@{ Bytes = $b; Text = [System.Text.Encoding]::UTF8.GetString($b); Sha = $h }
}
# R2-END ReadShared

# R2-BEGIN Assert-NoEvidenceReparse
function Assert-NoEvidenceReparse([string]$p) {
    $p = [System.IO.Path]::GetFullPath($p)
    while ($p) {
        if (Test-Path -LiteralPath $p) {
            if (((Get-Item -LiteralPath $p -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) { throw '证据路径含链接/junction，人工核对，不越界取证' }
        }
        $Parent = [System.IO.Path]::GetDirectoryName($p)
        if ($Parent -eq $p) { break }
        $p = $Parent
    }
}
# R2-END Assert-NoEvidenceReparse


# New helpers: NOT RUN ON WINDOWS. No credential or environment-content reads.
function Assert-Under([string]$Path, [string]$Root) {
    $Full = Get-InstallFullPath $Path
    $Bound = Get-InstallFullPath $Root
    if (-not $Full.StartsWith(($Bound + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside allowed root: $Full" }
    Assert-NoInstallReparse $Full
    return $Full
}
function Assert-TreeNoReparse([string]$Root) {
    Assert-NoInstallReparse $Root
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { throw "Directory missing: $Root" }
    $Pending = New-Object 'System.Collections.Generic.Queue[string]'
    $Pending.Enqueue($Root)
    while ($Pending.Count -gt 0) {
        $Directory = $Pending.Dequeue()
        foreach ($Item in @(Get-ChildItem -LiteralPath $Directory -Force)) {
            if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Tree contains link/junction: $($Item.FullName)" }
            if ($Item.PSIsContainer) { $Pending.Enqueue($Item.FullName) }
        }
    }
}
function New-SafeDirectory([string]$Path, [string]$Root) {
    $Full = Assert-Under $Path $Root
    if (Test-Path -LiteralPath $Full) { throw "Directory already exists; retained: $Full" }
    New-Item -ItemType Directory -Path $Full -ErrorAction Stop | Out-Null
}
function Get-DeclaredNames([string]$Root) {
    Assert-NoInstallReparse (Join-Path $Root 'release-manifest.json')
    $Manifest = Get-Content -LiteralPath (Join-Path $Root 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $Names = @($Manifest.files)
    if ($Manifest.schema_version -ne 1 -or $Names.Count -eq 0 -or $Names.Count -ne @($Names | Sort-Object -Unique).Count) { throw 'Invalid release manifest' }
    foreach ($Name in $Names) {
        if ($Name -isnot [string] -or $Name -notmatch '^[A-Za-z0-9._/-]+$' -or $Name -match '(^/|//|(^|/)\.\.?(/|$)|(^|/)(\.git|\.env[^/]*|credentials|id_rsa[^/]*|id_ed25519[^/]*)(/|$))') { throw 'Unsafe manifest path' }
        if ($Name -match '(^|/)(\.aws|\.ssh|\.codex|\.workbuddy)(/|$)' -or [IO.Path]::GetExtension($Name) -match '^\.(pem|key|p12|pfx)$') { throw 'Credential paths are not release inputs' }
        $null = Assert-Under (Join-Path $Root ($Name -replace '/', '\')) $Root
    }
    if ($Names -cnotcontains 'settings.json' -or $Names -cnotcontains 'VERSION') { throw 'Manifest missing required files' }
    return $Names
}
function ConvertTo-HashTable($Value) {
    $Table = @{}
    foreach ($Property in $Value.PSObject.Properties) {
        if ([string]$Property.Value -notmatch '^[0-9a-f]{64}$') { throw 'Invalid recorded file hash' }
        $Table[$Property.Name] = [string]$Property.Value
    }
    return $Table
}
function Write-NewJson([string]$Path, $Value) {
    Assert-NoInstallReparse $Path
    if (Test-Path -LiteralPath $Path) { throw "Report already exists: $Path" }
    Write-Utf8Lf $Path (($Value | ConvertTo-Json -Depth 100) + "`n")
}
function Invoke-Native([string]$Program, [string[]]$Arguments, [string]$Log, [string]$LogHeader = '') {
    if ($Log -and (Test-Path -LiteralPath $Log)) { throw 'Command log already exists' }
    $SavedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $global:LASTEXITCODE = $null
        $Captured = @(& $Program @Arguments 2>&1)
        $Code = $global:LASTEXITCODE
    } finally { $ErrorActionPreference = $SavedPreference }
    $Result = Protect-Output (($Captured | ForEach-Object { $_.ToString() }) -join "`n")
    if ($Log) {
        $LogText = $Result + "`n"
        if ($LogHeader) { $LogText = (Protect-Output $LogHeader) + "`n" + $LogText }
        Write-Utf8Lf $Log $LogText
    }
    if ($Code -ne 0) { throw "Native command failed (exit=$Code). See command log; no further steps executed." }
    return $Result.Trim()
}
function Get-NativeProgram([string]$Name) {
    $Program = @(Get-Command -Name $Name -CommandType Application -All -ErrorAction Stop)[0].Source
    if ($Program -like '*\WindowsApps\*' -or $Program -notlike '*.exe') { throw 'Use a real executable, not WindowsApps or a command wrapper' }
    Assert-NoInstallReparse $Program
    return $Program
}
function Assert-UpdaterIdentity {
    Assert-NoInstallReparse $PSCommandPath
    if ($ExpectedScriptSha256 -and (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash -ine $ExpectedScriptSha256) { throw 'Updater SHA256 does not match -ExpectedScriptSha256' }
    # A worktree may have a .git directory or a worktree .git file. Walk parents
    # by exact path only; do not read configuration/credential files ourselves.
    $Probe = Split-Path -Parent $PSCommandPath
    $WorkTree = $null
    while ($Probe) {
        Assert-NoInstallReparse $Probe
        if (Test-Path -LiteralPath (Join-Path $Probe '.git')) { $WorkTree = $Probe; break }
        $Parent = Split-Path -Parent $Probe
        if ($Parent -eq $Probe) { break }
        $Probe = $Parent
    }
    if (-not $WorkTree) { Write-Host 'Standalone updater; PLAN still binds it to the target tag script.'; return }
    $GitArgs = @('--no-optional-locks','-c','core.hooksPath=NUL','-C',$WorkTree)
    $Inside = Invoke-Native $Git ($GitArgs + @('rev-parse','--is-inside-work-tree')) $null
    $Head = Invoke-Native $Git ($GitArgs + @('rev-parse','HEAD')) $null
    $Dirty = Invoke-Native $Git ($GitArgs + @('status','--porcelain','--untracked-files=all','--ignore-submodules=none')) $null
    if ($Inside -cne 'true' -or $Head -cne $ExpectedCommit -or $Dirty) { throw 'Bootstrap HEAD mismatch or dirty worktree; stop before PLAN/APPLY' }
    $Relative = $PSCommandPath.Substring($WorkTree.TrimEnd('\').Length + 1).Replace('\','/')
    $CommitBlob = Invoke-Native $Git ($GitArgs + @('rev-parse',($ExpectedCommit + ':' + $Relative))) $null
    $DiskBlob = Invoke-Native $Git ($GitArgs + @('hash-object','--no-filters','--',$PSCommandPath)) $null
    if ($CommitBlob -cne $DiskBlob) { throw 'Raw updater bytes differ from the committed script blob' }
    Write-Host "Bootstrap verified: HEAD=$Head; clean worktree; script blob=$DiskBlob"
    return $WorkTree
}
function Assert-ClientStopped {
    if (Get-Process -Name 'WorkBuddy*','CodeBuddy*' -ErrorAction SilentlyContinue) { throw 'Exit WorkBuddy/CodeBuddy yourself; no process is killed.' }
}
function Get-SourceSnapshot([string]$Root) {
    Assert-TreeNoReparse $Root
    $Names = @(Get-DeclaredNames $Root)
    $Hashes = @{}
    $Missing = @()
    foreach ($Rel in $Names) {
        $FilePath = Join-Path $Root ($Rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
            if ($Rel -ceq 'settings.json' -and -not (Test-Path -LiteralPath $FilePath)) { $Missing += $Rel; continue }
            throw "Old source missing declared file: $Rel"
        }
        $Hashes[$Rel] = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return [pscustomobject]@{ version=([IO.File]::ReadAllText((Join-Path $Root 'VERSION'), $Utf8NoBom).Trim()); hashes=$Hashes; missing=$Missing }
}
function Assert-OldSource([string]$Root, $Snapshot) {
    $Actual = Get-SourceSnapshot $Root
    if ($Actual.version -cne $Snapshot.version -or (@($Actual.missing) -join '|') -cne (@($Snapshot.missing) -join '|')) { throw 'Old source changed since PLAN; preserve evidence and stop' }
    Assert-HashesEqual (ConvertTo-HashTable $Snapshot.hashes) $Actual.hashes
}
function Assert-MarketEntry {
    if ($Entries.Count -ne 1 -or $Entries[0].name -cne 'crm-sre-team' -or $Entries[0].source -isnot [string]) { throw 'Marketplace structure needs human review' }
    $EntryPath = [string]$Entries[0].source
    if ($EntryPath -notmatch '^[A-Za-z]:\\') { $EntryPath = Join-Path $MarketRoot $EntryPath }
    if ((Get-InstallFullPath $EntryPath) -ine (Get-InstallFullPath $InstallSource)) { throw 'Marketplace source does not resolve to the fixed install source' }
    if ($Entries[0].PSObject.Properties.Name -notcontains 'version') { throw 'Marketplace entry needs an explicit version field; human review required' }
}
function Test-InstalledDeclaredFiles([string]$Root, [string]$Label) {
    # r2 block 21 semantics, manifest-derived count. NOT RUN ON WINDOWS.
    Assert-TreeNoReparse $Root
    $DeclaredNames = @($PackageHashes.Keys)
    $Total = @($InstallExpectedNames).Count
    Assert-PathSetEqual $InstallExpectedNames $DeclaredNames
    $Matched = 0
    $MissingSettings = $false
    foreach ($Rel in $DeclaredNames) {
        $FilePath = Join-Path $Root ($Rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
            if ($Rel -ceq 'settings.json' -and -not (Test-Path -LiteralPath $FilePath)) { $MissingSettings = $true; continue }
            throw "$Label missing declared file or not a file: $Rel"
        }
        $Actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($Actual -cne $PackageHashes[$Rel]) { throw "$Label byte mismatch: $Rel" }
        $Matched++
    }
    $ExtraPaths = @(Get-PackageFiles $Root | Where-Object { $DeclaredNames -cnotcontains $_ })
    if ($MissingSettings) { $Integrity = "$Matched/$Total, root settings.json missing (host-managed)" }
    else { $Integrity = "$Matched/$Total, root settings.json matches package" }
    Write-Host "$Label : $Integrity"
    foreach ($Extra in $ExtraPaths) { Write-Host "$Label extra path (human review): $Extra" }
    return [pscustomobject]@{ root=$Root; integrity=$Integrity; declared_matched=$Matched; declared_total=$Total; missing_root_settings=$MissingSettings; extra_paths=$ExtraPaths }
}
function Assert-Package {
    Assert-TreeNoReparse $PackageRoot
    Assert-PathSetEqual $InstallExpectedNames @(Get-DeclaredNames $PackageRoot)
    Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $PackageRoot)
    Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $PackageRoot)
    if ([IO.File]::ReadAllText((Join-Path $PackageRoot 'VERSION'), $Utf8NoBom).Trim() -cne $Version) { throw 'Package version changed' }
}
function Confirm-Yes([string]$Action) {
    Write-Host $Action
    if ((Read-Host 'Type YES to confirm the displayed plan') -cne 'YES') { throw 'Confirmation refused; no installation writes performed' }
}
function Assert-PlanLayout($Document) {
    if ($Document.schema -cne 'crm-oncall-plan/v1' -or $Document.tag -cne $Tag -or $Document.commit -cne $ExpectedCommit -or $Document.zip_sha256 -cne $ExpectedZipSha256) { throw 'PLAN does not match release inputs' }
    if ($Document.run_id -notmatch '^[0-9a-f]{32}$' -or $Document.version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$') { throw 'Invalid PLAN identifier or version' }
    $WantArtifacts = Join-Path $Handoff ('update-' + $Document.run_id)
    if ((Get-InstallFullPath $Document.artifacts) -ine $WantArtifacts -or (Get-InstallFullPath $PlanPath) -ine (Join-Path $WantArtifacts 'install-plan.json')) { throw 'PLAN must be in its unique handoff directory' }
    $null = Assert-Under $Document.artifacts $Handoff
    $WantRepo = Join-Path $DevRoot ('crm-oncall-' + $Document.run_id + '\repo')
    if ((Get-InstallFullPath $Document.repo) -ine $WantRepo) { throw 'Unexpected clone path' }
    $null = Assert-Under $Document.repo $DevRoot
    $WantPackage = Join-Path $WantArtifacts 'install-clean\crm-sre-team'
    $IP = $Document.install_plan
    if ($IP.mode -cne 'REAL' -or $IP.fault -cne 'NONE' -or $IP.bound_root -cne 'C:\Users\AI\.workbuddy' -or (Get-InstallFullPath $IP.package) -ine $WantPackage) { throw 'Unexpected install mode or package path' }
    $MR = 'C:\Users\AI\.workbuddy\plugins\marketplaces\my-experts'
    $BR = Join-Path $MR ('backups\crm-v36-' + $Document.run_id + '-oncall')
    $Want = [ordered]@{ MarketRoot=$MR; InstallSource=(Join-Path $MR 'plugins\crm-sre-team'); Marketplace=(Join-Path $MR '.codebuddy-plugin\marketplace.json'); BackupRoot=$BR; OldSource=(Join-Path $BR 'install-source'); MarketplaceBackup=(Join-Path $BR 'marketplace.json'); StatePath=(Join-Path $BR 'install-state.json'); CacheRoot='C:\Users\AI\.workbuddy\plugins\cache\my-experts\crm-sre-team' }
    foreach ($Key in $Want.Keys) {
        if ((Get-InstallFullPath $IP.paths.$Key) -ine $Want[$Key]) { throw "Unexpected planned path: $Key" }
        if ($Mode -cne 'DRILL') { Assert-NoInstallReparse $Want[$Key] }
    }
    if ($Document.script_sha256 -ine (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash) { throw 'Updater changed since PLAN; use the same script' }
    if ($Document.market_before_hash -notmatch '^[0-9A-F]{64}$') { throw 'Invalid marketplace hash in PLAN' }
}
function Load-Plan {
    if (-not $PlanPath -or -not $PlanSha256) { throw 'This mode requires -PlanPath and -PlanSha256 from PLAN' }
    $null = Assert-Under $PlanPath $Handoff
    $Read = ReadShared $PlanPath
    if ($Read.Sha -ine $PlanSha256) { throw 'PLAN SHA256 mismatch; refuse all installation writes' }
    $Document = $Read.Text | ConvertFrom-Json
    Assert-PlanLayout $Document
    return $Document
}
function Import-PlanContext($Document) {
    # Dot-source this function: keep original r2 variables in the caller scope.
    $InstallMode = 'REAL'
    $InstallFault = 'NONE'
    $DrillRoot = $null
    $RunId = $Document.run_id
    $Artifacts = $Document.artifacts
    $Version = $Document.version
    $Repo = $Document.repo
    $ReleaseZip = Join-Path $Artifacts 'release.zip'
    $InstallLabel = 'oncall'
    $InstallPlan = $Document.install_plan
    $PackageRoot = $InstallPlan.package
    foreach ($Key in @('MarketRoot','InstallSource','Marketplace','BackupRoot','OldSource','MarketplaceBackup','StatePath','CacheRoot')) { Set-Variable -Name $Key -Value $InstallPlan.paths.$Key }
    $MarketBeforeHash = $Document.market_before_hash
    $InstallMetadataNames = @()
    $InstallExpectedNames = @($Document.expected_names)
    $PackageHashes = ConvertTo-HashTable $Document.package_hashes
    Assert-InstallPaths -RequirePlan
}
function Import-InstallState {
    Assert-InstallPaths -RequirePlan
    $StateRead = ReadShared $StatePath
    $State = $StateRead.Text | ConvertFrom-Json
    if (($State.install_plan | ConvertTo-Json -Depth 20 -Compress) -cne ($InstallPlan | ConvertTo-Json -Depth 20 -Compress)) { throw 'Installation state belongs to a different PLAN' }
    foreach ($Pair in @(@('mode',$InstallMode),@('fault',$InstallFault),@('label',$InstallLabel),@('version',$Version),@('market_before_hash',$MarketBeforeHash),@('market_root',$MarketRoot),@('marketplace',$Marketplace),@('old_source',$OldSource),@('marketplace_backup',$MarketplaceBackup),@('state_path',$StatePath),@('cache_root',$CacheRoot),@('source',$InstallSource),@('package',$PackageRoot),@('backup',$BackupRoot))) {
        if ([string]$State.($Pair[0]) -cne [string]$Pair[1]) { throw 'State metadata does not match PLAN' }
    }
    $InstallStage = [string]$State.stage
    if ($InstallStage -cnotin @('PLANNED','MARKET_BACKUP','SOURCE_MOVE','COPY','VERIFY','MARKET_WRITE','INSTALLED','ROLLED_BACK')) { throw 'Unknown installation stage' }
    foreach ($Pair in @(@('MoveStarted','move_started'),@('OldSourceMoved','old_source_moved'),@('CopyStarted','copy_started'),@('CopyComplete','copy_complete'),@('SourceVerified','source_verified'),@('MarketBackupComplete','market_backup_complete'),@('MarketWriteStarted','market_write_started'),@('MarketWriteComplete','market_write_complete'),@('MarketFailureCaptured','market_failure_captured'))) {
        $Value = $State.($Pair[1])
        if ($Value -isnot [bool]) { throw 'Invalid state flag' }
        Set-Variable -Name $Pair[0] -Value $Value
    }
    $MarketAfterHash = $State.market_after_hash
    $MarketFailureHash = $State.market_failure_hash
    foreach ($Hash in @($MarketAfterHash,$MarketFailureHash)) { if ($Hash -and $Hash -notmatch '^[0-9A-F]{64}$') { throw 'Invalid state marketplace hash' } }
}
function Initialize-Stages {
    $InstallStage = 'PLANNED'
    foreach ($Key in @('MoveStarted','OldSourceMoved','CopyStarted','CopyComplete','SourceVerified','MarketBackupComplete','MarketWriteStarted','MarketWriteComplete','MarketFailureCaptured')) { Set-Variable -Name $Key -Value $false }
    $MarketAfterHash = $null
    $MarketFailureHash = $null
}
function Prepare-InstallContext {
    # Path construction and PLAN finalization from r2 block 19.
    $InstallLabel = 'oncall'
    $InstallFault = 'NONE'
    $InstallPlan = $null
    . Initialize-Stages
    if ($InstallMode -ceq 'DRILL') {
        $MarketRoot = Join-Path $DrillRoot 'my-experts'
        $CacheRoot = Join-Path $DrillRoot 'cache\my-experts\crm-sre-team'
        $PackageRoot = Join-Path $DrillRoot 'candidate'
    } else {
        $MarketRoot = 'C:\Users\AI\.workbuddy\plugins\marketplaces\my-experts'
        $CacheRoot = 'C:\Users\AI\.workbuddy\plugins\cache\my-experts\crm-sre-team'
    }
    $InstallSource = Join-Path $MarketRoot 'plugins\crm-sre-team'
    $Marketplace = Join-Path $MarketRoot '.codebuddy-plugin\marketplace.json'
    $BackupRoot = Join-Path $MarketRoot ("backups\crm-v36-$RunId-$InstallLabel")
    $OldSource = Join-Path $BackupRoot 'install-source'
    $MarketplaceBackup = Join-Path $BackupRoot 'marketplace.json'
    $StatePath = Join-Path $BackupRoot 'install-state.json'
    Assert-InstallPaths
    if (Test-Path -LiteralPath $BackupRoot) { throw 'Backup already exists; choose a new PLAN' }
    $InstallMetadataNames = @()
    $InstallExpectedNames = @(Get-DeclaredNames $PackageRoot)
    Assert-TreeNoReparse $PackageRoot
    $PackageHashes = Get-SelectedPackageHashes $PackageRoot
    Assert-Package
    $MarketBeforeHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash
    $MarketData = Get-Content -LiteralPath $Marketplace -Raw -Encoding UTF8 | ConvertFrom-Json
    $Entries = @($MarketData.plugins | Where-Object { $_.name -eq 'crm-sre-team' })
    Assert-MarketEntry
    $PlannedPaths = [ordered]@{}
    foreach ($PathName in @('MarketRoot','InstallSource','Marketplace','BackupRoot','OldSource','MarketplaceBackup','StatePath','CacheRoot')) {
        $PlannedPaths[$PathName] = Get-InstallFullPath ([string](Get-Variable -Name $PathName -ValueOnly))
    }
    $BoundRoot = 'C:\Users\AI\.workbuddy'
    if ($InstallMode -ceq 'DRILL') { $BoundRoot = Get-InstallFullPath $DrillRoot }
    $InstallPlan = [pscustomobject]@{ mode=$InstallMode; fault=$InstallFault; bound_root=$BoundRoot; package=(Get-InstallFullPath $PackageRoot); paths=[pscustomobject]$PlannedPaths }
}
function Assert-CloneIdentity([switch]$AfterChecks) {
    $Head = Invoke-Native $Git @('-C',$Repo,'rev-parse','HEAD') $null
    $TagCommit = Invoke-Native $Git @('-C',$Repo,'rev-parse',('refs/tags/' + $Tag + '^{commit}')) $null
    $StatusArgs = @('-C',$Repo,'status','--porcelain','--untracked-files=all','--ignore-submodules=none')
    if ($AfterChecks) {
        # Host capabilities change generated reports; exclude only exact declared reports.
        $Manifest = Get-Content -LiteralPath (Join-Path $Repo 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $StatusArgs += @('--','.')
        foreach ($Report in @($Manifest.excluded_generated_reports)) {
            if ($Report -isnot [string] -or $Report -notmatch '^tests/[A-Za-z0-9][A-Za-z0-9._-]*\.(json|txt)$' -or $Manifest.files -contains $Report) { throw 'Invalid generated report allowlist' }
            $StatusArgs += (':(top,literal,exclude)' + $Report)
        }
    }
    $Dirty = Invoke-Native $Git $StatusArgs $null
    if ($Head -cne $ExpectedCommit -or $TagCommit -cne $ExpectedCommit -or $Dirty) { throw 'Tag/HEAD mismatch or dirty clone' }
}
function Test-SuccessfulDrill {
    # Only immediate drill-* directories and their exact report/state paths.
    Assert-NoInstallReparse $Handoff
    if (-not (Test-Path -LiteralPath $Handoff -PathType Container)) { return $false }
    foreach ($Directory in @(Get-ChildItem -LiteralPath $Handoff -Directory -Filter 'drill-*' -Force)) {
        if ($Directory.Name -notmatch '^drill-[A-Za-z0-9][A-Za-z0-9-]*$') { continue }
        $null = Assert-Under $Directory.FullName $Handoff
        $ReportPath = Join-Path $Directory.FullName 'drill-report.json'
        Assert-NoInstallReparse $ReportPath
        if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) { continue }
        $Report = (ReadShared $ReportPath).Text | ConvertFrom-Json
        if ($Report.status -cne 'PASS_APPLY_ROLLBACK_ONLY' -or $Report.real_host -cne 'NOT_ACCESSED_BY_DRILL' -or (Get-InstallFullPath $Report.root) -ine $Directory.FullName) { continue }
        $null = Assert-Under $Report.state $Directory.FullName
        $DrillState = (ReadShared $Report.state).Text | ConvertFrom-Json
        if ($DrillState.mode -ceq 'DRILL' -and $DrillState.fault -ceq 'NONE' -and $DrillState.stage -ceq 'ROLLED_BACK') {
            Write-Host "Previous successful DRILL: $ReportPath"
            return $true
        }
    }
    return $false
}
function Quote-PowerShellArgument([string]$Value) { return "'" + $Value.Replace("'","''") + "'" }
function Get-VerifyCommand([string]$SelectedSessionId) {
    $Command = 'powershell -NoProfile -ExecutionPolicy Bypass -File ' + (Quote-PowerShellArgument $PSCommandPath) + ' -Mode VERIFY'
    foreach ($Pair in @(@('Tag',$Tag),@('ExpectedCommit',$ExpectedCommit),@('ExpectedZipSha256',$ExpectedZipSha256),@('PlanPath',$PlanPath),@('PlanSha256',$PlanSha256),@('GitExe',$Git))) {
        $Command += ' -' + $Pair[0] + ' ' + (Quote-PowerShellArgument ([string]$Pair[1]))
    }
    if ($ExpectedScriptSha256) { $Command += ' -ExpectedScriptSha256 ' + (Quote-PowerShellArgument $ExpectedScriptSha256) }
    if ($SelectedSessionId) { $Command += ' -SessionId ' + (Quote-PowerShellArgument $SelectedSessionId) }
    return $Command
}
function Get-ApplyCompletedUtc {
    $ApplyReportPath = Join-Path $Artifacts 'apply-report.json'
    $null = Assert-Under $ApplyReportPath $Handoff
    $ApplyReport = (ReadShared $ApplyReportPath).Text | ConvertFrom-Json
    if ($ApplyReport.status -cne 'INSTALLED' -or $ApplyReport.version -cne $Version -or $ApplyReport.plan_sha256 -ine $PlanSha256 -or $ApplyReport.state -ine $StatePath -or -not $ApplyReport.completed_utc) { throw 'APPLY completion report missing or does not match this PLAN' }
    return [DateTime]::ParseExact([string]$ApplyReport.completed_utc, 'o', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
}
function Show-RecentSessionMetadata([DateTime]$CompletedUtc) {
    # Exactly projects -> project -> main *.jsonl; no recursion/content reads.
    $Projects = 'C:\Users\AI\.workbuddy\projects'
    Assert-NoEvidenceReparse $Projects
    if (-not (Test-Path -LiteralPath $Projects -PathType Container)) { throw 'Projects root missing' }
    $Candidates = @()
    foreach ($Project in @(Get-ChildItem -LiteralPath $Projects -Directory -Force)) {
        if (($Project.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Write-Host "Skip project junction: $($Project.FullName)"; continue }
        Assert-NoEvidenceReparse $Project.FullName
        foreach ($Lead in @(Get-ChildItem -LiteralPath $Project.FullName -File -Filter '*.jsonl' -Force)) {
            if (($Lead.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Write-Host "Skip record link: $($Lead.FullName)"; continue }
            Assert-NoEvidenceReparse $Lead.FullName
            if ($Lead.BaseName -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$' -or $Lead.LastWriteTimeUtc -le $CompletedUtc) { continue }
            $Candidates += [pscustomobject]@{ session_id=$Lead.BaseName; size_bytes=$Lead.Length; created_utc=$Lead.CreationTimeUtc.ToString('o'); modified_utc=$Lead.LastWriteTimeUtc.ToString('o'); project=$Project.Name }
        }
    }
    Write-Host "SESSION_SELECTION_REQUIRED. Main records modified after APPLY $($CompletedUtc.ToString('o')):"
    foreach ($Candidate in @($Candidates | Sort-Object modified_utc -Descending)) {
        Write-Host "SessionId=$($Candidate.session_id); Size=$($Candidate.size_bytes); CreatedUtc=$($Candidate.created_utc); ModifiedUtc=$($Candidate.modified_utc); Project=$($Candidate.project)"
        Write-Host (Get-VerifyCommand $Candidate.session_id)
    }
    if ($Candidates.Count -eq 0) { Write-Host 'No recent main session records. Open a NEW client session, paste Self-check 1, then rerun the printed VERIFY command.'; Write-Host (Get-VerifyCommand) }
    Write-Host 'Select the Self-check 1 SessionId and rerun VERIFY. No session contents were read; verification/evidence is pending. Omit AgentId for a leader-only session.'
}
function Get-ToolNodes($Record) {
    # Walk parsed JSON objects, never filesystem paths or prompt JSON strings.
    $Pending = New-Object 'System.Collections.Generic.Queue[object]'
    $Pending.Enqueue($Record)
    while ($Pending.Count -gt 0) {
        $Node = $Pending.Dequeue()
        if ($null -eq $Node -or $Node -is [string] -or $Node -is [ValueType]) { continue }
        if ($Node -is [Array]) { foreach ($Child in $Node) { $Pending.Enqueue($Child) }; continue }
        if ($Node.type -cin @('function_call','function_call_result')) { Write-Output $Node }
        foreach ($Property in $Node.PSObject.Properties) { $Pending.Enqueue($Property.Value) }
    }
}
function Collect-SessionEvidence {
    # Fixed two-level location and shared-read snapshots from r2 block 26.
    # Receipt correlation added here: NOT RUN ON WINDOWS.
    $Projects = 'C:\Users\AI\.workbuddy\projects'
    Assert-NoEvidenceReparse $Projects
    if (-not (Test-Path -LiteralPath $Projects -PathType Container)) { throw 'Projects root missing' }
    $HasSessionId = -not [string]::IsNullOrWhiteSpace($SessionId)
    $HasAgentId = -not [string]::IsNullOrWhiteSpace($AgentId)
    $Located = @()
    foreach ($Project in @(Get-ChildItem -LiteralPath $Projects -Directory -Force)) {
        if (($Project.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Write-Host "Skip project junction: $($Project.FullName)"; continue }
        Assert-NoEvidenceReparse $Project.FullName
        if (-not $HasAgentId) {
            $LeadPath = Join-Path $Project.FullName ($SessionId + '.jsonl')
            Assert-NoEvidenceReparse $LeadPath
            if (Test-Path -LiteralPath $LeadPath -PathType Leaf) { $Located += @{ SessionId=$SessionId; Lead=$LeadPath; Member=$null } }
            continue
        }
        foreach ($Session in @(Get-ChildItem -LiteralPath $Project.FullName -Directory -Force)) {
            if (($Session.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Write-Host "Skip session junction: $($Session.FullName)"; continue }
            Assert-NoEvidenceReparse $Session.FullName
            $MemberPath = Join-Path $Session.FullName ('subagents\' + $AgentId + '.jsonl')
            Assert-NoEvidenceReparse $MemberPath
            if (Test-Path -LiteralPath $MemberPath -PathType Leaf) { $Located += @{ SessionId=$Session.Name; Lead=(Join-Path $Project.FullName ($Session.Name + '.jsonl')); Member=$MemberPath } }
        }
    }
    if ($Located.Count -ne 1) { throw 'Session location must be unique; no recursive search or guessed paths' }
    if ($Located[0].SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$' -or ($HasSessionId -and $SessionId -cne $Located[0].SessionId)) { throw 'SessionId does not match member parent directory' }
    $Files = @(@{ Name=('lead-' + $Located[0].SessionId + '.jsonl'); Path=$Located[0].Lead })
    if ($HasAgentId) { $Files += @{ Name=('member-' + $AgentId + '.jsonl'); Path=$Located[0].Member } }
    $Snapshots = @()
    foreach ($File in $Files) {
        Assert-NoEvidenceReparse $File.Path
        $Read = ReadShared $File.Path
        if ($Read.Bytes.Length -eq 0) { throw 'Empty session record' }
        $Snapshots += @{ File=$File; Data=$Read }
    }
    $EvidenceRoot = Join-Path $Artifacts ('raw-evidence-' + [guid]::NewGuid().ToString('N'))
    New-SafeDirectory $EvidenceRoot $Handoff
    $Sums = ''
    $ReceiptPaths = @()
    foreach ($Snapshot in $Snapshots) {
        $Destination = Join-Path $EvidenceRoot $Snapshot.File.Name
        [IO.File]::WriteAllBytes($Destination, $Snapshot.Data.Bytes)
        if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ine $Snapshot.Data.Sha) { throw 'Evidence copy hash mismatch' }
        $Sums += $Snapshot.Data.Sha + '  ' + $Snapshot.File.Name + "`n"
    }
    Write-Utf8Lf (Join-Path $EvidenceRoot 'SHA256SUMS') $Sums
    foreach ($Snapshot in $Snapshots) {
        $SkillIds = [System.Collections.Hashtable]::new([StringComparer]::Ordinal)
        foreach ($Line in ($Snapshot.Data.Text -split "`n")) {
            if ([string]::IsNullOrWhiteSpace($Line)) { continue }
            try { $Record = $Line | ConvertFrom-Json } catch { throw 'Invalid/truncated JSONL; snapshots retained for human review' }
            foreach ($ToolNode in @(Get-ToolNodes $Record)) {
                if ($ToolNode.type -ceq 'function_call' -and $ToolNode.name -ceq 'Skill' -and $ToolNode.callId) { $SkillIds[[string]$ToolNode.callId] = $true }
                if ($ToolNode.type -ceq 'function_call_result' -and $SkillIds.ContainsKey([string]$ToolNode.callId) -and -not $ToolNode.is_error) {
                    $ReceiptText = ($ToolNode | ConvertTo-Json -Depth 100)
                    # Decode JSON escaped backslashes until path separators are single.
                    while ($ReceiptText.Contains('\\')) { $ReceiptText = $ReceiptText.Replace('\\','\') }
                    $Needle = (Join-Path $CacheRoot ($Version + '\skills\')).Replace('\','/')
                    $Normalized = $ReceiptText.Replace('\','/')
                    $Hits = [regex]::Matches($Normalized, ([regex]::Escape($Needle) + '[A-Za-z0-9-]+'))
                    foreach ($Hit in $Hits) { $ReceiptPaths += $Hit.Value }
                }
            }
        }
    }
    if ($ReceiptPaths.Count -eq 0) { throw 'No correlated Skill receipt contains the target cache version; evidence retained, host acceptance incomplete' }
    Write-NewJson (Join-Path $EvidenceRoot 'skill-receipts.json') ([ordered]@{ session_id=$Located[0].SessionId; version=$Version; paths=@($ReceiptPaths | Sort-Object -Unique); scope='SKILL_RECEIPT_PATH_NOT_AGENT_BODY_PROOF' })
    Write-Host "Evidence: $EvidenceRoot; Skill receipt target version verified; Agent body loading is not proved."
    return $EvidenceRoot
}

# Main orchestration. No system ExecutionPolicy change, install, push, or deletion.
function Invoke-OncallMode([string]$Mode, [switch]$FromUpdate) {
    if ($Mode -ceq 'PLAN') {
        if ($PlanPath -or $PlanSha256 -or $SessionId -or $AgentId) { throw 'PLAN creates a new plan; do not pass an existing plan or session ID' }
        $RunId = [guid]::NewGuid().ToString('N')
        # build_bundle stages in root.parent: reserve that whole new workspace.
        $CloneRoot = Join-Path $DevRoot ('crm-oncall-' + $RunId)
        $Repo = Join-Path $CloneRoot 'repo'
        $Artifacts = Join-Path $Handoff ('update-' + $RunId)
        if ($PythonExe -ceq 'C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe' -and -not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Default Python312 python.exe is missing; pass -PythonExe with the verified real interpreter path.' }
        $Python = Get-NativeProgram $PythonExe
        $null = Assert-Under $Repo $DevRoot
        $null = Assert-Under $Artifacts $Handoff
        if ((Test-Path -LiteralPath $CloneRoot) -or (Test-Path -LiteralPath $Artifacts)) { throw 'New clone/artifact path already exists' }
        New-SafeDirectory $CloneRoot $DevRoot
        New-SafeDirectory $Artifacts $Handoff
        $TaskTemp = Join-Path $Artifacts 'temp'
        New-SafeDirectory $TaskTemp $Handoff
        $env:TEMP = $TaskTemp
        $env:TMP = $TaskTemp
        $env:TMPDIR = $TaskTemp
        $env:PYTHONUTF8 = '1'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        # The verified bootstrap supplies local objects; standalone uses GitHub.
        if ($VerifiedWorkTree) { $CloneSource = $VerifiedWorkTree }
        else { $CloneSource = $RepoUrl }
        $CloneSourceMessage = 'Clone source: ' + $CloneSource
        Write-Host (Protect-Output $CloneSourceMessage)
        $null = Invoke-Native $Git @('-c','credential.helper=','-c','credential.interactive=never','-c','core.askPass=','-c','http.extraHeader=','-c','core.hooksPath=NUL','clone','--no-local','--config','core.autocrlf=false','--config','core.hooksPath=NUL','--branch',$Tag,'--single-branch',$CloneSource,$Repo) (Join-Path $Artifacts 'clone.txt') $CloneSourceMessage
        Assert-CloneIdentity
        $null = Get-DeclaredNames $Repo
        $Version = [IO.File]::ReadAllText((Join-Path $Repo 'VERSION'), $Utf8NoBom).Trim()
        if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$') { throw 'Invalid release VERSION' }
        if ((Get-FileHash -LiteralPath (Join-Path $Repo 'tools\oncall\Update-CrmSreTeam.ps1') -Algorithm SHA256).Hash -ine (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash) { throw 'Use the updater from this tag, not a different release' }
        Push-Location -LiteralPath $Repo
        try {
            $Before = Get-ManifestHashes $Repo
            $null = Invoke-Native $Python @('-c','import sys; assert sys.version_info >= (3,10)') (Join-Path $Artifacts 'python.txt')
            $null = Invoke-Native $Python @('tools/build_bundle.py') (Join-Path $Artifacts 'build.txt')
            Assert-HashesEqual $Before (Get-ManifestHashes $Repo)
            $null = Invoke-Native $Python @('tools/check_workbuddy.py') (Join-Path $Artifacts 'check-workbuddy.txt')
            $null = Invoke-Native $Python @('tools/validate_bundle.py') (Join-Path $Artifacts 'validate-bundle.txt')
            if ($RunPytest) {
                $null = Invoke-Native $Python @('-m','pytest','tests/','-q') (Join-Path $Artifacts 'pytest.txt')
                $null = Invoke-Native $Python @('-m','pytest','tools/oncall/test_oncall_updater.py','-q') (Join-Path $Artifacts 'pytest-oncall.txt')
            }
            $ReleaseZip = Join-Path $Artifacts 'release.zip'
            $null = Invoke-Native $Python @('tools/build_release.py','--output',$ReleaseZip) (Join-Path $Artifacts 'build-release.txt')
            if ((Get-FileHash -LiteralPath $ReleaseZip -Algorithm SHA256).Hash -ine $ExpectedZipSha256) { throw 'Rebuilt ZIP differs from Mac release SHA256' }
            $null = Invoke-Native $Python @('tools/validate_release.py','--zip',$ReleaseZip) (Join-Path $Artifacts 'validate-release.txt')
            Assert-HashesEqual $Before (Get-ManifestHashes $Repo)
            Assert-CloneIdentity -AfterChecks
        } finally { Pop-Location }
        $ReleaseZipHash = (Get-FileHash -LiteralPath $ReleaseZip -Algorithm SHA256).Hash
        $InstallUnpack = Join-Path $Artifacts 'install-clean'
        if (Test-Path -LiteralPath $InstallUnpack) { throw 'Installation staging already exists' }
# R2-BEGIN stage-17
Expand-Archive -LiteralPath $ReleaseZip -DestinationPath $InstallUnpack
$PackageRoot = Join-Path $InstallUnpack 'crm-sre-team'
$ExpectedNames = @((Get-Content -LiteralPath (Join-Path $PackageRoot 'release-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json).files)
Assert-PathSetEqual $ExpectedNames @(Get-PackageFiles $PackageRoot)
Assert-HashesEqual (Get-ManifestHashes $Repo) (Get-ManifestHashes $PackageRoot)
if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot 'settings.json') -PathType Leaf)) { throw '根 settings.json 缺失' }
# R2-END stage-17

        Assert-TreeNoReparse $PackageRoot
        $InstallMode = 'REAL'
        $DrillRoot = $null
        . Prepare-InstallContext
        $OldSnapshot = Get-SourceSnapshot $InstallSource
        $CacheVersions = @()
        if (Test-Path -LiteralPath $CacheRoot -PathType Container) { $CacheVersions = @(Get-ChildItem -LiteralPath $CacheRoot -Directory -Force | Select-Object -ExpandProperty Name) }
        $Document = [ordered]@{ schema='crm-oncall-plan/v1'; run_id=$RunId; created_utc=([DateTime]::UtcNow.ToString('o')); tag=$Tag; commit=$ExpectedCommit; zip_sha256=$ExpectedZipSha256; zip=$ReleaseZip; repo=$Repo; artifacts=$Artifacts; version=$Version; install_plan=$InstallPlan; expected_names=$InstallExpectedNames; package_hashes=$PackageHashes; manifest_sha256=$PackageHashes['release-manifest.json']; script_sha256=((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()); market_before_hash=$MarketBeforeHash; marketplace_entry=$Entries[0]; old_source=$OldSnapshot; cache_versions=$CacheVersions; pytest_requested=[bool]$RunPytest; host_acceptance='NOT_RUN' }
        $PlanPath = Join-Path $Artifacts 'install-plan.json'
        Write-NewJson $PlanPath $Document
        $PlanSha256 = (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Utf8Lf (Join-Path $Artifacts 'install-plan.sha256') ($PlanSha256 + "  install-plan.json`n")
        if ($FromUpdate) { Write-Host "UPDATE PLAN ready. PlanPath=$PlanPath; PlanSha256=$PlanSha256" }
        else {
            Write-Host ([IO.File]::ReadAllText($PlanPath, $Utf8NoBom))
            Write-Host "PLAN ONLY. PlanPath=$PlanPath; PlanSha256=$PlanSha256"
            Write-Host 'Review all paths/hashes, exit client, then run APPLY with this PLAN and hash. Nothing in WorkBuddy was written.'
        }
    } else {
        $Document = Load-Plan
        if ($Mode -ceq 'DRILL') {
            # Do not hydrate the REAL host context, even for path metadata reads.
            $Artifacts = $Document.artifacts
            $Version = $Document.version
            $PackageRoot = $Document.install_plan.package
            $InstallMetadataNames = @()
            $InstallExpectedNames = @($Document.expected_names)
            $PackageHashes = ConvertTo-HashTable $Document.package_hashes
        } else { . Import-PlanContext $Document }
        if ($Mode -ceq 'APPLY') {
            Assert-ClientStopped
            if (Test-Path -LiteralPath $BackupRoot) { throw 'PLAN already used; preserve backup and choose a new PLAN' }
            Assert-Package
            Assert-NoInstallReparse $ReleaseZip
            if ((Get-FileHash -LiteralPath $ReleaseZip -Algorithm SHA256).Hash -ine $ExpectedZipSha256) { throw 'Release ZIP changed since PLAN' }
            Assert-OldSource $InstallSource $Document.old_source
            Write-Host ($Document | ConvertTo-Json -Depth 100)
            Confirm-Yes "APPLY $Version to $InstallSource; backup=$BackupRoot"
            $null = Load-Plan
            Assert-ClientStopped
            Assert-Package
            Assert-NoInstallReparse $ReleaseZip
            Assert-TreeNoReparse $InstallSource
            Assert-OldSource $InstallSource $Document.old_source
            $MarketData = Get-Content -LiteralPath $Marketplace -Raw -Encoding UTF8 | ConvertFrom-Json
            $Entries = @($MarketData.plugins | Where-Object { $_.name -eq 'crm-sre-team' })
            Assert-MarketEntry
            . Initialize-Stages
# R2-BEGIN block-20
. {
$ErrorActionPreference = 'Stop'
Assert-InstallPaths -RequirePlan # 任何读写或客户端检查之前，逐一断言实际路径。
if ($InstallMode -cne 'DRILL' -and (Get-Process -Name 'WorkBuddy*','CodeBuddy*' -ErrorAction SilentlyContinue)) { throw '客户端未退出，请用户退出，不强杀' }
# 只有 DRILL 且上面的全部路径断言通过，才允许跳过客户端退出检查。
if ((Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 自计划后变动，重新审阅' }
Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $PackageRoot)
Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $PackageRoot)
if (-not (Test-Path -LiteralPath $InstallSource -PathType Container)) { throw '旧安装来源缺失，先核实' }
New-Item -ItemType Directory -Path $BackupRoot -ErrorAction Stop | Out-Null
Save-InstallState
try {
    $InstallStage = 'MARKET_BACKUP'
    Save-InstallState
    Invoke-IoRetry { Copy-Item -LiteralPath $Marketplace -Destination $MarketplaceBackup -Force } 'marketplace 备份'
    if ((Get-FileHash -LiteralPath $MarketplaceBackup -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 备份字节不符' }
    $MarketBackupComplete = $true
    $InstallStage = 'SOURCE_MOVE'
    $MoveStarted = $true
    Save-InstallState
    Invoke-IoRetry { Move-Item -LiteralPath $InstallSource -Destination $OldSource } '旧来源移动'
    if ((Test-Path -LiteralPath $InstallSource) -or -not (Test-Path -LiteralPath $OldSource -PathType Container)) { throw '旧来源移动未完成' }
    $OldSourceMoved = $true
    $InstallStage = 'COPY'
    $CopyStarted = $true
    Save-InstallState
    if ($InstallFault -eq 'COPY_FAILURE') {
        New-Item -ItemType Directory -Path $InstallSource | Out-Null
        Copy-Item -LiteralPath (Join-Path $PackageRoot 'VERSION') -Destination (Join-Path $InstallSource 'VERSION')
        throw 'DRILL: partial copy failure'
    }
    # 跨盘复制；旧来源连 .git 一起归档，宿主状态不迁移。
    Copy-Item -LiteralPath $PackageRoot -Destination $InstallSource -Recurse
    $CopyComplete = $true
    $InstallStage = 'VERIFY'
    Save-InstallState
    if ($InstallFault -eq 'VERIFY_FAILURE') { throw 'DRILL: verification failure' }
    Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $InstallSource)
    Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $InstallSource)
    $SourceVerified = $true
    $InstallStage = 'MARKET_WRITE'
    Save-InstallState
    if ($Entries[0].PSObject.Properties.Name -contains 'version') {
        $Entries[0].version = $Version
        $MarketWriteStarted = $true
        Save-InstallState
        if ($InstallFault -eq 'MARKET_PARTIAL') {
            Write-Utf8Lf $Marketplace '{"plugins":'
            throw 'DRILL: partial marketplace write'
        }
        $MarketJson = ($MarketData | ConvertTo-Json -Depth 100) + "`n"
        Invoke-IoRetry { Write-Utf8Lf $Marketplace $MarketJson } 'marketplace 写入'
        $VerifyMarket = Get-Content -LiteralPath $Marketplace -Raw -Encoding UTF8 | ConvertFrom-Json
        $VerifyEntries = @($VerifyMarket.plugins | Where-Object { $_.name -eq 'crm-sre-team' })
        if ($VerifyEntries.Count -ne 1 -or $VerifyEntries[0].version -cne $Version) { throw 'marketplace 写后校验失败' }
        $MarketWriteComplete = $true
    }
    $MarketAfterHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash
    $InstallStage = 'INSTALLED'
    Save-InstallState
} catch {
    $InstallError = $_
    # 移动可能已完成但随后异常；以精确路径现状补记，不猜状态。
    if ($MoveStarted -and (Test-Path -LiteralPath $OldSource -PathType Container) -and -not (Test-Path -LiteralPath $InstallSource)) { $OldSourceMoved = $true }
    try {
        if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { $MarketFailureHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash } else { $MarketFailureHash = $null }
        $MarketFailureCaptured = $true
        Save-InstallState
    } catch { Write-Host '失败后状态记录也未完成：保留全部备份，人工核对，不自动恢复 marketplace' }
    Write-Host "安装停在 $InstallStage；BackupRoot=$BackupRoot；按 5C 恢复，不启动客户端"
    throw $InstallError
}
}
# R2-END block-20

            $AppliedUtc = [DateTime]::UtcNow
            Write-NewJson (Join-Path $Artifacts 'apply-report.json') ([ordered]@{ status=$InstallStage; completed_utc=$AppliedUtc.ToString('o'); version=$Version; state=$StatePath; plan_sha256=$PlanSha256; backup=$BackupRoot; host_acceptance='NOT_RUN' })
            Write-Host "INSTALLED. StatePath=$StatePath. Open client, select $Version, start a NEW session, paste Self-check 1, then run VERIFY."
            Write-Host (Get-VerifyCommand)
        } elseif ($Mode -ceq 'VERIFY') {
            . Import-InstallState
            if ($InstallStage -cne 'INSTALLED') { throw 'VERIFY requires an INSTALLED state' }
            if (-not $SessionId -and -not $AgentId) {
                Show-RecentSessionMetadata (Get-ApplyCompletedUtc)
                return
            }
            Assert-Package
            $Cache = Join-Path $CacheRoot $Version
            $SourceCheck = Test-InstalledDeclaredFiles $InstallSource 'Source (after client)'
            $CacheCheck = Test-InstalledDeclaredFiles $Cache 'Target cache'
            $Evidence = $null
            if ($SessionId -or $AgentId) { $Evidence = Collect-SessionEvidence }
            $ReportPath = Join-Path $Artifacts ('verify-' + [guid]::NewGuid().ToString('N') + '.json')
            Write-NewJson $ReportPath ([ordered]@{ status='PASS_DECLARED_FILES_ONLY'; source=$SourceCheck; cache=$CacheCheck; evidence=$Evidence; host_acceptance='HUMAN_REVIEW_REQUIRED'; plan_sha256=$PlanSha256 })
            Write-Host "Report=$ReportPath. Cache existence is not proof of active version or Agent body loading. Review extra paths and session evidence."
        } elseif ($Mode -ceq 'ROLLBACK') {
            Assert-ClientStopped
            . Import-InstallState
            if ($InstallStage -ceq 'ROLLED_BACK') { throw 'Already rolled back; no writes' }
            Assert-TreeNoReparse $BackupRoot
            if ($MoveStarted) { Assert-OldSource $OldSource $Document.old_source }
            Confirm-Yes "ROLLBACK to old source $($Document.old_source.version); cache/settings.json are not separately written. Backup=$BackupRoot"
            $null = Load-Plan
            Assert-ClientStopped
            Assert-TreeNoReparse $BackupRoot
            if ($MoveStarted) { Assert-OldSource $OldSource $Document.old_source }
# R2-BEGIN block-22
. {
$ErrorActionPreference = 'Stop'
Assert-InstallPaths -RequirePlan # 恢复也必须先逐一断言实际路径；失败时不读写目标。
if ($InstallMode -cne 'DRILL' -and (Get-Process -Name 'WorkBuddy*','CodeBuddy*' -ErrorAction SilentlyContinue)) { throw '先退出客户端' }
if (-not $MarketBackupComplete) { throw 'marketplace 备份未完成；停止写入，人工检查现状' }
if ((Get-FileHash -LiteralPath $MarketplaceBackup -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 备份字节不符' }
$CurrentMarketHash = $null
if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { $CurrentMarketHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash }
if ($MarketWriteStarted) {
    if ($MarketWriteComplete -and $MarketAfterHash) { $ExpectedMarketHash = $MarketAfterHash }
    elseif ($MarketFailureCaptured) { $ExpectedMarketHash = $MarketFailureHash }
    else { throw '没有可靠的写失败后哈希；人工核对，不整文件恢复' }
} else { $ExpectedMarketHash = $MarketBeforeHash }
if ($CurrentMarketHash -cne $ExpectedMarketHash) { throw 'marketplace 已有后续变更，停止整文件恢复' }
if ($MoveStarted -and -not (Test-Path -LiteralPath $OldSource -PathType Container)) { throw '旧来源备份缺失；人工核对，不覆盖现有来源' }
$RollbackId = Get-Date -Format 'yyyyMMdd-HHmmss'
$FailedSource = Join-Path $BackupRoot ('failed-source-' + $RollbackId)
$CurrentMarketBackup = Join-Path $BackupRoot ('marketplace-before-rollback-' + $RollbackId + '.json')
if ((Test-Path -LiteralPath $FailedSource) -or (Test-Path -LiteralPath $CurrentMarketBackup)) { throw '回滚证据路径已存在' }
if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { Invoke-IoRetry { Copy-Item -LiteralPath $Marketplace -Destination $CurrentMarketBackup -Force } '失败时 marketplace 归档' }
if ($MoveStarted) {
    if (Test-Path -LiteralPath $InstallSource) { Invoke-IoRetry { Move-Item -LiteralPath $InstallSource -Destination $FailedSource } '失败来源隔离' }
    Invoke-IoRetry { Move-Item -LiteralPath $OldSource -Destination $InstallSource } '旧来源恢复'
    if (-not (Test-Path -LiteralPath $InstallSource -PathType Container)) { throw '来源恢复未完成，保留备份并停止' }
}
if ($MarketWriteStarted) { Invoke-IoRetry { Copy-Item -LiteralPath $MarketplaceBackup -Destination $Marketplace -Force } 'marketplace 恢复' }
if ((Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 恢复未完成，保留备份并停止' }
$InstallStage = 'ROLLED_BACK'
Save-InstallState
}
# R2-END block-22

            Assert-OldSource $InstallSource $Document.old_source
            Write-NewJson (Join-Path $Artifacts ('rollback-' + [guid]::NewGuid().ToString('N') + '.json')) ([ordered]@{ status=$InstallStage; old_version=$Document.old_source.version; backup=$BackupRoot; plan_sha256=$PlanSha256 })
            Write-Host 'ROLLED_BACK. Open client, reselect the previous active version and verify its cache. No cache deletion/rebuild or settings.json repair was performed.'
        } elseif ($Mode -ceq 'DRILL') {
            # Only synthetic host state. The checked release supplies the candidate.
            Assert-Package
            $CandidateSource = $PackageRoot
            $RunId = [guid]::NewGuid().ToString('N')
            $DrillRoot = Join-Path $Handoff ('drill-' + $RunId)
            Write-Host "DRILL new root=$DrillRoot; synthetic source/marketplace; no real host reads/writes after this point."
            if (-not $FromUpdate) { Confirm-Yes 'DRILL will APPLY then ROLLBACK inside the displayed synthetic root only' }
            New-SafeDirectory $DrillRoot $Handoff
            $InstallMode = 'DRILL'
            $InstallFault = 'NONE'
            $PackageRoot = Join-Path $DrillRoot 'candidate'
            Copy-Item -LiteralPath $CandidateSource -Destination $PackageRoot -Recurse
            $SyntheticSource = Join-Path $DrillRoot 'my-experts\plugins\crm-sre-team'
            $SyntheticMarket = Join-Path $DrillRoot 'my-experts\.codebuddy-plugin\marketplace.json'
            New-Item -ItemType Directory -Path $SyntheticSource -ErrorAction Stop | Out-Null
            New-Item -ItemType Directory -Path (Split-Path -Parent $SyntheticMarket) -ErrorAction Stop | Out-Null
            Write-Utf8Lf (Join-Path $SyntheticSource 'VERSION') "0.0.0-drill`n"
            Write-Utf8Lf (Join-Path $SyntheticSource 'old.txt') "SYNTHETIC OLD SOURCE`n"
            Write-NewJson $SyntheticMarket ([ordered]@{ name='synthetic'; plugins=@([ordered]@{ name='crm-sre-team'; source=$SyntheticSource; version='0.0.0-drill' }) })
            $DrillOldHash = (Get-FileHash -LiteralPath (Join-Path $SyntheticSource 'old.txt') -Algorithm SHA256).Hash
            . Prepare-InstallContext
            Write-NewJson (Join-Path $DrillRoot 'drill-plan.json') $InstallPlan
# R2-BEGIN block-20
. {
$ErrorActionPreference = 'Stop'
Assert-InstallPaths -RequirePlan # 任何读写或客户端检查之前，逐一断言实际路径。
if ($InstallMode -cne 'DRILL' -and (Get-Process -Name 'WorkBuddy*','CodeBuddy*' -ErrorAction SilentlyContinue)) { throw '客户端未退出，请用户退出，不强杀' }
# 只有 DRILL 且上面的全部路径断言通过，才允许跳过客户端退出检查。
if ((Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 自计划后变动，重新审阅' }
Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $PackageRoot)
Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $PackageRoot)
if (-not (Test-Path -LiteralPath $InstallSource -PathType Container)) { throw '旧安装来源缺失，先核实' }
New-Item -ItemType Directory -Path $BackupRoot -ErrorAction Stop | Out-Null
Save-InstallState
try {
    $InstallStage = 'MARKET_BACKUP'
    Save-InstallState
    Invoke-IoRetry { Copy-Item -LiteralPath $Marketplace -Destination $MarketplaceBackup -Force } 'marketplace 备份'
    if ((Get-FileHash -LiteralPath $MarketplaceBackup -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 备份字节不符' }
    $MarketBackupComplete = $true
    $InstallStage = 'SOURCE_MOVE'
    $MoveStarted = $true
    Save-InstallState
    Invoke-IoRetry { Move-Item -LiteralPath $InstallSource -Destination $OldSource } '旧来源移动'
    if ((Test-Path -LiteralPath $InstallSource) -or -not (Test-Path -LiteralPath $OldSource -PathType Container)) { throw '旧来源移动未完成' }
    $OldSourceMoved = $true
    $InstallStage = 'COPY'
    $CopyStarted = $true
    Save-InstallState
    if ($InstallFault -eq 'COPY_FAILURE') {
        New-Item -ItemType Directory -Path $InstallSource | Out-Null
        Copy-Item -LiteralPath (Join-Path $PackageRoot 'VERSION') -Destination (Join-Path $InstallSource 'VERSION')
        throw 'DRILL: partial copy failure'
    }
    # 跨盘复制；旧来源连 .git 一起归档，宿主状态不迁移。
    Copy-Item -LiteralPath $PackageRoot -Destination $InstallSource -Recurse
    $CopyComplete = $true
    $InstallStage = 'VERIFY'
    Save-InstallState
    if ($InstallFault -eq 'VERIFY_FAILURE') { throw 'DRILL: verification failure' }
    Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $InstallSource)
    Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $InstallSource)
    $SourceVerified = $true
    $InstallStage = 'MARKET_WRITE'
    Save-InstallState
    if ($Entries[0].PSObject.Properties.Name -contains 'version') {
        $Entries[0].version = $Version
        $MarketWriteStarted = $true
        Save-InstallState
        if ($InstallFault -eq 'MARKET_PARTIAL') {
            Write-Utf8Lf $Marketplace '{"plugins":'
            throw 'DRILL: partial marketplace write'
        }
        $MarketJson = ($MarketData | ConvertTo-Json -Depth 100) + "`n"
        Invoke-IoRetry { Write-Utf8Lf $Marketplace $MarketJson } 'marketplace 写入'
        $VerifyMarket = Get-Content -LiteralPath $Marketplace -Raw -Encoding UTF8 | ConvertFrom-Json
        $VerifyEntries = @($VerifyMarket.plugins | Where-Object { $_.name -eq 'crm-sre-team' })
        if ($VerifyEntries.Count -ne 1 -or $VerifyEntries[0].version -cne $Version) { throw 'marketplace 写后校验失败' }
        $MarketWriteComplete = $true
    }
    $MarketAfterHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash
    $InstallStage = 'INSTALLED'
    Save-InstallState
} catch {
    $InstallError = $_
    # 移动可能已完成但随后异常；以精确路径现状补记，不猜状态。
    if ($MoveStarted -and (Test-Path -LiteralPath $OldSource -PathType Container) -and -not (Test-Path -LiteralPath $InstallSource)) { $OldSourceMoved = $true }
    try {
        if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { $MarketFailureHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash } else { $MarketFailureHash = $null }
        $MarketFailureCaptured = $true
        Save-InstallState
    } catch { Write-Host '失败后状态记录也未完成：保留全部备份，人工核对，不自动恢复 marketplace' }
    Write-Host "安装停在 $InstallStage；BackupRoot=$BackupRoot；按 5C 恢复，不启动客户端"
    throw $InstallError
}
}
# R2-END block-20

            if ($InstallStage -cne 'INSTALLED') { throw 'DRILL installation did not complete' }
            # Cross-session hydration path, with the same original state format.
            . Import-InstallState
# R2-BEGIN block-22
. {
$ErrorActionPreference = 'Stop'
Assert-InstallPaths -RequirePlan # 恢复也必须先逐一断言实际路径；失败时不读写目标。
if ($InstallMode -cne 'DRILL' -and (Get-Process -Name 'WorkBuddy*','CodeBuddy*' -ErrorAction SilentlyContinue)) { throw '先退出客户端' }
if (-not $MarketBackupComplete) { throw 'marketplace 备份未完成；停止写入，人工检查现状' }
if ((Get-FileHash -LiteralPath $MarketplaceBackup -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 备份字节不符' }
$CurrentMarketHash = $null
if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { $CurrentMarketHash = (Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash }
if ($MarketWriteStarted) {
    if ($MarketWriteComplete -and $MarketAfterHash) { $ExpectedMarketHash = $MarketAfterHash }
    elseif ($MarketFailureCaptured) { $ExpectedMarketHash = $MarketFailureHash }
    else { throw '没有可靠的写失败后哈希；人工核对，不整文件恢复' }
} else { $ExpectedMarketHash = $MarketBeforeHash }
if ($CurrentMarketHash -cne $ExpectedMarketHash) { throw 'marketplace 已有后续变更，停止整文件恢复' }
if ($MoveStarted -and -not (Test-Path -LiteralPath $OldSource -PathType Container)) { throw '旧来源备份缺失；人工核对，不覆盖现有来源' }
$RollbackId = Get-Date -Format 'yyyyMMdd-HHmmss'
$FailedSource = Join-Path $BackupRoot ('failed-source-' + $RollbackId)
$CurrentMarketBackup = Join-Path $BackupRoot ('marketplace-before-rollback-' + $RollbackId + '.json')
if ((Test-Path -LiteralPath $FailedSource) -or (Test-Path -LiteralPath $CurrentMarketBackup)) { throw '回滚证据路径已存在' }
if (Test-Path -LiteralPath $Marketplace -PathType Leaf) { Invoke-IoRetry { Copy-Item -LiteralPath $Marketplace -Destination $CurrentMarketBackup -Force } '失败时 marketplace 归档' }
if ($MoveStarted) {
    if (Test-Path -LiteralPath $InstallSource) { Invoke-IoRetry { Move-Item -LiteralPath $InstallSource -Destination $FailedSource } '失败来源隔离' }
    Invoke-IoRetry { Move-Item -LiteralPath $OldSource -Destination $InstallSource } '旧来源恢复'
    if (-not (Test-Path -LiteralPath $InstallSource -PathType Container)) { throw '来源恢复未完成，保留备份并停止' }
}
if ($MarketWriteStarted) { Invoke-IoRetry { Copy-Item -LiteralPath $MarketplaceBackup -Destination $Marketplace -Force } 'marketplace 恢复' }
if ((Get-FileHash -LiteralPath $Marketplace -Algorithm SHA256).Hash -cne $MarketBeforeHash) { throw 'marketplace 恢复未完成，保留备份并停止' }
$InstallStage = 'ROLLED_BACK'
Save-InstallState
}
# R2-END block-22

            if ($InstallStage -cne 'ROLLED_BACK' -or (Get-FileHash -LiteralPath (Join-Path $InstallSource 'old.txt') -Algorithm SHA256).Hash -cne $DrillOldHash -or [IO.File]::ReadAllText((Join-Path $InstallSource 'VERSION'), $Utf8NoBom).Trim() -cne '0.0.0-drill') { throw 'DRILL restore mismatch' }
            Write-NewJson (Join-Path $DrillRoot 'drill-report.json') ([ordered]@{ status='PASS_APPLY_ROLLBACK_ONLY'; completed_utc=([DateTime]::UtcNow.ToString('o')); state=$StatePath; root=$DrillRoot; tag=$Tag; commit=$ExpectedCommit; plan_sha256=$PlanSha256; script_sha256=((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()); windows_orchestration='THIS_RUN_ONLY'; fault_injection='NOT_RUN'; real_host='NOT_ACCESSED_BY_DRILL' })
            Write-Host "DRILL PASS (APPLY -> state reload -> ROLLBACK). Report=$DrillRoot\drill-report.json; keep all evidence."
        }
    }
}
try {
    if ($Drill -and $Mode -cne 'UPDATE') { throw '-Drill is an UPDATE switch; use -Mode DRILL for a standalone drill.' }
    $Git = Get-NativeProgram $GitExe
    # Process-only settings; never read existing credential/environment values.
    $env:GIT_CONFIG_NOSYSTEM = '1'
    $env:GIT_CONFIG_GLOBAL = 'NUL'
    $env:GIT_OPTIONAL_LOCKS = '0'
    $env:GIT_TERMINAL_PROMPT = '0'
    $env:GCM_INTERACTIVE = 'Never'
    $env:GIT_ASKPASS = ''
    $env:SSH_ASKPASS = ''
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'url.https://github.com/caomz/crm-sre-team.git.insteadOf'
    $env:GIT_CONFIG_VALUE_0 = $RepoUrl
    $VerifiedWorkTree = Assert-UpdaterIdentity
    if ($Mode -ceq 'UPDATE') {
        if ($PlanPath -or $PlanSha256 -or $SessionId -or $AgentId) { throw 'UPDATE creates its own PLAN; do not pass a plan/session ID.' }
        Assert-ClientStopped
        # Dot-sourcing keeps the generated PlanPath/PlanSha256 in this process.
        . Invoke-OncallMode 'PLAN' -FromUpdate
        if ($Drill -or -not (Test-SuccessfulDrill)) {
            . Invoke-OncallMode 'DRILL' -FromUpdate
        }
        # Reload REAL context after synthetic DRILL; APPLY prints it and asks YES.
        . Invoke-OncallMode 'APPLY' -FromUpdate
    } else { . Invoke-OncallMode $Mode }
} catch {
    Write-Host ('STOP: ' + (Protect-Output $_.Exception.Message))
    Write-Host 'Retain new clone, reports, and all backups. Do not start the client after a partial APPLY; use the reviewed PLAN for ROLLBACK or human recovery.'
    exit 1
}
