适用范围：本文的领域方法和证据纪律可用于三模式；宿主状态机、编号账本、闭合 Schema 字段、强制 JSON、接纳与发布门仅用于 MANAGED_HARNESS。原生/兼容不执行这些托管要求、不据此升级模式或索取控制字段，以当前 Agent/Skill 的互斥模式契约为准。

# OODA 与序数化证据更新
版本：2.5.0。仅为托管契约与人工阅读参考，不是已实现的 Harness，也不是可校准的概率计算。

## 用途与边界
OODA 是同一任务内的 Observe、Orient、Decide、Act 判断顺序，不等于 P0–P7。Observe 看 evidence_delta；Orient 更新候选；Decide 选最能区分候选的材料；Act 仅提议请求、路由、评审需求或交接，不执行。模型不得改变 phase、状态、先验或 ooda_cycle_id。

## 证据价值表
逐条回答：候选为真时该证据是否常见；候选为假时是否仍常见。后者必须有授权基线、正常窗口或相邻对象依据；无依据写 UNKNOWN，不凭直觉。
| expected_if_true | expected_if_false | 允许 effect |
|---|---|---|
| 任一 UNKNOWN | 任一 UNKNOWN | UNKNOWN；任一为未知即适用 |
| COMMON | COMMON | NEUTRAL |
| UNCOMMON | COMMON | WEAKENS / STRONGLY_WEAKENS |
| COMMON | UNCOMMON | SUPPORTS / STRONGLY_SUPPORTS |
| UNCOMMON | UNCOMMON | UNKNOWN；异常，需要重新判断 |
每项 evidence_effects 记录 evidence_ref、effect、上述两个判断和 reason。强弱仍是提议，不能因为多人复述同一 E 而提高支持强度。reason 说明授权对照与适用范围，不能把时间相关写成因果。

## 候选与方向
已有候选使用 current_candidates 中宿主分配的 H 编号；新候选用本输出唯一的 L 编号，接纳后才由宿主映射为 H 编号。posterior_direction 为 UP、DOWN、UNCHANGED 或 INDETERMINATE。
UP 须有 SUPPORTS 类，DOWN 须有 WEAKENS 类；只由本轮新证据触发，触发证据必须属于 evidence_delta.added 或 revised。旧 E 不跨轮重复推动。同一 E 的重复支持只计一次。delta 为空时只允许 UNCHANGED 或 INDETERMINATE；L 编号只能 INDETERMINATE。
支持类 E 必须同时列入 support_refs；削弱类 E 同时列入 counterevidence_refs。counterevidence_status=PRESENT 必须存在削弱类 effect 且反证引用非空；NOT_OBTAINED 不得出现削弱类 effect 或反证引用。失效证据先由宿主处理，不能仅因失效就伪造本轮新增支持。

## 合成示例
CPU 示例：故障窗口 CPU 80%，同节点历史高峰也常见 80%，且授权基线可比。对“CPU 饱和导致故障”这一候选，两种情况下此观察都常见，COMMON/COMMON，只能 NEUTRAL；只记录观察，不据此定根因。
JVM 示例：仅故障窗口出现大量 JVM 停顿，恢复后消失，相邻正常节点没有，且窗口、负载与对象可比。对“JVM 停顿参与请求延迟”的候选可提议 COMMON/UNCOMMON 与 SUPPORTS；更强 effect 须另有理由。仍需核查时间先后、共同原因和基线有效性；恢复成功不能倒推原始根因。

## 请求示例
验证候选 H01：请提供获准分享的同窗 JVM 停顿时间摘要与请求延迟摘要，只要可比窗口和匿名对象。if_positive：停顿先于延迟且正常对照无相同现象，则增加对 H01 的支持。if_negative：延迟在无停顿时仍同样出现，则削弱 H01，转查关键替代解释。information_gain：区分停顿相关等待与其他等待位置。只描述材料，不给采集命令。人工模式写候选名称，不自造编号。

## 宿主责任与停止事件
宿主从账本编译 evidence_delta，提供 current_candidates，唯一分配 H 编号，维护状态、先验与 ooda_cycle_id。空集合不等于上下文字段缺失。首轮先验 UNKNOWN；宿主按 reasoning 策略映射历史状态，不由模型填写。
NO_INFORMATION_GAIN：引用 limits.max_no_gain_completed_rounds，由宿主按真实完成回灌判断。BLOCKED：登记受阻，同一材料不重复请求，不增设提前交接权限。RECOVERY_ONLY：恢复与 RCA 分开记录。CONFIRMED：模型不得宣布，RCA CONFIRMED 须人工或可核规则。
宿主检查引用存在性、事故与授权范围、L 编号唯一性、target 指向、效果引用归属及本轮触发依据，不能只信 Schema。

## 局限
expected_* 仍由模型判断，可能出错；COMMON/UNCOMMON/UNKNOWN 三档无法区分“都罕见但程度不同”。direction 只是提议，不是后验概率或自动状态迁移。Schema 验证格式与条件组合，不证明基线真实、证据独立或因果成立。
