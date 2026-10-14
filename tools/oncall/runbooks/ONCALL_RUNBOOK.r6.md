# 值班机手册 r6 · rc5 已发布候选（待 Claude 审阅）

本手册只交付，不在本轮执行。普通 Windows PowerShell 5.1，本地来源只读 D:\python_code\github_my\crm-sre-team；不访问GitHub、不删除已有文件、不杀进程。用户正常退出客户端后再切包，保留所有旧计划、备份、证据和用户数据。UPDATE 仅构建工具可清理自己本次新建 crm-oncall-<RunId> 及本次系统临时文件；失败保留证据。

## ① 前置：r5 未完成时先恢复rc3正式，再UPDATE rc4并VERIFY

r5第①②步已完成且有真实回执者跳过。未完成者使用以下原r5两步与已发布身份，不借用Mac会话ID、不复用旧安装计划。

### ① 用 10-12 实验集 SWITCH 回 rc3 正式包 + VERIFY，报告 WorkBuddy 版本

沿用 10-12 的原 bootstrap 与原实验集。SWITCH 内部生成新计划，按需 DRILL，再显示安装计划、等待一次大写 YES、执行 APPLY；不另发 APPLY。确认来源、目标与备份路径正确后才输入 YES。

~~~powershell
. {
    $Rc3Script = 'D:\crm-v36-handoff\bootstrap-c034956655cf478fa2da372d883968c5\tools\oncall\Update-CrmSreTeam.ps1'
    $Rc3Args = @('-Tag', 'crm-sre-team-2.8.0-rc3-oncall4', '-ExpectedCommit', '58731a99a706fec8440f17d9864a023699f569be', '-ExpectedZipSha256', 'c543e5d2fec31607963d791e5c13e7d194e0a989dff07714661bea249b074f41')
    $Rc3SetPath = 'D:\crm-v36-handoff\experiment-59b011856b7d45829aa5d8c913474d72\experiment-set.json'
    $Rc3SetHash = '2f3ba2c4fbcdf2236d0f1e8fdc844c22f992b810dd6026a0b8ea63c8f5187578'
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
    if (-not (Test-Path -LiteralPath $Rc3Script -PathType Leaf) -or -not (Test-Path -LiteralPath $Rc3SetPath -PathType Leaf)) { throw 'The original rc3 bootstrap or experiment set is missing' }
    if ((Get-FileHash -LiteralPath $Rc3SetPath -Algorithm SHA256).Hash -ine $Rc3SetHash) { throw 'Original experiment set SHA256 mismatch' }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Rc3Script -Mode SWITCH @Rc3Args -ExperimentSet $Rc3SetPath -ExperimentSetSha256 $Rc3SetHash -Package formal
    if ($global:LASTEXITCODE -ne 0) { throw 'SWITCH stopped; retain this plan, reports and backups' }
}
~~~

看到 INSTALLED 后，保存**本次**打印的 PlanPath、PlanSha256 和完整 VERIFY 命令。启动客户端、刷新市场、选中正式 2.8.0-rc3；新开短会话只用 Skill 加载 stability-director 并转述真实 Base directory，不调用成员。记录真实会话 ID，再运行：

~~~powershell
. {
    $Rc3Plan = Read-Host 'Paste THIS SWITCH PlanPath'
    $Rc3PlanHash = Read-Host 'Paste THIS SWITCH PlanSha256'
    $Rc3SessionId = Read-Host 'Paste the NEW rc3 Skill receipt session ID'
    if ($Rc3Plan -notmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $Rc3PlanHash -notmatch '^[0-9a-fA-F]{64}$' -or $Rc3SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan or session value' }
    if (-not (Test-Path -LiteralPath $Rc3Plan -PathType Leaf) -or (Get-FileHash -LiteralPath $Rc3Plan -Algorithm SHA256).Hash -ine $Rc3PlanHash) { throw 'Current plan missing or SHA256 mismatch' }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Rc3Script -Mode VERIFY @Rc3Args -PlanPath $Rc3Plan -PlanSha256 $Rc3PlanHash -SessionId $Rc3SessionId
    if ($global:LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
}
~~~

回报客户端 About/左侧显示的 WorkBuddy 版本、插件 2.8.0-rc3、真实 Skill 路径与 VERIFY 报告。无 SessionId 的 VERIFY 仅列元数据，不能当加载验收 PASS；不借用旧安装计划。

### ② rc4 推送并同步本地项目后，UPDATE 到 rc4 + VERIFY

**发布已完成，标签新 clone 的十步发布与 ZIP 字节一致性已复核，以下三个最终值已填入。** 用户先把值班机本地项目同步到包含最终提交的状态；以下代码只读取本地项目对象，不执行远端同步。更新前正常退出客户端。

**UPDATE 已放行，清理范围与 10-12 rc3 的 UPDATE 一致。** 粘贴的命令和更新脚本不得删除任何已有文件，包括本地项目、WorkBuddy 插件来源与缓存、D:\crm-v36-handoff 下已有的计划/备份/证据，以及用户数据。构建工具仅允许清理本次 UPDATE 自己新建的工作区 crm-oncall-<RunId>，以及系统临时目录中本次生成的临时文件。仅有这两类本次新建对象在允许清理范围内；旧来源按既有备份流程保留，不以删除旧文件完成更新。

~~~powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc4'
    $ExpectedCommit = '43894bd41f237684615cdd600940bf2550524510'
    $ExpectedZipSha256 = '5c3b7534bd59f6fdabac0d356ab3a0ecb54f0c7ff5bcaebd8734c572be75a992'
    $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $ExpectedZipSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Fill the three verified final publication values first' }
        if (-not (Test-Path -LiteralPath $SourceRepo -PathType Container -ErrorAction Stop)) { throw 'Local project missing' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}') 2>$null
        if ($global:LASTEXITCODE -ne 0) { throw 'Local project does not contain the final commit; sync it first' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'New bootstrap path already exists' }
        Write-Host "Local source=$SourceRepo; new bootstrap=$Bootstrap"
        git -c core.hooksPath=NUL clone -q --no-local --no-checkout --config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap
        if ($global:LASTEXITCODE -ne 0) { throw 'Local bootstrap clone failed' }
        git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'
        if ($global:LASTEXITCODE -ne 0) { throw 'Copying local remote-tracking refs failed' }
        git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($global:LASTEXITCODE -ne 0) { throw 'Final commit is not reachable from local project refs' }
        git -C $Bootstrap -c core.hooksPath=NUL show-ref --verify --quiet ('refs/tags/' + $Tag)
        $TagLookupExit = $global:LASTEXITCODE
        if ($TagLookupExit -eq 0) {
            $LocalTagCommit = git -C $Bootstrap -c core.hooksPath=NUL rev-parse ($Tag + '^{commit}')
            if ($global:LASTEXITCODE -ne 0 -or $LocalTagCommit.Trim() -ine $ExpectedCommit) { throw 'Local final tag points to another commit' }
        } elseif ($TagLookupExit -eq 1) {
            git -C $Bootstrap -c core.hooksPath=NUL tag $Tag $ExpectedCommit
            if ($global:LASTEXITCODE -ne 0) { throw 'New bootstrap tag binding failed' }
        } else { throw 'Tag lookup failed' }
        git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag
        if ($global:LASTEXITCODE -ne 0) { throw 'New bootstrap checkout failed' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' -ErrorAction Stop
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf -ErrorAction Stop)) { throw 'Updater missing in final commit' }
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256
        if ($global:LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }
    } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
~~~

两个 clone/fetch 的来源均为本地 SourceRepo。标签核对或绑定只作用于全新 bootstrap；来源项目保持只读。Updater 在已验证工作树中从本地 bootstrap 构建，拒绝脏树/HEAD/脚本 blob 不一致；此处不给独立脚本路径，避免网络备选。UPDATE 按 PLAN → 必要时 DRILL → 一次 YES → APPLY 执行。

INSTALLED 后保存本次计划，启动客户端、刷新到正式 2.8.0-rc4，新会话只取真实 Skill 回执，再执行本次 VERIFY：

~~~powershell
. {
    $Rc4Plan = Read-Host 'Paste THIS UPDATE PlanPath'
    $Rc4PlanHash = Read-Host 'Paste THIS UPDATE PlanSha256'
    $Rc4SessionId = Read-Host 'Paste the NEW rc4 Skill receipt session ID'
    if ($Rc4Plan -notmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $Rc4PlanHash -notmatch '^[0-9a-fA-F]{64}$' -or $Rc4SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan or session value' }
    if (-not (Test-Path -LiteralPath $Rc4Plan -PathType Leaf) -or (Get-FileHash -LiteralPath $Rc4Plan -Algorithm SHA256).Hash -ine $Rc4PlanHash) { throw 'Current plan missing or SHA256 mismatch' }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -PlanPath $Rc4Plan -PlanSha256 $Rc4PlanHash -SessionId $Rc4SessionId
    if ($global:LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
}
~~~

VERIFY 须核来源/缓存及真实 Skill 回执中的 2.8.0-rc4 路径。正式 rc4 允许唯一根 settings.json 缺失时明确记录 517/518；其他缺失/差异失败。记录打印的报告路径，不改缓存来凑通过。


## ② rc5 发布且本地同步后 UPDATE + VERIFY

rc5候选已按用户2026-10-14决定发布，main与附注标签已推送并复核一致。以下绑定实际提交和最终ZIP；唯一关键失败K01（KB-7限制句改写）按用户决定保留。本手册仅交付给Claude审阅，本轮Windows NOT_RUN；审阅后由用户另行完成本地项目同步与UPDATE，不得用候选基线或探测包替代下列身份。

普通PowerShell中用Read-Host取得最终提交与ZIP哈希，确认格式后，沿上面rc4第②步的本地SourceRepo→全新Bootstrap流程，三个值替换为rc5；工具脚本仍是新Bootstrap内的原 updater。该步骤的bootstrap绑定下列已推送候选标签；Claude审阅后由用户在值班机执行，本轮不执行安装。UPDATE 按 PLAN→必要DRILL→用户核计划并一次YES→APPLY；启动WorkBuddy后新会话只取Skill真实Base directory，再用本次PlanPath/PlanSha256加-SessionId运行VERIFY。正式包应为2.8.0-rc5，不出现实验核验行；来源/缓存N-1/N只允许唯一缺根settings.json，其余差异失败。

以下值已与远端main/附注标签、两份独立发布、跨目录核对和标签重建ZIP逐字节核对。值班机执行前仍应确认本地目标提交与这些值一致。

| 发布值 | 当前状态 |
|---|---|
| Tag | crm-sre-team-2.8.0-rc5（已推送附注标签） |
| ExpectedCommit | 58682ff17dd9e3f9f6be0c681f2b110a758fad9a |
| ExpectedZipSha256 | 7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e |

交付审阅的完整本地升级代码（本轮未执行）：

```powershell
. {
    $Tag = 'crm-sre-team-2.8.0-rc5'
    $ExpectedCommit = '58682ff17dd9e3f9f6be0c681f2b110a758fad9a'
    $ExpectedZipSha256 = '7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e'
    $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
        if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $ExpectedZipSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Fill the three verified final publication values first' }
        if (-not (Test-Path -LiteralPath $SourceRepo -PathType Container -ErrorAction Stop)) { throw 'Local project missing' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}') 2>$null
        if ($global:LASTEXITCODE -ne 0) { throw 'Local project does not contain the final commit; sync it first' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'New bootstrap path already exists' }
        Write-Host "Local source=$SourceRepo; new bootstrap=$Bootstrap"
        git -c core.hooksPath=NUL clone -q --no-local --no-checkout --config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap
        if ($global:LASTEXITCODE -ne 0) { throw 'Local bootstrap clone failed' }
        git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'
        if ($global:LASTEXITCODE -ne 0) { throw 'Copying local remote-tracking refs failed' }
        git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($global:LASTEXITCODE -ne 0) { throw 'Final commit is not reachable from local project refs' }
        git -C $Bootstrap -c core.hooksPath=NUL show-ref --verify --quiet ('refs/tags/' + $Tag)
        $TagLookupExit = $global:LASTEXITCODE
        if ($TagLookupExit -eq 0) {
            $LocalTagCommit = git -C $Bootstrap -c core.hooksPath=NUL rev-parse ($Tag + '^{commit}')
            if ($global:LASTEXITCODE -ne 0 -or $LocalTagCommit.Trim() -ine $ExpectedCommit) { throw 'Local final tag points to another commit' }
        } elseif ($TagLookupExit -eq 1) {
            git -C $Bootstrap -c core.hooksPath=NUL tag $Tag $ExpectedCommit
            if ($global:LASTEXITCODE -ne 0) { throw 'New bootstrap tag binding failed' }
        } else { throw 'Tag lookup failed' }
        git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag
        if ($global:LASTEXITCODE -ne 0) { throw 'New bootstrap checkout failed' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' -ErrorAction Stop
        if (-not (Test-Path -LiteralPath $Script -PathType Leaf -ErrorAction Stop)) { throw 'Updater missing in final commit' }
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256
        if ($global:LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }
    } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

安装完成、新会话取真实Skill回执后：

```powershell
. {
    $Rc5Plan = Read-Host 'Paste THIS UPDATE PlanPath'
    $Rc5PlanHash = Read-Host 'Paste THIS UPDATE PlanSha256'
    $Rc5SessionId = Read-Host 'Paste the NEW rc5 Skill receipt session ID'
    if ($Rc5Plan -notmatch '^D:\\crm-v36-handoff\\update-[0-9a-f]{32}\\install-plan\.json$' -or $Rc5PlanHash -notmatch '^[0-9a-fA-F]{64}$' -or $Rc5SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9-]*$') { throw 'Invalid current plan or session value' }
    if (-not (Test-Path -LiteralPath $Rc5Plan -PathType Leaf) -or (Get-FileHash -LiteralPath $Rc5Plan -Algorithm SHA256).Hash -ine $Rc5PlanHash) { throw 'Current plan missing or SHA256 mismatch' }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -PlanPath $Rc5Plan -PlanSha256 $Rc5PlanHash -SessionId $Rc5SessionId
    if ($global:LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain evidence and report the original output' }
}
```

## ③ 知识库只读元数据探查（不读正文）

根目录由用户输入。只输出存在性、顶层目录的Markdown文件计数、索引大小与更新时间，不输出文件正文或真实文件名清单。Python3.12路径必须存在。脚本兼容性由本站查询验证；Mac复制脚本使用fcntl，不假定Windows可运行，失败走导航回退并由维护人修复，不在本轮改脚本。

```powershell
. {
    if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1' }
    $KbRoot = Read-Host 'Paste the authorized absolute knowledge root'
    $KbPython = Read-Host 'Paste the Python 3.12 executable absolute path'
    if (-not [IO.Path]::IsPathRooted($KbRoot) -or -not (Test-Path -LiteralPath $KbRoot -PathType Container)) { throw 'Knowledge root missing or not absolute' }
    if (-not [IO.Path]::IsPathRooted($KbPython) -or -not (Test-Path -LiteralPath $KbPython -PathType Leaf)) { throw 'Python executable missing or not absolute' }
    @('wiki\index.md', 'scripts\kb_search_zh.py', '.kb\search_index_zh.json') | ForEach-Object {
        [pscustomobject]@{Check=$_; Exists=(Test-Path -LiteralPath (Join-Path $KbRoot $_) -PathType Leaf)}
    }
    Get-ChildItem -LiteralPath $KbRoot -Directory | ForEach-Object {
        if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse directory refused' }
        [pscustomobject]@{Directory=$_.Name; MarkdownCount=@(Get-ChildItem -LiteralPath $_.FullName -Filter '*.md' -File -Recurse).Count}
    }
    $KbIndex = Join-Path $KbRoot '.kb\search_index_zh.json'
    if (Test-Path -LiteralPath $KbIndex -PathType Leaf) {
        $KbIndexMeta = Get-Item -LiteralPath $KbIndex
        [pscustomobject]@{Check='search_index'; Bytes=$KbIndexMeta.Length; UpdatedUtc=$KbIndexMeta.LastWriteTimeUtc}
    }
}
```

## ④ 新建插件外配置，不覆盖

在上一步同一PowerShell窗口运行。若knowledge.json存在就停，不读/覆盖其内容。使用UTF-8无BOM、CreateNew保证不覆盖。top=5/max_pages=3/allowed_read_dirs=wiki，私密标记由用户按本站维护协议核对后使用。先确认最小必要页面可交给glm-5.3-flash云端模型。

```powershell
. {
    $ConfigDir = Join-Path $env:USERPROFILE '.crm-sre-team'
    $ConfigPath = Join-Path $ConfigDir 'knowledge.json'
    if (Test-Path -LiteralPath $ConfigPath) { throw 'knowledge.json already exists; stop without overwrite' }
    if (-not (Test-Path -LiteralPath $ConfigDir)) { New-Item -ItemType Directory -Path $ConfigDir -ErrorAction Stop | Out-Null }
    $Config = [ordered]@{schema='crm-sre-knowledge/v1'; root=$KbRoot; python=$KbPython; search_script='scripts/kb_search_zh.py'; search_index='.kb/search_index_zh.json'; entry='wiki/index.md'; top=5; max_pages=3; allowed_read_dirs=@('wiki'); exclude_markers=@('private','confidential','secret','敏感','私密')}
    $ConfigJson = $Config | ConvertTo-Json -Depth 4
    $ConfigJson | ConvertFrom-Json -ErrorAction Stop | Out-Null
    $ConfigBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($ConfigJson)
    $ConfigStream = [IO.File]::Open($ConfigPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $ConfigStream.Write($ConfigBytes,0,$ConfigBytes.Length); $ConfigStream.Flush() } finally { $ConfigStream.Dispose() }
    Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop | Out-Null
    $KbKeyword = Read-Host 'One authorized business topic, no secrets'
    if ($KbKeyword -notmatch '^[一-龥A-Za-z0-9 _-]{1,32}$' -or $KbRoot.Contains("'") -or $KbPython.Contains("'")) { throw 'Unsafe keyword/path; do not execute query' }
    & $KbPython -X utf8 (Join-Path $KbRoot 'scripts\kb_search_zh.py') $KbKeyword --top 5
    if ($LASTEXITCODE -ne 0) { throw 'Query failed; retain config and use documented navigation fallback' }
}
```

固定显示命令应为 `& '<python>' -X utf8 '<root>\scripts\kb_search_zh.py' '<关键词>' --top 5`；首轮最多5项、阅读不超过3页。禁止--rebuild、自由搜索、未引用raw、私密页面和写回。前面的人工元数据探查不属于WorkBuddy Agent可执行命令白名单。

## ⑤ WorkBuddy知识库短会话及VERIFY

预注册冒烟提示词，只有主题由用户填。不要提供真实事故数据或凭据：

```text
先只通过宿主 Skill 工具加载 stability-director。只围绕业务主题“<用户填一个已授权主题>”查询已配置本地知识库，不连接生产、不读取环境变量或凭据、不写文件、不联网。知识库只读检索仅允许固定查询命令，除此以外不执行任何终端命令；不运行--rebuild、不自由搜索、不读私密页和未引用raw资料、不调用成员。读取最相关不超过3页，给出知识库依据、E-K路径与真实行号、页面日期/置信度和知识缺口；背景知识不能单独确认根因。不能读取时如实说明，不猜路径，不编回执。
```

完成后保存真实SessionId；若另有明确授权成员测试则保存真实AgentId。用本次rc5安装计划与原updater的VERIFY加-SessionId/-AgentId取证；只传AgentId须由工具唯一反查父会话。核原始Read/Bash调用和路径、固定命令、退出码、遮蔽与真实Skill版本，文件完整性PASS不替代行为复核。

## ⑥ 版本与模型记录、差异补核

| 时间 | WorkBuddy版本 | 插件版本 | 主/成员实际模型 | 构建/manifest与缓存哈希 | 会话/成员ID | VERIFY/行为结论 |
|---|---|---|---|---|---|---|
| 本站实测 | 由用户记录 | 2.8.0-rc5 | 逐次记录glm-5.3-flash | 由VERIFY取得 | 本站真实ID | 原始证据定位 |

值班机不是5.8.2时，由用户二选一：先升级客户端到5.8.2并记录，或在rc5正式包上补跑冻结自检2与知识库冒烟。冻结自检2原文随交接 selfcheck-2.frozen.txt 保留，SHA256=b057d3dca04e2760afc84357b3f25d611e81ef30300ca1d4c6762ad9790e3337；不要编辑其中限制或判据，不借用Mac会话。仍固定实际glm-5.3-flash。Mac结论不能自动覆盖Windows差异。

提醒：WorkBuddy读到的知识片段进入glm-5.3-flash云端上下文。必要页面上限3，遵守敏感标记；数据授权与脚本筛选兼容性由用户确认。知识库仅提供背景；不替代现场证据，不提供生产执行权。正式版本、安装、知识库查询的失败都要原样保留，不能为通过更改缓存或判据。

## 10-14 Mac 最终发布核验

- 提交：`58682ff17dd9e3f9f6be0c681f2b110a758fad9a`；附注标签：`crm-sre-team-2.8.0-rc5`；main与标签均已非force原子推送。
- ZIP SHA256：`7d69c2ce5b70f9e86ec5d5f61164a69f4c8c4c2b7812366d6592ebff7629a74e`，两份独立发布、跨目录核对及标签重建均逐字节一致。
- 完整补丁SHA256：`2252e8b95345b48f5151e0fcf5655e5db9f25f769090c1f62316c88355140c8f`。
- Mac WorkBuddy 5.8.2 / glm-5.3-flash，正式Skill回执PASS，实际路径指向2.8.0-rc5；最终来源544/545，仅缺settings.json，缓存545/545全量相等。知识库配置保持.bak，来源与缓存的旧整包备份保留。
- K01：KB-7限制句改写，原FAIL保留；其他已知问题见VALIDATION.md。Windows及正式关口NOT_RUN。
- 本手册已填发布身份，仅交付Claude审阅，没有执行Windows命令。
