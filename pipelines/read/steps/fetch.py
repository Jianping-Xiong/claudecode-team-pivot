#!/usr/bin/env python3
"""Fetch thread detail and flatten posts into a prompt-ready text block.

Cap per-post body at 3000 chars so the combined prompt stays under typical
context budgets. Truncation is marked explicitly.
每条 post body 截到 3000 字，避免总 prompt 太大；截断时显式标注。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bin"))
from api import PivotAPI, PivotAPIError  # noqa: E402


POST_BODY_CAP = 3000


def _load_config() -> dict:
    cfg_path = Path.home() / ".pivot" / "config.json"
    cfg: dict = {}
    if cfg_path.is_file():
        with cfg_path.open(encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
    if os.environ.get("PIVOT_BASE_URL"):
        cfg["base_url"] = os.environ["PIVOT_BASE_URL"]
    if os.environ.get("PIVOT_TOKEN"):
        cfg["token"] = os.environ["PIVOT_TOKEN"]
    return cfg


def _truncate(body: str, cap: int) -> str:
    if len(body) <= cap:
        return body
    return body[:cap] + f"\n\n...[truncated, original {len(body)} chars]..."


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})

    thread = input_.get("thread") or ""
    if "/" not in thread:
        print("read.fetch: --thread must be <category>/<slug>", file=sys.stderr)
        return 1

    cat, slug = thread.split("/", 1)
    cfg = _load_config()
    api = PivotAPI(cfg["base_url"], cfg.get("token", ""))

    try:
        detail = api.get_thread(cat, slug)
    except PivotAPIError as e:
        print(f"read.fetch: cannot fetch thread {thread}: {e}", file=sys.stderr)
        return 1

    meta = detail.get("meta", {})
    posts = detail.get("posts", [])

    # Stitch posts into a single text block in oldest-first order.
    # 把每条 post 拼成有序文本块，供 LLM step 阅读。
    parts: list[str] = []
    for p in posts:
        fm = p.get("frontmatter") or {}
        author = p.get("author_display") or fm.get("author") or "?"
        ptype = fm.get("type") or "post"
        created = fm.get("created") or ""
        body = _truncate(p.get("body") or "", POST_BODY_CAP)
        mentions = p.get("mentions") or []
        mention_note = ""
        if mentions:
            mention_note = " (has @mentions)"
        parts.append(
            f"### [{ptype}] {author} · {created}{mention_note}\n{body}"
        )
    posts_text = "\n\n".join(parts) if parts else "(no posts)"

    out = {
        "output": {
            "thread": thread,
            "title": meta.get("title", ""),
            "author": meta.get("author_display", ""),
            "status": meta.get("status", ""),
            "post_count": len(posts),
            "last_updated": meta.get("last_updated", ""),
            "favorite": meta.get("favorite", False),
            "posts_text": posts_text,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
