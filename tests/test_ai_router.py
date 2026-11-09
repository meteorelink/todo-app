"""
tests/test_ai_router.py —— 测 /ai/parse 的【五个边界】

============================================================
⭐ 这些测试【一次都不会调用真模型】——
   全部用 monkeypatch 把 parse_text / load_api_key 换成假函数。

   为什么必须打桩？三个理由，缺一不可：

     ① 花钱      每次真调用都有成本，而测试要能在 CI 里跑一万次
     ② 不确定    模型输出是随机的，拿它做断言 = 一个会自己变红的测试
     ③ 覆盖不到  ⭐ 这条最重要 ——
                 真实模型永远不会返回 401，也不会超时。
                 可那两个分支【必须】被测到，
                 否则它们和没写过一样（未执行的代码 = 未验证的代码）。

============================================================
跑法（在 todo-app 目录下）：

    python -m pytest tests/test_ai_router.py -v
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import database

# ⚠️ 必须在 import main 【之前】改 DB_FILE ——
#    main 在 import 时就会执行 init_db()，那一刻路径就定死了。
#    （又是"import 只执行一次"那个坑，这次我们主动避开它。）
#
# 为什么不用 tempfile.mkdtemp()？
#   它建在系统临时目录（C:\Users\...\Temp），而那个位置在沙盒里
#   建不了 sqlite 库（OperationalError: unable to open database file）。
#   放在仓库内 tests/_tmp_ai/ 下，稳定可写，测完在 teardown 里删掉。
_TEST_DIR = Path(__file__).resolve().parent / "_tmp_ai"
_TEST_DIR.mkdir(exist_ok=True)
database.DB_FILE = _TEST_DIR / "test.db"

from ai_client import AIConfigError, AITimeoutError, AIUpstreamError  # noqa: E402
from ai_tasks import ParseFailed, ParseResult, Task  # noqa: E402
from routers import ai as ai_router  # noqa: E402

import main  # noqa: E402


client = TestClient(main.app)


def teardown_module(module):
    """整个文件跑完后清掉临时库。

    删不掉也无所谓（Windows 上偶发文件占用），
    tests/_tmp_ai/ 已经在 .gitignore 里，不会被提交。
    """
    for f in _TEST_DIR.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        _TEST_DIR.rmdir()
    except OSError:
        pass


# ============================================================
#  ⭐ autouse 兜底：任何测试都不许摸到真模型
#
#  这个 fixture 把 parse_text 换成一个【一调就炸】的函数。
#  于是"某个测试忘了打桩，结果悄悄花了钱"这种事不可能发生 ——
#  它会直接 AssertionError。
#
#  ⭐ 这叫"失败要响"。默认状态是"禁止"，需要时才显式打开。
# ============================================================

@pytest.fixture(autouse=True)
def forbid_real_model(monkeypatch):
    monkeypatch.setattr(ai_router, "load_api_key", lambda: "fake-key")

    def boom(*args, **kwargs):
        raise AssertionError("测试里不允许真的调用模型 —— 请先打桩")

    monkeypatch.setattr(ai_router, "parse_text", boom)


# ============================================================
#  ① 成功路径
# ============================================================

def test_returns_tasks(monkeypatch):
    """有任务 → 200，且 date 被序列化成 "YYYY-MM-DD"。"""
    fake = ParseResult(
        tasks=[Task(title="交实验报告", priority="high", due=date(2030, 1, 1))],
        note=None,
    )
    monkeypatch.setattr(ai_router, "parse_text", lambda text, key: fake)

    r = client.post("/ai/parse", json={"text": "2030 年 1 月 1 日前交实验报告"})

    assert r.status_code == 200
    body = r.json()
    assert body["tasks"][0]["title"] == "交实验报告"
    assert body["tasks"][0]["priority"] == "high"
    # ⭐ 断言的是【字符串】——response_model 把 date 对象转成了 ISO 文本
    assert body["tasks"][0]["due"] == "2030-01-01"
    assert body["note"] is None


def test_empty_result_is_200_not_4xx(monkeypatch):
    """⭐ 本文件最重要的一条：空结果必须是 200。

    "这句话里没有任务" 是一个【成功的分析结论】，不是错误。
    如果哪天有人"顺手"把它改成 404 / 422，这条测试会立刻变红。
    """
    fake = ParseResult(tasks=[], note="只是闲聊天气，没有提到待办事项")
    monkeypatch.setattr(ai_router, "parse_text", lambda text, key: fake)

    r = client.post("/ai/parse", json={"text": "今天天气真好"})

    assert r.status_code == 200            # ← 不是 4xx
    body = r.json()
    assert body["tasks"] == []
    assert body["note"] == "只是闲聊天气，没有提到待办事项"


# ============================================================
#  ② 内部异常 → HTTP 状态码（并且不泄露细节）
# ============================================================

def test_parse_failed_is_502(monkeypatch):
    """模型多次输出不合法 → 502（上游没按约定输出）。"""
    def boom(text, key):
        raise ParseFailed("重试 3 次仍未通过校验。最后一次的错误：priority 只能是 [...]")

    monkeypatch.setattr(ai_router, "parse_text", boom)

    r = client.post("/ai/parse", json={"text": "周五前交周报"})

    assert r.status_code == 502
    assert "priority" not in r.text        # 内部细节不外流
    assert "换个说法" in r.text            # 但给了用户可行动的建议


def test_timeout_is_504(monkeypatch):
    """超时 → 504。"""
    def boom(text, key):
        raise AITimeoutError("请求失败或超时：timed out")

    monkeypatch.setattr(ai_router, "parse_text", boom)

    r = client.post("/ai/parse", json={"text": "周五前交周报"})

    assert r.status_code == 504
    assert "timed out" not in r.text


def test_upstream_error_is_502_and_hides_secrets(monkeypatch):
    """⭐ 信息边界测试：上游错误的原文绝不能出现在响应体里。

    这条测试的价值不在"现在是对的"，而在【锁住】：
    一旦以后有人为了"方便排查"把 str(e) 塞进 detail，它立刻变红。
    """
    leaky = ('HTTP 401: {"error":{"message":"Authentication Fails, '
             'Your api key: sk-secret-123 is invalid"}}')

    def boom(text, key):
        raise AIUpstreamError(leaky)

    monkeypatch.setattr(ai_router, "parse_text", boom)

    r = client.post("/ai/parse", json={"text": "周五前交周报"})

    assert r.status_code == 502

    # ⭐ 逐个检查不该出现的关键词
    for word in ["401", "api key", "sk-secret-123", "Authentication"]:
        assert word.lower() not in r.text.lower(), f"响应体泄露了 {word!r}：{r.text}"

    assert "暂时不可用" in r.text


def test_missing_config_is_503(monkeypatch):
    """没配 API key → 503，且不告诉用户缺的是哪个环境变量。"""
    def boom():
        raise AIConfigError("未设置 DEEPSEEK_API_KEY（请检查项目根目录的 .env）")

    monkeypatch.setattr(ai_router, "load_api_key", boom)

    r = client.post("/ai/parse", json={"text": "周五前交周报"})

    assert r.status_code == 503
    assert "DEEPSEEK" not in r.text
    assert ".env" not in r.text


# ============================================================
#  ③ 输入边界（结构性问题应该在【最外层】被拦下）
# ============================================================

def test_empty_text_is_422():
    r = client.post("/ai/parse", json={"text": ""})

    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "string_too_short"


def test_whitespace_only_is_422():
    """⭐ 验证 strip 真的在【约束检查之前】跑。

    如果 mode 写错了（写成 after），这里会变成 value_error 而不是
    string_too_short —— 两种错误结构会让前端多写一个分支。
    """
    r = client.post("/ai/parse", json={"text": "        "})

    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "string_too_short"


def test_too_long_is_422():
    r = client.post("/ai/parse", json={"text": "任" * 2001})

    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "string_too_long"


def test_max_length_boundary_passes(monkeypatch):
    """边界值 2000 应该【通过】—— 上一条是 2001 被拒。

    ⭐ 两条一起看，才证明边界画在哪：
       2000 → 通过
       2001 → 拒绝
    只测一边，你不知道边界是画在 2000 还是 5000。
    """
    monkeypatch.setattr(ai_router, "parse_text",
                        lambda text, key: ParseResult(tasks=[]))

    r = client.post("/ai/parse", json={"text": "任" * 2000})

    assert r.status_code == 200


def test_text_is_stripped_before_model(monkeypatch):
    """⭐ 验证模型收到的是【去空白后】的文本，不是原始文本。"""
    seen = {}

    def fake(text, key):
        seen["text"] = text
        return ParseResult(tasks=[])

    monkeypatch.setattr(ai_router, "parse_text", fake)

    client.post("/ai/parse", json={"text": "  周五前交周报  "})

    assert seen["text"] == "周五前交周报"


# ============================================================
#  ④ 省钱测试：校验失败时绝不能调模型
# ============================================================

def test_invalid_input_never_reaches_the_model(monkeypatch):
    """⭐ 这条测试没有断言任何"结果"，它断言的是【什么都没发生】。

    一个空字符串如果走到了模型那里，就是一次白花的 API 调用。
    而这种浪费【不会报错、不会告警、看不出来】—— 只有测试能锁住它。
    """
    calls = []

    def fake(text, key):
        calls.append(text)
        return ParseResult(tasks=[])

    monkeypatch.setattr(ai_router, "parse_text", fake)

    r = client.post("/ai/parse", json={"text": ""})

    assert r.status_code == 422
    assert calls == []          # ← 一个字节都没发出去
