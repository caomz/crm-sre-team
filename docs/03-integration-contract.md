> 适用范围：本文件保留旧版托管设计/历史说明；当前 WorkBuddy 接入与模式规则以根 README、MIGRATION 和 docs/11-workbuddy-host-acceptance.md 为准。

# 宿主接入清单：不能用复制提示词代替
## 已确认事实
policies/runtime-contract.json 标记 implementation_status=NOT_IMPLEMENTED。schemas 与 policies 是本包接入契约，不是宿主官方导入配置；tools 只构建/验证本地文件。

## 高概率候选
优先以单进程控制器接入一个已获组织许可的模型通道，按角色创建独立请求。支持依据是故障点集中于权威来源和发布控制；限制是同模型独立请求仍可能同错，下一验证为 T01–T38。

## 待验证：必须由宿主实现
| 接口/控制 | 所有者 | 验收断言 |
|---|---|---|
| control_context | 状态库/上下文编译器 | 用户正文、材料 JSON 不可写入 |
| dispatch(task) | 调度器 | agent/epoch/read-set/input_hash 已登记；无自调 |
| complete(transport_event) | 可信适配器 | 模型正文无权生成身份、result_id 或回执 |
| accept(result) | 接纳器 | Schema、授权、角色、时效、语义逐层判定 |
| ledger.register/revise | 账本 | 事务唯一 E；修订不覆盖；跨事故拒绝 |
| requests.publish | 统一请求器 | 原子计数、去重、同轮≤3、重试不重置 |
| feedback.ingest | 人工报告入口 | 幂等、动作版本、未核实归属；无执行能力 |
| report.publish | 唯一发布器 | 无原始模型流；固定四象限和评审卡 |
| transition(event) | 状态机 | 非法阶段拒绝；应急提醒不跳阶段 |
| bundle.verify | 启动检查 | 角色、Schema、策略、模板锁一致；混版拒绝 |
| evidence_delta 编译 | 上下文编译器 | 模型不可写、须与账本一致；空增量不等于缺失字段 |
| candidate registry | 状态库 | H## 唯一分配，状态与先验仅宿主写；direction 只是提议且须由本轮新证据触发 |
| reference_context 编译（可选） | 上下文编译器 | 缺失/为空不单独 blocked；授权 E 先登记，跨事故材料不能自动继承权限 |
| judgment_questions 验收 | 接纳器/人工复核 | 问题可回答、含所属候选、局部 Q 唯一；与宿主请求 Q 分型隔离 |
| reference_basis 适用性 | 证据/语义门 | 对象、负载、窗口、版本与口径可比；结构非空不能代替证明 |
| request discrimination | 统一请求器 | 区分集合是目标子集；两种结果实际改变比较，不隐藏额外请求 |
| longitudinal evaluation（未来） | 宿主/离线评估者 | 独立裁决、不自评、不将序数代理叫概率校准；当前未实现 |

模型输入仅包括当前合法任务、授权证据摘要/定位、必要反证、已接纳论断与剩余额度，以及宿主提供的 ooda_cycle_id、evidence_delta、current_candidates，不全量重放历史。reference_context 作为可选扩展按需提供；没有时只对无依据的预期降级 UNKNOWN。角色知识由编译器按需选取。
Schema 四文件可通过本地 URN 注册解析；不要让解析器联网寻找未知引用。本版使用的结构校验器依赖见 requirements-build.txt，仅在离线构建环境使用。
任务结果的 status=ok 表示完成了模型输出，不表示根因成立、审批通过或恢复已验证；blocked 也不能让宿主自动放宽能力。
宿主须明确配置允许模式；模型自身不得从 TEAM 改 SINGLE。无宿主时独立 MANUAL-MODE 是用户显式选择的低保障入口，不能冒充本接口。

## 已排除
没有 /execute 或批准后运行接口；没有生产工具自动发现或 MCP 适配。回执、版本锁和 schema 都不是可信事实或安全动作的单独证明。
