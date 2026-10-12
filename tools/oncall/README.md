# 值班机一键更新（Windows PowerShell 5.1）

只接收 Mac 已验证的 `Tag / ExpectedCommit / ExpectedZipSha256` 交接值。完整更新：**退出客户端 → 从本地项目取得目标提交并在新 bootstrap 运行 UPDATE → 输入一次 YES → 打开客户端贴自检 1 → 运行打印出的 VERIFY 命令**。`UPDATE` 在同一进程内执行 `PLAN → 必要时 DRILL → 打印安装计划 → YES → APPLY`，自动传递计划路径和哈希。原有五个模式保留供排错、核验和回退。

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
| APPLY | 校验计划/脚本哈希，来源快照和包仍一致；进程退出；YES 后再次核验；原块 20 备份、移动、复制、严格 VERIFY、更新 marketplace | 备份内 `install-state.json` 按阶段持久化；`apply-report.json` 记录 `completed_utc`。复制后不得应用 settings.json 例外 |
| VERIFY | 无 ID 时只列 APPLY 后写过的主会话元数据并停止；指定会话后按 manifest 核对来源和目标 cache，并取证 | 唯一缺根 settings.json 输出 `N-1/N, root settings.json missing (host-managed)`，实际打印数值；存在必须哈希一致；其他缺失/差异失败；额外文件只列路径。指定会话完成后报告 `verify-<GUID>.json`，仍需人工宿主验收 |
| ROLLBACK | 从该 PLAN 的 StatePath 恢复阶段/哈希；校验原来源备份与 marketplace 没有后续变动；YES；原块 22 隔离失败来源并恢复旧来源/marketplace | `rollback-<GUID>.json`；保留失败来源及当前 marketplace 原字节；不删 cache，不单独补写/恢复 settings.json。客户端重新选旧活动版本，再人工核对旧 cache |
| DRILL | 在 `D:\crm-v36-handoff\drill-<GUID>` 建合成来源/marketplace，用同轮已验证暂存包为候选，执行原块 20 → 状态重新读取 → 原块 22 | `drill-plan.json`、`drill-report.json`、备份/状态/failed-source；独立模式需 YES，UPDATE 内自动运行；UPDATE 仅在报告为成功且关联状态为 DRILL/NONE/ROLLED_BACK 时允许复用；不新增故障注入 |

取证仅在固定 `projects → project → session` 两层枚举：主会话取 `project\<SessionId>.jsonl`；成员取 `project\<SessionId>\subagents\<AgentId>.jsonl`。零匹配/多匹配/ID 不一致/链接会停止，不递归搜宿主目录。按块 26 的 ReadShared 读取原字节、写副本、校验 SHA256SUMS；从解析后的 JSON 节点以 `callId` 关联 `Skill` 调用与 `function_call_result`，要求回执路径包含完整目标 cache/version/skills。回执结构无法识别、截断或没有匹配路径均停止，保留证据供人工判断。记录副本可能包含会话内容，只存本机交接目录，不外发。

VERIFY 的 cache 文件完整性、Skill 回执路径和团长 Agent 正文加载是不同证据：报告不据前两者声称已完成后者。根 settings.json 的宿主管理例外只适用于客户端运行后的来源/cache，5A 和复制后的严格 VERIFY 保持原口径。

## 失败恢复

部分 APPLY 后保留所有目录并停止启动客户端。计划记录了 StatePath；先核对该状态和备份，再退出客户端并运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode ROLLBACK @ReleaseArgs -PlanPath $Plan -PlanSha256 $PlanHash
if ($LASTEXITCODE -ne 0) { throw 'ROLLBACK stopped; preserve all evidence and follow runbook 5C human recovery' }
```

marketplace 备份未完成、旧来源丢失、状态与计划不一致、旧来源备份字节改变、marketplace 有安装后的独立变更，均停止自动回退，按 runbook 5C 人工处理。不要修改状态文件让检查通过。重复 APPLY 同一计划拒绝；已 ROLLED_BACK 再回退拒绝。新的安装必须重新 PLAN。

## PowerShell 5.1 / .NET Framework 4.x 静态语义审计

按启动身份校验 → PLAN → DRILL → APPLY → VERIFY，及 ROLLBACK 的执行顺序逐行审计全部非 R2 编排。以下结论来自代码阅读、Python 静态回归和 Mac 上检查工具的实际输出；本机没有 PowerShell，不包含 PS 解析或运行测试。所有 R2 逐字片段及块 20/22 保持原字节。

| 缺陷位置（脚本行号） | 后果 | 最小修法与回归约束 |
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

专项测试验证 BOM/编码、静态 PS 5.1 禁用语法、六模式/新参数、bootstrap 自检、已校验工作树的本地 clone 与独立脚本 GitHub 备选、来源日志、README 本地提交核验/引用复制/标签绑定/UPDATE 顺序与环境恢复、确认门、默认 Python 路径、APPLY 时间与只列元数据的 VERIFY、原块/辅助函数固定 SHA256、精确清单、ZIP 排除。**没有 PowerShell 时不把这些检查描述为 PowerShell 解析或运行测试。** Windows 仍需 DRILL、真实 APPLY、客户端后的 VERIFY/取证以及故障/文件占用分支的现场验证。开发代码回退使用仓库外保存的原字节备份：恢复复核前的三个 `tools/oncall/` 文件并重新 build；本次不提交、不推送、不打标签，也不执行 Git 回退或删除操作。
