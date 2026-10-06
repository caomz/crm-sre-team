历史记录，非 2.3.0 结论

# 电信 CRM 稳定性专家团 · 2.2.0
2026-09-21 修订｜离线证据分析｜所有生产动作仅人工评审卡｜保留 1 团长、6 常设专家与 1 按需 K8s。

## 已确认事实
本版修改了八份 Agent 提示词、八份独立 Skill 入口、共享协议、七类专业知识、九种模板、插件快捷提示和八个独立角色 ZIP。版本与副本从同一编辑源生成。
保留既有注册 ID `telecom-crm-sre-team-lead`；`stability-director` 是 Skill ID，另一个团长称呼仅在策略中声明为显式别名，尚未在任何宿主注册。
本包含机器可读策略、JSON Schema、离线构建/结构校验工具以及待执行行为用例。**不含已实现的运行时 Harness，不宣称已在 WorkBuddy 注册、导入或调用成功。**

## 高概率候选
本版将反自模拟、阶段、证据与风险要求集中为宿主接入契约，预计可减少旧提示词互相冲突；支持依据见 [诊断与修订映射](docs/01-diagnosis-resolution.md)。
限制是提示词、Schema 和静态检查不能证明真实调用或语义正确；下一验证应运行 [T01–T24](tests/harness-acceptance-checklist.md)，不能只看回复措辞。

## 待验证：选择正确入口
| 当前条件 | 使用入口 | 不能声称具备的能力 |
|---|---|---|
| 没有 Harness，只能加载普通提示词/Skill | 显式选择 [人工记账单模型](manual-mode/single-model.md)，或对应 Skill 的 MANUAL-MODE.md | 没有自动账本、阶段门、调用证明或发布门，不是多人会诊 |
| 已自行实现并验证宿主 Harness | agents/ 与各 Skill 的 SKILL.md；按 [接入契约](docs/03-integration-contract.md) 注入任务 | 文件导入本身不等于 Harness 生效 |
| 宿主声称能多 Agent，但无唯一输出门/权限隔离/调用验收 | 不启用托管团队 | 不能以工具名字存在代替能力验证 |
托管入口缺少可信上下文应返回 blocked，这是防止假冒运行时的设计；不要让模型自造 harness_context 来“修复”。两个入口不能同时加载为同一角色提示词。

## 文件导航
[变更摘要](MODIFICATIONS.md) · [迁移说明](MIGRATION.md) · [实际验证记录](VALIDATION.md)。
[Harness 建议稿](docs/02-harness-architecture-proposed.md) · [MVP/目标态](docs/04-mvp-target-plan.md) · [与本地蓝图对照状态](docs/05-local-blueprint-comparison.md)。
`policy-source/` 是编辑源；`agents/`、`skills/`、`templates/` 与 `individual-packages/` 是生成发布物。
`policies/` 是接入策略，不是已执行的权限配置；`schemas/` 只做结构约束；[离线构建工具](tools/README.md) 可重建和校验副本。
[原 B01–B24](tests/behavior-cases.md) 与 [T01–T24](tests/harness-acceptance-checklist.md) 均保留未运行状态。`tests/test_contracts.py` 是独立的离线结构/策略测试，不代表 48 个目标行为用例通过。

## 已排除
没有生产连接、执行器、凭据需求、可复制生产命令示例、自动审批或自动恢复验证。没有改动用户的 WorkBuddy 配置或生产环境。
上传包未包含用户的 `02-harness-architecture.md`；本稿使用不同文件名，不覆盖该预留文档，不伪造逐条差异。
离线不等于模型本地运行或材料不外发；分享许可、人工审批制度与目标宿主权限仍须现场落实。
