# ============================================================
#  routers/todos.py —— 所有 /todos 相关的接口
#
#  ⭐ 关键变化：@app.get(...) 变成了 @router.get(...)
#
#  `router` 是一个「接口组」。
#  你可以在多个文件里各建一个 router（todos、users、auth……），
#  最后在 main.py 里统一挂到 app 上。
#
#  这就是"分层"：main.py 不需要知道具体有哪些接口，
#  它只需要知道"有 todos 这个组，挂上去"。
# ============================================================

from fastapi import APIRouter, HTTPException

from database import get_connection
from models import TodoCreate, TodoUpdate, row_to_todo

# 创建一个接口组
router = APIRouter()


# ============================================================
#  接口：装饰器只是"往路由表里登记一行"
#  @router.get("/todos")  ≈  routes["GET /todos"] = read_todos
# ============================================================

@router.get("/todos")
def read_todos():
    """列出全部任务"""
    conn = get_connection()

    # 执行 SQL，fetchall() 把结果全部取出来（不取的话结果会被丢弃！）
    # ORDER BY 不能省：不写就没有顺序保证。
    rows = conn.execute("SELECT * FROM todos ORDER BY id").fetchall()

    conn.close()

    # 列表推导式：把每一行都转成字典
    return [row_to_todo(r) for r in rows]


@router.get("/todos/{id}")
def read_one_todo(id: int):
    """查单条任务"""
    # 路径里的 {id} 会被 FastAPI 抠出来传给 id 参数。
    # id: int 这个类型注解让 FastAPI 自动把 "5" 转成整数 5（转不了就 422）。
    conn = get_connection()

    # ⚠️ 永远用 ? 占位符，绝不用 f-string 拼 SQL（否则会被注入）
    # fetchone() 只取第一行，没有则返回 None
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()

    conn.close()

    if row is None:
        # 错误必须用状态码表达，不能只写在 body 里
        raise HTTPException(status_code=404, detail="任务不存在")

    return row_to_todo(row)


@router.post("/todos", status_code=201)
def create_todo(todo: TodoCreate):
    """新增任务。成功返回 201 Created（比笼统的 200 更精确）"""
    conn = get_connection()

    # 用 cur 接住返回值，才能拿到 cur.lastrowid
    cur = conn.execute(
        "INSERT INTO todos (title, done) VALUES (?, ?)",
        # ⚠️ 写进数据库前要把 bool 转成 int（True → 1）
        (todo.title, int(todo.done)),
    )

    conn.commit()          # ⚠️ 少这一行数据不会真的写进去，而且不报错
    new_id = cur.lastrowid # 数据库刚分配的自增 id（永不复用）
    conn.close()

    return {"id": new_id, "title": todo.title, "done": todo.done}


@router.put("/todos/{id}")
def update_todo(id: int, todo: TodoUpdate):
    """整体替换一条任务"""
    conn = get_connection()

    conn.execute(
        "UPDATE todos SET title = ?, done = ? WHERE id = ?",
        (todo.title, int(todo.done), id),
    )

    # ⚠️ UPDATE 改 0 行不会报错（静默失败），所以再查一次判断"到底改到没有"
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()

    conn.commit()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 返回"从数据库读回来的真实值"，而不是把输入原样回显 —— 更有说服力
    return row_to_todo(row)


@router.delete("/todos/{id}", status_code=204)
def delete_todo(id: int):
    """删除一条任务。204 = 成功，但没有内容要返回"""
    conn = get_connection()

    cur = conn.execute("DELETE FROM todos WHERE id = ?", (id,))
    conn.commit()

    changed = cur.rowcount   # 影响了几行。0 表示没有这个 id
    conn.close()

    if changed == 0:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 注意这里不返回任何东西 —— 204 就不该有 body


@router.post("/todos/{id}/toggle")
def toggle_todo(id: int):
    """翻转完成状态（未完成 ↔ 已完成）"""
    conn = get_connection()

    # ⭐ 一条 SQL 就完成翻转。
    #    为什么不用"先查出来再改"？因为并发下会丢失更新：
    #    你读到的旧值，在写回去之前可能已经被别人改了。
    #    写成"基于当前值的操作"（NOT done）就没有这个问题。
    conn.execute("UPDATE todos SET done = NOT done WHERE id = ?", (id,))

    # UPDATE 找不到行不报错，所以靠后面的 SELECT 判断存在性
    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()

    conn.commit()
    conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    return row_to_todo(row)
