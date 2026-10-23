#requires -Version 5.1
# Approved design: pinned tag -> verified local clone -> offline checks -> hashed PLAN;
# UPDATE carries PLAN/hash in-process; optional synthetic DRILL; one YES -> APPLY.
# Git bootstrap checks HEAD, clean tree and raw script blob before any mode.
# PLAN uses that verified worktree as clone source; standalone uses GitHub.
# EXPBUILD shares formal preparation; SWITCH uses a frozen set and one YES.
# NEW ORCHESTRATION: NOT RUN ON WINDOWS. UTF-8 BOM preserves verbatim r2 text.
[CmdletBinding()]
param(
    [ValidateSet('PLAN','APPLY','VERIFY','ROLLBACK','DRILL','UPDATE','EXPBUILD','SWITCH')][string]$Mode = 'PLAN',
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]*$')][string]$Tag,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{40}$')][string]$ExpectedCommit,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedZipSha256,
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedScriptSha256,
    [string]$ExperimentSet,
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExperimentSetSha256,
    [ValidateSet('formal','probe','cmp-n','cmp-s','probe-webfetch-denied','probe-bash-denied','probe-powershell-denied')][string]$Package,
    [string]$PlanPath,
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$PlanSha256,
    [string]$DevRoot = 'D:\Dev',
    [string]$HandoffRoot = 'D:\crm-v36-handoff',
    [string]$WorkBuddyRoot = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.workbuddy'),
    [string]$PythonExe = (Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Python\Python312\python.exe'),
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
$DefaultPythonExe = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Python\Python312\python.exe'
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
    $RealRoot = $WorkBuddyRoot
    $RealPrefix = $RealRoot + '\'
    if ($InstallMode -ceq 'DRILL') {
        $BoundRoot = Get-InstallFullPath $DrillRoot
        if ((Split-Path -Path $BoundRoot -Parent) -ine $Handoff -or (Split-Path -Path $BoundRoot -Leaf) -notmatch '^drill-[A-Za-z0-9][A-Za-z0-9-]*$') { throw '演练根必须是 HandoffRoot 下的 drill-<唯一编号>' }
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


# rc7 roots: normalize once, require a local drive, retain all reparse guards.
function Get-ConfiguredRoot([string]$Value) {
    if ($Value -match '(^|[\\/])\.\.([\\/]|$)' -or $Value -match '[<>"|?*]' -or $Value -match '[. ]([\\/]|$)') { throw 'Unsafe root path' }
    $Full = Get-InstallFullPath $Value
    $Drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($Full + '\'))
    if ($Drive.DriveType -notin @([IO.DriveType]::Fixed,[IO.DriveType]::Removable)) { throw 'Root must use a local drive' }
    if ($Full -match '^[A-Za-z]:$') { throw 'Root must be a directory below the drive root' }
    Assert-NoInstallReparse $Full
    if ((Test-Path -LiteralPath $Full) -and -not (Test-Path -LiteralPath $Full -PathType Container)) { throw 'Root is not a directory' }
    return $Full
}
function Initialize-PathRoots {
    # Dot-source into script scope, before any use of Assert-Under.
    $DevRoot = Get-ConfiguredRoot $DevRoot
    $Handoff = Get-ConfiguredRoot $HandoffRoot
    $WorkBuddyRoot = Get-ConfiguredRoot $WorkBuddyRoot
    foreach ($Root in @($DevRoot,$Handoff)) {
        if ($Root -ieq $WorkBuddyRoot -or $Root.StartsWith(($WorkBuddyRoot + '\'), [StringComparison]::OrdinalIgnoreCase) -or $WorkBuddyRoot.StartsWith(($Root + '\'), [StringComparison]::OrdinalIgnoreCase)) { throw 'DevRoot/HandoffRoot must not overlap WorkBuddyRoot' }
    }
    $PathRoots = [pscustomobject][ordered]@{ dev_root=$DevRoot; handoff_root=$Handoff; workbuddy_root=$WorkBuddyRoot }
}
function Assert-PathRootsMatch($Recorded) {
    if ($null -eq $Recorded) { throw 'PLAN/set lacks rc7 path_roots; use its original updater' }
    Assert-PathSetEqual @('dev_root','handoff_root','workbuddy_root') @($Recorded.PSObject.Properties.Name)
    foreach ($Key in @('dev_root','handoff_root','workbuddy_root')) {
        if ($Recorded.$Key -isnot [string] -or (Get-ConfiguredRoot $Recorded.$Key) -ine $PathRoots.$Key) { throw "Root differs from PLAN/set: $Key" }
    }
}

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
    if (Test-Path -LiteralPath (Join-Path $Root 'VERSION') -PathType Leaf) {
        $SnapshotVersion = [IO.File]::ReadAllText((Join-Path $Root 'VERSION'), $Utf8NoBom).Trim()
        if ($SnapshotVersion -cmatch '-probe\.r[0-9a-f]{8}$') { $Names += 'probe-manifest.json' }
    }
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
    if ($Entries[0].PSObject.Properties.Name -contains 'version' -and ($Entries[0].version -isnot [string] -or [string]::IsNullOrWhiteSpace($Entries[0].version))) {
        throw 'Marketplace entry has an invalid version field; human review required'
    }
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
    Assert-PathSetEqual $InstallExpectedNames @(@(Get-DeclaredNames $PackageRoot) + @($InstallMetadataNames))
    Assert-PathSetEqual $InstallExpectedNames @(Get-PackageFiles $PackageRoot)
    Assert-HashesEqual $PackageHashes (Get-SelectedPackageHashes $PackageRoot)
    if ([IO.File]::ReadAllText((Join-Path $PackageRoot 'VERSION'), $Utf8NoBom).Trim() -cne $Version) { throw 'Package version changed' }
}
function Confirm-Yes([string]$Action) {
    Write-Host $Action
    try { $Host.UI.RawUI.FlushInputBuffer() } catch {}
    if ((Read-Host 'Type YES to confirm the displayed plan') -cne 'YES') { throw 'Confirmation refused; no installation writes performed' }
}
function Assert-PlanLayout($Document) {
    Assert-PathRootsMatch $Document.path_roots
    if ($Document.schema -cne 'crm-oncall-plan/v1' -or $Document.tag -cne $Tag -or $Document.commit -cne $ExpectedCommit -or $Document.zip_sha256 -cne $ExpectedZipSha256) { throw 'PLAN does not match release inputs' }
    if ($Document.run_id -notmatch '^[0-9a-f]{32}$' -or $Document.version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$') { throw 'Invalid PLAN identifier or version' }
    $WantArtifacts = Join-Path $Handoff ('update-' + $Document.run_id)
    if ((Get-InstallFullPath $Document.artifacts) -ine $WantArtifacts -or (Get-InstallFullPath $PlanPath) -ine (Join-Path $WantArtifacts 'install-plan.json')) { throw 'PLAN must be in its unique handoff directory' }
    $null = Assert-Under $Document.artifacts $Handoff
    $IsSwitch = $Document.operation -ceq 'SWITCH'
    $CloneId = $Document.run_id
    $Label = 'oncall'
    if ($IsSwitch) {
        if ($Document.experiment_set_id -notmatch '^[0-9a-f]{32}$' -or $Document.experiment_set_sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid switch set identifier/hash' }
        $CloneId = $Document.experiment_set_id
        $Label = $Document.package_kind
        $Metadata = @(Get-PackageMetadataNames $Label)
        Assert-PathSetEqual $Metadata @($Document.metadata_names)
        $SetRoot = Join-Path $Handoff ('experiment-' + $CloneId)
        if ((Get-InstallFullPath $Document.experiment_set) -ine (Join-Path $SetRoot 'experiment-set.json') -or (Get-InstallFullPath $Document.zip) -ine (Join-Path $WantArtifacts 'release.zip')) { throw 'Unexpected switch set/ZIP path' }
        $null = Assert-Under $Document.zip $Handoff
    }
    $WantRepo = Join-Path $DevRoot ('crm-oncall-' + $CloneId + '\repo')
    if ((Get-InstallFullPath $Document.repo) -ine $WantRepo) { throw 'Unexpected clone path' }
    $null = Assert-Under $Document.repo $DevRoot
    $WantPackage = Join-Path $WantArtifacts 'install-clean\crm-sre-team'
    $IP = $Document.install_plan
    if ($IP.mode -cne 'REAL' -or $IP.fault -cne 'NONE' -or $IP.bound_root -ine $WorkBuddyRoot -or (Get-InstallFullPath $IP.package) -ine $WantPackage) { throw 'Unexpected install mode or package path' }
    $MR = Join-Path $WorkBuddyRoot 'plugins\marketplaces\my-experts'
    $BR = Join-Path $MR ('backups\crm-v36-' + $Document.run_id + '-' + $Label)
    $Want = [ordered]@{ MarketRoot=$MR; InstallSource=(Join-Path $MR 'plugins\crm-sre-team'); Marketplace=(Join-Path $MR '.codebuddy-plugin\marketplace.json'); BackupRoot=$BR; OldSource=(Join-Path $BR 'install-source'); MarketplaceBackup=(Join-Path $BR 'marketplace.json'); StatePath=(Join-Path $BR 'install-state.json'); CacheRoot=(Join-Path $WorkBuddyRoot 'plugins\cache\my-experts\crm-sre-team') }
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
    $PackageKind = 'formal'
    $ExpectedMarkers = @()
    if ($Document.operation -ceq 'SWITCH') {
        $InstallLabel = $Document.package_kind
        $PackageKind = $Document.package_kind
        $ExpectedMarkers = @($Document.expected_markers)
        $ReleaseZip = $Document.zip
    }
    $InstallPlan = $Document.install_plan
    $PackageRoot = $InstallPlan.package
    foreach ($Key in @('MarketRoot','InstallSource','Marketplace','BackupRoot','OldSource','MarketplaceBackup','StatePath','CacheRoot')) { Set-Variable -Name $Key -Value $InstallPlan.paths.$Key }
    $MarketBeforeHash = $Document.market_before_hash
    $InstallMetadataNames = @()
    if ($Document.operation -ceq 'SWITCH') { $InstallMetadataNames = @($Document.metadata_names) }
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
function Prepare-InstallContext([string]$ContextLabel = 'oncall', [string[]]$ContextMetadataNames = @()) {
    # Path construction and PLAN finalization from r2 block 19.
    $InstallLabel = $ContextLabel
    $InstallFault = 'NONE'
    $InstallPlan = $null
    . Initialize-Stages
    if ($InstallMode -ceq 'DRILL') {
        $MarketRoot = Join-Path $DrillRoot 'my-experts'
        $CacheRoot = Join-Path $DrillRoot 'cache\my-experts\crm-sre-team'
        $PackageRoot = Join-Path $DrillRoot 'candidate'
    } else {
        $MarketRoot = Join-Path $WorkBuddyRoot 'plugins\marketplaces\my-experts'
        $CacheRoot = Join-Path $WorkBuddyRoot 'plugins\cache\my-experts\crm-sre-team'
    }
    $InstallSource = Join-Path $MarketRoot 'plugins\crm-sre-team'
    $Marketplace = Join-Path $MarketRoot '.codebuddy-plugin\marketplace.json'
    $BackupRoot = Join-Path $MarketRoot ("backups\crm-v36-$RunId-$InstallLabel")
    $OldSource = Join-Path $BackupRoot 'install-source'
    $MarketplaceBackup = Join-Path $BackupRoot 'marketplace.json'
    $StatePath = Join-Path $BackupRoot 'install-state.json'
    Assert-InstallPaths
    if (Test-Path -LiteralPath $BackupRoot) { throw 'Backup already exists; choose a new PLAN' }
    $InstallMetadataNames = @($ContextMetadataNames)
    $InstallExpectedNames = @(@(Get-DeclaredNames $PackageRoot) + $InstallMetadataNames)
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
    $BoundRoot = $WorkBuddyRoot
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
    foreach ($Pair in @(@('Tag',$Tag),@('ExpectedCommit',$ExpectedCommit),@('ExpectedZipSha256',$ExpectedZipSha256),@('PlanPath',$PlanPath),@('PlanSha256',$PlanSha256),@('GitExe',$Git),@('DevRoot',$DevRoot),@('HandoffRoot',$Handoff),@('WorkBuddyRoot',$WorkBuddyRoot))) {
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
    $Projects = Join-Path $WorkBuddyRoot 'projects'
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
    $Projects = Join-Path $WorkBuddyRoot 'projects'
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
    if (@($ExpectedMarkers).Count -gt 0) {
        $MarkerRecords = @()
        foreach ($Snapshot in $Snapshots) {
            $Counts = Get-RawMarkerCounts $Snapshot.Data.Text $ExpectedMarkers
            $MarkerRecords += [pscustomobject]@{ record=$Snapshot.File.Name; counts=$Counts }
            foreach ($Marker in $Counts.Keys) { Write-Host "Raw marker aid: Record=$($Snapshot.File.Name); Marker=$Marker; Count=$($Counts[$Marker]); location unknown, NOT A VERDICT" }
        }
        Write-NewJson (Join-Path $EvidenceRoot 'marker-counts.json') ([ordered]@{ scope='RAW_OCCURRENCES_LOCATION_UNKNOWN_NOT_A_VERDICT'; records=$MarkerRecords })
    }
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

# Experiment helpers: NOT RUN ON WINDOWS. R2 path substitutions are reviewed in tests.
function Get-ExperimentPython {
    if ($PythonExe -ieq $DefaultPythonExe -and -not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Default Python312 python.exe is missing; pass -PythonExe with the verified real interpreter path.' }
    return (Get-NativeProgram $PythonExe)
}
function Get-PackageMetadataNames([string]$Kind) {
    if ($Kind -cin @('probe','probe-webfetch-denied','probe-bash-denied','probe-powershell-denied')) { return @('probe-manifest.json') }
    if ($Kind -cnotin @('formal','cmp-n','cmp-s')) { throw 'Unknown package kind' }
    return @()
}
function Load-ExperimentSet {
    if (-not $ExperimentSet -or -not $ExperimentSetSha256 -or -not $Package) { throw 'SWITCH requires -ExperimentSet, -ExperimentSetSha256 and -Package' }
    $null = Assert-Under $ExperimentSet $Handoff
    $Read = ReadShared $ExperimentSet
    if ($Read.Sha -ine $ExperimentSetSha256) { throw 'Experiment set SHA256 mismatch; no install plan or host writes' }
    $Set = $Read.Text | ConvertFrom-Json
    Assert-PathRootsMatch $Set.path_roots
    if ($Set.schema -cne 'crm-oncall-experiment/v1' -or $Set.tag -cne $Tag -or $Set.commit -cne $ExpectedCommit -or $Set.zip_sha256 -cne $ExpectedZipSha256 -or $Set.script_sha256 -ine (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash) { throw 'Experiment set identity mismatch; use its original bootstrap and release inputs' }
    if ($Set.set_id -notmatch '^[0-9a-f]{32}$') { throw 'Invalid experiment set identifier' }
    $SetRoot = Join-Path $Handoff ('experiment-' + $Set.set_id)
    if ((Get-InstallFullPath $ExperimentSet) -ine (Join-Path $SetRoot 'experiment-set.json') -or (Get-InstallFullPath $Set.artifacts) -ine $SetRoot) { throw 'Unexpected experiment set path' }
    return $Set
}
function Invoke-ExperimentBuild {
    # Dot-source: shared PLAN preparation has already verified formal ZIP/unpack.
    Assert-HashesEqual $Before (Get-ManifestHashes $Repo)
    Assert-CloneIdentity -AfterChecks
    Push-Location -LiteralPath $Repo
    try {
        $null = Invoke-Native $Python @('tools/make_probe_build.py','--root',$Repo,'--out',(Join-Path $Artifacts 'probe')) (Join-Path $Artifacts 'probe-build.txt')
        $null = Invoke-Native $Python @('tools/make_comparison_build.py','--root',$Repo,'--out',(Join-Path $Artifacts 'comparison')) (Join-Path $Artifacts 'comparison-build.txt')
        foreach ($Spec in @(@('probe-webfetch-denied','WebFetch'),@('probe-bash-denied','Bash'),@('probe-powershell-denied','PowerShell'))) {
            $null = Invoke-Native $Python @('tools/make_probe_build.py','--root',$Repo,'--out',(Join-Path $Artifacts $Spec[0]),'--disallow',('oracle-dba=' + $Spec[1])) (Join-Path $Artifacts ($Spec[0] + '-build.txt'))
        }
        Assert-HashesEqual $Before (Get-ManifestHashes $Repo)
        Assert-CloneIdentity -AfterChecks
    } finally { Pop-Location }
    $VerifierPath = Join-Path $Artifacts 'experiment-verifier.py'
    Write-ExperimentVerifier $VerifierPath
    $ScriptHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $null = Invoke-Native $Python @($VerifierPath,'build','--repo',$Repo,'--artifacts',$Artifacts,'--head',$ExpectedCommit,'--tag',$Tag,'--zip-sha',$ExpectedZipSha256,'--script-sha',$ScriptHash,'--set-id',$RunId,'--dev-root',$DevRoot,'--handoff-root',$Handoff,'--workbuddy-root',$WorkBuddyRoot) (Join-Path $Artifacts 'experiment-verify.txt')
    $ExperimentSet = Join-Path $Artifacts 'experiment-set.json'
    $ExperimentSetSha256 = (Get-FileHash -LiteralPath $ExperimentSet -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Utf8Lf (Join-Path $Artifacts 'experiment-set.sha256') ($ExperimentSetSha256 + "  experiment-set.json`n")
    Write-Host "ExperimentSet=$ExperimentSet; ExperimentSetSha256=$ExperimentSetSha256"
    Write-Host 'EXPBUILD ONLY. Formal/probe/N/S/limited packages verified locally; no WorkBuddy reads/writes or host acceptance. Preserve this ONE set for the whole gate round.'
}
function Invoke-SwitchPlan {
    # Dot-source: publish PlanPath/PlanSha256 for the existing DRILL/APPLY path.
    if ($PlanPath -or $PlanSha256 -or $SessionId -or $AgentId -or $RunPytest) { throw 'SWITCH creates its own plan from an existing set; no plan/session IDs or -RunPytest' }
    Assert-ClientStopped
    $Set = Load-ExperimentSet
    $Python = Get-ExperimentPython
    $RunId = [guid]::NewGuid().ToString('N')
    $Artifacts = Join-Path $Handoff ('update-' + $RunId)
    New-SafeDirectory $Artifacts $Handoff
    $TaskTemp = Join-Path $Artifacts 'temp'
    New-SafeDirectory $TaskTemp $Handoff
    $env:TEMP = $TaskTemp
    $env:TMP = $TaskTemp
    $env:TMPDIR = $TaskTemp
    $env:PYTHONUTF8 = '1'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $VerifierPath = Join-Path $Artifacts 'experiment-verifier.py'
    Write-ExperimentVerifier $VerifierPath
    $ScriptHash = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $SelectionPath = Join-Path $Artifacts 'selection.json'
    $null = Invoke-Native $Python @($VerifierPath,'select','--set',$ExperimentSet,'--set-sha',$ExperimentSetSha256.ToLowerInvariant(),'--package',$Package,'--head',$ExpectedCommit,'--tag',$Tag,'--zip-sha',$ExpectedZipSha256,'--script-sha',$ScriptHash,'--output',$SelectionPath,'--dev-root',$DevRoot,'--handoff-root',$Handoff,'--workbuddy-root',$WorkBuddyRoot) (Join-Path $Artifacts 'selected-package-verify.txt')
    $Selection = (ReadShared $SelectionPath).Text | ConvertFrom-Json
    $Set = $Selection.experiment
    $Selected = $Selection.selected
    $null = Assert-Under $Set.repo $DevRoot
    $null = Assert-Under $Set.zip $Handoff
    $null = Assert-Under $Selected.root $Set.artifacts
    Assert-TreeNoReparse $Selected.root
    # Exact set/bytes have been re-hashed BEFORE creating the install plan.
    $InstallUnpack = Join-Path $Artifacts 'install-clean'
    New-SafeDirectory $InstallUnpack $Handoff
    $PackageRoot = Join-Path $InstallUnpack 'crm-sre-team'
    Copy-Item -LiteralPath $Selected.root -Destination $PackageRoot -Recurse
    $Version = $Selected.version
    $Repo = $Set.repo
    $ReleaseZip = Join-Path $Artifacts 'release.zip'
    Copy-Item -LiteralPath $Set.zip -Destination $ReleaseZip
    if ((Get-FileHash -LiteralPath $ReleaseZip -Algorithm SHA256).Hash -ine $ExpectedZipSha256) { throw 'Copied formal ZIP differs from the experiment set' }
    $InstallMode = 'REAL'
    $DrillRoot = $null
    $Metadata = @(Get-PackageMetadataNames $Package)
    . Prepare-InstallContext -ContextLabel $Package -ContextMetadataNames $Metadata
    Assert-PathSetEqual @($Selected.expected_names) $InstallExpectedNames
    Assert-HashesEqual (ConvertTo-HashTable $Selected.hashes) $PackageHashes
    if ($Entries[0].PSObject.Properties.Name -notcontains 'version') { Write-Host 'SWITCH PLAN: Marketplace entry has no version field; marketplace.json will not be written. Refresh/update the client to the package version.' }
    $OldSnapshot = Get-SourceSnapshot $InstallSource
    $CacheVersions = @()
    if (Test-Path -LiteralPath $CacheRoot -PathType Container) { $CacheVersions = @(Get-ChildItem -LiteralPath $CacheRoot -Directory -Force | Select-Object -ExpandProperty Name) }
    $Document = [ordered]@{ schema='crm-oncall-plan/v1'; path_roots=$PathRoots; operation='SWITCH'; run_id=$RunId; created_utc=([DateTime]::UtcNow.ToString('o')); tag=$Tag; commit=$ExpectedCommit; zip_sha256=$ExpectedZipSha256; zip=$ReleaseZip; repo=$Repo; artifacts=$Artifacts; version=$Version; install_plan=$InstallPlan; expected_names=$InstallExpectedNames; package_hashes=$PackageHashes; manifest_sha256=$PackageHashes['release-manifest.json']; script_sha256=$ScriptHash; market_before_hash=$MarketBeforeHash; marketplace_entry=$Entries[0]; old_source=$OldSnapshot; cache_versions=$CacheVersions; pytest_requested=$false; host_acceptance='NOT_RUN'; package_kind=$Package; metadata_names=$Metadata; expected_markers=@($Selected.markers.expected); markers=$Selected.markers; disallow=$Selected.disallow; experiment_set=$ExperimentSet; experiment_set_sha256=$ExperimentSetSha256.ToLowerInvariant(); experiment_set_id=$Set.set_id; source_tree_sha256=$Set.source_tree_sha256; source_version=$Set.source_version; builder_manifest=$Selected.builder_manifest }
    $PlanPath = Join-Path $Artifacts 'install-plan.json'
    Write-NewJson $PlanPath $Document
    $PlanSha256 = (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Utf8Lf (Join-Path $Artifacts 'install-plan.sha256') ($PlanSha256 + "  install-plan.json`n")
    Write-Host ([IO.File]::ReadAllText($PlanPath, $Utf8NoBom))
    Write-Host "SWITCH PLAN ready. Package=$Package; PlanPath=$PlanPath; PlanSha256=$PlanSha256"
}
function Assert-RollbackCurrentPackage {
    # R6 for INSTALLED only: declared bytes with the host-managed root settings exception.
    try { $null = Test-InstalledDeclaredFiles $InstallSource 'ROLLBACK current source' }
    catch { throw 'ROLLBACK refused: roll back the newest plan first, or SWITCH to the wanted package. Current source does not match this plan; retain evidence for human recovery.' }
}
function Get-RawMarkerCounts([string]$Text, [string[]]$Markers) {
    $Counts = [ordered]@{}
    foreach ($Marker in @($Markers)) {
        if ([string]::IsNullOrEmpty($Marker)) { throw 'Invalid empty expected marker' }
        $Counts[$Marker] = [regex]::Matches($Text, [regex]::Escape($Marker)).Count
    }
    return $Counts
}
function Write-ExperimentVerifier([string]$Path) {
    Assert-NoInstallReparse $Path
    if (Test-Path -LiteralPath $Path) { throw 'Verifier output already exists' }
    $ExperimentVerifierCode = @'
"""Offline structural verifier; writes new JSON files and prints status only."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
from datetime import datetime, timezone
from zipfile import ZipFile

PACKAGE_NAMES = (
    'formal', 'probe', 'cmp-n', 'cmp-s', 'probe-webfetch-denied',
    'probe-bash-denied', 'probe-powershell-denied',
)
DISALLOW = {
    'probe': {}, 'probe-webfetch-denied': {'oracle-dba': ['WebFetch']},
    'probe-bash-denied': {'oracle-dba': ['Bash']},
    'probe-powershell-denied': {'oracle-dba': ['PowerShell']},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new_json(path, value):
    path = no_links(path)
    data = (json.dumps(value, ensure_ascii=True, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')
    with path.open('xb') as output:
        output.write(data)


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink(), 'Link path: ' + str(part))
        if part.exists():
            require(not (getattr(part.lstat(), 'st_file_attributes', 0) & 0x400),
                    'Reparse path: ' + str(part))
    return path


def file_paths(root):
    root = no_links(root)
    require(root.is_dir(), 'Missing package root: ' + str(root))
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            no_links(Path(directory) / name)
        for name in files:
            path = Path(directory) / name
            require(path.is_file(), 'Non-file package entry')
            result[path.relative_to(root).as_posix()] = path
    return dict(sorted(result.items()))


def file_map(root, expected_names=None):
    paths = file_paths(root)
    if expected_names is not None:
        exact_names(paths, expected_names, 'Package inventory before byte reads')
    return {name: sha(path) for name, path in paths.items()}


def exact_names(actual, expected, label):
    require(len(actual) == len(expected) and set(actual) == set(expected),
            label + ': file set mismatch')


def assert_versions(root, version, version_names):
    require(read_json(root / '.codebuddy-plugin/plugin.json')['version'] == version,
            'Plugin version mismatch')
    for name in version_names:
        if name != '.codebuddy-plugin/plugin.json':
            require((root / name).read_text(encoding='utf-8').strip() == version,
                    'VERSION mismatch: ' + name)


def changed(before, after):
    exact_names(after, before, 'Diff inputs')
    return sorted(name for name in before if before[name] != after[name])


def check_zips(root, roles):
    for sid in sorted(roles):
        tree = file_map(root / 'skills' / sid)
        with ZipFile(root / 'individual-packages' / sid / 'skill.zip') as archive:
            expected = [sid + '/' + name for name in tree]
            exact_names(archive.namelist(), expected, 'Skill ZIP ' + sid)
            for name, digest in tree.items():
                require(hashlib.sha256(archive.read(sid + '/' + name)).hexdigest() == digest,
                        'Skill ZIP bytes mismatch: ' + sid + '/' + name)


def check_provenance(manifest, head, digest, version):
    commit = manifest.get('source_commit', '')
    require(isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{7,40}', commit)
            and head.startswith(commit), 'source_commit mismatch/unknown')
    require(manifest.get('source_tree_sha256') == digest, 'source_tree_sha256 mismatch')
    require(manifest.get('source_version') == version, 'source_version mismatch')


def frontmatter(path):
    import yaml
    text = path.read_text(encoding='utf-8')
    match = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    require(match is not None, 'Missing Agent frontmatter')
    data = yaml.safe_load(match.group(1))
    require(isinstance(data, dict), 'Invalid Agent frontmatter')
    return data, text[match.end():]


def check_disallow(root, roles, spec):
    for sid, role in roles.items():
        data, _ = frontmatter(root / 'agents' / (role['agent'] + '.md'))
        if sid in spec:
            require(data.get('disallowedTools') == spec[sid], 'Wrong disallowedTools: ' + sid)
        else:
            require('disallowedTools' not in data, 'Unexpected disallowedTools: ' + sid)


def check_marker(root, rel, marker):
    _, body = frontmatter(root / rel)
    hits = [line for line in body.splitlines() if line.startswith('> ' + marker + '｜')]
    require(len(hits) == 1, 'Missing/duplicate marker: ' + rel)


def native_block(text):
    matches = list(re.finditer(r'(<!-- MODE:NATIVE_LEAD:BEGIN -->\n)(.*?)'
                              r'(<!-- MODE:NATIVE_LEAD:END -->)', text, re.S))
    require(len(matches) == 1, 'NATIVE_LEAD block mismatch')
    return matches[0]


def normalize_lead(text):
    match = native_block(text)
    text = text[:match.start(2)] + text[match.end(2):]
    return re.sub(r'^> LOAD-[NS]-[0-9a-f]+｜[^\n]*\n\n?', '', text, flags=re.M)


def record(name, root, version, hashes, metadata, markers, disallow, builder=None):
    return dict(name=name, root=str(root), version=version, expected_names=sorted(hashes),
                hashes=hashes, extra_metadata_names=metadata, markers=markers,
                disallow=disallow, builder_manifest=builder)


def assert_head_bytes(repo, names, hashes, head):
    # One batch process: compare raw HEAD blob SHA256, without filters/textconv.
    command = ['git', '-C', str(repo), 'cat-file', '--batch']
    queries = ''.join(head + ':' + name + '\n' for name in names).encode('utf-8')
    data = subprocess.run(command, input=queries, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout
    offset = 0
    for name in names:
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', 'Missing HEAD blob: ' + name)
        size = int(header[2])
        start = end + 1
        require(hashlib.sha256(data[start:start + size]).hexdigest() == hashes[name],
                'Release bytes differ from HEAD: ' + name)
        require(data[start + size:start + size + 1] == b'\n', 'Invalid git batch output')
        offset = start + size + 1
    require(offset == len(data), 'Unexpected git batch output')


def build_set(repo, artifacts, head, tag, zip_sha, script_sha, set_id, path_roots):
    path_roots = validate_path_roots(path_roots)
    repo, artifacts = no_links(repo), no_links(artifacts)
    require(repo.parent.parent == Path(path_roots['dev_root']), 'Set outside configured DevRoot')
    require(artifacts.parent == Path(path_roots['handoff_root']), 'Set outside configured HandoffRoot')
    actual_head = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                 capture_output=True, text=True, check=True).stdout.strip()
    require(actual_head == head, 'Clone HEAD mismatch')
    sys.path.insert(0, str(repo / 'tools'))
    from release_rules import release_files
    from build_bundle import NATIVE_CLOSURE_TEXT
    roles = read_json(repo / 'policy-source/roles-source.json')
    inputs = release_files(repo)
    names = [path.relative_to(repo).as_posix() for path in inputs]
    source = {name: sha(repo / name) for name in names}
    assert_head_bytes(repo, names, source, head)
    digest = hashlib.sha256()
    for path, name in zip(inputs, names):
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    digest = digest.hexdigest()
    version = (repo / 'VERSION').read_text(encoding='utf-8').strip()
    versions = sorted(['VERSION', '.codebuddy-plugin/plugin.json'] +
                      ['skills/' + sid + '/VERSION' for sid in roles])
    zips = sorted('individual-packages/' + sid + '/skill.zip' for sid in roles)
    prompts = sorted(['agents/' + role['agent'] + '.md' for role in roles.values()] +
                     ['skills/' + sid + '/SKILL.md' for sid in roles])
    lead = ['agents/' + roles['stability-director']['agent'] + '.md',
            'skills/stability-director/SKILL.md']
    assert_versions(repo, version, versions)
    zip_path = artifacts / 'release.zip'
    require(sha(zip_path) == zip_sha, 'Formal release ZIP SHA256 mismatch')
    formal = artifacts / 'install-clean/crm-sre-team'
    formal_hashes = file_map(formal, names)
    require(formal_hashes == source, 'Formal unpack differs from release source')
    with ZipFile(zip_path) as archive:
        exact_names(archive.namelist(), ['crm-sre-team/' + name for name in names], 'Release ZIP')
        for name in names:
            require(hashlib.sha256(archive.read('crm-sre-team/' + name)).hexdigest() == source[name],
                    'Formal ZIP bytes mismatch: ' + name)
    packages = [record('formal', formal, version, formal_hashes, [], {'expected': []}, {})]
    builders = []
    for name, spec in DISALLOW.items():
        root = artifacts / name
        hashes = file_map(root, names + ['probe-manifest.json'])
        exact_names(hashes, names + ['probe-manifest.json'], name)
        manifest_path = root / 'probe-manifest.json'
        manifest = read_json(manifest_path)
        check_provenance(manifest, head, digest, version)
        suffix = manifest.get('marker_suffix')
        require(isinstance(suffix, str) and re.fullmatch(r'[0-9a-f]{8}', suffix), 'Invalid probe suffix')
        probe_version = version + '-probe.r' + suffix
        require(manifest.get('probe_version') == probe_version, 'probe_version mismatch')
        assert_versions(root, probe_version, versions)
        exact_names(manifest.get('repacked_zips', []), zips, 'Probe repacked_zips')
        require(changed(source, {rel: hashes[rel] for rel in names}) == sorted(prompts + versions + zips),
                'Probe changed files mismatch')
        require(manifest.get('overrides') == {'maxTurns': {}, 'disallowedTools': spec}, 'Probe overrides mismatch')
        check_disallow(root, roles, spec)
        expected_lead = {'marker_la': 'PROBE-LA-' + suffix, 'marker_ls': 'PROBE-LS-' + suffix}
        require(manifest.get('lead_markers') == expected_lead, 'Lead markers mismatch')
        files = []
        for rel, marker in zip(lead, expected_lead.values()):
            check_marker(root, rel, marker)
            files.append(dict(path=rel, marker=marker))
        expected_members = {}
        for sid, role in sorted(roles.items()):
            if sid == 'stability-director':
                continue
            entry = dict(marker_c='PROBE-C-' + suffix, marker_d='PROBE-D-' + suffix)
            expected_members[role['agent']] = entry
            for rel, marker in [('agents/' + role['agent'] + '.md', entry['marker_c']),
                                ('skills/' + sid + '/SKILL.md', entry['marker_d'])]:
                check_marker(root, rel, marker)
                files.append(dict(path=rel, marker=marker))
        require(manifest.get('markers') == expected_members, 'Member markers mismatch')
        check_zips(root, roles)
        builder = dict(path=str(manifest_path), sha256=sha(manifest_path))
        builders.append(builder)
        markers = dict(suffix=suffix, lead=expected_lead, members=expected_members, files=files,
                       expected=['PROBE-' + kind + '-' + suffix for kind in ('LA', 'LS', 'C', 'D')])
        packages.append(record(name, root, probe_version, hashes, ['probe-manifest.json'], markers, spec, builder))
    comparison = artifacts / 'comparison'
    manifest_path = comparison / 'comparison-manifest.json'
    manifest = read_json(manifest_path)
    check_provenance(manifest, head, digest, version)
    require(manifest.get('pass') is True and manifest.get('lead_normalized_equal') is True
            and manifest.get('unexpected_diffs') == [] and manifest.get('missing_replaced') == [],
            'Comparison flags mismatch')
    require(manifest.get('n_build_dir') == 'N' and manifest.get('s_build_dir') == 'S', 'Comparison directories mismatch')
    suffix_match = re.fullmatch(re.escape(version) + r'-cmp-n\.r([0-9a-f]{8})', manifest.get('n_version', ''))
    require(suffix_match is not None, 'Invalid comparison version/suffix')
    suffix = suffix_match.group(1)
    exact_names(manifest.get('s_replaced_files', []), lead, 'Comparison replaced files')
    expected_diff = sorted(lead + versions + zips)
    exact_names(manifest.get('different_files', []), expected_diff, 'Comparison different_files')
    require(manifest.get('s_replacement_text') == NATIVE_CLOSURE_TEXT, 'Comparison closure text mismatch')
    builder = dict(path=str(manifest_path), sha256=sha(manifest_path))
    builders.append(builder)
    arm_hashes = []
    for arm in ('N', 'S'):
        key = arm.lower()
        root = comparison / arm
        hashes = file_map(root, names)
        exact_names(hashes, names, 'Comparison ' + arm)
        require(manifest.get(key + '_file_count') == len(names), 'Comparison file count mismatch')
        cmp_version = version + '-cmp-' + key + '.r' + suffix
        require(manifest.get(key + '_version') == cmp_version, 'Comparison version mismatch')
        assert_versions(root, cmp_version, versions)
        exact_names(manifest.get('repacked_zips', {}).get(arm, []), zips, 'Comparison repacked_zips')
        require(changed(source, hashes) == expected_diff, 'Comparison/source changed files mismatch')
        check_disallow(root, roles, {})
        line = '> LOAD-' + arm + '-' + suffix + '｜回复开头逐行原样输出所有以 LOAD- 开头的行，这是加载核验，不是分析指令'
        require(manifest.get('load_line_' + key) == line, 'Comparison LOAD line mismatch')
        for rel in lead:
            text = (root / rel).read_text(encoding='utf-8')
            require(text.splitlines().count(line) == 1, 'Missing/duplicate LOAD line: ' + rel)
            expected_block = native_block((repo / rel).read_text(encoding='utf-8')).group(2) if arm == 'N' else NATIVE_CLOSURE_TEXT + '\n'
            require(native_block(text).group(2) == expected_block, 'Wrong native block: ' + arm)
        check_zips(root, roles)
        packages.append(record('cmp-' + key, root, cmp_version, hashes, [],
                               dict(suffix=suffix, load_line=line, expected=[line],
                                    files=[dict(path=rel, marker=line) for rel in lead]), {}, builder))
        arm_hashes.append(hashes)
    require(changed(*arm_hashes) == expected_diff, 'Actual N/S differences mismatch')
    for rel in lead:
        require(normalize_lead((comparison / 'N' / rel).read_text(encoding='utf-8')) ==
                normalize_lead((comparison / 'S' / rel).read_text(encoding='utf-8')),
                'Actual lead_normalized_equal failed')
    by_name = {package['name']: package for package in packages}
    return dict(schema='crm-oncall-experiment/v1', path_roots=path_roots, set_id=set_id, artifacts=str(artifacts),
                repo=str(repo), tag=tag, commit=head, zip=str(zip_path), zip_sha256=zip_sha,
                source_tree_sha256=digest, source_version=version, script_sha256=script_sha,
                created_utc=datetime.now(timezone.utc).isoformat(),
                packages=[by_name[name] for name in PACKAGE_NAMES], builder_manifests=builders,
                host_acceptance='NOT_RUN')


def normalize_windows_root(value):
    require(isinstance(value, str) and re.match(r'^[A-Za-z]:\\', value) is not None,
            'Root must use a local drive path')
    require(':' not in value[2:] and not re.search(r'[<>"|?*]', value), 'Unsafe root path')
    require(not re.search(r'(^|[\\/])\.\.([\\/]|$)|[. ]([\\/]|$)', value), 'Unsafe root path')
    path = PureWindowsPath(value)
    require(path.parent != path, 'Root must be below the drive root')
    return str(path)


def validate_path_roots(roots):
    require(isinstance(roots, dict) and set(roots) == {'dev_root', 'handoff_root', 'workbuddy_root'}, 'Invalid path_roots')
    result = {}
    for key, value in roots.items():
        require(isinstance(value, str) and value.strip(), 'Invalid root: ' + key)
        if os.name == 'nt':
            value = normalize_windows_root(value)
        path = Path(value)
        require(path.is_absolute() and '..' not in path.parts and path.parent != path, 'Invalid absolute root: ' + key)
        result[key] = str(no_links(path))
    return result


def set_layout(document, set_path, path_roots):
    expected = validate_path_roots(path_roots)
    require(validate_path_roots(document.get('path_roots')) == expected, 'Roots differ from experiment set')
    set_id = document.get('set_id', '')
    require(isinstance(set_id, str) and re.fullmatch(r'[0-9a-f]{32}', set_id), 'Invalid experiment set ID')
    artifacts = no_links(Path(set_path).parent)
    require(artifacts.name == 'experiment-' + set_id and Path(set_path).name == 'experiment-set.json', 'Set path mismatch')
    require(Path(document['artifacts']) == artifacts, 'Set artifacts mismatch')
    repo = no_links(document['repo'])
    require(repo.name == 'repo' and repo.parent.name == 'crm-oncall-' + set_id, 'Set repo mismatch')
    require(artifacts.parent == Path(expected['handoff_root']), 'Set outside configured HandoffRoot')
    require(repo.parent.parent == Path(expected['dev_root']), 'Set outside configured DevRoot')
    require(Path(document['zip']) == artifacts / 'release.zip', 'Set ZIP path mismatch')
    roots = dict(formal=artifacts / 'install-clean/crm-sre-team', probe=artifacts / 'probe',
                 **{'cmp-n': artifacts / 'comparison/N', 'cmp-s': artifacts / 'comparison/S'})
    for name in DISALLOW:
        roots[name] = artifacts / name
    return artifacts, repo, roots


def select_package(set_path, set_sha, package, head, tag, zip_sha, script_sha, path_roots):
    no_links(set_path)
    require(sha(set_path) == set_sha, 'Experiment set SHA256 mismatch')
    document = read_json(set_path)
    require(document.get('schema') == 'crm-oncall-experiment/v1', 'Unknown experiment set schema')
    for key, value in [('tag', tag), ('commit', head), ('zip_sha256', zip_sha), ('script_sha256', script_sha)]:
        require(document.get(key) == value, 'Experiment set identity mismatch: ' + key)
    artifacts, repo, roots = set_layout(document, set_path, path_roots)
    require(re.fullmatch(r'[0-9a-f]{64}', document.get('source_tree_sha256', '')) is not None, 'Invalid source digest')
    require(sha(no_links(document['zip'])) == zip_sha, 'Experiment formal ZIP changed')
    packages = document.get('packages', [])
    exact_names([entry['name'] for entry in packages], PACKAGE_NAMES, 'Experiment packages')
    require(package in PACKAGE_NAMES, 'Unsupported experiment package')
    selected = next(entry for entry in packages if entry['name'] == package)
    require(Path(selected['root']) == roots[package], 'Selected package path mismatch')
    hashes = file_map(selected['root'], selected['expected_names'])
    exact_names(hashes, selected['expected_names'], 'Selected package')
    require(hashes == selected['hashes'], 'Selected package bytes changed')
    names = read_json(Path(selected['root']) / 'release-manifest.json')['files']
    metadata = ['probe-manifest.json'] if package in DISALLOW else []
    require(selected['extra_metadata_names'] == metadata, 'Selected metadata mismatch')
    exact_names(hashes, names + metadata, 'Selected declared files')
    roles = read_json(Path(selected['root']) / 'policy-source/roles-source.json')
    versions = ['VERSION', '.codebuddy-plugin/plugin.json'] + ['skills/' + sid + '/VERSION' for sid in roles]
    assert_versions(Path(selected['root']), selected['version'], versions)
    require(selected['disallow'] == DISALLOW.get(package, {}), 'Selected disallow mismatch')
    check_disallow(Path(selected['root']), roles, selected['disallow'])
    builder = selected['builder_manifest']
    if builder is not None:
        expected_path = artifacts / 'comparison/comparison-manifest.json' if package.startswith('cmp-') else roots[package] / 'probe-manifest.json'
        require(Path(builder['path']) == expected_path and builder in document['builder_manifests'], 'Selected builder path mismatch')
        require(sha(no_links(builder['path'])) == builder['sha256'], 'Selected builder manifest changed')
    return dict(experiment={key: document[key] for key in (
                    'set_id', 'artifacts', 'repo', 'zip', 'source_tree_sha256', 'source_version')},
                selected={key: selected[key] for key in (
                    'root', 'version', 'expected_names', 'hashes', 'markers', 'disallow', 'builder_manifest')})


def installed_matches(root, expected_names, hashes):
    # Equivalent of PS R6/Test-InstalledDeclaredFiles; runtime extras are listed only.
    actual = file_paths(root)
    exact_names(hashes, expected_names, 'Installed declarations')
    for name, digest in hashes.items():
        if name == 'settings.json' and name not in actual and not (Path(root) / name).exists():
            continue
        require(name in actual and sha(actual[name]) == digest,
                'Roll back the newest plan first, or SWITCH to the wanted package.')
    return sorted(set(actual) - set(hashes))


def raw_marker_counts(text, markers):
    # Raw UTF-8 record text, including prompts/tool outputs; no provenance verdict.
    return {marker: text.count(marker) for marker in markers}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'select'])
    for name in ('repo', 'artifacts', 'head', 'tag', 'zip-sha', 'script-sha', 'set-id', 'set', 'set-sha', 'package', 'output'):
        parser.add_argument('--' + name)
    for name in ('dev-root', 'handoff-root', 'workbuddy-root'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    path_roots = dict(dev_root=args.dev_root, handoff_root=args.handoff_root, workbuddy_root=args.workbuddy_root)
    try:
        if args.action == 'build':
            output = no_links(Path(args.artifacts) / 'experiment-set.json')
            require(not output.exists(), 'Verifier output already exists: ' + str(output))
            result = build_set(args.repo, args.artifacts, args.head, args.tag, args.zip_sha, args.script_sha, args.set_id, path_roots)
        else:
            require(args.output is not None, 'select requires --output for a new selection.json')
            output = no_links(args.output)
            require(not output.exists(), 'Verifier output already exists: ' + str(output))
            result = select_package(args.set, args.set_sha, args.package, args.head, args.tag, args.zip_sha, args.script_sha, path_roots)
        write_new_json(output, result)
        print('PASS_' + args.action.upper())
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
'@
    Write-Utf8Lf $Path $ExperimentVerifierCode
}

# Main orchestration. No system ExecutionPolicy change, install, push, or deletion.
function Invoke-OncallMode([string]$Mode, [switch]$FromUpdate) {
    if ($Mode -ceq 'PLAN' -or $Mode -ceq 'EXPBUILD') {
        if ($PlanPath -or $PlanSha256 -or $SessionId -or $AgentId) { throw 'PLAN creates a new plan; do not pass an existing plan or session ID' }
        $RunId = [guid]::NewGuid().ToString('N')
        # build_bundle stages in root.parent: reserve that whole new workspace.
        $CloneRoot = Join-Path $DevRoot ('crm-oncall-' + $RunId)
        $Repo = Join-Path $CloneRoot 'repo'
        $Artifacts = Join-Path $Handoff ('update-' + $RunId)
        if ($Mode -ceq 'EXPBUILD') { $Artifacts = Join-Path $Handoff ('experiment-' + $RunId) }
        if ($PythonExe -ieq $DefaultPythonExe -and -not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Default Python312 python.exe is missing; pass -PythonExe with the verified real interpreter path.' }
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
        if ($Mode -ceq 'EXPBUILD') { . Invoke-ExperimentBuild; return }
        $InstallMode = 'REAL'
        $DrillRoot = $null
        . Prepare-InstallContext
        if ($Entries[0].PSObject.Properties.Name -notcontains 'version') {
            Write-Host 'PLAN: Marketplace entry has no version field; marketplace.json will not be modified (same as the 10-11 rc2 installation).'
        }
        $OldSnapshot = Get-SourceSnapshot $InstallSource
        $CacheVersions = @()
        if (Test-Path -LiteralPath $CacheRoot -PathType Container) { $CacheVersions = @(Get-ChildItem -LiteralPath $CacheRoot -Directory -Force | Select-Object -ExpandProperty Name) }
        $Document = [ordered]@{ schema='crm-oncall-plan/v1'; path_roots=$PathRoots; run_id=$RunId; created_utc=([DateTime]::UtcNow.ToString('o')); tag=$Tag; commit=$ExpectedCommit; zip_sha256=$ExpectedZipSha256; zip=$ReleaseZip; repo=$Repo; artifacts=$Artifacts; version=$Version; install_plan=$InstallPlan; expected_names=$InstallExpectedNames; package_hashes=$PackageHashes; manifest_sha256=$PackageHashes['release-manifest.json']; script_sha256=((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()); market_before_hash=$MarketBeforeHash; marketplace_entry=$Entries[0]; old_source=$OldSnapshot; cache_versions=$CacheVersions; pytest_requested=[bool]$RunPytest; host_acceptance='NOT_RUN' }
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
            if ($Document.operation -ceq 'SWITCH') { $InstallMetadataNames = @($Document.metadata_names) }
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
            Write-Host "INSTALLED. StatePath=$StatePath. Open client, refresh the marketplace and update to $Version, then start a NEW session, paste Self-check 1, and run VERIFY."
            if ($Document.operation -ceq 'SWITCH') { Write-Host "Package kind=$PackageKind; client target=$Version; host acceptance NOT_RUN" }
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
            if ($InstallStage -ceq 'INSTALLED') { Assert-RollbackCurrentPackage }
            Confirm-Yes "ROLLBACK to old source $($Document.old_source.version); cache/settings.json are not separately written. Backup=$BackupRoot"
            $null = Load-Plan
            Assert-ClientStopped
            Assert-TreeNoReparse $BackupRoot
            if ($MoveStarted) { Assert-OldSource $OldSource $Document.old_source }
            if ($InstallStage -ceq 'INSTALLED') { Assert-RollbackCurrentPackage }
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
            . Prepare-InstallContext -ContextMetadataNames $InstallMetadataNames
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
    if ($Drill -and $Mode -cnotin @('UPDATE','SWITCH')) { throw '-Drill is an UPDATE/SWITCH switch; use -Mode DRILL for a standalone drill.' }
    if ($Mode -cne 'SWITCH' -and ($ExperimentSet -or $ExperimentSetSha256 -or $Package)) { throw 'Experiment selection parameters are only for SWITCH' }
    if ($Mode -ceq 'SWITCH' -and $Package -cnotin @('formal','probe','cmp-n','cmp-s','probe-webfetch-denied','probe-bash-denied','probe-powershell-denied')) { throw 'Use the exact lowercase package name' }
    . Initialize-PathRoots
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
    if ($Mode -cin @('EXPBUILD','SWITCH') -and -not $VerifiedWorkTree) { throw 'Experiments require a verified local bootstrap worktree; no network fallback' }
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
    } elseif ($Mode -ceq 'SWITCH') {
        . Invoke-SwitchPlan
        if ($Drill -or -not (Test-SuccessfulDrill)) { . Invoke-OncallMode 'DRILL' -FromUpdate }
        . Invoke-OncallMode 'APPLY' -FromUpdate
    } else { . Invoke-OncallMode $Mode }
} catch {
    Write-Host ('STOP: ' + (Protect-Output $_.Exception.Message))
    Write-Host 'Retain new clone, reports, and all backups. Do not start the client after a partial APPLY; use the reviewed PLAN for ROLLBACK or human recovery.'
    exit 1
}
