#!/usr/bin/env python3
"""Freshen the local mirror before digest loads commits.

Policy:
- No mirror → clone (fatal on failure; digest can't proceed)
- Mirror exists, last fetch >1h ago → pull (non-fatal on failure; stale
  mirror is better than no digest — we warn and continue)
- Mirror exists, last fetch <1h ago → skip (fast path)

The age check reads `.git/FETCH_HEAD` mtime — touched on every `git fetch` /
`git pull`. For a brand-new clone, FETCH_HEAD is also created, so it's a
reliable unified marker.
以 .git/FETCH_HEAD 的 mtime 作为"上次同步时间"——fetch/pull/clone 都会刷。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "bin"))
from api import PivotAPI  # noqa: E402
from mirror import Mirror, MirrorError  # noqa: E402

STALE_SECONDS = 3600  # 1h freshness window


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
    if os.environ.get("PIVOT_MIRROR_DIR"):
        cfg["mirror_dir"] = os.environ["PIVOT_MIRROR_DIR"]
    return cfg


def _fetch_age(repo: Path) -> int | None:
    """Seconds since last fetch/pull/clone, or None if unknown."""
    fh = repo / ".git" / "FETCH_HEAD"
    if not fh.is_file():
        return None
    return int(time.time() - fh.stat().st_mtime)


def main() -> int:
    sys.stdin.read()  # consume pipeline payload; not needed for sync

    cfg = _load_config()
    api = PivotAPI(cfg["base_url"], cfg.get("token", ""))
    mirror = Mirror(api, mirror_dir=cfg.get("mirror_dir") or None)
    repo = mirror.repo_path_if_ready()

    action: str
    if not repo:
        # No mirror — must clone. Failure here is fatal for digest.
        try:
            repo = mirror.sync()
            action = "cloned"
        except MirrorError as e:
            print(f"digest.sync: clone failed: {e}", file=sys.stderr)
            return 1
    else:
        age = _fetch_age(repo)
        if age is None or age > STALE_SECONDS:
            try:
                mirror.sync()
                action = "pulled"
            except MirrorError as e:
                # Non-fatal: old data beats no data. Warn to stderr.
                # 失败不致命；旧 mirror 也比没数据强。
                print(
                    f"digest.sync: pull failed (continuing with cached mirror): {e}",
                    file=sys.stderr,
                )
                action = "pull_failed_using_cached"
        else:
            action = "fresh_skipped"

    out = {
        "output": {
            "action": action,
            "repo_path": str(repo),
            "age_seconds": _fetch_age(repo),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
