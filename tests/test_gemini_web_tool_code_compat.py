import os
import sys
import types


def test_extract_tool_code_tag_as_tool_call():
    # Avoid requiring playwright at import-time for this parser unit test.
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

    provider = GeminiWebProvider()
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
