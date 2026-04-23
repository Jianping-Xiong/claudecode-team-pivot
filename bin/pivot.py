#!/usr/bin/env python3
"""pivot.py — atomic CLI entrypoint for the claudecode-team-pivot skill.

Intentionally thin. This script does deterministic work only (HTTP calls, git
subprocess, argparse). Intent understanding and orchestration live in SKILL.md
— the agent composes these atomic commands.

本脚本只做确定性操作（HTTP / git / argparse）。意图理解和编排交给
SKILL.md，由 agent 组合这些原子命令。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# bin/ is the canonical location; add it to sys.path for direct execution.
# 支持直接执行 pivot.py 时正确 import 同级模块。
_BIN_DIR = Path(__file__).resolve().parent
if str(_BIN_DIR) not in sys.path:
    sys.path.insert(0, str(_BIN_DIR))

from api import PivotAPI, PivotAPIError  # noqa: E402
from mirror import Mirror, MirrorError   # noqa: E402
import search as search_mod               # noqa: E402


# ------------------------------- config ----------------------------------

def load_config() -> dict:
    """Resolve config with precedence: env var > ~/.pivot/config.json > default."""
    cfg_path = Path.home() / ".pivot" / "config.json"
    cfg: dict = {}
    if cfg_path.exists():
        try:
            # utf-8-sig tolerates an optional BOM; PowerShell 5.1's Set-Content
            # -Encoding UTF8 writes one by default on Windows.
            # utf-8-sig 容忍可选 BOM；PS 5.1 的 Set-Content -Encoding UTF8 默认加 BOM。
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            _die(f"{cfg_path} is not valid JSON: {e}")

    cfg.setdefault("base_url", "https://pivot.enclaws.ai")
    cfg.setdefault("token", "")
    cfg.setdefault("mirror_dir", "")

    if os.environ.get("PIVOT_BASE_URL"):
        cfg["base_url"] = os.environ["PIVOT_BASE_URL"]
    if os.environ.get("PIVOT_TOKEN"):
        cfg["token"] = os.environ["PIVOT_TOKEN"]
    if os.environ.get("PIVOT_MIRROR_DIR"):
        cfg["mirror_dir"] = os.environ["PIVOT_MIRROR_DIR"]
    return cfg


def require_token(cfg: dict) -> None:
    if not cfg.get("token"):
        _die(
            "no PAT token configured.\n"
            "  1. Generate a token on Pivot Web settings page\n"
            "  2. Save to ~/.pivot/config.json (see config.example.json)\n"
            "     or export PIVOT_TOKEN=pvt_xxx"
        )


# ------------------------------- utils -----------------------------------

def split_thread_key(key: str) -> tuple:
    if "/" not in key:
        _die(f"thread key must be <category>/<slug>, got: {key}")
    cat, slug = key.split("/", 1)
    return cat, slug


def _build_mentions(mention: Optional[str], comment: Optional[str]) -> Optional[dict]:
    if not mention:
        return None
    open_ids = [x.strip() for x in mention.split(",") if x.strip()]
    if not open_ids:
        return None
    return {
        "open_ids": open_ids,
        # Server requires comments to be non-empty. Default tag if skill forgot.
        # 服务端要求 comments 非空；skill 忘传时用占位，但应尽量传真实评论。
        "comments": (comment or "mention").strip() or "mention",
    }


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(2)


# -------------------------- command handlers ------------------------------

def cmd_me(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.me())


def cmd_threads(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    data = api.list_threads(category=args.category)
    items = data.get("items", [])
    if args.favorite_only:
        items = [t for t in items if t.get("favorite")]
    if args.unread_first:
        # Secondary sort by last_updated desc; server already returned
        # last_updated-desc order, so stable sort preserves it within ties.
        items.sort(key=lambda t: -(t.get("unread_count") or 0))
    # else: trust server order (last_updated desc)
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    _print({"items": items})


def cmd_show(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    _print(api.get_thread(cat, slug))


def cmd_reply(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    # utf-8-sig tolerates the BOM that PowerShell 5.1's Set-Content adds.
    # utf-8-sig 容忍 PS 5.1 写文件时加的 BOM。
    body = Path(args.file).read_text(encoding="utf-8-sig")
    mentions = _build_mentions(args.mention, args.mention_comment)
    _print(
        api.reply(
            cat, slug,
            body=body,
            mentions=mentions,
            reply_to=args.reply_to,
            references=args.references or [],
        )
    )


def cmd_new(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    # utf-8-sig tolerates the BOM that PowerShell 5.1's Set-Content adds.
    # utf-8-sig 容忍 PS 5.1 写文件时加的 BOM。
    body = Path(args.file).read_text(encoding="utf-8-sig")
    mentions = _build_mentions(args.mention, args.mention_comment)
    _print(
        api.new_thread(
            category=args.category, title=args.title, body=body, mentions=mentions,
        )
    )


def cmd_mention(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    open_ids = [x.strip() for x in (args.mention or "").split(",") if x.strip()]
    if not open_ids:
        _die("--mention requires at least one open_id")
    if not args.mention_comment:
        _die("--mention-comment required")
    _print(
        api.add_mention(
            cat, slug,
            target_filename=args.target_filename,
            open_ids=open_ids,
            comments=args.mention_comment,
        )
    )


def cmd_status(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    _print(api.change_status(cat, slug, to=args.to, reason=args.reason))


def cmd_favorite(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    _print(api.set_favorite(cat, slug, favorite=not args.unfavorite))


def cmd_read(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    cat, slug = split_thread_key(args.thread)
    _print(api.mark_read(cat, slug))


def cmd_contacts(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.list_contacts(q=args.search, limit=args.limit))


def cmd_sync(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    mirror = Mirror(api, mirror_dir=cfg["mirror_dir"] or None)
    if args.check:
        _print(mirror.status())
        return
    path = mirror.sync()
    _print({"ok": True, "repo_path": str(path)})


def cmd_search(args, cfg: dict) -> None:
    # search / history are local-only (read the mirror dir), no API calls.
    # Mirror still needs an instance to resolve repo_path_if_ready.
    mirror = Mirror(None, mirror_dir=cfg["mirror_dir"] or None)
    repo = mirror.repo_path_if_ready()
    if not repo:
        _die("mirror not synced yet. Run: pivot.py sync")
    results = search_mod.search(repo, args.pattern, max_results=args.limit)
    _print({"results": results, "count": len(results)})


def cmd_history(args, cfg: dict) -> None:
    mirror = Mirror(None, mirror_dir=cfg["mirror_dir"] or None)
    repo = mirror.repo_path_if_ready()
    if not repo:
        _die("mirror not synced yet. Run: pivot.py sync")
    _print({"commits": search_mod.history(repo, since=args.since, limit=args.limit)})


# --------------------------- argparse setup ------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pivot.py",
        description="Team Pivot CLI (claudecode-team-pivot skill).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # me
    sub.add_parser("me", help="Print current user (verify token).")

    # threads
    sp = sub.add_parser("threads", help="List threads.")
    sp.add_argument("--category", help="Filter by category.")
    sp.add_argument("--unread-first", action="store_true", help="Sort unread first.")
    sp.add_argument("--favorite-only", action="store_true", help="Show favorites only.")
    sp.add_argument("--limit", type=int, default=0, help="Max items (0 = all).")

    # show
    sp = sub.add_parser("show", help="Show thread detail.")
    sp.add_argument("thread", help="<category>/<slug>")

    # reply
    sp = sub.add_parser("reply", help="Reply to an existing thread.")
    sp.add_argument("thread", help="<category>/<slug>")
    sp.add_argument("--file", required=True, help="Markdown body file.")
    sp.add_argument("--mention", help="Comma-separated open_ids.")
    sp.add_argument("--mention-comment", help="Comment shown in mention notification.")
    sp.add_argument("--reply-to", help="Filename of the post being replied to.")
    sp.add_argument("--references", nargs="*", help="Referenced post filenames.")

    # new
    sp = sub.add_parser("new", help="Start a new thread.")
    sp.add_argument("category")
    sp.add_argument("--title", required=True)
    sp.add_argument("--file", required=True, help="Markdown body file.")
    sp.add_argument("--mention")
    sp.add_argument("--mention-comment")

    # mention
    sp = sub.add_parser("mention", help="Add a standalone mention to an existing post.")
    sp.add_argument("thread")
    sp.add_argument("--target-filename", required=True)
    sp.add_argument("--mention", required=True)
    sp.add_argument("--mention-comment", required=True)

    # status
    sp = sub.add_parser("status", help="Change thread status.")
    sp.add_argument("thread")
    sp.add_argument(
        "--to", required=True,
        choices=["open", "pending", "resolved", "closed"],
        help="Target status; server rejects invalid transitions.",
    )
    sp.add_argument("--reason")

    # favorite
    sp = sub.add_parser("favorite", help="Toggle favorite.")
    sp.add_argument("thread")
    sp.add_argument("--unfavorite", action="store_true")

    # read
    sp = sub.add_parser("read", help="Mark thread as read.")
    sp.add_argument("thread")

    # contacts
    sp = sub.add_parser("contacts", help="List or search contacts.")
    sp.add_argument("--search", help="Name/keyword filter.")
    sp.add_argument("--limit", type=int, default=20)

    # sync
    sp = sub.add_parser("sync", help="Clone or pull the local git mirror.")
    sp.add_argument("--check", action="store_true", help="Only report status, don't sync.")

    # search
    sp = sub.add_parser("search", help="Full-text search in the local mirror.")
    sp.add_argument("pattern")
    sp.add_argument("--limit", type=int, default=50)

    # history
    sp = sub.add_parser("history", help="Git log summary from the local mirror.")
    sp.add_argument("--since", default="7d", help="e.g. 7d, 24h, 2w, or any git approxidate.")
    sp.add_argument("--limit", type=int, default=200, help="Max commits to return.")

    return p


HANDLERS = {
    "me": cmd_me,
    "threads": cmd_threads,
    "show": cmd_show,
    "reply": cmd_reply,
    "new": cmd_new,
    "mention": cmd_mention,
    "status": cmd_status,
    "favorite": cmd_favorite,
    "read": cmd_read,
    "contacts": cmd_contacts,
    "sync": cmd_sync,
    "search": cmd_search,
    "history": cmd_history,
}


def main() -> int:
    args = build_parser().parse_args()
    cfg = load_config()
    handler = HANDLERS[args.cmd]
    try:
        handler(args, cfg)
        return 0
    except PivotAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1
    except MirrorError as e:
        print(f"Mirror error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
