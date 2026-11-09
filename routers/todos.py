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
from models import TodoBatchCreate, TodoCreate, TodoUpdate, row_to_todo

# 创建一个接口组
router = APIRouter()


def _values(todo) -> tuple:
    """把 Pydantic 对象转成 SQL 参数元组

    ⭐ 为什么单独抽出来？
       因为"新增一条"和"批量新增"要写两次同样的转换 ——
       两处写法一旦不一致，就会出现"单条能存日期、批量存不进去"这种
       最难查的 bug（两条路径长得太像，你根本想不到它们不一样）。

    ⚠️ 为什么 date 要手动转成字符串？
       sqlite3 只认识 Python 的 int / float / str / bytes / None 这几类。
       直接塞一个 datetime.date 进去，会报
           sqlite3.InterfaceError: Error binding parameter 2 ...
       必须在边界上转成 "YYYY-MM-DD"。
    """
    return (
        todo.title,
        int(todo.done),                              # bool → 0/1
        todo.due.isoformat() if todo.due else None,  # date → "2026-11-06"
        todo.priority,
    )


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
        "INSERT INTO todos (title, done, due, priority) VALUES (?, ?, ?, ?)",
        _values(todo),
    )

    conn.commit()          # ⚠️ 少这一行数据不会真的写进去，而且不报错
    new_id = cur.lastrowid # 数据库刚分配的自增 id（永不复用）
    conn.close()

    return {
        "id": new_id,
        "title": todo.title,
        "done": todo.done,
        "due": todo.due.isoformat() if todo.due else None,
        "priority": todo.priority,
    }


@router.post("/todos/batch", status_code=201)
def create_todos_batch(payload: TodoBatchCreate):
    """批量新增 —— 一个事务：要么全部成功，要么一条都不写

    ⭐ 为什么不能让前端循环调 N 次 POST /todos？
       那样"用户点一次确认"这一个业务动作，就被拆成了 N 个独立事务：
       第 3 条失败时，前 2 条已经永久入库了。
       用户看到的是"出错了，什么都没加上"，数据库里却躺着 2 条。
       他再点一次"确认"，那 2 条就变成重复数据 ——
       而 title 相同完全合法，没有任何约束会拦它，程序也不会报错。
       又是"静默失败"，只是这次它藏在网络里。

    ⭐ 为什么参数是 list[TodoCreate]？
       只要有一条不合法，整个请求体就不合法，Pydantic 直接 422，
       请求根本进不到这个函数里 —— 一条都写不进去。
       这就是"整批拒绝"，不用自己写 if 逐个判断。

    ⭐ 为什么这个接口里完全看不到 AI？
       AI 的活在前一步 /ai/parse 就干完了。这里只认"一个任务列表"，
       谁给的都一样。所以将来 AI 之外的功能（比如从模版批量导入）
       也能直接用它。
    """
    conn = get_connection()
    created = []

    try:
        for t in payload.tasks:
            cur = conn.execute(
                "INSERT INTO todos (title, done, due, priority) VALUES (?, ?, ?, ?)",
                _values(t),
            )
            # lastrowid 是刚插入那一条的 id，所以必须【插一条取一次】
            created.append({
                "id": cur.lastrowid,
                "title": t.title,
                "done": t.done,
                "due": t.due.isoformat() if t.due else None,
                "priority": t.priority,
            })

        # ⚠️ commit() 只调【一次】，而且写在循环【外面】。
        #    写在循环里面 = 每插一条就提交一次 = 又变回 N 个事务了，
        #    这次连 try/except 都救不回来。
        conn.commit()

    except Exception:
        # 任何一条出错 → 全部回滚 → 数据库回到调用前的样子
        conn.rollback()
        raise
    finally:
        conn.close()

    return created


@router.put("/todos/{id}")
def update_todo(id: int, todo: TodoUpdate):
    """整体替换一条任务"""
    conn = get_connection()

    conn.execute(
        "UPDATE todos SET title = ?, done = ?, due = ?, priority = ? WHERE id = ?",
        # ⚠️ _values(todo) 返回 4 个值，这里还要再拼上 id ——
        #    SQL 里 ? 的顺序必须和这里元组的顺序完全对应
        _values(todo) + (id,),
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


def set_done(id: int, done: bool) -> dict:
    """把完成状态【设为】done（幂等）。

    ⭐ 这个函数没有挂成 HTTP 路由 —— 它是给 AI 工具用的。

    界面用 toggle_todo（"切换"），因为人看着当前状态点一下；
    AI 用 set_done（"设为"），因为模型会重试，而重试要求幂等：
    调一次和调两次必须得到同样的结果。

        toggle_todo(id)         调两次 → 回到原点  ✗
        set_done(id, True)      调两次 → 还是完成  ✓

    ⚠️ 如果哪天界面也需要"明确设为已完成"，把这个函数挂上
       @router.post("/todos/{id}/done") 就行 —— 逻辑不用重写。
    """
    conn = get_connection()

    # 一条 UPDATE 搞定，不"先读再写" —— 和 toggle 同理：
    # 先读再写会在两次调用之间被别的写入插队。
    cur = conn.execute("UPDATE todos SET done = ? WHERE id = ?", (int(done), id))
    conn.commit()
    changed = cur.rowcount

    # UPDATE 找不到行时 rowcount 是 0，且【不报错】——
    # 所以必须自己看 rowcount，否则删/改不存在的 id 会"成功"。
    if changed == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="任务不存在")

    row = conn.execute("SELECT * FROM todos WHERE id = ?", (id,)).fetchone()
    conn.close()

    return row_to_todo(row)
