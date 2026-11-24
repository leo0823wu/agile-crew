#!/bin/bash
# 重啟／重建容器前的檢查（L-161）：在「主機」上跑，有 ⚠ 的先處理再重啟。
# 用法：bash restart_precheck.sh <容器名稱> [額外要測的 host:port ...]
#   1. 容器查自己的主機名稱要多久（Oracle 等驅動會查；容器掛了主機的 /etc/hosts、DNS 又不通時，每條連線卡 10 秒，整站跟著卡）
#   2. 設定裡的資料庫／外部主機連不連得到（容器環境變數、加上參數給的 host:port；從容器裡測，連不到再從主機測）
#   3. docker diff：容器裡被直接改過的檔（重建容器會消失；只有 restart 才保留）
#   3b. compose 檔是不是 CRLF 行尾（換版腳本用 sed 改 image 行時要容許 \r）
#   4. 磁碟
# 只讀，不改任何東西。相容 BusyBox 映像（沒有 getent／bash／nc 時自動換方法）。
C=${1:?用法：bash restart_precheck.sh <容器名稱> [host:port ...]}
shift
warn=0
w() { echo "⚠ $*"; warn=$((warn + 1)); }
now_ms() { local v; v=$(date +%s%3N 2>/dev/null); case $v in *[!0-9]*|'') echo $(( $(date +%s) * 1000 ));; *) echo "$v";; esac; }

docker inspect "$C" >/dev/null 2>&1 || { echo "找不到容器 $C"; exit 2; }
echo "== $C（image $(docker inspect -f '{{.Config.Image}}' "$C")，狀態 $(docker inspect -f '{{.State.Status}}' "$C")）"

echo "-- 1. 主機名稱解析"
H=$(docker exec "$C" hostname 2>/dev/null)
t0=$(now_ms)
# getent／ping 走系統解析（跟 Java 一樣先看 /etc/hosts）；BusyBox 的 nslookup 只問 DNS，放最後
# getent ahosts＝getaddrinfo（跟 Java 一樣，hosts 有 IPv4 就不問 DNS）；getent hosts 會先問 IPv6 而去等 DNS，造成誤報（2026-11-06）
r=$(docker exec "$C" sh -c "if command -v getent >/dev/null; then getent ahosts $H | head -1; elif command -v ping >/dev/null; then ping -c 1 -W 2 $H 2>&1 | head -1; else nslookup $H 2>&1 | tail -2; fi" 2>&1)
t1=$(now_ms)
ms=$((t1 - t0))
echo "   $H → $(echo "$r" | tr '\n' ' ' | cut -c1-100)（${ms}ms）"
[ "$ms" -gt 2000 ] && w "容器查自己的主機名稱花 ${ms}ms：重啟後資料庫連線可能每條卡住。修法：compose 加 extra_hosts 或主機 /etc/hosts 加「127.0.0.1 $H」（看容器是否掛了主機的 /etc/hosts）"
docker inspect -f '{{range .Mounts}}{{.Source}} {{end}}' "$C" | grep -q -w /etc/hosts && echo "   （容器掛了主機的 /etc/hosts）"

echo "-- 2. 設定裡的連線"
T=$( { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$C" | grep -o -E '(jdbc:[a-z]+:(thin:@)?(//)?|https?://)[A-Za-z0-9._-]+(:[0-9]+)?' | sed -E 's#^(jdbc:[a-z]+:(thin:@)?(//)?|https?://)##'; printf '%s\n' "$@"; } | sort -u)
[ -z "$T" ] && echo "   環境變數裡沒有連線位址；設定寫在檔案裡的，把 host:port 當參數傳進來"
for hp in $T; do
  h=${hp%%:*}; p=${hp##*:}; [ "$p" = "$hp" ] && p=80
  res=$(docker exec "$C" sh -c "if command -v nc >/dev/null; then nc -z -w 3 $h $p && echo ok; elif command -v bash >/dev/null; then timeout 3 bash -c '</dev/tcp/$h/$p' && echo ok; else echo skip; fi" 2>/dev/null)
  if [ "$res" = skip ] || [ -z "$res" ]; then
    timeout 3 bash -c "</dev/tcp/$h/$p" 2>/dev/null && res="ok（主機測）" || res=${res:-fail}
  fi
  case $res in ok*) echo "   $h:$p 通 $res";; skip) echo "   $h:$p 無法測（容器沒有 nc／bash）";; *) w "$h:$p 連不到（容器內與主機都測不通）：重啟後用到它的功能會失敗；連線沒設逾時的話會拖垮整站";; esac
done

echo "-- 3. 容器裡被直接改過的檔（重建會消失）"
# 只列真正的檔：拿掉「只是底下有東西變了」的上層資料夾（C /usr、C /usr/local…）和掛載點本身
MNT=$(docker inspect -f '{{range .Mounts}}{{.Destination}} {{end}}' "$C")
# Tomcat 啟動時把 xxx.war 解開成 webapps/xxx/：那些檔每次都會重新解開，不算手改（曾經兩個站各報 2 千多個誤報）
# 解開的資料夾名稱可能跟 war 不同（server.xml 指成 ROOT），所以用 Tomcat 留在裡面的 META-INF/war-tracker 認
WARS=$( { docker exec "$C" sh -c 'ls /usr/local/tomcat/webapps/*.war 2>/dev/null' | sed -E 's#\.war$##';
          docker exec "$C" sh -c 'for d in /usr/local/tomcat/webapps/*/; do [ -f "${d}META-INF/war-tracker" ] && echo "${d%/}"; done' 2>/dev/null; } | sort -u | tr '\n' '|' | sed 's/|$//')
[ -n "$WARS" ] && WRX="^[AC] ($WARS)(/|\$)|^[AC] /usr/local/tomcat/conf/Catalina(/|\$)" || WRX='^[AC] /usr/local/tomcat/conf/Catalina(/|$)'
# 先在完整清單上去掉上層資料夾（C /usr/local/tomcat 這種），再排除雜訊；順序反過來會留下「子檔都被排除的上層資料夾」
D=$(docker diff "$C" 2>/dev/null | grep -E '^[AC] ' | sort -k2 \
  | awk -v mnt=" $MNT " '{p[NR]=$2; l[NR]=$0} END {for (i=1;i<=NR;i++) { if (i<NR && index(p[i+1], p[i] "/")==1) continue; if (index(mnt, " " p[i] " ")) continue; print l[i] } }' \
  | grep -v -E "$WRX" | grep -v -E '/(logs?|temp|tmp|work|cache|\.cache|run|proc)(/|$)|\.(log|pid|lock|swp)$|/root/\.[a-z_]*history$')
if [ -n "$D" ]; then
  echo "$D" | head -20 | sed 's/^/   /'
  [ "$(echo "$D" | wc -l)" -gt 20 ] && echo "   …共 $(echo "$D" | wc -l) 項"
  w "有 $(echo "$D" | wc -l) 個檔在容器裡被改過或新增：restart 會保留，重建（compose up 換 image、--force-recreate）會消失。先 docker cp 出來比對，該保留的改進 image／compose／掛載"
else
  echo "   沒有"
fi
docker diff "$C" 2>/dev/null | grep -q -E '/root/\.[a-z_]*history$' && echo "   （/root 的 shell 歷史被改過：有人進過容器，要查誰做了什麼時先 docker cp 保存）"

echo "-- 3b. compose 檔的行尾"
# 2026-11-13：正式機 compose 是 CRLF，換版腳本用 "image: X$" 比對抓不到（本機 Git Bash 會吃掉 CR，本機模擬測不出來，L-070）
CF=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$C" 2>/dev/null)
if [ -n "$CF" ]; then
  for f in $(echo "$CF" | tr ',' ' '); do
    [ -f "$f" ] || { echo "   $f 不在這台主機上，跳過"; continue; }
    n=$(grep -c $'\r$' "$f" || true)
    if [ "${n:-0}" -gt 0 ]; then
      echo "   ℹ $f 是 CRLF 行尾（$n 行）：腳本用 sed／grep 比對整行要寫 [[:space:]]*\$、替換用 \1 保留行尾；先在這台主機用複本測換版＋回退要跟原檔 cmp 相同"
    else
      echo "   $f 是 LF 行尾"
    fi
  done
else
  echo "   不是 compose 啟動的容器"
fi

echo "-- 4. 磁碟"
df -h / | tail -1 | awk '{print "   / 使用 "$5"，剩 "$4}'
u=$(df / | tail -1 | awk '{gsub("%","",$5); print $5}')
[ "${u:-0}" -ge 90 ] && w "磁碟 ${u}%：重啟時寫 log／解壓 war 可能失敗"

echo "== 結果：$([ $warn = 0 ] && echo '沒有問題，可以重啟' || echo "$warn 項 ⚠，先處理再重啟")"
exit $([ $warn = 0 ] && echo 0 || echo 1)
