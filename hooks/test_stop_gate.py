"""stop_gate.py（回顧＋專案紀錄合成一個 Stop 入口）的情境測試。

python -I ~/.claude/skills/dev-team/hooks/test_stop_gate.py
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stop_gate.py")
TMP = tempfile.mkdtemp(prefix="sg_test_", dir=os.path.expanduser("~"))   # hook 不看 AppData 底下的改檔
WORK, CODE, LOCAL = (os.path.join(TMP, x) for x in ("work", "code", "local"))
OLD = datetime.datetime(2020, 1, 1).timestamp()
REC = os.path.join(WORK, "G", "甲官網", "record.md")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


write(os.path.join(WORK, "index.md"), "| G | 甲官網 | [紀錄](G/甲官網/record.md) |\n")
write(REC, f"# 甲\n\n## 基本資料\n\n| 項目 | 內容 |\n|---|---|\n| 程式碼 | `{CODE}\\alpha` |\n")
os.makedirs(os.path.join(CODE, "alpha", ".git"))
write(os.path.join(LOCAL, "config.json"), json.dumps(
    {"project_index": os.path.join(WORK, "index.md"), "work_root": WORK, "code_root": CODE}))
T0 = datetime.datetime(2026, 11, 1, 1, 0, tzinfo=datetime.timezone.utc)
A = os.path.join(CODE, "alpha", "App.java")
_n = [0]


def ev(m, **kw):
    _n[0] += 1
    d = {"uuid": f"u{_n[0]}", "sessionId": "s", "isSidechain": False, "cwd": os.path.join(CODE, "alpha"),
         "timestamp": (T0 + datetime.timedelta(minutes=m)).isoformat().replace("+00:00", "Z")}
    d.update(kw)
    return d


def ask(m):
    return ev(m, type="user", origin={"kind": "human"}, message={"role": "user", "content": "改一下"})


def tool(m, name, inp):
    return ev(m, type="assistant", message={"role": "assistant", "content": [
        {"type": "tool_use", "id": f"t{_n[0] + 1}", "name": name, "input": inp}]})


def edit(m, p):
    return tool(m, "Edit", {"file_path": p, "old_string": "a", "new_string": "b"})


def retro(m, cell):
    return tool(m, "Edit", {"file_path": os.path.join(LOCAL, "retro-log.md"), "old_string": "| 日期 |\n",
                            "new_string": f"| 日期 |\n| 2026-11-01 | {cell} | 糾正 0 |\n"})


def push(m):
    return tool(m, "Bash", {"command": "git push origin main"})


def stop(m):
    return ev(m, type="system", subtype="stop_hook_summary")


def fb(m, text):   # 真實順序：Stop hook feedback 在 stop_hook_summary 前面
    return ev(m, type="user", message={"role": "user", "content": "Stop hook feedback:\n" + text})


def run(events, active=False):
    p = os.path.join(TMP, "s.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.utime(REC, (OLD, OLD))
    r = subprocess.run([sys.executable, "-I", HOOK], capture_output=True,
                       input=json.dumps({"transcript_path": p, "stop_hook_active": active}).encode(),
                       env=dict(os.environ, DEV_TEAM_LOCAL=LOCAL, RECORD_GATE_DEBUG="1"))
    if r.stderr.strip():
        print("   stderr:", r.stderr.decode("utf-8", "replace")[-500:])
    out = r.stdout.decode("utf-8", "replace").strip()
    return json.loads(out).get("reason", "") if out else None


RETRO_MARK = "團隊回顧"
REC_MARK = "專案紀錄還沒更新"
cases = [
    ("沒交付：放行", [ask(0), edit(1, A)], None, None),
    ("push＋紀錄有更新、沒回顧：只要回顧", [ask(0), edit(1, A), edit(2, REC), push(3)], [RETRO_MARK], [REC_MARK]),
    ("回顧寫甲官網、紀錄沒更新、沒有 push：只要紀錄", [ask(0), retro(1, "甲官網 修正")], [REC_MARK], [RETRO_MARK]),
    ("push、沒回顧、沒紀錄：兩個都要（合成一個理由）", [ask(0), edit(1, A), push(2)], [RETRO_MARK, REC_MARK], []),
    ("push＋紀錄＋回顧：放行", [ask(0), edit(1, A), edit(2, REC), push(3), retro(4, "甲官網 修正")], None, None),
    ("續跑、這一段已被兩個檢查擋過：放行（不會卡死）",
     [ask(0), edit(1, A), push(2), fb(3, "還沒做團隊回顧…專案紀錄還沒更新"), stop(3), retro(4, "甲官網 修正")], "active", None),
    ("續跑：回顧 hook 逼出來的補寫回顧寫甲官網、紀錄沒更新 → 只擋紀錄一次",
     [ask(0), fb(1, "這個工作階段在最後一次 git push 之後還沒做團隊回顧"), stop(1), retro(2, "甲官網 補寫")],
     "active-block", [REC_MARK]),
    ("api-request-blob 重放的舊 push 不會逼出回顧", [ask(0), edit(1, A), edit(2, REC), push(3), retro(4, "甲官網 修正"),
                                             {"type": "api-request-blob", "message": {"role": "assistant", "content": [
                                                 {"type": "tool_use", "name": "Bash", "input": {"command": "git push"}}]}}],
     None, None),
]
fail = 0
for name, events, want, not_want in cases:
    act = want in ("active", "active-block")
    if want == "active-block":
        want, not_want = not_want, [RETRO_MARK]
    got = run(events, active=act)
    if want in (None, "active"):
        ok = got is None
    else:
        ok = got is not None and all(w in got for w in want) and not any(w in got for w in not_want or [])
    fail += not ok
    print("PASS" if ok else "FAIL", name, "→", "放行" if got is None else got[:80].replace("\n", " "))
bad = subprocess.run([sys.executable, "-I", HOOK], input=b"oops", capture_output=True)
ok = bad.returncode == 0 and not bad.stdout.strip()
fail += not ok
print("PASS" if ok else "FAIL", "壞掉的輸入放行")
shutil.rmtree(TMP, ignore_errors=True)
print("failures:", fail)
sys.exit(1 if fail else 0)
