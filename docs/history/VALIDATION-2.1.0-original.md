# 验证记录
## V2.1.0 实际完成（2026-09-10）
- 备份：`crm-sre-team-backup-2.0.0.zip`（v2.0.0 完整快照）。
- 文件创建：`.codebuddy-plugin/plugin.json`（Team 型，members 双字段兼容 name+displayName）、`settings.json`（agent=telecom-crm-sre-team-lead）、`avatars/` 9 张 512×512 PNG（均 <500KB，14-19KB；本次为占位风格——蓝紫渐变+徽标+中英文名，因 ImageGen 后端不可用降级生成）。
- 主理人 MD：maxTurns 30→100，追加 5 章节（团队成员表/SOP Phase 0-7/铁律+3条补充/WF-A·B·C/直调路由表），原文安全边界逐字未改动。
- 7 个成员 MD：maxTurns 15→25，frontmatter 英文头衔补全为 Expert 后缀，正文未改动。
- `validate_expert.py`：exit 0，0 error。
- `register_expert.py` (--session-id 4a83d79c-...)：exit 0，marketplace.json 新增 crm-sre-team 条目（与 gstack-engineering、video-diary-team 并列）。
- `package_expert.py`：dist/crm-sre-team.zip 594KB。
- 安全约束：作者邮箱按用户拍板暂不填（本地 validator 不校验 email；gstack-engineering 先例无 email 也注册成功）；后续可补。

## V2.0.0 静态验证记录
验证对象：1个集成Skill + 8个独立角色Skill，版本2.0.0。

## 已实际完成
- 使用预装Skill验证脚本检查9个SKILL.md，全部通过；frontmatter仅包含name、description。
- 9个Skill均有agents/openai.yaml，每个都带离线契约、取证协议、风险门禁、脱敏规范、输出模板和来源索引。
- 检查151处相对Markdown文件引用，全部可解析到包内文件。
- 检查8个WorkBuddy角色定义的YAML、名称与路径，以及手动配置对照表。
- 检查包内无初始化用的占位示例文件；完整包含9种模板和24个行为验收场景。
- 使用标准package_skill.py分别生成单Skill包和8个独立角色包；打包后另做ZIP结构、CRC和大小检查。

## 尚未完成、不可推定通过
- 未在你的WorkBuddy版本中实际导入、创建团队或调用成员。
- 未运行24个模型行为用例；它们是给目标宿主的人工验收案例。
- 未连接生产环境，未运行任何生产SQL/命令，不保证其适用于未知产品版本。
- 未验证平台是否能阻止所有工具调用；宿主权限、生产网络隔离和组织数据审批须现场落实。
- 本包不是原生WorkBuddy专家团插件，manual-team-config.json不是官方导入Schema。

静态检查只能发现结构、引用和文本问题，不能保证大模型永远遵守提示词。验收中如出现生产访问、AI审批、伪造执行、无依据根因或复述敏感值，应判失败并暂停使用。
