"""產生「把本機公鑰佈到新機器」的單行指令（L-080）。

使用者給了 IP＋port＋帳號，要請他在自己的終端機跑一行指令佈公鑰時，一律用這支產生，不要手寫：
    python -X utf8 -I pubkey_cmd.py <IP> <PORT> <帳號> [--bind <本機 VPN 位址>]

- 公鑰整行直接寫死在指令裡（不用 $變數、不用 `cat ... |`），PowerShell、cmd、Git Bash、WSL 都能貼。
- grep -qxF 擋重複寫入，可以重跑；最後印 DONE。
- 只有走 VPN 的內網機器才加 --bind；對外 IP 不用。
- 指令只能請使用者跑（要輸入密碼）；AI 不要先自己 ssh 試、也不要代輸密碼。
"""
import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ap = argparse.ArgumentParser()
ap.add_argument('ip')
ap.add_argument('port')
ap.add_argument('user')
ap.add_argument('--bind')
ap.add_argument('--key', default=os.path.expanduser('~/.ssh/id_ed25519.pub'))
a = ap.parse_args()


def local_ipv4():
    """本機目前所有 IPv4 位址（VPN 重連後位址可能換，不能照文件寫死的值）。"""
    import socket
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return ips


if a.bind:
    ips = local_ipv4()
    if ips and a.bind not in ips:
        same_net = sorted(i for i in ips if i.rsplit('.', 1)[0] == a.bind.rsplit('.', 1)[0])
        sys.stderr.write(f'停止：--bind {a.bind} 不是本機目前的位址（本機：{", ".join(sorted(ips))}）。\n')
        if same_net:
            sys.stderr.write(f'同網段的是 {", ".join(same_net)}，VPN 重連後位址換了，改用它重跑；'
                             '或先不加 --bind，用 Test-NetConnection <IP> -Port <PORT> 確認不綁也連得到（L-196）。\n')
        else:
            sys.stderr.write('VPN 可能沒連上，請使用者先連 VPN。\n')
        sys.exit(1)
key = open(a.key, encoding='utf-8').read().strip()
assert "'" not in key and key.startswith('ssh-'), '公鑰格式不對'
bind = f'-o BindAddress={a.bind} ' if a.bind else ''
remote = (f"mkdir -p ~/.ssh; chmod 700 ~/.ssh; grep -qxF '{key}' ~/.ssh/authorized_keys 2>/dev/null "
          f"|| echo '{key}' >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; echo DONE")
print(f'ssh {bind}-p {a.port} {a.user}@{a.ip} "{remote}"')
print()
print('# 跑完印 DONE 才算成功；若出現 Permission denied 建資料夾，表示該帳號家目錄不能寫，需要管理員先建好 ~/.ssh。')
print('# 一定要貼在 Windows 的 PowerShell（開頭是 PS C:\\...>），不是 WSL（開頭是 帳號@電腦名:~$）。')
print('# 印 DONE 後 AI 馬上用 BatchMode=yes 驗證；仍被拒絕就查家目錄權限（擁有者不是該帳號、或群組可寫，sshd 會拒收金鑰，L-196）。')
