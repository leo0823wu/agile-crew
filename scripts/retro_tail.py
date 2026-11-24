"""印出回顧紀錄最近幾列的摘要（不用把整份回顧紀錄讀進對話）。

用法：python -X utf8 -I retro_tail.py [列數，預設 5] [每格最多幾個字，預設 160]
"""
import os
import re
import sys

LOCAL = os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "dev-team-local")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cut = int(sys.argv[2]) if len(sys.argv) > 2 else 160
    path = os.path.join(LOCAL, "retro-log.md")
    if not os.path.exists(path):
        print("沒有回顧紀錄：%s" % path)
        return 1
    text = open(path, encoding="utf-8").read()
    m = re.search(r"^## 回顧紀錄.*$", text, re.M)
    rows = [l for l in (text[m.end():] if m else text).splitlines() if re.match(r"^\|\s*\d{4}-\d{2}-\d{2}", l)]
    for line in rows[:n]:
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        c += [""] * (7 - len(c))
        short = lambda s: s if len(s) <= cut else s[: cut - 1] + "…"
        print("● %s｜%s" % (c[0], short(c[1])))
        print("  發現：%s" % short(c[3]))
        print("  狀態：%s" % short(c[5]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
