"""round_time.py（每輪耗時）與 team_metrics.py（重工解析、每週趨勢）的測試。

python -I ~/.claude/skills/agile-crew/scripts/test_round_time.py
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="rt_test_")
LOCAL = os.path.join(TMP, "local")
PROJ = os.path.join(TMP, "projects")
os.environ["AGILE_CREW_LOCAL"] = LOCAL
os.environ["AGILE_CREW_TRANSCRIPTS"] = PROJ
sys.path.insert(0, HERE)
import round_time as RT  # noqa: E402
import team_metrics as TM  # noqa: E402

T0 = datetime.datetime(2026, 11, 3, 1, 0, tzinfo=datetime.timezone.utc)
RETRO = os.path.join(LOCAL, "retro-log.md")
HDR = "| 日期 | 專案／這輪 | 指標摘要 | 主要發現 | 已改（檔案） | 狀態 |\n|---|---|---|---|---|---|\n"
_n = [0]
fail = 0


def check(name, ok, detail=""):
    global fail
    fail += not ok
    print("PASS" if ok else "FAIL", name, "" if ok else detail)


def ev(m, **kw):
    _n[0] += 1
    d = {"uuid": f"u{_n[0]}", "sessionId": "s1", "isSidechain": False, "cwd": "C:/repo",
         "timestamp": (T0 + datetime.timedelta(minutes=m)).isoformat().replace("+00:00", "Z")}
    d.update(kw)
    return d


def human(m, text="請做"):
    return ev(m, type="user", origin={"kind": "human"}, message={"role": "user", "content": text})


def tool(m, name, inp, tid):
    return ev(m, type="assistant", message={"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]})


def result(m, tid):
    return ev(m, type="user", message={"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": "ok"}]})


def text(m):
    return ev(m, type="assistant", message={"role": "assistant", "content": [{"type": "text", "text": "好了"}]})


def stop(m):
    return ev(m, type="system", subtype="stop_hook_summary")


def notify(m, tid):
    return ev(m, type="user", origin={"kind": "task-notification"},
              message={"role": "user", "content": f"<task-notification>\n<tool-use-id>{tid}</tool-use-id>\n</task-notification>"})


def hookfb(m, msg):
    return ev(m, type="user", message={"role": "user", "content": "Stop hook feedback:\n" + msg})


def retro(m, cell, tid):
    return tool(m, "Edit", {"file_path": RETRO, "old_string": HDR,
                            "new_string": HDR + f"| 2026-11-03 | {cell} | 糾正 0 |\n"}, tid)


def save(name, events):
    d = os.path.join(PROJ, "C--repo")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
    return p


# 一輪開發：上一列回顧在 -60 分；這一輪從 0 分的真人訊息開始，161 分寫回顧
dev = [
    human(-70, "上一個需求"), retro(-60, "甲官網 上一輪", "tprev"), text(-59), stop(-59),
    human(0, "請改甲官網"),
    tool(1, "Bash", {"command": "git commit -m x"}, "t1"), result(2, "t1"),
    tool(2, "Bash", {"command": "scp app.jar host:/opt/app.jar"}, "t2"), result(10, "t2"),     # 等外部 8 分
    tool(10, "Bash", {"command": "mvn package"}, "t3"), result(20, "t3"),                    # 建置 10 分：算工作
    text(21), stop(21),
    human(81, "選 A"),                                                                         # 等使用者 60 分
    tool(82, "AskUserQuestion", {"questions": []}, "t4"), result(102, "t4"),                  # 等使用者 20 分
    tool(103, "Agent", {"prompt": "QA"}, "t5"), result(140, "t5"),                            # 子代理：算工作
    tool(141, "Bash", {"command": "ssh prod 'deploy'", "run_in_background": True}, "t6"), result(141, "t6"),
    text(142), stop(142),
    notify(160, "t6"),                                                                         # 等背景工作 18 分
    retro(161, "甲官網 改版", "tend"),
]
p_dev = save("s1", dev)
m = RT.measure(p_dev, "tend")
hrs = lambda td: round(td.total_seconds() / 3600, 2)  # noqa: E731
check("開發輪：總耗時 161 分（從上一列回顧之後的第一則真人訊息起算）", m and hrs(m["total"]) == round(161 / 60, 2), m)
check("開發輪：等使用者 80 分（隔一段時間回覆 60＋AskUserQuestion 20）", m and hrs(m["user"]) == round(80 / 60, 2), m)
check("開發輪：等外部 26 分（scp 8＋背景 ssh 18；mvn、子代理不算）", m and hrs(m["ext"]) == round(26 / 60, 2), m)
check("開發輪：類型＝開發", m and m["kind"] == "開發", m)
check("格式", RT.fmt(m) == "開發 2.7h（等使用者 1.3h、等外部 0.4h）", RT.fmt(m))
check("格式解析回來", RT.parse_cell(RT.fmt(m)) == {"kind": "開發", "total": 2.7, "user": 1.3, "ext": 0.4,
                                               "work": round(2.7 - 1.3 - 0.4, 10)}, RT.parse_cell(RT.fmt(m)))

# 問答輪：只讀、沒有改檔
qa = [human(0, "這是什麼"), tool(1, "Read", {"file_path": "C:/repo/a.java"}, "q1"), result(1, "q1"), text(2), stop(2),
      retro(5, "甲官網 問答", "qend")]
m = RT.measure(save("s2", qa), "qend")
check("問答輪：類型＝問答", m and m["kind"] == "問答", m)

# 補寫：之前的 push 沒寫回顧，使用者問問題 → retro_gate 擋 → 補寫回顧（這一輪沒有 push）
forced = [human(-700, "做 X"), tool(-690, "Bash", {"command": "git push"}, "f0"), result(-689, "f0"), stop(-688),
          human(0, "哪天上線"), text(1), hookfb(1, "這個工作階段在最後一次 git push 之後還沒做團隊回顧"), stop(1),
          retro(3, "甲官網 補做", "fend")]          # 真實順序：Stop hook feedback 在 stop 前面
m = RT.measure(save("s3", forced), "fend")
check("被 hook 逼出來的回顧＝補寫", m and m["kind"] == "補寫", m)

# 同上，但擋下之後到寫回顧之間做了一次上下文壓縮（接續摘要不是真人訊息）→ 仍是補寫、壓縮前的空檔不算等使用者
compact = [human(-700, "做 X"), tool(-690, "Bash", {"command": "git push"}, "c0"), result(-689, "c0"), stop(-688),
           human(0, "哪天上線"), text(1), hookfb(1, "這個工作階段在最後一次 git push 之後還沒做團隊回顧"), stop(1),
           ev(30, type="user", isCompactSummary=True, isVisibleInTranscriptOnly=True,
              message={"role": "user", "content": "This session is being continued from a previous conversation…"}),
           retro(31, "甲官網 補做", "cend")]
m = RT.measure(save("s7", compact), "cend")
check("壓縮後的接續摘要不算真人訊息：仍是補寫、不算等使用者", m and m["kind"] == "補寫" and m["user"].total_seconds() == 0, m)

# 視窗裡有上一列被逼補寫的 feedback，但這一列是做完實際工作後主動寫的 → 開發（QA 抓到原本會誤判成補寫）
own = [human(-700, "做 X"), tool(-690, "Bash", {"command": "git push"}, "o0"), result(-689, "o0"), stop(-688),
       human(0, "哪天上線"), text(1), hookfb(1, "這個工作階段在最後一次 git push 之後還沒做團隊回顧"), stop(1),
       retro(3, "甲官網 補做", "o1"), text(4), stop(4),
       human(5, "接著做 Y"), tool(6, "Write", {"file_path": "C:/repo/y.py", "content": "y"}, "o2"), result(6, "o2"),
       tool(7, "Bash", {"command": "git commit -m y"}, "o3"), result(8, "o3"), text(9), stop(9),
       human(20, "好"), retro(30, "甲官網 做 Y", "oend")]
m = RT.measure(save("s5", own), "oend")
check("主動寫的回顧不算補寫（上一列的 feedback 不影響）", m and m["kind"] == "開發", m)

# 同上，但上一次被逼補寫的回顧是用腳本寫的（不是 Edit，不會切開這一輪）→ 視窗裡有那次 feedback，這一列仍是主動寫的
own2 = [human(0, "哪天上線"), text(1), hookfb(1, "這個工作階段在最後一次 git push 之後還沒做團隊回顧"), stop(1),
        tool(2, "Bash", {"command": "python fix.py retro-log.md"}, "p1"), result(2, "p1"), text(3), stop(3),
        notify(10, "bg1"), tool(11, "Write", {"file_path": "C:/repo/y.py", "content": "y"}, "p2"), result(11, "p2"),
        tool(12, "Bash", {"command": "git commit -m y"}, "p3"), result(13, "p3"), text(14), stop(14),
        notify(20, "bg2"), retro(25, "甲官網 做 Y", "pend")]       # 後面幾輪是背景工作通知開的，中間沒有真人訊息
m = RT.measure(save("s6", own2), "pend")
check("視窗裡有別次的補寫 feedback、這一列是做完工作主動寫的 → 開發", m and m["kind"] == "開發", m)

# 閒置超過 8 小時：從回來的那則訊息重新起算
idle = [human(0, "開始"), tool(1, "Write", {"file_path": "C:/repo/a.py", "content": "x"}, "i1"), text(2), stop(2),
        human(2 + 60 * 12, "繼續"), tool(2 + 60 * 12 + 1, "Write", {"file_path": "C:/repo/b.py", "content": "y"}, "i2"),
        retro(2 + 60 * 12 + 30, "甲官網 隔天", "iend")]
m = RT.measure(save("s4", idle), "iend")
check("閒置 12 小時後重新起算：耗時 30 分", m and hrs(m["total"]) == 0.5, m)

# 回填：沒有耗時欄 → 加欄；5 格的舊列補齊；能對到的填數字、對不到的寫 —；再跑一次不重算
os.makedirs(LOCAL, exist_ok=True)
with open(RETRO, "w", encoding="utf-8") as f:
    f.write("# 回顧\n\n## 回顧紀錄（最新在最上面）\n\n" + HDR +
            "| 2026-11-03 | 甲官網 改版（後來改過字） | 糾正 0 | x | y | ✅ |\n"
            "| 2026-11-03 | 甲官網 問答 | 糾正 0 | x | y | ✅ |\n"
            "| 2026-11-01 | 對不到的一列 | 糾正 1 | x | ✅ |\n")
rc = RT.fill(30, dry_run=False)
with open(RETRO, encoding="utf-8") as f:
    out = f.read()
rows = [line for line in out.splitlines() if line.startswith("| 20")]
check("回填：表頭加上耗時欄", "| 狀態 | 耗時 |" in out and "|---|---|---|---|---|---|---|" in out, out[:400])
check("回填：開發那一列（之後改過字也對得到）", "開發 2.7h（等使用者 1.3h、等外部 0.4h）" in rows[0], rows[0])
check("回填：問答那一列", "問答 " in rows[1], rows[1])
check("回填：對不到的寫 —、5 格的舊列補成 7 格", rows[2].endswith("| — |") and rows[2].count("|") == 8, rows[2])
before = out
RT.fill(30, dry_run=False)
with open(RETRO, encoding="utf-8") as f:
    check("回填：再跑一次不變", f.read() == before)

# 手寫的耗時不覆蓋；--recompute 只重算自動算出的格子（格式對得上的、—），手寫的照樣不動
with open(RETRO, encoding="utf-8") as f:
    text = f.read()
text = text.replace("| 甲官網 問答 | 糾正 0 | x | y | ✅ | 問答", "| 甲官網 問答 | 糾正 0 | x | y | ✅ | 約 40 分鐘（手寫）| 舊")
text = text.replace("開發 2.7h（等使用者 1.3h、等外部 0.4h）", "開發 9.9h（等使用者 0.0h、等外部 0.0h）")
with open(RETRO, "w", encoding="utf-8") as f:
    f.write(text)
RT.fill(30, dry_run=False)
with open(RETRO, encoding="utf-8") as f:
    out = f.read()
check("回填：手寫的耗時不覆蓋", "約 40 分鐘（手寫）" in out, out[-600:])
check("回填：沒加 --recompute 時，舊的自動值也不動", "開發 9.9h" in out)
RT.fill(30, dry_run=False, recompute=True)
with open(RETRO, encoding="utf-8") as f:
    out = f.read()
check("--recompute：自動值重算、手寫的不動", "開發 2.7h（等使用者 1.3h、等外部 0.4h）" in out and "約 40 分鐘（手寫）" in out,
      out[-600:])

# team_metrics：重工解析、每週趨勢
check("重工 2（…）→ 2", TM.rework("糾正 0；重工 2（A、B）；等待 0") == 2)
check("重工：一項（括號裡的、不算）→ 1", TM.rework("重工：補字 4 版（Regular→混 Bold、加粗）；等待") == 1)
check("重工：三項 → 3", TM.rework("重工：A（x、y）、B、C；等待 0") == 3)
check("沒寫重工 → 0", TM.rework("糾正 0；追問 1") == 0)
d = datetime.date(2026, 11, 3)
mk = lambda kind, total, user: {"date": d, "corr": 1, "ask": 0, "qa": 0, "rework": 2,  # noqa: E731
                                "dur": {"kind": kind, "total": total, "user": user, "ext": 0.0, "work": total - user}}
trend = "\n".join(TM.weekly_trend([mk("開發", 1.0, 0.2), mk("開發", 3.0, 1.0), mk("開發", 2.0, 0.5), mk("問答", 0.2, 0.0),
                                   mk("補寫", 9.0, 8.0)], 4))
dev_line = trend.split("**開發任務**")[1].splitlines()[4]
check("趨勢：開發任務 3 列、耗時中位數 2.0h、實際工作中位數 1.5h", "| 3 |" in dev_line and "| 2.0h | 1.5h |" in dev_line, dev_line)
qa_line = trend.split("**小問答**")[1].splitlines()[4]
check("趨勢：小問答 1 列標樣本不足", "| 1 |" in qa_line and "樣本不足" in qa_line, qa_line)
all_line = trend.split("**全部**")[1].splitlines()[4]
check("趨勢：全部 5 列、補寫不算耗時", "| 5 |" in all_line and "補寫 1 列不算耗時" in all_line, all_line)

shutil.rmtree(TMP, ignore_errors=True)
print("failures:", fail)
sys.exit(1 if fail else 0)
