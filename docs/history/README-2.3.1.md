历史记录，非 2.4.0 结论。

# 电信 CRM 稳定性专家团 · 2.3.1
2026-09-21 修订｜离线证据分析｜OODA 契约不变｜校验确定性与审计可复现性修复。

## 已确认事实
本次是 2.3.0 的修订版，不增加候选/请求字段，不改 effect、direction、反证一致性规则或宿主可信上下文；共享 Schema 原文件保持不变。仅修复校验输出顺序、补齐具名矩阵与兼容边界回归测试，并校正迁移说明。所有发布生成物由编辑源统一重建。
**OODA 是任务内判断协议，不等于 P0–P7。** phase、候选状态、先验与循环计数仅由宿主管理。Harness 仍为 NOT_IMPLEMENTED；文件导入不代表托管能力已经实现。
2.2.0→2.3.x 对实际出现的 candidate/request 对象有破坏性 Schema 变更：非空 candidates 或 request_proposals 中的旧对象缺少新增必填字段时会被拒绝。未实例化这些对象、且其他字段满足约束的结果，例如 candidates 与 request_proposals 均为空的某些 blocked 回包，仍可能合法。不是所有 blocked 都自动兼容，也不是所有旧输出都会失败。宿主须依据 Agent/Skill/Schema/策略与版本锁的整包一致性识别升级，不能用“旧输出必定校验失败”检测旧成员。
2.3.0→2.3.1 没有新增输出协议破坏；仍须整包替换，避免混用版本锁、Agent、Skill、策略、Schema 副本及独立包。

## 高概率候选
具名矩阵能降低审计时把反证联动或单向蕴含误当漏洞的风险，但仅覆盖列明维度，不证明证据真实或模型推理正确。详见 [可复现验证说明](docs/07-reproducible-validation.md) 和 [OODA 契约](docs/06-ooda-reasoning.md)。

## 待验证：选择正确入口
| 当前条件 | 使用入口 | 不能声称具备的能力 |
|---|---|---|
| 没有 Harness | 显式选择 [人工记账单模型](manual-mode/single-model.md) 或对应 Skill 的 MANUAL-MODE.md | 无自动账本、阶段门、调用证明或多人会诊 |
| 已自行实现并验收 Harness | agents/ 与 Skill 的 SKILL.md；遵循 [接入契约](docs/03-integration-contract.md) | 不能以导入成功代替接入验收 |
| 缺少唯一输出门、权限隔离或调用验收 | 不启用托管团队 | 工具名字存在不代表可信调用 |
托管入口缺少可信上下文应 blocked；存在但为空不等于缺失。不能同时加载人工与托管入口。
[行为 B01–B28](tests/behavior-cases.md) 与 [验收 T01–T30](tests/harness-acceptance-checklist.md) 仍全为 NOT_RUN_IN_TARGET_HOST。settings 历史缺失、early handoff 缺口、团长自检极性说明与外链未联网核验状态保持不变。

## 文件导航
[迁移说明](MIGRATION.md) · [修改摘要](MODIFICATIONS.md) · [实际验证记录](VALIDATION.md) · [修订记录](CHANGELOG.md) · [本地工具](tools/README.md)。
policy-source 是提示词编辑源；agents、skills、templates、manual-mode、individual-packages 与 prompt-bundles.lock 是生成物，不能手工修补生成副本。
新增的 tests/test_reasoning_matrix.py 可直接重跑具名矩阵并导出逐例报告；tests/test_validation_determinism.py 是单独执行的集成测试，避免校验器递归调用自身。
历史 2.1.0→2.2.0、2.2.0→2.3.0 提示词补丁保留但不适用于当前文件。当前补丁为 docs/prompts-2.3.0-to-2.3.1.patch，只更新提示词版本标记，不能代替整包更新。历史文档与旧验证产物保存在 docs/history，不充当本次结果。

## 已排除
没有实现 Harness、生产连接、执行器或自动审批；没有扩大权限或改动 Agent/Skill ID、头像、插件角色列表、maxTurns、用户账户或宿主配置。静态通过不等于真实模型、市场认证或宿主导入通过。
