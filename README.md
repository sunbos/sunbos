<div align="center">

# SunBo · sunbos

**LLM 应用 · MCP 工具 · 数据生成 · 工程验证**

把模型能力接入实际工具，让生成与执行结果可以检查、反馈和复现。

[sqlseed](https://github.com/sunbos/sqlseed) · [GemmaSQLSeed](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/tree/main/submissions/2026/track_A/GemmaSQLSeed) · [开源贡献](https://github.com/search?q=author%3Asunbos+is%3Apr&type=pullrequests)

</div>

我维护 sqlseed，也参与 AI 应用接口、Agent 安全验证与工具分发的开源工作。我的实践围绕模型与执行系统之间的连接：提供上下文、形成结构化配置、调用工具，以及检查结果。

`Python` · `LLM APIs` · `MCP` · `SQLite` · `同步 / 异步 SDK` · `pytest` · `GitHub Actions`

## 项目与实践

### sqlseed · 从 AI 配置生成到数据执行

**作者 / 维护者** · [项目](https://github.com/sunbos/sqlseed) · [架构](https://github.com/sunbos/sqlseed/blob/main/docs/architecture.md) · [AI 实现](https://github.com/sunbos/sqlseed/tree/main/plugins/sqlseed-ai) · [MCP 实现](https://github.com/sunbos/sqlseed/tree/main/plugins/mcp-server-sqlseed)

开发和测试需要能表达业务规则、保留关联关系、重复生成的数据。我在 sqlseed 中把声明式数据引擎与 AI 配置生成接在一起：

- **给模型提供数据库上下文**：整理 schema、索引、外键、数据样本及分布信息，生成可复用的数据规则。
- **验证与反馈修正**：配置经过结构校验、列名核对和少量样本预览；把错误摘要反馈给模型，在限定重试次数内修正配置。
- **通过 MCP 接入 AI 助手**：提供 schema 资源，以及检查、生成配置和执行填充的工具入口。
- **处理实际的数据约束**：表依赖拓扑排序、循环依赖检测、外键关联和固定 seed，让配置能接入可复现的数据生成流程。

> **正在构建：数据生成工作台。** 将字段规则调整、预览、生成和记录查看串成可交互流程，并完善候选包交付。[工作台 PR](https://github.com/sunbos/sqlseed/pull/10) 尚未合并。

### GemmaSQLSeed · sqlseed 的 AI Agent 参赛实践

**2026.06 · GDG 上海 Gemma 4 开发者大赛 · AI Agent 赛道**

围绕自然语言需求、SQLite schema 理解、配置生成和反馈修正，提交 GemmaSQLSeed 参赛作品与技术报告。作品与 sqlseed 共用技术基础，重点呈现模型如何参与数据生成工作流。

参赛材料通过两次 PR 合并收录，可查看问题定义、工具设计与技术方案：

[作品与技术报告](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/tree/main/submissions/2026/track_A/GemmaSQLSeed) · [首次提交 #19](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/pull/19) · [后续完善 #39](https://github.com/gdgshanghai/Gemma4-Hackathon-ShangHai/pull/39)

## 开源协作

### Dify Python SDK · AI 应用接口集成

**代码贡献 · PR 审阅中** · [上游 PR #3](https://github.com/langgenius/dify-python-sdk/pull/3)

为 SDK 补充 **7 类 API 的同步与异步实现**，覆盖知识库检索、文档与分段访问、生成任务控制、反馈及终端用户信息，并补充 mock 测试。

这部分工作聚焦 AI 应用集成中的具体接口：让知识库检索与文档能力可以从 Python 工作流调用，并维护同步、异步客户端的接口一致性。

### SIQ Agent Security · 安全场景与工具交付验证

**开源贡献 · 相关 PR 审阅中**

围绕 Agent 的授权边界、执行证据和 Skills 交付，补充可复现、可核验的工程验证：

- **安全场景复现**：为正常执行、MCP 收件人注入、同值不同来源、工具伪成功四类场景补充 Linux 复现报告与离线验证记录。[场景报告 PR #25](https://github.com/maoyadongsh/siq-agent-security/pull/25)
- **Skills 分发验证**：检查四种 Agent 目标的安装、卸载、目录内容和可执行位一致性，并补充分发测试与证据归档；范围是工具交付和生命周期验证。[分发验证 PR #29](https://github.com/maoyadongsh/siq-agent-security/pull/29)

### sunbo-skills · 把日常脚本做成 Agent 工具

**个人工具实践** · [项目](https://github.com/sunbos/sunbo-skills) · [中文说明](https://github.com/sunbos/sunbo-skills/blob/main/README_CN.md)

将 HTML 清理与 Markdown 批量转换封装为可安装的 Agent Skill，支持编码检测、增量处理和预览，并通过 Claude Code Marketplace 分发。

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

[所有公开项目](https://github.com/sunbos?tab=repositories&type=source) · [主页维护说明](.github/PROFILE.md)

![主页访问次数](https://visitor-badge.laobi.icu/badge?page_id=sunbos.sunbos&left_color=%23333333&right_color=%23ff5555&left_text=👥%20Total%20Views)
