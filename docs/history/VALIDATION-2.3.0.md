历史记录，非 2.3.1 结论；其中迁移概括及矩阵数字请以当前文档为准。

# 2.3.0 验证记录（2026-09-21）
## 已确认事实
操作对象为上传 ZIP 的副本，orig 全程只读且逐文件哈希未变；baseline 单独运行原版校验，new 仅编辑源文件再重建生成物。原上传 ZIP SHA256：679518abfb96aa0a4c603f4ec51603a1bb6bc4e89599bd3cebe160fa2f284ea7。
本次真实环境：Python 3.13.5；PyYAML 6.0.3；jsonschema 4.26.0；referencing 0.37.0。依赖已可用，无需安装；使用官方 jsonschema.Draft202012Validator 和本地 URN Registry，没有用自造校验器替代官方库。requirements-build.txt 未修改。

| 验证项 | 本次实际结果 | 证明范围 |
|---|---|---|
| 原版基线 | 811/811，PASS_STATIC_ONLY；30 项单测、0 失败、0 错误 | 原 2.2.0 的静态与离线契约基线，不是目标宿主验证 |
| 新版完整校验 | 1353/1353，PASS_STATIC_ONLY | 文件、版本、JSON、frontmatter、本地引用、Schema、副本与独立 ZIP 一致性 |
| 新版单测 | 43 项，0 失败、0 错误 | 真实官方 JSON Schema 与策略测试；原有 30 项测试函数 AST 未改 |
| 相对 Markdown 链接 | 200 项通过 | 只验证本地路径，不代表外部网页可访问或官方认证 |
| 独立候选条件矩阵 | 1024 种组合，739 个预期拒绝，0 偏差 | 用官方校验器独立枚举 H/L、方向、反证状态与 effect 子集；旧 candidate/request 形状被拒 |
| 重复构建 | 9 个跟踪产物哈希一致 | prompt-bundles.lock 与独立 Skill ZIP；不声称整个外层 ZIP 永远同字节 |
| 篡改负例 | 校验器退出码 1，FAIL；检出 4 项漂移 | 仅在临时生成副本追加惰性标记，检出 reference、skill lock、内嵌 ZIP、root lock 漂移 |
| 提示词补丁正向/反向 | 各 16 文件；退出码 0 / 0，无 fuzz/offset | 原件临时副本正向 dry-run；新版临时副本反向 dry-run，原件未应用 |
| 默认编码/换行模拟 | GBK/CRLF 默认值模拟中构建与校验通过，9 个跟踪产物哈希不变 | pathlib I/O 默认值模拟；不是 Windows 原生实机验收 |
| 运行时文本扫描 | 209 份 Markdown，0 命中 | 代码围栏、列明命令/SQL 模式、数字概率模式、未渲染 COMMON 占位符；有限静态扫描 |
| 生成文本换行/版本 | 校验内逐文件检查通过 | 按字节检查无 CR；活动运行时无旧当前版本声明 |
| 文件集合对比 | 原 374，现 392；新增 18、修改 241、删除 0、未变 133 | 逐文件路径与 SHA256 对比；完整差异清单随外部发布报告交付 |

根版本锁 SHA256：86b9b83fe2976d6689f8484ba4ebc1b11555a6a8aee0f2a380b2c58447408b6e。
机器报告：tests/static-checks.json；单测输出：tests/contract-test-results.txt；重复构建：tests/rebuild-check.json；篡改负例：tests/validator-negative-test.json；补丁检查：tests/prompt-patch-check.json；独立审计与环境：tests/upgrade-audit.json。
2.2.0 原校验记录已在首次新版校验前保存为 docs/history/VALIDATION-2.2.0.md 与 docs/history/static-checks-2.2.0.json。旧 README/MIGRATION/MODIFICATIONS 原文另归档；历史数字不充当本次执行结果。

## 高概率候选
闭合 Schema 可拒绝新增权威属性与不一致的证据效应组合，版本锁可检出生成副本漂移。限制：Schema 不能证明 H 存在、L 唯一、target 真正可达、E 授权、基线真实，不能证明 UP/DOWN 来自本轮证据。残余风险测试明确让这类结构合法输入通过，宿主须另行拒绝。自然语言中的状态词、数字概率、因果或命令也不能仅靠字段闭合保证安全。

## 待验证
B01–B28 与 T01–T30 全部 NOT_RUN_IN_TARGET_HOST。没有调用真实模型，没有执行 WorkBuddy/CodeBuddy 目标宿主导入、注册、多 Agent 回执、状态/账本持久化、权限沙箱、语义/隐私门或唯一发布器测试。runtime-contract 的 implementation_status=NOT_IMPLEMENTED，reasoning 的 status=CONTRACT_ONLY_NOT_RUNTIME_ENFORCED。
2.1.0 历史记录提到 settings.json（agent=telecom-crm-sre-team-lead），当前包没有；须对照用户的 2.1.0 原包，本次不创建。
workflows.json 的 early_handoff_event 允许任意阶段受阻交接，而 roles.json 团长 HANDOFF 仅 P7；该契约缺口保持不动，没有新增提前交接任务或执行权限。
包内外部链接均未联网核验；vmstat 链接只去掉多余斜杠。原生 Windows 环境未运行，只有 GBK/CRLF 默认 I/O 模拟。无需因依赖缺失跳过的本地校验项；这不改变目标行为用例的未运行状态。
2.2.0→2.3.0 为破坏性 Schema 升级，宿主须整体更新并提供新增可信字段；无 Harness 时显式选择 MANUAL-MODE，不能伪造控制上下文。

## 已排除
静态 PASS 不等于模型行为 PASS、市场认证、审批、生产执行、业务恢复或 RCA 确认。没有生产访问、凭据获取、生产命令执行或用户账户配置修改。未扩大角色工具权限，未更改 Agent/Skill ID、头像、插件角色列表、原有 Schema 主体、blocked/feedback fixture 或既有测试断言。
本次执行中的歧义处理见 MODIFICATIONS.md 的“决策记录”；不以继续增加提示词冒充已实现的 Harness。
