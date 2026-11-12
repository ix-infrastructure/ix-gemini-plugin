#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""What the AfterTool search and read hints cost, and how to turn them off.

A shell grep or read used to start two or three ix processes (`ix text` plus
`ix locate`; `ix inventory`, `ix overview` and `ix impact`), mostly to restate
the command's own output. Now:

- a grep gets a hint only when its pattern is a plain identifier, and the hint
  is one `ix locate`; a phrase or a regular expression starts no ix process;
- a read is one `ix overview`;
- neither runs `ix status` first: a fresh cached health answer is honoured,
  and a lookup that times out pauses the hints (only the hints) for the cache
  window;
- a pattern that looks like a token is never sent to ix nor echoed;
- IX_HOOK_SEARCH_HINT / IX_HOOK_READ_HINT = 0|off|false|no turn each hint off.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fake_ix  # noqa: E402

# Shaped like the credentials the scanners know; none of them is real.
TOKEN_LIKE = (
    "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "github_pat_" + "11ABCDEFG0123456789_abcdefghijklmnop",
    "AKIA" + "IOSFODNN7EXAMPLE",
    "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc",
    "xoxb" + "_1234567890_abcdefghijABCDEFGHIJ",
    "a3f9c2e1" + "7b4d6f8a0c2e4f6a8b0d2e4f",
    "Zq7Lp2Xv9Rt4" + "Wm8Ks1Ny6Bj3",
)


def _load_common():
    spec = importlib.util.spec_from_file_location("ix_common_hints", HOOKS_DIR / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _HintCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        self.log_path = Path(self.env["FAKE_IX_LOG"])
        patcher = patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.common = _load_common()

    def hook(self, command: str, **env: str) -> subprocess.CompletedProcess[str]:
        event = {
            "hook_event_name": "AfterTool",
            "cwd": str(self.tmp),
            "tool_name": "run_shell_command",
            "tool_input": {"command": command},
            "tool_response": {"llmContent": "..."},
        }
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / "after_tool.py")],
            input=json.dumps(event), env={**os.environ, **env},
            capture_output=True, text=True, timeout=30,
        )

    def ix_calls(self) -> list[list[str]]:
        return [entry["argv"] for entry in fake_ix.read_log(self.log_path)]

    def context(self, result: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


class SearchHintTest(_HintCase):
    def test_phrase_and_regex_start_no_ix_process(self) -> None:
        for command in (
            "grep -rn 'token expired' src",
            "rg 'verify_.*token' src",
            "grep -rnE '^def (verify|check)_' .",
            "rg -n 'foo|bar' .",
            "grep -rn hooks/common.py .",
            "grep -rn x .",
        ):
            with self.subTest(command=command):
                result = self.hook(command)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)
                self.assertEqual([], self.ix_calls())

    def test_identifier_is_one_locate_and_no_text_echo(self) -> None:
        context = self.context(self.hook("grep -rn verify_token src"))
        self.assertEqual([["locate", "verify_token", "--format", "json"]], self.ix_calls())
        self.assertIn("symbol: verify_token (function, fake.py)", context)
        self.assertIn("ix callers verify_token", context)
        self.assertNotIn("text hits", context)
        self.assertNotIn("ix text", context)

    def test_token_like_pattern_is_neither_sent_nor_echoed(self) -> None:
        for token in TOKEN_LIKE:
            with self.subTest(token=token[:6]):
                self.assertTrue(self.common.looks_like_secret(token))
                result = self.hook(f"grep -rn {token} .")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stdout)
                self.assertNotIn(token, result.stderr)
                self.assertEqual([], self.ix_calls())
                self.assertIsNone(self.common.build_search_message(token, self.tmp))
                self.assertEqual([], self.ix_calls())

    def test_ordinary_identifiers_are_not_taken_for_tokens(self) -> None:
        for name in (
            "verify_token", "HOOK_BUDGET_SECONDS", "getUserAccountByEmailAddress",
            "test_windows_launch_uses_node", "AKIAvalidator", "sk_live_mode",
            "build_search_message", "Utf8Decoder", "parseHttp2Frame",
        ):
            with self.subTest(name=name):
                self.assertTrue(self.common.looks_like_identifier(name))
                self.assertFalse(self.common.looks_like_secret(name))

    def test_switch_turns_the_search_hint_off(self) -> None:
        for value in ("0", "off", "false", "no", "OFF"):
            with self.subTest(value=value):
                result = self.hook("grep -rn verify_token src", IX_HOOK_SEARCH_HINT=value)
                self.assertEqual("", result.stdout)
                self.assertEqual([], self.ix_calls())
        # Any other value leaves it on.
        self.context(self.hook("grep -rn verify_token src", IX_HOOK_SEARCH_HINT="1"))
        # The read hint has its own switch.
        self.context(self.hook("cat src/auth.py", IX_HOOK_SEARCH_HINT="0"))


class ReadHintTest(_HintCase):
    def test_read_is_one_overview(self) -> None:
        context = self.context(self.hook("cat src/auth.py"))
        self.assertEqual([["overview", "auth.py", "--format", "json"]], self.ix_calls())
        self.assertIn("key: auth", context)

    def test_switch_turns_the_read_hint_off(self) -> None:
        result = self.hook("cat src/auth.py", IX_HOOK_READ_HINT="off")
        self.assertEqual("", result.stdout)
        self.assertEqual([], self.ix_calls())
        self.context(self.hook("grep -rn verify_token src", IX_HOOK_READ_HINT="off"))


class HealthGateTest(_HintCase):
    def test_cached_unhealthy_starts_nothing(self) -> None:
        os.environ["FAKE_IX_STATUS"] = "fail"
        self.assertFalse(self.common.ix_healthy(self.tmp))
        self.log_path.unlink()
        for command in ("grep -rn verify_token src", "cat src/auth.py"):
            with self.subTest(command=command):
                self.assertEqual("", self.hook(command).stdout)
                self.assertEqual([], self.ix_calls())

    def test_cached_healthy_starts_only_the_lookup(self) -> None:
        self.assertTrue(self.common.ix_healthy(self.tmp))
        self.log_path.unlink()
        self.context(self.hook("cat src/auth.py"))
        self.assertEqual([["overview", "auth.py", "--format", "json"]], self.ix_calls())

    def test_a_lookup_timeout_pauses_the_hints(self) -> None:
        os.environ["FAKE_IX_SLEEP"] = "20"
        self.assertIsNone(self.common.build_search_message(
            "verify_token", self.tmp, deadline=self.common.Deadline(1.0)))
        self.assertTrue(self.common.ix_known_unhealthy(self.tmp))
        self.assertEqual(1, len(self.ix_calls()))
        # The next hinted command starts nothing for the cache window.
        del os.environ["FAKE_IX_SLEEP"]
        self.assertEqual("", self.hook("cat src/auth.py").stdout)
        self.assertEqual(1, len(self.ix_calls()))

    def test_a_lookup_timeout_leaves_the_shared_health_answer_alone(self) -> None:
        # SessionStart and BeforeAgent gate on ix_healthy; a slow hint lookup
        # must not turn their guidance and briefing off.
        os.environ["FAKE_IX_SLEEP"] = "20"
        self.common.build_search_message(
            "verify_token", self.tmp, deadline=self.common.Deadline(1.0))
        del os.environ["FAKE_IX_SLEEP"]
        self.assertIsNone(self.common._cached_health(self.tmp))
        self.assertTrue(self.common.ix_healthy(self.tmp))
        self.assertEqual(["status"], self.ix_calls()[-1][:1])

    def test_the_hint_pause_ends_with_the_window(self) -> None:
        os.environ["FAKE_IX_SLEEP"] = "20"
        self.common.build_search_message(
            "verify_token", self.tmp, deadline=self.common.Deadline(1.0))
        del os.environ["FAKE_IX_SLEEP"]
        stamp = self.common._hint_backoff_path(self.tmp)
        old = stamp.stat().st_mtime - self.common.HEALTH_TTL_SECONDS - 1
        os.utime(stamp, (old, old))
        self.assertFalse(self.common.ix_known_unhealthy(self.tmp))
        self.context(self.hook("cat src/auth.py"))

    def test_no_ix_on_path_starts_nothing(self) -> None:
        result = self.hook("grep -rn verify_token src", PATH=str(self.tmp / "empty"))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        self.assertEqual([], self.ix_calls())


if __name__ == "__main__":
    unittest.main()
