> 适用范围：本文件保留旧版托管设计/历史说明；当前 WorkBuddy 接入与模式规则以根 README、MIGRATION 和 docs/11-workbuddy-host-acceptance.md 为准。

# 判断依据契约 · 2.4.0（2026-09-21）
## 已确认事实
本设计以用户给出的费米化、外部视角、内部修正、更新和长期校验框架为需求来源；没有外部研究验真或诊断改善实验。这里定义工程契约，不声称实现数值贝叶斯推断或统计概率校准。

| 判断步骤 | 本次结构 | 边界 |
|---|---|---|
| 费米化 | candidate.judgment_questions | 模糊问题拆成可观测判据；不加新 phase 或隐藏请求 |
| Observe | evidence_delta 与授权 E | 只认宿主增量；同源重复不增量计数 |
| Outside view | evidence_effect.reference_basis | 对照来源/范围/可比性/局限；无参考则未知 |
| Inside view | evidence_effect.case_specific_factors | 当前差异与证据；不能代替基线或制造因果 |
| Orient | expected_*、effect、posterior_direction | 保留原映射、反证条件与本轮触发规则 |
| Decide | discriminates_between、if_positive/if_negative | 实际区分候选，不靠列举数量证明信息增益 |
| Act | 原路由/请求/评审/交接提议 | 不执行、不批准、不改变状态 |
| 长期检验（未来） | 独立裁决与离线题集设计 | 当前不评分，不等价于概率校准或正式 resolution |

### 模型输出字段表
所有新增对象 additionalProperties=false，以下长度和数量是设计上限而非测试统计。

| 对象/字段 | 类型和边界 | 语义 |
|---|---|---|
| candidate.judgment_questions | 必填数组，1–6 项 | 每个候选至少一个子问题；无候选依据不凑 candidate |
| question.question_ref | 字符串，^Q[0-9]{2,}$ | 本输出局部 Q；与宿主请求 Q 不同命名空间 |
| question.question / observable | 字符串，各 1–1000 | 具体问题；对象、时窗、口径和判据 |
| question.target_candidate_refs | 1–3 项，唯一 H/L | 须含所属候选；实际关系由宿主验收 |
| question.answer_type | BINARY / DIRECTIONAL / ORDERING / COMPARATIVE / UNKNOWN | 拟判断的可观测关系 |
| question.decision_relevance | HIGH / MEDIUM / LOW | 区分价值，不是概率 |
| question.current_answer | 字符串，1–1000 | 未知使用 UNKNOWN；无引用不得填其他答案 |
| question.basis_refs | 0–12 个 evidence_ref | 非空不代表真实或答案正确 |
| effect.reference_basis | 必填闭合对象 | 以下五项均必填 |
| basis.basis_type | SAME_OBJECT_HISTORY / PEER_OBJECTS / NORMAL_WINDOW / SIMILAR_INCIDENTS / DOCUMENTED_BASELINE / NO_REFERENCE_AVAILABLE | 参考来源类型，不是天然可信等级 |
| basis.basis_refs | 0–12 个 evidence_ref | NO_REFERENCE_AVAILABLE 必须空；其他类型至少一个 |
| basis.comparison_scope | 原 scope 对象 | object_alias、event_window、timezone、limitations；对照是否可比由宿主判断 |
| basis.baseline_relation | 字符串，1–1000 | 参考怎样支持各侧预期，不编造基础率 |
| basis.limitations | 字符串，1–1500 | 口径、负载、窗口、版本、选择偏差及缺失 |
| effect.case_specific_factors | 必填数组，0–6 项 | 可以为空；不强迫编故事 |
| factor.factor / reason | 字符串，各 1–600 | 差异与理由 |
| factor.evidence_refs | 1–12 个 evidence_ref | 当前差异的授权依据 |
| factor.direction | FAVORS_CANDIDATE / WEAKENS_CANDIDATE / NO_DISCRIMINATION / UNKNOWN | 特异因素提议，不是候选状态或阶段 |
| request.discriminates_between | 必填 1–3 项，唯一 H/L | 须为 target_candidate_refs 子集；Schema 不验证动态子集 |

### 条件约束
NO_REFERENCE_AVAILABLE 使两个 expected_* 与 effect 都为 UNKNOWN。非 UNKNOWN 预期必须有参考；提供参考仍允许 UNKNOWN，不能仅因存在材料就声称常见。旧 effect 的五种映射与反证、L 编号、方向最低证据规则原样保留。
只有在 basis_refs 为空时，current_answer 必须 UNKNOWN；已有证据仍不足判断时也可以 UNKNOWN。问题/对照/因素的 evidence_ref 复用原 E/revision/locator 类型，不新增身份分配权限。
case_specific_factors 不重写映射，不将同一个 E 计成多个独立支持。子问题可能依赖或重叠，不在本包做独立概率假设、乘法或聚合。

### 可选宿主参考上下文
runtime-contract 增加 optional_trusted_context_fields=[reference_context]，原必需列表保持。reference_context 的策略结构允许 historical_baselines、peer_baselines、known_similar_incidents、service_norms，每项使用 basis_type、basis_refs、comparison_scope、baseline_relation、limitations；这是接入约定，不是本包已实现的宿主官方配置。
宿主须先授权、脱敏并登记引用。历史事故或 peer 不等于开放其他事故/租户材料。缺失、为空、过期或不可比时不能当基线；可继续对无依据预期使用 UNKNOWN。用户正文同名对象不是控制通道。

## 高概率候选
可审计的判断链有望暴露空泛推断，仍需行为试验才知道收益与额外输出成本。对照存在不是因果证明；历史故障与当前事故不一定同类。提问数量、非 UNKNOWN 比例和果断程度都不作为单独成功指标。

## 待验证
### 宿主/人工语义门
须验证 Q 在本结果跨候选唯一、target 含所属候选、引用存在且已授权、reference 与观察可比、每侧 expected 有依据、特异因素与主 effect 的关系有说明、不绕过旧映射、区分集合是 target 子集且两分支真正改变比较。原 phase、权限、原子预算、状态及最终确认门不变。结构通过的反例已用于证明这些语义不能由 Schema 替代。
自由文字仍可能夹带数字概率或自报评分，闭合属性只拒绝新增字段。不能把 test 中演示的结构可通过文本拿去直接发布；唯一输出门仍待实现。

### 合成评估设计与未来指标
J 题仅存合成证据序列、参考可用性、UNRESOLVED 的独立裁决占位和良好判断属性；NOT_RUN_IN_MODEL / NOT_SCORED，不把设计标签当真实 RCA。
未来按 incident class、role、材料充足性和参考类型分层，并保留未知裁决与弃答覆盖。人工或可审计规则须先定义裁决时间、证据窗口、适用范围、分母和排除条件，不能由待评模型给自己打分。
| 拟议指标 | 必须先定义的分母/裁决 | 限制 |
|---|---|---|
| support_precision / weaken_precision | 被独立裁决的效应提议数与逐效应判定 | 候选最终真假不自动裁决中途方向是否合理 |
| request_discrimination_rate | 已得到结果且可裁决的请求 | 未取得材料单列，不算无信息或错误 |
| stale_evidence_reuse_rate | 可审计方向提议及触发 E/delta | 同源再叙述不是新增支持 |
| unsupported_commonness_rate | 已复核的非 UNKNOWN 预期 | 填了 refs 仍可能无可比依据 |
| contradiction_response_rate | 已确定适用反证、且模型有接收机会的回合 | 反证本身可能修订，不强迫每次 DOWN |
| false_causal_link_rate | 已独立复核的因果断言 | 不用单纯恢复裁决因果 |
| indeterminate_rate + unsupported_direction_rate | 同一分层中的可评提议与依据裁决 | 联合看覆盖与无依据判断，不奖励强行猜测 |
这些是待实现的过程代理指标，不是 Brier、概率 calibration 或正式 resolution。没有持久评估采集器、数值概率映射、自动候选分离状态或评分结果。

## 已排除
不引入模型 host_probability、prior_level、candidate_status、ooda_cycle_id、Brier/校准字段；不让模型宣布 CONFIRMED。不实现 Harness、不扩大参考访问、不把子问题作为额外请求、不用历史事故强套当前基础率。settings、early handoff、外链和真实宿主兼容性另行验证。

### 决策记录
可选参考上下文：计划一处要求“新增可信上下文”，另一处又要求缺失时不 blocked。本次放在 optional_trusted_context_fields，不改原必需 trusted_context_fields；宿主可不给，但不得用伪造控制或模型常识补基线。
编号冲突：现有 Q 是宿主取证请求编号；计划中的 question_ref 仍采用 Q 格式，但限定为本输出 judgment_questions 的局部命名空间，宿主必须分型解析，不能按裸字符串合并。人工模式仍不分配编号。
未指定的字段类型与上限：observable 为有界文字（对象/时窗/口径/判据由宿主复核）；comparison_scope 复用已有 scope；current_answer 无依据时使用文字 UNKNOWN。每候选子问题上限六项、特异因素上限六项；参考/问题/因素引用上限十二项。这些是本次保守契约选择，不是运行测量。
case_specific_factors 保留为必填数组但允许空，避免强迫模型编造当前差异。reference_basis 也必填；无参考用 NO_REFERENCE_AVAILABLE，而不是漏字段。
跨字段关系：discriminates_between 是目标子集、子问题含所属候选、Q 唯一、引用存在性与可比性均列为未实现的宿主门；不采用非标准 Schema 扩展伪装能验真。
文档编号：已有 docs/07-reproducible-validation.md，判断依据说明使用 docs/08-judgment-basis.md，保留原文档与历史补丁。
评估边界：保留用户计划中的费米化、参考类、内部修正、长期评估框架；只落结构和离线题集，不引入模型概率、Brier、正式校准/resolution 或自动状态。代理指标不等价于统计校准；没有实验支持“已提高诊断质量”。
