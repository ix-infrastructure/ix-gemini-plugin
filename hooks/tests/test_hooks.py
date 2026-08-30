#!/usr/bin/env python3
"""Smoke tests for Gemini hook scripts — verifiable without a live Gemini session."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent.resolve()
PYTHON = sys.executable


def _run_hook(script: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(HOOKS_DIR / script)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
    )


# ── after_tool ────────────────────────────────────────────────────────────────

class AfterToolHookTest(unittest.TestCase):

    def test_after_tool_empty_stdin_exits_zero(self) -> None:
        result = _run_hook("after_tool.py", stdin="")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_after_tool_valid_non_write_command_exits_zero(self) -> None:
        event = json.dumps({"tool_input": {"command": "ls -la"}, "cwd": str(HOOKS_DIR)})
        result = _run_hook("after_tool.py", stdin=event)
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_after_tool_valid_write_command_exits_zero(self) -> None:
        event = json.dumps({"tool_input": {"command": "touch /tmp/ix_test_file"}, "cwd": str(HOOKS_DIR)})
        result = _run_hook("after_tool.py", stdin=event)
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_after_tool_malformed_json_exits_zero(self) -> None:
        result = _run_hook("after_tool.py", stdin="not json {{{")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_after_tool_missing_fields_exits_zero(self) -> None:
        event = json.dumps({"unexpected_field": "value"})
        result = _run_hook("after_tool.py", stdin=event)
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_after_tool_no_stdout(self) -> None:
        event = json.dumps({"tool_input": {"command": "ls"}, "cwd": str(HOOKS_DIR)})
        result = _run_hook("after_tool.py", stdin=event)
        assert result.stdout == "", f"after_tool should produce no stdout, got: {result.stdout!r}"


# ── session_end ───────────────────────────────────────────────────────────────

class SessionEndHookTest(unittest.TestCase):

    def test_session_end_empty_stdin_exits_zero(self) -> None:
        result = _run_hook("session_end.py", stdin="")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_session_end_malformed_json_exits_zero(self) -> None:
        result = _run_hook("session_end.py", stdin="garbage")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


# ── before_tool ───────────────────────────────────────────────────────────────

class BeforeToolHookTest(unittest.TestCase):

    def test_before_tool_empty_stdin_exits_zero(self) -> None:
        result = _run_hook("before_tool.py", stdin="")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


    def test_before_tool_malformed_json_exits_zero(self) -> None:
        result = _run_hook("before_tool.py", stdin="not json")
        assert result.returncode == 0, f"expected exit 0, got {result.returncode}\nstderr: {result.stderr}"


# ── _is_write_command ─────────────────────────────────────────────────────────

class WriteCommandDetectionTest(unittest.TestCase):

    def test_write_command_detection(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        from after_tool import _is_write_command  # type: ignore[import]

        assert _is_write_command("mv foo bar") is True
        assert _is_write_command("cp src dst") is True
        assert _is_write_command("rm -f file") is True
        assert _is_write_command("touch file") is True
        assert _is_write_command("echo hello > out.txt") is True
        assert _is_write_command("cat file >> other") is True
        assert _is_write_command("ls -la") is False
        assert _is_write_command("grep foo bar") is False
        assert _is_write_command("") is False


if __name__ == "__main__":
    unittest.main()
