"""檢查一排項目（選單、頁籤、按鈕列）在各種螢幕寬度下，文字有沒有超出自己的格子、壓到旁邊的項目。

為什麼要有這支：截圖用肉眼看，小小的壓字很容易被「參考網站也一樣」「差一點點」放過（L-215）。
這支把「每一項文字的範圍」和「格子範圍」「同一行下一項的文字」逐一比對，有問題就 FAIL。

用法：
  python -I -X utf8 check_text_overflow.py <網址> "<項目的 CSS 選擇器>" [--widths 768,1024,1366,1920]
        [--before "<JS：量測前先執行，例如把下拉選單展開>"] [--css <要先套上的 CSS 檔，試改法用>]
        [--shots <截圖資料夾>] [--clip-height 220]

  例：python -I -X utf8 check_text_overflow.py https://example.com/page ".sub-nav a" \
        --before "document.querySelector('.sub-nav').classList.add('show')" --shots out

  結束碼：0＝全部通過、1＝有寬度不通過、2＝選擇器一個都沒抓到（多半是選擇器寫錯或選單沒展開）。

需求：playwright（async API；本機有 Edge 就用 channel=msedge，不用另外下載瀏覽器）。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

MEASURE = """(sel) => {
  const els = [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null);
  const items = els.map(e => {
    const r = document.createRange(); r.selectNodeContents(e);
    const t = r.getBoundingClientRect(); const c = e.getBoundingClientRect();
    return {text: e.innerText.trim().replace(/\\s+/g, ' '), top: Math.round(c.top),
            cellL: c.left, cellR: c.right, textL: t.left, textR: t.right};
  });
  const bad = [];
  items.forEach((it, i) => {
    if (it.textR > it.cellR + 1 || it.textL < it.cellL - 1) bad.push(`「${it.text}」超出自己的格子`);
    const nx = items[i + 1];
    if (nx && Math.abs(nx.top - it.top) < 2 && it.textR > nx.textL - 4) bad.push(`「${it.text}」碰到下一項「${nx.text}」`);
  });
  return {count: items.length, rows: new Set(items.map(x => x.top)).size, bad};
}"""


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("selector")
    ap.add_argument("--widths", default="768,1024,1280,1366,1440,1600,1920")
    ap.add_argument("--before", default="")
    ap.add_argument("--css", default="")
    ap.add_argument("--shots", default="")
    ap.add_argument("--clip-height", type=int, default=220)
    a = ap.parse_args()
    widths = [int(w) for w in a.widths.split(",")]
    if a.shots:
        Path(a.shots).mkdir(parents=True, exist_ok=True)
    fails, empty = 0, 0
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="msedge", args=["--no-proxy-server", "--disable-gpu"])
        for w in widths:
            pg = await b.new_page(viewport={"width": w, "height": 800})
            # 不等 networkidle：外部追蹤碼常讓網路一直不閒置
            await pg.goto(a.url, wait_until="domcontentloaded")
            await pg.wait_for_timeout(1500)
            if a.css:
                await pg.add_style_tag(content=Path(a.css).read_text(encoding="utf-8"))
            if a.before:
                await pg.evaluate(f"() => {{ {a.before} }}")
            await pg.wait_for_timeout(400)
            res = await pg.evaluate(MEASURE, a.selector)
            if a.shots:
                await pg.screenshot(path=str(Path(a.shots) / f"w{w}.png"),
                                    clip={"x": 0, "y": 0, "width": w, "height": a.clip_height})
            empty += res["count"] == 0
            fails += bool(res["bad"])
            print(w, json.dumps(res, ensure_ascii=False))
            await pg.close()
        await b.close()
    if empty:
        print("RESULT NO_ITEMS（有寬度一個項目都沒抓到：檢查選擇器，或用 --before 把選單展開）")
        sys.exit(2)
    print("RESULT", "FAIL" if fails else "PASS")
    sys.exit(1 if fails else 0)


asyncio.run(main())
