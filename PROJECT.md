---
project_id: crm-sre
project_type: code
observed: 2026-11-04
verification: documented_not_executed
---

# crm-sre-team · 项目说明

## 定位

CRM SRE 专家协作规则包，包含协议、发布清单、构建与离线一致性校验。规则包本身不提供生产写权限。

## 输入与输出

输入为规则、文档或离线测试修改；输出为可审阅的源文件、必要的构建产物与验证证据。诊断材料、生产执行和发布授权相互独立。

## 先读

- [AGENTS.md](<AGENTS.md>)
- [CLAUDE.md](<CLAUDE.md>)
- [README.md](<README.md>)
- [policy-source/claude.md](<policy-source/claude.md>)
- [release-manifest.json](<release-manifest.json>)

## 操作

AGENTS.md 定义真源与构建产物边界。policy-source/ 是规则真源；agents/、skills/、templates/、manual-mode/、individual-packages/ 和锁文件按原构建流程生成，不手工覆盖。

Claude 的 CLAUDE.md 导入 policy-source/claude.md，保留其专属委派模式。普通文档导航不改变该约定。新增交付文件按 release-manifest.json 的精确白名单登记；不顺带安装 Git hook。

## 验证

文档改动检查链接和 diff；按 AGENTS.md 运行适用的 check_workbuddy / validate_bundle。触及 policy-source、policies 或 tools 时再执行其要求的全量回归。本次说明不降低原验收门槛。

从本项目根目录按适用改动执行：

```bash
python3 tools/check_workbuddy.py
```

命令由既有资料核对，不表示本轮已执行；实际结果须另记命令、环境、退出码与覆盖限制。

## 状态与交接

发布与验证口径见 [VALIDATION.md](VALIDATION.md) 和当前任务证据；生产状态必须来自授权现场信息，不从说明文档推断。

## 边界与恢复

生产写操作仍需独立变更审批。不得以本机文档重构启用生产工具或更改远端。回滚仅覆盖本轮 PROJECT/导航/清单补丁，保留其他规则和构建状态。
