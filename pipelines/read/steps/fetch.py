#!/usr/bin/env python3
"""Fetch matter detail and flatten posts into a prompt-ready text block.

v0.5: migrated from deprecated get_thread to Matter API get_matter.
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


def _resolve_matter_id(thread: str) -> str:
    """Accept both 'matter_id' and 'category/matter_id' formats."""
    if "/" in thread:
        return thread.split("/", 1)[1]
    return thread


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})

    thread = input_.get("thread") or ""
    if not thread:
        print("read.fetch: --thread <matter_id> required", file=sys.stderr)
        return 1

    matter_id = _resolve_matter_id(thread)
    cfg = _load_config()
    api = PivotAPI(cfg["base_url"], cfg.get("token", ""))

    try:
        detail = api.get_matter(matter_id)
    except PivotAPIError as e:
        print(f"read.fetch: cannot fetch matter {matter_id}: {e}", file=sys.stderr)
        return 1

    matter = detail.get("matter", {})
    timeline = detail.get("timeline", [])

    parts: list[str] = []
    for p in timeline:
        ptype = p.get("type") or "post"
        creator = p.get("creator_display") or p.get("creator") or "?"
        created_at = p.get("created_at") or ""
        body = _truncate(p.get("body") or "", POST_BODY_CAP)
        has_mentions = " (has @mentions)" if (p.get("comments") or []) else ""
        parts.append(
            f"### [{ptype}] {creator} · {created_at}{has_mentions}\n{body}"
        )
    posts_text = "\n\n".join(parts) if parts else "(no posts)"

    out = {
        "output": {
            "thread": thread,
            "matter_id": matter_id,
            "title": matter.get("title", ""),
            "status": matter.get("current_status", ""),
            "post_count": len(timeline),
            "last_updated": matter.get("updated_at", ""),
            "favorite": matter.get("favorite", False),
            "posts_text": posts_text,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
