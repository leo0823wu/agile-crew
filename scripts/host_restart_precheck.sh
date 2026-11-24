#!/bin/bash
# 主機服務（systemd，沒有 docker；例：主機上的 Tomcat）重啟前檢查（L-161 主機版，容器用 restart_precheck.sh）。
# 用法：bash host_restart_precheck.sh <systemd 服務名> [應用 log 路徑] [host:port ...]
#   host:port 傳設定檔裡的資料庫與外部服務（設定檔權限常常讀不到，自己從設定裡抄主機名與埠）。
# 只讀，不改任何東西；每個網路動作都有逾時（主機 DNS 壞掉時一次解析可以卡 10～20 秒）。
U=${1:?用法：bash host_restart_precheck.sh <systemd 服務名> [log 路徑] [host:port ...]}
shift
LOG=""
case ${1:-} in /*) LOG=$1; shift;; esac
warn=0
w() { echo "⚠ $*"; warn=$((warn + 1)); }
ms() { local v; v=$(date +%s%3N 2>/dev/null); case $v in *[!0-9]*|'') echo $(( $(date +%s) * 1000 ));; *) echo "$v";; esac; }

echo "== 服務 $U"
systemctl show "$U" -p ActiveState -p User -p ExecMainStartTimestamp -p ExecStart --no-pager 2>&1 | cut -c1-200
systemctl cat "$U" >/dev/null 2>&1 || w "找不到 systemd 服務 $U（用 systemctl list-units | grep -i 名稱 找）"

echo "-- 1. 主機名稱解析（Java、資料庫驅動啟動時會查）"
H=$(hostname); t0=$(ms); r=$(timeout 15 getent ahosts "$H" | head -1); t1=$(ms)
echo "   $H → ${r:-查不到}（$((t1 - t0))ms）"
[ $((t1 - t0)) -gt 2000 ] || [ -z "$r" ] && w "主機查自己名稱慢或查不到：重啟後連線可能每條卡住。修法：/etc/hosts 加「127.0.1.1 $H」"

echo "-- 2. DNS 通不通（不通時程式裡用網址連外的功能都會失敗，重啟也修不好）"
t0=$(ms); timeout 12 getent ahosts example.com >/dev/null 2>&1 && d=ok || d=fail; t1=$(ms)
if [ $d = ok ]; then echo "   外部網址解析正常（$((t1 - t0))ms）"; else
  w "外部網址解析失敗（$((t1 - t0))ms）：上游 DNS 見 resolvectl status；用 IP 直連的連線不受影響。重啟不會修好用網址連外的功能"
fi

echo "-- 3. 設定裡的連線"
[ $# -eq 0 ] && echo "   （沒傳 host:port；資料庫、外部服務從設定檔抄來當參數）"
for hp in "$@"; do
  h=${hp%%:*}; p=${hp##*:}; [ "$p" = "$hp" ] && p=80
  if timeout 5 bash -c "</dev/tcp/$h/$p" 2>/dev/null; then echo "   $h:$p 通"
  else
    case $h in *[a-zA-Z]*) timeout 8 getent ahosts "$h" >/dev/null 2>&1 || { w "$h 查不到網址（DNS）"; continue; };; esac
    w "$h:$p 連不到：重啟後用到它的功能會失敗；若在啟動時就連（資料庫），網站會起不來"
  fi
done

echo "-- 4. 上次啟動花多久（重啟大約要停這麼久）"
if [ -n "$LOG" ] && [ -r "$LOG" ]; then
  grep -a -E 'Server startup in|Started .* in [0-9.]+ seconds' "$LOG" | tail -2 | cut -c1-160
else echo "   （沒給 log 或讀不到）"; fi

echo "-- 5. 磁碟"; df -h / | tail -1
u=$(df -P / | awk 'NR==2{gsub("%","",$5); print $5}'); [ "${u:-0}" -ge 90 ] && w "根目錄已用 ${u}%：啟動寫 log 可能失敗"

echo "== 結果：⚠ $warn 項"
echo "   提醒：重啟會清掉記在記憶體的登入狀態（已登入的人要重登）；同一個 Tomcat 底下的其他網站也會一起停。"
