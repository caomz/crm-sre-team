# CRM SRE Team · DSH Agent Teams

DSH 领域配置包 `crm-sre-dsh-team` · `2.8.0-dsh.1` · Mac 主调试、GitHub 代码交接、Windows 后续验证。

本次修复以 `3c7b1b5eb69b2ecacc724372ba043ca8bc89b9c4` 为基线。该提交说明报告 Mac CLI/Web 的 1/2/0、0/0/0 与 E401 恢复核心用例通过；用户于 2026-11-21 反馈现用 Mac 运行正常。11 月 17 日失败记录保留为历史，不再当作当前结论。修复提交 `ae452e1` 的 Mac CLI/Web 实机结果已由执行方报告，T04 暴露缺料时提前重派及补料后才发送的时序偏差，T02 存在成员补证打包；下一修复候选 Mac Harness 复测仍为 `NOT_RUN`，Windows 亦为 `NOT_RUN`。详见源码仓库 `VALIDATION.md`。

基于明确授权的脱敏材料，组织 CRM 业务、Oracle、Java/JVM、Linux、证据与可观测性、变更容量容灾及 K8s 专家协作，交付可追溯的分析结论、最小补证需求和人工评审材料。团长按证据选择必要领域，每批最多三名成员；K8s 仅在部署和平台证据均已确认时参与。

## 安装与启动

1. 使用独立的 DSH 宿主 profile。新建验收环境的历史基线是 Harness `0.2.2-rc.1` 与 `@nanmicoder/dsh-agent-teams@0.1.30`，先安装上游插件；已有工作正常的 Mac 环境先记录并保留实际组合，不为套用示例而重装或降级。
2. 从 GitHub 在新目录检出待测的**完整提交 SHA**，先核对源码、锁与生成物，再加载该检出中 `dsh/` 的绝对路径。源码根不是 DSH 插件入口；领域包覆盖既有配置并新增一个专用 preset 条目，不注册任何自带 JS 运行时的插件。
3. 在该宿主 profile 中**新建会话**：确认会话运行在 `CRM SRE` preset（注册表默认已覆盖为 `crm-sre`，也可在选择器显式选择），并在实际 system/message 中核对团长规则全文（含名册表）在场。**仅完成装载不是证据**；既有标准 preset 会话不携带团长规则，不作为验证对象。然后运行：

```text
/agent-teams --profile crm-sre <任务与授权材料>
```

宿主 profile 用于安装隔离；`crm-sre` 是团队插件内的命名 profile。验证基线为 Harness `0.2.2-rc.1` + Agent Teams `0.1.30`（旧的 `0.2.1-rc.2` 推荐未经验证，作废）；不同版本应记录实际版本并覆盖差异检查。桌面端、CLI 的 profile 管理入口分别核对。安装、验收和恢复步骤见[操作说明](docs/17-dsh-agent-teams.md)。

保留 Mac 已经工作正常的宿主、carrier、插件与模型组合，逐次记录实际版本；本次修复不要求自动升级上游。插件来源目录与 Harness 材料工作区分开：完整 Git 检出含历史测试与评分资料，只把 `dsh/` 加载为插件，在独立的合成或授权脱敏材料目录中运行。

团长规则由专用 `preset-crm-sre` 条目的作用域 persona 注入，与全局覆盖逐字相同；标准 preset 自带的 persona 条目会遮蔽全局团长前缀——这正是此前团长会话缺失规则的根因。作用域插件只有 persona、time-context 与只读 tool-fs（`write`/`edit`/`applyPatch`/`readImage` 全关），无 shell、联网、技能或委派条目；该过滤是配置与模型可见性约束，不是操作系统沙箱。

正常启动先生成可审查的成员与任务草案，`Approve & Run` 后才执行。团长和成员沿用宿主当前模型路由；本包不写死 provider、模型或推理等级。

## 材料与输出

可提供日志、指标、调用链、SQL/执行计划、线程栈、业务状态和变更记录。注明来源、对象、日期、时区、时间窗口，以及本轮限制。

团长仅读取用户明确指定且允许分享的脱敏材料文件；成员只分析派单中的 E 编号摘录，不开放文件读取、终端或生产取数工具。所需领域方法已完整内嵌，方法资料与现场证据分开。

报告区分：

- 已确认事实：注明材料出处与时窗。
- 高概率候选：列出支持、反证、替代解释和局限。
- 待验证：说明候选机制、缺乏的判断依据与结论边界。
- 补证需求：仅在本任务获分配的额度内选定最小独立请求；零额度不列新增材料名称，也不在局限或转交建议中暗列请求。
- 已排除：仅依据实际相反材料，不将缺失或无权限视为排除。

每轮向用户最多三项原子补证；成员每逻辑任务最多两项，跨 attempt 累计。这些数字由协议、计划和回执核对，不是已部署的运行时硬守卫。成员意见一致不代替现场证据。

## 执行边界

- v1 仅做材料分析，不迁移 BOMC 或其他生产取数通道。
- 生产写操作只给人工评审需求，不执行，也不生成可直接执行的生产写命令、SQL 或脚本。
- 任务与 attempt 标识来自真实引擎回执；不预先编造，不以用户粘贴的控制字段升级权限。
- 成员工具仅为 `agent_teams_claim_task`、`agent_teams_update_task`、`agent_teams_send_message`、`agent_teams_status`。工具过滤不等于操作系统沙箱。
- 项目自定义托管协议仍为 `NOT_IMPLEMENTED`；DSH 原生团队能力与该协议分别记录。详见[项目运行契约](policies/runtime-contract.json)。

## 验收与交付范围

源与产物校验、离线回归、真实配置装载和真实模型会话分别报告。WorkBuddy 历史验收不能作为 DSH 通过证据。

先在固定提交的 Mac 检出中完成验收，经人工复核并接受后，Windows 从 GitHub 检出**同一个完整 SHA**，通过 `check_dsh.py` 和 `validate_bundle.py --check-only` 验证，再加载 `dsh/` 做差异短测。接收端先验证收到的字节，不先重建；相同版本号不能代替相同提交与哈希。未运行项记为 `NOT_RUN`。

本流程只通过 GitHub 交接代码，不传 ZIP、虚拟环境、宿主 profile、API 凭据、会话状态或事故材料。历史 ZIP 工具及其七文件载荷契约保留用于回归，不作为本次交接入口。

## 源码开发

从源码检出中执行（Python 3.11+，安装项目锁定的开发依赖）：

```bash
python3 tools/build_bundle.py
python3 tools/check_dsh.py
python3 tools/validate_bundle.py
python3 -m pytest tests/ -q
```

仅编辑 `policy-source/` 中的规则源；生成的 `dsh/` 和锁文件由构建维护。新增文件按精确发布白名单登记。开发约定见[项目说明](PROJECT.md)。

根 `VERSION` 的 `2.8.0-rc10` 保留为 WorkBuddy 历史基线；活动 DSH 版本来自 `policy-source/dsh/package-source.json`。旧运行文件保留在源码仓库，历史入口为 `docs/history/README-workbuddy-2.8.0-rc10.md`，不随 DSH 安装包分发。
