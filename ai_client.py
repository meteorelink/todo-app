"""
ai_client.py —— 和模型打交道的【传输层】

============================================================
它只做四件事：
    ① 读配置（API key）
    ② 发一次 HTTP 请求
    ③ 从响应里取出 content / finish_reason / usage
    ④ 把网络错误翻译成明确的异常

它【完全不知道】任何业务：
    不知道什么是"任务"，不知道 prompt 该怎么写，
    不知道什么算合法输出。那些在 ai_tasks.py 里。

⭐ 为什么单独一层？因为【换模型只改这里】。
   今天 DeepSeek，明天通义，改这一个文件，上面两层一行不动。

============================================================
⚠️ 和"写个脚本试试 API"（我们最早那份 ai_hello.py）最大的区别：
   脚本是【出错就 SystemExit】—— 退出程序，反正只有你一个人在看。
   本文件是【库】—— 出错就 raise 一个异常，让调用者决定怎么办。
   （ai_hello.py 已经在 8.3 完成后删掉了，git 历史里还能翻到。）

   为什么这个区别很关键？
       在 FastAPI 的路由函数里，SystemExit 继承自 BaseException，
       不会被 except Exception 捕获，很可能一路冒到 uvicorn 主循环，
       把【整个服务器进程】干掉 —— 一个用户的坏输入能打挂所有人。
"""

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv


# ============================================================
#  可调的旋钮
# ============================================================

URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
TEMPERATURE = 0        # 0 = 尽量确定（做结构化输出时必须）
TIMEOUT = 60           # 秒
MAX_TOKENS = 2000      # 限制的是【思考 + 回答】的总量


# ============================================================
#  异常体系
#
#  ⭐ 每一种失败都有对应的异常类型，调用者才能分别处理：
#       配置错  → 503（服务没准备好）
#       超时    → 504
#       上游错  → 502
#
#     如果只有一个笼统的 Exception，路由层就没法区分。
#     **异常的类型，就是错误分类的载体。**
# ============================================================

class AIError(Exception):
    """所有 AI 相关错误的基类。捕获它 = 捕获全部 AI 失败。"""


class AIConfigError(AIError):
    """配置问题（比如没设 API key）。属于【服务端没准备好】。"""


class AITimeoutError(AIError):
    """请求超时或网络不通。属于【上游太慢/不可达】。"""


class AIUpstreamError(AIError):
    """上游返回了 HTTP 错误（4xx/5xx）。属于【上游拒绝或出错】。"""


# ============================================================
#  ① 配置
# ============================================================

def load_api_key() -> str:
    """从 .env 读 API key。

    ⚠️ 没配 key 时 raise AIConfigError，而不是 SystemExit ——
       这样 FastAPI 能把它映射成 503，而不是让服务器退出。
    """
    load_dotenv()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise AIConfigError("未设置 DEEPSEEK_API_KEY（请检查项目根目录的 .env）")
    return key


# ============================================================
#  ② ③ 发送并返回原始响应 dict
# ============================================================

def chat(
    messages: list[dict],
    api_key: str,
    *,
    model: str = MODEL,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
    tools: list[dict] | None = None,
) -> dict:
    """发一次对话请求，返回解析后的响应 dict。

    ⭐ 参数是 messages（对话数组），不是整个 body ——
       把"API 的请求体长什么样"这件细节藏在这一层里面。

    ⭐ messages 由调用者维护 —— 因为重试时对话会变长，
       而"怎么变长"属于业务逻辑，不属于传输层。

    ⭐ tools：工具列表（8.5 新增）。不传就完全不出现这个字段 ——
       ⚠️ 是 `if tools is not None`，不是 `if tools`。
          区别在于：传空列表 [] 时，"有工具但一个都不给"这个意思
          也要如实发出去；用 truthy 判断会把它悄悄吞掉。
          （虽然这种情况下两者行为差不多，但"我传了什么就发什么"
            是传输层该守的规矩。）
    """
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if tools is not None:
        body["tools"] = tools
        # tool_choice 默认就是 "auto"（模型自己决定用不用、用哪个）。
        # 我们这里【不显式传】—— 让"想不想调工具"完全由模型判断。
        # 以后要做"必须调工具"（tool_choice="required"）再加参数。

    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.HTTPError as e:
        # 上游明确拒绝（401 key 错 / 402 没余额 / 429 太频繁 / 5xx 挂了）
        detail = e.read().decode("utf-8", errors="replace")
        # ⚠️ 注意：这个 detail 里可能含敏感信息，只能进【服务端日志】，
        #    绝不能直接返回给用户。
        raise AIUpstreamError(f"HTTP {e.code}: {detail[:500]}") from e

    except (urllib.error.URLError, TimeoutError) as e:
        # 连不上 / 超时
        raise AITimeoutError(f"请求失败或超时：{e}") from e


# ============================================================
#  ④ 从响应里取字段
#
#  ⭐ 这些小函数看着"没必要"，但它们把"响应长什么样"这个知识
#     收在了一个地方。以后 API 改结构，只改这里。
# ============================================================

def get_content_and_finish(data: dict) -> tuple[str, str | None]:
    """取出正文和结束原因。

    ⚠️ finish_reason 必须一起返回 ——
       调用者需要靠它判断"是不是被截断了"。
       （这是我们在 8.2 学到的：length 意味着 JSON 一定不完整）
    """
    choice = data["choices"][0]
    content = (choice["message"].get("content") or "").strip()
    return content, choice.get("finish_reason")


def get_usage(data: dict) -> dict:
    """取出用量（就是钱）。"""
    return data.get("usage", {})


def get_message(data: dict) -> dict:
    """取出整个 message 对象（8.5 新增）。

    ⭐ 为什么不能只用 get_content_and_finish()？

       工具调用的时候，模型那条 assistant 消息里带着 tool_calls 字段。
       下一轮请求【必须把这条消息原样放回 messages 里】，
       否则模型会问"我刚才说了什么？"——因为它看不到自己的调用请求，
       而你又发了一条 tool 结果过去，它就会觉得莫名其妙。

       ⚠️ "原样"三个字很重要：不要自己拼一个
          {"role":"assistant","content":"","tool_calls":[...]}，
          上游返回什么就放回什么。字段漏一个，下一轮就可能 400。
    """
    return data["choices"][0]["message"]


def get_tool_calls(data: dict) -> list[dict]:
    """取出模型想要调用工具的那些请求（可能为空列表）。

    ⭐ 返回的每一条长这样：
           {
             "id": "call_0abc...",            ← 你要用它把结果指回来
             "type": "function",
             "function": {
                 "name": "create_todo",
                 "arguments": "{\\"title\\":\\"买牛奶\\"}"   ← ⚠️ 是一段【字符串】
             }
           }

       ⚠️⚠️ arguments 是 JSON 文本，不是 dict。
           这是整个工具调用里最容易踩的坑：直接 args["title"] 会报
           TypeError: string indices must be integers。
           一律先 json.loads()，而且它【可能解析失败】——模型写错是常事。

    ⭐ 为什么可能一次返回多个？
       模型可以在一次回答里同时请求多个工具（并行）。
       这一层只负责"取出来"，要不要并行执行是业务层的决定。
    """
    message = data["choices"][0]["message"]
    return message.get("tool_calls") or []


def get_reasoning_tokens(usage: dict) -> int | None:
    """取出"思考"用了多少 token（这部分你看不到，但你付钱）。

    ⭐ 它是成本分析的关键数字：
       实测思考量在 9 ~ 1314 之间波动，占输出的 70%~90%。
    """
    return (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
