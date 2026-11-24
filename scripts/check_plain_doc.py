# -*- coding: utf-8 -*-
r"""檢查「要給非技術的人看、要他回覆」的文件(Excel／Markdown／文字檔)夠不夠白話、有沒有說清楚要他做什麼。

為什麼:給業務主管、需求方的確認文件,三次被使用者說「看不懂／沒說清楚要他做什麼」——
  滿是內部用語(識別碼、相似度、欄位名)、沒有說明頁、要對方填代碼、幾百列沒分輕重(L-183)。
用法:python -X utf8 -I check_plain_doc.py <檔案> [--terms <本地詞表.txt>]
  - 本地詞表:每行一個不該出現的詞(專案代號、資料表名、內部稱呼),放 <本地>/plain-terms.txt
檢查(有一項不過就 exit 1):
  1. 有說明:Excel 第一個工作表的名稱或 A1 含「先看」「說明」「請先讀」;文字檔開頭 30 行內有「要請您」「請您」「麻煩您」
  2. 有說要他做什麼:說明裡有「要請您」「請您」「麻煩您」其中之一,也有「回傳」「回覆」「填」其中之一
  3. 有回覆的地方(Excel):某個工作表的標題列有「您的」「意見」「決定」「回覆」
  4. 沒有技術用語:預設詞表＋本地詞表;英文欄位名樣式(全大寫底線 FOO_BAR)、小數相似度(0.72)也算
  5. 不要對方填代碼:回覆欄標題不能有「代碼」「識別碼」「ID」
"""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8")
DEFAULT_TERMS = ["識別碼", "相似度", "資料表", "資料庫", "欄位", "SQL", "JSON", "NULL", "null", "API", "KEY_ID", "key", "Key",
                 "流水號", "主鍵", "防呆", "對照表 tsv", "tsv", "判定", "延續", "接法", "演練", "正式站", "本機", "commit", "部署"]
ASK = ("要請您", "請您", "麻煩您")
REPLY = ("回傳", "回覆", "填")


def load_terms(path):
    terms = list(DEFAULT_TERMS)
    if path and os.path.exists(path):
        terms += [l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")]
    return terms


def cells_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = [[("" if v is None else str(v)) for v in r] for r in ws.iter_rows(values_only=True)]
        sheets.append((ws.title, rows))
    return sheets


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    path = args[0]
    terms_path = sys.argv[sys.argv.index("--terms") + 1] if "--terms" in sys.argv else None
    terms = load_terms(terms_path)
    problems = []
    if path.lower().endswith((".xlsx", ".xlsm")):
        sheets = cells_xlsx(path)
        first_title, first_rows = sheets[0]
        intro = "\n".join(" ".join(r) for r in first_rows)
        a1 = first_rows[0][0] if first_rows and first_rows[0] else ""
        if not any(k in first_title + a1 for k in ("先看", "說明", "請先讀")):
            problems.append(f"1. 第一個工作表「{first_title}」不是說明頁(名稱或 A1 要有「先看／說明／請先讀」)")
        if not (any(k in intro for k in ASK) and any(k in intro for k in REPLY)):
            problems.append("2. 說明頁沒寫清楚要他做什麼(要有「請您／要請您」＋「填／回覆／回傳」)")
        # 資料多時要分輕重:寫明哪些一定要看、哪些不用看(2026-11-09 使用者:「一次列出來是全部都要看,還是先看重要的幾點?」)
        n_rows = sum(max(0, len(rows) - 1) for _, rows in sheets[1:])
        if n_rows > 50 and not (any(k in intro for k in ("一定要看", "必看", "只有")) and any(k in intro for k in ("不用看", "備查", "有空"))):
            problems.append(f"2b. 明細共 {n_rows} 列,說明頁沒分輕重(要寫「一定要看／只有…」和「不用看／有空再看／備查」)")
        reply_cols = [(t, h) for t, rows in sheets if rows for h in rows[0] if any(k in h for k in ("您的", "意見", "決定", "回覆"))]
        if not reply_cols:
            problems.append("3. 沒有給他填的欄位(某個工作表標題列要有「您的／意見／決定／回覆」)")
        for t, h in reply_cols:
            if re.search(r"代碼|識別碼|\bID\b", h):
                problems.append(f"5. 「{t}」的回覆欄要他填代碼:{h}")
        texts = [(t, i + 1, c) for t, rows in sheets for i, r in enumerate(rows) for c in r if c]
    else:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        head = "\n".join(lines[:30])
        if not (any(k in head for k in ASK) and any(k in head for k in REPLY)):
            problems.append("1/2. 開頭 30 行內沒寫要他做什麼(要有「請您／要請您」＋「填／回覆／回傳」)")
        texts = [("", i + 1, l) for i, l in enumerate(lines)]
    hits = {}
    for t, row, text in texts:
        for term in terms:
            pat = r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])" if re.fullmatch(r"[A-Za-z_ ]+", term) else re.escape(term)
            if re.search(pat, text):
                hits.setdefault(term, []).append(f"{t}第{row}列")
        for m in re.findall(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b", text):
            hits.setdefault(m, []).append(f"{t}第{row}列")
        if re.search(r"(?<![\d.])0\.\d{2}(?!\d)", text) and "相似" in text:
            hits.setdefault("相似度數字", []).append(f"{t}第{row}列")
    for term, where in sorted(hits.items(), key=lambda x: -len(x[1])):
        problems.append(f"4. 技術用語「{term}」出現 {len(where)} 處(例:{'、'.join(where[:3])})")
    # 6. 選項要寫具體內容:「照另一個選項」看不出是什麼(2026-11-09 使用者:「照另一個選項又是甚麼」)
    vague = [f"{t}第{row}列" for t, row, text in texts if re.search(r"另一個選項|其他選項|照另一個|照上面|如上所述", text)]
    if vague:
        problems.append(f"6. 選項寫得不具體(「另一個選項／照上面」)出現 {len(vague)} 處(例:{'、'.join(vague[:3])})——改成「做法①／做法②」並在欄位寫明具體怎麼做")
    if problems:
        print(f"白話檢查:{len(problems)} 項要改")
        for p in problems:
            print("  ", p)
        sys.exit(1)
    print("白話檢查:通過")


if __name__ == "__main__":
    main()
