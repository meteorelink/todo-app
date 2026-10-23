# ============================================================
#  main.py —— 接口层（HTTP 进来，数据出去）
#
#  它只负责三件事：
#    ① 接收 HTTP 请求（路径 + 方法 → 哪个函数，靠装饰器注册）
#    ② 校验请求里的数据（Pydantic 模型）
#    ③ 调用数据层读写数据库，然后把结果转成 JSON 返回
#
#  真正的 SQL 细节都在 database.py 里 —— 这就是"分层"。
# ============================================================

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import get_connection, init_db

app = FastAPI()

# ---------- CORS：允许浏览器里的前端跨域访问我 ----------
# 同源策略是【浏览器】的限制，所以"解法"只能是【服务器同意】。
# allow_origins 必须和浏览器发来的 Origin 头【精确匹配】（字符串比对，一个字符都不能差）。
# ⚠️ 生产环境只写你真实的域名，绝不能用 ["*"]。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",     # 4A 的原生版本
        "http://127.0.0.1:5173",     # 4B 的 Vite
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 应用启动时建表（表已存在则什么都不做）
init_db()


# ============================================================
#  Pydantic 模型 —— 请求体的"模具"
#
#  客户端发来的只是一段无类型的 JSON 文本。
#  这两个类负责把它校验并转换成有类型的 Python 对象。
#  校验不过 → FastAPI 自动返回 422，你一行校验代码都不用写。
# ============================================================

class TodoCreate(BaseModel):
    """新增任务时，客户端要提供的数据"""
    title: str
    # done 有默认值：新建一条任务本来就是"未完成"，允许省略。
    # （这里给默认值是安全的，因为不会覆盖任何已有数据）
    done: bool = False


class TodoUpdate(BaseModel):
    """更新任务时，客户端要提供的数据"""
    title: str
    # ⚠️ done 必填：PUT 是"整体替换"，
    #    如果有默认值，客户端不传就会把已有任务静默改成"未完成"。
    done: bool


# ============================================================
#  边界转换：数据库的一行  →  API 要返回的字典
#
#  为什么要有这个函数？因为"转换逻辑只应该有一份"。
#  以后加字段（比如 created_at），只改这一个地方。
# ============================================================

def row_to_todo(row):
    """把数据库的一行，转成 API 要返回的字典"""
    return {
        "id": row["id"],
        "title": row["title"],
        # ⚠️ 数据库存的是 0/1，API 契约是布尔值。
        #    不转的话会返回 "done": 0 —— 前端 JS 里 0 === false 是 false，会出问题。
        "done": bool(row["done"]),
    }


# ============================================================
#  接口：装饰器只是"往路由表里登记一行"
#  @app.get("/todos")  ≈  routes["GET /todos"] = read_todos
# ============================================================

@app.get("/")
def read_root():
    return {"status": "ok", "message": "待办清单后端已启动"}


@app.get("/todos")
def read_todos():
    """列出全部任务"""
    conn = get_connection()

    # 执行 SQL，fetchall() 把结果全部取出来（不取的话结果会被丢弃！）
    # ORDER BY 不能省：不写就没有顺序保证。
    rows = conn.execute("SELECT * FROM todos ORDER BY id").fetchall()

    conn.close()

    # 列表推导式：把每一行都转成字典
    return [row_to_todo(r) for r in rows]


@app.get("/todos/{id}")
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


@app.post("/todos", status_code=201)
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


@app.put("/todos/{id}")
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


@app.delete("/todos/{id}", status_code=204)
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


@app.post("/todos/{id}/toggle")
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
