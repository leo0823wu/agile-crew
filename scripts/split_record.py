"""把專案紀錄裡舊的進度、已解決的問題、已完成的待辦搬到同資料夾的歷史檔，讓專案紀錄只留現況。

只搬整列／整個項目，不改寫任何文字；搬完核對「留下的＋搬走的＝原本的」，對不上就不寫檔。

用法：
  python -X utf8 -I split_record.py <紀錄檔> [...]          預設只預覽
  python -X utf8 -I split_record.py --all                    本地 config.json 總表裡的每一份
  加 --apply 才真的寫檔；--days 7（幾天內的留下）；--keep 5（工作進度至少留最新幾列）

搬的規則：
  工作進度：超過 --days 天、而且不在最新 --keep 列裡的列
  遇到的問題：狀態格有 ✅、沒有 ⏳、而且超過 --days 天的列
  待辦：開頭是 ✅、整個項目裡最新的日期超過 --days 天的項目（找不到日期的留下）
  其他段落（基本資料、目前狀況、資安檢測…）不動
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projlib  # noqa: E402

POINTER = "> 舊的進度、已解決的問題、已完成的待辦在同資料夾的 `%s`（開工不用讀，要查舊事再 Grep）。"
DATE = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})")
MD = re.compile(r"(?<![\d/.-])(\d{1,2})/(\d{1,2})(?![\d/])")


def est(s):
    cjk = sum(1 for ch in s if "⺀" <= ch <= "鿿" or "＀" <= ch <= "￯" or "　" <= ch <= "〿")
    return int(cjk * 1.1 + (len(s) - cjk) / 3.6)


def latest_date(text, today):
    ds = []
    for y, m, d in DATE.findall(text):
        try:
            ds.append(datetime.date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for m, d in MD.findall(text):
        try:
            dt = datetime.date(today.year, int(m), int(d))
            if dt > today + datetime.timedelta(days=31):
                dt = datetime.date(today.year - 1, int(m), int(d))
            ds.append(dt)
        except ValueError:
            pass
    return max(ds) if ds else None


def row_date(line):
    m = re.match(r"^\|\s*(20\d{2})-(\d{1,2})-(\d{1,2})", line)
    if not m:
        return None
    try:
        return datetime.date(*map(int, m.groups()))
    except ValueError:
        return None


def split_sections(lines):
    """[(標題行或 None, [行…])]，依 '## ' 切。"""
    out = [[None, []]]
    for l in lines:
        if l.startswith("## "):
            out.append([l, []])
        else:
            out[-1][1].append(l)
    return out


def plan(lines, today, days, keep):
    cutoff = today - datetime.timedelta(days=days)
    secs = split_sections(lines)
    moved = {"progress": [], "problems": [], "todos": []}
    heads = {}
    for sec in secs:
        title, body = sec
        if title is None:
            continue
        if title.startswith("## 工作進度"):
            rows = [i for i, l in enumerate(body) if row_date(l)]
            heads["progress"] = [l for l in body if l.startswith("|") and not row_date(l)][:2]
            order = sorted(rows, key=lambda i: row_date(body[i]), reverse=True)
            safe = set(order[:keep])
            drop = [i for i in rows if i not in safe and row_date(body[i]) < cutoff]
            moved["progress"] = [body[i] for i in drop]
            sec[1] = [l for i, l in enumerate(body) if i not in set(drop)]
        elif title.startswith("## 遇到的問題"):
            heads["problems"] = [l for l in body if l.startswith("|") and not row_date(l)][:2]
            drop = []
            for i, l in enumerate(body):
                d = row_date(l)
                if not d or d >= cutoff:
                    continue
                last = projlib.cells(l)[-1]
                if "✅" in last and "⏳" not in l:
                    drop.append(i)
            moved["problems"] = [body[i] for i in drop]
            sec[1] = [l for i, l in enumerate(body) if i not in set(drop)]
        elif title.startswith("## 待辦"):
            # 一個項目＝「- 」開頭的行＋後面縮排的續行
            items, cur = [], None
            for i, l in enumerate(body):
                if re.match(r"^[-*]\s", l):
                    cur = [i]
                    items.append(cur)
                elif cur is not None and l.startswith((" ", "\t")) and l.strip():
                    cur.append(i)
                else:
                    cur = None
            drop = set()
            for it in items:
                text = "\n".join(body[i] for i in it)
                if not re.match(r"^[-*]\s*✅", body[it[0]]) or "⏳" in text:
                    continue
                d = latest_date(text, today)
                if d and d < cutoff:
                    drop.update(it)
            moved["todos"] = [body[i] for i in sorted(drop)]
            sec[1] = [l for i, l in enumerate(body) if i not in drop]
    kept = []
    for title, body in secs:
        if title is not None:
            kept.append(title)
        kept.extend(body)
    return kept, moved, heads


def merge_history(path, title, moved, heads):
    names = [("progress", "## 工作進度（新的在上）"), ("problems", "## 遇到的問題"), ("todos", "## 已完成的待辦")]
    if os.path.exists(path):
        lines = projlib.read(path).replace("\r\n", "\n").split("\n")
    else:
        lines = ["# %s 歷史紀錄" % title, "",
                 "> 從 `%s` 搬來的舊進度、已解決的問題、已完成的待辦，原文沒有改。開工不用讀，要查舊事時 Grep。" % projlib.RECORD, ""]
    secs = split_sections(lines)
    for key, head in names:
        if not moved[key]:
            continue
        sec = next((s for s in secs if s[0] and s[0].startswith(head[:8])), None)
        if sec is None:
            sec = [head, [""] + (heads.get(key, []) if key != "todos" else []) + [""]]
            secs.append(sec)
        body = sec[1]
        if key == "todos":
            at = next((i for i, l in enumerate(body) if l.strip()), len(body))
        else:
            tbl = [i for i, l in enumerate(body) if l.startswith("|") and not row_date(l)]
            at = (tbl[-1] + 1) if tbl else len(body)
        sec[1] = body[:at] + moved[key] + body[at:]
    out = []
    for t, body in secs:
        if t is not None:
            out.append(t)
        out.extend(body)
    return out


def process(path, today, days, keep, apply):
    raw = open(path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig", errors="replace")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    kept, moved, heads = plan(lines, today, days, keep)
    n = sum(len(v) for v in moved.values())
    all_moved = moved["progress"] + moved["problems"] + moved["todos"]
    if sorted(kept + all_moved) != sorted(lines):
        print("✗ %s：核對不過（留下＋搬走≠原本），不處理" % path)
        return None
    before = est(text)
    if n and not any(projlib.HISTORY in l for l in kept[:12]):
        pointer = POINTER % os.path.basename(projlib.history_path(path))
        at = next((i for i, l in enumerate(kept) if l.startswith("## ")), len(kept))
        while at > 0 and not kept[at - 1].strip():
            at -= 1
        kept = kept[:at] + [pointer, ""] + kept[at:]
    after_text = "\n".join(kept)
    cur = projlib.section(after_text, "目前狀況")
    info = (before, est(after_text), len(moved["progress"]), len(moved["problems"]), len(moved["todos"]), est(cur))
    if apply and n:
        hist_path = projlib.history_path(path)
        title = re.sub(r"^#\s*|\s*專案紀錄\s*$", "", lines[0]).strip() or os.path.basename(os.path.dirname(path))
        hist = merge_history(hist_path, title, moved, heads)
        with open(hist_path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(hist).replace("\n", nl))
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(after_text.replace("\n", nl))
    return info


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    apply = "--apply" in args
    days = int(args[args.index("--days") + 1]) if "--days" in args else 7
    keep = int(args[args.index("--keep") + 1]) if "--keep" in args else 5
    skip = set()
    for flag in ("--days", "--keep"):
        if flag in args:
            skip.add(args.index(flag) + 1)
    paths = [a for i, a in enumerate(args) if not a.startswith("--") and i not in skip]
    if "--all" in args:
        paths += [p["path"] for p in projlib.projects()]
    if not paths:
        print(__doc__)
        return 1
    today = datetime.date.today()
    print("%s｜%d 天內的留下、工作進度至少留 %d 列" % ("寫檔" if apply else "預覽（加 --apply 才寫檔）", days, keep))
    print("  改前→改後（估 token）｜搬走：進度／問題／待辦｜目前狀況那一節多大｜檔案")
    tb = ta = 0
    for p in paths:
        r = process(p, today, days, keep, apply)
        if not r:
            continue
        tb += r[0]
        ta += r[1]
        flag = "  ←目前狀況偏長，要人工整理" if r[5] > 1500 else ""
        print("  %6d → %6d｜%3d／%2d／%2d｜%5d｜%s%s" % (r[0], r[1], r[2], r[3], r[4], r[5], p, flag))
    print("合計 %d → %d" % (tb, ta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
