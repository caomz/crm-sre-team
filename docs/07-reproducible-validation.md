# 本地可复现验证（当前修复分支）

本节命令仅用于本项目的离线开发，不是生产指令。先安装 requirements-dev.txt 中的开发依赖。建议在新目录中执行，保持报告在 reports/ 或项目目录之外。

```bash
python tools/build_bundle.py
python tools/validate_bundle.py
python tools/check_workbuddy.py
python tools/check_thinking_tools.py
python -m pytest tests -q
python tools/check_determinism.py --output reports/rebuild-check.json
python tools/build_release.py --output dist/crm-sre-team.zip
python tools/validate_release.py --zip dist/crm-sre-team.zip
```

`check_release_diff.py` 现在针对真实原始上传的 2.5.0 ZIP，不再把 2.4.0 当作本次基线；历史脚本保留在 docs/history。只有拥有该原始上传版时才运行：

```bash
python tools/check_release_diff.py --baseline /path/to/original-2.5.0/crm-sre-team --output reports/release-diff.json
```

基线全文件指纹须匹配 source-baseline.json。缺失或版本不匹配必须失败，不制造基线。该脚本支持 --output，但结果不能冒充当前 GitHub HEAD 审计。

本包已有生成产物；构建以规范源为真源。root settings 的额外用户配置不会被覆盖。构建拥有的五个生成目录会替换，不存用户资料。发行文件只认 release-manifest.json；报告、缓存、虚拟环境、事故材料及未登记文件不入包。

两次生成相同只说明本环境确定性，不代表 Windows/其他 Python 与压缩库版本下 ZIP 必然同哈希。原始测试输出、耗时、退出码保存在本轮外部证据包；静态校验器中的可复现报告会归一化耗时。
