# agile-crew（專業專案開發團隊技能）

> 專案名稱是 `agile-crew`；裝進 Claude Code 之後的技能代號是 `dev-team`（資料夾名稱請維持 `dev-team`，hook 與腳本的路徑都用這個名字）。

Claude Code 技能：接到需求時用 PM／系統規劃與開發／UI-UX／QA 分工，盤點所有情況、驗收通過才交付；
每次交付後做團隊回顧，**把經驗變成技能的改版**，並追蹤每個改動有沒有效。

這個技能**可以直接分享**：裡面只有通用的流程面、技術面內容，沒有任何個人或公司資料。
每個使用者自己的工作方式、公司慣例、專案細節寫在自己的**本地資料夾**，技能每次都會讀，所以越用越貼合你的工作，但不會外流。
分層規則見 `references/shareable.md`。

| 檔案 | 內容 |
|---|---|
| `SKILL.md` | 技能本體（流程與規矩） |
| `references/lessons.md` | 踩坑表入口與索引；`lessons-workflow.md`（流程）、`lessons-tech.md`（技術） |
| `references/agent-briefs.md` | PM／UI-UX／QA 子代理的任務簡報範本 |
| `references/edge-case-checklist.md` | 全面情境盤點清單 |
| `references/retro.md` | 團隊回顧的做法 |
| `references/shareable.md` | 技能與本地分層：什麼寫進技能、什麼寫進本地、怎麼檢查 |
| `scripts/` | `init_local.py` 建本地資料夾、`lesson_id.py` 加鎖取號、`team_metrics.py` 回顧指標、改版成效與每週趨勢、`round_time.py` 每輪耗時（從工作階段紀錄算，回填回顧紀錄）、`check_shareable.py` 檢查技能裡有沒有私人資料、`surefire_check.py` Maven 測試數字 |
| `templates/` | 本地資料夾的範本（`init_local.py` 會複製） |
| `hooks/` | `session_brief.py` 開工帶入、`project_pointer.py` 提到專案名稱時帶入紀錄與程式的位置（不用讀總表）、`guard_tool_input.py` 擋已知錯誤指令、`read_guard.py` 擋「整份讀」踩坑表／回顧紀錄／改版紀錄（一次超過 2 萬字就擋，教它改讀哪一段）、`context_watch.py` 對話累積超過 30 萬 token 時提醒該交接開新的工作階段、`tool_hints.py` 提醒、`stop_gate.py` 收尾檢查（＝`retro_gate.py` 回顧＋`record_gate.py` 專案紀錄，讀一次紀錄、合成一個理由）、`transcript.py` 讀工作階段紀錄的共用模組；各有 `test_*.py`，`replay_*.py` 用過去的紀錄回放看會不會誤擋 |

## 安裝

1. 把這個資料夾放到 `~/.claude/skills/dev-team`（解壓縮，或 `git clone <這個專案的網址> ~/.claude/skills/dev-team`——最後一定要寫資料夾名稱 `dev-team`，不然會變成 `agile-crew`）。重新開啟 Claude Code，技能清單會出現 `dev-team`。
2. 建本地資料夾：`python -I ~/.claude/skills/dev-team/scripts/init_local.py`（預設 `~/.claude/dev-team-local/`，要放別處就設環境變數 `DEV_TEAM_LOCAL`）。它會從 `templates/` 複製：
   - `local-rules.md`：你的慣例——專案紀錄放哪、部署文件在哪、檔案放置規則、回報格式偏好（**請填**）
   - `private-terms.txt`：不能出現在技能裡的字（公司名、專案名、人名、主機、內部用語），一行一個（**請填**）
   - `retro-log.md`、`skill-changelog.md`、`lessons-local.md`：回顧、改版、本地經驗的紀錄（格式已定好，不要改段落標題）
   - `config.json`（選用）：`project_index` 專案總表、`work_root` 文件根目錄、`code_root` 程式碼根目錄，開工時會帶入對到的專案待辦；
     收尾時 `record_gate.py` 用它判斷「這一輪改的檔屬於哪份專案紀錄」，交付了卻沒更新紀錄就擋一次（沒填就不檢查；細項設定 `record_gate` 見 `hooks/record_gate.py` 開頭）
3. （建議）掛 hook：在 `~/.claude/settings.json` 的 `hooks` 加入下面幾段。`<python>` 換成你的 Python 路徑；
   **Windows 上 `~` 不一定會展開，路徑一律寫完整**（例：`"C:/Users/<你>/.claude/skills/dev-team/hooks/guard_tool_input.py"`，含空白要加引號）：

```json
"PreToolUse": [
  {"matcher": "Read", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/read_guard.py", "timeout": 5}]},
  {"matcher": "Edit|Write|Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/guard_tool_input.py", "timeout": 10}]},
  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/tool_hints.py", "timeout": 10}]}
],
"PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/tool_hints.py", "timeout": 10}]}],
"PostToolUseFailure": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/tool_hints.py", "timeout": 10}]}],
"SessionStart": [{"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/session_brief.py", "timeout": 15}]}],
"UserPromptSubmit": [
  {"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/project_pointer.py", "timeout": 5}]},
  {"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/context_watch.py", "timeout": 5}]}
],
"Stop": [{"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/dev-team/hooks/stop_gate.py", "timeout": 30}]}]
```

   `guard_tool_input.py` 會**擋下**幾種已知會出錯的指令（大多是 Windows＋PowerShell／Git Bash 環境的坑；Git Bash 專屬的兩條在 macOS／Linux 自動不檢查），其他 hook 只提醒。
   `stop_gate.py` 在 Claude 要結束時**擋一次**：push 之後沒寫回顧、或交付的這一輪改了專案卻沒更新專案紀錄（要有 `config.json`）。
   只想要回顧檢查就改掛 `retro_gate.py`；設定 `"record_gate": {"enabled": false}` 可關掉紀錄檢查。
   掛之前先跑測試：`python -I ~/.claude/skills/dev-team/hooks/test_guard_tool_input.py`（其他 `test_*.py` 同理）。

4. （選用）讓 Claude 每次接到需求都先用這個技能：在 `~/.claude/CLAUDE.md` 加上

```markdown
## 使用者提出任何需求 → 先載入 `dev-team` 技能

只要是需求、功能、修改、修 bug、調版型、改流程、上線前檢查，**動手前先用 Skill 工具載入 `dev-team`**，照它的流程：
理解需求與目的 → 拆解並盤點所有情況 → 系統規劃 → PM／UI-UX／QA 分工（子代理）→ 驗收通過才交付。
純問答、查狀態、閒聊不需要。
```

## 持續精進

- 每次交付後的回顧：通用的改進寫回技能、個人／公司的寫進本地（`references/retro.md`、`shareable.md`）。
- 改完技能跑 `python -I ~/.claude/skills/dev-team/scripts/check_shareable.py`，要 0 行才分享或推送。
- 想把你的通用改進分享回來：只送技能資料夾的改動，本地資料夾不要送。

## 更新

```
git -C ~/.claude/skills/dev-team pull
```
