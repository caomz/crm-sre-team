# 值班机一键更新（Windows PowerShell 5.1）

只接收 Mac 已验证并打标签的版本。完整更新：**退出客户端 → 一条 clone 命令取得脚本 → 一条 UPDATE 命令并输入一次 YES → 打开客户端贴自检 1 → 运行打印出的 VERIFY 命令**。`UPDATE` 在同一进程内执行 `PLAN → 必要时 DRILL → 打印安装计划 → YES → APPLY`，自动传递计划路径和哈希。原有五个模式保留供排错、核验和回退。

**新增编排代码未在 Windows 实跑。** Mac 的 Python 静态检查不能证明 PS 5.1 运行正确，也不能证明 WorkBuddy 加载了团长 Agent 正文。首次使用须 DRILL；`UPDATE` 找不到本机交接目录内成功的 DRILL 报告时会自动演练，通过后才显示真实安装计划并等待 YES；`-Drill` 可强制本轮重做。此工具仅更新桌面插件；生产写操作仍只产出人工评审需求。

## 文件与发布边界

- `Update-CrmSreTeam.ps1` 使用 **UTF-8 BOM + LF**。保留 runbook 中文代码原文，避免 PS 5.1 按 ANSI/GBK 错读；新增编排的提示使用英文。下载后保持原字节，不用编辑器另存编码或换行。
- 现有 `tools/release_rules.py` 不接受 `.ps1`，构建/打包器只读取 `release-manifest.json.files`。本单新增 `repository_only_files` 精确登记这三个开发文件（脚本、本文、静态测试），由专项测试约束其排序、唯一性、存在性与不进入 ZIP。未更改打包规则；该字段是登记信息，**不会让插件安装或执行脚本**。
- 三个文件随 Git 同步，插件 ZIP 不含它们。插件的期望文件数一律读取 `files`，没有固定成 517。manifest 本身变化会导致 `prompt-bundles.lock` 重建。
- 脚本启动时若位于 Git 工作树内，先校验 `HEAD = ExpectedCommit`、工作树干净，以及该提交内脚本 blob 哈希与磁盘原字节哈希相同；任何不符立即停止。`PLAN` 仍比对目标标签内脚本 SHA256，后续模式绑定计划里的脚本哈希。`-ExpectedScriptSha256 <64-hex>` 是可选的额外交接核验，不要求手工传脚本或单独核对哈希。Mac 改完脚本后必须重新提交、验证并提供相应标签。

## 前置条件与固定路径

- Windows PowerShell **5.1**、Git for Windows、实际可运行的 Python **3.10+**；该 Python 已具备仓库离线检查所需依赖。工具不安装或升级任何依赖。
- 默认 `PythonExe` 是 runbook 在值班机核对过的 `C:\Users\AI\AppData\Local\Programs\Python\Python312\python.exe`。存在时直接使用；不存在就停止并要求显式传 `-PythonExe 'C:\<verified-python-dir>\python.exe'`。不回退到 `python3` 或 WindowsApps alias。
- 默认仓库为公开的 `https://github.com/caomz/crm-sre-team.git`，clone 不需凭据。仅 bootstrap 和 `PLAN` 的 `git clone` 联网；禁用 credential helper/交互提示和 hooks，忽略全局/系统 Git 配置，不读取凭据文件。网络失败就停止，不进入安装。
- bootstrap：`D:\crm-v36-handoff\bootstrap-<唯一编号>`，直接运行其 `tools\oncall\Update-CrmSreTeam.ps1`。每次更新用全新目录，保留旧目录供排错。
- 新 clone 工作区：`D:\Dev\crm-oncall-<GUID>\repo`。父工作区也全新，容纳仓库构建器在 `root.parent` 下的隔离暂存；任何同名已有路径均拒绝复用。
- 新计划/ZIP/暂存/日志/测试临时目录：`D:\crm-v36-handoff\update-<GUID>`。PLAN 的写入只发生在这两个新工作区，WorkBuddy 只读。进程级 `TEMP/TMP/TMPDIR/PYTHONUTF8/PYTHONDONTWRITEBYTECODE/GIT_CONFIG_*` 设置随调用的 PowerShell 进程退出而失效，不读取旧环境变量值；禁止 Python 在已有依赖目录写入 bytecode cache。
- REAL 路径沿用已验证的值班机账户：`C:\Users\AI\.workbuddy\plugins\marketplaces\my-experts`；来源是其 `plugins\crm-sre-team`，清单是其 `.codebuddy-plugin\marketplace.json`。cache 根为 `C:\Users\AI\.workbuddy\plugins\cache\my-experts\crm-sre-team`。账户/布局不同就停止并人工评审，不传参扩大边界。
- 备份：marketplace 根下的 `backups\crm-v36-<GUID>-oncall`，包括 `install-source`、`marketplace.json`、`install-state.json`；计划列出全部准确路径。
- 路径拒绝 junction/symlink/越界；递归复制前检查树内链接。工具没有删除操作，也不强杀进程，不修改系统执行策略。唯一执行策略选项在启动命令中：进程级 `-ExecutionPolicy Bypass`。

## Mac 发布时取得交接值

合并本单和 rc3 的内容后，在最终待发布提交的干净仓库操作。此处命令用于发布人的人工操作说明；本单不会创建标签或推送。期望 commit/ZIP SHA256 **不写入仓库**，否则包会再次变化。

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

脚本随上述标签从 GitHub clone 取得，不再单独导出或人工传文件。发布人可选择额外提供该提交中脚本的 SHA256，供值班机传 `-ExpectedScriptSha256`；它不是更新的必需输入。脚本不在插件 ZIP 内。

## 一次完整更新的命令序列

在普通 PS 5.1 窗口执行。替换 `<tag>`、`<40-hex>`、`<64-hex>` 为 Mac 本轮交接值；脚本对占位值会拒绝。先退出 WorkBuddy/CodeBuddy。以下 clone 是一条可复制的命令：生成唯一 bootstrap 目录，设置本窗口进程级 Git 选项，禁用凭据和 hooks，失败即停止；结束后 `$Script` 指向标签内脚本。

```powershell
. { $Bootstrap = 'D:\crm-v36-handoff\bootstrap-' + [guid]::NewGuid().ToString('N'); $env:GIT_CONFIG_NOSYSTEM = '1'; $env:GIT_CONFIG_GLOBAL = 'NUL'; $env:GIT_CONFIG_COUNT = '0'; $env:GIT_TERMINAL_PROMPT = '0'; $env:GCM_INTERACTIVE = 'Never'; $env:GIT_ASKPASS = ''; $env:SSH_ASKPASS = ''; if (Test-Path -LiteralPath $Bootstrap) { throw 'Bootstrap path already exists' }; git -c credential.helper= -c credential.interactive=never -c core.askPass= -c http.extraHeader= -c core.hooksPath=NUL clone --config core.autocrlf=false --config core.hooksPath=NUL --branch '<tag>' --single-branch https://github.com/caomz/crm-sre-team.git $Bootstrap; if ($LASTEXITCODE -ne 0) { throw 'Bootstrap clone failed' }; $Script = Join-Path $Bootstrap 'tools\oncall\Update-CrmSreTeam.ps1' }
```

然后一条更新命令，安装计划出现后只输入一次大写 `YES`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File $Script -Mode UPDATE -Tag '<tag>' -ExpectedCommit '<40-hex>' -ExpectedZipSha256 '<64-hex>' -RunPytest
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
| PLAN（默认） | 标签 clone；HEAD 与标签均等于 ExpectedCommit；前后工作树干净；重建不改变申报字节；离线检查；现有确定性打包；Mac SHA256 对比；5A 解压后严格集合和逐文件哈希 | `install-plan.json` 包含全部路径、版本、备份、marketplace 条目与原哈希、旧来源 VERSION/申报哈希、cache 版本目录名、全部包哈希、manifest/脚本哈希；`install-plan.sha256` 和终端打印同一计划哈希；各命令单独日志 |
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

专项测试验证 BOM/编码、静态 PS 5.1 禁用语法、六模式/新参数、bootstrap 自检、UPDATE 顺序与确认门、默认 Python 路径、APPLY 时间与只列元数据的 VERIFY、原块/辅助函数固定 SHA256、精确清单、ZIP 排除。**没有 PowerShell 时不把这些检查描述为 PowerShell 解析或运行测试。** Windows 仍需 DRILL、真实 APPLY、客户端后的 VERIFY/取证以及故障/文件占用分支的现场验证。开发代码回退须保留上一单文件：恢复复核前的三个 `tools/oncall/` 文件并重新 build；本次不提交、不推送、不打标签，也不执行 Git 回退或删除操作。
