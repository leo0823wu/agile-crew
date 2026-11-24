# -*- coding: utf-8 -*-
r"""兩份表格逐格比對(xlsx／xls／csv／tsv),說「A 就是 B 原樣」「兩份一樣」之前一定要跑。

由來(L-019):只比表頭、或只比主鍵,就說兩份檔「相同」「原樣另存」,實際上內容有改(空白補值、日期改寫)。

用法:
  python -I diff_sheets.py <檔A> <檔B> [--key 欄號或欄名] [--sheet-a N] [--sheet-b N] [--header-a/--no-header-a ...] [--show 3]
  --key:用哪一欄對齊列(預設照列順序);沒有標題列的檔用欄號(從 0 起)
輸出:列數、對不到的列、每一欄「相同／A 空 B 有值／A 有值 B 空／值不同」的筆數與例子。
結束碼:0 = 每一格都相同;1 = 有不同
"""
import sys, os, csv, argparse, collections
sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10 ** 9)

def load(path, sheet=0):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[sheet]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if ext == ".xls":
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_index(sheet)
        return [[sh.cell_value(r, c) if sh.cell_type(r, c) != 0 else None for c in range(sh.ncols)] for r in range(sh.nrows)]
    delim = "\t" if ext in (".tsv", ".txt") else ","
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [list(r) for r in csv.reader(f, delimiter=delim)]

def norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)

ap = argparse.ArgumentParser()
ap.add_argument("a"); ap.add_argument("b")
ap.add_argument("--key", default=None)
ap.add_argument("--sheet-a", type=int, default=0); ap.add_argument("--sheet-b", type=int, default=0)
ap.add_argument("--no-header-a", action="store_true"); ap.add_argument("--no-header-b", action="store_true")
ap.add_argument("--show", type=int, default=3)
o = ap.parse_args()

A, B = load(o.a, o.sheet_a), load(o.b, o.sheet_b)
ha = [norm(x) for x in A[0]] if not o.no_header_a else [str(i) for i in range(max(len(r) for r in A))]
hb = [norm(x) for x in B[0]] if not o.no_header_b else [str(i) for i in range(max(len(r) for r in B))]
ra, rb = (A if o.no_header_a else A[1:]), (B if o.no_header_b else B[1:])
print(f"A:{o.a}  {len(ra)} 列 × {len(ha)} 欄")
print(f"B:{o.b}  {len(rb)} 列 × {len(hb)} 欄")
if ha != hb:
    print("欄名不同:", [(i, x, y) for i, (x, y) in enumerate(zip(ha, hb)) if x != y][:10], "| 欄數", len(ha), len(hb))

def keyidx(h):
    if o.key is None:
        return None
    return int(o.key) if o.key.isdigit() else h.index(o.key)
ka, kb = keyidx(ha), keyidx(hb)
if ka is None:
    pairs = list(zip(ra, rb))
    only_a, only_b = len(ra) - len(pairs), len(rb) - len(pairs)
else:
    ma = {norm(r[ka]): r for r in ra}
    mb = {norm(r[kb]): r for r in rb}
    pairs = [(ma[k], mb[k]) for k in ma if k in mb]
    only_a, only_b = len(set(ma) - set(mb)), len(set(mb) - set(ma))
    if len(ma) != len(ra) or len(mb) != len(rb):
        print(f"注意:主鍵有重複(A {len(ra) - len(ma)}、B {len(rb) - len(mb)} 列)")
print(f"對上的列 {len(pairs)};只在 A {only_a};只在 B {only_b}")

ncol = max(len(ha), len(hb))
stats = [collections.Counter() for _ in range(ncol)]
ex = [[] for _ in range(ncol)]
for x, y in pairs:
    for c in range(ncol):
        a = norm(x[c]) if c < len(x) else ""
        b = norm(y[c]) if c < len(y) else ""
        if a == b:
            k = "相同"
        elif a == "":
            k = "A空B有"
        elif b == "":
            k = "A有B空"
        else:
            k = "值不同"
        stats[c][k] += 1
        if k != "相同" and len(ex[c]) < o.show:
            ex[c].append((a[:40], b[:40]))
diff_cols = 0
for c in range(ncol):
    name = ha[c] if c < len(ha) else hb[c]
    s = stats[c]
    if set(s) - {"相同"}:
        diff_cols += 1
        print(f"  ✗ [{c}] {name}:{dict(s)} 例:{ex[c]}")
same_all = diff_cols == 0 and only_a == 0 and only_b == 0 and ha == hb
print("結論:", "每一格都相同 ✓" if same_all else f"不同:{diff_cols} 欄有差異(上面列出)")
sys.exit(0 if same_all else 1)
