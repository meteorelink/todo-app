// ============================================================
//  TodoItem.jsx —— 一条任务
//
//  接收四个 props：
//    todo      —— 这条任务的数据 { id, title, done, due, priority }
//    onToggle  —— 父组件给的函数，调用它表示"我想切换完成状态"
//    onDelete  —— 同上，表示"我想删除"
//    onEdit    —— 同上，表示"我想编辑"（目前还没做，先留着）
//
//  ⚠️ props 是只读的。这里不能直接改 todo，只能调用父组件的函数。
// ============================================================

/**
 * 返回今天的日期，格式 "YYYY-MM-DD"
 *
 * ⚠️ 为什么不直接用 new Date(todo.due) 来比较？
 *
 *   JS 的 Date 构造函数遇到【只有日期】的字符串（"2026-11-06"），
 *   会按 UTC 零点来解析 —— 在东八区它其实是 11 月 6 日早上 8 点。
 *   再拿去和"今天本地时间零点"比较，就会差一天。
 *   这种 bug 在晚上 8 点以后测不出来，在早上 8 点以前才显形。
 *
 *   而 "2026-11-06" 这种 ISO 格式，字典序恰好就是时间序：
 *       "2026-11-06" < "2026-11-07"  →  true
 *   所以直接比字符串，最简单也最不会错。
 */
function todayISO() {
    const d = new Date();
    // padStart(2, "0")：把 9 变成 "09"，保证月份和日期都是两位
    const pad = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function TodoItem({ todo, onToggle, onDelete }) {
    // 逾期 = 有截止日期 且 还没完成 且 截止日早于今天
    const overdue = todo.due && !todo.done && todo.due < todayISO();

    return (
        // className 用三元表达式：
        //   todo.done 为真 → "done"，否则 → ""
        // 这就是"描述"：done 是什么，class 就是什么。
        // （对比 4A 的 li.classList.add("done") —— 那是在"下命令"）
        <li className={todo.done ? "done" : ""}>
            <input
                type="checkbox"
                checked={todo.done}
                // ⚠️ 必须包一层箭头函数！
                //    onChange={() => onToggle(todo.id)}  → 事件触发时才调用
                //    onChange={onToggle(todo.id)}        → 渲染时就立即调用 ❌
                onChange={() => onToggle(todo.id)}
            />

            {/* 高优先级才显示徽章 —— normal 是绝大多数，天天挂个标签反而是噪音 */}
            {todo.priority === "high" && (
                <span className="pri pri-high">高</span>
            )}

            <span className="title">{todo.title}</span>

            {/* 没有截止日期时，整个 <span> 都不渲染（不是显示一个空的） */}
            {todo.due && (
                <span className={`due${overdue ? " overdue" : ""}`}>
                    {overdue ? "已逾期 " : ""}
                    {todo.due}
                </span>
            )}

            <button onClick={() => onDelete(todo.id)}>删除</button>
        </li>
    );
}

export default TodoItem;
