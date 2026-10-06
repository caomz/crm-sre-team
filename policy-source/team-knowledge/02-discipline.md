# 团队知识引用纪律

本文件仅用于旧版外部 Harness 契约，不可混入 Native 运行入口。
知识索引说明资料可能存在，不证明授权、已读取、可比性或本次现场事实。原始资料如果确实属于本次事故，须由宿主核对对象、时窗与授权后登记；不能只凭存储位置决定证据资格。历史案例必须标清历史，不迁移历史根因到当前事故。

## Schema 是结构真源

具体类型以随包 common.schema.json 的 $defs.reference_basis、$defs.scope、$defs.evidence_ref 和 $defs.evidence_effect 为准。
reference_basis 的字段为 basis_type、basis_refs、comparison_scope、baseline_relation、limitations。不得新增别名字段。
basis_type 只允许 SAME_OBJECT_HISTORY、PEER_OBJECTS、NORMAL_WINDOW、SIMILAR_INCIDENTS、DOCUMENTED_BASELINE、NO_REFERENCE_AVAILABLE。
basis_refs 是包含 evidence_id、revision、locator 的对象数组，不是路径字符串数组。非空引用只能回显宿主已登记且授权的材料编号；索引链接、模型记忆或“文档存在”都不是有效引用。
comparison_scope 是包含 object_alias、event_window、timezone、limitations 的对象，不是自由文本。时区未知使用 null，不猜测。

## 已登记参考资料的结构示例

下例仅为离线 Schema 合成测试。E002 并未在用户现场登记；模型不能复制它作为真实证据。只有实际宿主已提供相应引用时，才能使用 DOCUMENTED_BASELINE。

```yaml
basis_type: DOCUMENTED_BASELINE
basis_refs:
  - evidence_id: E002
    revision: 1
    locator: 合成参考资料第1段
comparison_scope:
  object_alias: SYNTHETIC_OBJECT_A
  event_window: 合成正常窗口
  timezone: null
  limitations: 未核对版本可比性
baseline_relation: 仅演示已登记参考资料的结构，不代表事故事实
limitations: 合成示例，不能用于现场结论
```

## 没有可用参考资料

```yaml
basis_type: NO_REFERENCE_AVAILABLE
basis_refs: []
comparison_scope:
  object_alias: SYNTHETIC_OBJECT_A
  event_window: 事故窗口待确认
  timezone: null
  limitations: 没有可比参考
baseline_relation: 尚不能建立参考关系
limitations: 等待宿主提供授权参考，不根据模型记忆补齐
```

NO_REFERENCE_AVAILABLE 时 basis_refs 必须为空，对应 evidence_effect 的 expected_if_true、expected_if_false 和 effect 都须为 UNKNOWN。
expected_if_true/expected_if_false 只能为 COMMON、UNCOMMON、UNKNOWN，解释写在 reason，不把句子塞进枚举字段。两边都是 COMMON 时 effect 只能 NEUTRAL；任一边 UNKNOWN 时 effect 只能 UNKNOWN。evidence_effect 还需要 evidence_ref 和 case_specific_factors，不能把候选级字段随意放到 effect 里。
反证状态按正式候选 Schema 使用 PRESENT 或 NOT_OBTAINED，不新增自定义 NONE。缺少材料不是排除依据，也不能因为索引缺一项就推导未发生。

## 取证与阶段

P1/P3 可按需读 [知识索引](01-knowledge-index.md) 与 [上下文摘要](00-context-summary.md)，但不自动获得访问其他对象的权限。P2 只提出有判别价值的最小需求；不得添加正式 request Schema 未定义的字段。P6 分别记录恢复与根因状态；P7 可建议人工更新知识库，不自动写入用户仓库。
维护真源为 policy-source/team-knowledge；不要手改生成的 skills 目录。修改后重新构建并验证所有 lock 与独立 ZIP。
