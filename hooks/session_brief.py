"""SessionStart hook：開工自動帶入上次留下的經驗。

帶這幾件事進對話（都從本地資料夾讀，見 references/shareable.md）：
1. `<本地>/retro-log.md`〈回顧紀錄〉最近幾列還標 ⏳ 的改進
2. `<本地>/skill-changelog.md` 成效還是 ⏳ 的技能改動（碰到同類問題要填有效／沒效）
3. 技能 lessons-*.md 與 `<本地>/lessons-local.md` 裡再犯 >= 2、還不是機制的列
4. 這個工作目錄對到的專案紀錄裡標 ⏳ 的待辦（要 `<本地>/config.json` 設 project_index，沒設就略過）
5. 技能裡有沒有個人／公司資料（scripts/check_shareable.py）
6. 對到的專案紀錄有〈交接單〉就整段帶入（上一個工作階段留給接手的人；格式見 references/handoff.md），放在最前面

`<本地>`：環境變數 DEV_TEAM_LOCAL，沒設就是 ~/.claude/dev-team-local。
只讀不寫；任何錯誤都安靜放行（exit 0），不能擋住開工。
"""
import json
import os
import re
import subprocess
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(SKILL, "references")
LOCAL = os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "dev-team-local")

RETRO_ROWS = 8      # 看最近幾列回顧
MAX_ITEMS = 8       # 每一類最多列幾項
CUT = 90            # 每項最多幾個字
HANDOFF_MAX = 1500  # 交接單最多帶幾個字進對話
RECORD_WARN = 6000  # 專案紀錄超過幾個字就提醒整理（只放現況，舊的搬到歷史檔）


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def config():
    path = os.path.join(LOCAL, "config.json")
    return json.loads(read(path)) if os.path.exists(path) else {}


def short(text, n=CUT):
    text = re.sub(r"\*\*|`", "", text).strip(" ；;，,。")
    return text if len(text) <= n else text[: n - 1] + "…"


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def section(text, title_re):
    """回傳某個 ## 段落的內容（到下一個同級標題為止）。"""
    m = re.search(r"^## " + title_re + r".*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[: n.start()] if n else rest


def retro_open_items():
    path = os.path.join(LOCAL, "retro-log.md")
    if not os.path.exists(path):
        return []
    rows = [l for l in section(read(path), "回顧紀錄").splitlines()
            if re.match(r"^\| \d{4}-\d{2}-\d{2} ", l)][:RETRO_ROWS]
    out = []
    for row in rows:
        c = cells(row)
        date, proj = c[0], short(c[1], 18)
        for cell in c[4:]:
            for frag in re.findall(r"⏳\s*([^；|✅⏳]+)", cell):
                out.append(f"{date[5:]} {proj}：{short(frag, 70)}")
    return out


def changes_pending():
    """skill-changelog.md 成效還是 ⏳ 的改動：這次工作碰到它要解決的問題，就要填有效／沒效。"""
    path = os.path.join(LOCAL, "skill-changelog.md")
    if not os.path.exists(path):
        return []
    out = []
    for line in section(read(path), "改版紀錄").splitlines():
        if not re.match(r"^\| \d{4}-\d{2}-\d{2} ", line):
            continue
        c = cells(line)
        if len(c) >= 5 and "⏳" in c[4]:
            out.append(f"{c[0][5:]} 問題：{short(c[2], 45)} → 看：{short(c[3], 45)}")
    return out


def lessons_unmechanized():
    out = []
    paths = [os.path.join(REF, n) for n in ("lessons-workflow.md", "lessons-tech.md")]
    paths.append(os.path.join(LOCAL, "lessons-local.md"))
    for path in paths:
        if not os.path.exists(path):
            continue
        for line in read(path).splitlines():
            if not re.match(r"^\| [LP]-\d", line):
                continue
            c = cells(line)
            if len(c) < 5 or not c[-1].isdigit() or int(c[-1]) < 2:
                continue
            todo = c[3]
            if "⏳" in todo or not re.search(r"機制|hook|Test|測試|腳本", todo):
                out.append(f"{c[0]}（再犯 {c[-1]}）{short(c[1], 60)}")
    return out


def project_records(cwd, cfg):
    """用工作目錄對到專案紀錄：目錄在紀錄的資料夾裡，或 repo 名稱出現在紀錄的「基本資料」。"""
    index = cfg.get("project_index")
    if not index or not os.path.exists(index):
        return None
    work = cfg.get("work_root") or os.path.dirname(index)
    links = re.findall(r"\]\(([^)]*\.md)\)", read(index))
    cwd_n = os.path.normcase(os.path.abspath(cwd)) if cwd else ""
    # 只有在程式碼根目錄或文件根目錄底下才用名稱比對，避免「Desktop」這種字到處對到
    name = ""
    code = os.path.normcase(cfg.get("code_root") or "\0") + os.sep
    work_n = os.path.normcase(work) + os.sep
    if cwd_n.startswith(code):
        name = cwd_n[len(code):].split(os.sep)[0]
    elif cwd_n.startswith(work_n):
        name = os.path.basename(cwd_n)
    pat = re.compile(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", re.I) if name else None
    inside, by_code, by_basic = [], [], []
    for rel in links:
        path = os.path.join(work, rel.replace("/", os.sep))
        if not os.path.exists(path):
            continue
        folder = os.path.normcase(os.path.dirname(path))
        if cwd_n == folder or cwd_n.startswith(folder + os.sep):
            inside.append(path)
            continue
        if not pat:
            continue
        basic = section(read(path), "基本資料")
        code_row = "\n".join(l for l in basic.splitlines() if l.startswith("| 程式碼"))
        if pat.search(code_row):
            by_code.append(path)
        elif pat.search(basic):
            by_basic.append(path)
    # 優先順序：目錄就在紀錄資料夾裡 > 「程式碼」那列寫的 repo > 基本資料其他地方提到
    return (inside or by_code or by_basic)[:2]


def project_todos(path):
    text = read(path)
    out = []
    for title in ("待辦", "資安檢測"):
        for line in section(text, title).splitlines():
            m = re.match(r"^\s*[-*]\s*⏳\s*(.+)", line)
            if m:
                out.append(short(m.group(1)))
    return out


def project_handoff(path):
    """專案紀錄的〈交接單〉（references/handoff.md）：有內容就整段回傳（最多 HANDOFF_MAX 字），
    沒有這一段、只有範本的空欄位、或每項都寫「無」就回空字串。"""
    body = section(read(path), "交接單").strip()
    filled = 0
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith(">"):
            continue
        value = re.sub(r"^\s*[-*]?\s*(\*\*[^*]*\*\*)?[：:\s]*", "", line).strip(" 。")
        if value and not re.match(r"^(<[^>]*>|[（(]?無[）)]?|無（.*）|N/?A|none|-+|—+)$", value, re.I):
            filled += 1
    if not filled:
        return ""
    return body if len(body) <= HANDOFF_MAX else body[:HANDOFF_MAX] + "…（太長，其餘看專案紀錄）"


def shareable_hits():
    r = subprocess.run([sys.executable, "-I", os.path.join(SKILL, "scripts", "check_shareable.py"), "--quiet"],
                       capture_output=True, timeout=8)
    return r.returncode, r.stdout.decode("utf-8", "replace").strip().splitlines()[-1:]


def block(title, items, more_hint):
    if not items:
        return [f"### {title}：無"]
    lines = [f"### {title}（{len(items)} 項）"]
    lines += [f"- {i}" for i in items[:MAX_ITEMS]]
    if len(items) > MAX_ITEMS:
        lines.append(f"- …另有 {len(items) - MAX_ITEMS} 項，{more_hint}")
    return lines


def sync_stale(cfg, now=None):
    """跨裝置同步（本地設定 sync_state_file，JSON 裡的 last_push 是上次成功推送的時間）超過
    sync_stale_hours（預設 24）沒成功推送就回傳一句說明；沒設定或正常就回傳空字串。
    sync_log_file 有設定時，附上最後一次執行記錄裡「不同步／失敗」那一行。"""
    import time
    path = cfg.get("sync_state_file")
    if not path or not os.path.exists(os.path.expanduser(path)):
        return ""
    st = json.loads(read(os.path.expanduser(path)))
    last = float(st.get("last_push") or 0)
    hours = float(cfg.get("sync_stale_hours") or 24)
    age = ((now or time.time()) - last) / 3600
    if age < hours:
        return ""
    msg = "上次成功推送是 %d 小時前" % age if last else "從沒成功推送過"
    log = cfg.get("sync_log_file")
    if log and os.path.exists(os.path.expanduser(log)):
        bad = [l.strip() for l in read(os.path.expanduser(log)).splitlines() if re.search(r"不同步|失敗|錯誤|error", l, re.I)]
        if bad:
            msg += "；最後的記錄：" + short(bad[-1], 120)
    return msg


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except Exception:
        data = {}
    cwd = data.get("cwd") or os.getcwd()

    parts = ["## 開工提醒（dev-team SessionStart hook 自動帶入：上次留下、還沒做完的經驗）",
             f"跟這次工作有關的先處理或先跟使用者講；無關的不用提。本地資料夾：{LOCAL}"]
    if not os.path.isdir(LOCAL):
        parts.append("### 還沒有本地資料夾：照 references/shareable.md「第一次用」建立（至少 local-rules.md、private-terms.txt）")
    retro, pending, lessons = [], [], []
    records, handoffs = None, 0
    try:
        records = project_records(cwd, config())
        for path in records or []:
            try:
                text = project_handoff(path)
            except Exception:       # 一份讀不到不影響下一份
                text = ""
            if text:
                handoffs += 1
                parts += [f"### 交接單（{os.path.basename(os.path.dirname(path))}；上一個工作階段留給接手的人）",
                          f"這次是接著做這件事的話：先照「下一步的第一個動作」開始，交接單寫明做過、試過的不重做；"
                          f"不夠用（要回頭問使用者、要重讀一批檔）就記下缺哪一項，回顧時填 `接手問 N`、`接手重做 N`。來源：{path}",
                          text]
    except Exception:
        pass
    try:
        retro = retro_open_items()
        parts += block("回顧行動項還沒做完（retro-log.md）", retro, "看 retro-log.md〈回顧紀錄〉")
    except Exception:
        pass
    try:
        pending = changes_pending()
        parts += block("技能改版待驗證成效（skill-changelog.md；這次碰到同類問題就填 ✅ 有效／❌ 沒效）",
                       pending, "看 skill-changelog.md")
    except Exception:
        pass
    try:
        lessons = lessons_unmechanized()
        parts += block("再犯 ≥ 2 但還不是機制（這次碰到就要做成機制）", lessons, "看 lessons-*.md")
    except Exception:
        pass
    todo_count = 0
    try:
        if records == []:
            parts.append("### 專案待辦：這個工作目錄沒對到專案紀錄，有在做專案就先照本地規則找到它")
        for path in records or []:
            todos = project_todos(path)
            todo_count += len(todos)
            parts += block(f"專案待辦 ⏳（{os.path.basename(os.path.dirname(path))}）", todos, f"看 {path}")
            try:
                size = len(read(path))
                if size > RECORD_WARN:
                    parts.append(f"### 這份專案紀錄偏長（{size} 字）：這次有在這個專案做事的話，收尾時把「目前狀況」改寫成現況（不是往下加），"
                                 f"並跑 `python -X utf8 -I scripts/split_record.py \"{path}\" --apply` 把舊的搬到歷史檔")
            except Exception:
                pass
    except Exception:
        pass
    share_note = ""
    try:
        rc, last = shareable_hits()
        if rc == 1 and last:
            share_note = "、技能裡有私人資料"
            parts.append(f"### 技能可分享檢查沒過：{last[0]}。跑 `python -I scripts/check_shareable.py` 看是哪幾行，移到本地（見 shareable.md）")
    except Exception:
        pass
    try:
        stale = sync_stale(config())
        if stale:
            share_note += "、跨裝置同步卡住"
            parts.append("### 跨裝置同步卡住：" + stale + "。先跑設定裡的同步指令看原因、修好再開工，不要等收尾")
    except Exception:
        pass
    parts.append("新增 lessons 列要編號：`python -I ~/.claude/skills/dev-team/scripts/lesson_id.py next`（加鎖取號）。"
                 "通用的寫進技能、個人／公司的寫進本地（references/shareable.md）。")

    if handoffs:
        share_note = "、有交接單" + share_note
    summary = (f"開工提醒：回顧未完成 {len(retro)} 項、技能改版待驗證 {len(pending)} 項、"
               f"再犯未成機制 {len(lessons)} 條、專案待辦 {todo_count} 項{share_note}（已帶入對話）")
    out = {
        "systemMessage": summary,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(parts)},
    }
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
