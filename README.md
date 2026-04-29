# claudecode-team-pivot

> **Personal experimental tool.** Not an official team-pivot-web client; I built it for my own AI-native workflow. Maintained solo. Happy to open issues/PRs, but no SLA.
>
> **MCP-first notice (2026-04-29).** The current working mode is: use the Pivot MCP server as the primary path, and keep this skill as the operating guide plus CLI/runner fallback. The code has moved to the Matter API (`/api/matters/*`), with matter states (`planning / executing / paused / finished / cancelled / reviewed`) and file types (`think / act / verify / result / insight`). Old `/api/threads/*` concepts are deprecated in user-facing docs.

This repository gives Claude Code a compact Pivot operating manual plus local tools for gaps that MCP does not cover yet. It talks to [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) so an agent can browse matters, read timeline files, draft replies with a confirmation gate, @-mention teammates, search local history, and produce digests.

Execution surfaces, in preferred order:

1. **Pivot MCP tools** - primary path for matter listing, URL/context resolution, detail reads, file body reads, and creating timeline files. This avoids local encoding/path issues and uses the current Matter API directly.
2. **Atomic CLI via `bin/pivot.py`** - fallback for contacts, @-mention comments, read marks, favorites, local mirror sync/search/history, and when MCP is unavailable.
3. **Runner pipelines via `runner.py`** - legacy/complex workflows with Agent Pipeline Protocol v0.4 paused/resume handoff. Keep for read/reply/draft/digest flows that need framework-enforced preflight or confirmation.

Related official projects (maintained by the Pivot team, independent of this skill): [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) (server + Web UI + MCP implementation), [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot), [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot).

中文版: [README_CN.md](README_CN.md)

## Prerequisites

- **Claude Code** installed and working (`~/.claude/skills/` must exist or be creatable).
- **Pivot MCP server configured** when available. In Claude Code, `/mcp` should show a `pivot` server. The MCP server is the preferred runtime path.
- **Python 3.8+** for CLI/runner fallback. macOS Ventura+ no longer ships Python by default; install via [python.org](https://www.python.org/downloads/) or Homebrew (`brew install python`). On Windows, the python.org installer can add `python` to PATH.
- **PyYAML** only for `runner.py` pipelines. Install with `python3 -m pip install pyyaml`. Atomic `bin/pivot.py` commands work without it.
  - On macOS Ventura+ with the python.org installer, you may hit PEP 668 `externally-managed-environment` errors. Preferred options:
    1. `brew install python` then `python3 -m pip install pyyaml`
    2. `python3 -m pip install --user pyyaml`
    3. `python3 -m pip install --break-system-packages pyyaml` as a last resort
- **git** for clone/upgrade and local mirror search.
- **ripgrep (`rg`)** optional but recommended for fast mirror search. The CLI falls back to `git grep`.

## Installation

### Quick install via agent

Paste this to Claude Code:

```text
Install the skill at https://github.com/Jianping-Xiong/claudecode-team-pivot
by following the Installation section of its README.
```

Claude should detect the OS, install the repo as a symlink/junction, and walk through the PAT step only if CLI fallback is needed.

### Manual install - macOS / Linux

```bash
# 1. Clone into your workspace
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  ~/repository/claudecode-team-pivot

# HTTPS fallback:
# git clone https://github.com/Jianping-Xiong/claudecode-team-pivot.git \
#   ~/repository/claudecode-team-pivot

# 2. Symlink into the Claude Code skills directory
mkdir -p ~/.claude/skills
ln -s ~/repository/claudecode-team-pivot ~/.claude/skills/claudecode-team-pivot

# 3. Optional: create CLI fallback config
mkdir -p ~/.pivot
cp ~/.claude/skills/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

### Manual install - Windows

Important: `ln -s` in Git Bash can silently fall back to a full copy when symlink creation is unsupported. A copy means repo edits do not propagate to the skill directory. Use a **directory junction** instead; it requires no admin rights and no Developer Mode.

PowerShell is recommended because it handles non-ASCII profile paths cleanly.

```powershell
# 1. Clone
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git `
  D:\repository\claudecode-team-pivot

# 2. Create junction
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
  -Target "D:\repository\claudecode-team-pivot"

# 3. Optional: create CLI fallback config
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.pivot" | Out-Null
Copy-Item D:\repository\claudecode-team-pivot\config.example.json `
  "$env:USERPROFILE\.pivot\config.json"
```

Verify it is a real junction:

```powershell
(Get-Item "$env:USERPROFILE\.claude\skills\claudecode-team-pivot").LinkType
# Expected: Junction
```

> PowerShell note: avoid rewriting config with `Set-Content -Encoding UTF8` on Windows PowerShell 5.1 because it adds a UTF-8 BOM. `Copy-Item` preserves the source encoding. The tools read config with `utf-8-sig`, but other tooling may be stricter.

## Configure CLI Fallback PAT

MCP usage does not require this repository's local config. Configure `~/.pivot/config.json` only when you need `bin/pivot.py` or `runner.py`.

Guided setup:

```bash
# macOS / Linux
python3 ~/.claude/skills/claudecode-team-pivot/runner.py setup

# Windows PowerShell
python "$env:USERPROFILE\.claude\skills\claudecode-team-pivot\runner.py" setup
```

The command prompts for:

1. **Pivot server URL** - the host you use for Pivot Web.
2. **PAT token** - generate it at `<base-url>/settings/api-tokens`. Name it per device/client, such as `mac-cc` or `windows-cc`.

Non-interactive setup:

```bash
python runner.py setup --base-url https://pivot.<your-team>.com --token pvt_xxx
```

Verify CLI fallback:

```bash
python runner.py check-init
python bin/pivot.py me
python bin/pivot.py matters --limit 5
```

Common failures:

- `[401:invalid_token]` - token is wrong, expired, or signed by a different host than `base_url`.
- `[0:network_error]` - host unreachable, VPN missing, or URL typo.
- `requires PyYAML` - install `pyyaml` if you are using `runner.py`.

## Upgrade

Because the skill is installed as a symlink/junction, upgrading is just a pull inside the workspace clone. No reinstall is needed.

```bash
cd ~/repository/claudecode-team-pivot      # or D:\repository\... on Windows
git pull
python runner.py check-init                # optional CLI fallback sanity check
python bin/pivot.py matters --limit 5       # optional CLI fallback smoke test
```

Config, PAT, local mirror, sessions, and drafts remain untouched.

## Usage

In Claude Code, talk naturally:

- "pivot 上有啥新讨论"
- "帮我看下这个 Pivot URL"
- "帮我读一下 OPC-数字员工服务台-产品规划"
- "给这个 matter 回一句：同意方案 A，先在测试环境跑一周"
- "pivot 上谁提过 ClickHouse"
- "这周讨论的重点是什么"

The skill should choose MCP first when available. Writes must still be shown to you for explicit approval before publishing.

## MCP-First Workflow

When `/mcp` shows `pivot`, prefer these tools:

| Tool | Use |
|---|---|
| `mcp__pivot__resolve_context` | Resolve a Pivot URL into a matter snapshot and available status transitions. Use this for Pivot URLs instead of WebFetch. |
| `mcp__pivot__list_matters` | List matters with `status`, `owner`, or title query filters. |
| `mcp__pivot__get_matter` | Get matter metadata and timeline without large file bodies. |
| `mcp__pivot__read_files` | Read timeline file bodies, up to 5 files / 50000 chars. |
| `mcp__pivot__create_file` | Create a timeline file (`think / act / verify / result / insight`) with optional `status_change`. |

MCP currently does not cover contact search, standalone @-mention comments, mark-read, favorite, or local mirror search. Use CLI fallback for those.

Strict rules:

- `create_file` / reply requires explicit user confirmation with the draft body shown.
- Any `status_change` must be explicitly selected by the user; never attach one silently.
- @-mention sends Feishu notification. Confirm target person and comment before running CLI `mention`.
- Do not create placeholder timeline files just to change state or notify someone.

## CLI Commands

Atomic commands use the Matter API and accept `<matter_id>`, not old `<category>/<slug>` thread keys.

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

For full arguments:

```bash
python bin/pivot.py --help
python bin/pivot.py matters --help
```

## Runner Pipelines

Runner remains useful for complex flows and for older APP v0.4 integrations. It accepts `<matter_id>` and also tolerates `<category>/<matter_id>` for compatibility.

```bash
python runner.py read --thread <matter_id>
python runner.py reply --thread <matter_id> --draft-file <path> [--mention <ou_xxx,...>]
python runner.py draft --thread <matter_id> --content-file <path>
python runner.py digest --since 7d
python runner.py resume <session> --llm-output '<json>'
```

Runner protocol:

- `completed` - show `output` to the user.
- `paused` - the agent completes the `llm_request`, then calls `resume`.
- `error` - surface the error and fix config/network/token issues first.

## Architecture

```text
Claude Code
   |
   | preferred
   v
Pivot MCP server                  # current Matter API path
   |
   v
team-pivot-web /api/matters/*

Fallback tools in this repo:

~/.pivot/config.json              # PAT + base_url + mirror_dir
~/.pivot/sessions/                # paused runner sessions
~/.pivot/drafts/                  # persistent drafts
~/pivot-mirror/                   # local git mirror for search/history
        |
        v
bin/pivot.py                      # atomic CLI fallback
runner.py                         # APP v0.4 pipeline runner
        |
        v
team-pivot-web REST API
        + git mirror
```

- Writes always go through the server API.
- Reads prefer MCP/REST for freshness.
- The git mirror is only an accelerator for full-text search and rich local context.
- Mirror defaults to `~/pivot-mirror/`, shared with vscode-team-pivot.

## Config

Precedence: env var > `~/.pivot/config.json` > built-in default.

| Key | Env var | Default |
|---|---|---|
| `base_url` | `PIVOT_BASE_URL` | `https://pivot.enclaws.ai` |
| `token` | `PIVOT_TOKEN` | required for CLI/runner |
| `mirror_dir` | `PIVOT_MIRROR_DIR` | `~/pivot-mirror` |

The built-in `base_url` is a placeholder for internal deployments. If CLI fallback returns `[0:network_error]` right after install, check `base_url` first.

## For AI Agents Installing This Skill

Ask the user for:

1. **Install path** - suggest `~/repository/claudecode-team-pivot` or `D:\repository\claudecode-team-pivot`, but do not assume.
2. **Pivot MCP availability** - check `/mcp` for `pivot`.
3. **Pivot server `base_url`** - needed only for CLI/runner fallback.
4. **PAT token** - needed only for CLI/runner fallback. The user generates it at `<base-url>/settings/api-tokens`.

Prefer `python runner.py setup` over manually constructing config when configuring fallback.

## Related

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) - server + Web UI + REST contract + MCP implementation
- [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot) - VS Code extension
- [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot) - IntelliJ plugin
- [agent-pipeline-protocol](https://github.com/hashSTACS-Global/agent-pipeline-protocol) v0.4

## License

MIT
