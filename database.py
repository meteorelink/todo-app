# ============================================================
#  database.py —— 数据层（只管"怎么和数据库打交道"）
#
#  把数据库相关的东西集中在这里，main.py 就不用管 SQL 细节了。
#  这就是"分层"：接口层（main.py）管 HTTP，数据层管存储。
# ============================================================

import sqlite3
from pathlib import Path

# 数据库文件放在 database.py 同一个目录下。
# ⚠️ 为什么不用 "todos.db"？因为相对路径是相对【运行命令的目录】，
#    但 Path(__file__).parent 是"本文件所在目录"，不管你从哪里启动都对。
DB_FILE = Path(__file__).parent / "todos.db"


def get_connection():
    """打开一个数据库连接。

    每个请求开一个、用完就关。简单、不会漏。
    """
    conn = sqlite3.connect(DB_FILE)

    # ⚠️ 这一行很关键：
    #    不设它 → 查询结果是不能按列名取值的元组，只能 row[0]、row[1]
    #    设了它 → 可以 row["title"]，而且不怕列顺序变化
    conn.row_factory = sqlite3.Row

    return conn


def init_db():
    """建表 + 迁移。应用启动时调用一次。

    IF NOT EXISTS 不能少：每次 --reload 重启都会执行这里，
    没有它第二次启动就会报 "table todos already exists"。
    """
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键 + 永不复用的自增
            title    TEXT    NOT NULL,                    -- 文本，不能为空
            done     INTEGER NOT NULL DEFAULT 0,          -- ⚠️ SQLite 没有布尔类型，用 0/1
            due      TEXT,                                -- 截止日期 "YYYY-MM-DD"，可空
            priority TEXT    NOT NULL DEFAULT 'normal'    -- high / normal / low
        )
    """)

    # ⭐ 第二张表：多轮对话的"记忆"（见 conversations.py）
    #
    #    ⚠️ 为什么这里不需要 _migrate 那样的补列逻辑？
    #       因为这是一张【新的】表。`IF NOT EXISTS` 对"第一次建"是完全够用的：
    #       表不存在 → 建；存在 → 跳过。
    #
    #       只有当"表已经存在、但你想加列"的时候，IF NOT EXISTS 才会静默失效，
    #       那才需要 ALTER TABLE（就是上面 _migrate 干的事）。
    #       换句话说：新建表用 CREATE，改老表用 ALTER，两件事不要混。
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         TEXT PRIMARY KEY,          -- uuid4().hex，猜不出来
            messages   TEXT NOT NULL,             -- 整个 messages 数组的 JSON
            created_at TEXT NOT NULL,             -- ISO 时间，带时区
            updated_at TEXT NOT NULL              -- 用来判断过期
        )
    """)

    _migrate(conn)

    conn.commit()   # 建表也是写操作，也要 commit
    conn.close()


def _migrate(conn):
    """给【已经存在】的旧表补上后来新增的列。

    ⭐ 为什么需要这个函数？（这是本项目里"静默失败"的第 N 个变种）

       `CREATE TABLE IF NOT EXISTS` 遇到已存在的表会【直接跳过】。
       .db 文件里已经有 todos 表了，所以哪怕你把新列写进上面的 CREATE 语句，
       SQLite 也不会去动那张旧表 —— 不报错、不提示、什么也不发生。

       结果就是：代码看起来改了，跑起来一切正常，但新字段永远存不进去。

    ⭐ 正确做法：数据库迁移（migration）
       ALTER TABLE ... ADD COLUMN 是【就地改已有表】，原有的行都会保留。
       （SQLite 的 ALTER TABLE 只支持 ADD COLUMN / RENAME / DROP，够用。）

    ⭐ 为什么先查 PRAGMA 再改？
       因为 ALTER TABLE ADD COLUMN 加一个【已存在】的列会报错。
       这个函数在每次启动都会跑，所以必须先判断"有没有"。
    """
    # PRAGMA table_info(todos) 返回这张表每一列的信息（名字、类型、是否可空……）
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(todos)")}

    if "due" not in existing:
        conn.execute("ALTER TABLE todos ADD COLUMN due TEXT")

    if "priority" not in existing:
        # ⚠️ ADD COLUMN 加 NOT NULL 列时，必须给一个默认值 ——
        #    否则已有那些行不知道该填什么。SQLite 会直接拒绝。
        conn.execute(
            "ALTER TABLE todos ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'"
        )
