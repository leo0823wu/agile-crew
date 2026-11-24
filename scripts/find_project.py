"""用關鍵字找專案：印出專案紀錄、程式碼、網址、部署的位置，不用讀整份專案總表。

用法：
  python -X utf8 -I find_project.py <關鍵字> [關鍵字...]   專案名、repo 名、網址、主機的一部分都可以
  python -X utf8 -I find_project.py                        列出所有專案名稱（一行一個）
設定：<本地>/config.json 的 project_index（專案總表）、work_root、code_root；別名寫在 aliases。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projlib  # noqa: E402

SHOW = ("程式碼", "網址", "部署", "相關文件")
CUT = 260


def short(s, n=CUT):
    return s if len(s) <= n else s[: n - 1] + "…"


def card(p):
    lines = ["■ %s（%s）" % (p["name"], p["group"]), "  紀錄：%s" % p["path"]]
    hist = projlib.history_path(p["path"])
    if os.path.exists(hist):
        lines.append("  歷史：%s（要查舊事才 Grep，開工不用讀）" % hist)
    know = projlib.knowledge_path(p["path"])
    if os.path.exists(know):
        lines.append("  知識：%s（架構、流程、坑；需要時才讀）" % know)
    for k in SHOW:
        if p["basic"].get(k):
            lines.append("  %s：%s" % (k, short(p["basic"][k])))
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    plist = projlib.projects()
    if not plist:
        print("找不到專案總表：請在 <本地>/config.json 設定 project_index")
        return 1
    words = [w for w in sys.argv[1:] if w.strip()]
    if not words:
        for p in plist:
            print("%s｜%s｜%s" % (p["group"], p["name"], "、".join(sorted(p["names"] - {p["name"]}))))
        return 0
    found = []
    for p in plist:
        hay = " ".join([p["name"], p["group"], p["path"], " ".join(p["names"]), " ".join(p["basic"].values())]).lower()
        score = sum(1 for w in words if w.lower() in hay)
        name_hit = sum(1 for w in words if any(w.lower() in n.lower() for n in p["names"]))
        if score == len(words):
            found.append((name_hit, p))
    found.sort(key=lambda x: -x[0])
    if not found:
        print("沒有對到專案紀錄。不帶參數執行可以列出所有專案名稱；新專案照本地規則建紀錄。")
        return 2
    for _, p in found[:5]:
        print(card(p))
    if len(found) > 5:
        print("…另有 %d 個符合，關鍵字再具體一點" % (len(found) - 5))
    return 0


if __name__ == "__main__":
    sys.exit(main())
