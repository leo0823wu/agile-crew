#!/bin/bash
# L-165：PostgreSQL 資料庫有沒有寫進亂碼（UTF-8 中文被當 ISO-8859-1 讀再存回去）。在資料庫主機上跑。
# 今天建立／修改的資料裡有沒有亂碼（日期型別看今天、時間戳看起算時間之後）。只讀。
# 用法：bash pg_mojibake.sh <postgres 容器> <資料庫> <起算時間 YYYY-MM-DD HH:MM:SS>
PC=$1; DB=$2; TL=$3; DAY=${TL%% *}
PSQL() { docker exec -e PGOPTIONS='-c default_transaction_read_only=on' "$PC" sh -c "psql -U postgres -d $DB -At -F '|' -c \"\$0\"" "$1" </dev/null; }
RX='[à-ï][\u0080-¿]{2}'
echo "== $DB（起算 $TL）；對照組 $(PSQL "SELECT convert_from(convert_to('編碼','UTF8'),'LATIN1') ~ '$RX'")（要 t）"
PSQL "SELECT table_name||'|'||column_name||'|'||data_type FROM information_schema.columns WHERE table_schema='public' AND (data_type LIKE 'timestamp%' OR data_type='date') AND column_name ~* '(create|update|modif|insert|edit).*(date|time|_at)|^(create|update)d?_?(date|time|at)?$' ORDER BY 1" > /tmp/pgm_cols.txt
echo "時間欄位 $(wc -l < /tmp/pgm_cols.txt) 個"
while IFS='|' read -r t c ty; do
  if [ "$ty" = date ]; then cond="\"$c\" >= '$DAY'"; else cond="\"$c\" >= '$TL'"; fi
  n=$(PSQL "SELECT count(*) FROM \"$t\" WHERE $cond")
  [ "${n:-0}" -gt 0 ] || continue
  m=$(PSQL "SELECT count(*) FROM \"$t\" x WHERE $cond AND x::text ~ '$RX'")
  echo "$t.$c（$ty）起算後 $n 筆，含亂碼 $m 筆"
  [ "${m:-0}" -gt 0 ] && PSQL "SELECT \"$c\", left(regexp_replace(x::text, '\s+', ' ', 'g'), 200) FROM \"$t\" x WHERE $cond AND x::text ~ '$RX' LIMIT 5" | sed 's/^/     /'
done < /tmp/pgm_cols.txt
rm -f /tmp/pgm_cols.txt
echo "--- 全部表：含亂碼的筆數（包含起算前，了解原本就有的）"
PSQL "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1" > /tmp/pgm_t.txt
while read -r t; do
  m=$(PSQL "SELECT count(*) FROM \"$t\" x WHERE x::text ~ '$RX'" 2>/dev/null)
  [ "${m:-0}" -gt 0 ] && echo "$t 含亂碼 $m 筆"
done < /tmp/pgm_t.txt
rm -f /tmp/pgm_t.txt
echo "（全部表掃完）"
