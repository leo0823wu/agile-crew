"""工具呼叫的提醒 hook（只提醒、不擋）：把已知會一再發生的坑，在發生當下告訴 Claude 怎麼處理。

掛在 PreToolUse、PostToolUse、PostToolUseFailure（matcher: Bash|PowerShell；PostToolUse 另加 mcp__terminal__run_in_terminal）。

L-036 Windows 主控台編碼：
  - 執行前：`python ... xxx.py` 的腳本會印非 ASCII 字、卻沒有 `reconfigure(` 也沒用 `-X utf8` → 提醒先加
  - 執行後：輸出出現 UnicodeEncodeError（cp1252／charmap／cp950）→ 告訴它怎麼修，不要原樣重跑
L-055 Git Bash 卡住：
  - 執行後：Bash 出現「Command timed out after」→ 記下這個工作階段，提醒簡單指令卡住代表 Bash 掛了，改用 PowerShell／Read／Grep
  - 執行前：同一個工作階段 30 分鐘內 Bash 逾時過，又要用 Bash 跑簡單指令 → 再提醒一次
L-105 舊 repo 搬到新主機：
  - 執行前：指令（或它執行的 .sh）用 `git push` 推 `refs/heads/*`，卻沒推 `refs/remotes/` → 提醒只存在遠端追蹤的分支會漏掉
L-161 遠端重啟／重建容器：
  - 執行前：指令有 ssh，指令本身或裡面出現的本機 .sh（含 PowerShell `$f="..."` 變數）有 docker restart／compose up／--force-recreate，
    卻沒有一起跑 restart_precheck → 提醒先檢查主機名稱解析、連線、docker diff、磁碟
L-234 證明測試會紅的對照組腳本：
  - 執行前：指令執行的 .py／.ps1／.sh 同時有替換檔案內容、跑測試（mvnw、pytest、npm test…）、還原（finally、Copy-Item、cp）
    → 提醒四點（先跑基準、逐檔退回、只看預期測試、XML 讀報告）；同一工作階段每支腳本只提醒一次
L-188 終端機分頁等使用者輸入：
  - 執行後：run_in_terminal 跑的指令（或它執行的 .sh／.ps1）會停下來等輸入（read -s／read -p／Read-Host／getpass、ssh、sudo）
    → 提醒馬上用 show_pane 把那個分頁打到前面、照抄最後一行提示（2026-11-10 背景分頁開了，使用者說「我沒看到輸入密碼的畫面」）

登入前置（PreToolUse，內建瀏覽器 navigate／preview_start）：
  - 要開的網址符合本地 `login-hints.json` 的片段 → 提醒登入前要先做的事（例：先幫使用者打開帳密檔）

任何錯誤都安靜放行（exit 0、不輸出）。
"""
import json
import os
import re
import sys
import tempfile
import time

STATE_DIR = os.path.join(tempfile.gettempdir(), "claude-tool-hints")
HANG_WINDOW = 30 * 60
SIMPLE_CMD = re.compile(r"^\s*(?:cd\s+\S+\s*(?:&&|;)\s*)?(cat|sed|grep|head|tail|ls|cp|mv|wc|find|echo|docker\s+ps|git\s+(?:status|log|diff))\b")
PY_FILE = re.compile(r"(?:^|[\s;&|(\"'])(?:\S*[\\/])?(?:python(?:3)?(?:\.exe)?|py)[\"']?\s+((?:-\S+\s+)*)[\"']?([^\s\"']+\.py)\b", re.I)
RUNS_PY = re.compile(r"(?:^|[\s;&|(\"'/\\])(?:python(?:\d+(?:\.\d+)?)?|py)(?:\.exe)?[\"']?(?:\s|$)", re.I)
# 要像真的 traceback（`UnicodeEncodeError: 'charmap' codec`）；測試名稱、說明文字裡提到這個字不算（2026-11-06 跑 test_tool_hints 誤報）
ENCODE_ERR = re.compile(r"UnicodeEncodeError: '(cp1252|charmap|cp950|cp437)' codec")

FIX_036 = ("L-036：Windows 主控台的 Python 輸出編碼不是 UTF-8，`python -I` 又會忽略 PYTHONIOENCODING，印中文就當掉。"
           "修法（擇一）：腳本開頭加 `import sys; sys.stdout.reconfigure(encoding=\"utf-8\")`；或執行時加 `-X utf8`（`python -X utf8 -I x.py`，-I 不會擋 -X）。"
           "不要原樣重跑。")
HANG_055 = ("L-055：Bash 逾時了。如果剛才是簡單指令（cat／sed／grep／cp／ls／docker ps），代表 Git Bash 卡住了（電腦負載高或背景服務佔住），"
            "這個工作階段接下來讀檔改用 Read／Grep 工具、其他指令改用 PowerShell，**不要重試 Bash**；"
            "要清殘留程序可用 PowerShell `Get-Process bash | Stop-Process`（先確認沒有自己要的背景工作）。"
            "如果是本來就要跑很久的工作（上傳、建置、測試），改用 run_in_background。")
SH_FILE = re.compile(r"(?:^|[\s;&|(\"'])(?:bash|sh)\s+[\"']?([^\s\"']+\.sh)\b")
GIT_PUSH = re.compile(r"\bgit\b(?:\s+-C\s+\S+)?(?:\s+-c\s+\S+)*\s+push\b")
PUSH_QA_028 = ("L-028：要推送了。中、大的需求推之前要有獨立驗收（QA 子代理看 diff、出對抗測試），自己跑的測試與回歸不算；"
               "還沒驗就先開 QA，驗完再推。小的需求忽略這則。")
MIGRATE_105 = ("L-105：這是在把 repo 整批推到新主機嗎？只推 `refs/heads/*` 會漏掉只存在遠端追蹤裡的分支（本機常只有 master）。"
               "要一起推 `refs/remotes/origin/<分支>:refs/heads/<分支>`（本機沒有同名分支的那些），加 tags；"
               "推之前查 shallow、LFS；推完 `ls-remote` 逐分支比對 SHA 才改本機遠端。")
RESTART_156 = ("L-161：這次要在遠端機器重啟／重建容器。先跑 `scripts/restart_precheck.sh <容器>`（傳上去用 bash 跑；"
               "查容器解析自己主機名稱的速度、設定裡的資料庫／外部主機連不連得到、docker diff 裡被直接改過的檔、磁碟），"
               "有 ⚠ 先處理再重啟。重建（換 image、--force-recreate）會丟掉容器裡手改的檔；連不到又沒設逾時的連線會拖垮整站。"
               "已經檢查過就忽略。")
READERS_159 = ("L-159：這支 SQL 會寫入 {tables}。寫之前要知道還有誰在讀這些表（同網站的別頁、別的系統、排程）——"
               "兩次都是使用者提醒或做完才發現（共用設定表被別的系統讀；另一頁也顯示同一份資料、而且讀法早就錯了）。"
               "跑 `python -X utf8 -I ~/.claude/skills/agile-crew/scripts/find_table_readers.py <工作區根目錄> {tables}`，"
               "把每個讀取處放進計畫逐一判斷這次會不會影響它。這個工作階段已經查過就忽略。")
SQL_FILE = re.compile(r"((?:[A-Za-z]:)?[^\s\"'<>|;&]+\.sql)\b", re.I)
# 真的在執行 SQL 檔(cat／Read 看內容不算):mysql、psql 這類用戶端,或專案自己的執行腳本(名稱含 db_local、run_sql、db_sql)
EXEC_SQL = re.compile(r"\b(?:mysql|mariadb|psql|sqlcmd|db_local|run_sql|db_sql)\w*|<\s*\S+\.sql", re.I)
SQL_WRITE = re.compile(r"\b(?:insert\s+(?:ignore\s+)?into|replace\s+into|update|delete\s+(?:\w+\s+)?from|alter\s+table|truncate(?:\s+table)?)"
                       r"\s+(?:`?\w+`?\.)?`?(\w+)`?", re.I)
# docker 後面（可夾 -f x.yml 這類選項）緊接 restart／up 才算；`$DC up -d`（變數存 docker compose）也算；grep restart 這類不算
RESTART_CMD = re.compile(r"\bdocker(?:-compose|\s+compose)?(?:\s+-[-\w]+(?:[ =][^\s;|&]+)?)*\s+(?:restart|up)\b"
                         r"|--force-recreate|^\s*\$\{?\w+\}?\s+(?:up|restart)\b", re.M)
# PowerShell `$f="..."`、Bash `S="..."`（指令裡用 "$f.lf"、"$S/x.sh" 指到本機的 .sh）
PS_VAR = re.compile(r"(?:\$|(?:^|(?<=[\s;&]))(?=\w+=))(\w+)\s*=\s*[\"']([^\"']+)[\"']")
LOCAL_SH = re.compile(r"((?:[A-Za-z]:)?[^\s\"';|&<>]*\.sh)(?:\.lf)?\b")


SED_INPLACE = re.compile(r"\bsed\s+(?:-[A-Za-z]*\s+)*-[A-Za-z]*i")
UI_FILE = re.compile(r"\.(html?|vue|css|scss|less|jsx|tsx|jsp|svelte)$", re.I)
UIUX_244 = ("L-244：要改畫面檔，但這個工作階段還沒載入 UI/UX 設計技能。只要跟畫面有關，不分大小都要用 UI/UX："
            "小的需求先載入 UI/UX 技能（例：ui-ux-pro-max）照它的層次、字級、對比做；中、大的需求另開 UI/UX 子代理驗收。"
            "品牌色、字型沿用該品牌既有的（從它的網站樣式取），不要自己配。")
CRLF_070 = ("L-070：{files} 是 CRLF 換行，在 Git Bash 用 `sed -i` 會把整個檔的換行改掉（diff 變成整檔都改）。"
            "改用位元組替換：`python -c \"b=open(p,'rb').read(); assert b.count(old)==1; open(p,'wb').write(b.replace(old,new))\"`（old／new 用 bytes），"
            "改完 `git diff --stat` 確認只動到那幾行。")


def crlf_sed_targets(cmd, cwd):
    """L-070：Bash 指令有 sed -i，且指令裡提到的既有檔案含 CRLF → 回傳檔名（for 迴圈的檔名也會掃到）。"""
    if not SED_INPLACE.search(cmd):
        return []
    base = cwd or os.getcwd()
    m = re.match(r"\s*cd\s+[\"']?([^\"'&;]+?)[\"']?\s*(?:&&|;)", cmd)
    if m:
        base = m.group(1).strip()
    def win(path):
        mm = re.match(r"^/([a-zA-Z])/(.*)$", path)
        return f"{mm.group(1)}:/{mm.group(2)}" if mm else path
    base = win(base)
    hits = []
    for tok in re.findall(r"[^\s\"';|&()<>]+", cmd):
        if "/" not in tok and "." not in tok:
            continue
        cand = win(tok)
        path = cand if os.path.isabs(cand) else os.path.join(base, cand)
        try:
            if os.path.isfile(path) and os.path.getsize(path) < 20_000_000:
                with open(path, "rb") as f:
                    if b"\r\n" in f.read(65536):
                        hits.append(os.path.basename(path))
        except OSError:
            pass
    return sorted(set(hits))


def remote_restart_unchecked(cmd, cwd):
    """經 ssh 在遠端重啟／重建容器（指令本身，或指令裡出現的本機 .sh），而且沒有一起跑 restart_precheck。"""
    if not re.search(r"\bssh(?:\.exe)?\b", cmd):
        return False
    expanded = cmd
    for name, value in PS_VAR.findall(cmd):  # 變數名稱要整個對上：$S 不能換掉 $SCP 的開頭
        expanded = re.sub(r"\$\{?" + re.escape(name) + r"\}?(?!\w)", lambda _m: value, expanded)
    texts = [cmd]
    for m in LOCAL_SH.finditer(expanded):
        for path in (m.group(0), m.group(1)):
            path = os.path.expanduser(os.path.expandvars(path))
            if not os.path.isabs(path):
                path = os.path.join(cwd or os.getcwd(), path)
            try:
                if os.path.isfile(path) and os.path.getsize(path) < 300_000:
                    texts.append(open(path, encoding="utf-8", errors="replace").read())
                    break
            except Exception:
                pass
    joined = "\n".join(texts)
    return bool(RESTART_CMD.search(joined)) and "restart_precheck" not in joined


def pushes_heads_only(cmd, cwd):
    """git push 推 refs/heads/*，卻沒有推 refs/remotes/（看指令本身和它執行的 .sh）。"""
    texts = [cmd]
    for m in SH_FILE.finditer(cmd):
        path = os.path.expanduser(os.path.expandvars(m.group(1)))
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        try:
            if os.path.getsize(path) < 300_000:
                texts.append(open(path, encoding="utf-8").read())
        except Exception:
            pass
    return any(re.search(r"git\b[^\n]*\bpush\b[^\n]*refs/heads/\*", t) and "refs/remotes/" not in t for t in texts)


SCRIPT_TOKEN = re.compile(r"[^\s\"'&;|()]+\.(?:sh|ps1)\b", re.I)
WAITS_INPUT = re.compile(r"\bread\s+-[A-Za-z]*[sp]|\bRead-Host\b|\bgetpass\b|\bpause\b")
CMD_WAITS = re.compile(r"(?:^|[\s;&|(\"'])(?:ssh|scp|sudo|Read-Host)\b", re.I)
TAB_ID = re.compile(r'tab_id\\?"\s*:\s*\\?"([\w-]+)|terminal tab \\?"([\w-]+)')
TERMINAL_188 = ("L-188：這個終端機分頁會停下來等使用者輸入（密碼／按 Enter），但 run_in_terminal 常在背景開分頁，使用者看不到提示。"
                "現在就用 `mcp__ccd_view__show_pane`（pane: terminal, tab_id: {tab}）把它打到前面，回覆裡附分頁連結；"
                "照抄它最後一行提示（先用 read_terminal 看），說明那是終端機裡的一行字、不是跳出視窗，點進去打完按 Enter。")


# 只算「被執行」的腳本：python x.py、bash x.sh、& x.ps1／-File x.ps1／.\x.ps1；cp、sed、cat 提到檔名不算
MUT_SCRIPT = re.compile(r"(?:\b(?:python(?:3)?(?:\.exe)?|py|bash|sh)[\"']?\s+(?:-[XW]\s+\S+\s+|-\S+\s+)*|(?:^|[;&|]\s*)&\s*|-File\s+|(?:^|[;&|]\s*)\.[\\/])"
                        r"[\"']?([^\s\"'&;|()<>]+\.(?:py|ps1|sh))\b", re.I | re.M)
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_RUNNER = re.compile(r"\bmvnw?\b|\bgradlew?\b|\bpytest\b|\bnpm\s+(?:run\s+)?test\b|\bjest\b|\bvitest\b|\bgo\s+test\b|\bdotnet\s+test\b", re.I)
RESTORE = re.compile(r"\bfinally\b|shutil\.copy|Copy-Item|\bcp\s|\btrap\b", re.I)
REPLACE = re.compile(r"\.replace\(|-replace\b|\bsed\s|write_text\(|Set-Content", re.I)
MUTATION_234 = ("L-234：{name} 看起來是「改壞檔案 → 跑測試 → 還原」的對照組腳本。跑之前確認四點："
                "①第一筆先跑不改任何檔的基準，必須通過、輸出裡真的有跑到測試（例：有 `Tests run:`），基準沒過後面的「紅」都不算；"
                "②每個改過的檔各自退回一次（工具函式、呼叫端、樣板都算）；"
                "③只看預期的那個測試有沒有紅，程式跑不起來（語法錯、匯入失敗）或別的測試紅都不算；"
                "④用 XML 解析器讀測試報告（surefire `TEST-*.xml`），不用單行 grep。還原後把修改時間設成現在（L-107）。已經照做就忽略。")


SCRATCH_174 = ("L-174：要刪的暫存資料夾裡有腳本（{names}）。之後還會重跑的（打包、比對、本機啟動、驗證）先搬到專案的文件資料夾"
               "（例：`<專案>\\部署\\工具\\`），附一行用法；不會再用的才刪。曾發生：隔天要重做上線包，得從對話紀錄撈回打包與啟動腳本。")
RM_RECURSIVE = re.compile(r"\brm\s+(?:-\w*\s+)*-\w*[rR]\w*\b|\bRemove-Item\b[^;|&]*-Recurse", re.I)
SH_ASSIGN = re.compile(r"(?:^|[\s;&])\$?(\w+)\s*=\s*[\"']([^\"']+)[\"']")
SCRIPT_EXT = (".py", ".sh", ".ps1")


def scratch_scripts_removed(cmd):
    """遞迴刪除含 scratchpad 的資料夾、裡面有腳本 → 回傳腳本檔名（最多 5 個）"""
    if not RM_RECURSIVE.search(cmd) or "scratchpad" not in cmd.lower():
        return []
    expanded = cmd
    for var, val in SH_ASSIGN.findall(cmd):
        expanded = re.sub(r"\$\{?" + var + r"\b\}?", lambda _m, v=val: v, expanded)
    names = []
    for seg in re.split(r"&&|\|\||;|\n", expanded):
        if not RM_RECURSIVE.search(seg):
            continue
        for tok in re.findall(r"[\"']([^\"']+)[\"']|(\S+)", seg):
            p = (tok[0] or tok[1]).rstrip("/\\")
            if "scratchpad" not in p.lower() or not os.path.isdir(p):
                continue
            for root, _dirs, files in os.walk(p):
                names += [f for f in files if f.lower().endswith(SCRIPT_EXT)]
    return sorted(set(names))[:5]


def mutation_script(cmd, cwd):
    """指令執行的腳本同時有「替換檔案內容」「跑測試」「還原」→ 回傳腳本檔名。"""
    for tok in MUT_SCRIPT.findall(cmd):
        path = os.path.expanduser(os.path.expandvars(tok.strip("\"'")))
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        if os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(SKILL_DIR) + os.sep):
            continue  # 技能自己的腳本與測試（測試檔裡寫著範例對照組腳本）
        try:
            if os.path.getsize(path) > 300_000:
                continue
            src = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if TEST_RUNNER.search(src) and RESTORE.search(src) and REPLACE.search(src):
            return os.path.basename(path)
    return None


def terminal_waits_input(cmd, cwd):
    """終端機指令本身或它執行的 .sh／.ps1 會停下來等使用者輸入。"""
    if CMD_WAITS.search(cmd):
        return True
    for tok in SCRIPT_TOKEN.findall(cmd):
        path = os.path.expanduser(tok.strip("\"'"))
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        try:
            if os.path.getsize(path) > 300_000:
                continue
            if WAITS_INPUT.search(open(path, encoding="utf-8", errors="replace").read()):
                return True
        except Exception:
            continue
    return False


def emit(event, text):
    out = {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


def state_path(session):
    return os.path.join(STATE_DIR, re.sub(r"[^\w-]", "_", session or "unknown") + ".json")


def load_state(session):
    try:
        with open(state_path(session), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(session, state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(session), "w", encoding="utf-8") as f:
        json.dump(state, f)


def sql_written_tables(cmd, cwd):
    """指令執行的 .sql 檔會寫入哪些表（暫存表 tmp_* 與 SQL 關鍵字不算）。"""
    tables = []
    for m in SQL_FILE.finditer(cmd):
        path = os.path.expanduser(os.path.expandvars(m.group(1)))
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        try:
            if os.path.getsize(path) > 20_000_000:
                continue
            src = open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for t in SQL_WRITE.findall(src):
            t = t.lower()
            if t.startswith(("tmp", "temp")) or t in ("set", "table", "from", "into", "ignore") or t in tables:
                continue
            tables.append(t)
    return tables


def script_needs_utf8(cmd, cwd):
    """執行的 .py 會印非 ASCII 字、卻沒處理輸出編碼（每一個 python 呼叫各自看有沒有 -X utf8）。"""
    for m in PY_FILE.finditer(cmd):
        if re.search(r"-X\s*utf8", m.group(1) or "", re.I):
            continue
        path = m.group(2).strip("\"'")
        path = re.sub(r"\$env:(\w+)", lambda v: os.environ.get(v.group(1), v.group(0)), path, flags=re.I)  # PowerShell
        path = os.path.expanduser(os.path.expandvars(path))  # $HOME、%TEMP%、~
        if not os.path.isabs(path):
            path = os.path.join(cwd or os.getcwd(), path)
        try:
            if os.path.getsize(path) > 300_000:
                continue
            src = open(path, encoding="utf-8").read()
        except Exception:
            continue
        if "reconfigure(" in src or "print(" not in src:
            continue
        if any(ord(ch) > 127 for ch in src):
            return os.path.basename(path)
    return None


def login_hint(url):
    """要開的網址在本地 login-hints.json 裡（例：要使用者登入的跳板），回傳事先要做的提醒。
    檔案格式：[{"match": "網址片段", "hint": "登入前要做的事"}]；公司網址只放本地，不放技能。"""
    local = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "agile-crew-local")
    try:
        with open(os.path.join(local, "login-hints.json"), encoding="utf-8") as f:
            rules = json.load(f)
    except Exception:
        return None
    for rule in rules:
        if rule.get("match") and rule["match"].lower() in (url or "").lower():
            return "提醒（本地規則）：要開的頁面需要使用者登入。" + rule.get("hint", "")
    return None


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    event = data.get("hook_event_name", "")
    tool = data.get("tool_name", "")
    if event == "PreToolUse" and "Browser" in tool:  # 內建瀏覽器開網址（navigate／preview_start）
        hint = login_hint((data.get("tool_input") or {}).get("url"))
        if hint:
            emit(event, hint)
        return
    if tool == "mcp__terminal__run_in_terminal":
        tin = data.get("tool_input") or {}
        if event == "PostToolUse" and terminal_waits_input(tin.get("command") or "", tin.get("cwd") or data.get("cwd")):
            m = TAB_ID.search(json.dumps(data.get("tool_response"), ensure_ascii=False))
            emit(event, TERMINAL_188.format(tab=(m.group(1) or m.group(2)) if m else "剛開的分頁"))
        return
    # L-244：碰到畫面檔一定要用 UI/UX；載入過 UI/UX 技能就不提醒，否則每個工作階段提醒一次
    if event == "PreToolUse" and tool in ("Skill", "Write", "Edit"):
        tin = data.get("tool_input") or {}
        session = data.get("session_id", "")
        state = load_state(session)
        if tool == "Skill":
            if re.search(r"ui-?ux|design", tin.get("skill") or "", re.I):
                state["uiux_loaded"] = True
                save_state(session, state)
        elif UI_FILE.search(tin.get("file_path") or "") and not state.get("uiux_loaded") and not state.get("uiux_hinted"):
            state["uiux_hinted"] = True
            save_state(session, state)
            emit(event, UIUX_244)
        return
    if tool not in ("Bash", "PowerShell"):
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    session = data.get("session_id", "")

    if event == "PreToolUse":
        hints = []
        name = script_needs_utf8(cmd, data.get("cwd"))
        if name:
            hints.append(f"提醒：{name} 會印中文等非 ASCII 字，但沒有設定 UTF-8 輸出，Windows 上可能 UnicodeEncodeError。" + FIX_036)
        if tool == "Bash" and SIMPLE_CMD.search(cmd):
            hang = load_state(session).get("bash_timeout_at", 0)
            if hang and time.time() - hang < HANG_WINDOW:
                hints.append("提醒：這個工作階段的 Bash 不久前逾時過。" + HANG_055)
        if tool == "Bash":
            crlf = crlf_sed_targets(cmd, data.get("cwd"))
            if crlf:
                hints.append(CRLF_070.format(files="、".join(crlf)))
        if pushes_heads_only(cmd, data.get("cwd")):
            hints.append(MIGRATE_105)
        if GIT_PUSH.search(cmd):
            st = load_state(session)
            if not st.get("push_qa_hinted"):
                st["push_qa_hinted"] = True
                save_state(session, st)
                hints.append(PUSH_QA_028)
        if remote_restart_unchecked(cmd, data.get("cwd")):
            hints.append(RESTART_156)
        kept = scratch_scripts_removed(cmd)
        if kept:
            hints.append(SCRATCH_174.format(names="、".join(kept)))
        # L-234：對照組腳本，同一個工作階段每支腳本只提醒一次
        mut = mutation_script(cmd, data.get("cwd"))
        if mut:
            state = load_state(session)
            if mut not in state.get("mutation_hinted", []):
                hints.append(MUTATION_234.format(name=mut))
                state["mutation_hinted"] = state.get("mutation_hinted", []) + [mut]
                save_state(session, state)
        # L-159：跑 find_table_readers 的表記為已查；跑會寫表的 .sql、而那些表這個工作階段還沒查過也還沒提醒過 → 提醒一次
        if "find_table_readers" in cmd or (SQL_FILE.search(cmd) and EXEC_SQL.search(cmd)):
            state = load_state(session)
            changed = False
            if "find_table_readers" in cmd:
                after = cmd.split("find_table_readers", 1)[1]
                state["readers_checked"] = sorted(set(state.get("readers_checked", [])) | {w.lower() for w in re.findall(r"\b[A-Za-z_]\w{2,}\b", after)})
                changed = True
            else:
                tables = sql_written_tables(cmd, data.get("cwd"))
                seen = set(state.get("readers_checked", [])) | set(state.get("readers_hinted", []))
                new = [t for t in tables if t not in seen]
                if new:
                    hints.append(READERS_159.format(tables=" ".join(new)))
                    state["readers_hinted"] = sorted(set(state.get("readers_hinted", [])) | set(new))
                    changed = True
            if changed:
                save_state(session, state)
        if hints:
            emit(event, "\n".join(hints))
        return

    if event in ("PostToolUse", "PostToolUseFailure"):
        blob = json.dumps({k: v for k, v in data.items() if k not in ("tool_input", "transcript_path")}, ensure_ascii=False)
        hints = []
        # 只在這個指令有跑 Python 時才算（避免只是讀到含這串字的檔案就誤報）
        if ENCODE_ERR.search(blob) and RUNS_PY.search(cmd):
            hints.append(FIX_036)
        # 逾時只看工具本身的錯誤欄位：指令輸出裡剛好有這串字（例：grep 踩坑表）不算（2026-11-04 誤報兩次）
        if tool == "Bash" and "Command timed out after" in str(data.get("error") or ""):
            state = load_state(session)
            state["bash_timeout_at"] = time.time()
            state["bash_timeouts"] = state.get("bash_timeouts", 0) + 1
            save_state(session, state)
            hints.append(HANG_055)
        if hints:
            emit(event, "\n".join(hints))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
