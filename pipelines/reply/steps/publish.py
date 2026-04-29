#!/usr/bin/env python3
"""Publish the reply via Matter API append_file.

v0.5: migrated from deprecated api.reply() to api.append_file().
Reads steps.confirm.output.approved from stdin. If false, returns a
skipped-status output — no POST happens.
用户没点同意就不 POST，返回 skipped 状态。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bin"))
from api import PivotAPI, PivotAPIError  # noqa: E402


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


def _resolve_matter_id(thread: str) -> str:
    if "/" in thread:
        return thread.split("/", 1)[1]
    return thread


def _parse_comments(mention: str, comment: str) -> list[dict] | None:
    if not mention:
        return None
    open_ids = [x.strip() for x in mention.split(",") if x.strip()]
    if not open_ids:
        return None
    return [{"body": (comment or "mention").strip() or "mention", "mentions": open_ids}]


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})
    steps = payload.get("steps", {})

    confirm_out = (steps.get("confirm") or {}).get("output") or {}
    if not confirm_out.get("approved"):
        out = {
            "output": {
                "status": "skipped",
                "reason": "user_declined",
                "notes": confirm_out.get("notes", ""),
            }
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    preview = (steps.get("preview") or {}).get("output") or {}
    draft_content = preview.get("draft_body") or preview.get("draft_full") or ""
    if not draft_content.strip():
        print("reply.publish: empty draft — refusing to post", file=sys.stderr)
        return 1

    thread = input_.get("thread") or ""
    matter_id = _resolve_matter_id(thread)
    comments = _parse_comments(
        input_.get("mention") or "",
        input_.get("mention_comment") or "",
    )

    cfg = _load_config()
    api = PivotAPI(cfg["base_url"], cfg.get("token", ""))

    try:
        result = api.append_file(
            matter_id,
            type="think",
            summary="",
            body=draft_content,
            comments=comments,
        )
    except PivotAPIError as e:
        print(f"reply.publish: API error: {e}", file=sys.stderr)
        return 1

    out = {
        "output": {
            "status": "published",
            "result": result,
            "matter_id": matter_id,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
