#!/usr/bin/env python3
"""Destructor: prune sessions older than 24h. Safe — destructor failure must
not mask a business pipeline error."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SESSIONS_DIR = Path.home() / ".pivot" / "sessions"
TTL_SECONDS = 24 * 3600


def main() -> int:
    sys.stdin.read()  # consume stdin per spec
    pruned = 0
    if SESSIONS_DIR.is_dir():
        now = time.time()
        for p in SESSIONS_DIR.glob("*.json"):
            try:
                if now - p.stat().st_mtime > TTL_SECONDS:
                    p.unlink()
                    pruned += 1
            except OSError:
                pass
    print(json.dumps({"output": {"sessions_pruned": pruned}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
