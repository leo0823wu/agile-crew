"""Stop hook 入口：讀一次工作階段紀錄，跑兩個收尾檢查，要擋就合成一個理由。

- 團隊回顧（retro_gate.py）：最後一次 git push 之後沒改過回顧紀錄 → 要先做回顧
- 專案紀錄（record_gate.py）：交付的這一輪改了專案、紀錄卻沒更新 → 要先更新紀錄

合成一個入口的原因：兩支 hook 各讀一次紀錄（最大的紀錄檔 190 MB）會讓每次停下慢好幾秒；
而且兩支同時擋時，兩個理由是否都會送到 Claude 沒有把握，合成一個理由最保險。
兩支也都還能單獨執行（各自的測試照舊）。續跑（stop_hook_active）時回顧檢查放行；紀錄檢查只在這一段還沒被它擋過時才判斷
（被回顧檢查逼出來補寫的回顧，寫了哪個專案、紀錄沒更新，也要擋得到），所以不會卡死。任何錯誤一律放行。
測試：python -I ~/.claude/skills/dev-team/hooks/test_stop_gate.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import record_gate  # noqa: E402
import retro_gate  # noqa: E402
import transcript as T  # noqa: E402

RETRO_ALSO = "回顧那一列「專案／這輪」開頭寫專案名稱；那個專案的專案紀錄也要一起更新（「工作進度」加一列、這次的發現補進「遇到的問題」）。"


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    active = bool(data.get("stop_hook_active"))
    path = data.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0
    events = T.session_events(path, results=False)
    reasons = []
    if not active:      # 回顧檢查照舊：被擋過一次（續跑）就放行
        try:
            mine = ((e.name, e.inp) for e in events if e.kind == "tool" and not e.side)
            if retro_gate.needs_retro_from(mine):
                reasons.append(retro_gate.REASON + RETRO_ALSO)
        except Exception:
            pass
    try:
        # 紀錄檢查在續跑時也跑一次（這一段還沒被它擋過才會擋），補寫的回顧寫了哪個專案、紀錄沒更新也擋得到
        text = record_gate.check(events, path, active=active)
        if text:
            reasons.append(text)
    except Exception:
        if os.environ.get("RECORD_GATE_DEBUG"):
            import traceback
            traceback.print_exc()
    if reasons:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"decision": "block", "reason": "\n\n".join(reasons)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
