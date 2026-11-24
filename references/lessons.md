# 踩過的坑與做法（入口＋索引）

每一條都是實際糾正過或出過錯的事，寫成通用的流程面、技術面做法（不含個人、公司、專案資料，可以分享）。分兩份：

| 檔案 | 內容 | 什麼時候讀 |
|---|---|---|
| `lessons-workflow.md` | 通用流程：需求、分工、回報、文案、驗證、設計原則 | **不整份讀**：再犯最多的已整理在 `SKILL.md`〈必守規則〉；中、大的需求依段落（W1～W6）讀跟這次有關的，查細節用編號 Grep |
| `lessons-tech.md` | 技術環境：本機 Shell、部署、資料庫、Java、前端、匯入匯出、外部服務 | 開工時看這次會碰到哪些技術，**用下面的索引只讀相關段落** |
| `<本地>/lessons-local.md` | 只適用這個使用者／公司的踩坑，以及通用列在本地的具體細節（同一個編號） | 開工時一起看（本地資料夾見 `shareable.md`） |

## 編號與再犯次數

- 每列有固定編號 `L-001`～，搬段落、搬檔、搬到本地都不改編號；引用時寫編號（例：「見 L-042」），不要寫「第幾列」。技能與本地共用同一組編號。
- **新增一列一律先取號**：`python -I ~/.claude/skills/agile-crew/scripts/lesson_id.py next --note "一句話"`，印出的編號就是你的（加鎖取號，好幾個工作階段同時寫也不會撞號；取號紀錄在 `<本地>/lesson-ids.log`）。檢查重號：`lesson_id.py check`。由來：手動「讀計數→用→加一」撞號三次。
- 「再犯」欄＝規則寫下之後又發生的次數。回顧（`retro.md` 第 0 步）發現又犯了，就在原列 +1，並在「以後的做法」補一句「又一次（日期）」。
- **再犯 ≥ 2 的列必須是機制**（測試、腳本、hook），不能只是文字；回顧時檢查，還不是機制的列成行動項。
- 已經做成 hook 的（`hooks/`，安裝見 `README.md`）：
  - **擋**（`guard_tool_input.py`）：L-033 Bash 用 Git Bash 的 ssh／scp、L-032 Edit 結尾空白、L-042 指令裡直接寫 Python、L-014 PowerShell 下 ssh 時遠端字串夾雙引號或管線、或 pipe 給 ssh、L-052／L-064 PowerShell 寫原始碼／SQL／設定檔加 BOM（含同一行寫訊息檔再 `git commit -F`）、L-046 `grep -P`、印出 `.env`／環境變數值、L-047 Playwright 沒指定 channel、L-122 `mvnw.cmd` 沒加 `.\`。
  - **腳本**（`scripts/`）：L-065 回答「現在／換版後會怎樣」「系統有沒有某功能」前用 `grep_branches.py` 看每個分支各長怎樣（`--since <需求日期>` 列出之後動到關鍵字的 commit，命中的註解行會標出來）；L-019 說「兩份檔一樣／原樣另存」前用 `diff_sheets.py` 逐格比；L-062 說「本來就有／重啟前就有」前用 `log_daily_count.py` 看舊 log 逐日次數；L-161 重啟／重建容器前在主機跑 `restart_precheck.sh`（主機服務、沒有 docker 用 `host_restart_precheck.sh`，含主機 DNS 檢查）；L-165 懷疑資料庫寫進亂碼時用 `db_mojibake_pg.sh`／`db_mojibake_mysql.sh`（只讀，內建對照組）；L-184 找惡意 jsp 用 `jsp_backdoor_scan.sh`（看內容特徵、不看位置）；L-137 逐檔換 class 上線前用 `class_diff.py`（可直接吃正式 jar／war：`"app.jar!BOOT-INF/classes/<套件>"`）；L-033 VPN 不穩時傳大檔用 `put_file_resume.py`、在主機上跑換版用 `remote_run.py`。
  - **提醒**（`tool_hints.py`）：L-036 Python 會印非 ASCII 卻沒設定 UTF-8 輸出（執行前）、出現 UnicodeEncodeError（執行後）；L-055 Bash 逾時後提醒改用 PowerShell／Read／Grep，同一工作階段 30 分鐘內再用 Bash 跑簡單指令會再提醒；L-161 經 ssh 重啟／重建容器（含上傳的 .sh）卻沒跑 `scripts/restart_precheck.sh` 時提醒；L-234 執行「改壞檔案＋跑測試＋還原」的對照組腳本前提醒四點（回放 300 個工作階段：去重後提醒 13 次，6 次是真的對照組，7 次是同樣會改檔＋跑測試的演練腳本，提醒寫「看起來是」）。
  - 規則測試：`python -I ~/.claude/skills/agile-crew/hooks/test_guard_tool_input.py`、`test_tool_hints.py`；回放：`hooks/replay_guard.py 30`。改規則前先用過去工作階段的實際指令回放，看會不會大量誤擋（曾經一條 ssh 規則在 Git Bash 誤擋 900 多次，改成只擋 PowerShell）。**回放的每一筆擋下都要打開原始紀錄判斷合不合理**，只看總數會漏（2026-11-05 收尾紀錄檢查：總數對得上，12 筆裡卻有 6 筆實際不會發生，見 L-154）。
- 經驗延續的其他機制：**開工**——SessionStart hook `session_brief.py` 帶入回顧沒做完的行動項、待驗證的技能改版、再犯 ≥ 2 還不是機制的列、這個工作目錄對到的專案 ⏳ 待辦；**收尾**——Stop hook `stop_gate.py`：`retro_gate.py`（push 後沒寫回顧就擋）＋`record_gate.py`（L-034：push 或寫回顧的那一輪，改過的專案或回顧寫的專案對到的專案紀錄沒更新就擋；測試 `test_record_gate.py`、回放 `replay_record_gate.py`）；**耗時**——`scripts/round_time.py --fill` 從工作階段紀錄算每輪耗時填進回顧紀錄，`team_metrics.py --trend` 看每週趨勢；**改技能要驗證成效**——記在 `<本地>/skill-changelog.md`；**定期**——`scripts/team_metrics.py` 算指標與成效，找跨回顧的模式直接改技能（見 `retro.md`〈定期技能優化〉）。

## 規則（兩份都適用）

- 收尾時把這次的新坑加進**最接近的段落**（不是檔尾）。跟技術無關的進 workflow，有技術名詞的進 tech。
- **先分層**（`shareable.md`）：通用的做法寫進這裡；公司、專案、人名、主機、路徑、commit 這些具體資訊寫進 `<本地>/lessons-local.md`〈本地細節〉（同一個編號）；整件事只適用本地的整列寫進本地。寫完跑 `scripts/check_shareable.py` 要 0 行。
- 同一類問題第二次出現時，不能只再寫一次：改成機制（測試、腳本檢查、清單欄位、固定格式），在「以後的做法」寫明機制在哪。
- 一列只寫一件事；同一件事又發生，就在原列補「第二次（日期）」，不另開新列。
- 新增段落時，同步更新下面的索引。
- **新增前先比對重疊**：問題、根因、解法有兩項以上跟既有列相同，就改那一列（補「又一次」或強化做法），不另開新列。
- **只做增量修改，禁止整份改寫或「精簡」**：研究顯示整份重寫會把細節壓掉，效果比不累積還差（ACE 論文 arXiv 2510.04618）。要合併重複的列，一次只合併一組，並保留兩邊的機制與範例。改寫成通用版時也一樣，只刪私人資料。
- **過期淘汰**：一列描述的環境已經不存在（例：工具換掉、平台改版），移到該檔最下面的〈舊做法〉段，不直接刪除。
- 工作方式的檢討（哪裡慢、哪裡重工）不寫這裡，寫回顧（`retro.md`）。
- **事件經過寫這裡，不寫進 `SKILL.md`**：主檔每條規則只留一行＋編號，發生經過、日期、做法步驟都在這裡的那一列。`check_shareable.py` 會擋主檔出現日期或超過長度上限。

## 技術索引：碰到這些就讀 `lessons-tech.md` 的哪一段

| 這次會碰到 | 讀 |
|---|---|
| PowerShell、Bash、heredoc、`python -I`、中文輸出、BOM、CRLF／autocrlf、中文路徑、git commit／拆 commit、git push 要不要登入、開合併請求、別人正在用的 repo、空白被編輯工具吃掉 | T1 Windows 本機、Shell、編碼、Git |
| 部署、正式機、遠端桌面跳板、ssh／scp、VPN、新機器 IP＋帳號、組織的部署文件、啟動測試服務、限制 IP／使用者真實 IP／代理（L-200） | T2 部署與遠端機器（**碰正式機的指令也一定要讀 T1 第一列**） |
| PostgreSQL、Supabase、RLS、PostgREST 錯誤碼、MariaDB、修資料 SQL、演練、交易／savepoint、對調欄位、衍生／對照表重建（L-178）、跨年查詢用穩定識別碼（L-177）、防呆查詢沒索引（L-180）、暫存表比對規則（collation、utf8mb3）（L-182）、補餘額／點數的回退用相對值（L-193） | T3 資料庫（RLS 速度另見 workflow W5「一千筆實測」） |
| Java、Spring Boot、Maven、Lombok、Thymeleaf、@Transactional、外部系統（內部 ERP、LINE Pay）呼叫、JUnit 測試設定 | T4 Java／Spring／Thymeleaf（外部呼叫的設計原則另見 workflow W6） |
| Playwright、截圖、樣式、配色預覽、靜態檔快取 | T5 前端、瀏覽器、截圖 |
| Excel 匯入匯出、原樣匯回、openpyxl、跨年配對識別碼（L-181） | T6 匯入匯出（QA 固定項另見 workflow W6） |
| Notion 寫入、行事曆、本機演練環境（多系統多埠）、滲透測試、n8n、`npm test` 在新 clone 跑不起來 | T7 外部服務與測試工具 |

## 通用流程的段落（`lessons-workflow.md`，依段落讀）

W1 需求與範圍｜W2 團隊分工與交付｜W3 回報與溝通｜W4 文案與介面規則｜W5 驗證方法｜W6 系統設計原則
