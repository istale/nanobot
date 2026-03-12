import os
import sys
import types


def _make_provider():
    # Avoid requiring playwright at import-time for parser unit tests.
    fake_async_api = types.ModuleType("playwright.async_api")
    fake_async_api.BrowserContext = object
    fake_async_api.Page = object
    fake_async_api.TimeoutError = RuntimeError
    fake_async_api.Playwright = object

    async def _fake_async_playwright():
        return None

    fake_async_api.async_playwright = _fake_async_playwright
    sys.modules.setdefault("playwright", types.ModuleType("playwright"))
    sys.modules["playwright.async_api"] = fake_async_api
    os.environ.setdefault("NANOBOT_GEMINI_WEB_URL", "https://gemini.google.com/app")

    from nanobot.providers.gemini_web_provider import GeminiWebProvider

    return GeminiWebProvider()


def test_extract_tool_code_tag_as_tool_call():
    provider = _make_provider()
    content = (
        'Before call\n'
        '<tool_code>{"name":"read_file","arguments":{"path":"D:\\\\temp\\\\README.md"}}</tool_code>\n'
        'After call'
    )

    cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    assert calls[0].name == "read_file"
    # Windows path normalization should still apply in compatibility path
    assert calls[0].arguments["path"] == "D:/temp/README.md"
    assert "tool_code" not in (cleaned or "")


def test_fallback_parse_malformed_write_file_payload():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\\\temp\\\\main.py",'
        '"content":"""module doc"""\nprint(1)\nprint(\"line1\\\\nline2\")"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert calls[0].arguments["path"] == "D:/temp/main.py"
    assert '"""module doc"""' in calls[0].arguments["content"]
    assert "print(1)" in calls[0].arguments["content"]
    # Keep string escape sequence as literal, do not convert to real newline.
    assert 'print("line1\\nline2")' in calls[0].arguments["content"]
    assert "tool_call" not in (cleaned or "")


def test_write_file_escaped_newlines_outside_strings_are_restored():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\\\temp\\\\y.py",'
        '"content":"def main():\\n    print(\"ok\")\\nprint(\"line1\\\\nline2\")"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    out = calls[0].arguments["content"]
    assert "def main():\n    print(\"ok\")" in out
    assert 'print("line1\\nline2")' in out


def test_restore_python_dunder_guard_pattern():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\\\temp\\\\guard.py",'
        '"content":"def run():\\n    pass\\n\\nif name == \"main\":\\n    run()"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    out = calls[0].arguments["content"]
    assert 'if __name__ == "__main__":' in out


def test_write_file_end_boundary_ignores_braces_inside_strings():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\\\temp\\\\x.py",'
        '"content":"print(\\"}} inside string\\")\nprint(2)"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    assert calls[0].name == "write_file"
    assert 'print("}} inside string")' in calls[0].arguments["content"]
    assert "print(2)" in calls[0].arguments["content"]


def test_write_file_comment_with_triple_quotes_does_not_truncate():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\temp\\comment.py",'
        '"content":"# \"\"\" marker in comment\\nprint(123)\\nprint(456)"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    out = calls[0].arguments["content"]
    assert '# """ marker in comment' in out
    assert "print(123)" in out
    assert "print(456)" in out


def test_write_file_newline_before_decorator_restored():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\temp\\api.py",'
        '"content":"def x():\\n    return 1\\n@app.route(\"/ok\")\\ndef ok():\\n    return \'ok\'"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    out = calls[0].arguments["content"]
    assert "def x():\n    return 1\n@app.route(\"/ok\")" in out


def test_write_file_repairs_mailto_pollution_near_decorator():
    provider = _make_provider()
    malformed = (
        '{"name":"write_file","arguments":{"path":"D:\\temp\\polluted.py",'
        '"content":"@app.routemailto:n@app.route(\"/\")\\ndef index():\\n    return \'ok\'"}}'
    )
    content = f"<tool_call>{malformed}</tool_call>"

    _cleaned, calls = provider._extract_tool_calls(content)

    assert len(calls) == 1
    out = calls[0].arguments["content"]
    assert "@app.route(\"/\")" in out
    assert "mailto:" not in out
