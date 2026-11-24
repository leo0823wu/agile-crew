"""這個錯誤是不是「本來就有」？把 log 裡每個關鍵字逐日計數（L-062：說「之前就有／重啟前就有」前必跑）。

用法：python -X utf8 -I log_daily_count.py <log 檔…> -e <關鍵字或正規表示式> [-e …] [--days 14]
  log 檔可以是一般檔、.gz，或「-」讀標準輸入（例：ssh 主機 'docker logs 容器 2>&1' | python … -）
  日期支援 2026-11-06、2026/11/06、06-Nov-2026（Tomcat catalina）、[06/Nov/2026（存取紀錄）；
  沒有日期的行（例：例外的堆疊行）算進上一個有日期的行那天。
輸出：每個關鍵字的總次數、第一次／最後一次出現的日期、最近 N 天逐日次數。
「最近幾天才出現」跟「每天都有」結論相反，回報時把這張表附上當證據。
"""
import argparse
import collections
import gzip
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
MON = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
DATE = re.compile(r"(\d{4})[-/](\d{2})[-/](\d{2})|(\d{2})[-/](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/](\d{4})")


def day_of(line):
    m = DATE.search(line[:60])
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return f"{m.group(6)}-{MON[m.group(5)]:02d}-{m.group(4)}"


def lines(path):
    if path == "-":
        yield from sys.stdin.buffer
    elif path.endswith(".gz"):
        with gzip.open(path, "rb") as f:
            yield from f
    else:
        with open(path, "rb") as f:
            yield from f


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("-e", dest="pats", action="append", required=True, help="關鍵字或正規表示式，可多個")
    ap.add_argument("--days", type=int, default=14, help="列出最近幾天的逐日次數（預設 14）")
    a = ap.parse_args()
    pats = [(p, re.compile(p)) for p in a.pats]
    count = {p: collections.Counter() for p, _ in pats}
    seen_days = set()
    for path in a.files:
        cur = None
        for raw in lines(path):
            line = raw.decode("utf-8", "replace")
            d = day_of(line)
            if d:
                cur = d
                seen_days.add(d)
            for p, rx in pats:
                if rx.search(line):
                    count[p][cur or "（沒有日期）"] += 1
    days = sorted(seen_days)
    if not days:
        print("log 裡找不到日期，無法逐日統計（確認檔案對不對、日期格式）")
    else:
        print(f"log 涵蓋 {days[0]} ～ {days[-1]}，共 {len(days)} 天有紀錄")
    recent = days[-a.days:]
    for p, _ in pats:
        c = count[p]
        dated = sorted(k for k in c if k[0].isdigit())
        total = sum(c.values())
        if not total:
            print(f"\n「{p}」：0 次（整段 log 都沒有）")
            continue
        print(f"\n「{p}」：共 {total} 次，出現在 {len(dated)} 天；第一次 {dated[0] if dated else '—'}、最後一次 {dated[-1] if dated else '—'}")
        print("  最近逐日：" + "  ".join(f"{d[5:]} {c.get(d, 0)}" for d in recent))
        if dated and recent and dated[0] >= recent[-min(3, len(recent))]:
            print("  → 只在最近幾天出現：不是「本來就有」")


if __name__ == "__main__":
    main()
