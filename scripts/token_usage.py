"""從工作階段紀錄量 token 花在哪，用來檢查工作方式有沒有變省。唯讀。

用法：python -X utf8 -I token_usage.py [--days 14] [--since 2026-01-01] [--until 2026-01-08] [--top 8]
      --since／--until 是 UTC，可以只給日期，也可以給到秒（2026-01-01T16:00:00）；--until 不含那個時間點。
      每週固定報表（按天、按資料夾、最貴的工作階段、跟前一週比）用 token_weekly.py。

看三個數字有沒有降：
  1. 載入團隊技能的回合，動手改第一個檔之前 context 多了多少（開工前讀太多）
  2. 主對話花費裡，context 超過 40 萬 token 時花掉的占比（對話拖太長）
  3. 子代理占總花費的比例（子代理開太多、模型太貴）

「加權成本」＝未快取輸入×1＋寫快取×1.25＋讀快取×0.1＋輸出×5，單位是等值的輸入 token，只用來比大小，不是帳單金額。
同一則回覆在分支出去的工作階段裡會重複出現，這裡用訊息編號去重。
"""
import collections
import datetime
import glob
import io
import json
import os
import statistics
import sys

ROOT = os.path.join(os.path.expanduser("~"), ".claude", "projects")
EDIT = {"Edit", "Write", "NotebookEdit"}
DOCS = ["lessons-workflow", "lessons-tech", "lessons-local", "retro-log", "skill-changelog",
        "edge-case-checklist", "agent-briefs", "SKILL.md"]


def weight(u):
    return (u.get("input_tokens", 0) + 1.25 * u.get("cache_creation_input_tokens", 0)
            + 0.1 * u.get("cache_read_input_tokens", 0) + 5 * u.get("output_tokens", 0))


def ctx(u):
    return u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)


def load(path):
    """依序回傳事件：['user', 文字, 時間] 或 ['asst', 訊息編號, usage, [(工具, 輸入)], 時間, 模型]"""
    ev, seen = [], {}
    try:
        f = io.open(path, "rb")
    except OSError:
        return ev
    for line in f:
        # 紀錄檔兩週就有好幾 GB：用位元組讀、先用字串判斷略過用不到的行，只解析回覆與使用者的話（量過，整體快一倍以上）。
        # 1) 沒有 "assistant" 也沒有 "user" 這兩個字的行，不可能是這兩種項目
        # 2) 工具結果那幾行（讀檔內容、指令輸出，占檔案大半）本來解析完也是跳過
        if b'"assistant"' not in line and b'"user"' not in line:
            continue
        if b'"type":"tool_result"' in line and b'"type":"assistant"' not in line:
            continue
        try:
            o = json.loads(line)
        except UnicodeDecodeError:
            try:
                o = json.loads(line.decode("utf-8", errors="replace"))
            except ValueError:
                continue
        except ValueError:
            continue
        ts = o.get("timestamp") or ""
        m = o.get("message") or {}
        if o.get("type") == "assistant":
            mid = m.get("id") or o.get("uuid")
            tools = [(b.get("name"), b.get("input") or {}) for b in (m.get("content") or [])
                     if isinstance(b, dict) and b.get("type") == "tool_use"]
            if mid in seen:
                e = ev[seen[mid]]
                e[2] = m.get("usage") or e[2]
                e[3].extend(tools)
            else:
                seen[mid] = len(ev)
                ev.append(["asst", mid, m.get("usage") or {}, tools, ts, m.get("model", "")])
        elif o.get("type") == "user" and not o.get("isMeta"):
            c = m.get("content")
            if isinstance(c, str):
                txt = c
            else:
                parts = [b for b in (c or []) if isinstance(b, dict)]
                if any(b.get("type") == "tool_result" for b in parts):
                    continue
                txt = " ".join(b.get("text", "") for b in parts if b.get("type") == "text")
            if txt.strip():
                ev.append(["user", txt, ts])
    return ev


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    days = int(args[args.index("--days") + 1]) if "--days" in args else 14
    top = int(args[args.index("--top") + 1]) if "--top" in args else 8
    since = args[args.index("--since") + 1] if "--since" in args else (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    until = args[args.index("--until") + 1] if "--until" in args else "9999"
    floor = datetime.datetime.strptime(since[:10], "%Y-%m-%d").timestamp() - 86400

    seen = set()
    main_w = sub_w = 0.0
    parts = collections.Counter()
    buckets, bucket_w = collections.Counter(), collections.Counter()
    models = collections.Counter()
    reads, whole = collections.Counter(), collections.Counter()
    turns, baselines, peaks, sub_each, sub_ctx0 = [], [], [], [], []
    n_sess = n_calls = 0
    for p in glob.glob(os.path.join(ROOT, "*", "*.jsonl")):
        if os.path.getmtime(p) < floor:
            continue
        full = load(p)
        first = next((e for e in full if e[0] == "asst" and ctx(e[2])), None)
        ev = [e for e in full if since <= (e[4] if e[0] == "asst" else e[2]) < until]
        if not ev:
            continue
        n_sess += 1
        if first and since <= first[4] < until and first[1] not in seen:
            baselines.append(ctx(first[2]))
        proj = os.path.basename(os.path.dirname(p))[-26:]
        cur, peak = None, 0

        def close(c):
            if c and c["edit"] is not None and c["start"] is not None:
                turns.append((max(c["edit"] - c["start"], 0), c["pre"], c["skill"], proj, c["prompt"]))

        for e in ev:
            if e[0] == "user":
                close(cur)
                cur = {"prompt": e[1][:50].replace("\n", " "), "start": None, "edit": None, "pre": 0, "skill": False}
                continue
            if e[1] in seen:
                continue
            seen.add(e[1])
            u = e[2]
            c = ctx(u)
            if not c:
                continue
            w = weight(u)
            main_w += w
            n_calls += 1
            peak = max(peak, c)
            models[e[5]] += w
            parts["輸出"] += 5 * u.get("output_tokens", 0)
            parts["新讀進來的內容（寫快取）"] += 1.25 * u.get("cache_creation_input_tokens", 0)
            parts["每一步重帶的舊內容（讀快取）"] += 0.1 * u.get("cache_read_input_tokens", 0)
            b = "10 萬以下" if c < 1e5 else "10～20 萬" if c < 2e5 else "20～40 萬" if c < 4e5 else "40 萬以上"
            buckets[b] += 1
            bucket_w[b] += w
            if cur is None:
                cur = {"prompt": "（接續）", "start": None, "edit": None, "pre": 0, "skill": False}
            if cur["start"] is None:
                cur["start"] = c
            for name, inp in e[3]:
                if name == "Read":
                    fp = str(inp.get("file_path", ""))
                    for k in DOCS:
                        if k in fp:
                            reads[k] += 1
                            if not inp.get("offset") and not inp.get("limit"):   # 沒帶範圍才算整份讀（L-255）
                                whole[k] += 1
                if name == "Skill" and "dev-team" in str(inp.get("skill", "")):
                    cur["skill"] = True
                if cur["edit"] is None:
                    fp = str(inp.get("file_path", ""))
                    if name in EDIT and "scratchpad" not in fp and os.sep + "memory" + os.sep not in fp:
                        cur["edit"] = c
                    else:
                        cur["pre"] += 1
        close(cur)
        if peak:
            peaks.append(peak)
        for sp in glob.glob(os.path.join(p[:-6], "subagents", "*.jsonl")):
            sev = [e for e in load(sp) if e[0] == "asst" and since <= e[4] < until and e[1] not in seen]
            if not sev:
                continue
            w = 0.0
            for e in sev:
                seen.add(e[1])
                w += weight(e[2])
                models["子代理：" + e[5]] += weight(e[2])
            sub_w += w
            sub_each.append(w)
            sub_ctx0.append(ctx(sev[0][2]))

    total = main_w + sub_w
    if not total:
        print("這段期間沒有工作階段紀錄")
        return 1
    med = statistics.median
    print("期間：%s 起%s｜工作階段 %d 個｜主對話呼叫 %d 次" % (since, "" if until == "9999" else "、到 %s 之前" % until, n_sess, n_calls))
    print("\n■ 三個要看的數字")
    sk = [t for t in turns if t[2]]
    other = [t for t in turns if not t[2]]
    if sk:
        print("  1. 載入團隊技能的回合（%d 輪）：動手前 context 增加 中位數 %.1f 萬、工具呼叫 中位數 %d 次" % (len(sk), med([t[0] for t in sk]) / 1e4, med([t[1] for t in sk])))
    if other:
        print("     其他有改檔的回合（%d 輪）：中位數 %.1f 萬、%d 次" % (len(other), med([t[0] for t in other]) / 1e4, med([t[1] for t in other])))
    print("  2. 主對話花費裡，context 超過 40 萬時花掉的：%.0f%%（超過 20 萬：%.0f%%）" % (
        100 * bucket_w["40 萬以上"] / main_w, 100 * (bucket_w["40 萬以上"] + bucket_w["20～40 萬"]) / main_w))
    print("  3. 子代理占總花費：%.0f%%（%d 個；每個開場 context 中位數 %.1f 萬）" % (
        100 * sub_w / total, len(sub_each), (med(sub_ctx0) / 1e4) if sub_ctx0 else 0))
    print("\n■ 其他")
    print("  加權成本合計 %.0fM｜主對話 %.0fM｜子代理 %.0fM" % (total / 1e6, main_w / 1e6, sub_w / 1e6))
    print("  主對話拆解：" + "、".join("%s %.0f%%" % (k, 100 * v / main_w) for k, v in parts.most_common()))
    if baselines:
        print("  新工作階段第一則回覆時的 context：中位數 %.1f 萬（%d 個）" % (med(baselines) / 1e4, len(baselines)))
    if peaks:
        print("  工作階段最高 context：中位數 %.0f 萬；超過 40 萬的 %d／%d 個" % (med(peaks) / 1e4, sum(1 for x in peaks if x > 4e5), len(peaks)))
    print("  依模型：" + "、".join("%s %.0f%%" % (k or "?", 100 * v / total) for k, v in models.most_common(5)))
    if reads:
        print("  固定文件被 Read 的次數（括號內：沒帶範圍、整份讀的次數）：" + "、".join("%s %d（%d）" % (k, v, whole[k]) for k, v in reads.most_common()))
    if turns:
        print("\n■ 動手前讀最多的 %d 輪" % top)
        for t in sorted(turns, key=lambda x: -x[0])[:top]:
            print("  +%.1f 萬 %3d 次工具%s｜%s｜%s" % (t[0] / 1e4, t[1], "（技能）" if t[2] else "", t[3], t[4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
