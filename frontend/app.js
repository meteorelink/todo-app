
// ---------- 把一条任务变成 DOM 节点 ----------
function createTodoElement(todo) {
    const li = document.createElement("li");
    if (todo.done) {
        li.classList.add("done");        // 加 CSS 类 → 显示删除线
    }

    // 复选框：打勾
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = todo.done;

    // 任务标题
    const span = document.createElement("span");
    span.className = "title";
    span.textContent = todo.title;

    // 删除按钮
    const delBtn = document.createElement("button");
    delBtn.textContent = "删除";

    // 组装：把三个子节点塞进 li
    li.appendChild(checkbox);
    li.appendChild(span);
    li.appendChild(delBtn);

    checkbox.addEventListener("change", async () => {
        await fetch(`http://127.0.0.1:8000/todos/${todo.id}/toggle`, {
            method: "POST",
        });
        await loadTodos();
    });

    delBtn.addEventListener("click", async () => {
        await fetch(`http://127.0.0.1:8000/todos/${todo.id}`, {
            method: "DELETE",
        });
        await loadTodos();
    });

    return li;
}


// ---------- 渲染整个列表 ----------
function render(todos) {
    const list = document.querySelector("#list");
    list.innerHTML = "";                 // ① 先清空

    for (const todo of todos) {          // ② 再逐条重新创建
        list.appendChild(createTodoElement(todo));
    }
}

// ---------- 加载函数 ----------
async function loadTodos() {
    const res = await fetch("http://127.0.0.1:8000/todos");
    const todos = await res.json();
    render(todos);
}

loadTodos();

document.querySelector("#new-form").addEventListener("submit", async (event) => {
    event.preventDefault();                 // ⚠️ 不能少
    event.stopPropagation();                // ← 见下面的解释

    const input = document.querySelector("#new-title");
    const title = input.value.trim();
    if (title === "") return;               // 空内容不提交

    await fetch("http://127.0.0.1:8000/todos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },   // ⚠️ 不能少
        body: JSON.stringify({ title: title, done: false }),  // ⚠️ 不能少
    });

    input.value = "";                       // 清空输入框
    await loadTodos();                      // 重新拉数据、重绘
});