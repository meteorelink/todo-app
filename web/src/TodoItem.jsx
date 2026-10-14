function TodoItem({ todo, onToggle, onDelete }) {
    return (
        <li className={todo.done ? "done" : ""}>
            <input
                type="checkbox"
                checked={todo.done}
                onChange={() => onToggle(todo.id)}       // ← readOnly 去掉了
            />
            <span className="title">{todo.title}</span>
            <button onClick={() => onDelete(todo.id)}>删除</button>
        </li>
    );
}

export default TodoItem;