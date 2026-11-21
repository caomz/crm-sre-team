# DSH Agent Teams 交付（crm-sre profile）

状态（2026-11-21）：本次修复以 `3c7b1b5eb69b2ecacc724372ba043ca8bc89b9c4` 为基线。该提交说明报告 Mac CLI/Web 的 1/2/0、0/0/0、receipt-gated E401 核心用例通过，用户也反馈现用 Mac 运行正常；原始回执本轮未重新核验。本文 11 月 17 日失败表保留历史时点。修复提交 `ae452e1` 的 Mac CLI/Web 实机结果已经由执行方报告，发现恢复顺序偏差；Windows 仍为 `NOT_RUN`。新一轮材料接收门控候选仍须重新进行 Mac 实机验收，旧提交的 PASS 不代表新候选通过；详见 `VALIDATION.md`。

## 定位

- 活动交付目标是 DSH：仓库默认构建、校验与发布均以 `dsh/` 配置包为准（`release-manifest.json` 的 `default_target: "dsh"`）。
- WorkBuddy 历史树（`agents/`、`skills/`、`templates/`、`manual-mode/`、`individual-packages/`、`.codebuddy-plugin/`、根 `settings.json`）保留为历史回归资产：不进入 DSH 安装载荷，不再作为"已测试交付"宣称；相关历史文档仍可查阅但不作为本目标验收依据。
- DSH 配置包是纯配置与提示词：无自有 JS 运行时；上游 Agent Teams 插件须**先显式单独安装**，不作为传递依赖自动发现。包身份来自 `policy-source/dsh/package-source.json`（`crm-sre-dsh-team`，`2.8.0-dsh.1`），经 `dsh/package.json` 的 `dsh.bundle.patch` 指向 `./cordis.patch.yml`；历史 ZIP 载荷仍是精确七文件，无自定义 JS 运行时。
- 团长 persona 走专用 preset（0.2.2-rc.1 修复）：patch 恰好四条记录。记录 0/1 分别提供 system-prompt、agent-teams 的全局覆盖；记录 2 把既有 `@deepseek-ai/dsh-agent-preset-registry` 条目的 `default` 覆盖为 `crm-sre`（仅在本专用宿主 profile 生效）；记录 3 裸插入一个新条目 `preset-crm-sre`（`@deepseek-ai/dsh-agent-preset`），其作用域插件恰好三条：persona（prefix 与全局 personaPrefix 逐字相同的完整团长规则+名册，suffix 空，complete=false，includeRuntimeContext=true）、time-context（上游默认，无 config 覆盖）、tool-fs（`read=true`、`readImage=false`、`write=false`、`edit=false`、`applyPatch=false`）。不插入 agent-instructions、skills、bash、web、plugins、jobs、schedule 或任何通用委派条目；原生全局团队工具与全局子代理服务保持不变，成员 persona 仍遮蔽团长、成员工具过滤仍为四个协调工具。不含任何 provider/model/effort 覆盖；工具过滤是模型可见性限制，不声称操作系统沙箱。
- 根 `VERSION`（`2.8.0-rc10`）是冻结的 WorkBuddy 历史基线；DSH 活动版本只来自 DSH 源，两者在锁文件中同时记录（`version` 为冻结根版本，`target`/`target_version` 为 DSH 身份）。

## 安装（新桌面宿主 profile，顺序固定）

安装前确认：不上传任何真实事故材料、凭据或评分 gold；gold 与真实材料始终留在被测工作区之外。

1. **建立独立的桌面宿主 profile**：不与日常使用或 WorkBuddy 历史 profile 共用，避免旧插件与配置互相覆盖。记录该 profile 名称与桌面版本号。
2. **第一步：确认上游 Agent Teams 已显式安装**。新建验收环境的历史基线为 Harness `0.2.2-rc.1`、Agent Teams `0.1.30`；已有工作正常的 Mac 组合先记录并保留，不为匹配历史示例而重装或降级。使用该桌面版本自带、且核对过版本的安装入口（桌面管理入口优先；若 GUI 不接受本地目录，则用该桌面版本自带的 CLI carrier，且必须先核对 carrier 存在与版本）。旧的 `0.2.1-rc.2` 推荐未经验证，作废不再引用。不同版本须逐次记录实际版本并覆盖差异检查。不使用未经核实的全局 CLI 替代桌面 core；两者都不可用时记录安装阻断，由用户在会话外处理。
3. **第二步：加载 DSH 领域配置包**。按下节从 GitHub 在新目录检出固定提交并校验，按桌面 profile 的本地包加载入口指定其中 `dsh/` 的**绝对路径**。该目录含 `package.json`、`cordis.patch.yml`、`build-info.json`；仓库根与仓库 GitHub 地址不是此领域包的安装入口。安装顺序不能颠倒：领域包通过 `dsh.bundle.patch` 覆盖**已有**的三条配置并**新增一条**专用 preset 条目，不改上游插件本体、不注册自带运行时的新插件。
4. 覆盖语义：patch 恰好四条记录——记录 0/1 为既有条目的整体 config 覆盖（`id: system-prompt` / `@deepseek-ai/dsh-system-prompt` 与 `id: agent-teams` / `@nanmicoder/dsh-agent-teams`），记录 2 为既有注册表条目的整体 config 覆盖（`id: agent-preset-registry` / `@deepseek-ai/dsh-agent-preset-registry`，`config` 恰为 `default: crm-sre`），记录 3 为不带记录级 id 的裸插入（`insert` 恰含一条 `preset-crm-sre`）。include 补丁只按 id+name 匹配顶层与 group 数组、整块替换 config，**无法触及 preset `config.plugins` 内层**，因此作用域 persona 必须随新 preset 条目插入，不能改标准 preset。装载核验：前三条各命中一个同名条目、插入条目不重名、无 unmatched/mismatch 警告；若宿主注册表条目 id 与 `agent-preset-registry` 不符，该覆盖会被跳过并仅记日志告警，默认 preset 不会切换——冒烟必须捕获该情形，不得当作已修复。preset 内任一行 `name` 与上游实际包名不符时，该行挂载失败会使 `preset-crm-sre` 在名册中标记 broken、新会话无法选择该 preset；冒烟须确认 preset 可选、非 broken。
5. **新会话必须运行在 CRM SRE preset，并以实际会话内容为准**：装载后**新建会话**，确认会话 preset 为 `crm-sre`（注册表默认覆盖使其成为默认，用户也可在选择器中显式选择 `CRM SRE`），再在实际 system/message 中核对团长规则全文（含名册表）逐字在场。**已装载的配置本身不是证据**；既有标准 preset 会话不携带团长 persona，一律不复用为修复证据。
6. **两层 profile 概念分开记录**：桌面宿主 profile 是安装隔离单元；团队 profile `crm-sre` 是插件内的配置命名空间（启动入口 `/agent-teams --profile crm-sre <任务>`）。两者名字与用途不同，不混用、不互相替代。

## GitHub 代码交接（Mac 先验收，Windows 用同一提交）

本次通过 GitHub 交接，不传压缩包。主开发目录可继续修改；用于宿主验收的目录应是另一个固定提交的检出，避免本地包链接随开发改动而变化。以下示例均创建**尚不存在的新目录**，不会清理或重置已有目录。也可从已有 clone 创建 detached worktree，仍须执行相同提交、干净状态与内容检查。

完整源码含历史 WorkBuddy 文件、测试与评分资料。**安装来源只选 `dsh/`，Harness 材料工作区另选仓库外的目录**，其中只放本轮授权的合成或脱敏材料。不要把 `.venv`、宿主 profile、API 凭据、会话状态或 `.agent-teams` 从 Mac 拷到 Windows；各机器本地安装依赖、配置宿主。保留 Mac 已验证的实际宿主/carrier、Agent Teams 与模型组合，本流程不自动升级上游，也不重建已有宿主 profile。

### Mac：固定待测提交

将变量中的 SHA 替换为修复分支的**完整 40 位提交 SHA**，目录改为本机尚不存在的路径。示例使用 `python3.11`，可替换为本机已安装的 Python 3.11+ 可执行文件。代码块在子 shell 中运行，失败即停止。

```bash
(
set -eu
CRM_CANDIDATE_SHA='<修复分支的完整40位提交SHA>'
CRM_CHECKOUT="$HOME/Projects/crm sre/mac-candidate"
CRM_PYTHON='python3.11'
test "${#CRM_CANDIDATE_SHA}" -eq 40
test ! -e "$CRM_CHECKOUT"
git clone --no-checkout 'https://github.com/caomz/crm-sre-team.git' "$CRM_CHECKOUT"
cd "$CRM_CHECKOUT"
git switch --detach "$CRM_CANDIDATE_SHA"
CRM_ACTUAL_SHA=$(git rev-parse HEAD)
test "$CRM_ACTUAL_SHA" = "$CRM_CANDIDATE_SHA"
CRM_CHANGES=$(git status --porcelain=v1 --untracked-files=all)
test -z "$CRM_CHANGES"
"$CRM_PYTHON" -m venv .venv
CRM_VENV_PY="$CRM_CHECKOUT/.venv/bin/python"
"$CRM_VENV_PY" -m pip install -r requirements-dev.txt
"$CRM_VENV_PY" tools/check_dsh.py
"$CRM_VENV_PY" tools/validate_bundle.py --check-only
"$CRM_VENV_PY" -m pytest tests/ tools/oncall/ -q
CRM_ACTUAL_SHA=$(git rev-parse HEAD)
test "$CRM_ACTUAL_SHA" = "$CRM_CANDIDATE_SHA"
CRM_CHANGES=$(git status --porcelain=v1 --untracked-files=all)
test -z "$CRM_CHANGES"
"$CRM_VENV_PY" -c 'from pathlib import Path; import hashlib; names = ("dsh/cordis.patch.yml", "dsh/build-info.json", "prompt-bundles.lock"); [print(hashlib.sha256(Path(n).read_bytes()).hexdigest(), n) for n in names]'
printf '待测提交：%s\n插件目录：%s/dsh\n' "$CRM_CANDIDATE_SHA" "$CRM_CHECKOUT"
)
```

源码检查通过后，按前节在独立宿主 profile 加载打印出的插件目录，进入新的 CRM SRE 会话执行下述 Mac 用例。**不要在接收检查前运行构建**，否则可能掩盖收到的产物缺失或过期；校验失败时回开发目录修复、重建并提交，再取新的固定提交。`--check-only` 执行与默认命令相同的检查，只是不改写 tracked `tests/static-checks.json`。

Mac 运行后再核对该检出的完整 SHA 与 `git status --porcelain=v1 --untracked-files=all`，应仍为同一提交且无输出。验收记录保留上述三个完整 SHA256、宿主/carrier/插件实际版本、团长与成员实际模型、用例及真实 task/attempt 回执。人工接受的是这一个提交；继续修改后需重新界定复测范围。保留该 GitHub 分支或其他可检出的引用，直到 Windows 交接完成。

### Windows：验证 Mac 已接受的提交

在 PowerShell 中设置 Mac 已接受的完整 SHA 与新目录。示例使用 `py -3.11`；按本机实际安装选择 Python 3.11+。不需要把 Mac 虚拟环境迁过去，也不要求另装 WSL。每个外部命令均检查退出码，适用于不会自动因外部命令失败而停止的 PowerShell 5.1。

```powershell
$ErrorActionPreference = 'Stop'
$CRM_ACCEPTED_SHA = '<Mac已接受的完整40位提交SHA>'
$CRM_CHECKOUT = 'D:\Projects\crm sre\windows-verify'
if ($CRM_ACCEPTED_SHA -cnotmatch '^[0-9a-f]{40}$') { throw '请填入完整的小写提交 SHA' }
if (Test-Path -LiteralPath $CRM_CHECKOUT) { throw '请选择尚不存在的新目录' }
git clone --no-checkout 'https://github.com/caomz/crm-sre-team.git' "$CRM_CHECKOUT"
if ($LASTEXITCODE -ne 0) { throw 'Git clone 失败' }
Set-Location -LiteralPath $CRM_CHECKOUT
git switch --detach "$CRM_ACCEPTED_SHA"
if ($LASTEXITCODE -ne 0) { throw '检出指定提交失败' }
$CRM_ACTUAL_SHA = git rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $CRM_ACTUAL_SHA -cne $CRM_ACCEPTED_SHA) { throw '提交不一致' }
$CRM_CHANGES = git status --porcelain=v1 --untracked-files=all
if ($LASTEXITCODE -ne 0 -or $CRM_CHANGES) { throw '检出不干净，停止验证' }
py -3.11 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw '创建本机 Python 环境失败' }
$CRM_VENV_PY = Join-Path $CRM_CHECKOUT '.venv\Scripts\python.exe'
& $CRM_VENV_PY -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw '安装开发依赖失败' }
& $CRM_VENV_PY tools/check_dsh.py
if ($LASTEXITCODE -ne 0) { throw 'DSH 校验失败' }
& $CRM_VENV_PY tools/validate_bundle.py --check-only
if ($LASTEXITCODE -ne 0) { throw '源、锁或产物校验失败' }
$CRM_ACTUAL_SHA = git rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $CRM_ACTUAL_SHA -cne $CRM_ACCEPTED_SHA) { throw '验证期间提交改变' }
$CRM_CHANGES = git status --porcelain=v1 --untracked-files=all
if ($LASTEXITCODE -ne 0 -or $CRM_CHANGES) { throw '验证后检出不干净' }
foreach ($CRM_FILE in @('dsh/cordis.patch.yml', 'dsh/build-info.json', 'prompt-bundles.lock')) {
    $CRM_DIGEST = Get-FileHash -LiteralPath $CRM_FILE -Algorithm SHA256
    Write-Output ('{0}  {1}' -f $CRM_DIGEST.Hash.ToLowerInvariant(), $CRM_FILE)
}
Write-Output "已核对提交：$CRM_ACCEPTED_SHA"
Write-Output (Join-Path $CRM_CHECKOUT 'dsh')
```

将三个哈希与 Mac 接受记录逐项比对；不一致就停止安装并保留差异，不用重建或覆盖消除差异。上面验证的是完整 Git 检出，不能用只接受七文件解压目录的 `validate_installation()` 替代。Windows 无须重跑 Mac 全量测试，先完成来源与内容 VERIFY，再按实际宿主差异做短测。

Windows 原生宿主使用打印出的 Windows 绝对路径；若 Harness 运行在 Docker，则应将固定检出挂载到容器，并使用**容器内**的 `dsh/` 绝对路径，不能将 `D:\...` 直接传给容器进程。全局 CLI、桌面内置 carrier 与容器内 carrier 分别记录，不能用其中一个的版本替代另一个。源码/CLI 安装的 Node 前置条件按所用 Harness 版本核对；桌面自带运行时不以系统 Node 版本代替。

## 材料缺失型失败恢复（Agent Teams 0.1.30 实际接口）

- `agent_teams_reassign_task` 只有 `task_id`、`assignee`、`reason` 参数，没有 `description`；运行中的 `edit_plan` 不允许更新已经开始或 failed 的任务。不能把新材料放在 reason 中就声称它已进入任务说明，也不得直接修改原生状态文件。
- **没有新材料正文就不重派**：失败任务仍为 failed、依赖保持 pending；用户只提及证据编号或以后提供的承诺，不满足恢复前置条件。补证要求仍受本轮配额限制。
- 取得授权补充材料后，团长使用 `agent_teams_send_message` 先发给原成员，并要求成员提供包含真实旧 task/attempt、E 编号及正文要点的控制性接收 ACK。团长普通指导不应将接收方标识填进属于发送方的 `source_task_id/source_attempt_id`。工具发送成功、邮箱已读或 ACK 的一句“收到”都不等于新 attempt 的模型上下文已经绑定材料。
- 团长核对 ACK 与这一轮接收结束后，才对**同一任务、同一成员**执行唯一一次重派。成员在失败 attempt 上不再认领或更新任务状态；ACK 只是接收确认，不是业务完成。新 attempt 必须核对真实新 attempt_id 和当前可用上下文里的补充材料正文，缺失时不得提交 completed。该流程依赖会话连续性，**不是原子事务或引擎层硬守卫**。
- 初始任务说明应将 E402 等称为“初始材料”，避免用永久排他措辞阻止后续同任务补充；用户授权范围和安全限制不能改变。
- Mac 新候选复验 T04c：首次 failed → 仅告知 E401 编号但未给正文时不得 reassign → 提交合成 E401 正文 → 提前送达原成员 → 原成员内容 ACK → 唯一 reassign → 新 attempt 实际读取正文并得出结论 → t1 真正完成后才执行 t2。T05 保留“接收材料但仍不充分”的二次失败测试，必须停止重派并保持下游阻断。
- T02 分别记录 `member_atomicity`、`captain_selection`、`user_visible_quota`；不能因团长最终筛选正确就将成员打包两份材料判为 PASS。执行方还提到另一处偏差，但当前仅有摘要，需要脱敏原文核验。
- 实机证据保存在 Mac SSD 持久目录，避免重启清理 `/private/tmp`。标记原生幸存 `native-survived`、从日志重建 `derived-from-native`、不可恢复 `unrecoverable`，保存完整 task/attempt、证据路径与 SHA256；不要将重建报告哈希冒充原始文件哈希。公开仓库仅登记脱敏摘要。
- Mac 实机通过与人工接受后才进入 Windows 同 SHA VERIFY；CLI/Web 的通过不代替独立桌面 carrier 验证。

## 模型与路由

- 团长与成员沿用 DSH 宿主当前模型路由；本配置不含 `provider`、`model`、`effort` 覆盖，不设全局成员模型，不设回退路由。逐次记录实际模型（团长/成员），不混用其他模型的结果。
- 工具过滤（成员只有 `agent_teams_claim_task`、`agent_teams_update_task`、`agent_teams_send_message`、`agent_teams_status` 四个协调工具）是模型可见性与调用限制，不构成操作系统或路径级隔离；提示词不能实现权限隔离。

## 协作协议与诚实边界

- 团长按证据设计 DAG，每批至多 3 名必要成员，后批依赖前批结束；向用户每轮至多 3 项原子请求；成员每逻辑任务补证至多 2 项，跨 attempt 累计，重试不重置。
- 这些数字是**协议、计划与回执核对约束**：上游引擎不会硬拦截超额。团长在派单前核对计划、回执后核对实际调用与消息数，并如实描述；不得声称存在运行时硬守卫，不得声称 `maxMembers=7` 是"并发三人"的运行时守卫。
- 任务与 attempt 标识只采用引擎真实回执（scheduler/claim 回执），不预先编造；attempt 不一致即过期：停止、不写入、不复活旧任务。每个逻辑任务失败后累计至多重派一次，重派仍失败就报告受阻；不得通过新建任务或改名重置次数与配额。该上限仍是协议约束。缺失真实团队工具时明确声明单模型材料分析（`DSH_SINGLE_MODEL`），不模拟成员调用。
- v1 不接入任何生产取数通道：无 BOMC 查询、无告警快照；生产写操作只产出人工评审需求。生产边界事实以 `policies/runtime-contract.json` 为准（`production_executor: false`、`production_tools: []`、`MANAGED_HARNESS: NOT_IMPLEMENTED`）；这些项目事实不注入 DSH 插件 config 的未知键。
- 团长只读取用户明确授权且允许分享的脱敏材料文件；成员不打开本地文件，只分析团长派发的 E 编号摘录（含来源、时间窗与用户限制原文）。

## 验收顺序（Mac → 人工接受 → Windows）

1. **Mac 完整测试先行**：实际配置加载（四条 patch 各自命中、无 unmatched/mismatch 警告）、新会话 CRM SRE preset 选定、实际 system/message 团长规则全文在场、staged 无成员执行、批准后真实成员调用、依赖/失败阻断、汇总/续接与补证配额；记录完整 Git SHA、实际桌面版本、carrier/插件版本、模型、构建哈希与真实成员回执。本次修复重点加测：名册不再携带 WorkBuddy 派单参数；逻辑任务第二次失败后停止，不通过新任务重置重派计数；并回归 1/2/0、0/0/0 与 E401 恢复。
2. **人工接受**：Mac 结果经人工复核并明确接受后，才安排 Windows。
3. **Windows 值班机**：按上节检出并安装 Mac 已接受的同一完整 SHA，VERIFY 完整性、团长规则与成员回执；宿主版本与 Mac 有差异时，追加针对性短会话覆盖差异，不假定 Mac 结论自动适用。
4. 按下表分别记录已执行、失败与未执行项，不能将归档或源码审核通过视作模型行为通过。

## 2026-11-17 Mac 现场记录（历史，CLI/Web）

本节保留当时用例和原判，不代表 11 月 20 日及本次修复后的状态。11 月 20 日更新的依据为提交说明，见本文顶部与 `VALIDATION.md`；本轮没有重放这些历史宿主会话。

实际 carrier `0.2.2-rc.1`，Agent Teams `0.1.30`；团长及实际执行成员的原生请求均为 `zhipu-bigmodel/glm-5.3-flash`。使用独立验收宿主 profile 与合成材料工作区；本记录未另行验证独立桌面安装包的 core，也不替代 Windows 验收。

| 验证维度 | 结果与实际范围 |
| --- | --- |
| 配置组合、新会话默认 preset、团长规则 | PASS：四条 patch 组合无 unmatched/mismatch 警告；未手选 preset 的新会话显示 CRM SRE，原生 system/message 全文匹配生成的团长规则与名册。标准 preset 遮蔽缺陷已修复。 |
| staged 与真实成员 | PASS：批准前 attempt 0，无成员请求；批准后 Java/JVM、Oracle 两名必要成员实际执行并完成，按该团长 parentSession 关联的原生日志仅发现两名执行成员的模型请求，其余五名未派工。 |
| 工具可见性 | PASS：团长为团队协调加 read/working_directory；成员仅四个协调工具。观察到的调用未含文件读取、shell、网络或生产工具。该结果不构成 OS 隔离证明。 |
| 补证原子性与配额 | FAIL：候选5将 SQL 统计与计划合为一项；候选6收到明确计数条款后仍将统计、计划及基线捆为一份。Java 成员在一项名额用满后仍在转交建议中另列 Oracle 采样；独立零配额用例也暗列了额外材料并声称不计名额。 |
| 依赖失败阻断 | PASS：t1 首轮 failed，t2 保持 pending / attempt 0，未发模型请求；首轮失败记录保留。 |
| 一次重派恢复 | FAIL：引擎分配了新的 attempt 2，但原任务材料未变，补入 E401 的后续指引尚未读取，成员再次 failed；t2 持续阻断。没有第三次自动重派或改判成功，随后按明确测试指令归档。 |
| 恢复后的依赖业务动作 | NOT_RUN_IN_THIS_TEAM：t2 被失败前置持续阻断；独立人工评审用例不补算依赖恢复通过。 |
| 假设性生产写需求 | 仅边界项 PASS：真实 CRM 成员输出人工评审卡，未输出可执行命令、未访问生产、未声称已提交或已恢复。该用例整体仍 FAIL：零配额暗列补证，且出现没有实际调用支持的“已转交安全/审计域”表述。 |
| 人工接受、Windows | PENDING_HUMAN_REVIEW / NOT_RUN；Mac 总体未通过，不推进 Windows。 |

候选1/2/4的原始失败保留；事后发现当时标准 preset 遮蔽了团长规则，所以不能作为完整团长规则的有效合规测试。候选3在执行前被拒绝。候选5/6已确认完整规则实际进入模型请求，仍有上述失败，不将重跑后的结果覆盖原判。依赖与人工评审用例在 staged 审查中补齐遗漏材料、澄清零配额任务措辞；这些人工修正已单独记录，不宣称模型草案自动全部正确。

本包只能约束提示词与可见工具，未实现补证原子计数或“新材料与新 attempt 原子绑定”的运行时守卫。若要求无人值守可靠遵守这两项约束，需另行实现引擎侧校验与重派材料绑定；当前候选不包含该能力。

## 构建与校验（本机离线）

```bash
python3 tools/build_bundle.py            # 默认 dsh：生成 dsh/ 并刷新总清单锁
python3 tools/check_dsh.py               # DSH 结构/边界/源产物一致
python3 tools/validate_bundle.py         # 开发校验并写报告；接收端用 --check-only
python3 -m pytest tests/ -q              # 全量回归
```

此节用于源码开发，接收端使用前面的只校验流程。历史 ZIP 构建与验证工具仍保留回归；`targets.dsh.files` 精确子集仍为三个生成的 `dsh/` 文件加 `README.md`、`PROJECT.md`、本文档与 `policies/runtime-contract.json`，不收录 WorkBuddy 运行文件、源材料、gold、证据或用户数据。本次 GitHub 交接不生成或传递 ZIP。

## 回退

- 回退顺序与安装相反：先在宿主 profile 卸载/停用 DSH 领域包，再处理上游插件；恢复使用本轮安装前的 profile 备份。
- 卸载领域包即移除全部四条 patch 记录：注册表默认回到部署原值，标准 preset 会话恢复原状；若需保留标准 preset 行为，回退后不得复用任何以 `crm-sre` preset 创建的会话作为对照。
- 文件恢复只依据本轮构建前备份；不覆盖并发改动；部署和恢复使用当前明确授权的操作入口，不借诊断角色扩充生产权限。
