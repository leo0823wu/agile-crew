"""回放：把過去 session 實際下過的 Bash／PowerShell 指令丟給 guard_tool_input.py 的 check_command（同一個程序內，不開子程序），
看新規則會擋下多少、擋到什麼，用來找誤擋。改規則前後都跑一次。
只印擋下原因與指令前 90 字（`=` 後面的值遮掉）。
用法：python -I ~/.claude/skills/dev-team/hooks/replay_guard.py <最近幾個 session，例 30>
（2026-10-29 第一次回放：ssh 規則在 Git Bash 誤擋 900 多次，改成只擋 PowerShell；BOM 規則改成只擋寫原始碼／SQL／設定檔）"""
import glob
import importlib.util
import json
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("guard", os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_tool_input.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

proj = os.path.expanduser(os.path.join("~", ".claude", "projects"))
files = sorted(glob.glob(os.path.join(proj, "*", "*.jsonl")), key=os.path.getmtime)[-int(sys.argv[1] if len(sys.argv) > 1 else 30):]
seen = 0
hits = Counter()
examples = []
for f in files:
    for line in open(f, encoding="utf-8", errors="replace"):
        if '"tool_use"' not in line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        msg = d.get("message") or {}
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict) or c.get("type") != "tool_use" or c.get("name") not in ("Bash", "PowerShell"):
                continue
            cmd = (c.get("input") or {}).get("command") or ""
            seen += 1
            hit = g.check_command(c["name"], cmd)
            if hit:
                hits[hit[0]] += 1
                examples.append((hit[0], hit[1][:28], c["name"], re.sub(r"=\S+", "=<v>", cmd).replace("\n", " ")[:90]))
print("sessions:", len(files), "commands:", seen, "blocked:", sum(hits.values()), dict(hits))
only = sys.argv[2] if len(sys.argv) > 2 else None  # 第二個參數：只列某條規則（python／ssh／bom／grep-P／secret）
for rule, why, tool, cmd in examples:
    if (only and rule != only) or (not only and rule == "python"):
        continue
    print(rule, "|", tool, "|", why, "|", cmd)
