"""
tests/test_conversations.py —— 测"记忆"的存储层（不碰模型，也不花钱）

============================================================
⭐ 这个文件测的是最底层，也是最容易悄悄坏掉的一层。

    上层的测试会告诉你"第二句话接上了第一句"，
    但如果 trim 把一个工具调用切成了两半，那种错误
    在【第一次】对话里完全看不出来 —— 要等第二天重新打开会话才 400。

    ⚠️ 那种 bug 最难查，因为：
        · 出问题时你早就忘了当时改了什么
        · 报错信息说的是协议，不是你的代码
        · 它只在"历史足够长"的时候才出现

    所以这里专门把"存"和"截断"单独钉死。

============================================================
跑法（在 todo-app 目录下）：
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_conversations.py -v
"""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import database

# ⚠️ 必须在 import conversations 之前改 DB_FILE。
#    （conversations 里是 `from database import get_connection`，
#      get_connection 读的是 database 模块里的全局 DB_FILE，
#      所以这里换了之后它也跟着换 —— 但顺序还是别赌。）
test_dir = Path(__file__).resolve().parent / "_tmp_conversations"
shutil.rmtree(test_dir, ignore_errors=True)
test_dir.mkdir(parents=True, exist_ok=True)
database.DB_FILE = test_dir / "test.db"

import conversations  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    database.init_db()
    conn = database.get_connection()
    conn.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()
    yield


def teardown_module(module):
    shutil.rmtree(test_dir, ignore_errors=True)


# ============================================================
#  小工具
# ============================================================

def _iso(hours_ago: float = 0) -> str:
    """造一个 ISO 时间字符串。hours_ago=25 表示"25 小时前"。"""
    moment = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return moment.isoformat(timespec="seconds")


def _insert_raw(cid: str, messages: list[dict], updated_at: str) -> None:
    """绕过 save() 直接写一行。

    ⭐ 为什么需要它？因为 save() 永远写"现在"这个时间，
       而"过期"这个行为必须用【过去的时间】才测得到。
       测试需要造出正常路径造不出来的数据。
    """
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO conversations (id, messages, created_at, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (cid, json.dumps(messages, ensure_ascii=False), updated_at, updated_at),
    )
    conn.commit()
    conn.close()


def _turn(i: int) -> list[dict]:
    """造一轮完整的对话：user → assistant(要调工具) → tool → assistant(回复)。

    ⭐ 重点是这一轮【有四条消息】，而不是两条。
       这正是"按条数截断"会出错、"按轮次截断"才对的原因。
    """
    return [
        {"role": "user", "content": f"第{i}句"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": "list_todos", "arguments": "{}"},
            }],
        },
        {"role": "tool", "tool_call_id": f"call_{i}", "content": "查到了"},
        {"role": "assistant", "content": f"回复{i}"},
    ]


def _assert_protocol_valid(messages: list[dict]) -> None:
    """检查这份 messages 能不能被【原样再发一次】。

    ⭐ 这条断言比"内容对不对"重要得多：
       内容错了，模型会答得不对（用户能看出来）；
       协议错了，下一次请求直接 400，整个会话报废。
    """
    pending: set[str] = set()

    for m in messages:
        role = m.get("role")

        if role == "assistant" and m.get("tool_calls"):
            pending |= {c["id"] for c in m["tool_calls"]}

        elif role == "tool":
            assert m["tool_call_id"] in pending, (
                f"tool 消息 {m['tool_call_id']} 找不到它的来源调用 —— 这一组被切开了"
            )
            pending.discard(m["tool_call_id"])

        elif role == "user":
            assert not pending, "上一轮的调用还没回执，就开始了新一轮"

        elif role == "assistant":
            assert not pending, "assistant 说话时，上一批调用还没回执"

    assert not pending, "最后有一条调用永远没等到回执"


# ============================================================
#  存取
# ============================================================

def test_save_then_load_roundtrip():
    messages = _turn(1)
    conversations.save("c1", messages)

    loaded = conversations.load("c1")
    assert loaded == messages


def test_load_unknown_id_returns_none():
    assert conversations.load("从来没存在过") is None


def test_chinese_is_stored_readably():
    """⚠️ ensure_ascii=False：库里存的是中文本身，不是 \\u4e73\\u725b\\u5976。

    这只影响"人能不能直接看懂库里的内容"，
    但排查问题时这一点很值 —— 你得能 eyeball 它。
    """
    conversations.save("c1", [{"role": "user", "content": "买牛奶"}])

    conn = database.get_connection()
    raw = conn.execute(
        "SELECT messages FROM conversations WHERE id = 'c1'"
    ).fetchone()["messages"]
    conn.close()

    assert "买牛奶" in raw


def test_save_overwrites_previous_content():
    conversations.save("c1", [{"role": "user", "content": "第一版"}])
    conversations.save("c1", [{"role": "user", "content": "第二版"}])

    loaded = conversations.load("c1")
    assert loaded == [{"role": "user", "content": "第二版"}]

    # 只有一行 —— 是 UPDATE 不是又 INSERT 了一条
    conn = database.get_connection()
    count = conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
    conn.close()
    assert count == 1


def test_delete_returns_whether_it_existed():
    conversations.save("c1", [{"role": "user", "content": "嗯"}])

    assert conversations.delete("c1") is True
    assert conversations.delete("c1") is False   # 第二次就没了
    assert conversations.load("c1") is None


def test_new_id_is_random_and_long_enough():
    a, b = conversations.new_id(), conversations.new_id()

    assert a != b
    assert len(a) == 32          # uuid4().hex 的长度
    assert a.isalnum()


# ============================================================
#  过期
# ============================================================

def test_expired_conversation_reads_as_none():
    """25 小时前的会话，读出来应该是"不存在"。

    ⭐ 注意这里【没有删任何东西】—— 过期是"读的时候判断"的，
       不是"写的时候清掉的"。两件事都要有：
         · 读时判断 → 行为立刻正确（不会读到本该过期的数据）
         · 写时清理 → 表不会无限长（垃圾早晚被删掉）
    """
    _insert_raw("old", _turn(1), _iso(hours_ago=conversations.CONVERSATION_TTL_HOURS + 1))

    assert conversations.load("old") is None


def test_fresh_conversation_still_reads():
    """⚠️ 和上一个测试是一对。

       只有"过期读不到"的测试，那么"永远读不到"也能通过 ——
       那是把功能删掉，不是把它写对。
    """
    _insert_raw("new", _turn(1), _iso(hours_ago=1))

    assert conversations.load("new") == _turn(1)


def test_saving_purges_expired_rows():
    _insert_raw("old", _turn(1), _iso(hours_ago=conversations.CONVERSATION_TTL_HOURS + 1))
    conversations.save("fresh", [{"role": "user", "content": "新的"}])

    conn = database.get_connection()
    ids = {row["id"] for row in conn.execute("SELECT id FROM conversations")}
    conn.close()

    assert "old" not in ids
    assert "fresh" in ids


# ============================================================
#  截断 ← 本文件最重要的一组
# ============================================================

def test_trim_keeps_only_the_last_three_turns():
    messages = _turn(1) + _turn(2) + _turn(3) + _turn(4) + _turn(5)

    trimmed = conversations.trim(messages, max_turns=3)

    assert trimmed[0] == {"role": "user", "content": "第3句"}
    assert len(trimmed) == 12        # 3 轮 × 每轮 4 条


def test_trim_never_splits_a_tool_group():
    """⭐ 这是整个模块存在的理由。

       如果按【消息条数】截断（比如"只留最后 10 条"），
       切开的位置很可能落在 assistant(tool_calls) 和 tool 之间 ——
       那份历史再发出去，上游直接 400。
    """
    messages = _turn(1) + _turn(2) + _turn(3) + _turn(4) + _turn(5)

    # 造一个"按条数截"会切坏的位置，确认按轮次截是安全的
    trimmed = conversations.trim(messages, max_turns=3)
    _assert_protocol_valid(trimmed)

    # 而且截断后的第一条必须是 user —— 一眼就能看出切在哪
    assert trimmed[0]["role"] == "user"


def test_trim_does_nothing_when_short_enough():
    messages = _turn(1) + _turn(2)

    trimmed = conversations.trim(messages, max_turns=3)

    assert trimmed == messages
    # ⚠️ 是副本不是同一个对象：调用方拿到之后随便改，都不会动到传进来的那个列表
    assert trimmed is not messages


def test_trim_with_zero_turns_returns_empty():
    assert conversations.trim(_turn(1), max_turns=0) == []


def test_trim_keeps_the_whole_longest_turn():
    """一轮里有 5 次工具调用（11 条消息）时，也不能被切开。"""
    long_turn = [{"role": "user", "content": "复杂的活"}]
    for i in range(5):
        long_turn.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": f"c{i}",
                "type": "function",
                "function": {"name": "list_todos", "arguments": "{}"},
            }],
        })
        long_turn.append({"role": "tool", "tool_call_id": f"c{i}", "content": "ok"})
    long_turn.append({"role": "assistant", "content": "做完了"})

    trimmed = conversations.trim(_turn(1) + long_turn, max_turns=1)

    assert trimmed == long_turn
    _assert_protocol_valid(trimmed)
