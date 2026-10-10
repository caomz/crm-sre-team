## v3.6.2 / 2.8.0-rc2 · 未部署前工具修订（2026-10-10）

在 v3.6.1 的 116 个未提交修改之上修复二进制临时写入与执行 agent 模式选择两项问题。基线仍为 35d9193fa1b71fd9cd05c151e774fd6338b0e4e2，分支 codex/v3.6。动手前保存完整 git diff --binary，SHA256 a16fb59b9e2403c753ebfe027592b6db47052f8bcc47f221132c3538c569117c，与交接的 v3.6.1 补丁逐字节相同。仓库内仅手工修改 tools/sync_git.py、tests/test_git_sync.py、CHANGELOG.md 和本文；生成内容仅由工具更新。版本、提示词、权限契约、评分输入及判据保持不变。

macOS 26.4.1 arm64 + Python 3.14.7，使用既有 /private/tmp/crm-v341-venv；检查显式设置 PATH=/private/tmp/crm-v341-venv/bin:$PATH 与 TMPDIR=/private/tmp，未安装依赖。全量 pytest -q -rs 为 392 passed、0 failed、1 skipped、1504 subtests passed（50.35 秒），1 条既有重复 ZIP 条目负例 UserWarning。唯一 skip 为真实 Windows junction（POSIX: no junction concept）。本轮新增 3 个测试方法均无平台跳过，14 个子用例全部执行；全量检查显式用 CRM_GATE_GOLD_DIR 指向本轮交付评分副本，评分承诺和内容边界测试实际执行。

回归先在未修实现上实跑：捕获到 8 个失败子用例（两个打开标志分支及六个写损坏分支），日志保留；修复后定向检查 3 passed / 14 subtests passed。实际临时字节摘要在替换前核对，不依赖写入返回值或事后账本；不一致抛 SyncError，原目标或目标不存在状态保持，临时文件保留。成功路径对空数据、混合换行、全部 256 种字节执行逐字节断言。v3.6.1 的权限及 umask 断言未修改。

静态校验 1816/1816（PASS_STATIC_ONLY、errors=[]），137 offline unit tests，root lock 508；check_workbuddy pass=true/errors=[]，check_thinking_tools 251/251（PASS_STATIC_ONLY）。补写本节与 CHANGELOG 实测记录后重建并复核静态一致性，最终重建零差异、发布 ZIP 与解包逐字节检查的数字及 SHA256 记录在 /private/tmp/crm-v362-handoff/Mac记录/verification.json 和各项日志；包自身 SHA256 只记录在仓库外交付材料。

Runbook 改为两个拒绝占位值的显式赋值，由执行 agent 按对话批准内容填写，回显后等待用户确认再继续。5B、5C 完整代码及生成全新演练根的逻辑与 v3.6.1 逐字节一致，三处 MAIN_SHA 保留。Mac 文本核对 24/24；首轮检查因 5D 赋值说明的措辞未匹配而报 1 项失败，调整说明后复核通过，日志保留。这些代码只在 Mac 上人工审查过，未在 PS 5.1 实测；静态检查不替代 Windows、PS 5.1 故障演练或 WorkBuddy 宿主验收。生产写仍只产人工评审需求，本轮未提交、推送或部署。

## v3.6.1 / 2.8.0-rc2 · 未部署前工具修订（2026-10-10）

在 v3.6 的 116 个未提交修改之上修复独立复核的四项问题，版本保持 2.8.0-rc2。基线仍为 35d9193fa1b71fd9cd05c151e774fd6338b0e4e2，分支 codex/v3.6。开始前保存完整二进制补丁，SHA256 为 f2545a58f9e9d89dac20128a202d63a3a372682ba82d0dce60df36b2d1a2b0e2，与持久 v3.6 交付一致。只手工修改 tools/sync_git.py、tests/test_git_sync.py、tests/test_v35_regressions.py 及本次 CHANGELOG/VALIDATION 记录；生成文件仅由构建器/校验器写入，仓库外另修 P1 值班机说明。

macOS + Python 3.14.7，使用既有 /private/tmp/crm-v341-venv，所有检查显式设置 PATH 与 TMPDIR=/private/tmp。完整 pytest 389 passed、0 failed、1 skipped、1490 subtests passed（51.01 秒），1 条既有重复 ZIP 条目负例 UserWarning。唯一 skip 为真实 Windows junction（POSIX: no junction concept）。11 个新增测试方法覆盖原有 0755/0644、读写位保留、新文件 umask、远端仅改 100755 后再规划收敛、移除执行位及失败回滚，JSON bool/int/float 与嵌套比较、单侧变更/非对象根、暂存冲突保护、评分目录环境变量和文档默认值。POSIX 权限专属用例在 Windows 明确 skip，因为 Windows 不提供对应执行位/umask 语义。

静态校验 1816/1816（PASS_STATIC_ONLY、errors=[]），137 offline unit tests，root lock 508；check_workbuddy pass=true/errors=[]，check_thinking_tools 251/251（PASS_STATIC_ONLY）。manifest 仍为排序无重复的 517 项。最终重建零差异、发布与解包 517 文件逐字节核验、评分目录显式覆盖检查和 ZIP SHA256，以仓库外 Mac记录/verification.json 及各项日志为准；ZIP 自身哈希不写入载荷。

首轮定向检查的锁未重建失败、全量检查的新测试夹具受宿主 umask 影响失败，以及后续再次规划时合成仓库遗漏 reports/ 排除的失败日志均保留。补齐夹具初始权限和与项目一致的排除规则后，新修复定向检查 13 passed / 43 subtests passed，全量结果如上；未放宽旧断言。

评分材料 7 个文件与持久交付逐字节一致，6 项 SHA256 承诺匹配。P1 代码只在 Mac 上人工审查过，未在 PS 5.1 实测；REAL/DRILL 的七路径断言、故障恢复与客户端跳过条件须由值班机实测。Windows、WorkBuddy 加载/缓存/审计与关口仍待执行；本轮未提交、推送或部署。提示词与判定规则冻结不变，生产写仍仅产人工评审需求。

## v3.6 / 2.8.0-rc2 · Mac 修复端实测（2026-10-10）

基于 main=35d9193fa1b71fd9cd05c151e774fd6338b0e4e2，工作分支 codex/v3.6；首次关口前按 R-01/R-05 修订并重新冻结为 2.8.0-rc2。macOS + Python 3.14.7，使用既有 /private/tmp/crm-v341-venv，检查显式设置 PATH 与 TMPDIR=/private/tmp，未安装依赖。

最终完整 pytest 378 passed、0 failed、1 skipped、1463 subtests passed，1 条 ZIP 重复条目负例的 UserWarning；唯一 skip 仍为真实 Windows junction 测试（POSIX: no junction concept），Python 3.11 重解析点回退与不存在目标已由 Mac 元数据负例覆盖，Windows 实测待执行。test_version_consistency 单独重跑 5 passed；check_workbuddy pass=true/errors=[]；静态校验 1816/1816（PASS_STATIC_ONLY、errors=[]），137 offline unit tests、root lock 508，manifest 517。全量 pytest 前后 /private/tmp/crm-precommit.* 为 66→66，未新增、未处理既有目录。

R-02 真实提交故障注入覆盖重建前后 generated file/lock 的 hash-object、文件枚举和排序失败，确认 HEAD/暂存区/工作树不变；R-04/R-09 覆盖独占临时文件、固定名用户文件/链接、回滚未完成留备份，以及本地未提交修改/删除/未跟踪同名文件/暂存修改保护。R-08 覆盖空报告/错误 scope/零测试/不一致计数/ZIP 实际哈希；R-10 覆盖缺键与 null；R-11 覆盖禁止类别混合大小写。R-12 用精确审核哈希及重建完整历史字节哈希限定只有两行恒真断言被移除；未削弱其余断言。

公开/独立评分协议的硬规则逐字一致，评分协议承诺 e72cabce17dffa847213add19d7c0ccf93a47478ab9ac1c17b015d27df5340cf，案例答案及 routing-assertions 原字节保持。凭据/环境变量禁读覆盖所有任务与渲染入口，自主公开检索继续无需逐次审批，生产写操作只产人工评审需求。除 R-01/R-05 外不改提示词、案例和判据。

最终两次重建零差异、打包/解包校验、ZIP SHA256 和统一流水线的实际结果另留仓库外交付 FINDINGS.md 与日志，避免把外层包自身哈希写入载荷。Windows 10 值班机复核、PS 5.1 三种安装故障演练、WorkBuddy 加载/版本往返/工具审计/WB07/WB09H/18 次关口均待执行；Mac 未提交、推送或部署。

# 历史验证状态 · 2.8.0-rc1（PRE-GATE，以下保留原实测记录）

## v3.5.2 Mac 工具修订复核（2026-10-10）

基于 main=917b31e7cab94811235c0e9bc72f6de6eacffe4b，工作分支 codex/v3.5.2；插件版本仍为 2.8.0-rc1，属于值班机安装前的工具和测试修订。macOS + Python 3.14.7，使用已装 /private/tmp/crm-v341-venv，检查命令显式设置 PATH 与 TMPDIR=/private/tmp。完整 pytest 354 passed、0 failed、1 skipped、1312 subtests passed，1 条 ZIP 重复条目负例的 UserWarning；唯一 skip 为 tests/test_git_sync.py 的 POSIX: no junction concept。check_workbuddy pass=true/errors=[]；静态校验 1816/1816（validate_bundle PASS_STATIC_ONLY，errors=[]），root lock 集 508，137 offline unit tests。

test_git_hooks 共 22 项、18 个 subtests，覆盖真实提交成功和检查失败后自动清理、临时根内哨兵文件/目录/外部符号链接及快照内外部链接保护、6 类路径校验拒绝并保留退出码、清理失败只警告、INT/TERM 分别返回 130/143、临时根符号链接解析、Python 不可用时拒绝提交与 python/py -3 回退。各测试有独立 TMPDIR，结束检查无 crm-precommit.* 残留。另在同一合成仓库实跑一次成功提交（exit 0）和一次 stale 拒绝（exit 1），失败时 HEAD/暂存区不变，两个路径的独立临时根均为空。全量 pytest 前后 /private/tmp 下 crm-precommit.* 目录均为 66 个，未新增、未删除已有目录。

用户 2026-10-10 决定钩子仅自动清理自己创建的 mktemp 目录。清理前校验非空、目录且非符号链接、父目录与创建时解析出的临时根一致、crm-precommit.* 前缀；不通过只警告，清理失败不改变提交结果。v3.5.1 的快照人工管理说明已被本节取代。保留 B-01 与 Windows Git Bash/cygpath 兼容；Windows 10 值班机复核待执行。

最终重建、发行 ZIP 与解包复核以仓库外 /private/tmp/crm-v352-handoff/logs/ 的实际日志为准；生成报告仅由工具写出。提示词、权限契约、首次关口判定规则及版本未修改。WorkBuddy 加载、版本往返、工具审计与关口仍 NOT_RUN；生产写仅产人工评审需求。本轮未在真实克隆提交、推送或执行宿主/生产操作。

## v3.5.1 Mac 工具修订复核（2026-10-10）

基于 main=5fbe9e02214ca8f1b51fcb63c7fb8447a751da69，工作分支 codex/v3.5.1；插件版本保持 2.8.0-rc1，属于值班机安装前的工具和测试修订。macOS + Python 3.14.7，使用已装 /private/tmp/crm-v341-venv，检查命令显式设置 PATH 与 TMPDIR=/private/tmp。静态校验 1816/1816（validate_bundle PASS_STATIC_ONLY，errors=[]），root lock 集 508；完整 pytest 351 passed、0 failed、1 skipped、1296 subtests passed，1 条 ZIP 重复条目负例的 UserWarning；check_workbuddy pass=true/errors=[]。唯一 skip 为 tests/test_git_sync.py 的 POSIX: no junction concept，Windows 10 仍需实际执行该能力检查。

test_git_hooks 共 19 项、2 个 subtests，新增 Python 不可用时真实提交被拒且 HEAD/暂存区不变、无递归删除、保留暂存快照与意外残留、清理不掩盖构建失败、python/py -3 回退；安装器子进程使用 sys.executable。钩子只逐项删除两个固定元数据文件并尝试 rmdir 空目录，非空暂存快照保留并提示路径，需人工管理磁盘占用。

两次重建的精确发布文件哈希、发行 ZIP 的文件数/SHA256/validate_release --zip、解包静态复核与评分材料边界检查均记录在仓库外 crm-v351-handoff 的实际日志；生成报告只由工具更新。提示词、权限契约与首次关口判定规则保持冻结。Windows 10 值班机复核待执行；WorkBuddy 的加载、版本往返、工具审计与关口均 NOT_RUN。PowerShell 执行说明经过人工逐行自审，未在 PS 5.1 实测；本轮没有提交、推送或宿主/生产操作。生产写只产人工评审需求。

## v3.5 Mac 候选复核（2026-10-09）

基于 GitHub 9f06afd（v3.4.1），审查基线 main=3ae6769（v3.3.2）。macOS + Python 3.14.7，使用已装 /private/tmp/crm-v341-venv；命令显式设置 PATH 与 TMPDIR=/private/tmp。静态校验 1816/1816（validate_bundle PASS_STATIC_ONLY，errors=[]），root lock 集 508。完整 pytest 346 passed、0 failed、1 skipped、1294 subtests passed；唯一 skip 为 tests/test_git_sync.py 的 POSIX: no junction concept，1 条 UserWarning 为 ZIP 重复条目负例。check_workbuddy pass=true/errors=[]，check_thinking_tools 251/251。build_release 产出 517 文件，validate_release --zip pass=true/errors=[]（最终包与 SHA256 见仓库外交付记录）；最终重建零差异检查与 ZIP 解压后静态复核由交付命令实际执行并留日志。Windows 10 值班机复核待执行。新增 14 项 v3.5 回归覆盖干净 ZIP 首次校验与文档错数拒绝、构建输出防覆盖/越界/链接/Windows reparse point（含 Python 3.11 回退）/未申报文件、实际输入哈希、探测参数、参考条款冲突与关口路由/材料边界；不调用宿主或模型。

首轮 shell 实际命中了 Homebrew Python（缺 jsonschema），且 TMPDIR 未按会话约定生效；已改为显式环境后重跑，未安装依赖。静态校验先检出新增测试读取未注明 UTF-8，已修复；之后检出 VALIDATION 数字与新报告不一致，按工具实际结果同步，不手改报告、不删断言。测试期间补 manual-team-config 版本曾触发源码不变守卫，停止编辑并冻结后全量复跑通过；这次失败不当作最终通过结果。

2.6.1 的 2026-10-09 宿主观察见 docs/11；它不替代 2.8.0-rc1 的模型行为/导入/工具权限/缓存验收。WORKBUDDY_HOST（本候选）：NOT_RUN；MODEL_BEHAVIOR（本候选）：NOT_RUN；CUSTOM_MANAGED_HARNESS / PRODUCTION_READ_EXECUTION：NOT_IMPLEMENTED。只读边界不新增生产执行能力。

## 历史 v3.4.1 验证记录（2.7.0，保留）

本文只描述本地源码交付的验收范围；最终实际执行结果与原始日志在随交付的验证报告中。历史 2.5.0 报告存于 docs/history/VALIDATION-2.5.0.md，不是本次结果。当前状态为 PRE-GATE：Slice 1（运行时剥离 MANAGED_HARNESS）+ Slice 2（名册/证据编号/派单/REFUTE）已落地，宿主实测未执行。

STATIC（GitHub 克隆 `fix/host-observed-v3.4` 分支实测，2026-10-09）：v3.4.1 修改在 Mac 由 Codex 完成，基于 d653bac；运行环境为 macOS 26.4.1（arm64）+ Python 3.14.7（临时 venv）。完整 pytest 为 332 passed、0 failed、1 skipped、1270 subtests passed（另有 1 条 ZIP 重复条目负例触发的 UserWarning）。静态校验 1810/1810（validate_bundle，PASS_STATIC_ONLY，root lock 集 504），check_workbuddy pass=true、errors=[]，check_thinking_tools 251/251（PASS_STATIC_ONLY、errors=[]），check_determinism pass=true（构建产物、发行树与校验输出确定性均通过）。历史 V2 复现结论：0017dec 描述的"git 2.55 吞钩子退出码"说法不成立——最小仓库与本地 clone 实测中，PortableGit 2.55.0.windows.3 与系统 Git 2.49.0.windows.1 都正确传播 pre-commit 非零退出并保持 HEAD 不变；钩子以 100755 入库，Windows 下需 `python tools/install_git_hooks.py` 设 core.hooksPath 方生效。v3.3.1 变更：放开自主联网检索（common.md 新增条目 + 8 个 manual 源边界段同步，底线为不外发用户信息）；runtime-contract.json 的 public_read_execution 改 AUTHORIZED_PUBLIC_READ_AND_SEARCH_NO_USER_DATA_EGRESS（production_read_execution / production_write 一条不动，经 workbuddy-allowed-changes 通道重算 revised_sha256 并由 check_thinking_tools 的 reviewed_change 校验通过）；值班机 WB 规则细化（WB09 拆 WB09H、新增 WB15 检索不外发）。新增测试覆盖：test_runtime_render（7 项：MANAGED 块零残留/运行时 check_prompt/重引入拒绝/占位符无残留/源保留/render_full 源检查/剥离逐字验证）、test_native_collab（24 项：名册三方一致性正负例 + 文案渲染检查 + 负例参数化 runtime/render_full 双跑 + 成员约定段逐字一致性）、test_probe_build（6 项：探测版本派生/7 成员 C/D 暗号与 echo 措辞/8 zip 全量重打包且 zip 内 VERSION==probe_version 与暗号/仓库外 --out/主目录零改动/团长 LA/LS 同 suffix 暗号与 echo 指令及 lead_markers 内存和磁盘清单一致性）、test_host_observed（16 项：团长 SKILL.md 名册与 description 加载引导/成员派单前缀识别与 COMPAT 作用域/派单模板位于 NATIVE_LEAD 块/subagent_type 注册 ID 与 name 标签/禁止 bypassPermissions/日常不传 max_turns、仅用户明确限轮时传/宿主工具回退/团长与 7 成员两源模式块逐字一致性）、test_comparison_build（6 项：N/S 差异集/版本派生/LOAD 行位置/S 臂收束文本/F4 措辞/缺 NATIVE_LEAD 负例）、test_git_hooks（14 项：暂存区构建门拒绝不修复/部分暂存负例/工作区不变/干净放行/钩子 100755 入库/真实 git commit 拒绝 stale 树/钩子用暂存区脚本）、test_knowledge_docs（7 项：含 docs/11↔docs/12 术语一致性、docs/12 N 组同轮定义、docs/12 值班机安全规则、VALIDATION.md 数字与 static-checks.json 一致性、自主联网检索规则在 common.md 与 8 个 manual 源就位 + public_read_execution 取值锁定 + production 红线锁定 + WB09H/WB15 就位）。运行时产物 MANAGED_HARNESS 段占比 = 0%；Agent↔SKILL.md 重复率 98.59%–98.94%（measure_prompts.py 文件级字符测量，团长 98.94% 为最高；v3.4 起名册同时注入团长 Agent 正文与 SKILL.md）。measure_prompts.py routing_table_present=True。
两次构建、整个临时发行树、反向 glob/rglob/iterdir 与不同哈希种子的校验报告均一致。故意删除 sorted 后退出 1，检出排序守卫；对 ZIP 实际制造乱序、重复、缺失、路径穿越、内容修改的负例均拒绝。配置保留、预检失败无改动、提交中途异常回滚与重新构建均已运行通过。
本候选交付已安排发行 ZIP 解压后首轮静态复验；实际记录在仓库外交付日志，不能复用旧包结果；以随交付的 TEST_REPORT.md 与 test-results.json 中实际命令/退出码为准，工作树结果不替代宿主验收。
MODEL_BEHAVIOR：NOT_RUN；本环境未调用真实模型来运行事故场景。只读边界是否被模型正确执行、是否仍残留自然语言矛盾，未验证。
WORKBUDDY_HOST：NOT_RUN；本环境没有 WorkBuddy 客户端会话，未验证导入、权限、真实派生、续轮或失败回执，也未验证公开读取的真实执行。本包未修改任何本机权限或缓存。
CUSTOM_MANAGED_HARNESS：NOT_IMPLEMENTED。
PRODUCTION_READ_EXECUTION：NOT_IMPLEMENTED；本次修订不新增生产只读通道，无真实配置时须写明未执行。

独立在未修复的原上传版运行基线得到 105 passed、2 failed（确定性集成的两个子检查），原因是原始生成产物与源码重建不一致。本次必须重建并验证，不能复用历史 PASS。

原 B/T/J/TT 及新 WB 行为 JSON 是待执行规格，不是运行日志；其中不得填伪造 PASS。静态标记检查只能捕获列明的结构冲突，不能证明任意自然语言不会矛盾或模型必定遵守。文件哈希验证完整性，不证明来源认证、事实正确或生产操作安全。
