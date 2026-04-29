#!/usr/bin/env python3
"""pivot.py — atomic CLI entrypoint for the claudecode-team-pivot skill.

Intentionally thin. This script does deterministic work only (HTTP calls, git
subprocess, argparse). Intent understanding and orchestration live in SKILL.md
— the agent composes these atomic commands.

本脚本只做确定性操作（HTTP / git / argparse）。意图理解和编排交给
SKILL.md，由 agent 组合这些原子命令。

v0.5: migrated from deprecated /api/threads/* to /api/matters/*.
v0.5: 从已废弃的 /api/threads/* 迁移到 /api/matters/*。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

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

def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(2)


def _parse_comments(raw: Optional[str]) -> Optional[list[dict]]:
    """Parse --mention and --mention-comment into comments array for Matter API.
    Format: [{"body": "<comment>", "mentions": ["ou_xxx", ...]}]
    """
    if not raw:
        return None
    open_ids = [x.strip() for x in raw.split(",") if x.strip()]
    if not open_ids:
        return None
    comment_body = "mention"
    return [{"body": comment_body, "mentions": open_ids}]


# -------------------------- command handlers ------------------------------

def cmd_me(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.me())


def cmd_matters(args, cfg: dict) -> None:
    """List matters. Replaces old `threads` command."""
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    data = api.list_matters(
        status=args.status or None,
        owner=args.owner or None,
        q=args.q or None,
    )
    items = data.get("items", [])
    if args.favorite_only:
        items = [t for t in items if t.get("favorite")]
    if args.unread_first:
        items.sort(key=lambda t: -(t.get("unread_count") or 0))
    if args.limit and args.limit > 0:
        items = items[: args.limit]
    _print({"items": items})


def cmd_show(args, cfg: dict) -> None:
    """Show matter detail. matter_id is the slug/ID (not category/slug)."""
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.get_matter(args.matter_id))


def cmd_reply(args, cfg: dict) -> None:
    """Append a file to an existing matter."""
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    body = Path(args.file).read_text(encoding="utf-8-sig")
    comments = _parse_comments(args.mention)
    _print(
        api.append_file(
            args.matter_id,
            type=args.type or "think",
            summary=args.summary or "",
            body=body,
            quote=args.quote or None,
            refer=args.references or None,
            comments=comments,
        )
    )


def cmd_new(args, cfg: dict) -> None:
    """Create a new matter."""
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    body = Path(args.file).read_text(encoding="utf-8-sig")
    comments = _parse_comments(args.mention)
    _print(
        api.create_matter(
            category=args.category,
            title=args.title,
            initial_type=args.type or "think",
            summary=args.summary or args.title,
            body=body,
            comments=comments,
        )
    )


def cmd_mention(args, cfg: dict) -> None:
    """Add a comment with @-mentions on a target file. Triggers Feishu notification."""
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    open_ids = [x.strip() for x in (args.mention or "").split(",") if x.strip()]
    if not open_ids:
        _die("--mention requires at least one open_id (ou_xxx)")
    _print(
        api.add_comment(
            args.matter_id,
            target_file=args.target_filename,
            body=args.mention_comment or "",
            mentions=open_ids,
        )
    )


def cmd_favorite(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.toggle_favorite(args.matter_id, favorite=not args.unfavorite))


def cmd_read(args, cfg: dict) -> None:
    require_token(cfg)
    api = PivotAPI(cfg["base_url"], cfg["token"])
    _print(api.mark_read(args.matter_id))


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
    """Full-text search in the local git mirror. Only covers mirrored files."""
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
        description="Team Pivot CLI (claudecode-team-pivot skill) — Matter API v0.5.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # me
    sub.add_parser("me", help="Print current user (verify token).")

    # matters (was "threads")
    sp = sub.add_parser("matters", help="List matters.")
    sp.add_argument("--status", help="Filter by status (planning/executing/paused/...).")
    sp.add_argument("--owner", help="Filter by owner (pinyin).")
    sp.add_argument("--q", help="Search in titles only.")
    sp.add_argument("--unread-first", action="store_true", help="Sort unread first.")
    sp.add_argument("--favorite-only", action="store_true", help="Show favorites only.")
    sp.add_argument("--limit", type=int, default=0, help="Max items (0 = all).")

    # show
    sp = sub.add_parser("show", help="Show matter detail with timeline.")
    sp.add_argument("matter_id", help="Matter ID (e.g. 'OPC-数字员工服务台-产品规划').")

    # reply
    sp = sub.add_parser("reply", help="Append a file to a matter.")
    sp.add_argument("matter_id")
    sp.add_argument("--file", required=True, help="Markdown body file.")
    sp.add_argument("--type", default="think", help="File type (think/act/verify/result/insight).")
    sp.add_argument("--summary", default="", help="One-line summary.")
    sp.add_argument("--mention", help="Comma-separated open_ids for @-mention.")
    sp.add_argument("--quote", help="Filename of the post being quoted.")
    sp.add_argument("--references", nargs="*", help="Referenced post filenames.")

    # new
    sp = sub.add_parser("new", help="Create a new matter.")
    sp.add_argument("category")
    sp.add_argument("--title", required=True)
    sp.add_argument("--file", required=True, help="Markdown body file.")
    sp.add_argument("--type", default="think", help="Initial file type (default: think).")
    sp.add_argument("--summary", default="", help="One-line summary (defaults to title).")
    sp.add_argument("--mention", help="Comma-separated open_ids for @-mention.")

    # mention
    sp = sub.add_parser("mention", help="Add a comment with @-mentions on an existing file.")
    sp.add_argument("matter_id")
    sp.add_argument("--target-filename", required=True)
    sp.add_argument("--mention", required=True, help="Comma-separated open_ids.")
    sp.add_argument("--mention-comment", required=True, help="Comment body.")

    # favorite
    sp = sub.add_parser("favorite", help="Toggle favorite on a matter.")
    sp.add_argument("matter_id")
    sp.add_argument("--unfavorite", action="store_true")

    # read
    sp = sub.add_parser("read", help="Mark matter as read.")
    sp.add_argument("matter_id")

    # contacts
    sp = sub.add_parser("contacts", help="List or search contacts.")
    sp.add_argument("--search", help="Name/keyword filter.")
    sp.add_argument("--limit", type=int, default=20)

    # sync
    sp = sub.add_parser("sync", help="Clone or pull the local git mirror.")
    sp.add_argument("--check", action="store_true", help="Only report status, don't sync.")

    # search (mirror-based)
    sp = sub.add_parser("search", help="Full-text search in the local mirror (title+body).")
    sp.add_argument("pattern")
    sp.add_argument("--limit", type=int, default=50)

    # history
    sp = sub.add_parser("history", help="Git log summary from the local mirror.")
    sp.add_argument("--since", default="7d")
    sp.add_argument("--limit", type=int, default=200)

    return p


HANDLERS = {
    "me": cmd_me,
    "matters": cmd_matters,
    "show": cmd_show,
    "reply": cmd_reply,
    "new": cmd_new,
    "mention": cmd_mention,
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
