# write_file 文字處理說明（custom branch）

> 適用分支：`custom`  
> 目的：記錄 Gemini Web provider 在 `write_file` tool-call 的文字解析策略，供內網實測比對。

## 1) 背景

在內網 Gemini Web（text protocol）場景，模型可能輸出：

- tag 漂移（`<tool_call>` / `<tool_code>`）
- JSON 看似合法但 `content` 被截斷或污染
- `"""`、反斜線、Windows 路徑、字串 escape（例如 `\\n`）造成解析偏差

因此 custom branch 對 `write_file` 增加了專用解析策略（fallback parser）。

## 2) 目前流程（重點）

在 `nanobot/providers/gemini_web_provider.py` 的 `_extract_tool_calls()` 中：

1. 先嘗試一般 JSON 解析（`json.loads` / backslash 修復 / `json_repair`）
2. **若判斷是 `write_file`，優先改用專用 fallback 解析 raw payload**
3. fallback 成功時，以 fallback 結果覆蓋一般解析結果

## 3) `write_file` 專用 fallback 解析

函式：`_fallback_write_file_payload(raw: str)`

- `content` 由 `"content":"` 起點後開始擷取
- 尾端優先用反向搜尋 `"}}`，其次 `"}` 作為結束邊界
- 對 `"content":"""...` 常見破損形態做最小修復

### 解碼策略（目前版本）

- `path`：做最小 JSON-safe 解碼，失敗時保守還原
- `content`：**保留字面 escape 序列**，不展開為真控制字元
  - 不做：`\\n -> \n`、`\\t -> \t`、`\\r -> \r`
  - 只做最小必要還原：`\\" -> "`、`\\\\ -> \\`

> 目的：避免 `print("a\\nb")` 被寫成跨行內容。

## 4) 與 Windows 路徑的關係

仍會經過 `_normalize_windows_paths(arguments)`：

- path 類欄位會正規化（例：`D:\\temp\\a.py` -> `D:/temp/a.py`）
- `content` 不做路徑正規化

## 5) 已知限制

- fallback 依賴目前常見輸出模式；若模型再漂移，仍可能失效
- 極端複雜字串（巢狀引號/反斜線）可能仍需更強 parser
- 目前只保護 `write_file`，`edit_file` 尚未套同級策略

## 6) 回歸測試

測試檔：`tests/test_gemini_web_tool_code_compat.py`

執行：

```bash
python -m pytest -q tests/test_gemini_web_tool_code_compat.py
```
