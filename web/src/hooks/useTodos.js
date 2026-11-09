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
    // ⭐ 注意 addTodo 的参数：收的是【数据】（字符串 + 可选日期），不是事件对象 e。
    //    为什么？
    //      · "什么算合法标题"（trim、防空）是【界面】的判断
    //      · "怎么把标题发给后端"是【数据】的事
    //    分开了，这个 Hook 才能被别的地方复用 ——
    //    AI 拆解出的任务产出的也是这个形状，直接调 addTodo 就行，
    //    完全不需要一个 <form> 或一个事件对象。
    //
    // ⭐ due 是可选参数（不传就是 undefined → 存 null = 没有截止日）。
    //    为什么要给默认值？因为绝大多数调用方只关心标题 ——
    //    让"不需要日期"的情况写起来跟以前一模一样，是一次向后兼容。
    async function addTodo(title, due = null) {
        // POST 请求要带三样：method / headers / body
        await fetch(`${API}/todos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            // body 要的是【字符串】。JSON.stringify 把对象转成 JSON 文本
            //
            // ⚠️ due 用 `due || null` 而不是直接传 due：
            //    <input type="date"> 没填的时候值是【空字符串 ""】，
            //    直接发过去后端会当成"有个空的日期"→ 422。
            //    空字符串在布尔判断里是 false，所以 `|| null` 把它变成"没有"。
            body: JSON.stringify({ title: title, done: false, due: due || null }),
        });
        await reload();                // 重新拉一遍，让列表更新
    }

    // ---------- 批量创建（AI 草稿"确认"之后走这条） ----------
    //
    // ⭐ 为什么参数是【数组】，而不是在 App 里循环调用 addTodo？
    //
    //   因为"用户确认了一次"是**一个**动作。
    //   如果循环调 addTodo，就变成 N 个请求：
    //   第 2 条失败时，第 1 条已经进库了 → 界面上出现"半成功"——
    //   而这正是上次讨论批量接口时说要避免的第三种状态。
    //   后端 /todos/batch 用一次事务保证"要么全进，要么全不进"，
    //   前端也必须用一次请求去配合它。
    async function addMany(tasks) {
        const res = await fetch(`${API}/todos/batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tasks: tasks }),
        });
        if (!res.ok) {
            throw new Error(`批量创建失败：服务器返回 ${res.status}`);
        }
        await reload();
    }

    async function toggleTodo(id) {
        await fetch(`${API}/todos/${id}/toggle`, { method: "POST" });
        await reload();
    }

    async function deleteTodo(id) {
        const res = await fetch(`${API}/todos/${id}`, { method: "DELETE" });

        // ⭐ 404 要当成成功。
        //    404 的意思是"这条已经没了"，而我们的目的就是"让它没了" ——
        //    目的已经达到了。把它当失败，会让用户盯着一句
        //    "任务不存在"发呆："可它刚刚还在我眼前啊。"
        //    （这叫幂等：调用一次和调用三次，结果一样。）
        if (!res.ok && res.status !== 404) {
            throw new Error(`删除失败：服务器返回 ${res.status}`);
        }

        await reload();
    }

    // ---------- 把"外界需要的东西"交出去 ----------
    // 就像函数的返回值：调用方只拿到这些，不需要知道里面怎么实现的
    return {
        todos,
        loading,
        error,
        addTodo,
        addMany,       // 批量创建（AI 草稿确认后用它）
        toggleTodo,
        deleteTodo,
        reload,        // 暴露出来，以后想做"出错后点重试"直接用它
    };
}
