# 本地开发工具

这些程序不调用模型、WorkBuddy API 或生产系统。

- build_bundle.py：在隔离副本生成 Agent、Skill、锁和八个独立包，替换自有输出；失败正常回滚，根 settings 不改写。
- validate_bundle.py：源/产物/Schema/锁/引用和非递归静态测试检查。生成 tests 下四份可复现报告。
- check_workbuddy.py：模式作用域、入口、配对和运行契约负向规则检查，不是权限执行器。
- check_thinking_tools.py：课程分工及原契约/窄范围变更指纹保护。
- check_determinism.py：临时副本中重建、重复/反向目录遍历校验和排序守卫负例。
- build_release.py / validate_release.py / release_rules.py：共享准确文件白名单，原子确定性 ZIP 与严格安全/内容检查。
- check_release_diff.py：对真实原上传 2.5.0 基线检查旧 Schema/测试保护和允许的源码差异；支持 --output。
- sync_git.py：工作区与 origin 双向同步计划器。默认 dry-run；写入需 --apply 加 plan_id 确认；只改项目根内文件，拒绝越界路径与符号链接；构建自有产物（agents/skills/templates/manual-mode/individual-packages/prompt-bundles.lock）不按文件同步；每次写入记入 reports/sync-ledger-*.jsonl，中途失败回滚。不授予任何权限，不改生产只读边界。
- install_git_hooks.py：设置/卸载 core.hooksPath=tools/git-hooks（提交前重建门），幂等。
- make_probe_build.py：生成 Step 0 探测包（reports/probe-build/，gitignored；主目录零改动），注入 C/D 暗号并派生探测版本。
- make_comparison_build.py：生成 N/S 对照双包（reports/comparison-build/，gitignored；主目录零改动），S 臂用 NATIVE_CLOSURE_TEXT 并自检差异集。
- measure_prompts.py：度量各构建产物的提示词长度与块结构，支持 --root。

完整命令见 ../docs/07-reproducible-validation.md。新增源文件须审查并加入 release-manifest.json；不能用全目录扫描替代发布清单。
