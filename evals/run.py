#!/usr/bin/env python
"""evals/run.py —— 跑评估集（真调模型）

用法（在 todo-app 目录下）：

    .\\.venv\\Scripts\\python.exe evals\\run.py --list          # 只列出用例，不花钱
    .\\.venv\\Scripts\\python.exe evals\\run.py --dry-run       # 检查 yaml 和日期解析，不花钱
    .\\.venv\\Scripts\\python.exe evals\\run.py                  # 全跑，花几毛钱
    .\\.venv\\Scripts\\python.exe evals\\run.py --kind injection # 只跑对抗组
    .\\.venv\\Scripts\\python.exe evals\\run.py --only 逾期      # 只跑名字里含"逾期"的
    .\\.venv\\Scripts\\python.exe evals\\run.py --target parse   # 只跑不需要写库的那 17 条

⭐ 它和 tests/ 的分工：

    tests/  打桩，测"我的代码有没有写错"       每次提交都跑，免费、确定、快
    evals/  真调模型，测"它还准不准"           改 prompt 后跑，花钱、不确定、慢

⚠️ 三条自我约束（写在这里是为了以后不会忘）：

    ① 只调一次，失败不重试。记 pass@1。
       重试会让通过率虚高 —— 真实的 60% 会被显示成 85%，
       而线上用户碰到的就是那 60%。重试是产品策略，不是质量指标。

    ② 红了先怀疑 eval 自己写错了。
       第一版 eval 的通过率通常是假的：太松则永远绿，太紧则永远红。

    ③ 断言行为，不断言措辞。
       "几条任务 / 哪一天 / 库里还剩几条"是行为；
       "回复里说了哪句话"是措辞，会随模型每次微调变化。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

# ------------------------------------------------------------
#  路径
# ------------------------------------------------------------

EVALS_DIR = Path(__file__).resolve().parent
ROOT = EVALS_DIR.parent            # todo-app/
CASES_FILE = EVALS_DIR / "cases.yaml"
TMP_DIR = EVALS_DIR / "_tmp"       # ⚠️ agent 用例的临时库放这里，绝不碰 todos.db
RESULTS_DIR = EVALS_DIR / "results"

# ⚠️ 必须把 ROOT 放进 sys.path：run.py 在 evals/ 子目录里，
#    不这样处理，"import database" 会找不到（它只会在 evals/ 里找）。
#    这跟 pytest.ini 里写 testpaths 是同一类问题：入口在哪，决定 import 从哪找起。
sys.path.insert(0, str(ROOT))

import ai_agent       # noqa: E402  （必须在 sys.path 处理之后 import）
import ai_client      # noqa: E402
import ai_tasks       # noqa: E402
import database       # noqa: E402


# ============================================================
#  ① 日期写法 → 真实日期
# ============================================================

_OFFSET = re.compile(r"^([+-])(\d+)d$")
_WEEKDAY = re.compile(r"^(this|next)_weekday\(([1-7])\)$")

# 未使用的日期写法允许的取值，写在这里当"文档也是代码"用
DUE_FORMS = '"+Nd" / "-Nd" / "this_weekday(1..7)" / "next_weekday(1..7)" / null'


def resolve_due(spec, today: date):
    """把 cases.yaml 里的日期写法翻译成一个真实的 date。

    ⭐ 为什么 eval 里不能写死 "2026-11-13"？
       下周这份文件就全红了，而且红得莫名其妙 ——
       你会以为模型退化，其实只是自己的测试过期了。
       这和项目里那族"静默失败"是同一类问题：测试悄悄变成了假的。

    ⭐ 为什么不能写死偏移量，比如用 "+6d" 表示"下周一"？
       周二跑是对的，周一跑就错一天。
       相对量也得挑对参照物，否则只是把"写死日期"换了个马甲。
    """
    if spec is None:
        return None

    if not isinstance(spec, str):
        raise ValueError(f"日期必须是字符串或 null，实际是 {type(spec).__name__}")

    m = _OFFSET.match(spec)
    if m:
        sign, days = m.group(1), int(m.group(2))
        return today + timedelta(days=days if sign == "+" else -days)

    m = _WEEKDAY.match(spec)
    if m:
        which, n = m.group(1), int(m.group(2))
        # date.weekday(): 周一 = 0，周日 = 6
        monday = today - timedelta(days=today.weekday())
        base = monday + timedelta(days=7 if which == "next" else 0)
        return base + timedelta(days=n - 1)

    raise ValueError(f"看不懂的日期写法：{spec!r}（只支持 {DUE_FORMS}）")


# ============================================================
#  ② 断言：一条一条查，把问题收集起来
#
#  ⭐ 关键是"收集"而不是"抛异常"：
#     一条 case 有 3 个地方不对时，应该一次告诉你 3 个，
#     而不是修完第一个再跑一遍才发现第二个（那要花三次钱）。
# ============================================================

def _find(items: list[dict], contains: str):
    for it in items:
        if contains in (it.get("title") or ""):
            return it
    return None


def _check_items(expected, actual, today, label, problems):
    """检查 tasks / db_tasks 这种"列表里找某一条"的断言。"""
    for want in expected or []:
        contains = want.get("title_contains")
        if not contains:
            problems.append(f"{label}: 有一项没写 title_contains，没法匹配")
            continue

        found = _find(actual, contains)
        if found is None:
            titles = [t.get("title") for t in actual]
            problems.append(f"{label}: 没找到标题含「{contains}」的，实际有 {titles}")
            continue

        if "due" in want:
            expect_due = resolve_due(want["due"], today)
            if found.get("due") != expect_due:
                problems.append(
                    f"{label}: 「{contains}」的日期应为 {expect_due}，实际 {found.get('due')}"
                )

        if "priority" in want and found.get("priority") != want["priority"]:
            problems.append(
                f"{label}: 「{contains}」的优先级应为 {want['priority']}，实际 {found.get('priority')}"
            )

        if "priority_in" in want and found.get("priority") not in want["priority_in"]:
            problems.append(
                f"{label}: 「{contains}」的优先级应为 {want['priority_in']} 之一，"
                f"实际 {found.get('priority')}"
            )

        if "done" in want and bool(found.get("done")) != bool(want["done"]):
            problems.append(
                f"{label}: 「{contains}」的完成状态应为 {want['done']}，实际 {found.get('done')}"
            )


def check_parse_expect(expect, result, today, problems):
    """检查 /ai/parse 的结果。"""
    tasks = [
        {"title": t.title, "due": t.due, "priority": t.priority}
        for t in result.tasks
    ]

    if "task_count" in expect and len(tasks) != expect["task_count"]:
        problems.append(f"任务条数应为 {expect['task_count']}，实际 {len(tasks)}")

    if "task_count_max" in expect and len(tasks) > expect["task_count_max"]:
        problems.append(f"任务条数应不超过 {expect['task_count_max']}，实际 {len(tasks)}")

    if "note_required" in expect:
        has_note = bool((result.note or "").strip())
        if expect["note_required"] and not has_note:
            problems.append("期望 note 里有说明，实际是空的")
        if not expect["note_required"] and has_note:
            # 不要求 note 时不惩罚"多说了"，只提示 —— 措辞上的多寡不是质量
            pass

    if "note_contains" in expect:
        if expect["note_contains"] not in (result.note or ""):
            problems.append(
                f"note 里应出现「{expect['note_contains']}」，实际：{result.note!r}"
            )

    _check_items(expect.get("tasks"), tasks, today, "tasks", problems)


def check_agent_expect(expect, result, rows, today, problems):
    """检查 /ai/agent 的结果 + 跑完之后的数据库状态。"""
    if "actions_count" in expect and len(result.actions) != expect["actions_count"]:
        problems.append(
            f"工具调用次数应为 {expect['actions_count']}，实际 {len(result.actions)}"
        )

    if "turns_max" in expect and result.turns > expect["turns_max"]:
        problems.append(f"轮次应不超过 {expect['turns_max']}，实际 {result.turns}")

    if "proposals_min" in expect and len(result.proposals) < expect["proposals_min"]:
        problems.append(
            f"删除提案应至少 {expect['proposals_min']} 条，实际 {len(result.proposals)}"
        )

    if "db_count" in expect and len(rows) != expect["db_count"]:
        problems.append(
            f"库里应有 {expect['db_count']} 条，实际 {len(rows)}："
            f"{[r['title'] for r in rows]}"
        )

    _check_items(expect.get("db_tasks"), rows, today, "db", problems)


# ============================================================
#  ③ 跑一条 case
# ============================================================

def run_parse_case(case, api_key, today):
    """parse 用例：不写库，纯解析。"""
    problems: list[str] = []
    expect = case.get("expect") or {}

    want_raise = expect.get("raises")
    try:
        result = ai_tasks.parse_text(case["input"], api_key)
    except Exception as e:                                # noqa: BLE001
        if want_raise and type(e).__name__ == want_raise:
            return {"result": f"按预期失败：{type(e).__name__}"}, problems
        problems.append(f"抛了不该抛的异常：{type(e).__name__}: {e}")
        return {"result": "异常"}, problems

    if want_raise:
        problems.append(f"期望抛出 {want_raise}，实际成功了")
        return {"result": "没有抛出"}, problems

    check_parse_expect(expect, result, today, problems)

    snapshot = {
        "tasks": [
            {
                "title": t.title,
                # ⚠️ 用 isoformat 而不是 str()：str(None) 是字符串 "None"，
                #    存档里出现 "None" 会让下一个人以为是模型返回了这五个字母。
                "due": t.due.isoformat() if t.due else None,
                "priority": t.priority,
            }
            for t in result.tasks
        ],
        "note": result.note,
    }
    return snapshot, problems


def _apply_setup(items, today):
    """给 agent 用例造前置数据。"""
    if not items:
        return
    conn = database.get_connection()
    try:
        for it in items:
            conn.execute(
                "INSERT INTO todos (title, done, due, priority) VALUES (?, ?, ?, ?)",
                (
                    it["title"],
                    int(bool(it.get("done", False))),
                    (resolve_due(it.get("due"), today).isoformat()
                     if it.get("due") else None),
                    it.get("priority", "normal"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _read_all_rows():
    conn = database.get_connection()
    try:
        rows = []
        for r in conn.execute("SELECT * FROM todos ORDER BY id"):
            rows.append(
                {
                    "id": r["id"],
                    "title": r["title"],
                    "done": bool(r["done"]),
                    "due": date.fromisoformat(r["due"]) if r["due"] else None,
                    "priority": r["priority"],
                }
            )
        return rows
    finally:
        conn.close()


def run_agent_case(case, api_key, today):
    """agent 用例：真调工具、真写库（写到独立临时库）。"""
    problems: list[str] = []

    # ⚠️⚠️ 这一行是全文件最危险的一行。
    #      database.DB_FILE 是个模块级变量，get_connection() 在【调用时】才读它，
    #      所以这里一改，后面所有连接都指向临时库 —— 开发库 todos.db 一条都不会少。
    #      反过来，如果哪天有人把它改回常量，eval 就会开始删真实任务。
    database.DB_FILE = TMP_DIR / f"{_slug(case['name'])}.db"
    if database.DB_FILE.exists():
        database.DB_FILE.unlink()
    database.init_db()

    _apply_setup(case.get("setup"), today)

    # 第一句 + 所有 follow_ups，共用同一个 conversation_id
    turns_in = [case["input"]] + [f["input"] for f in (case.get("follow_ups") or [])]
    results = []
    cid = None
    try:
        for text in turns_in:
            res = ai_agent.run_agent(text, api_key, conversation_id=cid)
            cid = res.conversation_id
            results.append(res)
    except Exception as e:                                # noqa: BLE001
        problems.append(f"抛了不该抛的异常：{type(e).__name__}: {e}")
        return {"result": "异常"}, problems

    rows = _read_all_rows()

    # 每一句的 expect 都要检查；db_* 检查的是【全部跑完之后】的最终状态
    pairs = [(case.get("expect") or {}, results[0], "第1句")]
    for i, fu in enumerate(case.get("follow_ups") or []):
        pairs.append((fu.get("expect") or {}, results[i + 1], f"第{i + 2}句"))

    for expect, res, label in pairs:
        before = len(problems)
        check_agent_expect(expect, res, rows, today, problems)
        for j in range(before, len(problems)):
            problems[j] = f"{label} {problems[j]}"

    last = results[-1]
    snapshot = {
        "reply": last.reply,
        "actions": [{"tool": a.tool, "ok": a.ok, "detail": a.detail} for a in last.actions],
        "proposals": [{"id": p.id, "title": p.title} for p in last.proposals],
        "turns": last.turns,
        "db": [
            {
                "title": r["title"],
                "done": r["done"],
                "due": r["due"].isoformat() if r["due"] else None,
                "priority": r["priority"],
            }
            for r in rows
        ],
    }
    return snapshot, problems


def _slug(name: str) -> str:
    """把中文用例名变成一个能当文件名的东西。"""
    keep = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", name).strip("-")
    return (keep or "case")[:40]


# ============================================================
#  ④ 主流程
# ============================================================

def load_cases() -> list[dict]:
    data = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise SystemExit("cases.yaml 里没有 cases")
    return cases


def select(cases, args):
    out = cases
    if args.target:
        out = [c for c in out if c.get("target") == args.target]
    if args.kind:
        out = [c for c in out if c.get("kind") == args.kind]
    if args.only:
        out = [c for c in out if args.only in c.get("name", "")]
    if args.limit:
        out = out[: args.limit]
    return out


def git_sha() -> str:
    """不调 git 命令，直接读 .git 下的文件 —— 少一个外部依赖，也少一个沙盒问题。"""
    for git in (ROOT / ".git", ROOT.parent / ".git"):
        try:
            head = (git / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(" ", 1)[1].strip()
                return (git / ref).read_text(encoding="utf-8").strip()[:12]
            return head[:12]
        except OSError:
            continue
    return "unknown"


def selftest(today: date) -> int:
    """证明这套断言【真的会红】。

    ⭐ 为什么需要这个？

       第一版 eval 跑出 22/22 的时候，第一个念头不该是"我的模型真好"，
       而该是"我的断言是不是什么都没查"。

       一个永远绿的评价体系比没有评价体系更糟 ——
       它给你的是虚假的安全感，而且你还会拿它去说服自己。

       所以这里喂给断言函数一批【故意做错】的数据，
       要求它们必须报错。断言函数要是查不出来，问题在 eval，不在模型。
    """
    cases = [
        # (说明, 期望, 实际, 必须报出来)
        (
            "条数不符",
            {"task_count": 1},
            ai_tasks.ParseResult(tasks=[], note=None),
            True,
        ),
        (
            "日期不符",
            {"tasks": [{"title_contains": "周报", "due": "+1d"}]},
            ai_tasks.ParseResult(
                tasks=[ai_tasks.Task(title="交周报", due=None)],
                note=None,
            ),
            True,
        ),
        (
            "优先级不符",
            {"tasks": [{"title_contains": "周报", "priority": "high"}]},
            ai_tasks.ParseResult(
                tasks=[ai_tasks.Task(title="交周报", priority="normal")],
                note=None,
            ),
            True,
        ),
        (
            "放宽的 priority_in 也得拦住",
            {"tasks": [{"title_contains": "牛奶", "priority_in": ["low", "normal"]}]},
            ai_tasks.ParseResult(
                tasks=[ai_tasks.Task(title="买牛奶", priority="high")],
                note=None,
            ),
            True,
        ),
        (
            "该有的标题找不到",
            {"tasks": [{"title_contains": "作业"}]},
            ai_tasks.ParseResult(
                tasks=[ai_tasks.Task(title="买牛奶")],
                note=None,
            ),
            True,
        ),
        (
            "空结果却没给 note",
            {"note_required": True},
            ai_tasks.ParseResult(tasks=[], note=None),
            True,
        ),
        (
            # ⭐ 反向用例：结果全对时必须【一条问题都不报】。
            #    少了这条，断言函数"永远报错"也能通过上面全部检查。
            "正确的数据不该被冤枉",
            {
                "task_count": 1,
                "note_required": False,
                "tasks": [{"title_contains": "牛奶", "due": "+1d", "priority": "normal"}],
            },
            ai_tasks.ParseResult(
                tasks=[ai_tasks.Task(title="买牛奶", due=today + timedelta(days=1))],
                note=None,
            ),
            False,
        ),
    ]

    bad = 0
    for label, expect, result, should_complain in cases:
        problems: list[str] = []
        check_parse_expect(expect, result, today, problems)
        if should_complain and not problems:
            bad += 1
            print(f"[BROKEN] {label}：断言没报错，说明它根本没在查")
        elif not should_complain and problems:
            bad += 1
            print(f"[BROKEN] {label}：断言冤枉了正确的数据 -> {problems}")
        else:
            print(f"[OK]     {label}")

    # agent 侧几项
    agent_cases = [
        (
            "轮次超了",
            {"turns_max": 2},
            ai_agent.AgentResult(reply="x", turns=5),
            [{"title": "买牛奶", "done": False, "due": None, "priority": "normal"}],
            True,
        ),
        (
            "库里条数不符",
            {"db_count": 1},
            ai_agent.AgentResult(reply="x", turns=1),
            [{"title": "买牛奶", "done": False, "due": None, "priority": "normal"},
             {"title": "交电费", "done": False, "due": None, "priority": "normal"}],
            True,
        ),
        (
            "任务被翻回未完成",
            {"db_tasks": [{"title_contains": "买牛奶", "done": True}]},
            ai_agent.AgentResult(reply="x", turns=1),
            [{"title": "买牛奶", "done": False, "due": None, "priority": "normal"}],
            True,
        ),
        (
            "该出现的删除提案没出现",
            {"proposals_min": 1},
            ai_agent.AgentResult(reply="x", turns=1),
            [],
            True,
        ),
        (
            "agent 侧正确的数据也不该被冤枉",
            {
                "turns_max": 3,
                "db_count": 1,
                "db_tasks": [{"title_contains": "牛奶", "done": True, "due": "+1d"}],
                "proposals_min": 0,
            },
            ai_agent.AgentResult(reply="x", turns=2),
            [{"title": "买牛奶", "done": True, "due": today + timedelta(days=1),
              "priority": "normal"}],
            False,
        ),
    ]
    for label, expect, result, rows, should_complain in agent_cases:
        problems = []
        check_agent_expect(expect, result, rows, today, problems)
        if should_complain and not problems:
            bad += 1
            print(f"[BROKEN] {label}：断言没报错")
        elif not should_complain and problems:
            bad += 1
            print(f"[BROKEN] {label}：冤枉了正确的数据 -> {problems}")
        else:
            print(f"[OK]     {label}")

    print()
    if bad:
        print(f"自检失败 {bad} 项 —— 先修 eval，别去怪模型。")
        return 1
    print("自检通过：断言既查得出错，也不冤枉对的。")
    return 0


def dry_run(cases, today):
    """只为省钱的模式：把日期算出来给你看，一条 API 都不调。"""
    bad = 0
    for c in cases:
        line = f"[{c['kind']:<9}] {c['name']}"
        try:
            notes = []
            for item in c.get("setup") or []:
                if item.get("due"):
                    notes.append(f"setup:{resolve_due(item['due'], today)}")
            for item in (c.get("expect") or {}).get("tasks") or []:
                if "due" in item:
                    notes.append(f"tasks:{resolve_due(item['due'], today)}")
            for item in (c.get("expect") or {}).get("db_tasks") or []:
                if "due" in item:
                    notes.append(f"db:{resolve_due(item['due'], today)}")
            for fu in c.get("follow_ups") or []:
                for item in (fu.get("expect") or {}).get("db_tasks") or []:
                    if "due" in item:
                        notes.append(f"fu-db:{resolve_due(item['due'], today)}")
            print(f"{line}  {' '.join(notes)}")
        except ValueError as e:
            bad += 1
            print(f"{line}  <--- 日期写错了：{e}")
    print()
    print(f"今天 = {today}（周{'一二三四五六日'[today.weekday()]}）")
    print(f"{len(cases)} 条 case，日期解析失败 {bad} 条")
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="跑评估集（真调模型）")
    parser.add_argument("--list", action="store_true", help="只列用例名，不花钱")
    parser.add_argument("--dry-run", action="store_true", help="只检查 yaml 与日期解析，不花钱")
    parser.add_argument("--selftest", action="store_true",
                        help="证明断言函数真的会红（喂假数据，不调用模型）")
    parser.add_argument("--target", choices=["parse", "agent"], help="只跑某一类")
    parser.add_argument("--kind", help="只跑某个 kind（normal/edge/injection/memory）")
    parser.add_argument("--only", help="只跑名字里含这几个字的")
    parser.add_argument("--limit", type=int, help="最多跑几条")
    parser.add_argument("--no-save", action="store_true", help="不落 jsonl")
    args = parser.parse_args()

    today = date.today()
    cases = select(load_cases(), args)

    if args.list:
        for c in cases:
            print(f"[{c['kind']:<9}] [{c['target']:<5}] {c['name']}")
        print(f"\n共 {len(cases)} 条")
        return 0

    if args.dry_run:
        return dry_run(cases, today)

    if args.selftest:
        return selftest(today)

    if not cases:
        print("没有匹配的 case")
        return 1

    try:
        api_key = ai_client.load_api_key()
    except ai_client.AIConfigError as e:
        print(f"没拿到 API key：{e}")
        return 2

    TMP_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    n_agent = sum(1 for c in cases if c.get("target") == "agent")
    print(f"今天 = {today}（周{'一二三四五六日'[today.weekday()]}）")
    print(f"共 {len(cases)} 条（agent {n_agent} 条会真写库，用的是 evals/_tmp/ 下的独立库）")
    print("每条只调一次，失败不重试 —— 记的是 pass@1。")
    print()

    started = time.time()
    records = []
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        try:
            if case.get("target") == "parse":
                snapshot, problems = run_parse_case(case, api_key, today)
            else:
                snapshot, problems = run_agent_case(case, api_key, today)
        except Exception as e:                            # noqa: BLE001
            snapshot, problems = {"result": "崩溃"}, [f"runner 自己崩了：{type(e).__name__}: {e}"]

        elapsed = time.time() - t0
        ok = not problems
        mark = "PASS" if ok else "FAIL"
        print(f"[{i:>2}/{len(cases)}] {mark}  {case['name']}  ({elapsed:.1f}s)")
        if not ok:
            for p in problems:
                print(f"         ! {p}")
            print(f"         实际：{_short(snapshot)}")

        records.append(
            {
                "name": case["name"],
                "kind": case.get("kind"),
                "target": case.get("target"),
                "passed": ok,
                "problems": problems,
                "elapsed_s": round(elapsed, 2),
                "output": snapshot,
            }
        )

    total_s = time.time() - started
    passed = sum(1 for r in records if r["passed"])
    print()
    print("=" * 60)
    print(f"通过 {passed}/{len(records)}  "
          f"({passed / len(records) * 100:.0f}%)   总耗时 {total_s:.1f}s")

    # 按 kind 分组 —— 比总分更有信息量：
    # "15/16 通过"里如果 4 条对抗全红，那和 15/16 是两件事。
    kinds = sorted({r["kind"] or "?" for r in records})
    for k in kinds:
        sub = [r for r in records if (r["kind"] or "?") == k]
        p = sum(1 for r in sub if r["passed"])
        print(f"  {k:<10} {p}/{len(sub)}")

    failed = [r["name"] for r in records if not r["passed"]]
    if failed:
        print()
        print("红了的：")
        for name in failed:
            print(f"  - {name}")

    if not args.no_save:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = RESULTS_DIR / f"{ts}_{git_sha()}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print()
        print(f"结果已存：{path}")
        print("（下次跑可以拿来对比。没有基线，18/20 到底是好是差你判断不了。）")

    return 0 if not failed else 1


def _short(snapshot, limit=200) -> str:
    text = json.dumps(snapshot, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


if __name__ == "__main__":
    raise SystemExit(main())
