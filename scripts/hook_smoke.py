"""逐條實測 settings.json 裡掛的技能 hook 真的會跑（改路徑、搬資料夾、換裝置之後用）。

用法：python -X utf8 -I <技能>/scripts/hook_smoke.py [--settings <settings.json>] [--old]
  照 settings.json 裡每一條指向技能 hooks/ 的指令原樣執行，餵一筆該事件的輸入，看有沒有預期的反應。
  --old：另外把指令裡的 skills/agile-crew 換回 skills/dev-team 再測一次（驗相容用的轉送檔）。
路徑漏改時 hook 是無聲失效（或每個動作都被擋），單元測試測不到，所以要照設定檔原樣跑。
不會改任何檔；對話過長提醒那一條會拿這台最大的一份工作階段紀錄來餵。
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import uuid

HOME = os.path.expanduser("~")
CLAUDE = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
LOCAL = os.environ.get("AGILE_CREW_LOCAL") or os.environ.get("DEV_TEAM_LOCAL") or os.path.join(CLAUDE, "agile-crew-local")


def biggest_transcript():
    files = glob.glob(os.path.join(CLAUDE, "projects", "*", "*.jsonl"))
    return max(files, key=os.path.getsize) if files else ""


def small_transcript():
    p = os.path.join(tempfile.gettempdir(), "hook-smoke-empty.jsonl")
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
    return p


def scratch_with_script():
    """暫存區裡放一支腳本：刪它的指令一定會讓 tool_hints 出提醒。"""
    d = os.path.join(tempfile.gettempdir(), "hook-smoke", "scratchpad", "app_local")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/bash\njava -jar x.jar\n")
    return d.replace("\\", "/")


def cases():
    """hook 檔名 -> [(說明, 輸入, 預期輸出裡要有的字或 None＝只要正常結束, 預期是擋下)]。每次呼叫用新的對話代號（有些提醒同一個對話只出一次）。"""
    sid = "smoke-" + uuid.uuid4().hex[:8]
    retro = os.path.join(LOCAL, "retro-log.md")
    return {
        "session_brief.py": [("開工帶入", {"hook_event_name": "SessionStart", "source": "startup", "cwd": HOME}, "開工提醒", False)],
        "project_pointer.py": [("專案位置帶入（沒對到專案時安靜也算過）",
                                {"hook_event_name": "UserPromptSubmit", "prompt": "hook smoke", "session_id": sid, "cwd": HOME}, None, False)],
        "context_watch.py": [("對話過長提醒", {"hook_event_name": "UserPromptSubmit", "prompt": "x", "session_id": sid,
                                          "transcript_path": biggest_transcript()}, "工作階段", False)],
        "read_guard.py": [("整份讀回顧紀錄要擋", {"hook_event_name": "PreToolUse", "tool_name": "Read",
                                         "tool_input": {"file_path": retro}}, "", True)],
        "guard_tool_input.py": [("擋已知錯誤指令", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                            "tool_input": {"command": "printenv"}, "session_id": sid}, "已擋下", True)],
        "tool_hints.py": [("提醒（刪暫存區裡的腳本）", {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                           "tool_input": {"command": f'rm -rf "{scratch_with_script()}"'},
                                           "session_id": sid, "cwd": HOME}, "L-174", False)],
        "stop_gate.py": [("收尾檢查（沒事可擋時放行）", {"hook_event_name": "Stop", "session_id": sid,
                                              "transcript_path": small_transcript(), "cwd": HOME}, None, False)],
    }


KNOWN = ("session_brief.py", "project_pointer.py", "context_watch.py", "read_guard.py",
         "guard_tool_input.py", "tool_hints.py", "stop_gate.py")


def hook_name(cmd):
    for part in cmd.replace("\\", "/").replace('"', " ").replace("'", " ").split():
        if part.endswith(".py"):
            return part.rsplit("/", 1)[-1]
    return ""


def commands(settings):
    data = json.load(open(settings, encoding="utf-8"))
    out = []
    for event, groups in (data.get("hooks") or {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                c = h.get("command", "")
                # 用檔名認，不用路徑認：路徑寫錯的那一條正是要抓的，不能因為路徑不對就跳過
                if hook_name(c) in KNOWN:
                    out.append((event, g.get("matcher", ""), c))
    return out


def run(cmd, payload):
    r = subprocess.run(cmd, shell=True, input=json.dumps(payload).encode("utf-8"), capture_output=True, timeout=120)
    text = (r.stdout + r.stderr).decode("utf-8", "replace")
    return r.returncode, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default=os.path.join(CLAUDE, "settings.json"))
    ap.add_argument("--old", action="store_true")
    a = ap.parse_args()
    cs, bad, n = commands(a.settings), 0, 0
    if not cs:
        print("settings.json 裡沒有技能的 hook 指令——還沒掛。")
        return 1
    seen = set()
    for event, matcher, cmd in cs:
        name = hook_name(cmd)
        for variant in ([cmd, cmd.replace("skills/agile-crew/", "skills/dev-team/").replace("skills\\agile-crew\\", "skills\\dev-team\\")]
                        if a.old else [cmd]):
            if (event, variant) in seen:
                continue
            seen.add((event, variant))
            which = "舊路徑轉送" if variant != cmd else "設定檔原樣"
            for label, payload, want, block in cases().get(name, [("（沒有內建的輸入，只看能不能執行）", {"hook_event_name": event}, None, False)]):
                n += 1
                if name == "tool_hints.py" and event != "PreToolUse":
                    want = None      # 事後、失敗時的提醒要看指令結果，這裡只確認能執行
                    payload = dict(payload, hook_event_name=event, tool_response={"stdout": "", "stderr": ""})
                code, text = run(variant, payload)
                blocked = code == 2 or '"deny"' in text or '"block"' in text
                missing = "can't open file" in text or "No such file" in text or "找不到" in text and "python" in text.lower()
                ok = not missing and (blocked if block else code == 0) and (want is None or want in text)
                bad += 0 if ok else 1
                first = text.strip().splitlines()[0][:70] if text.strip() else "（沒有輸出）"
                print(f"{'OK ' if ok else 'XX '} {event:<18} {name:<20} {which}｜{label}｜結束碼 {code}｜{first}")
    mounted = {hook_name(c) for _, _, c in cs}
    not_mounted = [k for k in KNOWN if k not in mounted]
    if not_mounted:
        print("沒掛（設定檔裡找不到）：" + "、".join(not_mounted))
    print(f"\n共 {n} 項，有問題 {bad} 項")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
