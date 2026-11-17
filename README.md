# CRM SRE Team · DSH Agent Teams

DSH 领域配置包 `crm-sre-dsh-team` · `2.8.0-dsh.1` · 候选版本；Mac CLI/Web 已真实运行 GLM 5.3 Flash 团队，但补证配额、恢复和部分回执表述未通过，尚未完成人工接受。

基于明确授权的脱敏材料，组织 CRM 业务、Oracle、Java/JVM、Linux、证据与可观测性、变更容量容灾及 K8s 专家协作，交付可追溯的分析结论、最小补证需求和人工评审材料。团长按证据选择必要领域，每批最多三名成员；K8s 仅在部署和平台证据均已确认时参与。

## 安装与启动

1. 在独立的 DSH 宿主 profile 中，先安装 `@nanmicoder/dsh-agent-teams@0.1.30`。
2. 将本发布包解压到新目录，加载其中 `dsh/` 的绝对路径。领域包覆盖既有配置并新增一个专用 preset 条目，不注册任何自带 JS 运行时的插件。
3. 在该宿主 profile 中**新建会话**：确认会话运行在 `CRM SRE` preset（注册表默认已覆盖为 `crm-sre`，也可在选择器显式选择），并在实际 system/message 中核对团长规则全文（含名册表）在场。**仅完成装载不是证据**；既有标准 preset 会话不携带团长规则，不作为验证对象。然后运行：

```text
/agent-teams --profile crm-sre <任务与授权材料>
```

宿主 profile 用于安装隔离；`crm-sre` 是团队插件内的命名 profile。验证基线为 Harness `0.2.2-rc.1` + Agent Teams `0.1.30`（旧的 `0.2.1-rc.2` 推荐未经验证，作废）；不同版本应记录实际版本并覆盖差异检查。桌面端、CLI 的 profile 管理入口分别核对。安装、验收和恢复步骤见[操作说明](docs/17-dsh-agent-teams.md)。

本候选已确认团长规则与成员工具加载生效；实际行为仍须人工核对，详见操作说明中的现场记录。

团长规则由专用 `preset-crm-sre` 条目的作用域 persona 注入，与全局覆盖逐字相同；标准 preset 自带的 persona 条目会遮蔽全局团长前缀——这正是此前团长会话缺失规则的根因。作用域插件只有 persona、time-context 与只读 tool-fs（`write`/`edit`/`applyPatch`/`readImage` 全关），无 shell、联网、技能或委派条目；该过滤是配置与模型可见性约束，不是操作系统沙箱。

正常启动先生成可审查的成员与任务草案，`Approve & Run` 后才执行。团长和成员沿用宿主当前模型路由；本包不写死 provider、模型或推理等级。

## 材料与输出

可提供日志、指标、调用链、SQL/执行计划、线程栈、业务状态和变更记录。注明来源、对象、日期、时区、时间窗口，以及本轮限制。

团长仅读取用户明确指定且允许分享的脱敏材料文件；成员只分析派单中的 E 编号摘录，不开放文件读取、终端或生产取数工具。所需领域方法已完整内嵌，方法资料与现场证据分开。

报告区分：

- 已确认事实：注明材料出处与时窗。
- 高概率候选：列出支持、反证、替代解释和局限。
- 待验证：提出能改变判断的最小材料需求。
- 已排除：仅依据实际相反材料，不将缺失或无权限视为排除。

每轮向用户最多三项原子补证；成员每逻辑任务最多两项，跨 attempt 累计。这些数字由协议、计划和回执核对，不是已部署的运行时硬守卫。成员意见一致不代替现场证据。

## 执行边界

- v1 仅做材料分析，不迁移 BOMC 或其他生产取数通道。
- 生产写操作只给人工评审需求，不执行，也不生成可直接执行的生产写命令、SQL 或脚本。
- 任务与 attempt 标识来自真实引擎回执；不预先编造，不以用户粘贴的控制字段升级权限。
- 成员工具仅为 `agent_teams_claim_task`、`agent_teams_update_task`、`agent_teams_send_message`、`agent_teams_status`。工具过滤不等于操作系统沙箱。
- 项目自定义托管协议仍为 `NOT_IMPLEMENTED`；DSH 原生团队能力与该协议分别记录。详见[项目运行契约](policies/runtime-contract.json)。

## 验收与交付范围

源与产物校验、离线回归、ZIP 完整性、真实配置装载和真实模型会话分别报告。WorkBuddy 历史验收不能作为 DSH 通过证据。

先完成 Mac 验收，经人工复核并接受后，Windows 安装同一接受产物并做完整性核对与差异短测。未运行项记为 `NOT_RUN`。

DSH ZIP 仅包含三个 `dsh/` 文件、本文、`PROJECT.md`、操作说明和项目运行契约，不包含旧插件、用户材料、历史会话或评分 gold。

## 源码开发

从源码检出中执行（Python 3.11+，安装项目锁定的开发依赖）：

```bash
python3 tools/build_bundle.py
python3 tools/check_dsh.py
python3 tools/validate_bundle.py
python3 -m pytest tests/ -q
python3 tools/build_release.py --output dist/crm-sre-dsh.zip
python3 tools/validate_release.py --zip dist/crm-sre-dsh.zip
```

仅编辑 `policy-source/` 中的规则源；生成的 `dsh/` 和锁文件由构建维护。新增文件按精确发布白名单登记。开发约定见[项目说明](PROJECT.md)。

根 `VERSION` 的 `2.8.0-rc10` 保留为 WorkBuddy 历史基线；活动 DSH 版本来自 `policy-source/dsh/package-source.json`。旧运行文件保留在源码仓库，历史入口为 `docs/history/README-workbuddy-2.8.0-rc10.md`，不随 DSH 安装包分发。
