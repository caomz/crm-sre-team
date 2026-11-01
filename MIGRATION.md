# 迁移到 2.8.0-rc10

rc10 收紧验收审计与输出读取范围，不自动迁移 WorkBuddy 配置、记忆或缓存。Mac 精简验收已复核并获用户确认，当前准备发布交接；发布身份固定后再安排值班机简单检查。rc9 标签与缓存保留。

审计 CLI 退出码：PASS=0、FAIL=1、执行/输入错误=2、BLOCKED=3、HOST_LIMIT/PASS_WITH_KNOWN_ISSUES 或其他待复核=4；PASS 仍有 review_required 时也为 4。report 有阻断或待复核也不返回 0。调用方必须核对 JSON result 和待复核字段。

含成员的 audit 同时传 --collection 与明确可信的 --projects；裸 --member 或无法重核来源的离线日志不再自动通过。正常消息需明确 completed；仅自动评分一个明确请求。多请求、缺终态或未答追加请求保持阻断，不能用裁剪日志或补造字段规避。知识路径使用源平台物理身份；跨机缺证明不自动通过。具体参数见 docs/14。

rc10 的 Mac 精简验收已通过，正在整理发布交接，尚未创建本次发布提交或标签。2026-11-01 13:16～13:50（+08:00），Codex 桌面会话执行八例各一次、零重跑，机器草表 8 PASS；Claude 逐例复核 8/8 PASS，用户于当日 14:20（+08:00）回复“确认验收”。WorkBuddy 5.9.3，团长与 MEMBER 成员实际模型均为 glm-5.3-flash；INSTALL、真实 MEMBER、KB 三页、TD-01～TD-04、rc6 RESTORE 均通过。Windows UPDATE/VERIFY、真实 YES、Windows Job、真实 BOMC 查询与 bomc.json 部署、正式 N/S、WB 全量仍为 NOT_RUN。

被测包为 `2.8.0-rc10-mac-lean4.r20261101758e264c425445ce`（ZIP SHA256 `5383cf64b745e14d0eb668704c7ba7559569128060878c13f39a6b7d27cb3e26`），与 `candidate-5.zip`（`747612b296075afb1cc77362a1da9aab7a9c3878955ceaceac8bc0bc487f8b2d`）只差版本串。候选5与验收后补写前的 rc10 离线正式构包有 334 项宿主运行文件同字节，560 项载荷仅 `docs/15-bomc-readonly.md` 与 `prompt-bundles.lock` 不同；本次验收归档另改文档，最终全部差异由仓库外交接逐文件列出，运行文件仍须同字节。正式版本为 `2.8.0-rc10`，目标标签为 `crm-sre-team-2.8.0-rc10`；发布提交及最终 ZIP SHA256 在提交后确定，发布身份见标签说明与 r7 手册固定记录；r7 身份固定行由发布后的独立手册提交补入。

外部证据：`/Volumes/WorkSSD/Archives/claude-tests/rc10-mac-lean-20261101-131633`，执行人 `REPORT.md`、`checks/1793511988652113000/` 与 `SHA256SUMS`（118 项 OK）。封存报告当时的 PENDING_HUMAN_REVIEW 保留；Claude 复核与用户确认是其后的验收事实，本节为其后补记。完整八例、历次失败/改判、宿主恢复及转存更正见 [VALIDATION.md](VALIDATION.md)。

Mac 已留存 10-25 的 rc10 测试缓存；后续加载须核对实际来源、全部申报文件与根锁哈希，不能以相同版本目录名认定是本候选，也不能覆盖旧缓存。

rc9 已于 2026-10-23 发布：安装提交 `a838012a37d86b5e0a77fdf85fc677cf8538e267`，标签 `crm-sre-team-2.8.0-rc9`（标签对象 `656cf3fd80d1512fc2496358f7d361c54f4be073`），发布 ZIP SHA256 `67e54af00c572757da6b19eea12aa6689f8cbfbd050175d7fba9defa93cd39eb`；手册附记提交为 `83ae9f9225bf701eb95531b060b515a8e5797cbf`。Mac R4 的技术结果及已记录偏差已获用户接受。

以下保留 rc9 及更早迁移记录。

# 迁移到 2.8.0-rc9

rc9 统一插件、Skill 包和守卫 VERSION / guard_version，纳入当前 main 的发布门与审计修复，以及更新器 YES 输入缓冲修复。BOMC 配置 Schema、参数白名单、最小权限和生产写边界不变；旧配置和旧包保留，不自动改 bomc.json。Mac R4 聚焦验收已完成，用户在知悉技术结果和准备阶段临时清理偏差后同意继续。rc9 发布提交、标签与 ZIP SHA256 已固定（见上方发布身份），Windows UPDATE + VERIFY 仍待正式回执；Windows 与真实生产通道仍未验证。

rc8 标签发布包与 cd1423a 同步工作树存在非运行时字节差异，不能仅凭相同 rc8 目录名确认安装身份。rc9 使用新的版本目录，由客户端从新来源创建缓存；不覆盖旧缓存、不移动或清理旧记忆。后续安装只使用正式固定的 rc9 身份与更新器安装记录，不复用 rc8 补充指令中的计划路径或常量。

## rc8 配置变更沿用说明

rc8 的 bomc.json 新增必填 code_sha256，先由执行人会话外复核三项哈希再部署；旧配置保留。含新字段的配置不能用于 rc7（未知字段退出 3），回退需匹配旧包与旧配置。Mac venv 使用 --copies，保持环境入口，不 resolve Python 链接；部署细节与未验证边界见 docs/15。

本候选包升级版本以消除“同版本、不同内容”的缓存歧义，预发布后缀、加载和提示词测试先在 Mac 验收；Mac 跑完、返回结果经人工复核并验收后，Windows 11 值班机（家庭版 23H2，10.0.22631）只做安装/切换 + VERIFY（来源/缓存完整性、Skill 回执路径）+ 记录版本，仅在需确认宿主行为时加一个短会话。两台都记录实际 WorkBuddy 版本、插件版本和模型，有差异时值班机检查覆盖差异；日常与关口固定 glm-5.3-flash，逐次记录实际模型。关口前两台都查看宿主记忆条目，是否清理或关闭由用户决定。推荐等 2.8.0 正式版再上线（R2-35）；不因候选版静态通过恢复市场回同步。

安装来源目录与开发 clone 分开。退出 WorkBuddy 后备份 marketplace.json，把旧来源整目录（含其本地 .git）归档到 my-experts\backups\，从已验证 ZIP 解压的新暂存目录 Copy-Item -Recurse 到全新来源目录；不把工作树覆盖缓存，不迁移 .workbuddy/memory、reports 或用户设置。开发源与发布 ZIP 的根 settings.json 必须存在，供离线结构一致性检查；桌面会话按 plugin.json 的 teamInfo.leadAgent 绑定。启用/停用专家后缓存仅缺 settings.json 时视为宿主管理（rc2 实测 516/517），不得据此判坏或补写缓存；其他文件仍逐个比较 SHA256，额外宿主元数据单列。市场条目若有 version 字段同步成候选版本，再由 WorkBuddy 更新插件、开新会话；实际加载另以宿主 jsonl/daemon.log 验收。
回滚先退出客户端，把新来源归档到独立目录，再恢复旧来源整目录和 marketplace.json 备份，用客户端重新加载旧版本；不删除或覆盖缓存。任何新旧目录重名、来源漂移或 SHA256 不匹配先停止，不继续验证。

## 历史迁移记录（2.6.0-rc3.workbuddy.2）

先把本包解压到新文件夹，不向旧工作区覆盖；不要再运行此前有缺陷的一键补丁。旧脚本部分执行过的工作区先保存 `git diff` 与自己的设置，禁止用破坏性重置清理。

当前 Agent 和 Skill ID 保持不变，因此不要同时启用旧包和新包。保留用户自己的账号、凭据和事故材料在包外，不复制进源码。已有 settings 的额外字段请人工比较后只在新目录中保留；本包只需主 Agent 字段，构建器不会覆盖其他字段。

原生/兼容输出采用自然语言四象限，不把新字段塞入原闭合 Schema。严格 Schema 和原 Harness 约束只在 MANAGED_HARNESS 使用。外部消费程序若之前从 runtime-contract.json 顶层读取 trusted_context_fields 等字段，推荐改读 managed_mode 内对应字段；三项旧字段提供只适用于托管模式的兼容别名并校验与新位置一致，不能用于原生任务；此处是有意明确的模式拆分，不是已部署适配器。

新包中个人化环境/知识索引为空，必须按本次任务重新获得授权。不自动迁移历史字段为事实。修复基于完整上传版恢复，不能保证包含当前 GitHub main 的所有新增文件；与自己较新的工作区合并前先审查 source-provenance.json。

回退时停用新目录，从未改动的旧目录重新加载；不要混装同名成员。任何真实宿主验证失败都应保存脱敏错误，不改用假回执让模型继续。

## Slice 1 / Slice 2 运行时变更（工作区构建说明）

- 运行时产物（agents、skills、individual-packages）已剥离 MANAGED_HARNESS 段；托管设计完整保留在 policy-source/ 源文件中，源级校验继续覆盖托管契约。
- 独立 skill.zip 自本次起由剥离后的 Skills 重建，当时版本号未变（仍为 2.7.0）；本次候选已升为 2.8.0-rc4。**在 PR-5（2.8.0）发布之前暂停从本仓库向 WorkBuddy 市场回同步 skill.zip**：仓库 zip 与市场 2.7.0 包（commit 91faeaf 回同步）内容已不同；若需提前回同步，必须先说明同版本 zip 的调和方式（版本升级或逐字节比对记录）。
- 团长 Agent 正文新增成员名册（注册 ID + 触发证据 + 不该派情形），由 policy-source/routing-source.json 生成；该文件是项目内部字段，不是宿主工具参数。
- 证据编号、派单模板与反证（REFUTE）约定见 policy-source/prompts/common.md 共用段与团长/成员提示词；成员返回标题保持"已确认事实／高概率候选／待验证／已排除"。
