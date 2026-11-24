"""把舊名 dev-team 的安裝升級成 agile-crew（技能資料夾、本地資料夾、設定檔裡的路徑）。可以重跑。

用法（先試跑，看過再套用）：
  python -X utf8 -I <技能>/scripts/migrate_name.py                 只列出會做什麼、會改哪幾行
  python -X utf8 -I <技能>/scripts/migrate_name.py --apply         真的做
  python -X utf8 -I <技能>/scripts/migrate_name.py --remove-compat --apply   確定沒有東西用舊路徑後，拿掉相容用的轉送檔與連結

會做的事（都在 Claude 設定資料夾底下，預設 ~/.claude，可用 --home 指定）：
  1. skills/dev-team → skills/agile-crew；dev-team-local → agile-crew-local
  2. 舊位置留相容：skills/dev-team/{hooks,scripts}/ 放轉送檔（沒有 SKILL.md，技能清單不會出現舊名）、
     dev-team-local 做成指向新資料夾的連結。已經開著的工作階段、還沒改的設定才不會找不到檔。--no-compat 不留。
  3. 改這些檔裡的舊名：settings.json、settings.local.json、CLAUDE.md、hooks/*.py、
     scheduled-tasks/*/SKILL.md、projects/*/memory/*.md，以及 --also 另外指定的檔。
     改之前把 settings.json、CLAUDE.md 備份到 --backup-dir（預設 <home>/backups/agile-crew-rename-<時間>/）。
  取代規則：dev-team-local → agile-crew-local；DEV_TEAM_X → AGILE_CREW_X；獨立出現的 dev-team → agile-crew
  （前後接英數字或連字號的不動，例：檔名 dev-team-xxx.md）。講「以前叫 dev-team」的句子會被改壞，試跑時先看。

注意：相容用的 dev-team-local 是連結，不要用 rm -rf／Remove-Item -Recurse 刪（會連新資料夾的內容一起刪），用 --remove-compat。
作業系統的排程（Windows 工作排程器、cron、launchd）裡寫死的路徑這支不改，最後會提醒。
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time

OLD, NEW = "dev-team", "agile-crew"
STUB_MARK = "agile-crew compat stub"
STUB = '''"""%s：技能已改名為 agile-crew，這支只轉送給還在用舊路徑的設定，之後用 migrate_name.py --remove-compat 拿掉。"""
import os
import runpy
import sys

_t = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  "agile-crew", "%s", os.path.basename(__file__))
sys.path.insert(0, os.path.dirname(_t))
sys.argv[0] = _t
runpy.run_path(_t, run_name="__main__")
'''
BARE = re.compile(r"(?<![\w-])dev-team(?![\w-])")
ENV = re.compile(r"DEV_TEAM_(?=[A-Z])")


def rename_text(s):
    s = s.replace(OLD + "-local", NEW + "-local")
    s = ENV.sub("AGILE_CREW_", s)
    return BARE.sub(NEW, s)


def is_link(p):
    if os.path.islink(p):
        return True
    # Windows 的目錄連結（junction）：3.12 以前 islink 認不出來，直接看「重新解析點」屬性
    try:
        return bool(getattr(os.lstat(p), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def make_link(link, target):
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
        if r.returncode != 0:
            raise OSError(r.stderr.decode("mbcs", "replace").strip() or "mklink 失敗")
    else:
        os.symlink(target, link, target_is_directory=True)


def remove_link(p):
    if os.name == "nt":
        os.rmdir(p)          # 只拿掉連結，不碰目標
    else:
        os.unlink(p)


class Run:
    def __init__(self, apply):
        self.apply = apply
        self.changed = 0

    def say(self, msg):
        print(("" if self.apply else "[試跑] ") + msg)

    def do(self, msg, fn):
        self.say(msg)
        self.changed += 1
        if self.apply:
            fn()


def move_dir(run, old, new, what):
    if is_link(old):
        return
    old_real = os.path.isdir(old) and (what != "skill" or os.path.isfile(os.path.join(old, "SKILL.md")))
    if not old_real:
        return
    if os.path.exists(new):
        print(f"！{old} 和 {new} 都在，沒有搬。請先看兩邊內容、手動合併後再重跑。")
        sys.exit(1)
    def fn():
        try:
            os.rename(old, new)
        except OSError as e:
            print(f"！搬不動 {old}（{e.__class__.__name__}）：多半是別的程式開著這個資料夾。"
                  "關掉其他 Claude 工作階段、編輯器、停在這個資料夾裡的終端機後重跑；已經做的步驟不會重做。")
            sys.exit(1)
    run.do(f"搬資料夾：{old} → {new}", fn)


def write_stubs(run, old_skill, new_skill):
    for sub in ("hooks", "scripts"):
        src = os.path.join(new_skill, sub)
        if not os.path.isdir(src) and run.apply:
            continue
        # 試跑時新資料夾還沒搬過來，改看舊的
        look = src if os.path.isdir(src) else os.path.join(old_skill, sub)
        names = sorted(n for n in os.listdir(look) if n.endswith(".py")) if os.path.isdir(look) else []
        dst_dir = os.path.join(old_skill, sub)
        if os.path.isfile(os.path.join(old_skill, "SKILL.md")):
            todo = names        # 只會在試跑時發生：舊資料夾還沒搬走
        else:
            todo = [n for n in names if not os.path.isfile(os.path.join(dst_dir, n))]
        if not todo:
            continue

        def fn(dst_dir=dst_dir, todo=todo, sub=sub):
            os.makedirs(dst_dir, exist_ok=True)
            for n in todo:
                with open(os.path.join(dst_dir, n), "w", encoding="utf-8", newline="\n") as f:
                    f.write(STUB % (STUB_MARK, sub))
        run.do(f"相容：在 {dst_dir} 放 {len(todo)} 支轉送檔", fn)


def remove_compat(run, home):
    old_skill = os.path.join(home, "skills", OLD)
    old_local = os.path.join(home, OLD + "-local")
    if is_link(old_local):
        run.do(f"拿掉連結：{old_local}", lambda: remove_link(old_local))
    if os.path.isdir(old_skill) and not os.path.isfile(os.path.join(old_skill, "SKILL.md")):
        bad = []
        for root, dirs, files in os.walk(old_skill):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for n in files:
                p = os.path.join(root, n)
                if STUB_MARK not in open(p, encoding="utf-8", errors="replace").read(300):
                    bad.append(p)
        if bad:
            print(f"！{old_skill} 裡有不是轉送檔的檔案，沒有刪：{bad[:5]}")
        else:
            run.do(f"刪掉轉送檔資料夾：{old_skill}", lambda: shutil.rmtree(old_skill))


def text_targets(home, also):
    pats = ["settings.json", "settings.local.json", "CLAUDE.md", "hooks/*.py",
            "scheduled-tasks/*/SKILL.md", "projects/*/memory/*.md"]
    out = []
    for pat in pats:
        out += sorted(glob.glob(os.path.join(home, *pat.split("/"))))
    return out + [os.path.abspath(p) for p in also]


def rewrite(run, path, backup_dir, backup_names):
    try:
        raw = open(path, "rb").read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return
    new = rename_text(text)
    if new == text:
        return
    old_lines, new_lines = text.splitlines(), new.splitlines()
    diff = [(i + 1, a, b) for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
    print(f"\n{path}：{len(diff)} 行")
    for no, a, b in diff:
        m = re.search(r"dev-team|DEV_TEAM_", a)
        lo = max(0, m.start() - 45)
        print(f"  {no}: …{a[lo:m.end() + 45]}…")

    def fn():
        if os.path.basename(path) in backup_names:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path) + ".改名前"))
        with open(path, "wb") as f:
            f.write(new.encode("utf-8"))
    run.do(f"改 {os.path.basename(path)}", fn)


def main():
    ap = argparse.ArgumentParser(description="dev-team → agile-crew 升級")
    ap.add_argument("--home", default=os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-compat", action="store_true")
    ap.add_argument("--remove-compat", action="store_true")
    ap.add_argument("--backup-dir")
    ap.add_argument("--also", action="append", default=[], help="另外要改的檔（可重複）")
    a = ap.parse_args()
    home = os.path.abspath(a.home)
    run = Run(a.apply)
    old_skill, new_skill = os.path.join(home, "skills", OLD), os.path.join(home, "skills", NEW)
    old_local, new_local = os.path.join(home, OLD + "-local"), os.path.join(home, NEW + "-local")

    if a.remove_compat:
        remove_compat(run, home)
    else:
        if os.path.abspath(os.getcwd()).lower().startswith(old_skill.lower()):
            os.chdir(home)      # 人在舊資料夾裡，Windows 會搬不動
        move_dir(run, old_skill, new_skill, "skill")
        move_dir(run, old_local, new_local, "local")
        if not a.no_compat:
            write_stubs(run, old_skill, new_skill)
            if not os.path.lexists(old_local) or (not run.apply and not is_link(old_local)):
                if os.path.isdir(new_local) or not run.apply:
                    run.do(f"相容：{old_local} 做成指向 {new_local} 的連結", lambda: make_link(old_local, new_local))
        backup_dir = a.backup_dir or os.path.join(home, "backups", "agile-crew-rename-" + time.strftime("%Y%m%d_%H%M%S"))
        for p in text_targets(home, a.also):
            rewrite(run, p, backup_dir, {"settings.json", "CLAUDE.md"})

    print(f"\n{'已完成' if a.apply else '試跑結束（沒有改任何東西；加 --apply 才會做）'}：{run.changed} 個動作。")
    if not a.remove_compat:
        print("還要自己做：①作業系統排程（工作排程器、cron、launchd）裡寫死的舊路徑 ②環境變數 DEV_TEAM_LOCAL 有設的話改名 AGILE_CREW_LOCAL"
              " ③新開一個工作階段，確認開工提醒有出現、技能清單是 agile-crew。")


if __name__ == "__main__":
    main()
