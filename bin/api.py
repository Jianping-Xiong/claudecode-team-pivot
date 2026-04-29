"""Zero-dep REST wrapper for team-pivot-web (Matter API).

Uses urllib so the skill works immediately after install — no pip required.
零依赖 REST 封装；故意不引 requests，skill 安装即用。

v0.5: migrated from deprecated /api/threads/* to /api/matters/* endpoints.
v0.5: 从已废弃的 /api/threads/* 迁移到 /api/matters/*。
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
            filtered = {k: v for k, v in params.items() if v is not None and v != ""}
            if filtered:
                url = f"{url}?{urllib.parse.urlencode(filtered)}"

        data = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "claudecode-team-pivot/0.5",
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
            raise PivotAPIError(0, "network_error", str(e.reason)) from e

    @staticmethod
    def _classify_http_error(status: int, detail: str) -> str:
        if status == 401:
            if "invalid_token" in str(detail):
                return "invalid_token"
            return "unauthorized"
        if status == 400 and "profile setup" in str(detail).lower():
            return "profile_setup_required"
        # Extract code from Pydantic detail objects for 404/409/422
        if isinstance(detail, dict):
            code = detail.get("code", "")
            if code:
                return code
        if status == 404:
            return "not_found"
        if status == 409:
            return "conflict"
        if status == 422:
            return "validation_error"
        return f"http_{status}"

    # ------------------------------ user -------------------------------

    def me(self) -> dict:
        """Verify the PAT works + return server info.

        team-pivot-web currently has no Bearer-capable /api/me endpoint — the
        /me route at root is cookie-only. /api/app/home is the cheapest Bearer
        endpoint that both (a) returns 200 on a valid token and (b) gives
        useful data (workspace head, server version).
        """
        return self._request("GET", "/api/app/home")

    # ----------------------------- matters -----------------------------

    def list_matters(
        self,
        status: Optional[str] = None,
        owner: Optional[str] = None,
        q: Optional[str] = None,
    ) -> dict:
        """List matters visible to the current user. Supports filtering.
        Note: `q` searches titles only, not file bodies.
        """
        return self._request(
            "GET", "/api/matters",
            params={"status": status, "owner": owner, "q": q},
        )

    def get_matter(self, matter_id: str) -> dict:
        """Get matter detail with timeline (bodies included)."""
        return self._request("GET", f"/api/matters/{_q(matter_id)}")

    def create_matter(
        self,
        *,
        category: str,
        title: str,
        initial_type: str,
        summary: str,
        body: str = "",
        owner: Optional[str] = None,
        comments: Optional[list[dict]] = None,
    ) -> dict:
        """Create a new matter with an initial timeline item.
        comments can include mentions: [{"body": "...", "mentions": ["ou_xxx"]}]
        """
        initial: dict = {"type": initial_type, "summary": summary, "body": body}
        if owner:
            initial["owner"] = owner
        if comments:
            initial["comments"] = comments
        payload: dict = {"category": category, "title": title, "initial_file": initial}
        return self._request("POST", "/api/matters", body=payload)

    def append_file(
        self,
        matter_id: str,
        *,
        type: str,
        summary: str,
        body: str = "",
        owner: Optional[str] = None,
        quote: Optional[str] = None,
        refer: Optional[list[str]] = None,
        comments: Optional[list[dict]] = None,
        verifications: Optional[list[dict]] = None,
        outcome: Optional[str] = None,
        status_change: Optional[dict] = None,
    ) -> dict:
        """Append a timeline item to a matter.
        Include `comments[].mentions` to @-mention people in the same request.
        Include `status_change: {from, to}` to transition matter status.
        """
        payload: dict = {"type": type, "summary": summary, "body": body}
        if owner:
            payload["owner"] = owner
        if quote:
            payload["quote"] = quote
        if refer:
            payload["refer"] = refer
        if comments:
            payload["comments"] = comments
        if verifications:
            payload["verifications"] = verifications
        if outcome:
            payload["outcome"] = outcome
        if status_change:
            payload["status_change"] = status_change
        return self._request(
            "POST", f"/api/matters/{_q(matter_id)}/files", body=payload
        )

    def add_comment(
        self,
        matter_id: str,
        *,
        target_file: str,
        body: str,
        mentions: Optional[list[str]] = None,
    ) -> dict:
        """Add a standalone comment (with optional @-mentions) on a target file.
        Mentions are open_ids; the server resolves them to pinyin and sends
        Feishu notifications.
        """
        payload: dict = {"target_file": target_file, "body": body}
        if mentions:
            payload["mentions"] = mentions
        return self._request(
            "POST", f"/api/matters/{_q(matter_id)}/comments", body=payload
        )

    def mark_read(self, matter_id: str) -> dict:
        return self._request("POST", f"/api/matters/{_q(matter_id)}/read")

    def toggle_favorite(self, matter_id: str, *, favorite: bool) -> dict:
        return self._request(
            "POST",
            f"/api/matters/{_q(matter_id)}/favorite",
            body={"favorite": favorite},
        )

    # ---------------------------- contacts -----------------------------

    def list_contacts(self, q: Optional[str] = None, limit: int = 20) -> dict:
        """Search contacts. Returns items with open_id, name, en_name, avatar_url.
        Use `name` (Chinese display name) to identify the right person.
        """
        params: dict = {"limit": limit}
        if q:
            params["q"] = q
        return self._request("GET", "/api/contacts", params=params)

    # --------------------------- workspace -----------------------------

    def get_workspace_mirror(self) -> dict:
        return self._request("GET", "/api/workspace/mirror")

    # --------------- deprecated thread API (kept for reference) --------
    # These call /api/threads/* which does NOT work for matters.
    # Matters use /api/matters/* endpoints above.
    # 以下旧 API 对 matter 返回 404，仅保留供参考。

    def list_threads(self, category: Optional[str] = None) -> dict:
        """DEPRECATED: does not work for matters. Use list_matters()."""
        return self._request("GET", "/api/threads", params={"category": category})

    def get_thread(self, category: str, slug: str) -> dict:
        """DEPRECATED: does not work for matters. Use get_matter()."""
        return self._request("GET", f"/api/threads/{_q(category)}/{_q(slug)}")


def _q(s: str) -> str:
    """URL-quote a path segment. Treat everything non-alphanumeric as safe=''."""
    return urllib.parse.quote(s, safe="")
