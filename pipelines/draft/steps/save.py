#!/usr/bin/env python3
"""Save a draft to ~/.pivot/drafts/ after validating its YAML frontmatter.

Contract (matches 2discuss /file):
- Content file starts with YAML frontmatter delimited by `---` lines
- Frontmatter MUST contain `summary` (摘要 3-5 句 + 亮点 1-2 句)

Output destination:
  ~/.pivot/drafts/<slug>--<ts>.md      (reply — thread given)
  ~/.pivot/drafts/_new--<ts>.md        (new-thread proposal — thread empty)

Returns {"path": "...", "bytes": N, "summary": "..."} so the agent can tell
the user where the draft landed.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

DRAFTS_DIR = Path.home() / ".pivot" / "drafts"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _slugify_for_filename(thread: str) -> str:
    """Turn '<cat>/<slug>' into a filesystem-safe token.

    Keeps CJK chars (Windows NTFS handles them fine); replaces `/`, `\\`, `:`
    with `--` so the path stays flat.
    保留中文；把斜杠冒号替换成 --，避免再生成子目录。
    """
    if not thread:
        return "_new"
    t = thread.strip().replace("\\", "/")
    t = re.sub(r'[\\/:*?"<>|]+', "--", t)
    return t[:120]  # cap length to avoid Windows MAX_PATH issues


def _extract_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Minimal YAML-ish parse — we only care
    about top-level string keys. If PyYAML is available, use it; otherwise
    fall back to a line-based parser sufficient for our use case.
    """
    m = FRONTMATTER_RE.match(content)
    if not m:
        return {}, content
    raw = m.group(1)
    body = content[m.end():]
    # Prefer PyYAML (already a dep via runner); fall back if unavailable.
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            data = {}
        return data, body
    except Exception:
        data: dict = {}
        for line in raw.splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip().strip('"').strip("'")
        return data, body


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})

    content_file = input_.get("content_file")
    if not content_file:
        print("draft.save: --content-file required", file=sys.stderr)
        return 1

    src = Path(content_file).expanduser()
    if not src.is_file():
        print(f"draft.save: content file not found: {src}", file=sys.stderr)
        return 1

    # utf-8-sig in case the agent wrote via PowerShell Set-Content.
    content = src.read_text(encoding="utf-8-sig")

    fm, body = _extract_frontmatter(content)
    if not fm:
        print(
            "draft.save: content file has no YAML frontmatter. Prepend "
            "---\\nsummary: \"**摘要**：... **亮点**：...\"\\n---",
            file=sys.stderr,
        )
        return 1
    summary = fm.get("summary", "").strip()
    if not summary:
        print(
            "draft.save: frontmatter is missing 'summary' field. Required "
            "format: 摘要 3-5 句 + 亮点 1-2 句 (see SKILL.md §draft).",
            file=sys.stderr,
        )
        return 1

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slugify_for_filename(input_.get("thread") or "")
    ts = int(time.time())
    dest = DRAFTS_DIR / f"{slug}--{ts}.md"
    # Always write without BOM so pivot.py reply (utf-8-sig) round-trips cleanly.
    dest.write_text(content, encoding="utf-8")

    out = {
        "output": {
            "path": str(dest),
            "bytes": dest.stat().st_size,
            "summary": summary,
            "thread": input_.get("thread") or "",
            "frontmatter_keys": sorted(fm.keys()),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
