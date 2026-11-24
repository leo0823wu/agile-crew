"""定期技能優化的數字部分（見 references/retro.md〈定期技能優化〉）。

只讀不改：算出這段期間的回顧指標、行動項關閉率、技能改版成效、lessons 新增與再犯、重號，
並列出「可能重複」「可能過時」「再犯 >= 2 還不是機制」的候選，交給技能優化判斷要不要動。
回顧紀錄、改版紀錄、本地 lessons 從本地資料夾讀（DEV_TEAM_LOCAL，預設 ~/.claude/dev-team-local）。

用法：
  python -I team_metrics.py [--days 7] [--snapshot 路徑] [--save-snapshot]
    --snapshot       上週存的快照（每列的再犯次數），用來算「這週新增幾列、哪幾列再犯 +1」
    --save-snapshot  跑完把這週的快照寫回 --snapshot（週彙總最後才加，測試時不要加）
"""
import argparse
import datetime
import difflib
import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import round_time as RT  # noqa: E402  耗時欄的格式（回填：round_time.py --fill）

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(SKILL, "references")
LOCAL = os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "dev-team-local")
LESSON_FILES = (os.path.join(REF, "lessons-workflow.md"), os.path.join(REF, "lessons-tech.md"),
                os.path.join(LOCAL, "lessons-local.md"))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def section(text, title):
    m = re.search(r"^## " + title + r".*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[: n.start()] if n else rest


def num(pattern, text):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def rework(text):
    """「重工 2（…）」→ 2；「重工：A、B（…）」這種沒寫數字的 → 數頂層的「、」分出幾項；沒寫 → 0。"""
    m = re.search(r"重工\s*(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"重工[：:]\s*([^；;|]+)", text)
    if not m:
        return 0
    depth, items = 0, 1
    for ch in m.group(1):
        depth += ch in "（(「"
        depth -= ch in "）)」"
        items += ch == "、" and depth == 0
    return items


def retro_rows():
    path = os.path.join(LOCAL, "retro-log.md")
    if not os.path.exists(path):
        return []
    text = read(path)
    rows = []
    head = []
    for line in section(text, "回顧紀錄").splitlines():
        if line.startswith("| 日期"):
            head = cells(line)
        if re.match(r"^\| \d{4}-\d{2}-\d{2} ", line):
            c = cells(line)
            mi = head.index("指標摘要") if "指標摘要" in head else 2
            di = head.index("耗時") if "耗時" in head else None
            rows.append({
                "date": datetime.date.fromisoformat(c[0]),
                "what": c[1],
                "corr": num(r"糾正\s*(\d+)", c[mi]),
                "ask": num(r"追問(?:狀況)?\s*(\d+)", c[mi]),
                "qa": num(r"QA 退回\s*(\d+)", c[mi]),
                "rework": rework(c[mi]),
                "dur": RT.parse_cell(c[di]) if di is not None and di < len(c) else None,
                "done": len(re.findall(r"✅", " ".join(c[4:]))),
                "open": len(re.findall(r"⏳", " ".join(c[4:]))),
            })
    return rows


def weekly_trend(rows, weeks):
    """按週（週一～週日）：每類的回顧數、平均糾正／追問／QA 退回／重工、耗時中位數。
    類別看耗時欄：開發＝開發任務、問答＝小問答；補寫（hook 逼出來補做的回顧）與沒耗時的只算進「全部」。"""
    def monday(d):
        return d - datetime.timedelta(days=d.weekday())

    def med(xs):
        xs = sorted(xs)
        if not xs:
            return "—"
        mid = len(xs) // 2
        return f"{(xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2):.1f}h"

    def mean(rs, k):
        return f"{sum(r[k] for r in rs) / len(rs):.2f}" if rs else "—"

    out = []
    starts = sorted({monday(r["date"]) for r in rows}, reverse=True)[:weeks]
    for label, pick in (("全部", lambda r: True),
                        ("開發任務", lambda r: r["dur"] and r["dur"]["kind"] == "開發"),
                        ("小問答", lambda r: r["dur"] and r["dur"]["kind"] == "問答")):
        out.append(f"\n**{label}**\n")
        out.append("| 週 | 回顧數 | 糾正 | 追問 | QA 退回 | 重工 | 耗時中位數 | 實際工作中位數 | 等使用者中位數 | 備註 |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for s in sorted(starts):
            rs = [r for r in rows if monday(r["date"]) == s and pick(r)]
            ds = [r["dur"] for r in rs if r["dur"] and r["dur"]["kind"] != "補寫"]
            note = []
            if len(rs) < 3:
                note.append("樣本不足")
            if label == "全部":
                forced = sum(1 for r in rs if r["dur"] and r["dur"]["kind"] == "補寫")
                none = sum(1 for r in rs if not r["dur"])
                note += [f"補寫 {forced} 列不算耗時"] if forced else []
                note += [f"{none} 列沒有耗時"] if none else []
            out.append(f"| {s:%m-%d}～{s + datetime.timedelta(days=6):%m-%d} | {len(rs)} | {mean(rs, 'corr')} | "
                       f"{mean(rs, 'ask')} | {mean(rs, 'qa')} | {mean(rs, 'rework')} | "
                       f"{med([d['total'] for d in ds])} | {med([d['work'] for d in ds])} | "
                       f"{med([d['user'] for d in ds])} | {'；'.join(note)} |")
    return out


def lessons():
    out = []
    for path in LESSON_FILES:
        if not os.path.exists(path):
            continue
        name = os.path.basename(path)
        sec = ""
        for line in read(path).splitlines():
            if line.startswith("## "):
                sec = line[3:].split()[0]
            elif re.match(r"^\| [LP]-\d", line) and not sec.startswith("本地細節"):
                c = cells(line)
                if len(c) >= 5:
                    out.append({"id": c[0], "file": name, "sec": sec, "what": c[1], "how": c[3],
                                "rep": int(c[-1]) if c[-1].isdigit() else 0})
    return out


def skill_changes():
    path = os.path.join(LOCAL, "skill-changelog.md")
    if not os.path.exists(path):
        return []
    out = []
    for line in section(read(path), "改版紀錄").splitlines():
        if re.match(r"^\| \d{4}-\d{2}-\d{2} ", line):
            c = cells(line)
            if len(c) >= 5:
                mark = "✅" if c[4].startswith("✅") else "❌" if c[4].startswith("❌") else "⏳"
                out.append({"date": datetime.date.fromisoformat(c[0]), "what": c[1], "mark": mark})
    return out


def unmechanized(rows):
    return [r for r in rows if r["rep"] >= 2
            and ("⏳" in r["how"] or not re.search(r"機制|hook|Test|測試|腳本", r["how"]))]


def similar_pairs(rows, top=5, floor=0.45):
    def norm(r):
        return re.sub(r"[\s`*（）()，。、；：「」0-9a-zA-Z-]", "", r["what"] + r["how"])
    texts = [norm(r) for r in rows]
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            sm = difflib.SequenceMatcher(None, texts[i], texts[j], autojunk=False)
            if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
                continue
            ratio = sm.ratio()
            if ratio >= floor:
                pairs.append((ratio, rows[i]["id"], rows[j]["id"]))
    return sorted(pairs, reverse=True)[:top]


def possibly_stale(rows, today, days=90):
    out = []
    for r in rows:
        dates = re.findall(r"(20\d\d)-(\d\d)-(\d\d)", r["what"] + r["how"])
        if r["rep"] == 0 and dates:
            newest = max(datetime.date(int(y), int(m), int(d)) for y, m, d in dates)
            if (today - newest).days > days:
                out.append((r["id"], newest))
    return out


def short(t, n=50):
    t = re.sub(r"\*\*|`", "", t)
    return t if len(t) <= n else t[: n - 1] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--snapshot")
    ap.add_argument("--save-snapshot", action="store_true")
    ap.add_argument("--sim", type=float, default=0.3, help="可能重複的相似度門檻")
    ap.add_argument("--trend", action="store_true", help="只印每週趨勢（回答「有沒有變快、變好」用）")
    ap.add_argument("--weeks", type=int, default=8, help="趨勢列幾週")
    a = ap.parse_args()
    today = datetime.date.today()
    since = today - datetime.timedelta(days=a.days - 1)

    rr = retro_rows()
    trend = ["## 每週趨勢（retro-log〈回顧紀錄〉；耗時由 round_time.py --fill 從工作階段紀錄算）",
             "糾正、追問、QA 退回、重工是每列平均；耗時看中位數（少數超長的輪次會把平均拉歪）。"
             "實際工作＝耗時－等使用者－等外部。補寫＝被 retro_gate 擋下才補做的回顧，真正的工作在更早，不算耗時。"]
    trend += weekly_trend(rr, a.weeks)
    missing = sum(1 for r in rr if r["dur"] is None)
    if missing:
        trend.append(f"\n（{missing} 列沒有耗時：跑 `python -I scripts/round_time.py --fill` 補；寫「—」的是找不到工作階段紀錄）")
    if a.trend:
        print("\n".join(trend))
        return
    week = [r for r in rr if r["date"] >= since]
    ls = lessons()
    snap = {}
    if a.snapshot and os.path.exists(a.snapshot):
        snap = json.loads(read(a.snapshot))
    new_ids = [r["id"] for r in ls if snap and r["id"] not in snap]
    rep_up = [(r["id"], snap[r["id"]], r["rep"]) for r in ls if r["id"] in snap and r["rep"] > snap[r["id"]]]

    def avg(key, rows):
        return f"{sum(r[key] for r in rows) / len(rows):.1f}" if rows else "—"

    done_all, open_all = sum(r["done"] for r in rr), sum(r["open"] for r in rr)
    done_w, open_w = sum(r["done"] for r in week), sum(r["open"] for r in week)
    rate = lambda d, o: f"{d / (d + o):.0%}" if d + o else "—"  # noqa: E731

    p = print
    p(f"# 團隊經驗週彙總數字 {since}～{today}")
    p()
    p("## 回顧（retro-log.md）")
    p(f"- 這週回顧 {len(week)} 次（全部 {len(rr)} 次）")
    p(f"- 這週平均：使用者糾正 {avg('corr', week)}、追問狀況 {avg('ask', week)}、QA 退回 {avg('qa', week)}")
    p(f"- 全部平均：使用者糾正 {avg('corr', rr)}、追問狀況 {avg('ask', rr)}、QA 退回 {avg('qa', rr)}")
    p(f"- 行動項關閉率：這週 {rate(done_w, open_w)}（✅{done_w}／⏳{open_w}）；全部 {rate(done_all, open_all)}（✅{done_all}／⏳{open_all}）")
    p()
    p("## 技能改版與成效（skill-changelog.md）")
    sc = skill_changes()
    sc_w = [s for s in sc if s["date"] >= since]
    cnt = lambda rows, m: sum(1 for s in rows if s["mark"] == m)  # noqa: E731
    p(f"- 這週改了技能 {len(sc_w)} 處（全部 {len(sc)} 處）")
    p(f"- 成效：✅ 有效 {cnt(sc, '✅')}、❌ 沒效 {cnt(sc, '❌')}、⏳ 還沒機會驗證 {cnt(sc, '⏳')}")
    for s in sc:
        if s["mark"] == "❌":
            p(f"  - ❌ {s['date']} {short(s['what'], 60)}（要換做法）")
    stale_pending = [s for s in sc if s["mark"] == "⏳" and (today - s["date"]).days > 30]
    if stale_pending:
        p(f"- 超過 30 天還沒驗證：{len(stale_pending)} 處（看是沒碰到相關工作，還是忘了填）")
    p()
    p("## 踩坑表（lessons）")
    by_sec = {}
    for r in ls:
        by_sec[r["sec"]] = by_sec.get(r["sec"], 0) + 1
    p(f"- 共 {len(ls)} 列：" + "、".join(f"{k} {v}" for k, v in by_sec.items()))
    if snap:
        p(f"- 這週新增 {len(new_ids)} 列：{'、'.join(new_ids) or '無'}")
        p(f"- 這週再犯 +1：{len(rep_up)} 列 " + "、".join(f"{i}（{o}→{n}）" for i, o, n in rep_up))
    else:
        p("- 沒有上週快照（第一次跑），新增與再犯變化從下週開始算")
    um = unmechanized(ls)
    p(f"- 再犯 ≥ 2 還不是機制：{len(um)} 列")
    for r in um:
        p(f"  - {r['id']}（再犯 {r['rep']}）{short(r['what'])}")
    chk = subprocess.run([sys.executable, "-I", os.path.join(SKILL, "scripts", "lesson_id.py"), "check"],
                         capture_output=True)
    p("- 編號檢查：" + chk.stdout.decode("utf-8").strip().replace("\n", "；"))
    p()
    p("## 候選（要人判斷，不代表一定要改）")
    pairs = similar_pairs(ls, floor=a.sim)
    p(f"- 可能重複（文字相似度）：{len(pairs)} 組")
    for ratio, x, y in pairs:
        p(f"  - {x} ↔ {y}（{ratio:.0%}）")
    stale = possibly_stale(ls, today)
    p(f"- 可能過時（再犯 0、列裡最新的日期超過 90 天）：{len(stale)} 列 " + "、".join(f"{i}（{d}）" for i, d in stale))
    p()
    p("\n".join(trend))
    p()
    p("## 〈趨勢〉表建議加的一列")
    rep_sum = sum(n - o for _, o, n in rep_up) if snap else "—"
    p(f"| {since}～{today} | {len(week)} | {avg('corr', week)} | {avg('qa', week)} | {rep_sum} | {rate(done_w, open_w)} |")

    if a.save_snapshot and a.snapshot:
        os.makedirs(os.path.dirname(os.path.abspath(a.snapshot)), exist_ok=True)
        with open(a.snapshot, "w", encoding="utf-8") as f:
            json.dump({r["id"]: r["rep"] for r in ls}, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
