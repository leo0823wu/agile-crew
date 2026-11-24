"""收尾時更新專案總表裡某個專案那一列（狀態、一句話現況、日期），不用把整份總表讀進對話。

用法：
  python -X utf8 -I index_row.py <專案關鍵字> "<一句話現況>" [--status 維運中]
  python -X utf8 -I index_row.py <專案關鍵字>                     只印那一列現在的內容
一句話限 200 字，細節寫在專案紀錄。日期自動填今天。欄位用表頭判斷（含「狀態」「狀況」「更新」的欄）。
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projlib  # noqa: E402

LIMIT = 200


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    status = None
    if "--status" in args:
        i = args.index("--status")
        status = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 1
    key, note = args[0], (args[1] if len(args) > 1 else None)
    cfg = projlib.config()
    index = cfg.get("project_index")
    plist = [p for p in projlib.projects(cfg) if any(key.lower() == n.lower() for n in p["names"])] or \
            [p for p in projlib.projects(cfg) if any(key.lower() in n.lower() for n in p["names"])]
    if len(plist) != 1:
        print("要剛好對到一個專案，現在對到 %d 個：%s" % (len(plist), "、".join(p["name"] for p in plist) or "（無）"))
        return 2
    p = plist[0]
    raw = open(index, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    work = cfg.get("work_root") or os.path.dirname(index)
    row = None
    for i, l in enumerate(lines):
        for rel in re.findall(r"\]\(([^)]*\.md)\)", l):
            if os.path.normpath(os.path.join(work, rel.replace("/", os.sep))) == p["path"] and l.startswith("|"):
                row = i
    if row is None:
        print("總表裡找不到這個專案那一列")
        return 2
    head = row
    while head > 0 and not re.match(r"^\|\s*-", lines[head]):
        head -= 1
    names = projlib.cells(lines[head - 1]) if head > 0 else []
    col = {k: next((j for j, n in enumerate(names) if k in n), None) for k in ("狀態", "狀況", "更新")}
    c = projlib.cells(lines[row])
    if note is None:
        print("%s｜%s" % (p["name"], "｜".join(c[j] for j in col.values() if j is not None and j < len(c))))
        return 0
    if None in col.values() or max(col.values()) >= len(c):
        print("這一列所在的表格沒有「狀態／目前狀況／最後更新」三欄，請手動改")
        return 2
    note = note.replace("|", "／").replace("\n", " ").strip()
    if len(note) > LIMIT:
        print("一句話現況請在 %d 字內（現在 %d 字）；細節寫在專案紀錄的「目前狀況」" % (LIMIT, len(note)))
        return 2
    if status:
        c[col["狀態"]] = status
    c[col["狀況"]] = note
    c[col["更新"]] = datetime.date.today().isoformat()
    lines[row] = "| " + " | ".join(c) + " |"
    for i, l in enumerate(lines[:6]):
        m = re.match(r"^(>\s*最後更新：)\d{4}-\d{2}-\d{2}(.*)$", l)
        if m:
            lines[i] = m.group(1) + datetime.date.today().isoformat() + m.group(2)
    with open(index, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        f.write("\n".join(lines).replace("\n", nl))
    print("已更新總表：%s｜%s｜%s" % (p["name"], c[col["狀態"]], note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
