# agile-crew：一個負責人＋AI 團隊的敏捷協作流程

> [English version below](#english)
>
> 專案名稱、技能代號、資料夾名稱都是 `agile-crew`（hook 與腳本的路徑都用這個名字）。

這是一個 Claude Code 技能，讓 AI 不是「講什麼就只做什麼」，而是像一個小團隊在運作：
你是決定做什麼、先做哪個的人；AI 分成 PM、系統規劃與開發、UI/UX、QA 四個角色，把需求做完、驗收過才交給你。

它在意的是**團隊怎麼運作**，不是某一種程式技術：

- **小塊交付、早點給你看**：大的需求切成幾輪，每輪交出一塊驗收過、看得到的成果，看完再決定下一輪。
- **待辦有順序**：待辦分成進行中／接下來／之後／等別人，每項寫明為誰、要達到什麼、怎樣算完成。
- **完成有定義**：照需求大小各有一張清單，沒達到的不叫完成，交付時會明講還差什麼。
- **進行中有上限**：每個專案同時進行的事最多 2 項，先做完再開新的。
- **驗收後才交付**：QA 與 UI/UX 由獨立的子代理實測，看的是實際畫面與資料。
- **每輪回顧，而且回顧會改流程**：每次交付後檢討哪裡慢、哪裡重工，發現直接改成技能的規則、清單或腳本，並追蹤改了有沒有效。
- **需求多大就做多少**：小的修改不開子代理、不多讀檔，流程不會因為這些做法變重。

敏捷開發裡沒有採用的（固定兩週一輪、每日站會、故事點、燃盡圖）與原因，寫在 `references/agile.md`。

這個技能**可以直接分享**：裡面只有通用的流程面、技術面內容，沒有任何個人或公司資料。
每個使用者自己的工作方式、公司慣例、專案細節寫在自己的**本地資料夾**，技能每次都會讀，所以越用越貼合你的工作，但不會外流。
分層規則見 `references/shareable.md`。

| 檔案 | 內容 |
|---|---|
| `SKILL.md` | 技能本體（流程與規矩） |
| `references/agile.md` | 敏捷做法：待辦排序與拆小、分輪交付、完成的定義、進行中上限、回顧怎麼接上輪次 |
| `references/lessons.md` | 踩坑表入口與索引；`lessons-workflow.md`（流程）、`lessons-tech.md`（技術） |
| `references/agent-briefs.md` | PM／UI-UX／QA 子代理的任務簡報範本 |
| `references/edge-case-checklist.md` | 全面情境盤點清單 |
| `references/handoff.md` | 工作階段之間的交接：交接單格式、由 Claude 開新的工作階段、接手怎麼開工、怎麼量交接順不順（`scripts/handoff_metrics.py`） |
| `references/retro.md` | 團隊回顧的做法 |
| `references/shareable.md` | 技能與本地分層：什麼寫進技能、什麼寫進本地、怎麼檢查 |
| `scripts/` | `init_local.py` 建本地資料夾、`lesson_id.py` 加鎖取號、`team_metrics.py` 回顧指標、改版成效與每週趨勢、`round_time.py` 每輪耗時（從工作階段紀錄算，回填回顧紀錄）、`check_shareable.py` 檢查技能裡有沒有私人資料、`surefire_check.py` Maven 測試數字 |
| `templates/` | 本地資料夾的範本（`init_local.py` 會複製）；`backlog.md` 是待辦的分段格式，複製到你的專案紀錄用 |
| `hooks/` | `session_brief.py` 開工帶入、`project_pointer.py` 提到專案名稱時帶入紀錄與程式的位置（不用讀總表）、`guard_tool_input.py` 擋已知錯誤指令、`read_guard.py` 擋「整份讀」踩坑表／回顧紀錄／改版紀錄（一次超過 2 萬字就擋，教它改讀哪一段）、`context_watch.py` 對話累積超過 30 萬 token 時提醒該交接開新的工作階段、`tool_hints.py` 提醒、`stop_gate.py` 收尾檢查（＝`retro_gate.py` 回顧＋`record_gate.py` 專案紀錄，讀一次紀錄、合成一個理由）、`transcript.py` 讀工作階段紀錄的共用模組；各有 `test_*.py`，`replay_*.py` 用過去的紀錄回放看會不會誤擋 |

## 安裝

1. 把這個資料夾放到 `~/.claude/skills/agile-crew`（解壓縮，或 `git clone <這個專案的網址> ~/.claude/skills/agile-crew`）。重新開啟 Claude Code，技能清單會出現 `agile-crew`。
2. 建本地資料夾：`python -I ~/.claude/skills/agile-crew/scripts/init_local.py`（預設 `~/.claude/agile-crew-local/`，要放別處就設環境變數 `AGILE_CREW_LOCAL`）。它會從 `templates/` 複製：
   - `local-rules.md`：你的慣例——專案紀錄放哪、部署文件在哪、檔案放置規則、回報格式偏好（**請填**）
   - `private-terms.txt`：不能出現在技能裡的字（公司名、專案名、人名、主機、內部用語），一行一個（**請填**）
   - `retro-log.md`、`skill-changelog.md`、`lessons-local.md`：回顧、改版、本地經驗的紀錄（格式已定好，不要改段落標題）
   - `config.json`（選用）：`project_index` 專案總表、`work_root` 文件根目錄、`code_root` 程式碼根目錄，開工時會帶入對到的專案待辦；
     收尾時 `record_gate.py` 用它判斷「這一輪改的檔屬於哪份專案紀錄」，交付了卻沒更新紀錄就擋一次（沒填就不檢查；細項設定 `record_gate` 見 `hooks/record_gate.py` 開頭）
3. （建議）掛 hook：在 `~/.claude/settings.json` 的 `hooks` 加入下面幾段。`<python>` 換成你的 Python 路徑；
   **Windows 上 `~` 不一定會展開，路徑一律寫完整**（例：`"C:/Users/<你>/.claude/skills/agile-crew/hooks/guard_tool_input.py"`，含空白要加引號）：

```json
"PreToolUse": [
  {"matcher": "Read", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/read_guard.py", "timeout": 5}]},
  {"matcher": "Edit|Write|Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/guard_tool_input.py", "timeout": 10}]},
  {"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/tool_hints.py", "timeout": 10}]}
],
"PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/tool_hints.py", "timeout": 10}]}],
"PostToolUseFailure": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/tool_hints.py", "timeout": 10}]}],
"SessionStart": [{"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/session_brief.py", "timeout": 15}]}],
"UserPromptSubmit": [
  {"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/project_pointer.py", "timeout": 5}]},
  {"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/context_watch.py", "timeout": 5}]}
],
"Stop": [{"hooks": [{"type": "command", "command": "<python> -I ~/.claude/skills/agile-crew/hooks/stop_gate.py", "timeout": 30}]}]
```

   `guard_tool_input.py` 會**擋下**幾種已知會出錯的指令（大多是 Windows＋PowerShell／Git Bash 環境的坑；Git Bash 專屬的兩條在 macOS／Linux 自動不檢查），其他 hook 只提醒。
   `stop_gate.py` 在 Claude 要結束時**擋一次**：push 之後沒寫回顧、或交付的這一輪改了專案卻沒更新專案紀錄（要有 `config.json`）。
   只想要回顧檢查就改掛 `retro_gate.py`；設定 `"record_gate": {"enabled": false}` 可關掉紀錄檢查。
   掛之前先跑測試：`python -I ~/.claude/skills/agile-crew/hooks/test_guard_tool_input.py`（其他 `test_*.py` 同理）。

4. （選用）讓 Claude 每次接到需求都先用這個技能：在 `~/.claude/CLAUDE.md` 加上

```markdown
## 使用者提出任何需求 → 先載入 `agile-crew` 技能

只要是需求、功能、修改、修 bug、調版型、改流程、上線前檢查，**動手前先用 Skill 工具載入 `agile-crew`**，照它的流程：
理解需求與目的 → 拆解並盤點所有情況 → 系統規劃 → PM／UI-UX／QA 分工（子代理）→ 驗收通過才交付。
純問答、查狀態、閒聊不需要。
```

## 持續精進

- 每次交付後的回顧：通用的改進寫回技能、個人／公司的寫進本地（`references/retro.md`、`shareable.md`）。
- 改完技能跑 `python -I ~/.claude/skills/agile-crew/scripts/check_shareable.py`，要 0 行才分享或推送。
- 想把你的通用改進分享回來：只送技能資料夾的改動，本地資料夾不要送。

## 更新

```
git -C ~/.claude/skills/agile-crew pull
```

## 問題與建議

- 碰到問題、想要新功能：到 [Issues](https://github.com/leo0823wu/agile-crew/issues) 開一筆。
- 想問怎麼用、聊聊想法：到 [Discussions](https://github.com/leo0823wu/agile-crew/discussions)。
- 開之前請拿掉公司名稱、主機、帳號、個資等內容，這兩個地方所有人都看得到。

---

<a id="english"></a>

# agile-crew: an agile workflow for one lead and an AI team

> The project name, the skill id and the folder name are all `agile-crew` (the hooks and scripts use that path).
>
> The skill itself (`SKILL.md`, `references/`, templates, hook messages) is written in Traditional Chinese. Claude follows it in any language, and it reports in the language you use.

This is a Claude Code skill that makes the AI work like a small team instead of doing only what was literally asked.
You decide what gets built and in what order. The AI takes four roles — PM, planning and development, UI/UX, and QA — and hands work over only after it has been tested.

It is about **how a team works**, not about a particular technology:

- **Small deliveries, early feedback.** Large requests are split into rounds. Each round ends with a tested, visible result, and you decide what the next round is after seeing it.
- **An ordered backlog.** To-dos are grouped as in progress / next / later / waiting on others. Each item says who it is for, what it should achieve, and how to tell it is done.
- **A definition of done.** There is one checklist per request size. Work that does not meet it is not reported as done; the delivery report says what is missing.
- **A limit on work in progress.** At most 2 items in progress per project. Finish one before starting another.
- **Tested before delivery.** QA and UI/UX checks are run by independent subagents against the real screens and data.
- **A retrospective every round that changes the process.** After each delivery the team reviews what was slow and what was redone. Each finding becomes a rule, a checklist item, or a script in the skill, and later rounds record whether the change worked.
- **Effort scaled to the request.** Small changes use no subagents and read few files, so these practices do not make small work heavier.

`references/agile.md` lists the agile practices that were left out (fixed two-week sprints, daily stand-ups, story points, burndown charts) and why.

The skill is **safe to share**: it contains only general process and technical content, with no personal or company data.
Your own conventions, company rules, and project details live in a **local folder** that the skill reads each time, so it adapts to your work without leaking anything.
See `references/shareable.md` for the split.

## Install

1. Put this folder at `~/.claude/skills/agile-crew` (unzip it, or `git clone <this repo's URL> ~/.claude/skills/agile-crew` — the folder name must be `agile-crew`). Restart Claude Code; `agile-crew` appears in the skill list.
2. Create the local folder: `python -I ~/.claude/skills/agile-crew/scripts/init_local.py` (default `~/.claude/agile-crew-local/`; set the `AGILE_CREW_LOCAL` environment variable to use another place). Then fill in `local-rules.md` (your conventions) and `private-terms.txt` (words that must never appear in the skill).
3. (Recommended) Register the hooks in `~/.claude/settings.json`. The JSON block is in the Chinese section above. On Windows, write full paths instead of `~`.
   - `guard_tool_input.py` **blocks** a few commands that are known to fail, mostly on Windows with PowerShell or Git Bash. The other tool hooks only print reminders.
   - `stop_gate.py` blocks **once** when Claude is about to stop, if work was pushed without a retrospective entry, or a project was changed without updating its project record. The record check needs `config.json` in the local folder, which tells it where your project records and code live.
   - `session_brief.py` brings unfinished follow-ups into the start of each session, and `context_watch.py` reminds Claude to hand over and start a new session when a conversation gets long.
   - Run the tests before registering a hook: `python -I ~/.claude/skills/agile-crew/scripts/run_tests.py`.
4. (Optional) Tell Claude to load the skill for every request by adding a short section to `~/.claude/CLAUDE.md`; the Chinese section above has the text.

## Continuous improvement

- After each delivery, general improvements go back into the skill, and personal or company ones go into the local folder (`references/retro.md`, `references/shareable.md`).
- After editing the skill, run `python -I ~/.claude/skills/agile-crew/scripts/check_shareable.py`. It must print 0 lines before you share or push.
- To contribute improvements back, send only changes to the skill folder, never the local folder.

## Update

```
git -C ~/.claude/skills/agile-crew pull
```

## Questions and suggestions

- Found a problem or want a feature: open an [issue](https://github.com/leo0823wu/agile-crew/issues).
- Questions about how to use it, or ideas to talk through: use [Discussions](https://github.com/leo0823wu/agile-crew/discussions).
- Both are public. Remove company names, hosts, accounts and personal data before posting.
