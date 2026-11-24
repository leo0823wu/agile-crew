"""每輪開發的耗時：從使用者提出需求到交付（寫回顧那一刻），其中等使用者、等外部各多久。由工作階段紀錄的時間戳自動算。

用法：
  python -I round_time.py --fill [--dry-run] [--recompute] [--days 45]
      回填 `<本地>/retro-log.md`〈回顧紀錄〉「耗時」欄**空著的格子**（沒有這一欄就先加上；有值的、手寫的都不動）。
      回顧加完一列後跑一次。--recompute：改了算法後，自動算出的格子（格式對得上的、「—」）重算，手寫的照樣不動。
  python -I round_time.py --row "<日期>" "<專案／這輪 開頭幾個字>"
      只算一列、印出來，不寫檔（檢查用）

怎麼算（一列回顧＝一輪）：
- 找寫入那一列的編輯：所有工作階段紀錄裡，Edit／MultiEdit 回顧紀錄（含 2026-10-30 以前在技能 references/retro.md 的舊位置）、
  new_string 比 old_string 多出這一列（列數沒變多＝只是改字，不算）。
- 結束＝那次編輯的時間。開始＝同一個工作階段裡上一次寫回顧之後的第一則真人訊息（沒有上一次就從工作階段開頭）；
  中間 Claude 停下到使用者下一則訊息超過 8 小時，就從那則訊息重新起算（工作階段常開好幾週，之前沒寫回顧的部分不算；
  代價是跨夜的工作只量到隔天那段）。
- 等使用者：Claude 停下到使用者下一則訊息的間隔加總，加上 AskUserQuestion 等回答的時間。
- 等外部：執行超過 3 分鐘、而且是在等網路或遠端的指令（ssh、scp、git push、curl、docker push／save…），
  以及等背景工作（不是子代理的）完成通知的空檔。建置、測試、打包、本機輪詢（sleep）、子代理（Agent）算團隊在做事。
  VPN、登入這類要使用者動手的，算在等使用者。
- 類型：這一輪有改檔（~/.claude、暫存區以外）、git commit／push、用了子代理、或寫入外部服務（Notion 等 MCP 的
  create／update…）＝「開發」，否則＝「問答」。team_metrics.py 依這個分兩類算平均，避免小問答把平均拉低。
  被 retro_gate 擋下才補寫的回顧（寫回顧前最近的停點被回顧 hook 擋下、之後沒有真人訊息、這一輪沒有 push）＝「補寫」：
  真正的工作在更早，不進趨勢。
- 耗時欄格式：`開發 3.2h（等使用者 1.0h、等外部 0.2h）`；找不到寫入那一列的紀錄（例：用 Write 整份寫、紀錄已被清掉）就寫 `—`。
  工作階段紀錄預設 30 天後會被 Claude Code 清掉，所以要在回顧當下或每週跑一次，數字才留得下來。
"""
import argparse
import datetime
import glob
import os
import re
import shutil
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL, "hooks"))
import record_gate as R  # noqa: E402
import transcript as T  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HOME = os.path.expanduser("~")
LOCAL = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(HOME, ".claude", "agile-crew-local")
PROJECTS = os.environ.get("AGILE_CREW_TRANSCRIPTS") or os.path.join(HOME, ".claude", "projects")   # 測試時換成假資料夾
LONG_TOOL = datetime.timedelta(minutes=3)
RESET_GAP = datetime.timedelta(hours=8)
COL = "耗時"
MCP_WRITE = re.compile(r"(create|update|delete|write|send|move|upload|append|insert|post|batch)", re.I)
# 執行很久的指令裡，這些是在等外部（網路、遠端機器、別人的服務）；建置、測試、打包算團隊在做事
# （sleep／Start-Sleep 不算：多半是在本機輪詢等 QA、截圖、建置，QA 2026-11-05 抓到會把本機等待算成外部）
EXTERNAL_CMD = re.compile(r"(?i)\b(ssh|scp|sftp|rsync|curl|wget|Invoke-WebRequest|Invoke-RestMethod|run_remote|"
                          r"ping|Test-NetConnection)\b|\bgit\s+(push|pull|fetch|clone|ls-remote)\b|"
                          r"\bdocker\s+(push|pull|save|load)\b")
FORCED = "還沒做團隊回顧"     # retro_gate 擋下的理由裡的字：這一輪的回顧是被逼出來補寫的
# 回顧紀錄：現在的位置，加上 2026-10-30 搬到本地之前寫在技能裡的舊位置（references/retro.md）
RETRO_ANY = re.compile(r"retro-log\.md|references[\\/]+retro\.md", re.I)


def squash(t):
    return re.sub(r"[\s`*]", "", t or "").casefold()


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


# ---------------------------------------------------------------- 找寫入回顧列的那次編輯

def insertions(days):
    """→ [dict(date, cell, ts, tid, path)]：每一筆是「新增了某一列回顧」的編輯（同一個 tool id 只算一次）。"""
    since = datetime.datetime.now().timestamp() - days * 86400
    files = [f for f in glob.glob(os.path.join(PROJECTS, "*", "*.jsonl")) if os.path.getmtime(f) >= since]
    out, seen = [], set()
    for f in sorted(files, key=os.path.getmtime):
        with open(f, "rb") as fh:
            for line in fh:
                if b"tool_use" not in line or (b"retro-log.md" not in line and b"retro.md" not in line):
                    continue
                for e in T.read_events_from_lines([line]):
                    if e.kind != "tool" or e.name not in ("Edit", "MultiEdit") or e.tid in seen:
                        continue
                    if not RETRO_ANY.search(e.inp.get("file_path") or ""):
                        continue
                    for ed in e.inp.get("edits") or [e.inp]:
                        for date, cell in _new_rows(ed.get("old_string"), ed.get("new_string")):
                            seen.add(e.tid)
                            out.append({"date": date, "cell": cell, "ts": e.ts, "tid": e.tid, "path": f})
    return out


def _new_rows(old, new):
    """新加的列 [(日期, 專案那一格)]；列數沒變多＝只是改既有列的字，不算新加。"""
    rows_old, rows_new = R.ROW.findall(old or ""), R.ROW.findall(new or "")
    if len(rows_new) <= len(rows_old):
        return []
    before = set(rows_old)
    return [(d, c.strip()) for d, c in rows_new if (d, c) not in before]


def match_row(date, cell, ins, with_score=False):
    """回顧列 → 寫入它的那次編輯（同一天、專案那一格開頭最像的；之後被改過字也對得到）。
    共同開頭要 ≥ 6 字而且占較短那格的 4 成以上，或較短那格整段都對上（中文專案名常不到 6 字）；
    只有「某某 CRM v1」這種開頭幾個字相同的不算（QA 2026-11-05：兩列對到同一筆編輯）。"""
    key = squash(cell)
    best, best_score = None, 0
    for x in ins:
        if x["date"] != date:
            continue
        other = squash(x["cell"])
        short = min(len(key), len(other))
        n = 0
        while n < short and key[n] == other[n]:
            n += 1
        whole = n == short
        ok = (n >= 6 and n >= 0.4 * short) or (whole and n >= 3)
        score = n + (1000 if whole else 0)
        if ok and score > best_score:
            best, best_score = x, score
    return (best, best_score) if with_score else best


# ---------------------------------------------------------------- 算一輪

def _is_retro_insert(e):
    if e.kind != "tool" or e.name not in ("Edit", "MultiEdit") or not RETRO_ANY.search(e.inp.get("file_path") or ""):
        return False
    return any(_new_rows(ed.get("old_string"), ed.get("new_string")) for ed in (e.inp.get("edits") or [e.inp]))


_cache = {}


def measure(path, tid):
    """→ dict(start, end, total, user, ext, kind) 或 None。"""
    if path not in _cache:
        _cache.clear()      # 同一時間只留一個工作階段（最大的紀錄檔 190 MB）
        _cache[path] = [e for e in T.session_events(path) if e.ts]
    ev = _cache[path]
    end = next((k for k, e in enumerate(ev) if e.kind == "tool" and e.tid == tid and not e.side), None)
    if end is None:
        return None
    prev = max((k for k in range(end) if _is_retro_insert(ev[k]) and not ev[k].side), default=-1)
    humans = [k for k in range(prev + 1, end) if ev[k].kind == "human"]
    if not humans:   # 跟上一列回顧在同一輪寫的：從上一列那一輪的開頭算
        p2 = max((k for k in range(prev) if _is_retro_insert(ev[k]) and not ev[k].side), default=-1)
        humans = [k for k in range(p2 + 1, end) if ev[k].kind == "human"]
    if not humans:
        return None
    start = humans[0]
    last_active = None
    for k in range(start, end):
        e = ev[k]
        if e.side:
            continue
        if e.kind == "human" and last_active and e.ts - last_active > RESET_GAP:
            start = k
        if e.kind in ("text", "tool", "result", "stop"):
            last_active = e.ts
    tools = {e.tid: e for e in ev[start:end + 1] if e.kind == "tool" and not e.side}
    user = ext = datetime.timedelta(0)
    last = None
    kind = "問答"
    for k in range(start, end + 1):
        e = ev[k]
        if e.side:
            if e.kind == "tool" and e.name in R.WRITE_TOOLS:
                kind = "開發"
            continue
        if e.kind == "human" and last and e.ts > last:
            user += e.ts - last
        elif e.kind == "notify" and last and e.ts > last:
            m = re.search(r"<tool-use-id>(\w+)</tool-use-id>", e.text or "")
            src = tools.get(m.group(1)) if m else None
            if not (src and src.name == "Agent"):
                ext += e.ts - last
        elif e.kind == "result" and e.tid in tools:
            t = tools[e.tid]
            dur = e.ts - t.ts
            if t.name == "AskUserQuestion":
                user += max(dur, datetime.timedelta(0))
            elif t.name in R.SHELLS and dur > LONG_TOOL and EXTERNAL_CMD.search(t.inp.get("command") or ""):
                ext += dur
        if e.kind in ("text", "tool", "result", "stop", "hookfb"):
            last = e.ts
        if e.kind == "tool" and kind == "問答":
            kind = _kind_of(e)
    # 被 retro_gate 擋下才補寫的回顧：真正的工作在更早的輪次，這一輪只量到補寫，不能拿來比快慢。
    # 只看「寫回顧前最近的停點」：它前面緊接 retro_gate 的 Stop hook feedback（真實順序 feedback → stop）、
    # 停點到寫回顧之間沒有真人訊息、這一輪也沒有 push（有 push 的話是交付後正常補回顧）。
    # 不能看整個視窗：視窗裡的 feedback 可能是上一列被逼補寫用的（QA 2026-11-05 抓到 2 列開發被誤判）
    forced = False
    s = max((k for k in range(start, end) if ev[k].kind == "stop" and not ev[k].side), default=None)
    if s is not None and not any(ev[k].kind == "human" for k in range(s + 1, end)):
        before = next((ev[k] for k in range(s - 1, start - 1, -1) if not ev[k].side and ev[k].kind != "result"), None)
        if before is not None and before.kind == "hookfb" and FORCED in (before.text or ""):
            forced = not any(e.kind == "tool" and not e.side and e.name in R.SHELLS and
                             any(op == "push" for op, _ in R.shell_effects(e.inp.get("command") or "", e.cwd)[0])
                             for e in ev[start:s])
    total = ev[end].ts - ev[start].ts
    return {"start": ev[start].ts, "end": ev[end].ts, "total": total, "user": user, "ext": ext,
            "kind": "補寫" if forced else kind}


def _kind_of(e):
    if e.name == "Agent":
        return "開發"
    if e.name in R.WRITE_TOOLS:
        p = R.norm(e.inp.get("file_path") or e.inp.get("notebook_path") or "", e.cwd)
        if not R.not_project_path(p):      # 暫存區、~/.claude、本地資料夾（回顧紀錄）不算開發
            return "開發"
    elif e.name in R.SHELLS:
        git_ops, _, _ = R.shell_effects(e.inp.get("command") or "", e.cwd)
        if any(op in ("commit", "push", "merge", "cherry-pick") for op, _ in git_ops):
            return "開發"
    elif e.name.startswith("mcp__") and MCP_WRITE.search(e.name.split("__")[-1]):
        return "開發"
    return "問答"


def hours(td):
    return f"{td.total_seconds() / 3600:.1f}h"


def fmt(m):
    if not m:
        return "—"
    return f"{m['kind']} {hours(m['total'])}（等使用者 {hours(m['user'])}、等外部 {hours(m['ext'])}）"


DUR = re.compile(r"(開發|問答|補寫)\s*([\d.]+)h（等使用者\s*([\d.]+)h、等外部\s*([\d.]+)h）")


def parse_cell(text):
    """耗時欄 → dict(kind, total, user, ext, work)（小時）或 None。"""
    m = DUR.search(text or "")
    if not m:
        return None
    total, user, ext = float(m.group(2)), float(m.group(3)), float(m.group(4))
    return {"kind": m.group(1), "total": total, "user": user, "ext": ext, "work": max(total - user - ext, 0.0)}


# ---------------------------------------------------------------- 回填

def fill(days, dry_run, recompute=False):
    """只填空著的格子。recompute＝改了算法後重算：自動算出來的格子（格式對得上的、「—」）重算，手寫的內容一律不動。"""
    path = os.path.join(LOCAL, "retro-log.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    sec = next((i for i, l in enumerate(lines) if l.startswith("## 回顧紀錄")), None)
    if sec is None:
        print("找不到〈回顧紀錄〉段落")
        return 1
    hdr = next(i for i in range(sec, len(lines)) if lines[i].startswith("| 日期"))
    head = cells(lines[hdr])
    if COL not in head:
        head.append(COL)
        lines[hdr] = "| " + " | ".join(head) + " |"
        lines[hdr + 1] = "|" + "---|" * len(head)
    ci = head.index(COL)
    ins = insertions(days)
    # 一筆編輯只配給最像的那一列（避免兩列算成同一段時間）
    owner = {}
    for i in range(hdr + 2, len(lines)):
        if lines[i].startswith("## "):
            break
        if re.match(r"^\| \d{4}-\d{2}-\d{2} ", lines[i]):
            c = cells(lines[i])
            x, score = match_row(c[0], c[1], ins, with_score=True)
            if x and score > owner.get(x["tid"], (None, -1))[1]:
                owner[x["tid"]] = (i, score)
    filled = missing = kept = 0
    report = []
    for i in range(hdr + 2, len(lines)):
        l = lines[i]
        if not re.match(r"^\| \d{4}-\d{2}-\d{2} ", l):
            if l.startswith("## "):
                break
            continue
        c = cells(l)
        while len(c) < len(head):
            c.append("")
        auto = bool(parse_cell(c[ci])) or c[ci].strip() == "—"
        if c[ci].strip() and not (recompute and auto):
            kept += 1          # 已經有值（算過的、找不到紀錄的「—」、手寫的）：不動
            continue
        x = match_row(c[0], c[1], ins)
        if x and owner.get(x["tid"], (None,))[0] != i:
            x = None                    # 這筆編輯配給了更像的另一列
        m = measure(x["path"], x["tid"]) if x else None
        new = fmt(m)
        if new == c[ci].strip():
            kept += 1
            continue
        c[ci] = new
        if m:
            filled += 1
        else:
            missing += 1
        report.append(f"- {c[0]} {c[1][:30]} → {c[ci]}")
        lines[i] = "| " + " | ".join(c) + " |"
    print(f"耗時：新填 {filled} 列、找不到紀錄 {missing} 列（寫 —）、原本就有 {kept} 列")
    print("\n".join(report))
    if not dry_run and (filled or missing or COL not in cells(text.split("\n")[hdr])):
        bak = os.path.join(LOCAL, "_archive", "retro-log.before-duration.md")
        if not os.path.exists(bak):
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copyfile(path, bak)
        with open(path, encoding="utf-8") as f:
            if f.read() != text:
                print("回顧紀錄在計算期間被別的工作階段改過，這次不寫入，請再跑一次")
                return 1
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recompute", action="store_true", help="改了算法後：自動算出的格子（含「—」）重算，手寫的不動")
    ap.add_argument("--days", type=int, default=45, help="只看最近幾天有更新的工作階段紀錄")
    ap.add_argument("--row", nargs=2, metavar=("DATE", "CELL"))
    a = ap.parse_args()
    if a.row:
        x = match_row(a.row[0], a.row[1], insertions(a.days))
        print(x and {k: v for k, v in x.items() if k != "cell"})
        print(fmt(measure(x["path"], x["tid"])) if x else "找不到寫入這一列的編輯")
        return 0
    if a.fill:
        return fill(a.days, a.dry_run, a.recompute)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
