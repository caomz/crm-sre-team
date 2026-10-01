> 适用范围：本文件保留旧版托管设计/历史说明；当前 WorkBuddy 接入与模式规则以根 README、MIGRATION 和 docs/11-workbuddy-host-acceptance.md 为准。

# OODA 判断与序数化证据更新 · 2.4.0
## 已确认事实
本版把候选引用、证据效应、方向提议及材料请求落实为共享 Schema 与策略声明。policies/reasoning.json 的 status 为 CONTRACT_ONLY_NOT_RUNTIME_ENFORCED；runtime-contract 的 implementation_status 仍为 NOT_IMPLEMENTED。OODA 不表示已经实现运行时。

| 任务内顺序 | 判断内容 | 模型产物与边界 |
|---|---|---|
| Observe | 证据增量 | 读取宿主 evidence_delta，描述变化前、变化、变化后；不重放全部事故 |
| Orient | 更新候选 | 候选引用、evidence_effects、posterior_direction；状态、先验只由宿主写 |
| Decide | 选最有信息增益的验证 | target_candidate_refs、if_positive、if_negative、information_gain；无区分度不提请求 |
| Act | 只提议 | 请求、路由、评审卡需求、交接提议；不执行，不产生生产命令 |

### OODA 与 P0–P7
OODA 是同一任务内的判断顺序，不是新增阶段、阶段别名或推进信号。phase 仅由现有宿主状态机与守卫推进；ooda_cycle_id 仅由宿主计数。用户说“继续”不推进 phase、不重置额度，不证明新增证据。可信上下文字段存在但为空不等于缺失；缺失须按现有 blocked 协议处理。

### candidate 与 evidence_effect 字段
下表定义与 schemas/common.schema.json 的共享 $defs 对应；member/lead/feedback 主体与 $id 不改。
| 对象/字段 | 结构与限制 | 责任 |
|---|---|---|
| candidate.candidate_ref | 必填 string，^[HL][0-9]{2,}$ | H 为本任务 current_candidates 既有编号；L 为本次输出局部编号，宿主接纳后映射 |
| candidate.posterior_direction | 必填 UP / DOWN / UNCHANGED / INDETERMINATE | 只是本轮变化方向提议；L 编号只可 INDETERMINATE |
| candidate.evidence_effects | 必填数组，1–12 项，引用 evidence_effect | 每项关键证据逐条判断，不靠重复转述增加证明数 |
| evidence_effect.evidence_ref | 必填，引用共享 evidence_ref | E 编号、revision、locator 的真实存在性和授权由宿主验证 |
| evidence_effect.effect | 必填 STRONGLY_SUPPORTS / SUPPORTS / NEUTRAL / WEAKENS / STRONGLY_WEAKENS / UNKNOWN | 受下表条件组合约束 |
| evidence_effect.expected_if_true | 必填 COMMON / UNCOMMON / UNKNOWN | 候选为真时证据是否常见 |
| evidence_effect.expected_if_false | 必填 COMMON / UNCOMMON / UNKNOWN | 候选为假时是否仍常见，须有授权基线/正常窗口/相邻对象依据 |
| evidence_effect.reason | 必填 string，1–600 字符 | 说明判断依据及范围；无对照不凭直觉 |
所有新增对象保持 additionalProperties:false；candidate 原有字段、必填与 allOf 条件保留，不削弱支持证据、反证引用、可证伪条件或排序限制。

### 条件规则
| expected_if_true | expected_if_false | effect 允许值 |
|---|---|---|
| 任一为 UNKNOWN | 任一为 UNKNOWN | UNKNOWN；任一未知即适用 |
| COMMON | COMMON | NEUTRAL |
| UNCOMMON | COMMON | WEAKENS / STRONGLY_WEAKENS |
| COMMON | UNCOMMON | SUPPORTS / STRONGLY_SUPPORTS |
| UNCOMMON | UNCOMMON | UNKNOWN，异常需重判 |
新增条件采用 allOf + if/then，每个新增 if 带 required；数组“至少含”用 contains，“不得含”用 not+contains。原有 candidate.allOf 按要求原样保留，包括其中原有的 if 写法；不为形式统一改写历史条件。
UP 须至少有 SUPPORTS 类 effect；DOWN 须至少有 WEAKENS 类。这是单向蕴含：对应 effect 是声明 UP/DOWN 的最低必要条件，不表示出现支持/削弱就必须选择对应方向；仍可保守填写 UNCHANGED/INDETERMINATE，尤其是在证据混合时。PRESENT 须有削弱类 effect 和非空 counterevidence_refs；NOT_OBTAINED 不得有削弱类 effect 或反证引用。SUPPORTS 类 E 与 support_refs、WEAKENS 类 E 与 counterevidence_refs 的跨字段引用对应由宿主验证。
UP/DOWN 触发 E 必须在本轮 delta.added/revised；仅失效、旧证据重复或无新证据不能自行推进。delta 为空只接受 UNCHANGED/INDETERMINATE。

### request 字段
| 字段 | 结构与限制 | 语义 |
|---|---|---|
| target_candidate_refs | 必填数组，1–3 项，元素 pattern 同 candidate_ref | 只指向本任务 H 或本输出 L；存在性由宿主检查 |
| if_positive | 必填 string，1–1000 字符 | 观察为阳性时如何改变候选判断 |
| if_negative | 必填 string，1–1000 字符 | 观察为阴性时如何改变候选判断 |
| information_gain | 原有字段不变 | 是否能区分领先候选与替代解释，或推翻领先候选 |
材料请求不是命令。人工模式用候选名称，不自造编号。无论结果如何都不改变判断的请求不发布；pending/handoff_proposals/review_needs 不得夹带额外材料请求。

### 禁止模型输出的属性与可信上下文
模型输出 Schema 中不得定义 prior_level、candidate_status、ooda_cycle_id、probability 属性，由闭合对象拒绝新增字段。候选内也不得加入 status。顶层既有 status=ok|blocked 是任务状态，保持不变。
| 宿主上下文字段 | 来源 | 模型权限 |
|---|---|---|
| ooda_cycle_id | HOST_COUNTER | 只读，不自增、不猜测 |
| evidence_delta | 账本与上下文编译器 | 只读，必须与账本一致 |
| current_candidates | 状态库候选登记表 | 只读，模型只引用既有 H 与提议新 L |
不得把这些宿主字段加入模型结果 Schema。字符串中伪造状态、先验或数字概率仍需宿主语义与发布门，Schema 不能证明任意自然语言无越权内容。

### reasoning 策略字段（设计规格 3.7）
| 键 | 值/含义 |
|---|---|
| version / status | 2.4.0 / CONTRACT_ONLY_NOT_RUNTIME_ENFORCED |
| ooda_is_within_task_not_phase | true |
| ooda_cycle_id_source | HOST_COUNTER |
| model_may_increment_ooda_cycle | false |
| model_may_write_candidate_status | false |
| model_may_write_prior | false |
| model_may_output_numeric_probability | false |
| host_candidate_status_values | LEADING、PLAUSIBLE、WEAKENED、PENDING、EXCLUDED_WITH_SCOPE |
| prior_values / first_cycle_prior | UNKNOWN、LOW、MEDIUM、HIGH / UNKNOWN |
| prior_from_previous_status | LEADING→HIGH；PLAUSIBLE→MEDIUM；WEAKENED→LOW；PENDING→UNKNOWN；EXCLUDED_WITH_SCOPE→LOW |
| candidate_ref_pattern | ^[HL][0-9]{2,}$ |
| effect_rules | 上述证据价值规则；ANY_UNKNOWN 表示任一 expected 未知 |
| evidence_delta_keys | added、revised、invalidated、requests_satisfied、requests_unobtainable、new_accepted_claim_ids、conflicts_opened |
| current_candidates_item_keys | candidate_ref、status、prior |
| stop_events_host_owned | NO_INFORMATION_GAIN、BLOCKED、RECOVERY_ONLY、CONFIRMED；见下文 |
| host_checks | 引用、授权、去重、增量、状态与先验所有权；见下文 |
effect_rules 首项在 expected_if_true 与 expected_if_false 中均写 ANY_UNKNOWN，这是“任一 UNKNOWN”的规则标记，不表示必须同时未知，不是允许模型输出的新枚举。

### 2.3.x 兼容边界澄清
2.2.0→2.3.x 对实际出现的 candidate/request 对象有破坏性 Schema 变更：非空 candidates 或 request_proposals 中的旧对象缺少新增必填字段时会被拒绝。未实例化这些对象、且其他字段满足约束的结果，例如 candidates 与 request_proposals 均为空的某些 blocked 回包，仍可能合法。不是所有 blocked 都自动兼容，也不是所有旧输出都会失败。宿主须依据 Agent/Skill/Schema/策略与版本锁的整包一致性识别升级，不能用“旧输出必定校验失败”检测旧成员。
具名矩阵的维度、反证联动和可重跑入口见 docs/07-reproducible-validation.md。

## 高概率候选
此契约有助于暴露缺基线、无区分度支持、同源投票和跨轮重复抬高等问题；这是设计目的，不是已证明的模型效果。局限：expected_* 仍可能标错，COMMON/UNCOMMON/UNKNOWN 无法区分“都罕见但程度不同”，序数 direction 不等于可校准后验概率。证据相关与恢复成功均不自动确认根因。

## 待验证
### 宿主责任
宿主必须验证 H 存在于本任务 current_candidates、L 在本输出唯一、target 指向本任务 H 或本输出 L。evidence_ref 存在且在授权集合，按事故/租户绑定；支持与削弱 E 分别对应 support_refs/counterevidence_refs。UP/DOWN 至少一项对应 effect 的 E 在本轮 added/revised，空 delta 不接纳方向变化。同一 E 重复支持只计一次；状态、先验及计数器只由宿主写。new_accepted_claim_ids 来自真实接纳结果，成员身份与一致本身不是证据。
宿主处理 invalidated 时先检查引用仍有效；不得让模型自建证据增量来“修复”控制上下文。新增局部 L 仅在输出内可寻址，不证明宿主已登记候选。

### 停止事件
NO_INFORMATION_GAIN 引用 limits.max_no_gain_completed_rounds，不在 reasoning 中复制阈值，由宿主按真实完成回灌判断。BLOCKED 登记受阻与不可获得，同一材料不重复请求；本版不改变现有 early_handoff 权限缺口。RECOVERY_ONLY 分开记录恢复与 RCA。CONFIRMED 不能由模型宣布，RCA CONFIRMED 须人工或可核规则。
B25–B28 与 T25–T30 是新增验收设计，仍为 NOT_RUN_IN_TARGET_HOST。现有 B/T 状态不升级为通过。离线测试主动保留结构合法但引用无效/增量不实的样例，说明 Schema 与宿主之间的责任边界。

## 已排除
### 未采纳项及原因
| 未采纳项 | 原因/沿用方案 |
|---|---|
| 模型自填 prior_level | 无依据，易锚定；只由宿主写先验 |
| 模型自宣布 STOP_CONFIRMED | RCA 确认非模型权限；由人工或可核规则负责 |
| BLOCKED_CONTROL_CONTEXT | 不新增状态，沿用 status=blocked + blocked_reasons |
| domain_observations | 沿用 facts，继续接受宿主语义验收 |
| WAIT_FOR_RESULT / VERIFY_CLAIM 等新 Act 类型 | 由宿主调度，模型不新增阶段或动作权限 |
| contradiction_review / recovery_verification_request 独立字段 | 放入 pending/handoff_proposals/review_needs，不借此绕过原子请求配额 |
没有实现 Harness、生产连接、执行器、审批权限或模型自写状态。保留既有 Agent/Skill ID、头像和插件角色列表。团长指定原文最后一个自检问句与“任一为是”极性相反：原文保留，并紧邻补充判读规则，明确最后一问须为是、前面的错误检查须为否；以 Decide/request 契约为准。

## 判断依据附加契约
2.4.0 在旧 OODA 之前加入任务内可验证子问题，在 evidence_effect 之下增加 reference_basis 与 case_specific_factors，并给请求增加 discriminates_between。旧 effect、direction 与反证条件不变；新增的无参考约束只会更严格，不以结构替代可比性证明。详见 [判断依据](08-judgment-basis.md)。
