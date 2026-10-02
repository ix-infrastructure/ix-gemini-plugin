#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""Smoke tests for Gemini hook scripts — verifiable without a live Gemini session."""
from __future__ import annotations

import atexit
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).parent.parent.resolve()
PYTHON = sys.executable
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import fake_ix  # noqa: E402

# Every hook runs with the strict fake ix first on PATH and a private HOME and
# state dir. Before this, these tests ran the hooks against whatever `ix` was
# installed, so the write-command and session_end cases could start a real
# `ix map` against the shared backend.
_TMP = Path(tempfile.mkdtemp(prefix="ix-gemini-hook-tests-"))
atexit.register(shutil.rmtree, _TMP, True)
HOOK_ENV = fake_ix.isolated_env(_TMP)


def _run_hook(script: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PYTHON, str(HOOKS_DIR / script)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=15,
        env=HOOK_ENV,
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


# ── every registered hook ─────────────────────────────────────────────────────

class RegisteredHooksTest(unittest.TestCase):
    """Each script hooks.json registers exits 0 and prints nothing or one JSON object.

    Gemini parses a hook's whole stdout as JSON and treats any other text as a
    plain-text systemMessage (hookRunner.ts).
    """

    def _scripts(self) -> list[str]:
        config = json.loads((HOOKS_DIR / "hooks.json").read_text())["hooks"]
        scripts = []
        for definitions in config.values():
            for definition in definitions:
                for hook in definition["hooks"]:
                    scripts.append(hook["command"].rsplit("/", 1)[-1])
        return scripts

    def test_registered_scripts_exist(self) -> None:
        for script in self._scripts():
            assert (HOOKS_DIR / script).is_file(), script

    def test_bad_stdin_exits_zero_with_json_or_nothing(self) -> None:
        for script in self._scripts():
            for stdin in ("", "not json {{{", "[]"):
                result = _run_hook(script, stdin=stdin)
                assert result.returncode == 0, f"{script} {stdin!r}: {result.stderr}"
                if result.stdout.strip():
                    assert isinstance(json.loads(result.stdout), dict), (script, result.stdout)


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

    def test_fd_redirects_are_not_writes(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        from after_tool import _is_write_command  # type: ignore[import]

        # Any `>` used to count, so every `2>/dev/null` started a map.
        assert _is_write_command("ls src 2>/dev/null") is False
        assert _is_write_command("npm test > /dev/null 2>&1") is False
        assert _is_write_command("grep -r foo . 2>&1") is False
        assert _is_write_command("cmd | tee /dev/stderr") is False
        assert _is_write_command("sed -n 1,20p file.py") is False
        assert _is_write_command("git status && git diff") is False

    def test_in_place_and_compound_writes(self) -> None:
        sys.path.insert(0, str(HOOKS_DIR))
        from after_tool import _is_write_command  # type: ignore[import]

        assert _is_write_command("sed -i 's/a/b/' file.py") is True
        assert _is_write_command("sed -i.bak -e 's/a/b/' file.py") is True
        assert _is_write_command("perl -pi -e 's/a/b/' file.py") is True
        assert _is_write_command("make 2>&1 | tee build.log") is True
        assert _is_write_command("cd src && rm old.py") is True
        assert _is_write_command("cd src\nmv a.py b.py") is True
        assert _is_write_command("echo x >| out.txt") is True
        assert _is_write_command("git checkout -- file.py") is True
        assert _is_write_command("sudo -u me cp a b") is True


if __name__ == "__main__":
    unittest.main()
