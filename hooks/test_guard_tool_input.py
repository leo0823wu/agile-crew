import json, os, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_tool_input.py")

def run(payload, env=None):
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    r = subprocess.run([sys.executable, "-I", HOOK], input=raw, capture_output=True,
                       env=dict(os.environ, **(env or {})))
    return r.returncode, r.stderr.decode("utf-8", "replace")

def edit(old, new):
    return {"tool_name": "Edit", "tool_input": {"file_path": "x.txt", "old_string": old, "new_string": new}}

def sh(cmd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": cmd}}

NOTION_UPDATE = "mcp__x__notion-update-page"
NOTION_CREATE = "mcp__x__notion-create-pages"

cases = [
    # L-240 Notion 寫入的簡體／轉義錯字
    ("Notion 更新：正常繁體", {"tool_name": NOTION_UPDATE, "tool_input": {"content_updates": [{"old_str": "a", "new_str": "連一個標點都瞞不過"}]}}, 0),
    ("Notion 更新：瞞寫成瞒", {"tool_name": NOTION_UPDATE, "tool_input": {"content_updates": [{"old_str": "a", "new_str": "連一個標點都瞒不過"}]}}, 2),
    ("Notion 更新：修正錯字時 old_str 含錯字", {"tool_name": NOTION_UPDATE, "tool_input": {"content_updates": [{"old_str": "B 路也跳脱", "new_str": "B 路也跳脫"}]}}, 0),
    ("Notion 建頁：內容有簡體", {"tool_name": NOTION_CREATE, "tool_input": {"pages": [{"properties": {"title": "測試"}, "content": "这是简体"}]}}, 2),
    ("Notion 建頁：正常", {"tool_name": NOTION_CREATE, "tool_input": {"pages": [{"properties": {"title": "測試"}, "content": "這是繁體，資料庫備份"}]}}, 0),
    ("Notion 讀取不檢查", {"tool_name": "mcp__x__notion-fetch", "tool_input": {"id": "这"}}, 0),
    ("Edit 一般", edit("abc", "def"), 0),
    ("Edit new 結尾空格", edit("abc", "abc "), 2),
    ("Edit old 結尾 Tab", edit("abc\t", "abc"), 2),
    ("Edit 結尾換行", edit("abc\n", "def\n"), 0),
    ("Edit 刪除（new 空字串）", edit("abc", ""), 0),
    ("Edit 結尾縮排", edit("a\n    ", "b\n    "), 2),
    ("python -c 無內層引號", sh('python -I -c "import bcrypt; print(bcrypt.__version__)" 2>&1 | tail -1'), 0),
    ("python -c 內層單引號", sh("python -I -c \"print('x')\""), 2),
    ("python -c 單引號包雙引號", sh("python -c 'print(\"x\")'"), 2),
    ("python -c 引號沒收尾", sh('python -c "print(1)'), 2),
    ("python 跑腳本", sh("python -I seed_local_member.py"), 0),
    ("cd 後跑腳本", sh('cd "/c/tmp" && python -I rec.py'), 0),
    ("python heredoc", sh("python - <<'EOF'\nprint(1)\nEOF"), 2),
    ("含空白路徑的 python.exe", sh("\"/c/Program Files/Python/python.exe\" -c \"print('a')\""), 2),
    ("py -3 -c", sh("py -3 -c \"print('x')\""), 2),
    ("python3 -Ic 合併旗標", sh("python3 -Ic \"print('x')\""), 2),
    ("python -m 帶引號參數", sh("python -m pytest -k \"a and 'b'\""), 0),
    ("grep 字串裡有 python -c", sh('grep -n "python -I -c\\|夾引號" lessons.md'), 0),
    ("psql -c 有引號", sh("psql -c \"select 'x'\""), 0),
    ("bash -c 有引號", sh("bash -c \"echo 'x'\""), 0),
    ("PowerShell python -c 有引號", sh("python -I -c \"print('x')\"", "PowerShell"), 2),
    # L-014 ssh
    ("ssh 遠端字串夾雙引號（10/28 事故原型）", sh("ssh.exe prodhost 'cat /etc/x | grep -v -E \"password|passwd\"'", "PowerShell"), 2),
    ("PowerShell ssh 遠端字串有管線", sh("ssh.exe prodhost 'ps aux | grep java'", "PowerShell"), 2),
    ("PowerShell ssh 雙引號字串有管線", sh('ssh.exe host "ls | wc -l"', "PowerShell"), 2),
    # 回放 30 個 session：Git Bash 的單引號原樣保留雙引號與管線，900 多次都正常 → Bash 不擋
    # （2026-10-29 起 Bash 一律要用 Windows ssh.exe，見下方 L-033；這兩條改用 Windows 路徑，照樣驗 L-014 不在 Bash 擋）
    ("Bash ssh 單引號夾雙引號不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe webhost 'docker ps --format \"{{.Names}}\" | grep web'"), 0),
    ("Bash ssh 遠端管線不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe prodhost 'ps aux | grep java'"), 0),
    ("PowerShell 字串裡寫 SSH 不算", sh("$t = @(@('203.0.113.10',22,'demo SSH (VPN)')); $t | % { $_[0] }", "PowerShell"), 0),
    ("PowerShell echo 字串裡有 ssh 不算", sh('"--- ssh key"; Get-Content $HOME\\.ssh\\id_ed25519.pub | Select-Object -First 1', "PowerShell"), 0),
    ("PowerShell 加引號的 ssh.exe 路徑照樣檢查", sh("& \"C:\\Windows\\System32\\OpenSSH\\ssh.exe\" host 'ls | wc -l'", "PowerShell"), 2),
    ("PowerShell Get-Content pipe 給 ssh", sh('Get-Content "$S\\prod_check.sql" -Raw | ssh apphost "docker exec -i pg psql"', "PowerShell"), 2),
    ("ssh 正規做法：跑上傳的腳本", sh("ssh.exe prodhost 'bash /tmp/x.sh; rm -f /tmp/x.sh'", "PowerShell"), 0),
    ("ssh 後面接本機管線", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'uptime' | tail -1"), 0),
    ("ssh 帶 -o 選項", sh("/c/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -o ConnectTimeout=5 host 'hostname'"), 0),
    ("PowerShell pipe 給 ssh", sh("Get-Content x.sh | ssh.exe host bash", "PowerShell"), 2),
    ("scp 不檢查 L-014", sh("/c/Windows/System32/OpenSSH/scp.exe a.sh host:/tmp/a.sh"), 0),
    # L-033 Bash 裡不准用 Git Bash 的 ssh／scp（VPN 不穩會卡死；2026-10-29）
    ("Bash 用 Git Bash 的 ssh", sh("ssh apphost 'bash /tmp/x.sh; rm -f /tmp/x.sh'"), 2),
    ("Bash timeout 後接 scp", sh("timeout 40 scp -o BatchMode=yes a.sh apphost:/tmp/"), 2),
    ("Bash 不帶路徑的 ssh.exe（Git Bash 會解析成自己的）", sh("ssh.exe apphost 'echo ok'"), 2),
    ("Bash 不帶路徑的 scp.exe", sh("scp.exe a.sh host:/tmp/a.sh"), 2),
    ("Bash /usr/bin/ssh", sh("/usr/bin/ssh host 'uptime'"), 2),
    ("Bash cd 後接 ssh", sh("cd /tmp && ssh host 'uptime'"), 2),
    ("Bash Windows ssh.exe 可以", sh("/c/Windows/System32/OpenSSH/ssh.exe -o ConnectTimeout=10 apphost 'bash /tmp/x.sh; rm -f /tmp/x.sh'"), 0),
    # 2026-11-12：heredoc 寫部署文件，內文提到「ssh 別名」被誤擋
    ("heredoc 寫文件內文有 ssh 不擋", sh("cat >> docs.md <<'EOF'\n| 連線 | `ssh apphost`（帳號 x） |\nssh apphost 'uptime'\nEOF\necho done"), 0),
    ("heredoc 之後真的用 Git Bash ssh 照擋", sh("cat > a.md <<'EOF'\nssh apphost\nEOF\nssh apphost 'uptime'"), 2),
    ("heredoc 餵給 bash 的內文照樣檢查", sh("bash <<'EOF'\nssh apphost 'uptime'\nEOF"), 2),
    ("heredoc 那一行本身用 Git Bash ssh 照擋", sh("ssh apphost bash <<'EOF'\nuptime\nEOF"), 2),
    ("Bash timeout 接 Windows scp.exe 可以", sh("timeout 40 /c/Windows/System32/OpenSSH/scp.exe a.sh apphost:/tmp/a.sh"), 0),
    ("Bash C:/ 路徑的 ssh.exe 可以", sh("C:/Windows/System32/OpenSSH/ssh.exe host 'uptime'"), 0),
    ("Bash 加引號的 Windows ssh.exe 可以", sh('"C:\\Windows\\System32\\OpenSSH\\ssh.exe" host \'uptime\''), 0),
    ("Bash grep 字串裡的 ssh 不算", sh('grep -n "ssh apphost" notes.md'), 0),
    ("Bash ls ~/.ssh 不算", sh("ls ~/.ssh && cat ~/.ssh/config"), 0),
    ("PowerShell 的 ssh 不擋 L-033（本來就是 Windows 的）", sh("ssh apphost 'bash /tmp/x.sh; rm -f /tmp/x.sh'", "PowerShell"), 0),
    ("ssh-keygen 不算 ssh", sh('ssh-keygen -t ed25519 -C "a|b"'), 0),
    ("GIT_SSH_COMMAND 不算", sh('GIT_SSH_COMMAND="ssh -i k" git fetch'), 0),
    # L-033 第二次：手寫遠端背景啟動要擋，改用 remote_run.py（2026-11-11）
    ("手寫 ssh nohup & 背景啟動（11/11 原型）", sh("timeout 30 /c/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes apphost 'chmod 700 ~/x.sh; setsid nohup bash ~/x.sh > ~/x.log 2>&1 < /dev/null & echo STARTED'"), 2),
    ("PowerShell 手寫 ssh nohup & 也擋", sh("ssh.exe host 'nohup bash x.sh > x.log 2>&1 &'", "PowerShell"), 2),
    ("ssh nohup 但只有 2>&1 和 && 不算背景", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'nohup bash x.sh > x.log 2>&1 && echo ok'"), 0),
    ("ssh cat nohup.out 不算", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'cat nohup.out & wait'"), 0),
    ("remote_run.py 本身不擋", sh("python -X utf8 -I -u ~/.claude/skills/agile-crew/scripts/remote_run.py apphost /srv/app x.log DONE \"bash x.sh\" x.sh"), 0),
    ("沒有 ssh 的本機 nohup & 不擋", sh("nohup python -I server.py > s.log 2>&1 &"), 0),
    # L-052／L-064 BOM
    ("Set-Content -Encoding UTF8", sh("Set-Content -Path a.java -Value $s -Encoding UTF8", "PowerShell"), 2),
    ("Out-File 寫 SQL -Encoding utf8", sh("$t | Out-File C:\\x\\fix.sql -Encoding utf8", "PowerShell"), 2),
    ("Out-File -Encoding utf8 在前、檔名在後", sh("Set-Content -Encoding UTF8 -Path app.ts -Value $s", "PowerShell"), 2),
    ("寫 log 到變數路徑不擋", sh("& mvn test 2>&1 | Out-File $log -Encoding utf8", "PowerShell"), 0),
    ("寫 txt 輸出不擋", sh("$r | Out-File out.txt -Encoding utf8", "PowerShell"), 0),
    ("pipe 給 git commit", sh("$msg | git commit -F -", "PowerShell"), 2),
    # 2026-11-04 再犯：先用 Set-Content utf8 寫 commit 訊息 .txt，同一行再 git commit -F → 標題被加 BOM
    ("Set-Content utf8 寫訊息檔後 git commit -F", sh("Set-Content -Encoding utf8 -Path $m -Value \"docs: x\"; git -C $p commit -q -F $m", "PowerShell"), 2),
    ("Out-File utf8 寫 msg.txt 後 git commit -F", sh("$t | Out-File msg.txt -Encoding utf8; git commit -F msg.txt", "PowerShell"), 2),
    ("Write 寫好訊息檔再 git commit -F 不擋", sh("git -C $p commit -q -F $m", "PowerShell"), 0),
    ("寫 txt 不 commit 不擋", sh("Set-Content -Encoding utf8 -Path notes.txt -Value $s; Get-Content notes.txt", "PowerShell"), 0),
    ("WriteAllText 無 BOM", sh("[IO.File]::WriteAllText($p, $t, (New-Object Text.UTF8Encoding $false))", "PowerShell"), 0),
    ("Set-Content 不指定 utf8（ASCII 內容）", sh("Set-Content a.txt 'x'", "PowerShell"), 0),
    ("Bash 的 Out-File 字串不檢查", sh('grep -n "Out-File -Encoding utf8" lessons.md'), 0),
    # L-046 grep -P
    ("grep -P", sh("grep -P '\\d+' a.txt"), 2),
    ("grep -oP", sh("grep -oP 'x' a"), 2),
    ("grep -E", sh("grep -E 'a|b' a"), 0),
    ("grep -n 內容含 -P", sh('grep -n "grep -P" lessons.md'), 0),
    # 印出祕密
    ("cat .env", sh("cat supabase/.env"), 2),
    ("Get-Content .env", sh("Get-Content C:\\x\\.env", "PowerShell"), 2),
    ("head .env.local", sh("head -5 .env.local"), 2),
    ("cat .env.example 可以", sh("cat .env.example"), 0),
    ("grep 單一值可以", sh("grep -c '^ANON_KEY=' .env"), 0),
    ("docker inspect 無 format", sh("docker inspect supabase-rest"), 2),
    ("docker inspect 接 grep 也擋", sh("docker inspect supabase-rest | grep KEY"), 2),
    ("docker inspect 有 format", sh("docker inspect x --format '{{.State.Status}}'"), 0),
    ("printenv", sh("printenv"), 2),
    ("docker exec env", sh("docker exec supabase-rest env"), 2),
    ("printenv 單一變數可以", sh("printenv PATH"), 0),
    ("cd env 不算", sh("cd env && ls"), 0),
    ("grep 樣式裡的 |env 不算", sh("sed -n 1,9p a.properties | grep -v -i \"secret\\|password\\|env\""), 0),
    ("Select-String 樣式裡的 |ENV| 不算", sh("Select-String -Path Dockerfile -Pattern 'ARG|ENV|ANON'", "PowerShell"), 0),
    ("env 接 grep 也擋", sh("command -v glab; env | grep -i GITLAB"), 2),
    ("cat 加引號的 .env 路徑", sh('cat "/c/x/app-test-login.env"'), 2),
    ("grep -P 寫在引號裡不算", sh("echo 'do not use grep -P here'"), 0),
    ("venv env 不算", sh("python -m venv env"), 0),
    ("Read 工具不檢查", {"tool_name": "Read", "tool_input": {"file_path": "a "}}, 0),
    ("壞掉的 JSON 放行", b"not json", 0),
]
fail = 0
# 上面的預期是照 Windows（Git Bash）寫的，一律模擬 Windows 跑：在 macOS／Linux 也能驗到這段判斷，
# 不會因為跑的機器不同而失敗（2026-11-24 Mac 跑出 11 項失敗，都是下面這幾條 Git Bash 專屬規則）。
for name, payload, want in cases:
    code, err = run(payload, {"AGILE_CREW_GUARD_OS": "nt"})
    ok = code == want
    fail += not ok
    print(("PASS" if ok else "FAIL"), name, "exit", code, "(want", want, ")")
# macOS／Linux：Git Bash 專屬的兩條（L-046 grep -P、L-033 ssh）不擋，其他照擋
GITBASH_ONLY = {
    "Bash 用 Git Bash 的 ssh", "Bash timeout 後接 scp", "Bash 不帶路徑的 ssh.exe（Git Bash 會解析成自己的）",
    "Bash 不帶路徑的 scp.exe", "Bash /usr/bin/ssh", "Bash cd 後接 ssh", "heredoc 之後真的用 Git Bash ssh 照擋",
    "heredoc 餵給 bash 的內文照樣檢查", "heredoc 那一行本身用 Git Bash ssh 照擋", "grep -P", "grep -oP",
}
picked = [(n, pl) for n, pl, _ in cases if n in GITBASH_ONLY]
if len(picked) != len(GITBASH_ONLY):
    fail += 1
    print("FAIL GITBASH_ONLY 名單對不到案例：", sorted(GITBASH_ONLY - {n for n, _ in picked}))
posix_cases = [("非 Windows 不擋：" + n, pl, 0) for n, pl in picked] + [
    ("非 Windows：python -c 夾引號照擋", sh("python -I -c \"print('x')\""), 2),
]
# 其餘案例在非 Windows 的結果要跟 Windows 一樣（證明只有 Git Bash 專屬規則放行，其他不會誤擋或漏擋）
posix_cases += [("非 Windows 同 Windows：" + n, pl, w) for n, pl, w in cases if n not in GITBASH_ONLY]
for name, payload, want in posix_cases:
    got = run(payload, {"AGILE_CREW_GUARD_OS": "posix"})[0]
    ok = got == want
    fail += not ok
    print("PASS" if ok else "FAIL", name, got)
# L-047 Playwright:沒裝自帶瀏覽器時沒指定 channel 要擋;裝了就不擋;預覽版 Python 的同步 API 要擋
def wpy(content, path="shot.py"):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
NO_BROWSERS = {"PLAYWRIGHT_BROWSERS_PATH": os.path.join(os.path.dirname(HOOK), "__no_such_dir__")}
HAS_BROWSERS = {"PLAYWRIGHT_BROWSERS_PATH": os.path.dirname(HOOK)}
ASYNC = "from playwright.async_api import async_playwright\n"
SYNC_EXPECT = 0 if sys.version_info.releaselevel == "final" else 2
pw_cases = [
    ("沒裝瀏覽器、launch 沒 channel", wpy(ASYNC + "b = await p.chromium.launch(args=['--disable-gpu'])"), NO_BROWSERS, 2),
    ("沒裝瀏覽器、launch 有 channel", wpy(ASYNC + "b = await p.chromium.launch(channel='msedge', args=['--disable-gpu'])"), NO_BROWSERS, 0),
    ("沒裝瀏覽器、多行參數有 channel", wpy(ASYNC + "b = await p.chromium.launch(\n    headless=True,\n    channel='msedge')"), NO_BROWSERS, 0),
    ("沒裝瀏覽器、指定 executable_path", wpy(ASYNC + "b = await p.chromium.launch(executable_path=r'C:\\e.exe')"), NO_BROWSERS, 0),
    ("裝了瀏覽器、launch 沒 channel 不擋", wpy(ASYNC + "b = await p.chromium.launch()"), HAS_BROWSERS, 0),
    ("不是 .py 不檢查", wpy(ASYNC + "p.chromium.launch()", "notes.md"), NO_BROWSERS, 0),
    ("沒用 Playwright 不檢查", wpy("print('chromium.launch(')"), NO_BROWSERS, 0),
    ("同步 API(預覽版 Python 才擋)", wpy("from playwright.sync_api import sync_playwright\np.chromium.launch(channel='msedge')"), HAS_BROWSERS, SYNC_EXPECT),
]
# L-122 mvnw.cmd 沒加 .\（只在 Windows 擋）
def wfile(content, path):
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
WIN = {"AGILE_CREW_GUARD_OS": "nt"}
POSIX = {"AGILE_CREW_GUARD_OS": "posix"}
import tempfile
_cfg = os.path.join(tempfile.mkdtemp(), "config")
with open(_cfg, "w", encoding="utf-8") as _f:
    _f.write("Host known\n    HostName 198.51.100.5\n    Port 2201\n\nHost 198.51.100.9\n    Port 22\n")
CFG = dict(WIN, AGILE_CREW_SSH_CONFIG=_cfg)
pw_cases += [
    # L-014 再犯：ssh 讀本機檔當 stdin（11/19 事故原型）
    ("ssh-stdin：bash -s < 腳本", sh("/c/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes host 'bash -s' < \"$S/x.sh\" > out.txt"), WIN, 2),
    ("ssh-stdin：< 緊接檔名", sh("/c/Windows/System32/OpenSSH/ssh.exe host bash <x.sh"), WIN, 2),
    ("ssh-stdin：只導出 stdout 不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'mysqldump db' > \"$R/a.sql\""), WIN, 0),
    ("ssh-stdin：2>&1 不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'ls' 2>&1"), WIN, 0),
    ("ssh-stdin：遠端字串裡的 < 不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe host 'mysql db < /tmp/a.sql'"), WIN, 0),
    ("ssh-stdin：本機 docker exec -i < 檔不擋", sh("docker exec -i apptest-db mysql -uroot appdb < \"$S/schema.sql\""), WIN, 0),
    ("ssh-stdin：PowerShell 不檢查", sh("ssh host 'ls'", "PowerShell"), WIN, 0),
    # L-080 第三次：新機器先 ssh 試（11/19 事故原型）
    ("new-host：config 沒有的 IP 用 Windows ssh 試連", sh("/c/Windows/System32/OpenSSH/ssh.exe -o BatchMode=yes -p 2105 u\x40203.0.113.7 'hostname'"), CFG, 2),
    ("new-host：PowerShell 也擋", sh("ssh -p 2105 u\x40203.0.113.7 hostname", "PowerShell"), CFG, 2),
    ("new-host：scp 也擋", sh("/c/Windows/System32/OpenSSH/scp.exe -P 2105 a.txt u\x40203.0.113.7:/tmp/"), CFG, 2),
    ("new-host：config 的 HostName 不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe -p 2201 u\x40198.51.100.5 hostname"), CFG, 0),
    ("new-host：config 的 Host 是 IP 不擋", sh("ssh u\x40198.51.100.9 hostname", "PowerShell"), CFG, 0),
    ("new-host：用別名不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe known hostname"), CFG, 0),
    ("new-host：遠端字串裡的 帳號@IP 不擋", sh("/c/Windows/System32/OpenSSH/ssh.exe known 'grep u\x40203.0.113.7 /var/log/x'"), CFG, 0),
    ("new-host：沒有 ssh 的指令不擋", sh("git log --author=u\x40203.0.113.7"), CFG, 0),
    ("new-host：config 讀不到放行", sh("ssh -p 2105 u\x40203.0.113.7 hostname", "PowerShell"), dict(WIN, AGILE_CREW_SSH_CONFIG=_cfg + ".none"), 0),
    ("msys-path：docker run -e APP_BASE_PATH=/app（11/12 事故原型）", sh('docker run -d --name t -p 1:2 -e APP_BASE_PATH=/app -e X="$U" img:v1'), WIN, 2),
    ("msys-path：--build-arg BASE=/app", sh("docker build --build-arg BASE=/app -t a ."), WIN, 2),
    ("msys-path：加 MSYS_NO_PATHCONV 不擋", sh("MSYS_NO_PATHCONV=1 docker run -e APP_BASE_PATH=/app img"), WIN, 0),
    ("msys-path：值不是斜線開頭不擋", sh("docker run -e SERVER_PORT=8080 -e U='jdbc:mysql://db/x' img"), WIN, 0),
    ("msys-path：// 開頭不擋", sh("docker run -e P=//server/share img"), WIN, 0),
    ("msys-path：-v 掛載路徑不擋", sh("docker run -v /c/data:/data img"), WIN, 0),
    ("msys-path：PowerShell 不擋", sh("docker run -e APP_BASE_PATH=/app img", "PowerShell"), WIN, 0),
    ("msys-path：非 Windows 不擋", sh("docker run -e APP_BASE_PATH=/app img"), POSIX, 0),
    ("docker-rm-db：rm -f 測試庫沒帶 -v（11/13 事故原型）", sh("docker rm -f apptest-web apptest-ai apptest-db 2>&1 | tr x y"), WIN, 2),
    ("docker-rm-db：PowerShell 也擋", sh("docker rm -f app-mariadb-local", "PowerShell"), WIN, 2),
    ("docker-rm-db：postgres 容器", sh("docker container rm shop-pg"), POSIX, 2),
    ("docker-rm-db：-fv 不擋", sh("docker rm -fv apptest-db"), WIN, 0),
    ("docker-rm-db：--volumes 不擋", sh("docker rm -f --volumes apptest-db"), WIN, 0),
    ("docker-rm-db：非資料庫容器不擋", sh("docker rm -f apptest-web apptest-ai"), WIN, 0),
    ("docker-rm-db：rmi 映像檔不擋", sh("docker rmi mariadb:10.3"), WIN, 0),
    ("docker-rm-db：volume rm 不擋", sh("docker volume rm abc123"), WIN, 0),
    ("docker-rm-db：dashboard 名稱不誤擋", sh("docker rm -f dashboard-web"), WIN, 0),
    ("docker-rm-db：字串裡的指令不擋（11/13 改測試檔誤擋）", sh("$t=$t.Replace('docker rm -f a-db','x')", "PowerShell"), WIN, 0),
    ("mvnw：cmd //c \"mvnw.cmd ...\"（11/04 事故原型）", sh('(cd "$1" && cmd //c "mvnw.cmd -q -o test -Dtest=$2" > x.log)'), WIN, 2),
    ("mvnw：PowerShell 行首 mvnw.cmd", sh("mvnw.cmd -q test", "PowerShell"), WIN, 2),
    ("mvnw：PowerShell & mvnw.cmd", sh("& mvnw.cmd -q test", "PowerShell"), WIN, 2),
    ("mvnw：cmd /c mvnw.cmd", sh("cmd /c mvnw.cmd -q package", "PowerShell"), WIN, 2),
    ("mvnw：& .\\mvnw.cmd 不擋", sh("Set-Location $r; & .\\mvnw.cmd -q -o test", "PowerShell"), WIN, 0),
    ("mvnw：完整路徑不擋", sh('& "C:\\code\\x\\mvnw.cmd" -q test', "PowerShell"), WIN, 0),
    ("mvnw：./mvnw.cmd 不擋", sh("cd /c/x && ./mvnw.cmd -q test"), WIN, 0),
    ("mvnw：只是 ls 這個檔不擋", sh("ls /c/code/x/mvnw.cmd"), WIN, 0),
    ("mvnw：grep 正規式裡的 |mvnw.cmd 不擋（回放誤擋）", sh('grep -n -E "ISO-8859|mvnw.cmd|cmd //c" lessons-tech.md'), WIN, 0),
    ("mvnw：cd x && mvnw.cmd 要擋", sh("cd /c/x && mvnw.cmd -q test"), WIN, 2),
    ("mvnw：寫 .sh 裡有 cmd //c \"mvnw.cmd\"", wfile('cmd //c "mvnw.cmd -q test"\n', "t.sh"), WIN, 2),
    ("mvnw：寫 .cmd 用 .\\mvnw.cmd 不擋", wfile("cd /d C:\\x\r\n.\\mvnw.cmd -q package\r\n", "b.cmd"), WIN, 0),
    ("mvnw：寫 .md 文件提到 mvnw.cmd 不擋", wfile('"mvnw.cmd" 要加 .\\\n', "notes.md"), WIN, 0),
    ("grep-P：寫 .sh 裡有 grep -qP（11/05 正式站防呆失效原型）", wfile("set -uo pipefail\ngrep -qP '^years\\t2026\\t' f && stop x\n", "prod.sh"), WIN, 2),
    ("grep-P：.sh 註解提到 grep -P 不擋", wfile("# 不用 grep -P(會失效)\nawk -F'\\t' '$1==\"x\"' f\n", "prod.sh"), WIN, 0),
    ("grep-P：寫 .md 文件提到 grep -P 不擋", wfile("不要用 grep -qP\n", "notes.md"), WIN, 0),
    ("mvnw：非 Windows 不擋", sh("mvnw.cmd -q test", "PowerShell"), POSIX, 0),
    ("ps-case：$G 路徑、$g 內容（11/05 事故原型）", sh('$G="C:\\a\\x.md"; $g=[IO.File]::ReadAllText($G); [IO.File]::WriteAllText($G,$g)', "PowerShell"), WIN, 2),
    ("ps-case：$D／$d", sh('$D="C:\\work\\notes.md"; $d=[IO.File]::ReadAllText($D)', "PowerShell"), WIN, 2),
    ("ps-case：同名重複賦值不擋", sh('$t=[IO.File]::ReadAllText($F); $t=$t.Replace("a","b")', "PowerShell"), WIN, 0),
    ("ps-case：只比較不賦值不擋", sh("if ($x -eq $X) { }; $b == 2", "PowerShell"), WIN, 0),
    ("ps-case：字串裡的 $G=1 不擋", sh('Write-Host "$G=1 and $g=2"', "PowerShell"), WIN, 0),
    ("ps-case：Bash 工具不擋", sh("G=1; g=2; echo $G $g"), WIN, 0),
    ("ps1：中文標籤沒 BOM（11/05 事故原型）", wfile("$muts = @(\n  @('拿掉比對', 'a', 'b')\n)\n", "mutate.ps1"), WIN, 2),
    ("ps1：全 ASCII 不擋", wfile("Set-Location C:\\x\n& .\\mvnw.cmd -q test\n", "mutate.ps1"), WIN, 0),
    ("ps1：有 BOM 的中文不擋", wfile("\ufeff# 中文註解\nWrite-Host 'ok'\n", "a.ps1"), WIN, 0),
    ("ps1：.py 有中文不擋", wfile("print('中文')\n", "a.py"), WIN, 0),
    ("ps1：.sh 有中文不擋", wfile("echo '中文'\n", "a.sh"), WIN, 0),
    ("ps1：非 Windows 不擋", wfile("Write-Host '中文'\n", "a.ps1"), POSIX, 0),
    ("jdk：.py 直接 javap 原路徑（11/06 事故原型）", wfile("import subprocess\nJAVAP = r'C:\\jdk\\bin\\javap.exe'\nsubprocess.run([JAVAP, '-c', '-p', path])\n", "cmp.py"), WIN, 2),
    ("jdk：.py 先複製到 tempfile 不擋", wfile("import subprocess, tempfile, shutil\nd = tempfile.mkdtemp()\nsubprocess.run(['javap', '-c', d + '/X.class'])\n", "cmp.py"), WIN, 0),
    ("jdk：.sh 用 /tmp 不擋", wfile("cp \"$1\" /tmp/x.class && javap -c /tmp/x.class\n", "a.sh"), WIN, 0),
    ("jdk：.sh 直接 javac 原路徑", wfile("javac -d out \"$SRC\"/*.java\n", "b.sh"), WIN, 2),
    ("jdk：註解提到 javap 不擋", wfile("# 不要直接 javap 中文路徑\nprint(1)\n", "c.py"), WIN, 0),
    ("jdk：java 不算（只看 javap／javac）", wfile("subprocess.run(['java', '-version'])\n", "d.py"), WIN, 0),
    ("jdk：非 Windows 不擋", wfile("subprocess.run(['javap', path])\n", "e.py"), POSIX, 0),
]
for name, payload, env, want in pw_cases:
    got = run(payload, env)[0]
    ok = got == want
    fail += not ok
    print("PASS" if ok else "FAIL", name, got)
print("sample message:", run(sh("python -I -c \"print('x')\""))[1].splitlines()[0])
print("sample message:", run(edit("abc", "abc "))[1].splitlines()[0])
print("failures:", fail)
