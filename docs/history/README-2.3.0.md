历史记录，非 2.3.1 结论；其中迁移概括及矩阵数字请以当前文档为准。

# 电信 CRM 稳定性专家团 · 2.3.0
2026-09-21 修订｜离线证据分析｜OODA 与序数化证据更新契约｜所有生产动作仅人工评审卡。

## 已确认事实
本版在共享 Schema 中增加 candidate_ref、posterior_direction、evidence_effects，以及请求的 target_candidate_refs、if_positive、if_negative；增加 reasoning 策略并同步托管提示词、人工入口、参考与模板。Agent/Skill、注册 ID、头像及插件 agents/skills/members 列表保持兼容约束。
**OODA 是任务内判断协议，不等于 P0–P7。** phase、候选状态、先验与循环计数仅由宿主控制，模型只提议。本包没有实现运行时 Harness，implementation_status=NOT_IMPLEMENTED，不宣称已在 WorkBuddy 注册、导入或调用成功。
2.2.0→2.3.0 是 Schema 破坏性变更，旧形状输出会被拒；须整体替换 Agent+Skill+schemas+individual-packages，宿主须新增可信 ooda_cycle_id、evidence_delta、current_candidates。保留注册 ID telecom-crm-sre-team-lead；stability-director 仍是 Skill ID。

## 高概率候选
本版以证据常见性比较和请求分支暴露无区分度支持、同源投票、旧证据跨轮重复抬高。设计依据与剩余责任见 [OODA 契约](docs/06-ooda-reasoning.md) 与 [诊断映射](docs/01-diagnosis-resolution.md)。这些是契约约束，不是目标模型效果或已实现的宿主门禁。Schema 不证明引用真实、基线准确或因果成立。

## 待验证：选择正确入口
| 当前条件 | 使用入口 | 不能声称具备的能力 |
|---|---|---|
| 没有 Harness，只能加载普通提示词/Skill | 显式选择 [人工记账单模型](manual-mode/single-model.md)，或对应 Skill 的 MANUAL-MODE.md | 无自动账本、状态门、调用证明或发布门，不是多人会诊 |
| 已自行实现并验证宿主 Harness | agents/ 与各 Skill 的 SKILL.md；按 [接入契约](docs/03-integration-contract.md) 注入任务 | 文件导入本身不等于 Harness 生效 |
| 宿主无唯一输出门、权限隔离或调用验收 | 不启用托管团队 | 工具名字存在不代表可信调用 |
托管入口缺少可信上下文应 blocked；存在但为空不等于缺失。不要让模型自造 harness_context，不能同时加载托管与人工入口。
[行为 B01–B28](tests/behavior-cases.md) 与 [验收 T01–T30](tests/harness-acceptance-checklist.md) 全部 NOT_RUN_IN_TARGET_HOST。离线 Schema 单测不代表这些目标行为用例通过。settings 历史缺失、提前交接契约缺口及外链未核验，详见修改摘要。

## 文件导航
[变更摘要](MODIFICATIONS.md) · [迁移说明](MIGRATION.md) · [实际验证记录](VALIDATION.md) · [修订记录](CHANGELOG.md)。
[Harness 建议稿](docs/02-harness-architecture-proposed.md) · [MVP/目标态](docs/04-mvp-target-plan.md) · [本地蓝图对照](docs/05-local-blueprint-comparison.md)。
policy-source 是提示词编辑源；agents、skills、templates、manual-mode、individual-packages 与 prompt-bundles.lock 均为生成物。policies 是接入策略而非已执行权限；[本地构建工具](tools/README.md) 只处理本包文件。
2.1.0→2.2.0 提示词补丁是历史补丁，不适用于当前文件；2.2.0→2.3.0 补丁及真实验证记录分别见 docs/prompts-2.2.0-to-2.3.0.patch 与 tests/prompt-patch-check.json。旧版本原文保存在 docs/history。

## 已排除
没有生产连接、执行器、凭据需求、可复制生产命令示例、自动审批或自动恢复验证。没有改动用户账户、WorkBuddy 配置或生产环境。不实现 Harness，不扩大任何权限。
用户未提供 02-harness-architecture.md，不覆盖该预留文件，不伪造逐条差异。离线不等于模型本地运行或材料不外发；组织分享许可与目标宿主权限仍须现场落实。
