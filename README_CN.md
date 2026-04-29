# claudecode-team-pivot

> **个人实验工具。** 不是 team-pivot-web 的官方客户端，为我自己的 AI-native 工作流做的。一个人维护，无 SLA，欢迎 issue / PR。
>
> **MCP 优先注记（2026-04-29）。** 当前工作模式是：Pivot MCP 服务器作为主路径，本 skill 作为操作手册和 CLI/runner 兜底。代码已迁移到 Matter API（`/api/matters/*`），对应状态为 `planning / executing / paused / finished / cancelled / reviewed`，文件类型为 `think / act / verify / result / insight`。旧 `/api/threads/*` 概念不再作为用户文档主线。

这个仓库给 Claude Code 提供一份紧凑的 Pivot 操作手册，以及 MCP 暂未覆盖时可用的本地工具。它面向 [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web)，支持浏览 matter、读取时间线文件、带确认闸门的回复草稿、@ 同事、本地历史搜索和周报摘要。

执行通路按优先级分三层：

1. **Pivot MCP tools**：主路径。用于列 matter、解析 URL/context、读取 matter 详情、读取文件正文、创建时间线文件。它直接走当前 Matter API，也绕开本地编码和路径问题。
2. **`bin/pivot.py` 原子 CLI**：兜底路径。用于查联系人、独立 @-mention 评论、标已读、收藏、本地 mirror 同步/搜索/历史，以及 MCP 不可用时的基本操作。
3. **`runner.py` pipeline**：遗留/复杂流程。基于 Agent Pipeline Protocol v0.4 的 paused/resume 交接，适合 read/reply/draft/digest 这类需要 preflight 或确认闸门的流程。

相关官方项目（由 Pivot 团队维护，与本 skill 独立）：[team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web)（服务端 + Web UI + MCP 实现）、[vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot)、[intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot)。

English: [README.md](README.md)

## 前置依赖

- **Claude Code** 已安装（`~/.claude/skills/` 存在或可创建）。
- **Pivot MCP server 已配置**（推荐）。在 Claude Code 里 `/mcp` 应能看到 `pivot` server。MCP 是首选运行路径。
- **Python 3.8+** 用于 CLI/runner 兜底。macOS Ventura+ 不再预装 Python，可从 [python.org](https://www.python.org/downloads/) 或 Homebrew（`brew install python`）安装；Windows 可用 python.org 安装器并勾选加入 PATH。
- **PyYAML** 只在使用 `runner.py` pipeline 时需要：`python3 -m pip install pyyaml`。`bin/pivot.py` 原子命令不需要。
  - macOS Ventura+ 使用 python.org 安装器时可能遇到 PEP 668 `externally-managed-environment`。推荐顺序：
    1. `brew install python`，再 `python3 -m pip install pyyaml`
    2. `python3 -m pip install --user pyyaml`
    3. 最后才用 `python3 -m pip install --break-system-packages pyyaml`
- **git** 用于 clone、升级和本地 mirror。
- **ripgrep (`rg`)** 可选但推荐，mirror 全文搜索更快；没有时 CLI 会 fallback 到 `git grep`。

## 安装

### 让 agent 一键装

把下面这段发给 Claude Code：

```text
按 https://github.com/Jianping-Xiong/claudecode-team-pivot 的 README Installation 章节帮我装。
```

Claude 应该按当前 OS 安装为软链/junction；只有需要 CLI 兜底时才引导你配置 PAT。

### 手动安装 - macOS / Linux

```bash
# 1. clone 到本地工作区
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  ~/repository/claudecode-team-pivot

# HTTPS 备用：
# git clone https://github.com/Jianping-Xiong/claudecode-team-pivot.git \
#   ~/repository/claudecode-team-pivot

# 2. 软链到 Claude Code skills 目录
mkdir -p ~/.claude/skills
ln -s ~/repository/claudecode-team-pivot ~/.claude/skills/claudecode-team-pivot

# 3. 可选：创建 CLI 兜底配置
mkdir -p ~/.pivot
cp ~/.claude/skills/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

### 手动安装 - Windows

重要：Git Bash 的 `ln -s` 在默认环境下可能静默退化成完整复制。复制意味着 repo 里的更新不会同步到 skill 目录。请用 **directory junction**，不需要管理员权限，也不需要 Developer Mode。

推荐 PowerShell，因为它对含中文字符的用户目录更稳。

```powershell
# 1. clone
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git `
  D:\repository\claudecode-team-pivot

# 2. 建 junction
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
  -Target "D:\repository\claudecode-team-pivot"

# 3. 可选：创建 CLI 兜底配置
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.pivot" | Out-Null
Copy-Item D:\repository\claudecode-team-pivot\config.example.json `
  "$env:USERPROFILE\.pivot\config.json"
```

验证是真 junction：

```powershell
(Get-Item "$env:USERPROFILE\.claude\skills\claudecode-team-pivot").LinkType
# 期望：Junction
```

> PowerShell 注意：不要在 Windows PowerShell 5.1 下用 `Set-Content -Encoding UTF8` 重写 config，它会加 UTF-8 BOM。`Copy-Item` 会保留源文件编码。本工具用 `utf-8-sig` 读配置，能容忍 BOM，但其他工具未必。

## 配置 CLI 兜底 PAT

MCP 使用不依赖本仓库的本地 config。只有需要 `bin/pivot.py` 或 `runner.py` 时，才需要配置 `~/.pivot/config.json`。

交互式 setup：

```bash
# macOS / Linux
python3 ~/.claude/skills/claudecode-team-pivot/runner.py setup

# Windows PowerShell
python "$env:USERPROFILE\.claude\skills\claudecode-team-pivot\runner.py" setup
```

它会询问：

1. **Pivot server URL**：你平时登录 Pivot Web 的域名。
2. **PAT token**：在 `<base-url>/settings/api-tokens` 生成。建议按设备/客户端命名，例如 `mac-cc`、`windows-cc`。

非交互配置：

```bash
python runner.py setup --base-url https://pivot.<your-team>.com --token pvt_xxx
```

验证 CLI 兜底：

```bash
python runner.py check-init
python bin/pivot.py me
python bin/pivot.py matters --limit 5
```

常见失败：

- `[401:invalid_token]`：token 错误、过期，或不是这个 `base_url` 签发的。
- `[0:network_error]`：域名不可达、没开 VPN、URL 拼错。
- `requires PyYAML`：你在用 `runner.py`，需要安装 `pyyaml`。

## 升级

因为安装方式是软链/junction，升级只需要在本地 clone 里拉代码，不用重装。

```bash
cd ~/repository/claudecode-team-pivot      # Windows 下可用 D:\repository\...
git pull
python runner.py check-init                # 可选：CLI 兜底健康检查
python bin/pivot.py matters --limit 5       # 可选：CLI 兜底 smoke test
```

config、PAT、本地 mirror、sessions、drafts 都不会被动。

## 使用

在 Claude Code 里自然语言即可：

- "pivot 上有啥新讨论"
- "帮我看下这个 Pivot URL"
- "帮我读一下 OPC-数字员工服务台-产品规划"
- "给这个 matter 回一句：同意方案 A，先在测试环境跑一周"
- "pivot 上谁提过 ClickHouse"
- "这周讨论的重点是什么"

Skill 应该在 MCP 可用时优先选择 MCP。任何写入仍必须展示草稿并得到你明确确认后才能发布。

## MCP 优先工作流

当 `/mcp` 能看到 `pivot` 时，优先用这些工具：

| 工具 | 用途 |
|---|---|
| `mcp__pivot__resolve_context` | 解析 Pivot URL，获取 matter 快照和可用状态迁移。遇到 Pivot URL 时用它，不要 WebFetch。 |
| `mcp__pivot__list_matters` | 列 matter，支持 `status`、`owner`、标题查询过滤。 |
| `mcp__pivot__get_matter` | 获取 matter 元信息和时间线，不拉大正文。 |
| `mcp__pivot__read_files` | 读取时间线文件正文，最多 5 个文件 / 50000 字符。 |
| `mcp__pivot__create_file` | 创建时间线文件（`think / act / verify / result / insight`），可选带 `status_change`。 |

MCP 目前不覆盖查联系人、独立 @-mention 评论、标已读、收藏、本地 mirror 搜索。这些用 CLI 兜底。

严格规则：

- `create_file` / 回复必须展示草稿正文，并得到用户明确确认。
- `status_change` 必须由用户明确选择，绝不静默附加。
- @-mention 会发飞书通知，运行 CLI `mention` 前必须确认目标人和评论。
- 不为了改状态或提醒别人创建占位时间线文件。

## CLI 命令

原子命令使用 Matter API，参数是 `<matter_id>`，不是旧的 `<category>/<slug>` thread key。

```bash
python bin/pivot.py me
python bin/pivot.py matters [--status X] [--owner X] [--q X] [--unread-first] [--favorite-only] [--limit N]
python bin/pivot.py show <matter_id>
python bin/pivot.py contacts --search <name>
python bin/pivot.py mention <matter_id> --target-filename <F> --mention <ou_xxx,...> --mention-comment "短评"
python bin/pivot.py favorite <matter_id> [--unfavorite]
python bin/pivot.py read <matter_id>
python bin/pivot.py sync [--check]
python bin/pivot.py search <pattern>
python bin/pivot.py history --since 7d
```

完整参数：

```bash
python bin/pivot.py --help
python bin/pivot.py matters --help
```

## Runner Pipelines

Runner 仍可用于复杂流程和旧 APP v0.4 集成。它接受 `<matter_id>`，也兼容 `<category>/<matter_id>`。

```bash
python runner.py read --thread <matter_id>
python runner.py reply --thread <matter_id> --draft-file <path> [--mention <ou_xxx,...>]
python runner.py draft --thread <matter_id> --content-file <path>
python runner.py digest --since 7d
python runner.py resume <session> --llm-output '<json>'
```

Runner protocol：

- `completed`：把 `output` 展示给用户。
- `paused`：agent 完成 `llm_request`，然后 `resume`。
- `error`：展示错误，先修 config/network/token。

## 架构

```text
Claude Code
   |
   | 首选
   v
Pivot MCP server                  # 当前 Matter API 主路径
   |
   v
team-pivot-web /api/matters/*

本仓库兜底工具：

~/.pivot/config.json              # PAT + base_url + mirror_dir
~/.pivot/sessions/                # 暂停的 runner session
~/.pivot/drafts/                  # 持久化草稿
~/pivot-mirror/                   # 本地 git mirror，用于搜索/历史
        |
        v
bin/pivot.py                      # 原子 CLI 兜底
runner.py                         # APP v0.4 pipeline runner
        |
        v
team-pivot-web REST API
        + git mirror
```

- 写入永远走服务端 API。
- 读取优先 MCP/REST，保证新鲜。
- git mirror 只是全文搜索和本地大上下文加速层。
- Mirror 默认 `~/pivot-mirror/`，与 vscode-team-pivot 共用。

## 配置

优先级：环境变量 > `~/.pivot/config.json` > 内置默认值。

| 字段 | 环境变量 | 默认值 |
|---|---|---|
| `base_url` | `PIVOT_BASE_URL` | `https://pivot.enclaws.ai` |
| `token` | `PIVOT_TOKEN` | CLI/runner 必填 |
| `mirror_dir` | `PIVOT_MIRROR_DIR` | `~/pivot-mirror` |

内置 `base_url` 只是内部部署占位。CLI 兜底刚装完就报 `[0:network_error]` 时，优先检查 `base_url`。

## 给 AI Agent 安装时看

要问用户：

1. **安装路径**：可以建议 `~/repository/claudecode-team-pivot` 或 `D:\repository\claudecode-team-pivot`，但不要擅自假设。
2. **Pivot MCP 是否可用**：用 `/mcp` 看有没有 `pivot`。
3. **Pivot server `base_url`**：只有 CLI/runner 兜底需要。
4. **PAT token**：只有 CLI/runner 兜底需要。用户在 `<base-url>/settings/api-tokens` 自己生成。

配置兜底时优先用 `python runner.py setup`，不要手拼 config。

## 相关项目

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) - 服务端 + Web UI + REST 契约 + MCP 实现
- [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot) - VS Code 扩展
- [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot) - IntelliJ 插件
- [agent-pipeline-protocol](https://github.com/hashSTACS-Global/agent-pipeline-protocol) v0.4

## License

MIT
