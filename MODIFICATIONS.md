# 修复说明 · 2.6.0-rc3.workbuddy.2

## 本轮改动（2026-09-30，宿主验收准备）

1. **恢复根 settings.json**：rc3.workbuddy.1 树中该文件缺失导致构建/校验链全线失败；从原交付 ZIP 字节级恢复（SHA-256 d5991e15…23114e 与原包一致），未改写内容。
2. **静态检查器同义句漏检修复**：tools/check_workbuddy.py 原仅靠 5 条托管专属规则的字面匹配，3 条语义改写（禁止派生的同义句、缺 harness_context 停止回答、原生模式强制 task_id/phase）全部漏检。新增作用域感知语义模式 + 否定前缀守卫，并先加失败回归（tests/test_semantic_conflicts.py，6 例含合法否定句反例）再修复。
3. **Skill 预加载绑定**：8 个角色规范源 frontmatter 各加官方可选 skills 字段，仅绑定本角色 Skill；检查器同步校验"绑定且仅绑定自己的 Skill"。
4. **release-manifest.json** 纳入新回归测试；全量重建 agents/skills/锁/独立包。

环境限制（非产品缺陷）：Windows 重建的 BUNDLE-LOCK/prompt-bundles.lock 键序与 Linux 构建不同（内容逐键相同）；本机无法创建符号链接，3 个符号链接防护测试无法执行。宿主场景验收见 audit-output-20260930-glm53，进行中。

# 修复说明 · 2.6.0-rc3.workbuddy.1

## 核心改动

补根 settings.json，统一注册主 Agent；团长及七成员的 Agent/Skill 规范源明确拆分托管、原生、兼容的输入、权限和返回方式。托管专属字段与绝对禁止调用规则被整体限定到托管段，不与原生调度同时生效。成员直接对话不因缺 Harness 返回空 blocked。
Oracle 新增同对象/时窗的反证边界和无证据不量化规则；所有模式保留来源、反证、替代解释、请求额度和生产隔离边界。

构建器从规范源重建全部角色、接口、参考、知识模板、锁和八个单技能包，采用暂存生成/异常回滚；不含旧套补丁脚本，不覆盖根 settings。三个旧团队知识文件由 canonical source 生成；个人环境和旧事故索引改为空模板。

新增逐文件发布白名单、原子 ZIP 构建、原始条目顺序与重复检查、路径/符号链接/元数据/内容验证。测试覆盖输出位于根目录或 dist、重复构建、虚构敏感文件、错误配置、模式冲突、文件缺失、失败回滚和重跑。

原四份 Schema、五份被历史基线保护的测试及其他已有测试源保持字节不变；历史 baseline-contract.json 不改写。角色接口登记、确定性脚本、运行契约与插件文案的必要变更逐项列入窄范围授权指纹表，不放宽 Schema，不删除负例。

本轮不实现专用 Harness、不声称宿主权限隔离或模型行为已通过。旧验证文件另存 docs/history，不能当本轮结果。完整来源和公开锁比对见 source-provenance.json。
