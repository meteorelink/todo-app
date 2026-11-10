"""
conversations.py —— 多轮对话的存储（"记忆"到底存在哪）

============================================================
⭐ 先说清楚一件容易误会的事：

    【模型什么都不记得。】

    它之所以能接上"那另一条呢"，唯一的原因是：
    上一次的 messages 又出现在了这一次的请求里。

    所以"给 agent 加记忆"在代码里就是一句话：

        messages = [system] + 上次的 messages + [这次的 user]

    这个文件干的活，就是把"上次的 messages"存起来、取出来。

============================================================
⭐ 存的是什么？（这一点很容易搞错）

    不是"用户说过的话"，是【完整的 messages 数组】，包括：

        {"role": "user",      "content": "把买牛奶加进去"}
        {"role": "assistant", "content": "", "tool_calls": [...]}   ← 它说要调什么
        {"role": "tool",      "tool_call_id": "call_1", "content": "已创建 #36"}  ← 结果

    少存哪一样，下一轮就是残的：
      · 少 tool_calls → 模型不知道"#36 是哪来的"
      · 少 tool 回执  → 协议不合规，下次请求直接 400

⭐⭐ 但 system 那条【绝对不能存】。

    它里面有一句「今天是 {date.today()}」。
    存进来，明天打开这个会话，模型看到的就是昨天的日期 ——
    这正是 8.2 我们花了一整轮才修掉的那个 bug，换了个地方复发。

    所以：库里永远没有 system，每次请求现拼一条新的。

============================================================
⭐ 为什么用 SQLite 而不是一个全局 dict？

    内存 dict 三行就能写完，但：
      · 重启 → 没了
      · 改一行代码触发 --reload → 没了
      · --workers 2 → 两个进程各存各的，用户会觉得"时好时坏"

    最后一条最坑：你会分不清"记忆功能坏了"和"进程换了一个"。

============================================================
⭐ 为什么一整段 JSON 塞一列，而不是建 messages 表？

    正常的做法是 messages 表（一行一条消息，外键指向会话），
    好处是能按条查询、能单独删某一条。

    但我们其实【从不按条查】——每次都是"把整个会话读出来"。
    为这个需求建第二张表，只换来 JOIN 和更多代码。

    ⭐ 判断标准：**你将来会不会按这个维度查询？**
       不会，就别拆表。
       哪天要做"只删对话里某一条"或者"按工具名统计"，再拆也不迟。
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from database import get_connection

# ⚠️ 24 小时没动过的会话，视为过期。
#    对应"用户关掉页面，第二天再来"——他想要的是新对话，
#    而不是接着昨天的上下文继续说（那会很怪：模型突然提起昨天的事）。
CONVERSATION_TTL_HOURS = 24

# ⚠️ 只保留最近 3 个"用户轮次"。
#
#    为什么必须有上限？成本是【乘法】：
#      第 N 轮请求要重发前 N-1 轮的全部内容。
#      10 轮的对话，第 10 次请求的费用约等于前 10 次的总和。
#
#    ⚠️ 为什么是"轮次"而不是"条数"？
#      一轮可能包含 3 条消息（user → assistant+tool_calls → tool），
#      也可能包含 11 条（模型连调 5 次工具）。
#      按条数截，同样"留 10 条"，有时是 3 轮，有时是 1 轮，用户会觉得莫名其妙。
MAX_KEPT_TURNS = 3

_UPSERT = """
    INSERT INTO conversations (id, messages, created_at, updated_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        messages   = excluded.messages,
        updated_at = excluded.updated_at
"""


def new_id() -> str:
    """生成一个新的会话 id。

    ⭐ 用 uuid4 而不是自增数字：
       自增 id 会暴露"你是第几个用户"，而且别人从 1 开始猜就能翻别人的对话。
       uuid4 是 32 位十六进制随机串，猜不出来。
    """
    return uuid.uuid4().hex


def load(conversation_id: str) -> list[dict] | None:
    """取一个会话的历史消息。

    返回 None 表示"这个会话不存在 或 已经过期"——
    两种情况对调用方是同一件事：**从头开始**。
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT messages, updated_at FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    # ⭐ 过期检查放在【读】的时候，而不是只在写的时候清。
    #
    #    如果只在写入时清理，一个"半年没人动"的会话会一直留在表里，
    #    直到下一次有人保存东西才被扫掉 —— 期间它仍然可以读出来。
    #    那就等于没过期。
    updated = datetime.fromisoformat(row["updated_at"])
    if datetime.now(timezone.utc) - updated > timedelta(hours=CONVERSATION_TTL_HOURS):
        return None

    return json.loads(row["messages"])


def save(conversation_id: str, messages: list[dict]) -> None:
    """写入（或覆盖）一个会话的历史消息。"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ⭐ ensure_ascii=False：中文按原样存进去，不转成 \u4e73\u725b\u5976。
    #    这样直接用 sqlite 命令行 or DB 工具看，也能读得懂。
    payload = json.dumps(messages, ensure_ascii=False)

    cutoff = (
        datetime.fromisoformat(now) - timedelta(hours=CONVERSATION_TTL_HOURS)
    ).isoformat(timespec="seconds")

    conn = get_connection()
    try:
        conn.execute(_UPSERT, (conversation_id, payload, now, now))

        # 顺手清理过期会话。
        #
        # ⚠️ 真实系统会把这行放进定时任务（cron / 后台 worker），
        #    不该放在每次保存的热路径上。这里表很小，顺手做掉最简单。
        conn.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff,))

        conn.commit()
    finally:
        conn.close()


def delete(conversation_id: str) -> bool:
    """删掉一个会话。返回"真的删掉了"还是"本来就没有"。

    ⭐ 调用方通常不需要区分这两种情况 —— 用户点"新对话"，
       目的是"别再用这段历史了"，已经达到。
    """
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def trim(messages: list[dict], max_turns: int = MAX_KEPT_TURNS) -> list[dict]:
    """只保留最近 max_turns 个"用户轮次"。

    ⭐⭐ 这里是整个文件最容易写出 400 的地方，规则只有一条：

        【只在 user 消息前面切。】

    为什么？因为一轮对话长这样：

        user → assistant(tool_calls) → tool → assistant(tool_calls) → tool → assistant

    你要是从中间切，可能留下一条 tool 消息，而它对应的
    assistant(tool_calls) 已经被切掉了。下次请求上游直接报：

        An assistant message with 'tool_calls' must be followed by
        tool messages responding to each tool_call_id

    ⭐ 所以截断的粒度不是"消息"，是"轮次"。
       而"轮次"的唯一定义就是：从一条 user 消息开始。
    """
    if max_turns <= 0:
        return []

    user_at = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if len(user_at) <= max_turns:
        # 没超，原样返回。
        # ⚠️ 返回一个新的 list，不返回传进来的那个对象 ——
        #    避免调用方拿到之后 append，把库里的东西也一起改了（虽然不会，
        #    但"返回副本"是个不用解释的好习惯）。
        return list(messages)

    return messages[user_at[-max_turns]:]
