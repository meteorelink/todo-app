"""
零依赖测试示例 —— 只用 Python 自带的 unittest，不需要装任何包。

跑法（在 todo-app 目录下）：
    python -m unittest tests.test_row_to_todo -v

注意：不需要 pytest，也不需要 httpx。
"""

import unittest

from models import row_to_todo


def _row(**over):
    """造一行"和数据库里一模一样"的字典

    ⚠️ 为什么不直接在各个测试里写 {"id":1,"title":"x","done":1}？
       因为 8.4 给表加了 due 和 priority 两列之后，
       row_to_todo 要读这两个键 —— 一行缺了它就会 KeyError。
       用一个工厂函数，以后再加字段只需要改这里一处，
       而不是每个测试都去补一遍。
    """
    base = {
        "id": 1,
        "title": "x",
        "done": 0,
        "due": None,
        "priority": "normal",
    }
    base.update(over)
    return base


class TestRowToTodo(unittest.TestCase):
    """测 row_to_todo：把数据库的一行转成 API 的字典

    这是整个项目里最重要的"边界转换"：
        数据库存 0/1  →  API 必须返回 false/true
    """

    def test_done_1_becomes_true(self):
        """1 必须变成 True（布尔），不能原样返回整数 1"""
        result = row_to_todo(_row(done=1))
        self.assertIs(result["done"], True)

    def test_done_0_becomes_false(self):
        """0 必须变成 False"""
        result = row_to_todo(_row(done=0))
        self.assertIs(result["done"], False)

    def test_other_fields_unchanged(self):
        """其他字段应该原样复制"""
        result = row_to_todo(_row(id=7, title="写报告", done=0))
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["title"], "写报告")

    def test_returns_plain_dict(self):
        """返回的必须是普通 dict（才能被 FastAPI 转成 JSON）"""
        result = row_to_todo(_row())
        self.assertIs(type(result), dict)

    # ---------- 8.4 新增的两个字段 ----------

    def test_due_is_passed_through(self):
        """数据库里存的 "YYYY-MM-DD" 文本要原样返回（前端直接拿它比较）"""
        result = row_to_todo(_row(due="2026-11-06"))
        self.assertEqual(result["due"], "2026-11-06")

    def test_no_due_stays_none(self):
        """NULL 必须是 None，不能变成空字符串

        ⚠️ 为什么较真这个？
           如果这里返回 ""，前端 if (todo.due) 会把空字符串当成"有日期"，
           于是界面上出现一行 "截止 "，后面什么都没有。
        """
        result = row_to_todo(_row(due=None))
        self.assertIsNone(result["due"])

    def test_priority_is_passed_through(self):
        result = row_to_todo(_row(priority="high"))
        self.assertEqual(result["priority"], "high")


if __name__ == "__main__":
    unittest.main()
