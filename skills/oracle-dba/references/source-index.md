适用范围：本文的领域方法和证据纪律可用于三模式；宿主状态机、编号账本、闭合 Schema 字段、强制 JSON、接纳与发布门仅用于 MANAGED_HARNESS。原生/兼容不执行这些托管要求、不据此升级模式或索取控制字段，以当前 Agent/Skill 的互斥模式契约为准。

# 来源、适用范围与更新规则
版本：2.5.0。2026-09-22 本次仅修订本地包，未重新联网核验下列来源。链接与技术引用沿用原包；不是对当前版本或许可的保证。
## 原包记录的来源导航（本次未重新核验）
| ID | 来源 | 用途与边界 |
|---|---|---|
| WBEXPERT | [WorkBuddy专家说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Expert-Center) | 专家与专家团区分、授权访问与上传材料边界；本包未实机导入 |
| WBTEAM | [WorkBuddy专家团开发结构](https://open.workbuddy.cn/docs/expert-team) | 检索索引显示plugin.json、agents、avatars等结构；直连抓取失败，不声称完整校验原生插件发布规范 |
| WBREF | [用户指定的社区参考仓库](https://github.com/darker2016/workbuddy-skill-groups) | 参考角色化组织方式；不当作产品官方保证，不复制第三方实现 |
| SREINC | [Google SRE Managing Incidents](https://sre.google/sre-book/managing-incidents/) | 事故职责、协调、记录与恢复；本包改为用户提供证据的流程 |
| JVM21 | [Oracle JDK21 jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) | 核对诊断影响级别与堆转储风险；不能代替JDK8等目标版本文档 |
| ORACLELIC | [Oracle 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html) | AWR/ASH与相关访问的许可门禁；具体授权由现场合同/许可负责人确认 |
| OSESSION | [Oracle 19c V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSION.html) | STATE、EVENT、等待时间字段含义；版本与RAC/PDB边界需现场确认 |
| KLOG | [Kubernetes kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/) | since-time、previous、tail、limit-bytes等参数；仍核对客户端版本 |
| TMF622 | [TM Forum产品订单API](https://www.tmforum.org/open-digital-architecture/open-apis/product-ordering-management-api-TMF622/v5.0) | 产品订单业务对象划分，不要求现场实现该接口 |
| TMF641 | [TM Forum服务订单API](https://www.tmforum.org/open-digital-architecture/open-apis/service-ordering-management-api-TMF641/v4.1) | 区分服务订单与产品订单；链接为指定版本，不当作最新版本推荐 |
| VMSTAT | [procps-ng vmstat手册发布页](https://www.man7.org/linux/man-pages/man8/vmstat.8.html) | 首次报告与后续间隔、瞬时字段的区别；以现场man页为准 |

## 按目标版本由人工维护的知识入口
下列为知识导航，不标记为本轮逐页核验，不据此给出未经确认的生产参数。
| ID | 入口 | 重点 |
|---|---|---|
| SREMON | [Google SRE监控](https://sre.google/sre-book/monitoring-distributed-systems/) | 黄金信号与症状监控 |
| SRESLO | [Google SRE服务目标](https://sre.google/sre-book/service-level-objectives/) | SLI/SLO与错误预算 |
| IOSTAT | [sysstat官方项目](https://github.com/sysstat/sysstat) | 现场版本的iostat/sar手册及字段语义 |
| WLS | [Oracle WebLogic文档入口](https://docs.oracle.com/en/middleware/fusion-middleware/weblogic-server/) | 根据现场版本查线程池、JDBC、健康状态 |
| TOMCAT | [Apache Tomcat文档](https://tomcat.apache.org/) | 根据现场主版本查监控与配置 |
| RMAN | [Oracle数据库文档](https://docs.oracle.com/en/database/oracle/oracle-database/) | 按现场版本查备份恢复、Data Guard、诊断与许可 |

## 使用规则
现场证据用来判断“发生了什么”；内部已批准流程用来决定“谁能怎么做”；对应版本官方文档用来解释产品语义。三者冲突时明确冲突、停止危险建议，不能用旧Runbook绕过权限与安全边界。
外部案例只能作为待验证模式；不得直接作为现场根因。原生/兼容可自主检索公开资料，检索只用通用技术词，不外发本次材料，不登录、不上传、不读取凭据文件或环境变量；标注网址、访问日期、版本与适用条件。
运行环境无联网能力时说明版本未核验，并收用户提供的官方资料摘录；不要编造已查证最新文档。
新增内部案例要记录产品版本、业务范围、证据、反证、人工动作、恢复验证、失效条件与脱敏状态；不上传完整生产配置作为长期知识库。

## 构建与版本绑定
以根 VERSION 为唯一版本源；插件版本、八个 Skill 的 VERSION 与根 VERSION 一致。领域资料的历史基底版本不是当前发布版本。policy-source 是编辑源；tools/build_bundle.py 生成 Agent、Skill、副本、模板与独立包。prompt-bundles.lock 绑定源、角色、Schema 与策略文件哈希。
版本锁只是配置完整性证据，不证明模型行为或 Harness 已部署。托管宿主须实际验证版本锁，禁止混用旧安全协议、模板或独立 ZIP。

## 本版用户提供的思考工具来源
course:T023–T038 与 T091、T005、T096、T021、T053、T087、T076 的名称和概括来自用户粘贴文本；并未访问用户本地目录文件或课程全文。角色分配、数据触发和限制为工程适配，详见 [思考工具](thinking-tools.md)。不把摘录当作现场 E 或独立事实依据。
