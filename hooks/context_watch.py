"""UserPromptSubmit hook：對話累積太長時提醒一次（L-229：對話越長，每一步都要把前面全部內容重帶一次）。

從工作階段紀錄檔的尾端找最後一則回覆的 context 大小（輸入＋寫快取＋讀快取）。
超過門檻（預設 30 萬）提醒一次，之後每再多一段（預設 10 萬）再提醒一次；摘要後掉回門檻以下就重新計。
提醒同時給使用者（systemMessage）與 Claude（additionalContext：先講一句，換一件事就先寫交接再開新的）。

任何錯誤都安靜結束（exit 0），不能擋住使用者送出訊息。
設定：<本地>/config.json 的 "context_watch": {"warn": 300000, "step": 100000}；設成 false 可關。
測試：python -X utf8 -I test_context_watch.py
"""
import json
import os
import sys
import tempfile

WARN = 300000
STEP = 100000
TAIL_BYTES = 4 * 1024 * 1024


def last_context(path, tail_bytes=TAIL_BYTES):
    """紀錄檔最後一則主對話回覆的 context 大小；找不到回 0。只讀檔尾，大檔也快。"""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > tail_bytes:
            f.seek(size - tail_bytes)
            f.readline()  # 丟掉被切到一半的那一行
        lines = f.read().split(b"\n")
    for raw in reversed(lines):
        if b'"usage"' not in raw:
            continue
        try:
            o = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        u = (o.get("message") or {}).get("usage") or {}
        c = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
        if c:
            return c
    return 0


def level(ctx, warn=WARN, step=STEP):
    return 0 if ctx < warn else 1 + int((ctx - warn) // max(step, 1))


def settings():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        import projlib
        cfg = projlib.config().get("context_watch")
    except Exception:
        cfg = None
    if cfg is False:
        return None
    cfg = cfg if isinstance(cfg, dict) else {}
    return int(cfg.get("warn") or WARN), int(cfg.get("step") or STEP)


def build(transcript_path, session_id, warn=WARN, step=STEP, state_dir=None):
    """要提醒就回 (給使用者的話, 給 Claude 的話)，不用提醒回 None。"""
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    ctx = last_context(transcript_path)
    lv = level(ctx, warn, step)
    state_dir = state_dir or os.path.join(tempfile.gettempdir(), "dev-team-context-watch")
    os.makedirs(state_dir, exist_ok=True)
    state = os.path.join(state_dir, "".join(ch for ch in (session_id or "nosession") if ch.isalnum() or ch in "-_")[:80] + ".txt")
    try:
        done = int(open(state, encoding="utf-8").read().strip() or 0) if os.path.exists(state) else 0
    except ValueError:
        done = 0
    if lv == done:
        return None
    with open(state, "w", encoding="utf-8") as f:
        f.write(str(lv))
    if lv < done:      # 摘要後變短：只把紀錄降回去，不提醒
        return None
    wan = ctx / 10000.0
    user = "這個對話已經累積約 %.0f 萬 token，之後每問一句都要把這些重帶一次。要換一件事時，建議開新的工作階段。" % wan
    claude = ("【對話長度提醒（hook 自動量）】這個工作階段的 context 約 %.0f 萬 token，每一步都會重帶。"
              "回覆開頭先用一句話告訴使用者這件事。接著判斷使用者這句話：換一件不相關的事、或同一件事已經告一段落 → "
              "先照〈一件事一個工作階段〉寫好交接（專案紀錄的目前狀況、待辦、工作進度、這次的決定），再建議開新的工作階段；"
              "同一件事還在來回修改 → 講完那一句就繼續做，不用停。讀大量內容的工作改交給子代理，主對話只收結論。" % wan)
    return user, claude


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        st = settings()
        if st is None:
            return 0
        res = build(data.get("transcript_path") or "", data.get("session_id") or "", st[0], st[1])
        if res:
            out = {"systemMessage": res[0],
                   "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": res[1]}}
            sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
