// ============================================================
//  App.jsx —— 主组件（现在只管"界面"）
//
//  它现在只做三件事：
//    ① 从 useTodos 拿数据
//    ② 管理【纯界面】状态（输入框文字、当前筛选）
//    ③ 描述整个页面长什么样
//
//  和后端的全部往来，都在 hooks/useTodos.js 里。
//
//  ⭐ 对比重构前：166 行 → 现在约 120 行，而且少了 5 个 fetch。
//     但真正的收益不是"行数变少"，是"职责变清楚"：
//     想改接口地址？改 useTodos.js。
//     想改界面？改这里。
// ============================================================

import { useState } from "react";
import TodoList from "./TodoList";
import AiPreview from "./AiPreview";
import AgentPanel from "./AgentPanel";
import { useTodos } from "./hooks/useTodos";
import { useAiParse } from "./hooks/useAiParse";
import { useAgent } from "./hooks/useAgent";
import "./App.css";

function App() {
    // ---------- 数据：全部来自自定义 Hook ----------
    // 一行拿到五样东西，不需要知道它们是怎么来的
    const { todos, loading, error, addTodo, addMany, toggleTodo, deleteTodo, reload } = useTodos();

    // ---------- AI 解析：另一组独立的状态 ----------
    //
    //    useTodos   → 管"已经存在的任务"
    //    useAiParse → 管"还没被创建、只是候选的草稿"
    //
    //  ⭐ 为什么一定要分成两个 Hook？
    //     因为它们的生命周期完全不同：
    //     草稿可以随时被丢弃，而丢弃它【不应该影响任何已存在的数据】。
    //     如果塞进 useTodos，"放弃草稿"就变成了一次和数据库有关的事，
    //     而它本来什么都不是。
    const ai = useAiParse();

    // ---------- AI 助手：会真的动手 ----------
    //
    //    useAiParse → 只解析，什么都不写   （"先预览"路径）
    //    useAgent   → 自己判断、直接执行    （"交给助手"路径）
    //
    //  ⭐ 为什么不做成"一个按钮，自动判断该走哪条路"？
    //     因为"要不要先让我看一眼"是【用户】的决定，不是模型的决定。
    //     同一句话"买牛奶"，有人想先核对，有人嫌麻烦想直接建。
    //     把决定权交回去，比让模型猜用户性格要诚实得多。
    const agent = useAgent();

    // ---------- 纯界面状态：留在组件里 ----------
    // 为什么这两个不放 hook？
    //   因为它们只和"这个界面"有关，别的界面未必需要。
    //   Hook 只管"任务的增删改查"，不管"用户现在打了几个字"。
    const [text, setText] = useState("");            // 输入框里的文字
    const [due, setDue] = useState("");              // 日期框里的值（"" = 没填）
    const [filter, setFilter] = useState("all");     // "all" | "active" | "done"
    const [aiText, setAiText] = useState("");        // AI 输入框里的文字
    const [aiConfirmError, setAiConfirmError] = useState(null);  // 确认创建时的错误

    // ---------- 派生数据：从 todos + filter 算出来 ----------
    // ⚠️ 它不是 state —— 每次渲染时重新算，所以永远和 todos 一致
    const visibleTodos = todos.filter(todo => {
        if (filter === "active") return !todo.done;   // 未完成 → 留
        if (filter === "done")   return todo.done;    // 已完成 → 留
        return true;                                   // all → 全留
    });

    // ---------- 添加：这里只处理"界面"那部分 ----------
    // 阻止表单刷新、去掉首尾空格、清空输入框 —— 这些都是界面的事。
    // 真正"发给后端"的那一步，已经交给 addTodo 了。
    async function handleAdd(e) {
        e.preventDefault();            // 阻止表单默认行为（刷新页面）
        const title = text.trim();     // trim() 去掉首尾空格
        if (title === "") return;      // 空内容不提交

        // ⭐ 第二个参数是日期。没填时 due 是空字符串 ""，
        //    addTodo 里会把它转成 null（"没有截止日"）。
        await addTodo(title, due);     // ← ⭐ 交接点：界面 → 数据
        setText("");                   // 清空输入框（改 state，界面自动变）
        setDue("");                    // 日期框也清空（不然下一条会带着旧日期）
    }

    // ---------- AI 第一步：把一句话交给后端解析 ----------
    // 注意：这一步【什么都不写库】，只拿回一份草稿
    async function handleAiParse(e) {
        e.preventDefault();
        const t = aiText.trim();
        if (t === "") return;
        setAiConfirmError(null);
        await ai.parse(t);
    }

    // ---------- AI 第二步：用户点了"确认创建" ----------
    async function handleAiConfirm() {
        // AI 给的是 {title, priority, due}，这里原样交给后端 ——
        // todos 表现在有 due 和 priority 两列了（见 database.py 的 _migrate）。
        const tasks = ai.draft.map(t => ({
            title: t.title,
            done: false,
            due: t.due,           // 可能是 null（"没有截止日期"）
            priority: t.priority, // "high" | "normal" | "low"
        }));
        if (tasks.length === 0) return;

        setAiConfirmError(null);
        try {
            await addMany(tasks);      // ← 唯一一次真的写数据库
            ai.discardDraft();         // 成功之后才清草稿
            setAiText("");
        } catch (err) {
            // ⚠️ 失败时【保留草稿】。
            //    如果这里清空了，用户辛辛苦苦等来的解析结果就白丢了，
            //    还得重新说一遍、再等一次模型。草稿留着，他可以直接重试。
            setAiConfirmError(err.message);
        }
    }

    // ---------- 助手：把一句话直接交给它 ----------
    //
    //  ⚠️ 这里和 handleAiParse 有一个关键区别：**它真的会写库**。
    //     所以进来先要把旧的草稿和旧的结果清掉，
    //     否则界面上会同时挂着"上一次的草稿"和"这一次的回执"，谁也说不清哪条是新发生的。
    async function handleAgentRun() {
        const t = aiText.trim();
        if (t === "") return;
        setAiConfirmError(null);
        ai.discardDraft();        // 两条路互斥：走助手就不要再留着预览草稿
        const result = await agent.run(t);

        // ⭐⭐ 它真的动过库，就得把列表重新拉一遍 —— 这一行是当初漏掉的。
        //
        //   漏掉的后果很典型：助手说"已标记为完成"，后端也确实改了，
        //   但界面还是旧样子，用户必须按 F5 才看得见。
        //   这种 bug 特别难自查，因为【后台是对的】—— 错的是前端没去问。
        //
        // ⚠️ 但不是每次都刷：list_todos 是只读的，调它不会改变任何数据。
        //    刷一次要发一个请求，还会把 loading 打回 true 让列表闪一下 ——
        //    什么都没变就不值得做。
        //    判据不是"它说了几句话"，而是"它有没有真的动手"。
        const wrote = result?.actions?.some(a => a.ok && a.tool !== "list_todos");
        if (wrote) {
            await reload();
        }
    }

    // ---------- 列表里那个"删除"按钮 ----------
    //
    //  ⭐ 为什么要包一层？因为 deleteTodo 现在会 throw（服务器 500 之类）。
    //     不接住它，就会变成浏览器的 Unhandled Promise Rejection ——
    //     控制台一行红字，界面上什么都没变，用户以为按钮坏了。
    //     "失败要响"：能响在界面上，就别只响在控制台里。
    async function handleDelete(id) {
        try {
            await deleteTodo(id);
        } catch (err) {
            setAiConfirmError(err.message);
        }
    }

    // ---------- 助手说"要不要删" → 用户点了"删除" ----------
    //
    //  ⭐ 这一行才是真正调用 DELETE 的地方。
    //     注意它调的是 deleteTodo —— 就是列表里那个"删除"按钮用的同一个函数，
    //     走的是同一条 `DELETE /todos/{id}`。
    //     模型这一路上从来没碰过删除，它只是把"我想删这条"写成了结构化数据，
    //     最后由人按下的这个按钮完成。
    async function handleAgentConfirmDelete(proposal) {
        try {
            await deleteTodo(proposal.id);      // 真的删（并 reload）
            agent.dismissProposal(proposal.id); // 删成功后才把这条询问从界面上撤掉
        } catch (err) {
            // 删失败就【保留】这条询问，用户还能再点一次
            setAiConfirmError(err.message);
        }
    }

    // ---------- 换个话题：把记忆清掉 ----------
    //
    //  ⚠️ 为什么需要这个按钮？因为记忆是把双刃剑：
    //     上一段对话在聊"实验报告"，你现在说"那个不用了"，
    //     模型会顺着上文理解成"实验报告不用了" —— 这是它尽责，不是它犯傻。
    //     用户需要一个明确的出口来表达"我们换个话题"，
    //     否则他只能刷新页面（而刷新是个连自己都解释不清的动作）。
    function handleNewConversation() {
        agent.newConversation();
        setAiConfirmError(null);
        setAiText("");
    }

    // ---------- 描述界面 ----------
    // 注意：这里只"描述"，不"操作 DOM"。React 负责把描述变成真实界面。
    return (
        <div>
            <h1>我的待办</h1>

            <p>共 {todos.length} 条，已完成 {todos.filter(t => t.done).length} 条</p>

            {/* onSubmit：表单提交时调用 handleAdd */}
            <form onSubmit={handleAdd}>
                {/* 受控组件：value 由 state 决定，onChange 时更新 state */}
                <input
                    value={text}
                    onChange={e => setText(e.target.value)}
                    placeholder="要做什么？"
                />
                {/* ⭐ type="date" 是浏览器【自带】的日期选择器 —— 免费得到一个日历。
                    它给的值永远是 "YYYY-MM-DD" 格式的字符串，
                    正好等于后端 date 字段要的格式，中间不用转换。
                    没填时值是空字符串 ""（不是 null），这就是 addTodo 里
                    要做 `due || null` 的原因。
                    ⚠️ 它显示成什么样子由【浏览器语言】决定，
                       但 value 永远是 ISO 格式 —— 显示归显示，数据归数据。 */}
                <input
                    type="date"
                    value={due}
                    onChange={e => setDue(e.target.value)}
                    aria-label="截止日期（可不填）"
                />
                <button type="submit">添加</button>
            </form>

            {/* ===== AI：用一句话操作 =====
                ⚠️ 这是【第二个 form】，和上面"要做什么？"那个不是同一个。
                两个 form 各有自己的 state（text / aiText），互不干扰。
                这也是把逻辑拆成两个 Hook 之后自然的结果：
                加一个功能 = 加一块 state + 加一块 JSX，不用动已有的代码。

                ⭐ 一个输入框，两个按钮，两种信任程度：
                   "先预览"   → 只解析，你点确认才写库（安全、慢一步）
                   "交给助手" → 它自己决定调哪些工具，直接执行（快、但你要愿意放手）
                两个按钮共用一个输入框，因为"我说的话"是同一句话。
            */}
            <h2>用一句话操作</h2>
            <form onSubmit={handleAiParse}>
                {/* maxLength 和后端 MAX_INPUT_CHARS 对齐：后端会拒超过 2000 字的输入，
                    这里提前拦住，用户就不用等一个来回才知道太长。
                    "前后端各拦一次"不是重复劳动 —— 前端挡手滑，后端挡恶意。 */}
                <input
                    value={aiText}
                    onChange={e => setAiText(e.target.value)}
                    placeholder="例：周五前交实验报告，很重要，顺便买牛奶"
                    maxLength={2000}
                />
                {/* 两个按钮在对方忙的时候都要禁用：
                    模型一次调用可能要几十秒，不禁用用户就会连点三次，
                    三次都真的执行、三次都收费。
                    ⚠️ 这是目前我们能做的【唯一的】成本闸门 —— 我们没有"用户"概念，
                       挡不住换个浏览器再来的人，只能挡住手滑的人。 */}
                <button type="submit" disabled={ai.parsing || agent.running}>
                    {ai.parsing ? "解析中……" : "先预览"}
                </button>
                <button
                    type="button"
                    onClick={handleAgentRun}
                    disabled={ai.parsing || agent.running}
                >
                    {agent.running ? "处理中……" : "交给助手"}
                </button>
            </form>

            <p className="ai-hint">
                「先预览」不会写库，你确认后才创建；「交给助手」它自己判断并直接执行（删东西仍会先问你）。
            </p>

            {/* ===== 对话状态 =====
                助手现在会记住这次对话里说过的话：后端按 conversation_id
                把 messages 存进 conversations 表，下一句再取出来一起发。

                所以"把买牛奶删掉" → 你点确认 → "那另一条呢" 能接上。
                ⚠️ 但这也意味着：你换了话题它未必知道，它会顺着上文理解你。
                   所以给一个明确的出口，比让它猜要诚实。 */}
            {agent.conversationId && (
                <p className="ai-hint ai-conversation">
                    助手记得这次对话。
                    <button type="button" onClick={handleNewConversation}>
                        开始新对话
                    </button>
                </p>
            )}

            {ai.error && <p style={{ color: "red" }}>出错了：{ai.error}</p>}
            {agent.error && <p style={{ color: "red" }}>出错了：{agent.error}</p>}
            {aiConfirmError && (
                <p style={{ color: "red" }}>出错了：{aiConfirmError}</p>
            )}

            {/* 只有拿到草稿才显示预览卡片；null 时什么都不渲染 */}
            {ai.draft && (
                <AiPreview
                    tasks={ai.draft}
                    note={ai.note}
                    busy={loading}
                    onRemove={ai.removeDraftTask}
                    onConfirm={handleAiConfirm}
                    onCancel={ai.discardDraft}
                />
            )}

            {/* 助手做完之后显示它说了什么、做了什么、还想做什么 */}
            <AgentPanel
                result={agent.result}
                continued={agent.continued}
                onConfirmDelete={handleAgentConfirmDelete}
                onDismiss={agent.dismissProposal}
            />

            {/* ===== 筛选按钮 =====
                位置：form 之后、任务列表之前 —— 因为它们控制"显示哪些任务"。
                样式规则在 App.css 里：.filters 和 .filters button.active
            */}
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

            {/* {条件 && JSX} —— 短路写法：条件为真才渲染 */}
            {loading && <p>加载中……</p>}
            {error && <p style={{ color: "red" }}>出错了：{error}</p>}

            {/* 只有"不在加载中 且 没出错"时才显示列表 */}
            {!loading && !error && (
                <TodoList
                    todos={visibleTodos}       // 数据往下传（筛选后的）
                    onToggle={toggleTodo}      // 函数往下传（子组件用它"请求"修改）
                    onDelete={handleDelete}
                />
            )}
        </div>
    );
}

// ⚠️ 必须导出，否则 main.jsx 里 import 不到
export default App;
