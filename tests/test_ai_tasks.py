"""
tests/test_ai_tasks.py —— 测"重试逻辑"和"日期规则"，但【不真的调模型】

============================================================
⭐ 核心思想：把模型调用【打桩】（mock / stub）。

    被测的：你的逻辑  → 什么时候重试、重试时喂回去什么、什么时候放弃
    隔离的：模型调用  → 随机、花钱、可能挂、无法复现

    一行就能换掉：
        monkeypatch.setattr(ai_tasks, "chat", 假的函数)

于是你可以【精确制造】任何情况：
    finish_reason = "length"      → 模拟截断
    content = "好的，以下是..."    → 模拟非法 JSON
    priority = "urgent"           → 模拟非法枚举值
    一直返回坏数据                  → 模拟重试用尽

好处：零成本（不花 token）、毫秒级、100% 可复现。

============================================================
⚠️ 这个文件原来是 test_ai_parse.py，测的是 ai_parse.py。
   8.3 把逻辑搬进 ai_tasks.py 之后，那些测试还在测一个【没人用的模块】——
   全绿，但完全没有保护到线上跑的那份代码。
   这种"测试还在、保护对象换了"的情况，比没有测试更危险。
   所以整个文件迁到了 ai_tasks：打桩点从 call_api 改成 chat，
   SystemExit 改成 ParseFailed。

============================================================
跑法（在 todo-app 目录下）：
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_ai_tasks.py -v
"""

import json

import pytest

import ai_tasks


def fake_response(content: str, finish: str = "stop") -> dict:
    """伪造一个"形状正确"的 DeepSeek 响应。"""
    return {
        "choices": [{
            "message": {"role": "assistant", "content": content},
            "finish_reason": finish,
        }],
        "usage": {"completion_tokens": 10, "prompt_tokens": 5},
    }


@pytest.fixture
def make_api(monkeypatch):
    """返回一个"装弹药"的函数：给它一串响应，它造一个假的 chat。

    返回的 calls 列表会记录每次请求的 messages —— 用来断言
    "第二次请求里到底带了什么"。
    """
    def _make(responses):
        calls = []

        def fake_chat(messages, api_key, **kwargs):
            # ⚠️⚠️ 这里必须【深拷贝】每一条 message。
            #
            #   parse_text 里的 messages 是一个不断 append 的【同一个列表】。
            #   如果直接 calls.append(messages)，那么 calls 里存的是同一个
            #   列表的引用 —— 等测试跑完，calls[0] 和 calls[1] 指向的东西
            #   完全一样，都是"最后那一版"。
            #
            #   于是 "第二次请求里含有错误信息" 这种断言会【永远成立】，
            #   哪怕代码根本没有把错误喂回去。测试假绿，比没有测试更糟。
            calls.append([dict(m) for m in messages])

            if not responses:
                raise AssertionError("假 chat 被调用次数超过了准备的响应数")
            return responses.pop(0)

        monkeypatch.setattr(ai_tasks, "chat", fake_chat)
        return calls

    return _make


# ============================================================
#  正常路径
# ============================================================

def test_success_first_try(make_api):
    """一次就对 —— 只应该调一次模型"""
    calls = make_api([
        fake_response('{"tasks":[{"title":"交周报","priority":"high","due":null}]}'),
    ])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 1
    assert len(result.tasks) == 1
    assert result.tasks[0].title == "交周报"


# ============================================================
#  ⭐ 重试路径（这些分支在真实调用里从没跑到过）
# ============================================================

def test_retry_after_invalid_priority(make_api):
    """模型给了非法枚举值 → 应该重试，并且把【具体错误】喂回去"""
    calls = make_api([
        fake_response('{"tasks":[{"title":"x","priority":"urgent","due":null}]}'),
        fake_response('{"tasks":[{"title":"x","priority":"high","due":null}]}'),
    ])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 2
    assert result.tasks[0].priority == "high"

    # ⭐⭐ 最关键的断言：
    #    第二次请求的 messages 里，必须带着上一次的【具体错误】。
    #    如果只喂回去一句"出错了请重试"，模型根本不知道该改哪里 ——
    #    错误信息的精度，就是重试的胜率。
    feedback = " ".join(m["content"] for m in calls[1])
    assert "priority 只能是" in feedback, "重试时没告诉模型字段规则"
    assert "urgent" in feedback, "重试时没告诉模型它实际给了什么"


def test_retry_after_truncation(make_api):
    """finish_reason=length → 应该重试，并说明"被截断了" """
    calls = make_api([
        fake_response('{"tasks":[{"title":"被截', finish="length"),
        fake_response('{"tasks":[{"title":"完整","priority":"normal","due":null}]}'),
    ])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 2
    assert result.tasks[0].title == "完整"

    feedback = " ".join(m["content"] for m in calls[1])
    assert "截断" in feedback, "截断后没告诉模型原因"


def test_retry_after_bad_json(make_api):
    """模型加了 markdown 围栏和解释文字 → 应该重试"""
    calls = make_api([
        fake_response("好的，以下是任务：\n```json\n{}\n```"),
        fake_response('{"tasks":[{"title":"x","priority":"low","due":null}]}'),
    ])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 2
    assert result.tasks[0].title == "x"


def test_retry_after_too_many_tasks(make_api):
    """任务数量超过上限（20）→ 应该被拒并重试"""
    too_many = json.dumps({
        "tasks": [{"title": f"任务{i}", "priority": "normal", "due": None}
                  for i in range(21)]
    })
    calls = make_api([fake_response(too_many), fake_response('{"tasks":[]}')])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 2
    assert result.tasks == []


# ============================================================
#  ⭐ 日期规则：过去 ≠ 错误
# ============================================================

def test_past_due_within_a_year_is_accepted(make_api):
    """⭐ 近期的过去日期是【合法】的 —— 逾期任务真实存在

    这条测试锁住的是一个真实的坑：
        以前规则是"早于今天就算错"，于是「昨天要交的作业」
        被逼着把 due 填成 null，界面上就永远看不到"已逾期"。
        而它恰恰最该被标红。
    """
    calls = make_api([
        fake_response('{"tasks":[{"title":"补交作业","priority":"normal","due":"2026-11-05"}]}'),
    ])

    result = ai_tasks.parse_text("昨天要交的作业", "fake-key")

    # 只调一次 —— 说明没有被判定为"非法"而打回重试
    assert len(calls) == 1
    assert result.tasks[0].due is not None
    assert result.tasks[0].due < ai_tasks.date.today()


def test_retry_after_absurd_past_due(make_api):
    """一年前的日期 → 几乎一定是模型算飞了，应该拒绝并重试

    ⚠️ 这条和上一条是一对，缺一不可：
       只留上一条 → 模型把"周五"算成 2025 年也能通过
       只留下一条 → 合法的逾期任务被误杀
       规则的边界在哪，测试就该在哪画线。
    """
    calls = make_api([
        fake_response('{"tasks":[{"title":"x","priority":"normal","due":"2000-01-01"}]}'),
        fake_response('{"tasks":[]}'),
    ])

    result = ai_tasks.parse_text("随便", "fake-key")

    assert len(calls) == 2
    assert result.tasks == []


# ============================================================
#  放弃路径：必须"明确失败"，绝不假装成功
# ============================================================

def test_gives_up_after_max_attempts(make_api):
    """模型一直不听话 → 重试次数用完必须抛错，不能返回空结果糊弄过去"""
    bad = '{"tasks":[{"title":"x","priority":"urgent","due":null}]}'
    calls = make_api([fake_response(bad) for _ in range(ai_tasks.MAX_ATTEMPTS)])

    with pytest.raises(ai_tasks.ParseFailed):
        ai_tasks.parse_text("随便", "fake-key")

    # ⭐ 必须正好调了 MAX_ATTEMPTS 次 —— 多一次就是烧钱
    assert len(calls) == ai_tasks.MAX_ATTEMPTS
