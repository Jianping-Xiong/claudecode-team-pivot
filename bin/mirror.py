"""Optional local git mirror for the Team Pivot discussion repo.

Mirror is read-only. Writes always go through the REST API (server handles
atomic commits). Default directory is `~/pivot-mirror/`, intentionally the
same as vscode-team-pivot so both tools share one clone on the same machine.

本模块维护讨论仓库的只读 clone；写操作走 REST（服务端原子提交）。默认
目录与 vscode-team-pivot 一致，两者共用同一份 clone。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

from api import PivotAPI, PivotAPIError


class MirrorError(Exception):
    pass


class Mirror:
    def __init__(self, api: Optional[PivotAPI], mirror_dir: Optional[str] = None):
        # api is only required for sync(); repo_path_if_ready / status work
        # without it, so local search/history commands can pass None.
        # api 仅 sync() 需要；本地查询（search/history）允许 api=None。
        self.api = api
        self.root = Path(mirror_dir).expanduser() if mirror_dir else Path.home() / "pivot-mirror"

    # ------------------------------ status -----------------------------

    def status(self) -> dict:
        path = self.repo_path_if_ready()
        return {
            "mirror_root": str(self.root),
            "repo_path": str(path) if path else None,
            "ready": path is not None,
        }

    def repo_path_if_ready(self) -> Optional[Path]:
        """Return the cloned repo directory if one exists under root, else None.

        Scans one level deep only. Matches vscode-team-pivot's discovery logic.
        只扫一层深度，和 vscode-team-pivot 的发现逻辑一致。
        """
        if not self.root.exists():
            return None
        try:
            for child in self.root.iterdir():
                if child.is_dir() and (child / ".git").is_dir():
                    return child
        except OSError:
            return None
        return None

    # ------------------------------ sync -------------------------------

    def sync(self) -> Path:
        """Clone if absent, fast-forward pull if present. Returns repo path."""
        if self.api is None:
            raise MirrorError("Mirror.sync requires a PivotAPI instance")
        try:
            info = self.api.get_workspace_mirror()
        except PivotAPIError as e:
            raise MirrorError(f"cannot fetch mirror info: {e}") from e

        if "repo_url" not in info:
            raise MirrorError(
                "server returned no repo_url; workspace not configured?"
            )

        auth_url = self._auth_url(info)
        repo_name = info.get("repo_name") or Path(urlparse(info["repo_url"]).path).stem
        branch = info.get("branch") or "main"

        self.root.mkdir(parents=True, exist_ok=True)
        repo_path = self.root / repo_name

        if (repo_path / ".git").is_dir():
            # Refresh remote URL every time — server may rotate git_token.
            # 每次都刷 remote URL；服务端可能滚动 git_token。
            self._git(["remote", "set-url", "origin", auth_url], cwd=repo_path)
            self._git(["fetch", "origin", branch], cwd=repo_path)
            self._git(["checkout", branch], cwd=repo_path)
            self._git(["pull", "--ff-only", "origin", branch], cwd=repo_path)
        else:
            self._git(
                [
                    "clone",
                    "--branch", branch,
                    "--single-branch",
                    auth_url,
                    str(repo_path),
                ]
            )
        return repo_path

    # ------------------------------ helpers ----------------------------

    @staticmethod
    def _auth_url(info: dict) -> str:
        """Embed credentials into the repo URL for basic-auth git.

        Matches vscode-team-pivot's auth flow. Uses `x-access-token` as the
        username by convention when the server omits `git_username`.
        User and token are percent-encoded — JS `URL` setters do this
        automatically, Python urllib does not, so we do it explicitly.
        Without this, a token containing `@` / `:` / `/` would break the URL.
        用户名和 token 要 percent-encode；JS URL 自动做，Python urllib 不做，
        不编码的话 token 含 @ / : / / 就会破坏 URL。
        """
        url = info["repo_url"]
        token = info.get("git_token")
        if not token:
            return url
        parsed = urlparse(url)
        user = info.get("git_username") or "x-access-token"
        host = parsed.hostname or ""
        netloc = f"{quote(user, safe='')}:{quote(token, safe='')}@{host}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunparse(
            (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

    def _git(self, args: list, cwd: Optional[Path] = None) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            return result.stdout
        except FileNotFoundError as e:
            raise MirrorError("git not found in PATH") from e
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip()
            # Scrub any embedded token from error text before surfacing.
            # 日志里擦掉可能泄露的 token。
            raise MirrorError(
                f"git {args[0]} failed: {_scrub_token(stderr)}"
            ) from e


def _scrub_token(s: str) -> str:
    """Best-effort redaction of `user:token@host` style credentials."""
    import re
    return re.sub(r"://[^/\s@:]+:[^/\s@]+@", "://***:***@", s)
