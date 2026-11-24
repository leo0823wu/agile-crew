"""VPN 時斷時續時操作主機：上傳（重試）→ 在主機上用 setsid nohup 獨立執行並寫 log → 重試讀 log 直到出現結束字樣。
用法：python -X utf8 -I -u remote_run.py <主機別名> <主機工作資料夾> <log 檔名> <結束字樣> <要執行的指令> [要上傳的本機檔 ...]
指令會在 <工作資料夾> 裡執行，輸出寫到 <log 檔名>（執行前先刪掉舊的同名 log）。最多等 15 分鐘。
"""
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
host, rdir, logname, marker, cmd = sys.argv[1:6]
files = sys.argv[6:]
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
SCP = r"C:\Windows\System32\OpenSSH\scp.exe"
O = ["-o", "ConnectTimeout=15", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=10"]


def retry(c, tries=30):
    for i in range(tries):
        p = subprocess.run(c, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return p.stdout
        time.sleep(10)
    raise SystemExit("一直連不上：%s" % p.stderr.strip()[:200])


if files:
    retry([SCP] + O + list(files) + ["%s:%s/" % (host, rdir)])
    print("已上傳 %d 個檔" % len(files))
launch = "cd %s && rm -f %s && (setsid nohup bash -c '%s' > %s 2>&1 < /dev/null &) && echo launched" % (rdir, logname, cmd.replace("'", "'\\''"), logname)
out = retry([SSH] + O + [host, launch])
print(out.strip())
t0 = time.time()
while time.time() - t0 < 900:
    time.sleep(8)
    p = subprocess.run([SSH] + O + [host, "cat %s/%s" % (rdir, logname)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode == 0 and marker in p.stdout:
        print(p.stdout)
        sys.exit(0)
print("15 分鐘內沒看到「%s」，最後讀到的 log：\n%s" % (marker, p.stdout if p.returncode == 0 else "(讀不到)"))
sys.exit(1)
