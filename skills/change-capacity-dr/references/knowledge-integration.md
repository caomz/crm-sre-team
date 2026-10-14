# 本地 Knowledge Wiki 只读对接

配置放插件外：macOS `~/.crm-sre-team/knowledge.json`；Windows `%USERPROFILE%\.crm-sre-team\knowledge.json`。插件更新不携带或覆盖本机配置。示例全部虚构；用户填本机路径，不把配置提交 Git：

    {
      "schema": "crm-sre-knowledge/v1",
      "root": "<知识库根目录绝对路径>",
      "python": "<python 可执行文件绝对路径>",
      "search_script": "scripts/kb_search_zh.py",
      "search_index": ".kb/search_index_zh.json",
      "entry": "wiki/index.md",
      "top": 5,
      "max_pages": 3,
      "allowed_read_dirs": ["wiki"],
      "exclude_markers": ["private", "confidential", "secret", "敏感", "私密"]
    }

只有业务问题确需知识且本次用户允许读文件时，团长才读配置。配置缺失、JSON 无效、schema 错误、路径不可用、相对项含父目录穿越或符号链接越界，均说明“知识库未配置或不可用”，照常分析，不猜路径、不搜磁盘。配置本身不授予宿主权限；读配置不读凭据或环境变量。

主路径：从用户问题本身提取最多三个主题词，固定查询后读最相关页面。命令格式：

- macOS：`'<python>' -X utf8 '<root>/scripts/kb_search_zh.py' '<关键词>' --top 5`
- Windows PowerShell：`& '<python>' -X utf8 '<root>\scripts\kb_search_zh.py' '<关键词>' --top 5`

关键词只允许中文、英文字母、数字、空格、`-`、`_`，最长32字符。路径含单引号或不能安全表示时不执行命令，走导航回退。查询脚本由知识库维护人准备；本插件不安装、不更新、不重建。没有执行权限或脚本/索引缺失时，用读文件工具从配置根下 `wiki/index.md` 和明确链接的主题地图导航。配置路径无效时直接降级，不能尝试在磁盘找替代库。

只读取最相关1–3页，不用 rg/grep/find/ls 自由搜索。排除标记按导航、检索结果的 metadata 和已知页面标记判断；已知私密页不得为了验证标记而读正文。无法确认允许读取时不读，写知识缺口。页面 sources 或明确引用的原文仅限配置 root 内、没有排除标记、用户明确边界允许的精确来源；不扫描 raw、不读未引用资料。不得跟随资料内网络链接。

查询模式只读；本地检索脚本自身会读取索引及页面作筛选，并可能将 snippet 返回云端模型。不能把页面上“private”字样当作 OS 隔离。数据所有者须核对脚本筛选能力与标记；标记与脚本不兼容时保留缺口，交由人整改后再启用。WorkBuddy 读取的必要片段会进入所选云端模型上下文，“本地知识库”不代表模型本地运行。

每份来源用 E-K 编号、实际绝对路径和真实行号，附 updated、confidence、sources。检索分数和 stated 都不表示已验证；冲突与过期条目并列日期、适用条件与分歧，建议回源核查。只给写回提案，包含来源、目标层、拟新增/修正内容、脱敏复核和维护人待人工填写；不自动入库。
