# 本地开发工具

这些程序不调用模型、WorkBuddy API 或生产系统。

- build_bundle.py：在隔离副本生成 Agent、Skill、锁和八个独立包，替换自有输出；失败正常回滚，根 settings 不改写。
- validate_bundle.py：源/产物/Schema/锁/引用和非递归静态测试检查。生成 tests 下四份可复现报告。
- check_workbuddy.py：模式作用域、入口、配对和运行契约负向规则检查，不是权限执行器。
- check_thinking_tools.py：课程分工及原契约/窄范围变更指纹保护。
- check_determinism.py：临时副本中重建、重复/反向目录遍历校验和排序守卫负例。
- build_release.py / validate_release.py / release_rules.py：共享准确文件白名单，原子确定性 ZIP 与严格安全/内容检查。
- check_release_diff.py：对真实原上传 2.5.0 基线检查旧 Schema/测试保护和允许的源码差异；支持 --output。

完整命令见 ../docs/07-reproducible-validation.md。新增源文件须审查并加入 release-manifest.json；不能用全目录扫描替代发布清单。
