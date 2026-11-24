#!/bin/bash
# L-165：MySQL／MariaDB 版（用容器的 MYSQL_ROOT_PASSWORD 環境變數，不印出）。在資料庫主機上跑。
# MySQL／MariaDB：起算時間後建立／修改的資料裡有沒有亂碼（中文 UTF-8 被當 ISO-8859-1 讀再存回去）。只讀（read only 交易）。
# 亂碼特徵（位元組）：C3 A4～A9（ä～é，中文字的第一個位元組）接兩個 C2 80～BF
# 用法：bash my_mojibake.sh <資料庫容器> <資料庫> <起算時間>
DC=$1; DB=$2; TL=$3
Q() { docker exec "$DC" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B -e "SET SESSION TRANSACTION READ ONLY; $0"' "$1" </dev/null; }
HX="'^(..)*C3A[4-9]C2[89AB].C2[89AB].'"
# 對照組：把「編碼」的 UTF-8 位元組當 latin1 讀、再存成 utf8（＝實際發生的亂碼）；兩個字的後續位元組都 ≥ 0xA0，cp1252 跟 ISO-8859-1 結果相同
echo "== $DB（起算 $TL）；對照組 $(Q "SELECT HEX(CONVERT(CONVERT(CAST(CONVERT('編碼' USING utf8) AS BINARY) USING latin1) USING utf8)) REGEXP $HX")（要 1）、$(Q "SELECT HEX(CONVERT('編碼' USING utf8)) REGEXP $HX")（要 0）"
Q "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='$DB' AND data_type IN ('date','datetime','timestamp') AND column_name REGEXP '(create|update|modif|insert|edit|add).*(date|time|_at)|^(create|update)d?_?(date|time|at)?\$'" > /tmp/my_cols.txt
echo "時間欄位 $(wc -l < /tmp/my_cols.txt) 個；最新寫入時間前 8："
while read -r t c ty; do echo "$(Q "SELECT IFNULL(MAX(\`$c\`),'—') FROM \`$DB\`.\`$t\`")  $t.$c"; done < /tmp/my_cols.txt | grep -v '^—' | sort -r | head -8
while read -r t c ty; do
  if [ "$ty" = date ]; then cond="\`$c\` >= '${TL%% *}'"; else cond="\`$c\` >= '$TL'"; fi
  n=$(Q "SELECT count(*) FROM \`$DB\`.\`$t\` WHERE $cond")
  [ "${n:-0}" -gt 0 ] || continue
  cols=$(Q "SELECT GROUP_CONCAT(CONCAT('IFNULL(HEX(\`',column_name,'\`),\'\') REGEXP $HX') SEPARATOR ' OR ') FROM information_schema.columns WHERE table_schema='$DB' AND table_name='$t' AND data_type IN ('char','varchar','text','mediumtext','longtext','tinytext')")
  if [ -z "$cols" ] || [ "$cols" = NULL ]; then echo "$t.$c 起算後 $n 筆（沒有文字欄位）"; continue; fi
  m=$(Q "SELECT count(*) FROM \`$DB\`.\`$t\` WHERE $cond AND ($cols)")
  echo "$t.$c 起算後 $n 筆，含亂碼 $m 筆"
done < /tmp/my_cols.txt
rm -f /tmp/my_cols.txt
