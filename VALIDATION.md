# 验证状态 · 2.7.0 实验前开发工作区（PRE-GATE）

本文只描述本地源码交付的验收范围；最终实际执行结果与原始日志在随交付的验证报告中。历史 2.5.0 报告存于 docs/history/VALIDATION-2.5.0.md，不是本次结果。当前状态为 PRE-GATE：Slice 1（运行时剥离 MANAGED_HARNESS）+ Slice 2（名册/证据编号/派单/REFUTE）已落地，宿主实测未执行。

STATIC（开发 clone 实际结果）：Python 3.13.12；完整 pytest 为 244 passed、0 failed、5 skipped。静态校验 1801/1801（validate_bundle），check_workbuddy pass=true，check_thinking_tools 0 误判，check_determinism pass=true。新增测试覆盖：test_runtime_render（7 项：MANAGED 块零残留/运行时 check_prompt/重引入拒绝/占位符无残留/源保留/render_full 源检查/剥离逐字验证）、test_native_collab（22 项：名册三方一致性正负例 + 文案渲染检查 + 负例参数化 runtime/render_full 双跑）。运行时产物 MANAGED_HARNESS 段占比 = 0%；Agent↔SKILL.md 重复率 74%–98.6%（团长因名册只注 Agent 侧而降幅最大）。measure_prompts.py routing_table_present=True。
两次构建、整个临时发行树、反向 glob/rglob/iterdir 与不同哈希种子的校验报告均一致。故意删除 sorted 后退出 1，检出排序守卫；对 ZIP 实际制造乱序、重复、缺失、路径穿越、内容修改的负例均拒绝。配置保留、预检失败无改动、提交中途异常回滚与重新构建均已运行通过。
最终交付还需从发行 ZIP 解压后复验；以随交付的 TEST_REPORT.md 与 test-results.json 中实际命令/退出码为准，工作树结果不替代宿主验收。
MODEL_BEHAVIOR：NOT_RUN；本环境未调用真实模型来运行事故场景。只读边界是否被模型正确执行、是否仍残留自然语言矛盾，未验证。
WORKBUDDY_HOST：NOT_RUN；本环境没有 WorkBuddy 客户端会话，未验证导入、权限、真实派生、续轮或失败回执，也未验证公开读取的真实执行。本包未修改任何本机权限或缓存。
CUSTOM_MANAGED_HARNESS：NOT_IMPLEMENTED。
PRODUCTION_READ_EXECUTION：NOT_IMPLEMENTED；本次修订不新增生产只读通道，无真实配置时须写明未执行。

独立在未修复的原上传版运行基线得到 105 passed、2 failed（确定性集成的两个子检查），原因是原始生成产物与源码重建不一致。本次必须重建并验证，不能复用历史 PASS。

原 B/T/J/TT 及新 WB 行为 JSON 是待执行规格，不是运行日志；其中不得填伪造 PASS。静态标记检查只能捕获列明的结构冲突，不能证明任意自然语言不会矛盾或模型必定遵守。文件哈希验证完整性，不证明来源认证、事实正确或生产操作安全。
