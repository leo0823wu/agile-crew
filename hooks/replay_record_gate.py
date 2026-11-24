"""回放 record_gate.py：用過去的工作階段紀錄，模擬每個停點 hook 會不會擋，算擋到幾次、誤擋幾次。

用法：python -I replay_record_gate.py [N=30] [--since 2026-10-22T03:00] [--triggers retro,push]
                                        [--every] [--include <id>…] [--exclude <id>…] [--detail]
  N           取最近修改的 N 個工作階段（不含子代理紀錄）；--include 的另外加進來
  --since     只算這個時間（UTC）之後的停點（專案紀錄的規則從那時才有）
  --triggers  哪些訊號算交付（retro、push、commit），預設跟 hook 一樣
  --every     比較用：每個停點都判斷（不看交付訊號），看會多擋多少
  --detail    每個工作階段都列出來（預設只列有改專案或有擋的）

模擬方式（跟 hook 一樣）：
- 上一次停下被 Stop hook 擋（真實紀錄是「Stop hook feedback → stop_hook_summary」，看停點前面那一筆）
  → 這次是續跑（stop_hook_active）：這一段還沒被紀錄檢查擋過才判斷
- 擋過一次後，假設 Claude 在續跑裡補寫了紀錄：同一輪同一份紀錄不再重複計擋
- 每次擋下標出證據類型：有改檔／只有回顧列（補寫回顧、純問答輪）
判斷「擋得對不對」的參考：
- 純問答／只讀：這段期間沒有任何改專案的檔 → 一定不能擋（擋了就是誤擋）
- 不在專案：有改檔，但全部對不到任何紀錄或 repo → 一定不能擋
- 擋到的那一份紀錄，之後同一個工作階段多久才補寫（沒補寫＝真漏寫）；紀錄裡有沒有那天的日期（可能是別的工作階段補的）
回放看不到紀錄檔當時的修改時間（hook 實際執行時會看），所以回放的擋下次數只會比實際多、不會少。
"""
import argparse
import datetime
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import record_gate as R  # noqa: E402
import transcript as T  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
TW = datetime.timezone(datetime.timedelta(hours=8))


def date_strings(ts):
    local = ts.astimezone(TW)
    return [local.strftime("%Y-%m-%d"), f"{local.month}/{local.day}", f"{local.month:02d}/{local.day:02d}"]


def hm(td):
    m = int(td.total_seconds() // 60)
    return f"{m} 分" if m < 120 else f"{m / 60:.1f} 小時"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=30)
    ap.add_argument("--since", default="2026-10-22T03:00")
    ap.add_argument("--triggers", default=None)
    ap.add_argument("--every", action="store_true")
    ap.add_argument("--include", nargs="*", default=[])
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    since = datetime.datetime.fromisoformat(a.since).replace(tzinfo=datetime.timezone.utc)
    cfg = R.load_config()
    rg = cfg.get("record_gate") or {}
    idle = float(rg.get("idle_split_hours") or 8)
    triggers = a.triggers.split(",") if a.triggers else (rg.get("triggers") or R.DEFAULT_TRIGGERS)
    proj = R.Projects(cfg)
    allf = [f for f in glob.glob(os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", "*.jsonl"))
            if not any(x in f for x in a.exclude)]
    files = sorted(allf, key=os.path.getmtime, reverse=True)[: a.n]
    files += [f for f in allf if any(x in f for x in a.include) and f not in files]
    seen_stops = set()
    tot = dict.fromkeys(["sessions", "stops", "trig", "blocks", "qa_blocks", "noproj_blocks", "qa_sessions",
                         "noproj_sessions", "proj_sessions", "blocked_sessions", "later", "never", "cont",
                         "retro_only", "with_change"], 0)
    record_text = {}
    out = []
    for f in sorted(files, key=os.path.getmtime):
        sid_f = os.path.basename(f)[:-6]
        s = R.Session([e for e in T.session_events(f, results=False) if e.side or not e.sid or e.sid == sid_f],
                      triggers)   # 跟 hook 一樣：不看 resume／fork 帶過來的舊歷史
        ev = s.ev
        sid = os.path.basename(f)[:8]
        cwd = next((e.cwd for e in ev if e.cwd), "")
        stops = [k for k, e in enumerate(ev) if e.kind == "stop" and e.ts and e.ts >= since
                 and (e.ts.isoformat(), e.uuid) not in seen_stops]
        seen_stops.update((ev[k].ts.isoformat(), ev[k].uuid) for k in stops)
        if not stops:
            continue
        tot["sessions"] += 1
        first = next((k for k, e in enumerate(ev) if e.ts and e.ts >= since), len(ev))
        changed, unmapped, _, _ = s.analyze(first, len(ev), proj)
        if changed or unmapped:
            kind = "專案"
        elif any(e.kind == "tool" and (e.name in R.WRITE_TOOLS or s.kinds(i)) for i, e in enumerate(ev[first:], first)):
            kind = "不在專案"
        else:
            kind = "純問答／只讀"
        tot[{"專案": "proj_sessions", "不在專案": "noproj_sessions", "純問答／只讀": "qa_sessions"}[kind]] += 1
        n_block = n_trig = 0
        nagged = set()
        lines = []
        for k in stops:
            tot["stops"] += 1
            p = s.last_stop_before(k)
            if s.is_trigger_turn(k):
                n_trig += 1
            cont = p >= 0 and s.blocked(p)       # 續跑：hook 收到 stop_hook_active
            tot["cont"] += cont
            res = s.pending(k, proj, idle, live=False, every_stop=a.every, active=cont)
            if not res:
                continue
            need, miss_code, start = res
            need = {g: w for g, w in need.items() if (start, g) not in nagged}
            miss_code = {d: w for d, w in miss_code.items() if (start, d) not in nagged}
            if not need and not miss_code:
                continue
            nagged.update((start, g) for g in need)
            nagged.update((start, d) for d in miss_code)
            n_block += 1
            when = ev[k].ts.astimezone(TW).strftime("%m-%d %H:%M")
            for group, why in need.items():
                after = None
                for j in range(k + 1, len(ev)):
                    _, _, t_after, _ = s.analyze(j, j + 1, proj)
                    if t_after & group:
                        after = ev[j].ts - ev[k].ts if ev[j].ts else None
                        break
                texts = []
                for i in group:
                    path = proj.records[i]["path"]
                    if path not in record_text:
                        with open(path, encoding="utf-8") as fh:
                            record_text[path] = fh.read()
                    texts.append(record_text[path])
                dated = any(d in t for d in date_strings(ev[k].ts) for t in texts)
                tot["later" if after is not None else "never"] += 1
                fix = (f"同一工作階段 {hm(after)}後補寫" if after is not None else "同一工作階段沒補寫") + \
                      ("、紀錄裡有當天日期" if dated else "、紀錄裡沒有當天日期")
                names = "、".join(proj.records[i]["rel"].split("\\")[-2] for i in sorted(group))
                items = list(dict.fromkeys(why))
                only_retro = all(w.startswith("回顧「") for w in items)
                tot["retro_only" if only_retro else "with_change"] += 1
                tag = ("［續跑］" if cont else "") + ("［只有回顧列］" if only_retro else "［有改檔］")
                lines.append(f"    擋 {when} {tag}{names}：{'、'.join(items[:5])}"
                             f"{' 等 %d 項' % len(items) if len(items) > 5 else ''} → {fix}")
            for d, why in miss_code.items():
                lines.append(f"    擋 {when} 對不到紀錄的 repo {os.path.basename(d)}：{'、'.join(list(dict.fromkeys(why))[:4])}")
        tot["trig"] += n_trig
        tot["blocks"] += n_block
        if n_block:
            tot["blocked_sessions"] += 1
            tot["qa_blocks"] += n_block if kind == "純問答／只讀" else 0
            tot["noproj_blocks"] += n_block if kind == "不在專案" else 0
        if a.detail or n_block or kind == "專案":
            names = sorted({proj.records[i]["rel"].split("\\")[-2] for g in changed for i in g}
                           | {os.path.basename(d) for d in unmapped})
            out.append(f"- {sid}（{cwd[-38:]}）｜{kind}｜停點 {len(stops)}、交付輪 {n_trig}、擋 {n_block}｜改到：{'、'.join(names) or '—'}")
            out += lines
    print(f"# record_gate 回放：最近 {a.n} 個工作階段{'＋指定 ' + '、'.join(a.include) if a.include else ''}，"
          f"{a.since}（UTC）之後的停點；交付訊號 {'／'.join(triggers)}{'；每個停點都判斷' if a.every else ''}")
    print(f"- 有停點的工作階段 {tot['sessions']} 個：有改專案 {tot['proj_sessions']}、純問答／只讀 {tot['qa_sessions']}、"
          f"有改檔但不在專案 {tot['noproj_sessions']}")
    print(f"- 停點 {tot['stops']} 個（其中續跑 {tot['cont']} 個），交付輪 {tot['trig']} 個；"
          f"擋下 {tot['blocks']} 次（{tot['blocked_sessions']} 個工作階段）")
    print(f"- 擋下的證據：這一輪有改專案的檔 {tot['with_change']} 筆、只有回顧列寫了專案（補寫回顧／問答輪）{tot['retro_only']} 筆")
    print(f"- 誤擋：純問答／只讀的工作階段 {tot['qa_blocks']} 次、不在專案的工作階段 {tot['noproj_blocks']} 次")
    print(f"- 擋下的紀錄：同一工作階段之後有補寫 {tot['later']} 筆、沒補寫 {tot['never']} 筆")
    print()
    print("\n".join(out))


if __name__ == "__main__":
    main()
