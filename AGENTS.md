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

`git push` / `git commit` 属于独立的显式决定，不因本文件的存在而自动发生。
