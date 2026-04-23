# claudecode-team-pivot

> **Personal experimental tool.** Not an official team-pivot-web client; I built it for my own AI-native CLI workflow. Maintained solo. Happy to open issues/PRs, but no SLA.

A Claude Code **APP** ([Agent Pipeline Protocol v0.4](https://github.com/hashSTACS-Global/agent-pipeline-protocol)) for talking to [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) in natural language — browse threads, summarize, draft replies with a mandatory confirmation gate, @-mention teammates, full-text search history, weekly digests.

Two execution surfaces:
- **Pipelines via `runner.py`** — multi-step flows with framework-enforced preflight checks + LLM steps (read / reply / draft / digest). Handles `{status: paused, llm_request: {...}}` / `runner.py resume` handoff with Claude Code.
- **Atomic commands via `bin/pivot.py`** — single-API-call ops (threads / show / contacts / mention / status / favorite / read / sync / search / history / me). Zero-dep, works without PyYAML.

Related official projects (maintained by the Pivot team, independent of this skill): [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) (server + Web UI), [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot), [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot).

中文版: [README_CN.md](README_CN.md)

## Prerequisites

- **Claude Code** installed and working (`~/.claude/skills/` must exist or be creatable).
- **Python 3.8+** — macOS Ventura+ no longer ships Python by default; install via [python.org](https://www.python.org/downloads/) or Homebrew (`brew install python`). On Windows, the python.org installer adds `python` to PATH.
- **PyYAML** — required for `runner.py` pipelines. Install with `python3 -m pip install pyyaml`. (Atomic `bin/pivot.py` commands work without it.)
  - On macOS Ventura+ with the python.org installer, you may hit PEP 668 `externally-managed-environment` errors. Three options, in preferred order:
    1. `brew install python` then `python3 -m pip install pyyaml` (clean)
    2. `python3 -m pip install --user pyyaml` (install into user site-packages)
    3. `python3 -m pip install --break-system-packages pyyaml` (last resort; trades safety for convenience)
- **git** — preinstalled on macOS (Xcode Command Line Tools prompt on first use), `brew install git` otherwise; Windows via [git-scm.com](https://git-scm.com/).
- **ripgrep (`rg`)** *optional* — full-text search is 5-10× faster with it. Install via `brew install ripgrep` (macOS), `winget install BurntSushi.ripgrep.MSVC` (Windows), or the [release page](https://github.com/BurntSushi/ripgrep/releases). The skill automatically falls back to `git grep` if `rg` is not on PATH.

## Installation

### Quick install via agent

Paste this to Claude Code:

```
Install the skill at https://github.com/Jianping-Xiong/claudecode-team-pivot
by following the Installation section of its README.
```

Claude will detect your OS, pick the right commands from below, and walk you through the PAT step.

### Manual install — macOS / Linux

```bash
# 1. Clone into your workspace
#    SSH (preferred if you've set up GitHub SSH keys):
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  ~/repository/claudecode-team-pivot
#    HTTPS (fallback if SSH isn't configured on this machine):
# git clone https://github.com/Jianping-Xiong/claudecode-team-pivot.git \
#   ~/repository/claudecode-team-pivot

# 2. Symlink into the Claude Code skills directory
mkdir -p ~/.claude/skills
ln -s ~/repository/claudecode-team-pivot ~/.claude/skills/claudecode-team-pivot

# 3. Create config file (then populated via `runner.py setup` below, or edit by hand)
mkdir -p ~/.pivot
cp ~/.claude/skills/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

### Manual install — Windows

Important: `ln -s` in Git Bash **silently falls back to a full copy** when symlink creation is not supported (the default without Developer Mode ON or `MSYS=winsymlinks:nativestrict` set). A copy means edits to the repo do NOT propagate to the skills directory. Use a **directory junction** instead — no admin, no Dev Mode required.

PowerShell is recommended because it handles non-ASCII user profile paths (e.g. Chinese names) cleanly. Git Bash works too but be careful with path syntax.

**PowerShell** (recommended):

```powershell
# 1. Clone (adjust drive as needed)
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git `
  D:\repository\claudecode-team-pivot

# 2. Create junction
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\skills" | Out-Null
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
  -Target "D:\repository\claudecode-team-pivot"

# 3. Create config
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.pivot" | Out-Null
Copy-Item D:\repository\claudecode-team-pivot\config.example.json `
  "$env:USERPROFILE\.pivot\config.json"
```

> PowerShell note: **do not** rewrite the config with `Set-Content -Encoding UTF8` on Windows PowerShell 5.1 — it adds a UTF-8 BOM. `Copy-Item` (above) preserves the source encoding and is safe. If you need to regenerate the file from scratch, use: `[System.IO.File]::WriteAllText("$env:USERPROFILE\.pivot\config.json", $content, (New-Object System.Text.UTF8Encoding $false))`. The skill reads config with `utf-8-sig` anyway, but other tooling may not be BOM-tolerant.

**Git Bash** (alternative — note the PowerShell call-out for the junction step, since `ln -s` is unsafe):

```bash
# 1. Clone
git clone git@github.com:Jianping-Xiong/claudecode-team-pivot.git \
  /d/repository/claudecode-team-pivot

# 2. Create junction — delegate to PowerShell so Unicode paths stay safe
mkdir -p ~/.claude/skills
powershell.exe -NoProfile -Command \
  'New-Item -ItemType Junction `
    -Path "$env:USERPROFILE\.claude\skills\claudecode-team-pivot" `
    -Target "D:\repository\claudecode-team-pivot"'

# 3. Create config (note: Git Bash uses Unix-style paths under /d/..., /c/...)
mkdir -p ~/.pivot
cp /d/repository/claudecode-team-pivot/config.example.json ~/.pivot/config.json
```

Verify it's a real junction and not a copy:

```powershell
(Get-Item "$env:USERPROFILE\.claude\skills\claudecode-team-pivot").LinkType
# Expected output: Junction
```

### Configure your PAT (all platforms)

The fastest path is the guided setup:

```bash
# macOS / Linux
python3 ~/.claude/skills/claudecode-team-pivot/runner.py setup

# Windows (PowerShell)
python "$env:USERPROFILE\.claude\skills\claudecode-team-pivot\runner.py" setup
```

The command prompts for:
1. **Your team's Pivot server URL** (e.g. `https://pivot.<your-team>.com` — whatever host you log into for Pivot Web)
2. **A PAT token** — generate one at `<base-url>/settings/api-tokens`. Name it per-device + per-client (e.g. `mac-cc`, `windows-cc`; don't share with your `*-vs-code` tokens). The **plaintext is shown only once** — copy immediately.

Setup writes `~/.pivot/config.json` (UTF-8 no BOM) and runs the constructor to verify end-to-end. A successful run prints `status: completed` plus next-step commands.

For non-interactive / scripted install:

```bash
python runner.py setup --base-url https://pivot.<your-team>.com --token pvt_xxx
```

**Manual alternative**: copy `config.example.json` to `~/.pivot/config.json`, edit `base_url` and `token`, then verify with `python runner.py check-init`.

**Verification command**:
```bash
python runner.py check-init   # or: python bin/pivot.py me
```
Expected: `"initialized": true` (from `check-init`) or a JSON profile (from `me`). On `[401:invalid_token]`, the PAT is wrong / expired / from a different host than `base_url`.

### Upgrade

Because the skill is installed as a symlink / junction, upgrading is a `git pull` inside your workspace clone — the `~/.claude/skills/claudecode-team-pivot` path auto-reflects the new files. No re-install needed.

```bash
cd ~/repository/claudecode-team-pivot          # or D:\repository\... on Windows
git pull
python -m pip install --upgrade pyyaml          # only if new minor deps land
python runner.py check-init                     # sanity check
```

Upgrade is **purely additive** — new files, new optional runtime dirs (`~/.pivot/sessions/`, `~/.pivot/drafts/`), no migration needed. Config schema is stable. Your PAT, mirror clone, and all user data survive untouched.

Rollback is `git checkout <previous-tag>` in the same clone.

### For AI agents installing this skill

If you are Claude Code or another AI agent acting on the user's behalf, read this:

**Always ask the user for** — do not guess:
1. **Install path** — default suggestion is `~/repository/claudecode-team-pivot` (macOS/Linux) or `D:\repository\claudecode-team-pivot` (Windows). Some users prefer `~/Codes/` or other conventions.
2. **Pivot server `base_url`** — internal per-team. Users typically know their Pivot web URL; ask "what URL do you log into Pivot Web with?" Don't default to anything.
3. **PAT token** — the user generates this themselves at `<base-url>/settings/api-tokens` (plaintext shown once). Prompt the user; don't auto-generate.

**The guided setup exists for exactly this**:
```bash
python runner.py setup
```
It walks through base_url + token interactively and verifies in one command. Prefer it over manual file editing when running on behalf of a human.

**Expected failure modes to recognize**:
- `YOUR_DOMAIN placeholder` → base_url still the template; ask user for their real URL
- `[401:invalid_token]` → token wrong/expired, or signed by a different host than `base_url`
- `[0:network_error]` → base_url unreachable (VPN? typo?)
- `requires PyYAML` → run `python -m pip install pyyaml`

### Uninstall

```bash
# macOS / Linux / Windows (Git Bash)
rm ~/.claude/skills/claudecode-team-pivot

# Windows (cmd, if you used mklink /J)
rmdir "%USERPROFILE%\.claude\skills\claudecode-team-pivot"
```

The clone under `~/repository/` is untouched; delete it manually if you want.

## Usage

In Claude Code, just talk naturally:

- "pivot 上有啥新讨论"
- "帮我看下 proposals/database-migration 那个讨论"
- "给这个 thread 回一句：同意方案 A，先在测试环境跑一周"
- "pivot 上谁提过 ClickHouse"
- "这周讨论的重点是什么"

The skill orchestrates the right sequence of REST API calls and (optionally) local git mirror operations. Draft replies are always shown for confirmation before publishing.

## Commands

### Pipelines (`runner.py`)

Multi-step flows; use when a workflow has LLM reasoning or needs a confirmation gate.

| Command | Purpose | Has LLM step |
|---|---|---|
| `runner.py setup [--base-url U --token T]` | Guided first-run config | no |
| `runner.py check-init` | Preflight check (config + token) | no |
| `runner.py list` | List available pipelines | no |
| `runner.py read --thread <cat>/<slug>` | Fetch + summarize thread + propose next actions | yes (summarize) |
| `runner.py reply --thread <cat>/<slug> --draft-file F [...]` | Publish reply with mandatory confirm gate | yes (confirm) |
| `runner.py draft --thread <cat>/<slug> --content-file F` | Persist a draft to `~/.pivot/drafts/` with YAML frontmatter | no |
| `runner.py digest --since 7d` | Sync + per-thread commit digest | yes (group) |
| `runner.py resume <session> --llm-output '<json>'` | Continue a paused pipeline after LLM work | — |

Paused pipelines return `{"status": "paused", "llm_request": {...}}`. The invoking agent produces the LLM output and calls `resume`.

### Atomic commands (`bin/pivot.py`)

Single API / subprocess call each. No pipeline scaffolding; no PyYAML required.

| Command | Purpose |
|---|---|
| `pivot.py me` | Verify token + print server/workspace info |
| `pivot.py threads [--unread-first] [--category X] [--limit N]` | List threads |
| `pivot.py show <cat>/<slug>` | Thread detail (posts, mentions) |
| `pivot.py reply <cat>/<slug> --file F [--mention ids --mention-comment C]` | Post reply (no confirm gate — prefer `runner.py reply` for new code) |
| `pivot.py new <cat> --title T --file F` | New thread |
| `pivot.py mention <cat>/<slug> --target-filename FN --mention ids --mention-comment C` | Standalone @-mention |
| `pivot.py status <cat>/<slug> --to STATE [--reason R]` | Change status |
| `pivot.py favorite <cat>/<slug> [--unfavorite]` | Toggle favorite |
| `pivot.py read <cat>/<slug>` | Mark as read |
| `pivot.py contacts [--search Q]` | Look up open_id by name |
| `pivot.py sync [--check]` | Clone / pull the local git mirror |
| `pivot.py search <pattern>` | Full-text search in the mirror |
| `pivot.py history [--since 7d]` | Git log summary from the mirror |

See `pivot.py --help` and `runner.py --help` for the full surface.

## Architecture

```
~/.pivot/config.json             # PAT + base_url + mirror_dir
~/.pivot/sessions/               # paused pipelines (24h TTL)
~/.pivot/drafts/                 # persistent reply / proposal drafts
~/pivot-mirror/                  # local git mirror (shared with vscode-team-pivot)
        │
        ▼
runner.py                        # Pipeline Runner (APP v0.4 entrypoint)
   ├── pipelines/_constructor/   # preflight: config + token + base_url sanity
   ├── pipelines/_destructor/    # housekeeping: prune expired sessions
   ├── pipelines/read/           # thread fetch + LLM summarize + action suggest
   ├── pipelines/reply/          # fetch + LLM confirm (paused) + publish
   ├── pipelines/draft/          # persistent draft with frontmatter validation
   └── pipelines/digest/         # sync + git log + LLM per-thread grouping
        │
        ▼ (steps import)
bin/pivot.py                     # atomic CLI dispatcher (still works standalone)
   ├── api.py                    # REST wrapper (urllib, zero deps)
   ├── mirror.py                 # git clone/pull
   └── search.py                 # ripgrep / git grep
        │
        ▼
team-pivot-web REST API          ← all writes
        + git mirror (readonly)  ← reads optionally here for speed
```

- **Writes always go through REST** — the server does atomic commits
- **Reads prefer REST** for freshness; the git mirror is an optional accelerator for full-text search and rich AI context
- Mirror defaults to `~/pivot-mirror/` — **intentionally the same as vscode-team-pivot** so both tools share one clone
- Pipelines with `llm` steps hand control back to the invoking agent via the paused/resume protocol — the runner itself does not embed an LLM API key

## Config

Precedence: env var > `~/.pivot/config.json` > built-in default.

| Key | Env var | Default |
|---|---|---|
| `base_url` | `PIVOT_BASE_URL` | `https://pivot.enclaws.ai` |
| `token` | `PIVOT_TOKEN` | *(required)* |
| `mirror_dir` | `PIVOT_MIRROR_DIR` | `~/pivot-mirror` |

> The built-in `base_url` default is a placeholder. Internal users typically point at their production host (e.g. `https://pivot.enclaws.com`). Change `base_url` in `~/.pivot/config.json` if the default doesn't match your deployment. If `pivot.py me` returns `[0:network_error]` right after install, this is the most likely cause.

## Related

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) — server + web UI, REST contract owner
- [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot) — VS Code extension
- [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot) — IntelliJ plugin

## License

MIT
