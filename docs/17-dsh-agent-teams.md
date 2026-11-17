# DSH Agent Teams 交付（crm-sre profile）

状态：离线检查与 Mac CLI/Web 真实 GLM 团队测试已运行；完整团长规则和工具加载通过，配额与一次恢复仍失败。本包为待人工审查的候选，不能称 Mac 整体验收通过，Windows 未运行。

## 定位

- 活动交付目标是 DSH：仓库默认构建、校验与发布均以 `dsh/` 配置包为准（`release-manifest.json` 的 `default_target: "dsh"`）。
- WorkBuddy 历史树（`agents/`、`skills/`、`templates/`、`manual-mode/`、`individual-packages/`、`.codebuddy-plugin/`、根 `settings.json`）保留为历史回归资产：不进入 DSH 安装载荷，不再作为"已测试交付"宣称；相关历史文档仍可查阅但不作为本目标验收依据。
- DSH 配置包是纯配置与提示词：无自有 JS 运行时；上游 Agent Teams 插件须**先显式单独安装**，不作为传递依赖自动发现。包身份来自 `policy-source/dsh/package-source.json`（`crm-sre-dsh-team`，`2.8.0-dsh.1`），经 `dsh/package.json` 的 `dsh.bundle.patch` 指向 `./cordis.patch.yml`；安装载荷仍是精确七文件，无自定义 JS 运行时。
- 团长 persona 走专用 preset（0.2.2-rc.1 修复）：patch 恰好四条记录。记录 0/1 保留原有两个全局覆盖（system-prompt、agent-teams，内容不变）；记录 2 把既有 `@deepseek-ai/dsh-agent-preset-registry` 条目的 `default` 覆盖为 `crm-sre`（仅在本专用宿主 profile 生效）；记录 3 裸插入一个新条目 `preset-crm-sre`（`@deepseek-ai/dsh-agent-preset`），其作用域插件恰好三条：persona（prefix 与全局 personaPrefix 逐字相同的完整团长规则+名册，suffix 空，complete=false，includeRuntimeContext=true）、time-context（上游默认，无 config 覆盖）、tool-fs（`read=true`、`readImage=false`、`write=false`、`edit=false`、`applyPatch=false`）。不插入 agent-instructions、skills、bash、web、plugins、jobs、schedule 或任何通用委派条目；原生全局团队工具与全局子代理服务保持不变，成员 persona 仍遮蔽团长、成员工具过滤仍为四个协调工具。不含任何 provider/model/effort 覆盖；工具过滤是模型可见性限制，不声称操作系统沙箱。
- 根 `VERSION`（`2.8.0-rc10`）是冻结的 WorkBuddy 历史基线；DSH 活动版本只来自 DSH 源，两者在锁文件中同时记录（`version` 为冻结根版本，`target`/`target_version` 为 DSH 身份）。

## 安装（新桌面宿主 profile，顺序固定）

安装前确认：不上传任何真实事故材料、凭据或评分 gold；gold 与真实材料始终留在被测工作区之外。

1. **建立独立的桌面宿主 profile**：不与日常使用或 WorkBuddy 历史 profile 共用，避免旧插件与配置互相覆盖。记录该 profile 名称与桌面版本号。
2. **第一步：显式安装上游 Agent Teams 插件 0.1.30**。使用该桌面版本自带、且核对过版本的安装入口（桌面管理入口优先；若 GUI 不接受本地目录，则用该桌面版本自带的 CLI carrier，且必须先核对 carrier 存在与版本）。验证基线锁定 Harness `0.2.2-rc.1`、Agent Teams `0.1.30`；旧的 `0.2.1-rc.2` 推荐未经验证，作废不再引用。不同版本须逐次记录实际版本并覆盖差异检查。不使用未经核实的全局 CLI 替代桌面 core；两者都不可用时记录安装阻断，由用户在会话外处理。
3. **第二步：加载 DSH 领域配置包**。将本仓库构建产物 `dsh/`（`package.json`、`cordis.patch.yml`、`build-info.json`）放入一个**绝对路径**的新目录，按桌面 profile 的本地包加载入口指定该绝对路径。安装顺序不能颠倒：领域包通过 `dsh.bundle.patch` 覆盖**已有**的三条配置并**新增一条**专用 preset 条目，不改上游插件本体、不注册自带运行时的新插件。
4. 覆盖语义：patch 恰好四条记录——记录 0/1 为既有条目的整体 config 覆盖（`id: system-prompt` / `@deepseek-ai/dsh-system-prompt` 与 `id: agent-teams` / `@nanmicoder/dsh-agent-teams`，保持原有键与内容），记录 2 为既有注册表条目的整体 config 覆盖（`id: agent-preset-registry` / `@deepseek-ai/dsh-agent-preset-registry`，`config` 恰为 `default: crm-sre`），记录 3 为不带记录级 id 的裸插入（`insert` 恰含一条 `preset-crm-sre`）。include 补丁只按 id+name 匹配顶层与 group 数组、整块替换 config，**无法触及 preset `config.plugins` 内层**，因此作用域 persona 必须随新 preset 条目插入，不能改标准 preset。装载核验：前三条各命中一个同名条目、插入条目不重名、无 unmatched/mismatch 警告；若宿主注册表条目 id 与 `agent-preset-registry` 不符，该覆盖会被跳过并仅记日志告警，默认 preset 不会切换——冒烟必须捕获该情形，不得当作已修复。preset 内任一行 `name` 与上游实际包名不符时，该行挂载失败会使 `preset-crm-sre` 在名册中标记 broken、新会话无法选择该 preset；冒烟须确认 preset 可选、非 broken。
5. **新会话必须运行在 CRM SRE preset，并以实际会话内容为准**：装载后**新建会话**，确认会话 preset 为 `crm-sre`（注册表默认覆盖使其成为默认，用户也可在选择器中显式选择 `CRM SRE`），再在实际 system/message 中核对团长规则全文（含名册表）逐字在场。**已装载的配置本身不是证据**；既有标准 preset 会话不携带团长 persona，一律不复用为修复证据。
6. **两层 profile 概念分开记录**：桌面宿主 profile 是安装隔离单元；团队 profile `crm-sre` 是插件内的配置命名空间（启动入口 `/agent-teams --profile crm-sre <任务>`）。两者名字与用途不同，不混用、不互相替代。

## 模型与路由

- 团长与成员沿用 DSH 宿主当前模型路由；本配置不含 `provider`、`model`、`effort` 覆盖，不设全局成员模型，不设回退路由。逐次记录实际模型（团长/成员），不混用其他模型的结果。
- 工具过滤（成员只有 `agent_teams_claim_task`、`agent_teams_update_task`、`agent_teams_send_message`、`agent_teams_status` 四个协调工具）是模型可见性与调用限制，不构成操作系统或路径级隔离；提示词不能实现权限隔离。

## 协作协议与诚实边界

- 团长按证据设计 DAG，每批至多 3 名必要成员，后批依赖前批结束；向用户每轮至多 3 项原子请求；成员每逻辑任务补证至多 2 项，跨 attempt 累计，重试不重置。
- 这些数字是**协议、计划与回执核对约束**：上游引擎不会硬拦截超额。团长在派单前核对计划、回执后核对实际调用与消息数，并如实描述；不得声称存在运行时硬守卫，不得声称 `maxMembers=7` 是"并发三人"的运行时守卫。
- 任务与 attempt 标识只采用引擎真实回执（scheduler/claim 回执），不预先编造；attempt 不一致即过期：停止、不写入、不复活旧任务。缺失真实团队工具时明确声明单模型材料分析（`DSH_SINGLE_MODEL`），不模拟成员调用。
- v1 不接入任何生产取数通道：无 BOMC 查询、无告警快照；生产写操作只产出人工评审需求。生产边界事实以 `policies/runtime-contract.json` 为准（`production_executor: false`、`production_tools: []`、`MANAGED_HARNESS: NOT_IMPLEMENTED`）；这些项目事实不注入 DSH 插件 config 的未知键。
- 团长只读取用户明确授权且允许分享的脱敏材料文件；成员不打开本地文件，只分析团长派发的 E 编号摘录（含来源、时间窗与用户限制原文）。

## 验收顺序（Mac → 人工接受 → Windows）

1. **Mac 完整测试先行**：实际配置加载（四条 patch 各自命中、无 unmatched/mismatch 警告）、新会话 CRM SRE preset 选定、实际 system/message 团长规则全文在场、staged 无成员执行、批准后真实成员调用、依赖/失败阻断、汇总/续接与补证配额；记录实际桌面版本、carrier/插件版本、模型、构建哈希与真实成员回执。
2. **人工接受**：Mac 结果经人工复核并明确接受后，才安排 Windows。
3. **Windows 值班机**：安装同一份已接受的产物，VERIFY 完整性、团长规则与成员回执；宿主版本与 Mac 有差异时，追加针对性短会话覆盖差异，不假定 Mac 结论自动适用。
4. 按下表分别记录已执行、失败与未执行项，不能将归档或源码审核通过视作模型行为通过。

## 2026-11-17 Mac 现场记录（CLI/Web）

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
python3 tools/validate_bundle.py         # DSH 默认校验（--target workbuddy 为历史回归）
python3 -m pytest tests/ -q              # 全量回归
python3 tools/build_release.py --output dist/crm-sre-dsh.zip
python3 tools/validate_release.py --zip dist/crm-sre-dsh.zip
```

DSH 发布 ZIP 只收录 `targets.dsh.files` 精确子集：三个生成的 `dsh/` 文件加 `README.md`、`PROJECT.md`、本文档与 `policies/runtime-contract.json`。不收录 WorkBuddy 运行文件、源材料、gold、证据或用户数据。

## 回退

- 回退顺序与安装相反：先在宿主 profile 卸载/停用 DSH 领域包，再处理上游插件；恢复使用本轮安装前的 profile 备份。
- 卸载领域包即移除全部四条 patch 记录：注册表默认回到部署原值，标准 preset 会话恢复原状；若需保留标准 preset 行为，回退后不得复用任何以 `crm-sre` preset 创建的会话作为对照。
- 文件恢复只依据本轮构建前备份；不覆盖并发改动；部署和恢复使用当前明确授权的操作入口，不借诊断角色扩充生产权限。
