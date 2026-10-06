> 适用范围：本文件保留旧版托管设计/历史说明；当前 WorkBuddy 接入与模式规则以根 README、MIGRATION 和 docs/11-workbuddy-host-acceptance.md 为准。

# 诊断与本次修订映射
## 已确认事实
本表保留原 2.1.0→2.2.0 历史诊断，并保留 OODA、追加 2.4.0 判断依据契约。P 表示提示词/文档已改，C 表示机器可读契约已写，R 表示仍需运行时实现；P/C 不是 R 已生效。

| ID/严重度 | 原问题与失效场景 | 已修改文件/内容 | 本次落实/剩余门 | 验收 |
|---|---|---|---|---|
| D01 高 | 工具存在条件与强制团队调用冲突，伪会诊 | 八角色去掉直接调度，明确三件套；roles/runtime-contract | P+C；R 独立调用与可信回执待实现 | T01/T02 |
| D02 高 | 阶段混乱、P2 阻塞与应急冲突 | incident-workflow、workflows、团长/Skill；统一八阶段 | P+C；R 状态持久化与守卫待实现 | T03/T14 |
| D03 高 | 只读/可回退打开命令出口 | risk gate、七专业参考、九模板；全部评审卡 | P+C；R 唯一受限发布器待实现 | T04 |
| D04 高 | 离线边界只是提示词 | offline-contract、runtime-contract | P+C；R 宿主权限隔离待实现 | T21/T22 |
| D05 高 | 多角色分配 E，漂号 | evidence-protocol、所有入口/模板 | P+C；R 事务账本待实现 | T06/T15 |
| D06 高 | 附件伪控制/秘密进入 trace | data-handling、harness-contract | P+C；R 模型前隔离待实现 | T12/T13 |
| D07 高 | 建议/审批/执行混同 | action-review、feedback schema、变更参考 | P+C；R 版本绑定报告入库待实现 | T08 |
| D08 高 | 恢复与 RCA 无关闭守卫 | recovery-check、handoff、workflows | P+C；R 恢复验证/人工记录待实现 | T09/T20 |
| D09 高 | 成员权威替代证据 | 团长、四象限 schema、evidence 协议 | P+C；R 引用语义复核待实现 | T10 |
| D10 高 | WF-B 二选一/默认回退 | scenario-playbook、团长 | P+C；R Workflow 路由待实现 | T17 |
| D11 中 | 成员串台 | 六常设和 K8s 角色、roles.json | P+C；R 论断权限门待实现 | T05 |
| D12 中 | 配额超额例外/轮次可重置 | evidence-protocol、limits、请求 schema | P+C；R 原子请求与轮次配额待实现 | T07/T18 |
| D13 中 | 默认直调/K8s 条件过宽 | 团长、K8s、plugin quickPrompts、roles | P+C；R 指向证据资格待实现 | T11 |
| D14 中 | 长上下文和并行结果过期 | harness-contract、workflow、上下文锚点 | P+C；R epoch/read-set 并发控制待实现 | T03/T16 |
| D15 中 | 共享副本潜在混版 | 单一 policy-source、build 工具、版本锁、八个 ZIP | 已实际生成并可离线校验；R 宿主加载校验待接入 | T22 |
| D16 中 | 静态检查冒充行为验收 | 重写 VALIDATION、保留 B/T 待测、增加离线测试 | 本次只运行结构/契约测试；R 行为测试未运行 | T24 |
| D17 低 | 团长别名与 Skill ID 混淆 | 保留注册 ID；roles.json 显式别名 | P+C；R 宿主别名映射待实现 | T02 |
| D18 高 | 候选与请求缺可寻址编号、请求不写明结果如何改变判断 | common schema 的 candidate_ref/target_candidate_refs/if_positive/if_negative，公共 Prompt 与模板 | P+C；R 候选登记、引用及请求信息增益验收待实现 | T27/T28 |
| D19 高 | 证据被无区分当作支持、同源一致被当独立证据、旧证据跨轮重复计数 | evidence_effects、posterior_direction、reasoning 策略、团长与成员 OODA | P+C；R 基线真实性、同源去重与本轮触发验收待实现 | T26/T29/T30 |
| D20 高 | 模型自填先验/状态/循环计数或被“继续”推动 | 闭合 Schema、宿主可信增量/候选上下文、状态与先验所有权 | P+C；R 状态库、计数器与唯一发布门待实现 | T25/T30 |

| D21 高 | 云状问题不可验证、局部问题与请求编号混用 | judgment_questions、局部命名空间、common/角色 Prompt | P+C；R 问题可验证性、关联和命名空间待实现 | T31 |
| D22 高 | 预期常见性无依据、参考越权或不可比 | reference_basis、可选 reference_context、NO_REFERENCE_AVAILABLE 规则 | P+C；R 授权、基线真实性与可比性待实现 | T32/T33/T34 |
| D23 高 | 请求不区分候选、重复包装额外材料 | discriminates_between、两分支、子集与预算纪律 | P+C；R 子集、实际信息增益和统一发布门待实现 | T35/T36 |
| D24 高 | 伪精确概率、模型自评校准或最终裁决 | 闭合 Schema、judgment 评估归属、未评分合成题 | P+C；R 文本语义与独立裁决待实现 | T37/T38 |

## 高概率候选
这些修订能消除已发现的文本冲突并提供可实现的边界。反向限制：没有运行时守卫，模型仍可能不遵守；JSON 合法也可能引用错误材料。下一验证须对同模型/同输入比较原提示词、优化提示词、实际 Harness 三组。

## 待验证
目标宿主导入与能力隔离、MiniMax-M3 调用、真实多 Agent 来源、阶段/账本事务、角色和引用语义、输出门、恢复判据均未运行。不得把静态 PASS 改成目标行为 PASS。

## 已排除
本次没有证据证明原包共享副本已经内容分叉；原包各共享协议本来一致，修订针对未来漂移与现有内部冲突。没有证据证明模型总体性能，只针对用户描述的失败场景。
