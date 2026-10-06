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
