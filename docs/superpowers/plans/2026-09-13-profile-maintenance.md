# Profile Maintenance Implementation Plan

> **For agentic workers:** Use subagent-driven-development for the independent collector, reviewer and state components. Integrate and review in this task.

**Goal:** 每天检查选定公开项目的实质证据，仅在变化后用 DeepSeek 审查，保护核心叙事并更新同一个草稿 PR。

**Architecture:** Python 标准库完成公开证据采集、快照比较、受限 JSON 审查和段落验证；GitHub Actions 定时运行，create-pull-request 负责 PR 生命周期。成功审查的快照写入独立状态分支，包含“无需修改”结果；失败不推进状态。

**Tech Stack:** Python 3.12、unittest、GitHub REST API、DeepSeek Chat Completions、GitHub Actions、create-pull-request v8.1.1。

---

## 固定约束

- 核心项目和排序、标题、流程示意、两段已批准脱敏案例、访问徽章、图表及精选 Star 名单不允许模型改写。
- 只有 README 中明确标记的公开描述可以更新。每个修改引用本轮采集的、属于该区域的证据 ID。
- 所有来源逐一验证为 public；不读取私有仓库、不执行源码、不读取本地私有调研缓存。
- Fork、Star 不代表本人贡献；已合并、未合并、关闭、已发布分别表述。未证明的指标、使用关系和经历不得新增。
- 首次运行审查一次以建立基线；随后忽略统计数量、时间戳、未选中文件的提交。SQLAlchemy 表格只编辑第三格内的标记内容，保持 Markdown 表格连续。状态或选定源码变化才调用模型。
- 每次最多一次模型请求，不自动重试可能已经计费的请求；最大输入、输出、网络超时均有限制。无变化不检查密钥、不调用模型、不提交。
- 只维护一个机器人专用草稿 PR，不自动合并。发现人工修改机器人分支或主页并发变化即停止，避免覆盖。

## 文件与接口

- `scripts/profile_maintenance/collector.py`：`collect(config, get_json) -> dict` 返回 `{"snapshot": dict, "evidence": list}`。`get_json(path)` 仅接受 GitHub API 相对路径；证据项含 `id, source_id, url, text`。快照包含选中文件的 blob SHA 和 PR 事实，不包含采集时间或无关计数；证据使用固定 commit URL。
- `scripts/profile_maintenance/reviewer.py`：`extract_blocks(readme, config) -> dict`、`protected_text(readme, config) -> str`、`apply_updates(readme, config, evidence, response) -> str`、`review(config, blocks, evidence, api_key) -> dict`。响应固定为 `{"summary": str, "updates": [{"block_id": str, "markdown": str, "evidence_ids": [str]}]}`，空 updates 表示不修改。
- `scripts/profile_maintenance/state.py`：`GitHubClient(token)` 的 `get(path)`、`write(method,path,payload)`；`load_state(client,config) -> (state_or_none,file_sha_or_none)`；`save_state(client,config,state,file_sha)` 使用 Contents API 的文件 SHA 条件更新；`load_proposal(client,config,state,base_readme) -> dict|None` 只接受匹配上次记录 head 的开放 PR，返回 number/head_sha/readme；`assert_base_unchanged(client,config,base_readme)` 发布前核对当前 main README；`fingerprint(config,snapshot,protected) -> str`。
- `scripts/profile_maintenance/run.py`：命令 `prepare --output-dir PATH [--dry-run] [--force]` 采集与审查、写本地候选与待保存状态；命令 `checkpoint --output-dir PATH --pr-head-sha SHA` 在 PR 发布成功或无需变更后保存状态。环境变量 `GH_TOKEN`、`DEEPSEEK_API_KEY`、可选 `DEEPSEEK_MODEL`；不记录密钥和原始 HTTP 错误响应。
- `.github/profile-maintenance.json`：固定允许来源、文件、区域和模型；README 标记为 `<!-- profile-ai:ID:start -->` / `<!-- profile-ai:ID:end -->`。
- `.github/workflows/profile-maintenance.yml`：每日北京时间 08:57、手动 dry-run/force；运行单元测试→prepare→受限文件 PR→checkpoint。状态独立分支不改变 main，PR Action 限 README。
- `.github/workflows/profile-maintenance-check.yml`：无密钥的单元测试、标记与公开采集检查；显式手动选择时，使用密钥进行只读模型预览。
- `.github/PROFILE.md`：选型、来源范围、启用和停用、故障与私有案例规则。

## Task 1: 证据采集

- [x] 写 `tests/test_collector.py`：无关 head/计数变化不改变 snapshot、选中文件变化改变 snapshot、PR 三种状态不同、私有来源拒绝且不读内容、404/截断失败不冒充空证据、证据引用固定 SHA。
- [x] 运行 `python3 -m unittest discover -s tests -p test_collector.py -v`，确认缺少实现导致失败。
- [x] 实现 `collector.py`，每个来源先检查可见性再读取内容，固定文件清单、响应大小和文件长度上限。
- [x] 重跑相同测试，确认全部通过。

## Task 2: DeepSeek 与局部更新

- [x] 写 `tests/test_reviewer.py`：合法局部变更保留其余字节、未知/重复区域和跨区域证据拒绝、空 JSON/截断拒绝、HTML/新标题/外链/明显密钥拒绝、删空或过度缩减拒绝、无 updates 不改变原文。
- [x] 运行 `python3 -m unittest discover -s tests -p test_reviewer.py -v`，确认缺少实现导致失败。
- [x] 实现 `reviewer.py`，官方接口固定 HTTPS，默认 `deepseek-v4-pro`、JSON 模式、开启 thinking、无工具、单次请求。
- [x] 重跑相同测试，确认全部通过。

## Task 3: 持久状态与并发保护

- [x] 写 `tests/test_state.py`：状态不存在与网络失败区分、使用 SHA 防覆盖写、人工 PR 提交拒绝、主分支 README 变化拒绝、无关资产提交允许、稳定 fingerprint。
- [x] 运行 `python3 -m unittest discover -s tests -p test_state.py -v`，确认缺少实现导致失败。
- [x] 实现 `state.py`，独立 `automation/profile-maintenance-state` 分支记录成功快照，任何 HTTP/权限/冲突错误失败退出。
- [x] 重跑相同测试，确认全部通过。

## Task 4: 集成与交付

- [x] 写 `tests/test_run.py`：重复快照调用次数为零、无更新也 checkpoint、异常不写状态、dry-run 不调用模型、不写远端。
- [x] 运行 `python3 -m unittest discover -s tests -p test_run.py -v`，确认预期失败。
- [x] 实现 `run.py`，候选文件和报告只写指定临时目录；验证完成后由 workflow 将候选 README 复制到工作树。
- [x] 配置公开来源和 README 区域，增加定时与校验 workflow；固定所有 Action SHA，限制写入路径，发布前检查 base 和 PR head。
- [x] 执行 `python3 -m unittest discover -s tests -v`、`.git/tools/actionlint`、`git diff --check`、真实公开采集 dry-run；独立审核内容保护和失败路径。
- [x] 更新维护说明和 PR #2，说明已验证范围、尚需 Secret 和合并后才能启用的事实。

## Verification record

2026-09-13: 112 tests passed locally, including real temporary Git repositories for concurrent push protection. actionlint and git diff --check passed. GitHub Markdown rendering preserved one seven-row table and six picture groups. Public evidence collection covered six sources and 21 evidence items (17 selected files plus four PR facts); model payload is bounded and excludes protected cases. Live provider and scheduled publication remain pending the DeepSeek Secret and default-branch merge.

2026-09-13 provider verification: the DeepSeek Secret is valid. The initial Flash response failed format/content validation; a subsequent Flash preview passed structural checks but contained an incorrect retry claim and removed the confirmed partial-failure recovery capability. Neither suggestion was applied. The collector now includes errors.py, recovery.js and its tests; protected_phrases rejects the exact prior deletion. DeepSeek V4 Pro with thinking completed a real 24-evidence review and returned no updates, leaving the candidate identical to the base README. Run: https://github.com/sunbos/sunbos/actions/runs/34721330457 . Replaying that real snapshot with an in-memory successful checkpoint made zero additional model calls and zero remote writes. All actual-review explanations now appear in the Actions summary, including no-change decisions. Scheduled publication remains pending the default-branch merge; preview does not create a checkpoint.

Final local verification: 146 tests passed, including the known bad-candidate replay and visible no-change review explanations; actionlint, block validation and git diff --check passed.
