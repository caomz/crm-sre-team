# AGENTS.md

项目用途、操作与验证导航见 [PROJECT.md](PROJECT.md)；本文件及既有专项入口的约束继续适用。当前活动交付目标是 DSH Agent Teams（见 `docs/17-dsh-agent-teams.md`）；WorkBuddy 是保留的历史回归资产，不是当前交付宣称。

本文件是本项目的 AI 协作规则，优先级高于通用习惯，活动 DSH 契约来自 `policy-source/dsh/` 与 `policies/runtime-contract.json`；`policy-source/prompts/common.md` 保留 WorkBuddy 历史契约。

## 唯一真源

`policy-source/` 是唯一可手工编辑的真源；DSH 领域源在 `policy-source/dsh/`。以下目录是构建产物，**不要手工修改**：

```
agents/  skills/  templates/  manual-mode/  individual-packages/  dsh/  prompt-bundles.lock
```

`dsh/` 与 `prompt-bundles.lock` 由默认构建维护；`agents/` 等历史树由 `--target workbuddy` 回归构建维护。改完源文件后必须重建：

```powershell
python3 tools/build_bundle.py                # 默认 dsh：生成 dsh/ 并刷新总清单锁
python3 tools/build_bundle.py --target workbuddy   # 仅历史回归
```

`policy-source/prompts/common.md` 通过 `{{COMMON_CONTRACT}}` 占位符注入到 WorkBuddy 的 agent 与 SKILL 产物中。根 `VERSION` 是冻结的 WorkBuddy 历史基线；DSH 活动版本只来自 `policy-source/dsh/package-source.json`，锁文件同时记录两者（`version`/`target`/`target_version`）。

## 提交前：源与产物必须一致

安装一次 pre-commit 门（真实拦截，不是提示词承诺）：

```powershell
python3 tools/install_git_hooks.py
```

它把 `core.hooksPath` 指向 `tools/git-hooks`，之后每次 `git commit` 都会先重建产物；若产物与源不一致，提交被拒绝并提示重新暂存。

钩子按能力选择运行构建的解释器：`CRM_SRE_PYTHON` 非空时只用它（含路径分隔符的相对路径按仓库根解析，裸命令名按 PATH 查找；不合格直接拒绝提交，不回退 PATH；为空等同未设置）；否则依次尝试 PATH 上的 `python3`、`python`、`py -3`，只接受 Python 3.11+ 且能导入 PyYAML 的解释器，全部不合格时逐个列出原因。macOS 自带的 `/usr/bin/python3` 是 3.9，会被拒绝；请把 `CRM_SRE_PYTHON` 指向按 `requirements-dev.txt` 安装的项目环境（例如 `.venv/bin/python`），或把该环境放到 PATH 最前。

已装过后重复执行是安全的（幂等）。卸载：

```powershell
python3 tools/install_git_hooks.py --uninstall
```

钩子被刻意绕过时的唯一方式：

```bash
git commit --no-verify    # 仅在你能人工确认产物正确时使用
```

**不要用提示词措辞假装同步已经发生。** 产物是否一致由 `tools/build_bundle.py` 的实际输出和上锁哈希决定，不由任何模型陈述决定。

## 新增文件必须申报

任何新增的源文件、测试或工具，都要先加入 `release-manifest.json` 再提交。该清单是精确白名单，**不能用全目录扫描替代**。清单必须保持字典序且无重复。

`tools/git-hooks/pre-commit` 故意**不**申报：它无文件扩展名，是本地开发工具，不属于发布载荷。

## 验证命令

```powershell
python3 -m pytest tests/ -q                    # 全量回归
python3 tools/check_dsh.py                     # DSH 结构/边界/源产物一致
python3 tools/validate_bundle.py               # DSH 默认校验；--target workbuddy 仅历史回归
python3 tools/check_workbuddy.py               # WorkBuddy 历史模式一致性（历史回归）
python3 tools/build_release.py --output dist/crm-sre-dsh.zip        # DSH 精确子集 ZIP
python3 tools/validate_release.py --zip dist/crm-sre-dsh.zip
```

改动 `policy-source/`、`policies/` 或 `tools/` 后至少跑全量回归。只读边界由 `tests/test_read_only_boundary.py` 锁定，任何"放宽权限"的改动都会让它变红——这是设计意图，不要通过削弱断言来让它通过。

## DSH 交付流程（活动目标）

- DSH 规则源在 `policy-source/dsh/`，生成物 `dsh/` 只读；DSH 发布载荷是 `targets.dsh.files` 精确子集（三个生成的 `dsh/` 文件、README、PROJECT、docs/17、`policies/runtime-contract.json`），不含 WorkBuddy 运行文件、源材料、gold、证据或用户数据。
- 团长规则走专用 preset：patch 恒为四条记录（两个原全局覆盖、`agent-preset-registry` 默认覆盖为 `crm-sre`、裸插入 `preset-crm-sre`；作用域插件仅 persona/time-context/只读 tool-fs）。标准 preset 的作用域 persona 会遮蔽全局团长前缀——这是既有宿主失败的根因；新会话必须确认运行在 CRM SRE preset，并在实际 system/message 核对团长规则全文在场，已装载配置不是证据。按维度记录实际加载和行为结果；本候选状态见 `VALIDATION.md`，不得把加载成功等同于配额、恢复或事实正确性通过。
- 顺序固定：先在独立桌面宿主 profile 显式安装上游 Agent Teams 0.1.30（验证基线 Harness 0.2.2-rc.1），再以绝对路径加载 DSH 领域包；桌面宿主 profile 与团队 profile `crm-sre` 是两层概念。安装、验收与回退细节见 `docs/17-dsh-agent-teams.md`。
- 测试顺序固定：Mac 完整运行 → 人工复核并接受 → Windows 安装同一接受产物做 VERIFY 与差异短测；逐台记录实际宿主/carrier/插件版本、构建哈希与真实成员回执，模型逐次记录。未执行项一律 `NOT_RUN`；CLI 配置装载与真实模型/桌面会话分别记录，不互相替代。
- 配额（每批 3 名、每轮 3 项、每任务补证 2 项）是协议与计划/回执核对约束，不是运行时硬守卫；任务与 attempt 标识只采用引擎真实回执。v1 无生产取数通道；生产写只产出人工评审需求。生产事实以 `policies/runtime-contract.json` 为准，不注入 DSH 插件 config。

## WorkBuddy 历史测试与交付流程（历史回归，非当前交付宣称）

- 提示词测试（自检、WB 用例、7A/7B、校准和关口）全部先在 Mac 运行；Mac 跑完、返回结果经人工复核并验收后，再安排 Windows 值班机。
- 值班机默认只做安装/切换 + VERIFY（来源/缓存完整性、Skill 回执路径）+ 记录版本；仅在需确认宿主行为时加一个短会话，每次列明确切项目。
- 两台都记录实际 WorkBuddy 版本、插件版本和模型；有差异时，值班机检查必须覆盖差异，不假定 Mac 结论自动适用。日常与关口固定 glm-5.3-flash，逐次记录实际模型（团长/成员），不混用其他模型结果。
- 每轮 N/S（校准与正式 18 次关口）只使用同一台机器上同次构建的双包，不混用 Mac 与值班机的构建。两台机器各自记录构建后缀与身份（机器、source_commit、manifest 与缓存哈希）。
- 校准和关口前两台机器都要查看宿主记忆条目，由执行人在会话外核对 conversation_search 可检索的测试历史，记录可能进入被测会话的内容及隔离状态；Mac 测试历史更多，同样适用。是否清理或关闭由用户决定。遵守 docs/11 的宿主用例与关口材料隔离要求。
- WB07 的 HOST_LIMIT 前提按实际运行该测试的机器的 WorkBuddy 版本核验：Mac 采用只读代码复核，按 runbook r3/r4 第 8 节“代码证据”的做法；块 27 只用于 Windows 值班机，值班机的 5.7.7 记录不能代替 Mac 核验。值班机版本与 Mac 不同时，由值班机简单检查补核轮数下限与团长处理。WorkBuddy 5.7.7 会把子代理 max_turns 的有效值钳到不低于 200（请求 1 的有效值也是 200），不是每个成员实际执行 200 轮；HOST_LIMIT 与恢复 WB07 须 PASS 的判读按 docs/11–13 保持。
- gold 只由执行人持有，不放进插件目录、缓存或被测工作区，Mac 上同样保持此隔离。直接在 Mac 评分；如需交到值班机，只在 Mac 运行结束、结果返回并验收接受后进行。

## 权限与边界

- 本仓库的提示词与离线测试**不授予任何权限**，也**不能**实现权限隔离。`policies/runtime-contract.json` 中 `production_executor: false`、`production_tools: []`、`implementation_status: NOT_IMPLEMENTED` 是事实陈述。
- 生产写操作只产出人工评审需求，不代为执行。`read_only_boundary.production_write` 恒为 `SEPARATE_CHANGE_APPROVAL_REQUIRED`。
- 不要在提示词或文档里写入"已授予最高权限""自动同步已完成"这类无法验证的断言。

## 与远端同步

```powershell
python3 tools/sync_git.py                      # dry-run，输出计划与 plan_id
python3 tools/sync_git.py --apply --confirm <plan_id>
```

默认 dry-run；写入需 `--apply` 加 plan_id 二次确认；仅作用于项目根内文件；构建自有产物不按文件同步。工具不执行 `git add` / `commit` / `push`。

从开发 clone 同步到 GitHub 克隆之前，先列出 `origin/main` 自上次同步以来改过的文件（`git log --name-only HEAD..origin/main` 或等价命令），逐个确认本地改动不会被覆盖回旧版本，再开始同步。

`git push` / `git commit` 属于独立的显式决定，不因本文件的存在而自动发生。
