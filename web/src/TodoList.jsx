// ============================================================
//  TodoList.jsx —— 列表容器
//
//  它自己不持有数据，只做两件事：
//    ① 把 todos 数组"翻译"成一组 <TodoItem>
//    ② 把 onToggle / onDelete 继续往下传
//
//  这种"只转手"的组件叫「展示型组件」。
// ============================================================

import TodoItem from "./TodoItem";

// { todos, onToggle, onDelete } 是"解构 props"
// 等价于接收一个 props 对象，然后写 props.todos / props.onToggle ...
function TodoList({ todos, onToggle, onDelete }) {
    // 空列表时提前返回，显示提示
    if (todos.length === 0) {
        return <p>还没有任务</p>;
    }

    return (
        <ul>
            {/*
              todos.map(元素 => JSX)
              —— 把数组里每个元素"变成"一个 JSX，组成一个新数组

              key={todo.id} 不能少：
                React 靠它识别"这一项还是刚才那一项"，
                从而只更新变化的部分，而不是整个重建。

              用 id 而不是数组下标：列表会增删，下标会变，id 不会。
            */}
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
