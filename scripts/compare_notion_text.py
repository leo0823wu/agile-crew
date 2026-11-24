"""比對 Notion 抓回來的內容和本機底稿：底稿裡每一段連續中文（6 字以上）都要在 Notion 找得到；
另外列出 Notion 裡出現、底稿沒有的字（抓手寫轉義造成的錯字）。"""
import json
import re
import sys

md_path, notion_path = sys.argv[1], sys.argv[2]
md = open(md_path, encoding='utf-8').read()
raw = open(notion_path, encoding='utf-8').read()
try:
    notion = json.loads(raw)['text']
except Exception:
    notion = raw

cjk = re.compile(r'[一-鿿　-〿＀-￯]{6,}')
missing = []
for i, line in enumerate(md.splitlines(), 1):
    for run in cjk.findall(line):
        if run not in notion:
            missing.append((i, run))

md_chars = set(md)
extra = sorted({c for c in notion if '一' <= c <= '鿿' and c not in md_chars})

print('底稿有、Notion 找不到的中文片段：%d' % len(missing))
for i, run in missing[:80]:
    print('  第 %d 行：%s' % (i, run))
print('Notion 有、底稿沒有的中文字：%s' % (''.join(extra) or '無'))
