# 待办清单 · Todo App

一个从零手写的待办清单，用来把 **HTTP / SQL / React / 大模型接口** 这几件事串成一个能跑的东西。

没什么黑科技，但每一层都是自己写的：数据库是 `sqlite3` 标准库，没有 ORM；前端没有路由库、没有状态管理库，只有 `useState` / `useEffect`；接大模型是直接 `urllib` 发 POST，没有 SDK，也没有 agent 框架。

---

## 能做什么

**基础**
- 增删改查任务，数据存在本地 `todos.db`，重启不丢
- 打勾完成 / 取消完成，已完成显示灰色删除线
- 按「全部 / 未完成 / 已完成」筛选
- 给任务设截止日期和优先级（高 / 中 / 低），逾期且未完成的日期标红

**AI（自然语言）**
- **先说一句，看清楚再建**：输入「周五前交实验报告，很重要，顺便买牛奶」→ 解析成 2 条草稿（含日期、优先级）→ 你可以划掉不要的 → 点确认才真正写库
- **让助手直接动手**：同一个输入框，「交给助手」会让模型自己决定调哪些工具（查列表 / 新建 / 改状态），直接执行并回报它做了什么
- **删东西必须先问人**：模型只能提交「删除请求」，界面上出现一张黄色确认卡片，点「删除」才真的删

---

## 技术栈

| 层 | 用了什么 | 刻意没用的 |
|---|---|---|
| 后端 | Python 3 · FastAPI · Pydantic v2 | ORM（直接写 SQL） |
| 数据库 | SQLite（`sqlite3` 标准库） | — |
| 前端 | React 19 · Vite 8 · 手写 CSS | 路由库、状态管理库、UI 组件库 |
| 大模型 | DeepSeek `chat/completions`，`urllib` 直连 | OpenAI SDK、LangChain、任何 agent 框架 |
| 测试 | pytest · FastAPI `TestClient` · `unittest` | — |

---

## 快速开始

需要 **两个终端**，都保持开着。

### 0. 准备（只做一次）

```powershell
cd "D:\DSH projects\todo-app"

# 后端依赖
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 密钥：复制模板，然后填入你自己的 key
Copy-Item .env.example .env
# 编辑 .env，把 DEEPSEEK_API_KEY 换成真实值（形如 sk-xxxxxxxx）
```

```powershell
# 前端依赖
cd web
npm install
```

### 1. 终端 A —— 后端

```powershell
cd "D:\DSH projects\todo-app"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

- 接口：<http://127.0.0.1:8000>
- 接口文档（Swagger）：<http://127.0.0.1:8000/docs>

### 2. 终端 B —— 前端

```powershell
cd "D:\DSH projects\todo-app\web"
npm run dev
```

页面：**<http://127.0.0.1:5173>**

> ⚠️ Vite 打印的是 `localhost`，但请用 `127.0.0.1` 打开。
> 后端 CORS 是精确字符串匹配，`localhost` 和 `127.0.0.1` 在浏览器眼里是两个不同的源；
> 而且在本机上 `localhost` 会被优先解析成 IPv6 的 `::1`，Vite 未必监听在那儿。

> ⚠️ 改了 `.env` 必须**手动重启** uvicorn —— `--reload` 只监控 `*.py`，配置文件变了它不知道。

`start.txt` 里也有同样的备忘，可以直接看那个。

### 3. 跑测试

```powershell
cd "D:\DSH projects\todo-app"
.\.venv\Scripts\python.exe -m pytest -q
```

预期 **73 passed**。

其中 2 个是**真**集成测试（真的向 `http://127.0.0.1:8000` 发 HTTP 请求），
所以要么先把 uvicorn 开着（73 passed），要么接受它们是红的（71 passed + 2 failed）。
其余 71 个都在进程内跑（`TestClient` 或打桩），不碰网络、不碰模型、**不花钱**。

---

## 目录结构

```
todo-app/
├── main.py              # 应用入口：只做装配（建 app、配 CORS、建表、挂路由）
├── database.py          # 连接、建表、以及"给已有表加列"的迁移
├── models.py            # Pydantic 模型 + row → dict 的转换
├── routers/
│   ├── todos.py         # 任务接口 + set_done()（不挂路由，给 AI 用）
│   └── ai.py            # AI 接口 + 异常 → 状态码的统一翻译
├── ai_client.py         # 传输层：只管"把 messages 发出去，把 data 拿回来"
├── ai_tasks.py          # 业务层：一句话 → 结构化任务（含校验 + 重试）
├── ai_agent.py          # 业务层：工具调用的那个 while 循环
├── conversations.py     # 多轮记忆：会话的存取、过期、截断
├── tests/               # 94 个测试
├── docs/                # 学习笔记（见下）
├── web/                 # React + Vite 前端
│   └── src/
│       ├── App.jsx      # 只描述界面
│       ├── hooks/       # useTodos / useAiParse / useAgent —— 所有 fetch 都在这
│       └── *.jsx        # TodoList / TodoItem / AiPreview / AgentPanel
├── frontend/            # 4A 版本：纯原生 JS（留着当对照物）
└── todos.db             # 数据（已 gitignore）
```

---

## 几个值得说的设计决定

**① 解析和创建是两个接口**

`POST /ai/parse` 只出草稿，`POST /todos/batch` 才写库。
如果让解析接口直接写库，"用户看完觉得不对"就变成了"删掉刚才建的三条"——
而垃圾数据已经进库了。**草稿不是数据。**

**② 「没有找到任务」返回 200，不是 422**

输入「今天天气真好」→ `{"tasks": []}` → **200**。
这不是错误，是 `successful empty result`（成功的空结果），跟搜索引擎搜不到东西一样。
422 只留给"请求本身不合法"：空字符串、超过 2000 字、优先级写了 `urgent`。

**③ 给界面的接口是 `toggle`，给模型的接口是 `set_done`**

按钮调 `toggle`（翻转），因为人看着状态点，不会连点。
模型调 `set_done(id, true)`（设为某个值），因为它会重试、会并行——`toggle` 执行两次就回到原点了。
**幂等不是洁癖，是给会重试的调用方准备的。**

**④ 模型删不掉任何东西**

工具表里有 `request_delete`，它的函数体里一行 `DELETE` 都没有，只是查一下确认存在、然后返回 `"deleted": False` 和一句"等用户确认"。
真正的删除发生在那个红色按钮上，走的 `DELETE /todos/{id}` 和普通删除按钮**完全同一条路**。

代价是"确认"必须拆成两次请求——因为 HTTP 是一问一答，后端没法在请求中途停下来问用户。
**能删东西的权限留在人手里，不留在提示词里。**

**⑤ 只有模型能改的错误才重试**

输出不是合法 JSON、字段类型不对、id 不存在、被截断 → 把错误信息喂回去让它自己修。
数据库挂了、上游 401、超时 → 直接抛，映射成 500/502/504。
一句话：**模型能改的喂回去，改不了的抛出去。**

**⑥ 记忆是"把上次的 messages 再发一遍"**

模型本身不记得任何东西。所谓多轮对话，就是每一轮把 `[system] + 历史 + 新的一句`
拼起来发出去。所以"加记忆"在代码里只是加一张表 + `load` / `save` 两个函数，
循环一行没改。**上下文工程听起来玄，落地就是这段拼接。**

代价是成本变乘法：第 N 轮要为前 N-1 轮再付一次钱，所以只留最近 3 轮。

---

## 已知限制

- **没有用户体系**。所有数据属于"这台机器"，限流只能靠前端禁用按钮 + 按 IP。真要做多用户得先有登录。
- **会话记忆只在服务端存 24 小时，且只留 3 轮**。另外前端把 `conversation_id` 存在内存里，**刷新页面就等于开始新对话**（刻意没做 localStorage，调试时更好用）。三种失忆都是静默降级，不报错。
- **迁移只加不减**。`database.py` 里用 `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` 给旧表补列，没有回滚、没有版本号。够本地用，不够上线。
- **CORS 写死了两个本地端口**。换成别的端口就得改 `main.py`。
- **只在本机跑过**。没有部署配置，没有反向代理，也没有 HTTPS。要上线至少还缺：把 `uvicorn` 换成多进程、把 SQLite 换成能并发写的库、把 CORS 改成真实域名。

---

## 文档

`docs/` 里是跟着项目一起写的笔记，不是抄来的教程：

| 文件 | 内容 |
|---|---|
| `01-http-basics.md` | 请求/响应长什么样、方法、状态码、无状态、路由表 |
| `02-stage2-check.md` | 阶段自测 + 参考答案 |
| `03-sql-basics.md` | 声明式 vs 命令式、五条语句、参数化与注入、索引 |
| `04-frontend-basics.md` | DOM、事件、`fetch`、CORS 与同源策略 |
| `05-react-basics.md` | 组件、JSX、state、单向数据流、4A→4B 对照 |
| `06-js-essentials.md` | 箭头函数、`map/filter`、展开解构、加新功能的思考流程 |
| `07-ai-agent.md` | 工具调用循环、协议三件套、幂等、删除确认、成本与注入防护、多轮记忆 |

`07` 末尾有 6 条面试问答和 8 道自测题，都是从这份代码本身出发的。
