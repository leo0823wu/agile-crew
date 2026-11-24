"""檢查給沒學過的人看的知識文件（教材）夠不夠「看得懂」。

用法：
    python -X utf8 -I check_knowledge_doc.py <文件.md> [--skip 11,12] [--min-lines 6]

檢查項目：
1. 開頭有「讀完能做到什麼」。
2. 每個編號章節（「## 1. xxx」）裡有一個標題含「實際走一遍」的小節，
   而且那一小節至少有 --min-lines 行內容（表格列、編號步驟、段落都算）。
   名詞表、資料來源這類章節自動略過；其他不需要的章節用 --skip 指定編號。

為什麼：只放一張比較表或一句比喻，讀者看得到名詞，卻不知道實際怎麼運作。
每個概念都要有「具體的人、具體的資料、一步一步走到結果」的例子。
"""
import re
import sys

SKIP_WORDS = ('名詞表', '資料來源', '目錄', '讀完能做到什麼')


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    skip = set()
    min_lines = 6
    if '--skip' in args:
        skip = {s.strip() for s in args[args.index('--skip') + 1].split(',') if s.strip()}
    if '--min-lines' in args:
        min_lines = int(args[args.index('--min-lines') + 1])

    text = open(path, encoding='utf-8').read()
    lines = text.splitlines()
    problems = []

    if '讀完能做到什麼' not in text:
        problems.append('開頭沒有「讀完能做到什麼」')

    # 切出編號章節
    sections = []
    cur = None
    for line in lines:
        m = re.match(r'^##\s+(\d+)\.\s*(.+)$', line)
        if m:
            cur = {'no': m.group(1), 'title': m.group(2).strip(), 'body': []}
            sections.append(cur)
            continue
        if re.match(r'^##\s', line):
            cur = None
            continue
        if cur is not None:
            cur['body'].append(line)

    if not sections:
        problems.append('找不到「## 1. 標題」這種編號章節，無法檢查')

    checked = 0
    for s in sections:
        if s['no'] in skip or any(w in s['title'] for w in SKIP_WORDS):
            continue
        checked += 1
        body = s['body']
        idx = [i for i, l in enumerate(body) if re.match(r'^###\s', l) and '實際走一遍' in l]
        if not idx:
            problems.append('第 %s 節〈%s〉沒有「實際走一遍」小節' % (s['no'], s['title']))
            continue
        start = idx[0] + 1
        end = next((i for i in range(start, len(body)) if re.match(r'^###\s', body[i])), len(body))
        content = [l for l in body[start:end] if l.strip() and not re.match(r'^\|[-|\s]+\|$', l.strip())]
        if len(content) < min_lines:
            problems.append('第 %s 節〈%s〉的「實際走一遍」只有 %d 行，少於 %d 行'
                            % (s['no'], s['title'], len(content), min_lines))

    print('檢查了 %d 節（略過：%s）' % (checked, '、'.join(sorted(skip)) or '無'))
    if problems:
        print('不通過：')
        for p in problems:
            print('  - ' + p)
        return 1
    print('通過')
    return 0


if __name__ == '__main__':
    sys.exit(main())
