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
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """整个测试会话共用一个临时数据库 + 一个 TestClient。

    注意：database.DB_FILE 必须在 import main 之前改掉，
    因为 main.py 在被 import 时会立刻执行 init_db()（建表）。

    为什么不用 pytest 的 tmp_path_factory？
    它会建在系统临时目录（C:/Users/.../Temp/pytest-of-<用户>），
    那个位置在当前的环境里不可写（PermissionError: WinError 5）。
    改成仓库内 tests/_tmp_api/，稳定可写，也已加进 .gitignore。
    """
    test_dir = Path(__file__).resolve().parent / "_tmp_api"
    test_dir.mkdir(exist_ok=True)
    database.DB_FILE = test_dir / "test.db"

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

    # ⚠️ due 和 priority 必须带上（PUT 是整体替换，不给就是 422）。
    #    due 可以是 null，但那表示"我明确不要截止日期"，
    #    而不是"我忘了传"—— 这两件事在 API 上必须分得开。
    res = client.put(
        f"/todos/{created['id']}",
        json={"title": "新标题", "done": True, "due": None, "priority": "high"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "新标题"
    assert res.json()["done"] is True
    assert res.json()["priority"] == "high"
    assert res.json()["due"] is None


# ============================================================
#  8.4：截止日期与优先级
# ============================================================

def test_due_and_priority_are_stored(client):
    """新建时带上 due/priority，读回来必须一模一样"""
    client.post(
        "/todos",
        json={"title": "交实验报告", "due": "2026-11-06", "priority": "high"},
    )

    todo = client.get("/todos").json()[0]
    assert todo["due"] == "2026-11-06"
    assert todo["priority"] == "high"


def test_due_and_priority_have_defaults(client):
    """什么都不传时，due 是 null、priority 是 normal"""
    client.post("/todos", json={"title": "没有日期的任务"})

    todo = client.get("/todos").json()[0]
    assert todo["due"] is None
    assert todo["priority"] == "normal"


def test_bad_due_format_is_422(client):
    """日期格式不对 → 边界拦下，绝不进数据库

    ⚠️ 这正是关键：如果放进去，数据库里就会存一串
       "下周五" 这样的文本，前端按字符串比较时会得到无意义的结果。
    """
    res = client.post("/todos", json={"title": "x", "due": "下周五"})
    assert res.status_code == 422


def test_invalid_priority_is_422(client):
    """priority 只能是 high / normal / low"""
    res = client.post("/todos", json={"title": "x", "priority": "urgent"})
    assert res.status_code == 422
    # 错误信息里应该列出允许的值，用户才知道该改成什么
    assert "high" in res.text


def test_batch_keeps_due_and_priority(client):
    """批量创建也要把两个新字段存进去

    ⚠️ 为什么单条和批量都要测？
       因为它们是两条不同的代码路径（两条 INSERT）。
       只测单条的话，"批量那条忘了加字段"这种 bug 是测不出来的。
    """
    res = client.post(
        "/todos/batch",
        json={
            "tasks": [
                {"title": "交报告", "due": "2026-11-06", "priority": "high"},
                {"title": "买牛奶"},
            ]
        },
    )
    assert res.status_code == 201

    todos = client.get("/todos").json()
    assert todos[0]["due"] == "2026-11-06"
    assert todos[0]["priority"] == "high"
    assert todos[1]["due"] is None
    assert todos[1]["priority"] == "normal"


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


# ============================================================
#  边界校验：空标题不是"没内容"，是"不合法"
# ============================================================

def test_blank_title_is_rejected(client):
    """全是空格的标题应该 422，而不是被当成一条正常的任务存进去

    以前 title 是裸的 str，POST {"title": ""} 会 201 成功，
    然后前端渲染出一个空的 li —— 用户完全看不见它，也删不掉。
    """
    for bad in ["", "   ", "\t\n"]:
        res = client.post("/todos", json={"title": bad})
        assert res.status_code == 422, f"{bad!r} 竟然被接受了"

    assert client.get("/todos").json() == []


def test_title_is_stripped_before_saving(client):
    """首尾空白会被去掉再入库"""
    body = client.post("/todos", json={"title": "  写实验报告  "}).json()
    assert body["title"] == "写实验报告"


# ============================================================
#  ⭐ 批量新增：守"要么全成，要么全不成"
# ============================================================

def test_batch_creates_all(client):
    """三条一起进，返回三条，id 依次递增"""
    res = client.post(
        "/todos/batch",
        json={"tasks": [{"title": "A"}, {"title": "B"}, {"title": "C"}]},
    )
    assert res.status_code == 201

    created = res.json()
    assert [t["title"] for t in created] == ["A", "B", "C"]
    assert [t["id"] for t in created] == [1, 2, 3]
    assert len(client.get("/todos").json()) == 3


def test_batch_with_one_invalid_item_creates_nothing(client):
    """⭐ 这条最值钱：第 2 条非法 → 整批被拒 → 数据库里一条都没有

    如果哪天有人把校验挪进循环里、改成"跳过坏的、写进好的"，
    这条会立刻红 —— 而那个改动正是最危险的静默失败：
    用户以为确认了 3 条，实际只有 2 条，且他永远不会知道。
    """
    res = client.post(
        "/todos/batch",
        json={"tasks": [{"title": "A"}, {"title": ""}, {"title": "C"}]},
    )
    assert res.status_code == 422
    assert client.get("/todos").json() == []


def test_batch_empty_list_is_422(client):
    """批量创建 0 条没有意义 —— 它只可能是调用方出了 bug"""
    assert client.post("/todos/batch", json={"tasks": []}).status_code == 422


def test_batch_rolls_back_when_an_insert_fails(client, monkeypatch):
    """⭐ 真正验证"事务"的测试：第 2 条插入时炸掉，第 1 条必须被回滚

    为什么需要这条？
      "校验不过 → 422" 那条其实【没走到事务代码】——
      请求在 Pydantic 那一层就被拦下了，rollback() 一行都没执行。
      也就是说：只测 422，那个 try/except/rollback 相当于没写过。
      未执行的代码 = 未验证的代码。

    做法：把 get_connection 换成"第 2 次 INSERT 会抛异常"的假连接。
    这种故障真实存在（磁盘满、I/O 错误、锁冲突）。
    """
    import sqlite3

    import main
    from routers import todos as todos_router

    real_factory = todos_router.get_connection

    class FlakyConn:
        def __init__(self, real):
            self.real = real
            self.inserts = 0

        def execute(self, sql, params=()):
            if sql.lstrip().upper().startswith("INSERT"):
                self.inserts += 1
                if self.inserts == 2:
                    raise sqlite3.OperationalError("disk I/O error（模拟）")
            return self.real.execute(sql, params)

        def commit(self):
            return self.real.commit()

        def rollback(self):
            return self.real.rollback()

        def close(self):
            return self.real.close()

    monkeypatch.setattr(
        todos_router, "get_connection", lambda: FlakyConn(real_factory())
    )

    # 默认的 TestClient 会把服务器异常重新抛出来（方便调试），
    # 这里我们要看"真的返回了 500"，所以关掉它。
    safe = TestClient(main.app, raise_server_exceptions=False)
    res = safe.post(
        "/todos/batch",
        json={"tasks": [{"title": "A"}, {"title": "B"}, {"title": "C"}]},
    )

    assert res.status_code == 500
    # ⭐ 关键断言：A 也不该留下
    assert client.get("/todos").json() == []
