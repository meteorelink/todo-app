# tests/test_api_integration.py
"""
集成测试：真的发 HTTP 请求给运行中的服务器
要求：先启动后端（终端 A 跑 uvicorn）

跑法：python -m unittest tests.test_api_integration -v
"""
import json
import unittest
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def request(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else None


class TestAPIIntegration(unittest.TestCase):
    def test_list_returns_200_and_list(self):
        status, data = request("GET", "/todos")
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)

    def test_create_then_get_then_delete(self):
        status, created = request("POST", "/todos", {"title": "集成测试"})
        self.assertEqual(status, 201)
        self.assertIs(created["done"], False)

        status, got = request("GET", f"/todos/{created['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(got["title"], "集成测试")

        status, _ = request("DELETE", f"/todos/{created['id']}")
        self.assertEqual(status, 204)

        status, _ = request("GET", f"/todos/{created['id']}")
        self.assertEqual(status, 404)