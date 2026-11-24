#!/bin/bash
# L-184：全部 jsp（WEB-INF 以外）看內容特徵找惡意 jsp，不是只看放在哪個資料夾；只讀檔，不對它們發 HTTP 請求（HEAD 也會執行它）
# 命中的要逐支讀內容判斷：正常表單也可能用 Runtime.exec；同大小、同雜湊的通常是同一支惡意 jsp
# 用法：bash jsp_sigscan.sh <容器> <網站根目錄（容器內）>
C=$1; W=$2
KW='URLClassLoader|defineClass|javax\.crypto|Cipher\.getInstance|Runtime\.getRuntime|ProcessBuilder|unGzip|ScriptEngine|getReader\(\)|\.exec\('
docker exec "$C" sh -c "find $W -name '*.jsp' -not -path '*/WEB-INF/*' -not -path '*/logs/*'" > /tmp/sig_list.txt
echo "== $(hostname) $C：WEB-INF 以外的 jsp $(wc -l < /tmp/sig_list.txt) 支"
while read -r f; do
  hits=$(docker exec "$C" sh -c "grep -o -E '$KW' '$f' 2>/dev/null | sort -u | tr '\n' ','")
  loc=""; echo "$f" | grep -q -i -E '/(images|img|css|js|files|upload|fonts?|pdf)/' && loc="位置可疑"
  if [ -n "$hits" ] || [ -n "$loc" ]; then
    echo "⚠ $(docker exec "$C" stat -c '%y %sB' "$f" | cut -c1-16,36-) ${f#$W} ｜ $loc ｜ ${hits:-無關鍵字} ｜ sha256 $(docker exec "$C" sha256sum "$f" | cut -c1-12)"
  fi
done < /tmp/sig_list.txt
echo "--- 大小分布前 5（同一支惡意 jsp 常常同大小）"
while read -r f; do docker exec "$C" stat -c '%s' "$f"; done < /tmp/sig_list.txt | sort | uniq -c | sort -rn | head -5
rm -f /tmp/sig_list.txt
