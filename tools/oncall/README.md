# 值班机一键更新（Windows PowerShell 5.1）

## rc4 使用流程（2.8.0-rc4）

提示词测试（自检、WB 用例、7A/7B、校准和关口）全部先在 Mac 运行；Mac 跑完、返回结果经人工复核并验收后，Windows 值班机只做安装/切换 + VERIFY（来源/缓存完整性、Skill 回执路径）+ 记录版本，仅在需确认宿主行为时加一个短会话。两台都记录实际 WorkBuddy 版本、插件版本和模型，有差异时值班机检查覆盖差异；日常与关口固定 glm-5.3-flash，逐次记录实际模型。校准和关口前两台都查看宿主记忆条目，由执行人在会话外核对 conversation_search 可检索的测试历史，记录可能进入被测会话的内容及隔离状态；Mac 测试历史更多，同样适用。是否清理或关闭由用户决定，宿主用例与关口材料按 docs/11 隔离。
WB07 的 HOST_LIMIT 前提按实际运行该测试的机器的 WorkBuddy 版本核验；Mac 采用只读代码复核，块 27 只用于 Windows 值班机，值班机的 5.7.7 记录不能代替 Mac 核验。值班机版本与 Mac 不同时，由值班机简单检查补核轮数下限与团长处理，具体判读按 docs/11–13。两台机器各自记录构建后缀与身份（机器、source_commit、manifest 与缓存哈希），N/S 校准和正式关口不混用双机构建。
当前交接每次列明获准的安装/切换、VERIFY 和版本记录项。下文 rc3 bootstrap、固定 ZIP 哈希和 runbook r3/r4 引用保留为当时的历史操作记录，当前交接须绑定实际 rc4 包、源码和脚本身份。工具保留的 EXPBUILD、DRILL、`-RunPytest` 等能力不改变本轮的 Mac 测试流程；Windows 的授权范围以本节为准。

只接收 Mac 已验证的 `Tag / ExpectedCommit / ExpectedZipSha256` 交接值。完整更新：**退出客户端 → 从本地项目取得目标提交并在新 bootstrap 运行 UPDATE → 输入一次 YES → 打开客户端贴自检 1 → 运行打印出的 VERIFY 命令**。`UPDATE` 在同一进程内执行 `PLAN → 必要时 DRILL → 打印安装计划 → YES → APPLY`，自动传递计划路径和哈希。六个正式更新模式继续用于排错、核验和回退；实验流程使用下文 `EXPBUILD / SWITCH`。

**本轮修复后的新增编排代码未在 Windows 实跑。** Mac 的 Python 静态检查不能证明 PS 5.1 运行正确，也不能证明 WorkBuddy 加载了团长 Agent 正文。首次使用须 DRILL；`UPDATE` 找不到本机交接目录内成功的 DRILL 报告时会自动演练，通过后才显示真实安装计划并等待 YES；`-Drill` 可强制本轮重做。此工具仅更新桌面插件；生产写操作仍只产出人工评审需求。

## 文件与发布边界

- `Update-CrmSreTeam.ps1` 使用 **UTF-8 BOM + LF**。保留 runbook 中文代码原文，避免 PS 5.1 按 ANSI/GBK 错读；新增编排的提示使用英文。下载后保持原字节，不用编辑器另存编码或换行。
- 现有 `tools/release_rules.py` 不接受 `.ps1`，构建/打包器只读取 `release-manifest.json.files`。现有 `repository_only_files` 已精确登记这三个开发文件（脚本、本文、静态测试），由专项测试约束其排序、唯一性、存在性与不进入 ZIP。该字段是登记信息，**不会让插件安装或执行脚本**。
- 三个文件随 Git 同步，插件 ZIP 不含它们。插件的期望文件数一律读取 `files`，没有固定成 517。本次保持 manifest 和发布载荷字节不变。
- 脚本启动时若位于 Git 工作树内，先校验 `HEAD = ExpectedCommit`、工作树干净，以及该提交内脚本 blob 哈希与磁盘原字节哈希相同；任何不符立即停止。`PLAN` 仍比对目标标签内脚本 SHA256，后续模式绑定计划里的脚本哈希。`-ExpectedScriptSha256 <64-hex>` 是可选的额外交接核验，不要求手工传脚本或单独核对哈希。Mac 改完脚本后必须重新提交、验证并提供相应标签。

## 前置条件与固定路径

- Windows PowerShell **5.1**、Git for Windows、实际可运行的 Python **3.10+**；该 Python 已具备仓库离线检查所需依赖。工具不安装或升级任何依赖。
- 默认 `PythonExe` 是 runbook 在值班机核对过的 `C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe`。存在时直接使用；不存在就停止并要求显式传 `-PythonExe 'C:\<verified-python-dir>\python.exe'`。不回退到 `python3` 或 WindowsApps alias。
- 主获取路径只读值班机本地项目 `D:\python_code\github_my\crm-sre-team`，不访问网络。本地项目须由用户自行更新到包含 `ExpectedCommit`；没有目标提交就停止。来源仓库的分支、工作树、索引、标签和远程配置都不改。完整性依靠 `ExpectedCommit` 与插件 ZIP SHA256。
- bootstrap：先在来源仓库用 `cat-file` 核对目标提交，再用 `--no-local --no-checkout` 本地 clone 到全新 `D:\crm-v36-handoff\bootstrap-<GUID>`；复制 `refs/remotes/*` 到 bootstrap 的独立引用空间，以覆盖只 fetch 过、提交仅在远程跟踪引用上的情况。只在新 bootstrap 内用 `tag -f` 把 `Tag` 绑定到 `ExpectedCommit`，再 detach checkout；不依赖来源仓库里的标签，它可能仍指向较早提交。直接运行 bootstrap 的 `tools\oncall\Update-CrmSreTeam.ps1`。`PLAN` 再从已通过启动身份校验的 bootstrap 工作树本地 clone；两次均使用 `--no-local`，不联网。每次更新用全新目录，保留旧目录供排错。没有本地项目的机器才使用下文 GitHub 直接 clone 备选；独立脚本找不到 Git 工作树时，`PLAN` 也保留原 GitHub clone。
- 新 clone 工作区：`D:\Dev\crm-oncall-<GUID>\repo`。父工作区也全新，容纳仓库构建器在 `root.parent` 下的隔离暂存；任何同名已有路径均拒绝复用。
- 新计划/ZIP/暂存/日志/测试临时目录：`D:\crm-v36-handoff\update-<GUID>`。PLAN 的写入只发生在这两个新工作区，WorkBuddy 只读。脚本所在 PowerShell 子进程的 `TEMP/TMP/TMPDIR/PYTHONUTF8/PYTHONDONTWRITEBYTECODE/GIT_CONFIG_*` 设置随子进程退出而失效；它继续隔离全局/系统 Git 配置并禁用 credential helper、交互和 hooks。主获取段在 `finally` 中恢复 `$ErrorActionPreference`。GitHub 备选仅在 clone 期间临时设置七个 Git 环境变量，并在 `finally` 中恢复进程原值；原值不存在时移除变量。禁止 Python 在已有依赖目录写入 bytecode cache。
- REAL 路径沿用已验证的值班机账户：`C:\Users\AI\.workbuddy\plugins\marketplaces\my-experts`；来源是其 `plugins\crm-sre-team`，清单是其 `.codebuddy-plugin\marketplace.json`。cache 根为 `C:\Users\AI\.workbuddy\plugins\cache\my-experts\crm-sre-team`。账户/布局不同就停止并人工评审，不传参扩大边界。
- REAL marketplace 条目必须唯一，`name` 精确为 `crm-sre-team`，`source` 必须是字符串且解析到上述固定安装来源。`version` 字段可省略：PLAN 会提示，APPLY 不修改 `marketplace.json`，客户端读取包内 `.codebuddy-plugin/plugin.json` 的版本，与 10-11 rc2 实装一致；字段存在时必须为非空、非纯空白字符串，否则停止并人工评审。
- 备份：marketplace 根下的 `backups\crm-v36-<GUID>-oncall`，包括 `install-source`、`marketplace.json`、`install-state.json`；计划列出全部准确路径。
- 路径拒绝 junction/symlink/越界；递归复制前检查树内链接。工具没有删除操作，也不强杀进程，不修改系统执行策略。唯一执行策略选项在启动命令中：进程级 `-ExecutionPolicy Bypass`。

## Mac 发布时取得交接值

在包含本次脚本修改的最终待发布提交的干净仓库操作。此处命令用于发布人的人工操作说明；本单不会创建标签或推送。期望 commit/ZIP SHA256 **不写入仓库**，否则包会再次变化。

```bash
python3 tools/build_bundle.py
python3 -m pytest tests/ -q
python3 -m pytest tools/oncall/test_oncall_updater.py -q
python3 tools/check_workbuddy.py
python3 tools/validate_bundle.py
git status --short
# 检查源/产物一致、全部通过；经授权提交后，工作树必须干净。
python3 tools/release.py
# 从输出的 release_dir / release_sha256 取得同轮 ZIP 路径与 SHA256。
# release.py 内部调用现有 build_release.py 和 validate_release.py。
git rev-parse HEAD
```

也可直接使用确定性打包工具，输出到仓库忽略的 `dist/` 下一个全新文件名：

```bash
python3 tools/build_release.py --output dist/crm-sre-team-handoff.zip
python3 tools/validate_release.py --zip dist/crm-sre-team-handoff.zip
shasum -a 256 dist/crm-sre-team-handoff.zip
git rev-parse HEAD
```

通过发布审核后另行创建标签。提供 `Tag`、`ExpectedCommit`（40 位）、`ExpectedZipSha256`（64 位），并在交接消息或**标签注释**中记录 Windows 尚待实跑的项目。注释不属于工作树/ZIP，不改变包哈希。发布人必须用 `git rev-parse '<tag>^{commit}'` 再核对标签指向相同 commit；推送 main 和标签需用户另行明确授权。

值班机先确认本地项目包含上述 `ExpectedCommit`，从本地 clone 取得脚本并在新 bootstrap 内绑定标签；没有本地项目的机器用下文 GitHub 直接 clone 备选。不单独导出或人工传文件。发布人可选择额外提供该提交中脚本的 SHA256，供值班机传 `-ExpectedScriptSha256`；它不是更新的必需输入。脚本不在插件 ZIP 内。

## 一次完整更新的命令序列

在普通 PS 5.1 窗口执行。先退出 WorkBuddy/CodeBuddy；在以下同一段开头集中填写 `Tag`、`ExpectedCommit`、`ExpectedZipSha256`（替换三个占位值），确认 `SourceRepo` 是值班机现有项目且已包含目标提交。整段只从本地项目获取，不访问 GitHub；标签名在新 bootstrap 内绑定到交接提交。安装计划出现后只输入一次大写 `YES`。每个原生命令后都立即检查 `$LASTEXITCODE`，失败就停止；`$Script` 保留供单独模式和回退使用。

```powershell
. {
    $Tag = '<tag>'
    $ExpectedCommit = '<40-hex>'
    $ExpectedZipSha256 = '<64-hex>'
    $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $ExpectedZipSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Fill the three verified release values first' }
        if (-not (Test-Path -LiteralPath $SourceRepo -PathType Container -ErrorAction Stop)) { throw 'Local project missing' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}') 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Local project does not contain the target commit yet; update it first, then rerun' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'Bootstrap path already exists' }
        Write-Host "Local project has $ExpectedCommit; bootstrap=$Bootstrap (no network)"
        git -c core.hooksPath=NUL clone -q --no-local --no-checkout --config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap
        if ($LASTEXITCODE -ne 0) { throw 'Local bootstrap clone failed' }
        git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'
        if ($LASTEXITCODE -ne 0) { throw 'Copying local remote-tracking refs failed' }
        git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($LASTEXITCODE -ne 0) { throw 'Target commit is not reachable from local project refs' }
        git -C $Bootstrap -c core.hooksPath=NUL tag -f $Tag $ExpectedCommit
        if ($LASTEXITCODE -ne 0) { throw 'Bootstrap tag failed' }
        git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag
        if ($LASTEXITCODE -ne 0) { throw 'Bootstrap checkout failed' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' -ErrorAction Stop
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -RunPytest
        if ($LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }
    } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

### 没有现成来源仓库时：GitHub 直接 clone 备选

仅用于没有本地项目的机器。以下备选在当前窗口用 `. { }` 执行，从公开 GitHub 仓库直接 clone 目标标签；需要 Git 隔离配置下 GitHub 联网正常。七个 Git 环境变量先保存进程原值，仅在 clone 期间设置，并在 `finally` 中逐个恢复；clone 错误直接显示。之后直接用 `powershell -File` 运行 UPDATE，安装计划与 YES 提示在终端显示；`$Script` 保留在会话里供单独模式使用。同样先退出客户端，在段首填写三个交接值；失败时保留打印出的 bootstrap 路径。

```powershell
. {
    $Tag = '<tag>'
    $ExpectedCommit = '<40-hex>'
    $ExpectedZipSha256 = '<64-hex>'
    $SavedGitConfigNoSystem = [Environment]::GetEnvironmentVariable('GIT_CONFIG_NOSYSTEM', 'Process')
    $SavedGitConfigGlobal = [Environment]::GetEnvironmentVariable('GIT_CONFIG_GLOBAL', 'Process')
    $SavedGitConfigCount = [Environment]::GetEnvironmentVariable('GIT_CONFIG_COUNT', 'Process')
    $SavedGitTerminalPrompt = [Environment]::GetEnvironmentVariable('GIT_TERMINAL_PROMPT', 'Process')
    $SavedGcmInteractive = [Environment]::GetEnvironmentVariable('GCM_INTERACTIVE', 'Process')
    $SavedGitAskPass = [Environment]::GetEnvironmentVariable('GIT_ASKPASS', 'Process')
    $SavedSshAskPass = [Environment]::GetEnvironmentVariable('SSH_ASKPASS', 'Process')
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $ExpectedZipSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Fill the three verified release values first' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'Bootstrap path already exists' }
        Write-Host "Bootstrap: $Bootstrap"
        try {
            $env:GIT_CONFIG_NOSYSTEM = '1'
            $env:GIT_CONFIG_GLOBAL = 'NUL'
            $env:GIT_CONFIG_COUNT = '0'
            $env:GIT_TERMINAL_PROMPT = '0'
            $env:GCM_INTERACTIVE = 'Never'
            $env:GIT_ASKPASS = ''
            $env:SSH_ASKPASS = ''
            git -c credential.helper= -c credential.interactive=never -c core.askPass= -c http.extraHeader= -c core.hooksPath=NUL clone --config core.autocrlf=false --config core.hooksPath=NUL --branch $Tag --single-branch https://github.com/caomz/crm-sre-team.git $Bootstrap
            if ($LASTEXITCODE -ne 0) { throw 'GitHub bootstrap clone failed' }
        } finally {
            [Environment]::SetEnvironmentVariable('GIT_CONFIG_NOSYSTEM', $SavedGitConfigNoSystem, 'Process')
            [Environment]::SetEnvironmentVariable('GIT_CONFIG_GLOBAL', $SavedGitConfigGlobal, 'Process')
            [Environment]::SetEnvironmentVariable('GIT_CONFIG_COUNT', $SavedGitConfigCount, 'Process')
            [Environment]::SetEnvironmentVariable('GIT_TERMINAL_PROMPT', $SavedGitTerminalPrompt, 'Process')
            [Environment]::SetEnvironmentVariable('GCM_INTERACTIVE', $SavedGcmInteractive, 'Process')
            [Environment]::SetEnvironmentVariable('GIT_ASKPASS', $SavedGitAskPass, 'Process')
            [Environment]::SetEnvironmentVariable('SSH_ASKPASS', $SavedSshAskPass, 'Process')
        }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' -ErrorAction Stop
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -RunPytest
        if ($LASTEXITCODE -ne 0) { throw 'UPDATE stopped; retain bootstrap, reports and backups' }
    } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

`UPDATE` 先运行完整 PLAN，再按需自动执行合成 DRILL（不额外询问 YES），最后显示真实路径、版本、备份和哈希，等待 YES 后 APPLY。任一步失败立即停止；拒绝 YES 时不写真实安装来源/marketplace，已生成的 clone、计划及演练现场保留。需要重演练就在同一命令末尾加 `-Drill`。默认 Python 路径不存在时显式加 `-PythonExe`；脚本哈希只有需要额外核验时才加 `-ExpectedScriptSha256`。

安装结束打印的 **VERIFY 命令已填好脚本路径、Tag、ExpectedCommit、ExpectedZipSha256、PlanPath、PlanSha256、GitExe**，不需要抄写计划路径或计划哈希。打开客户端、选择该新版本，新开会话贴本轮交接的“自检 1”，然后原样运行打印出的命令。

未提供 `SessionId/AgentId` 时，VERIFY 仅按固定两层枚举列出 **APPLY 完成时间之后修改过的主会话**：会话 ID、大小、UTC 创建/修改时间及项目名；不读内容，不核验 cache，不生成成功报告，然后停止并提示选定 SessionId 重跑。每个候选会话旁打印已填 SessionId 的 VERIFY 命令。选择自检 1 的记录运行它，才开始来源/cache 核验与取证；没有成员的会话只取团长记录，省略 AgentId。进程退出码 0 的候选列表表示枚举完成，**不代表 VERIFY 验收完成**。

`-RunPytest` 可省略；此时 PLAN 仍运行 build/check_workbuddy/validate_bundle/build_release/validate_release，但报告记 `pytest_requested=false`。不能把省略的测试写成通过。也可传 `AgentId` 通过成员父目录唯一定位，或同时传两个 ID 并校验一致。

## 单独模式（排错与回退）

这些模式仍使用 PLAN 输出的路径和哈希，适合检查现场及恢复；完整更新使用上面的 UPDATE。

```powershell
$ReleaseArgs = @('-Tag','<tag>', '-ExpectedCommit','<40-hex>', '-ExpectedZipSha256','<64-hex>')
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode PLAN @ReleaseArgs -RunPytest
# 只在 PLAN 成功后填写它实际输出的值；不要修改计划后重新算哈希。
$Plan = 'D:\crm-v36-handoff\update-<GUID>\install-plan.json'
$PlanHash = '<PLAN-printed-64-hex>'
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode DRILL @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash
# 只有 DRILL 成功且审阅报告后才执行 APPLY；单独 DRILL/APPLY 各自需要 YES。
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode APPLY @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash
# 客户端运行自检 1 后，明确 SessionId；无成员就不要传 AgentId。
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash -SessionId '<this-session-id>'
```

## 各模式的核验与产物

| 模式 | 行为 | 报告/判据 |
|---|---|---|
| UPDATE | 进程内 PLAN → `-Drill` 或本机无成功报告时 DRILL → 打印真实安装计划 → 一次 YES → APPLY；任一步失败停止 | 自动传递 PlanPath/PlanSha256；结束打印参数已填好的 VERIFY 命令；成功 DRILL 只证明合成 APPLY/ROLLBACK，不证明宿主验收 |
| PLAN（默认） | 从已校验工作树本地标签 clone（独立脚本才从 GitHub clone）；终端和 `clone.txt` 显示来源；HEAD 与标签均等于 ExpectedCommit；检查前工作树干净；检查后只允许 manifest 精确声明的生成报告变化，其他文件仍须干净；检查前后全部发布文件哈希相同；离线检查；现有确定性打包；Mac SHA256 对比；5A 解压后严格集合和逐文件哈希 | `install-plan.json` 包含全部路径、版本、备份、marketplace 条目与原哈希、旧来源 VERSION/申报哈希、cache 版本目录名、全部包哈希、manifest/脚本哈希；`install-plan.sha256` 和终端打印同一计划哈希；各命令单独日志 |
| APPLY | 校验计划/脚本哈希，来源快照和包仍一致；进程退出；YES 后再次核验；原块 20 备份、移动、复制、严格 VERIFY、仅在条目含有效 version 字段时更新 marketplace | 备份内 `install-state.json` 按阶段持久化；`apply-report.json` 记录 `completed_utc`。复制后不得应用 settings.json 例外 |
| VERIFY | 无 ID 时只列 APPLY 后写过的主会话元数据并停止；指定会话后按 manifest 核对来源和目标 cache，并取证 | 唯一缺根 settings.json 输出 `N-1/N, root settings.json missing (host-managed)`，实际打印数值；存在必须哈希一致；其他缺失/差异失败；额外文件只列路径。指定会话完成后报告 `verify-<GUID>.json`，仍需人工宿主验收 |
| ROLLBACK | 从该 PLAN 的 StatePath 恢复阶段/哈希；校验原来源备份与 marketplace 没有后续变动；仅 INSTALLED 计划要求当前来源仍是该计划包（只允许缺宿主管理的根 settings.json），YES 后重查；失败 APPLY 的其他阶段沿原块 22 恢复 | `rollback-<GUID>.json`；保留失败来源及当前 marketplace 原字节；拒绝时转 runbook 5C；不删 cache，不单独补写/恢复 settings.json。客户端重新选旧活动版本，再人工核对旧 cache |
| DRILL | 在 `D:\crm-v36-handoff\drill-<GUID>` 建合成来源/marketplace，用同轮已验证暂存包为候选，执行原块 20 → 状态重新读取 → 原块 22 | `drill-plan.json`、`drill-report.json`、备份/状态/failed-source；独立模式需 YES，UPDATE/SWITCH 内自动运行；UPDATE/SWITCH 仅在报告为成功且关联状态为 DRILL/NONE/ROLLED_BACK 时允许复用；不新增故障注入 |

`APPLY` 显示 `INSTALLED` 后，须在客户端刷新市场并更新到计划的 `$Version`，再开新会话、粘贴自检 1 并运行打印出的 VERIFY 命令；客户端不会自动更新到新版本。marketplace 条目缺少 `version` 时也要完成这些操作。

取证仅在固定 `projects → project → session` 两层枚举：主会话取 `project\<SessionId>.jsonl`；成员取 `project\<SessionId>\subagents\<AgentId>.jsonl`。零匹配/多匹配/ID 不一致/链接会停止，不递归搜宿主目录。按块 26 的 ReadShared 读取原字节、写副本、校验 SHA256SUMS；从解析后的 JSON 节点以 `callId` 关联 `Skill` 调用与 `function_call_result`，要求回执路径包含完整目标 cache/version/skills。回执结构无法识别、截断或没有匹配路径均停止，保留证据供人工判断。记录副本可能包含会话内容，只存本机交接目录，不外发。

VERIFY 的 cache 文件完整性、Skill 回执路径和团长 Agent 正文加载是不同证据：报告不据前两者声称已完成后者。根 settings.json 的宿主管理例外适用于客户端运行后的来源/cache，以及 INSTALLED 计划 ROLLBACK 写入前的当前来源检查；5A 和复制后的严格 VERIFY 保持原口径。

## 失败恢复

部分或失败 APPLY 后保留所有目录并停止启动客户端。计划记录了 StatePath；先核对该状态和备份，再退出客户端，使用该计划及原 bootstrap 运行下列 ROLLBACK。非 INSTALLED 阶段不执行 R6 当前包比对，保留原块 22 的失败恢复行为；ROLLBACK 拒绝时转 runbook 5C 人工评审恢复：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode ROLLBACK @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash
if ($LASTEXITCODE -ne 0) { throw 'ROLLBACK stopped; preserve all evidence and follow runbook 5C human recovery' }
```

marketplace 备份未完成、旧来源丢失、状态与计划不一致、旧来源备份字节改变、marketplace 有安装后的独立变更，均停止自动回退，按 runbook 5C 人工处理。不要修改状态文件让检查通过。**失败 APPLY 后，必须先恢复它（ROLLBACK 或 5C），再进行任何新的 SWITCH/UPDATE。** 重复 APPLY 同一计划拒绝；已 ROLLED_BACK 再回退拒绝。新的安装必须重新 PLAN，或用 SWITCH 创建新的独立计划。多个 INSTALLED 计划须从最新计划向前回退；较旧计划若当前来源已变，会提示先回退最新计划，或 SWITCH 到需要的包。

## PowerShell 5.1 / .NET Framework 4.x 静态语义审计

按启动身份校验 → PLAN → DRILL → APPLY → VERIFY，及 ROLLBACK 的执行顺序逐行审计全部非 R2 编排。以下结论来自代码阅读、Python 静态回归和 Mac 上检查工具的实际输出；本机没有 PowerShell，不包含 PS 解析或运行测试。所有 R2 逐字片段及块 20/22 保持原字节。

| 历史缺陷位置（7a3b118 的脚本行号） | 后果 | 最小修法与回归约束 |
|---|---|---|
| `Invoke-Native`：271、273 | 函数内赋值创建局部 `$LASTEXITCODE`，读取到 `$null`，首个 `rev-parse` 即报 `exit=` 停止；该故障已在值班机出现 | 重置和读取均改用 `$global:LASTEXITCODE`；静态测试禁止非 global 赋值，并断言调用前重置、调用后读取 |
| `Assert-CloneIdentity`：498–512；PLAN：711–712 | `validate_bundle` 的生成报告会因宿主 symlink 能力不同而改变；合法检查通过后，末尾仍可能因 dirty clone 停在 PLAN。Mac 已复现报告差异 | 初始校验要求全工作树干净；检查后仅以 literal Git pathspec 排除 manifest 精确声明且不在 `files` 内的报告，并再比较全部发布文件哈希；静态测试约束开关、白名单和核验顺序 |
| `Collect-SessionEvidence`：637 | 默认哈希表将大小写不同的 `callId` 视为同一键，可能把其他调用的结果错配为 Skill 回执 | 使用 .NET Framework 支持的 `Hashtable(StringComparer.Ordinal)`；静态测试锁定比较器及 ID 写入/读取 |

| 项目 | 已查结论 |
|---|---|
| (a) 自动变量作用域 | 已修复 `$LASTEXITCODE` 遮蔽。非 R2 编排不依赖 `$?`、`$Matches`、`$input`、`$args`；`$_` 仅用于当前管道或 catch，没有跨嵌套块借用。R2 的外层异常另存 `InstallError`，原片段保持不变 |
| (b) 函数输出、数组 | 未发现其他缺陷。目录 `New-Item` 均 `Out-Null`；队列 `Enqueue` 返回 void，`Dequeue` 赋值捕获；没有 `ArrayList.Add` 或 `Directory.CreateDirectory` 输出泄漏。集合函数的计数/比较调用均用 `@()`，可处理空结果和单元素；哈希表和记录对象按单对象返回，`Write-Host` 不混入成功输出 |
| (c) JSON 与 PSCustomObject | 未发现其他缺陷。JSON 直接赋值，不用 `@(ConvertFrom-Json ...)` 统计根数组；JSONL 根数组由节点队列显式展开。`files/expected_names/plugins` 等集合在消费处处理，空/null 不可绕过必要文件、条目和路径检查；计数不依赖 PS 5.1 的 PSCustomObject `.Count`。JSON 写入传单个对象并设 Depth 100，原状态 Depth 10 足够容纳安装计划，重新加载比较用 Depth 20；没有 PS6+ JSON 参数 |
| (d) 大小写 | 已修复 `callId` 键比较。标签、版本、类型、SessionId 和文件集合使用区分大小写的比较；Windows 路径、十六进制哈希使用不区分大小写的比较。manifest 去重拒绝 Windows 下会碰撞的路径，marketplace 的默认 `-eq` 过滤后仍由 `Assert-MarketEntry` 检查精确名称/唯一性；回执路径 `Sort-Object -Unique` 按 Windows 路径语义去重 |
| (e) 原生命令参数 | 未发现其他缺陷。实际参数没有独立空字符串或内嵌双引号；`credential.helper=` 等是非空参数。固定路径含空格时由数组参数传递；Python `-c` 代码没有内嵌双引号。打印的 VERIFY 命令用单引号并把内部单引号加倍。新 literal pathspec 没有空值或内嵌引号 |
| (f) 版本/API | 未发现其他缺陷。所用 Queue、Hashtable 比较器、SHA256、UTF8Encoding、共享文件读取、DateTime.ParseExact 及字符串/路径重载均存在于 .NET Framework 4.x；`::new`、Get-FileHash、Expand-Archive、文件/目录筛选参数支持 PS 5.1，没有 PS6+ 专属 API 或参数 |
| (g) 错误与空结果 | 已修复生成报告导致的 PLAN 误停。cmdlet 在 Stop 下终止流程；`Get-ChildItem` 空结果由 `@()` 转为空集合，读取失败仍会抛错。`Get-Process` 仅客户端检测使用 SilentlyContinue；原生命令临时用 Continue 捕获 stderr，之后恢复偏好并检查 global 退出码 |
| (h) 点源上下文 | 未发现其他缺陷。主分派 `. Invoke-OncallMode`、`. Prepare-InstallContext`、`. Import-PlanContext`、`. Initialize-Stages`、`. Import-InstallState` 均在调用方作用域赋值；`Set-Variable` 也落在该作用域。DRILL 后 APPLY 重新读取 REAL 计划，不复用合成路径；R2 retry 块仅执行 IO，不承担状态变量写回 |
| (i) 交互 | 未发现其他缺陷。UPDATE 直接以 `powershell -File` 启动，未捕获或重定向该进程；计划和 Read-Host 可见，仅大写 YES 通过。拒绝/无交互输入停止，独立 DRILL 和 ROLLBACK 保留各自确认门 |
| (j) 路径参数 | 未发现其他缺陷。Join-Path 都只有 Path/ChildPath 两个位置参数；现有文件读取、检查、复制、移动、哈希使用 LiteralPath。New-Item 没有 LiteralPath，所建目录使用固定根和受约束 GUID；没有可进入路径的 wildcard 值 |

Windows 后续核验顺序：本地 bootstrap → 启动身份校验 → PLAN → 强制 `-Drill` 的合成安装/状态重读/恢复 → 审阅计划并 YES → 客户端自检 1 → 指定 SessionId 的 VERIFY；ROLLBACK 和文件占用/故障路径仍按现场评审执行。当前静态通过不能替代这些运行证据。

## 复用来源与本地检查

只读来源：`/Volumes/HDD/download/v364-runbook-r2/ONCALL_RUNBOOK.md`，文件 SHA256 `50ed48a24dcdd9a06705c4475acbe8596d74e1b4b639fe89b696d6202d068f77`。

- 块 17 的解压/严格集合/哈希片段逐字复用；块 19 的路径断言、selected hashes、Invoke-IoRetry、Save-InstallState 辅助函数逐字复用，编排单独初始化变量。
- 块 20 全块 SHA256 `5b0d3710558af44aeac59e8d7a73b6d61521bb42ef7db38f84e1d7beea0dc431`，块 22 全块 SHA256 `1774e3b4d40e778caad99946079a43a55690e81175aa9c47dabaa3a22cdaddad`；APPLY/DRILL 和 ROLLBACK/DRILL 中各两份完全相同。块 20 沿用已有 PS 5.1 的 5D 73/73 与 REAL 安装验证。
- 块 19 r2 的宿主检查函数、块 21、块 26 原说明均标未在 Windows 实跑；这里动态文件数、客户端后核验、会话定位/Skill 回执关联、所有新增编排也标 **未在 Windows 实跑**。本次没有承诺继承原脚本的 Windows 验证结论。

```bash
python3 tools/build_bundle.py
python3 -m pytest tools/oncall/test_oncall_updater.py -q
python3 -m pytest tests/ -q
python3 tools/check_workbuddy.py
python3 tools/validate_bundle.py
```

专项测试含真实 HEAD 克隆、四种 probe 与一次 N/S 构建、提取内嵌 Python 校验器的功能正反例；并验证 BOM/编码、静态 PS 5.1 禁用语法、八模式/新参数、bootstrap 自检、已校验工作树的本地 clone 与独立脚本 GitHub 备选、来源日志、README 本地提交核验/引用复制/标签绑定/UPDATE 顺序与环境恢复、确认门、默认 Python 路径、APPLY 时间与只列元数据的 VERIFY、原块/辅助函数固定 SHA256、精确清单、ZIP 排除。**没有 PowerShell 时不把这些检查描述为 PowerShell 解析或运行测试。** Windows 仍需 DRILL、真实 APPLY、客户端后的 VERIFY/取证以及故障/文件占用分支的现场验证。开发代码回退使用仓库外保存的原字节备份：恢复复核前的三个 `tools/oncall/` 文件并重新 build；本次不提交、不推送、不打标签，也不执行 Git 回退或删除操作。

## 实验集合与切包（NOT RUN ON WINDOWS）

本节保留 10-12 rc3 工具交接记录，**NOT RUN ON WINDOWS / PS 5.1 NOT RUN**。Mac 运行真实构建器和从 `.ps1` 提取的同一 Python 校验器；这些结果不证明 PowerShell 编排、交互、安装/回退或宿主加载通过。rc4 的实际步骤按本页“rc4 使用流程”：Mac 完成全部测试并验收，值班机只做安装/切换 + VERIFY + 记录版本。下列 rc3 bootstrap 与 runbook r4 块 23/24 保留原文；关口材料与判据按 docs/11–13 保持。

### 1. 从本地项目取得新 bootstrap，只做 EXPBUILD

必须使用包含此修改的**新提交/新标签**；交接人审核、另获提交/推送授权并核对后提供 `<new-tag>` 和 `<new-40-hex>`。本次不提交、不推送、不创建标签。`crm-sre-team-2.8.0-rc3-oncall3 / 7a3b118` 不含新模式，不能当新交接值。ZIP 仍须为下列既有 SHA256。本机只访问 `D:\python_code\github_my\crm-sre-team`，没有目标提交就停止，由人先准备本地项目。退出客户端；整个块由人粘贴到普通 PowerShell 5.1 窗口。末行运行 EXPBUILD，不运行 UPDATE，不重新安装当前正式包。

```powershell
. {
    $Tag = '<new-tag>'
    $ExpectedCommit = '<new-40-hex>'
    $ExpectedZipSha256 = 'c543e5d2fec31607963d791e5c13e7d194e0a989dff07714661bea249b074f41'
    $SourceRepo = 'D:\python_code\github_my\crm-sre-team'
    $SavedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Tag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$' -or $ExpectedCommit -notmatch '^[0-9a-fA-F]{40}$' -or $ExpectedZipSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Fill the three verified release values first' }
        if (-not (Test-Path -LiteralPath $SourceRepo -PathType Container -ErrorAction Stop)) { throw 'Local project missing' }
        git -C $SourceRepo -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}') 2>$null
        if ($global:LASTEXITCODE -ne 0) { throw 'Local project does not contain the target commit yet; update it first, then rerun' }
        $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N')
        if (Test-Path -LiteralPath $Bootstrap -ErrorAction Stop) { throw 'Bootstrap path already exists' }
        Write-Host "Local project has $ExpectedCommit; bootstrap=$Bootstrap (no network)"
        git -c core.hooksPath=NUL clone -q --no-local --no-checkout --config core.autocrlf=false --config core.hooksPath=NUL $SourceRepo $Bootstrap
        if ($global:LASTEXITCODE -ne 0) { throw 'Local bootstrap clone failed' }
        git -C $Bootstrap -c core.hooksPath=NUL fetch -q --no-tags $SourceRepo '+refs/remotes/*:refs/crm-source-remotes/*'
        if ($global:LASTEXITCODE -ne 0) { throw 'Copying local remote-tracking refs failed' }
        git -C $Bootstrap -c core.hooksPath=NUL cat-file -e ($ExpectedCommit + '^{commit}')
        if ($global:LASTEXITCODE -ne 0) { throw 'Target commit is not reachable from local project refs' }
        git -C $Bootstrap -c core.hooksPath=NUL tag -f $Tag $ExpectedCommit
        if ($global:LASTEXITCODE -ne 0) { throw 'Bootstrap tag failed' }
        git -C $Bootstrap -c core.hooksPath=NUL checkout -q --detach $Tag
        if ($global:LASTEXITCODE -ne 0) { throw 'Bootstrap checkout failed' }
        $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' -ErrorAction Stop
        powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode EXPBUILD -Tag $Tag -ExpectedCommit $ExpectedCommit -ExpectedZipSha256 $ExpectedZipSha256 -RunPytest
        if ($global:LASTEXITCODE -ne 0) { throw 'EXPBUILD stopped; retain bootstrap and reports' }
    } finally {
        $ErrorActionPreference = $SavedErrorActionPreference
    }
}
```

`EXPBUILD` 无 YES 门：仅在全新本地构建目录写输出，不读写 WorkBuddy。从启动身份校验通过的 bootstrap 本地 clone 到新 `D:\Dev\crm-oncall-<GUID>\repo`，新 `D:\crm-v36-handoff\experiment-<GUID>` 保存 ZIP、5A 解包、日志、临时文件、实验包和集合。独立脚本没有已验证工作树时拒绝 EXPBUILD/SWITCH，不走 GitHub 备选。正式 PLAN/UPDATE 的备选行为保留。

与 PLAN 共用正式准备：严格干净 clone → 重建与申报文件零差异 → check_workbuddy / validate_bundle → 可选 `-RunPytest` 全量及专项测试 → 确定性发行 ZIP → ExpectedZipSha256 比对 → validate_release → 5A 精确解包。实验构建前后仅允许 manifest 精确声明的生成报告变化；所有发布文件须与原字节一致，内嵌校验器另用 Git `cat-file --batch` 核对 SHA256 等于 HEAD 原始 blob。

一次构建普通 probe、一次 comparison 的 N/S、三种独立 disallow probe；不加 maxTurns、不混用限制。以下包名大小写固定：

| `-Package` | 内容 | 版本来源 / 元数据 |
|---|---|---|
| `formal` | 同轮已校验 ZIP 的严格解包；回正式包的快捷路径 | clone 的 VERSION；无额外元数据 |
| `probe` | LA/LS 与七成员 C/D；无 disallowedTools | `<source>-probe.r<suffix>`；probe-manifest.json |
| `cmp-n` | NATIVE_LEAD 保留；LOAD-N 行 | `<source>-cmp-n.r<同轮suffix>` |
| `cmp-s` | 固定单模型 closure；LOAD-S 行 | `<source>-cmp-s.r<同轮suffix>` |
| `probe-webfetch-denied` | 仅 oracle-dba 的 WebFetch 限制 | 独立 probe 版本、manifest 与 suffix |
| `probe-bash-denied` | 仅 oracle-dba 的 Bash 限制 | 独立 probe 版本、manifest 与 suffix |
| `probe-powershell-denied` | 仅 oracle-dba 的 PowerShell 限制 | 独立 probe 版本、manifest 与 suffix |

每个实验 manifest 均核 source_commit（非 unknown 的 HEAD 前缀）、按 release_files 顺序串联 UTF-8 路径+NUL+原 SHA256 的 source_tree_sha256、source_version（同时等于 VERSION 和 plugin.json）。probe 核精确文件集合、全部版本、角色派生的 16 prompt / 10 version / 8 ZIP 差异、各正确文件的 LA/LS/C/D、全部 ZIP 与 Skill 树逐文件相同、仅 oracle-dba 的指定 disallowedTools；普通 probe 不得有该字段。N/S 核 pass / normalized / no missing-unexpected、实际 N/S 差异集合（团长双文件+版本+ZIP）、closure、同 suffix LOAD 行和 ZIP 内容。名单从 roles-source.json 派生，不固定 rc2/rc3 版本。实验锁保留源版本是设计行为，不运行正式 validate_bundle/validate_release 去检查实验副本的锁。

内嵌 Python verifier 的 `build` 直接新建 `experiment-set.json`，已存在即拒绝；使用 `sort_keys=True / ensure_ascii=True`、紧凑分隔符、UTF-8 无 BOM + 末尾 LF 确定性序列化。记录 tag/commit/正式 ZIP SHA256、源码摘要/版本、脚本 SHA256、UTC、每包路径/版本/精确名单/每文件 SHA256/元数据/标记/限权、五份 builder manifest 的 SHA256。verifier 只打印短状态；PowerShell 不解析其 stdout、不重新序列化集合，只用 Get-FileHash 取得哈希、写 `experiment-set.sha256` 并在终端打印：

```text
ExperimentSet=D:\crm-v36-handoff\experiment-<GUID>\experiment-set.json; ExperimentSetSha256=<64-hex>
```

保留这一套原始集合与哈希；整轮 WB 前置、T02 与 18 次关口只用**一套集合、一对同次构建 N/S**，不为缓存往返或补次数重建。集合输出不是宿主 PASS。重新 EXPBUILD 是新一轮；已开跑时不得换包或修改判据。

### 2. SWITCH → 客户端刷新/更新 → 新会话 → VERIFY

在上述普通窗口填写打印值；`$Script / $Tag / $ExpectedCommit / $ExpectedZipSha256` 沿用新 bootstrap。每次切包先退出客户端，由人执行一条 SWITCH；它创建新计划、展示完整内容、复用成功本地 DRILL（无报告时自动用所选候选包演练）、要求一次大写 `YES`，随后执行原字节块 20。可追加 `-Drill` 强制重做本次合成演练，仍只需一次安装 YES。

```powershell
$ReleaseArgs = @('-Tag', $Tag, '-ExpectedCommit', $ExpectedCommit, '-ExpectedZipSha256', $ExpectedZipSha256)
$SetPath = 'D:\crm-v36-handoff\experiment-<GUID>\experiment-set.json'
$SetHash = '<EXPBUILD-printed-64-hex>'
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode SWITCH @ReleaseArgs -ExperimentSet $SetPath -ExperimentSetSha256 $SetHash -Package probe
if ($global:LASTEXITCODE -ne 0) { throw 'SWITCH stopped; retain the printed plan, reports and backups' }
```

新参数/门：`-ExperimentSet`、`-ExperimentSetSha256`、`-Package` 只用于 SWITCH，三个都必填；Package 必须为上表原样小写。拒绝 PlanPath/PlanSha256、会话 ID 或 `-RunPytest`，它们不用于切包构建。先核客户端退出 → 集合文件 SHA256 → 同 Tag/ExpectedCommit/ExpectedZipSha256/脚本 SHA256 → 固定集合路径与选定包精确集合/逐字节重哈希（含 builder manifest 与正式 ZIP）。这些检查通过才创建安装计划。`-ExpectedScriptSha256` 仍为可选附加身份检查；`-PythonExe/-GitExe` 含义不变，SWITCH 的 Python 与 EXPBUILD 使用同一已核对环境，不自动安装依赖。

verifier 的 `select` 在本次全新 `update-<GUID>` 新建 `selection.json`（已有文件即拒绝），仅保存 PowerShell 需要的集合路径/编号/源摘要和所选包字段，使用同样的 ASCII JSON 编码。PowerShell 用 ReadShared 读取该文件并一次 ConvertFrom-Json，原生命令 stdout 只作为状态日志。正常安装计划仍由已在 Windows 验证过的 Write-NewJson 路径写出；集合/选择数据不经过 PowerShell ConvertTo-Json。

每次将选定包复制到新 `update-<GUID>\install-clean\crm-sre-team` 并重核，同时复制并核对正式 ZIP 到该计划的 release.zip，计划自包含包快照，绑定版本、哈希、标记、元数据、集合与脚本；不为 SWITCH 再 clone 或重新构建 N/S。备份 label 为包名，路径 `backups\crm-v36-<本次GUID>-<package>`，避免覆盖前次计划/备份。REAL 市场和 cache 根仍固定。YES 后重载计划、退出检查、候选包与旧来源快照检查再执行块 20；probe-manifest.json 与全部发布文件一起复制/严格校验。

INSTALLED 会打印本计划的 VERIFY 命令与包种类；它只代表来源安装完成。真实市场条目**没有 version 字段，允许且不写 marketplace.json**。人打开客户端，刷新市场并更新到终端显示的**该包版本**，完成 VERIFY 的来源/缓存和 Skill 回执路径核对；仅在需确认宿主行为时加一个短会话。已有 N/S/probe/formal cache 也经客户端重新选择，不删 `.in_use/<pid>` 或改 cache/settings.json。

```powershell
# 从这次 INSTALLED 输出复制本计划参数；不是前一次的计划。
$Plan = 'D:\crm-v36-handoff\update-<THIS-SWITCH-GUID>\install-plan.json'
$PlanHash = '<THIS-SWITCH-printed-64-hex>'
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode VERIFY @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash -SessionId '<this-session-id>' -AgentId 'agent-<this-member-id>'
if ($global:LASTEXITCODE -ne 0) { throw 'VERIFY incomplete; retain local evidence and report the original output' }
```

无成员去掉 `-AgentId`；也支持只给 AgentId 唯一反查父会话。无 ID 的 VERIFY 仅列 APPLY 之后写过的主会话元数据，不生成验收 PASS。实验 VERIFY 根据**该计划**的版本、期望集合（probe 多 probe-manifest.json）与 `CacheRoot\<package version>` 检查，Skill 回执必须含该版本的 cache 路径。唯一缺宿主管理的根 settings.json 明确打印 N-1/N，N 取该计划的期望文件数（正式 rc3 为 516/517，正式 rc4 为 517/518）；存在须字节相同；其他缺失/差异失败，`.in_use/<pid>` 等额外路径只列名称。

取证副本、SHA256SUMS、skill-receipts.json 保持仅本机。实验另输出 marker-counts.json 和终端原始字符串计数：probe 的 PROBE-LA/LS/C/D-同 suffix 或 N/S 完整 LOAD 行，在**每份复制记录**中计数。它包含 prompt/工具返回/回复等任意位置，也可能因 JSON 转义计不到；明确为 **raw aid / location unknown / NOT A VERDICT**，不能替代宿主回执、逐时序审计或模型回复中的标记核验。未找到目标 Skill 回执时，副本及计数保留，VERIFY 仍失败；按原 runbook 26 或人工审阅取证，不补写成功。工具不访问或输出 gold/关口答案。

### 3. Mac 验收使用的包与顺序

以下提示词与宿主验收全部在 Mac 运行；错峰切包，每次更新后新会话，逐次保存实际版本、来源/缓存、Skill 回执与调用证据。Mac 测试段结束立即回 formal，跑完后提交结果供人工复核并验收。Windows 安装/切换 + VERIFY 的计划另行绑定，**NOT RUN ON WINDOWS**。输入/评分协议、工具可审计前置、WB07 HOST_LIMIT 的判读不变，WB09H 仍须真实 PASS 才能校准/关口；max_turns 的有效值被钳到不低于 200，不是每个成员实际执行 200 轮。

| 剩余步骤 | Package 与顺序 | 记录要求 |
|---|---|---|
| WB09H | `probe` → `formal` | 无害注入，真实 PASS；不运行含凭据诱饵的 WB09 原版 |
| 候选加载核验 | `probe` → `formal` | PROBE-LA/LS/C/D 同 suffix；Skill 路径/版本、Agent 参数和实际返回交叉审计 |
| 7A 审计演练 | `probe`（七个独立成员会话）→ `formal` | 七成员注册 ID、每份实际参数/返回；PROBE 只辅助 |
| 7B 往返 | `cmp-n` → `cmp-s` → `cmp-n` cached → `probe` → `formal` → `probe` cached → `formal` cached | Mac 各次独立切换/备份/新会话；同一 N/S 对与 probe；核活动 Skill 回执和实际标记 |
| WB14 | `probe-webfetch-denied` → `formal` | Oracle 指定 WebFetch 的真实宿主拒绝回执；失败后不换工具绕过 |
| WB17 | `probe` 基线 → `probe-bash-denied` → `formal` | 先确认 Bash 确实可用；指定 echo，真实宿主拒绝才算限制证据 |
| WB17 PowerShell 备选 | `probe` 基线 → `probe-powershell-denied` → `formal` | 仅在基线实际终端为 PowerShell 时采用；独立会话，不在拒绝后换工具 |
| T02 校准 x2 | 同集合 N/S；校准后 `formal` | 两次不计分；建议 cmp-n、cmp-s 各一次（先 N 后 S），开跑前由用户确认并记录；不改变评分口径 |
| C1 六次 | `cmp-n` `cmp-s` `cmp-s` `cmp-n` `cmp-n` `cmp-s` → `formal` | N S S N N S |
| C2 六次 | `cmp-s` `cmp-n` `cmp-n` `cmp-s` `cmp-s` `cmp-n` → `formal` | S N N S S N |
| C3 六次 | `cmp-n` `cmp-s` `cmp-s` `cmp-n` `cmp-n` `cmp-s` → `formal` | N S S N N S；共 18 runs，整轮同一 N/S pair |

WB16 与正式自检在 Mac 用 `formal`；WB11/WB14/WB15 在 Mac 单独公开无害测试，不混入离线 N/S 关口。安装与取证由人在会话外执行；不授予被测会话读文件、写日志或生产权限。生产写请求只产出人工评审需求。

宿主若拒绝 rc/probe/cmp **预发布后缀**，立即停止，报告包版本、来源、客户端版本与原始报错；回 Mac 另定纯数字候选版本与同轮编号/回退路径并重新全量验证。不要在安装目录改版本，不用正式 2.8.0 当测试号，不把版本拒绝改算模型失败。

### 4. 回 formal、计划绑定与回退

```powershell
# 先退出客户端；复用同一 SetPath/SetHash。快捷恢复正式 rc3 字节。
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode SWITCH @ReleaseArgs -ExperimentSet $SetPath -ExperimentSetSha256 $SetHash -Package formal
if ($global:LASTEXITCODE -ne 0) { throw 'Return to formal stopped; retain evidence' }
# 人在客户端刷新/更新到集合的 source_version，开新正式会话。
# 使用本次打印的 VERIFY 命令，追加这次 SessionId；不用之前的实验计划。
```

formal SWITCH 不重建正式包；UPDATE 仍是完整重建路径。**每个计划的 VERIFY/ROLLBACK 都用创建该计划的原 bootstrap 脚本与原 Tag/ExpectedCommit/ExpectedZipSha256/PlanSha256**。新计划绑定新脚本 SHA256，不能借用旧 bootstrap；同样不能用新脚本处理旧计划。

10-12 的 `update-effac22650784f529d6274dd570d511c` / PlanSha256 `05225a8ecb8f12c6c4f46a15984c7aa6d2567761b4046b289aa386a667d2a202` 继续仅由 **7a3b118 原 bootstrap** 验证/回退（路径以当时打印的 -File 为准，runbook 13.3/13.4）。它没有新增 R6 防护；多次新切包后不可把旧计划当“回正式包”的捷径，要用新集合 SWITCH formal；若真要退到旧计划的前一版本，先按最新计划逐层恢复并人工核对到 10-12 安装状态，再决定是否使用旧 bootstrap。

新 ROLLBACK 的 R6 仅用于导入状态为 **INSTALLED** 的计划：在 YES 前、重载计划/退出检查之后各核一次当前来源申报哈希（probe 包含 manifest），允许唯一缺根 settings.json；其他不符时**写入前拒绝**，提示“roll back the newest plan first, or SWITCH to the wanted package”。因此若新计划已装了不同包，不能用较旧的 INSTALLED 计划覆盖它。安装相同字节的另一个计划不能靠内容比较区分，操作上仍必须从最新计划回退；不把字节相同当历史顺序证明。PLANNED / MARKET_BACKUP / SOURCE_MOVE / COPY / VERIFY / MARKET_WRITE 等非 INSTALLED 阶段不加 R6 门，沿原块 22 尝试失败恢复，原有备份/marketplace/路径校验不变；拒绝则转 5C。失败 APPLY 后，必须先恢复它（ROLLBACK 或 5C），再进行任何新的 SWITCH/UPDATE。cache 不单独回退；人重新选旧活动版本并核 cache。

### 5. 本轮设计选择与验证范围

- 采用共用正式准备的 EXPBUILD，避免正式 ZIP 路径分叉；采用新计划内复制快照，保证后续 APPLY/VERIFY 不依赖实验源目录仍可用。计划 `repo` 指向集合的源 clone，`zip` 指向本计划内的正式 ZIP 副本；固定 REAL 路径不变。
- ONE here-string Python 校验器写到新目录再执行，规避 PS 5.1 原生命令内嵌双引号问题；Mac 测试提取原文本，运行真实四种 probe/一对 N/S，读取 build 实际写出的 experiment-set.json、计算其 SHA256，再对七包运行 select 并读取 selection.json；检查结构及负例、集合 hash/身份与选定包重哈希。集合/选择文件均拒绝覆盖，避免约 600 KB 集合经 PS 5.1 JSON 往返序列化及 Invoke-Native 的 stderr 合并/脱敏影响数据。这组功能 fixture 在 Windows 明确 skip（临时路径与产品固定 D: 边界不同），静态测试继续运行；不以 skip 替代现场 DRILL/宿主验收。没有新增仓库文件或依赖。
- PowerShell 的退出检查、作用域、点源变量、两参数 Join-Path、LiteralPath、BOM/LF、禁止删除/强杀/网络命令、门顺序与固定块由静态测试约束；R6 申报比对/settings 例外、R5 原始计数在 Mac 用等价 Python 正反例验证，不能称为 PS 执行。外部脚本/集合身份也在提取校验器中重复核验并有功能负例。
- `Test-SuccessfulDrill` 原判据保留：成功合成 APPLY/ROLLBACK 报告及其 DRILL/NONE/ROLLED_BACK 状态可复用；不是本包宿主验收或故障注入证明。首次现场建议 SWITCH 加 `-Drill`，保存这次报告。
- **NOT_RUN**：全部新 PS 5.1 编排/解析、真实安装/客户端更新/版本拒绝、实验缓存选择/Skill/Agent 加载、宿主限权、WB09H/7A/7B/T02/18 runs、REAL 回退及新 R6 的 Windows 行为。不得据 Mac 测试写成宿主 PASS 或升级完成。

代码回滚：丢弃这三个未提交的 tools/oncall 文件修改即可（需操作人决定；本任务不执行 restore/reset）；无提交、无生产写入。交接 patch 与原始检查记录在仓库外保留。Windows 现场恢复按各自计划、R6 与 runbook 5C，不删除任何输出或证据。
