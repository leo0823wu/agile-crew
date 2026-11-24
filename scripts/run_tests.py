"""一次跑技能裡所有的測試（hooks/test_*.py、scripts/test_*.py），並檢查「印出的 failures」跟結束碼對得上。

由來（L-046）：有一支測試失敗時只印 `failures: N`、結束碼還是 0，自動化流程（例：故意改壞檔案、看測試會不會紅）就看不到失敗。
用法：python -I ~/.claude/skills/dev-team/scripts/run_tests.py
"""
import glob
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    tests = sorted(glob.glob(os.path.join(SKILL, "hooks", "test_*.py")) + glob.glob(os.path.join(SKILL, "scripts", "test_*.py")))
    bad = 0
    for t in tests:
        r = subprocess.run([sys.executable, "-X", "utf8", "-I", t], capture_output=True, timeout=900)
        out = r.stdout.decode("utf-8", "replace")
        m = re.findall(r"failures:\s*(\d+)", out)
        printed = int(m[-1]) if m else None
        fails_in_text = len(re.findall(r"^FAIL\b", out, re.M))
        if printed is None:
            status = "沒印 failures（看不出結果）"
            bad += 1
        elif (printed > 0 or fails_in_text > 0) and r.returncode == 0:
            status = f"失敗 {max(printed, fails_in_text)} 項，但結束碼是 0（無聲失效，要補 sys.exit）"
            bad += 1
        elif printed == 0 and r.returncode != 0:
            status = f"印 0 失敗，但結束碼 {r.returncode}（看 stderr）"
            bad += 1
        elif printed > 0:
            status = f"失敗 {printed} 項"
            bad += 1
        else:
            status = "0 失敗"
        print(f"{'OK ' if status == '0 失敗' else 'NG '} {os.path.relpath(t, SKILL)}：{status}")
        if r.returncode != 0 and r.stderr.strip():
            print("    " + r.stderr.decode("utf-8", "replace").strip().splitlines()[-1][:200])
    print(f"共 {len(tests)} 支，有問題 {bad} 支")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
