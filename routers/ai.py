"""
routers/ai.py —— AI 能力对外暴露的唯一入口

============================================================
这个文件很短，但它同时是【三个边界】：

    ① 输入边界    —— 用户输入在这里被 Pydantic 拦一次（结构性校验）
    ② 错误边界    —— 内部异常在这里被翻译成 HTTP 状态码
    ③ 信息边界    —— 上游的详细错误在这里被截断，只留用户能用的部分

⭐ 记住这一句：
   **进来之前拦，出去之前翻译，中间的全部细节不外流。**

============================================================
⭐ 为什么这里用 `def` 而不是 `async def`？

   因为 `parse_text` 内部用的是 urllib —— 它是【阻塞】的，
   一次调用会让当前线程卡住最多 60 秒。

   · 写成 `async def`：这个阻塞调用跑在事件循环里，
     **整个服务器在这 60 秒内无法处理任何其他请求**。
     （一个用户解析一句话 → 所有人都卡住）

   · 写成 `def`：FastAPI 会把它丢进【线程池】执行，
     事件循环立刻空出来，其他请求照常处理。

   ⭐ 规则：**async def 里不能有阻塞调用。有阻塞调用就用 def。**
      想用 async def，就得把 urllib 换成 httpx.AsyncClient。
"""

import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

import conversations
from ai_agent import AgentFailed, AgentResult, run_agent
from ai_client import (
    AIConfigError,
    AIError,
    AITimeoutError,
    AIUpstreamError,
    load_api_key,
)
from ai_tasks import ParseFailed, ParseResult, parse_text


log = logging.getLogger(__name__)

router = APIRouter(tags=["ai"])


# ⭐ 输入长度上限。
#
#    为什么必须有？
#      · 成本：输入按 token 计费，5000 字就是几千 tokens，全是钱
#      · 安全：超长输入是 prompt injection 的常见载体（把指令埋在中间）
#      · 现实：一句"周五前交周报"最多几十字，2000 已经非常宽松
#
#    ⚠️ 超长时返回 422（客户端的问题），不是 500。
MAX_INPUT_CHARS = 2000


class AIRequest(BaseModel):
    """请求体（/ai/parse 和 /ai/agent 共用）。

    ⭐ 这里只做【结构性】校验：是不是字符串、长度是否在范围内。

       语义性的判断（这句话里有没有任务）**不在这里做** ——
       那必须交给模型，因为"周五前交周报"和"今天天气真好"
       在结构上完全一样，只有理解语义才能区分。
    """

    text: str = Field(
        min_length=1,
        max_length=MAX_INPUT_CHARS,
        description="用户用自然语言描述的一件事或几件事",
    )

    @field_validator("text", mode="before")
    @classmethod
    def strip_text(cls, v):
        """先把首尾空白删掉，再交给 min_length / max_length 检查。

        ⭐ `mode="before"` 是这里的关键，它决定这个函数在【什么时候】运行：

            mode="before"  →  在约束检查【之前】跑
                              "        " 先变成 ""，再被 min_length=1 拦下
                              报的错误是 string_too_short（和真空字符串一模一样）

            mode="after"（默认）→ 在约束检查【之后】跑
                              "        " 长度是 8，先通过了 min_length=1
                              然后才被我们手动报错 → 错误类型变成 value_error
                              前端的报错处理要同时应付两种结构

        ⭐ 一句话：**校验的顺序，决定了用户看到哪种错误。**
           让统一的约束去报错，比在事后手动补一个错误要干净。
        """
        if isinstance(v, str):
            return v.strip()
        return v


class AgentRequest(AIRequest):
    """助手接口的请求体 = 一句话 + 可选的会话编号。

    ⭐ 为什么用【继承】而不是直接往 AIRequest 里加一个可选字段？

       因为 /ai/parse 是【无状态】的：它每次都从头理解一句话，
       同一个输入永远得到同一个输出。它不需要记忆，也不该有记忆。

       如果 conversation_id 加在共享的 AIRequest 上，那么调用方
       给 /ai/parse 传了这个字段，它会被【静默忽略】——
       调用方以为自己接上了上下文，其实没有。
       这又是一次"不报错，但行为和你以为的不一样"。

    ⭐ 规则：**一个字段只出现在真正用它的那个请求模型里。**
       共享的基类只放真正共享的东西。
    """

    conversation_id: str | None = Field(
        default=None,
        max_length=64,
        description="上一次响应里返回的会话编号；第一次对话不传",
    )


# ============================================================
#  ⭐ 两个端点共用的"边界流程"
#
#  /ai/parse 和 /ai/agent 的异常处理是【一模一样】的：
#      取 key → 调业务 → 把内部异常翻译成状态码 → 细节只进日志
#
#  不一样的地方只有中间那一行（调 parse_text 还是 run_agent）。
#  所以把相同的部分抽成函数，把"不同的那一行"作为参数 work 传进来。
#
#  ⚠️ 为什么不复制一份？
#     复制之后两边会慢慢长歪：某天给 parse 补了 429 的处理，
#     忘了给 agent 补，于是同一类错误在两个接口上表现不同。
#     这种 bug 没人会主动查，因为两边"看起来都对"。
#
#  ⭐ 这也是一种 Hook：把"会变的那一步"抽出来当参数，
#     剩下的骨架只写一次。
# ============================================================

T = TypeVar("T")


def _call_ai(work: Callable[[str], T]) -> T:
    """跑一次 AI 业务，把内部异常翻译成 HTTP 状态码。

    ⭐ 三种"结果"，三种表达方式（这是本文件最重要的设计）：

        ① 正常有结果        → 200 + 业务数据
        ② 正常但没有结果    → 200 + 业务数据里的 note（**不是错误！**）
        ③ 我们给不出结论    → 5xx + {"detail":"用户能看懂的一句话"}

    ⚠️ 特别强调 ②：**"没有任务"是一个成功的分析结论，不是失败。**
       如果把它判成 4xx，前端会显示红色报错，冤枉用户。
    """
    # ---------------------------------------------------------
    # 1. 配置检查 —— 放在最前面
    #
    #    load_api_key() 抛 AIConfigError（不是 SystemExit），
    #    所以我们能在这里接住它，把它变成 503。
    # ---------------------------------------------------------
    try:
        api_key = load_api_key()
    except AIConfigError as e:
        # ⭐ 日志里写真相：具体缺什么配置
        log.error("AI 配置缺失，无法处理请求：%s", e)
        # ⭐ 响应里写用户能用的信息：他不需要知道我们缺的是哪个环境变量
        raise HTTPException(
            status_code=503,
            detail="AI 服务暂时不可用，请稍后再试",
        ) from e

    # ---------------------------------------------------------
    # 2. 调用业务层，并把异常翻译成状态码
    #
    #    ⚠️ 顺序很重要：子类必须写在父类前面。
    #       ParseFailed / AgentFailed 都是 AIError 的子类，
    #       如果 AIError 写在前面，那两个分支永远进不去。
    # ---------------------------------------------------------
    try:
        return work(api_key)

    except AITimeoutError as e:
        # 上游太慢 → 504 Gateway Timeout
        log.warning("AI 请求超时：%s", e)
        raise HTTPException(
            status_code=504,
            detail="AI 服务响应太慢，请稍后再试",
        ) from e

    except (ParseFailed, AgentFailed) as e:
        # 模型连续多次给不出能用的东西 → 502（上游没按约定输出）
        # ⭐ 这条对用户是【可行动】的：换个说法可能就好了
        log.error("模型多次输出不合法：%s", e)
        raise HTTPException(
            status_code=502,
            detail="AI 没能给出有效结果，请换个说法再试",
        ) from e

    except AIUpstreamError as e:
        # 上游 HTTP 错误（401 key 错 / 402 没余额 / 429 太频繁 / 5xx 挂了）
        #
        # ⚠️⚠️ 这一行是本文件最关键的安全点：
        #      e 里含上游返回的原文，可能带 key 片段、request_id、
        #      甚至（换一家服务商）完整的凭证。
        #
        #      所以：**详细内容只进日志，绝不进响应体。**
        #      而且我们【无法预知】上游会不会回显敏感信息 ——
        #      规则不是"信任上游"，而是"永不转发上游原文"。
        log.error("AI 上游返回错误：%s", e)
        raise HTTPException(
            status_code=502,
            detail="AI 服务暂时不可用，请稍后再试",
        ) from e

    except AIError as e:
        # 兜底：将来新增的 AI 异常类型也会被接住，不会漏成 500 裸奔
        log.exception("未分类的 AI 错误")
        raise HTTPException(
            status_code=500,
            detail="服务内部错误",
        ) from e


# ============================================================
#  /ai/parse —— 只"理解"，不动数据
# ============================================================

@router.post("/ai/parse", response_model=ParseResult)
def parse_endpoint(payload: AIRequest) -> ParseResult:
    """把一句自然语言拆成任务列表（草稿）。

    ⭐ 它【什么都不写库】。用户在前端看到草稿、确认之后，
       才会由前端去调 POST /todos/batch。

    ⚠️ 为什么必须分成两步？
       如果这里直接写库，用户在预览里划掉的那几条就已经落盘了 ——
       用户关掉页面，数据库里留下 3 条他从未确认过的垃圾任务。
       "确认"这个动作，就是"从草稿到数据"的那道门。
    """
    return _call_ai(lambda api_key: parse_text(payload.text, api_key))


# ============================================================
#  /ai/agent —— 真的动手（8.5 新增）
# ============================================================

@router.post("/ai/agent", response_model=AgentResult)
def agent_endpoint(payload: AgentRequest) -> AgentResult:
    """让模型自己决定调哪个工具，把事情直接做掉。

    ⭐ 和 /ai/parse 的根本区别：

        /ai/parse   → 模型只"说"，人做
        /ai/agent   → 模型"说 + 做"，代码执行它的决定

       中间多出来的那个东西叫【循环】。模型说"我要调 create_todo"，
       我们执行，把结果喂回去，它再说下一句 —— 直到它不要工具了。

    ⚠️ 这里的响应时间是【不可控】的：
       最多 5 轮，每轮都可能等 60 秒。前端必须显示"处理中"，
       而且要有超时提示 —— 不然用户会以为页面卡死了。

    ⚠️ 也正因为不可控，这个接口【不适合】放在普通 HTTP 请求里
       做长任务。真要做"跑十分钟的 agent"，得改成任务队列 +
       轮询/推送。我们这里 5 轮封顶（十几次工具调用以内），
       放在请求里还撑得住。
    """
    return _call_ai(
        lambda api_key: run_agent(
            payload.text, api_key, conversation_id=payload.conversation_id
        )
    )


# ============================================================
#  会话管理（多轮记忆的"副作用"接口）
#
#  ⭐ 为什么会话要单独给两个接口？
#
#     因为"记忆"本身是【有状态的】，而 HTTP 请求是【无状态的】。
#     一旦引入了跨请求的状态，就必须给用户一个能看见它、能清掉它的口子：
#
#        GET    → 我现在这段对话里到底存了什么？（看得见）
#        DELETE → 我不想接着说了，忘掉它   （清得掉）
#
#     ⚠️ 没有这两个口子，用户就只有一个办法清上下文：等 24 小时。
#        而且他自己还不知道发生了什么。
# ============================================================

class ConversationView(BaseModel):
    """一段对话的样子（给调试和教学用的，前端界面不依赖它）。"""

    id: str
    message_count: int
    messages: list[dict] = Field(default_factory=list)


@router.get("/ai/conversations/{conversation_id}", response_model=ConversationView)
def get_conversation(conversation_id: str) -> ConversationView:
    """看看这段对话里存了什么。

    ⭐ 这个接口最有用的时候是你怀疑"模型为什么这么说"——
       把 messages 打印出来，往往一眼就能看出：它根本没看到你以为它看到了的东西。

    ⚠️ 它把原始 messages 完整吐出来（含 tool_calls 和 tool 回执）。
       真产品不该这样（会有隐私问题），这里是为了看得见。
    """
    messages = conversations.load(conversation_id)
    if messages is None:
        # 不存在 和 已过期 是同一件事：对它来说，这段对话都没了。
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    return ConversationView(
        id=conversation_id,
        message_count=len(messages),
        messages=messages,
    )


@router.delete("/ai/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str):
    """忘掉这段对话。

    ⭐ 返回 204 而【不是 404】——即使它本来就不存在。

       因为用户的目的只有一个："之后别再看见这段历史"。
       目的达到了，就是成功。
       如果因为"本来就没有"报 404，前端反而要去处理一个
       对用户毫无意义的错误（"我想清空，你说没有可清空的"）。
    """
    conversations.delete(conversation_id)
    # 204 不返回任何东西
