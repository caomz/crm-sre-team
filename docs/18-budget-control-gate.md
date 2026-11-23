# Budget Gate 0B — GitHub 代码交接与验收隔离

## 固定背景

- 源仓库：`caomz/crm-sre-team`。
- 审查基线：`64ad6aef7cfc89cb834917e7594dc0be7801d91e`。
- 与 `aeea8307bd50b02ce091d881f57997dd56adbd17` 的 T04c/T05/T06
  修复线分叉，**没有在本预算分支自动合并**。
- Harness 0.2.2-rc.1、Agent Teams 0.1.30、glm-5.3-flash
  的原有组合保持不变；GitHub 合成测试未启动其中任何一个。
- Mac 报告当前零 0B 实例、零真实供应商发送、零 staged 批准；
  该数据仅为用户提供的执行报告，并未由 GitHub 端独立测量。

## 架构所有权

`dsh/` 不自带运行时。硬预算的控制对象是 **宿主最终请求到供应商的
每一笔不可绕过的网络发送**，不是 DSH 提示词的配额文字。

当前 `budget_guard/` 属于**独立离线原型**：

```
测试客户端（合成请求）
  -> 127.0.0.1 本地 Bearer 检查
  -> OpenAI text-only 请求形状检查
  -> SQLite BEGIN IMMEDIATE 原子预留（次数 / 合成 tokens / 合成费用）
  -> COMMIT 持久化 RESERVED
  -> COMMIT DISPATCHING（唯一派发权）
  -> SyntheticReceiver（仅内存；不会出站）
  -> CONFIRMED 或 UNKNOWN（均不自动返还）
```

禁止把 `llm/stream` hook 直接视为最终请求锁；它可以早拒绝和传递关联，
但真实 pi-ai adapter / SDK 路由、重试/恢复、辅助请求及 fallback 的完整覆盖
仍缺硬证据。未形成可信宿主适配、最终 payload hash 及 OS 出站封锁前，
任何消费者不得把本代理从 synthetic 切到 live。

## 代码与测试分层

| 项目 | 验证程度 | 说明 |
|---|---|---|
| SQLite 持久事务与 35/36 并发争用 | OFFLINE_TEST | 受信本地文件系统 |
| 同一 request_id 唯一派发、重启 UNKNOWN 不退款 | OFFLINE_TEST | 不宣称供应商账单 exactly once |
| 429/超时/断流与写入失败的本地合成异常 | OFFLINE_TEST | 无任何供应商真实行为 |
| 文本 OpenAI-shaped 合成接收器 | OFFLINE_TEST | 不支持 streaming/tools/multimodal |
| OS 网络无旁路及唯一最终发送拦截 | NOT_VERIFIED | 必须在 Mac 主机独立证明 |
| 真实 provider 最终 token 上限和价格 | BLOCKED | 模型路由/输出上限/账单缺证据 |
| T04c/T05/T06/T02/T03 新 SHA Harness | NOT_RUN | 另一个独立验收阶段 |
| Mac 人工接受 / Windows VERIFY | BLOCKED | 不可跨用旧 SHA 结论 |

## 下一轮实施最优先检查

在 Mac 上不启动 Harness 的只读预检，应先判定：

1. 被测二进制载体实际读取的模型配置，能否将所有供应商请求强制路由到
   本机代理（而不是在代理失败时回退直连）？
2. 原始 request body 在哪个最终 SDK 入口完成序列化？是否包含隐藏重试、
   tool call、stream、辅助 LLM 以及不同模型 adapter？
3. 可否在没有供应商真实流量时以具体 socket 拒绝回执证明整个宿主进程树
   被 OS 规则阻断外连？回环是否仍可工作？
4. 如何取得**可信**输出上限与保守计费上界？价格版本/账户折扣/额外收费
   是否可验证？无法取得时保持 `TOKEN_COST_HARD_CAP=BLOCKED`。

这些是改变后续架构决定的信息；没有就不应启动 0B Harness，也不得批准 A。

## 精确交接与停止线

本分支仅通过 GitHub Draft PR 分发。Mac 新建独立 worktree、采用**完整
40 位 SHA**；不要复用 T04c/T05/T06 已运行的 profile 或接受旧日志
作为新 SHA 的证据。原先 `mac_tested_commit=f4729df...` 不改变。

需先在 GitHub CI 达到 `tests/test_budget_guard.py` 与既有全量测试、
`tools/check_dsh.py`、`tools/validate_bundle.py --check-only`、
`tools/build_bundle.py` 和零 diff PASS；但这仅说明离线原型可交接，
不是 Mac 0B 或 A 的放行凭据。

停机/回退：任何测试意外形成到真实供应商的连接尝试、持久账本丢失、
对请求 ID 重放、未经过持久预留即触达合成 receiver、CI manifest/lock
不一致、或与 DSH 旧产物产生无关 diff，都停止并保留证据。
