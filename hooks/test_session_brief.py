"""session_brief.py 的情境測試：用臨時的假本地資料夾（DEV_TEAM_LOCAL）跑，不碰真的資料。"""
import json
import os
import subprocess
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_brief.py")
root = tempfile.mkdtemp()
LOCAL = os.path.join(root, "local")
WORK = os.path.join(root, "work")
CODE = os.path.join(root, "code")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


write(os.path.join(LOCAL, "config.json"), json.dumps(
    {"project_index": os.path.join(WORK, "index.md"), "work_root": WORK, "code_root": CODE}))
write(os.path.join(WORK, "index.md"),
      "| 專案 | 紀錄 |\n|---|---|\n| Alpha | [紀錄](groupA/Alpha/record.md) |\n| Beta | [紀錄](groupA/Beta/record.md) |\n"
      "| Gamma | [紀錄](groupA/Gamma/record.md) |\n")
write(os.path.join(WORK, "groupA", "Alpha", "record.md"),
      "# Alpha\n\n## 基本資料\n\n| 項目 | 內容 |\n|---|---|\n| 程式碼 | 本機：`alpha-web`（main） |\n\n"
      "## 交接單\n\n> 2026-01-05 10:00 寫。給下一個接手的工作階段。\n\n- **下一步的第一個動作**：開 login.jsp 第 40 行\n"
      "- **試過但沒用的方法**：清快取沒用\n- **做到一半的狀態**：無\n- **使用者這次講過的偏好**：無\n\n"
      "## 待辦\n\n- ⏳ 修 alpha 的登入頁\n- ✅ 已完成的事\n\n## 資安檢測\n\n- ⏳ alpha 金鑰輪替\n")
write(os.path.join(WORK, "groupA", "Gamma", "record.md"),
      "# Gamma\n\n## 基本資料\n\n| 項目 | 內容 |\n|---|---|\n| 程式碼 | 本機：`gamma-app` |\n\n"
      "## 交接單\n\n無（2026-01-06 已交付，沒有進行中的工作）\n\n## 待辦\n\n- ⏳ gamma 的報表\n")
write(os.path.join(WORK, "groupA", "Beta", "record.md"),
      "# Beta\n\n## 基本資料\n\n| 項目 | 內容 |\n|---|---|\n| 程式碼 | 本機：`beta-api` |\n| 相關文件 | 也參考 `alpha-web` |\n\n"
      "## 交接單\n\n> YYYY-MM-DD HH:MM 寫。\n\n- **下一步的第一個動作**：<寫到開哪個檔>\n- **試過但沒用的方法**：無\n"
      "- **做到一半的狀態**：\n- **使用者這次講過的偏好**：<這次講的>\n\n"
      "## 待辦\n\n- ⏳ beta 的匯出\n")
write(os.path.join(LOCAL, "retro-log.md"),
      "# 回顧紀錄\n\n## 回顧紀錄（最新在最上面）\n\n| 日期 | 專案 | 指標 | 發現 | 已改 | 狀態 |\n|---|---|---|---|---|---|\n"
      "| 2026-10-30 | Alpha 第一輪 | 糾正 0 | — | x | ✅ 已改；⏳ 補一支測試 |\n")
write(os.path.join(LOCAL, "skill-changelog.md"),
      "# 改版\n\n## 改版紀錄（最新在最上面）\n\n| 日期 | 改了什麼 | 問題 | 訊號 | 成效 |\n|---|---|---|---|---|\n"
      "| 2026-10-30 | 範本加一句 | 子代理超範圍 | 子代理問題 0 | ⏳ 待驗證 |\n| 2026-10-29 | hook | 忘了回顧 | 都有回顧 | ✅ 有效 |\n")
write(os.path.join(LOCAL, "lessons-local.md"),
      "## 只適用本地的經驗\n\n| 編號 | 事 | 反應 | 做法 | 再犯 |\n|---|---|---|---|---|\n| P-001 | 本地的坑 | — | 下次注意 | 3 |\n"
      "\n## 本地細節\n\n| 編號 | 本地細節 |\n|---|---|\n| L-005 | 某專案的測試類別 |\n")


def brief(cwd, local=LOCAL):
    env = dict(os.environ, DEV_TEAM_LOCAL=local)
    t = time.time()
    r = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps({"cwd": cwd}).encode("utf-8"),
                       capture_output=True, env=env)
    out = json.loads(r.stdout.decode("utf-8"))
    return out["hookSpecificOutput"]["additionalContext"], out["systemMessage"], time.time() - t, r.returncode


cases = [
    # (工作目錄, 一定要出現, 一定不能出現)
    (os.path.join(CODE, "alpha-web"), ["修 alpha 的登入頁", "alpha 金鑰輪替"], ["beta 的匯出", "已完成的事"]),
    (os.path.join(CODE, "alpha-web", ".claude", "worktrees", "x"), ["修 alpha 的登入頁"], ["beta 的匯出"]),
    (os.path.join(WORK, "groupA", "Beta"), ["beta 的匯出"], ["修 alpha 的登入頁"]),
    (os.path.join(WORK, "groupA", "Beta", "screens"), ["beta 的匯出"], []),
    (os.path.join(root, "elsewhere"), ["沒對到專案紀錄"], ["專案待辦 ⏳"]),
    (os.path.join(CODE, "no-such-repo"), ["沒對到專案紀錄"], ["專案待辦 ⏳"]),
    # 交接單：有內容整段帶入；只有範本空欄位、或寫「無（已交付）」不帶
    (os.path.join(CODE, "alpha-web"), ["### 交接單（Alpha", "開 login.jsp 第 40 行", "清快取沒用", "接手問 N"], []),
    (os.path.join(WORK, "groupA", "Beta"), ["beta 的匯出"], ["### 交接單"]),
    (os.path.join(CODE, "gamma-app"), ["gamma 的報表"], ["### 交接單"]),
    (os.path.join(root, "elsewhere"), [], ["### 交接單"]),
    # 回顧 ⏳、改版待驗證、本地 lessons 再犯未成機制
    (os.path.join(root, "elsewhere"), ["補一支測試", "子代理超範圍", "P-001（再犯 3）"], ["忘了回顧", "某專案的測試類別"]),
]
fail = 0
for cwd, must, mustnot in cases:
    ctx, msg, sec, rc = brief(cwd)
    ok = rc == 0 and all(m in ctx for m in must) and not any(m in ctx for m in mustnot) and sec < 10
    fail += not ok
    print("PASS" if ok else "FAIL", f"{sec*1000:.0f}ms", os.path.relpath(cwd, root), "|", msg)
    if not ok:
        print(ctx)

# 沒有本地資料夾：要提示怎麼建，不能當掉
ctx, msg, _, rc = brief(os.path.join(root, "elsewhere"), local=os.path.join(root, "nope"))
ok = rc == 0 and "還沒有本地資料夾" in ctx
fail += not ok
print("PASS" if ok else "FAIL", "沒有本地資料夾時提示建立 |", msg)

for bad in (b"", b"not json", b"{}"):
    r = subprocess.run([sys.executable, "-I", HOOK], input=bad, capture_output=True,
                       env=dict(os.environ, DEV_TEAM_LOCAL=LOCAL))
    ok = r.returncode == 0
    fail += not ok
    print("PASS" if ok else "FAIL", "壞輸入放行", bad)
print("failures:", fail)
