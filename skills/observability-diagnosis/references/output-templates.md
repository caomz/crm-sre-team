适用范围：本文的领域方法和证据纪律可用于三模式；宿主状态机、编号账本、闭合 Schema 字段、强制 JSON、接纳与发布门仅用于 MANAGED_HARNESS。原生/兼容不执行这些托管要求、不据此升级模式或索取控制字段，以当前 Agent/Skill 的互斥模式契约为准。

# 结构化输出与四象限发布
版本：2.5.0。模型输出是待验收提议；最终署名、阶段、E/取证请求 Q 编号、审批与恢复状态由程序渲染。

## 已确认事实
facts 数组可为空。每条含 claim_type、domain、statement、scope、evidence_refs、source_kind；事实提议经引用归属、位置和语义核验后才可显示为已确认事实。用户口述保持“用户报告”归属。
没有事实时写“无足够材料支持的已确认事实”，不得将一般经验、模型意见或缺失数据填入。

## 高概率候选
candidates 数组可为空；每项必须包含 hypothesis、domain、scope、support_refs、counterevidence_refs、counterevidence_status、falsification_condition、critical_alternatives、next_validation、ordinal_rank、rank_reason。
反证未获得用 NOT_OBTAINED；可证伪条件不能冒充已有反证。下一验证说明判断标准，不另向用户索取隐藏材料；实际请求仅来自配额内 request_proposals。
没有依据不要凑数量；仅一个有支持的候选也必须保留关键替代解释。排序不等于概率，不以根因已确认结束候选竞争。

## 待验证
pending 记录限制、缺口和无法核实的报告；实际请求由 request_proposals 合并到 Q 清单。风险内容只进 review_needs，最终使用预审人工评审卡，无命令或步骤字段。
成员使用 member-result.schema.json，团长使用 lead-result.schema.json；每条对象禁止未知字段。成员最多 2 请求、团长最多 3；缺上下文时 status=blocked，task_id=null 或回显已知 ID，四象限为空，blocked_reasons 明确。
可选上下文摘要、评审卡、恢复矩阵和交接都放在四象限之内，不能在正文旁路发布未验收内容。原始 token 不直接外显。

## 已排除
excluded 必须带范围与 evidence_refs，只排除材料实际能够排除的对象/时间/条件。无数据、取证失败、当前正常都不能直接排除历史故障。
格式通过、真实调用、引用存在不代表语义成立。关键因果与恢复结论需人工或可验证规则复核。

## 宿主专属字段
模型不得写 result_id、receipt、approved、executed、next_phase、正式 recovery/rca 状态。TEAM/SERIAL 专业汇编使用 basis_claim_ids，不能添加不存在的成员结果。
advice_state、approval_report、execution_report、outcome_evidence 分开；“评审材料齐备”不表示批准、安全或实施成功。所有状态变更必须有可信事件来源。
人工模式不具备上述自动能力，使用 MANUAL-MODE 入口与人工账本，不能伪装托管结果。

## 判断依据附加结构
candidates 内含 judgment_questions；evidence_effects 内含 reference_basis 与 case_specific_factors；request_proposals 内含 discriminates_between。局部子问题 Q 不代表请求已登记。结构齐全不证明参考适用、引用真实或答案正确。
