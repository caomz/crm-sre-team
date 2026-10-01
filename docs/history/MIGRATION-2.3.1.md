历史记录，非 2.4.0 结论。

# 2.3.0 → 2.3.1 迁移说明（2026-09-21）
## 已确认事实
2.3.1 是验证工具、审计证据和文档修订版。共享 Schema 字节、策略业务语义、trusted_context_fields 与 OODA 提示词正文保持不变；仅更新当前版本标记。2.3.0 已合法的候选/请求对象不因本次修订产生新的必填字段或枚举要求。
整体更新 Agent、Skill、schemas、policies、references/assets、manual-mode、individual-packages、构建工具和 prompt-bundles.lock。版本锁现额外覆盖全部 tests/*.py 测试源；动态测试报告仍不进入根锁。哈希用于完整性而非来源签名。

### 从 2.2.0 升级的精确边界
2.2.0→2.3.x 对实际出现的 candidate/request 对象有破坏性 Schema 变更：非空 candidates 或 request_proposals 中的旧对象缺少新增必填字段时会被拒绝。未实例化这些对象、且其他字段满足约束的结果，例如 candidates 与 request_proposals 均为空的某些 blocked 回包，仍可能合法。不是所有 blocked 都自动兼容，也不是所有旧输出都会失败。宿主须依据 Agent/Skill/Schema/策略与版本锁的整包一致性识别升级，不能用“旧输出必定校验失败”检测旧成员。
候选新增字段为 candidate_ref、posterior_direction、evidence_effects；请求新增字段为 target_candidate_refs、if_positive、if_negative；反证一致性规则继续执行，不放宽 additionalProperties 或必填约束。
仍须由宿主提供可信 ooda_cycle_id、evidence_delta、current_candidates。H 编号登记、L 唯一性、增量真实性、证据授权、状态/先验与去重由宿主检查，本包没有实现这些运行时控制。
新增 test_44/test_45 分别隔离候选与请求的旧形状拒绝；test_46 记录空候选且空请求的 blocked fixture 可继续合法。这个事实不赋予旧成员运行时兼容资格。

## 高概率候选
先保存可回退配置，再用版本锁、角色绑定、缓存清理和合成任务确认整包一致性，比依赖一次 blocked 回包更能发现成员未升级。这里是接入检查建议，不是已实现的版本协商机制。

## 待验证
没有 Harness 时显式选择 MANUAL-MODE，不与托管提示词同时加载。有 Harness 时仍须单独运行 B01–B28、T01–T30；当前所有用例为 NOT_RUN_IN_TARGET_HOST。没有在用户宿主执行安装、注册、模型调用或权限验收。
settings.json、early handoff 权限缺口、外部链接及宿主市场字段兼容性本次不处理。跨平台保证限于当前环境和明确的排序扰动测试，不宣称原生 Windows 或不同依赖环境已验收。

## 已排除
没有新的 Schema 破坏性变更，没有增加生产权限、候选状态字段或宿主功能。旧版迁移文档已原样归档在 docs/history/MIGRATION-2.3.0.md；其中“旧形状输出都会被拒绝”的概括已由本文件限定，不把历史措辞当现行保证。
历史提示词补丁不适用于 2.3.1 当前文件；新增 2.3.0→2.3.1 补丁仅更新版本标记，不能代替完整升级。
