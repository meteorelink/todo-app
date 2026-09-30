from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class TodoCreate(BaseModel):
    """新增任务时，客户端要提供的数据"""
    title: str
    done: bool = False


class TodoUpdate(BaseModel):
    """更新任务时，客户端要提供的数据"""
    title: str
    done: bool

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

@app.post("/todos", status_code=201)
def create_todo(todo: TodoCreate):
    new_id = max([t["id"] for t in todos], default=0) + 1
    new_todo = {"id": new_id, "title": todo.title, "done": todo.done}
    todos.append(new_todo)
    return new_todo

@app.put("/todos/{id}")
def update_todo(id: int, todo: TodoUpdate):
    for t in todos:
        if t["id"] == id:
            t["title"] = todo.title
            t["done"] = todo.done
            return t
    raise HTTPException(status_code=404, detail="任务不存在")

@app.delete("/todos/{id}", status_code=204)
def delete_todo(id: int):
    for todo in todos:
        if todo["id"] == id:
            todos.remove(todo)
            return
    raise HTTPException(status_code=404, detail="任务不存在")

@app.post("/todos/{id}/toggle")
def toggle_todo(id: int):
    for todo in todos:
        if todo["id"] == id:
            todo["done"] = not todo["done"]
            return todo
    raise HTTPException(status_code=404, detail="任务不存在")