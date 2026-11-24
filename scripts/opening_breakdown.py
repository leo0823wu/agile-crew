"""量一個工作階段「第一則回覆之前」帶了哪些東西、各約多少 token。唯讀。
用法：python -X utf8 -I opening_breakdown.py <jsonl>
token 是估的：中日韓字 1 字約 1 token、其餘約 4 字元 1 token；最後用第一則回覆的實際 context 對照，差額＝紀錄檔沒記的部分（工具的完整定義等）。
"""
import collections, io, json, re, sys

CJK = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")


def est(s):
    c = len(CJK.findall(s))
    return c + (len(s) - c) / 4.0


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k in ("type", "hookName", "toolUseID", "hookEvent", "digests", "names", "addedNames", "wireHiddenNames", "builtInTypes", "addedTypes"):
                continue
            for s in strings(v):
                yield s
    elif isinstance(o, list):
        for v in o:
            for s in strings(v):
                yield s


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parts = collections.OrderedDict()
    detail = collections.defaultdict(collections.Counter)
    actual = None
    for line in io.open(sys.argv[1], encoding="utf-8", errors="replace"):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        t = o.get("type")
        if t == "assistant":
            u = (o.get("message") or {}).get("usage") or {}
            actual = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
            if actual:
                break
            continue
        if t == "user":
            c = (o.get("message") or {}).get("content")
            txt = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict))
            parts["使用者第一句話"] = parts.get("使用者第一句話", 0) + est(txt)
            continue
        if t != "attachment":
            continue
        a = o.get("attachment") or {}
        at = a.get("type")
        txt = "\n".join(strings(a))
        parts[at] = parts.get(at, 0) + est(txt)
        if at == "skill_listing":
            for ln in (a.get("content") or "").split("\n"):
                m = re.match(r"^- ([^:\s]+)(:[^:\s]+)?: ", ln)
                if m:
                    grp = m.group(1) if m.group(2) else "（內建與個人技能）"
                    detail[at][grp] += est(ln)
                    detail[at + "#n"][grp] += 1
        elif at == "deferred_tools_delta":
            for ln in a.get("addedLines") or a.get("addedNames") or []:
                m = re.match(r"^(mcp__[^_]+(?:_[^_]+)*?)__", ln)
                grp = m.group(1) if m else "（內建工具）"
                detail[at][grp] += est(ln)
                detail[at + "#n"][grp] += 1
        elif at == "mcp_instructions_delta":
            blocks = a.get("addedBlocks") or []
            names = a.get("addedNames") or []
            for i, b in enumerate(blocks):
                s = b if isinstance(b, str) else json.dumps(b, ensure_ascii=False)
                detail[at][names[i] if i < len(names) else str(i)] += est(s)
        elif at == "instructions":
            for f in a.get("files") or []:
                if isinstance(f, dict):
                    detail[at][str(f.get("path") or f.get("file") or f.get("name") or "?")[-60:]] += est("\n".join(strings(f)))
        elif at in ("hook_additional_context", "hook_success", "hook_system_message"):
            detail[at][str(a.get("hookName"))] += est(txt)
    total = sum(parts.values())
    print("第一則回覆時實際 context：%s｜紀錄檔裡量得到的：約 %.0f｜差額（工具完整定義等，沒記在檔裡）：約 %.0f" % (actual, total, (actual or 0) - total))
    for k, v in sorted(parts.items(), key=lambda x: -x[1]):
        print("\n%-28s 約 %6.0f token  %4.1f%%" % (k, v, 100 * v / (actual or total)))
        for g, w in detail[k].most_common(12):
            n = detail[k + "#n"].get(g)
            print("    %6.0f  %s%s" % (w, g, "（%d 個）" % n if n else ""))


main()
