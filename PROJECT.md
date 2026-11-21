---
project_id: crm-sre
project_type: code
observed: 2026-11-21
verification: repair_candidate_offline_checked_runtime_not_run
---

# crm-sre-team · 项目说明

当前活动交付是 DSH Agent Teams 领域配置包，采用 Mac 主调试、GitHub 代码交接、Windows 后续验证。版本 `2.8.0-dsh.1` 来自 `policy-source/dsh/package-source.json`；根 `VERSION` 保留 WorkBuddy 历史基线 `2.8.0-rc10`。团长规则经专用 `preset-crm-sre` 条目的作用域 persona 注入（与全局覆盖逐字相同）：标准 preset 自带的 persona 会遮蔽全局团长前缀，这是既有宿主失败的根因；新会话默认并须确认运行在 CRM SRE preset，实际 system/message 含团长规则全文才算装载生效，已装载配置本身不是证据。

11 月 20 日提交 `3c7b1b5eb69b2ecacc724372ba043ca8bc89b9c4` 的说明报告 Mac CLI/Web 配额与 E401 恢复核心用例通过；用户于 2026-11-21 反馈现用 Mac 运行正常。11 月 17 日失败保留为历史；本轮未重新核验其后 Mac 原始回执。本次修复候选的 Mac、Windows 运行复测均为 `NOT_RUN`，离线状态见 `VALIDATION.md`。构建目标仍只有默认 `dsh` 与历史回归 `workbuddy`。

## 使用入口

- [README](README.md)：安装、材料范围和输出。
- [DSH 操作与验收](docs/17-dsh-agent-teams.md)：独立宿主 profile、两步安装、Mac 与 Windows 验收顺序。
- [运行契约](policies/runtime-contract.json)：项目边界事实；不授予宿主权限。

## 源码维护

开发者先读源码根的 `AGENTS.md`；Claude Code 入口仍为 `CLAUDE.md` 与 `policy-source/claude.md`。这些开发文件不随运行安装包分发。

`policy-source/` 是规则真源；活动 DSH 规则在 `policy-source/dsh/`。角色、路由及领域 Runbook 沿用规范源。成员所需专业内容完整内嵌，不依赖 WorkBuddy Skill 加载。

默认构建和校验目标由 `release-manifest.json` 的 `default_target: dsh` 指定。构建仅替换 `dsh/` 与总锁，历史运行树保留；`--target workbuddy` 仅用于历史回归，两个目标之外没有第三条构建路径。新增文件逐个登记，目标载荷使用排序、无重复的精确子集（历史 DSH ZIP 载荷恒为七文件）。Git 交接保留完整源码检出，宿主只加载其中 `dsh/` 的绝对路径；完整检出不适用七文件解压目录校验。

验证命令从源码根执行：

```bash
python3 tools/build_bundle.py
python3 tools/check_dsh.py
python3 tools/validate_bundle.py
python3 -m pytest tests/ -q
```

构建、检查和发布包验证均不调用模型或生产系统；实际结果按本轮回执记录。源码仓库的 `VALIDATION.md` 保留验证记录，历史 WorkBuddy 结果不计作 DSH 通过。

接收端在新目录检出 Mac 已接受的完整提交 SHA，先确认 Git 状态干净，再运行 `python3 tools/check_dsh.py` 与 `python3 tools/validate_bundle.py --check-only`；后者执行相同校验但不改写报告。接收验证前不重建，不用移动分支名或相同版本号代替提交身份。Mac 接受以后再让 Windows 验证同一提交；虚拟环境、宿主配置、凭据与运行材料均在各机器本地管理，材料工作区与源码目录分开。

## 边界与恢复

v1 只分析本轮授权脱敏材料，无生产取数通道。生产写只给人工评审需求。工具过滤不构成 OS 隔离；自定义托管实现保持 `NOT_IMPLEMENTED`。

每次只恢复本轮备份对应的补丁和 profile，不覆盖并发改动。构建、安装、提交、推送与发布分别授权、分别报告。
