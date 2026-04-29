"""Tests for the Matter API client (bin/api.py v0.5).

Uses unittest.mock to simulate HTTP responses — no network required.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(_BIN))

from api import PivotAPI, PivotAPIError


def _fake_response(status: int, body: dict) -> callable:
    """Return a urlopen mock that returns the given status + JSON body."""

    class _Resp:
        def __init__(self, raw_bytes):
            self._raw = raw_bytes

        def read(self):
            return self._raw

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def _urlopen(req, timeout=None):
        if status >= 400:
            import urllib.error
            raise urllib.error.HTTPError(
                req.full_url, status, str(status), {}, _Resp(
                    json.dumps(body, ensure_ascii=False).encode("utf-8")
                ),
            )
        return _Resp(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    return _urlopen


class TestListMatters(unittest.TestCase):
    def test_list_empty(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        with patch("urllib.request.urlopen", _fake_response(200, {"items": []})):
            result = api.list_matters()
        self.assertEqual(result, {"items": []})

    def test_list_with_filters(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        with patch("urllib.request.urlopen", _fake_response(200, {"items": [
            {"id": "test-1", "title": "Test", "current_status": "planning"}
        ]})):
            result = api.list_matters(status="planning", owner="jason", q="Test")
        self.assertEqual(len(result["items"]), 1)


class TestGetMatter(unittest.TestCase):
    def test_get_matter_ok(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {
            "matter": {"id": "m1", "title": "T", "current_status": "planning"},
            "timeline": [
                {"file": "d/p/m1/001_u_think_x.md", "type": "think",
                 "creator": "jason", "body": "# Hello\n\nWorld"}
            ]
        }
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.get_matter("m1")
        self.assertEqual(result["matter"]["id"], "m1")
        self.assertEqual(len(result["timeline"]), 1)

    def test_get_matter_404(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        detail = {"detail": {"code": "matter_not_found"}}
        with patch("urllib.request.urlopen", _fake_response(404, detail)):
            with self.assertRaises(PivotAPIError) as ctx:
                api.get_matter("ghost")
        self.assertEqual(ctx.exception.code, "matter_not_found")


class TestCreateMatter(unittest.TestCase):
    def test_create_matter_ok(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {
            "matter": {"id": "m1", "title": "Test", "current_status": "planning"},
            "initial_timeline_item": {"type": "think", "file": "d/p/m1/001_j_think_x.md"},
            "matter_id": "m1",
            "file": "d/p/m1/001_j_think_x.md",
        }
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.create_matter(
                category="Pivot", title="Test",
                initial_type="think", summary="s", body="b",
            )
        self.assertEqual(result["matter_id"], "m1")


class TestAppendFile(unittest.TestCase):
    def test_append_file_with_status_change(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {
            "item": {"type": "act", "file": "d/p/m1/002_j_act_x.md"},
            "matter": {"current_status": "executing"},
        }
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.append_file(
                "m1", type="act", summary="go",
                status_change={"from": "planning", "to": "executing"},
            )
        self.assertEqual(result["matter"]["current_status"], "executing")

    def test_append_file_with_comments_and_mentions(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {
            "item": {"type": "think", "file": "d/p/m1/002_j_think_x.md"},
            "matter": {"current_status": "planning"},
        }
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.append_file(
                "m1", type="think", summary="review",
                comments=[{"body": "请指正", "mentions": ["ou_aaa", "ou_bbb"]}],
            )
        self.assertEqual(result["item"]["type"], "think")


class TestAddComment(unittest.TestCase):
    def test_add_comment_ok(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {"ok": True}
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.add_comment(
                "m1", target_file="d/p/m1/001_x.md",
                body="LGTM", mentions=["ou_aaa"],
            )
        self.assertTrue(result["ok"])


class TestMarkReadAndFavorite(unittest.TestCase):
    def test_mark_read(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        with patch("urllib.request.urlopen", _fake_response(200, {"ok": True})):
            result = api.mark_read("m1")
        self.assertTrue(result["ok"])

    def test_toggle_favorite(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        with patch("urllib.request.urlopen", _fake_response(200, {"ok": True, "favorite": True})):
            result = api.toggle_favorite("m1", favorite=True)
        self.assertTrue(result["favorite"])


class TestContacts(unittest.TestCase):
    def test_list_contacts(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {"items": [
            {"open_id": "ou_1", "name": "邓柯", "en_name": "", "avatar_url": ""},
            {"open_id": "ou_2", "name": "刘昱", "en_name": "", "avatar_url": ""},
        ], "total": 2}
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.list_contacts(q="邓")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["name"], "邓柯")


class TestURLError(unittest.TestCase):
    def test_network_error(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            with self.assertRaises(PivotAPIError) as ctx:
                api.list_matters()
        self.assertEqual(ctx.exception.code, "network_error")


class TestDeprecatedAPIs(unittest.TestCase):
    """Old thread APIs still exist but return 404 for matters."""

    def test_list_threads_still_callable(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        with patch("urllib.request.urlopen", _fake_response(200, {"items": []})):
            result = api.list_threads(category="Pivot")
        self.assertEqual(result, {"items": []})

    def test_get_thread_still_callable(self):
        api = PivotAPI("https://pivot.example.com", "pvt_test")
        resp = {"meta": {"title": "T"}, "posts": []}
        with patch("urllib.request.urlopen", _fake_response(200, resp)):
            result = api.get_thread("Pivot", "old-slug")
        self.assertEqual(result["meta"]["title"], "T")


if __name__ == "__main__":
    unittest.main()
