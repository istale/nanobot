# Open WebUI 內網特規 - 建置與使用（Windows）

## A. 建置環境

```powershell
cd D:\nanobot-root\repos\nanobot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .
pip install playwright
```

> CDP 模式不需 `playwright install chromium`。

## B. 啟動前必要環境變數（當前視窗）

```powershell
$env:NANOBOT_HOME="D:\nanobot-root\home"
$env:NANOBOT_CHROME_CDP_URL="http://127.0.0.1:9222"
$env:NANOBOT_GEMINI_WEB_URL="https://gemini.google.com/app"
```

## C. 啟動 CDP Chrome（獨立 profile）

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\nanobot-root\home\profiles\chrome-cdp"
```

## D. 啟動 nanobot gateway

```powershell
cd D:\nanobot-root\repos\nanobot
.\.venv\Scripts\Activate.ps1
$env:NANOBOT_HOME="D:\nanobot-root\home"
$env:NANOBOT_CHROME_CDP_URL="http://127.0.0.1:9222"
$env:NANOBOT_GEMINI_WEB_URL="https://gemini.google.com/app"

nanobot gateway --port 18790 --verbose
```

## E. Open WebUI 端設定

- API Base URL: `http://<nanobot-host>:<http-port>/v1`
- 選用模型：`nanobot-cdp`（由 `/v1/models` 提供）

## F. 快速驗證

```powershell
# 模型清單
curl http://127.0.0.1:<http-port>/v1/models

# 對話
curl -X POST http://127.0.0.1:<http-port>/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"nanobot-cdp","messages":[{"role":"user","content":"hello"}]}'
```

---

若出現 CDP 連線問題，先檢查：

```powershell
Invoke-RestMethod http://127.0.0.1:9222/json/version
```
