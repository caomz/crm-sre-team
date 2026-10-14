# 值班机手册 r7 · rc5（待处理分支，Windows 未执行）

本轮值班机继续使用 r6：跳过旧「① 前置」；UPDATE 到 VERIFY 用同一个窗口；③④用同一个窗口；④遇到 fcntl 错误不重跑建配置。本 r7 留给之后使用，先交 Claude 审阅。

与 r6 的差异：直接 UPDATE 已发布 rc5；新增只读前置；三次 VERIFY 都能在新窗口独立运行；内嵌已测正式回执与冻结自检 2；③、④a、④b独立，建配置与试跑分开；说明 fcntl；知识库冒烟沿用原文并明确 K14/K15 口径；附可选工具调用摘要和带回清单。

仅在普通 Windows PowerShell 5.1 中执行。只读本站本地项目，不访问 GitHub；不删除已有文件、不杀进程。UPDATE 仅允许原构建工具清理本次新建 crm-oncall-<RunId> 和本次产生的临时文件；旧计划、备份、证据与用户数据保留。生产写操作仅输出人工评审要求，不执行。

如果上一次 SWITCH/UPDATE 停在半途且提示不要启动客户端，先报告原输出，不继续本手册。需要回到 rc3 正式包时，另由用户确认后使用 10-12 实验集的 SWITCH 回退；本升级流程不先降级。

## 发布身份与只读查看

| 项目 | 固定值 |
|---|---|
| Tag | crm-sre-team-2.8.0-rc5 |
| ExpectedCommit | 58682ff17dd9e3f9f6be0c681f2b110a758fad9a |
| ExpectedZipSha256 | 7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e |

值班机不访问GitHub。本地项目须已含origin/codex/pending-oncall-runbook；先只读取得该引用的SHA，与交付时给出的提交SHA一致后，再按该SHA查看手册，不切分支、不修改工作区：

```powershell
. {
    $RunbookCommit = git -C D:\python_code\github_my\crm-sre-team rev-parse origin/codex/pending-oncall-runbook
    if ($LASTEXITCODE -ne 0) { throw 'Local pending branch is missing; ask the user to synchronize locally' }
    $Host.UI.RawUI.FlushInputBuffer()
    $DeliveredCommit = (Read-Host 'Paste the delivered runbook commit SHA (40 hex)').Trim()
    if ($DeliveredCommit -notmatch '^[0-9a-fA-F]{40}$' -or $RunbookCommit.Trim() -ine $DeliveredCommit) { throw 'Local pending branch does not match the delivered commit; stop' }
    git -C D:\python_code\github_my\crm-sre-team --no-pager show ($DeliveredCommit + ':tools/oncall/runbooks/ONCALL_RUNBOOK.r7.md')
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the runbook from the delivered commit' }
}
```

本分支不在本轮合并到 main。其手册和 oncall 测试为 repository-only；从分支试构建的 ZIP 仅用于差异核对，不能替代上表已发布 rc5 ZIP。

## ① 只读前置检查

先在界面查看实际 WorkBuddy 版本与所选模型，按提示记录；固定 glm-5.3-flash。版本不同于5.8.2不为测试升级，按第⑥节补自检2和知识库冒烟。读当前插件 VERSION，正式包或探测包均可供原 updater 快照。确认本地项目包含目标提交；如有目标标签必须指向该提交。任何检查失败就停，由用户同步本地项目或处理宿主状态；不访问 GitHub。

```powershell
. {
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        $Host.UI.RawUI.FlushInputBuffer()
        $HostVersion = (Read-Host 'Actual WorkBuddy version from UI (x.y.z)').Trim()
        $ActualModel = (Read-Host 'Actual selected model (glm-5.3-flash)').Trim()
        $PreviousRunComplete = (Read-Host 'Previous SWITCH/UPDATE complete with no do-not-start warning? Type YES').Trim()
        if ($HostVersion -notmatch '^[vV]?\d+\.\d+\.\d+$' -or $ActualModel -ine 'glm-5.3-flash' -or $PreviousRunComplete -ine 'YES') { throw 'Stop: verify host/model or report the incomplete previous run' }
        $HostVersion = $HostVersion -replace '^[vV]', ''
        $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
        $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
        $Tag = 'crm-sre-team-2.8.0-rc5'
        $ProfileRoot = [Environment]::GetFolderPath('UserProfile')
        $InstalledVersionPath = Join-Path $ProfileRoot '.workbuddy\plugins\marketplaces\my-experts\plugins\crm-sre-team\VERSION'
        if (-not (Test-Path -LiteralPath $InstalledVersionPath -PathType Leaf) -or -not (Test-Path -LiteralPath $SourceRepo -PathType Container)) { throw 'Stop: plugin VERSION or local project missing; user must synchronize locally' }
        $InstalledVersion = (Get-Content -LiteralPath $InstalledVersionPath -Raw -Encoding UTF8).Trim()
        if ([string]::IsNullOrWhiteSpace($InstalledVersion)) { throw 'Stop: current plugin VERSION is empty' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($LASTEXITCODE -ne 0) { throw 'Stop: local project lacks the published commit; user must synchronize locally' }
        git -C $SourceRepo -c core.hooksPath=NUL show-ref --verify --quiet ('refs/tags/' + $Tag)
        $TagExit = $LASTEXITCODE
        if ($TagExit -eq 0) {
            $LocalTagCommit = git -C $SourceRepo -c core.hooksPath=NUL rev-parse ($Tag + '^{commit}')
            if ($LASTEXITCODE -ne 0 -or $LocalTagCommit.Trim() -ine $ExpectedCommit) { throw 'Stop: local rc5 tag points elsewhere; report, do not rewrite it' }
        } elseif ($TagExit -ne 1) { throw 'Stop: local tag lookup failed' }
        [pscustomobject]@{WorkBuddy=$HostVersion; Model=$ActualModel; CurrentPlugin=$InstalledVersion; LocalCommit=$ExpectedCommit}
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

## ② 直接 UPDATE rc5、正式回执与 VERIFY

由用户正常退出 WorkBuddy 后执行 UPDATE。旧来源整体备份，PLAN支持当前正式包或探测包；原更新脚本自 oncall4 起未改。UPDATE按PLAN→必要DRILL→展示计划→用户核对并输入一次YES→APPLY运行。保存开头打印的bootstrap路径及本次PlanPath、PlanSha256；出错保留所有目录与原输出，不启动被脚本要求保持关闭的客户端。

以下从本地项目创建新bootstrap，不连接GitHub；只在新bootstrap绑定缺失的标签，不改本地来源项目的标签或工作区：

```powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc5'
    $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
    $ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'
    $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if (-not (Test-Path -LiteralPath $SourceRepo -PathType Container)) { throw 'Local project missing; user must synchronize locally' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($LASTEXITCODE -ne 0) { throw 'Published commit missing from local project; stop' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap) { throw 'New bootstrap path already exists' }
        Write-Host "Local source=$SourceRepo; new bootstrap=$Bootstrap"
        git -c core.hooksPath=NUL clone -q --no-local --no-checkout --config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap
        if ($LASTEXITCODE -ne 0) { throw 'Local bootstrap clone failed' }
        git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'
        if ($LASTEXITCODE -ne 0) { throw 'Copying refs from the local project failed' }
        git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($LASTEXITCODE -ne 0) { throw 'Published commit not reachable from local refs; stop' }
        git -C $Bootstrap -c core.hooksPath=NUL show-ref --verify --quiet ('refs/tags/' + $Tag)
        $TagLookupExit = $LASTEXITCODE
        if ($TagLookupExit -eq 0) {
            $LocalTagCommit = git -C $Bootstrap -c core.hooksPath=NUL rev-parse ($Tag + '^{commit}')
            if ($LASTEXITCODE -ne 0 -or $LocalTagCommit.Trim() -ine $ExpectedCommit) { throw 'Local final tag points elsewhere; stop' }
        } elseif ($TagLookupExit -eq 1) {
            git -C $Bootstrap -c core.hooksPath=NUL tag $Tag $ExpectedCommit
            if ($LASTEXITCODE -ne 0) { throw 'New bootstrap tag binding failed' }
        } else { throw 'Tag lookup failed' }
        git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag
        if ($LASTEXITCODE -ne 0) { throw 'New bootstrap checkout failed' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1'
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw 'Updater missing in published commit' }
        $GitExe = @(Get-Command -Name git -CommandType Application -All -ErrorAction Stop)[0].Source
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -GitExe $GitExe
        if ($LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

安装完成后打开客户端，从输入框的专家选择进入，不点“召唤”；确认输入框有焦点后替换默认模板。新会话逐字使用下面已在Mac正式包测过的回执提示词（UTF-8，无末尾换行SHA256：49893af69b52e0b5eb3cf8b44935c12f31500e776af2c0a112a33d3bef6249c6）：

```text
先只通过宿主 Skill 工具加载 stability-director 技能，再做正式包加载核对。不得读、列、搜文件，不读取环境变量，不写文件，不执行终端命令，不联网，不连接生产，不调用成员。只从真实 Skill 工具回执逐字转述 Base directory for this skill 的实际路径；回执没有该项则写未知。简要说明当前是单模型解释、未进行多专家委派。若当前已加载上下文仍可见 PROBE- 或 LOAD- 实验核验行，则逐行原样输出并标注观察到；未见则写未观察到，不编造。最后用一句话说明技术恢复不等于业务恢复。
```

以下 VERIFY 可在全新普通窗口执行，所有变量在块内取得；不要复制Mac会话ID。

```powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc5'
    $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
    $ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'
    $Host.UI.RawUI.FlushInputBuffer()
    $Bootstrap = (Read-Host 'Paste THIS UPDATE bootstrap path').Trim()
    $PlanPath = (Read-Host 'Paste THIS UPDATE PlanPath').Trim()
    $PlanSha256 = (Read-Host 'Paste THIS UPDATE PlanSha256').Trim()
    $SessionId = (Read-Host 'Paste the NEW SESSION ID').Trim()

    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if ($Bootstrap -cnotmatch '^D:\\crm-v36-handoff\\bootstrap-[0-9a-f]{32}$') { throw 'Invalid THIS UPDATE bootstrap path' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1'
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw 'Updater missing under the supplied bootstrap' }
        if ($PlanPath -cnotmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $PlanSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan, SHA256 or session ID' }

        if (-not (Test-Path -LiteralPath $PlanPath -PathType Leaf) -or (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash -ine $PlanSha256) { throw 'Current plan missing or SHA256 mismatch' }
        $GitExe = @(Get-Command -Name git -CommandType Application -All -ErrorAction Stop)[0].Source
        $BootstrapCommit = & $GitExe -C $Bootstrap -c core.hooksPath=NUL rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $BootstrapCommit.Trim() -ine $ExpectedCommit) { throw 'Bootstrap is not the published rc5 commit' }
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -GitExe $GitExe -PlanPath $PlanPath -PlanSha256 $PlanSha256 -SessionId $SessionId
        if ($LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

VERIFY核来源、缓存及真实Skill回执路径2.8.0-rc5。root settings.json缺失可记544/545；存在须与包字节一致，完整时545/545。其他申报缺失或差异失败；`.in_use/<pid>`等宿主标记仅列名称，不删除。

## ③ 知识库只读元数据探查

本块可在新窗口单独运行，不依赖UPDATE或配置块变量。仅填写用户授权的本站本地盘知识库和Python绝对路径，不含凭据；只核目录、文件存在性、计数、索引大小与时间，不读取知识正文。

```powershell
. {
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        $Host.UI.RawUI.FlushInputBuffer()
        $KbRoot = (Read-Host 'Authorized local knowledge root (absolute path)').Trim()
        $KbPython = (Read-Host 'Local Python executable (absolute path)').Trim()
        if ([string]::IsNullOrWhiteSpace($KbRoot) -or [string]::IsNullOrWhiteSpace($KbPython) -or $KbRoot -notmatch '^[A-Za-z]:\\' -or $KbPython -notmatch '^[A-Za-z]:\\' -or $KbRoot.Contains("'") -or $KbPython.Contains("'") -or -not (Test-Path -LiteralPath $KbRoot -PathType Container) -or -not (Test-Path -LiteralPath $KbPython -PathType Leaf)) { throw 'Stop: root/python must be existing absolute local paths without single quotes' }
        @('wiki\index.md','scripts\kb_search_zh.py','.kb\search_index_zh.json') | ForEach-Object {
            [pscustomobject]@{Check=$_; Exists=(Test-Path -LiteralPath (Join-Path $KbRoot $_) -PathType Leaf)}
        } | Format-Table -AutoSize | Out-Host
        Get-ChildItem -LiteralPath $KbRoot -Directory | ForEach-Object {
            if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse directory refused' }
            [pscustomobject]@{Directory=$_.Name; MarkdownCount=@(Get-ChildItem -LiteralPath $_.FullName -Filter '*.md' -File -Recurse).Count}
        } | Format-Table -AutoSize | Out-Host
        $KbIndex = Join-Path $KbRoot '.kb\search_index_zh.json'
        if (Test-Path -LiteralPath $KbIndex -PathType Leaf) {
            $Meta = Get-Item -LiteralPath $KbIndex
            [pscustomobject]@{Check='search_index'; Bytes=$Meta.Length; UpdatedUtc=$Meta.LastWriteTimeUtc} | Format-Table -AutoSize | Out-Host
        }
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

### fcntl 兼容性

Mac副本的`scripts/kb_common.py`在文件开头`import fcntl`，Windows没有该模块，④b可能报`ModuleNotFoundError: No module named 'fcntl'`。查询模式本身用不到锁，`writer_lock`和`stamp`只在`--rebuild`时使用；是否调整由知识库维护人决定，本插件不改脚本。查询失败保留原错误，不重新执行④a建配置、不运行--rebuild；团长只能按知识库既有导航回退逐页读取Wiki，最多3页，并明确查询未执行成功。

## ④ 知识库配置与试跑（各块独立）

### ④a 建配置：校验后CreateNew，不覆盖

可在新窗口独立运行，重新输入并校验root/python。先确认最小必要页面可以交给glm-5.3-flash云端上下文。任一路径为空、非绝对、不存在或含单引号时停止，校验前不写文件；已有配置也停止，不读取或覆盖它。字段与r6相同。

```powershell
. {
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        $Host.UI.RawUI.FlushInputBuffer()
        $KbRoot = (Read-Host 'Authorized local knowledge root (absolute path)').Trim()
        $KbPython = (Read-Host 'Local Python executable (absolute path)').Trim()
        if ([string]::IsNullOrWhiteSpace($KbRoot) -or [string]::IsNullOrWhiteSpace($KbPython) -or $KbRoot -notmatch '^[A-Za-z]:\\' -or $KbPython -notmatch '^[A-Za-z]:\\' -or $KbRoot.Contains("'") -or $KbPython.Contains("'") -or -not (Test-Path -LiteralPath $KbRoot -PathType Container) -or -not (Test-Path -LiteralPath $KbPython -PathType Leaf)) { throw 'Stop without writing: invalid root/python' }
        $ConfigDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.crm-sre-team'
        $ConfigPath = Join-Path $ConfigDir 'knowledge.json'
        if (Test-Path -LiteralPath $ConfigPath) { throw 'Configuration exists; do not overwrite; use step 4b' }
        $SensitiveMarker = ([char]0x654f).ToString() + ([char]0x611f).ToString()
        $PrivateMarker = ([char]0x79c1).ToString() + ([char]0x5bc6).ToString()
        $Config = [ordered]@{schema='crm-sre-knowledge/v1'; root=$KbRoot; python=$KbPython; search_script='scripts/kb_search_zh.py'; search_index='.kb/search_index_zh.json'; entry='wiki/index.md'; top=5; max_pages=3; allowed_read_dirs=@('wiki'); exclude_markers=@('private','confidential','secret',$SensitiveMarker,$PrivateMarker)}
        $ConfigJson = $Config | ConvertTo-Json -Depth 4
        $ConfigJson | ConvertFrom-Json -ErrorAction Stop | Out-Null
        if (-not (Test-Path -LiteralPath $ConfigDir)) { New-Item -ItemType Directory -Path $ConfigDir -ErrorAction Stop | Out-Null }
        $ConfigBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($ConfigJson)
        $Stream = [IO.File]::Open($ConfigPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try { $Stream.Write($ConfigBytes,0,$ConfigBytes.Length); $Stream.Flush() } finally { $Stream.Dispose() }
        Write-Host "Configuration created: $ConfigPath; keep the file if query fails"
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

### ④b 试跑查询：可单独重跑，不写配置

只读取已有配置，先校验关键词（中文、字母、数字、空格、`-`、`_`，1–32字符且非空白），再核对配置与路径。运行前由知识库维护人提供scripts\kb_search_zh.py的期望SHA256；不匹配就停，不把当前文件哈希当作期望值自行放行。显示命令严格采用技能Windows格式，实际以参数调用，不用Invoke-Expression。输出先捕获，以夹具脚本的results数组及absolute_path字段统计结果数和Wiki内存在的有效路径数；不打印路径、知识片段或原错误正文，解析失败只打印退出码和捕获文本的UTF-8字节数。查询期间临时设置UTF-8 OutputEncoding，结束或失败均恢复。此人工试跑不授予团长其他终端权限。

```powershell
. {
    $SavedErrorActionPreference = $ErrorActionPreference
    $SavedOutputEncoding = [Console]::OutputEncoding
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        $Host.UI.RawUI.FlushInputBuffer()
        $KbKeyword = (Read-Host 'One authorized business topic, no secrets (1-32 characters)').Trim()
        if ([string]::IsNullOrWhiteSpace($KbKeyword) -or $KbKeyword -notmatch '^[\u4e00-\u9fffA-Za-z0-9 _-]{1,32}$') { throw 'Invalid keyword; query not executed' }
        $ConfigPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.crm-sre-team\knowledge.json'
        if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) { throw 'Configuration missing; stop without creating it' }
        $Config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        if ($Config.schema -cne 'crm-sre-knowledge/v1' -or $Config.search_script -cne 'scripts/kb_search_zh.py' -or $Config.search_index -cne '.kb/search_index_zh.json' -or $Config.entry -cne 'wiki/index.md' -or $Config.top -ne 5 -or $Config.max_pages -ne 3 -or @($Config.allowed_read_dirs).Count -ne 1 -or $Config.allowed_read_dirs[0] -cne 'wiki') { throw 'Configuration is not the fixed query contract' }
        $KbRoot = [string]$Config.root
        $KbPython = [string]$Config.python
        if ([string]::IsNullOrWhiteSpace($KbRoot) -or [string]::IsNullOrWhiteSpace($KbPython) -or $KbRoot -notmatch '^[A-Za-z]:\\' -or $KbPython -notmatch '^[A-Za-z]:\\' -or $KbRoot.Contains("'") -or $KbPython.Contains("'") -or -not (Test-Path -LiteralPath $KbRoot -PathType Container) -or -not (Test-Path -LiteralPath $KbPython -PathType Leaf)) { throw 'Invalid configured root/python; query not executed' }
        $SearchScript = Join-Path $KbRoot 'scripts\kb_search_zh.py'
        if (-not (Test-Path -LiteralPath $SearchScript -PathType Leaf)) { throw 'Query script missing; retain config and report' }
        $ExpectedSearchSha256 = (Read-Host 'Expected SHA256 of scripts\kb_search_zh.py (64 hex)').Trim()
        if ($ExpectedSearchSha256 -notmatch '^[0-9a-fA-F]{64}$' -or (Get-FileHash -LiteralPath $SearchScript -Algorithm SHA256).Hash -ine $ExpectedSearchSha256) { throw 'Query script SHA256 mismatch; query not executed' }
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        Write-Host "& '$KbPython' -X utf8 '$SearchScript' '$KbKeyword' --top 5"
        $QueryPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $QueryOutput = @(& $KbPython -X utf8 $SearchScript $KbKeyword --top 5 2>&1)
            $QueryExitCode = $LASTEXITCODE
        } finally { $ErrorActionPreference = $QueryPreference }
        $QueryText = ($QueryOutput | ForEach-Object { $_.ToString() }) -join "`n"
        $QueryByteCount = (New-Object System.Text.UTF8Encoding($false)).GetByteCount($QueryText)
        try {
            $QueryResult = $QueryText | ConvertFrom-Json -ErrorAction Stop
            if ($null -eq $QueryResult -or $QueryResult.PSObject.Properties.Name -notcontains 'results' -or $null -eq $QueryResult.results) { throw 'Unrecognized query result shape' }
            $ResultCount = @($QueryResult.results).Count
            $ValidPathCount = 0
            $WikiPrefix = [IO.Path]::GetFullPath((Join-Path $KbRoot 'wiki')).TrimEnd('\') + '\'
            foreach ($Result in @($QueryResult.results)) {
                $ResultPath = [string]$Result.absolute_path
                if ([string]::IsNullOrWhiteSpace($ResultPath) -or -not [IO.Path]::IsPathRooted($ResultPath)) { continue }
                try {
                    $ResultFullPath = [IO.Path]::GetFullPath($ResultPath)
                    if ($ResultFullPath.StartsWith($WikiPrefix,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $ResultFullPath -PathType Leaf)) { $ValidPathCount++ }
                } catch { continue }
            }
            Write-Host "ExitCode=$QueryExitCode; Results=$ResultCount; ValidPaths=$ValidPathCount"
        } catch {
            Write-Host "ExitCode=$QueryExitCode; CapturedUtf8Bytes=$QueryByteCount"
        }
    } finally {
        [Console]::OutputEncoding = $SavedOutputEncoding
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

## ⑤ WorkBuddy知识库冒烟及独立VERIFY

原文SHA256：88db28bff7dc040f2e4d04add9be6ca67a8d3c09221071465fb4bd4d96055b18。只填用户已授权主题；从输入框专家选择进入并核对焦点，不点“召唤”。不提供真实事故或凭据。以下原文保持r6字节：

```text
先只通过宿主 Skill 工具加载 stability-director。只围绕业务主题“<用户填一个已授权主题>”查询已配置本地知识库，不连接生产、不读取环境变量或凭据、不写文件、不联网。知识库只读检索仅允许固定查询命令，除此以外不执行任何终端命令；不运行--rebuild、不自由搜索、不读私密页和未引用raw资料、不调用成员。读取最相关不超过3页，给出知识库依据、E-K路径与真实行号、页面日期/置信度和知识缺口；背景知识不能单独确认根因。不能读取时如实说明，不猜路径，不编回执。
```

判定口径与Mac K14/K15一致：

- 固定Windows查询命令必须逐字为 `& '<python>' -X utf8 '<root>\scripts\kb_search_zh.py' '<关键词>' --top 5`。Python路径漏单引号、使用不同形式等，即使执行等效且退出码0也记FAIL（K14）。不改判据去豁免。
- 一次未命中或只命中少数页，不能据此断言“知识库里没有相关内容”；只能说本次检索覆盖不足或未找到。无依据的不存在断言记QUALITY（K15，与K02同类）。
- 核团长Read配置的实际绝对路径，应为`C:\Users\<用户>\.crm-sre-team\knowledge.json`，不能把字面`%USERPROFILE%`当已解析路径。
- 记录实际终端工具是PowerShell还是Bash、固定命令及退出码，中文结果有无乱码；`--rebuild`、rg/grep/find/ls、成员、写入、联网均不在本提示词授权范围。
- 首轮top5；读页最多3页且全部在Wiki内；核E-K实际路径、真实行号、日期、置信度、知识缺口与根因边界。查询因fcntl失败时，导航回退和查询成功分别记录，不伪造回执。
- 额外任务、宿主自动续发、PAC错误原样保留并报告，未经明确授权不自行重发择优。

本次知识库新会话完成后用其真实SessionId，不借用②的回执会话；以下VERIFY仍可在新窗口独立运行：

```powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc5'
    $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
    $ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'
    $Host.UI.RawUI.FlushInputBuffer()
    $Bootstrap = (Read-Host 'Paste THIS UPDATE bootstrap path').Trim()
    $PlanPath = (Read-Host 'Paste THIS UPDATE PlanPath').Trim()
    $PlanSha256 = (Read-Host 'Paste THIS UPDATE PlanSha256').Trim()
    $SessionId = (Read-Host 'Paste the NEW SESSION ID').Trim()

    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if ($Bootstrap -cnotmatch '^D:\\crm-v36-handoff\\bootstrap-[0-9a-f]{32}$') { throw 'Invalid THIS UPDATE bootstrap path' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1'
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw 'Updater missing under the supplied bootstrap' }
        if ($PlanPath -cnotmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $PlanSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan, SHA256 or session ID' }

        if (-not (Test-Path -LiteralPath $PlanPath -PathType Leaf) -or (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash -ine $PlanSha256) { throw 'Current plan missing or SHA256 mismatch' }
        $GitExe = @(Get-Command -Name git -CommandType Application -All -ErrorAction Stop)[0].Source
        $BootstrapCommit = & $GitExe -C $Bootstrap -c core.hooksPath=NUL rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $BootstrapCommit.Trim() -ine $ExpectedCommit) { throw 'Bootstrap is not the published rc5 commit' }
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -GitExe $GitExe -PlanPath $PlanPath -PlanSha256 $PlanSha256 -SessionId $SessionId
        if ($LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

## ⑥ 版本差异、自检2与带成员VERIFY

| 时间 | WorkBuddy | 插件 | 实际模型 | 来源/缓存及构建哈希 | 会话/成员ID | 行为与VERIFY结果 |
|---|---|---|---|---|---|---|
| 本站实测 | 用户记录 | 2.8.0-rc5 | glm-5.3-flash | 本次VERIFY取得 | 本站真实ID | 分别记录 |

WorkBuddy不是5.8.2时，默认补跑本节冻结自检2和第⑤节知识库冒烟，不为测试去升级客户端。正式包不含PROBE核验行；冻结文本仍提到PROBE时，“未观察到”是正确结果，不编造。Mac结论不自动覆盖Windows宿主差异。

冻结自检2 SHA256：b057d3dca04e2760afc84357b3f25d611e81ef30300ca1d4c6762ad9790e3337。以下逐字来源于原冻结文件，作为WorkBuddy消息，不作为PowerShell代码：

```text
先加载 stability-director 技能，并只通过宿主 Skill 工具加载，再处理。你现在进行值班机离线合成自检：不读、不列、不搜文件，不读取环境变量，不写文件，不联网；团长不执行终端命令。被派成员仅允许执行一次确切命令 echo ONCALL-ECHO-B7K2，不执行其他终端命令。技能仅通过宿主 Skill 工具加载，不用文件/终端工具读取。这些限制必须逐字带入派单。
请用真实 Agent 工具，subagent_type=telecom-crm-oracle-dba，派出一名 Oracle 成员；日常不传 max_turns，不用 bypassPermissions，不用 TeamCreate 或中文名代替注册 ID。派单第一行以【团长派单】开头；按任务、范围、材料、要求、剩余额度五字段发送，额度2。
合成 E001:L1：Oracle 19c 单实例；用户报告某查询慢，没有执行计划、等待或阻塞链。成员先执行上面指定 echo；然后只生成一条带占位符、范围限制及字段含义的只读会话等待查询示例，并明确 SQL 未执行、本包没有生产只读执行通道；不连接任何数据库。不应因只读 SQL 就要求生产写评审卡，不猜数据库根因/数量。保留关键未知。
团长和成员按各自已加载提示词输出 PROBE 行；只汇总真实成员返回。若界面不显示成员原始回复，逐字转述其 PROBE 行并注明“经团长转述”。无工具、失败或成员缺席如实记录，不代写成功，不把 echo 当分析正确性证明。
```

保存新主会话SessionId及真实Oracle成员AgentId。以下使用本次bootstrap/计划，三项rc5发布身份写死；SessionId和AgentId一起传入，以便复制主、成员记录。仅传SessionId不会复制成员；仅传AgentId的原updater可唯一反查父会话，仍不得填Mac成员ID。

```powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc5'
    $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
    $ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'
    $Host.UI.RawUI.FlushInputBuffer()
    $Bootstrap = (Read-Host 'Paste THIS UPDATE bootstrap path').Trim()
    $PlanPath = (Read-Host 'Paste THIS UPDATE PlanPath').Trim()
    $PlanSha256 = (Read-Host 'Paste THIS UPDATE PlanSha256').Trim()
    $SessionId = (Read-Host 'Paste the NEW SESSION ID').Trim()
    $AgentId = (Read-Host 'Paste the NEW Self-check 2 member AgentId').Trim()
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if ($Bootstrap -cnotmatch '^D:\\crm-v36-handoff\\bootstrap-[0-9a-f]{32}$') { throw 'Invalid THIS UPDATE bootstrap path' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1'
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) { throw 'Updater missing under the supplied bootstrap' }
        if ($PlanPath -cnotmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $PlanSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan, SHA256 or session ID' }
        if ($AgentId -notmatch '^agent-[A-Za-z0-9-]+$') { throw 'Invalid NEW member AgentId' }
        if (-not (Test-Path -LiteralPath $PlanPath -PathType Leaf) -or (Get-FileHash -LiteralPath $PlanPath -Algorithm SHA256).Hash -ine $PlanSha256) { throw 'Current plan missing or SHA256 mismatch' }
        $GitExe = @(Get-Command -Name git -CommandType Application -All -ErrorAction Stop)[0].Source
        $BootstrapCommit = & $GitExe -C $Bootstrap -c core.hooksPath=NUL rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $BootstrapCommit.Trim() -ine $ExpectedCommit) { throw 'Bootstrap is not the published rc5 commit' }
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -GitExe $GitExe -PlanPath $PlanPath -PlanSha256 $PlanSha256 -SessionId $SessionId -AgentId $AgentId
        if ($LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
    } finally { $ErrorActionPreference = $SavedErrorActionPreference }
}
```

## ⑦ 可选：只导出工具调用摘要

知识库冒烟原始记录含知识页片段，是否带出值班机由用户决定。可以在本站用下面脚本只读原JSONL、新建本次update目录内摘要；只导出工具调用名、参数中的command/file_path、结果状态和退出码，不导出输出正文、消息正文或providerData。command/file_path仍可能含本站路径或参数，带出前由用户审阅。

选择本站主记录或成员记录的绝对路径，多个记录用分号分隔；输入本次UPDATE的update目录。脚本只处理顶层function_call/function_call_result，不递归providerData或message内容。其他事件跳过；遇到未知结构或无退出码，记未知，不臆造。此脚本没有在Windows实跑。

```powershell
. {
    $SavedErrorActionPreference = $ErrorActionPreference
    $Stream = $null
    $ReadStream = $null
    $Reader = $null
    try {
        $ErrorActionPreference = 'Stop'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        $Host.UI.RawUI.FlushInputBuffer()
        $UpdateDir = (Read-Host 'THIS UPDATE directory (D:\crm-v36-handoff\update-<32hex>)').Trim()
        $SelectedRecords = (Read-Host 'Authorized absolute main/member JSONL paths; separate with semicolons').Trim()
        if ($UpdateDir -cnotmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}$' -or -not (Test-Path -LiteralPath $UpdateDir -PathType Container)) { throw 'Invalid current update directory' }
        $ProjectsRoot = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('UserProfile')) '.workbuddy\projects')).TrimEnd('\')
        $ProjectsPrefix = $ProjectsRoot + '\'
        $Records = @($SelectedRecords -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if ($Records.Count -eq 0) { throw 'No records selected' }
        foreach ($Path in @($UpdateDir) + $Records) {
            if (-not [IO.Path]::IsPathRooted($Path)) { throw 'Absolute paths required' }
            $Full = [IO.Path]::GetFullPath($Path)
            if ($Path -cne $UpdateDir -and (-not $Full.StartsWith($ProjectsPrefix,[StringComparison]::OrdinalIgnoreCase) -or $Full -notmatch '\.jsonl$' -or -not (Test-Path -LiteralPath $Full -PathType Leaf))) { throw 'Record must be an existing JSONL under this user projects root' }
            $Cursor = $Full
            while (-not [string]::IsNullOrWhiteSpace($Cursor)) {
                if ((Get-Item -LiteralPath $Cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse path refused' }
                $Parent = [IO.Path]::GetDirectoryName($Cursor)
                if ($Parent -eq $Cursor) { break }
                $Cursor = $Parent
            }
        }
        $Destination = Join-Path $UpdateDir ('tool-calls-only-' + [guid]::NewGuid().ToString('N') + '.jsonl')
        $Utf8 = New-Object System.Text.UTF8Encoding($false)
        $Stream = [IO.File]::Open($Destination,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        foreach ($Path in $Records) {
            $Full = [IO.Path]::GetFullPath($Path)
            $LineNo = 0
            $ReadStream = [IO.File]::Open($Full,'Open','Read','ReadWrite')
            try {
                $Reader = [IO.StreamReader]::new($ReadStream,$Utf8,$true)
                while (($Line = $Reader.ReadLine()) -ne $null) {
                    $LineNo++
                    if ([string]::IsNullOrWhiteSpace($Line)) { continue }
                    $Row = $Line | ConvertFrom-Json -ErrorAction Stop
                    if ($Row.type -cnotin @('function_call','function_call_result')) { continue }
                    $Item = [ordered]@{record=[IO.Path]::GetFileName($Full); line=$LineNo; type=$Row.type; name=$Row.name; command=$null; file_path=$null; status=$null; exit_code=$null}
                    if ($Row.type -ceq 'function_call') {
                        $CallArgs = $Row.arguments
                        if ($CallArgs -is [string]) { $CallArgs = $CallArgs | ConvertFrom-Json -ErrorAction Stop }
                        if ($CallArgs.command -is [string]) { $Item.command = $CallArgs.command }
                        if ($CallArgs.file_path -is [string]) { $Item.file_path = $CallArgs.file_path }
                    } else {
                        if ($Row.status -is [string]) { $Item.status = $Row.status }
                        if ($Row.exit_code -is [int] -or $Row.exit_code -is [long]) { $Item.exit_code = $Row.exit_code }
                        elseif ($Row.exitCode -is [int] -or $Row.exitCode -is [long]) { $Item.exit_code = $Row.exitCode }
                        else {
                            $ResultText = $null
                            if ($Row.output -is [string]) { $ResultText = $Row.output }
                            elseif ($Row.output.text -is [string]) { $ResultText = $Row.output.text }
                            if ($null -ne $ResultText -and $ResultText -match '(?m)^Exit Code:\s*(-?\d+)\s*$') { $Item.exit_code = [long]$Matches[1] }
                        }
                    }
                    $Bytes = $Utf8.GetBytes(($Item | ConvertTo-Json -Compress -Depth 4) + "`n")
                    $Stream.Write($Bytes,0,$Bytes.Length)
                }
            } finally {
                if ($null -ne $Reader) { $Reader.Dispose(); $Reader = $null }
                if ($null -ne $ReadStream) { $ReadStream.Dispose(); $ReadStream = $null }
            }
        }
        $Stream.Flush(); $Stream.Dispose(); $Stream = $null
        Write-Host "Tool-only evidence: $Destination"
        Get-FileHash -LiteralPath $Destination -Algorithm SHA256
    } finally {
        if ($null -ne $Reader) { $Reader.Dispose() }
        if ($null -ne $ReadStream) { $ReadStream.Dispose() }
        if ($null -ne $Stream) { $Stream.Dispose() }
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

## 带回的证据清单

- 本次`D:\crm-v36-handoff\update-<RunId>\`整个目录：计划、各次VERIFY报告、`raw-evidence-<GUID>`下团长记录副本及SHA256SUMS，不复用旧目录。
- 跑自检2时，还要带回`C:\Users\AI\.workbuddy\projects\<工作区>\<会话ID>\subagents\`成员记录；只传SessionId的VERIFY不会复制成员。使用⑥的SessionId+AgentId核对。
- 知识库冒烟记录含正文片段，是否带出由用户决定；不能带出时仅交⑦摘要和本站人工判读，注明没有外部原文复核，不把摘要当完整记录。
- 记录实际用r6还是r7、对应提交SHA、文件SHA256、WorkBuddy/模型/插件身份。失败原样保留，不用新提示词或改缓存凑通过。

## 10-14 Mac 最终发布核验

- 已发布提交`58682ff17dd9e3f9f6be0c681f2b110a758fad9a`，附注标签`crm-sre-team-2.8.0-rc5`；标签对象`e97abf0d4c9864a823fc388866145dd37540d2c7`。
- 正式ZIP SHA256：`7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e`；main和标签未因本手册分支改变。本分支不重新发布rc5。
- WorkBuddy5.8.2 / glm-5.3-flash，Mac正式回执PASS；来源544/545仅缺settings.json，缓存545/545完整。知识库配置收尾保持.bak。
- K01：KB-7限制传递逐字问题，FAIL保留，用户接受rc5候选发布；与K14/K15列rc6待修，本手册不改插件提示词。
- 第⑤节Mac冒烟主题“挂起订单”，单次会话cd5efdd4-b11e-4a35-9bcc-a33fff4e9534：FAIL（K14，Python路径漏单引号，执行等效且退出0，未越权）；K15（QUALITY，单次检索扩大为全库不存在，与K02同类）。不改判据、不重跑；值班机按同一口径判。
- 本机无pwsh：PowerShell语法检查NOT_RUN；Windows执行NOT_RUN。以下身份及提示词已作Mac静态核对，不能替代Windows实际运行。
