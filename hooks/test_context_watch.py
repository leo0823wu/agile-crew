"""context_watch.py 的測試：用暫存的紀錄檔，不碰真實資料。
執行：python -X utf8 -I test_context_watch.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import context_watch as cw  # noqa: E402


def asst(ctx, sidechain=False):
    return json.dumps({"type": "assistant", "isSidechain": sidechain,
                       "message": {"usage": {"input_tokens": 10, "cache_creation_input_tokens": 0,
                                             "cache_read_input_tokens": ctx - 10, "output_tokens": 5}}})


def write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    fails = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        t = os.path.join(tmp, "s.jsonl")
        st = os.path.join(tmp, "state")
        user = json.dumps({"type": "user", "message": {"content": "嗨"}})

        write(t, [user, asst(120000)])
        check("12 萬：不提醒", cw.build(t, "s1", state_dir=st) is None)

        write(t, [user, asst(120000), user, asst(310000)])
        r = cw.build(t, "s1", state_dir=st)
        check("31 萬：提醒，兩段話都有數字", bool(r) and "31 萬" in r[0] and "31 萬" in r[1])
        check("31 萬第二次送訊息：不重複提醒", cw.build(t, "s1", state_dir=st) is None)

        write(t, [user, asst(310000), user, asst(395000)])
        check("39.5 萬（還沒多一段）：不提醒", cw.build(t, "s1", state_dir=st) is None)

        write(t, [user, asst(395000), user, asst(410000)])
        r = cw.build(t, "s1", state_dir=st)
        check("41 萬（多一段）：再提醒", bool(r) and "41 萬" in r[0])

        write(t, [user, asst(410000), user, asst(90000)])
        check("摘要後掉到 9 萬：不提醒", cw.build(t, "s1", state_dir=st) is None)
        write(t, [user, asst(90000), user, asst(305000)])
        check("摘要後又長到 30.5 萬：重新提醒", bool(cw.build(t, "s1", state_dir=st)))

        write(t, [user, asst(100000), asst(900000, sidechain=True)])
        check("子代理的回覆不算（主對話 10 萬）", cw.last_context(t) == 100000)

        write(t, [user, asst(350000), "這行不是 JSON", json.dumps({"type": "user", "message": {"content": "x" * 50}})])
        check("最後幾行不是回覆：往前找到 35 萬", cw.last_context(t) == 350000)

        big = os.path.join(tmp, "big.jsonl")
        write(big, [asst(50000)] + [json.dumps({"type": "user", "message": {"content": "y" * 1000}})] * 3000 + [asst(330000)])
        check("大檔只讀檔尾也找得到最後一則", cw.last_context(big, tail_bytes=200000) == 330000)

        check("別的工作階段各記各的", bool(cw.build(big, "s2", state_dir=st)))
        check("紀錄檔不存在：不提醒、不出錯", cw.build(os.path.join(tmp, "none.jsonl"), "s3", state_dir=st) is None)

        # 實際當 hook 跑：輸出要是合法 JSON、兩個欄位都有；壞輸入要 exit 0 沒輸出
        write(t, [user, asst(520000)])
        env = dict(os.environ, TMP=tmp, TEMP=tmp, TMPDIR=tmp)
        p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "context_watch.py")],
                           input=json.dumps({"session_id": "hook1", "transcript_path": t, "prompt": "hi"}).encode("utf-8"),
                           capture_output=True, env=env)
        try:
            o = json.loads(p.stdout.decode("utf-8"))
        except ValueError:
            o = {}
        check("當 hook 跑：exit 0、有 systemMessage 與 additionalContext",
              p.returncode == 0 and "52 萬" in o.get("systemMessage", "")
              and o.get("hookSpecificOutput", {}).get("hookEventName") == "UserPromptSubmit"
              and "52 萬" in o.get("hookSpecificOutput", {}).get("additionalContext", ""))
        p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "context_watch.py")], input=b"not json", capture_output=True, env=env)
        check("壞輸入：exit 0、沒輸出", p.returncode == 0 and not p.stdout)

    print("\n%s（%d 項失敗）" % ("全部通過" if not fails else "有失敗", len(fails)))
    print("failures:", len(fails))      # run_tests.py 認這一行
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
