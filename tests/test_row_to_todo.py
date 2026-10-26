"""
零依赖测试示例 —— 只用 Python 自带的 unittest，不需要装任何包。

跑法（在 todo-app 目录下）：
    python -m unittest tests.test_row_to_todo -v

注意：不需要 pytest，也不需要 httpx。
"""

import unittest

from models import row_to_todo


class TestRowToTodo(unittest.TestCase):
    """测 row_to_todo：把数据库的一行转成 API 的字典

    这是整个项目里最重要的"边界转换"：
        数据库存 0/1  →  API 必须返回 false/true
    """

    def test_done_1_becomes_true(self):
        """1 必须变成 True（布尔），不能原样返回整数 1"""
        result = row_to_todo({"id": 1, "title": "x", "done": 1})
        self.assertIs(result["done"], True)

    def test_done_0_becomes_false(self):
        """0 必须变成 False"""
        result = row_to_todo({"id": 1, "title": "x", "done": 0})
        self.assertIs(result["done"], False)

    def test_other_fields_unchanged(self):
        """其他字段应该原样复制"""
        result = row_to_todo({"id": 7, "title": "写报告", "done": 0})
        self.assertEqual(result["id"], 7)
        self.assertEqual(result["title"], "写报告")

    def test_returns_plain_dict(self):
        """返回的必须是普通 dict（才能被 FastAPI 转成 JSON）"""
        result = row_to_todo({"id": 1, "title": "x", "done": 0})
        self.assertIs(type(result), dict)


if __name__ == "__main__":
    unittest.main()