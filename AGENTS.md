# AGENTS.md

本文件是本项目的 AI 协作规则，优先级高于通用习惯，与 `policy-source/prompts/common.md` 描述的运行契约一致。

## 唯一真源

`policy-source/` 是唯一可手工编辑的真源。以下目录是构建产物，**不要手工修改**：

```
agents/  skills/  templates/  manual-mode/  individual-packages/  prompt-bundles.lock
```

改完源文件后必须重建：

```powershell
python3 tools/build_bundle.py
```

`policy-source/prompts/common.md` 通过 `{{COMMON_CONTRACT}}` 占位符注入到全部 agent 与 SKILL 产物中。改 common.md 后同样必须重建，否则产物里仍是旧契约。

## 提交前：源与产物必须一致

安装一次 pre-commit 门（真实拦截，不是提示词承诺）：

```powershell
python3 tools/install_git_hooks.py
```

它把 `core.hooksPath` 指向 `tools/git-hooks`，之后每次 `git commit` 都会先重建产物；若产物与源不一致，提交被拒绝并提示重新暂存。

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
python3 tools/check_workbuddy.py               # 模式/入口/契约静态一致性
python3 tools/validate_bundle.py               # 源/产物/Schema/锁/引用一致性
```

改动 `policy-source/`、`policies/` 或 `tools/` 后至少跑全量回归。只读边界由 `tests/test_read_only_boundary.py` 锁定，任何"放宽权限"的改动都会让它变红——这是设计意图，不要通过削弱断言来让它通过。

## WorkBuddy 测试与交付流程

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
