import TodoItem from "./TodoItem";

function TodoList({ todos, onToggle, onDelete }) {
    if (todos.length === 0) {
        return <p>还没有任务</p>;
    }

    return (
        <ul>
            {todos.map(todo => (
                <TodoItem
                    key={todo.id}
                    todo={todo}
                    onToggle={onToggle}
                    onDelete={onDelete}
                />
            ))}
        </ul>
    );
}

export default TodoList;