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
    """建表（如果还不存在的话）。应用启动时调用一次。

    IF NOT EXISTS 不能少：每次 --reload 重启都会执行这里，
    没有它第二次启动就会报 "table todos already exists"。
    """
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,   -- 主键 + 永不复用的自增
            title TEXT    NOT NULL,                    -- 文本，不能为空
            done  INTEGER NOT NULL DEFAULT 0           -- ⚠️ SQLite 没有布尔类型，用 0/1
        )
    """)

    conn.commit()   # 建表也是写操作，也要 commit
    conn.close()
