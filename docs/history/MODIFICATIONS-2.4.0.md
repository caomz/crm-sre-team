历史记录，非 2.5.0 结论。

# 2.4.0 修改摘要（2026-09-21）
## 已确认事实
从上传 2.3.1 ZIP 的只读 orig 和独立 baseline 开始，在 new 编辑允许源；所有生成物统一重建。
Schema 新增 judgment_question、reference_basis、case_specific_factor；候选、证据效应、请求新增必填字段，原条件与闭合约束不放宽。新增 judgment 策略，可选 reference_context，与原 reasoning/角色/阶段/预算权限分开。
公共 Prompt、团长、七成员、人工入口与模板增加分解、参考、差异和候选区分规则；参考文档统一分发。新增判断依据测试、具名矩阵与合成评估题；原有测试断言保留，原矩阵只补新必填 fixture 字段。新测试源与评估设计纳入根锁，报告仍在锁外。
验证工具增加新契约检查和稳定矩阵报告；差异审计从旧版“全部 Schema 字节不变”升级为“只允许追加本次定义与约束”，保护旧规则和原测试。旧审计源原样归档，不能把历史修订白名单拿来放行本次升级。

## 高概率候选
新增中间结构有助于人工审查判断依据，但无行为实验，不能宣称判断质量提高或已校准。独立样本裁决、误判代价、弃答覆盖及参考类选择仍需现场设计。

### 决策记录
可选参考上下文：计划一处要求“新增可信上下文”，另一处又要求缺失时不 blocked。本次放在 optional_trusted_context_fields，不改原必需 trusted_context_fields；宿主可不给，但不得用伪造控制或模型常识补基线。
编号冲突：现有 Q 是宿主取证请求编号；计划中的 question_ref 仍采用 Q 格式，但限定为本输出 judgment_questions 的局部命名空间，宿主必须分型解析，不能按裸字符串合并。人工模式仍不分配编号。
未指定的字段类型与上限：observable 为有界文字（对象/时窗/口径/判据由宿主复核）；comparison_scope 复用已有 scope；current_answer 无依据时使用文字 UNKNOWN。每候选子问题上限六项、特异因素上限六项；参考/问题/因素引用上限十二项。这些是本次保守契约选择，不是运行测量。
case_specific_factors 保留为必填数组但允许空，避免强迫模型编造当前差异。reference_basis 也必填；无参考用 NO_REFERENCE_AVAILABLE，而不是漏字段。
跨字段关系：discriminates_between 是目标子集、子问题含所属候选、Q 唯一、引用存在性与可比性均列为未实现的宿主门；不采用非标准 Schema 扩展伪装能验真。
文档编号：已有 docs/07-reproducible-validation.md，判断依据说明使用 docs/08-judgment-basis.md，保留原文档与历史补丁。
评估边界：保留用户计划中的费米化、参考类、内部修正、长期评估框架；只落结构和离线题集，不引入模型概率、Brier、正式校准/resolution 或自动状态。代理指标不等价于统计校准；没有实验支持“已提高诊断质量”。

## 待验证
runtime-contract 仍 NOT_IMPLEMENTED；reasoning/judgment 为 CONTRACT_ONLY_NOT_RUNTIME_ENFORCED。B/T 全部 NOT_RUN_IN_TARGET_HOST；合成 J 题为 NOT_RUN_IN_MODEL、NOT_SCORED。没有模型、宿主注册、生产或长期质量统计。
settings.json 未创建，须核对 2.1.0 原包；early_handoff_event 任意阶段与团长 HANDOFF 仅 P7 缺口未改。团长原自检最后一问的极性矛盾与相邻判读补充保留，不悄悄改原文。作者邮箱、市场展示、外部链接未验证或修改。

## 已排除
没有新 Harness、评分器、概率模型或生产工具；没有删除原文件、改变 Agent/Skill ID、头像、角色列表、工具权限或 maxTurns。所有实际测试数和哈希以 VALIDATION.md、机器报告与原始日志为准。
