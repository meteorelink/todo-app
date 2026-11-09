# ============================================================
#  models.py —— 数据模型层
#
#  只放两样东西：
#    ① 请求体的"模具"（Pydantic 模型）
#    ② 数据库行 → API 字典 的转换函数
#
#  为什么单独一个文件？
#  因为它们描述的是「数据的形状」，和"哪个 URL 调哪个函数"无关。
#  以后加字段（比如 created_at）时，只改这里。
# ============================================================

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ⭐ 用一个类型别名把"优先级只能是这三个词"写死。
#    Literal 的好处：传了 "urgent" 之类的值，Pydantic 会在边界直接 422，
#    错误信息里还会列出允许的值，一行校验代码都不用自己写。
Priority = Literal["high", "normal", "low"]


# ============================================================
#  Pydantic 模型 —— 请求体的"模具"
#
#  客户端发来的只是一段无类型的 JSON 文本。
#  这两个类负责把它校验并转换成有类型的 Python 对象。
#  校验不过 → FastAPI 自动返回 422，你一行校验代码都不用写。
# ============================================================

class TodoCreate(BaseModel):
    """新增任务时，客户端要提供的数据"""
    # ⚠️ 空标题是【不合法】的，不是"没内容"。
    #    以前这里是裸的 str，于是 POST {"title": ""} 会 201 成功，
    #    数据库里就多出一条看不见的空白任务 —— 前端渲染出来是一个空 li。
    #    max_length=200 是上限：防止有人一次塞进一兆文本。
    title: str = Field(min_length=1, max_length=200)

    # done 有默认值：新建一条任务本来就是"未完成"，允许省略。
    # （这里给默认值是安全的，因为不会覆盖任何已有数据）
    done: bool = False

    # ⭐ 截止日期。date 类型由 Pydantic 自动解析：
    #    收到 "2026-11-06" 会变成一个 datetime.date 对象，
    #    收到 "明天" 或 "2026-13-01" 会直接 422 —— 边界校验免费送。
    #    None 表示"没有截止日期"，这是合法的，不是错误。
    due: date | None = None

    # 优先级。默认 normal —— 大多数任务就是普通优先级，
    # 要求客户端每次都写一遍是没必要的负担。
    priority: Priority = "normal"

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v):
        """先去掉首尾空白，再交给 min_length 检查。

        mode="before" 让 strip 发生在长度校验【之前】，
        所以 "    " 会先变成 ""，再被 min_length=1 拦下，
        错误类型统一是 string_too_short。
        """
        return v.strip() if isinstance(v, str) else v


class TodoUpdate(BaseModel):
    """更新任务时，客户端要提供的数据"""
    # 和 TodoCreate 用同一套约束：POST 和 PUT 不该对 title 有两套标准
    title: str = Field(min_length=1, max_length=200)
    # ⚠️ done 必填：PUT 是"整体替换"，
    #    如果有默认值，客户端不传就会把已有任务静默改成"未完成"。
    done: bool

    # ⚠️ due 和 priority 也【必填】—— 同样的道理。
    #    due 允许是 null（"没有截止日期"是一个明确的值），
    #    但这个 key 必须出现。否则"忘记传 due"和
    #    "明确表示不要截止日期"就分不开了，PUT 会把日期悄悄抹掉。
    due: date | None
    priority: Priority

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v):
        return v.strip() if isinstance(v, str) else v


class TodoBatchCreate(BaseModel):
    """批量新增任务的请求体

    为什么要 min_length=1？
        一个"批量创建 0 条"的请求没有任何意义 ——
        它只可能意味着调用方出了 bug（比如前端把过滤后的空数组发了上来）。
        让它在边界被拦下，比让它"成功地什么也不做"更有用。

    max_length=50：AI 一次最多拆 20 条，50 留了余量，
    同时挡住"一口气塞一万条"这种请求。
    """
    tasks: list[TodoCreate] = Field(min_length=1, max_length=50)


# ============================================================
#  边界转换：数据库的一行  →  API 要返回的字典
#
#  为什么要有这个函数？因为"转换逻辑只应该有一份"。
#  以后加字段（比如 created_at），只改这一个地方。
# ============================================================

def row_to_todo(row):
    """把数据库的一行，转成 API 要返回的字典"""
    return {
        "id": row["id"],
        "title": row["title"],
        # ⚠️ 数据库存的是 0/1，API 契约是布尔值。
        #    不转的话会返回 "done": 0 —— 前端 JS 里 0 === false 是 false，会出问题。
        "done": bool(row["done"]),
        # due 存的是 "YYYY-MM-DD" 文本或 NULL，原样返回即可。
        # （前端也用字符串比较，见 TodoItem.jsx 里 todayISO() 那段注释）
        "due": row["due"],
        "priority": row["priority"],
    }
