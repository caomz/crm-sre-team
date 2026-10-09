# 2.7.0 实验前开发工作区（PRE-GATE）

**状态：PRE-GATE。** Slice 1 + Slice 2 代码已落地（GitHub 克隆 `D:\python_code\github_my\crm-sre-team`，origin/main=7adefd8；开发 clone 的同名 tag 指向已被 7adefd8 链取代的旧链、仅存在于本地且未推送），宿主实测未执行（MODEL_BEHAVIOR=NOT_RUN、WORKBUDDY_HOST=NOT_RUN）。VERSION 仍为 2.7.0；PR-5 发布时才升 2.8.0。

**Slice 1 / PR-3a**（当前链等价 commit b3e3d8a；开发 clone 本地 tag pr-3a-strip-managed 指向被取代旧链）：运行时产物（agents/skills/individual-packages）剥离 MANAGED_HARNESS 段；源文件 policy-source/ 保留完整 common.md 含 MANAGED 段用于源级校验。build_bundle.strip_managed()；check_workbuddy.check_prompt(runtime=True) 禁止运行时含 MANAGED 块 + render_full() 源完整渲染跑全部旧规则；validate_bundle 契约比对改用剥离后 common.md。test_07/test_04/test_20/test_01/semantic_conflicts 迁移到 render_full；新增 test_runtime_render（7 checks）。运行时 MANAGED 占比 40.61%–50.99% → 0%。

**T5 / M15**（当前链等价 commit 0904538；开发 clone 本地 tag pr-1-min-collab-roster 指向被取代旧链）：新增 policy-source/routing-source.json（7 成员 route_when/do_not_route_when/expected_output/aliases，K8s 双条件+按需别名）；build_bundle.render_team_roster() + {{TEAM_ROSTER}} 注入团长 Agent 正文；check_workbuddy.routing_errors() 三方一致性（名册↔roles-source↔plugin.json）接入 run()；validate_bundle 占位符检查扩展到 {{TEAM_ROSTER}}；新增 test_native_collab（15 checks）。

**T6 / M13+M16**（当前链等价 commit da0563c；开发 clone 本地 tag pr-1-min-collab 指向被取代旧链）：common.md 证据编号统一（E###/E003:L120–L180/同源映射/成员不自行编号/缺依据记"成员未给出依据"）+ 共用成员约定节；团长派单五字段模板（随机标记分隔符/8000 字符封顶/截断补充计入成员额度）+ REFUTE 派发规则（领先候选定义/观察性成员路由/跳过记录/逐条写变化）；7 成员角色源+8 Skill 源 REFUTE 与配对逐字同步；负例参数化（runtime+render_full 双跑）；D18 旧四段名保留。

**T7 / TD**（当前链等价 commit 4a0fdbc；开发 clone 本地 tag t7-prereg 指向被取代旧链）：docs/12-native-vs-single-comparison.md 预注册锁定（18 planned run/INFRA_INVALID/SECURITY_FAIL/gold sheet 锚点/C1 更好+C2C3 非劣性/NOT_EVALUABLE）；MIGRATION 补 skill.zip 回同步暂停声明（R2-35）。新增 tools/make_comparison_build.py（S 构建实现：N/S 双包 + 自动字节差异验证）。docs/12 修正 18 次运行顺序（3 案例 × 6 次，逐案例序列冻结）+ 登记进 release-manifest + 本地路径泛化 + PASS/FAIL/BLOCKED 交付分支说明。

**关口前修复 fix/pre-gate-v3.2（2026-10-08，基于 origin/main=7adefd8）**：F1——探测与对照包加载核验暗号改为"逐行输出所有 PROBE-/LOAD- 行"（C/D 与 N/S 不再抢同一首行），docs/12 删除"整轮核验失败判 BLOCKED"，术语拆分 INFRA_BLOCKED（基础设施失败，按未通过发布、不作能力结论）与 CAPABILITY_BLOCKED（即 GATE_BLOCKED，仅宿主无 AgentTool 或所有写法派不中成员），第六节补"构建未加载"定义，文首补修订记录并重新冻结；F2——探测包版本派生 `<srcver>-probe.r<suffix>`（plugin.json/VERSION 同步）、成员 zip 按注入后 skills/ 重打包、probe-manifest 记 probe_version 与 lock_note、--out 仓库外不崩、docs/11 加缓存分流与团长转述规则；F3——C3 任何成员派发（含 REFUTE）计入约束，出现 REFUTE 直接记 routing failure；F4——build_bundle 新增 NATIVE_CLOSURE_TEXT 单一来源（产品形态措辞，无实验用语）；F5——对照工具重写：N/S 版本派生 `<srcver>-cmp-{n,s}.r<suffix>`、LOAD 行注入团长双文件（模式块外）、全部 8 个 zip 重打包、差异集自检（恰为团长双文件+版本文件+zip）通过否则非零退出；F6——pre-commit 改为 checkout-index 导出暂存树在临时目录构建 + OWNED 哈希对比，拒绝且不改写工作区，新增部分暂存负例/工作区不变/干净放行测试；F7——tools/README.md 恢复 sync_git.py 行并补 4 工具行，AGENTS.md 加同步前文件确认规则；F8——docs/11 K8s 派单改三写法（注册 ID/名册中文名/宿主显示名）+ 预注册判定表；F9——common.md NON_MANAGED 段删去托管账本半句，等义说明移入 MANAGED_HARNESS 段；F11——VALIDATION/CHANGELOG 数字与 tag 引用对齐当前链；F12——D16/D17 更名计划决策 PD-16/PD-17；F13——measure_prompts.py 输出路径仓库外不再崩溃。

**关口前修复 fix/host-observed-v3.4（2026-10-09，基于 origin/main=3ae6769）**：宿主机制观察落地——①团长 SKILL.md 自带名册（build_bundle.py 的 skill_text 增加 {{TEAM_ROSTER}} 替换；frontmatter description 加引导句"先加载本技能再作答"）；②成员识别派单（common.md WORKBUDDY_NATIVE 定义改为以"【团长派单】"识别；14 个成员源 NATIVE_MEMBER 块加派单标记识别句；COMPAT_MEMBER 块限定"只有用户直接打开本角色对话时才按本段回答"）；③派单参数写实（NATIVE_LEAD 块加 subagent_type 填注册 ID、name 只作标签、不用 bypassPermissions、限轮用 max_turns；名册说明同步）；④docs/11 新增"宿主机制观察（2026-10-09，值班机，2.6.1）"节、WB07 改为传 max_turns=1、暗号判读只认 PROBE-C/D、K8s 三写法补记实测结果、手动验证清单加项；⑤docs/12 修订记录加条目并重新冻结、开场消息第一句统一、加载核验明确 LOAD 行来自 SKILL.md；⑥新增 tests/test_host_observed.py（16 checks）。新增文件登记到 release-manifest.json。

**未执行**：宿主权限未修改、缓存未替换。WorkBuddy 实机导入、真实派生、REFUTE 回传、disallowedTools 生效、公开读取执行均未验证。skill.zip 市场回同步暂停至 PR-5。

# 2.7.0 只读查询误拦截解除版

在 2.6.1 基础上，按《解除只读查询误拦截的实施任务书》修改 canonical source（2026-10-05）：
共享固定边界与全部 8 个 Agent、8 个 Skill、8 个人工入口新增「只读诊断与执行边界」段——区分“生成命令”与“执行命令”，允许为明确诊断问题提供可复制只读 curl/查询 SQL/诊断命令，用户指定的公开读取在宿主允许时直接执行，结果可写入已授权工作目录；授权不自动覆盖重定向/代理/DNS 落点，内网、环回、链路本地与云元数据端点不因“只读”放行，本地凭据文件、影子副本与 curlrc 隐式注入不作为查询目标或请求体来源。生产只读执行本包仍未实现（写明未执行），生产写操作仍只给人工评审卡。MANAGED_HARNESS 块与生产连接/输出限制未放宽。清理 common.md、manual、roles/skills、references、templates 与 plugin.json 中“只输出评审卡、不给命令”的旧误拒条款。runtime-contract.json 新增 scoped `read_only_boundary`；静态检查器新增 blanket-ban 检测、9 项边界标记检测、托管块泄漏检测与 `read_only_boundary_errors`；新增 `tests/test_read_only_boundary.py`（16 项正负例，含数据外泄原语的“只允许出现在禁止句中”断言）。全部产物经项目自身构建器重建。

**未执行**：宿主权限未修改、缓存未替换、未提交推送。WorkBuddy/CLI 真实导入、有效工具权限、公开读取实机执行与生产只读通道均未验证。

# 2.6.1 开发工作区同步版

发布工具链、版本一致性（VERSION 为唯一版本源）与独立包 zip 安全校验；`tools/release.py` 与 `tests/test_version_consistency.py` 等新增并登记到 release-manifest。

# 2.6.0-rc3.workbuddy.2 宿主验收修复候选版

在 2.6.0-rc3.workbuddy.1 基础上，按 WorkBuddy 真实宿主验收准备的最小修复（2026-09-30）：
恢复根 settings.json（字节级取自 rc3 原交付 ZIP）；静态一致性检查器新增作用域感知的同义冲突句检测（3 条托管专属规则的语义改写检出，含合法否定句守卫）；8 个角色 frontmatter 按官方可选字段各绑定自己的 Skill 并纳入静态校验；release-manifest 纳入新增回归测试 tests/test_semantic_conflicts.py。全部经项目自身构建器重建；宿主场景验收进行中，见 audit-output-20260930-glm53。非精确 GitHub HEAD checkout。

# 2.6.0-rc3.workbuddy.1 本地修复候选版

完整源码恢复、WorkBuddy 入口、三模式配对、原生成员返回、Oracle 反证量化边界、原子构建与安全发行、负向测试和验证文档。非精确 GitHub HEAD checkout；宿主测试尚未执行。见 MODIFICATIONS.md 与 source-provenance.json。

# 修订历史 · 2.5.0
2026-09-22

## 已确认事实
新增课程工具与八角色判断分工，区分原摘要与工程适配；按材料触发、复用已有输出字段。新增静态配置检查与正反例、未运行的 TT 设计。四份 Schema、旧测试、原权限与控制不改；所有发布入口由源重建。

## 高概率候选
判断依据更易审查是设计目标，不是已验证效果；需真实模型对照。

## 待验证
Harness、导入、有效权限、动态 OODA、材料真伪与长期判断质量没有因本版而完成。历史包与报告分别保留，历史通过数不自动迁移。

## 已排除
不新增数值概率、凯利投入计算、模型评分或生产执行。

## 历史
2.4.0：判断依据 Schema 增强，见 docs/history/CHANGELOG-2.4.0.md；更早版本沿归档继续保留。旧提示词补丁仅适用于文件名所列版本，不是当前整包迁移脚本。
