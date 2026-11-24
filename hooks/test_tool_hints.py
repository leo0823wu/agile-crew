"""tool_hints.py 的情境測試：該提醒的有提醒、不該提醒的安靜。"""
import json
import os
import subprocess
import sys
import tempfile
import uuid

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tool_hints.py")
tmp = tempfile.mkdtemp()
with open(os.path.join(tmp, "login-hints.json"), "w", encoding="utf-8") as f:
    json.dump([{"match": "login.example.test", "hint": "先開帳密檔再請使用者登入"}], f, ensure_ascii=False)


def script(name, body):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


bad = script("bad.py", 'print("中文")\n')
good = script("good.py", 'import sys\nsys.stdout.reconfigure(encoding="utf-8")\nprint("中文")\n')
ascii_only = script("ascii.py", 'print("hello")\n')
no_print = script("noprint.py", 'x = "中文"\n')
restart_sh = script("patch.sh", "#!/bin/bash\ncp a b\ndocker restart web\n")
recreate_sh = script("up.sh", "#!/bin/bash\ndocker compose up -d --force-recreate web\n")
checked_sh = script("checked.sh", "#!/bin/bash\nbash /tmp/restart_precheck.sh web || exit 1\ndocker restart web\n")
dc_sh = script("dc.sh", 'DC="docker compose"\n$DC config -q\n$DC up -d web\n')
readonly_sh = script("look.sh", "#!/bin/bash\ndocker ps\ndocker logs --since 5m web | grep -c restart\n")


def run(event, tool, cmd, session, **extra):
    payload = {"hook_event_name": event, "tool_name": tool, "tool_input": {"command": cmd},
               "session_id": session, "cwd": tmp, **extra}
    r = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       capture_output=True, env=dict(os.environ, HINT_TMP=tmp, AGILE_CREW_LOCAL=tmp))
    out = r.stdout.decode("utf-8")
    return r.returncode, (json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else "")


S1, S2, S3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
S4, S5, S6 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
write_sql = script("w.sql", "START TRANSACTION;\nINSERT INTO appdb.sample_table (A) SELECT 1;\n"
                   "DELETE r FROM sample_table_result r WHERE 1=0;\nCOMMIT;\n")
read_sql = script("r.sql", "SELECT COUNT(*) FROM sample_table WHERE YEAR = '2026';\n")
tmp_sql = script("t.sql", "CREATE TEMPORARY TABLE tmp_x (a INT);\nINSERT INTO tmp_x VALUES (1);\nUPDATE tmp_x SET a = 2;\n")
TIMEOUT = {"error": "Command timed out after 2m 0s\n"}
ENC = {"tool_response": {"stdout": "Traceback...\nUnicodeEncodeError: 'charmap' codec can't encode characters (cp1252.py)"}}
pw_sh = script("prod.sh", '#!/bin/bash\nread -rsp "DB 密碼: " PW; echo\n')
plain_sh = script("plain.sh", "#!/bin/bash\necho hi\n")
TERM = "mcp__terminal__run_in_terminal"
TAB_RESP = {"tool_response": [{"type": "text", "text": '{"tab_id":"c23","cwd":"x"}\nStarted in new terminal tab "c23"'}]}
S7 = str(uuid.uuid4())
S8, S9 = str(uuid.uuid4()), str(uuid.uuid4())
mut_py = script("mutate.py", "import subprocess, shutil\nfor f, old, new in CASES:\n    shutil.copy(f, f + '.bak')\n"
                "    try:\n        open(f, 'w').write(open(f).read().replace(old, new))\n"
                "        subprocess.run(['cmd', '/c', 'mvnw.cmd', 'test'])\n    finally:\n        shutil.copy(f + '.bak', f)\n")
mut_ps1 = script("mutate.ps1", "Copy-Item a.java a.bak\n(Get-Content a.java) -replace 'x','y' | Set-Content a.java\n.\\mvnw.cmd test\nCopy-Item a.bak a.java\n")
mut_sh = script("mutate.sh", "#!/bin/bash\ncp a.py a.bak\ntrap 'cp a.bak a.py' EXIT\nsed -i s/x/y/ a.py\npytest -q\n")
test_only = script("runtests.py", "import subprocess\nsubprocess.run(['pytest', '-q'])\n")
scratch = os.path.join(tmp, "scratchpad")
os.makedirs(os.path.join(scratch, "app_local"), exist_ok=True)
os.makedirs(os.path.join(scratch, "only_data"), exist_ok=True)
script(os.path.join("scratchpad", "app_local", "run.sh"), "#!/bin/bash\njava -jar x.jar\n")
script(os.path.join("scratchpad", "only_data", "dump.sql"), "SELECT 1;\n")
SP = scratch.replace("\\", "/")
cases = [
    # L-174 刪暫存區裡的腳本
    ("L-174：rm -rf 暫存區資料夾、裡面有腳本 → 提醒", "PreToolUse", "Bash", f'rm -rf "{SP}/app_local"', S9, {}, "L-174"),
    ("L-174：用變數寫路徑也抓得到 → 提醒", "PreToolUse", "Bash", f'S="{SP}"; docker rm -f x; rm -rf "$S/app_local" "$S/only_data"', S9, {}, "run.sh"),
    ("L-174：PowerShell Remove-Item -Recurse → 提醒", "PreToolUse", "PowerShell", f'Remove-Item -Recurse -Force "{SP}/app_local"', S9, {}, "L-174"),
    ("L-174：資料夾裡只有資料、沒有腳本 → 安靜", "PreToolUse", "Bash", f'rm -rf "{SP}/only_data"', S9, {}, None),
    ("L-174：只刪單一檔（沒有 -r）→ 安靜", "PreToolUse", "Bash", f'rm -f "{SP}/app_local/run.sh.bak"', S9, {}, None),
    # L-234 對照組腳本
    ("對照組：Python 腳本替換＋mvnw＋finally 還原 → 提醒", "PreToolUse", "PowerShell", f'python -X utf8 -I "{mut_py}"', S8, {}, "L-234"),
    ("對照組：同一支腳本第二次 → 安靜（只提醒一次）", "PreToolUse", "PowerShell", f'python -X utf8 -I "{mut_py}"', S8, {}, None),
    ("對照組：PowerShell 腳本 -replace＋mvnw＋Copy-Item → 提醒", "PreToolUse", "PowerShell", f'& "{mut_ps1}"', S8, {}, "L-234"),
    ("對照組：只跑測試、沒替換也沒還原 → 安靜", "PreToolUse", "Bash", f'python -X utf8 -I "{test_only}"', S9, {}, None),
    ("對照組：直接跑 mvnw test（沒有腳本）→ 安靜", "PreToolUse", "PowerShell", ".\\mvnw.cmd test", S9, {}, None),
    ("對照組：只是 cp／cat 這支腳本（沒執行）→ 安靜", "PreToolUse", "Bash", f'cp "{mut_py}" /tmp/x.py && cat "{mut_py}"', S9, {}, None),
    ("對照組：Bash 用 bash 跑含替換＋pytest＋trap 的 .sh → 提醒", "PreToolUse", "Bash", f'bash "{mut_sh}"', S9, {}, "L-234"),
    ("對照組：跑技能自己的測試檔 → 安靜", "PreToolUse", "PowerShell", f'python -X utf8 -I "{os.path.abspath(__file__)}"', S9, {}, None),
    ("終端機：腳本等密碼 → 提醒並帶分頁", "PostToolUse", TERM, f"bash {pw_sh}", S7, TAB_RESP, "tab_id: c23"),
    ("終端機：PowerShell 呼叫 bash.exe 跑相對路徑腳本 → 提醒", "PostToolUse", TERM, "& 'C:\\Program Files\\Git\\bin\\bash.exe' prod.sh sql x.sql", S7, TAB_RESP, "L-188"),
    ("終端機：指令本身 ssh → 提醒", "PostToolUse", TERM, "ssh example-host", S7, {}, "L-188"),
    ("終端機：不等輸入 → 安靜", "PostToolUse", TERM, f"bash {plain_sh}", S7, TAB_RESP, None),
    ("終端機：執行前不提醒", "PreToolUse", TERM, f"bash {pw_sh}", S7, {}, None),
    ("Bash 工具跑等密碼腳本 → 不是這條", "PostToolUse", "Bash", f"bash {pw_sh}", S7, {}, None),
    # (說明, event, tool, cmd, session, extra, 要出現的字 or None 表示要安靜)
    ("執行前：腳本印中文沒 reconfigure → 提醒", "PreToolUse", "PowerShell", f'& "C:/x/python.exe" -I "{bad}"', S1, {}, "L-036"),
    ("執行前：相對路徑 python -I bad.py → 提醒", "PreToolUse", "Bash", "python -I bad.py", S1, {}, "L-036"),
    ("執行前：有 reconfigure → 安靜", "PreToolUse", "PowerShell", f'python -I "{good}"', S1, {}, None),
    ("執行前：只印英文 → 安靜", "PreToolUse", "PowerShell", f'python -I "{ascii_only}"', S1, {}, None),
    ("執行前：沒有 print → 安靜", "PreToolUse", "PowerShell", f'python -I "{no_print}"', S1, {}, None),
    ("執行前：已加 -X utf8 → 安靜", "PreToolUse", "PowerShell", f'python -X utf8 -I "{bad}"', S1, {}, None),
    ("執行前：同一行先跑有 -X utf8、再跑沒有的 → 提醒", "PreToolUse", "PowerShell",
     f'python -X utf8 -I "{bad}"; python -I "{bad}"', S1, {}, "L-036"),
    ("執行前：PowerShell $env: 路徑 → 提醒", "PreToolUse", "PowerShell",
     'python -I "$env:HINT_TMP\\bad.py"', S1, {}, "L-036"),
    ("執行前：腳本不存在 → 安靜", "PreToolUse", "PowerShell", "python -I nope.py", S1, {}, None),
    ("執行後：UnicodeEncodeError cp1252 → 提醒修法", "PostToolUseFailure", "PowerShell", "python -I x.py", S1, ENC, "L-036"),
    ("執行後：只是讀到含 UnicodeEncodeError 字樣的檔案 → 安靜", "PostToolUse", "PowerShell",
     "Get-Content test_tool_hints.py", S1, ENC, None),
    ("執行後：正常輸出 → 安靜", "PostToolUse", "PowerShell", "python -I x.py", S1, {"tool_response": {"stdout": "ok"}}, None),
    ("逾時前：Bash 還沒逾時過、跑 cat → 安靜", "PreToolUse", "Bash", "cat a.txt", S2, {}, None),
    ("執行後：Bash 逾時 → 提醒 L-055", "PostToolUseFailure", "Bash", "sed -n 1,5p a.txt", S2, TIMEOUT, "L-055"),
    ("逾時後：同工作階段又用 Bash cat → 再提醒", "PreToolUse", "Bash", "cat a.txt", S2, {}, "不久前逾時過"),
    ("逾時後：Bash 跑非簡單指令（npm test）→ 安靜", "PreToolUse", "Bash", "npm test", S2, {}, None),
    ("逾時後：別的工作階段用 Bash cat → 安靜", "PreToolUse", "Bash", "cat a.txt", S1, {}, None),
    ("PowerShell 逾時不算 Bash 卡住 → 安靜", "PostToolUseFailure", "PowerShell", "Get-Content x", S1, TIMEOUT, None),
    ("Bash 正常跑完、輸出裡剛好有逾時字樣（grep 踩坑表）→ 安靜", "PostToolUse", "Bash", "grep -n timed lessons.md", S3,
     {"tool_response": {"stdout": "22:| L-055 | Bash 出現「Command timed out after」…"}}, None),
    ("上面那次不算逾時：同工作階段再用 Bash cat → 安靜", "PreToolUse", "Bash", "cat a.txt", S3, {}, None),
    ("別的工具（Edit）→ 安靜", "PreToolUse", "Edit", "", S1, {}, None),
    ("瀏覽器開要登入的網址 → 提醒登入前置", "PreToolUse", "mcp__Claude_Browser__navigate", "", S1,
     {"tool_input": {"url": "https://login.example.test/#/"}}, "先開帳密檔"),
    ("瀏覽器開一般網址 → 安靜", "PreToolUse", "mcp__Claude_Browser__navigate", "", S1,
     {"tool_input": {"url": "https://docs.example.com/"}}, None),
    # L-161 遠端重啟／重建容器前檢查
    ("遠端：ssh 直接 docker restart → 提醒", "PreToolUse", "PowerShell", "ssh.exe prod 'docker restart web'", S1, {}, "L-161"),
    ("遠端：scp 上傳含 docker restart 的 .sh 再 ssh 跑 → 提醒", "PreToolUse", "PowerShell",
     f"scp.exe \"{restart_sh}\" prod:/tmp/p.sh; ssh.exe prod 'bash /tmp/p.sh'", S1, {}, "L-161"),
    ("遠端：PowerShell 變數指到 .sh、上傳 .lf → 提醒", "PreToolUse", "PowerShell",
     f"$f=\"{recreate_sh}\"; scp.exe \"$f.lf\" prod:/tmp/u.sh; ssh.exe prod 'bash /tmp/u.sh'", S1, {}, "L-161"),
    ("遠端：腳本裡先跑 restart_precheck → 安靜", "PreToolUse", "PowerShell",
     f"scp.exe \"{checked_sh}\" prod:/tmp/c.sh; ssh.exe prod 'bash /tmp/c.sh'", S1, {}, None),
    ("遠端：只看 log（字串裡有 restart）→ 安靜", "PreToolUse", "PowerShell",
     f"scp.exe \"{readonly_sh}\" prod:/tmp/l.sh; ssh.exe prod 'bash /tmp/l.sh'", S1, {}, None),
    ("遠端：compose -f 夾選項再 up → 提醒", "PreToolUse", "PowerShell",
     "ssh.exe prod 'cd /opt/p && docker compose -f docker-compose.yml up -d web'", S1, {}, "L-161"),
    ("遠端：腳本用 $DC up -d（變數存 docker compose）→ 提醒", "PreToolUse", "PowerShell",
     f"scp.exe \"{dc_sh}\" prod:/tmp/d.sh; ssh.exe prod 'bash /tmp/d.sh'", S1, {}, "L-161"),
    ("執行後：測試輸出裡只是提到 UnicodeEncodeError cp1252 → 安靜", "PostToolUse", "PowerShell", "python -I t.py", S1,
     {"tool_response": {"stdout": "PASS 執行後：UnicodeEncodeError cp1252 → 提醒修法"}}, None),
    ("遠端：Bash 變數 S= 指到資料夾、\"$S/x.sh\" 上傳（$SCP 不能被 $S 換掉）→ 提醒", "PreToolUse", "Bash",
     f"S=\"{tmp}\"; SCP=/c/scp.exe; $SCP \"$S/dc.sh\" prod:/tmp/; /c/ssh.exe prod 'bash /tmp/dc.sh'", S1, {}, "L-161"),
    ("本機 docker compose up（沒有 ssh）→ 安靜", "PreToolUse", "PowerShell", "docker compose up -d db", S1, {}, None),
    ("本機 Bash 跑 docker restart（沒有 ssh）→ 安靜", "PreToolUse", "Bash", "docker restart n8n", S1, {}, None),
    # L-159 寫資料表前先列讀取者
    ("SQL：跑會寫表的 .sql、沒查過讀取者 → 提醒（列出表名）", "PreToolUse", "Bash", f"python -I db_local.py \"{write_sql}\"", S4, {}, "find_table_readers"),
    ("SQL：同一張表第二次 → 安靜（只提醒一次）", "PreToolUse", "Bash", f"python -I db_local.py \"{write_sql}\"", S4, {}, None),
    ("SQL：只有 SELECT 的 .sql → 安靜", "PreToolUse", "Bash", f"mysql appdb < \"{read_sql}\"", S5, {}, None),
    ("SQL：cat 看 .sql 內容（沒執行）→ 安靜", "PreToolUse", "Bash", f"cat \"{write_sql}\"", S5, {}, None),
    ("SQL：先跑 find_table_readers 查過 → 安靜", "PreToolUse", "Bash",
     "python -X utf8 -I find_table_readers.py C:/ws sample_table sample_table_result", S5, {}, None),
    ("SQL：查過的表再跑寫入 .sql → 安靜", "PreToolUse", "Bash", f"python -I db_local.py \"{write_sql}\"", S5, {}, None),
    ("SQL：暫存表 tmp_* 不算 → 安靜", "PreToolUse", "Bash", f"python -I db_local.py \"{tmp_sql}\"", S6, {}, None),
]
# 只在 Windows 成立的案例（PowerShell 反斜線路徑：macOS／Linux 的反斜線不是路徑分隔，找不到檔本來就不提醒）
WINDOWS_ONLY = {"執行前：PowerShell $env: 路徑 → 提醒"}
missing = WINDOWS_ONLY - {c[0] for c in cases}
fail = 1 if missing else 0
if missing:
    print("FAIL WINDOWS_ONLY 名單對不到案例：", sorted(missing))
skipped = 0
for name, ev, tool, cmd, sess, extra, want in cases:
    if os.name != "nt" and name in WINDOWS_ONLY:
        skipped += 1
        print("SKIP", name, "（只在 Windows 適用）")
        continue
    rc, ctx = run(ev, tool, cmd, sess, **extra)
    ok = rc == 0 and ((want is None and not ctx) or (want is not None and want in ctx))
    fail += not ok
    print("PASS" if ok else "FAIL", name, "" if ok else f"→ {ctx[:120]!r}")
for bad_input in (b"", b"not json"):
    r = subprocess.run([sys.executable, "-I", HOOK], input=bad_input, capture_output=True)
    ok = r.returncode == 0 and not r.stdout
    fail += not ok
    print("PASS" if ok else "FAIL", "壞輸入安靜放行", bad_input)
if skipped:
    print(f"skipped: {skipped}（非 Windows，只在 Windows 適用的案例）")
print("failures:", fail)
