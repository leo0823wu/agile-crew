"""Stop hook：這一輪改了專案的檔、交付了，專案紀錄卻沒更新，就擋下結束（擋一次）。

什麼時候判斷（只在「交付」那一輪，做到一半問使用者問題時不擋）：
- 這一輪（上一次停下之後）有 git push，或改了 `<本地>/retro-log.md`（回顧＝交付後）。
  設定 triggers 可加 "commit"（commit／merge／cherry-pick／am／revert 也算）；回放比較過，加了會在一連串 commit 時重複提醒。
- 續跑（stop_hook_active：剛被別的 Stop hook 擋下，例如回顧 hook 逼 Claude 補做回顧）：這一段裡**還沒被這支擋過**才判斷，
  擋過一次（紀錄裡有這支的理由）就放行，不會卡死。這樣「被逼補寫的回顧寫了某個專案、紀錄卻沒更新」也擋得到。
  真實紀錄的順序是「Stop hook feedback → stop_hook_summary」，被擋的停點看它**前面**那一筆（2026-11-05 QA 抓到原本寫反）。
- 腳本自己出錯、沒有本地設定一律放行。

「這一輪工作」（round）：從上一次寫回顧的那一段結束之後開始（被 Stop hook 擋下後的續跑算同一段）；
中間閒置超過 idle_split_hours（預設 8 小時）也切開，因為同一個工作階段常常開好幾週。
同一輪裡紀錄更新過一次，後面再 push 就不再擋（一輪最多提醒一次）。round 裡：
- **改了哪些專案**：Edit／Write／MultiEdit／NotebookEdit 的路徑、Bash／PowerShell 的 git 寫入（commit、merge、push…；
  repo 從 `git -C`、cd、或那一筆的工作目錄判斷）、其他寫檔指令（重導向、Set-Content／Out-File 的檔名、Copy-Item／cp 的目的地…，盡力而為）。
  子代理（Agent）改的檔也算。**回顧紀錄新加的那一列寫的專案**也算（例：只回答問題＋補做回顧、沒改程式的一輪）：
  用紀錄資料夾名稱比對（任何位置）、去掉「官網／系統／平台」字尾的簡稱比對開頭、本地設定的別名（record_gate.aliases）；
  一列提到好幾個專案時只認**最先出現的那個**（後面多半是舉例）。改既有列的字（列數沒變多）不算新加。
- **路徑對到哪一份紀錄**（設定在 `<本地>/config.json`，見 references/shareable.md）：
  ① 在某份紀錄的資料夾裡 ② 在紀錄「基本資料」寫到的資料夾裡（只被一份紀錄提到的才算）
  ③ 在程式碼根目錄（code_root、record_gate.extra_code_roots）的某個 repo，repo 名出現在某份紀錄「基本資料」的「程式碼」那列
  （worktree 用 `.git` 檔找主 repo，或用名稱前綴，例：`xxx-wt-hotfix` → `xxx`）；同一個 repo 寫在兩份紀錄，改其中一份就算
  ④ 程式碼根目錄裡對不到任何紀錄的 repo → 要求在專案總表找到或建一份紀錄（record_gate.unmapped_code: "ignore" 可關）。
  不算改檔：`~/.claude/`、AppData（暫存區）、CLAUDE.md、紀錄與總表本身、`.git/`、對不到紀錄的文件資料夾、程式碼根目錄的共用檔。
- **紀錄算更新過**：round 裡有 Edit／Write 或寫檔指令改到那份紀錄，或紀錄檔的修改時間在 round 開始之後（別的方式改的也算）；
  只有回顧列寫了專案（沒改檔，多半是補寫以前工作的回顧）時，紀錄在這個工作階段上一次 push 之後更新過也算。
  對不到紀錄的 repo：round 裡改過專案總表、或新建了紀錄就算。

設定（`<本地>/config.json`，都可省略）：
  "record_gate": {"enabled": true, "triggers": ["retro", "push"], "idle_split_hours": 8, "unmapped_code": "block",
                  "extra_code_roots": [], "ignore": ["路徑前綴", …], "basic_section": "基本資料"}
測試：python -I ~/.claude/skills/agile-crew/hooks/test_record_gate.py
回放：python -I ~/.claude/skills/agile-crew/hooks/replay_record_gate.py 30
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import transcript as T  # noqa: E402

HOME = os.path.expanduser("~")
LOCAL = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(HOME, ".claude", "agile-crew-local")
RETRO = re.compile(r"retro-log\.md", re.IGNORECASE)
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
SHELLS = ("Bash", "PowerShell")
GIT_CHANGE = {"commit", "merge", "cherry-pick", "am", "apply", "revert", "rebase", "push"}
GIT_DELIVER = {"commit", "push", "merge", "cherry-pick", "am", "revert"}
CD = {"cd", "set-location", "sl", "pushd", "push-location", "chdir"}
COPY = {"cp", "mv", "copy-item", "move-item", "copy", "move", "xcopy", "robocopy", "scp", "rsync", "cpi", "mi"}
WRITE = {"set-content", "add-content", "out-file", "new-item", "ni", "remove-item", "ri", "rm", "rmdir", "del",
         "rename-item", "ren", "clear-content", "mkdir", "md", "touch", "tee", "tee-object", "expand-archive",
         "compress-archive", "unzip"}
PATH_FLAGS = {"-path", "-literalpath", "-filepath", "-destination", "-destinationpath", "-outfile"}
ONE_TARGET = {"set-content", "add-content", "out-file", "new-item", "ni", "clear-content", "tee-object"}
VALUE_FLAGS = {"-value", "-encoding", "-itemtype", "-erroraction", "-ea", "-name", "-newname", "-filter", "-include",
               "-exclude", "-delimiter", "-width", "-inputobject"}   # 這些參數後面接的是值，不是路徑
NULLS = {"/dev/null", "$null", "nul"}
TOUCH_HINT = re.compile(r"(?i)\b(python|py|node|WriteAllText|WriteAllLines|AppendAllText|Set-Content|Add-Content|"
                        r"Out-File|sed|perl|tee|cp|copy-item|move-item)\b|>")
# Windows：路徑一律正規化成小寫、反斜線（C:/x、/c/x 都認）；macOS／Linux：斜線分隔，macOS 磁碟預設不分大小寫所以也轉小寫；
# Windows 寫法的路徑（從 Windows 同步來的紀錄）只用來認 repo 名（2026-11-24 Mac 上一律對不到紀錄、永遠不擋）
IS_WIN = os.name == "nt"
FOLD_CASE = IS_WIN or sys.platform == "darwin"
SEP = "\\" if IS_WIN else "/"
WIN_ABS = re.compile(r"^[a-zA-Z]:[\\/]")
ABS = re.compile(r"^([a-zA-Z]:[\\/]|~[\\/]|/[a-zA-Z]/)") if IS_WIN else re.compile(r"^(/|~/)")


# ---------------------------------------------------------------- 設定與路徑

def load_config():
    path = os.path.join(LOCAL, "config.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm(p, cwd=None):
    """各種寫法（C:/x、/c/x、~/x、相對路徑）→ 正規化的絕對路徑（Windows：小寫、反斜線）；判斷不了回空字串。"""
    if not p:
        return ""
    p = p.strip().strip('"').strip("'")
    if not IS_WIN:
        return _norm_posix(p, cwd)
    m = re.match(r"^/([a-zA-Z])(/.*)?$", p)
    if m:
        p = m.group(1) + ":" + (m.group(2) or "/")
    if p.startswith("~"):
        p = HOME + p[1:]
    p = p.replace("$HOME", HOME).replace("$env:USERPROFILE", HOME)
    if p.startswith(("$", "%")) or "$(" in p:
        return ""                           # 變數、指令替換：看不出實際路徑
    if not re.match(r"^[a-zA-Z]:[\\/]", p):
        if not cwd or p.startswith(("/", "\\")):
            return ""                       # Linux 路徑（遠端機器）、或不知道相對於哪裡
        p = os.path.join(cwd, p)
    return os.path.normcase(os.path.normpath(p))


def _norm_posix(p, cwd):
    if p.startswith("~"):
        p = HOME + p[1:]
    p = p.replace("${HOME}", HOME).replace("$HOME", HOME)
    if p.startswith(("$", "%")) or "$(" in p:
        return ""                           # 變數、指令替換：看不出實際路徑
    if WIN_ABS.match(p) or p.startswith("\\"):
        return ""                           # Windows 路徑：不是這台的檔
    if not p.startswith("/"):
        if not cwd:
            return ""
        p = os.path.join(cwd, p)
    p = os.path.normpath(p)
    return p.lower() if FOLD_CASE else p


def under(p, root):
    return bool(root) and (p == root or p.startswith(root.rstrip(SEP) + SEP))


def tool_dirs():
    """不算專案改檔的資料夾：~/.claude、技能的本地資料夾（AGILE_CREW_LOCAL 可能設在別處）、macOS／Linux 的暫存區。
    Windows 的暫存區在 AppData 底下，由 not_project_path 另外排除。record_gate 與 round_time 共用。"""
    dirs = [norm(os.path.join(HOME, ".claude")), norm(LOCAL)]
    if not IS_WIN:
        import tempfile
        dirs += [norm(os.path.realpath(tempfile.gettempdir())), norm(tempfile.gettempdir()),
                 "/tmp", "/private/tmp", "/var/folders", "/private/var/folders"]
    return [d for d in dirs if d]


def not_project_path(p):
    """暫存區、~/.claude、本地資料夾底下的檔（p 要先 norm 過）；空路徑也算。"""
    if not p or (IS_WIN and "\\appdata\\" in p):
        return True
    return any(under(p, d) for d in tool_dirs())


def section(text, title):
    m = re.search(r"^## " + re.escape(title) + r".*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[: n.start()] if n else rest


def worktree_main(d):
    """d 是 git worktree（.git 是檔案）→ 主 repo 資料夾名稱（小寫）；不是就回 None。"""
    g = os.path.join(d, ".git")
    try:
        if os.path.isfile(g):
            with open(g, encoding="utf-8") as f:
                m = re.match(r"gitdir:\s*(.+)", f.read().strip())
            if m:
                parts = re.split(r"[\\/]", m.group(1).strip())
                if ".git" in parts:
                    name = parts[parts.index(".git") - 1]
                    return name.lower() if FOLD_CASE else name
    except OSError:
        pass
    return None


def _prefixes(comp):
    return [comp[: m.start()] for m in reversed(list(re.finditer(r"[-_]", comp)))]


def _squash(text):
    return re.sub(r"\s+", "", text or "").casefold()


ROW = re.compile(r"^\| (\d{4}-\d{2}-\d{2}) \|([^|\n]*)\|", re.M)


def new_retro_rows(old, new):
    """Edit 回顧紀錄時新加的列 → [專案／這輪 那一格]。列數沒變多＝只是改既有列的字，不算新加。"""
    rows_old, rows_new = ROW.findall(old or ""), ROW.findall(new or "")
    if len(rows_new) <= len(rows_old):
        return []
    before = set(rows_old)
    return [cell.strip() for d, cell in rows_new if (d, cell) not in before]


class Projects:
    """專案總表 → 每份紀錄的資料夾、repo 名稱、基本資料提到的資料夾；map(路徑) 判斷屬於哪份紀錄。"""

    def __init__(self, cfg):
        rg = cfg.get("record_gate") or {}
        self.index = norm(cfg.get("project_index") or "")
        self.work = norm(cfg.get("work_root") or "") or (os.path.dirname(self.index) if self.index else "")
        self.code_roots = [norm(r) for r in [cfg.get("code_root")] + list(rg.get("extra_code_roots") or []) if r]
        self.ignore = [norm(x) for x in rg.get("ignore") or []] + tool_dirs()
        self.records = []           # dict(path, folder, rel)
        self.record_names = set()
        self.repo_map = {}          # repo 名（小寫）→ set(紀錄編號)
        self.owned = []             # (資料夾, set(紀錄編號))，長的在前
        self.full_alias, self.short_alias = [], []
        if not self.index or not os.path.exists(self.index):
            return
        basic_title = rg.get("basic_section") or "基本資料"
        with open(self.index, encoding="utf-8") as f:
            links = re.findall(r"\]\(([^)]*\.md)\)", f.read())
        owned = {}
        for rel in links:
            path = norm(os.path.join(self.work, rel.replace("/", os.sep)))
            if not os.path.exists(path) or any(r["path"] == path for r in self.records):
                continue
            i = len(self.records)
            folder = os.path.dirname(path)
            self.records.append({"path": path, "folder": folder, "rel": os.path.relpath(path, self.work)})
            self.record_names.add(os.path.basename(path))
            with open(path, encoding="utf-8") as f:
                basic = section(f.read(), basic_title)
            for line in basic.splitlines():
                is_code = bool(re.match(r"^\|\s*(程式碼|code)", line, re.I))
                for tok in re.findall(r"`([^`\n]+)`", line):
                    self._claim(i, tok, is_code, folder, owned)
        roots = set(self.code_roots) | {self.work, norm(HOME)}
        self.owned = sorted(((d, recs) for d, recs in owned.items() if len(recs) == 1 and d not in roots
                             and not any(under(d, r["folder"]) for r in self.records)),
                            key=lambda x: -len(x[0]))
        # 名稱 → 紀錄（回顧那一列寫的是哪個專案）：資料夾名稱（任何位置）；去掉常見字尾的簡稱（只比開頭）；本地設定的別名
        suffixes = rg.get("alias_strip_suffixes") or ["官網", "系統", "平台"]
        self.full_alias, self.short_alias = [], []
        for i, r in enumerate(self.records):
            name = _squash(os.path.basename(r["folder"]))
            self.full_alias.append((name, i))
            for suf in suffixes:
                if name.endswith(suf) and len(name) - len(suf) >= 2:
                    self.short_alias.append((name[: -len(suf)], i))
        for alias, rel in (rg.get("aliases") or {}).items():
            p = norm(os.path.join(self.work, rel.replace("/", os.sep)))
            for i, r in enumerate(self.records):
                if r["path"] == p:
                    self.full_alias.append((_squash(alias), i))

    def match_name(self, text):
        """回顧列「專案／這輪」那一格 → 對到的紀錄編號 frozenset。一列提到好幾個專案時只認一個（後面多半是舉例）：
        ① 開頭那段（第一個「：」或括號之前）有完整專案名 → 用最先出現的完整名（「某某部門 乙系統 修正」→ 乙系統，
           不是剛好跟部門名稱同字開頭的另一個專案簡稱）
        ② 否則開頭是簡稱 → 用簡稱（「甲 金流（參考丙官網做法）」→ 甲官網）
        ③ 都沒有 → 用整格最先出現的完整名（「批次工具（丙那邊用）」）。被較長名稱包含的不算（「甲」vs「甲CRM」）。"""
        raw = _squash(text)
        stripped = _squash(re.sub(r"[（(][^）)]*[）)]", "", text))
        head = re.split(r"[：:（(]", raw, maxsplit=1)[0]
        full = []
        for a, i in self.full_alias:
            if a in raw:
                full.append((raw.find(a), a, i))
            elif a in stripped:
                full.append((stripped.find(a), a, i))
        short = [(0, a, i) for a, i in self.short_alias if stripped.startswith(a) or raw.startswith(a)]
        allh = full + short
        drop = lambda hs: [(p, a, i) for p, a, i in hs if not any(a != b and a in b for _, b, _ in allh)]  # noqa: E731
        full, short = drop(full), drop(short)
        in_head = [h for h in full if head.find(h[1]) >= 0]
        pick = in_head or short or full
        if not pick:
            return frozenset()
        first = min(p for p, _, _ in pick)
        return frozenset(i for p, _, i in pick if p == first)

    def _claim(self, i, tok, is_code, folder, owned):
        tok = tok.strip().rstrip("\\/")
        if not tok or "://" in tok or tok.startswith(("http", "git@")) or len(tok) > 260:
            return
        if ABS.match(tok):
            cands = [norm(tok)]
        elif not IS_WIN and WIN_ABS.match(tok):
            # 從 Windows 同步來的紀錄（C:\\code\\repo）：用路徑裡的資料夾名對這台的程式碼根目錄
            cands = [norm(os.path.join(r, c)) for r in self.code_roots for c in re.split(r"[\\/]", tok)[1:] if c]
        else:
            cands = [norm(tok, b) for b in (folder, os.path.dirname(folder), self.work, *self.code_roots)]
        for c in cands:
            if not c:
                continue
            for root in self.code_roots:
                if under(c, root) and c != root:
                    name = c[len(root):].strip(SEP).split(SEP)[0]
                    if is_code and os.path.isdir(os.path.join(root, name)):
                        self.repo_map.setdefault(name, set()).add(i)
                        return
                    if os.path.isdir(os.path.join(root, name)):
                        return
            d = c if os.path.isdir(c) else (os.path.dirname(c) if os.path.isfile(c) else "")
            if d:   # 文件資料夾、或放在文件根目錄底下的程式（還沒搬到程式碼根目錄的 repo）
                owned.setdefault(d, set()).add(i)
                return

    def is_record(self, p):
        return any(r["path"] == p for r in self.records)

    def map(self, p, release=False):
        """→ ("rec", frozenset(紀錄編號)) ／ ("code", repo 資料夾) ／ None（不算專案改檔）。
        release＝git push：`~/.claude` 底下的 repo（例：技能）平常改檔不算（回顧時順手改技能很常見），推送出去才算那個專案的工作。"""
        if not p or (IS_WIN and "\\appdata\\" in p):
            return None
        claude = norm(os.path.join(HOME, ".claude"))
        if any(under(p, x) for x in self.ignore if not (release and x == claude)):
            return None
        if release and under(p, claude):
            hits = [recs for d, recs in self.owned if under(p, d)]
            return ("rec", frozenset(hits[0])) if hits else None
        base = p.split(SEP)[-1]
        if base.lower() == "claude.md" or SEP + ".git" + SEP in p + SEP or p == self.index or base in self.record_names:
            return None
        best = None
        for i, r in enumerate(self.records):
            if under(p, r["folder"]) and (best is None or len(r["folder"]) > len(self.records[best]["folder"])):
                best = i
        if best is not None:
            return ("rec", frozenset([best]))
        for d, recs in self.owned:
            if under(p, d):
                return ("rec", frozenset(recs))
        for root in self.code_roots:
            if under(p, root) and p != root:
                rel = p[len(root):].strip(SEP).split(SEP)
                comp = rel[0]
                if comp.startswith(".") or (len(rel) == 1 and not os.path.isdir(p)):
                    return None          # 根目錄的共用檔（部署總表、CLAUDE.md…）、.metadata
                for name in [comp, worktree_main(os.path.join(root, comp))] + _prefixes(comp):
                    if name and name in self.repo_map:
                        return ("rec", frozenset(self.repo_map[name]))
                return ("code", os.path.join(root, comp))
        return None


# ---------------------------------------------------------------- 指令分析

def strip_heredocs(cmd):
    """heredoc、PowerShell here-string 的內容是資料不是指令（例：寫一支含 git push 的腳本），先拿掉。"""
    cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?(.*?)\n.*?^\s*\1\s*$", r"\2", cmd, flags=re.S | re.M)
    cmd = re.sub(r"@'\s*\n.*?^'@", "''", cmd, flags=re.S | re.M)
    return re.sub(r'@"\s*\n.*?^"@', "''", cmd, flags=re.S | re.M)


def split_statements(cmd):
    """依換行、;、|、&&、|| 切成一段一段（引號裡的不切）。"""
    out, cur, q, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur.append(ch)
        elif ch in "\n;|" or cmd.startswith("&&", i):
            out.append("".join(cur))
            cur = []
            if cmd.startswith(("&&", "||"), i):
                i += 1
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def tokens_of(stmt):
    toks = re.findall(r'"[^"]*"|\'[^\']*\'|[^\s"\']+', stmt)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in toks]


def _expand(tok, env):
    """把指令裡自己設過的變數（S="..."、$f = '...'）換成值；還有沒設過的變數就保留 $，norm 會當成看不出路徑。"""
    if "$" not in tok:
        return tok
    return re.sub(r"\$\{?(?:env:)?(\w+)\}?", lambda m: env.get(m.group(1).lower(), m.group(0)), tok)


def shell_effects(cmd, cwd):
    """→ (git 操作 [(op, 資料夾)], 寫到的路徑 [正規化路徑], 提到的絕對路徑 [正規化路徑])。
    另外放 python_args：python／node 執行時帶的參數（判斷「用腳本改了回顧紀錄」用）。"""
    git_ops, writes, mentioned = [], [], []
    shell_effects.python_args = []
    cur = norm(cwd) if cwd else None      # 跟其他路徑一樣正規化，不然沒有 cd／-C 的 git 指令對不到 repo（QA 抓到）
    env = {}
    for stmt in split_statements(strip_heredocs(cmd or "")):
        m = re.match(r"^(?:export\s+)?\$?([A-Za-z_]\w*)\s*=\s*(.+)$", stmt)
        if m and not stmt.lower().startswith(("git", "cd ")):
            val = tokens_of(m.group(2))
            # 值是指令結果（PowerShell 的 Join-Path、Get-Item…，或 $(…)、`…`）時看不出路徑，不記，
            # 後面用到這個變數就保留 $，當成看不出路徑（不然 "$x\y" 會被當成工作目錄底下的 Join-Path\y）
            if val and (re.match(r"^[A-Za-z]+-[A-Za-z]+$", val[0]) or val[0].startswith(("$(", "`", "("))):
                env.pop(m.group(1).lower(), None)
                continue
            env[m.group(1).lower()] = _expand(val[0], env) if val else ""
            continue
        toks = [_expand(t, env) for t in tokens_of(stmt)]
        while toks and (toks[0] in ("&", ".", "sudo", "time", "timeout", "command") or re.fullmatch(r"\d+", toks[0])):
            toks = toks[1:]
        if not toks:
            continue
        head = os.path.basename(toks[0].replace("\\", "/")).lower()
        for j, t in enumerate(toks):
            m = re.match(r"^(\d*|&)(>>?)(.*)$", t)
            if not m:
                continue
            fd, _, rest = m.groups()
            if fd not in ("", "1") or rest.startswith("&"):
                continue                      # 2> 錯誤輸出、>&1
            target = rest or (toks[j + 1] if j + 1 < len(toks) else "")
            if target and target.lower() not in NULLS:
                writes.append(norm(target, cur))
        mentioned += [norm(t) for t in toks[1:] if ABS.match(t)]
        if head in CD and len(toks) > 1:
            arg = toks[2] if toks[1].lower() in ("-path", "-literalpath") and len(toks) > 2 else toks[1]
            cur = norm(arg, cur) or None        # 看不出切到哪裡 → 之後的相對路徑都不算
            continue
        if head in ("git", "git.exe"):
            d, k = cur, 1
            while k < len(toks) and toks[k].startswith("-"):
                if toks[k] in ("-C", "-c") and k + 1 < len(toks):
                    if toks[k] == "-C":
                        d = norm(toks[k + 1], cur)
                    k += 2
                else:
                    k += 1
            if k < len(toks) and toks[k] in GIT_CHANGE:
                git_ops.append((toks[k], d))
            continue
        if head in COPY:
            dest = None
            for j, t in enumerate(toks):
                if t.lower() in ("-destination", "-dest") and j + 1 < len(toks):
                    dest = toks[j + 1]
            plain = [t for t in toks[1:] if not t.startswith("-")]
            dest = dest or (plain[-1] if len(plain) >= 2 else None)
            if dest and not re.match(r"^[^\\/:]{2,}:", dest):     # host:/path 是遠端
                writes.append(norm(dest, cur))
        elif head in WRITE:
            flagged = [toks[j + 1] for j, t in enumerate(toks[:-1]) if t.lower() in PATH_FLAGS]
            plain = [t for j, t in enumerate(toks[1:], 1)
                     if not t.startswith("-") and toks[j - 1].lower() not in VALUE_FLAGS | PATH_FLAGS]
            if head in ONE_TARGET:
                # Set-Content 檔 "內容"、New-Item x -Value …：只有檔名是路徑，後面的內容不是（QA 抓到內容被當成路徑）
                targets = flagged or plain[:1]
            elif head in ("expand-archive", "compress-archive"):
                targets = [toks[j + 1] for j, t in enumerate(toks[:-1]) if t.lower() == "-destinationpath"] or plain[-1:]
            else:
                targets = flagged + [t for t in plain if re.search(r"[\\/.]", t) or ABS.match(t)]
            writes += [norm(t, cur) for t in targets]
        elif head == "sed" and any(t.startswith("-i") for t in toks[1:]):
            if re.search(r"[\\/.]", toks[-1]):
                writes.append(norm(toks[-1], cur))
        elif head in ("python", "python3", "py", "python.exe", "node"):
            shell_effects.python_args += [norm(t, cur) or t for t in toks[1:]]
    return git_ops, [w for w in writes if w], [m for m in mentioned if m]


# ---------------------------------------------------------------- 一輪工作的判斷

DEFAULT_TRIGGERS = ("retro", "push")


def signal_kinds(e):
    """這個工具呼叫帶的交付訊號：retro（改回顧紀錄）、push、commit（含 merge／cherry-pick／am／revert）。"""
    out = set()
    if e.kind != "tool" or e.side:
        return out
    if e.name in WRITE_TOOLS:
        if RETRO.search(e.inp.get("file_path") or e.inp.get("notebook_path") or ""):
            out.add("retro")
    elif e.name in SHELLS:
        cmd = e.inp.get("command") or ""
        git_ops, writes, _ = shell_effects(cmd, e.cwd)
        for op, _ in git_ops:
            if op == "push":
                out.add("push")
            elif op in GIT_DELIVER:
                out.add("commit")
        # 用腳本改回顧紀錄：回顧紀錄的路徑是 python／node 的參數才算（只是 grep 一下、指令裡剛好有 python 不算；QA 抓到）
        if any(RETRO.search(w) for w in writes) or any(RETRO.search(a) for a in shell_effects.python_args):
            out.add("retro")
    return out


class Session:
    """一個工作階段的事件＋快取（回放時每個停點都要算，避免重算）。"""

    def __init__(self, events, triggers=DEFAULT_TRIGGERS):
        self.ev = events
        self.triggers = set(triggers)
        self._kinds = {}

    def kinds(self, k):
        if k not in self._kinds:
            self._kinds[k] = signal_kinds(self.ev[k])
        return self._kinds[k]

    def last_stop_before(self, end):
        i = end - 1
        while i >= 0 and self.ev[i].kind != "stop":
            i -= 1
        return i

    def blocked(self, stop):
        """這個停點有沒有被 Stop hook 擋下 → 下一輪是續跑（hook 收到 stop_hook_active）。
        真實紀錄是「Stop hook feedback → stop_hook_summary」，所以看停點**前面**那一筆（2026-11-05 QA 抓到原本只看後面）。"""
        for k in range(stop - 1, -1, -1):
            e = self.ev[k]
            if e.side or e.kind == "result":
                continue
            return e.kind == "hookfb"
        return False

    def nagged_since(self, start, end):
        """events[start:end] 裡這支 hook 已經擋過（紀錄裡有它的理由）→ 續跑時不再擋。"""
        return any(e.kind == "hookfb" and MARK in (e.text or "") for e in self.ev[start:end])

    def is_trigger_turn(self, end):
        stop = self.last_stop_before(end)
        return any(self.kinds(k) & self.triggers for k in range(stop + 1, end))

    def round_start(self, end, idle_hours):
        """這一輪工作的起點，取比較晚的：
        - 上一次寫回顧的那一段結束之後（同一段＝被 Stop hook 擋下後的續跑也算在一起，續跑裡補寫的紀錄算那一輪的）
        - 閒置超過 idle_hours 的斷點之後"""
        gap = datetime.timedelta(hours=idle_hours)
        idle_start, nxt = 0, None
        for k in range(end - 1, -1, -1):
            e = self.ev[k]
            if e.side or not e.ts:
                continue
            if nxt and nxt - e.ts > gap:
                idle_start = k + 1
                break
            nxt = e.ts
        stop = self.last_stop_before(end)
        while stop >= 0 and self.blocked(stop):   # 這一輪本身是續跑：併到被擋的那一輪，一起算
            stop = self.last_stop_before(stop)
        group_end, has_retro = stop, False
        while stop > idle_start:
            prev = self.last_stop_before(stop)
            if any("retro" in self.kinds(k) for k in range(prev + 1, stop)):
                has_retro = True
            if prev >= 0 and self.blocked(prev):
                stop = prev              # 這一輪是上一輪被擋下後的續跑，併在同一段
                continue
            if has_retro:
                return max(group_end + 1, idle_start)
            group_end, has_retro, stop = prev, False, prev
        return idle_start

    def analyze(self, start, end, proj):
        """events[start:end] → (changed {frozenset(紀錄): [證據]}, unmapped {repo: [證據]}, touched set, index_touched)。"""
        changed, unmapped, touched = {}, {}, set()
        index_touched = False

        def hit(p, why, release=False):
            m = proj.map(p, release)
            if m and m[0] == "rec":
                changed.setdefault(m[1], []).append(why)
            elif m:
                unmapped.setdefault(m[1], []).append(why)

        def touch(p):
            nonlocal index_touched
            for i, r in enumerate(proj.records):
                if r["path"] == p:
                    touched.add(i)
            if p == proj.index:
                index_touched = True

        for e in self.ev[start:end]:
            if e.kind != "tool":
                continue
            if e.name in WRITE_TOOLS:
                p = norm(e.inp.get("file_path") or e.inp.get("notebook_path") or "", e.cwd)
                if RETRO.search(p) and not e.side:
                    # 回顧寫的是哪個專案：那份紀錄也要更新（例：只回答問題＋補做回顧的一輪，沒改程式也算在專案上做了事）
                    edits = e.inp.get("edits") or [e.inp]
                    for ed in edits:
                        for cell in new_retro_rows(ed.get("old_string"), ed.get("new_string")):
                            group = proj.match_name(cell)
                            if group:
                                changed.setdefault(group, []).append("回顧「" + cell[:18] + "…」")
                    continue
                if proj.is_record(p) or p == proj.index:
                    touch(p)
                elif os.path.basename(p) in proj.record_names:
                    index_touched = True          # 新建一份還沒進總表的紀錄
                else:
                    hit(p, os.path.basename(p))
            elif e.name in SHELLS:
                cmd = e.inp.get("command") or ""
                git_ops, writes, mentioned = shell_effects(cmd, e.cwd)
                for op, d in git_ops:
                    hit(d, "git " + op, release=(op == "push"))
                for w in writes:
                    if proj.is_record(w) or w == proj.index:
                        touch(w)
                    else:
                        hit(w, os.path.basename(w))
                # 用指令改紀錄（python、[IO.File]::WriteAllText、sed…）：指令裡有紀錄的路徑、又有寫檔的字眼就算改過（寧可放過）
                if TOUCH_HINT.search(cmd):
                    for m in mentioned:
                        if proj.is_record(m) or m == proj.index:
                            touch(m)
        return changed, unmapped, touched, index_touched

    def pending(self, end, proj, idle_hours, live=True, every_stop=False, active=False):
        """停在 events[:end] 時：這一輪是交付輪、round 裡有改專案卻沒更新紀錄 → (need, miss_code, start)；否則 None。
        need：{frozenset(紀錄編號): [證據]}，同一組改其中一份就算。every_stop＝回放比較用：每個停點都判斷。
        active＝續跑（stop_hook_active）：這一段裡這支已經擋過就放行（一段最多擋一次，不會卡死）。"""
        if not every_stop and not self.is_trigger_turn(end):
            return None
        start = self.round_start(end, idle_hours)
        if active and self.nagged_since(start, end):
            return None
        changed, unmapped, touched, index_touched = self.analyze(start, end, proj)
        t0 = next((e.ts for e in self.ev[start:end] if e.ts and not e.side), None)
        # 只有回顧列寫了專案（沒改檔，多半是補寫以前工作的回顧）：紀錄在這個工作階段上一次 push 之後更新過，就算已經涵蓋
        last_push = []      # 需要時才算（要掃整個工作階段的指令）

        def push_ts():
            if not last_push:
                last_push.append(next((self.ev[k].ts for k in range(start - 1, -1, -1)   # 往回找，第一個就是最近的
                                       if self.ev[k].ts and self.ev[k].kind == "tool" and "push" in self.kinds(k)), None))
            return last_push[0]

        need = {}
        for group, why in changed.items():
            if group & touched:
                continue
            if live and t0 and any(_mtime(proj.records[i]["path"]) >= t0 for i in group):
                continue
            retro_only = all(w.startswith("回顧「") for w in why)
            if live and retro_only and push_ts() and any(_mtime(proj.records[i]["path"]) >= push_ts() for i in group):
                continue
            need[group] = why
        miss_code = {} if index_touched else unmapped
        if not need and not miss_code:
            return None
        return need, miss_code, start


def _mtime(path):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
    except OSError:
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


MARK = "專案紀錄還沒更新"     # 理由裡固定有這幾個字：續跑時用來判斷「這一段已經擋過」


def reason(proj, need, miss_code):
    lines = [f"這一輪在專案上做了事、也交付了（push 或寫了回顧），但{MARK}（全域說明〈專案紀錄〉、agile-crew 第 7 步）。結束前請更新："]
    for group, why in need.items():
        files = list(dict.fromkeys(why))
        more = f" 等 {len(files)} 項" if len(files) > 4 else ""
        names = "、".join(proj.records[i]["rel"] for i in sorted(group))
        which = f"{names}（其中一份）" if len(group) > 1 else names
        only_retro = all(w.startswith("回顧「") for w in files)
        todo = ("把這次回顧的發現補進「遇到的問題」、「工作進度」加一列；紀錄已經涵蓋這次的工作就回一句原因" if only_retro else
                "「目前狀況」與最後更新日、「工作進度」加一列、遇到的問題；並同步專案總表那一列")
        lines.append(f"- {which}（{'這一輪寫的' if only_retro else '這一輪改了：'}{'、'.join(files[:4])}{more}）：{todo}。")
    for d, why in miss_code.items():
        lines.append(f"- {d}（{'、'.join(list(dict.fromkeys(why))[:3])}）對不到任何專案紀錄：先在專案總表找它屬於哪個專案"
                     "（找到就把 repo 補進那份紀錄「基本資料」的程式碼列，再更新紀錄）；沒有就照範本建一份，"
                     "不知道放哪先問使用者，同時在總表「未歸類」記一列。")
    lines.append("如果這次的改動真的不用記（例：只是暫時測試、已經全部還原），回覆一句原因就好。"
                 "如果這一輪原本是停下來問使用者問題，補完紀錄後把那個問題完整再問一次。")
    return "\n".join(lines)


def check(events, path, cfg=None, active=False):
    """Stop 時的判斷（stop_gate.py 也呼叫這個）：events 是 transcript.session_events(...) 的結果；active＝stop_hook_active。
    要擋 → 回傳理由文字；不用擋 → None。擋下時記一行到 `<本地>/record-gate.log`（之後算成效用）。"""
    cfg = load_config() if cfg is None else cfg
    rg = cfg.get("record_gate") or {}
    if rg.get("enabled") is False:
        return None
    proj = Projects(cfg)
    if not proj.records:
        return None
    sid = os.path.basename(path)[:-6] if path.endswith(".jsonl") else ""
    own = [e for e in events if e.side or not e.sid or e.sid == sid]   # 不看 resume／fork 帶過來的舊歷史
    s = Session(own, rg.get("triggers") or DEFAULT_TRIGGERS)
    end = len(s.ev)
    # 這次停下的 stop_hook_summary 通常在 hook 跑完才寫；萬一已經寫了，就判斷它結束的那一輪
    last_main = next((k for k in range(end - 1, -1, -1) if not s.ev[k].side), -1)
    if last_main >= 0 and s.ev[last_main].kind == "stop":
        end = last_main
    res = s.pending(end, proj, float(rg.get("idle_split_hours") or 8), live=True, active=active)
    if not res:
        return None
    need, miss_code, _ = res
    if rg.get("unmapped_code") == "ignore":
        miss_code = {}
    if not need and not miss_code:
        return None
    try:
        with open(os.path.join(LOCAL, "record-gate.log"), "a", encoding="utf-8") as f:
            names = [proj.records[i]["rel"] for g in need for i in sorted(g)] + [os.path.basename(d) for d in miss_code]
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{sid}\t{'續跑擋' if active else '擋'}\t"
                    f"{'、'.join(names)}\n")
    except OSError:
        pass
    return reason(proj, need, miss_code)


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0
    text = check(T.session_events(path, results=False), path, active=bool(data.get("stop_hook_active")))
    if not text:
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        if os.environ.get("RECORD_GATE_DEBUG"):     # 測試時看錯誤；平常一律安靜放行
            import traceback
            traceback.print_exc()
        sys.exit(0)
