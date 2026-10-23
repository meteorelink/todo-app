// ============================================================
//  TodoItem.jsx —— 一条任务
//
//  接收三个 props：
//    todo      —— 这条任务的数据 { id, title, done }
//    onToggle  —— 父组件给的函数，调用它表示"我想切换完成状态"
//    onDelete  —— 同上，表示"我想删除"
//
//  ⚠️ props 是只读的。这里不能直接改 todo，只能调用父组件的函数。
// ============================================================

function TodoItem({ todo, onToggle, onDelete }) {
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
            <span className="title">{todo.title}</span>
            <button onClick={() => onDelete(todo.id)}>删除</button>
        </li>
    );
}

export default TodoItem;
