import { useState, useEffect } from "react";
import TodoList from "./TodoList";
import "./App.css";

const API = "http://127.0.0.1:8000";

function App() {
    const [todos, setTodos] = useState([]);
    const [text, setText] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    async function loadTodos() {
        try {
            setLoading(true);
            setError(null);

            const res = await fetch(`${API}/todos`);
            if (!res.ok) {
                throw new Error(`服务器返回 ${res.status}`);
            }
            setTodos(await res.json());
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        loadTodos();
    }, []);

    async function handleAdd(e) {
        e.preventDefault();
        const title = text.trim();
        if (title === "") return;

        await fetch(`${API}/todos`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: title, done: false }),
        });

        setText("");
        await loadTodos();
    }

    async function toggleTodo(id) {
        await fetch(`${API}/todos/${id}/toggle`, { method: "POST" });
        await loadTodos();
    }

    async function deleteTodo(id) {
        await fetch(`${API}/todos/${id}`, { method: "DELETE" });
        await loadTodos();
    }

    return (
        <div>
            <h1>我的待办</h1>

            <form onSubmit={handleAdd}>
                <input
                    value={text}
                    onChange={e => setText(e.target.value)}
                    placeholder="要做什么？"
                />
                <button type="submit">添加</button>
            </form>

            {loading && <p>加载中……</p>}
            {error && <p style={{ color: "red" }}>出错了：{error}</p>}
            {!loading && !error && (
                <TodoList
                    todos={todos}
                    onToggle={toggleTodo}
                    onDelete={deleteTodo}
                />
            )}
        </div>
    );
}

export default App;