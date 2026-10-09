import sqlite3
from pathlib import Path

# 数据库文件放在 database.py 同一个目录下
DB_FILE = Path(__file__).parent / "todos.db"


def get_connection():
    """打开一个数据库连接"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row      # ← 让查询结果能按列名取值
    return conn


def init_db():
    """建表（如果还不存在的话）"""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()