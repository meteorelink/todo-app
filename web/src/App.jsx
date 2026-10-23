// ============================================================
//  App.jsx —— 主组件（整个应用的"大脑"）
//
//  它负责三件事：
//    ① 持有数据（四个 state）
//    ② 和后端 API 打交道（五个函数）
//    ③ 描述整个页面长什么样（return 里的 JSX）
//
//  规则：数据往下传（props），事件往上走（传函数）—— 单向数据流。
// ============================================================

import { useState, useEffect } from "react";
import TodoList from "./TodoList";
import "./App.css";

// 后端地址定义成常量：以后换域名只改这一处
const API = "http://127.0.0.1:8000";

function App() {
    // ---------- state：组件的"记忆" ----------
    // useState(初始值) 返回 [当前值, 修改它的函数]
    // 调用修改函数 → 组件函数重新执行 → 界面自动更新
    const [todos, setTodos] = useState([]);        // 任务列表
    const [text, setText] = useState("");          // 输入框里的文字
    const [loading, setLoading] = useState(true);  // 是否正在加载
    const [error, setError] = useState(null);      // 错误信息（null = 没错）
    const [filter, setFilter] = useState("all");     // "all" | "active" | "done"

    // ===== ② 加在 state 之后、loadTodos 之前 =====
    // 派生数据：算出"该显示哪些任务"
    // 提示：用 todos.filter(...)
    //       回调里根据 filter 的值返回 true（保留）或 false（过滤掉）
    const visibleTodos = todos.filter(todo => {
        if (filter === "active") return !todo.done;   // 未完成 → 留
        if (filter === "done")   return todo.done;    // 已完成 → 留
        return true;                                   // all → 全留
    });

    // ---------- 从后端拉取全部任务 ----------
    async function loadTodos() {
        try {
            setLoading(true);
            setError(null);

            // fetch 发 GET 请求；await 等"响应头"到达
            const res = await fetch(`${API}/todos`);

            // ⚠️ fetch 遇到 404/500 不会抛异常，必须自己检查 res.ok
            if (!res.ok) {
                throw new Error(`服务器返回 ${res.status}`);
            }

            // 再 await 一次，等"响应体"读完并解析成 JS 对象
            setTodos(await res.json());
        } catch (err) {
            setError(err.message);     // 出错就记下来，稍后显示给用户
        } finally {
            setLoading(false);         // 成功失败都要结束"加载中"
        }
    }

    // ---------- 副作用：组件第一次出现时跑一次 ----------
    // useEffect(要执行的函数, 依赖数组)
    // 依赖数组写 [] = "只在挂载时跑一次"
    // ⚠️ 不写第二个参数 = 每次渲染都跑 → loadTodos → setTodos → 又渲染 → 死循环
    useEffect(() => {
        loadTodos();
    }, []);

    // ---------- 添加任务 ----------
    async function handleAdd(e) {
        e.preventDefault();            // 阻止表单默认行为（刷新页面）
        const title = text.trim();     // trim() 去掉首尾空格
        if (title === "") return;      // 空内容不提交

        // POST 请求要带三样：method / headers / body
        await fetch(`${API}/todos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // body 要的是【字符串】。JSON.stringify 把对象转成 JSON 文本
            body: JSON.stringify({ title: title, done: false }),
        });

        setText("");                   // 清空输入框（改 state，界面自动变）
        await loadTodos();             // 重新拉一遍，让列表更新
    }

    // ---------- 打勾（切换完成状态）----------
    async function toggleTodo(id) {
        await fetch(`${API}/todos/${id}/toggle`, { method: "POST" });
        await loadTodos();
    }

    // ---------- 删除 ----------
    async function deleteTodo(id) {
        await fetch(`${API}/todos/${id}`, { method: "DELETE" });
        await loadTodos();
    }

    // ---------- 描述界面 ----------
    // 注意：这里只"描述"，不"操作 DOM"。React 负责把描述变成真实界面。
    return (
        <div>
            <h1>我的待办</h1>

            <p>共 {todos.length} 条，已完成 {todos.filter(t => t.done).length} 条</p>

            {/* onSubmit：表单提交时调用 handleAdd */}
            <form onSubmit={handleAdd}>
                {/* 受控组件：value 由 state 决定，onChange 时更新 state */}
                <input
                    value={text}
                    onChange={e => setText(e.target.value)}
                    placeholder="要做什么？"
                />
                <button type="submit">添加</button>
            </form>

            {/* ===== ③ 筛选按钮 =====
                位置：form 之后、任务列表之前 —— 因为它们控制"显示哪些任务"。
                样式规则在 App.css 里：.filters 和 .filters button.active
            */}
            <div className="filters">
                <button
                    className={filter === "all" ? "active" : ""}
                    onClick={() => setFilter("all")}
                >
                    全部
                </button>
                <button
                    className={filter === "active" ? "active" : ""}
                    onClick={() => setFilter("active")}
                >
                    未完成
                </button>
                <button
                    className={filter === "done" ? "active" : ""}
                    onClick={() => setFilter("done")}
                >
                    已完成
                </button>
            </div>

            {/* {条件 && JSX} —— 短路写法：条件为真才渲染 */}
            {loading && <p>加载中……</p>}
            {error && <p style={{ color: "red" }}>出错了：{error}</p>}

            {/* 只有"不在加载中 且 没出错"时才显示列表 */}
            {/* ⚠️ ④ 待填空：下面 TodoList 的 todos={todos} 该换成哪个变量？
                    提示：用你上面算出来的那个"派生数据"。
                    ⚠️ 但请先把 ② 的 filter 逻辑填完再改这里 ——
                       否则 visibleTodos 是空数组，列表会整个变空。
            */}
            {!loading && !error && (
                <TodoList
                    todos={visibleTodos}              // 数据往下传
                    onToggle={toggleTodo}      // 函数往下传（子组件用它"请求"修改）
                    onDelete={deleteTodo}
                />
            )}
        </div>
    );
}

// ⚠️ 必须导出，否则 main.jsx 里 import 不到
export default App;
