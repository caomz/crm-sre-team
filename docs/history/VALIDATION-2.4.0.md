历史记录，非 2.5.0 结论。

# 2.4.0 验证记录（2026-09-21）
## 已确认事实
本次真实操作上传 2.3.1 包的副本，orig 始终不运行写文件脚本，baseline 只作原版复跑，new 只改源后构建。原 ZIP SHA256：d0a1a1f6a71be2077cbcdcfd54ed9514d85e7accb6e7f7efaba08c7618acd8ec；原始文件数 411，已逐字节核对原目录未变。
实际环境：Python 3.13.5；PyYAML 6.0.3；jsonschema 4.26.0；referencing 0.37.0。依赖已具备，无安装、无自造校验替代。使用官方 Draft202012Validator 和本地 URN registry。

### 实际执行
| 检查 | 结果 | 解释 |
|---|---|---|
| 原 2.3.1 基线 | 1368/1368，PASS_STATIC_ONLY | 51 个方法，原契约和推理矩阵 |
| 本版主校验 | 1448/1448，PASS_STATIC_ONLY | 文件、锁、副本、Schema/策略离线检查 |
| 原契约方法 | 46，失败 0，错误 0 | 原函数 AST 保持不变 |
| 新判断依据方法 | 28，失败 0，错误 0 | 包括结构正反例及语义残余风险证明 |
| 原推理矩阵方法 | 5，失败 0，错误 0 | 114 组，0 偏差 |
| 判断依据矩阵方法 | 4，失败 0，错误 0 | 362 组，0 偏差 |
| 主校验方法总数 | 83 | 不把矩阵内部组合当额外 unittest 方法 |
| 独立确定性集成测试 | 1 项，0 失败、0 错误 | 已单独真实执行；不在主校验内递归调用 |
| 本地相对链接 | 206 | 不代表外链可访问或宿主导入成功 |
| 运行时有限扫描 | 217 份 Markdown，0 命中 | 仅列明的代码围栏、命令/SQL、概率文字、旧版号及占位符模式 |

### 具名矩阵：列明范围，不等于语义验真
| 矩阵 | 实际组合 | 预期接受 | 预期拒绝 | 偏差 |
|---|---:|---:|---:|---:|
| reasoning / effect_mapping | 54 | 11 | 43 | 0 |
| reasoning / direction_minimum_evidence | 16 | 10 | 6 | 0 |
| reasoning / candidate_reference | 32 | 10 | 22 | 0 |
| reasoning / counterevidence_consistency | 8 | 4 | 4 | 0 |
| reasoning / mixed_evidence_direction | 4 | 4 | 0 | 0 |
| judgment / reference_expectation_effect | 324 | 56 | 268 | 0 |
| judgment / reference_ref_count | 24 | 11 | 13 | 0 |
| judgment / question_answer_basis | 8 | 5 | 3 | 0 |
| judgment / discrimination_shape | 6 | 2 | 4 | 0 |

合计 476 个具名组合，偏差 0。逐例输入与预期/实际结果在 tests/reasoning-matrix-results.json、tests/judgment-matrix-results.json；不声称与历史大矩阵覆盖域等价，不证明实际参考可比或模型更准。

### 源契约保护
source-diff 通过；46 项原测试函数与 5 个辅助函数 AST 保持。将新增定义、字段与条件投影移除后，common Schema 与基线结构完全相同；其他结果/反馈 Schema 字节未变。原矩阵只增加新必填 fixture 字段，没有改维度或预期判断函数。角色、权限、旧策略业务值、头像、元数据列表与 maxTurns 未变。
本次发行树 443 文件：新增 32、修改 256、未变 155、删除 0。文件对比不包括临时缓存。历史文件保留，非空旧候选/请求回包保留为实际迁移负例；空 blocked 的兼容边界未放宽。

### 确定性、故障注入与补丁
9 个跟踪产物（根锁与独立 Skill ZIP）重复构建哈希一致；两次构建完整发行树无内容漂移。重复 validate 及反向 Path.glob/rglob/iterdir、哈希种子 23, 731 扰动后，四份稳定报告和验证后整树一致。仅限当前 Python/依赖环境，不是原生多平台验收。稳定日志只去掉耗时，原始直接输出另存发布日志。
生成的 evidence-protocol 副本被追加无害标记后，校验器退出 1，结果 FAIL，检出 4 个副本/锁/独立包漂移检查。
移除新增无参考约束并重新构建全部哈希后，根锁仍合法，但判断依据单测和矩阵使校验器退出 1；新矩阵出现 10 个偏差。这是有意故障注入结果，不是正式版失败。
临时提高旧策略专家额度后，源审计退出 1；移除排序并重建后，确定性工具确认校验器退出 1 并命中排序防回归检查。
当前提示词补丁含 8 份 Agent 和 8 份 Skill：双向 dry-run 退出 0、无 fuzz/offset；临时副本实际双向应用后逐字节相等。原目录未应用补丁；该补丁不能代替整包/Schema 升级。

## 高概率候选
判断结构更完整是否提高诊断质量仍需模型实验。没有参考时填 UNKNOWN 不是错误；保守方向合法，也不能仅凭空 blocked 通过说明成员已升级。新增参考、子问题和请求集合的语义必须由宿主复核。

## 待验证
Harness NOT_IMPLEMENTED；reasoning/judgment 均 CONTRACT_ONLY_NOT_RUNTIME_ENFORCED。B01–B36、T01–T38 共 74 个用例均 NOT_RUN_IN_TARGET_HOST。J01–J08 共 8 个合成评估设计均 NOT_RUN_IN_MODEL / NOT_SCORED；没有真实裁决、采集器、Brier 或校准结果。
没有真实模型、WorkBuddy/CodeBuddy 导入注册、调用回执、生产访问、原生 Windows 或跨依赖环境验收。settings.json 未创建；early_handoff 任意阶段与 HANDOFF 仅 P7 的缺口未改；团长自检极性原文与补充判读保留。外链和市场字段未联网核验。
结构上合法的未知 H、重复局部 Q、不可比参考、非目标子集、无区分请求和自由文字数值概率，仍可能通过 JSON Schema；新残余风险测试明确展示这一点。不能把单测通过当成这些宿主语义门已实现。

## 已排除
本版未扩生产权限、未修改旧 OODA/反证条件、未把指标代理包装成概率校准或模型性能提升。一次批量工具调用在独立集成测试结束前达到外部执行时限，未取得结论；随后单独重跑取得 integration-final 的成功结果，不把中断日志计为通过。
所有最终封包、unzip CRC、解压后复跑和逐文件哈希结果由外部发布报告及日志记录，不给本文件或外层 ZIP 求自引用哈希。
