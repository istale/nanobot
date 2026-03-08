# Gemini Web Attachments 功能規格（含 Interactive Mode）

狀態：Draft v1  
範圍：`gemini_web` provider（CDP / 非 API）

---

## 1. 目標

讓 nanobot 在 Gemini Web 模式下，支援「透過網頁附檔後送出提示」，並可在：

1) one-shot（`nanobot agent -m ...`）
2) interactive mode（持續對話）

中穩定使用。

---

## 2. 非目標（本階段不做）

- 不做雲端檔案管理/附件持久儲存服務
- 不做跨 provider 的統一附件抽象（先只做 gemini_web）
- 不做大型媒體轉碼流水線

---

## 3. 使用者介面規格

## 3.1 One-shot CLI 參數

- `--attach <path>`（可重複）
- `--attach-mode <auto|image|doc|data>`（預設 `auto`）
- `--attach-instruction "..."`（可選）
- `--attach-timeout-ms <int>`（可選，覆蓋預設）

範例：

```bash
nanobot agent -m "請分析附件重點" --attach ./report.pdf
nanobot agent -m "比較差異" --attach ./v1.png --attach ./v2.png --attach-instruction "請列出差異"
```

## 3.2 Interactive 命令（新增）

- `/attach <path>`：加入待送附件佇列
- `/attach-list`：查看佇列
- `/attach-remove <index|path>`：移除附件
- `/attach-clear`：清空佇列

送出規則：
- 若使用者送出一般訊息且佇列非空，則「本訊息 + 佇列附件」一起送出
- 預設送出成功後清空佇列（可由 config 改）

---

## 4. Config 規格

放在 `providers.geminiWeb.attachments`：

```json
{
  "providers": {
    "geminiWeb": {
      "attachments": {
        "enabled": true,
        "interactiveEnabled": true,
        "maxFiles": 5,
        "maxFileSizeMB": 20,
        "allowedExtensions": ["pdf", "txt", "md", "csv", "json", "png", "jpg", "jpeg", "webp"],
        "uploadTimeoutMs": 60000,
        "strictExistenceCheck": true,
        "autoClearAfterSend": true,
        "persistAttachmentsInSession": false,
        "defaultInstructionWhenEmpty": "請分析附件重點"
      }
    }
  }
}
```

備註：
- `autoClearAfterSend=true`：送出後清空 pending queue
- `persistAttachmentsInSession=true`：送出後保留 queue（進階模式）

---

## 5. 行為流程規格

## 5.1 One-shot

1. 解析 `--attach`
2. 檔案前置檢查（存在、大小、格式）
3. 在 Gemini 頁面執行上傳
4. 等待上傳完成標記
5. 組合提示（`message + attachInstruction`）
6. 送出、擷取結果

## 5.2 Interactive

1. `/attach` 操作只改 session 內 pending queue
2. 使用者送出訊息時：
   - 有 queue：先上傳再送 prompt
   - 無 queue：走原流程
3. 依 `autoClearAfterSend/persistAttachmentsInSession` 處理 queue
4. 回覆上傳與送出狀態給使用者

---

## 6. Session State 規格（Interactive）

每個 session 保存：

- `pending_attachments: list[AttachmentRef]`
- `last_uploaded_attachments: list[AttachmentRef]`（可選）
- `attachment_policy`（clear / persist）

`AttachmentRef` 建議欄位：
- `path`
- `name`
- `size_bytes`
- `added_at`
- `status`（pending/uploaded/failed）
- `error`（可選）

---

## 7. 錯誤處理規格

- 檔案不存在：指出具體 path
- 格式不允許：回報 `allowedExtensions`
- 檔案過大：回報上限與實際大小
- 找不到附件 selector：輸出 screenshot + URL 到 debug 路徑
- 上傳 timeout：回報並保留 queue（可重試）
- 多檔部分失敗：逐檔回報成功/失敗清單

---

## 8. 安全與限制

- 僅 `gemini_web` provider 啟用附件流程
- `restrict_to_workspace=true` 時，附件路徑需在 workspace 內
- Windows 路徑沿用現有正規化（`C:/...`）
- 預設禁止可執行檔副檔名（`.exe`, `.bat`, `.ps1`, `.dll`）

---

## 9. 與既有功能交互

- 與 `sendDelay` 相容：上傳完成後，送出前仍套用延遲規則
- 與 `toolCallTag/toolNamePrefix` 相容：不影響工具解析
- 與 `nativeWebMode` 相容：附件模式不改變網路工具策略

---

## 10. 開發分期

## Phase 1（MVP）
- One-shot 單檔/多檔上傳
- 基本檢查與 timeout
- 基本 debug 輸出

## Phase 2
- Interactive queue（/attach 家族命令）
- 逐檔狀態回報
- queue 清理策略

## Phase 3
- selector fallback 強化
- 上傳完成判定穩定化
- 回歸測試清單與自動化腳本

---

## 11. 驗收標準（DoD）

- one-shot 可成功附檔並得到針對附件的回答
- interactive 可管理 queue 並成功送出
- 錯誤時可定位（含 debug 檔路徑）
- 不破壞既有無附件流程

---

## 12. 後續可選擴充

- `/attach-from-clipboard`
- `/attach-template <audit|summary|extract-table>`
- 對大型 PDF 的分段上傳策略
