#!/usr/bin/env python3
"""Constructor: validate ~/.pivot/config.json exists, parses, and has a token.

Exits 0 on success with {"output": {...}} on stdout.
Exits 1 on failure with a user-facing error message on stderr.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CFG_PATH = Path.home() / ".pivot" / "config.json"


def main() -> int:
    # stdin is the pipeline payload; we ignore it in constructor.
    sys.stdin.read()

    if not CFG_PATH.is_file():
        print(
            f"Config file not found at {CFG_PATH}. "
            f"Copy config.example.json there and fill in your PAT.",
            file=sys.stderr,
        )
        return 1

    try:
        # utf-8-sig: tolerate BOMs from PowerShell Set-Content -Encoding UTF8.
        with CFG_PATH.open(encoding="utf-8-sig") as fh:
            cfg = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"Config file {CFG_PATH} is not valid JSON: {e}", file=sys.stderr)
        return 1

    token = cfg.get("token") or os.environ.get("PIVOT_TOKEN")
    if not token or token.startswith("pvt_REPLACE"):
        print(
            "No PAT token configured. Generate one on your Pivot Web Settings → "
            "API Tokens page (e.g. https://<your-base-url>/settings/api-tokens), "
            "then set the 'token' field in ~/.pivot/config.json "
            "or export PIVOT_TOKEN. Hint: run `python runner.py setup` for a "
            "guided flow.",
            file=sys.stderr,
        )
        return 1

    base_url = cfg.get("base_url") or os.environ.get("PIVOT_BASE_URL") or ""
    if not base_url or "YOUR_DOMAIN" in base_url:
        # Example-template value is a sentinel the user must replace; a silent
        # pass here would later manifest as 401/network_error, blame-shifting
        # to the token. Fail fast with a pointed message instead.
        # 模板占位必须替换，否则后面 401/网络错会让人错怪 token。
        print(
            "base_url is not configured (still set to the YOUR_DOMAIN "
            "placeholder, or empty). Edit ~/.pivot/config.json and set "
            "'base_url' to your team's Pivot deployment URL — the same host "
            "where you generated the PAT token. Tokens are tied to a specific "
            "host; a token from host A will not work against host B. "
            "Hint: `python runner.py setup` for a guided flow.",
            file=sys.stderr,
        )
        return 1
    base_url = base_url.rstrip("/")

    out = {
        "output": {
            "config_path": str(CFG_PATH),
            "base_url": base_url,
            # Don't echo the token — exposure risk. Emit length as a sanity hint.
            # 不回显 token 避免日志泄露，只给长度。
            "token_len": len(token),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
