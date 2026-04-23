---
name: claudecode-team-pivot
description: Interact with the Team Pivot discussion platform from Claude Code — browse threads, summarize, draft replies with mandatory confirmation gate, @-mention teammates, search history, weekly digests. APP v0.4 with runner.py + pipelines; atomic ops still exposed via bin/pivot.py.
---

# claudecode-team-pivot — delegation layer

Most work goes through the Pipeline Runner at `runner.py`. Atomic CRUD
(favorite / read-mark / status / contacts / sync / threads-list) stays on
`bin/pivot.py` — those are single API calls that don't need framework scaffolding.

## Trigger conditions

Use this skill when the user says things like:
- "pivot 上有啥新的 / 看看讨论 / 谁 @ 我了" (read)
- "帮我看下 <thread>" / "那个讨论讲了什么" (read)
- "回复 <thread>" / "给它回一句" (reply)
- "@ liuyu 问下" (mention)
- "把这段整理成草稿" / "save this as a draft" (draft)
- "这周讨论重点" / "近期 pivot 动态" (digest)
- "pivot 上谁提过 X" (search)

Do **not** use for:
- Raw HTTP debugging (use curl)
- Managing PAT tokens (redirect to Pivot Web settings page)

## Runner protocol (read this before calling runner.py)

Every runner invocation returns JSON with `status`:

**`"completed"`** — done. Show `output` to user in natural language.

**`"paused"`** — pipeline hit an `llm` step and needs the agent (you) to do
LLM work. Fields:
- `session` — opaque id to pass back on resume
- `llm_request.prompt` — rendered prompt, follow it
- `llm_request.schema` — your output must match this JSON Schema

Flow:
1. Read `llm_request.prompt`, do the LLM task yourself
2. Format output as JSON matching the schema
3. Resume: `python runner.py resume <session> --llm-output '<json>'`
4. Handle the next response (may be `completed`, `paused` again, or `error`)

**`"error"`** — inspect `error` field; often the constructor rejecting bad
config (token missing, base_url placeholder, etc.). Surface error verbatim.

## Commands

### First-run check

Before first use on a fresh machine:

```bash
python runner.py check-init   # are config + token present?
```

If not initialized, either walk the user through manual steps OR run the
guided flow (asks for base_url + token interactively):

```bash
python runner.py setup
# or non-interactive:
python runner.py setup --base-url https://pivot.<your-team>.com --token pvt_xxx
```

### Pipeline commands (via runner)

```bash
python runner.py read --thread <cat>/<slug>
# paused → you produce {brief, key_points, actions[]} → resume
# Show the brief + key_points to the user. If actions include reply/mention, ask next.

python runner.py reply --thread <cat>/<slug> --draft-file <path> \
    [--mention <ou_xxx,...>] [--mention-comment <text>] [--reply-to <filename>]
# paused → you show the plan to the user and ask to publish
# - approved yes → resume with {"approved": true}
# - approved no  → resume with {"approved": false, "notes": "what to change"}

python runner.py draft --thread <cat>/<slug> --content-file <path>
# content-file MUST start with YAML frontmatter including `summary:`
# summary format: "**摘要**：3-5 sentences. **亮点**：1-2 highlights"
# pure code pipeline — no pause. Drafts land in ~/.pivot/drafts/<slug>--<ts>.md

python runner.py digest --since 7d
# paused → you produce {window, groups[], overall} → resume
# Present overall first, then per-thread summaries grouped.
```

### Atomic commands (via bin/pivot.py, no runner)

These are single API calls. No pipeline value-add.

```bash
python bin/pivot.py threads [--unread-first] [--category X] [--limit N]
python bin/pivot.py show <cat>/<slug>
python bin/pivot.py contacts --search <name>   # resolve open_id
python bin/pivot.py mention <cat>/<slug> --target-filename <F> \
    --mention <ou_xxx,...> --mention-comment "短评"
python bin/pivot.py status <cat>/<slug> --to <open|pending|resolved|closed> \
    [--reason "..."]
python bin/pivot.py favorite <cat>/<slug> [--unfavorite]
python bin/pivot.py read <cat>/<slug>
python bin/pivot.py sync [--check]
python bin/pivot.py search <pattern>
python bin/pivot.py history --since 7d
python bin/pivot.py me   # connectivity + token check
```

## Workflow cookbook

### Ambiguous ask ("pivot 上有啥新的")

```
python bin/pivot.py threads --unread-first --limit 10
```

Show top unread + favorites, grouped by category if >1. Ask which to open.

### User wants to read a specific thread

```
python runner.py read --thread <cat>/<slug>
```

After completion, show the brief + key_points. Offer the suggested `actions`
as follow-ups.

### User wants to reply

1. Collect draft content. Either:
   - User dictates the reply verbatim → write it straight to a temp file
   - User asks you to draft → compose, then write to a temp file
   - Tone: internal thread → writing-for-team.md; outward thread → writing-for-client.md
   - Language: match thread's dominant language
2. Write the draft to `~/.pivot/drafts/<slug>--<ts>.md` via `runner.py draft`
   (if the user wants persistence) **OR** straight to `tempfile.gettempdir()`
   (if ephemeral)
3. `python runner.py reply --thread <cat>/<slug> --draft-file <path> \
   [--mention <ou_xxx>] [--mention-comment <text>]`
4. Pipeline pauses at `confirm`. Show the plan (target, mentions, draft body)
   to the user **verbatim**. Do not paraphrase. Ask yes/no explicitly.
5. Resume with the user's decision as JSON.

### User wants to @ someone (no new reply)

```
# step 1: resolve open_id
python bin/pivot.py contacts --search <name>

# step 2: after user confirms open_id and comment
python bin/pivot.py mention <cat>/<slug> --target-filename <post.md> \
    --mention <ou_xxx> --mention-comment "<短评>"
```

Confirm before calling — mention sends a Feishu notification.

### User wants to save current conversation as a draft

This mirrors 2discuss `/file`. The agent does the organizing in Skill mode;
`runner.py draft` handles persistence + frontmatter validation.

1. Identify the target thread (`<cat>/<slug>`) from context, or ask the user
   ("save as reply to which thread? or as a new-thread proposal?")
2. Organize the relevant chat content into a well-structured Markdown body
3. **Prepend YAML frontmatter with a `summary:` field** (this is enforced — the
   pipeline rejects content without it):
   ```markdown
   ---
   summary: "**摘要**：<3-5 sentences covering background + core point + key arguments>. **亮点**：<1-2 most valuable points>."
   thread: "<cat>/<slug>"   # optional; omit for new-thread proposals
   ---

   <actual body here>
   ```
4. Write to a temp file (e.g. `tempfile.gettempdir() + "/pivot-organize-<ts>.md"`)
5. `python runner.py draft --thread <cat>/<slug> --content-file <tempfile>`
6. On completion, tell the user the returned `path` (where the draft landed in
   `~/.pivot/drafts/`) — they can edit it further or pass it to `reply` later

### User wants a weekly digest

```
python runner.py digest --since 7d
```

The digest pipeline auto-syncs the mirror if it's missing or stale (>1h) —
no manual `sync` required. On network failure during pull, it warns to
stderr and continues with the cached mirror.

### Search

```
python bin/pivot.py sync        # refresh if stale (>1h since last sync)
python bin/pivot.py search "<pattern>"
```

`search` returns matching file paths + line snippets. For promising hits,
load full context via `show <cat>/<slug>`.

### User wants to change thread status

State transitions are rule-governed (server enforces valid transitions; some
require a `--reason`). Always confirm with the user before calling.

1. Show the current status (from a prior `show` or `threads`)
2. Propose: "change `<cat>/<slug>` from `open` → `pending`, reason `<...>`?"
3. On explicit yes:
   ```
   python bin/pivot.py status <cat>/<slug> --to <open|pending|resolved|closed> [--reason "..."]
   ```
4. If server returns `reopen requires a reason of at least N characters`,
   ask the user for a reason and retry.

### User wants to @ someone on an existing post

Mentions trigger a Feishu notification — confirm the target person + comment
before calling.

1. Resolve open_id if unknown: `python bin/pivot.py contacts --search <name>`
2. Show the plan to user: "@ `<person>` (open_id `ou_...`) on post `<filename>`
   with comment `<text>`?"
3. On explicit yes:
   ```
   python bin/pivot.py mention <cat>/<slug> --target-filename <post.md> \
       --mention <ou_xxx,...> --mention-comment "<text>"
   ```

### Favorite / unfavorite / mark read

Low-stakes, reversible. No confirmation needed.

```
python bin/pivot.py favorite <cat>/<slug>           # add
python bin/pivot.py favorite <cat>/<slug> --unfavorite
python bin/pivot.py read <cat>/<slug>                # mark as read
```

## Confirmation rules (strict)

| Action | Confirm first? |
|---|---|
| `runner.py reply` | **Yes** — pipeline enforces confirm step; don't resume without user's explicit yes |
| `bin/pivot.py mention`, `status`, `new` | **Yes** — show payload, get user approval |
| `favorite`, `read`, `sync` | No — reversible / local |
| `me`, `threads`, `show`, `contacts`, `search`, `history`, `runner.py read` | No — read-only from user POV |

## Error triage

- `[401:invalid_token]` → PAT bad/expired. `runner.py setup --token pvt_xxx` or edit `~/.pivot/config.json`.
- `[0:network_error]` → base_url unreachable. Check VPN. Verify base_url matches PAT's source host.
- `base_url is not configured (still YOUR_DOMAIN placeholder)` → `runner.py setup` to walk through it.
- `runner.py requires PyYAML` → `python -m pip install pyyaml`.
- `Mirror error: git not found` → install git.

## Related

- [team-pivot-web](https://github.com/hashSTACS-Global/team-pivot-web) — server + REST contract
- [vscode-team-pivot](https://github.com/hashSTACS-Global/vscode-team-pivot) — VS Code extension (shares `~/pivot-mirror/`)
- [intellij-team-pivot](https://github.com/hashSTACS-Global/intellij-team-pivot) — IntelliJ plugin
- [agent-pipeline-protocol](https://github.com/hashSTACS-Global/agent-pipeline-protocol) v0.4 — APP spec this skill implements
