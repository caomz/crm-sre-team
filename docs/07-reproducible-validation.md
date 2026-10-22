# 本地可复现验证（当前修复分支）

本节命令在 Mac 用于本项目的离线开发，不是生产指令。先核对现有环境满足 requirements-dev.txt，不自动安装或升级依赖。建议在新目录中执行，保持报告在 reports/ 或项目目录之外。提示词测试（自检、WB、7A/7B、校准和关口）全部在 Mac 跑完并由人工复核验收；值班机随后只做安装/切换 + VERIFY + 记录版本，仅在需确认宿主行为时加一个短会话。

```bash
python3 tools/build_bundle.py
python3 -m pytest tests/ -q
python3 tools/check_workbuddy.py
python3 tools/validate_bundle.py
python3 -m pytest tools/oncall -q
python3 tools/release.py
```

`tools/release.py` 是统一发布入口，串行执行静态/测试/确定性门、staging 构包、validate_release、解包复验，全部通过才移入 dist/releases。用两个独立输出目录重建同一候选，比较发布 ZIP 原字节与 SHA256；单独验证可用 `python3 tools/validate_release.py --zip <实际 ZIP 路径>`。离线流水线通过不代表 WorkBuddy 或模型行为通过。

发布测试门使用 pytest 同时执行 `tests/` 和 `tools/oncall/`，核对结构化的收集、运行、通过、失败、错误和跳过数量；任一范围缺失、全部跳过、收集失败或筛选漏跑都会阻断发布。该入口须在完整开发仓库运行，依赖 `requirements-dev.txt`；发行 ZIP 不含 repository-only 的 oncall 测试，不能直接重跑完整发布门。测试子进程忽略 `PYTEST_ADDOPTS`、pytest 配置中的 `addopts` 与自动加载的第三方插件，不调用发布入口自身。

`check_release_diff.py` 现在针对真实原始上传的 2.5.0 ZIP，不再把 2.4.0 当作本次基线；历史脚本保留在 docs/history。只有拥有该原始上传版时才运行：

```bash
python tools/check_release_diff.py --baseline /path/to/original-2.5.0/crm-sre-team --output reports/release-diff.json
```

基线全文件指纹须匹配 source-baseline.json。缺失或版本不匹配必须失败，不制造基线。该脚本支持 --output，但结果不能冒充当前 GitHub HEAD 审计。

本包已有生成产物；构建以规范源为真源。root settings 的额外用户配置不会被覆盖。构建拥有的五个生成目录会替换，不存用户资料。发行文件只认 release-manifest.json；报告、缓存、虚拟环境、事故材料及未登记文件不入包。

两次生成相同只说明本环境确定性，不代表 Windows/其他 Python 与压缩库版本下 ZIP 必然同哈希。原始测试输出、耗时、退出码保存在本轮外部证据包；静态校验器中的可复现报告会归一化耗时。
