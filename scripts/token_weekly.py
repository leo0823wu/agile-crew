"""每週 token 用量報表：上一週（週一到週日，本機時間）花了多少、花在哪、跟前一週比。唯讀，不經過模型，不花 token。

用法：python -X utf8 -I token_weekly.py [--week-of 2026-01-05] [--out <資料夾>] [--top 8]
  --week-of  那一週裡的任何一天；不給就是上一週
  --out      把報表寫成 <資料夾>/<週一日期>週_token用量.md；不給就印在畫面上
適合排程每週一跑一次（Windows 工作排程器／cron 直接執行 python）。

「加權成本」算法跟 token_usage.py 一樣（未快取輸入×1＋寫快取×1.25＋讀快取×0.1＋輸出×5），只用來比大小，不是帳單金額。
報表只放工作階段的標題與資料夾，不放對話內容。
"""
import collections
import contextlib
import datetime
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import token_usage as tu  # noqa: E402

UTC = datetime.timezone.utc
LONG = 400000      # context 超過這個數算「對話太長」


def week_start(day):
    return day - datetime.timedelta(days=day.weekday())


def utc_iso(local_date):
    """本機時間那一天 00:00 換成 UTC 的字串（跟紀錄檔的時間欄位同格式，可以直接比大小）。"""
    return datetime.datetime.combine(local_date, datetime.time()).astimezone().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def local_day(ts):
    try:
        t = datetime.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return "?"
    return t.astimezone().strftime("%m-%d")


def meta(path):
    """工作階段的標題（最後一次命名）與工作資料夾。"""
    title = cwd = ""
    try:
        for line in io.open(path, "rb"):      # 用位元組讀：大檔不用整份轉成文字
            if b'"custom-title"' in line and len(line) < 2000:
                try:
                    title = json.loads(line.decode("utf-8", errors="replace")).get("customTitle") or title
                except ValueError:
                    pass
            elif not cwd and b'"cwd"' in line:
                try:
                    cwd = json.loads(line.decode("utf-8", errors="replace")).get("cwd") or ""
                except ValueError:
                    pass
    except OSError:
        pass
    parts = [x for x in cwd.replace("\\", "/").split("/") if x]
    return title, "/".join(parts[-2:]) if parts else os.path.basename(os.path.dirname(path))[-30:]


def scan(windows, root=None):
    """windows：[(起, 迄)]（UTC 字串，不含迄）。回傳每個視窗的 (分組統計, 各工作階段)。"""
    root = root or tu.ROOT
    floor = datetime.datetime.strptime(min(w[0] for w in windows)[:10], "%Y-%m-%d").timestamp() - 86400
    res = [(collections.defaultdict(collections.Counter), {}) for _ in windows]
    seen = set()
    for p in glob.glob(os.path.join(root, "*", "*.jsonl")):
        if os.path.getmtime(p) < floor:
            continue
        title = folder = None
        sid = os.path.basename(p)[:-6]
        files = [(p, "main")] + [(sp, "sub") for sp in glob.glob(os.path.join(p[:-6], "subagents", "*.jsonl"))]
        for fp, kind in files:
            counted_sub = set()
            for e in tu.load(fp):
                if e[0] != "asst" or e[1] in seen:
                    continue
                u = e[2]
                c = tu.ctx(u)
                if not c:
                    continue
                wi = next((i for i, (lo, hi) in enumerate(windows) if lo <= e[4] < hi), None)
                if wi is None:
                    continue
                seen.add(e[1])
                if title is None:
                    title, folder = meta(p)
                R, sess = res[wi]
                w = tu.weight(u)
                raw = {"in": u.get("input_tokens", 0), "cw": u.get("cache_creation_input_tokens", 0),
                       "cr": u.get("cache_read_input_tokens", 0), "out": u.get("output_tokens", 0)}
                model = ("子代理 " if kind == "sub" else "") + (e[5] or "?")
                for key in (("total",), ("day", local_day(e[4])), ("folder", folder), ("model", model), ("kind", kind)):
                    k = R[key]
                    k["w"] += w
                    k["calls"] += 1
                    for a, b in raw.items():
                        k[a] += b
                s = sess.setdefault(sid, {"title": title, "folder": folder, "c": collections.Counter(), "peak": 0})
                s["c"]["w"] += w
                s["c"][kind] += w
                s["c"]["calls"] += 1
                if kind == "main":
                    s["peak"] = max(s["peak"], c)
                    if c > LONG:
                        s["c"]["long"] += w
                        R[("total",)]["long"] += w
                elif wi not in counted_sub:
                    counted_sub.add(wi)
                    s["c"]["n_sub"] += 1
    return res


def amount(n):
    return "%.1f 億" % (n / 1e8) if n >= 1e8 else "%.0f 萬" % (n / 1e4)


def pct(a, b):
    return "%.0f%%" % (100.0 * a / b) if b else "—"


def three_numbers(lo, hi):
    """token_usage.py 的三個指標（同一段期間）。"""
    buf = io.StringIO()
    argv = sys.argv
    try:
        sys.argv = ["token_usage.py", "--since", lo, "--until", hi, "--top", "0"]
        with contextlib.redirect_stdout(buf):
            tu.main()
    except Exception as ex:      # 指標算不出來不影響其他部分
        return ["（三個指標算不出來：%s）" % ex]
    finally:
        sys.argv = argv
    out, keep = [], False
    for ln in buf.getvalue().split("\n"):
        if ln.startswith("■ 三個要看的數字"):
            keep = True
            continue
        if ln.startswith("■ 動手前讀最多"):
            break
        if keep and ln.strip() and not ln.startswith("■"):
            out.append(ln.strip())
    return out


def report(start, top=8, root=None):
    end, prev = start + datetime.timedelta(days=7), start - datetime.timedelta(days=7)
    lo, hi, plo = utc_iso(start), utc_iso(end), utc_iso(prev)
    (R, sess), (P, _) = scan([(lo, hi), (plo, lo)], root)
    T, PT = R[("total",)], P[("total",)]
    last = end - datetime.timedelta(days=1)
    L = ["# %s 週 token 用量（%s～%s）" % (start.isoformat(), start.strftime("%m/%d"), last.strftime("%m/%d")), ""]
    if not T["w"]:
        L.append("這一週沒有使用紀錄。")
        return "\n".join(L) + "\n"
    main_w = R[("kind", "main")]["w"]
    L += ["## 總量", "",
          "- 加權成本 **%.0fM**%s" % (T["w"] / 1e6, "（前一週 %.0fM，%+.0f%%）" % (PT["w"] / 1e6, 100 * (T["w"] / PT["w"] - 1)) if PT["w"] else "（前一週沒有紀錄）"),
          "- 工作階段 %d 個、模型呼叫 %d 次%s" % (len(sess), T["calls"], "（前一週 %d 次）" % PT["calls"] if PT["calls"] else ""),
          "- 原始 token 合計 %s：重帶舊內容（讀快取）%s、新讀進來（寫快取）%s、未快取輸入 %s、輸出 %s"
          % (amount(T["in"] + T["cw"] + T["cr"] + T["out"]), amount(T["cr"]), amount(T["cw"]), amount(T["in"]), amount(T["out"])),
          "- 主對話 %s、子代理 %s" % (pct(main_w, T["w"]), pct(R[("kind", "sub")]["w"], T["w"])),
          "- 主對話花費裡，對話超過 %d 萬之後花掉的：**%s**" % (LONG / 1e4, pct(T["long"], main_w)), ""]
    L += ["## 要注意的工作階段", ""]
    flagged = [s for s in sess.values() if s["c"]["w"] >= 0.08 * T["w"] and s["c"]["main"] and s["c"]["long"] >= 0.5 * s["c"]["main"]]
    if flagged:
        for s in sorted(flagged, key=lambda s: -s["c"]["w"]):
            L.append("- **%s**（%s）：占全週 %s，最長累積到 %.0f 萬，%s 的花費發生在超過 %d 萬之後——這類對話該早點交接、開新的工作階段。"
                     % (s["title"] or "（未命名）", s["folder"], pct(s["c"]["w"], T["w"]), s["peak"] / 1e4, pct(s["c"]["long"], s["c"]["main"]), LONG / 1e4))
    else:
        L.append("- 沒有「占全週 8%% 以上、而且一半以上花在超過 %d 萬之後」的工作階段。" % (LONG / 1e4))
    L += ["", "## 三個指標與細項（跟 token_usage.py 同一套算法）", ""] + ["- " + x for x in three_numbers(lo, hi)]
    L += ["", "## 按天", "", "| 日期 | 占比 | 加權成本 | 呼叫次數 |", "|---|---|---|---|"]
    for k in sorted(k for k in R if k[0] == "day"):
        L.append("| %s | %s | %.0fM | %d |" % (k[1], pct(R[k]["w"], T["w"]), R[k]["w"] / 1e6, R[k]["calls"]))
    L += ["", "## 按工作資料夾", "", "| 資料夾 | 占比 | 加權成本 |", "|---|---|---|"]
    for k in sorted((k for k in R if k[0] == "folder"), key=lambda k: -R[k]["w"])[:12]:
        L.append("| %s | %s | %.0fM |" % (k[1], pct(R[k]["w"], T["w"]), R[k]["w"] / 1e6))
    L += ["", "## 按模型", "", "| 模型 | 占比 |", "|---|---|"]
    for k in sorted((k for k in R if k[0] == "model"), key=lambda k: -R[k]["w"]):
        L.append("| %s | %s |" % (k[1], pct(R[k]["w"], T["w"])))
    L += ["", "## 最貴的 %d 個工作階段" % top, "", "| 工作階段 | 資料夾 | 占比 | 最長對話 | 超過 %d 萬的花費 | 子代理 |" % (LONG / 1e4), "|---|---|---|---|---|---|"]
    for s in sorted(sess.values(), key=lambda s: -s["c"]["w"])[:top]:
        c = s["c"]
        L.append("| %s | %s | %s | %.0f 萬 | %s | %d 個（%s） |" % ((s["title"] or "（未命名）").replace("|", "／"), s["folder"], pct(c["w"], T["w"]),
                                                              s["peak"] / 1e4, pct(c["long"], c["main"]), c["n_sub"], pct(c["sub"], c["w"])))
    L += ["", "> 加權成本＝未快取輸入×1＋寫快取×1.25＋讀快取×0.1＋輸出×5，單位是等值的輸入 token（M＝百萬），只用來比大小，不是帳單金額。",
          "> 產生時間：%s（token_weekly.py）" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M")]
    return "\n".join(L) + "\n"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    day = (datetime.datetime.strptime(args[args.index("--week-of") + 1], "%Y-%m-%d").date() if "--week-of" in args
           else datetime.date.today() - datetime.timedelta(days=7))
    top = int(args[args.index("--top") + 1]) if "--top" in args else 8
    start = week_start(day)
    text = report(start, top)
    if "--out" in args:
        out_dir = args[args.index("--out") + 1]
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "%s週_token用量.md" % start.isoformat())
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print("已寫入 " + path)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
