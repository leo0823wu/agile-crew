# -*- coding: utf-8 -*-
r"""列出工作區裡「所有 repo」讀寫某幾張資料表的程式位置(L-159 → 機制)。

為什麼:要匯入、修資料、改欄位之前,得先知道還有誰在用這張表——同一個網站的別頁、別的系統、排程。
  2026-11-06 改共用設定表做完才搜到另外兩個系統也讀它;2026-11-09 匯入新一批資料,使用者提醒「另一頁也會顯示這份資料」才去查,
  一查發現那一頁的讀法在正式站本來就是錯的。兩次都是「沒先列出讀取者」。
用法:python -X utf8 -I find_table_readers.py <工作區根目錄> <表名> [<表名> ...] [--max 400]
  - 根目錄底下每個子資料夾當一個 repo:是 git repo 就用 `git grep`(快、只看版控的檔),不是就逐檔掃常見程式副檔名
  - 每個命中依那一行猜「讀/寫」(INSERT/UPDATE/DELETE/REPLACE/ALTER → 寫;其他 → 讀),並附上所在的方法/函式名稱
輸出:每個 repo 一段,最後彙總「哪些 repo 讀、哪些寫」。結果貼進計畫,逐一判斷這次的改動會不會影響它們。
"""
import os, re, subprocess, sys, collections

sys.stdout.reconfigure(encoding="utf-8")
SKIP_DIRS = {"node_modules", "target", ".git", "build", "dist", ".metadata", "vendor", "__pycache__", ".gradle", ".idea", "bin", "obj", "out"}
EXTS = {".java", ".kt", ".xml", ".py", ".js", ".ts", ".tsx", ".php", ".cs", ".sql", ".html", ".jsp", ".vue", ".go", ".rb", ".properties", ".yml", ".yaml"}
WRITE = re.compile(r"\b(insert\s+(?:ignore\s+)?into|update|delete\s+from|replace\s+into|alter\s+table|truncate|drop\s+table)\b", re.I)
METHOD = re.compile(r"^\s*(?:public|private|protected|static|def|function|async|func)\b.*?([A-Za-z_]\w*)\s*\(")


def method_of(lines, idx):
    for j in range(idx, max(-1, idx - 200), -1):
        m = METHOD.match(lines[j])
        if m and not lines[j].strip().startswith(("//", "*", "#")):
            return m.group(1)
    return ""


def scan_file(path, pats):
    try:
        if os.path.getsize(path) > 3_000_000:
            return []
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return []
    hits = []
    for i, l in enumerate(lines):
        if any(p.search(l) for p in pats):
            hits.append((i + 1, l.strip()[:200], method_of(lines, i)))
    return hits


def git_files_with(repo, tables):
    args = ["git", "-C", repo, "grep", "-l", "-I", "-i"]
    for t in tables:
        args += ["-e", t]
    r = subprocess.run(args, capture_output=True)
    if r.returncode not in (0, 1):
        return None
    return [os.path.join(repo, p) for p in r.stdout.decode("utf-8", "replace").splitlines() if p.strip()]


def walk_files(repo):
    for d, subs, files in os.walk(repo):
        subs[:] = [s for s in subs if s not in SKIP_DIRS and not s.startswith(".")]
        for f in files:
            if os.path.splitext(f)[1].lower() in EXTS:
                yield os.path.join(d, f)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 400
    if len(args) < 2:
        print(__doc__)
        sys.exit(2)
    root, tables = args[0], args[1:]
    if "--max" in sys.argv:
        tables = [t for t in tables if t != str(mx)]
    # 表名前後不能接字母數字底線(order_item 不要命中 order_item_log);前面可以有 schema.
    pats = [re.compile(r"(?<![\w])" + re.escape(t) + r"(?![\w])", re.I) for t in tables]
    summary = collections.defaultdict(lambda: {"讀": 0, "寫": 0})
    shown = 0
    repos = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and d not in SKIP_DIRS)
    for name in repos:
        repo = os.path.join(root, name)
        files = git_files_with(repo, tables) if os.path.isdir(os.path.join(repo, ".git")) else None
        if files is None:
            files = list(walk_files(repo))
        out = []
        for f in files:
            if os.path.splitext(f)[1].lower() not in EXTS:
                continue
            for ln, text, meth in scan_file(f, pats):
                kind = "寫" if WRITE.search(text) else "讀"
                summary[name][kind] += 1
                out.append(f"  [{kind}] {os.path.relpath(f, repo)}:{ln}" + (f"  ({meth})" if meth else "") + f"  {text}")
        if out:
            print(f"== {name}({len(out)} 處)")
            for l in out:
                if shown < mx:
                    print(l)
                shown += 1
    if shown > mx:
        print(f"…另有 {shown - mx} 處沒印(--max 調大)")
    print("\n== 彙總(讀／寫 處數):")
    for name, c in sorted(summary.items()):
        print(f"  {name}:讀 {c['讀']}、寫 {c['寫']}")
    if not summary:
        print("  沒有任何 repo 提到", tables)


if __name__ == "__main__":
    main()
