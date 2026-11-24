"""比對兩份 .class（或兩個 class 資料夾）的指令有沒有差，用在「逐檔換 class」上線前（L-073、L-137）。

用法：
  python -X utf8 -I class_diff.py <正式機的.class> <新編的.class>
  python -X utf8 -I class_diff.py <正式機 classes 資料夾> <新編 classes 資料夾>   # 逐檔比，列出相同／不同／只有一邊
  python -X utf8 -I class_diff.py "<正式的.jar或.war>!<封存檔內資料夾>" <新編 classes 資料夾>
      # 例："deploy/app.jar!BOOT-INF/classes/com/x/impl"：新資料夾裡有哪些類別，就只從封存檔取同名的（含 $1、$2 內部類別），
      # 不用另寫解壓或 md5 比對腳本（2026-11-10 又各寫了一支才補這個用法）
資料夾比對會多印「位元組不同（要換）」：指令相同、只有行號表不同的也要一起換，不然 log 的行號對不上。

做法：
- 先把檔案複製到英文暫存路徑再給 javap（javap 讀中文路徑會輸出空白，兩邊空對空會報相同）。
- javap 結束碼不是 0、或輸出裡沒有 class 宣告 → 直接中止，不往下比。
- 正規化後才比：常數池編號、指令位移、跳躍目標、例外表、ldc_w/ldc、對齊空白。
  這些在不同電腦或不同 JDK 編同一份原始碼時會不一樣，不正規化會報一堆假差異。
- 結束碼：0 = 指令完全相同；1 = 有差（印出差異，自己確認每一處都是這次要改的）；2 = 工具錯誤。
"""
import difflib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


def javap(path, tmp):
    dst = os.path.join(tmp, 'c%d.class' % len(os.listdir(tmp)))
    shutil.copyfile(path, dst)
    r = subprocess.run(['javap', '-c', '-p', dst], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0 or not re.search(r'\b(class|interface|enum)\s+[\w.$]+', r.stdout):
        print('javap 失敗或沒有輸出（%s）：%s' % (path, (r.stderr or r.stdout)[:300]), file=sys.stderr)
        sys.exit(2)
    return r.stdout


def normalize(text):
    out = []
    for line in text.splitlines():
        if line.startswith('Compiled from'):
            continue
        line = re.sub(r'#\d+(\.\d+)?', '#', line)                         # 常數池編號
        line = re.sub(r'^\s*\d+: ', '', line)                              # 指令位移
        line = re.sub(r'\b(goto(_w)?|if\w*|jsr(_w)?)\s+\d+', r'\1 L', line)  # 跳躍目標
        line = re.sub(r'\bldc(_w|2_w)?\b', 'ldc', line)
        line = re.sub(r'^\s*\d+\s+\d+\s+\d+\s+(Class|any)\b.*$', '', line)  # 例外表
        line = re.sub(r'^\s*(-?\d+|default): \d+$', '', line)               # switch 表
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            out.append(line)
    return out


def diff_file(a, b, tmp, label=None):
    na, nb = normalize(javap(a, tmp)), normalize(javap(b, tmp))
    d = list(difflib.unified_diff(na, nb, 'old/' + (label or a), 'new/' + (label or b), n=1, lineterm=''))
    return d


def base_name(rel):
    return rel.rsplit('.', 1)[0].split('$')[0]


def from_archive(spec, newdir, dst):
    """<jar/war>!<資料夾>：只取新資料夾裡出現的類別（外層名稱相同的內部類別一起取），解到 dst。"""
    arc, prefix = spec.split('!', 1)
    prefix = prefix.strip('/') + '/'
    bases = {base_name(f) for f in os.listdir(newdir) if f.endswith('.class')}
    n = 0
    with zipfile.ZipFile(arc) as z:
        for name in z.namelist():
            rel = name[len(prefix):] if name.startswith(prefix) else ''
            if not rel.endswith('.class') or '/' in rel or base_name(rel) not in bases:
                continue
            with open(os.path.join(dst, rel), 'wb') as f:
                f.write(z.read(name))
            n += 1
    if n == 0:
        print('封存檔 %s 的 %s 底下找不到新資料夾裡的類別，路徑寫錯？' % (arc, prefix), file=sys.stderr)
        sys.exit(2)
    return dst


def compiler_mismatch(diff_lines):
    """一邊 StringBuilder 串接、一邊 makeConcatWithConstants：兩邊是不同編譯器（ECJ 對 javac），不是程式改動。"""
    side = lambda sign, key: any(l.startswith(sign) and key in l for l in diff_lines)
    return (side('-', 'StringBuilder') and side('+', 'makeConcatWithConstants')) or \
           (side('-', 'makeConcatWithConstants') and side('+', 'StringBuilder'))


MSG_COMPILER = ('⚠ 有差異是編譯器不同造成的（一邊 StringBuilder 串接、一邊 makeConcatWithConstants）：'
                '正式機多半是 Eclipse（ECJ）編的、本機是 javac。這類差異不是程式改動，'
                '用跟正式機同一種編譯器重編再比（ECJ 做法見 lessons-tech L-137）')


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = sys.argv[1], sys.argv[2]
    tmp = tempfile.mkdtemp(prefix='class_diff_')
    try:
        if '!' in a and os.path.isfile(a.split('!', 1)[0]):
            if not os.path.isdir(b):
                sys.exit('第一個參數是封存檔時，第二個參數要是新編的 classes 資料夾')
            a = from_archive(a, b, tempfile.mkdtemp(prefix='class_diff_arc_', dir=tmp))
        if os.path.isfile(a) and os.path.isfile(b):
            d = diff_file(a, b, tmp)
            print('\n'.join(d) if d else '指令完全相同')
            if compiler_mismatch(d):
                print(MSG_COMPILER)
            return 1 if d else 0
        if not (os.path.isdir(a) and os.path.isdir(b)):
            sys.exit('兩個參數要都是 .class 檔，或都是資料夾')
        rel = lambda root: {os.path.relpath(os.path.join(dp, f), root).replace('\\', '/')
                            for dp, _, fs in os.walk(root) for f in fs if f.endswith('.class')}
        ra, rb = rel(a), rel(b)
        same, changed = [], []
        for r in sorted(ra & rb):
            d = diff_file(os.path.join(a, r), os.path.join(b, r), tmp, r)
            (changed if d else same).append((r, d))
        for r, d in changed:
            print('\n'.join(d))
        raw = [r for r in sorted(ra & rb) if open(os.path.join(a, r), 'rb').read() != open(os.path.join(b, r), 'rb').read()]
        print('位元組不同（要換）：%s' % ('、'.join(raw) if raw else '無'))
        print('相同 %d、不同 %d、只有舊的 %d、只有新的 %d' % (len(same), len(changed), len(ra - rb), len(rb - ra)))
        for r in sorted(ra - rb):
            print('  只有舊的：' + r)
        for r in sorted(rb - ra):
            print('  只有新的：' + r)
        by_compiler = [r for r, d in changed if compiler_mismatch(d)]
        if by_compiler:
            print(MSG_COMPILER + '（%d 個檔）' % len(by_compiler))
        return 1 if changed or ra != rb else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
