"""Gemini Web provider (non-API) backed by Playwright browser automation."""

from __future__ import annotations

import html
import json
import re
import traceback

import json_repair
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from nanobot.config.loader import get_data_dir
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.tools.gemini_web_mvp import run_once


class GeminiWebProvider(LLMProvider):
    """Provider that uses Gemini web UI instead of API."""

    def __init__(
        self,
        user_data_dir: Path | None = None,
        headless: bool = False,
        timeout_ms: int = 120000,
        output_dir: Path | None = None,
        text_protocol_config: dict[str, Any] | None = None,
        send_delay_config: dict[str, Any] | None = None,
    ):
        super().__init__(api_key=None, api_base=None)
        self.user_data_dir = user_data_dir or (get_data_dir() / "profiles" / "gemini-web")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.output_dir = output_dir or Path("outputs")
        self._seeded_system_prompt = False
        self.text_protocol = {
            "enabled": True,
            "include_tool_selection_policy": True,
            "include_parameter_constraints": True,
            "include_parallel_rules": False,
            "include_finish_reason_semantics": False,
            "include_output_format_guarantees": True,
            "include_instruction_priority": True,
            "include_error_recovery_policy": True,
            "include_context_compaction_policy": False,
            "include_native_web_policy": True,
            "native_web_mode": "prefer",  # off | prefer | strict
            "max_tools_in_prompt": 12,
            "max_schema_chars_per_tool": 1200,
            "windows_path_hints": True,
        }
        if isinstance(text_protocol_config, dict):
            self.text_protocol.update(text_protocol_config)

        self.send_delay = {
            "random_wait_enabled": True,
            "random_wait_min_seconds": 1.0,
            "random_wait_max_seconds": 3.0,
            "typing_speed_chars_per_second": 0.0,
            "max_total_wait_seconds": 10.0,
        }
        if isinstance(send_delay_config, dict):
            self.send_delay.update(send_delay_config)

    def get_default_model(self) -> str:
        return "gemini_web/default"

    @staticmethod
    def _to_text(content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text)
                elif isinstance(item, str) and item.strip():
                    parts.append(item)
            return "\n".join(parts)
        if isinstance(content, dict):
            text = content.get("text")
            return text if isinstance(text, str) else ""
        return str(content)

    def _render_tool_constraints(self, tools: list[dict[str, Any]]) -> str:
        if not self.text_protocol.get("include_parameter_constraints", True):
            return ""
        max_tools = int(self.text_protocol.get("max_tools_in_prompt", 12) or 12)
        max_chars = int(self.text_protocol.get("max_schema_chars_per_tool", 1200) or 1200)
        chunks: list[str] = []
        for tool in tools[:max_tools]:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function") or {}
            name = str(fn.get("name") or "").strip()
            if not name:
                continue
            params = fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {}
            required = params.get("required") if isinstance(params.get("required"), list) else []
            properties = params.get("properties") if isinstance(params.get("properties"), dict) else {}
            prop_lines: list[str] = []
            for k, v in list(properties.items())[:8]:
                if isinstance(v, dict):
                    t = v.get("type", "any")
                    enum = v.get("enum")
                    if isinstance(enum, list) and enum:
                        t = f"{t} enum={enum[:6]}"
                    prop_lines.append(f"- {k}: {t}")
            block = (
                f"[TOOL: {name}]\n"
                f"required: {', '.join(required) if required else '(none)'}\n"
                f"properties:\n{chr(10).join(prop_lines) if prop_lines else '- (no properties)'}"
            )
            if name == "exec":
                block += (
                    "\nexample:\n"
                    '<tool_call>{"name":"exec","arguments":{"command":"dir D:/temp"}}</tool_call>'
                )
            chunks.append(block[:max_chars])
        return "\n\n".join(chunks)

    def _build_tool_protocol(self, tools: list[dict[str, Any]] | None) -> str:
        if not tools or not self.text_protocol.get("enabled", True):
            return ""
        raw_names = [t.get("function", {}).get("name", "") for t in tools if isinstance(t, dict)]
        names = [n for n in raw_names if n]
        if not names:
            return ""

        lines = [
            "[TOOL_CALL_PROTOCOL]",
            "When you need a tool, include at least one XML block in your reply:",
            '<tool_call>{"name":"<tool_name>","arguments":{...}}</tool_call>',
            "You may include short natural language before/after the block.",
            f"Allowed tools: {', '.join(names)}",
        ]

        if self.text_protocol.get("include_tool_selection_policy", True):
            lines.append("Tool selection: use list_dir/read_file/edit_file when possible; use exec only when needed.")
        if self.text_protocol.get("include_output_format_guarantees", True):
            lines.append("Place valid JSON inside <tool_call>; avoid markdown fences for tool-call payload.")
        if self.text_protocol.get("include_error_recovery_policy", True):
            lines.append("If tool args are invalid, fix arguments and send a corrected <tool_call> block.")
        if self.text_protocol.get("windows_path_hints", True):
            lines.append(
                "Windows path rule (always apply): use forward slashes for all drive letters, "
                "e.g. C:/path/file.txt or D:/path/file.txt; avoid raw backslashes like C:\\path\\file.txt."
            )
        if self.text_protocol.get("include_instruction_priority", True):
            lines.append("Priority: system instruction > tool protocol > user request > tool result.")

        if self.text_protocol.get("include_native_web_policy", True):
            mode = str(self.text_protocol.get("native_web_mode", "prefer")).lower()
            has_web_search = "web_search" in names
            has_web_fetch = "web_fetch" in names
            if mode == "strict":
                lines.append(
                    "For internet information, use Gemini Web's own browsing/search capability directly. "
                    "Do not emit nanobot web tool calls unless explicitly required by system instruction."
                )
            elif mode == "prefer":
                if has_web_search or has_web_fetch:
                    lines.append(
                        "For internet information, prefer Gemini Web's own browsing/search capability first. "
                        "Use web_search/web_fetch only when the user explicitly asks for tool-based retrieval, "
                        "URL-grounded extraction, or deterministic reproducible fetch output."
                    )
                else:
                    lines.append(
                        "web_search/web_fetch are unavailable in this run. For internet information, use Gemini Web's own browsing/search capability directly."
                    )
        if self.text_protocol.get("include_parallel_rules", False):
            lines.append("Parallel tools: only emit multiple <tool_call> blocks when truly independent.")
        if self.text_protocol.get("include_finish_reason_semantics", False):
            lines.append("If no tool is needed, answer normally without <tool_call>.")
        if self.text_protocol.get("include_context_compaction_policy", False):
            lines.append("Keep tool-call payload minimal; avoid repeating long prior context in arguments.")

        constraints = self._render_tool_constraints(tools)
        body = "\n".join(lines)
        if constraints:
            body += "\n\n[TOOL_SCHEMAS]\n" + constraints
        return "\n\n" + body

    def _repair_hint_from_tool_result(self, tool_result: str) -> str:
        t = (tool_result or "").lower()
        if "invalid parameters for tool 'exec'" in t and "missing required command" in t:
            return (
                "\n\n[RETRY_HINT]\n"
                "The previous tool call was invalid for exec: missing required field 'command'.\n"
                "Send a corrected tool call, e.g.:\n"
                '<tool_call>{"name":"exec","arguments":{"command":"dir D:/temp"}}</tool_call>'
            )
        if "invalid parameters" in t:
            return (
                "\n\n[RETRY_HINT]\n"
                "The previous tool call had invalid arguments. Keep tool name, fix required fields/types, then resend one corrected <tool_call> block."
            )
        return ""

    def _build_prompt(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> str:
        """First turn includes system+tool protocol; later turns send user or tool-result context."""
        latest_user = ""
        latest_system = ""
        latest_tool_result = ""

        for msg in reversed(messages):
            role = msg.get("role")
            text = self._to_text(msg.get("content")).strip()
            if not text:
                continue
            if not latest_user and role == "user":
                latest_user = text
            elif not latest_system and role == "system":
                latest_system = text
            elif not latest_tool_result and role == "tool":
                latest_tool_result = text
            if latest_user and latest_system and latest_tool_result:
                break

        if not latest_user:
            latest_user = "Hello"

        tool_protocol = self._build_tool_protocol(tools)

        if not self._seeded_system_prompt and latest_system:
            self._seeded_system_prompt = True
            return (
                f"[SYSTEM INSTRUCTION - APPLY THIS STYLE FOR THIS CHAT]\n{latest_system}"
                f"{tool_protocol}\n\n[USER]\n{latest_user}"
            )

        if latest_tool_result:
            retry_hint = ""
            if self.text_protocol.get("include_error_recovery_policy", True):
                retry_hint = self._repair_hint_from_tool_result(latest_tool_result)
            return (
                f"[USER]\n{latest_user}\n\n"
                f"[TOOL_RESULT]\n{latest_tool_result}{retry_hint}\n\n"
                "Use the tool result to continue and answer the user."
            )

        return latest_user

    @staticmethod
    def _escape_invalid_json_backslashes(text: str) -> str:
        """Escape invalid backslashes inside JSON string literals.

        Helps with Windows paths like C:\temp\foo when model outputs single
        backslashes that are invalid in JSON.
        """
        out: list[str] = []
        in_str = False
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == '"':
                # Count preceding backslashes to determine if quote is escaped.
                bs = 0
                j = i - 1
                while j >= 0 and text[j] == "\\":
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    in_str = not in_str
                out.append(ch)
                i += 1
                continue

            if in_str and ch == "\\":
                nxt = text[i + 1] if i + 1 < n else ""
                if nxt in ('"', "\\", "/", "b", "f", "n", "r", "t"):
                    out.append(ch)
                elif nxt == "u" and i + 5 < n:
                    out.append(ch)
                else:
                    out.append("\\\\")
                i += 1
                continue

            out.append(ch)
            i += 1

        return "".join(out)

    @staticmethod
    def _load_tool_payload(raw: str) -> dict[str, Any] | None:
        text = (raw or "").strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except Exception:
            fixed = GeminiWebProvider._escape_invalid_json_backslashes(text)
            try:
                data = json.loads(fixed)
            except Exception:
                try:
                    data = json_repair.loads(fixed)
                except Exception:
                    return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _is_escaped(text: str, idx: int) -> bool:
        bs = 0
        j = idx - 1
        while j >= 0 and text[j] == "\\":
            bs += 1
            j -= 1
        return (bs % 2) == 1

    @staticmethod
    def _find_write_file_content_end(text: str, content_value_start: int) -> int:
        """Find end quote index for write_file.content using code-string aware scan.

        Returns index of the terminating quote (the quote before JSON closing braces),
        or -1 if not found.
        """
        i = content_value_start
        n = len(text)
        in_string = False
        in_comment = False
        quote_char = ""
        triple = False

        while i < n:
            if in_comment:
                if text[i] == "\n":
                    in_comment = False
                i += 1
                continue

            if not in_string:
                # JSON terminator candidate: " followed by optional whitespace and } / }}
                if text[i] == '"' and not GeminiWebProvider._is_escaped(text, i):
                    j = i + 1
                    while j < n and text[j].isspace():
                        j += 1
                    if j < n and text[j] == '}':
                        return i

                if text[i] == "#":
                    in_comment = True
                    i += 1
                    continue

                if text.startswith('"""', i) and not GeminiWebProvider._is_escaped(text, i):
                    in_string = True
                    quote_char = '"'
                    triple = True
                    i += 3
                    continue
                if text.startswith("'''", i) and not GeminiWebProvider._is_escaped(text, i):
                    in_string = True
                    quote_char = "'"
                    triple = True
                    i += 3
                    continue
                if text[i] in ('"', "'") and not GeminiWebProvider._is_escaped(text, i):
                    in_string = True
                    quote_char = text[i]
                    triple = False
                    i += 1
                    continue
                i += 1
                continue

            # inside code string
            if triple:
                marker = quote_char * 3
                if text.startswith(marker, i):
                    in_string = False
                    quote_char = ""
                    triple = False
                    i += 3
                    continue
                i += 1
                continue

            # single/double-quoted code string
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == quote_char and not GeminiWebProvider._is_escaped(text, i):
                in_string = False
                quote_char = ""
                i += 1
                continue
            i += 1

        return -1

    @staticmethod
    def _decode_escaped_controls_outside_strings(text: str) -> str:
        """Decode escaped controls only outside code strings.

        Uses [[NNNLLL]] as a temporary newline token so literal "\\n" inside
        string literals can be preserved.
        """
        nl_token = "[[NNNLLL]]"
        out: list[str] = []
        i = 0
        n = len(text)
        in_string = False
        quote_char = ""
        triple = False

        while i < n:
            if not in_string:
                if text.startswith(nl_token, i):
                    out.append("\n")
                    i += len(nl_token)
                    continue
                if text.startswith('"""', i):
                    in_string = True
                    quote_char = '"'
                    triple = True
                    out.append('"""')
                    i += 3
                    continue
                if text.startswith("'''", i):
                    in_string = True
                    quote_char = "'"
                    triple = True
                    out.append("'''")
                    i += 3
                    continue
                if text[i] in ('"', "'") and not GeminiWebProvider._is_escaped(text, i):
                    in_string = True
                    quote_char = text[i]
                    triple = False
                    out.append(text[i])
                    i += 1
                    continue
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    if nxt == "n":
                        out.append("\n")
                        i += 2
                        continue
                    if nxt == "r":
                        out.append("\r")
                        i += 2
                        continue
                    if nxt == "t":
                        out.append("\t")
                        i += 2
                        continue
                out.append(text[i])
                i += 1
                continue

            # inside string: keep escapes literal
            if triple:
                marker = quote_char * 3
                if text.startswith(marker, i):
                    in_string = False
                    quote_char = ""
                    triple = False
                    out.append(marker)
                    i += 3
                    continue
                out.append(text[i])
                i += 1
                continue

            ch = text[i]
            if ch == "\\" and i + 1 < n:
                out.append(text[i])
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote_char and not GeminiWebProvider._is_escaped(text, i):
                in_string = False
                quote_char = ""
                out.append(ch)
                i += 1
                continue
            out.append(ch)
            i += 1

        # Any token left must have been inside string literals; restore as literal "\\n".
        return "".join(out).replace(nl_token, "\\n")

    @staticmethod
    def _restore_common_python_dunder_tokens(text: str) -> str:
        """Restore common markdown-eaten Python dunder guard patterns.

        Some web-rendered markdown paths may drop leading/trailing double underscores,
        turning `if __name__ == "__main__":` into `if name == "main":`.
        """
        out = text
        out = re.sub(
            r"(^|\n)(\s*)if\s+name\s*==\s*(['\"])main\3\s*:",
            r"\1\2if __name__ == \3__main__\3:",
            out,
        )
        return out

    @staticmethod
    def _repair_mailto_pollution(text: str) -> str:
        """Repair web-render/mailto pollution seen in code payloads."""
        out = text
        # Common pollution around decorators/newline markers.
        out = out.replace("mailto:n@", "\\n@")
        out = out.replace("mailto:%0An@", "\\n@")
        # Generic leftover protocol token from auto-linking.
        out = out.replace("mailto:", "")
        return out

    @staticmethod
    def _fallback_write_file_payload(raw: str) -> dict[str, Any] | None:
        """Best-effort fallback parser for malformed write_file payloads.

        Used only when strict JSON parse fails. Targets common Gemini-web drift where
        content is present but JSON escaping is broken near the end of payload.
        """
        text = (raw or "").strip()
        if '"name"' not in text or "write_file" not in text or '"arguments"' not in text:
            return None

        path_match = re.search(r'"path"\s*:\s*"((?:\\.|[^"\\])*)"', text)
        content_start = re.search(r'"content"\s*:\s*"', text)
        if not path_match or not content_start:
            return None

        end = GeminiWebProvider._find_write_file_content_end(text, content_start.end())
        if end < content_start.end():
            # Fallback to reverse-boundary strategy for highly malformed tails.
            end = text.rfind('"}}')
            if end < content_start.end():
                end = text.rfind('"}')
            if end < content_start.end():
                return None

        raw_path = path_match.group(1)
        raw_content = text[content_start.end() : end]
        if '"content":"""' in text and raw_content.startswith('""') and not raw_content.startswith('"""'):
            raw_content = '"' + raw_content

        def _decode_path(s: str) -> str:
            try:
                return json.loads(f'"{s}"')
            except Exception:
                fixed = GeminiWebProvider._escape_invalid_json_backslashes(s)
                try:
                    return json.loads(f'"{fixed}"')
                except Exception:
                    return s.replace('\\\\', '\\')

        # Decode one JSON transport layer; temporarily protect literal \n with token
        # and only turn them into real newlines when outside string literals.
        content_value = raw_content.replace('\\"', '"').replace('\\\\', '\\')
        content_value = content_value.replace("\\n", "[[NNNLLL]]")
        content_value = GeminiWebProvider._decode_escaped_controls_outside_strings(content_value)
        content_value = GeminiWebProvider._repair_mailto_pollution(content_value)
        content_value = GeminiWebProvider._restore_common_python_dunder_tokens(content_value)

        return {
            "name": "write_file",
            "arguments": {
                "path": _decode_path(raw_path),
                "content": content_value,
            },
        }

    @staticmethod
    def _iter_json_objects(text: str) -> list[str]:
        objs: list[str] = []
        depth = 0
        start = -1
        in_str = False
        esc = False
        for i, ch in enumerate(text):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    objs.append(text[start : i + 1])
                    start = -1
        return objs

    @staticmethod
    def _normalize_windows_paths(arguments: dict[str, Any]) -> dict[str, Any]:
        path_keys = {"path", "file_path", "filepath", "workdir", "cwd", "user_data_dir", "output", "output_path"}

        def _normalize_inline_windows_paths(text: str) -> str:
            # Convert obvious Windows drive paths to forward slashes:
            # D:\temp\a.txt -> D:/temp/a.txt
            return re.sub(r"([A-Za-z]):\\([^\s\"']*)", lambda m: f"{m.group(1)}:/{m.group(2).replace('\\', '/')}", text)

        def _fix(v: Any, key: str | None = None) -> Any:
            if isinstance(v, dict):
                return {k: _fix(val, k) for k, val in v.items()}
            if isinstance(v, list):
                return [_fix(x, key) for x in v]
            if isinstance(v, str):
                s = v.strip()
                if re.match(r"^[A-Za-z]:\\", s):
                    return s.replace("\\", "/")
                if key in path_keys and re.match(r"^[A-Za-z]:/", s):
                    return s
                if key == "command":
                    return _normalize_inline_windows_paths(v)
                if key in path_keys and re.match(r"^[A-Za-z]:\\", s):
                    return s.replace("\\", "/")
            return v

        return _fix(arguments)

    def _extract_tool_calls(self, content: str) -> tuple[str | None, list[ToolCallRequest]]:
        calls: list[ToolCallRequest] = []
        source = html.unescape(content or "")

        patterns = [
            re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL),
            re.compile(r"<xx_tool_call>\s*(.*?)\s*</xx_tool_call>", re.DOTALL),  # backward compatibility
            re.compile(r"<tool_code>\s*(.*?)\s*</tool_code>", re.DOTALL),  # compatibility for model drift
            re.compile(r"<xx_tool_code>\s*(.*?)\s*</xx_tool_code>", re.DOTALL),  # compatibility variant
        ]

        candidates: list[str] = []
        for p in patterns:
            candidates.extend(m.group(1).strip() for m in p.finditer(source))

        # Fallback 1: JSON fenced block.
        if not candidates:
            for m in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", source, flags=re.IGNORECASE):
                candidates.append(m.group(1).strip())

        # Fallback 2: scan for JSON objects containing required keys.
        if not candidates:
            for obj in self._iter_json_objects(source):
                if '"name"' in obj and '"arguments"' in obj:
                    candidates.append(obj)

        for raw in candidates:
            data = self._load_tool_payload(raw)

            # For write_file, always prefer dedicated fallback parsing from raw payload,
            # because json.loads/json_repair may succeed but silently corrupt content.
            parsed_name = str((data or {}).get("name", "")).strip() if isinstance(data, dict) else ""
            raw_is_write_file = (
                parsed_name.replace("xx_", "", 1) == "write_file"
                or ('"name"' in raw and '"write_file"' in raw)
            )
            if raw_is_write_file:
                fallback = self._fallback_write_file_payload(raw)
                if fallback:
                    data = fallback

            if not data:
                data = self._fallback_write_file_payload(raw)
            if not data:
                continue
            name = str(data.get("name", "")).strip()
            if name.startswith("xx_"):
                name = name[3:]
            arguments = data.get("arguments", {})
            if isinstance(arguments, str):
                parsed_args = self._load_tool_payload(arguments)
                if isinstance(parsed_args, dict):
                    arguments = parsed_args
            if name and isinstance(arguments, dict):
                if self.text_protocol.get("windows_path_hints", True):
                    arguments = self._normalize_windows_paths(arguments)
                calls.append(ToolCallRequest(id=f"tw_{uuid4().hex[:12]}", name=name, arguments=arguments))

        cleaned = source
        if calls:
            for p in patterns:
                cleaned = p.sub("", cleaned)
            cleaned = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", cleaned, flags=re.IGNORECASE)
            cleaned = cleaned.strip() or None
        return cleaned, calls

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        del model, max_tokens, temperature, reasoning_effort  # Not supported in web mode.

        prompt = self._build_prompt(messages, tools=tools)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        output_path = self.output_dir / f"gemini-web-provider-{ts}.txt"

        try:
            content = await run_once(
                prompt=prompt,
                output_path=output_path,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
                user_data_dir=self.user_data_dir,
                keep_browser_open=True,
                random_wait_enabled=bool(self.send_delay.get("random_wait_enabled", True)),
                random_wait_min_seconds=float(self.send_delay.get("random_wait_min_seconds", 1.0) or 0.0),
                random_wait_max_seconds=float(self.send_delay.get("random_wait_max_seconds", 3.0) or 0.0),
                typing_speed_chars_per_second=float(self.send_delay.get("typing_speed_chars_per_second", 0.0) or 0.0),
                max_total_wait_seconds=float(self.send_delay.get("max_total_wait_seconds", 10.0) or 0.0),
            )
        except Exception as e:
            tb = traceback.format_exc()
            logger.exception("Gemini web provider failed: {}", e)
            debug_path = self.output_dir / f"gemini-web-provider-error-{ts}.log"
            try:
                debug_path.parent.mkdir(parents=True, exist_ok=True)
                debug_path.write_text(tb, encoding="utf-8")
            except Exception:
                pass
            return LLMResponse(
                content=(
                    "Gemini web provider error:\n"
                    f"{e}\n\n"
                    f"Traceback saved to: {debug_path}"
                ),
                finish_reason="error",
                usage={"prompt_tokens": len(prompt), "completion_tokens": 0, "total_tokens": len(prompt)},
            )

        cleaned, tool_calls = self._extract_tool_calls(content)
        usage = {
            "prompt_tokens": len(prompt),
            "completion_tokens": len(content),
            "total_tokens": len(prompt) + len(content),
        }
        if tool_calls:
            return LLMResponse(content=cleaned, tool_calls=tool_calls, finish_reason="tool_calls", usage=usage)
        return LLMResponse(content=cleaned or content, finish_reason="stop", usage=usage)
