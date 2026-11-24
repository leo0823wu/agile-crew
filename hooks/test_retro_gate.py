"""retro_gate.py 的情境測試：用假的對話紀錄（jsonl）跑 hook，看該擋／不該擋。"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retro_gate.py")


def tu(name, inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": inp}]}}


def sh(cmd, tool="Bash"):
    return tu(tool, {"command": cmd})


def edit(path):
    return tu("Edit", {"file_path": path, "old_string": "a", "new_string": "b"})


RETRO = r"C:\Users\<name>\.claude\agile-crew-local\retro-log.md"
OLD_RETRO = r"C:\Users\<name>\.claude\skills\agile-crew\references\retro.md"


def run(events, active=False):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        p = f.name
    payload = json.dumps({"transcript_path": p, "stop_hook_active": active}).encode("utf-8")
    r = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True)
    os.unlink(p)
    out = r.stdout.decode("utf-8", "replace").strip()
    return "block" if '"block"' in out else "allow"


cases = [
    ("沒有 push", [sh("git status"), sh("npm test")], "allow"),
    ("push 後沒回顧", [sh("git commit -F m.txt"), sh("git push origin main")], "block"),
    ("push 後有改 retro.md", [sh("git push origin main"), edit(RETRO)], "allow"),
    ("回顧在 push 之前、之後又 push", [edit(RETRO), sh("git push origin HEAD")], "block"),
    ("PowerShell 的 git push", [sh("Set-Location x; git push origin HEAD 2>&1", "PowerShell")], "block"),
    ("git -C 路徑 push", [sh("git -C /c/repo push")], "block"),
    ("用 Write 新增 retro.md", [sh("git push"), tu("Write", {"file_path": RETRO, "content": "x"})], "allow"),
    ("改的是別的檔", [sh("git push"), edit(r"C:\x\lessons.md")], "block"),
    ("只是 grep retro.md 不算", [sh("git push"), sh("grep -n x retro.md")], "block"),
    ("用 python 腳本改 retro-log.md", [sh("git push"), sh("python -I fix.py retro-log.md")], "allow"),
    ("改技能的流程文件 retro.md 不算回顧", [sh("git push"), edit(OLD_RETRO)], "block"),
    ("grep 字串裡有 git push 不算", [sh('grep -n "git push" notes.md')], "allow"),
    ("已經擋過一次（stop_hook_active）放行", [sh("git push")], "allow-active"),
    # api-request-blob 會把舊訊息（含很久以前的 git push）重放在檔案後面，不能當成剛發生（2026-11-05）
    ("api-request-blob 重放的舊 push 不算", [sh("git push"), edit(RETRO),
                                         {"type": "api-request-blob", "message": {"role": "assistant", "content": [
                                             {"type": "tool_use", "name": "Bash", "input": {"command": "git push"}}]}}],
     "allow"),
    ("子代理（sidechain）的 push 不算", [edit(RETRO), dict(sh("git push"), isSidechain=True)], "allow"),
]
fail = 0
for name, events, want in cases:
    active = want == "allow-active"
    got = run(events, active)
    exp = "allow" if active else want
    ok = got == exp
    fail += not ok
    print("PASS" if ok else "FAIL", name, got, "(want", exp, ")")
print("壞掉的輸入放行:", subprocess.run([sys.executable, "-I", HOOK], input=b"not json", capture_output=True).returncode == 0)
print("failures:", fail)
sys.exit(1 if fail else 0)   # 失敗要回非 0，對照組（故意改壞）才看得出測試有沒有抓到
