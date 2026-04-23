"""Zero-dep REST wrapper for team-pivot-web.

Uses urllib so the skill works immediately after install — no pip required.
零依赖 REST 封装；故意不引 requests，skill 安装即用。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class PivotAPIError(Exception):
    """Raised on any HTTP / network error. `code` maps server-specific failures
    to canonical strings for the caller (skill) to branch on.
    code 字段把服务端常见失败映射成规范字符串，便于 skill 层判断。
    """

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status}:{code}] {message}")
        self.status = status
        self.code = code
        self.message = message


class PivotAPI:
    def __init__(self, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            # drop None values so callers can pass optional params freely
            # 丢弃 None 值，允许调用方自由传可选参数
            filtered = {k: v for k, v in params.items() if v is not None and v != ""}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "claudecode-team-pivot/0.1",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except Exception:
                detail = raw
            code = self._classify_http_error(e.code, detail)
            raise PivotAPIError(e.code, code, detail) from e
        except urllib.error.URLError as e:
            # DNS / TLS / connection refused / proxy fail all land here
            # DNS/TLS/连接失败/代理错误都落在这里
            raise PivotAPIError(0, "network_error", str(e.reason)) from e

    @staticmethod
    def _classify_http_error(status: int, detail: str) -> str:
        if status == 401:
            if "invalid_token" in detail:
                return "invalid_token"
            return "unauthorized"
        # Server's exact string is "profile setup required"; match that phrase
        # rather than any 400 that happens to contain the word "profile".
        # 服务端的确切文案是 "profile setup required"；不要宽松匹配所有含
        # "profile" 的 400。
        if status == 400 and "profile setup" in detail.lower():
            return "profile_setup_required"
        if status == 404:
            return "not_found"
        return f"http_{status}"

    # ------------------------------ user -------------------------------

    def me(self) -> dict:
        """Verify the PAT works + return server info.

        team-pivot-web currently has no Bearer-capable /api/me endpoint — the
        /me route at root is cookie-only. /api/app/home is the cheapest Bearer
        endpoint that both (a) returns 200 on a valid token and (b) gives
        useful data (workspace head, server version).
        团队 Pivot 服务端现在没有 Bearer 能访问的 /api/me；/api/app/home
        是最便宜的认证探测点，200 即 token 有效。
        """
        return self._request("GET", "/api/app/home")

    # ----------------------------- threads -----------------------------

    def list_threads(self, category: Optional[str] = None) -> dict:
        return self._request("GET", "/api/threads", params={"category": category})

    def get_thread(self, category: str, slug: str) -> dict:
        return self._request("GET", f"/api/threads/{_q(category)}/{_q(slug)}")

    def new_thread(
        self,
        *,
        category: str,
        title: str,
        body: str,
        mentions: Optional[dict] = None,
    ) -> dict:
        payload: dict = {"category": category, "title": title, "body": body}
        if mentions:
            payload["mentions"] = mentions
        return self._request("POST", "/api/threads", body=payload)

    def reply(
        self,
        category: str,
        slug: str,
        *,
        body: str,
        mentions: Optional[dict] = None,
        reply_to: Optional[str] = None,
        references: Optional[list] = None,
    ) -> dict:
        payload: dict = {"body": body}
        if mentions:
            payload["mentions"] = mentions
        if reply_to:
            payload["reply_to"] = reply_to
        if references:
            payload["references"] = references
        return self._request(
            "POST", f"/api/threads/{_q(category)}/{_q(slug)}/posts", body=payload
        )

    def add_mention(
        self,
        category: str,
        slug: str,
        *,
        target_filename: str,
        open_ids: list,
        comments: str,
    ) -> dict:
        payload = {
            "target_filename": target_filename,
            "mentions": {"open_ids": open_ids, "comments": comments},
        }
        return self._request(
            "POST", f"/api/threads/{_q(category)}/{_q(slug)}/mentions", body=payload
        )

    def change_status(
        self,
        category: str,
        slug: str,
        *,
        to: str,
        reason: Optional[str] = None,
    ) -> dict:
        payload: dict = {"to": to}
        if reason:
            payload["reason"] = reason
        return self._request(
            "POST", f"/api/threads/{_q(category)}/{_q(slug)}/status", body=payload
        )

    def set_favorite(self, category: str, slug: str, *, favorite: bool) -> dict:
        return self._request(
            "POST",
            f"/api/threads/{_q(category)}/{_q(slug)}/favorite",
            body={"favorite": favorite},
        )

    def mark_read(self, category: str, slug: str) -> dict:
        return self._request(
            "POST", f"/api/threads/{_q(category)}/{_q(slug)}/read"
        )

    # ---------------------------- contacts -----------------------------

    def list_contacts(self, q: Optional[str] = None, limit: int = 20) -> dict:
        params: dict = {"limit": limit}
        if q:
            params["q"] = q
        return self._request("GET", "/api/contacts", params=params)

    # --------------------------- workspace -----------------------------

    def get_workspace_mirror(self) -> dict:
        return self._request("GET", "/api/workspace/mirror")


def _q(s: str) -> str:
    """URL-quote a path segment. Treat everything non-alphanumeric as safe=''."""
    return urllib.parse.quote(s, safe="")
