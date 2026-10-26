# ============================================================
#  main.py —— 应用入口（只做"装配"）
#
#  它现在只做四件事：
#    ① 创建 app
#    ② 配置中间件（CORS）
#    ③ 建表
#    ④ 把各个 router 挂上去
#
#  具体的接口逻辑  → routers/todos.py
#  数据模型        → models.py
#  数据库细节      → database.py
#
#  ⭐ 这就是"分层"：每个文件只关心一件事。
# ============================================================

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import todos

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


# ⭐ 把 todos 这个接口组挂到 app 上。
#    等价于把 routers/todos.py 里所有 @router.get(...) 变成 @app.get(...)。
#    以后加"用户"接口，就再写一行 app.include_router(users.router)，
#    main.py 一个字都不用改结构。
app.include_router(todos.router)


@app.get("/")
def read_root():
    return {"status": "ok", "message": "待办清单后端已启动"}
