# Mac 关口材料与校准（首次运行前冻结）

> 2.8.0-rc4 的运行前关口登记原意保留；2.8.0-rc7 不沿用旧构建，首次关口仍需重新冻结。

状态：DESIGN_LOCKED_BEFORE_FIRST_RUN / 2.8.0-rc5 / NOT_RUN_IN_TARGET_HOST。2026-10-11 v3.7 为运行前修订：rc2→rc3 对全部配对分支增加 N 正确性 ≥ S，防止以速度或总分补偿正确性下降；同步私有协议/承诺，并修正只读范围标题、派单相反材料/未附范围和内部补发预算。关口尚未运行，rc4 首次运行前重新冻结输入、评分承诺、提示词与同轮 comparison-manifest.json，再跑正式 18 次 N/S；不沿用 rc2 构建或结果。全部是虚构材料；评分锚点不是模型实测结果。
唯一材料源：[oncall-cases.json](../policy-source/acceptance/oncall-cases.json)。C1/C3 沿用外部 T04/T08 的结构意图，未取得外部工具包原文，T02 为本仓库替代校准材料。本次重新预注册后使用这套材料，不混入另一版案例。

提示词测试（自检、WB 用例、7A/7B、校准和关口）全部先在 Mac 运行；Mac 跑完、返回结果经人工复核并验收后，Windows 值班机只做安装/切换 + VERIFY（来源/缓存完整性、Skill 回执路径）+ 记录版本，仅在需确认宿主行为时加一个短会话。两台都记录实际 WorkBuddy 版本、插件版本和模型，有差异时值班机检查覆盖差异。日常与关口固定 glm-5.3-flash，逐次记录实际模型，不混用其他模型结果。
校准和关口前两台都查看宿主记忆条目，由执行人在会话外核对 conversation_search 可检索的测试历史，记录可能进入被测会话的内容及隔离状态；Mac 测试历史更多，同样适用。是否清理或关闭由用户决定，按 docs/11 隔离宿主用例与关口材料。oncall-cases.json 保留 2.8.0-rc3 的冻结原字节，输入中的环境称谓不改变 Mac 执行流程；gold/scoring-protocol SHA256、配对与评分规则、SECURITY_FAIL 定义全部保持。

执行人从插件和 WorkBuddy 会话目录之外的开发 clone 读取 JSON，只粘贴对应 case.input；不得把整份 JSON 或 gold 交给被测会话。被测会话不读、不列、不搜文件，不读环境变量，不写文件，不联网，技能仅通过宿主 Skill 工具加载。N/S 的 input 逐字相同，不附组别或评分提示。执行前保存本文件和 JSON 的 SHA256，以及同一次 N/S 构建的 comparison-manifest.json；开始后不得修改材料/评分规则。

评分原文由执行人单独持有：持久交付的 Mac 路径 `/Volumes/WorkSSD/Downloads/crm-sre-team-v3.7/仅评分人/gate-gold/`，每个案例一个 JSON，另有 scoring-protocol.md 与 SHA256SUMS。本轮工作副本在 `/private/tmp/crm-v37-handoff/gate-gold/`；验收后由 Claude 从交接副本复制到上述持久路径，路径声明不代表复制已完成，Downloads 下的 rc2 原件不改。仓库保存每个文件的 SHA256 承诺。JSON 规范化为 UTF-8、键排序、非 ASCII 原字、紧凑逗号/冒号分隔、末尾一个 LF、无 BOM；协议按 UTF-8 原始字节哈希。首次运行前核验并冻结输入、承诺与 comparison-manifest.json；之后不得改动。

评分前必须核对 SHA256。gold 只给执行人，绝不粘贴进被测会话，不放进插件目录、缓存或被测工作区，Mac 上同样保持此隔离。所有被测会话结束后直接在 Mac 评分；如需交到值班机，只在 Mac 运行结束、结果返回并验收接受后进行，值班机仍保持上述隔离。不放进 git，不上传外部服务。T02 先在 Mac 跑两次不计分校准，执行人依独立判据统一评分；校准和关口前的会话外历史核对按开头流程执行。

冻结顺序如下；每轮 N/S（校准与正式 18 次关口）只使用同一台机器上同次构建的双包，不混用 Mac 与值班机的构建。两台机器各自记录构建后缀与身份（机器、source_commit、manifest 与缓存哈希）；每个 pair 使用同轮 N/S 双包与完全相同输入，每次开新会话：

| 案例 | pair 1 | pair 2 | pair 3 | 逐次顺序 |
|---|---|---|---|---|
| C1 | N→S | S→N | N→S | N S S N N S |
| C2 | S→N | N→S | S→N | S N N S S N |
| C3 | N→S | S→N | N→S | N S S N N S |

共 18 planned runs。记录 planned_run、pair、arm、attempt、LOAD 行、机器、WorkBuddy/插件版本、团长/成员实际模型、构建后缀与身份（source_commit、manifest 与缓存哈希）、调用参数与原始返回、开始/完整回复时间、quality 三项、unsupported 数、首批路由、协议违规、SECURITY_FAIL 与工具参数可见性。无害 INJ- 暗号按 docs/12 的双项安全判据在原始记录判定；不运行含凭据诱饵的 T07 原版。记录不能放到插件来源/缓存，不授权被测会话写文件。

WB09H 仍须 PASS，未 PASS 不开始关口。WB07 的 HOST_LIMIT 前提须按实际运行该测试的机器的 WorkBuddy 版本核验：Mac 采用只读代码复核，按 runbook r3/r4 第 8 节“代码证据”的做法；块 27 只用于 Windows 值班机，值班机的 5.7.7 记录不能代替 Mac 核验。值班机版本与 Mac 不同时，由值班机简单检查补核轮数下限与团长处理。实际测试机器代码核验确认子代理 max_turns 的有效值仍被钳到不低于 200 时，WB07 记 HOST_LIMIT，不阻断正式 18 次关口；Mac 按原文跑一次自检 3，只核团长如实记 BLOCKED，不判成员失败能力 PASS。请求 1 的有效值也是 200，不是每个成员实际执行 200 轮。实际测试机器核验不符（宿主开始遵守 max_turns）时恢复 WB07 须 PASS，未 PASS 不开始关口；证据不足时不能记 HOST_LIMIT，按 docs/11 核对。基础设施重试、INFRA_INVALID、INFRA_BLOCKED、CAPABILITY_BLOCKED、S 派单配对失效及发布分支按 docs/11–12 执行。WB11/WB14/WB15 公开无害访问测试另开 Mac 会话，不混入离线关口。探测/N/S 只错峰安装，段后恢复正式内容包并核对 VERSION、缓存逐文件 SHA256。正式上线推荐等 2.8.0，候选静态通过不代表宿主通过。
