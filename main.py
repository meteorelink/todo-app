from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import get_connection, init_db      # ← 新增

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",     # 4A 的原生版本（保留，方便对照）
        "http://127.0.0.1:5173",     # 4B 的 Vite
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()          # ← 新增：应用启动时建表（已存在则什么都不做）

class TodoCreate(BaseModel):
    """新增任务时，客户端要提供的数据"""
    title: str
    done: bool = False


class TodoUpdate(BaseModel):
    """更新任务时，客户端要提供的数据"""
    title: str
    done: bool

def row_to_todo(row):
    """把数据库的一行，转成 API 要返回的字典"""
    return {
        "id": row["id"],
        "title": row["title"],
        "done": bool(row["done"]),      # ← 0/1 → False/True
    }

@app.get("/")
def read_root():
    return {"status": "ok", "message": "待办清单后端已启动"}


@app.get("/todos")
def read_todos():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM todos ORDER BY id").fetchall()
    conn.close()
    return [row_to_todo(r) for r in rows]

@app.get("/todos/{id}")
def read_one_todo(id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return row_to_todo(row)


@app.post("/todos", status_code=201)
def create_todo(todo: TodoCreate):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO todos (title, done) VALUES (?, ?)",
        (todo.title, int(todo.done)),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "title": todo.title, "done": todo.done}


@app.put("/todos/{id}")
def update_todo(id: int, todo: TodoUpdate):
    conn = get_connection()
    conn.execute(
        "UPDATE todos SET title = ?, done = ? WHERE id = ?",
        (todo.title, int(todo.done), id),
    )
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
    conn.commit()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return row_to_todo(row)


@app.delete("/todos/{id}", status_code=204)
def delete_todo(id: int):
    conn = get_connection()
    cur = conn.execute("DELETE FROM todos WHERE id = ?", (id,))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    if changed == 0:
        raise HTTPException(status_code=404, detail="任务不存在")


@app.post("/todos/{id}/toggle")
def toggle_todo(id: int):
    conn = get_connection()
    conn.execute("UPDATE todos SET done = NOT done WHERE id = ?", (id,))
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
    conn.commit()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return row_to_todo(row)