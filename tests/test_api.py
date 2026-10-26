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

    import main  # noqa: F401  （只为拿到 main.app 这个对象）

    # ⚠️ 光 import main 不够，这里必须显式建表。原因：
    #    Python 的 import 是"只执行一次"的。
    #    如果【别的测试文件】已经 import 过 main，
    #    这次 import 就不会重新执行，main 里的 init_db() 也就不会跑，
    #    测试库里就会【一张表都没有】→ 后面全部报 "no such table: todos"。
    #    显式再调一次 init_db()（它是幂等的，重复调用无害），
    #    这个 fixture 就【不再依赖测试文件的执行顺序】了。
    database.init_db()

    return TestClient(main.app)


@pytest.fixture(autouse=True)
def clean_db(client):
    """每个测试开始前清空表 —— 保证测试之间互不影响"""
    conn = database.get_connection()
    conn.execute("DELETE FROM todos")

    # ⚠️ 光 DELETE 不会重置自增计数器 —— 这正是"id 永不复用"的语义。
    #    但测试需要"每次从同一个起点开始"，否则
    #        assert body["id"] == 1
    #    会取决于这个测试是第几个跑的（顺序一变就红）。
    #
    #    SQLite 把 AUTOINCREMENT 的当前值存在 sqlite_sequence 这张系统表里，
    #    清掉它，下一个 insert 就又从 1 开始。
    #
    #    ⚠️ 注意：这只在【测试】里做 —— 生产代码绝不能这么干，
    #       那等于把"id 永不复用"这个保证拆掉了。
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'todos'")
    except Exception:
        pass   # 极端情况下这张系统表可能还没被创建，忽略即可

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
