"""第一次用：建立本地資料夾，把 templates/ 的範本複製過去（已經有的檔案不覆蓋）。

本地資料夾＝環境變數 AGILE_CREW_LOCAL，沒設就是 ~/.claude/agile-crew-local（見 references/shareable.md）。
用法：python -I init_local.py
"""
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(SKILL, "templates")
LOCAL = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "agile-crew-local")


def main():
    os.makedirs(LOCAL, exist_ok=True)
    created, kept = [], []
    for name in sorted(os.listdir(TEMPLATES)):
        dst = os.path.join(LOCAL, name)
        if os.path.exists(dst):
            kept.append(name)
            continue
        shutil.copyfile(os.path.join(TEMPLATES, name), dst)
        created.append(name)
    print(f"本地資料夾：{LOCAL}")
    print("新建：" + ("、".join(created) or "無"))
    print("已存在、沒動：" + ("、".join(kept) or "無"))
    if "local-rules.md" in created or "private-terms.txt" in created:
        print("下一步：打開 local-rules.md 填你的慣例、private-terms.txt 填公司／專案／人名等不能外流的字。")


if __name__ == "__main__":
    main()
