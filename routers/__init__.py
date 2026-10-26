# 这个文件让 routers 成为一个"包"（package）。
#
# 内容可以是空的 —— 它的存在本身就是告诉 Python：
# "routers 是一个可以被 import 的包"。
#
# 有了它，main.py 里才能写：
#     from routers import todos
# 然后 routers/todos.py 才能被加载。
