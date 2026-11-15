# 外部只读技能编排优化计划（B-lite 完整方案与逐文件修改清单）

状态：已定方案，未实施 · 基线 `2.8.0-rc10`（标签 `crm-sre-team-2.8.0-rc10`，HEAD `181a27c`）· 目标版本 rc11 / 2.9.0 · 编写日期 2026-11-06

本文是完整修改计划（含架构决策与逐文件修改原文），不代表任何代码或提示词改动已经发生。每期实际执行的命令、结果和宿主验收记录写入 `VALIDATION.md`，不回写到本文冒充完成。

---

## 1. 背景与定稿决策

参照华为云 SRE 张希《大模型和 Multi Agent 在运维领域的实验探索》，用三个只读审计子代理对本仓库做了对标审计。审计在下列运行前提下进行：

1. 只用 WorkBuddy 运行；`MANAGED_HARNESS` 不在本计划范围内。
2. 可以连生产，但只做查询；生产写操作照旧只出 `action-review` 人工评审卡。
3. 具体取数技能通过 WorkBuddy 外部 `skills` 引入（`~/.workbuddy/skills/`），专家团内不写死某个取数技能的配置。

定稿决策（2026-11-06 用户确认）：

- `bomc-alarm-readonly` 守卫本身是一个 skill，**保留在插件内**。它提供哈希校验、参数白名单、进程组/Job 隔离以及 50 条 / 2 次上限，是目前唯一不靠提示词的约束。真正的取数技能本来就在外部 `~/.workbuddy/skills/`。
- 采用 **B-lite**：守卫不动；删掉团长提示词里和守卫 SKILL 重复的 BOMC 段落，腾出的空间写通用的“外部只读技能协议”。
- 分两期实施：第一期不碰团长字节、不改测试锁；第二期做团长去重，同时迁移锁定检查。

---

## 2. 现状事实（2026-11-06 只读核验）

| 事实 | 证据 | 影响 |
|---|---|---|
| 团长 SKILL 只剩 5 字节 | `skills/stability-director/SKILL.md` 48123 B，上限 48128（`tools/check_prompt_sizes.py`） | 不先去重，团长侧无法再加任何规则 |
| 团长 BOMC 段大多是重复内容 | `policy-source/prompts/roles/telecom-crm-sre-team-lead.md` 第 21–45 行约 10.3 KB，24 行中 17 行与 `policy-source/skills/bomc-alarm-readonly.md` 逐字相同；第 23 行已要求“使用守卫前加载 bomc-alarm-readonly” | 去重后规则不丢，可腾出约 7 KB |
| 守卫 SKILL 已有同一套锁 | `tools/check_workbuddy.py` 第 497–503 行对守卫的源文件和产物检查 `BOMC_LEAD_MARKERS`、`BOMC_REPORTING_RULES`、`BOMC_MEMBER_RULE` | 第二期只需撤掉团长侧的重复检查（第 358–361 行），守卫侧的检查保持不变 |
| 外部技能本来就能被发现 | `docs/15-bomc-readonly.md` 第 411 行：团长会话的技能清单不受 frontmatter `skills` 限制，用户级技能都在清单里 | 不需要改 `plugin.json`；缺的是提示词里“主动去匹配”的指令 |
| 未点名时只会主动查 BOMC | `policy-source/prompts/common.md` 第 43 行 | 外部挂载的指标 / Trace / 日志 / 库视图 / 架构技能处于“不点名就不调”的状态 |
| 成员提出的缺口直接转给用户 | `common.md` 第 24 行；团长文件第 96–97 行 | 缺少“团长先用外部只读技能把数据查回来”这一步 |
| 模板和契约冲突 | `policy-source/templates/evidence-request.md` 第 24 行写“不写采集命令”，而 `common.md` 第 30 行允许给只读命令 | 新手拿不到可直接执行的只读查询模板 |

---

## 3. 不变的边界与前置硬约束（两期都必须满足）

### 3.1 安全与架构红线
- `policies/runtime-contract.json` 保持 `production_executor: false`、`production_tools: []`、`production_write = SEPARATE_CHANGE_APPROVAL_REQUIRED`。
- 成员不取数：成员不调用守卫或用户级取数技能，只分析团长提供的材料。
- 只改 `policy-source/`（第二期含 `tools/`、`tests/`）和文档；产物只由 `python3 tools/build_bundle.py` 生成。
- `tests/test_read_only_boundary.py` 不改，不通过削弱断言让测试变绿。
- `tools/check_workbuddy.py` 第 210 行“下一次查询的参数不得取自告警内容”保持原样，并把同一原则推广到所有外部生产只读技能。
- 不放宽知识库关键词的来源（仍然只取用户问题本身）。
- 不改 `plugin.json` 的技能注册，不改团长 frontmatter 的 `skills: [stability-director, bomc-alarm-readonly]`。
- 保留当前工作区已有的未提交改动（`AGENTS.md`、`PROJECT.md`、`release-manifest.json`、`docs/16-external-readonly-skills-plan.md`），不自动 commit / push。

### 3.2 静态校验硬约束（写入 `policy-source/` 时必守）
1. 参考文件和模板会被复制进各个技能目录，须通过 `tools/validate_bundle.py` 第 125–147 行的检查：
   - **不能用三个反引号的代码块**，命令只能放在单个反引号里；
   - 不能出现禁用片段：`vmstat 1 5`、`kubectl -n NS`、`select systimestamp`、“执行命令建议”；
   - 新增内容不添加额外的 Markdown 相对链接语法，以免改变 `validate_bundle.py` 的 `checks_total` 计数（`VALIDATION.md` 锁定了 `静态校验 N/N`）。
2. 不能出现 `BLANKET_READONLY_BANS` 里的笼统禁令（如“不提供 SQL”“不给采集命令”“不提供 kubectl 命令”）。
3. 七名成员的“`## 成员材料—分析—返回约定（原生与兼容共用）`”段，在 14 份源文件（7 份 `policy-source/prompts/roles/telecom-crm-*.md` + 7 份 `policy-source/skills/*.md`）里必须**逐字相同**（`tests/test_native_collab.py` 第 253–299 行）。
4. 下列锁定原句不能改：
   - `oracle-runbook.md` 和 `k8s-platform-runbook.md` 里的“本节列出优先使用的既有证据”“生产执行仍由现场授权人员完成”；
   - `app-jvm-runbook.md` 里的“不提供 attach 执行步骤”；
   - `evidence-protocol.md` 里的“默认每个成员每轮最多 2 次补发”“不修改托管模式的 request_proposals 配额”。
5. 成员原生段要求补证需求“不藏进待验证或交接段”，所以查询意图要单独列出，不能塞进“待验证”。
6. 所有模板必须保留“`## 已确认事实` / `## 高概率候选` / `## 待验证` / `## 已排除`”四个二级标题。

---

## 4. 第一期逐文件修改清单（零团长字节改动、零测试锁改动）

第一期共修改 `policy-source/` 下的 **26 个文件**（9 个参考文档 + 14 个成员提示词 + 3 个模板）。团长文件（`telecom-crm-sre-team-lead.md` 与 `stability-director.md`）不动。

### 4.1 `policy-source/references/observability-runbook.md`

**① 在第 14 行（`## 口径` 段末：“`“无告警”“无数据”“0值”“未采集”严格区分；CPU正常不能排除队列等待或下游超时。`”）之后插入以下两段：**

> 采样粒度：跨 1m/5m/10m/1h 比较前先对齐粒度并注明；粗粒度均值会抹平短时峰值，不能用粗粒度平稳否定细粒度日志、Trace 或 1m 指标里的短时卡顿。曲线断点不插值；除采集链路漏采外，核对目标对象是否因夯死、磁盘满、OOM 或断网停报，断点本身可能是饱和的伴生现象。
>
> 数据异常不等于故障：单个采样点冲高后随即回落、无连续多周期异常且无错误率或积压伴随时，登记为瞬时毛刺，不升为根因候选。慢调用/慢查询比较故障窗与正常窗的单次耗时和频次增量；长期存在、幅度无明显变化且未耗尽共享池或锁的，作为常态背景噪音单列，不作为本次触发因素。

**② 在原第 18 行（`## 时间线` 段末：“`候选原因要解释起点、影响面、机制和恢复变化……但不能为实验主动制造故障。`”）之后插入以下两段：**

> 多条告警或日志：先按时间戳疏密分出集中爆发簇和零散噪点；簇内按（对象、告警类型或错误码）折叠为“首条时间～末条时间，共 N 条”并保留代表原文，再找簇内最早出现的异常（首爆点）与随后衍生的告警。快照条数达到查询上限且首末时间跨度很窄时，写明“风暴截断，首爆点可能不在本次快照内”，不把快照最早一条当成故障起点。
>
> 跨服务链路：按节点核算净耗时 real_duration = 节点总耗时 − 下游子调用耗时（串行求和，并行取重叠时窗）。总耗时高但净耗时正常、主要在等下游的节点记为传播节点，不列为本地根因；净耗时显著上升或最先报错的节点才作为根因候选，并转交对应技术域。缺子调用耗时时写未知，不估算。

### 4.2 `policy-source/references/linux-runbook.md`

**① 在第 18 行（`vmstat / iostat 等现有采样需核对首份累计口径与后续区间口径，具体字段以目标版本资料为准。[VMSTAT][IOSTAT]`）之后插入：**

> 有界只读骨架（占位符替换为已确认对象，只生成不执行）：`vmstat -t <间隔> <次数>`、`iostat -xz <间隔> <次数> '<DEV>'`、`df -h '<MOUNT>'` 与 `df -i '<MOUNT>'`；次数建议不超过 5，疑似 NFS 挂起的挂载点不执行 df。

**② 在第 20 行（`## 第二轮分支` 标题）之后插入：**

> 多指标同时异常：本地磁盘空间/inode 耗尽或存储 await、D 状态阻塞，优先于同期的网络超时表象排查——写日志或刷盘卡住会让应用来不及响应，表现为连接超时或心跳断连。磁盘/IO 与网络同时异常时，一并核对 CPU 细分（%iowait、%si 软中断、D 状态进程数、steal）和内存直接回收/swap 活动。优先级只决定先看什么，不替代时间先后与机制证据。

### 4.3 `policy-source/references/app-jvm-runbook.md`

**在第 14 行（`外围接口：沿同一匿名请求检查开始/超时/返回以及对端结果，区分慢调用和本地排队；不要盲目提高timeout或重试次数。`）之后插入：**

> 跨跳耗时：本节点耗时须扣除下游 HTTP/RPC/JDBC 等待，核算净耗时 real_duration；线程主要停在下游响应等待且净耗时正常时，本节点是传播节点，写成向下游域的转交建议，不作本地运行时根因。比较故障前后同一慢调用的增量，长期存在且无增量的慢调用单列为背景噪音。

### 4.4 `policy-source/references/oracle-runbook.md`

**在第 27 行（`SQL：优先针对已知SQL_ID取既有执行摘要和计划……数据不足说明无法计算。`）之后插入以下两段：**

> 毛刺与常态慢 SQL：数据库 CPU 或等待单点冲高后回落、无阻塞链和事务堆积时按瞬时毛刺登记；慢 SQL 核对故障窗相对正常基线的单次耗时与执行次数增量，长期存在且未引发本次锁或池耗尽的慢 SQL 单列为背景噪音，不当本次根因。
>
> 会话与阻塞只读骨架（只生成不执行，占位符替换为已确认值）：`SELECT inst_id, sid, serial#, status, event, seconds_in_wait, blocking_instance, blocking_session, sql_id FROM gv$session WHERE username = '<SCHEMA>' AND (status = 'ACTIVE' OR blocking_session IS NOT NULL) FETCH FIRST 50 ROWS ONLY`；FETCH FIRST 需 12c 及以上，低版本改用 ROWNUM 并由 DBA 确认；不查绑定变量明文，许可未确认时不访问 AWR/ASH 视图。

### 4.5 `policy-source/references/k8s-platform-runbook.md`

**在第 15 行（`优先已有摘要，不全命名空间或全群导出……没有对应历史材料时承认无法验证。[KLOG]`）之后插入（保持第 12、14 行的锁定原句不变）：**

> 日志只读骨架（只生成不执行）：`kubectl logs -n '<NS>' '<POD>' -c '<CONTAINER>' --since-time='<ISO8601>' --tail=200 --limit-bytes=262144`，排查重启前退出原因时加 `--previous`；不加 -f 跟随，不 exec、不 debug，不导出 Secret。

### 4.6 `policy-source/references/telecom-crm-knowledge.md`

**在第 14 行（`第二轮只沿已发现的分支追踪：入口请求→受理校验→落库/提交→外围下发→回执→最终业务状态。不能假定用户已经部署链路追踪平台。`）之后插入：**

> 多跳链路（网关→受理→订单→计费/外围）结合各环节净耗时 real_duration 与首个状态分叉点，区分上游超时传播节点和下游卡顿节点；纯等待下游响应的环节不判为业务逻辑卡顿点。

### 4.7 `policy-source/references/team-topology.md`

**在第 22 行（`角色隔离基于论断类型与证据……机制结论转为 handoff_proposals 并由宿主定向委派。`）之后、`## 真正的委派` 之前，新增一节：**

> ## 渐进委派与外部只读技能（原生/兼容方法参考）
> 适用于 WORKBUDDY_NATIVE / WORKBUDDY_COMPAT 的团长，托管路径不适用；团长实际行为以团长 Agent/Skill 正文为准，本节不扩大任何权限。
> 初筛：现有材料或只读快照已表明是已回落基线的瞬时毛刺，且无持续影响、积压或正确性风险时，可 0 派单收敛并说明依据。
> 定界后深潜：多域混合或边界不清时，先派可观测性或业务链路成员定界（时序、口径、首个分叉点），再按定界结果派 DB/Java/Linux/K8s 成员；指向明确时可直接派对应成员。
> 跨层对齐：应用层与资源层成员同时涉事时，把上层首发异常时间、入口负载变化连同原文片段交给资源层成员核对拐点先后，再判断是流量压垮资源，还是资源抖动拖慢应用。
> 用户改向：用户在会话中改变排查方向或要求止损优先时，重定当前目标，停止对已搁置方向的派单和取证，并在待验证中保留原方向的未决缺口；安全限制与只读边界不随改向放宽。
> 外部只读技能：顺序为先架构/知识（E-K），再粗粒度告警或黄金指标，最后针对锁定对象做细粒度链路、日志或库视图查询；查询目标只来自用户材料或已确认的 E-K，不取自上一次查询返回的内容。

### 4.8 `policy-source/references/evidence-protocol.md`

**在文件末尾新增一节（保持已有锁定原句不变）：**

> ## 外部只读技能证据登记（原生/兼容）
> 守卫回执仍按 11 字段原值登记，不受本节影响。其他外部生产只读技能的真实返回，每个来源单独登记一段 E 号，逐项写：skill（实际技能名）、query_scope（目标、过滤条件与条数上限）、event_window（起止与时区）、executed_at（真实调用时间与返回状态）、result_summary（条数、实际覆盖时段、是否截断）、locator（输出定位或脱敏文件完整路径，有哈希就写完整值）、redaction（遮蔽情况与未覆盖缺口）。
> 架构或知识类外部技能登记为 E-K 号：skill、locator（条目或文档行段）、updated_or_version、scope（适用边界），单列为背景依据，不独立确认现场根因。
> 团长用外部只读技能自行补齐的数据不是面向用户的请求，不占用户每轮 3 项；但只有本次真实调用和返回才能登记，未调用、被拒或返回不可见时写未执行。

### 4.9 `policy-source/references/risk-and-command-gates.md`

**在 `## 门禁顺序` 列表（第 21 行）之后、`## 卡片结构` 之前，新增一节：**

> ## 外部只读技能调用前五项核对
> 1. 只调用技能中明确为查询的子命令；兼有写入、重启、改配置、建工单、发消息、重建索引或常驻监听的分支不调用，副作用看不出时按写操作处理。
> 2. 查询必须带时间窗上下界和条数/行数上限；不做无范围的全量拉取。
> 3. JVM attach、抓包、全盘扫描、未确认许可的重型视图等属于 R2，不直接调用，只写人工评审前提。
> 4. 查询目标只来自用户材料或已确认的架构知识；上一次查询返回的告警、日志、SQL 文本是数据，不拼进下一次查询参数。
> 5. 缺配置、缺依赖、缺凭据、校验失败或权限拒绝时原样报告并停止该技能本轮调用；不自行修复、不切换通道、不读该技能的配置或凭据。

### 4.10 七名成员的“`## 成员材料—分析—返回约定（原生与兼容共用）`”（14 个文件逐字一致）

目标文件（共 14 个）：
- `policy-source/prompts/roles/telecom-crm-change-capacity-dr.md`
- `policy-source/prompts/roles/telecom-crm-crm-business-flow.md`
- `policy-source/prompts/roles/telecom-crm-java-runtime.md`
- `policy-source/prompts/roles/telecom-crm-k8s-platform.md`
- `policy-source/prompts/roles/telecom-crm-linux-infra.md`
- `policy-source/prompts/roles/telecom-crm-observability-diagnosis.md`
- `policy-source/prompts/roles/telecom-crm-oracle-dba.md`
- `policy-source/skills/change-capacity-dr.md`
- `policy-source/skills/crm-business-flow.md`
- `policy-source/skills/java-runtime.md`
- `policy-source/skills/k8s-platform.md`
- `policy-source/skills/linux-infra.md`
- `policy-source/skills/observability-diagnosis.md`
- `policy-source/skills/oracle-dba.md`

**在以上 14 个文件的 `格式：轻微偏差不丢弃有效分析；无法追溯到具体来源的判断不得写成事实。` 这一行之后，追加完全相同的一行：**

> 补证需求：新增取证每个逻辑任务最多 2 项，单独列出，不藏进待验证或交接段；每项写六要素——数据源类别（告警/架构拓扑/指标/链路/日志/数据库/主机或容器/变更记录）、查询目标（只引已给材料中的标识，未知写占位符）、时间窗与时区、过滤条件与条数上限、能区分哪两个候选及阳性/阴性各怎样改变判断、无对应只读技能时供人工执行的 R1 只读命令或 SQL（带占位符与上限；R2 只写评审前提，R3 不给命令）。成员只描述需求，不取数。

### 4.11 五名成员的“`本域检查：`”行（10 个文件，角色文件与技能文件成对一致）

在对应成员的角色文件（`policy-source/prompts/roles/telecom-crm-<role>.md`）与技能文件（`policy-source/skills/<role>.md`）的 `本域检查：` 行末尾追加：

1. **`observability-diagnosis`**（原句：`本域检查：同一事件转发不是独立证据；缺失、零值、未采集分开；时间重合仅支持相关性。`）末尾追加：
   > 粗粒度平稳不否定细粒度峰值；瞬时毛刺、常态慢调用与持续故障分开；多条告警先分簇并折叠同源刷屏；链路按净耗时区分传播节点与根因节点。
2. **`linux-infra`**（原句：`本域检查：当前快照不能反推历史，单资源正常不排除其他瓶颈；只读采集命令按共用只读边界生成，修复动作只给人工评审卡。`）末尾追加：
   > 单点冲高回落与持续异常分开；磁盘/存储 IO 阻塞优先于同期网络超时表象，二者同时异常时核对 CPU 细分与内存回收。
3. **`java-runtime`**（原句：`本域检查：池满只是现象，不默认扩池、加堆、重启或诊断 attach；现场新采集必须有开销、停止条件和替代材料。`）末尾追加：
   > 按扣除下游等待后的净耗时区分传播节点与本地运行时根因，无增量的常态慢调用单列。
4. **`oracle-dba`**（原句：`本域检查：应用池和数据库会话分别建模；许可未知不索取受限诊断能力，接受已有合规摘要或替代材料；只读查询 SQL 按共用只读边界生成，不输出 DDL/DML 或变更语句。`）末尾追加：
   > 瞬时毛刺与持续等待分开，慢 SQL 看相对基线的增量。
5. **`crm-business-flow`**（原句：`本域检查：超时不等于失败或未提交；补单、重推、改状态、批次重跑仅提出 R3 人工评审需求。`）末尾追加：
   > 结合各跳净耗时区分上游超时传播节点与首个状态分叉点。

### 4.12 三个输出模板（`policy-source/templates/`）

1. **`policy-source/templates/evidence-request.md` 第 24 行**：
   将原第 24 行：
   `只说明所需证据与评审条件，不写采集命令。成员≤2、用户每轮≤3，全部原子计数，无“材料包”例外。`
   替换为：
   > 采集表达：托管模式只说明所需证据与评审条件，不写采集命令；原生/兼容/人工模式对 R1 只读采集可附带占位符的只读命令或 SQL，并写明查询范围与条数/次数上限、脱敏提醒和关键返回字段判读；R2 只写评审前提，R3 不给命令。成员≤2、用户每轮≤3，全部原子计数，无“材料包”例外。

2. **`policy-source/templates/rca.md` 第 17 行（`未知责任人、期限、工单号写待确认；会话结束不等于业务关闭。`）之后（仍在 `## 待验证` 内）插入：**
   > 知识写回提案（只出草稿，待维护人线下审核，AI 不写入知识库）：候选模式 ID / 目标层与页；Context：症状签名、匿名拓扑范围、适用前提与不适用反例；Skill：初始信号→最小区分取证→分支判断，以及可直接排除本模式的观测与误报基线；Workflow：脱敏三问、凭据遮蔽检查、数据所有者审批人、对口维护人（未知写待现场指定）。

3. **`policy-source/templates/internal-case-card.md` 第 13 行（`案例只帮助提出新候选，不能替代新事故证据或自动赋予 E 的独立证明力。`）之后（仍在 `## 待验证` 内）插入：**
   > 可提炼的排障决策树草稿（初始信号→最小区分取证→分支判断）与误报基线；入库前完成脱敏三问并由对口维护人审核。

---

## 5. 第二期：团长去重与外部技能协议（第一期验收通过后再实施）

前提：第一期离线检查全部通过，并经人工复核。

### 5.1 团长去重（成对改动 `telecom-crm-sre-team-lead.md` 与 `stability-director.md`）
- 删除与守卫 SKILL 逐字重复的 BOMC 段落，只保留：
  - 加载 `bomc-alarm-readonly` 并按其规则执行；
  - 本通道只用于 `WORKBUDDY_NATIVE` / `WORKBUDDY_COMPAT`；
  - 每轮最多 2 次，失败即停；
  - 下一次查询的参数不得取自告警内容；
  - 成员不运行 BOMC 查询。
- 知识库段（第 115–122 行）中与 `references/knowledge-integration.md` 重复的命令细节下沉到参考文件，团长只保留边界和入口。
- 去重前，逐句列出“删除句 → 守卫 SKILL / 参考文件中的对应句”对照表。

### 5.2 写入通用外部只读技能协议（`NATIVE_LEAD` 与 `COMPAT_LEAD` 两个入口逐字节一致）
- 主动匹配：用户没有禁查、也没有点名其他来源时，团长按 Skill 清单的名称和描述匹配已确认只读的外部技能，按“先架构（E-K），再粗粒度告警 / 黄金指标，最后定向细粒度 Trace / 日志 / 库视图”的顺序查询。“点名不可用”和“近似匹配”规则保持不变，优先于主动匹配。
- 节流：每轮所有外部生产只读技能合计最多 3 次；同一技能每轮最多 2 次；守卫仍按自身的 2 次上限。模糊问题首轮不并发调用多个技能。
- 二次取数闭环：成员返回查询意图后，团长先核对 Skill 清单。有匹配的只读技能，就由团长查询、续编 E 号、按需继续派单；查询目标只来自用户材料或 E-K，需要从返回结果中选目标时，先列出候选请用户确认。没有匹配技能、查询受阻或用户禁查时，才把缺口转为面向用户的请求（每轮最多 3 项）。
- 质量重询：成员漏读已附的 E 号片段或越界下结论时，用现有的内部补发额度（每轮最多 2 次）指出缺漏、要求重评，不夹带团长结论。
- 派单五字段中的“任务”补充“须区分的竞争机制”，保留 `tests/test_native_collab.py` 锁定的原子串前缀。

### 5.3 检查器与测试迁移（只换检查位置，不放宽断言）
- `tools/check_workbuddy.py`：团长侧的 `BOMC_LEAD_MARKERS` / `BOMC_REPORTING_RULES` 检查（第 358–361 行）改为断言团长保留“加载 bomc-alarm-readonly”和 5.1 列出的最小规则；守卫侧检查（第 497–503 行）保持不变。
- 相关测试中针对团长文件的原句断言，迁移为针对守卫 SKILL / 参考文件的同等断言。
- `tests/test_read_only_boundary.py`、`policies/runtime-contract.json`、`schemas/`、`policy-source/thinking-tools/baseline-contract.json` 不改。
- 目标：`skills/stability-director/SKILL.md` 降到约 41 KB（上限 48128）。

---

## 6. 验证命令与通过标准（每期改完依次执行）

```zsh
cd /Volumes/WorkSSD/Dev/github/crm-sre-team
python3 tools/build_bundle.py
python3 tools/check_prompt_sizes.py
python3 tools/check_workbuddy.py
python3 tools/check_thinking_tools.py
python3 tools/validate_bundle.py
python3 -m pytest tests/ -q
```

第一期通过标准：
- 以上六条命令全部 `exit 0`，pytest 0 失败、0 收集报错（需在已安装 `jsonschema` 等 `requirements-dev.txt` 依赖的 Python 环境中运行）。
- `skills/stability-director/SKILL.md` 字节数保持 `48123` 不变。
- `git diff --stat tools/ tests/` 为空。

---

## 7. 宿主验收与回滚

### 7.1 宿主验收（按 `AGENTS.md` 流程）
- 先在 Mac 运行；Mac 跑完、结果经人工复核验收后，再安排 Windows 值班机做安装 / 切换 + VERIFY。
- 固定 `glm-5.3-flash`，逐次记录 WorkBuddy 版本、插件版本以及团长 / 成员的实际模型。
- 第二期至少回归：INSTALL-VERIFY、BRC-1、BRC-2、BRC-8b、BRC-9c、BRC-10、QO-4、QO-5、RESTORE-VERIFY，以及合成用例 EXT-1～EXT-4。

### 7.2 回滚命令（保护工作区已有未提交改动）

```zsh
cd /Volumes/WorkSSD/Dev/github/crm-sre-team
git checkout -- policy-source/
python3 tools/build_bundle.py
```
