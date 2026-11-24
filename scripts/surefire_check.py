r"""檢查 Maven 測試報告是不是「這次真的跑了」（L-077）。

用法：python -I surefire_check.py <repo 路徑> [--since <分鐘>]
  - 只算 target/surefire-reports 裡、--since 分鐘內產生、而且 src/test 還找得到原始檔的報告
  - 列出：舊報告（不是這次產生的）、孤兒報告（測試檔已刪，例如暫時的 Zz 輸出測試）、0 項的類別
  - 結束碼：有失敗／錯誤、或這次一份報告都沒有 → 1

為什麼：2026-10-29 把資料夾裡所有報告加總報「431 項」，其實混了 7 份已刪測試的舊報告（實際 425）；
同一天另一個專案的 pom 略過測試，BUILD SUCCESS 卻一項都沒跑。回報測試數字以這支或 Maven 的 Results 那行為準。
"""
import os, sys, time, glob
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    repo = sys.argv[1]
    since_min = float(sys.argv[sys.argv.index("--since") + 1]) if "--since" in sys.argv else 120
    rep = os.path.join(repo, "target", "surefire-reports")
    files = glob.glob(os.path.join(rep, "TEST-*.xml"))
    cutoff = time.time() - since_min * 60
    # src/test 裡宣告過的類別（一個檔可以有好幾個類別、巢狀類別，報告名稱不一定等於檔名）
    import re
    declared = set()
    for root, _, names in os.walk(os.path.join(repo, "src", "test")):
        for n in names:
            if n.endswith((".java", ".kt", ".groovy")):
                with open(os.path.join(root, n), encoding="utf-8", errors="ignore") as fh:
                    declared.update(re.findall(r"\b(?:class|object)\s+(\w+)", fh.read()))
    cur, old, orphan, zero = [], [], [], []
    tests = fails = errs = skips = 0
    for f in files:
        try:
            s = ET.parse(f).getroot()
        except ET.ParseError:
            print("看不懂的報告：", f); continue
        name = s.get("name", "")
        simple = re.split(r"[.$]", name)[-1]
        if simple not in declared:
            orphan.append(name); continue
        if os.path.getmtime(f) < cutoff:
            old.append(name); continue
        n = int(s.get("tests", 0))
        cur.append(name)
        tests += n; fails += int(s.get("failures", 0)); errs += int(s.get("errors", 0)); skips += int(s.get("skipped", 0))
        if n == 0:
            zero.append(name)
    print(f"這次的報告 {len(cur)} 份：{tests} 項，失敗 {fails}、錯誤 {errs}、略過 {skips}（{since_min:g} 分鐘內產生）")
    if old:
        print(f"⚠ 不是這次產生的報告 {len(old)} 份（沒算進去）：", ", ".join(sorted(old)[:10]), "…" if len(old) > 10 else "")
    if orphan:
        print(f"⚠ 測試檔已不存在的孤兒報告 {len(orphan)} 份（沒算進去，可刪）：", ", ".join(sorted(orphan)))
    if zero:
        print("⚠ 0 項的類別：", ", ".join(sorted(zero)))
    if not cur:
        print("✗ 這次一份報告都沒有：測試可能被略過（maven.test.skip）或根本沒跑")
        return 1
    return 1 if fails or errs else 0


if __name__ == "__main__":
    sys.exit(main())
