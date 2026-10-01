# CRM SRE 专家团 · WorkBuddy 修复候选版

版本：`2.6.0-rc3.workbuddy.2`。这是**完整可编辑源码与已生成运行资源**，不是旧版补丁安装器。无需运行 `apply_workbuddy_native_fix.py`，该脚本不在本包中。

## 使用前先看
将 ZIP 解压到一个新目录，保留 `.codebuddy-plugin/`、`agents/`、`skills/`、`avatars/` 和根目录 `settings.json` 的相对位置。不要覆盖旧工作区，也不要整包同时启用新旧两份相同 ID 的插件。
按当前 WorkBuddy 客户端支持的专家团本地导入/加载方式选择包或目录。根目录入口为 `settings.json`，主理人 `telecom-crm-sre-team-lead`；不是 `manual-team-config.json`，后者只是人工配置参考。
本包的客户端导入、实际工具权限和真实多成员调用尚未实测，不能将本地测试通过当成宿主验收。官方结构参考：https://open.workbuddy.cn/en/docs/expert-team 。设置字段参考：https://www.workbuddy.cn/docs/cli/settings 。

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

仅分析本次明确授权且脱敏的材料，不连接生产、不索取凭据、不输出可执行生产命令/SQL/脚本。模型不是审批或执行人。宿主配置中的真实工具权限仍需人工核验，`production_tools: []` 不是权限隔离证据。
本包不携带旧版内嵌的个人工号、账号、内部地址和事故索引，改为空白知识模板。保留原有领域 Runbook；知识不是本次现场证据。

**来源说明：**本次完整文件基底来自你此前上传的 `2.5.0` 项目 ZIP，并对照可读取的公开 `2.6.0-rc2` 源码/锁文件修复。本环境未取得当前 GitHub 的完整 checkout 或提交 SHA，因此这是独立本地修复候选版，**不宣称等于当前 main 全量源码的精确补丁结果**。原四份闭合 Schema 与既有测试源保留。逐项来源见 [source-provenance.json](source-provenance.json)。

详见 [变更说明](MODIFICATIONS.md)、[迁移说明](MIGRATION.md)、[验证记录](VALIDATION.md)、[本地验证步骤](docs/07-reproducible-validation.md) 和 [WorkBuddy 宿主验收](docs/11-workbuddy-host-acceptance.md)。
