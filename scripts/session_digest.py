r"""從 Claude Code 工作階段逐字稿（~/.claude/projects/<資料夾>/<id>.jsonl）抽出「人看得懂的部分」。

用途：要補專案紀錄、回顧、查「那個工作階段做了什麼」，但它有上千則訊息（大多是工具呼叫），
用 list_events 一頁 40 則往回翻很慢、也看不出每天做了什麼。這支腳本直接讀 jsonl：

  python -X utf8 -I session_digest.py days  <jsonl>                 # 每天幾則、使用者講了幾句
  python -X utf8 -I session_digest.py text  <jsonl> <起> [<迄>] [--max N]
        # 列出 <起>～<迄>（UTC ISO 字串前綴，例 2026-10-22 或 2026-11-03T08:00）之間
        # 使用者與助理的文字訊息（略過工具呼叫、技能全文、task-notification、Stop hook 提示）
  python -X utf8 -I session_digest.py user  <jsonl> [<起>]          # 只列使用者的話（每句截 300 字）

注意：
- 時間是 UTC，台灣時間要 +8 小時（09:19Z = 17:19）。寫進紀錄前換算。
- 對話壓縮後的「This session is being continued…」摘要也會列出，它整理了之前的決定與數字，很好用，
  但仍要對照原始訊息或 git log 確認。
- 逐字稿裡可能有使用者貼的密碼、個資：只拿來理解，不抄進紀錄。
- 找 jsonl：工作階段的 cwd 把 `:` `\` `/` `_` 換成 `-` 就是資料夾名（例 D:\work\repo → D--work-repo），
  資料夾裡最大、最近修改的通常就是那個工作階段。
"""
import json
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

SKIP_PREFIX = ('Base directory for this skill', '<task-notification', 'Stop hook feedback',
               '<system-reminder', '(Re-invocation of /')


def texts(o):
    c = o.get('message', {}).get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return '\n'.join(b.get('text', '') for b in c
                         if isinstance(b, dict) and b.get('type') == 'text' and b.get('text', '').strip())
    return ''


def rows(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get('type') not in ('user', 'assistant') or o.get('isSidechain'):
                continue
            yield o


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    mode, path = sys.argv[1], sys.argv[2]
    args = [a for a in sys.argv[3:] if not a.startswith('--')]
    maxlen = 4000
    if '--max' in sys.argv:
        maxlen = int(sys.argv[sys.argv.index('--max') + 1])
        args = [a for a in args if a != str(maxlen)]
    start = args[0] if args else ''
    end = args[1] if len(args) > 1 else '9999'

    if mode == 'days':
        allc, userc = Counter(), Counter()
        for o in rows(path):
            d = o.get('timestamp', '')[:10]
            allc[d] += 1
            t = texts(o).strip()
            if o['type'] == 'user' and t and not t.startswith(SKIP_PREFIX):
                userc[d] += 1
        for d in sorted(allc):
            print(f'{d}  全部 {allc[d]:5d}  使用者文字 {userc[d]:3d}')
        return 0

    for o in rows(path):
        ts = o.get('timestamp', '')
        if not (start <= ts < end):
            continue
        t = texts(o).strip()
        if not t or t.startswith(SKIP_PREFIX):
            continue
        if mode == 'user':
            if o['type'] == 'user':
                print(ts[:19], '|', t[:300].replace('\n', ' / '))
        elif mode == 'text':
            print(f'### [{o["type"]}] {ts[:19]}Z')
            print(t[:maxlen])
            print()
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
