"""
tests/test_ai_agent.py —— 测工具调用循环，但【不真的调模型】

============================================================
⭐ 为什么这个文件特别重要？

    真机跑通只说明"顺利的那条路"能走。而 agent 的风险全在
    【不顺利的那条路】上：

      · 模型给了不合法的 JSON        → 会不会直接崩？
      · 模型想调一个不存在的工具      → 会不会误执行别的？
      · 模型一直失败                  → 会不会无限循环烧钱？
      · 数据库真的挂了                → 会不会被当成"模型的错"喂回去？

    这些路径，靠手点界面是【永远测不到】的 —— 你不能要求模型
    "请你现在输出一段坏 JSON"。所以只能打桩造出来。

============================================================
⚠️ 打桩打在哪？这是个经典坑。

    ai_agent.py 里写的是：

        import ai_client
        ...
        data = ai_client.chat(messages, api_key, tools=TOOL_SCHEMAS)

    所以补丁必须打在【ai_client 上】：

        monkeypatch.setattr(ai_client, "chat", fake)     ✅

    如果写成 monkeypatch.setattr(ai_agent, "chat", fake) ❌ ——
    ai_agent 里根本没有 chat 这个名字（它只有 ai_client），
    pytest 会直接报 AttributeError；如果 ai_agent 恰好有同名变量，
    补丁会静默失效，测试跑去调真模型，你还会收到账单。

    ⭐ 规则：**补丁打在"被查找的那个模块"上，不是"定义它的那个"上。**

       from ai_client import chat   → 补丁打在使用方模块（ai_tasks.chat）
       import ai_client; ai_client.chat() → 补丁打在 ai_client 上

    这两种写法本意一样，补丁位置完全不同。这也是为什么

    （顺带一提：test_ai_tasks.py 补的是 ai_tasks.chat，
      因为那边用的是 from ... import chat。）

============================================================
跑法（在 todo-app 目录下）：
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_agent.py -v
"""

import copy
import shutil
from pathlib import Path

import pytest

import database

# ⚠️ 必须在 import 任何会连数据库的模块【之前】改掉 DB_FILE。
#    顺序反了的话，模块级拿到的还是真库路径。
test_dir = Path(__file__).resolve().parent / "_tmp_agent"
shutil.rmtree(test_dir, ignore_errors=True)
test_dir.mkdir(parents=True, exist_ok=True)
database.DB_FILE = test_dir / "test.db"

import ai_agent            # noqa: E402
import ai_client           # noqa: E402
import conversations       # noqa: E402
from models import TodoCreate          # noqa: E402
from routers import todos as todos_router   # noqa: E402


# ============================================================
#  夹具：每个测试一个干净的库
# ============================================================

@pytest.fixture(autouse=True)
def clean_db():
    database.init_db()
    conn = database.get_connection()
    conn.execute("DELETE FROM todos")
    # ⚠️ DELETE 不会重置自增计数器，不清掉的话
    #    第二个测试里第一条任务的 id 就是 2，断言语义就乱了。
    conn.execute("DELETE FROM sqlite_sequence WHERE name='todos'")
    # 会话表也要清 —— 否则上一个测试留下的对话会跟着下一个测试跑，
    # "为什么这个测试里模型看到了一堆它没说过的话"会非常难查。
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
    yield


def teardown_module(module):
    shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
#  造响应：两个小工厂
# ============================================================

def wants_tool(call_id: str, name: str, arguments: str) -> dict:
    """造一条"模型要调工具"的响应。

    ⚠️ 注意三个细节，都是真机里真实存在的形状：
        · content 是 None（它这次一句话都没说）
        · reasoning_content 存在（思考原文，不该被回传）
        · arguments 是【字符串】，不是 dict
    """
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "reasoning_content": "（这是思考原文，回传会浪费 token）",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {},
    }


def says(text: str) -> dict:
    """造一条"模型只是说话"的响应。"""
    return {
        "choices": [{
            "message": {"role": "assistant", "content": text},
            "finish_reason": "stop",
        }],
        "usage": {},
    }


@pytest.fixture
def fake_model(monkeypatch):
    """装弹药：给它一串响应，它造一个假的 ai_client.chat。

    返回的 calls 记录每次请求时的 messages 快照 ——
    用来断言"我们喂回去的上下文长什么样"。
    """
    def _make(responses):
        calls = []

        def fake_chat(messages, api_key, **kwargs):
            # ⚠️ 深拷贝。这里 messages 里有嵌套的 tool_calls 列表，
            #    浅拷贝 [dict(m) for m in messages] 会让快照和原对象共享
            #    同一份嵌套数据 —— 后面聊到第 3 轮时，第 1 轮的快照
            #    会跟着变。
            calls.append(copy.deepcopy(messages))
            if not responses:
                raise AssertionError("假 chat 被调用次数超过了准备的响应数")
            return responses.pop(0)

        monkeypatch.setattr(ai_client, "chat", fake_chat)
        return calls

    return _make


def tool_msgs(messages: list[dict]) -> list[dict]:
    """从一次请求的 messages 里挑出所有 tool 消息。"""
    return [m for m in messages if m.get("role") == "tool"]


# ============================================================
#  正常路径
# ============================================================

def test_creates_a_task(fake_model):
    """模型调一次 create_todo，然后回话 → 库里真的多了一条"""
    calls = fake_model([
        wants_tool("call_1", "create_todo", '{"title":"买牛奶"}'),
        says("已经加好了"),
    ])

    result = ai_agent.run_agent("把买牛奶加进去", "fake-key")

    assert result.turns == 2
    assert result.truncated is False
    assert len(result.actions) == 1
    assert result.actions[0].ok is True
    assert result.actions[0].tool == "create_todo"

    # 真的写进库了吗？—— 断言数据库，不只是断言返回值
    tasks = todos_router.read_todos()
    assert [t["title"] for t in tasks] == ["买牛奶"]

    # actions 里的 detail 是给人看的话，不是 JSON
    assert "买牛奶" in result.actions[0].detail


def test_list_then_set_done_across_two_turns(fake_model):
    """先查再改 —— 这就是"多轮"存在的原因"""
    todos_router.create_todo(TodoCreate(title="买牛奶"))

    fake_model([
        wants_tool("call_1", "list_todos", "{}"),
        wants_tool("call_2", "set_done", '{"id":1,"done":true}'),
        says("标成完成了"),
    ])

    result = ai_agent.run_agent("把买牛奶标成完成", "fake-key")

    assert result.turns == 3
    assert [a.tool for a in result.actions] == ["list_todos", "set_done"]
    assert all(a.ok for a in result.actions)
    assert todos_router.read_todos()[0]["done"] is True


def test_set_done_is_idempotent(fake_model):
    """⭐ 幂等：同一次调用执行两遍，结果必须一样。

    这条测试的直接用途，是防止有人"顺手"把 set_done 改回 toggle。
    如果改回 toggle，第二遍会把 done 从 1 翻回 0，这里就会红。

    ⚠️ 为什么这么在意？因为 agent 会重试。网络抖一下、
       上游 5xx 一下、我们自己的循环多跑一轮，同一次调用就可能
       执行两次。不幂等的工具放在这种地方，结果会反过来，
       而接口返回 200、日志一片正常 —— 这种 bug 最难查。
    """
    todos_router.create_todo(TodoCreate(title="买牛奶"))

    fake_model([
        wants_tool("call_1", "set_done", '{"id":1,"done":true}'),
        wants_tool("call_2", "set_done", '{"id":1,"done":true}'),   # 同一件事再做一遍
        says("好了"),
    ])

    result = ai_agent.run_agent("把买牛奶标成完成", "fake-key")

    assert all(a.ok for a in result.actions)
    # 执行了两遍，但状态仍然是 True —— 这就是幂等
    assert todos_router.read_todos()[0]["done"] is True


def test_set_done_can_also_clear_the_flag(fake_model):
    """toggle 表达不出的那个方向：明确改回未完成"""
    todos_router.create_todo(TodoCreate(title="买牛奶"))
    todos_router.set_done(1, True)

    fake_model([
        wants_tool("call_1", "set_done", '{"id":1,"done":false}'),
        says("改回未完成了"),
    ])

    result = ai_agent.run_agent("买牛奶其实还没买，改回未完成", "fake-key")

    assert result.actions[0].ok is True
    assert todos_router.read_todos()[0]["done"] is False


def test_plain_chat_does_not_use_tools(fake_model):
    """闲聊不该调工具 —— 一轮就结束"""
    calls = fake_model([says("我是待办助手")])

    result = ai_agent.run_agent("你是谁", "fake-key")

    assert result.turns == 1
    assert result.actions == []
    assert len(calls) == 1


# ============================================================
#  ⭐ 上下文完整性：这几条最容易写错
# ============================================================

def test_assistant_message_is_kept_and_reasoning_is_dropped(fake_model):
    """第二轮请求里必须带着第一轮那条 assistant，但不能带思考原文"""
    calls = fake_model([
        wants_tool("call_1", "create_todo", '{"title":"买牛奶"}'),
        says("好了"),
    ])

    ai_agent.run_agent("加买牛奶", "fake-key")

    second = calls[1]
    assistant = [m for m in second if m.get("role") == "assistant"]

    assert len(assistant) == 1, "没把模型的 tool_calls 消息放回去，上下文就断了"
    assert assistant[0]["tool_calls"][0]["id"] == "call_1"

    # ⚠️ reasoning_content 是给我们看的，回传既费 token，
    #    某些模型还会直接 400。
    assert "reasoning_content" not in assistant[0]


def test_tool_message_carries_matching_call_id(fake_model):
    """tool 消息必须指回它对应哪次调用"""
    calls = fake_model([
        wants_tool("call_zzz", "create_todo", '{"title":"买牛奶"}'),
        says("好了"),
    ])

    ai_agent.run_agent("加买牛奶", "fake-key")

    msgs = tool_msgs(calls[1])
    assert len(msgs) == 1
    assert msgs[0]["tool_call_id"] == "call_zzz"


# ============================================================
#  ⭐ 失败路径：模型能改的 → 喂回去
# ============================================================

def test_bad_json_arguments_are_fed_back(fake_model):
    """arguments 不是合法 JSON → 不能崩，要把错误告诉模型让它重写"""
    calls = fake_model([
        wants_tool("call_1", "create_todo", "{标题: 买牛奶"),   # 没引号、没闭合
        says("抱歉我重来"),
    ])

    result = ai_agent.run_agent("加买牛奶", "fake-key")

    assert result.actions[0].ok is False
    assert "不是合法 JSON" in result.actions[0].detail

    # 错误信息必须真的进了第二轮请求
    assert "不是合法 JSON" in tool_msgs(calls[1])[-1]["content"]
    # 而且一条任务都没建成
    assert todos_router.read_todos() == []


def test_missing_title_is_fed_back(fake_model):
    """缺必填参数 → 错误信息里必须带字段名，否则模型不知道改哪"""
    calls = fake_model([
        wants_tool("call_1", "create_todo", "{}"),
        says("我再试"),
    ])

    result = ai_agent.run_agent("加一条", "fake-key")

    assert result.actions[0].ok is False
    fed_back = tool_msgs(calls[1])[-1]["content"]
    assert "参数不合法" in fed_back
    assert "title" in fed_back          # ← 字段名是关键
    assert todos_router.read_todos() == []


def test_unknown_tool_is_fed_back_with_the_available_list(fake_model):
    """⭐ 模型想调一个不存在的工具 → 拒绝，并告诉它有哪些可用"""
    calls = fake_model([
        wants_tool("call_1", "delete_todo", '{"id":1}'),
        says("我没有删除权限"),
    ])

    todos_router.create_todo(TodoCreate(title="买牛奶"))

    result = ai_agent.run_agent("把买牛奶删掉", "fake-key")

    assert result.actions[0].ok is False
    assert "没有名为 delete_todo 的工具" in result.actions[0].detail

    fed_back = tool_msgs(calls[1])[-1]["content"]
    assert "list_todos" in fed_back and "create_todo" in fed_back

    # ⭐⭐ 最重要的一条断言：东西还在。
    #    模型"想删"和"删掉了"是完全不同的两件事，
    #    这个测试就是把这条界线钉住。
    assert len(todos_router.read_todos()) == 1


def test_set_done_missing_id_is_fed_back(fake_model):
    """id 不存在（404）→ 这是模型能改的错，喂回去"""
    calls = fake_model([
        wants_tool("call_1", "set_done", '{"id":999,"done":true}'),
        says("没找到这条"),
    ])

    result = ai_agent.run_agent("把 999 标成完成", "fake-key")

    assert result.actions[0].ok is False
    assert "不存在" in tool_msgs(calls[1])[-1]["content"]


def test_wrong_argument_type_is_fed_back(fake_model):
    """id 给了个字符串 → Pydantic 拦下，喂回去"""
    fake_model([
        wants_tool("call_1", "set_done", '{"id":"第一件","done":true}'),
        says("我需要一个数字 id"),
    ])

    result = ai_agent.run_agent("标成完成", "fake-key")

    assert result.actions[0].ok is False
    assert "参数不合法" in result.actions[0].detail


# ============================================================
#  ⭐ 系统故障：模型改不了的 → 抛出去
# ============================================================

def test_system_error_is_raised_not_swallowed(fake_model, monkeypatch):
    """数据库级别的故障必须抛出去（→ 500），不能当成"模型的错"

    ⚠️ 如果这里被喂回去，模型会以为是自己参数不对，
       开始一轮一轮地改参数重试 —— 而故障在我们这边，
       它改一百次也没用，只会把用户的 60 秒 × 5 白白烧掉。
    """
    fake_model([wants_tool("call_1", "create_todo", '{"title":"买牛奶"}')])

    def broken_create(todo):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(todos_router, "create_todo", broken_create)

    with pytest.raises(RuntimeError, match="database is locked"):
        ai_agent.run_agent("加买牛奶", "fake-key")


# ============================================================
#  ⭐ 轮次上限：两种"没做完"必须分开
# ============================================================

def test_truncated_when_turns_run_out(fake_model):
    """5 轮都成功，只是话没说完 → 200 + truncated，不是异常"""
    fake_model([
        wants_tool(f"call_{i}", "create_todo", f'{{"title":"任务{i}"}}')
        for i in range(ai_agent.MAX_TURNS)
    ])

    result = ai_agent.run_agent("建 5 条", "fake-key")

    assert result.truncated is True
    assert result.turns == ai_agent.MAX_TURNS
    assert len(result.actions) == ai_agent.MAX_TURNS
    assert all(a.ok for a in result.actions)
    # 5 条都真的建了 —— 部分成功也是成功，不能回滚
    assert len(todos_router.read_todos()) == 5


def test_all_failed_raises_agent_failed(fake_model):
    """5 轮一次都没成功 → 这不是"部分成功"，是彻底的失败 → AgentFailed"""
    fake_model([
        wants_tool(f"call_{i}", "no_such_tool", "{}")
        for i in range(ai_agent.MAX_TURNS)
    ])

    with pytest.raises(ai_agent.AgentFailed):
        ai_agent.run_agent("随便", "fake-key")


def test_never_exceeds_max_turns(fake_model):
    """⭐ 绝对不能多问一次 —— 多一次就是多一份账单"""
    calls = fake_model([
        wants_tool(f"call_{i}", "create_todo", f'{{"title":"任务{i}"}}')
        for i in range(ai_agent.MAX_TURNS)
    ])

    ai_agent.run_agent("建很多条", "fake-key")

    # 准备的响应数正好是 MAX_TURNS 条：如果循环多问一次，
    # fake_chat 里那句 raise AssertionError 会响。
    assert len(calls) == ai_agent.MAX_TURNS


# ============================================================
#  ⭐ 两张表的一致性 + 最小权限
# ============================================================

def test_schema_and_table_declare_the_same_tools():
    """给模型看的说明书，和我们真正能执行的表，必须是同一批名字

    ⚠️ 只加了 schema 没加实现 → 模型会调一个我们执行不了的工具
       只加了实现没加 schema → 那段代码永远不会被调用（死代码）
       两边不一致时【不会报错】，只会表现为"AI 好像有点笨"。
    """
    declared = {t["function"]["name"] for t in ai_agent.TOOL_SCHEMAS}
    implemented = set(ai_agent.TOOL_TABLE)
    assert declared == implemented


def test_delete_is_only_ever_proposed():
    """⭐ 锁住"最小权限"这个决定。

    8.6 的结论是：模型【可以提议】删除，但【不能执行】删除。
    所以这张表里应该有一个 request_delete，而永远不该有 delete_todo。

    ⚠️ 将来谁想给模型真正的删除能力，会先在这里被拦下来 ——
       然后他必须面对这个问题：用户点确认了吗？
    """
    names = {t["function"]["name"] for t in ai_agent.TOOL_SCHEMAS}

    # 真正会毁掉数据的那个，不存在
    assert "delete_todo" not in names
    # 只能提议的那个，存在
    assert "request_delete" in names


def test_request_delete_does_not_delete(fake_model):
    """⭐⭐ 最重要的一条：模型请求删除之后，数据必须还在。

    "它想删"和"它删掉了"是两件事。这条测试把它们分开钉住。
    """
    todos_router.create_todo(TodoCreate(title="买牛奶"))

    fake_model([
        wants_tool("call_1", "request_delete", '{"id":1}'),
        says("我找到了《买牛奶》，确认要删吗"),
    ])

    result = ai_agent.run_agent("把买牛奶删掉", "fake-key")

    # 请求提交成功
    assert result.actions[0].ok is True
    assert "等你确认" in result.actions[0].detail

    # 但一条都没少
    remaining = todos_router.read_todos()
    assert len(remaining) == 1

    # 而且它进的是 proposals，不是 actions
    assert [p.id for p in result.proposals] == [1]
    assert result.proposals[0].title == "买牛奶"


def test_request_delete_missing_id_is_fed_back(fake_model):
    """想删一个不存在的 id → 404 → 喂回去让它查真实 id"""
    calls = fake_model([
        wants_tool("call_1", "request_delete", '{"id":999}'),
        says("没找到这条"),
    ])

    result = ai_agent.run_agent("删掉 999", "fake-key")

    assert result.actions[0].ok is False
    assert result.proposals == []
    assert "不存在" in tool_msgs(calls[1])[-1]["content"]


def test_every_tool_schema_has_a_description():
    """description 不是注释，是给模型看的说明书 —— 空着它就只能瞎猜"""
    for tool in ai_agent.TOOL_SCHEMAS:
        fn = tool["function"]
        assert fn.get("description", "").strip(), f"{fn['name']} 没有 description"
        assert "parameters" in fn


# ============================================================
#  ⑩ 多轮记忆
#
#  ⭐ 这一组测的是"记忆"能带来的那个效果本身：
#     第二句话能不能接上第一句。
#
#  ⚠️ 注意这里的断言方式和别的测试不一样：
#     别的测试断言"结果对不对"，这里断言【模型第二次看到了什么】。
#     因为"记得"这个能力不在模型里，也不在我们的返回值里 ——
#     它只存在于"我们发过去的 messages 里"。
#     所以唯一的验证方式就是：把那个 messages 抓下来看。
# ============================================================

def test_first_call_creates_a_conversation(fake_model):
    fake_model([says("好的。")])

    result = ai_agent.run_agent("随便说一句", "fake-key")

    assert len(result.conversation_id) == 32      # uuid4().hex
    # 而且真的落库了，不只是返回了一个字符串
    assert conversations.load(result.conversation_id) is not None


def test_second_turn_sees_the_first_turn(fake_model):
    """⭐⭐ 多轮记忆的核心断言。

    第一轮说"第一句话"，第二轮只说"第二句话"——
    模型第二轮的请求里，必须能同时看到【第一句】和【它的回答】。
    看不到，它就是个失忆的助手。
    """
    calls = fake_model([says("收到第一句。"), says("收到第二句。")])

    first = ai_agent.run_agent("第一句话", "fake-key")
    second = ai_agent.run_agent(
        "第二句话", "fake-key", conversation_id=first.conversation_id
    )

    assert second.conversation_id == first.conversation_id

    # 第二次请求实际发出去的 messages
    sent = calls[1]
    contents = [m.get("content") for m in sent]

    assert "第一句话" in contents
    assert "收到第一句。" in contents
    assert "第二句话" in contents           # 新的一句也在

    # 而且顺序是：system → 历史 → 新的 user
    assert sent[0]["role"] == "system"
    assert sent[-1] == {"role": "user", "content": "第二句话"}


def test_different_conversations_do_not_see_each_other(fake_model):
    """⚠️ 记忆最容易出的泄漏：A 的对话跑到 B 的请求里。

       我们这里每个会话是一行独立记录，按 id 取，
       但"忘了传 id"或"传了默认值"都会导致串话。
    """
    calls = fake_model([says("A 的回答"), says("B 的回答")])

    a = ai_agent.run_agent("苹果", "fake-key")     # 不给 id → 新会话
    b = ai_agent.run_agent("香蕉", "fake-key")     # 又新开一个

    assert a.conversation_id != b.conversation_id

    sent_b = [m.get("content") for m in calls[1]]
    assert "苹果" not in sent_b
    assert "A 的回答" not in sent_b


def test_system_prompt_is_never_stored(fake_model):
    """⭐⭐ system prompt 里含【今天的日期】，存进库明天就是错的。

       这是我们 8.2 修过的坑，换了个地方不能复发。
    """
    fake_model([says("嗯。")])

    result = ai_agent.run_agent("随便", "fake-key")
    stored = conversations.load(result.conversation_id)

    assert all(m["role"] != "system" for m in stored)
    # 库里的第一条应该是用户说的话
    assert stored[0] == {"role": "user", "content": "随便"}


def test_history_keeps_tool_calls_and_receipts(fake_model):
    """历史里必须同时有 assistant(tool_calls) 和 tool 回执。

    ⭐ 少任何一样，下一轮模型就不知道"#1 是哪来的"，
       或者协议直接 400。
    """
    fake_model([
        wants_tool("call_1", "create_todo", '{"title": "买牛奶"}'),
        says("已创建"),
    ])

    result = ai_agent.run_agent("买牛奶", "fake-key")
    stored = conversations.load(result.conversation_id)

    assert [m["role"] for m in stored] == ["user", "assistant", "tool", "assistant"]
    assert stored[1]["tool_calls"][0]["id"] == "call_1"
    assert stored[2]["tool_call_id"] == "call_1"
    # 工具的真实结果也在里面 —— 这就是模型下一轮"知道"#1 存在的唯一原因
    assert "买牛奶" in stored[2]["content"]

    # ⚠️ 思考原文不能存：白占 token，某些模型还会直接 400
    assert "reasoning_content" not in stored[1]


def test_only_the_last_three_turns_are_kept(fake_model):
    """说 4 句，只留最近 3 句。第 1 句应该被挤出去。"""
    fake_model([says("a"), says("b"), says("c"), says("d")])

    cid = None
    for text in ["第1句", "第2句", "第3句", "第4句"]:
        result = ai_agent.run_agent(text, "fake-key", conversation_id=cid)
        cid = result.conversation_id

    stored = conversations.load(cid)
    said = [m["content"] for m in stored if m["role"] == "user"]

    assert said == ["第2句", "第3句", "第4句"]


def test_incomplete_tool_group_is_not_stored(fake_model, monkeypatch):
    """⭐⭐ 最难想到的一种坏数据。

       工具执行到一半，代码抛了【系统级】异常（不是"模型能改"的那种）。
       这时 messages 里已经有 assistant(tool_calls)，但 tool 回执还没 append。

       如果原样存进去，这份历史明天打开时就会 400。
       所以存之前必须洗一遍。
    """
    def broken_create(payload):
        raise RuntimeError("database is locked（模拟）")

    monkeypatch.setattr(todos_router, "create_todo", broken_create)
    fake_model([wants_tool("call_x", "create_todo", '{"title": "买牛奶"}')])

    with pytest.raises(RuntimeError):
        ai_agent.run_agent("买牛奶", "fake-key", conversation_id="fixed-cid")

    stored = conversations.load("fixed-cid")

    assert stored is not None            # 历史还是存了（用户那句话得留下）
    assert all(m["role"] != "tool" for m in stored)
    assert all(not m.get("tool_calls") for m in stored)
    assert [m["content"] for m in stored] == ["买牛奶"]

    # ⭐ 最关键的一步：这份洗过的历史必须【真的能再发一次】。
    #    只断言"少了坏东西"是不够的 —— 得证明剩下的东西是能用的。
    fake_model([says("好的，再来一次。")])
    again = ai_agent.run_agent("再说一次", "fake-key", conversation_id="fixed-cid")

    assert again.conversation_id == "fixed-cid"
    assert again.reply == "好的，再来一次。"
