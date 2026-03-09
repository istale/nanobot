# Open WebUI 內網特規（nanobot-clean / CDP）

> Branch: `feature/openwebui-cdp-facade`  
> 目的：在特殊內網環境中，讓 Open WebUI 可作為 nanobot-clean（CDP/Gemini Web）的聊天介面。

## 1. 範圍與原則

- 單人單機（single-user, single-host）
- 內網專用，不考慮外網暴露
- 不考慮與 orchestrator 的未來相容性
- 不做多租戶隔離、不做額外 session 層
- 直接沿用 nanobot 既有 agent/session 能力

## 2. API 需求（最小可用）

### 2.1 `GET /v1/models`

- 必須存在（供 Open WebUI 探測模型）
- 回傳 OpenAI-style model list
- 最少提供 1 個模型 id（例如 `nanobot-cdp`）

### 2.2 `POST /v1/chat/completions`

- OpenAI-compatible request/response
- 先支援 non-stream
- 可選支援 stream（SSE）
- 內部將最後一則 user 訊息交給 nanobot agent 執行

## 3. 明確不做

- 不做 API key 驗證
- 不做額外 `ping` endpoint
- 不做獨立 user mapping
- 不做獨立 lifecycle manager

## 4. 啟動策略

採「方案一」：整合到 `nanobot gateway` 啟動流程。

- 仍使用 `nanobot gateway` 作為主要啟動指令
- gateway 啟動後，同時提供 WebUI 所需 `/v1/*` HTTP API

## 5. 驗收標準

1. Open WebUI 可成功連線至 `.../v1`
2. Open WebUI 能讀取 `/v1/models`
3. Open WebUI 可透過 `/v1/chat/completions` 拿到正常回覆
4. 回覆實際來自 nanobot-clean CDP provider 鏈路

## 6. 風險與備註

- 內網特規，日後可能與主線架構差異擴大
- 若 Open WebUI 對 stream 有強依賴，需補 SSE chunk 格式
- 若遇到 UI 探測差異，優先調整 `/v1/models` 與 chat 回傳欄位完整度
