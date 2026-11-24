"""lessons 編號分配：加鎖取號，好幾個工作階段同時寫也不會撞號。

新編號＝（技能 lessons-*.md、本地 lessons-local.md 已用的編號，以及取號紀錄裡取過的編號）最大值 + 1。
取號的同時寫進取號紀錄，別的工作階段就拿不到同一號。鎖與紀錄放本地資料夾（見 references/shareable.md）。

用法（一律 python -I）：
  python -I lesson_id.py next [--note "一句話說明"]   取一個技能用的新編號並印出（例：L-093）
  python -I lesson_id.py next --local [--note ...]     取一個本地專屬的編號（P-001～），寫進 <本地>/lessons-local.md
  python -I lesson_id.py check                         檢查重號；有問題 exit 1

兩組編號分開：技能的通用經驗用 L-，只適用本地的用 P-。這樣技能之後更新新增的 L- 編號，不會跟你本地的撞號。
"""
import argparse
import datetime
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(SKILL, "references")
LOCAL = os.environ.get("DEV_TEAM_LOCAL") or os.path.join(os.path.expanduser("~"), ".claude", "dev-team-local")
FILES = [os.path.join(REF, n) for n in ("lessons-workflow.md", "lessons-tech.md")] + [os.path.join(LOCAL, "lessons-local.md")]
LOCK = os.path.join(LOCAL, ".lesson_id.lock")
LOG = os.path.join(LOCAL, "lesson-ids.log")
ROW = re.compile(r"^\| ([LP])-(\d+) \|", re.M)


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def used_ids(prefix="L"):
    """{編號: [出現的檔名, ...]}，只算表格列（`| L-xxx |` 開頭）；本地檔的〈本地細節〉表也是 `| L-xxx |`，要排除。"""
    seen = {}
    for path in FILES:
        if not os.path.exists(path):
            continue
        text = read(path)
        if path.endswith("lessons-local.md"):  # 只算〈只適用本地的經驗〉段，〈本地細節〉是同編號的補充
            text = "\n".join(re.findall(r"^## 只適用本地的經驗.*?(?=^## |\Z)", text, re.M | re.S))
        for m in ROW.finditer(text):
            if m.group(1) == prefix:
                seen.setdefault(int(m.group(2)), []).append(os.path.basename(path))
    return seen


def reserved_ids(prefix="L"):
    if not os.path.exists(LOG):
        return set()
    return {int(m) for m in re.findall(r"^" + prefix + r"-(\d+)\t", read(LOG), re.M)}


class Lock:
    def __enter__(self):
        os.makedirs(LOCAL, exist_ok=True)
        deadline = time.time() + 15
        while True:
            try:
                self.fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:  # 拿鎖的程式當掉留下的鎖，30 秒後視為過期
                    if time.time() - os.path.getmtime(LOCK) > 30:
                        os.unlink(LOCK)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    sys.exit("拿不到鎖（另一個工作階段正在取號），稍後再試")
                time.sleep(0.2)

    def __exit__(self, *exc):
        os.close(self.fd)
        os.unlink(LOCK)


def cmd_next(note, prefix):
    with Lock():
        taken = set(used_ids(prefix)) | reserved_ids(prefix)
        n = max(taken or {0}) + 1
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(LOG, "a", encoding="utf-8", newline="") as f:
            f.write(f"{prefix}-{n:03d}\t{stamp}\t{note or ''}\n")
    print(f"{prefix}-{n:03d}")


def cmd_check():
    problems = []
    for prefix in ("L", "P"):
        seen = used_ids(prefix)
        for i, where in sorted(seen.items()):
            if len(where) > 1:
                problems.append(f"{prefix}-{i:03d} 重號：出現在 {', '.join(where)}")
        top = max(set(seen) | reserved_ids(prefix) or {0})
        unused = sorted(reserved_ids(prefix) - set(seen))
        label = "技能" if prefix == "L" else "本地專屬"
        print(f"{label}（{prefix}-）已用 {len(seen)} 個，最大 {prefix}-{top:03d}；下一個 {prefix}-{top + 1:03d}")
        if unused:
            print("  取了號但還沒寫進 lessons（可能寫一半或放棄）：" + "、".join(f"{prefix}-{i:03d}" for i in unused))
    for p in problems:
        print("問題：" + p)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["next", "check"])
    ap.add_argument("--note", default="")
    ap.add_argument("--local", action="store_true", help="取本地專屬編號（P-）")
    a = ap.parse_args()
    cmd_next(a.note, "P" if a.local else "L") if a.action == "next" else cmd_check()
