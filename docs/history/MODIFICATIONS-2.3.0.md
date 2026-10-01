历史记录，非 2.3.1 结论；其中迁移概括及矩阵数字请以当前文档为准。

# 2.3.0 修改摘要（2026-09-21）
## 已确认事实
共享 common Schema 增加候选引用、方向、证据效应及请求正反分支；原有约束不放宽，member-result/lead-result/feedback 主体和 $id 不改。新增 reasoning 策略，runtime-contract 仅追加可信上下文字段并升级版本。
只编辑源文件，所有 Agent、Skill、references、assets、schemas 副本、模板、人工入口、独立包与锁文件由 build_bundle 重新生成。原有 Agent/Skill ID、头像、plugin 的 agents/skills/members 列表与权限保持不变。
公共/团长/成员提示词及人工入口同步 OODA；新增参考与设计说明，追加诊断映射、行为/验收用例及 Schema 正反例。工具显式 UTF-8 读取、LF 写入，用 AST 检查读调用，按字节检查生成文本 CR。requirements-build.txt 保持不动。
vmstat 链接仅修复 linux//man-pages 的多余斜杠，不声称目标网页已核验。

## 高概率候选
本次契约用于暴露缺基线、无区分度支持、同源计数及旧证据跨轮驱动问题；方向提议仍可能错误，不能当作概率或状态迁移证明。实际本地结果见 [VALIDATION.md](VALIDATION.md)，真实模型效果须另行验收。

## 待验证
2.1.0 历史记录提到 settings.json（agent=telecom-crm-sre-team-lead），本包没有；须对照用户的 2.1.0 原包，本次不创建。
workflows.json 的 early_handoff_event 允许任意阶段受阻交接，与 roles.json 团长 HANDOFF 仅 P7 存在契约缺口；本次仅升级 version，不调整这两处语义。
包内外部链接均未联网核验。没有运行目标模型、宿主导入、真实多 Agent 回执、持久账本、状态机、权限/语义门或唯一发布器。B/T 全部保持 NOT_RUN_IN_TARGET_HOST，Harness 保持 NOT_IMPLEMENTED。

## 已排除
没有擅自新增 author.email、settings 或市场展示字段修订，不猜联系邮箱；这些不是本次 OODA 升级范围。没有修改 maxTurns、生产执行权限或现有角色/阶段授权。

## 决策记录
“安装计划修改”按上下文解释为“按照计划修改”，不是把插件安装到用户宿主。
按要求保留 candidate 原有 allOf 原文；“每个 if 带 required”应用于本次新增条件，不回写已有条件。
reasoning.effect_rules 首项两个 expected 槽均使用 ANY_UNKNOWN，明示为任一 expected 未知的规则标记，不是 AND 条件，也不是模型输出枚举。
团长指定原文最后一个自检问题与“任一为是”存在极性矛盾；保留原文，紧邻补充最后一问须为是、前五问须为否，以 Decide/request 契约为准。
保持 T24 对原有 B 基线的历史描述，新增 B/T 场景单独追加；不把旧历史检查数量改写成当前通过数量。所有当前检查数与哈希最终从本次实际输出写入。

## 历史记录
原 2.2.0 修改摘要完整保存在 docs/history/MODIFICATIONS-2.2.0.md，不作为本次模型或宿主验收结论。
