# 验证状态 · 2.7.0

本文只描述本地源码交付的验收范围；最终实际执行结果与原始日志在随交付的验证报告中。历史 2.5.0 报告存于 docs/history/VALIDATION-2.5.0.md，不是本次结果。

STATIC（工作树实际结果）：Python 3.12.10；完整 pytest 为 210 passed、0 failed、5 skipped，另有 1094 个子测试通过（不与方法数相加）。静态校验 1794/1794，嵌入非递归离线测试 132 项通过。新增 `tests/test_read_only_boundary.py` 16 项正负例：全 16 个 Agent/Skill 入口声明只读边界、8 个人工入口无残留 blanket ban、边界标记缺失被拒、把只读放宽写进 MANAGED_HARNESS 被拒、契约 `read_only_boundary` 缺项/越权/泄漏/生产写边界变更均被拒、数据外泄原语（云元数据端点、POST -d @、--data-binary @、--upload-file、$(cat，凭据文件、curlrc 隐式注入）只允许出现在禁止句中不得作为可执行示例、空文档不得通过。来源审计对实际上传版核验 26 个受保护文件，原四份闭合 Schema 与所有原测试源保持；`policies/runtime-contract.json` 与 `.codebuddy-plugin/plugin.json` 的本次修订走既有 `workbuddy-allowed-changes.json` 审查通道并更新指纹与理由。
两次构建、整个临时发行树、反向 glob/rglob/iterdir 与不同哈希种子的校验报告均一致。故意删除 sorted 后退出 1，检出排序守卫；对 ZIP 实际制造乱序、重复、缺失、路径穿越、内容修改的负例均拒绝。配置保留、预检失败无改动、提交中途异常回滚与重新构建均已运行通过。
最终交付还需从发行 ZIP 解压后复验；以随交付的 TEST_REPORT.md 与 test-results.json 中实际命令/退出码为准，工作树结果不替代宿主验收。
MODEL_BEHAVIOR：NOT_RUN；本环境未调用真实模型来运行事故场景。只读边界是否被模型正确执行、是否仍残留自然语言矛盾，未验证。
WORKBUDDY_HOST：NOT_RUN；本环境没有 WorkBuddy 客户端会话，未验证导入、权限、真实派生、续轮或失败回执，也未验证公开读取的真实执行。本包未修改任何本机权限或缓存。
CUSTOM_MANAGED_HARNESS：NOT_IMPLEMENTED。
PRODUCTION_READ_EXECUTION：NOT_IMPLEMENTED；本次修订不新增生产只读通道，无真实配置时须写明未执行。

独立在未修复的原上传版运行基线得到 105 passed、2 failed（确定性集成的两个子检查），原因是原始生成产物与源码重建不一致。本次必须重建并验证，不能复用历史 PASS。

原 B/T/J/TT 及新 WB 行为 JSON 是待执行规格，不是运行日志；其中不得填伪造 PASS。静态标记检查只能捕获列明的结构冲突，不能证明任意自然语言不会矛盾或模型必定遵守。文件哈希验证完整性，不证明来源认证、事实正确或生产操作安全。
