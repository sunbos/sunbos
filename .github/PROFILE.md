# 主页维护

`README.md` 是个人主页内容入口。项目介绍和链接手动维护，统计图由 GitHub Actions 更新；不要直接修改生成的 SVG。

| 内容 | Workflow | 更新时间（北京时间） | 输出 |
| --- | --- | --- | --- |
| 浅色、深色统计卡片 | `profile-summary-cards.yml` | 每天 08:17 | `profile-summary-card-output/github/`、`github_dark/` |
| 精简活动统计 | `metrics.yml` | 每天 08:37 | `github-metrics.svg` |
| 浅色、深色贡献动画 | `snake.yml` | 每 6 小时，分钟为 43 | `output` 分支的两个 SVG |

以上是计划时间，GitHub 的定时任务可能延迟。卡片与 Metrics 共享按分支隔离的并发组，避免同时提交。两者手动运行时回写触发分支；Snake 只从默认分支发布到 `output`，其他分支仅生成和校验。

## 修改内容或主题

- 在 README 的项目与开源协作章节中维护背景、本人贡献和实现链接，不将项目介绍嵌进图片。新经历应有可公开的事实依据，并区分已实现、进行中及尚未合并的贡献。
- 非开源案例只使用本人确认可公开的脱敏描述，不加入仓库地址、部署信息或未经确认的业务指标。代表项目应以实际贡献和工程内容为依据，不能仅凭仓库名称、fork 或提交数量判断。
- 访问计数保留在姓名标题下；调整位置和样式时保持 `page_id=sunbos.sunbos` 不变。
- 使用 `<picture>` 的 `prefers-color-scheme` 同时维护浅色和深色来源；`img` 提供浅色回退和替代文本。
- 统计卡片只生成 `github`、`github_dark` 两套主题，每套五张图；主页直接展示五张卡片，概览单独一行，其他卡片以两列排列，在窄屏自然换行。
- 上游卡片 Action 每次执行都会清空输出目录。因此先暂存浅色卡片，生成深色后恢复浅色，并校验十张 SVG，再一次性提交。
- 主题目录的说明页统一使用相对图片链接，避免上游截断带斜杠分支名造成失效链接。
- Metrics 只展示基础活动、近期 Star 和公开贡献关联。插件失败时任务失败，避免用错误图覆盖正常结果。

## 凭据与依赖

- `SUMMARY_GITHUB_TOKEN`：沿用现有 Secret，用于读取统计数据；卡片提交使用本仓库的 `GITHUB_TOKEN`。
- `METRICS_TOKEN`：沿用现有可用 Secret，用于读取 Metrics 数据；`committer_token` 显式使用本仓库的 `GITHUB_TOKEN`。
- 三个任务的 `GITHUB_TOKEN` 都只声明 `contents: write`。这不会缩减上述两个现有 Secret 本身的授权范围；如调整 Secret，应按实际需要保留最小数据读取权限。当前 Metrics 版本不支持 fine-grained PAT，不要直接替换令牌类型。
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
