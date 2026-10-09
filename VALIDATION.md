# 验证状态 · 2.7.0 实验前开发工作区（PRE-GATE）

本文只描述本地源码交付的验收范围；最终实际执行结果与原始日志在随交付的验证报告中。历史 2.5.0 报告存于 docs/history/VALIDATION-2.5.0.md，不是本次结果。当前状态为 PRE-GATE：Slice 1（运行时剥离 MANAGED_HARNESS）+ Slice 2（名册/证据编号/派单/REFUTE）已落地，宿主实测未执行。

STATIC（GitHub 克隆 `fix/pre-gate-v3.3.2` 分支实测，2026-10-09，基于 origin/main 453dafa）：Windows + Python 3.13.14（.workbuddy 托管 venv）+ git 2.55.0.windows.3。完整 pytest 为 310 passed、0 failed、6 skipped（平台间 skip 分布不同，Mac 复核 453dafa：315 passed / 1 skipped；另有 1209 subtests passed）。静态校验 1809/1809（validate_bundle，PASS_STATIC_ONLY，root lock 集 503），check_workbuddy pass=true，check_thinking_tools 251 项全部 passed，check_determinism pass=true。V2 复现结论：0017dec 描述的"git 2.55 吞钩子退出码"说法不成立——最小仓库与本地 clone 实测中，PortableGit 2.55.0.windows.3 与系统 Git 2.49.0.windows.1 都正确传播 pre-commit 非零退出并保持 HEAD 不变；钩子以 100755 入库，Windows 下需 `python tools/install_git_hooks.py` 设 core.hooksPath 方生效。v3.3.1 变更：放开自主联网检索（common.md 新增条目 + 8 个 manual 源边界段同步，底线为不外发用户信息）；runtime-contract.json 的 public_read_execution 改 AUTHORIZED_PUBLIC_READ_AND_SEARCH_NO_USER_DATA_EGRESS（production_read_execution / production_write 一条不动，经 workbuddy-allowed-changes 通道重算 revised_sha256 并由 check_thinking_tools 的 reviewed_change 校验通过）；值班机 WB 规则细化（WB09 拆 WB09H、新增 WB15 检索不外发）。新增测试覆盖：test_runtime_render（7 项：MANAGED 块零残留/运行时 check_prompt/重引入拒绝/占位符无残留/源保留/render_full 源检查/剥离逐字验证）、test_native_collab（24 项：名册三方一致性正负例 + 文案渲染检查 + 负例参数化 runtime/render_full 双跑 + 成员约定段逐字一致性）、test_probe_build（5 项：探测版本派生/暗号措辞/8 zip 全量重打包含团长且 zip 内 VERSION==probe_version/仓库外 --out/主目录零改动）、test_comparison_build（6 项：N/S 差异集/版本派生/LOAD 行位置/S 臂收束文本/F4 措辞/缺 NATIVE_LEAD 负例）、test_git_hooks（14 项：暂存区构建门拒绝不修复/部分暂存负例/工作区不变/干净放行/钩子 100755 入库/真实 git commit 拒绝 stale 树/钩子用暂存区脚本）、test_knowledge_docs（7 项：含 docs/11↔docs/12 术语一致性、docs/12 N 组同轮定义、docs/12 值班机安全规则、VALIDATION.md 数字与 static-checks.json 一致性、自主联网检索规则在 common.md 与 8 个 manual 源就位 + public_read_execution 取值锁定 + production 红线锁定 + WB09H/WB15 就位）。运行时产物 MANAGED_HARNESS 段占比 = 0%；Agent↔SKILL.md 重复率 74%–98.6%（团长因名册只注 Agent 侧而降幅最大）。measure_prompts.py routing_table_present=True。
两次构建、整个临时发行树、反向 glob/rglob/iterdir 与不同哈希种子的校验报告均一致。故意删除 sorted 后退出 1，检出排序守卫；对 ZIP 实际制造乱序、重复、缺失、路径穿越、内容修改的负例均拒绝。配置保留、预检失败无改动、提交中途异常回滚与重新构建均已运行通过。
最终交付还需从发行 ZIP 解压后复验；以随交付的 TEST_REPORT.md 与 test-results.json 中实际命令/退出码为准，工作树结果不替代宿主验收。
MODEL_BEHAVIOR：NOT_RUN；本环境未调用真实模型来运行事故场景。只读边界是否被模型正确执行、是否仍残留自然语言矛盾，未验证。
WORKBUDDY_HOST：NOT_RUN；本环境没有 WorkBuddy 客户端会话，未验证导入、权限、真实派生、续轮或失败回执，也未验证公开读取的真实执行。本包未修改任何本机权限或缓存。
CUSTOM_MANAGED_HARNESS：NOT_IMPLEMENTED。
PRODUCTION_READ_EXECUTION：NOT_IMPLEMENTED；本次修订不新增生产只读通道，无真实配置时须写明未执行。

独立在未修复的原上传版运行基线得到 105 passed、2 failed（确定性集成的两个子检查），原因是原始生成产物与源码重建不一致。本次必须重建并验证，不能复用历史 PASS。

原 B/T/J/TT 及新 WB 行为 JSON 是待执行规格，不是运行日志；其中不得填伪造 PASS。静态标记检查只能捕获列明的结构冲突，不能证明任意自然语言不会矛盾或模型必定遵守。文件哈希验证完整性，不证明来源认证、事实正确或生产操作安全。
