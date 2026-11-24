"""handoff_metrics.py 的測試：用暫存的假紀錄檔，不碰真實資料。
執行：python -X utf8 -I test_handoff_metrics.py
"""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import handoff_metrics as hm  # noqa: E402
import token_weekly as tw  # noqa: E402

REC = r"C:\work\groupA\Alpha\record.md"
n = [0]


def user(text, ts):
    return json.dumps({"type": "user", "timestamp": ts, "message": {"content": text}}, ensure_ascii=False, separators=(",", ":"))


def asst(ts, tools, ctx=50000):
    n[0] += 1
    content = [{"type": "tool_use", "id": "t%d" % n[0], "name": name, "input": inp} for name, inp in tools]
    return json.dumps({"type": "assistant", "timestamp": ts, "uuid": "u%d" % n[0],
                       "message": {"id": "m%d" % n[0], "model": "x", "content": content,
                                   "usage": {"input_tokens": 10, "cache_read_input_tokens": ctx - 10, "output_tokens": 5}}},
                      ensure_ascii=False, separators=(",", ":"))


def write(root, name, lines):
    d = os.path.join(root, "proj")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    long_cmd = "python -X utf8 -I scripts/scan_all.py --deep"
    with tempfile.TemporaryDirectory() as root:
        # 前一個工作階段 A：讀了三個檔、跑了掃描，最後把交接單寫進專案紀錄
        write(root, "aaaa", [
            user("幫我修登入頁", "2026-01-05T01:00:00.000Z"),
            asst("2026-01-05T01:01:00.000Z", [("Read", {"file_path": r"C:\code\alpha\login.jsp"}),
                                              ("Read", {"file_path": r"C:\code\alpha\auth.java"}),
                                              ("Read", {"file_path": REC}),
                                              ("Bash", {"command": long_cmd}), ("Bash", {"command": "git status"})]),
            asst("2026-01-05T02:00:00.000Z", [("Edit", {"file_path": REC, "old_string": "x",
                                                        "new_string": "## 交接單\n\n- **下一步的第一個動作**：開 login.jsp"})]),
        ])
        # 更早的另一個工作階段 Z 也寫過同一份交接單（要選比較晚的 A 當前一個）
        write(root, "zzzz", [
            user("別的事", "2026-01-04T01:00:00.000Z"),
            asst("2026-01-04T01:01:00.000Z", [("Read", {"file_path": r"C:\code\alpha\other.java"}),
                                              ("Write", {"file_path": REC, "content": "## 交接單\n舊的"})]),
        ])
        # 接手的工作階段 B：動手前重讀兩個檔（其中一個是專案紀錄，不算）、重跑掃描、使用者又講一次話、問了一題
        write(root, "bbbb", [
            user("Background: 專案背景\n\nTask:\n交接單：`" + REC + "`\n- **下一步的第一個動作**：開 login.jsp", "2026-01-06T01:00:00.000Z"),
            asst("2026-01-06T01:01:00.000Z", [("Read", {"file_path": REC}),
                                              ("Read", {"file_path": "C:/code/alpha/login.jsp"}),
                                              ("Read", {"file_path": r"C:\code\alpha\new.css"}),
                                              ("Bash", {"command": "python -X utf8 -I  scripts/scan_all.py --deep"}),
                                              ("Bash", {"command": "git status"}),
                                              ("AskUserQuestion", {"questions": []})], ctx=80000),
            user("<task-notification>背景工作完成</task-notification>", "2026-01-06T01:02:00.000Z"),
            user("之前做到登入頁的驗證那一段", "2026-01-06T01:03:00.000Z"),
            asst("2026-01-06T01:04:00.000Z", [("Edit", {"file_path": r"C:\code\alpha\login.jsp", "old_string": "a", "new_string": "b"})], ctx=120000),
            asst("2026-01-06T01:05:00.000Z", [("Read", {"file_path": r"C:\code\alpha\auth.java"})], ctx=130000),
        ])
        # 接手開始之後才有人改交接單（工作階段 L）：不能被選成前一個
        write(root, "llll", [
            user("後來的事", "2026-01-06T08:00:00.000Z"),
            asst("2026-01-06T08:01:00.000Z", [("Read", {"file_path": r"C:\code\alpha\new.css"}),
                                              ("Write", {"file_path": REC, "content": "## 交接單\n後來寫的"})]),
        ])
        # 只是在討論交接單的工作階段 C（行首不是「交接單：路徑」）：不算接手
        write(root, "cccc", [
            user("1. **交接單**：在範本（`C:\\work\\template.md`）加一段", "2026-01-06T03:00:00.000Z"),
            asst("2026-01-06T03:01:00.000Z", [("Read", {"file_path": REC})]),
        ])
        # 接手但找不到前一個（紀錄路徑對不到），而且整個工作階段沒改檔
        write(root, "dddd", [
            user("交接單：C:\\work\\groupA\\Nobody\\record.md，讀完照第一個動作接著做。", "2026-01-07T01:00:00.000Z"),
            asst("2026-01-07T01:01:00.000Z", [("Read", {"file_path": r"C:\work\groupA\Nobody\record.md"})], ctx=60000),
        ])
        # 沒有「交接單」三個字的工作階段：不解析
        write(root, "eeee", [user("改個文案", "2026-01-06T05:00:00.000Z"),
                             asst("2026-01-06T05:01:00.000Z", [("Read", {"file_path": REC})])])

        rows, written = hm.collect("2026-01-05T00:00:00", "2026-01-12T00:00:00", root)
        by = {os.path.basename(r["path"])[:4]: r for r in rows}
        check("接手的工作階段只認 bbbb、dddd（討論交接單的 cccc 不算）", sorted(by) == ["bbbb", "dddd"])
        b = by.get("bbbb", {})
        check("前一個工作階段選最後寫交接單的 aaaa", os.path.basename(b.get("prev", "")).startswith("aaaa"))
        check("動手前使用者又講 1 次（通知不算）、問 1 題", b.get("user_turns") == 1 and b.get("asks") == 1)
        check("動手前讀 3 個檔、改檔後讀的不算", b.get("reads") == 3)
        check("重讀 1 個（login.jsp；專案紀錄本身不算、斜線寫法不同也對得上）", b.get("reread") == ["code/alpha/login.jsp"])
        check("重跑 1 個指令（空白不同也算同一個；git status 太短不算）", b.get("rerun") == [long_cmd])
        check("開始改檔時對話 12 萬", b.get("ctx") == 120000 and b.get("edited") is True)
        d = by.get("dddd", {})
        check("找不到前一個：重複欄是 None、標記沒改檔", d.get("reread") is None and d.get("rerun") is None and d.get("edited") is False)
        check("接手開始之後才寫交接單的 llll 不會被選成前一個（new.css 不算重讀）",
              "code/alpha/new.css" not in (b.get("reread") or []))
        check("這段期間寫交接單的工作階段 2 個（aaaa、llll；zzzz 在期間之前）", written == 2)

        text = "\n".join(hm.section("2026-01-05T00:00:00", "2026-01-12T00:00:00", root))
        check("報表一節：有表格、找不到前一個有寫明", "| bbbb | 1 | 1 | 3 | 1 | 1 | 12 萬 |" in text and "找不到前一個" in text)
        empty = "\n".join(hm.section("2026-02-02T00:00:00", "2026-02-09T00:00:00", root))
        check("沒有接手的工作階段：寫明沒有、不出表格", "沒有接手的工作階段" in empty and "|---" not in empty)

        rep = tw.report(datetime.date(2026, 1, 5), root=root)
        check("每週報表有〈交接〉一節", "## 交接（接手的工作階段動手前做了什麼）" in rep and "接手的工作階段 2 個" in rep)

    check("路徑正規化：只留最後三段、不分大小寫與斜線", hm.norm(r"`C:\A\B\c\D.md`") == hm.norm("~/x/b/C/d.md") == "b/c/d.md")
    print("\n%s（%d 項失敗）" % ("全部通過" if not fails else "有失敗", len(fails)))
    print("failures:", len(fails))      # run_tests.py 認這一行
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
