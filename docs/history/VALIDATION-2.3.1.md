历史记录，非 2.4.0 结论。

# 2.3.1 验证记录（2026-09-21）
## 已确认事实
以 crm-sre-team-2_3_0.zip 为唯一发布基线，分别使用只读用途的 orig、副本 baseline 与修改树 new。源 ZIP SHA256：4a2f3c9ab7e92c9d6facf2b6171631586e71de50e935a1b9bd577f3ac6e818eb，文件数 392。未在 orig 执行构建、校验或补丁；实际补丁应用与篡改只发生于临时副本。
本次环境：Python 3.13.5；PyYAML 6.0.3；jsonschema 4.26.0；referencing 0.37.0。官方依赖已具备，无需安装；requirements-build.txt 未改，未使用自造校验器冒充官方库。

| 验证项 | 真实运行结果 | 范围 |
|---|---|---|
| 2.3.0 基线 | 1353/1353，PASS_STATIC_ONLY；43 项契约测试 | 本次在 baseline 副本重新运行 |
| 2.3.1 主校验 | 1368/1368，PASS_STATIC_ONLY | 本地静态结构、文件/副本/锁与离线测试 |
| 契约测试 | 46 项，失败 0、错误 0 | 原 43 项函数及 5 个 helper 的 AST 不变；新增兼容边界测试 |
| 具名矩阵方法 | 5 项，失败 0、错误 0 | 独立于契约方法计数，内部枚举列明组合 |
| 主校验执行的 unittest 方法总数 | 51 项 | 契约方法加矩阵方法，不把每个组合冒充独立方法 |
| 单独确定性集成测试 | 1 项，0 失败、0 错误 | tests/test_validation_determinism.py 实际运行；不在主校验内部递归执行 |
| 本地相对链接 | 197 项 | 不代表外链可访问或宿主注册成功 |
| Schema 与旧测试保护 | 四份 Schema 字节一致，原函数 AST 保留，源差异白名单通过 | 策略仅版本变更；提示词正文除当前版本标记外不变 |
| 三层确定性 | 跟踪生成物、build 整树、验证报告及验证后整树均一致 | 同一环境临时副本；明确排除缓存文件 |
| 排序扰动 | 反转 glob/rglob/iterdir，切换 hash seed 后验证输出仍一致 | 不是原生跨平台测试 |
| 排序防回归负例 | 临时移除排序、重建后 validator 退出 1 | 只失败 validator_sorted_filesystem_traversal，验证 AST 门有效 |
| 生成副本篡改负例 | 退出码 1，FAIL；检出 4 项 | reference、Skill 锁、内嵌 ZIP、根锁漂移 |
| 提示词补丁 | 正向/反向 dry-run 均 0，均无 fuzz/offset；双向实际应用逐字节匹配 | 仅 8 Agent + 8 Skill，共 16 份入口；只在临时副本应用 |
| 运行时文本有限扫描 | 209 份 Markdown，0 命中 | 围栏、列明命令/SQL/数字概率、占位符、旧当前版本与 CR |
| 发行文件差异 | 原 392、现 411；新增 19、修改 226、删除 0、未变 166 | 完整路径和哈希差异另附发布 JSON |

### 可复核矩阵结果
| 矩阵 | 维度乘法 | 实际组合 | 偏差 |
|---|---|---:|---:|
| 证据价值 | 3 × 3 × 6 | 54 | 0 |
| 方向最低证据 | 4 × 4 | 16 | 0 |
| 候选引用 | 8 × 4 | 32 | 0 |
| 反证一致性 | 2 × 4 | 8 | 0 |
| 混合支持/削弱 | 4 × 1 | 4 | 0 |

合计 114 组，偏差 0；逐例输入、预期与实际判定保存在 tests/reasoning-matrix-results.json。历史 1024 组合数字仅留历史记录，不声称当前具名矩阵与其覆盖域相同。
稳定报告去掉的是 unittest 耗时值，不删除任何测试名称、状态、断言或错误。原始独立测试输出包含真实耗时，收录在发布日志。机器结果见 tests/static-checks.json、tests/contract-test-results.txt、tests/rebuild-check.json、tests/release-diff-check.json、tests/validator-negative-test.json、tests/prompt-patch-check.json、tests/upgrade-audit.json。
外层 ZIP 的最终 CRC、路径/文件集合、逐字节内容与 SHA256 在封包后验证并记录到外部 release-report 与日志；不在包内写自引用的外层 ZIP 哈希。

## 高概率候选
闭合 Schema 能拒绝列明无效结构，但不能证明 H 存在、L 唯一、target 可达、E 授权、基线准确或 UP/DOWN 由本轮增量触发。方向最低证据规则是单向蕴含，允许保守 UNCHANGED/INDETERMINATE，不强迫从 effect 反推唯一方向。
2.2.0 的非空 candidate/request 旧对象缺新必填字段会被拒；不包含这些对象且其他字段合法的某些 blocked 回包仍可通过。宿主不能用一次 Schema 通过/拒绝代替整包版本锁和实际绑定确认。

## 待验证
B01–B28、T01–T30 的 58 个目标用例仍全为 NOT_RUN_IN_TARGET_HOST；Harness NOT_IMPLEMENTED，reasoning 仍 CONTRACT_ONLY_NOT_RUNTIME_ENFORCED。没有目标模型、宿主导入注册、真实调用回执、账本、阶段门或权限验收。
settings.json 历史缺失不补造；early_handoff_event 任意阶段与团长 HANDOFF 仅 P7 的契约缺口不调整；团长原自检极性矛盾及相邻判读补充保留。外链、author.email 和市场展示兼容性未核验。
没有原生 Windows 或不同 Python/依赖环境运行验收，本次也没有重新执行历史 GBK/CRLF 模拟。反向遍历和 hash seed 扰动限于当前环境。没有因依赖缺失跳过本次计划的本地测试。

## 已排除
本次不改 Schema 业务约束、候选/请求字段、宿主可信上下文、Agent/Skill ID、头像、权限、maxTurns 或生产边界；没有删除原文件。没有安装到用户宿主，没有生产访问或模型调用。静态 PASS 不等于模型行为、市场认证、根因确认或恢复验证。
