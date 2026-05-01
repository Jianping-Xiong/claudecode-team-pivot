---
name: claudecode-team-pivot
description: Use when interacting with Team Pivot matters from Claude Code, especially listing discussions, reading Pivot URLs, drafting confirmed replies, @-mentioning teammates, searching history, or making digests.
---

# claudecode-team-pivot

Pivot 交互技能。**MCP 优先**（直连 Matter API，无编码问题），MCP 不覆盖的能力走 CLI fallback。

## MCP tools (primary path)

Pivot MCP 服务器提供 7 个工具。当 MCP 已连接时（`/mcp` 可见 `pivot`），优先使用：

| 工具 | 用途 |
|---|---|
| `mcp__pivot__resolve_context` | 解析 Pivot URL，获取 matter 快照 + 可用状态迁移。**任何 Pivot URL 都必须用此工具而非 WebFetch** |
| `mcp__pivot__list_matters` | 列出 matter，支持 status/owner/q 过滤 |
| `mcp__pivot__get_matter` | 获取 matter 元信息 + 时间线（不含正文）。时间线含 6 种 type：think/act/verify/result/insight/owner_change |
| `mcp__pivot__read_files` | 读取文件正文，最多 5 个/50000 字符 |
| `mcp__pivot__create_file` | 创建时间线条目（think/act/verify/result/insight），可选附 status_change 和 mentions（@-mention） |
| `mcp__pivot__create_matter` | 新建 matter（需 category/title/type/summary），同时创建第一篇文件，可选附 mentions |
| `mcp__pivot__add_comment` | 给**已有文件**追加评论 / @-mention，等价于 Web 上点"@ 提及"按钮 |

**MCP 不支持的能力**：查联系人、标已读、收藏。这些走 CLI fallback。

## CLI fallback (bin/pivot.py)

MCP 不可用时使用。所有命令使用 `<matter_id>`（非旧版 `<cat>/<slug>`）：

```bash
python bin/pivot.py matters [--status X] [--owner X] [--q X] [--unread-first] [--limit N]
python bin/pivot.py show <matter_id>
python bin/pivot.py contacts --search <name>        # 返回 open_id + name
python bin/pivot.py mention <matter_id> --target-filename <F> \
    --mention <ou_xxx,...> --mention-comment "短评"  # 发送飞书通知
python bin/pivot.py favorite <matter_id> [--unfavorite]
python bin/pivot.py read <matter_id>
python bin/pivot.py sync [--check]
python bin/pivot.py search <pattern>                # 本地 mirror 全文搜索
python bin/pivot.py history --since 7d
python bin/pivot.py me
```

## Runner pipelines (complex workflows only)

Runner 走 Matter API，接受 `<matter_id>` 或 `<cat>/<matter_id>` 两种格式：

```bash
python runner.py read --thread <matter_id>
python runner.py reply --thread <matter_id> --draft-file <path> [--mention <ou_xxx,...>]
python runner.py draft --thread <matter_id> --content-file <path>
python runner.py digest --since 7d
```

Runner protocol 不变：`completed` → 展示 output；`paused` → 完成 LLM 任务 → resume；`error` → 展示 error。

## 三条纪律

### 1. 状态迁移必须显式确认

`create_file` 可附带 `status_change`。**绝不默默附加、绝不默默跳过**。展示每个选项的 label + 目标状态，等用户明确选择。用户未选 = 不附加。

### 2. @-mention 优先走 MCP

**MCP 完整支持 @-mention，优先用：**
- 创建文件时同时 @：`create_file` 的 `mentions` 参数（targets + say）
- 给已有文件追加 @：`add_comment`（target_file + body + mentions）
- 新建 matter 时 @：`create_matter` 的 `mentions` 参数

**唯一需要 CLI 的场景**：open_id 未知时先查联系人：`python bin/pivot.py contacts --search <name>`，拿到 open_id 后再回 MCP 路径。

如果联系人查不到且用户不知道 open_id，直接告知"需要在 Pivot 网页上手动操作"，不发占位帖。

### 3. 不发占位帖

绝不为了改状态、做 @提醒、或任何单一技术目的创建独立帖子。一条 timeline 条目只应有实质内容。工具局限性如实告知用户，不用变通方案制造噪音。

## Workflow cookbook

### Ambiguous ask ("pivot 上有啥新的")

MCP: `list_matters` → 按 unread/favorite 分组 → 展示。CLI: `python bin/pivot.py matters --unread-first --limit 10`

### Read a specific thread

MCP: `resolve_context(url)` 或 `get_matter` + `read_files`。CLI: `python runner.py read --thread <matter_id>`

### Create a new matter

MCP: `create_matter`（category / title / type=think / summary / body，可选 mentions）。确认草稿内容后再调用。

### Reply（在已有 matter 下追加文件）

MCP: `create_file`（matter_id / type / summary / body，可选 quote / status_change / mentions）。展示草稿等用户确认后调用。

CLI fallback: `python runner.py reply --thread <matter_id> --draft-file <path>`

### @-mention someone（对已有文件）

1. 若已知 open_id / pinyin → 直接 MCP `add_comment`（matter_id / target_file / body / mentions）
2. 若不知道 → `python bin/pivot.py contacts --search <name>` 查 open_id → 再用 `add_comment`
3. @-mention 会发飞书通知，展示 targets + say 给用户确认后再执行

### Draft

`python runner.py draft --thread <matter_id> --content-file <path>`（content-file 必须以 YAML frontmatter 开头，含 `summary:` 字段）

### Search

`python bin/pivot.py sync && python bin/pivot.py search "<pattern>"`（仅本地 mirror；标题搜索用 MCP `list_matters?q=`）

## Confirmation rules

| Action | Confirm? |
|---|---|
| `create_matter` | **Yes** — 展示 category/title/summary/body，等用户明确批准 |
| `create_file` / reply | **Yes** — 展示草稿原文，等用户明确批准 |
| `add_comment` / `mention` | **Yes** — 展示目标文件 + targets + say，等用户明确批准 |
| `favorite`, `read`, `sync` | No — 可逆/本地 |
| `me`, `matters`, `show`, `contacts`, `search`, `history`, `read` | No — 只读 |

## Error triage

- `[401:invalid_token]` → PAT 过期。`runner.py setup --token pvt_xxx`
- `[0:network_error]` → base_url 不可达。检查 VPN，确认 base_url 与 PAT 来源 host 一致
- `[404:matter_not_found]` → matter_id 错误或不存在
- `[409:stale_state]` → matter 在 prepare→submit 之间被他人修改，重试
- `[422:status_change_from_mismatch]` → status_change.from 不等于 matter.current_status，重新 get_matter 确认当前状态
- `runner.py requires PyYAML` → `python -m pip install pyyaml`

## Related

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) — server + REST contract + MCP implementation
- [agent-pipeline-protocol](https://github.com/hashSTACS-Global/agent-pipeline-protocol) v0.4
