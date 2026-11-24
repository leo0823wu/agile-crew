"""read_guard.py 的測試：用暫存檔，不碰真實資料。每條都有該擋／不該擋的對照。
執行：python -X utf8 -I test_read_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import read_guard as rg  # noqa: E402


def main():
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "dev-team-local")
        os.makedirs(d)
        other = os.path.join(tmp, "elsewhere")
        os.makedirs(other)
        row = "| 2026-01-01 | " + "內容" * 500 + " |\n"          # 一列約 1000 字
        big = os.path.join(d, "retro-log.md")
        with open(big, "w", encoding="utf-8") as f:
            f.write("# 回顧紀錄\n\n| 日期 | 內容 |\n|---|---|\n" + row * 100)   # 約 10 萬字
        small = os.path.join(d, "lessons-tech.md")
        with open(small, "w", encoding="utf-8") as f:
            f.write("# 短的\n" + "一行\n" * 50)
        same_name = os.path.join(other, "retro-log.md")
        with open(same_name, "w", encoding="utf-8") as f:
            f.write(row * 100)
        normal = os.path.join(d, "local-rules.md")
        with open(normal, "w", encoding="utf-8") as f:
            f.write(row * 100)

        check("整份讀長的回顧紀錄：擋", "已擋下" in rg.problem({"file_path": big}))
        check("擋下的說明有教怎麼讀", "retro_tail.py" in rg.problem({"file_path": big}))
        check("limit 8 讀表頭：不擋", rg.problem({"file_path": big, "limit": 8}) == "")
        check("offset 50 limit 15（約 1.5 萬字）：不擋", rg.problem({"file_path": big, "offset": 50, "limit": 15}) == "")
        check("offset 5 limit 60（約 6 萬字）：擋", "已擋下" in rg.problem({"file_path": big, "offset": 5, "limit": 60}))
        check("offset 接近檔尾、沒帶 limit（剩 10 列）：不擋", rg.problem({"file_path": big, "offset": 95}) == "")
        check("limit 是 0（什麼都不讀）：不擋", rg.problem({"file_path": big, "limit": 0}) == "")
        check("同名但本身很短：不擋", rg.problem({"file_path": small}) == "")
        check("別的資料夾的同名檔：不擋", rg.problem({"file_path": same_name}) == "")
        check("同資料夾不在名單的長檔：不擋", rg.problem({"file_path": normal}) == "")
        check("反斜線路徑、檔名大小寫不同：照樣擋", "已擋下" in rg.problem({"file_path": big.replace("/", "\\").replace("retro-log", "Retro-Log")}) or os.name != "nt")
        check("檔案不存在：不擋", rg.problem({"file_path": os.path.join(d, "skill-changelog.md")}) == "")
        check("上限可調：調成 20 萬就不擋", rg.problem({"file_path": big}, 200000) == "")

        def run(payload):
            return subprocess.run([sys.executable, "-I", os.path.join(HERE, "read_guard.py")],
                                  input=payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8"),
                                  capture_output=True)
        p = run({"tool_name": "Read", "tool_input": {"file_path": big}})
        check("當 hook 跑、整份讀：exit 2、stderr 有說明", p.returncode == 2 and "已擋下" in p.stderr.decode("utf-8"))
        p = run({"tool_name": "Read", "tool_input": {"file_path": big, "limit": 8}})
        check("當 hook 跑、讀一小段：exit 0", p.returncode == 0 and not p.stderr)
        p = run({"tool_name": "Edit", "tool_input": {"file_path": big}})
        check("別的工具：exit 0", p.returncode == 0)
        p = run(b"not json")
        check("壞輸入：放行（exit 0）", p.returncode == 0)

    print("\n%s（%d 項失敗）" % ("全部通過" if not fails else "有失敗", len(fails)))
    print("failures:", len(fails))      # run_tests.py 認這一行
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
