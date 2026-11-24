"""核對「照本機底稿建到 Notion 的頁面」有沒有走樣（L-240、L-250）。

用法：python -X utf8 -I check_notion_pages.py <底稿資料夾> <對話紀錄 jsonl> [更多 jsonl ...]

底稿資料夾：一頁一個 .md，第一行「# 標題」是 Notion 頁面標題，第二行以後是內容。
對話紀錄：建頁面的那個工作階段或子代理的 jsonl（子代理的在
  ~/.claude/projects/<專案>/<工作階段 id>/subagents/agent-<id>.jsonl；Agent 工具回傳的 output_file 可能是空的）。
後面的 jsonl 蓋過前面的，所以修正後重抓的那份紀錄放最後。

從紀錄裡找出：
  1. notion-create-pages 送出去的 title 與 content → 跟底稿逐字比
  2. notion-fetch 抓回來的頁面文字 → 底稿每一段連續中文（6 字以上）都要找得到；
     列出 Notion 多出來、底稿沒有的中文字（手寫跳脫碼造成的錯字）；列出沒生效的粗體（頁面上出現字面的反斜線加星號）
每份底稿印一行結果，最後印總結。有任何一份沒對上，結束碼是 1。
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

cards_dir = sys.argv[1]
logs = sys.argv[2:]

cards = {}
for name in sorted(os.listdir(cards_dir)):
    if not name.endswith(".md"):
        continue
    text = open(os.path.join(cards_dir, name), encoding="utf-8").read().replace("\r\n", "\n")
    first, _, body = text.partition("\n")
    cards[first.lstrip("# ").strip()] = {"file": name, "body": body.strip(), "full": text}


def walk(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def result_text(content):
    if isinstance(content, str):
        return content
    out = []
    for part in content or []:
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text", ""))
    return "\n".join(out)


sent = {}      # title -> content 送出去的
fetch_ids = {}  # tool_use_id -> True
fetched = {}   # title -> 抓回來的文字
for log in logs:
    for line in open(log, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for node in walk(rec):
            t = node.get("type")
            if t == "tool_use" and "notion-create-pages" in str(node.get("name", "")):
                pages = (node.get("input") or {}).get("pages") or []
                if isinstance(pages, str):
                    try:
                        pages = json.loads(pages)
                    except Exception:
                        pages = []
                for p in pages:
                    title = ((p.get("properties") or {}).get("title") or "").strip()
                    sent[title] = (p.get("content") or "").replace("\r\n", "\n").strip()
            elif t == "tool_use" and "notion-fetch" in str(node.get("name", "")):
                fetch_ids[node.get("id")] = True
            elif t == "tool_result" and node.get("tool_use_id") in fetch_ids:
                raw = result_text(node.get("content"))
                try:
                    data = json.loads(raw)
                    title, text = (data.get("title") or "").strip(), data.get("text") or ""
                except Exception:
                    title, text = "", raw
                if not title:
                    for k in cards:
                        if k in raw[:600]:
                            title = k
                if title:
                    fetched[title] = text

cjk = re.compile(r"[一-鿿　-〿＀-￯]{6,}")
bad = 0
for title, card in cards.items():
    notes = []
    if title not in sent:
        notes.append("沒找到送出的紀錄")
    elif sent[title] != card["body"]:
        a, b = card["body"], sent[title]
        i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
        notes.append("送出內容跟本機不同（第 %d 字起）本機「%s」送出「%s」" % (i, a[max(0, i - 12):i + 12].replace("\n", "⏎"), b[max(0, i - 12):i + 12].replace("\n", "⏎")))
    if title not in fetched:
        notes.append("沒找到抓回來的紀錄")
    else:
        notion = fetched[title]
        missing = [run for line in card["body"].splitlines() for run in cjk.findall(line) if run not in notion]
        extra = sorted({c for c in notion if "一" <= c <= "鿿" and c not in card["full"]})
        if missing:
            notes.append("Notion 找不到的片段 %d 個，例：%s" % (len(missing), "／".join(missing[:3])))
        if extra:
            notes.append("Notion 多出來的字：%s" % "".join(extra))
        star = "\\" + "*"  # Notion 把沒生效的粗體記號存成 \*
        if star in notion:
            pos = [m.start() for m in re.finditer(re.escape(star + star), notion)]
            notes.append("粗體沒生效 %d 處，例：%s" % (len(pos), "／".join(notion[p:p + 16].replace("\n", "⏎") for p in pos[:3])))
    # 送出時有錯、但最後抓回來的內容已經對上（事後在 Notion 修過）→ 只提示，不算有問題
    if len(notes) == 1 and notes[0].startswith("送出內容跟本機不同") and title in fetched:
        print("✓ " + card["file"] + "\n    （提示：第一次送出時有錯，最後抓回來的內容已對上）")
        continue
    if notes:
        bad += 1
    print(("✗ " if notes else "✓ ") + card["file"] + ("" if not notes else "\n    " + "\n    ".join(notes)))

print("\n底稿 %d 份，對上 %d 份，有問題 %d 份；紀錄裡送出 %d 頁、抓回 %d 頁" % (len(cards), len(cards) - bad, bad, len(sent), len(fetched)))
sys.exit(1 if bad else 0)
