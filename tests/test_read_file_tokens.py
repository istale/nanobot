import asyncio
from pathlib import Path

from nanobot.agent.tools.filesystem import ReadFileTool


def test_read_file_wraps_with_file_tokens(tmp_path: Path):
    fp = tmp_path / "a.py"
    fp.write_text("print('ok')\n", encoding="utf-8")

    tool = ReadFileTool(workspace=tmp_path, allowed_dir=tmp_path)
    out = asyncio.run(tool.execute("a.py"))

    assert out.startswith('[[FILE_START path="a.py"]]\n')
    assert "print('ok')" in out
    assert out.rstrip().endswith('[[FILE_END path="a.py"]]')


def test_read_file_truncated_still_has_tokens(tmp_path: Path):
    fp = tmp_path / "big.txt"
    fp.write_text("x" * 10, encoding="utf-8")

    tool = ReadFileTool(workspace=tmp_path, allowed_dir=tmp_path)
    tool._MAX_CHARS = 5
    out = asyncio.run(tool.execute("big.txt"))

    assert out.startswith('[[FILE_START path="big.txt"]]\n')
    assert "truncated" in out
    assert out.rstrip().endswith('[[FILE_END path="big.txt"]]')
