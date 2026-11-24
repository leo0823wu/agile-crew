"""record_gate.py 的情境測試：在暫存資料夾建假的專案總表、紀錄、repo 與對話紀錄（jsonl），跑 hook 看該擋／不該擋。

python -I ~/.claude/skills/agile-crew/hooks/test_record_gate.py
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
HOOK = os.path.join(HERE, "record_gate.py")
# hook 不看 AppData（暫存區）與 ~/.claude 底下的改檔，所以測試資料夾放在家目錄，測完刪掉
TMP = tempfile.mkdtemp(prefix="rg_test_", dir=os.path.expanduser("~"))
WORK = os.path.join(TMP, "work")
CODE = os.path.join(TMP, "code")
LOCAL = os.path.join(TMP, "local")
OLD = datetime.datetime(2020, 1, 1).timestamp()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def record(group, site, code_line):
    path = os.path.join(WORK, group, site, "record.md")
    write(path, f"# {site}\n\n## 基本資料\n\n| 項目 | 內容 |\n|---|---|\n| 程式碼 | {code_line} |\n\n## 待辦\n")
    os.utime(path, (OLD, OLD))
    return path


def setup():
    write(os.path.join(WORK, "index.md"),
          "# 總表\n\n| 群 | 網站 | 紀錄 |\n|---|---|---|\n"
          "| A | 甲官網 | [紀錄](GroupA/甲官網/record.md) |\n"
          "| A | 乙丁系統 | [紀錄](GroupA/乙丁系統/record.md) |\n"
          "| B | 丙平台 | [紀錄](GroupB/丙平台/record.md) |\n")
    os.utime(os.path.join(WORK, "index.md"), (OLD, OLD))
    rec = {
        "甲": record("GroupA", "甲官網", f"本機：`{CODE}\\alpha`（分支 `main`）"),
        "乙": record("GroupA", "乙丁系統", f"本機：`{CODE}\\beta`、`{CODE}\\shared`"),
        "丙": record("GroupB", "丙平台", f"`{CODE}\\shared`；文件 `docs-gamma`"),
    }
    for repo in ("alpha", "beta", "shared", "orphan"):
        os.makedirs(os.path.join(CODE, repo, ".git"), exist_ok=True)
    os.makedirs(os.path.join(CODE, "alpha-wt-fix"), exist_ok=True)
    write(os.path.join(CODE, "alpha-wt-fix", ".git"), f"gitdir: {CODE}\\alpha\\.git\\worktrees\\alpha-wt-fix")
    write(os.path.join(LOCAL, "config.json"), json.dumps(
        {"project_index": os.path.join(WORK, "index.md"), "work_root": WORK, "code_root": CODE}))
    return rec


REC = setup()
T0 = datetime.datetime(2026, 11, 1, 1, 0, tzinfo=datetime.timezone.utc)
_n = [0]


def ev(kind, minutes=0, **kw):
    _n[0] += 1
    ts = (T0 + datetime.timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")
    base = {"uuid": f"u{_n[0]}", "timestamp": ts, "cwd": kw.pop("cwd", os.path.join(CODE, "alpha")),
            "isSidechain": False, "parentUuid": None}
    if kind == "human":
        base.update(type="user", origin={"kind": "human"}, message={"role": "user", "content": kw["text"]})
    elif kind == "tool":
        base.update(type="assistant", message={"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{_n[0]}", "name": kw["name"], "input": kw["inp"]}]})
    elif kind == "stop":
        base.update(type="system", subtype="stop_hook_summary", preventedContinuation=False)
    elif kind == "hookfb":   # 真實紀錄的順序：Stop hook feedback 在 stop_hook_summary 前面
        base.update(type="user", message={"role": "user", "content": "Stop hook feedback:\n" + kw.get(
            "text", "這個工作階段在最後一次 git push 之後還沒做團隊回顧")})
    return base


def blocked_stop(m, text=None):
    """被 Stop hook 擋下的停點：真實順序是「Stop hook feedback → stop_hook_summary」（2026-11-05 QA 從 22 筆真實紀錄確認）。"""
    return [ev("hookfb", m, **({"text": text} if text else {})), ev("stop", m)]


def ask(m, text="請幫我改"):
    return ev("human", m, text=text)


def edit(m, path):
    return ev("tool", m, name="Edit", inp={"file_path": path, "old_string": "a", "new_string": "b"})


def sh(m, cmd, tool="Bash", cwd=None):
    kw = {"cwd": cwd} if cwd else {}
    return ev("tool", m, name=tool, inp={"command": cmd}, **kw)


def retro(m, cell):
    return ev("tool", m, name="Edit", inp={
        "file_path": os.path.join(LOCAL, "retro-log.md"),
        "old_string": "| 日期 | 專案／這輪 | 指標摘要 |\n",
        "new_string": f"| 日期 | 專案／這輪 | 指標摘要 |\n| 2026-11-01 | {cell} | 糾正 0 |\n"})


def stop(m):
    return ev("stop", m)


A = os.path.join(CODE, "alpha", "src", "App.java")
PUSH = "git push origin main"


def run(events, active=False, side=None, touch_now=None, touch_at=None):
    sess = os.path.join(TMP, "s.jsonl")
    with open(sess, "w", encoding="utf-8") as f:
        for e in events:     # 跟真實紀錄一樣用緊湊格式（沒有空格）
            f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
    sub = os.path.join(TMP, "s", "subagents")
    shutil.rmtree(os.path.join(TMP, "s"), ignore_errors=True)
    if side:
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-1.jsonl"), "w", encoding="utf-8") as f:
            for e in side:
                e = dict(e, isSidechain=True)
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    for p in REC.values():
        os.utime(p, (OLD, OLD))
    if touch_now:
        os.utime(touch_now, None)
    if touch_at:                      # (路徑, 時間)：紀錄在某個時間點被改過
        os.utime(touch_at[0], (touch_at[1].timestamp(), touch_at[1].timestamp()))
    env = dict(os.environ, AGILE_CREW_LOCAL=LOCAL, RECORD_GATE_DEBUG="1")
    payload = json.dumps({"transcript_path": sess, "stop_hook_active": active}).encode("utf-8")
    r = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True, env=env)
    if r.stderr.strip():
        print("   stderr:", r.stderr.decode("utf-8", "replace")[-600:])
    out = r.stdout.decode("utf-8", "replace").strip()
    if not out:
        return "allow", ""
    return ("block" if json.loads(out).get("decision") == "block" else "allow"), json.loads(out).get("reason", "")


def has(text):
    return lambda reason: text in reason


def lacks(text):
    return lambda reason: text not in reason


cases = [
    ("純問答：沒有工具呼叫", [ask(0, "這是什麼"), stop(1)], "allow", None),
    ("只讀：Read、git status、git log", [ask(0), ev("tool", 1, name="Read", inp={"file_path": A}),
                                       sh(2, "git status; git log -3"), stop(3)], "allow", None),
    ("做到一半：改了檔但沒有 push、沒寫回顧（問使用者問題）", [ask(0), edit(1, A), stop(2)], "allow", None),
    ("改程式＋push、沒更新紀錄 → 擋，指出甲官網", [ask(0), edit(1, A), sh(2, PUSH), stop(3)], "block",
     has("甲官網")),
    ("同上，但這次停下的 stop 紀錄還沒寫（hook 實際執行時的樣子）", [ask(0), edit(1, A), sh(2, PUSH)], "block",
     has("甲官網")),
    ("上一輪 push 已擋過；這一輪只是問答（最後一筆是上一輪的 stop 之後的新問題）",
     [ask(0), edit(1, A), edit(2, REC["甲"]), sh(3, PUSH), stop(4), ask(5, "還有嗎")], "allow", None),
    ("改程式＋更新紀錄＋push", [ask(0), edit(1, A), edit(2, REC["甲"]), sh(3, PUSH), stop(4)], "allow", None),
    ("續跑：這一段已經被紀錄檢查擋過（理由裡有標記）→ 放行，不會卡死",
     [ask(0), edit(1, A), sh(2, PUSH), *blocked_stop(3, "…專案紀錄還沒更新…"), sh(4, PUSH)], "allow-active", None),
    ("續跑：回顧 hook 擋下後補寫的回顧寫甲官網、紀錄沒更新 → 續跑也擋一次",
     [ask(0, "哪天上線的"), *blocked_stop(1), retro(2, "甲官網 表單修正")], "block-active", has("甲官網")),
    ("續跑：補寫回顧後已被紀錄檢查擋過一次，又寫一列 → 放行",
     [ask(0), *blocked_stop(1), retro(2, "甲官網 補寫"), *blocked_stop(3, "…專案紀錄還沒更新…"),
      retro(4, "甲官網 再補")], "allow-active", None),
    ("沒有 cd／-C 的 git commit／push，工作目錄大小寫跟設定不同 → 對得到 repo、擋",
     [ask(0), sh(1, "git commit -m x", cwd=os.path.join(CODE, "alpha").upper()),
      sh(2, PUSH, cwd=os.path.join(CODE, "alpha").upper())], "block", has("甲官網")),
    ("PowerShell 變數＝指令結果（$x = Join-Path $env:TEMP …）：之後寫到 \"$x\\y\" 不是寫到工作目錄的 repo",
     [ask(0), sh(1, '$stage = Join-Path $env:TEMP "pkg"; Copy-Item "C:/tmp/a.txt" "$stage\\b.txt"', "PowerShell",
                 cwd=os.path.join(CODE, "alpha")),
      edit(2, REC["乙"]), retro(3, "乙丁系統 上線"), stop(4)], "allow", None),
    ("Set-Content 的內容不是路徑（內容剛好是別的 repo 的路徑也不算改到它）",
     [ask(0), sh(1, f'Set-Content C:/tmp/note.txt "{CODE}\\beta\\z.txt"', "PowerShell"), edit(2, REC["甲"]),
      sh(3, PUSH), stop(4)], "allow", None),
    ("回顧列主專案在前、後面舉例別的專案 → 只要求主專案（理由裡不出現舉例的專案）",
     [ask(0), retro(1, "甲官網 修正（例：丙平台 也有同樣問題）"), stop(3)], "block",
     lambda r: "甲官網\\record.md" in r and "丙平台\\record.md" not in r),
    ("開頭那段有完整專案名 → 用完整名，不用簡稱（「乙丁 群組 丙平台 修正」→ 丙平台）",
     [ask(0), retro(1, "乙丁群組 丙平台 修正"), stop(2)], "block",
     lambda r: "丙平台\\record.md" in r and "乙丁系統\\record.md" not in r),
    ("開頭是簡稱、完整專案名只在括號裡當參考 → 用簡稱",
     [ask(0), retro(1, "乙丁 金流（參考 甲官網 的做法）"), stop(2)], "block",
     lambda r: "乙丁系統\\record.md" in r and "甲官網\\record.md" not in r),
    ("只有回顧列、紀錄在這個工作階段上一次 push 之後更新過 → 已涵蓋，放行",
     [ask(0), edit(1, A), sh(2, PUSH), stop(3), ask(60 * 20, "哪天上線"), *blocked_stop(60 * 20 + 1),
      retro(60 * 20 + 2, "甲官網 補寫")], "allow-active-touch", None),
    ("改舊回顧列的字（列數沒變多）→ 不算新加的回顧列",
     [ask(0), ev("tool", 1, name="Edit", inp={"file_path": os.path.join(LOCAL, "retro-log.md"),
                                              "old_string": "| 2026-10-01 | 甲官網 錯字 | x |",
                                              "new_string": "| 2026-10-01 | 甲官網 改字 | x |"}), stop(2)], "allow", None),
    ("只 grep 回顧紀錄、指令裡剛好有 python → 不算寫回顧（不觸發）",
     [ask(0), edit(1, A), sh(2, "grep -n x retro-log.md; python --version"), stop(3)], "allow", None),
    ("只補做回顧、回顧寫甲官網、沒改紀錄 → 擋", [ask(0, "哪天上線的"), retro(1, "甲官網 表單修正"), stop(2)], "block",
     has("甲官網")),
    ("回顧用簡稱（去掉「系統」字尾）開頭 → 對到乙丁系統", [ask(0), retro(1, "乙丁 匯入修正"), stop(2)], "block", has("乙丁系統")),
    ("回顧寫甲官網、紀錄有更新", [ask(0), retro(1, "甲官網 修正"), edit(2, REC["甲"]), stop(3)], "allow", None),
    ("回顧沒寫任何專案、只改了技能", [ask(0), edit(1, os.path.join(os.path.expanduser("~"), ".claude", "skills", "x.md")),
                              retro(2, "工具整理：側邊欄分組"), stop(3)], "allow", None),
    ("對不到紀錄的 repo＋push → 擋，要求找／建紀錄",
     [ask(0), edit(1, os.path.join(CODE, "orphan", "a.py")), sh(2, PUSH, cwd=os.path.join(CODE, "orphan")), stop(3)],
     "block", has("對不到任何專案紀錄")),
    ("對不到紀錄的 repo＋改了總表 → 放行",
     [ask(0), edit(1, os.path.join(CODE, "orphan", "a.py")), edit(2, os.path.join(WORK, "index.md")),
      sh(3, PUSH, cwd=os.path.join(CODE, "orphan")), stop(4)], "allow", None),
    ("worktree（.git 是檔案）對到主 repo 的紀錄",
     [ask(0), edit(1, os.path.join(CODE, "alpha-wt-fix", "x.java")), sh(2, PUSH, cwd=os.path.join(CODE, "alpha-wt-fix")),
      stop(3)], "block", has("甲官網")),
    ("同一個 repo 寫在兩份紀錄，更新其中一份就算",
     [ask(0), edit(1, os.path.join(CODE, "shared", "a.py")), edit(2, REC["丙"]),
      sh(3, PUSH, cwd=os.path.join(CODE, "shared")), stop(4)], "allow", None),
    ("同一個 repo 寫在兩份紀錄，都沒更新 → 擋，寫「其中一份」",
     [ask(0), edit(1, os.path.join(CODE, "shared", "a.py")), sh(2, PUSH, cwd=os.path.join(CODE, "shared")), stop(3)],
     "block", has("其中一份")),
    ("上一輪有回顧＋紀錄，這一輪又改＋push 沒更新 → 擋",
     [ask(0), edit(1, A), edit(2, REC["甲"]), retro(3, "甲官網 第一輪"), stop(4),
      ask(10), edit(11, A), sh(12, PUSH), stop(13)], "block", has("甲官網")),
    ("上一輪被擋、續跑裡補了紀錄；這一輪又改＋push → 續跑的那次不算這一輪 → 擋",
     [ask(0), edit(1, A), retro(2, "甲官網 第一輪"), *blocked_stop(3), edit(4, REC["甲"]), stop(5),
      ask(10), edit(11, A), sh(12, PUSH), stop(13)], "block", has("甲官網")),
    ("同一輪先 push 被擋、補紀錄後再 push → 這次放行",
     [ask(0), edit(1, A), sh(2, PUSH), *blocked_stop(3, "…專案紀錄還沒更新…"), edit(4, REC["甲"]), stop(5),
      ask(6, "再改一下"), edit(7, A), sh(8, PUSH), stop(9)], "allow", None),
    ("閒置超過 8 小時切成新的一輪：昨天的紀錄不算今天",
     [ask(0), edit(1, A), edit(2, REC["甲"]), stop(3), ask(60 * 16), edit(60 * 16 + 1, A), sh(60 * 16 + 2, PUSH),
      stop(60 * 16 + 3)], "block", has("甲官網")),
    ("紀錄是用別的方式改的（修改時間在這一輪之後）→ 放行",
     [ask(0), edit(1, A), sh(2, PUSH), stop(3)], "allow-touch", None),
    ("子代理改的檔也算", [ask(0), sh(5, PUSH), stop(6)], "block-side", has("甲官網")),
    ("cp 的來源是專案、目的地是暫存區 → 不算改檔",
     [ask(0), sh(1, f'cp "{A}" /tmp/x.java', cwd=os.path.join(CODE, "beta")),
      edit(2, REC["乙"]), sh(3, PUSH, cwd=os.path.join(CODE, "beta")), stop(4)], "allow", None),
    ("cp 的目的地是專案 → 算改檔",
     [ask(0), sh(1, f'cp /tmp/x.java "{A}"'), sh(2, PUSH), stop(3)], "block", has("甲官網")),
    ("PowerShell Set-Content 寫進專案 → 算改檔",
     [ask(0), sh(1, f"Set-Content -Path '{A}' -Value x -Encoding utf8", "PowerShell"), sh(2, PUSH, "PowerShell"),
      stop(3)], "block", has("甲官網")),
    ("heredoc 內容裡的 git push 不算交付", [ask(0), edit(1, A),
                                       sh(2, "cat > deploy.sh <<'EOF'\ngit push origin main\nEOF"), stop(3)], "allow", None),
    ("只改 repo 的 CLAUDE.md 與暫存區 → 不算（push 本身算這個 repo 有動作）",
     [ask(0), edit(1, os.path.join(CODE, "alpha", "CLAUDE.md")), sh(2, "git status"), retro(3, "工具：整理"), stop(4)],
     "allow", None),
    ("cd 到變數路徑後的相對路徑 → 看不出來，不算",
     [ask(0), sh(1, 'S="/tmp/x"; cd "$Q/bf" && cp a ../ora/x.txt', cwd=CODE), retro(2, "工具：整理"), stop(3)],
     "allow", None),
]

fail = 0
for name, events, want, check in cases:
    kw = {}
    exp = want
    if want in ("allow-active", "block-active"):
        kw["active"], exp = True, want.split("-")[0]
    if want == "allow-touch":
        kw["touch_now"], exp = REC["甲"], "allow"
    if want == "allow-active-touch":   # 紀錄在 push（第 2 分）之後、補寫回顧那一輪（20 小時後）之前改過
        kw["active"], kw["touch_at"], exp = True, (REC["甲"], T0 + datetime.timedelta(hours=5)), "allow"
    if want == "block-side":
        kw["side"], exp = [edit(4, A)], "block"
    got, reason = run(events, **kw)
    ok = got == exp and (check is None or check(reason))
    fail += not ok
    print("PASS" if ok else "FAIL", name, got, "(want", exp, ")")
    if not ok and reason:
        print("   reason:", reason[:300])

# 設定關掉
cfg = os.path.join(LOCAL, "config.json")
c = json.load(open(cfg, encoding="utf-8"))
c["record_gate"] = {"enabled": False}
json.dump(c, open(cfg, "w", encoding="utf-8"))
got, _ = run([ask(0), edit(1, A), sh(2, PUSH), stop(3)])
print("PASS" if got == "allow" else "FAIL", "設定 enabled=false 放行", got)
fail += got != "allow"
c["record_gate"] = {"unmapped_code": "ignore"}
json.dump(c, open(cfg, "w", encoding="utf-8"))
got, _ = run([ask(0), edit(1, os.path.join(CODE, "orphan", "a.py")), sh(2, PUSH, cwd=os.path.join(CODE, "orphan")), stop(3)])
print("PASS" if got == "allow" else "FAIL", "設定 unmapped_code=ignore：對不到紀錄的 repo 放行", got)
fail += got != "allow"

bad = subprocess.run([sys.executable, "-I", HOOK], input=b"not json", capture_output=True)
print("PASS" if bad.returncode == 0 and not bad.stdout.strip() else "FAIL", "壞掉的輸入放行")
fail += not (bad.returncode == 0 and not bad.stdout.strip())
missing = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps({"transcript_path": "C:/nope.jsonl"}).encode(),
                         capture_output=True, env=dict(os.environ, AGILE_CREW_LOCAL=LOCAL))
print("PASS" if missing.returncode == 0 and not missing.stdout.strip() else "FAIL", "找不到紀錄檔放行")
fail += not (missing.returncode == 0 and not missing.stdout.strip())

shutil.rmtree(TMP, ignore_errors=True)
print("failures:", fail)
sys.exit(1 if fail else 0)
