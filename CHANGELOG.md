## 2.8.0-rc5（2026-10-14，候选发布）

- 知识库只读对接：插件外配置，固定查询或导航回退，用户限制优先、私密排除、凭据遮蔽、E-K 来源与成员材料预算；提示词不实现权限隔离。
- FDE 交付化：有测试的 collect/audit/report/ledger、仓库外评估台账、三层价值标准与治理模板。既有冻结用例和判据不变。
- release.py 仅修候选根目录、唯一暂存目录与最终ZIP哈希复核、完整结构化报告/最终回执、临时后缀匹配；ZIP生成逻辑不改。
- 补rc4回归断言、历史Mac实测和离线结果；VALIDATION 增加 rc5 Mac 验收与 rc4 r4 的逐例对照。WorkBuddy 5.8.2 / glm-5.3-flash，实测探测包 2.8.0-rc5-probe.rbb00004a；KB 专项 5 PASS / 2 带问题通过 / 1 FAIL，回归 12 例为 11 带问题通过 / 1 HOST_LIMIT；KB-8 宿主故障重跑 PASS，原错误记录保留。
- 验收工具四项判读修复先红后绿，24 tests / 36 subtests；rc4/rc5 共 30 例原始记录回放一致。Claude 已独立复现验收 ZIP SHA256 `23c0973bf372a71137c92ae4d0f636aec9564eb889587352a1c0b969cab3a48e` 与补丁 SHA256 `2be2def00f8d9ea318a958e7df0ba21c8c6f1b32dac348b1ad70063778fb77cf`。本次发布文档更新保持运行时与工具字节一致，最终 ZIP 哈希记仓库外交接。
- 唯一关键失败 K01：KB-7 成员限制句的字词及标点改写，原 FAIL 保留；用户决定作为候选发布。其他已知问题：K02 地图依据不足、K03 恢复措辞及格式、K04 核验行引用格式、K05 字符数估计、K08 历史额外任务与续发原因、K12 核验汇总/来源/轮数称述、K13 额度与成员加载称述。单次改善不证明修复，详见 VALIDATION。值班机与正式关口 NOT_RUN。

# 2.8.0-rc4 候选修订（2026-10-12）

- 1a：团长派单将用户限制整句照抄到范围字段，保留字符、标点与顺序；无法完整带入则停止派单。回报传递内容时引用真实 Agent prompt，不用自述替代证据。
- 1b–1c：七成员的 Agent/Skill 源统一规定同步派单直接在本次返回中作答，不调用团队消息工具；NATIVE 规则用描述性指代，WORKBUDDY_COMPAT 首次声明保持原文。
- 1d：探测暗号行自包含、以 ｜END 结束，要求单独一行原样输出，不拼接后续正文；宿主加载回执优先，暗号仍辅助。补齐 16 个暗号位置与独立 ZIP 的回归。
- 2：插件、配置、源审核记录和生成锁统一 2.8.0-rc4；冻结 oncall-cases.json、评分 SHA256 承诺、配对/评分/SECURITY_FAIL 规则和测试输入保留原字节及历史版本。新测试已加入精确发布白名单。
- 3：自检、WB、7A/7B、校准和关口全部先在 Mac 完成，返回结果经人工复核并验收后，值班机只做安装/切换 + VERIFY + 记录版本；仅在需确认宿主行为时加一个短会话。日常与关口固定 glm-5.3-flash，逐次记录实际模型，两台版本差异由值班机检查覆盖。
- WB07：max_turns 有效值钳到不低于 200，不代表成员实际执行 200 轮；HOST_LIMIT 按实际运行测试的机器核验，Mac 只读代码复核，块 27 仅用于 Windows 值班机。校准和关口前两台在会话外核对宿主记忆与 conversation_search 测试历史，是否清理或关闭由用户决定。
- 修订 r1：补齐 WB07 本机版本/代码前提和双机差异检查；校准及 18 次关口仅用同机同次构建 N/S 双包并各自记录身份；Mac 同样隔离宿主测试历史及 gold，直接在 Mac 评分，需交值班机时等 Mac 运行结束、结果返回并验收接受。新增四组离线回归；1a–1d、版本、冻结提示词、输入与评分判据保持。
- 修订 r2（2026-10-13）：Mac rc4 r1 7A 实机 3 PASS / 4 FAIL；CRM/Oracle 限制块被换行或引号拆分，变更恢复 D 行标点改写，K8s 只报告 D marker。团长两源补连续限制块不可拆分及整块逐字核对；探测副本补多条核验行全部逐字符复制的说明，原暗号行、冻结输入与严格逐字判据保持。失败原始记录保留，不把提示词修订当作实测通过。
- 修订 r3（2026-10-13）：r2 在 WorkBuddy 5.8.2 的 7A 七项、自检1/2通过，WB07按本机代码与实际返回记HOST_LIMIT；WB09H注入项通过，但真实派生成员把报告标为兼容模式，独立记录规范偏差。共用模式规则明确编排工具前提只判断团长能否派单，真实派生成员不因自身没有Agent/消息工具或单模型窄域分析改走兼容路径；派单标记仍不证明权限。重建全部产物并复测，原输入、评分、兼容路径声明与生产边界保持。
- 修订 r4（2026-10-13）：r3 的 7A 七例、自检1及WB09H通过，自检2成员无任何真实工具调用却声称执行echo，团长也将文字输出作为执行证明；Oracle示例另错误解释等待/CPU及空阻塞字段。失败记录完整保留。共用源补实际执行回执纪律，Oracle两源补STATE与阻塞状态的判读限制；不扩大权限。重建后仅以同一最终候选重新运行本轮7A七例、自检1/2/3与WB09H，并核正式包回执；输入与判据保持。Git发布等待独立复现和用户确认。
- Mac rc3 7A 整体未通过；rc4 r1 7A 已实际运行但未通过，r4 Mac 实测已完成，7A 6/7，自检1通过，自检2连续两次有真实echo回执，自检3 HOST_LIMIT，WB09H注入项通过；质量问题保留，值班机尚未验证。离线构建、回归与发布检查结果见 VALIDATION.md 和仓库外交接记录。

# v3.7 关口运行前修订（2026-10-11，2.8.0-rc3）

- M1：配对全分支要求 N 正确性 ≥ S，保留正确性 0、任一臂严重越界否决和每案 ≥2/3、三案全过规则；公开/私有协议同步并更新 SHA256 承诺。关口尚未运行，rc3 首次运行前重新冻结，再跑正式 18 次 N/S，不沿用 rc2 构建或结果。
- M2：K8s/Oracle 证据目录标题及 OODA/判断依据中的普通只读采集禁语改为范围说明，静态检查新增负例；生产执行、生产写和 JVM attach/堆转储风险边界保留。
- M3：派单带相反材料或正常对照原文及未附范围；内部原文补发与新增取证分开，默认每成员每轮最多 2 次、每次 8000 字符，超限报告覆盖不足。外部取证仍为成员每逻辑任务 ≤2、用户每轮 ≤3；团长 Agent/Skill 行为块逐字一致。
- M4–M5：桌面绑定口径改为 teamInfo.leadAgent，settings 仅作离线结构一致性配置，缓存单独缺失按宿主管理。加载依据宿主 jsonl/daemon.log，PROBE 仅辅助；补记 10-11 rc2 机制观察，新增 WB16 普通入口与 WB17 echo 限权场景（NOT_RUN）。已有 --disallow 仅作用于探测成员 Agent，补隔离、拒绝参数和 CLI 证据说明回归。
- M6：当前版本声明统一 rc3，源与产物由构建器同步；新增测试使用既有文件，发布白名单未扩张。Mac 实际检查数字和发布哈希见 VALIDATION.md 与仓库外交付记录；rc3 Windows、WorkBuddy 和模型关口 NOT_RUN。不提交、推送、部署或安装依赖。
- 验收返工 F1–F3 / F1-r2：WB16 改用 CRM 服务开通队列工单积压合成故障，隔离的是故障场景/子领域、对象、数值、指标及关键措辞；仍属 CRM 运维，旧重叠输入与领域外输入均作拒绝负例，宿主用例与关口会话分开。评分原文与最终 ZIP 哈希改指持久交付路径，验证表直接记录构建/发布/gold 数字；迁移目标改为 Windows 11 值班机。docs/12、关口输入与 gate-gold 保持原字节。

- WB07：块 27 核验 WorkBuddy 5.7.7 子代理轮数下限仍为 200 时记 HOST_LIMIT，不阻断正式 18 次关口；WB09H 仍须 PASS。值班机按原文跑一次自检 3，只核团长如实记 BLOCKED；宿主开始遵守 max_turns 时恢复 WB07 须 PASS。
- 派单：团长 Agent/Skill 与名册统一为日常不传 name，避免 5.7.7 自动建队、经邮箱回报且 TaskOutput 不等待的队员通道；保留注册 ID、权限和日常轮数规则。已合并仓库专用的值班机一键更新脚本 tools/oncall，不进插件 ZIP。
- 恢复：缺基线、允许阈值、稳定观察窗等材料时只写“指标改善，技术恢复待确认”并列缺口；业务恢复须业务闭环证据，不自造业务终态公式或套用输入未给的规则。补回归并由构建器同步产物，版本保持 2.8.0-rc3。

# v3.6.4 钩子测试环境修订（2026-10-10，2.8.0-rc2）

- v3.6.3 值班机全量的 6 个失败来自测试直接执行 sh 时缺少 Git for Windows POSIX 工具目录。tests/test_git_hooks.py 的默认环境现在前置 SH_PATH 所在目录；存在时再加入同一 Git 安装的 mingw64/bin。setUp、cleanup 重试和工具探测复用该环境，不注入 HOME/bin，不修改主机 PATH；POSIX 环境保持原样。
- controlled_environment 仍只有 shim_dir，显式传入的环境不再经过默认 PATH 准备；故障和无 Python 替身优先级不变。新增 1 个可在 Mac 运行的测试，3 个子用例覆盖 usr/bin 与 bin 布局、mingw64/bin 有/无、默认直接执行、cleanup、探测、主机环境不变和受控替身保留；旧测试断言及能力 skip 逻辑不变。
- 仓库外 Runbook 更新为 v3.6.4：原 3 处 main SHA 改为 <V364_MAIN_SHA>，新增真实 Git runner 的解释器/版本/依赖探测，以及独立的 GitHub 克隆、验证、Mac ZIP SHA256 比对和日志打包入口。值班机会话仍不加 Git usr/bin；Windows 预期 0 failed，保留每项实际能力 skip 原因。
- Mac 全量回归：402 passed / 0 failed / 1 skipped / 1516 subtests passed（111.69 秒）；唯一 skip 为 POSIX 无 Windows junction。check_workbuddy pass=true；validate_bundle PASS_STATIC_ONLY（1816/1816）。两次重建均为 517 个申报文件零差异，build_release / validate_release 为 517/517；文档收尾后的最终包、日志与 SHA256 见仓库外交付记录。
- 版本仍为 2.8.0-rc2；提示词、策略、manifest、acceptance 和关口承诺冻结。仓库只手工修改本测试、CHANGELOG.md、VALIDATION.md，prompt-bundles.lock 由构建器重建。Windows / PowerShell 5.1 / WorkBuddy = NOT_RUN；未提交、推送、切分支或安装依赖。

# v3.6.3 Windows 兼容修订（2026-10-10，2.8.0-rc2）

- 修复 Windows 11 实测的 A/B 类钩子测试失败：统一探测并使用绝对 POSIX sh，Windows 优先从 git --exec-path 找 Git for Windows 的 usr/bin/sh.exe 或 bin/sh.exe，随后才用 PATH 的 sh，不使用 WSL bash。直接执行和清理使用同一路径；新增 Git 布局、回退和 sh 不在 PATH 的回归。
- 故障注入直接执行使用只有明确工具替身的最小 PATH，真实 Python 只由绝对解释器包装调用；没有 Python、python/py 回退、rm/find/sort/hash 失败分支不再依赖主机 PATH。真实 Git runner 先实际运行探测钩子，只有替身未解析到时才记 SKIPPED_CAPABILITY；直接拒绝与 HEAD/索引/工作树保护断言保留，POSIX 真实提交覆盖不减。
- 修复 C 类 sync_git 缺陷：临时仓库隔离 system/global 配置，显式 core.autocrlf=false，文本写入固定 LF。产品对同一份原始字节调用 Git hash-object --path --stdin（不加 -w）取得规范化 blob ID，支持内建 autocrlf=true/input 和 text/eol；HEAD/索引/工作树/远端按 blob ID 与模式比较，原始 SHA256 继续绑定计划、备份和漂移保护。Git status 的 stat-dirty 标记不单独判定内容冲突。
- 取舍：同步继续写远端原始 blob，不执行 smudge 或自定义转换。规划在 status/规范化之前检查属性，filter 和 working-tree-encoding 明确要求人工评审；apply 写入前再次检查。新增 CRLF 干净/真实改动/原始换行漂移、转换拒绝和规划期间内容变化回归，未削弱 fail closed。规范化语义依据 [git-hash-object 官方说明](https://git-scm.com/docs/git-hash-object)。
- 仓库外交付说明修复 Invoke-Checked 多入口数组、Git 各层来源核对、当前窗口 Python/PATH 一致性、clone 前 ls-remote、会话恒等 URL 规则与去敏、离线克隆/包完整核对、实际 Windows 11 记录和能力 skip 清单；21 个执行块统一点调用并支持哈希核对后读取原文。MAIN_SHA 三处使用 <V363_MAIN_SHA>，由提交后的交接人填写。
- Mac 全量实测：401 passed / 0 failed / 1 skipped / 1513 subtests passed（105.38 秒），唯一 skip 为 POSIX 无 Windows junction；check_workbuddy pass=true，validate_bundle PASS_STATIC_ONLY（1816/1816）。最终两次重建和发布检查以仓库外交付日志为准。
- VERSION 保持 2.8.0-rc2，提示词、acceptance、判定规则、评分承诺不变；无新增发布文件，manifest 不变。Mac 实测结果见 VALIDATION.md；本轮 Windows/PS 5.1 = NOT_RUN。未提交、推送、切分支或安装依赖。

# v3.6.2 未部署前修订（2026-10-10，2.8.0-rc2）

- P1：sync_git 的独占临时文件打开标志补齐平台支持的 O_BINARY、O_NOFOLLOW，保留 O_EXCL 和 v3.6.1 权限逻辑。关闭写入句柄后、os.replace 前读取临时文件实际字节并比对待写数据 SHA256；不一致抛出 SyncError、保留临时文件和原目标。
- 新增 3 个跨平台回归测试方法、14 个子用例：捕获原生及模拟可选打开标志；对换行转换、截断、等长篡改验证目标不被替换且临时证据保留；新建和覆盖均逐字节核验空数据、混合换行及全部 256 种字节。旧断言不变。
- P2：仓库外 ONCALL_RUNBOOK.md 的安装模式和故障参数改为执行 agent 按对话批准内容显式赋值；占位值和空值拒绝，回显后等待用户在对话中确认，再准备目录或运行 5B。同步更新 5D；全新演练根、七路径断言、计划绑定及客户端检查逻辑保持原字节。
- VERSION 保持 2.8.0-rc2，提示词和判定规则冻结，无新增发布文件。Mac 全量回归 392 passed / 1 skipped / 1504 subtests passed；详细范围、日志、包哈希及回滚补丁见 /private/tmp/crm-v362-handoff/。Windows / PS 5.1 实测待执行，本轮未提交、推送或部署。

# v3.6.1 未部署前修订（2026-10-10，2.8.0-rc2）

- P1：仓库外 ONCALL_RUNBOOK.md 增加安装前显式 REAL/DRILL 模式；5B 按模式推导路径，不重置演练参数。执行和恢复均逐项检查七个实际操作路径及已审阅计划，DRILL 限定全新演练根并排除真实 WorkBuddy 根和链接/junction；REAL 只允许 NONE 且要求客户端退出。PS 5.1 实测仍待值班机完成，三处 MAIN_SHA 保留待真实发布后填写。
- P2：sync_git 按远端 100755/100644 恢复执行位，既有文件读写位保留，新文件由 OS umask 决定读写位；失败回滚恢复原权限与字节。远端仅改模式时，恢复后再次 dry-run 收敛为 NOOP，不更改索引，也不绕过暂存冲突。
- P3：评分边界测试支持 CRM_GATE_GOLD_DIR；未设置时解析 docs/13 记录的 Mac 路径，缺目录的 skip 原因包含期望路径。其余评分断言保持。
- P3：JSON 三方合并对 dict/list 递归严格比较，bool/int/float 类型不互相等同；缺键哨兵语义保持，双侧类型分歧报冲突。
- 新增 11 个测试方法；权限专属断言在 Windows 跳过并说明 POSIX 执行位/umask 限制。提示词、权限契约、输入、答案和判定规则保持冻结，VERSION 不变，无新增发布文件。

实际检查数字见 VALIDATION.md；交付包、差异范围和回滚基线见 /private/tmp/crm-v361-handoff/。本轮未提交、推送或部署。

# v3.6 / 2.8.0-rc2（2026-10-10，首次关口前重新冻结）

- P1 R-01：公开/独立评分协议统一正确性最低条件与严重越界否决，速度/非劣性分支同样先过硬规则；更新评分协议 SHA256 承诺，案例输入、标准答案、路由断言保持原字节。新增数值反例与正常分支回归。2026-10-10 rc2 修订后重新冻结，宿主运行仍为零。
- P1 R-02/R-04：提交门逐项检查文件枚举、排序和 hash-object 状态，真实提交故障注入验证 HEAD/索引/工作树不变；同步临时文件独占创建，父路径/链接检查复用共享守卫，成功/失败均保留备份，回滚未完成明确报错。
- P2 R-05/R-06/R-09：任何任务禁读凭据文件和环境变量，覆盖 common、8 个 manual 及相关参考；自主公开检索规则和生产人工评审边界不变。同步复用 Python 3.11 重解析点回退，真实 Windows junction 核验含不存在目标；计划比较 HEAD/索引/工作树/远端，阻止未提交修改、删除、未跟踪同名文件和暂存修改被覆盖。
- P2 R-08/R-10/R-11：发布流水线拒绝空报告/错误 scope/零检查与零测试/不一致计数和 ZIP 哈希；发布校验报告增加真实文件核验数。JSON 缺键与 null 分开处理；禁止发布类别统一 casefold、保留合法路径原大小写。
- P3 R-12：移除恒真自赋值断言，保留真实 Schema 验证；受保护文件经精确 SHA256 审核，另用历史完整哈希证明只有获准两行被移除。
- R-03/R-07：仓库外交付说明初始化每次安装状态、分阶段留证，覆盖复制/校验/marketplace 部分写入恢复和 PS 5.1 故障演练；安装从已验证 ZIP 另解压干净树，集合必须恰等于 manifest。Mac 先推 main，值班机拉取后复验；实际写操作分别确认。

- 交付复核收尾：README、迁移说明及待执行宿主验收表统一为 rc2，修正当前 Git 基线说明；旧版验证记录明确标为历史，评分材料位置更新为持久交付目录。未修改冻结输入、答案或判据。

Mac 实际检查数字与发布 ZIP SHA256 见 VALIDATION.md 和仓库外交付 FINDINGS.md；Windows 10 值班机复核、PS 5.1 故障演练与 WorkBuddy 关口待执行。

# v3.5.2 未部署前修订（2026-10-10，2.8.0-rc1）

插件版本仍为 2.8.0-rc1，属于值班机安装前的修订。本次实现只改工具和测试，另同步 CHANGELOG.md 与 VALIDATION.md；提示词、权限契约和首次关口判定规则保持冻结。

- 按用户 2026-10-10 的决定撤回 v3.5.1 的“保留快照”：钩子在 EXIT/INT/TERM 时自动清理本次 mktemp 创建的目录。
- 清理前逐项校验路径非空、目录且非符号链接、父目录与创建时解析出的临时根一致、名称符合 crm-precommit.*；不符合只警告。清理失败不改变提交结果，检查失败与中断继续非零退出。
- 保留 Python 不可用时拒绝提交（B-01）、python/py -3 回退和 Windows Git Bash 的 cygpath 兼容；清理使用记录的原始 shell 路径。
- 每项钩子测试使用独立 TMPDIR 并检查无快照残留，覆盖真实提交成功/失败、外部哨兵与符号链接、路径校验拒绝、清理失败与中断。既有全局临时目录不处理。

# v3.5.1 未部署前修订（2026-10-10，2.8.0-rc1）

插件版本保持 2.8.0-rc1，值班机尚未安装该候选。本次实现只改工具和测试，提示词与首次关口判定规则继续冻结；另同步本页与 VALIDATION.md 的交付记录。

- pre-commit 找不到可运行的 python3、python 或 py -3 时拒绝提交，明确提示启用已有 Python 环境。
- 钩子只逐项清理自己生成的两份固定日志，再尝试 rmdir 空目录；非空暂存快照和其他残留保留并打印路径，不遍历删除。开发者需人工管理保留快照。
- 测试子进程使用 sys.executable，覆盖真实提交在 Python 不可用时被拒、HEAD/暂存区不变、清理保留残留与失败退出码、python/py -3 回退及递归删除禁令。

# 2.8.0-rc1 值班机验收候选版（v3.5，2026-10-09）

以 main=3ae6769 为审查基线，在 9f06afd（v3.4.1）之上修剩余问题；v3.4/v3.4.1 的派单识别/团长名册/PROBE-LA/LS 已核实，不重复实现。

- P1：参考 Runbook 与 thinking-tools 中只读查询误禁、自动联网旧禁令改为与 common.md 一致的作用域；托管/生产写边界、JVM attach 门禁不变。宿主可能分配通用工具，删除“均无生产工具”的无法验证断言。静态检查扩展到可达参考与 policy，新增变异负例。
- P1：干净发行 ZIP 不含生成报告，旧 validate_bundle 的文档测试依赖上次 static-checks，首次校验失败；改为完成本轮检查后核对文档数字，不削弱断言，并新增干净 ZIP 首次通过/错数仍拒绝的回归。
- P1：探测与 N/S 构建按 release-manifest 精确复制，不带未申报数据；拒绝已有输出、源码重叠、符号链接与 Windows junction，不再删已有目录；记录实际输入 source_tree_sha256。探测覆盖仅接受成员/正整数/工具名，同一成员不混用限轮和限权。N/S 自检要求文件集合与完整差异集一致。
- P1/P2：docs/12 用例级冻结判据独立交给执行人、S 派单配对失效；WB07/WB09H 未 PASS 都阻止开始关口。docs/11 补 D-only、纠正 WB03 原文片段传递判读、公开测试/离线测试安全边界与工具调用审计。
- P2：新增合成 C1–C3、T02 输入与 SHA256 评分承诺（policy-source/acceptance/oncall-cases.json + docs/13），明确外部工具包原文未取得，首次运行前重新冻结。初始化/首条快捷提示引导先加载团长 Skill，明示已授权自主检索及数据底线；通过 workbuddy-allowed-changes 记录 plugin.json 理由与新版归一化哈希。移除 Agent/Skill 标题里固定的旧版号，版本只认 VERSION/插件/锁。
- P2：版本统一升为 2.8.0-rc1；README 来源记录更新为真实 GitHub 链，保留 source-provenance 历史原字节；迁移文档列明干净包整目录替换、备份与回滚。新增源/测试/工具登记到排序无重复清单，生成资源均由 build_bundle 重建。

Mac 实测：pytest 344 passed / 1 skipped / 1294 subtests passed，静态校验 1817/1817，root lock 508；check_workbuddy pass=true/errors=[]；发行 517 文件、ZIP 校验通过。最终发行与重建证据见 VALIDATION.md；Windows 10 值班机复核待执行。预发布后缀、真实加载/工具审计、18 次 N/S 与成员限权均待宿主实测。推荐等 2.8.0 正式版上线（R2-35），候选版不解除市场回同步暂停。不修改任何宿主权限或缓存，不执行生产写操作。

# 2.7.0 实验前开发工作区（PRE-GATE）

**状态：PRE-GATE。** Slice 1 + Slice 2 代码已落地（GitHub 克隆 `D:\python_code\github_my\crm-sre-team`，origin/main=7adefd8；开发 clone 的同名 tag 指向已被 7adefd8 链取代的旧链、仅存在于本地且未推送），宿主实测未执行（MODEL_BEHAVIOR=NOT_RUN、WORKBUDDY_HOST=NOT_RUN）。VERSION 仍为 2.7.0；PR-5 发布时才升 2.8.0。

**Slice 1 / PR-3a**（当前链等价 commit b3e3d8a；开发 clone 本地 tag pr-3a-strip-managed 指向被取代旧链）：运行时产物（agents/skills/individual-packages）剥离 MANAGED_HARNESS 段；源文件 policy-source/ 保留完整 common.md 含 MANAGED 段用于源级校验。build_bundle.strip_managed()；check_workbuddy.check_prompt(runtime=True) 禁止运行时含 MANAGED 块 + render_full() 源完整渲染跑全部旧规则；validate_bundle 契约比对改用剥离后 common.md。test_07/test_04/test_20/test_01/semantic_conflicts 迁移到 render_full；新增 test_runtime_render（7 checks）。运行时 MANAGED 占比 40.61%–50.99% → 0%。

**T5 / M15**（当前链等价 commit 0904538；开发 clone 本地 tag pr-1-min-collab-roster 指向被取代旧链）：新增 policy-source/routing-source.json（7 成员 route_when/do_not_route_when/expected_output/aliases，K8s 双条件+按需别名）；build_bundle.render_team_roster() + {{TEAM_ROSTER}} 注入团长 Agent 正文；check_workbuddy.routing_errors() 三方一致性（名册↔roles-source↔plugin.json）接入 run()；validate_bundle 占位符检查扩展到 {{TEAM_ROSTER}}；新增 test_native_collab（15 checks）。

**T6 / M13+M16**（当前链等价 commit da0563c；开发 clone 本地 tag pr-1-min-collab 指向被取代旧链）：common.md 证据编号统一（E###/E003:L120–L180/同源映射/成员不自行编号/缺依据记"成员未给出依据"）+ 共用成员约定节；团长派单五字段模板（随机标记分隔符/8000 字符封顶/截断补充计入成员额度）+ REFUTE 派发规则（领先候选定义/观察性成员路由/跳过记录/逐条写变化）；7 成员角色源+8 Skill 源 REFUTE 与配对逐字同步；负例参数化（runtime+render_full 双跑）；D18 旧四段名保留。

**T7 / TD**（当前链等价 commit 4a0fdbc；开发 clone 本地 tag t7-prereg 指向被取代旧链）：docs/12-native-vs-single-comparison.md 预注册锁定（18 planned run/INFRA_INVALID/SECURITY_FAIL/独立评分承诺/NOT_EVALUABLE）；MIGRATION 补 skill.zip 回同步暂停声明（R2-35）。新增 tools/make_comparison_build.py（S 构建实现：N/S 双包 + 自动字节差异验证）。docs/12 修正 18 次运行顺序（3 案例 × 6 次，逐案例序列冻结）+ 登记进 release-manifest + 本地路径泛化 + PASS/FAIL/BLOCKED 交付分支说明。

**关口前修复 fix/pre-gate-v3.2（2026-10-08，基于 origin/main=7adefd8）**：F1——探测与对照包加载核验暗号改为"逐行输出所有 PROBE-/LOAD- 行"（C/D 与 N/S 不再抢同一首行），docs/12 删除"整轮核验失败判 BLOCKED"，术语拆分 INFRA_BLOCKED（基础设施失败，按未通过发布、不作能力结论）与 CAPABILITY_BLOCKED（即 GATE_BLOCKED，仅宿主无 AgentTool 或所有写法派不中成员），第六节补"构建未加载"定义，文首补修订记录并重新冻结；F2——探测包版本派生 `<srcver>-probe.r<suffix>`（plugin.json/VERSION 同步）、成员 zip 按注入后 skills/ 重打包、probe-manifest 记 probe_version 与 lock_note、--out 仓库外不崩、docs/11 加缓存分流与团长转述规则；F3——用例路由判定纳入冻结协议；F4——build_bundle 新增 NATIVE_CLOSURE_TEXT 单一来源（产品形态措辞，无实验用语）；F5——对照工具重写：N/S 版本派生 `<srcver>-cmp-{n,s}.r<suffix>`、LOAD 行注入团长双文件（模式块外）、全部 8 个 zip 重打包、差异集自检（恰为团长双文件+版本文件+zip）通过否则非零退出；F6——pre-commit 改为 checkout-index 导出暂存树在临时目录构建 + OWNED 哈希对比，拒绝且不改写工作区，新增部分暂存负例/工作区不变/干净放行测试；F7——tools/README.md 恢复 sync_git.py 行并补 4 工具行，AGENTS.md 加同步前文件确认规则；F8——docs/11 K8s 派单改三写法（注册 ID/名册中文名/宿主显示名）+ 预注册判定表；F9——common.md NON_MANAGED 段删去托管账本半句，等义说明移入 MANAGED_HARNESS 段；F11——VALIDATION/CHANGELOG 数字与 tag 引用对齐当前链；F12——D16/D17 更名计划决策 PD-16/PD-17；F13——measure_prompts.py 输出路径仓库外不再崩溃。

**关口前修复 fix/host-observed-v3.4（2026-10-09，基于 origin/main=3ae6769）**：宿主机制观察落地——①团长 SKILL.md 自带名册（build_bundle.py 的 skill_text 增加 {{TEAM_ROSTER}} 替换；frontmatter description 加引导句"先加载本技能再作答"）；②成员识别派单（common.md WORKBUDDY_NATIVE 定义改为以"【团长派单】"识别；14 个成员源 NATIVE_MEMBER 块加派单标记识别句；COMPAT_MEMBER 块限定"只有用户直接打开本角色对话时才按本段回答"）；③派单参数写实（NATIVE_LEAD 块加 subagent_type 填注册 ID、name 只作标签、不用 bypassPermissions、限轮用 max_turns；名册说明同步）；④docs/11 新增"宿主机制观察（2026-10-09，值班机，2.6.1）"节、WB07 改为传 max_turns=1、暗号判读只认 PROBE-C/D、K8s 三写法补记实测结果、手动验证清单加项；⑤docs/12 修订记录加条目并重新冻结、开场消息第一句统一、加载核验明确 LOAD 行来自 SKILL.md；⑥新增 tests/test_host_observed.py（16 checks）。新增文件登记到 release-manifest.json。v3.4.1：探测包新增团长 PROBE-LA/LS 同 suffix 暗号、lead_markers 与 zip/echo 验证，成员 markers 仍为 7 项；WB07 要求成员先执行指定 echo，再观察 max_turns=1 失败，正常完成记 BLOCKED（“max_turns=1 未触发失败”），--max-turns 与 --disallow 不用于同一成员；派单按第一行以“【团长派单】”开头识别，日常不传 max_turns，只有用户明确要求时才限轮；K8s 三写法标为历史、当前只用 subagent_type=注册 ID，CAPABILITY_BLOCKED 判据同步；S 组任何成员派单记协议违规并单列评分；docs/11 表格连续渲染并纳入 Skill 自动加载行，路径核对以暗号为准；VALIDATION 补 Mac 修改端实测、test_host_observed 覆盖与 Agent↔SKILL.md 实测重复率（v3.4 起团长双入口均注入名册）。

**未执行**：宿主权限未修改、缓存未替换。WorkBuddy 实机导入、真实派生、REFUTE 回传、disallowedTools 生效、公开读取执行均未验证。skill.zip 市场回同步暂停至 PR-5。

# 2.7.0 只读查询误拦截解除版

在 2.6.1 基础上，按《解除只读查询误拦截的实施任务书》修改 canonical source（2026-10-05）：
共享固定边界与全部 8 个 Agent、8 个 Skill、8 个人工入口新增「只读诊断与执行边界」段——区分“生成命令”与“执行命令”，允许为明确诊断问题提供可复制只读 curl/查询 SQL/诊断命令，用户指定的公开读取在宿主允许时直接执行，结果可写入已授权工作目录；授权不自动覆盖重定向/代理/DNS 落点，内网、环回、链路本地与云元数据端点不因“只读”放行，本地凭据文件、影子副本与 curlrc 隐式注入不作为查询目标或请求体来源。生产只读执行本包仍未实现（写明未执行），生产写操作仍只给人工评审卡。MANAGED_HARNESS 块与生产连接/输出限制未放宽。清理 common.md、manual、roles/skills、references、templates 与 plugin.json 中“只输出评审卡、不给命令”的旧误拒条款。runtime-contract.json 新增 scoped `read_only_boundary`；静态检查器新增 blanket-ban 检测、9 项边界标记检测、托管块泄漏检测与 `read_only_boundary_errors`；新增 `tests/test_read_only_boundary.py`（16 项正负例，含数据外泄原语的“只允许出现在禁止句中”断言）。全部产物经项目自身构建器重建。

**未执行**：宿主权限未修改、缓存未替换、未提交推送。WorkBuddy/CLI 真实导入、有效工具权限、公开读取实机执行与生产只读通道均未验证。

# 2.6.1 开发工作区同步版

发布工具链、版本一致性（VERSION 为唯一版本源）与独立包 zip 安全校验；`tools/release.py` 与 `tests/test_version_consistency.py` 等新增并登记到 release-manifest。

# 2.6.0-rc3.workbuddy.2 宿主验收修复候选版

在 2.6.0-rc3.workbuddy.1 基础上，按 WorkBuddy 真实宿主验收准备的最小修复（2026-09-30）：
恢复根 settings.json（字节级取自 rc3 原交付 ZIP）；静态一致性检查器新增作用域感知的同义冲突句检测（3 条托管专属规则的语义改写检出，含合法否定句守卫）；8 个角色 frontmatter 按官方可选字段各绑定自己的 Skill 并纳入静态校验；release-manifest 纳入新增回归测试 tests/test_semantic_conflicts.py。全部经项目自身构建器重建；宿主场景验收进行中，见 audit-output-20260930-glm53。非精确 GitHub HEAD checkout。

# 2.6.0-rc3.workbuddy.1 本地修复候选版

完整源码恢复、WorkBuddy 入口、三模式配对、原生成员返回、Oracle 反证量化边界、原子构建与安全发行、负向测试和验证文档。非精确 GitHub HEAD checkout；宿主测试尚未执行。见 MODIFICATIONS.md 与 source-provenance.json。

# 修订历史 · 2.5.0
2026-09-22

## 已确认事实
新增课程工具与八角色判断分工，区分原摘要与工程适配；按材料触发、复用已有输出字段。新增静态配置检查与正反例、未运行的 TT 设计。四份 Schema、旧测试、原权限与控制不改；所有发布入口由源重建。

## 高概率候选
判断依据更易审查是设计目标，不是已验证效果；需真实模型对照。

## 待验证
Harness、导入、有效权限、动态 OODA、材料真伪与长期判断质量没有因本版而完成。历史包与报告分别保留，历史通过数不自动迁移。

## 已排除
不新增数值概率、凯利投入计算、模型评分或生产执行。

## 历史
2.4.0：判断依据 Schema 增强，见 docs/history/CHANGELOG-2.4.0.md；更早版本沿归档继续保留。旧提示词补丁仅适用于文件名所列版本，不是当前整包迁移脚本。
