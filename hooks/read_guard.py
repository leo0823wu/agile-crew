"""PreToolUse hook（Read）：擋掉「整份讀」踩坑表、回顧紀錄、改版紀錄、盤點清單（L-229）。

這幾個檔很長（一份 3～10 萬 token），規則寫了「依索引只讀相關段落」仍一週被整份讀二十幾次，所以改成自動擋。
算這次 Read 實際會讀進來的字數（照 offset／limit），超過上限就擋；讀一小段不擋。

擋下＝exit 2，stderr 的說明會回給 Claude。腳本自己出錯一律放行（exit 0）。
上限 2 萬字是量過各檔的節才定的：踩坑表最大的一節約 1.7 萬字讀得到，整份（3～9 萬字）讀不到。
設定：<本地>/config.json 的 "read_guard": {"max_chars": 20000}；設成 false 可關。
測試：python -X utf8 -I test_read_guard.py
"""
import json
import os
import sys

MAX_CHARS = 20000
DEFAULT_LIMIT = 2000
# 檔名 → 該怎麼讀
FILES = {
    "retro-log.md": "要看最近幾列用 scripts/retro_tail.py；要加一列：Grep `^\\| 日期` 拿表頭的行號，Read 帶 offset＝那一行、limit 2 只讀表頭，再用 Edit 插在表頭下面第一列。",
    "skill-changelog.md": "要查某次改版用 Grep 找日期或關鍵字拿行號，再 Read 帶 offset＋limit 只讀那幾列；要加一列：Grep `^\\| 日期` 拿表頭的行號，Read 帶 offset＝那一行、limit 2，再 Edit。",
    "lessons-tech.md": "先看 lessons.md 的索引找段落代號（T1～T7），Grep 段落標題或編號（L-xxx）拿行號，再 Read 帶 offset＋limit 只讀那一段。",
    "lessons-workflow.md": "再犯最多的已在技能主檔〈必守規則〉；其餘 Grep 段落標題（W1～W6）或編號（L-xxx）拿行號，再 Read 帶 offset＋limit 只讀那一段。",
    "lessons-local.md": "Grep 編號或系統、主機關鍵字拿行號，再 Read 帶 offset＋limit 只讀那幾列。",
    "edge-case-checklist.md": "先 Grep `^## ` 看有哪幾節，再 Read 帶 offset＋limit 只讀跟這次有關的節。",
}


def span_chars(path, offset, limit):
    """這次 Read 會讀進來的字數。"""
    start = max(int(offset or 1), 1) - 1
    n = DEFAULT_LIMIT if limit is None else int(limit)
    total = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i < start:
                continue
            if i >= start + n:
                break
            total += len(line)
    return total


def problem(tool_input, max_chars=MAX_CHARS):
    path = str(tool_input.get("file_path") or "")
    name = os.path.basename(path.replace("\\", "/")).lower()
    low = path.replace("\\", "/").lower()
    if name not in FILES or not ("agile-crew" in low or "dev-team" in low):   # 舊名：相容用的連結
        return ""
    if not os.path.isfile(path):
        return ""
    chars = span_chars(path, tool_input.get("offset"), tool_input.get("limit"))
    if chars <= max_chars:
        return ""
    return ("已擋下（自動檢查）：這次 Read 會從 %s 讀進約 %.1f 萬字（上限 %.0f 萬字）。這個檔不整份讀，每多讀一次之後每一步都要重帶。\n"
            "%s\n真的需要整份內容（例：整理、搬移）時，分段讀（每段不超過上限）或交給子代理，主對話只收結論。"
            % (name, chars / 10000.0, max_chars / 10000.0, FILES[name]))


def settings():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        import projlib
        cfg = projlib.config().get("read_guard")
    except Exception:
        cfg = None
    if cfg is False:
        return None
    cfg = cfg if isinstance(cfg, dict) else {}
    return int(cfg.get("max_chars") or MAX_CHARS)


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
    if data.get("tool_name") != "Read":
        return 0
    mx = settings()
    if mx is None:
        return 0
    msg = problem(data.get("tool_input") or {}, mx)
    if msg:
        sys.stderr.buffer.write(msg.encode("utf-8"))
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
