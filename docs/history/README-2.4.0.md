历史记录，非 2.5.0 结论。

# 电信 CRM 稳定性专家团 · 2.4.0
2026-09-21｜离线判断依据契约：可验证子问题、参考类、当前差异和候选区分请求。

## 已确认事实
本版以 2.3.1 为基线，在现有 OODA 序数化证据更新上增加 judgment_questions、reference_basis、case_specific_factors 和 discriminates_between。只编辑源文件，生成入口与独立包由 tools/build_bundle.py 重建。
**费米化与 OODA 都是任务内判断顺序，不是 P0–P7。** 先验、候选状态、循环计数、最终确认仍由宿主维护；模型不输出数字概率，不执行生产动作。
2.3.x→2.4.0 是新增必填对象的 Schema 破坏性升级。非空候选/请求缺新增结构会被拒绝；未实例化这些对象且满足其他约束的某些 blocked 空回包仍合法，不能用一次 Schema 结果判断角色是否已升级。须整包替换 Agent、Skill、schemas、policies、参考/模板、manual、独立包及版本锁。
reference_context 是宿主可信通道的**可选**扩展，不加入必需锚点。缺失或为空不单独阻断任务；无法支持的预期保持 UNKNOWN，不能凭常识补参考。

## 高概率候选
结构化依据可供审计和未来行为比较，但还没有目标模型实验验证质量改善。Schema 只能检查结构，不证明基线可比、来源真实、问题可回答或请求确有信息增益。参考 [判断依据](docs/08-judgment-basis.md)、[OODA](docs/06-ooda-reasoning.md) 与 [可复现验证](docs/07-reproducible-validation.md)。

## 待验证：选择正确入口
没有 Harness 时显式选择 [人工记账单模型](manual-mode/single-model.md)，不与托管入口同时加载；不具备自动账本、阶段门或真实会诊。已有自建并验收 Harness 的环境按 [接入契约](docs/03-integration-contract.md) 提供控制和发布门。
[行为 B01–B36](tests/behavior-cases.md)、[宿主验收 T01–T38](tests/harness-acceptance-checklist.md) 均为 NOT_RUN_IN_TARGET_HOST。长期评估题集 tests/judgment-evaluation-cases.json 是合成设计，NOT_RUN_IN_MODEL / NOT_SCORED；没有 Brier 或校准成绩。
settings.json 历史缺失、任意阶段 early_handoff 与 P7-only HANDOFF 缺口、团长自检极性原文及其判读补充继续保留；外链和市场字段未联网核验。

## 文件导航
[迁移说明](MIGRATION.md) · [修改摘要](MODIFICATIONS.md) · [真实验证记录](VALIDATION.md) · [修订历史](CHANGELOG.md) · [本地工具](tools/README.md)。
policy-source 是提示词源；agents、skills、templates、manual-mode、individual-packages 与 prompt-bundles.lock 是生成物，不手改副本。tests/test_judgment_contracts.py 与 tests/test_judgment_matrix.py 提供判断依据回归；确定性集成仍单独执行。
当前提示词补丁为 docs/prompts-2.3.1-to-2.4.0.patch，只覆盖 Agent/Skill 入口，不能代替 Schema、策略和完整包升级。旧补丁与报告留在 docs/history 或原路径，明确仅作历史。

## 已排除
不实现 Harness、不提供生产连接、执行器、安装注册或自动审批；不扩大角色权限。不把结构通过写成模型准确、统计校准或恢复/RCA 已确认。
