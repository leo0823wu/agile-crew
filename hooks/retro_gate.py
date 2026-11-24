"""Stop hook：交付後沒做團隊回顧就擋下結束。

判斷（只看這個工作階段的對話紀錄）：
- 「交付」＝ Bash／PowerShell 執行了 git push（推上遠端就算交付一次）。
- 「回顧」＝ 之後有用 Edit／Write 改過回顧紀錄 `<本地>/retro-log.md`（或指令裡寫到它的檔案操作）。
  改技能的流程文件 `retro.md` 不算（那是做法，不是紀錄）。
- 最後一次 push 之後沒有回顧 → 擋下（decision: block），請 Claude 照 retro.md 做完並加一列再結束。
- 已經被這個 hook 擋過一次（stop_hook_active）就放行，避免卡死；腳本自己出錯也一律放行。

真的不需要回顧時（例：只推了一個錯字修正），在 retro-log.md 加一列「這次沒有要改的，因為…」即可。
測試：python -I ~/.claude/skills/dev-team/hooks/test_retro_gate.py
"""
import json
import re
import sys

PUSH = re.compile(r"(?:^|[\s;&|(])git(?:\.exe)?\s+(?:-C\s+\S+\s+|--no-optional-locks\s+)*push\b")
RETRO = re.compile(r"retro-log\.md", re.IGNORECASE)

REASON = (
    "這個工作階段在最後一次 git push 之後還沒做團隊回顧（dev-team 第 8 步）。結束前請照 "
    "~/.claude/skills/dev-team/references/retro.md 做：先對上一輪 ⏳ 行動項與待驗證的技能改版、查有沒有違反既有 lessons（再犯欄 +1）、"
    "量指標、回答四題，把每個發現直接改成技能（通用的寫進技能、個人／公司的寫進本地，見 shareable.md），"
    "最後用 Edit 在本地資料夾的 retro-log.md〈回顧紀錄〉加一列。"
    "如果這次真的沒有要改的，也加一列寫明「這次沒有要改的，因為…」。"
)


def tool_uses(path):
    """依序回傳 (工具名稱, input dict)。只看這個工作階段 Claude 自己的呼叫：
    api-request-blob 列會把舊訊息重放一次（很久以前的 git push 會被當成剛發生），子代理（sidechain）也不算。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"tool_use"' not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue
            msg = d.get("message") or {}
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    yield c.get("name") or "", c.get("input") or {}


def needs_retro(path):
    return needs_retro_from(tool_uses(path))


def needs_retro_from(tools):
    """tools：依序的 (工具名稱, input dict)。stop_gate.py 用已經讀好的事件呼叫這個，不用再讀一次檔。"""
    last_push = last_retro = -1
    for i, (name, inp) in enumerate(tools):
        if name in ("Bash", "PowerShell"):
            cmd = inp.get("command") or ""
            # heredoc 寫進檔案的內容不是在執行（例：寫一支含 git push 的腳本），先去掉再判斷
            cmd = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?.*?^\s*\1\s*$", "", cmd, flags=re.S | re.M)
            # 單引號字串是資料不是指令（例：sed 's/git push/.../'、grep 'git push'）；git push 本身的參數加引號不影響判斷
            cmd = re.sub(r"'[^']*'", "''", cmd)
            if PUSH.search(cmd):
                last_push = i
            if RETRO.search(cmd) and re.search(r"(>|Write|Set-Content|Add-Content|cp |python|sed -i)", cmd):
                last_retro = i
        elif name in ("Edit", "Write", "MultiEdit"):
            if RETRO.search(inp.get("file_path") or ""):
                last_retro = i
    return last_push >= 0 and last_retro < last_push


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        return 0
    if data.get("stop_hook_active"):
        return 0
    path = data.get("transcript_path")
    if not path:
        return 0
    if needs_retro(path):
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps({"decision": "block", "reason": REASON}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
