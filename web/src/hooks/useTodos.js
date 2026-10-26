// ============================================================
//  hooks/useTodos.js —— 自定义 Hook：所有"任务数据"的逻辑
//
//  它把三样东西从 App.jsx 里搬了出来：
//    ① 和后端打交道（所有 fetch 都在这里）
//    ② 数据状态（todos / loading / error）
//    ③ 什么时候加载（useEffect）
//
//  ⭐ 自定义 Hook 的规则只有两条：
//     1. 函数名必须以 use 开头 —— 这样 React 和 linter 才知道它是 Hook
//     2. 里面可以调用其他 Hook（useState / useEffect 都行）
//
//  ⭐ 这个 Hook【完全不知道】界面的事：
//     不知道有输入框、不知道有筛选按钮、不知道有 <li>。
//     它只认"任务的增删改查"这一件事。
// ============================================================

import { useEffect, useState } from "react";

// 后端地址：以后换域名只改这一处
const API = "http://127.0.0.1:8000";

export function useTodos() {
    // ---------- 数据状态 ----------
    const [todos, setTodos] = useState([]);        // 任务列表
    const [loading, setLoading] = useState(true);  // 是否正在加载
    const [error, setError] = useState(null);      // 错误信息（null = 没错）

    // ---------- 从后端拉取全部任务 ----------
    async function reload() {
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
            setError(err.message);     // 出错就记下来，界面会显示它
        } finally {
            setLoading(false);         // 成功失败都要结束"加载中"
        }
    }

    // ---------- 副作用：组件第一次出现时跑一次 ----------
    // 依赖数组写 [] = "只在挂载时跑一次"
    // ⚠️ 不写第二个参数 = 每次渲染都跑 → reload → setTodos → 又渲染 → 死循环
    useEffect(() => {
        reload();
    }, []);

    // ---------- 增 / 改 / 删 ----------
    //
    // ⭐ 注意 addTodo 的参数：收的是【字符串 title】，不是事件对象 e。
    //    为什么？
    //      · "什么算合法标题"（trim、防空）是【界面】的判断
    //      · "怎么把标题发给后端"是【数据】的事
    //    分开了，这个 Hook 才能被别的地方复用 ——
    //    比如以后加"AI 自动拆解任务"，它产出的也是字符串，直接调 addTodo 就行，
    //    完全不需要一个 <form> 或一个事件对象。
    async function addTodo(title) {
        // POST 请求要带三样：method / headers / body
        await fetch(`${API}/todos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // body 要的是【字符串】。JSON.stringify 把对象转成 JSON 文本
            body: JSON.stringify({ title: title, done: false }),
        });
        await reload();                // 重新拉一遍，让列表更新
    }

    async function toggleTodo(id) {
        await fetch(`${API}/todos/${id}/toggle`, { method: "POST" });
        await reload();
    }

    async function deleteTodo(id) {
        await fetch(`${API}/todos/${id}`, { method: "DELETE" });
        await reload();
    }

    // ---------- 把"外界需要的东西"交出去 ----------
    // 就像函数的返回值：调用方只拿到这些，不需要知道里面怎么实现的
    return {
        todos,
        loading,
        error,
        addTodo,
        toggleTodo,
        deleteTodo,
        reload,        // 暴露出来，以后想做"出错后点重试"直接用它
    };
}
