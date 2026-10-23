# JavaScript 语法要补的那一层

> **适用阶段**：阶段 4B 之后（写新功能之前）
> **为什么要单独写这一节**：4B 里我直接用了箭头函数、`.map()`、`.filter()`、`...` 展开、解构、三元、短路 —— **全都没单独教过**。这些是"能读懂但写不出来"的根源。
> **阅读方式**：不用背。**重点是第十节「加一个新功能的思考流程」和第十一节的完整走查。**

---

## 目录

1. [先认清一件事：你不是不会 React，是缺 JS 语法](#一先认清一件事你不是不会-react是缺-js-语法)
2. [箭头函数](#二箭头函数最重要)
3. [数组三件套：map / filter / find](#三数组三件套map--filter--find)
4. [展开运算符 `...`](#四展开运算符-)
5. [解构](#五解构)
6. [三元表达式](#六三元表达式)
7. [短路 `&&` 和 `||`](#七短路--和-)
8. [模板字符串](#八模板字符串)
9. [和 Python 的对照总表](#九和-python-的对照总表)
10. [**加一个新功能的思考流程**](#十-加一个新功能的思考流程)
11. [**用「筛选功能」完整走一遍**](#十一-用筛选功能完整走一遍)
12. [自测问题](#十二自测问题)

---

## 一、先认清一件事：你不是不会 React，是缺 JS 语法

**回头看你这几天的经历：**

| 你做到的 | 需要的其实是 |
|---|---|
| 看懂 `todos.map(todo => <TodoItem />)` | **`.map()` + 箭头函数** |
| 看懂 `setTodos([...todos, newTodo])` | **展开运算符** |
| 看懂 `function TodoItem({ todo })` | **解构** |
| 看懂 `className={todo.done ? "done" : ""}` | **三元表达式** |
| 看懂 `{loading && <p>加载中……</p>}` | **短路运算** |
| 看懂 `e => setText(e.target.value)` | **箭头函数** |

**这些全是 JavaScript，不是 React。**

**React 本身的概念（组件、props、state、Hooks）其实很少** —— 你已经理解了。**卡住你的是"用 JS 表达这些概念"的语法。**

---

## 二、箭头函数（最重要）

### 它是什么

**一种更短的写函数的方式。**

```javascript
// 普通函数
function add(a, b) {
    return a + b;
}

// 箭头函数（完全等价）
const add = (a, b) => {
    return a + b;
};

// 箭头函数简写：函数体只有一行 return 时，可以省掉 {} 和 return
const add = (a, b) => a + b;
```

### 三种写法对照

| 写法 | 例子 | 什么时候用 |
|---|---|---|
| 完整 | `(x) => { return x * 2 }` | 函数体有多行 |
| 省 `return` | `(x) => x * 2` | 函数体只有一行表达式 |
| 单参数省括号 | `x => x * 2` | 只有一个参数 |

**⚠️ 括号能不能省，只看"参数个数"：**
- 一个参数 → `x => ...` ✅
- 零个或多个参数 → **括号不能省**：`() => ...`、`(a, b) => ...`

### ⚠️ 坑一：想返回对象，必须包一层括号

```javascript
const f = x => { id: x }        // ❌ 这里的 {} 被当成了"函数体"，不是对象！
const f = x => ({ id: x })      // ✅ 想返回对象就包一层圆括号
```

**因为 `=>` 后面直接跟 `{}` 时，JS 认为那是"函数体"。**

### ⚠️⚠️ 坑二（React 里最常踩）：这两种写法意思完全不同

```javascript
onClick={() => handleDelete(id)}    // ✅ 传一个"函数"给 React，点击时才调用
onClick={handleDelete(id)}          // ❌ 现在就立刻调用，把【返回值】传过去
```

**判断方法：**

| 写法 | 是什么 |
|---|---|
| `() => ...` | **一个函数**（还没执行） |
| `handleDelete(id)` | **一个值**（已经执行完了） |

**在 JSX 里，`onClick={...}` 期待的是一个"函数"，不是"函数调用的结果"。**

> **对照你在 4A 学的 `addEventListener("click", fn)`** —— 第二个参数也是**函数**，不是函数的返回值。**概念一样，只是写法短了。**

---

## 三、数组三件套：`map` / `filter` / `find`

**这三个方法几乎撑起了 React 里所有的"数组 → 界面"转换。**

```javascript
const nums = [1, 2, 3, 4];

nums.map(n => n * 2)        // [2, 4, 6, 8]    ← 每个元素都"变成"另一个
nums.filter(n => n > 2)     // [3, 4]          ← 只留下"条件为真"的
nums.find(n => n > 2)       // 3               ← 找第一个符合条件的
```

| 方法 | 返回什么 | 长度变吗 | 什么时候用 |
|---|---|---|---|
| `map` | **新数组** | 不变 | "把每条任务渲染成一个组件" |
| `filter` | **新数组** | **可能变短** | "只保留未完成的" |
| `find` | **一个元素**（找不到是 `undefined`） | —— | "找出 id=3 那一条" |

### ⭐ 关键：它们都**不修改原数组**

```javascript
const a = [1, 2, 3];
const b = a.map(n => n * 2);
// a 还是 [1, 2, 3]  ← 原数组没被改
// b 是 [2, 4, 6]    ← 返回的是新数组
```

**这和 React 的要求正好一致** —— React 需要你"造新数组"，不是"改旧数组"。

### 关于括号和 `return`

```javascript
// 箭头函数体只有一行 → 那行的值自动作为返回值
nums.map(n => n * 2)          // ✅

// 函数体有多行 → 必须写 {} 和显式 return
nums.map(n => {
    const doubled = n * 2;
    return doubled;           // ⚠️ 这个 return 不能省
})
```

**⚠️ 一个常见错误**：用 `{}` 却忘了 `return` → 返回值全是 `undefined`，界面一片空白。

### 和 Python 对照

| JavaScript | Python |
|---|---|
| `arr.map(f)` | `[f(x) for x in arr]` |
| `arr.filter(f)` | `[x for x in arr if f(x)]` |
| `arr.find(f)` | `next((x for x in arr if f(x)), None)` |
| `arr.forEach(f)` | `for x in arr: f(x)` |

**所以 `todos.map(todo => <TodoItem />)` 读作**：
> "把 `todos` 里每一条任务，都变成 `<TodoItem />`，组成一个新数组。"

**Python 里你会写成 `[<TodoItem /> for todo in todos]`** —— 一模一样的意思。

---

## 四、展开运算符 `...`

### 它做什么：把数组/对象"拆开铺平"

```javascript
const a = [1, 2];
const b = [3, 4];

[...a, ...b]        // [1, 2, 3, 4]     ← 两个数组拼起来
[...a, 5]           // [1, 2, 5]        ← 在末尾追加一个
[0, ...a]           // [0, 1, 2]        ← 在开头插入

const obj = { x: 1, y: 2 };
{ ...obj, y: 99 }   // { x: 1, y: 99 }  ← 复制并覆盖某个字段
```

### ⭐ React 里三个最经典的用法

```javascript
// ① 追加一条
setTodos([...todos, newTodo]);

// ② 删除一条（filter 造一个新数组）
setTodos(todos.filter(t => t.id !== id));

// ③ 改一条（map + 展开，造一个新对象）
setTodos(todos.map(t =>
    t.id === id ? { ...t, done: !t.done } : t
));
```

**第 ③ 条读作**：
> "遍历每条任务：如果它的 id 是我要改的那条，就**复制它的所有字段、把 done 反过来**（`{ ...t, done: !t.done }`）；否则原样返回。"

### ⚠️ 为什么必须"造新的"

**因为 React 靠比较「引用」判断数据变没变。**

```javascript
const a = [1, 2];
a.push(3);        // a 还是那个数组对象（引用没变）
```

**React 一看："还是同一个数组，没变化" → 不重新渲染 → 界面不动。**

```javascript
setTodos([...todos, newTodo]);   // 一个【新】数组 → 引用变了 → React 知道要更新 ✅
```

---

## 五、解构

### 从数组里"按位置"取值

```javascript
const [a, b] = [1, 2];                    // a=1, b=2

const [count, setCount] = useState(0);    // ← useState 就是返回一个数组！
```

**所以 `const [count, setCount] = useState(0)` 读作**：
> "`useState(0)` 返回一个两元素数组，我把它拆成两个变量。"

### 从对象里"按名字"取值

```javascript
const todo = { id: 1, title: "写报告", done: false };

const { title, done } = todo;             // title="写报告", done=false

// 也可以改名
const { title: name } = todo;             // name = todo.title
```

### ⭐ 在函数参数里直接解构（React 组件最常见的写法）

```javascript
function TodoItem({ todo, onToggle, onDelete }) { }
```

**这完全等价于：**

```javascript
function TodoItem(props) {
    const todo = props.todo;
    const onToggle = props.onToggle;
    const onDelete = props.onDelete;
}
```

**所以 `<TodoItem todo={x} onToggle={f} />` 传进去的是一个**对象**：**

```javascript
{ todo: x, onToggle: f }
```

**React 把这个对象叫 `props`，而 `{ todo, onToggle }` 就是"从这个对象里按名字取出三个字段"。**

### 和 Python 对照

| JavaScript | Python |
|---|---|
| `const [a, b] = [1, 2]` | `a, b = 1, 2` |
| `const { x, y } = obj` | 没有直接对应（要 `x = obj["x"]`） |

---

## 六、三元表达式

```javascript
条件 ? 真时的值 : 假时的值
```

**例子：**

```javascript
todo.done ? "done" : ""          // done 为真 → "done"，否则 → ""
todos.length === 0 ? "空" : "有"
```

**和 Python 对照：**

| JavaScript | Python |
|---|---|
| `a ? b : c` | `b if a else c` |

**⚠️ 顺序不一样！** JS 把**条件放最前面**，Python 放中间。

**React 里的典型用法：**

```jsx
<li className={todo.done ? "done" : ""}>
```

**读作**："done 为真时，class 就是 `done`；否则是空字符串。"

> ⚠️ **注意 `: ""` 不能省** —— 三元必须有三部分。省了会语法错误。

---

## 七、短路 `&&` 和 `||`

```javascript
a && b        // a 为假 → 返回 a；a 为真 → 返回 b
a || b        // a 为真 → 返回 a；a 为假 → 返回 b
```

**和 Python 的 `and` / `or` 完全一样。**

**React 里最常见的用法：**

```jsx
{loading && <p>加载中……</p>}        // loading 为真才渲染这个 <p>
{error && <p>出错了</p>}
{name || "匿名"}                     // name 为空时显示"匿名"
```

**为什么 `{loading && <p>}</p>` 能控制渲染？**

| `loading` | 结果 | React 怎么做 |
|---|---|---|
| `true` | **返回右边的 `<p>`** | 渲染它 |
| `false` | **返回 `false`** | **`false` 不渲染任何东西** |

**这就是 JSX 里最常用的条件渲染写法。**

---

## 八、模板字符串

```javascript
const url = `${API}/todos/${id}`;
```

**反引号（`` ` ``，键盘左上角 Esc 下面那个）+ `${表达式}`。**

**对应 Python 的 f-string：**

| JavaScript | Python |
|---|---|
| `` `${a} 和 ${b}` `` | `f"{a} 和 {b}"` |

**⚠️ 用反引号，不是单引号。** 单引号里 `${}` 只是普通文本。

---

## 九、和 Python 的对照总表

| 概念 | JavaScript | Python |
|---|---|---|
| 变量 | `const x = 1` / `let x = 1` | `x = 1` |
| 函数 | `function f(a) { }` | `def f(a):` |
| 箭头函数 | `a => a * 2` | `lambda a: a * 2` |
| 条件 | `if (a === b) { }` | `if a == b:` |
| 循环 | `for (const x of xs) { }` | `for x in xs:` |
| 列表 | `[1, 2, 3]` | `[1, 2, 3]` |
| 字典/对象 | `{ a: 1 }` | `{"a": 1}` |
| 取属性 | `obj.a` 或 `obj["a"]` | `d["a"]` |
| 相等 | **`===`**（推荐） | `==` |
| 空值 | `null` / `undefined` | `None` |
| 布尔 | `true` / `false` | `True` / `False` |
| 字符串插值 | `` `${x}` `` | `f"{x}"` |
| 三元 | `a ? b : c` | `b if a else c` |
| 短路 | `a && b` | `a and b` |
| 映射 | `arr.map(f)` | `[f(x) for x in arr]` |
| 过滤 | `arr.filter(f)` | `[x for x in arr if f(x)]` |
| 查找 | `arr.find(f)` | `next((x for x in arr if f(x)), None)` |
| 展开 | `[...a, ...b]` | `[*a, *b]` |
| 列表解构 | `const [a, b] = [1, 2]` | `a, b = 1, 2` |
| 对象解构 | `const { a } = obj` | （无直接对应） |

---

## 十、⭐ 加一个新功能的思考流程

**这是全篇最该记住的东西。** 你不是不知道怎么"写代码"，你是**缺少一个从需求到代码的固定套路**。

### 四句话

> **① 这个功能需要"记住"什么吗？**
> **② 需要什么"从已有数据算出来"的东西吗？**
> **③ 界面上要出现什么新东西？**
> **④ 用户能操作什么？**

**一一对应到代码：**

| 问题 | 对应到 |
|---|---|
| ① 需要记住什么？ | **开一个 `useState`** |
| ② 需要算什么？ | **写一个普通 `const`（派生数据）** |
| ③ 界面加什么？ | **写 JSX** |
| ④ 能操作什么？ | **加 `onClick` / `onChange`，里面调用 `setState` 或已有函数** |

### ⭐ 顺序很重要：**先想数据，再想界面**

**新手最常犯的错是反过来** —— 先动手写 JSX，然后卡住："这个数字从哪来？"

**正确的思考顺序永远是：数据 → 派生 → 界面 → 交互。**

### ⚠️ 第 ② 条有个大坑：**派生数据不要开成新 state**

```jsx
// ❌ 错误：又开一个 state
const [todos, setTodos] = useState([]);
const [visibleTodos, setVisibleTodos] = useState([]);   // ← 多了一份"真相"
// 然后你必须在每次 todos 变化时手动同步 visibleTodos…… 这就是 4A 的痛！

// ✅ 正确：用普通变量算出来
const [todos, setTodos] = useState([]);
const [filter, setFilter] = useState("all");
const visibleTodos = todos.filter(...);     // ← 每次渲染时重新算，永远和 todos 一致
```

**判断标准一句话：**

> **"它能从已有的 state 直接算出来吗？"**
> **能 → 普通变量。不能 → 才开 state。**

**`filter`（当前选哪个筛选）算不出来 → 要 state。**
**`visibleTodos`（筛选后的列表）能算出来 → 普通变量。**

---

## 十一、用「筛选功能」完整走一遍

**需求**：页面上加「全部 / 未完成 / 已完成」三个按钮，点击切换列表显示的内容。

### ① 这个功能需要"记住"什么？

**"当前选的是哪个筛选"** —— 它有 3 个可能的值，而且用户点了之后要变。

**→ 开一个 state：**

```jsx
const [filter, setFilter] = useState("all");     // "all" | "active" | "done"
```

**为什么初始值是 `"all"`？** 因为一进页面应该显示全部。

### ② 需要什么"从已有数据算出来"的东西？

**"符合当前筛选的那些任务"。**

**它能从 `todos` 和 `filter` 算出来 → 普通变量，不是 state：**

```jsx
const visibleTodos = todos.filter(todo => {
    if (filter === "active") return !todo.done;   // 要未完成的
    if (filter === "done")   return todo.done;    // 要已完成的
    return true;                                   // otherall → 全部保留
});
```

**逐行读：**
- `todos.filter(回调)` —— 挑出回调返回 `true` 的那些
- 回调收到每一个 `todo`，根据 `filter` 返回"要不要它"

> 💡 **为什么这里用 `todos.filter(...)` 而不是 `todos.map(...)`？**
> 因为 `map` 是"每个都变成另一个"（长度不变），**`filter` 是"只留下符合条件的"（长度可能变短）**。
> **这正是我们要的。**

### ③ 界面上要出现什么新东西？

**三个按钮 + 列表改用 `visibleTodos`。**

```jsx
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
```

**⭐ 注意 `className={filter === "all" ? "active" : ""}`** ——
**和 `TodoItem` 里 `className={todo.done ? "done" : ""}` 是同一个套路：条件决定类名，CSS 负责好看。**

### ④ 用户能操作什么？

**点这三个按钮 → `setFilter("...")`。**

**然后**：把 `<TodoList todos={todos} .../>` 改成 `<TodoList todos={visibleTodos} .../>`。

### ⭐ 做完之后你会看到什么

**在"未完成"筛选下，点某条任务的勾** —— 它**立刻从列表里消失**。

**为什么？** 因为：
```
setFilter 没变，但 todo.done 变了
    ↓
todos 变 → visibleTodos 重新计算 → 这条不符合筛选了
    ↓
界面自动更新
```

**你没有写一行"把它从列表里移除"的代码。** 这就是**声明式**：
**你只描述了"哪些该显示"，剩下的是 React 的事。**

---

## 十二、自测问题

1. `(x) => x * 2` 和 `(x) => { x * 2 }` 有什么区别？（第二节）
2. **`onClick={() => f(id)}` 和 `onClick={f(id)}` 有什么区别？**（第二节）
3. `map` 和 `filter` 的返回值有什么不同？各在什么场景用？（第三节）
4. **`todos.push(x)` 之后界面为什么不更新？**（第四节）
5. `const [count, setCount] = useState(0)` 里的 `[]` 是什么语法？（第五节）
6. `function F({ a, b })` 这种参数写法等价于什么？（第五节）
7. JS 的三元 `a ? b : c` 和 Python 的写法顺序有什么不同？（第六节）
8. `{loading && <p>加载中</p>}` 里，`loading` 为 `false` 时渲染出什么？（第七节）
9. **加一个新功能，第一个该问自己的问题是什么？**（第十节）
10. **怎么判断一个东西该开 state，还是用普通变量？**（第十节）
11. 筛选功能里，`filter` 和 `visibleTodos` 哪个该是 state？为什么？（第十一节）

---

## 修订记录

| 日期 | 说明 |
|---|---|
| 阶段 4B 完成后 | 初版。补 4B 里直接使用但未讲解的 JavaScript 语法，以及"加新功能"的思考流程 |
