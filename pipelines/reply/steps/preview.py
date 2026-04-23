#!/usr/bin/env python3
"""Load the draft file + fetch latest thread context. Output is consumed by
the confirm LLM step to render an accurate plan for the user.

Keeps output small: only the last post's body, not every post, to avoid
blowing up the prompt context.
只抽最后一条 post 的 body，避免 prompt 过长。

IMPORTANT: the draft file may have YAML frontmatter (for local draft mgmt).
The frontmatter is local-only metadata and MUST be stripped before POSTing
to Pivot. We emit `draft_body` (stripped) for publishing and `draft_full`
(raw) if downstream needs it.
draft 文件可能带 YAML frontmatter（本地草稿元数据），不能 POST 到服务端。
这里剥掉得到 draft_body；保留原文 draft_full 供追溯。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Allow importing the api module from the bin/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bin"))
from api import PivotAPI, PivotAPIError  # noqa: E402

import os


def _load_config() -> dict:
    cfg_path = Path.home() / ".pivot" / "config.json"
    cfg = {}
    if cfg_path.is_file():
        with cfg_path.open(encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
    cfg.setdefault("base_url", "https://pivot.enclaws.ai")
    if os.environ.get("PIVOT_BASE_URL"):
        cfg["base_url"] = os.environ["PIVOT_BASE_URL"]
    if os.environ.get("PIVOT_TOKEN"):
        cfg["token"] = os.environ["PIVOT_TOKEN"]
    return cfg


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})

    thread = input_.get("thread") or ""
    draft_file = input_.get("draft_file") or ""
    if "/" not in thread:
        print("reply.preview: --thread must be <category>/<slug>", file=sys.stderr)
        return 1
    if not draft_file:
        print("reply.preview: --draft-file required", file=sys.stderr)
        return 1

    draft_path = Path(draft_file).expanduser()
    if not draft_path.is_file():
        print(f"reply.preview: draft file not found: {draft_path}", file=sys.stderr)
        return 1
    draft_full = draft_path.read_text(encoding="utf-8-sig")

    # Strip optional YAML frontmatter — it's local metadata, never POSTed.
    # 剥离 YAML frontmatter，只留正文准备 POST。
    m = re.match(r"^---\s*\n.*?\n---\s*\n", draft_full, flags=re.DOTALL)
    draft_body = draft_full[m.end():] if m else draft_full
    draft_body = draft_body.lstrip("\n")

    cfg = _load_config()
    api = PivotAPI(cfg["base_url"], cfg.get("token", ""))
    category, slug = thread.split("/", 1)
    try:
        detail = api.get_thread(category, slug)
    except PivotAPIError as e:
        print(f"reply.preview: cannot fetch thread {thread}: {e}", file=sys.stderr)
        return 1

    posts = detail.get("posts", [])
    last = posts[-1] if posts else {}
    out = {
        "output": {
            "thread_title": detail.get("meta", {}).get("title", ""),
            "post_count": len(posts),
            "last_author": last.get("author_display", ""),
            "last_post_body": last.get("body", "")[:4000],  # cap for prompt size
            # draft_body is the publishable content (frontmatter stripped);
            # draft_full is the raw file content, kept for traceability only.
            # draft_body 供发布；draft_full 保留原文便于回溯。
            "draft_body": draft_body,
            "draft_full": draft_full,
            "draft_path": str(draft_path),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
