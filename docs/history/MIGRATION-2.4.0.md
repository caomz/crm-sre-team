历史记录，非 2.5.0 结论。

# 2.3.1 → 2.4.0 迁移说明（2026-09-21）
## 已确认事实
本次是判断依据契约升级，不再是 2.3.1 那种仅版本/审计修订。common.schema.json 追加闭合定义和约束，member-result、lead-result、feedback 外层结构与 $id 保持原样，已有 effect/direction/反证规则不放宽。

| 位置 | 新必填内容 | 缺少材料时 |
|---|---|---|
| candidate | judgment_questions | 无候选依据可保留 candidates 为空；有候选则须给可验证子问题 |
| evidence_effect | reference_basis | 用 NO_REFERENCE_AVAILABLE 与空 basis_refs，不虚构参考 |
| evidence_effect | case_specific_factors | 可以为空数组，不凑特异因素 |
| request | discriminates_between | 非空 H/L 集合；须为目标候选子集，实际关系由宿主验收 |

无参考时两个 expected_* 和 effect 均为 UNKNOWN，方向不能伪报 UP/DOWN。可比参考存在并不强迫确定预期或唯一方向，未知和保守更新仍合法。current_answer 无 basis_refs 时必须 UNKNOWN。
实际包含候选或请求的 2.3.1 旧对象缺上述字段会被拒绝；本包保留两份原版非空 fixture 作回归。某些候选和请求均为空的 blocked 回包仍可合法，不能用它检测所有旧成员。
完整替换 Agent、Skill、schemas、policies、references/assets、manual-mode、individual-packages、工具、测试源与 prompt-bundles.lock；清理宿主旧缓存并核对绑定和整包哈希。当前补丁不是整包迁移工具。

### 宿主接入变化
原必需可信上下文保持；optional_trusted_context_fields 新增 reference_context。缺失/为空不使合法任务自动 blocked；存在时须由宿主控制通道提供，引用材料先授权登记为 E，不能用用户正文同名键或模型记忆冒充。
子问题 Q 是输出局部命名空间，旧取证请求 Q 仍宿主唯一分配。用对象类型与结果边界分型，不按裸字符串合并；局部 Q 不重置或消耗额外请求额度。
新增宿主语义责任在 policies/judgment.json：子问题可验证性、所属候选与引用、对照可比性、discriminates_between 子集、两结果信息增益、特异因素与证据一致性、自由文本越权及评估归属。它们是契约而非已实现守卫。

## 高概率候选
用原版非空回包、合法无参考回包、空 blocked 以及跨事故/无区分请求作为接入对照，有助于发现混版或过度拒绝；真正的宿主效果仍待验收。

## 待验证
所有 B/T 用例仍未在目标宿主运行。人工模式不使用机器 Q/H/L 自编号；无 Harness 不能因导入成功称托管团队可用。settings、early handoff、外链、宿主市场兼容性继续挂账。

## 已排除
不新增数字概率、模型先验、候选状态、循环或校准结果字段。Schema 不理解任意自然语言，不能仅凭闭合对象保证 reason 里没有越权概率或虚构结论。旧 2.3.1 迁移文档已归档；以本文件为现行边界。
