// ============================================================
//  App.jsx —— 主组件（现在只管"界面"）
//
//  它现在只做三件事：
//    ① 从 useTodos 拿数据
//    ② 管理【纯界面】状态（输入框文字、当前筛选）
//    ③ 描述整个页面长什么样
//
//  和后端的全部往来，都在 hooks/useTodos.js 里。
//
//  ⭐ 对比重构前：166 行 → 现在约 120 行，而且少了 5 个 fetch。
//     但真正的收益不是"行数变少"，是"职责变清楚"：
//     想改接口地址？改 useTodos.js。
//     想改界面？改这里。
// ============================================================

import { useState } from "react";
import TodoList from "./TodoList";
import { useTodos } from "./hooks/useTodos";
import "./App.css";

function App() {
    // ---------- 数据：全部来自自定义 Hook ----------
    // 一行拿到五样东西，不需要知道它们是怎么来的
    const { todos, loading, error, addTodo, toggleTodo, deleteTodo } = useTodos();

    // ---------- 纯界面状态：留在组件里 ----------
    // 为什么这两个不放 hook？
    //   因为它们只和"这个界面"有关，别的界面未必需要。
    //   Hook 只管"任务的增删改查"，不管"用户现在打了几个字"。
    const [text, setText] = useState("");            // 输入框里的文字
    const [filter, setFilter] = useState("all");     // "all" | "active" | "done"

    // ---------- 派生数据：从 todos + filter 算出来 ----------
    // ⚠️ 它不是 state —— 每次渲染时重新算，所以永远和 todos 一致
    const visibleTodos = todos.filter(todo => {
        if (filter === "active") return !todo.done;   // 未完成 → 留
        if (filter === "done")   return todo.done;    // 已完成 → 留
        return true;                                   // all → 全留
    });

    // ---------- 添加：这里只处理"界面"那部分 ----------
    // 阻止表单刷新、去掉首尾空格、清空输入框 —— 这些都是界面的事。
    // 真正"发给后端"的那一步，已经交给 addTodo 了。
    async function handleAdd(e) {
        e.preventDefault();            // 阻止表单默认行为（刷新页面）
        const title = text.trim();     // trim() 去掉首尾空格
        if (title === "") return;      // 空内容不提交

        await addTodo(title);          // ← ⭐ 交接点：界面 → 数据
        setText("");                   // 清空输入框（改 state，界面自动变）
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

            {/* ===== 筛选按钮 =====
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
            {!loading && !error && (
                <TodoList
                    todos={visibleTodos}       // 数据往下传（筛选后的）
                    onToggle={toggleTodo}      // 函数往下传（子组件用它"请求"修改）
                    onDelete={deleteTodo}
                />
            )}
        </div>
    );
}

// ⚠️ 必须导出，否则 main.jsx 里 import 不到
export default App;
