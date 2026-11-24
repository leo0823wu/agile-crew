"""讀 Claude Code 工作階段紀錄（jsonl）的共用工具：stop_gate.py、record_gate.py、scripts/round_time.py 用。

紀錄檔可能上百 MB，所以先用字串過濾掉不需要的列再解析：
- 以 {"type":"api-request…"} 等開頭的列不是對話內容。api-request-blob 會把**舊訊息重放一次、而且沒有時間戳**，
  當成對話讀會把很久以前的 git push 當成剛發生（2026-11-05 PM 盤點：102 個紀錄檔有 41 個有這種列）。
- resume／fork 出來的新紀錄檔會帶著舊工作階段的歷史（sessionId 是舊的）；要只看自己的，傳 session_id。
事件（Event）種類：
- human  ：真人送出的訊息（type=user、origin.kind == "human"；別的工作階段開的 side session 的第一則也算）
- notify ：不是真人開的一輪（背景工作完成通知 task-notification、別的工作階段傳來的訊息 peer…），text 放前 300 字
- tool   ：工具呼叫（assistant 內容的 tool_use），name、inp、tid（tool_use id）
- result ：工具結果（user 內容的 tool_result），tid 是對應的 tool_use id（results=False 時不讀，快很多）
- text   ：Claude 給使用者看的文字（assistant 內容的 text），text 放前 300 字
- stop   ：一輪結束（system / stop_hook_summary）
- hookfb ：Stop hook 擋下的回饋（"Stop hook feedback:"，text 放全文）。真實紀錄的順序是「hookfb → stop」：
           **緊接在 stop 前面**＝那次停下被擋，下一輪是續跑（hook 收到 stop_hook_active）。（2026-11-05 QA 抓到：原本寫成在後面）
子代理（Agent）的紀錄在 `<紀錄檔去掉 .jsonl>/subagents/agent-*.jsonl`，side=True。sid＝那一列的 sessionId。
只讀不寫；解析不了的列安靜跳過。
"""
import datetime
import glob
import json
import os
import re
from collections import namedtuple

Event = namedtuple("Event", "kind ts cwd name inp tid uuid side text sid")

_SKIP = re.compile(r'^\{"type":\s*"(?:api-request|queue-operation|custom-title|file-history|last-prompt|atis|mode|'
                   r'agent-name|bridge-session|cost-state|tools-used|summary|attachment)')
_KEEP = re.compile(r'"type":\s*"(?:user|assistant)"|stop_hook_summary')


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _user_kind(d, content):
    text = content if isinstance(content, str) else ""
    if isinstance(content, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return None
        text = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    t = text.lstrip()
    if t.startswith("Stop hook feedback"):    # Stop hook 擋下後要求繼續（下一輪是續跑，hook 收到 stop_hook_active）
        return "hookfb"
    if d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly"):
        return None                           # 上下文壓縮後的接續摘要不是真人訊息（QA 2026-11-05 抓到）
    origin = d.get("origin") or {}
    kind = origin.get("kind")
    if kind == "human":
        return "human"
    if kind:
        return "notify"
    if d.get("isMeta"):
        return None
    # 舊版紀錄沒有 origin：字串內容、不是系統插入的標籤，就當真人
    if t.startswith("<task-notification>"):
        return "notify"
    if "session that started this one" in t:   # 別的工作階段開的 side session：第一則就是需求
        return "human"
    if t.startswith("<") or not t:
        return None
    return "human"


def _events_from_line(d, side):
    t = d.get("type")
    ts = parse_ts(d.get("timestamp"))
    cwd = d.get("cwd") or ""
    uuid = d.get("uuid") or ""
    sid = d.get("sessionId") or ""
    if t == "system":
        if d.get("subtype") == "stop_hook_summary" and not side:
            yield Event("stop", ts, cwd, "", None, "", uuid, side, "", sid)
        return
    msg = d.get("message")
    if not isinstance(msg, dict):
        return
    content = msg.get("content")
    if t == "user":
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    yield Event("result", ts, cwd, "", None, c.get("tool_use_id") or "", uuid, side, "", sid)
        if side:
            return
        kind = _user_kind(d, content)
        if kind:
            text = content if isinstance(content, str) else " ".join(
                c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            yield Event(kind, ts, cwd, "", None, "", uuid, side, text[:4000] if kind == "hookfb" else text[:300], sid)
    elif t == "assistant" and isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                yield Event("tool", ts, cwd, c.get("name") or "", c.get("input") or {}, c.get("id") or "",
                            uuid, side, "", sid)
            elif c.get("type") == "text" and not side:
                yield Event("text", ts, cwd, "", None, "", uuid, side, (c.get("text") or "")[:300], sid)


def _wanted(line, results):
    """先判斷要不要解析這一列（大檔的速度關鍵：以位元組讀、只看開頭 800 位元組、用 in 找，不用正則掃整列；
    190 MB 的紀錄從 5～6 秒降到約 1.6 秒）。line 是 bytes。"""
    head = line[:800]
    if b'": "' in head:                     # 有空格的 JSON（測試資料）：解碼後用正則判斷
        text = line.decode("utf-8", "replace")
        return not _SKIP.match(text) and bool(_KEEP.search(text)) and (
            results or '"tool_result"' not in text or '"tool_use"' in text)
    if head.startswith(b'{"type":"') and _SKIP.match(head.decode("utf-8", "replace")):
        return False
    if b'"content":[{"type":"thinking"' in head:
        return False                        # 只有思考內容的列
    if b'"type":"user"' in head:
        return results or b'"type":"tool_result"' not in head
    if b"stop_hook_summary" in head:
        return True
    return b'"type":"assistant"' in line


def read_events_from_lines(lines, side=False, results=True, session_id=None):
    """逐列解析（lines 是 bytes 或 str 都可以）；同一個 uuid 只算一次。
    results=False：跳過純工具結果的列（通常佔檔案大部分）。"""
    seen = set()
    for line in lines:
        if isinstance(line, str):
            line = line.encode("utf-8", "replace")
        if not _wanted(line, results):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("isSidechain") and not side:
            continue
        if session_id and d.get("sessionId") and d.get("sessionId") != session_id:
            continue
        for e in _events_from_line(d, side):
            key = (e.uuid, e.kind, e.tid)
            if e.uuid and key in seen:
                continue
            seen.add(key)
            yield e


def read_events(path, side=False, results=True, session_id=None):
    with open(path, "rb") as f:
        return list(read_events_from_lines(f, side, results, session_id))


def subagent_files(path):
    stem = path[:-6] if path.endswith(".jsonl") else path
    return sorted(glob.glob(os.path.join(stem, "subagents", "*.jsonl")))


def session_events(path, with_subagents=True, results=True, own_only=False):
    """主紀錄＋子代理紀錄合併。主紀錄維持檔案順序；子代理的工具呼叫依時間插進主紀錄（只用來找改檔）。
    own_only：只留這個工作階段自己的列（sessionId＝檔名），不含 resume／fork 帶過來的舊歷史。"""
    sid = os.path.basename(path)[:-6] if own_only and path.endswith(".jsonl") else None
    main = read_events(path, results=results, session_id=sid)
    if not with_subagents:
        return main
    side = []
    for p in subagent_files(path):
        side += [e for e in read_events(p, side=True, results=False) if e.kind == "tool"]
    if not side:
        return main
    side.sort(key=lambda e: e.ts or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    out, i = [], 0
    for e in main:
        while i < len(side) and e.ts and side[i].ts and side[i].ts <= e.ts:
            out.append(side[i])
            i += 1
        out.append(e)
    out += side[i:]
    return out
