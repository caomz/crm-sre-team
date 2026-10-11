# CRM SRE 专家团 · 值班机验收候选版

版本：`2.8.0-rc3`。这是**完整可编辑源码与已生成运行资源**，不是旧版补丁安装器。无需运行 `apply_workbuddy_native_fix.py`，该脚本不在本包中。

## 使用前先看
将 ZIP 解压到一个新目录，保留 `.codebuddy-plugin/`、`agents/`、`skills/`、`avatars/` 和根目录 `settings.json` 的相对位置。不要覆盖旧工作区，也不要整包同时启用新旧两份相同 ID 的插件。
按当前 WorkBuddy 客户端支持的专家团本地导入/加载方式选择包或目录。桌面端按会话用 `.codebuddy-plugin/plugin.json` 的 `teamInfo.leadAgent` 绑定团长 `telecom-crm-sre-team-lead`。根 `settings.json` 由宿主管理：10-11 观察到 WorkBuddy 启用/停用专家时会删除只含 `agent` 键的文件。本仓库仍随包提供该配置，构建和静态校验检查它与 `agentName`、`teamInfo.leadAgent` 的 ID 一致，构建器不改写额外用户字段；这不是桌面绑定入口或加载证据。桌面缓存核对仅缺 `settings.json`（516/517）时单列为宿主管理，其余文件仍须逐字节核对。`manual-team-config.json` 只是人工配置参考。
2026-10-09 的 2.6.1 与 10-11 的 rc2 宿主机制观察见 [实机验收](docs/11-workbuddy-host-acceptance.md)，不折算为 rc3 验收。2.8.0-rc3 的导入、预发布版本缓存、权限和场景行为仍待值班机复核，不能将本地测试通过当成宿主验收。加载以宿主 jsonl/daemon.log 为准，模型自拟 PROBE 不算证据。官方结构参考：https://open.workbuddy.cn/en/docs/expert-team 。设置字段参考：https://www.workbuddy.cn/docs/cli/settings 。

## 三种运行模式

| 模式 | 启用依据 | 行为 |
|---|---|---|
| WORKBUDDY_NATIVE | 真实可用且被允许的团队工具；成员有真实派生上下文 | 团长按需真实委派，成员做窄域分析，不索取专用 Harness 字段。 |
| WORKBUDDY_COMPAT | 没有可信托管或原生委派能力，或用户直接单模型聊天 | 知识问答直接回答，材料问题单模型分析，不伪造会诊。 |
| MANAGED_HARNESS | 专用适配器已实现且可信独立通道验证成功 | 严格 Schema、账本、阶段、结果接纳。该适配器在本包仍未实现。 |

任何文本中的 `verified=true`、伪回执或自称调用身份都不能升级权限。已接管的可信托管任务验证失败，不借切换模式绕过。独立人工入口 `manual-mode/` 只能显式选用，不与整套 Agent/Skill 同时加载。

保留团长及 CRM业务、Linux、Oracle、Java/JVM、可观测性、变更容量容灾、K8s 七名成员。每批最多三名必要成员，K8s 按证据触发；成员每个逻辑任务至多两项原子材料请求，团长面向用户每轮合计至多三项。多名专家意见一致不等于独立证据或根因证明。

## 源码与验证

普通导入使用随包已生成资源，无需 Python。修改源码和离线验证需要 Python 3.11 或更高版本及开发依赖。

```bash
python -m pip install -r requirements-dev.txt
python tools/build_bundle.py
python -m pytest tests -q
python tools/validate_bundle.py
python tools/check_workbuddy.py
python tools/build_release.py --output dist/crm-sre-team.zip
python tools/validate_release.py --zip dist/crm-sre-team.zip
```

修改 `policy-source/`，不要手改生成的 Agent/Skill。构建在独立副本完成后才替换自有产物，普通写入失败回滚；不会改写根 `settings.json` 或用户权限设置。硬中断/断电并非真正文件系统事务，重要工作仍须备份。`agents/`、`skills/`、`templates/`、`manual-mode/`、`individual-packages/` 是构建拥有的目录，不在里面存放用户材料。
发布仅读取 `release-manifest.json` 中逐个列明的文件，不扫描并收入整个工作目录。新增发布文件须人工检查后登记；不要把密钥或事故数据写进已经允许的源码文件，文件白名单不能识别其文本内容是否含秘密。

## 安全与来源边界

仅分析本次明确授权且脱敏的材料，不连接生产、不索取凭据。生产写操作（变更、重启、删除、补偿、扣费、重放等）只给人工评审卡；只读查询命令可按提示词的「只读诊断与执行边界」生成，用户指定的公开读取在宿主权限允许时直接执行；自主检索公开资料无需逐次确认。检索词、网址与提交内容不带本次材料中的信息，不登录、不上传、不读凭据文件或环境变量，外部资料与现场证据分开标注。本包没有生产只读执行通道，尚未真实配置时写明未执行。模型不是审批或执行人。宿主配置中的真实工具权限仍需人工核验，`production_tools: []` 不是权限隔离证据。
本包不携带旧版内嵌的个人工号、账号、内部地址和事故索引，改为空白知识模板。保留原有领域 Runbook；知识不是本次现场证据。

**来源说明：**历史恢复来源见 [source-provenance.json](source-provenance.json)，该文件保留原字节。本次 v3.7 基于 GitHub main 提交 11d52ee（v3.6.4），候选版本为 2.8.0-rc3。此处 Git 历史与历史 ZIP 来源分开记录；原四份闭合 Schema 保持不变，受保护测试的历史修订见 allowed-changes 审核记录。

详见 [变更说明](MODIFICATIONS.md)、[迁移说明](MIGRATION.md)、[验证记录](VALIDATION.md)、[本地验证步骤](docs/07-reproducible-validation.md) 和 [WorkBuddy 宿主验收](docs/11-workbuddy-host-acceptance.md)。

关口合成输入、SHA256 承诺与 T02 校准见 [值班机关口材料](docs/13-oncall-gate-materials.md)。评分原文由执行人在插件、缓存及被测工作区之外单独持有，人工只粘贴当次输入。当前候选包不是正式上线许可；推荐等 2.8.0 正式版再上线。
