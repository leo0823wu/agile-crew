"""project_pointer.py 與 projlib 的測試：用暫存的總表與紀錄，不碰真實資料。
執行：python -X utf8 -I test_project_pointer.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import projlib  # noqa: E402
import project_pointer  # noqa: E402

REC = """# {name} 專案紀錄

## 基本資料

| 項目 | 內容 |
|---|---|
| 網址 | 正式：https://example.test |
| 程式碼 | 本機：`{code}` |

## 目前狀況

- **狀態**：進行中
"""


def setup(tmp):
    work = os.path.join(tmp, "work")
    code = os.path.join(tmp, "code")
    rows = []
    for group, name, repo in (("甲群", "紅茶官網", "redtea-web"), ("甲群", "紅茶系統", "redtea-admin"), ("乙群", "綠茶平台", "gt")):
        d = os.path.join(work, group, name)
        os.makedirs(d)
        with open(os.path.join(d, projlib.RECORD), "w", encoding="utf-8") as f:
            f.write(REC.format(name=name, code=os.path.join(code, repo)))
        rows.append("| %s | %s | 進行中 | 一句話 | 2026-01-01 | [專案紀錄](%s/%s/%s) |" % (group, name, group, name, projlib.RECORD))
    index = os.path.join(work, "index.md")
    with open(index, "w", encoding="utf-8") as f:
        f.write("# 總表\n\n| 群組 | 網站 | 狀態 | 目前狀況 | 最後更新 | 紀錄 |\n|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
    return {"project_index": index, "work_root": work, "code_root": code}


def main():
    fails = []

    def check(label, cond):
        print(("PASS " if cond else "FAIL ") + label)
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        cfg = setup(tmp)
        st = os.path.join(tmp, "state")
        plist = projlib.projects(cfg)
        check("讀到 3 個專案", len(plist) == 3)
        t = project_pointer.build("紅茶官網的首頁標題改一下", "s1", cfg, st)
        check("全名命中只帶那一個", "紅茶官網" in t and "紅茶系統" not in t)
        check("同一個工作階段不重複帶", project_pointer.build("紅茶官網再改一次", "s1", cfg, st) == "")
        t = project_pointer.build("紅茶那邊有問題", "s2", cfg, st)
        check("短名同時對到兩個專案時都列出", "紅茶官網" in t and "紅茶系統" in t)
        check("repo 名命中", "紅茶系統" in project_pointer.build("redtea-admin 編譯失敗", "s3", cfg, st))
        check("太短的英文名不比對（gt）", project_pointer.build("gt 這個字不該對到", "s4", cfg, st) == "")
        check("英文名要整個字（redtea-web 不對到 redtea-webhook）", project_pointer.build("redtea-webhook 壞了", "s5", cfg, st) == "")
        check("沒提到專案就沒有輸出", project_pointer.build("今天天氣如何", "s6", cfg, st) == "")
        check("只輸出位置、不輸出紀錄內容", "進行中" not in project_pointer.build("綠茶平台要加功能", "s7", cfg, st))
        off = dict(cfg, project_pointer=False)
        check("設定可關", project_pointer.build("紅茶官網", "s8", off, st) == "")
        # 壞輸入不能擋住送出：結束碼 0、沒有輸出
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "project_pointer.py")], input=b"not json", capture_output=True)
        check("壞輸入安靜結束", r.returncode == 0 and r.stdout == b"")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "project_pointer.py")],
                           input=json.dumps({"prompt": "", "session_id": "x"}).encode(), capture_output=True)
        check("空訊息安靜結束", r.returncode == 0 and r.stdout == b"")
    print("\n%d 項失敗" % len(fails))
    print("failures:", len(fails))      # run_tests.py 認這一行
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
