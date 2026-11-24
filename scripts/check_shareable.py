"""檢查技能資料夾能不能直接分享：不能有個人、公司、專案資料。

技能（本資料夾）只放通用的流程面、技術面內容；個人／公司／專案的內容放本地資料夾
（預設 ~/.claude/dev-team-local/，可用環境變數 DEV_TEAM_LOCAL 改）。

掃兩種東西：
1. 本地 `private-terms.txt` 列的字（公司名、專案名、人名、主機、內部路徑）——每個使用者自己維護
2. 通用的個資樣式：email、私有 IP、Windows／macOS 使用者家目錄路徑
另外順便檢查主檔 SKILL.md：不能寫日期（事件經過寫進踩坑表）、不能超過長度上限 MAIN_LIMIT。

用法：python -I check_shareable.py [--quiet]
  有發現就 exit 1，列出「檔案:行號  命中的字  該行開頭」。--quiet 只印總數。
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "dev-team-local")
SKIP_DIRS = {"_backup", "__pycache__", ".git"}
TEXT_EXT = {".md", ".py", ".txt", ".json", ".sh", ".ps1", ".mjs", ".js", ".ts", ".yml", ".yaml", ".log", ".csv"}

GENERIC = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("私有 IP", re.compile(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?\b")),
    ("使用者家目錄", re.compile(r"(?i)(?:[A-Z]:\\Users\\(?!<)[^\\\s`'\"]+|/Users/(?!<)[^/\s`'\"]+|/home/(?!<)[^/\s`'\"]+)")),
]
ALLOW_EMAIL = re.compile(r"(?i)@(example\.(com|org)|anthropic\.com)$")


def load_terms():
    path = os.path.join(LOCAL, "private-terms.txt")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


def scan(terms):
    hits = []
    lowered = [(t, t.lower()) for t in terms]
    for root, dirs, files in os.walk(SKILL):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if os.path.splitext(name)[1].lower() not in TEXT_EXT:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, SKILL)
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue  # 本檔的樣式字串會自己命中
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except UnicodeDecodeError:
                continue
            for no, line in enumerate(lines, 1):
                low = line.lower()
                found = [t for t, tl in lowered if tl in low]
                for label, pat in GENERIC:
                    for m in pat.finditer(line):
                        if label == "email" and ALLOW_EMAIL.search(m.group(0)):
                            continue
                        found.append(f"{label}:{m.group(0)}")
                if found:
                    hits.append((rel, no, sorted(set(found)), line.strip()[:80]))
    return hits


# 主檔只寫規則：發生經過、日期寫在踩坑表那一列（L-xxx）。上限比整理後（2026-11 約 27.4 KB）多留一點；
# 要加規則超過上限時，先把別處的細節搬到 references，不是調高上限。
MAIN_LIMIT = 28_500
DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")


def check_main():
    """回傳主檔的問題（日期、超過長度上限）。"""
    path = os.path.join(SKILL, "SKILL.md")
    try:
        raw = open(path, "rb").read()
    except OSError:
        return []
    problems = []
    for no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if DATE.search(line):
            problems.append(f"SKILL.md:{no}  主檔寫了日期（經過寫進踩坑表那一列，主檔只留規則＋編號）| {line.strip()[:60]}")
    if len(raw) > MAIN_LIMIT:
        problems.append(f"SKILL.md  {len(raw)} 位元組，超過上限 {MAIN_LIMIT}（把細節搬到 references，不是調高上限）")
    return problems


def main():
    terms = load_terms()
    hits = scan(terms)
    main_problems = check_main()
    for p in main_problems:
        print(p)
    print(f"主檔精簡檢查：{len(main_problems)} 項")
    if "--quiet" not in sys.argv:
        for rel, no, found, head in hits:
            print(f"{rel}:{no}  {'、'.join(found)}  | {head}")
    by_file = {}
    for rel, *_ in hits:
        by_file[rel] = by_file.get(rel, 0) + 1
    note = "" if terms else "（沒有本地 private-terms.txt，只檢查通用樣式）"
    print(f"可分享檢查{note}：{len(hits)} 行有個人／公司資料" +
          ("" if not hits else "：" + "、".join(f"{k} {v}" for k, v in sorted(by_file.items()))))
    if not hits:
        print("注意：0 行只代表「清單上的字與通用樣式沒出現」，不代表沒有內部資訊。"
              "第一次公開、或新增大量內容後，照 lessons-workflow L-259 請獨立審查員逐檔讀。")
    sys.exit(1 if hits or main_problems else 0)


if __name__ == "__main__":
    main()
