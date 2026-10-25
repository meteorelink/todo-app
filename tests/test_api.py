"""
后端接口测试 —— 这是"写测试"长什么样。

跑法（在 todo-app 目录下）：
    .\\.venv\\Scripts\\python.exe -m pytest tests -v

关键设计：
  · 用【临时数据库】跑测试 —— 不会碰你的 todos.db
  · 每个测试开始前清空表 —— 测试之间互不影响
  · 不需要启动 uvicorn —— TestClient 直接在进程内调用你的 app
"""

import pytest

import database
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """整个测试会话共用一个临时数据库 + 一个 TestClient。

    注意：database.DB_FILE 必须在 import main 之前改掉，
    因为 main.py 在被 import 时会立刻执行 init_db()（建表）。
    """
    test_db = tmp_path_factory.mktemp("testdata") / "test.db"
    database.DB_FILE = test_db

    import main  # ← 这时 init_db() 建的是【临时库】的表

    return TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_db(client):
    """每个测试开始前清空表 —— 保证测试之间互不影响"""
    conn = database.get_connection()
    conn.execute("DELETE FROM todos")
    conn.commit()
    conn.close()


# ============================================================
#  基础行为
# ============================================================

def test_empty_list(client):
    """一开始应该是空列表"""
    res = client.get("/todos")
    assert res.status_code == 200
    assert res.json() == []


def test_create_returns_201_and_server_id(client):
    """新增应返回 201，id 由服务器生成，done 是布尔值"""
    res = client.post("/todos", json={"title": "写实验报告"})
    assert res.status_code == 201

    body = res.json()
    assert body["id"] == 1
    assert body["title"] == "写实验报告"
    # ⚠️ 这一行是在守住一个重要约定：API 返回布尔值，不是 0/1
    assert body["done"] is False


def test_missing_title_returns_422(client):
    """缺 title 应该被 Pydantic 拦下，返回 422"""
    res = client.post("/todos", json={"done": False})
    assert res.status_code == 422


# ============================================================
#  行为往返（写进去 → 读出来，看是否一致）
# ============================================================

def test_toggle_flips_done(client):
    """打勾应该来回翻转"""
    created = client.post("/todos", json={"title": "A"}).json()
    url = f"/todos/{created['id']}/toggle"

    assert client.post(url).json()["done"] is True
    assert client.post(url).json()["done"] is False


def test_update_whole_todo(client):
    """PUT 是整体替换"""
    created = client.post("/todos", json={"title": "旧标题"}).json()

    res = client.put(
        f"/todos/{created['id']}",
        json={"title": "新标题", "done": True},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "新标题"
    assert res.json()["done"] is True


def test_delete_then_404(client):
    """删除后应查不到"""
    created = client.post("/todos", json={"title": "A"}).json()

    assert client.delete(f"/todos/{created['id']}").status_code == 204
    assert client.get(f"/todos/{created['id']}").status_code == 404


# ============================================================
#  ⭐ 把"学到的知识"固化成测试
#     测试最大的价值：让"你知道的道理"变成"改坏了会立刻报警"
# ============================================================

def test_id_never_reused(client):
    """删光之后再新增，id 应该继续往上走，不能回到 1

    这条守的是 AUTOINCREMENT 的语义。
    如果哪天有人把建表语句改成普通的 INTEGER PRIMARY KEY，这条会立刻红。
    """
    a = client.post("/todos", json={"title": "A"}).json()
    client.delete(f"/todos/{a['id']}")

    b = client.post("/todos", json={"title": "B"}).json()
    assert b["id"] > a["id"]


def test_sql_injection_attempt_is_harmless(client):
    """把注入字符串当普通文字提交 —— 应该只是存了一条怪名字，表还在

    这条守的是"永远用 ? 占位符"。
    如果哪天有人把 SQL 改成 f-string 拼接，这条会立刻红。
    """
    payload = "1; DROP TABLE todos; --"

    res = client.post("/todos", json={"title": payload})
    assert res.status_code == 201

    todos = client.get("/todos").json()
    assert len(todos) == 1
    assert todos[0]["title"] == payload
