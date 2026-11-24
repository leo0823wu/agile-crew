"""同一個關鍵字在「每個分支」各長怎樣（L-065：回答「現在／換版後會怎樣」看錯分支）。

用法：python -I -X utf8 grep_branches.py <repo> <正規式> [--since YYYY-MM-DD] [-- <路徑篩選，例 src/main/resources/templates>]
  例：python -I -X utf8 grep_branches.py C:/code/x "file_no" -- src/main/resources/templates/front/detail
  例：python -I -X utf8 grep_branches.py C:/code/x "剩餘次數|一週|WEEK\\(" --since 2025-07-31

列出本機分支、遠端預設分支、各 worktree 檢出的分支，每個分支印：最後 commit 日期、是哪個 worktree、命中幾行、前幾行內容。
命中的行如果是註解（// # <!-- * 開頭）會標「（註解）」——被註解掉的程式代表「以前有、後來拿掉」。
加 --since：另外列出那天之後所有分支裡「新增或刪掉含這個關鍵字的行」的 commit。

什麼時候跑：
- 回答「正式機現在會怎樣」「換版後會怎樣」前，再對照專案紀錄寫的「哪個分支在正式機、哪個是換版分支」，
  答案裡每個版本各寫一行（2026-11-04：看了舊分支就說「某站沒 PDF 會顯示壞掉的下載鈕」，其實換版分支 10/16 已修好）。
- 回答「系統有沒有某個功能」「需求單的東西做了沒」前：關鍵字用**畫面上的字**（欄位名、按鈕字）＋程式裡可能的寫法，
  --since 填需求提出的日期（2026-11-11：只看了需求單點名的那一頁就說「沒做」，其實別頁已做）。
- 列出的 commit 一律再看 `git show <hash> -- <檔>` 的 diff 才說「加了／拿掉什麼」：`+//` 開頭＝加進來就是註解；
  `-S`／`-G` 會誤中相似字串（2026-11-11：搜 `WEEK(` 中了 `DAYOFWEEK(`，差點說成「兩年前就有、去年拿掉」）。
"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
COMMENT = ("//", "#", "<!--", "*", "/*")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def is_comment(hit):
    # hit 長這樣：路徑:行號:內容
    parts = hit.split(":", 2)
    return len(parts) == 3 and parts[2].lstrip().startswith(COMMENT)


def main():
    argv = sys.argv[1:]
    paths = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[:argv.index("--")] if "--" in argv else argv
    since = None
    if "--since" in argv:
        i = argv.index("--since")
        since = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        return 1
    repo, pattern = argv[0], argv[1]

    worktrees = {}
    _, out = git(repo, "worktree", "list", "--porcelain")
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line.startswith("branch refs/heads/"):
            worktrees[line[18:]] = path

    branches = []
    _, out = git(repo, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)\t%(committerdate:short)",
                 "refs/heads")
    branches += [l.split("\t") for l in out.splitlines() if l]
    rc, head = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and head.strip():
        _, d = git(repo, "log", "-1", "--format=%cd", "--date=short", head.strip())
        branches.append([head.strip(), d.strip()])

    for name, date in branches:
        where = worktrees.get(name, "")
        rc, out = git(repo, "grep", "-n", "-E", pattern, name, "--", *paths)
        lines = [l[len(name) + 1:] for l in out.splitlines()] if rc == 0 else []
        n_comment = sum(1 for l in lines if is_comment(l))
        print(f"■ {name}（最後 commit {date}）" + (f"  worktree：{where}" if where else "")
              + f"  命中 {len(lines)} 行" + (f"（其中註解 {n_comment} 行）" if n_comment else ""))
        for l in lines[:6]:
            print("   ", ("（註解）" if is_comment(l) else "") + l[:200])
        if len(lines) > 6:
            print(f"    …另有 {len(lines) - 6} 行")

    if since:
        _, out = git(repo, "log", "--all", f"--since={since}", "-G", pattern, "--format=%h %ad %an %s",
                     "--date=short", "--", *paths)
        commits = [l for l in out.splitlines() if l.strip()]
        print(f"\n■ {since} 之後新增或刪掉含這個關鍵字的行的 commit：{len(commits)} 個")
        for l in commits[:20]:
            print("   ", l[:200])
        if len(commits) > 20:
            print(f"    …另有 {len(commits) - 20} 個")
        print("  → 每個 commit 用 `git show <hash>` 看是加上還是拿掉。")
    print("\n→ 對照專案紀錄：哪個分支在正式機、哪個是換版分支；回答時每個版本各寫一行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
