"""量交接順不順：找出「接手的工作階段」，數它動手前做了多少跟前一個工作階段重複的事。唯讀，不花 token。

做法與指標的意思見 references/handoff.md 第 4 節。
- 接手的工作階段：使用者（或開它的那個工作階段）的訊息裡，有一行以「交接單：<專案紀錄路徑>.md」開頭（交接時固定這樣寫）。
- 前一個工作階段：在它開始之前，最後一個改過那份專案紀錄、而且改的內容有交接單標題或「下一步的第一個動作」的工作階段。
- 動手前：從接手的那則訊息到第一次改檔（Edit／Write）為止；整個工作階段都沒改檔就算到結束。
數字是客觀的線索，不是結論：要改的檔本來就得讀一次；「有沒有回頭問使用者之前做到哪」由回顧的 `接手問 N` 填。

用法：python -X utf8 -I handoff_metrics.py [--since 2026-01-05] [--until 2026-01-12]   （本機日期，不含 until 那天；預設最近 7 天）
"""
import datetime
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import token_usage as tu  # noqa: E402

MARK = re.compile(r"(?m)^[ \t>]*交接單[：:][ \t]*`?([^\n`]*?\.md)")
KEY = "交接單".encode("utf-8")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
MIN_CMD = 20          # 比這短的指令（git status、ls）重跑不算
LOOKBACK_DAYS = 14    # 前一個工作階段最多往回找幾天
NOISE = ("<", "Stop hook feedback", "[Request interrupted")


def norm(path):
    """路徑比對用：統一斜線與大小寫，只留最後三段（同一份紀錄有人寫 ~、有人寫完整路徑）。"""
    parts = [x for x in str(path or "").strip().strip("`\"' ").replace("\\", "/").lower().split("/") if x]
    return "/".join(parts[-3:])


def cmd_key(cmd):
    return re.sub(r"\s+", " ", str(cmd or "")).strip()


def has_key(path):
    """檔案裡有沒有「交接單」三個字（位元組比對，很快）；沒有的整份不用解析。"""
    try:
        with open(path, "rb") as f:
            tail = b""
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    return False
                if KEY in tail + chunk:
                    return True
                tail = chunk[-16:]
    except OSError:
        return False


def analyze(ev):
    """一個工作階段的事件（token_usage.load 的格式）→ 交接相關的摘要。"""
    info = {"start": "", "record": "", "mark_at": None, "writes": [], "reads": set(), "cmds": set()}
    for i, e in enumerate(ev):
        ts = e[2] if e[0] == "user" else e[4]
        if ts and not info["start"]:
            info["start"] = ts
        if e[0] == "user":
            if info["mark_at"] is None:
                m = MARK.search(e[1])
                if m:
                    info["mark_at"], info["record"] = i, norm(m.group(1))
            continue
        for name, inp in e[3]:
            if name == "Read":
                info["reads"].add(norm(inp.get("file_path")))
            elif name in SHELL_TOOLS:
                info["cmds"].add(cmd_key(inp.get("command")))
            elif name in EDIT_TOOLS:
                body = "%s%s" % (inp.get("new_string") or "", inp.get("content") or "")
                if "## 交接單" in body or "**下一步的第一個動作**" in body:
                    info["writes"].append((ts, norm(inp.get("file_path"))))
    if info["mark_at"] is None:
        return info
    # 動手前：接手那則訊息之後，到第一次改檔為止
    pre = {"user_turns": 0, "asks": 0, "reads": set(), "cmds": set(), "ctx": 0, "edited": False}
    for e in ev[info["mark_at"] + 1:]:
        if e[0] == "user":
            if not e[1].lstrip().startswith(NOISE):
                pre["user_turns"] += 1
            continue
        pre["ctx"] = tu.ctx(e[2]) or pre["ctx"]
        hit = False
        for name, inp in e[3]:
            if name in EDIT_TOOLS:
                hit = True
            elif name == "AskUserQuestion":
                pre["asks"] += 1
            elif name == "Read":
                pre["reads"].add(norm(inp.get("file_path")))
            elif name in SHELL_TOOLS:
                pre["cmds"].add(cmd_key(inp.get("command")))
        if hit:
            pre["edited"] = True
            break
    info["pre"] = pre
    return info


def collect(lo, hi, root=None):
    """lo、hi：UTC 時間字串（跟紀錄檔的時間欄位同格式）。回傳 (接手的工作階段清單, 這段期間寫交接單的次數)。"""
    root = root or tu.ROOT
    floor = datetime.datetime.strptime(lo[:10], "%Y-%m-%d").timestamp() - (LOOKBACK_DAYS + 1) * 86400
    sessions = []
    for p in glob.glob(os.path.join(root, "*", "*.jsonl")):
        try:
            if os.path.getmtime(p) < floor or not has_key(p):
                continue
        except OSError:
            continue
        info = analyze(tu.load(p))
        info["path"] = p
        sessions.append(info)
    written = sum(1 for s in sessions if any(lo <= ts < hi for ts, _ in s["writes"]))
    out = []
    for s in sessions:
        if s["mark_at"] is None or not (lo <= s["start"] < hi):
            continue
        prev, prev_ts = None, ""
        for a in sessions:
            if a is s:
                continue
            for ts, rec in a["writes"]:
                if rec == s["record"] and prev_ts < ts < s["start"]:
                    prev, prev_ts = a, ts
        pre = s["pre"]
        row = {"path": s["path"], "start": s["start"], "record": s["record"], "user_turns": pre["user_turns"], "asks": pre["asks"],
               "reads": len(pre["reads"] - {""}), "ctx": pre["ctx"], "edited": pre["edited"], "prev": prev["path"] if prev else "",
               "reread": None, "rerun": None}
        if prev:
            row["reread"] = sorted((pre["reads"] & prev["reads"]) - {s["record"], ""})
            row["rerun"] = sorted(c for c in pre["cmds"] & prev["cmds"] if len(c) >= MIN_CMD)
        out.append(row)
    out.sort(key=lambda r: r["start"])
    return out, written


def section(lo, hi, root=None, title=None):
    """每週報表用的〈交接〉一節（markdown 的行）。title：給工作階段路徑、回傳顯示名稱的函式。"""
    rows, written = collect(lo, hi, root)
    L = ["## 交接（接手的工作階段動手前做了什麼）", "",
         "- 這一週寫了交接單的工作階段 %d 個、接手的工作階段 %d 個" % (written, len(rows))]
    if not rows:
        L.append("- 沒有接手的工作階段（接手的訊息裡要有一行「交接單：<專案紀錄路徑>」才認得出來）。")
        return L
    L += ["", "| 接手的工作階段 | 動手前使用者又講了幾次 | 動手前問了幾題 | 動手前讀的檔 | 其中前一個也讀過 | 重跑同樣的指令 | 開始改檔時對話多大 |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        name = (title(r["path"]) if title else "") or os.path.basename(r["path"]).split(".")[0][:8]
        no_prev = "找不到前一個"
        L.append("| %s | %d | %d | %d | %s | %s | %s |" % (
            str(name).replace("|", "／"), r["user_turns"], r["asks"], r["reads"],
            no_prev if r["reread"] is None else "%d" % len(r["reread"]),
            no_prev if r["rerun"] is None else "%d" % len(r["rerun"]),
            ("%.0f 萬" % (r["ctx"] / 1e4)) + ("" if r["edited"] else "（整個工作階段沒改檔）")))
    L += ["", "> 這些是線索不是結論：要改的檔本來就得讀一次。數字偏高的再看那個工作階段回顧寫的 `接手問 N`、`接手重做 N`（references/handoff.md）。"]
    return L


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import token_weekly as tw
    args = sys.argv[1:]
    today = datetime.date.today()
    until = datetime.datetime.strptime(args[args.index("--until") + 1], "%Y-%m-%d").date() if "--until" in args else today + datetime.timedelta(days=1)
    since = datetime.datetime.strptime(args[args.index("--since") + 1], "%Y-%m-%d").date() if "--since" in args else until - datetime.timedelta(days=7)
    lo, hi = tw.utc_iso(since), tw.utc_iso(until)
    print("\n".join(section(lo, hi, title=lambda p: tw.meta(p)[0])))
    rows, _ = collect(lo, hi)
    for r in rows:
        if r["reread"] or r["rerun"]:
            print("\n%s 重複的：" % os.path.basename(r["path"])[:8])
            for x in r["reread"]:
                print("  讀 " + x)
            for x in r["rerun"]:
                print("  跑 " + x[:120])
    return 0


if __name__ == "__main__":
    sys.exit(main())
