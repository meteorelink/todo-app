"""
数据库迁移测试 —— 测 database._migrate()

这是 8.4 加的。为什么单独一个文件？
因为它是本项目里第一个"不经过接口"就能测的东西：
_migrate 只接收一个 sqlite3 连接，不碰网络、不碰 FastAPI。
这种函数最容易测，也最值得测 —— 它一旦出错，是【静默】的。
"""

import sqlite3

from database import _migrate


def _old_schema_connection():
    """造一个"加 due/priority 之前"的数据库

    ⚠️ 这里的建表语句是【故意写成旧版本】的：
       只有 id / title / done 三列。
       如果哪天它和 database.py 里的 CREATE TABLE 变成一样了，
       这个测试就失去了意义 —— 它就不再能模拟"升级旧库"了。
    """
    conn = sqlite3.connect(":memory:")   # :memory: = 全在内存里，不落磁盘
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE todos (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
    """)
    # 塞一条旧数据 —— 迁移之后它必须还在
    conn.execute("INSERT INTO todos (title, done) VALUES (?, ?)", ("旧任务", 0))
    conn.commit()
    return conn


def _columns(conn):
    return {row["name"] for row in conn.execute("PRAGMA table_info(todos)")}


def test_migrate_adds_the_new_columns():
    conn = _old_schema_connection()
    assert "due" not in _columns(conn)      # 迁移前确实没有

    _migrate(conn)

    cols = _columns(conn)
    assert "due" in cols
    assert "priority" in cols


def test_migrate_keeps_existing_rows():
    """⭐ 迁移最关键的一条：不能删数据

    ALTER TABLE ADD COLUMN 是就地改表，原来的行都保留。
    如果哪天有人把它改成"建新表 + 拷数据 + 删旧表"，
    这条测试会第一时间发现数据丢了。
    """
    conn = _old_schema_connection()

    _migrate(conn)

    rows = conn.execute("SELECT * FROM todos").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == "旧任务"


def test_migrate_fills_sensible_defaults():
    """旧行补上新列时，应该拿到合理的默认值"""
    conn = _old_schema_connection()

    _migrate(conn)

    row = conn.execute("SELECT * FROM todos").fetchone()
    assert row["due"] is None              # 旧任务没有截止日期 → NULL
    assert row["priority"] == "normal"     # 旧任务不该被莫名标成高优先级


def test_migrate_is_idempotent():
    """⭐ 幂等：跑多少次结果都一样

    ⚠️ 这条测试不是多余的。
       init_db() 在每次 uvicorn --reload 重启时都会跑，
       也就是 _migrate 会被反复调用。
       如果它没有先查 PRAGMA 就直接 ALTER TABLE，
       第二次启动就会报 "duplicate column name: due" —— 服务直接起不来。
    """
    conn = _old_schema_connection()

    _migrate(conn)
    _migrate(conn)      # 第二次不该抛异常
    _migrate(conn)      # 第三次也一样

    assert {"due", "priority"} <= _columns(conn)
