# Nanobot（custom branch）Windows 完整安裝 SOP（CDP 模式）

> 目的：在新 Windows 電腦上，使用 `custom` 分支完成可執行環境，並採用 **CDP 連線既有 Chrome**（不使用 Playwright 下載 Chromium）。

---

## 0. 建議目錄規劃（統一 root）

建議先選一個根目錄，例如：

- `D:\nanobot-root`（若只有 C 槽就改 `C:\nanobot-root`）

目錄結構：

```text
nanobot-root/
  home/                    # NANOBOT_HOME
    config.json
    profiles/
  workspace-default/       # 預設 agent workspace
  workspace-<agent_name>/  # 其他 agent workspace（可選）
  repos/
    nanobot/               # 程式碼 repo
```

---

## 1. 前置需求

1. 安裝 **Git**
2. 安裝 **Python 3.11+**（建議 3.11 或 3.12）
3. 安裝 **Google Chrome**
4. 可使用 PowerShell

檢查：

```powershell
git --version
python --version
py --version
```

---

## 2. Clone custom 分支

```powershell
mkdir D:\nanobot-root\repos -Force
cd D:\nanobot-root\repos
git clone -b custom https://github.com/istale/nanobot.git
cd .\nanobot
```

> 若只有 C 槽，請把上面 `D:\nanobot-root` 全部改成 `C:\nanobot-root`。

---

## 3. 建立 venv 並安裝依賴

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
pip install playwright
```

> CDP 模式仍需要 Python 的 `playwright` 套件，但 **不需要** `playwright install chromium`。

---

## 4. 設定 NANOBOT_HOME（固定到 root/home）

### 4.1 永久設定（建議）

```powershell
setx NANOBOT_HOME "D:\nanobot-root\home"
```

### 4.2 重新開 PowerShell 後確認

```powershell
echo $env:NANOBOT_HOME
```

應看到：

- `D:\nanobot-root\home`

> 若你想立即在當前視窗生效，也可先加：

```powershell
$env:NANOBOT_HOME = "D:\nanobot-root\home"
```

---

## 5. 啟動一次 nanobot 以生成/讀取 config

```powershell
nanobot --help
```

預期 config 位置：

- `D:\nanobot-root\home\config.json`

---

## 6. 編輯 config.json（設定 provider + workspace + tool allowlist）

編輯 `D:\nanobot-root\home\config.json`，建議至少包含：

```json
{
  "agents": {
    "defaults": {
      "model": "gemini_web/default",
      "provider": "gemini_web",
      "workspace": "D:/nanobot-root/workspace-default"
    }
  },
  "tools": {
    "enabledTools": [
      "read_file",
      "write_file",
      "edit_file",
      "list_dir",
      "exec",
      "web_search",
      "web_fetch",
      "message",
      "spawn",
      "cron"
    ]
  },
  "providers": {
    "geminiWeb": {
      "textProtocol": {
        "nativeWebMode": "prefer"
      }
    }
  }
}
```

> Windows 路徑建議使用 `/`，如 `D:/...`，可減少反斜線跳脫問題。  
> `tools.enabledTools` 是「可用工具白名單」。不填時預設允許全部內建工具。

---

## 6.1 內建可用 tools 清單（供 `enabledTools` 參考）

- `read_file`：讀取檔案
- `write_file`：寫入檔案
- `edit_file`：以字串替換編輯檔案
- `list_dir`：列目錄
- `exec`：執行 shell 指令
- `web_search`：網路搜尋
- `web_fetch`：抓取網頁內容
- `message`：發送訊息到已連接 channel
- `spawn`：啟動子代理
- `cron`：排程（需有啟用 cron service）

內網限制範例（關閉 nanobot 網路工具，交給 Gemini Web 內建網路能力）：

```json
{
  "tools": {
    "enabledTools": ["read_file", "write_file", "edit_file", "list_dir", "exec", "message", "spawn", "cron"]
  },
  "providers": {
    "geminiWeb": {
      "textProtocol": {
        "nativeWebMode": "strict"
      }
    }
  }
}
```

最小安全範例（僅檔案工具）：

```json
{
  "tools": {
    "enabledTools": ["read_file", "write_file", "edit_file", "list_dir"]
  }
}
```

---

## 7. 建立 workspace 目錄

```powershell
mkdir D:\nanobot-root\workspace-default -Force
mkdir D:\nanobot-root\workspace-agentA -Force
mkdir D:\nanobot-root\workspace-agentB -Force
```

> 多 agent 時，按規則建立：`workspace-<agent_name>`。

---

## 8. 啟動 Chrome（CDP 模式）

請用 **獨立 profile 目錄** 開 Chrome，避免和日常 Chrome profile 互鎖。

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\nanobot-root\home\profiles\chrome-cdp"
```

---

## 9. 設定 CDP 連線位址

### 當前 session 生效：

```powershell
$env:NANOBOT_CHROME_CDP_URL="http://127.0.0.1:9222"
```

### 驗證（可選）：

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```

有回傳 JSON 代表 CDP 正常。

---

## 10. 首次執行測試

在 repo 根目錄（且 venv 已啟用）：

```powershell
nanobot agent -m "hello"
```

若 Gemini Web 需要登入，請在跳出的 Chrome 視窗完成登入後再測一次。

---

## 11. 日常啟動順序（建議）

1. 開 PowerShell，進 repo
2. 啟用 venv：
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
3. 設環境變數（若不是永久）：
   ```powershell
   $env:NANOBOT_HOME="D:\nanobot-root\home"
   $env:NANOBOT_CHROME_CDP_URL="http://127.0.0.1:9222"
   ```
4. 啟動 Chrome（CDP 參數）
5. 執行 `nanobot agent ...`

---

## 12. 常見問題排查

### Q1: `nanobot` 指令找不到
- 確認 venv 已啟用
- 重新執行 `pip install -e .`

### Q2: 連不上 CDP
- 確認 Chrome 用了 `--remote-debugging-port=9222`
- 確認 `NANOBOT_CHROME_CDP_URL` 設為 `http://127.0.0.1:9222`
- 用 `Invoke-RestMethod http://127.0.0.1:9222/json/version` 測

### Q3: Chrome profile 被鎖（Singleton/Process lock）
- 一律使用獨立 `--user-data-dir`
- 關掉舊的 CDP Chrome 視窗後重開

### Q4: workspace 路徑不生效
- 檢查 `config.json` 是否位於 `NANOBOT_HOME` 下
- 檢查 `agents.defaults.workspace` 是否寫成合法路徑

---

## 13. 升級維護（簡版）

本 repo 已有 `sync_branches.sh` 可同步 `main` 與 `custom`（單人維護模式）。

```powershell
bash ./sync_branches.sh
```

> 若你的環境沒有 bash，可改在 Git Bash 執行，或之後再補一版 `.ps1`。

---

## 14. 最小驗收清單

- [ ] `nanobot --help` 可執行
- [ ] `NANOBOT_HOME` 指向 `nanobot-root/home`
- [ ] `config.json` 可讀取且 model/provider 正確
- [ ] Chrome 已用 9222 CDP 啟動
- [ ] `NANOBOT_CHROME_CDP_URL` 已設定
- [ ] `nanobot agent -m "hello"` 可完成回應
