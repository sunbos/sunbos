<div align="center">

# SunBo · sunbos

![主页访问次数](https://visitor-badge.laobi.icu/badge?page_id=sunbos.sunbos&left_color=%23333333&right_color=%23ff5555&left_text=👥%20Total%20Views)

**AI 应用工程 · Agent 编排 · 数据与测试自动化**

构建能调用工具、处理异常并留下验证记录的 AI 工作流。

[sqlseed](https://github.com/sunbos/sqlseed) · [项目实践](#项目与实践) · [开源协作](#开源协作) · [技术关注](#技术关注与实践)

</div>

我主要用 Python 构建 AI 应用与自动化工具：维护 sqlseed，将 LangGraph、Dify 与设备测试流程结合，并参与 SDK、Agent 安全和工具交付的开源协作。

`Python` · `LangGraph` · `Dify` · `LLM APIs` · `MCP` · `SQLite` · `pytest` · `GitHub Actions`

## 项目与实践

### sqlseed · 数据生成引擎与 AI 工作台

**作者 / 维护者** · [项目](https://github.com/sunbos/sqlseed) · [架构](https://github.com/sunbos/sqlseed/blob/main/docs/architecture.md) · [AI 实现](https://github.com/sunbos/sqlseed/tree/main/plugins/sqlseed-ai) · [MCP 实现](https://github.com/sunbos/sqlseed/tree/main/plugins/mcp-server-sqlseed)

把数据库结构和业务规则转成可重复的测试数据，将声明式数据引擎与 AI 配置生成接在一起。

> **流程示意**：数据库结构与字段规则 → 配置校验、依赖检查和样例预览 → 生成并写入关联数据。

<!-- profile-ai:sqlseed-main:start -->
主分支已实现：

- **给模型提供数据库上下文**：整理 schema、索引、外键、数据样本及分布信息，生成可复用的数据规则。
- **验证与反馈修正**：配置经过结构校验、列名核对和少量样本预览；把错误摘要反馈给模型，在限定重试次数内修正配置。
- **通过 MCP 接入 AI 助手**：提供 schema 资源，以及检查、生成配置和执行填充的工具入口。
- **处理实际的数据约束**：表依赖拓扑排序、循环依赖检测、外键关联和固定 seed，让配置能接入可复现的数据生成流程。
<!-- profile-ai:sqlseed-main:end -->

#### 契约驱动修复与交互式工作台

<!-- profile-ai:sqlseed-workbench:start -->
**候选分支 · [工作台 PR #10](https://github.com/sunbos/sqlseed/pull/10) 尚未合并。** 将字段规则调整、预览、生成、运行记录和候选包交付串成完整流程：

- **分层修复配置**：先做契约检查与确定性规则修复，再按错误类型缩小上下文、调用分级模型；遇到重复违规、重试或时间预算耗尽时停止或降级。[修复编排](https://github.com/sunbos/sqlseed/blob/01b1584152aa1fc9f1135ea6add6fb1ab8c303be/plugins/sqlseed-ai/src/sqlseed_ai/auto_heal/orchestrator.py#L2953)
- **审阅后应用 AI 建议**：把建议约束到选定字段与生成器参数，校验依赖并生成只读样例，以规则差异供人审阅后应用。[建议校验](https://github.com/sunbos/sqlseed/blob/01b1584152aa1fc9f1135ea6add6fb1ab8c303be/plugins/sqlseed-web/src/sqlseed_web/workbench_ai.py#L735)
- **让执行结果可追溯**：绑定数据库身份、schema、配置版本与检查结果，保存运行快照并区分计划量和实际提交量；部分失败后，仅在计数明确时生成剩余数据计划。[运行记录](https://github.com/sunbos/sqlseed/blob/01b1584152aa1fc9f1135ea6add6fb1ab8c303be/plugins/sqlseed-web/src/sqlseed_web/workbench_runtime.py#L790)
<!-- profile-ai:sqlseed-workbench:end -->

#### GemmaSQLSeed · sqlseed 的 AI Agent 参赛实践

**2026.06 · GDG 上海 Gemma 4 开发者大赛 · AI Agent 赛道**

围绕自然语言需求、SQLite schema 理解、配置生成和反馈修正，提交 GemmaSQLSeed 参赛作品与技术报告。作品与 sqlseed 共用技术基础，重点呈现模型如何参与数据生成工作流。

参赛材料通过两次 PR 合并收录，可查看问题定义、工具设计与技术方案：

[作品与技术报告](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/tree/main/submissions/2026/track_A/GemmaSQLSeed) · [首次提交 #19](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/pull/19) · [后续完善 #39](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/pull/39)

### 设备稳定性测试 Agent · LangGraph 与确定性测试协作

**工程实践 · 非开源案例（脱敏）**

将设备稳定性测试拆成可配置的动作、检查项与 LangGraph 状态图，处理长时间运行中的异常检测、故障归因与环境恢复。

> **异常处理示意**：执行测试动作 → 并行采集状态与事件、规则判定、Agent 归因 → 输出失败结果与诊断信息。

- **模型建议与测试判定分工**：LLM 提供结构化故障诊断和风险注解，通过／失败仍由规则和采集事实决定；模型不可用时回退规则诊断。
- **按阶段限制工具**：测试循环提供查询与探测工具，环境恢复工具仅在相应阶段开放，恢复动作进入诊断记录。
- **诊断经验可追溯**：可按场景归档诊断，并将历史摘要用于后续风险先验，同时限制先验的影响范围。
- **离线验证**：通过 FakeClient 和图执行测试检查流程、能力依赖、诊断降级及模型不翻转规则判定的通过／失败结果这一边界。

### 多协议设备事件校验 · Python 与 Dify Workflow

**工程实践 · 非开源案例（脱敏）**

将 Python／pytest 与 Dify Workflow 用于多协议设备事件测试，串联环境准备、测试数据构造、动作触发和事件校验。

> **流程示意**：一项设备事件测试 → 触发操作、采集事件、程序与模型分层校验 → 回填结果和问题说明。

- **分层校验**：程序处理事件采集、能力预检和基础核对，模型参与复杂事件内容分析。
- **工作流工具化**：将准备环境、构造测试数据和触发操作拆成可组合的工作流，提供统一的 Python 调用入口。
- **运行约束**：处理查询限流、超时、设备能力差异，并将判定结果写回统一记录。

## 开源协作

### Dify Python SDK · AI 应用接口集成

<!-- profile-ai:dify-sdk:start -->
**代码贡献 · PR 审阅中** · [上游 PR #3](https://github.com/langgenius/dify-python-sdk/pull/3) · [我的 fork](https://github.com/sunbos/dify-python-sdk)

为 SDK 补充 **7 类 API 的同步与异步实现**，覆盖知识库检索、文档与分段访问、生成任务控制、反馈及终端用户信息，并补充 mock 测试。

这部分工作聚焦 AI 应用集成中的具体接口：让知识库检索与文档能力可以从 Python 工作流调用，并维护同步、异步客户端的接口一致性。
<!-- profile-ai:dify-sdk:end -->

### SIQ Agent Security · 安全场景与工具交付验证

<!-- profile-ai:siq:start -->
**开源贡献 · 相关 PR 审阅中** · [我的 fork](https://github.com/sunbos/siq-agent-security)

围绕 Agent 的授权边界、执行证据和 Skills 交付，补充可复现、可核验的工程验证：

- **安全场景复现**：为正常执行、MCP 收件人注入、同值不同来源、工具伪成功四类场景补充 Linux 复现报告与离线验证记录。[场景报告 PR #25](https://github.com/maoyadongsh/siq-agent-security/pull/25)
- **Skills 分发验证**：检查四种 Agent 目标的安装、卸载、目录内容和可执行位一致性，并补充分发测试与证据归档；范围是工具交付和生命周期验证。[分发验证 PR #29](https://github.com/maoyadongsh/siq-agent-security/pull/29)
<!-- profile-ai:siq:end -->

### sunbo-skills · 把日常脚本做成 Agent 工具

<!-- profile-ai:sunbo-skills:start -->
**个人工具实践** · [项目](https://github.com/sunbos/sunbo-skills) · [中文说明](https://github.com/sunbos/sunbo-skills/blob/main/README_CN.md)

将 HTML 清理与 Markdown 批量转换封装为可安装的 Agent Skill，支持编码检测、增量处理和预览，并通过 Claude Code Marketplace 分发。
<!-- profile-ai:sunbo-skills:end -->

## 技术关注与实践

从我的 Star 中精选，围绕 **Python 数据与测试、Agent 工作流、MCP 与文档处理**。已用于项目的部分附实践依据，其余记录具体关注点。

| 项目 | 关系 | 关注点与实践 |
| --- | --- | --- |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | 项目实践 | <!-- profile-ai:sqlalchemy:start -->候选分支采用：数据库连接、结构检查与事务管理，见 [sqlseed 适配实现](https://github.com/sunbos/sqlseed/blob/01b1584152aa1fc9f1135ea6add6fb1ab8c303be/src/sqlseed/database/sqlalchemy_adapter.py)（尚未合并）。<!-- profile-ai:sqlalchemy:end --> |
| [factory_boy](https://github.com/FactoryBoy/factory_boy) | 关注 | 测试数据工厂的复用方式，以及与声明式数据生成的取舍。 |
| [LangChain](https://github.com/langchain-ai/langchain) | 使用部分组件 | 测试 Agent 使用 Core／OpenAI 组件定义工具、接入模型；状态图编排由 LangGraph 完成，见[项目实践](#项目与实践)。 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 关注 | Agent 的工具组织、记忆机制与长期任务处理。 |
| [FastMCP](https://github.com/PrefectHQ/fastmcp) | 关注 | MCP 工具定义、参数约束与错误反馈的设计。 |
| [MarkItDown](https://github.com/microsoft/markitdown) | 关注 | 文档转 Markdown 的格式兼容与内容清洗质量。 |

[查看全部 Star](https://github.com/sunbos?tab=stars)

## GitHub 动态

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github_dark/0-profile-details.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/0-profile-details.svg">
  <img alt="sunbos 的 GitHub 贡献活动概览" src="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/0-profile-details.svg">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github_dark/3-stats.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/3-stats.svg">
  <img alt="sunbos 的 GitHub 统计摘要" src="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/3-stats.svg" width="340">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github_dark/2-most-commit-language.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/2-most-commit-language.svg">
  <img alt="sunbos 的 GitHub 提交按编程语言分布" src="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/2-most-commit-language.svg" width="340">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github_dark/1-repos-per-language.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/1-repos-per-language.svg">
  <img alt="sunbos 的 GitHub 仓库按编程语言分布" src="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/1-repos-per-language.svg" width="340">
</picture>
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github_dark/4-productive-time.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/4-productive-time.svg">
  <img alt="sunbos 的 GitHub 提交时间分布（UTC+8）" src="https://raw.githubusercontent.com/sunbos/sunbos/main/profile-summary-card-output/github/4-productive-time.svg" width="340">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/output/github-contribution-grid-snake-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/sunbos/sunbos/output/github-contribution-grid-snake.svg">
  <img alt="根据 sunbos 的 GitHub 贡献网格生成的贪吃蛇动画" src="https://raw.githubusercontent.com/sunbos/sunbos/output/github-contribution-grid-snake.svg">
</picture>

### 近期活动与关注

<img alt="sunbos 的 GitHub 活动、开源贡献关联与近期 Star" src="https://raw.githubusercontent.com/sunbos/sunbos/main/github-metrics.svg">

---

[所有公开项目](https://github.com/sunbos?tab=repositories) · [主页维护说明](.github/PROFILE.md)
