"""Full-text search and history queries over the local git mirror.

Prefers ripgrep (`rg`) for speed; falls back to `git grep` when ripgrep is
missing. Both are deterministic subprocess calls — no AI here.

默认用 ripgrep（快），没装时回退到 git grep。纯确定性子进程。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def search(repo: Path, pattern: str, max_results: int = 50) -> List[dict]:
    """Return list of {path, line, text} matches."""
    if shutil.which("rg"):
        return _rg_search(repo, pattern, max_results)
    return _git_grep(repo, pattern, max_results)


def history(repo: Path, since: str = "7d", limit: int = 200) -> List[dict]:
    """Return list of {sha, ts, author, subject} commits since the given window.

    `since` is passed directly to git; git's approxidate parser accepts
    "7d", "24h", "2 weeks ago", "yesterday", absolute dates, etc.
    since 直接透给 git；git 原生支持 "7d" / "24h" / 自然语言日期。
    """
    try:
        result = subprocess.run(
            [
                "git", "-c", "core.quotepath=false",
                "log",
                f"--since={since}",
                f"--max-count={limit}",
                "--pretty=format:%h|%ct|%an|%s",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return []
    commits: List[dict] = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        commits.append(
            {
                "sha": parts[0],
                "ts": int(parts[1]) if parts[1].isdigit() else 0,
                "author": parts[2],
                "subject": parts[3],
            }
        )
    return commits


# ------------------------------- internals ---------------------------------

def _rg_search(repo: Path, pattern: str, max_results: int) -> List[dict]:
    try:
        result = subprocess.run(
            [
                "rg", "--json",
                "--max-count", "3",
                "--glob", "*.md",
                "--glob", "*.yaml",
                "--glob", "*.yml",
                pattern, ".",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return _git_grep(repo, pattern, max_results)

    matches: List[dict] = []
    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "match":
            continue
        d = obj.get("data", {})
        path = d.get("path", {}).get("text")
        if not path:
            continue
        matches.append(
            {
                "path": _decode_rg_path(path),
                "line": d.get("line_number", 0),
                "text": d.get("lines", {}).get("text", "").rstrip("\n"),
            }
        )
        if len(matches) >= max_results:
            break
    return matches


def _decode_rg_path(s: str) -> str:
    """Windows ripgrep sometimes emits paths in Rust's Debug format —
    outer double-quotes + \\NNN octal escapes for non-ASCII bytes. Unwrap.

    Windows rg --json 的 path.text 字段在非 ASCII 路径下会是 Rust Debug
    格式："..." 包裹 + \\NNN 八进制字节转义。这里还原成正常 UTF-8 路径。
    Mac / Linux 上的 rg 不会这样，所以这个函数对正常路径是 no-op。
    """
    if not (s.startswith('"') and s.endswith('"') and len(s) >= 2):
        return s
    inner = s[1:-1]
    decoded = re.sub(
        r"\\([0-3][0-7]{2})",
        lambda m: chr(int(m.group(1), 8)),
        inner,
    )
    try:
        # Each code point in `decoded` is a 0-255 byte of the original path.
        # Round-trip through latin-1 so we can reinterpret as UTF-8 bytes.
        # decoded 里每个码点是原路径的一个 0-255 字节；先过 latin-1 再 utf-8 解回来。
        return decoded.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return s


def _git_grep(repo: Path, pattern: str, max_results: int) -> List[dict]:
    """Fallback search using `git grep`.

    `-c core.quotepath=false` disables git's default behavior of wrapping
    non-ASCII paths in quotes and escaping bytes as \\NNN octal — we want
    literal UTF-8 out.
    -c core.quotepath=false 禁用 git 对非 ASCII 路径的引号包裹 + 八进制
    转义，直接输出 UTF-8。
    """
    try:
        result = subprocess.run(
            [
                "git", "-c", "core.quotepath=false",
                "grep", "-n", "--", pattern,
                "*.md", "*.yaml", "*.yml",  # mirror the rg glob filter
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return []
    matches: List[dict] = []
    for line in result.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        matches.append(
            {
                "path": parts[0],
                "line": int(parts[1]) if parts[1].isdigit() else 0,
                "text": parts[2],
            }
        )
        if len(matches) >= max_results:
            break
    return matches


