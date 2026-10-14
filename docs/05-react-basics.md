# React 基础：从「操作界面」到「描述界面」

> **适用阶段**：阶段 4B（React 重写）前置阅读
> **为什么放在这里**：React 的心智模型和你之前学的一切都不同。**先建立模型，再动手写代码。**
> **阅读方式**：不用背 API。**重点是第 2 节「UI = f(state)」、第 6 节「state」和第 11 节那张对照表。**

---

## 目录

1. [回到痛点：4A 是怎么做的](#一回到痛点4a-是怎么做的)
2. [**核心思想：UI = f(state)**](#二核心思想ui--fstate)
3. [组件：把界面切成积木](#三组件把界面切成积木)
4. [JSX：在 JavaScript 里写界面](#四jsx在-javascript-里写界面)
5. [props：父组件给子组件传数据](#五props父组件给子组件传数据)
6. [**state：组件的"记忆"**](#六state组件的记忆)
7. [useEffect：副作用](#七useeffect副作用)
8. [渲染列表：`.map()` 和 `key`](#八渲染列表map-和-key)
9. [事件处理](#九事件处理写法变了但概念没变)
10. [Vite 与构建工具](#十vite-是什么为什么需要它)
11. [**对照表：你的 4A 代码 → React 写法**](#十一--一张对照表你的-4a-代码--react-写法)
12. [速查表](#十二速查表)
13. [自测问题](#十三自测问题)

---

## 一、回到痛点：4A 是怎么做的

**4A 里你的代码（简化）：**

```javascript
function render(todos) {
    const list = document.querySelector("#list");
    list.innerHTML = "";                          // ① 清空整棵子树
    for (const todo of todos) {
        list.appendChild(createTodoElement(todo)); // ② 从零重建
    }
}

checkbox.addEventListener("change", async () => {
    await fetch(`.../toggle`, { method: "POST" });
    await loadTodos();                            // ③ 全量重拉 + 全量重绘
});
```

**四个痛：**

| # | 痛 | 说明 |
|---|---|---|
| ① | **全量重建** | 只有一条任务变了，整个列表被删掉重建 |
| ② | **两份状态** | `todos` 数组 和 真实 DOM，必须手动保持一致 |
| ③ | **没有局部更新** | 只能整体重建，做不到"只更新那一项" |
| ④ | **职责混杂** | `createTodoElement` 里既有结构、又有样式类、又有事件绑定 |

**记住这四条。React 的每一个设计都在回应它们。**

---

## 二、核心思想：`UI = f(state)`

**这是整个 React 的唯一核心。理解这一句，其余都是它的推论。**

### 命令式（4A）vs 声明式（React）

| | 命令式（4A） | **声明式（React）** |
|---|---|---|
| 你写什么 | "**怎么做**"：找到节点、改文字、加类、删节点 | "**要什么**"：界面应该长成这样 |
| 谁负责更新界面 | **你自己** | **React** |

### ⭐ 这是你第三次遇到这个对比

| 领域 | 命令式 | 声明式 |
|---|---|---|
| 数据库 | 自己写循环遍历找数据 | `SELECT ... WHERE id = ?` |
| CSS | —— | `.done { text-decoration: line-through; }` |
| **界面** | **4A：手动创建/修改 DOM** | **4B：描述界面应该长什么样** |
| 排序 | 手写快排 | `qsort()` / `sorted()` |

**同一个思想，换了三个领域出现。**

### 精确表述

> **界面 = 一个函数，输入是数据（state），输出是"界面长什么样"。**
>
> **数据变了 → 函数重新跑一遍 → 得到新的界面描述 → React 把变化应用到真实 DOM。**

**这就是 `UI = f(state)`。**

---

## 三、组件：把界面切成积木

**组件就是一个「返回界面描述」的函数。**

```jsx
function TodoItem() {
    return <li>写实验报告</li>;
}
```

| 规则 | 说明 |
|---|---|
| **函数名首字母必须大写** | `TodoItem` ✅ / `todoItem` ❌（小写会被当成 HTML 标签） |
| **返回"界面描述"** | 看起来像 HTML，其实是 JSX（见下） |
| 可以像标签一样使用 | `<TodoItem />` |

**组件可以嵌套，形成一棵「组件树」：**

```
App
├── TodoInput        （输入框 + 添加按钮）
└── TodoList         （列表容器）
    ├── TodoItem     （一条任务）
    ├── TodoItem
    └── TodoItem
```

> **对照 4A**：你只有一个大函数 `createTodoElement` 在造整条 `li`。
> **React 把"界面"也拆成可复用的积木。**

---

## 四、JSX：在 JavaScript 里写界面

```jsx
function TodoItem({ todo }) {
    return (
        <li className="todo">
            <span>{todo.title}</span>
            <button>删除</button>
        </li>
    );
}
```

**看起来像 HTML，但它不是 HTML** —— 它是 JS 的语法扩展，**会被编译成 JavaScript**。

### 和 HTML 的四个区别

| # | HTML | JSX | 原因 |
|---|---|---|---|
| 1 | `class="..."` | **`className="..."`** | `class` 是 JS 保留字 |
| 2 | `onclick` | **`onClick`** | JSX 用驼峰命名 |
| 3 | 不能嵌 JS | **`{todo.title}`** | `{}` 里可以放任意 JS 表达式 |
| 4 | 可以有多个根元素 | **必须有一个根元素** | 可以包一层 `<></>`（Fragment） |

### ⭐⭐ 必须建立的认知：JSX 返回的**不是 DOM**

```jsx
const element = <li>写实验报告</li>;
```

**`element` 不是真实的 DOM 节点**，它只是一个**普通的 JavaScript 对象** —— 描述"这里应该有一个 `li`，内容是'写实验报告'"。

**React 拿到这个对象，自己决定怎么把它变成真实 DOM、怎么更新。**

> **这就是"声明式"能成立的前提**：
> **你的组件函数不碰真实 DOM，它只产出"描述"。真实 DOM 完全归 React 管。**
>
> **对照 4A**：`document.createElement("li")` 造出来的是**真家伙**，改它就是改界面。
> **React 里你造的是"图纸"，施工是 React 的事。**

### `{}` 里能放什么

```jsx
{todo.title}                      // 变量
{todo.done ? "已完成" : "未完成"}  // 三元表达式
{todos.length}                    // 任意表达式
{todos.map(t => <Item />)}        // 返回 JSX 的表达式
{todo.done && <span>✓</span>}     // 短路：为真才渲染
```

**不能放**：`if` 语句、`for` 循环（**语句**不能放，**表达式**可以）。
**条件用三元或 `&&`；循环用 `.map()`。**

---

## 五、props：父组件给子组件传数据

**"props" = properties，就是**函数的参数**。**

```jsx
function TodoItem({ todo, onDelete }) {          // ← 解构 props
    return (
        <li>
            <span>{todo.title}</span>
            <button onClick={() => onDelete(todo.id)}>删除</button>
        </li>
    );
}
```

**父组件里这样用：**

```jsx
<TodoItem todo={item} onDelete={handleDelete} />
```

### ⭐ props 是**只读**的

```jsx
function TodoItem({ todo }) {
    todo.title = "改一下";      // ❌ 绝对不要这么做
}
```

**为什么？** 因为数据是**父组件的**。**要改，就得让父组件改。**

**所以父组件会给子组件传一个「函数」** —— 上面例子里的 `onDelete`。子组件想删除时，**调用这个函数，让父组件去改**。

### ⭐ 单向数据流

```
        App（持有数据）
         │
    props ↓ （往下传数据）
         │
      TodoItem
         │
    ↑ 调用父组件传下来的函数（往上传"请求"）
```

**数据永远往下流，事件永远往上走。** 这让程序**可预测** —— 界面出错时，顺着树往上找"谁的数据错了"就行。

> **对照 4A**：你的 `createTodoElement(todo)` 也是"把数据传进去"，但那个函数**直接操作了 DOM**。
> **React 里组件只"描述"** —— 想改数据，得**请求父组件**。

---

## 六、`state`：组件的"记忆"

**这是 React 最重要的概念，也是初学者最懵的地方。**

### 先说"为什么需要它"

**组件是函数。函数执行完，里面的局部变量就没了。**

```jsx
function Counter() {
    let count = 0;                    // ← 每次渲染都重新变成 0
    return <button onClick={() => count++}>{count}</button>;
}
```

**点按钮，`count` 变了，但界面不动。** 因为：

1. `count` 是局部变量，**改了 React 不知道**
2. 就算 React 知道了，**重新渲染时这一行又会把它重置成 0**

### `useState` 解决这两个问题

```jsx
import { useState } from "react";

function Counter() {
    const [count, setCount] = useState(0);
    //     ↑ 当前值   ↑ 修改它的函数     ↑ 初始值

    return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

| | 作用 |
|---|---|
| `count` | **当前值**（跨渲染保留） |
| `setCount` | **修改它的函数** —— **调用它会触发重新渲染** |

### ⭐⭐ 关键：state 变化会触发「重新渲染」

```
setCount(count + 1) 被调用
        │
        ▼
React 重新执行 Counter() 这个函数
        │
        ▼
得到一份新的界面描述（这次 count 是 1）
        │
        ▼
React 把新的描述和上一次对比，只更新变化的地方
        │
        ▼
屏幕上显示 1
```

> ⭐ **"重新渲染" = React 把你的组件函数重新调用一遍。**
> **这一点想通了，React 就通了一半。**

### ⚠️ 所以：**绝对不能直接改 state**

```jsx
todos.push(newTodo);            // ❌ React 不知道变了，界面不会更新
setTodos([...todos, newTodo]);  // ✅ 传一个【新数组】给 setter
```

**为什么？** 因为 React 判断"变没变"靠的是**比较引用**：

```javascript
const a = [1, 2];
a.push(3);           // a 还是那个数组对象（引用没变）
```

**所以你必须造一个**新的**数组/对象**（`[...todos, newTodo]`）。

> 💡 **`[...todos, newTodo]` 读作**："把 `todos` 里的东西全展开，再加上 `newTodo`，组成一个新数组。"

### state 的"初始值"只在第一次用

```jsx
const [todos, setTodos] = useState([]);   // 这个 [] 只在组件第一次出现时用一次
```

**之后每次渲染，`useState` 都返回当前的值**，不会重新初始化。**这正是它和普通变量的根本区别。**

### 用函数式更新避免"过期值"

```jsx
setCount(count + 1);            // 直接基于当前值算
setCount(prev => prev + 1);     // ✅ 基于"最新的值"算（推荐）
```

**连续调用两次时，第一种会出问题**（两次都用同一个旧 `count`）—— 和你在阶段 3 学的「丢失更新」是同一类问题。

---

## 七、`useEffect`：副作用

**组件函数的职责只有一件：根据数据描述界面。**

**但有些事情不是"描述界面"：**

| 不是渲染的事 |
|---|
| 从服务器拉数据 |
| 设置定时器 |
| 订阅事件 |
| 手动操作 DOM |

**这些叫「副作用」（side effect），要放进 `useEffect`。**

```jsx
import { useEffect, useState } from "react";

function App() {
    const [todos, setTodos] = useState([]);

    useEffect(() => {
        loadTodos();               // ← 拉数据
    }, []);                        // ← 空数组：只在组件第一次出现时跑一次

    // ...
}
```

### ⭐ 这就是 4A 里 `loadTodos()` 的 React 版本

| 4A | 4B |
|---|---|
| 文件末尾写 `loadTodos();` | `useEffect(() => { loadTodos(); }, [])` |

**为什么不能直接在函数体里调？**

因为组件函数**会被反复执行**（每次 state 变化都跑一遍）→ **`loadTodos()` 会被调用无数次** → 无限请求循环。

**`[]` 空数组 = "只跑一次"。**

> 第二个参数叫**依赖数组**：写什么，就是"当这些值变化时才重新执行"。
> `[]` = 永远不重新执行（只在"挂载"时一次）。
> **不写第二个参数 = 每次渲染都执行** ← 这会导致无限循环，是经典新手 bug。

---

## 八、渲染列表：`.map()` 和 `key`

**4A 版本：**

```javascript
for (const todo of todos) {
    list.appendChild(createTodoElement(todo));
}
```

**React 版本：**

```jsx
<ul>
    {todos.map(todo => (
        <TodoItem key={todo.id} todo={todo} />
    ))}
</ul>
```

**`{}` 里可以放表达式** —— `todos.map(...)` 会把数组变成**一组 JSX 元素**。

### ⚠️ `key` 是必须的

| 没有 key | 有 key |
|---|---|
| React 不知道哪一项对应哪一项 | React 精确知道谁是谁 |
| 可能重建整个列表，**丢失输入框焦点、动画状态** | 只更新真正变化的那一项 |

**⚠️ 用 `id` 当 key，不要用数组下标 `index`。**

因为列表会增删重排 —— **下标会变，而 id 不会**。用 index 会出现"删除第 2 项，第 3 项的输入内容跑到第 2 项上"这类诡异 bug。

> **⭐ 这就是 4A 里 `render()` 那个"清空 + 重建"问题的正解** ——
> **`key` 让 React 能做「最小更新」而不是「全量重建」。**

---

## 九、事件处理：写法变了，但概念没变

**4A：**

```javascript
checkbox.addEventListener("change", () => { ... });
```

**4B：**

```jsx
<input type="checkbox" onChange={() => onToggle(todo.id)} />
```

**不需要 `addEventListener`** —— 直接写在 JSX 上。

### ⚠️ 一个必踩的坑

```jsx
<button onClick={handleDelete}>删除</button>       // ✅ 把函数交给 React
<button onClick={handleDelete()}>删除</button>     // ❌ 立即执行！并在渲染时执行
```

**`{handleDelete}` 是"把这个函数交给 React，需要时它来调"。**
**`{handleDelete()}` 是"现在立刻调用它，把返回值交给 React"。**

> **这和你理解的"注册回调"是同一个模型** —— 只是写法从 `addEventListener(名, 函数)` 变成了 `on事件={函数}`。
> **概念没变，语法缩短了。**

### 表单还是要 `preventDefault`，而且输入框由 state 管

```jsx
function TodoInput({ onAdd }) {
    const [text, setText] = useState("");

    function handleSubmit(e) {
        e.preventDefault();                    // ← 还是要
        if (text.trim() === "") return;
        onAdd(text.trim());
        setText("");                           // ← 清空输入框，也是靠 state
    }

    return (
        <form onSubmit={handleSubmit}>
            <input value={text} onChange={e => setText(e.target.value)} />
            <button type="submit">添加</button>
        </form>
    );
}
```

> 💡 注意 `value={text}` + `onChange` —— 这叫**受控组件**。
> **输入框的值也由 state 管理**，而不是像 4A 那样用 `input.value = ""` 手动清空。
> **"一切状态都归 React 管"** —— 这是 React 的一致性原则。

---

## 十、Vite 是什么，为什么需要它

**JSX 浏览器不认识。** 你需要一个工具把它编译成普通 JavaScript。

**Vite（读作 "veet"，法语"快"）就干这个**，顺便提供：

| 功能 | 说明 |
|---|---|
| **编译** | 把 JSX、新语法转成浏览器能懂的 JS |
| **开发服务器** | 跑在 **5173** 端口，提供页面 |
| **热更新（HMR）** | 改代码，浏览器**不刷新**就自动更新 |
| **打包** | 部署时把所有文件打包压缩 |

> **对照 4A**：你用 `python -m http.server`（纯静态服务，不做任何编译）。
> **4B 的 `npm run dev` 边编译边服务。** 这就是前端"构建工具"存在的理由。

**用 Vite 创建项目的命令：**

```powershell
npm create vite@latest web -- --template react
```

> `web` 是项目目录名。`--template react` 表示"用 React 模板（纯 JavaScript，不用 TypeScript）"。

---

## 十一、⭐ 一张对照表：你的 4A 代码 → React 写法

**这张表是 4B 的路线图。收藏它。**

| 你想做的事 | 4A（原生 JS） | **4B（React）** |
|---|---|---|
| **定义界面** | `document.createElement("li")` | **直接写 `<li>...</li>`** |
| 设置文字 | `el.textContent = todo.title` | **`{todo.title}`** |
| 加样式类 | `el.classList.add("done")` | **`className={todo.done ? "done" : ""}`** |
| 条件显示 | `if (todo.done) { ... }` | **`{todo.done && <span>✓</span>}`** |
| **渲染列表** | `for (...) appendChild(...)` | **`todos.map(t => <Item key={t.id} />)`** |
| **更新界面** | **`render()` 清空 + 重建** | **不需要写！改 state 就行** |
| 保存数据 | `let todos = [...]` | **`const [todos, setTodos] = useState([])`** |
| 改数据 | `todos.push(x)` | **`setTodos([...todos, x])`** |
| 绑定事件 | `el.addEventListener("click", fn)` | **`onClick={fn}`** |
| 清空输入框 | `input.value = ""` | **`setText("")`** + `value={text}` |
| 页面加载时拉数据 | 文件末尾写 `loadTodos()` | **`useEffect(() => loadTodos(), [])`** |
| 保持数据和界面一致 | **手动同步（你的痛）** | **React 自动做** |
| 局部更新一项 | **做不到，只能全量重建** | **靠 `key` 自动最小更新** |

**这张表里每一行的右边，都是对左边那个"痛"的回答。**

---

## 十二、速查表

### 三个最常用的 Hook

```jsx
import { useState, useEffect } from "react";

// 状态
const [todos, setTodos] = useState([]);

// 副作用（拉数据）：只在挂载时跑一次
useEffect(() => {
    loadTodos();
}, []);
```

### 组件的骨架

```jsx
function TodoItem({ todo, onToggle, onDelete }) {
    return (
        <li className={todo.done ? "done" : ""}>
            <input
                type="checkbox"
                checked={todo.done}
                onChange={() => onToggle(todo.id)}
            />
            <span className="title">{todo.title}</span>
            <button onClick={() => onDelete(todo.id)}>删除</button>
        </li>
    );
}

export default TodoItem;
```

### 渲染列表

```jsx
{todos.map(todo => (
    <TodoItem key={todo.id} todo={todo} />
))}
```

### 条件渲染

```jsx
{todos.length === 0 && <p>还没有任务</p>}
{todo.done ? "已完成" : "未完成"}
```

### 改 state 的正确姿势

```jsx
setTodos([...todos, newTodo]);                       // 追加
setTodos(todos.filter(t => t.id !== id));            // 删除
setTodos(todos.map(t => t.id === id ? {...t, done: !t.done} : t));  // 改一项
```

> `{...t, done: !t.done}` 读作："把 `t` 的所有字段展开，然后用新的 `done` 覆盖。"
> **又是"造一个新对象"，不是原地改。**

### 常用命令

```powershell
npm create vite@latest web -- --template react   # 创建项目
cd web
npm install                                       # 装依赖
npm run dev                                       # 启动开发服务器（5173）
```

---

## 十三、自测问题

1. `UI = f(state)` 是什么意思？"f" 指的是什么？（第二节）
2. 为什么组件名必须首字母大写？（第三节）
3. JSX 返回的是真实 DOM 吗？如果不是，是什么？（第四节）
4. `class` 在 JSX 里要写成什么？为什么？（第四节）
5. **props 能不能被修改？如果不能，子组件想改数据该怎么办？**（第五节）
6. `useState` 返回的两个东西分别是什么？第二个有什么用？（第六节）
7. **为什么 `todos.push(x)` 之后界面不更新？**（第六节）
8. `setTodos([...todos, x])` 里的 `...` 是干什么的？（第六节）
9. **`useEffect` 的第二个参数写 `[]` 和不写，有什么区别？**（第七节）
10. `key` 是干什么的？为什么不能用数组下标当 `key`？（第八节）
11. `onClick={fn}` 和 `onClick={fn()}` 有什么区别？（第九节）
12. 什么是"受控组件"？它和 4A 里 `input.value = ""` 有什么区别？（第九节）
13. Vite 帮你做了什么？为什么 JSX 需要编译？（第十节）

---

## 修订记录

| 日期 | 说明 |
|---|---|
| 阶段 4A 完成后 | 初版，作为阶段 4B 的前置阅读材料 |
