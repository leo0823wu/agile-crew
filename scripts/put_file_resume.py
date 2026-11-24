"""VPN 不穩時傳大檔：切成 8MB 小段，逐段上傳（失敗重試、已傳好的段跳過），主機上組回並比整檔 md5。
用法：python -X utf8 -I -u put_file_resume.py <本機檔（英文路徑）> <主機別名> <主機資料夾（家目錄下相對路徑）> [段大小 MB，預設 8]
結果：主機 <資料夾>/<檔名>，md5 跟本機相同才算成功（結束碼 0）。
"""
import hashlib
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
src, host, rdir = sys.argv[1:4]
part_mb = int(sys.argv[4]) if len(sys.argv) > 4 else 8
SSH = r"C:\Windows\System32\OpenSSH\ssh.exe"
SCP = r"C:\Windows\System32\OpenSSH\scp.exe"
O = ["-o", "ConnectTimeout=20", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
name = os.path.basename(src)
size = os.path.getsize(src)
work = os.path.join(r"C:\Temp\putparts", name + ".parts")
os.makedirs(work, exist_ok=True)


def md5_bytes(b):
    return hashlib.md5(b).hexdigest()


def run(cmd, tries=8):
    for i in range(tries):
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return p.stdout
        time.sleep(min(30, 5 * (i + 1)))
    raise SystemExit("連續失敗：%s\n%s" % (" ".join(cmd[-2:]), p.stderr.strip()[:300]))


whole = hashlib.md5()
parts = []
with open(src, "rb") as f:
    i = 0
    while True:
        b = f.read(part_mb * 1048576)
        if not b:
            break
        whole.update(b)
        pn = "%s.p%04d" % (name, i)
        pp = os.path.join(work, pn)
        if not os.path.exists(pp) or os.path.getsize(pp) != len(b):
            open(pp, "wb").write(b)
        parts.append((pn, md5_bytes(b)))
        i += 1
want = whole.hexdigest()
print("%s %.1f MB、%d 段、md5 %s" % (name, size / 1048576, len(parts), want))
run([SSH] + O + [host, "mkdir -p %s/parts" % rdir])
# 主機上已經有、md5 對的段跳過（重跑時接著傳）
have = run([SSH] + O + [host, "cd %s/parts && md5sum %s.p* 2>/dev/null; true" % (rdir, name)])
ok = {l.split()[1]: l.split()[0] for l in have.splitlines() if len(l.split()) == 2}
t0 = time.time()
for k, (pn, pm) in enumerate(parts, 1):
    if ok.get(pn) == pm:
        continue
    for attempt in range(1, 9):
        p = subprocess.run([SCP] + O + [os.path.join(work, pn), "%s:%s/parts/%s" % (host, rdir, pn)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode == 0:
            break
        print("  第 %d 段失敗（第 %d 次）：%s" % (k, attempt, p.stderr.strip()[:80]))
        time.sleep(min(30, 5 * attempt))
    else:
        raise SystemExit("第 %d 段連續失敗，停止；VPN 回來後重跑同一個指令會接著傳" % k)
    if k % 5 == 0 or k == len(parts):
        print("  已傳 %d/%d 段（%.0f 秒）" % (k, len(parts), time.time() - t0))
out = run([SSH] + O + [host, "cd %s && cat parts/%s.p* > %s.tmp && md5sum %s.tmp" % (rdir, name, name, name)])
got = out.split()[0] if out.strip() else ""
if got != want:
    raise SystemExit("主機組回的 md5 不符：%s（應為 %s）" % (got, want))
run([SSH] + O + [host, "cd %s && mv -f %s.tmp %s && rm -f parts/%s.p*" % (rdir, name, name, name)])
print("完成：%s:%s/%s md5 一致（%.0f 秒）" % (host, rdir, name, time.time() - t0))
