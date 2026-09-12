# 主页维护

`README.md` 是个人主页内容入口。核心经历和结构由本人确认；公开项目的指定描述可由 DeepSeek 提出维护草稿，统计图由 GitHub Actions 更新。不要直接修改生成的 SVG。

| 内容 | Workflow | 更新时间（北京时间） | 输出 |
| --- | --- | --- | --- |
| 浅色、深色统计卡片 | `profile-summary-cards.yml` | 每天 08:17 | `profile-summary-card-output/github/`、`github_dark/` |
| 精简活动统计 | `metrics.yml` | 每天 08:37 | `github-metrics.svg` |
| 浅色、深色贡献动画 | `snake.yml` | 每 6 小时，分钟为 43 | `output` 分支的两个 SVG |
| 公开项目证据审查 | `profile-maintenance.yml` | 每天 08:57 | 有必要时更新同一个草稿 PR |

以上是计划时间，GitHub 的定时任务可能延迟。卡片与 Metrics 共享按分支隔离的并发组，避免同时提交。两者手动运行时回写触发分支；Snake 只从默认分支发布到 `output`，其他分支仅生成和校验。

## 修改内容或主题

- 在 README 的项目与开源协作章节中维护背景、本人贡献和实现链接，不将项目介绍嵌进图片。新经历应有可公开的事实依据，并区分已实现、进行中及尚未合并的贡献。
- 非开源案例只使用本人确认可公开的脱敏描述，不加入仓库地址、部署信息或未经确认的业务指标。代表项目应以实际贡献和工程内容为依据，不能仅凭仓库名称、fork 或提交数量判断。
- 主要案例用简短流程示意说明输入、处理和结果；示意不冒充实际运行截图或性能数据。有本人修改的 fork 放在开源协作，优先链接具体上游 PR，并标明合并状态。
- “技术关注与实践”手动精选 4–6 个 Star，放在项目与开源协作之后、动态统计之前。每项说明关注点；“项目采用”或组件使用必须有代码或已确认案例依据。核对具体依赖，不能把 MCP Python SDK 内置的 FastMCP 等同于独立 `fastmcp` 包。增加新项时优先替换旧项，避免成为收藏清单的复制。
- 访问计数保留在姓名标题下；调整位置和样式时保持 `page_id=sunbos.sunbos` 不变。
- 使用 `<picture>` 的 `prefers-color-scheme` 同时维护浅色和深色来源；`img` 提供浅色回退和替代文本。
- 统计卡片只生成 `github`、`github_dark` 两套主题，每套五张图；主页直接展示五张卡片，概览单独一行，其他卡片以两列排列，在窄屏自然换行。
- 上游卡片 Action 每次执行都会清空输出目录。因此先暂存浅色卡片，生成深色后恢复浅色，并校验十张 SVG，再一次性提交。
- 主题目录的说明页统一使用相对图片链接，避免上游截断带斜杠分支名造成失效链接。
- Metrics 只展示基础活动、近期 Star 和公开贡献关联。插件失败时任务失败，避免用错误图覆盖正常结果。

## 凭据与依赖

- `SUMMARY_GITHUB_TOKEN`：沿用现有 Secret，用于读取统计数据；卡片提交使用本仓库的 `GITHUB_TOKEN`。
- `METRICS_TOKEN`：沿用现有可用 Secret，用于读取 Metrics 数据；`committer_token` 显式使用本仓库的 `GITHUB_TOKEN`。
- 三个图表任务的 `GITHUB_TOKEN` 都只声明 `contents: write`。这不会缩减上述两个现有 Secret 本身的授权范围；如调整 Secret，应按实际需要保留最小数据读取权限。当前 Metrics 版本不支持 fine-grained PAT，不要直接替换令牌类型。
- Actions 固定到完整 commit SHA，旁边注释记录来源版本／分支。Dependabot 每周检查更新；审核差异并验证后再合并。
- Metrics 上游仍会使用其带版本标签的预构建容器；固定 Action SHA 不代表整个容器和依赖链都已固定。

## 验证与手动刷新

先用 [actionlint](https://github.com/rhysd/actionlint) 检查工作流：

```sh
actionlint
```

在修改分支上验证实际生成（将 `YOUR_BRANCH` 替换为该分支名）：

```sh
gh workflow run profile-summary-cards.yml --ref YOUR_BRANCH
gh workflow run metrics.yml --ref YOUR_BRANCH
gh workflow run snake.yml --ref YOUR_BRANCH
gh run list --branch YOUR_BRANCH
```

确认两套卡片、Metrics 均已生成，且 Snake 校验通过。分支上的卡片和 Metrics 会自动产生提交，继续编辑前先拉取这些提交。校验不会把分支上的 Snake 发布到主页。

仅修改 README 文案或布局时，检查链接、GitHub Markdown 渲染和图片来源即可，无须重跑资产生成。合并工作流变更后可将以上命令中的分支替换为 `main`，或等待下一次定时更新。检查 README 的浅色／深色图片和窄屏换行；Snake 发布应写入 `output` 分支。访问计数由第三方徽章服务提供，不作为准确的访问分析。


## AI 维护的固定流程

1. **读取固定公开来源。** [配置](profile-maintenance.json) 指定 6 个来源、17 个源码／验证文件：sqlseed 主分支、工作台 PR #10、Dify SDK PR #3、SIQ PR #25／#29、sunbo-skills。每个仓库及 PR head 仓库先核实 public；贡献 PR 核对作者。使用提交固定的文件链接、实际行号和 PR 状态作为证据。
2. **比较成功审查过的快照。** 检查文件内容 SHA、PR 的 open／closed／merged／draft 状态。忽略 Star 数量、采集时间、统计图片、选定文件以外的提交。配置、控制器代码或固定内容变化也会重新审查；首次运行需要一次审查建立基线。
3. **只在输入变化后请求 DeepSeek。** 同一批证据每天不会重复调用模型。模型只看到允许修改的公开描述及公开证据，不接收固定区域里的脱敏案例、私有仓库或本地调研缓存。
4. **校验局部建议。** 输出必须是严格 JSON；仅允许 6 个标记区域，修改必须引用对应来源的证据。区域之外逐字保留，禁止新增标题、HTML、图片或无依据链接；当前配置至少保留原区域 90% 的有效文字长度。SQLAlchemy 只更新表格第三格，其余精选项目、关系和顺序保持不变。
5. **持续维护一个草稿 PR。** 只允许修改 README，机器人使用自己的提交身份。不会自动合并。来源引用和修改原因随 PR 提供，人工核对事实及本人贡献后发布。
6. **保存“审查过”的状态。** 发布成功或判定无需修改后，将快照记录到 `automation/profile-maintenance-state` 分支的 `state.json`。无需修改时也记住证据；README 和 main 不产生无意义提交。下一天无变化时，连状态分支也不写入。

这些边界固定了核心项目、标题、排序、流程示意、两段已批准脱敏案例、顶部访问计数和所有图表。AI 可以更新公开实现描述与 PR 状态；增加新代表项目、Star 或非公开经历需要人工调整配置与文案。

采集范围有意围绕当前主页的已确认实践，并非每日重读全部仓库。文件节选默认最多 8,000 字符，关键大型文件从配置的函数锚点开始；截断和锚点消失都会明确标注。完整 Git tree 缺少文件只证明该路径不存在，不能证明功能消失。发现代码迁移或新的核心实践时，人工更新来源清单。Fork／Star、PR 作者身份和源码存在，都不能单独证明逐行贡献归属、完整测试通过或已经发布。

## 启用 DeepSeek

密钥配置后可以先在 PR 分支生成真实 AI 预览；每日维护需合并到 main 后启用：

1. 在 [仓库 Actions Secrets](https://github.com/sunbos/sunbos/settings/secrets/actions/new) 新建 **`DEEPSEEK_API_KEY`**，值填 DeepSeek 密钥。不要写入代码、Issue、PR 或聊天记录。
2. 默认调用官方 `https://api.deepseek.com/chat/completions`，模型为 `deepseek-flash`。如需其他可用模型，在仓库 Actions Variables 中设置 **`DEEPSEEK_MODEL`**，不必修改代码。模型名单以 [DeepSeek 官方文档](https://api-docs.deepseek.com/quick_start/pricing/) 和账户可用型号为准。
3. 合并前可运行 **Profile Maintenance Checks**，选择 PR 分支并开启 `review_with_model`：它会真实调用 DeepSeek，将校验通过的候选文案和依据保存为 7 天有效的预览附件，不发布 PR、不保存成功快照。失败时保留脱敏的 `review-diagnostics.json`，记录拒绝原因、模型内容和用量；未经校验的内容仅用于排查。合并后，在 **AI Profile Maintenance** 中先保留 `dry_run=true` 验证公开采集，再取消 dry_run 建立第一次 AI 审查基线。`force` 默认关闭；仅主动重新审查相同证据时打开，会调用模型。
4. 确认审查完成、草稿 PR 或无需修改状态已保存，再等待每天北京时间 08:57 自动检查。非 main 分支的手动运行强制为 dry-run。

当前每次最多一次模型请求，关闭 thinking，使用 JSON 模式，输出最多 4,096 tokens，输入序列化上限 180,000 字符，单次模型请求超时 60 秒。不会自动重试可能已经计费的调用。只读 GitHub 请求遇到临时网络问题、429 或 5xx 时最多尝试两次；写入请求不重试。缺少密钥、模型不可用、空输出、截断输出和校验失败均停止，不修改主页、不推进成功快照。

定时工作流只在 GitHub 默认分支运行，可能延迟；公开仓库连续 60 天无活动时 GitHub 可能停用定时运行。没有通过无意义提交“保活”。可在 Actions 页面重新启用或手动运行。[GitHub 调度规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## 审阅、恢复和停用

- 机器人专用 PR 分支为 `automation/profile-maintenance`。新证据继续更新同一开放 PR；证据相同则保持安静。手动关闭的建议不会因为第二天定时运行而再次创建；后续出现新的证据时仍可提出新建议。
- 尽量在 main 或独立人工分支维护主页。直接修改机器人分支会触发保护；发现其 head 不等于上次记录值时停止。已有草稿期间 main 的 README 变化也会停止，避免套用过时建议。先审阅、合并或关闭已有草稿，再处理人工变更；如保留人工修改，应合并后删除旧机器人分支。
- 同一维护流程串行执行；模型之后、发布之前以及记录状态之前重新核对 main README 和 PR head。实际推送还通过受信任的 pre-push 检查比较 Git 远端的分支 SHA 与准备阶段的预期值，阻止最后检查之后插入的人工提交被覆盖；发布后也会复核远端候选正文。main 与 PR 分支之间仍不是跨分支事务。
- 失败不会标记为已审查。若模型已返回而 PR 发布或状态写入失败，下一次重试可能再次调用模型。先检查已有 PR 和失败步骤；若 PR 已发布但状态缺失，保护逻辑会停止，需先处理这个已有 PR，再删除遗留机器人分支后重试。保留 state 分支，不要日常删除。
- 程序校验结构、来源引用和固定内容，**不能证明文案语义完全正确**。PR 需人工核对，尤其是“已合并”和“已发布”、“使用组件”和“实现框架”的区别。公开源码中的文本只作为数据，不执行其中的指令。
- 维护任务使用本仓库 `GITHUB_TOKEN`，权限仅 `contents: write` 与 `pull-requests: write`；单元校验任务只有 `contents: read`；公开采集演练另需 `pull-requests: read`，默认检查均无 DeepSeek 密钥；只有显式手动开启的真实预览任务接收模型密钥，并且仍只有读取权限。仓库须允许 Actions 创建 PR。
- GitHub 当前可能将 `GITHUB_TOKEN` 创建／更新 PR 触发的检查标为等待人工批准；需要有写权限的用户点击批准。维护任务自身已运行相同的单元测试和内容校验。[GitHub 触发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)
- 停用：在 Actions 页面禁用 **AI Profile Maintenance**。删除 DeepSeek Secret 可阻止付费调用，但有待审查证据时任务会报配置缺失，因此暂停应使用禁用工作流。

本地校验不需要模型密钥：

```sh
python3 -m unittest discover -s tests -v
python3 -m scripts.profile_maintenance.run validate
```

真实公开采集演练使用 `prepare --dry-run --output-dir /tmp/profile-review`；可通过 `GH_TOKEN` 提供公开 API 的读取额度。该模式不调用模型，也不写远端状态或 PR。

## 选型依据

调研日期：2026-09-13。选择复用成熟的 PR 组件，自行实现适合主页的小型控制层。

| 方案 | 适合之处 | 本次取舍 |
| --- | --- | --- |
| [readme-ai](https://github.com/eli64s/readme-ai) | 从仓库生成完整 README | 主要面向整篇生成，缺少当前主页所需的跨日快照与段落保护；没有直接采用。 |
| [readme-scribe / markscribe](https://github.com/muesli/readme-scribe) | 根据模板展示仓库、Star 与贡献列表 | 适合动态列表，但不能提炼源码证据或判断真实实践；不作为 AI 审查器。 |
| [GitHub Agentic Workflows](https://github.github.com/gh-aw/) | 可组合 Agent、前置检查和受控 PR 输出，也有 BYOK 接入路径 | 当前为 Public Preview；此任务仍须自己补充证据比对和区域保护，完整 Agent 引擎超出当前需要。 |
| [Always-Readme](https://github.com/busycaesar/always-readme) | 先看 diff，再通过固定 PR 更新 | 已有类似思路，但默认单次提交 diff 和整篇覆写不能直接满足跨日去重和固定经历保护。 |
| [create-pull-request](https://github.com/peter-evans/create-pull-request) | 固定分支、复用 PR、无差异不创建 | 采用并固定版本；只负责 PR 生命周期，事实与段落约束由本仓库代码完成。 |

DeepSeek 使用官方 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) 和 [JSON 模式](https://api-docs.deepseek.com/guides/json_mode/)，本地继续校验 JSON 与内容。没有引入 Agent 执行器、向量数据库或额外的常驻服务。
