"""UserPromptSubmit hook：使用者的話裡提到某個專案（名稱、短名、repo 名、別名）時，帶入「紀錄在哪、程式在哪」一小段，
讓任何工作階段不用讀整份專案總表就接得上。同一個工作階段、同一個專案只帶一次。

只輸出位置，不輸出紀錄內容。任何錯誤都安靜結束（exit 0），不能擋住使用者送出訊息。
設定：<本地>/config.json 的 project_index、work_root、code_root、aliases；"project_pointer": false 可關。
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

MAX_PROJECTS = 3
CUT = 160


def short(s, n=CUT):
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def build(prompt, session_id, cfg=None, state_dir=None):
    import projlib
    cfg = cfg if cfg is not None else projlib.config()
    if cfg.get("project_pointer") is False:
        return ""
    plist = projlib.projects(cfg)
    hits = projlib.match(prompt, plist)
    if not hits:
        return ""
    state_dir = state_dir or os.path.join(tempfile.gettempdir(), "dev-team-pointer")
    os.makedirs(state_dir, exist_ok=True)
    state = os.path.join(state_dir, "".join(ch for ch in (session_id or "nosession") if ch.isalnum() or ch in "-_")[:80] + ".txt")
    done = set(open(state, encoding="utf-8").read().split("\n")) if os.path.exists(state) else set()
    out = []
    for p, hit in hits:
        if p["path"] in done:
            continue
        if len(out) >= MAX_PROJECTS:
            break
        line = "- %s（對到「%s」）｜紀錄：%s" % (p["name"], hit, p["path"])
        if os.path.exists(projlib.knowledge_path(p["path"])):
            line += "｜知識（架構、流程、坑，需要時才讀）：%s" % projlib.knowledge_path(p["path"])
        if p["basic"].get("程式碼"):
            line += "｜程式碼：%s" % short(p["basic"]["程式碼"])
        out.append(line)
        done.add(p["path"])
    if not out:
        return ""
    with open(state, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(done)))
    return ("專案位置（hook 依這句話自動對到，只給位置；要動手再讀那份紀錄的「目前狀況」「待辦」，不用讀專案總表；對錯了就忽略）：\n"
            + "\n".join(out))


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace") or "{}")
        prompt = data.get("prompt") or ""
        if not prompt.strip() or len(prompt) > 20000:
            return 0
        text = build(prompt, data.get("session_id") or "")
        if text:
            sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
