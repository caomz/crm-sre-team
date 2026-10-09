# 值班机关口材料与校准（首次运行前冻结）

状态：DESIGN_LOCKED_BEFORE_FIRST_RUN / NOT_RUN_IN_TARGET_HOST。全部是虚构材料；评分锚点不是模型实测结果。
唯一材料源：[oncall-cases.json](../policy-source/acceptance/oncall-cases.json)。C1/C3 沿用外部 T04/T08 的结构意图，未取得外部工具包原文，T02 为本仓库替代校准材料。本次重新预注册后使用这套材料，不混入另一版案例。

执行人从插件和 WorkBuddy 会话目录之外的开发 clone 读取 JSON，只粘贴对应 case.input；不得把整份 JSON 或 gold 交给被测会话。被测会话不读、不列、不搜文件，不读环境变量，不写文件，不联网，技能仅通过宿主 Skill 工具加载。N/S 的 input 逐字相同，不附组别或评分提示。执行前保存本文件和 JSON 的 SHA256，以及同一次 N/S 构建的 comparison-manifest.json；开始后不得修改材料/评分规则。

评分原文由执行人单独持有：Mac 路径 `/Volumes/WorkSSD/Downloads/crm-sre-team-v3.5/gate-gold/`，每个案例一个 JSON，另有 scoring-protocol.md 与 SHA256SUMS。仓库保存每个文件的 SHA256 承诺。JSON 规范化为 UTF-8、键排序、非 ASCII 原字、紧凑逗号/冒号分隔、末尾一个 LF、无 BOM；协议按 UTF-8 原始字节哈希。首次运行前核验并冻结输入、承诺与 comparison-manifest.json；之后不得改动。

评分前必须核对 SHA256。gold 只给执行人，绝不粘贴进被测会话，不放进插件目录、缓存或被测工作区。建议所有被测会话结束后才手动交到值班机，或直接在 Mac 评分。不放进 git，不上传外部服务。T02 先跑两次不计分校准，执行人依独立判据统一评分。

冻结顺序如下；每个 pair 使用同轮 N/S 双包与完全相同输入，每次开新会话：

| 案例 | pair 1 | pair 2 | pair 3 | 逐次顺序 |
|---|---|---|---|---|
| C1 | N→S | S→N | N→S | N S S N N S |
| C2 | S→N | N→S | S→N | S N N S S N |
| C3 | N→S | S→N | N→S | N S S N N S |

共 18 planned runs。记录 planned_run、pair、arm、attempt、LOAD 行、客户端/团长/成员模型版本、调用参数与原始返回、开始/完整回复时间、quality 三项、unsupported 数、首批路由、协议违规、SECURITY_FAIL 与工具参数可见性。无害 INJ- 暗号按 docs/12 的双项安全判据在原始记录判定；不运行含凭据诱饵的 T07 原版。记录不能放到插件来源/缓存，不授权被测会话写文件。

WB07 或 WB09H 任一未 PASS，不开始关口；基础设施重试、INFRA_INVALID、INFRA_BLOCKED、CAPABILITY_BLOCKED、S 派单配对失效及发布分支按 docs/11–12 执行。WB11/WB14/WB15 公开无害访问测试另开会话，不混入离线关口。探测/N/S 只错峰安装，段后恢复正式内容包并核对 VERSION、缓存逐文件 SHA256。正式上线推荐等 2.8.0，候选静态通过不代表宿主通过。
