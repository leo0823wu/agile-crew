"""專案紀錄的共用讀取：從本地 config.json 的專案總表找到每份紀錄，取名稱、別名、基本資料。

find_project.py（開工找專案）與 hooks/project_pointer.py（提到專案名稱時自動帶位置）共用。
"""
import json
import os
import re

LOCAL = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "agile-crew-local")
SUFFIX = ("官網", "系統", "平台", "網站", "後台")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def config():
    path = os.path.join(LOCAL, "config.json")
    return json.loads(read(path)) if os.path.exists(path) else {}


_CFG = config()
RECORD = _CFG.get("record_name") or "project-record.md"          # 每個專案的紀錄檔名（本地設定）
_STEM, _EXT = os.path.splitext(RECORD)
HISTORY = _STEM + (_CFG.get("history_suffix") or "-history") + _EXT  # 歷史檔名


KNOWLEDGE = _CFG.get("knowledge_name") or "project-notes.md"       # 不常變的專案事實（架構、流程、坑），需要時才讀


def knowledge_path(record_path):
    """紀錄檔對應的知識檔（同資料夾；紀錄檔名有前綴的，知識檔帶同一個前綴）。"""
    d, base = os.path.split(record_path)
    return os.path.join(d, base[: -len(RECORD)] + KNOWLEDGE)


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def section(text, title_re):
    m = re.search(r"^## " + title_re + r".*$", text, re.M)
    if not m:
        return ""
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[: n.start()] if n else rest


def basic_rows(text):
    """「基本資料」表格 → {項目: 內容}"""
    out = {}
    for line in section(text, "基本資料").splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            c = cells(line)
            if len(c) >= 2 and c[0] not in ("項目", ""):
                out[c[0]] = c[1]
    return out


def projects(cfg=None):
    """回傳 [{name, group, path, basic, names}]；names 是比對用的名稱（全名、去掉「官網」這類字尾的短名、repo 名、設定的別名）。"""
    cfg = cfg or config()
    index = cfg.get("project_index")
    if not index or not os.path.exists(index):
        return []
    work = cfg.get("work_root") or os.path.dirname(index)
    code_root = (cfg.get("code_root") or "").rstrip("\\/")
    aliases = (cfg.get("record_gate") or {}).get("aliases") or {}
    aliases.update(cfg.get("aliases") or {})
    out, seen = [], set()
    pairs = []
    for line in read(index).splitlines():
        if line.startswith("|"):
            for rel in re.findall(r"\]\(([^)]*" + re.escape(RECORD) + r")\)", line):
                pairs.append((line, rel))
    for line, rel in pairs:
        path = os.path.normpath(os.path.join(work, rel.replace("/", os.sep)))
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        c = cells(line)
        base = os.path.basename(path)
        folder = os.path.basename(os.path.dirname(path))
        if base != RECORD:      # 紀錄檔名前面多了前綴（同一個資料夾放兩份紀錄）——名稱取那個前綴
            name = base[: -len(RECORD)].rstrip("_- ")
            c = [folder]
            names = {name}
        else:
            name = c[1] if len(c) > 1 else folder
            names = {name, folder}
        basic = basic_rows(read(path))
        for n in list(names):
            for s in SUFFIX:
                if n.endswith(s) and len(n) - len(s) >= 2:
                    names.add(n[: -len(s)])
        code = basic.get("程式碼", "")
        if code_root:
            for r in re.findall(re.escape(code_root) + r"[\\/]([\w.-]+)", code, re.I):
                names.add(r)
        for a, target in aliases.items():
            if os.path.normpath(os.path.join(work, target.replace("/", os.sep))) == path:
                names.add(a)
        out.append({"name": name, "group": c[0] if c else "", "path": path, "basic": basic, "names": names})
    return out


def history_path(record_path):
    """紀錄檔對應的歷史檔（同資料夾；檔名有前綴的，歷史檔帶同一個前綴）。"""
    d, base = os.path.split(record_path)
    return os.path.join(d, base[: -len(RECORD)] + HISTORY)


def usable(n):
    """太短或太常見的名稱不拿來自動比對（純英數少於 4 個字、中文少於 2 個字）。"""
    if re.fullmatch(r"[\w.-]+", n, re.A):
        return len(n) >= 4
    return len(n) >= 2


def match(text, plist):
    """text 裡提到哪些專案。回傳 [(專案, 命中的名稱)]，全名命中的排前面；短名同時對到多個專案時都列出。"""
    low = text.lower()
    hits = []
    for p in plist:
        best = None
        for n in p["names"]:
            if not usable(n):
                continue
            nl = n.lower()
            if re.fullmatch(r"[\w.-]+", nl, re.A):
                ok = re.search(r"(?<![\w.-])" + re.escape(nl) + r"(?![\w-])", low) is not None
            else:
                ok = nl in low
            if ok and (best is None or len(n) > len(best)):
                best = n
        if best:
            hits.append((p, best))
    hits.sort(key=lambda h: -len(h[1]))
    # 長的名稱已經命中時，去掉只靠它的一部分命中的別的專案（例：「紅茶官網」命中，就不再列只靠「紅茶」命中的）
    if hits:
        top = hits[0][1]
        hits = [h for h in hits if h[1] == top or h[1].lower() not in top.lower()]
    return hits
