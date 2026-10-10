# 迁移到 2.8.0-rc2

本候选包升级版本以消除“同版本、不同内容”的缓存歧义，预发布后缀须在 Windows 10 宿主实测。推荐等 2.8.0 正式版再上线（R2-35）；不因候选版静态通过恢复市场回同步。

安装来源目录与开发 clone 分开。退出 WorkBuddy 后备份 marketplace.json，把旧来源整目录（含其本地 .git）归档到 my-experts\backups\，从已验证 ZIP 解压的新暂存目录 Copy-Item -Recurse 到全新来源目录；不把工作树覆盖缓存，不迁移 .workbuddy/memory、reports 或用户设置。旧 settings.json 删除原因不阻断，新包根 settings.json 必须存在。市场条目若有 version 字段同步成候选版本，再由 WorkBuddy 更新插件、开新会话；逐个发布文件比较 cache\<新版本> 的 SHA256，额外宿主元数据单列。
回滚先退出客户端，把新来源归档到独立目录，再恢复旧来源整目录和 marketplace.json 备份，用客户端重新加载旧版本；不删除或覆盖缓存。任何新旧目录重名、来源漂移或 SHA256 不匹配先停止，不继续验证。

## 历史迁移记录（2.6.0-rc3.workbuddy.2）

先把本包解压到新文件夹，不向旧工作区覆盖；不要再运行此前有缺陷的一键补丁。旧脚本部分执行过的工作区先保存 `git diff` 与自己的设置，禁止用破坏性重置清理。

当前 Agent 和 Skill ID 保持不变，因此不要同时启用旧包和新包。保留用户自己的账号、凭据和事故材料在包外，不复制进源码。已有 settings 的额外字段请人工比较后只在新目录中保留；本包只需主 Agent 字段，构建器不会覆盖其他字段。

原生/兼容输出采用自然语言四象限，不把新字段塞入原闭合 Schema。严格 Schema 和原 Harness 约束只在 MANAGED_HARNESS 使用。外部消费程序若之前从 runtime-contract.json 顶层读取 trusted_context_fields 等字段，推荐改读 managed_mode 内对应字段；三项旧字段提供只适用于托管模式的兼容别名并校验与新位置一致，不能用于原生任务；此处是有意明确的模式拆分，不是已部署适配器。

新包中个人化环境/知识索引为空，必须按本次任务重新获得授权。不自动迁移历史字段为事实。修复基于完整上传版恢复，不能保证包含当前 GitHub main 的所有新增文件；与自己较新的工作区合并前先审查 source-provenance.json。

回退时停用新目录，从未改动的旧目录重新加载；不要混装同名成员。任何真实宿主验证失败都应保存脱敏错误，不改用假回执让模型继续。

## Slice 1 / Slice 2 运行时变更（工作区构建说明）

- 运行时产物（agents、skills、individual-packages）已剥离 MANAGED_HARNESS 段；托管设计完整保留在 policy-source/ 源文件中，源级校验继续覆盖托管契约。
- 独立 skill.zip 自本次起由剥离后的 Skills 重建，当时版本号未变（仍为 2.7.0）；本次候选已升为 2.8.0-rc2。**在 PR-5（2.8.0）发布之前暂停从本仓库向 WorkBuddy 市场回同步 skill.zip**：仓库 zip 与市场 2.7.0 包（commit 91faeaf 回同步）内容已不同；若需提前回同步，必须先说明同版本 zip 的调和方式（版本升级或逐字节比对记录）。
- 团长 Agent 正文新增成员名册（注册 ID + 触发证据 + 不该派情形），由 policy-source/routing-source.json 生成；该文件是项目内部字段，不是宿主工具参数。
- 证据编号、派单模板与反证（REFUTE）约定见 policy-source/prompts/common.md 共用段与团长/成员提示词；成员返回标题保持"已确认事实／高概率候选／待验证／已排除"。
