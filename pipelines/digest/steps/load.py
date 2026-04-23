#!/usr/bin/env python3
"""Load recent commits from the local mirror for the digest LLM step.

Pure code step; no network. Assumes mirror has already been synced — if not,
we surface a clear error rather than silently scanning an empty repo.
纯本地读；mirror 没同步时明确报错而不是返空。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bin"))
from mirror import Mirror  # noqa: E402
import search as search_mod  # noqa: E402


def _load_config() -> dict:
    cfg_path = Path.home() / ".pivot" / "config.json"
    cfg: dict = {}
    if cfg_path.is_file():
        with cfg_path.open(encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
    if os.environ.get("PIVOT_MIRROR_DIR"):
        cfg["mirror_dir"] = os.environ["PIVOT_MIRROR_DIR"]
    return cfg


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    input_ = payload.get("input", {})

    since = input_.get("since") or "7d"
    try:
        limit = int(input_.get("limit") or 200)
    except (TypeError, ValueError):
        limit = 200

    cfg = _load_config()
    mirror = Mirror(None, mirror_dir=cfg.get("mirror_dir") or None)
    repo = mirror.repo_path_if_ready()
    if not repo:
        print(
            "digest.load: local mirror not found. Run `python bin/pivot.py sync` "
            "first to clone / pull the discussion repo.",
            file=sys.stderr,
        )
        return 1

    commits = search_mod.history(repo, since=since, limit=limit)

    # Build a compact text block for the LLM step.
    lines = []
    for c in commits:
        # `{sha, ts, author, subject}`
        lines.append(f"{c.get('sha','')} | {c.get('author','')} | {c.get('subject','')}")
    commits_text = "\n".join(lines) if lines else "(no commits in window)"

    # Compute earliest commit ts for the window label.
    ts_values = [c.get("ts") or 0 for c in commits]
    window_start = ""
    if ts_values and any(ts_values):
        import datetime as _dt
        earliest = min(t for t in ts_values if t)
        window_start = _dt.datetime.fromtimestamp(earliest).isoformat(timespec="seconds")

    out = {
        "output": {
            "since": since,
            "commit_count": len(commits),
            "window_start": window_start,
            "commits_text": commits_text,
            "repo_path": str(repo),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
