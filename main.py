from fastapi import FastAPI, HTTPException

app = FastAPI()

# 假数据：写死在代码里的任务列表
todos = [
    {"id": 1, "title": "写实验报告", "done": False},
    {"id": 2, "title": "复习数据结构", "done": True},
    {"id": 3, "title": "跑步 30 分钟", "done": False},
]


@app.get("/")
def read_root():
    return {"status": "ok", "message": "待办清单后端已启动"}


@app.get("/todos")
def read_todos():
    return todos

@app.get("/todos/{id}")
def read_one_todo(id: int):
    for todo in todos:
        if todo["id"] == id:
            return todo
    raise HTTPException(status_code=404, detail="任务不存在")