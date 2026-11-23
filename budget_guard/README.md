# CRM SRE — 离线预算控制原型（绝不发送真实模型请求）

> **当前状态：OFFLINE_PROTO_ONLY / TOKEN_COST_HARD_CAP=BLOCKED / MAC_0B=NOT_RUN / A=BLOCKED**
>
> 本目录与原有 `dsh/` 的配置/提示词包彼此独立。它并不是已安装到 Harness
> 0.2.2-rc.1 或 Agent Teams 0.1.30 的插件，更不是已经证明的最终发送拦截器。

## 为什么独立实现

DSH 没有自有 JavaScript 发送引擎。修改 persona、patch YAML、提示词自检
均不能保证所有模型、辅助、重试请求经同一本账。这个目录实现一个可审查的
**单出口预算账本和本地合成协议接收器**，以便先在 GitHub CI 验证正确的
并发/崩溃语义，再决定真实 SDK 或代理适配的位置。

## 已实现并可离线测试

- Python 3.11+ 标准库，持久 SQLite WAL、`BEGIN IMMEDIATE`、`synchronous=FULL`，
  每次接收请求先原子预留请求次数、合成 token 数和合成费用。
- `RESERVED → DISPATCHING → CONFIRMED / UNKNOWN`，写入 `DISPATCHING`
  成功提交**之后**才可触达本地合成接收器。
- 任何编号已被使用，均不重放；`UNKNOWN`、崩溃前的未完成预留占额且不自动退款。
  **任何 UNKNOWN 将冻结整个阶段**，不能在尚未人工核对账务前换一个请求 ID 继续发送。同一个账本被团长、成员和辅助角色共享。
- 仅绑定 `127.0.0.1`，要求私有 bearer token；OpenAI
  `POST /v1/chat/completions` **仅接受文本、非 streaming 子集**。
  不支持的字段、模型、路由一律拒绝，绝不静默退回供应商原直连。
- 合成 receiver 能模拟 429、timeout、disconnect、broken-stream 与账本写入故障。
  它不创建供应商连接；收件计数可与账本事件逐条关联。
- 安全审计只保存 SHA256、身份相关字段和整数预留数，不保存用户提示词正文、
  供应商凭据或完整响应。
- POSIX 宿主启动入口以 `flock` 锁住实例，防止两个入口同时恢复同一账本；
  不使用 `/private/tmp` 持久化，不支持 symlink 状态路径。

## 单机合成启动（只读仔细核对后）

先人工创建 SSD 私有目录和 0600 bearer 文件，不把令牌提交到 GitHub。
本命令**不是运行 Harness，也不是对阶段 A 的批准**。

```bash
mkdir -m 700 -p /Volumes/WorkSSD/Archives/claude-tests/budget-offline-0b
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' \
  > /Volumes/WorkSSD/Archives/claude-tests/budget-offline-0b/token
chmod 600 /Volumes/WorkSSD/Archives/claude-tests/budget-offline-0b/token
python3 -m budget_guard serve \
  --policy budget_guard/policy.synthetic.json \
  --ledger /Volumes/WorkSSD/Archives/claude-tests/budget-offline-0b/ledger.sqlite3 \
  --token-file /Volumes/WorkSSD/Archives/claude-tests/budget-offline-0b/token \
  --port 43183
```

上述 CLI 永远只提供 synthetic responder。不接受任何真实上游地址、
代理密钥、URL 或 HTTPS 转发配置。试图把它当成生产网关会被明确视为
**阻断**，而非按最小功能“自动升级”到真实请求。

## 本地测试（不启动 Harness）

```bash
python3 -m pytest tests/test_budget_guard.py -q -ra
python3 -m pytest tests/ tools/oncall/ -q -ra
python3 tools/check_dsh.py
python3 tools/validate_bundle.py --check-only
python3 tools/build_bundle.py
git diff --check
git diff --exit-code
```

将 sqlite 和 token 放在源码仓库外。测试默认使用 pytest 的隔离临时文件，
只触发本机回环 socket，没有远端供应商网络调用。

## 严格的局限

1. **真实供应商预算门控尚未接入。** Harness 的 `llm/stream` waterfall
   可作为早拒绝和关联层，但不是最终已冻结的 SDK 请求。
   此版本没有实现最终序列化请求绑定、全路由拦截、可信 SDK 适配或最终发送；
   `X-CRM-SRE-Role` / request ID 也只是本地合成关联字段，并非可信宿主证明。
2. **合成输入 token 预留算法**为 `4 * HTTP body bytes + 256`，
   仅测试账本机制，绝不是 GLM 供应商计费上界；合成 output 仅按声明的
   `max_tokens` / `max_completion_tokens` 预留，未涵盖实际 reasoning
   及隐藏 token。价目表字段仅用于测试预算算术，无账户价格认证、
   cache/multimodal/舍入/其他费用证明。
3. **OS 网络边界未在 GitHub CI 得到证明。** HTTP 接收器本身没有供应商
   发送代码不等于未来整个 Harness 进程树无外连。需要 Mac 分别验证
   IPv4/IPv6、DNS、代理、子进程、继承 FD 和 fallback 旁路。
4. **精确一次发送不等于提供商精确一次计费。** 账本只保证同一 ID
   不被本代理再次派发，不能阻止上游在未知状态内部重放，也不能保证
   网络传输/计费恰好一次。凡 UNKNOWN 均继续占额，等人工独立对账。
5. **当前只支持单机受信磁盘和本机 POSIX 文件锁。** 不适用于 NFS、
   不可信本地同用户进程或 Windows 直接验收。
6. 尚未支持流式 SSE、多模态、tool-calling 的最终协议适配，也没有可
   自动安装的 Harness 插件。不能把本地合成 receiver 的 PASS 写成
   T04c/T05/T06 或正式 TOKEN_COST_HARD_CAP PASS。

## 下一开发门

另建最小宿主适配器，要求有公开、可复核的最终请求捕获点：
`session/model/request_id/payload hash/route/output-effective-cap`；
并证明团长、全部成员、辅助请求、恢复重试和 fallback 都强制走该出口。
出站限制必须保证无法旁路。随后引入实际 tokenizer/价格保守边界、
SSE 与工具调用支持，在新 SHA 上重复离线与 Mac 零供应商 0B，
才能**申请**独立阶段 A 批准。

这份实施不修改现有 DSH prompt，不变更模型或运行版本，
不改变生产只读权限。
