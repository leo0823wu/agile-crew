"""PreToolUse 自動擋（2026-10-29 使用者同意加；編號見 ~/.claude/skills/dev-team/references/lessons.md）。

1) L-032 Edit 的 old_string / new_string 以空格或 Tab 結尾 → 擋。
   編輯工具會吃掉結尾空白（10/28、10/29 兩次，兩個啟動參數黏在一起）。
2) L-042 Bash / PowerShell 裡把 Python 程式直接寫在指令上：
   `python ... -c` 的程式碼含引號，或用 heredoc（`<<`）餵給 python → 擋。
   引號解析常出錯（unexpected EOF 五次以上、\\t \\f 被吃成控制字元）。
3) L-014（只在 PowerShell）ssh 後面的遠端指令字串裡有雙引號或管線 `|` → 擋；用管線把東西 pipe 給 ssh → 擋。
   PowerShell 5.1 曾把 `"password|passwd"` 的雙引號吃掉，遠端變成 `| passwd`，意外執行改密碼指令。
   Git Bash 不擋：單引號會原樣保留（回放 30 個 session，Bash 裡這類 ssh 900 多次都正常）。
4) L-052／L-064 PowerShell 用 Set-Content／Add-Content／Out-File -Encoding utf8 寫原始碼、SQL、設定檔，
   或把文字 pipe 給 git → 擋（會加 BOM）。寫 log／輸出檔不擋。
5) L-046 Bash 用 `grep -P` → 擋（Windows 的 Git Bash 在某些語系下會無聲失效，比對結果全是空的；只在 Windows 擋）。
6) 印出祕密：cat／type／Get-Content 整份 .env、沒帶 --format 的 docker inspect、不帶參數的 printenv／env → 擋
   （2026-10-29 子代理用 docker inspect 印出演練環境金鑰）。要確認設定只列名稱、或只取單一值放進變數。
7) L-033 Bash 工具裡用 Git Bash 的 ssh／scp（含不帶路徑的 ssh.exe，Git Bash 會解析成它自己的）→ 擋；
   VPN 不穩時它會整個卡住、timeout 也殺不掉（2026-10-29 部署卡逾時兩次）。要用 Windows 內建
   /c/Windows/System32/OpenSSH/ssh.exe、scp.exe。PowerShell 工具的 ssh 本來就是 Windows 的，不檢查。
8) L-047 Write 寫 .py：Playwright 開 Chromium 沒指定 channel／executable_path，而這台沒裝 Playwright 自帶的瀏覽器
   （PLAYWRIGHT_BROWSERS_PATH 或 %LOCALAPPDATA%\\ms-playwright 不存在）→ 擋；預覽版 Python 用同步 API → 擋
   （同步 API 會直接當掉）。裝了瀏覽器、正式版 Python 就不擋。規則寫進簡報後仍再犯（2026-11-04 主控自測）。
9) L-122（只在 Windows）指令或寫入的 .sh／.cmd／.bat／.ps1 裡，用 `mvnw.cmd` 當指令卻沒加 `.\\`／`./` → 擋。
   cmd、PowerShell、Git Bash 都不從目前目錄找執行檔，「找不到指令」被當成測試失敗（2026-10-16、11-04 兩次）。
10) L-143（只在 PowerShell）同一段指令賦值兩個只差大小寫的變數（`$G=` 和 `$g=`）→ 擋。
   PowerShell 變數不分大小寫，路徑被內容蓋掉（2026-11-05 同一 session 兩次；回放 16,007 筆 0 誤擋）。
11) L-134（只在 Windows）Write 寫 .ps1，內容有非 ASCII 字又沒有 BOM → 擋。
   PowerShell 5.1 用 ANSI 讀沒有 BOM 的檔，整支解析失敗（2026-11-04、11-05 兩次）。
12) L-073（只在 Windows）Write 寫 .py／.sh／.cmd／.bat／.ps1，呼叫 javap／javac 卻沒有先複製到英文暫存路徑 → 擋。
   JDK 8 讀不了中文路徑、輸出空的，比對腳本空對空報「一樣」（2026-10-28 兩次、11-06 第三次）。
13) L-033 第二次 Bash／PowerShell 指令裡手寫「ssh … nohup … &」在遠端背景啟動 → 擋，改用 scripts/remote_run.py。
   ssh 等背景工作做完才回、被 timeout 砍掉輸出全失（2026-10-29、11-11 兩次）。`2>&1`、`&&` 不算背景。
14) L-162（只在 Windows 的 Bash）docker 的 `-e／--env／--build-arg 名稱=/值` 沒加 MSYS_NO_PATHCONV → 擋。
   Git Bash 把 `/app` 改寫成 `C:/Program Files/Git/app`（2026-11-06 設定檔、11-12 容器起不來，兩次）。
15) L-223 `docker rm` 刪資料庫容器（名稱含 db／mariadb／mysql／postgres／pg）卻沒帶 -v／--volumes → 擋。
   資料庫映像檔把資料放在匿名磁碟區，只刪容器資料還在；測試庫的資料會一直留在磁碟區
   （曾經隔天才發現）。
16) L-080 第三次 ssh／scp 連「帳號@IPv4」而這個 IP 不在 ~/.ssh/config → 擋（新機器）：先讀部署說明文件、
   用 scripts/pubkey_cmd.py 產佈公鑰指令給使用者，不要自己先 ssh 試、不要手寫（pipe 公鑰會變 0 bytes）。
   config 讀不到就放行；測試用 DEV_TEAM_SSH_CONFIG 指定 config。
17) L-014 再犯（只在 Windows 的 Bash）ssh 指令用 `<` 把本機檔案餵給遠端（`ssh.exe 別名 'bash -s' < x.sh`）→ 擋；
   Windows 的 ssh 讀 Git Bash 轉進來的 stdin 會卡住（2026-11-19）。改 scp 上傳＋bash /tmp/x.sh 或 remote_run.py。

擋下＝exit 2，stderr 的說明會回給 Claude。腳本自己出錯一律放行（exit 0），不卡正常工作。
測試：python -I ~/.claude/skills/dev-team/hooks/test_guard_tool_input.py（每條規則都有該擋／不該擋的對照）。
"""
import json
import os
import re
import sys

# 規則 5、7 只在 Windows（Git Bash）適用；測試可用 DEV_TEAM_GUARD_OS=posix 模擬其他系統
IS_WINDOWS = (os.environ.get("DEV_TEAM_GUARD_OS") or os.name) == "nt"

PY_TOKEN = re.compile(
    r"""(?:^|[\s;&|(`])["']?(?:[^\s"';&|]*[/\\])?(?:python(?:\d+(?:\.\d+)?)?|py)(?:\.exe)?["']?(?=\s|$)""",
    re.IGNORECASE,
)

MSG_EDIT = (
    "已擋下（自動檢查）：Edit 的 {field} 以空白或 Tab 結尾，編輯工具會把結尾空白吃掉，"
    "改出來的檔案會跟預期不同（例：2026-10-29 兩個啟動參數黏在一起）。\n"
    "請把要改的字串往後多帶幾個字元，讓 old_string／new_string 都不以空白結尾；"
    "要改的就是空白本身，改用 Python 以 bytes 讀寫（注意 CRLF）。"
)
MSG_PY = (
    "已擋下（自動檢查）：Python 程式直接寫在指令裡（{why}）。bash／PowerShell 的引號解析常出錯"
    "（unexpected EOF、\\t \\f 被吃成控制字元），已發生五次以上。\n"
    "請用 Write 工具把程式寫成 .py 檔（放 scratchpad），再用 `python -I <檔案路徑>` 執行。"
)


def ends_with_blank(s):
    return isinstance(s, str) and s != "" and s[-1] in " \t"


def read_quoted(s, i):
    """s[i] 是引號；回傳 (內容, 是否有收尾)。雙引號內認反斜線跳脫。"""
    q = s[i]
    j = i + 1
    buf = []
    while j < len(s):
        c = s[j]
        if q == '"' and c == "\\" and j + 1 < len(s):
            buf.append(s[j:j + 2])
            j += 2
            continue
        if c == q:
            return "".join(buf), True
        buf.append(c)
        j += 1
    return "".join(buf), False


def python_inline_problem(cmd):
    for m in PY_TOKEN.finditer(cmd):
        rest = cmd[m.end():]
        line = rest.split("\n", 1)[0]
        if "<<" in line:
            return "用 heredoc 餵給 python"
        i = 0
        while True:
            while i < len(rest) and rest[i] in " \t":
                i += 1
            if i >= len(rest) or rest[i] != "-":
                break  # 接的是腳本路徑或指令結束：不是 -c
            j = i
            while j < len(rest) and rest[j] not in " \t\n;&|":
                j += 1
            tok = rest[i:j]
            i = j
            if tok.startswith("--"):
                continue
            if tok.endswith("c") and tok[1:].isalpha():
                while i < len(rest) and rest[i] in " \t":
                    i += 1
                if i < len(rest) and rest[i] in "\"'":
                    code, closed = read_quoted(rest, i)
                    if not closed:
                        return "python -c 的程式碼引號沒有收尾"
                    if "'" in code or '"' in code:
                        return "python -c 的程式碼裡面又有引號"
                break
    return None


SSH_TOKEN = re.compile(r"""(?:^|[\s;&|(`])["']?(?:[^\s"';&|]*[/\\])?ssh(?:\.exe)?["']?(?=\s|$)""", re.IGNORECASE)
MSG_SSH = (
    "已擋下（自動檢查 L-014）：{why}。PowerShell 5.1 曾把遠端字串裡的雙引號吃掉，"
    "`grep -v -E \"password|passwd\"` 變成 `| passwd`，意外執行改密碼指令。\n"
    "碰遠端機器一律：Write 工具寫 LF 的 .sh 檔 → scp.exe 上傳 → "
    "`ssh.exe 別名 'bash /tmp/x.sh; rm -f /tmp/x.sh'`。"
)


def quoted_positions(cmd):
    """引號裡面的字元位置（用來略過寫在字串裡的 ssh，例：'demo SSH (VPN)'、"--- ssh key"）。"""
    inside = set()
    i = 0
    while i < len(cmd):
        if cmd[i] in "\"'":
            seg, closed = read_quoted(cmd, i)
            end = i + len(seg) + (2 if closed else 1)
            inside.update(range(i + 1, end - (1 if closed else 0)))
            i = end
            continue
        i += 1
    return inside


def ssh_problem(cmd, tool):
    inside = quoted_positions(cmd)
    for m in SSH_TOKEN.finditer(cmd):
        # 比對到的第一個字（ssh 前面的空白或分隔字元）在引號裡＝寫在字串裡的 ssh，不是指令；
        # 加引號的執行檔路徑（& "C:\...\ssh.exe"）前面那個空白在引號外，照樣檢查
        if m.start() in inside:
            continue
        before = cmd[:m.start() + 1].rstrip()
        if tool == "PowerShell" and before.endswith("|"):
            return "用 PowerShell 管線把內容 pipe 給 ssh（會加 BOM、換行也會被改）"
        rest = cmd[m.end():].split("\n", 1)[0]
        i = 0
        while i < len(rest):
            c = rest[i]
            if c in "\"'":
                seg, _ = read_quoted(rest, i)
                if '"' in seg or (c == "'" and "\\\"" in seg):
                    return "ssh 的遠端指令字串裡又有雙引號"
                if "|" in seg:
                    return "ssh 的遠端指令字串裡有管線 |"
                i += len(seg) + 2
                continue
            if c in ";&" or (c == "|" and tool == "Bash"):
                break  # 本機這一段指令結束
            i += 1
    return None


# 只擋寫「會被程式讀」的檔（原始碼、SQL、設定）：寫 log／輸出檔給人看的不擋（回放 30 個 session，174 次是寫 log 到變數路徑）
BOM_WRITE = re.compile(
    r"\b(?:Set-Content|Add-Content|Out-File)\b[^\n|;]*?"
    r"\.(?:java|kt|ts|tsx|js|mjs|cjs|sql|sh|xml|properties|html|css|json|ya?ml|env|md|gradle)\b['\"]?"
    r"[^\n|;]*-Encoding\s+['\"]?utf-?8\b(?!NoBOM)"
    r"|\b(?:Set-Content|Add-Content|Out-File)\b[^\n|;]*-Encoding\s+['\"]?utf-?8\b(?!NoBOM)[^\n|;]*?"
    r"\.(?:java|kt|ts|tsx|js|mjs|cjs|sql|sh|xml|properties|html|css|json|ya?ml|env|md|gradle)\b",
    re.IGNORECASE,
)
PIPE_GIT = re.compile(r"\|\s*git(?:\.exe)?\s+(?:commit|apply|am)\b", re.IGNORECASE)
# 同一行先用 Set-Content／Out-File -Encoding utf8 寫檔、再 git commit -F：訊息檔是 .txt 不在上面的副檔名清單，
# 但一樣會把 BOM 帶進 commit 標題（2026-11-04 再犯）
ANY_UTF8_WRITE = re.compile(
    r"\b(?:Set-Content|Add-Content|Out-File)\b[^\n|;]*-Encoding\s+['\"]?utf-?8\b(?!NoBOM)", re.IGNORECASE)
GIT_COMMIT_F = re.compile(r"\bgit(?:\.exe)?\b[^\n|;]*\bcommit\b[^\n|;]*\s-F\b", re.IGNORECASE)
MSG_BOM = (
    "已擋下（自動檢查 L-052／L-064）：{why}，Windows PowerShell 5.1 會在開頭加 BOM"
    "（javac 報 \\ufeff、commit 訊息第一個字元被污染）。\n"
    "原始碼用 Edit／Write 工具；commit 訊息先用 Write 寫成檔再 `git commit -F <檔>`；"
    "一定要用 PowerShell 寫檔就用 [IO.File]::WriteAllText(path, text, (New-Object Text.UTF8Encoding $false))。"
)


def bom_problem(cmd):
    if BOM_WRITE.search(cmd):
        return "用 Set-Content／Add-Content／Out-File -Encoding utf8 寫檔"
    if PIPE_GIT.search(cmd):
        return "用 PowerShell 管線把文字 pipe 給 git"
    if ANY_UTF8_WRITE.search(cmd) and GIT_COMMIT_F.search(cmd):
        return "用 Set-Content／Out-File -Encoding utf8 寫 commit 訊息檔再 git commit -F"
    return None


GREP_P = re.compile(r"(?:^|[\s;&|(])grep\s+(?:-[A-Za-z]*P[A-Za-z]*|--perl-regexp)\b")
# L-240：寫 Notion 時手寫 \uXXXX 轉義，常把字轉成形近的簡體或罕用字（瞞→瞒、脫→脱、隨→随、銷→销），
# 讀回來才發現。只收「繁體文件裡不該出現」的簡體專用字，避免擋到正常內容。
SIMPLIFIED_ONLY = set(
    "这们时为个来说对发会过还进动实现点认让话应题关车东门问间长开华网专业转换设备计统资数库务页码报价单证书"
    "机络传输链连线经验记录读写删复迁护维检测试区节钥签凭电视频运营销脱随瞒抳攞掍兕妈"
    # 擴充：常用簡體專用字（排除干丑后里斗卜云几卷尸么伙刮岳御扎札朴范涂咸胜冲迹叶吁這類繁體也會用的字）
    "爱罢备贝笔边变标宾补币闭毕编辩飘别财蚕仓产尝厂场彻陈尘衬称惩迟齿处触辞聪丛错达带单担胆导灯敌递"
    "钓顶冻独断队吨夺恶尔饵罚阀飞费纷坟奋风凤妇复负该盖赶钢纲岗巩贡构购顾观馆惯广归龟规轨柜贵"
    "汉号轰红坏欢环唤挥辉汇绘浑获货祸击积饥鸡极辑级挤纪价驾坚监艰检荐鉴键剑奖酱胶浇骄搅较阶"
    "洁结紧锦仅尽惊经颈镜纠旧举剧惧觉绝军凯壳课垦恳库裤块宽矿亏馈扩阔蜡腊赖蓝栏拦篮兰揽览"
    "懒烂滥劳乐垒类离礼丽厉励历俩联莲怜帘敛脸恋炼练粮两辆谅疗辽猎临邻铃灵岭领刘龙聋笼楼芦卢炉虏"
    "鲁禄陆驴吕铝侣屡缕虑滤绿峦乱轮伦论萝罗逻锣骡骆玛码蚂马骂吗买麦卖迈馒蛮满贸镁闷梦谜弥觅"
    "绵庙灭悯鸣铭谬谋亩纳难挠脑恼闹腻酿鸟聂宁拧钮纽浓农诺欧殴呕盘庞赔喷鹏骗频贫苹评泼颇扑铺谱齐骑岂"
    "启气弃牵铅谦钱钳浅谴枪墙抢桥乔侨翘窍窃钦亲轻倾顷请庆琼穷趋躯驱权劝鹊饶扰绕热韧认荣绒软锐闰"
    "润赛伞丧骚扫涩杀纱筛晒闪陕伤赏烧绍摄设绅审婶肾渗声绳圣师狮湿诗蚀识驶势适释饰视寿兽枢输书赎属"
    "树竖帅双谁税顺硕丝饲耸颂讼诵苏诉肃虽岁孙损缩琐锁摊贪瘫滩坛谭谈叹汤烫涛腾题体条贴铁厅听铜统"
    "头图团颓驮驼洼袜弯湾顽万韦违围伟伪纬谓卫闻纹稳蜗涡窝呜钨乌诬无芜雾务误锡牺袭习戏细虾辖峡"
    "侠狭厦鲜纤贤衔闲显险现献县馅宪厢镶乡详响项萧晓啸协挟胁谐泻谢锌兴汹锈绣须许绪续轩悬选癣学勋询"
    "寻驯训讯逊压鸦鸭哑亚讶盐严颜阎艳厌砚谚验鸯杨扬阳痒养样摇尧遥窑谣药爷业医颐遗仪蚁艺亿忆义议谊"
    "译异荫阴银饮樱婴鹰缨莹萤营荧蝇颖拥踊咏优忧邮犹诱舆鱼渔娱与屿语狱誉预驭鸳渊辕园员圆缘远愿约"
    "跃粤阅郧陨蕴晕杂载暂赞赃脏凿枣灶责择则泽贼赠轧闸诈斋债毡盏斩辗崭栈战绽张涨帐账胀赵辙贞"
    "针侦诊镇阵挣睁帧郑织职执纸挚掷帜质钟终种肿众轴皱昼骤猪诸烛嘱贮铸驻砖转赚桩庄装妆壮状锥赘坠缀浊"
    "渍综总纵邹组钻"
)
MSG_NOTION_CHARS = (
    "已擋下（自動檢查 L-240）：要寫進 Notion 的內容裡有簡體字或已知的轉義錯字：{why}。\n"
    "這通常是手寫 \\uXXXX 轉義打錯字。請直接寫中文字（不要用轉義碼），改正後再送出；"
    "寫完把頁面抓回來，用 scripts/compare_notion_text.py 跟本機底稿比對。"
)


def collect_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k == "old_str":  # 修正錯字時，舊文字本來就含錯字
                continue
            yield from collect_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from collect_strings(v)


def notion_chars_problem(tool_input):
    found = []
    for s in collect_strings(tool_input):
        for ch in s:
            if ch in SIMPLIFIED_ONLY and ch not in found:
                found.append(ch)
    return "、".join(found) if found else None


MSG_GREP_P = (
    "已擋下（自動檢查 L-046）：Windows 的 Git Bash 的 `grep -P` 在目前語系下會無聲失效（抓到空字串），"
    "比對結果會變成假的「相同」。\n請改用 `grep -E`，或寫成 .py 檔用 Python 的 re。"
)

ENV_FILE = r"""["']?[^\s"'|;&]*\.env(?:\.local|\.production|\.prod)?["']?(?=\s|$|[|;&)])"""
SECRET_PRINT = [
    (re.compile(r"(?:^|[\s;&|(])(?:cat|type|more|less|head|tail|Get-Content|gc)\b[^|;&\n]*?\s" + ENV_FILE, re.IGNORECASE),
     "整份 .env 印出來"),
    (re.compile(r"(?:^|[\s;&|(])docker(?:\.exe)?\s+(?:container\s+)?inspect\b(?![^|;&\n]*(?:\s-f\b|\s--format\b))", re.IGNORECASE),
     "沒帶 --format 的 docker inspect（會印出容器全部環境變數，含金鑰）"),
    # 只認在指令開頭的 printenv／env（`cd env && …`、`python -m venv env` 不算）；docker exec 容器裡跑的也算
    (re.compile(r"(?:^|[;&|(]\s*|\bdocker(?:\.exe)?\s+exec\s+(?:-\S+\s+)*\S+\s+)(?:printenv|env)\s*(?=$|[|;&)\n])",
                re.IGNORECASE | re.MULTILINE),
     "不帶參數的 printenv／env（會印出全部環境變數）"),
]
MSG_SECRET = (
    "已擋下（自動檢查）：{why}。設定檔與環境變數裡有金鑰，印出來就進了對話紀錄"
    "（2026-10-29 子代理用 docker inspect 印出演練環境金鑰）。\n"
    "要確認有哪些設定：只列名稱（例：`grep -o '^[A-Z_]*=' .env`、"
    "`docker inspect X --format '{{{{range .Config.Env}}}}{{{{println .}}}}{{{{end}}}}' | cut -d= -f1`）；"
    "要用某個值：只取單一值放進變數，不要印出來。"
)


def strip_quoted(cmd):
    """引號裡的字串換成空字串（grep 的樣式 "secret\\|env"、Select-String 'ARG|ENV' 不能被當成指令）。"""
    out = []
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c in "\"'":
            seg, closed = read_quoted(cmd, i)
            out.append(c + c)
            i += len(seg) + (2 if closed else 1)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def secret_problem(cmd):
    bare = strip_quoted(cmd)
    for n, (rx, why) in enumerate(SECRET_PRINT):
        # 第一條（印 .env）路徑常加引號，看原字串；其他看去掉引號後的指令
        if rx.search(cmd if n == 0 else bare):
            return why
    return None


# L-033：Bash 工具裡的 ssh／scp 指令（去掉引號內容後找；grep "ssh x"、GIT_SSH_COMMAND="ssh -i k" 不算）
GITBASH_SSH = re.compile(r"""(?:^|[\s;&|(`])((?:[^\s;&|()`"']*[/\\])?(ssh|scp)(?:\.exe)?)(?=\s|$)""", re.IGNORECASE)
MSG_GITBASH_SSH = (
    "已擋下（自動檢查 L-033）：{why}。Git Bash 的 ssh／scp 在 VPN 不穩時會整個卡住（timeout 也殺不掉），"
    "2026-10-29 部署因此卡逾時兩次。\n"
    "請改用 Windows 內建的 `/c/Windows/System32/OpenSSH/ssh.exe`、`/c/Windows/System32/OpenSSH/scp.exe`（同樣讀 ~/.ssh/config 的別名）；"
    "伺服器端的長工作照 L-014：寫成 .sh 上傳、`ssh.exe 別名 'bash /tmp/x.sh; rm -f /tmp/x.sh'`，逾時後先唯讀查伺服器狀態再重試。"
)


# L-033 第二次（2026-10-29、11-11）：指令裡手寫「ssh … nohup … &」在遠端背景啟動，ssh 常等到背景工作做完才回，
# 外面包 timeout 被砍時 Windows ssh.exe 的輸出整段遺失。改用 remote_run.py（啟動、斷線重試、讀 log 都包好了）
# 只看同一行（回放時跨行比對會把 Python 字串裡的 & 也算進去）
REMOTE_BG = re.compile(r"\bssh(?:\.exe)?\b[^\n]*\bnohup\s+[^\n]*?(?<![&>|])&(?![&>])", re.IGNORECASE)
MSG_REMOTE_BG = (
    "已擋下（自動檢查 L-033）：{why}。ssh 常會等遠端背景工作做完才回（2026-10-29、11-11 兩次逾時），"
    "被 timeout 砍掉時 Windows ssh.exe 的輸出會整段遺失，看不出有沒有啟動。\n"
    "請改用 `python -X utf8 -I -u ~/.claude/skills/dev-team/scripts/remote_run.py <主機別名> <主機工作資料夾> <log 檔名> <結束字樣> \"<指令>\" [要上傳的本機檔 ...]`"
    "（上傳、背景啟動、斷線重試讀 log 到出現結束字樣都包好了）。"
)


def remote_bg_problem(cmd):
    if "remote_run.py" in cmd:
        return None
    return "手寫 ssh＋nohup＋& 在遠端背景啟動" if REMOTE_BG.search(cmd) else None


# L-162 第二次（2026-11-06 設定檔、11-12 `docker run -e APP_BASE_PATH=/app` 容器起不來）：
# Git Bash 把「斜線開頭的參數值」當成路徑改寫成 C:/Program Files/Git/...。
# 只擋最常見、幾乎不會是檔案路徑的寫法：docker 的 `-e／--env／--build-arg 名稱=/值`（不是 // 開頭）。
DOCKER_SLASH_ENV = re.compile(
    r"\bdocker(?:\.exe)?\b[^\n;|&]*?\s(?:-e|--env|--build-arg)[ =]['\"]?[A-Za-z_][A-Za-z0-9_]*=/(?!/)")
MSG_MSYS_PATH = (
    "已擋下（自動檢查 L-162）：{why}。Git Bash 會把斜線開頭的值改寫成 `C:/Program Files/Git/...`"
    "（2026-11-12 容器因 context-path 變成 Windows 路徑而起不來）。\n"
    "在指令最前面加 `MSYS_NO_PATHCONV=1 `（例：`MSYS_NO_PATHCONV=1 docker run -e APP_BASE_PATH=/app ...`），或改用 PowerShell 跑。"
)


def msys_path_problem(cmd):
    if "MSYS_NO_PATHCONV" in cmd or "MSYS2_ARG_CONV_EXCL" in cmd:
        return None
    m = DOCKER_SLASH_ENV.search(cmd)
    return "docker 環境變數的值是斜線開頭：" + m.group(0).split()[-1] if m else None


# L-223：資料庫映像檔（mariadb／mysql／postgres）宣告 VOLUME，`docker rm -f` 只刪容器、資料留在匿名磁碟區。
# 測試庫的資料不該留著，曾經留下沒發現、隔天又一次。容器名稱看得出是資料庫才擋
DOCKER_RM = re.compile(r"\bdocker(?:\.exe)?\s+(?:container\s+)?rm\b([^\n;|&]*)")
DB_NAME = re.compile(r"(?i)(?:^|[-_.])(?:db|mariadb|mysql|postgres|pg|sql)(?:$|[-_.\d])|(?:mariadb|mysql|postgres)")
MSG_DOCKER_RM_DB = (
    "已擋下（自動檢查 L-223）：{why}。資料庫映像檔把資料放在匿名磁碟區，只刪容器的話資料還在；"
    "測試庫的資料會一直留著，曾經這樣留下沒發現。\n"
    "請改成 `docker rm -fv <容器>`（-v 連匿名磁碟區一起刪）；確定要保留資料就先 `docker volume ls` 記下磁碟區名稱再說明理由。"
)


def docker_rm_db_problem(cmd):
    # 引號裡的是字串資料（例：PowerShell .Replace('docker rm -f x-db', ...) 改測試檔），不是要執行的指令
    m = DOCKER_RM.search(strip_quoted(cmd))
    if not m:
        return None
    args = m.group(1).split()
    flags = [a for a in args if a.startswith("-")]
    if any(a == "--volumes" or (not a.startswith("--") and "v" in a[1:]) for a in flags):
        return None
    names = [a.strip("\"'") for a in args if not a.startswith("-") and not a.startswith(">") and not a.startswith("2>")]
    dbs = [n for n in names if DB_NAME.search(n)]
    return "刪資料庫容器沒帶 -v：" + ", ".join(dbs) if dbs else None


HEREDOC_START = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
SHELL_HEREDOC = re.compile(r"(?:^|[\s;&|(])(?:bash|sh|zsh)(?:\s+-\w+)*\s*<<")


def strip_heredoc_bodies(cmd):
    """heredoc 內文是資料（寫文件、寫檔），不是本機要跑的指令；餵給 bash／sh 的才算指令，保留。"""
    out, lines, i = [], cmd.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC_START.search(line)
        i += 1
        if m and not SHELL_HEREDOC.search(line):
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
    return "\n".join(out)


# L-080 第三次：使用者給了新機器的 IP＋port＋帳號，沒讀部署說明文件就自己先 ssh 試、再手寫佈公鑰指令
#（pipe 公鑰給 ssh、登入後多步驟），規則寫在文件和踩坑表都沒擋住 → 指令當下擋。
# 判斷：ssh／scp 指令裡出現「帳號@IPv4」而這個 IP 不在 ~/.ssh/config 的 HostName／Host 裡＝還沒建過的新機器。
SSH_USER_IP = re.compile(r"[\w.\-]+@(\d{1,3}(?:\.\d{1,3}){3})\b")
MSG_NEW_HOST = (
    "已擋下（自動檢查 L-080）：{why}。新機器先不要自己 ssh 試，也不要手寫佈公鑰指令"
    "（pipe 公鑰給 Windows 的 ssh 會被當密碼吃掉、authorized_keys 變 0 bytes）。\n"
    "請先讀本地規則指定的部署說明文件裡「新機器佈公鑰」那節，"
    "用 `python -X utf8 -I ~/.claude/skills/dev-team/scripts/pubkey_cmd.py <IP> <PORT> <帳號>` 產生單行指令給使用者在自己的 PowerShell 跑；"
    "印 DONE 後先在 ~/.ssh/config 加別名（註明尚未驗證），再用別名＋BatchMode=yes 驗證。"
)


def ssh_config_hosts():
    path = os.environ.get("DEV_TEAM_SSH_CONFIG") or os.path.join(os.path.expanduser("~"), ".ssh", "config")
    hosts = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() in ("hostname", "host"):
                hosts.update(parts[1:])
    return hosts


# L-014 再犯（2026-11-19）：Git Bash 裡 `ssh.exe 別名 'bash -s' < 本機腳本`，Windows 的 ssh 讀 Git Bash 轉進來的
# stdin 會卡住（3 分鐘沒動靜、遠端根本沒執行）。L-014 早就規定「scp 上傳 → ssh 'bash /tmp/x.sh'」，仍再犯 → 指令當下擋。
SSH_STDIN = re.compile(r"(?:^|[\s;&|(`])(?:[^\s;&|()`\"']*[/\\])?ssh(?:\.exe)?\s[^|;&\n]*?(?<![<>0-9&])<(?![<(&])\s*\S", re.IGNORECASE)
MSG_SSH_STDIN = (
    "已擋下（自動檢查 L-014）：{why}。Windows 的 ssh 從 Git Bash 讀 stdin 會卡住、遠端沒執行（2026-11-19 卡 3 分鐘）。\n"
    "改成：Write 寫 LF 的 .sh → `scp.exe 檔 別名:/tmp/` → `ssh.exe 別名 'bash /tmp/x.sh; rm -f /tmp/x.sh'`，"
    "或用 `python -X utf8 -I -u ~/.claude/skills/dev-team/scripts/remote_run.py`。"
)


def ssh_stdin_problem(cmd):
    plain = strip_quoted(strip_heredoc_bodies(cmd))
    if SSH_STDIN.search(plain):
        return "ssh 指令用 < 把本機檔案餵給遠端"
    return None


def new_host_problem(cmd):
    plain = strip_quoted(strip_heredoc_bodies(cmd))
    if not GITBASH_SSH.search(plain):
        return None
    ips = SSH_USER_IP.findall(plain)
    if not ips:
        return None
    try:
        known = ssh_config_hosts()
    except OSError:
        return None
    for ip in ips:
        if ip not in known:
            return "ssh／scp 連 " + ip + "，這台不在 ~/.ssh/config（新機器）"
    return None


def git_bash_ssh_problem(cmd):
    for m in GITBASH_SSH.finditer(strip_quoted(strip_heredoc_bodies(cmd))):
        if "windows/system32/openssh/" in m.group(1).lower().replace("\\", "/"):
            continue
        return "Bash 裡用了 Git Bash 的 " + m.group(2).lower()
    return None


# L-047：Write 寫 .py 時,用 Playwright 開 Chromium 卻沒指定 channel／executable_path,而這台沒裝 Playwright 自帶的瀏覽器;
# 或在預覽版 Python 用同步 API(會直接當掉)。只在真的會失敗的環境擋,裝了瀏覽器、正式版 Python 就不擋
MSG_PLAYWRIGHT = (
    "已擋下（自動檢查 L-047）：{why}。"
    "改用 async API,啟動寫 `p.chromium.launch(channel='msedge', args=['--no-proxy-server', '--disable-gpu'])`（用本機已裝的 Edge）。"
)
LAUNCH = re.compile(r"chromium\s*\.\s*(launch|launch_persistent_context)\s*\(")


def playwright_browsers_missing():
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
    return not os.path.isdir(base)


def playwright_problem(content):
    if not content or "playwright" not in content:
        return None
    if "playwright.sync_api" in content and sys.version_info.releaselevel != "final":
        return "這台的 Python 是預覽版（{}），Playwright 同步 API 會直接當掉".format(sys.version.split()[0])
    if playwright_browsers_missing():
        for m in LAUNCH.finditer(content):
            args = content[m.end():m.end() + 400].split(")")[0]
            if "channel" not in args and "executable_path" not in args:
                return "Playwright 開瀏覽器沒有指定 channel,這台沒有裝 Playwright 自帶的瀏覽器,一啟動就失敗"
    return None


# L-122：呼叫目前目錄的 mvnw.cmd 沒加 `.\`／`./`：cmd（設了 NoDefaultCurrentDirectoryInExePath）、PowerShell、Git Bash
# 都不會從目前目錄找，直接「找不到指令」；包在腳本裡還會被當成測試失敗（2026-10-16、2026-11-04 兩次）
MSG_MVNW = (
    "已擋下（自動檢查 L-122）：{why}。cmd／PowerShell／Git Bash 都不會從目前目錄找執行檔，會直接「找不到指令」。"
    "改寫成 `.\\mvnw.cmd ...`（PowerShell 用 `& .\\mvnw.cmd ...`；Git Bash 呼叫 Windows 的 maven 建議整段改用 PowerShell）。"
)
# 不含 `|`：grep 的正規式 `a|mvnw.cmd` 會誤擋（回放 33,911 筆指令只有這一筆誤擋），管線接 mvnw 實務上不會出現
BARE_MVNW = re.compile(r"""(?:^|[;&(\n]|\bcmd(?:\.exe)?\s+/{1,2}[cCkK]\s+|["'])[ \t]*mvnw\.cmd\b""", re.IGNORECASE)
SCRIPT_EXT = (".sh", ".cmd", ".bat", ".ps1")


def mvnw_problem(text):
    return "呼叫 mvnw.cmd 沒有加 .\\（目前目錄）" if text and BARE_MVNW.search(text) else None


# L-143：PowerShell 變數不分大小寫，`$G=路徑` 之後再寫 `$g=內容` 會把路徑蓋掉，WriteAllText 報「路徑有不合法字元」
#（2026-11-05 同一個 session 連犯兩次）。只看賦值（`$x =`），兩個名稱只差大小寫就擋
MSG_PS_CASE = (
    "已擋下（自動檢查 L-143）：{why}。PowerShell 變數名稱不分大小寫，兩個其實是同一個變數，後面的賦值會蓋掉前面的。"
    "改用不同的名稱（例：$path／$text）。"
)
PS_ASSIGN = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)")


MSG_PS1_NON_ASCII = (
    "已擋下（自動檢查 L-134）：{why}。Write 工具存的是沒有 BOM 的 UTF-8，Windows PowerShell 5.1 會用 ANSI 讀，"
    "中文變亂碼、引號被吃，整支腳本解析失敗。\n"
    "請把 .ps1 改成只用 ASCII（標籤、訊息用英文），或改寫成 Python（python -I -X utf8 執行）；"
    "一定要中文就用 [IO.File]::WriteAllText(路徑, 內容, (New-Object Text.UTF8Encoding $true)) 存成有 BOM 的檔。"
)


MSG_JDK_PATH = (
    "已擋下（自動檢查 L-073）：{why}。Windows 上 JDK 8 的 javap／javac 讀不了中文路徑，會報 class not found、輸出空的；"
    "比對腳本兩邊都空就被當成「一樣」（2026-10-28 兩次、2026-11-06 第三次）。\n"
    "請在腳本裡先把檔案複製到英文暫存路徑（tempfile.mkdtemp()／%TEMP%）再呼叫，並在工具輸出是空的或結束碼不是 0 時直接停；"
    "寫好後用一組「已知不同」的對照組自測。"
)
JDK_TOOL = re.compile(r"\bjava[pc](?:\.exe)?\b")
JDK_SAFE = re.compile(r"tempfile|mkdtemp|gettempdir|%TEMP%|\$env:TEMP|\bTEMP\b|/tmp/|ascii", re.IGNORECASE)


def jdk_path_problem(content):
    code = "\n".join(l for l in content.splitlines() if not l.lstrip().startswith(("#", "//", "REM ", "rem ")))
    if JDK_TOOL.search(code) and not JDK_SAFE.search(code):
        return "寫入的腳本呼叫 javap／javac，卻沒有先把檔案複製到英文暫存路徑"
    return None


def ps1_non_ascii_problem(content):
    if not content or content.startswith("﻿"):
        return None
    for n, line in enumerate(content.splitlines(), 1):
        bad = next((ch for ch in line if ord(ch) > 127), None)
        if bad:
            return f"寫入的 .ps1 第 {n} 行有非 ASCII 字「{bad}」"
    return None


def ps_case_problem(cmd):
    seen = {}
    for name in PS_ASSIGN.findall(strip_quoted(cmd)):
        other = seen.setdefault(name.lower(), name)
        if other != name:
            return f"同一段指令裡同時賦值 ${other} 和 ${name}"
    return None


MSG_CRLF_SED = (
    "已擋下（自動檢查 L-070）：{why} 是 CRLF 換行，Git Bash 的 `sed -i` 會讓新加的行變 LF、有時整檔的 CR 被拿掉。\n"
    "請用 Write 寫一支 .py（放 scratchpad），以 bytes 讀檔、`assert data.count(old)==1` 後取代，換行一律用 b\"\\r\\n\"，"
    "改完印 CRLF 行數確認跟總行數一樣。"
)


def crlf_targets(cmd, cwd):
    """跟 tool_hints 共用同一個判斷：sed -i 指令裡提到的既有檔案含 CRLF → 回傳檔名。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from tool_hints import crlf_sed_targets
        return crlf_sed_targets(cmd, cwd)
    except Exception:
        return []


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    sys.stderr.reconfigure(encoding="utf-8")

    if "notion" in tool.lower() and ("update-page" in tool or "create-pages" in tool):
        why = notion_chars_problem(ti)
        if why:
            print(MSG_NOTION_CHARS.format(why=why), file=sys.stderr)
            return 2
    elif tool == "Edit":
        for field in ("old_string", "new_string"):
            if ends_with_blank(ti.get(field)):
                print(MSG_EDIT.format(field=field), file=sys.stderr)
                return 2
    elif tool in ("Bash", "PowerShell"):
        hit = check_command(tool, ti.get("command") or "")
        if hit:
            print(hit[2].format(why=hit[1]), file=sys.stderr)
            return 2
        # L-070 再犯：提醒放在 tool_hints 時指令照跑，CRLF 檔被 Git Bash 的 sed -i 改成 LF（新加的行 LF、修補時整檔 CR 被拿掉）
        if tool == "Bash" and IS_WINDOWS:
            files = crlf_targets(ti.get("command") or "", data.get("cwd"))
            if files:
                print(MSG_CRLF_SED.format(why="、".join(files)), file=sys.stderr)
                return 2
    elif tool == "Write" and str(ti.get("file_path", "")).lower().endswith(".py"):
        why = playwright_problem(ti.get("content") or "")
        if why:
            print(MSG_PLAYWRIGHT.format(why=why), file=sys.stderr)
            return 2
        why = jdk_path_problem(ti.get("content") or "") if IS_WINDOWS else None
        if why:
            print(MSG_JDK_PATH.format(why=why), file=sys.stderr)
            return 2
    elif tool == "Write" and str(ti.get("file_path", "")).lower().endswith(SCRIPT_EXT) and IS_WINDOWS:
        why = mvnw_problem(ti.get("content") or "")
        if why:
            print(MSG_MVNW.format(why=why), file=sys.stderr)
            return 2
        why = jdk_path_problem(ti.get("content") or "")
        if why:
            print(MSG_JDK_PATH.format(why=why), file=sys.stderr)
            return 2
        # L-134 再犯（2026-11-05）：Write 工具存的是沒有 BOM 的 UTF-8；.ps1 裡有非 ASCII 字，
        # Windows PowerShell 5.1 用 ANSI 讀，中文變亂碼、引號被吃，整支腳本解析失敗
        if str(ti.get("file_path", "")).lower().endswith(".ps1"):
            why = ps1_non_ascii_problem(ti.get("content") or "")
            if why:
                print(MSG_PS1_NON_ASCII.format(why=why), file=sys.stderr)
                return 2
        # L-046 再犯（2026-11-05）：寫進 .sh 腳本的 `grep -P` 不會經過指令檢查，在 Git Bash 報錯，
        # 防呆 `grep -P ... && stop` 因此失效。註解行不算。
        if str(ti.get("file_path", "")).lower().endswith(".sh"):
            code = "\n".join(l for l in (ti.get("content") or "").splitlines() if not l.lstrip().startswith("#"))
            if GREP_P.search(code):
                print(MSG_GREP_P, file=sys.stderr)
                return 2
    return 0


def check_command(tool, cmd):
    """回傳 (規則代號, 原因, 訊息範本) 或 None。回放工具也呼叫這裡，規則只有一份。"""
    checks = [
        ("python", python_inline_problem(cmd), MSG_PY),
        ("secret", secret_problem(cmd), MSG_SECRET),
        ("remote-bg", remote_bg_problem(cmd), MSG_REMOTE_BG),
        ("docker-rm-db", docker_rm_db_problem(cmd), MSG_DOCKER_RM_DB),
        ("new-host", new_host_problem(cmd), MSG_NEW_HOST),
    ]
    if IS_WINDOWS:
        checks.append(("mvnw", mvnw_problem(cmd), MSG_MVNW))
    if tool == "PowerShell":
        # L-014 只在 PowerShell 擋：出事的是 PowerShell 5.1 吃掉雙引號；Git Bash 的單引號會原樣保留
        #（回放 30 個 session：Bash 裡這類 ssh 指令 900 多次都正常）
        checks.append(("ssh", ssh_problem(cmd, tool), MSG_SSH))
        checks.append(("bom", bom_problem(cmd), MSG_BOM))
        checks.append(("ps-case", ps_case_problem(cmd), MSG_PS_CASE))
    elif IS_WINDOWS:
        # 這兩條是 Windows 上 Git Bash 的坑；macOS／Linux 的 bash、grep、ssh 都正常，不擋
        checks.append(("grep-P", "grep -P" if GREP_P.search(strip_quoted(cmd)) else None, MSG_GREP_P))
        # L-033 只在 Bash 擋：PowerShell 叫到的 ssh 本來就是 Windows 內建的
        checks.append(("gitbash-ssh", git_bash_ssh_problem(cmd), MSG_GITBASH_SSH))
        checks.append(("ssh-stdin", ssh_stdin_problem(cmd), MSG_SSH_STDIN))
        # L-162 只在 Windows 的 Git Bash：PowerShell 不會改寫斜線開頭的參數
        checks.append(("msys-path", msys_path_problem(cmd), MSG_MSYS_PATH))
    for rule, why, msg in checks:
        if why:
            return rule, why, msg
    return None


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
