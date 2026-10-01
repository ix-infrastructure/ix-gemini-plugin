#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""The hooks speak Gemini CLI's hook protocol, as the CLI's source defines it.

Pinned to google-gemini/gemini-cli @ c9096a847193c16e282d7bd20a70fddc57646bbe:

- packages/core/src/hooks/types.ts: DefaultHookOutput.getAdditionalContext()
  reads only `hookSpecificOutput.additionalContext`. A top-level
  `additionalContext` is never read.
- packages/cli/src/ui/AppContainer.tsx (SessionStart), core/client.ts
  (BeforeAgent) and core/coreToolHookTriggers.ts (AfterTool) are the only
  places that hand that context to the model.
- packages/core/src/scheduler/hook-utils.ts: a BeforeTool output reaches the
  model only by blocking the tool; `systemMessage` goes to the UI
  (hookEventHandler.ts emitHookSystemMessage), never to the model.
- packages/core/src/hooks/hookPlanner.ts: a tool matcher is an unanchored
  `new RegExp(matcher).test(toolName)`.
- packages/core/src/hooks/hookRunner.ts: a hook past its `timeout` (ms) is
  killed and its output dropped; the tool still runs.
- packages/core/src/tools/definitions/base-declarations.ts: the native write
  tools are `write_file` and `replace`, both taking `file_path`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
HOOKS_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

import fake_ix  # noqa: E402

# packages/core/src/hooks/types.ts, enum HookEventName.
GEMINI_EVENTS = {
    "BeforeTool", "AfterTool", "BeforeAgent", "Notification", "AfterAgent",
    "SessionStart", "SessionEnd", "PreCompress", "BeforeModel", "AfterModel",
    "BeforeToolSelection",
}
# base-declarations.ts: SHELL_TOOL_NAME, WRITE_FILE_TOOL_NAME, EDIT_TOOL_NAME.
SHELL_TOOL = "run_shell_command"
WRITE_TOOLS = ("write_file", "replace")
# Python start-up plus imports, on top of the hook's own ix budget.
STARTUP_MARGIN_MS = 1500


def model_context(output: dict) -> str | None:
    """What Gemini hands the model from a hook's JSON output.

    Mirrors DefaultHookOutput.getAdditionalContext(): only a string at
    hookSpecificOutput.additionalContext counts.
    """
    specific = output.get("hookSpecificOutput")
    if not isinstance(specific, dict):
        return None
    context = specific.get("additionalContext")
    return context if isinstance(context, str) else None


def _hooks_config() -> dict:
    return json.loads((HOOKS_DIR / "hooks.json").read_text())["hooks"]


def _load_common():
    spec = importlib.util.spec_from_file_location("ix_common_protocol", HOOKS_DIR / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_init(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path.resolve()


class ModelContextShapeTest(unittest.TestCase):
    """The shapes the hooks used to print carried nothing to the model."""

    def test_old_top_level_additional_context_reaches_nothing(self) -> None:
        self.assertIsNone(model_context({"additionalContext": "Ix Memory is available"}))

    def test_old_before_tool_system_message_reaches_nothing(self) -> None:
        self.assertIsNone(model_context({"decision": "allow", "systemMessage": "[ix] hits"}))

    def test_hook_specific_output_reaches_the_model(self) -> None:
        output = {"hookSpecificOutput": {"hookEventName": "AfterTool", "additionalContext": "x"}}
        self.assertEqual("x", model_context(output))


class HooksConfigTest(unittest.TestCase):
    def test_event_names_are_gemini_events(self) -> None:
        self.assertLessEqual(set(_hooks_config()), GEMINI_EVENTS)

    def test_no_before_tool_hook(self) -> None:
        # Nothing a non-blocking BeforeTool hook prints reaches the model, so
        # the Ix context moved to AfterTool.
        self.assertNotIn("BeforeTool", _hooks_config())

    def test_after_tool_matcher_covers_shell_and_native_writes(self) -> None:
        (definition,) = _hooks_config()["AfterTool"]
        matcher = re.compile(definition["matcher"])
        for tool in (SHELL_TOOL, *WRITE_TOOLS):
            self.assertTrue(matcher.search(tool), tool)
        # Unanchored RegExp.test: `replace` alone would also match these.
        for tool in ("read_file", "grep_search", "mcp_ix-memory_ix_replace", "replace_all"):
            self.assertFalse(matcher.search(tool), tool)

    def test_timeouts_cover_each_hook_budget(self) -> None:
        common = _load_common()
        config = _hooks_config()
        self.assertEqual(set(config), set(common.HOOK_BUDGET_SECONDS))
        for event, definitions in config.items():
            budget_ms = common.HOOK_BUDGET_SECONDS[event] * 1000
            for definition in definitions:
                for hook in definition["hooks"]:
                    self.assertGreaterEqual(
                        hook["timeout"], budget_ms + STARTUP_MARGIN_MS, f"{event}: {hook}"
                    )


class _HookRun(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        self.repo = _git_init(self.tmp / "repo")

    def run_hook(self, script: str, event: dict) -> subprocess.CompletedProcess[str]:
        base = {
            "session_id": "s-1",
            "transcript_path": "",
            "cwd": str(self.repo),
            "timestamp": "2026-10-01T00:00:00Z",
        }
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=json.dumps({**base, **event}),
            env=self.env, capture_output=True, text=True, timeout=30,
        )

    def json_output(self, result: subprocess.CompletedProcess[str], event: str) -> dict:
        self.assertEqual(0, result.returncode, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(event, output["hookSpecificOutput"]["hookEventName"])
        self.assertNotIn("additionalContext", output, "top-level additionalContext is ignored")
        self.assertNotIn("systemMessage", output, "systemMessage only reaches the user")
        return output

    def calls(self, command: str) -> list[dict]:
        entries = fake_ix.read_log(Path(self.env["FAKE_IX_LOG"]))
        return [e for e in entries if e["argv"][:1] == [command]]

    def wait_for_map(self, timeout: float = 10.0) -> list[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            maps = self.calls("map")
            if maps:
                return maps
            time.sleep(0.05)
        return []


class ContextHooksTest(_HookRun):
    def test_session_start_context_reaches_the_model(self) -> None:
        result = self.run_hook("session_start.py", {"hook_event_name": "SessionStart", "source": "startup"})
        context = model_context(self.json_output(result, "SessionStart"))
        self.assertIsNotNone(context)
        self.assertIn("Ix Memory is available", context)

    def test_before_agent_briefing_reaches_the_model(self) -> None:
        result = self.run_hook("before_agent.py", {"hook_event_name": "BeforeAgent", "prompt": "hi"})
        context = model_context(self.json_output(result, "BeforeAgent"))
        self.assertIsNotNone(context)
        self.assertIn("[ix] Session briefing", context)

    def test_shell_grep_context_reaches_the_model_after_the_tool(self) -> None:
        event = {
            "hook_event_name": "AfterTool",
            "tool_name": SHELL_TOOL,
            "tool_input": {"command": "grep -rn verify_token src"},
            "tool_response": {"llmContent": "src/x.py:1:verify_token"},
        }
        context = model_context(self.json_output(self.run_hook("after_tool.py", event), "AfterTool"))
        self.assertIsNotNone(context)
        self.assertIn("symbol: verify_token", context)
        self.assertEqual([], self.calls("map"))

    def test_shell_read_context_reaches_the_model_after_the_tool(self) -> None:
        event = {
            "hook_event_name": "AfterTool",
            "tool_name": SHELL_TOOL,
            "tool_input": {"command": "cat src/auth.py"},
            "tool_response": {"llmContent": "..."},
        }
        context = model_context(self.json_output(self.run_hook("after_tool.py", event), "AfterTool"))
        self.assertIsNotNone(context)
        self.assertIn("[ix] auth.py", context)


class NativeWriteToolsTest(_HookRun):
    def setUp(self) -> None:
        super().setUp()
        self.env["FAKE_IX_GRAPH_COMPLETED"] = "1"
        (self.repo / "src").mkdir()

    def _edit(self, tool: str, file_path: str, **extra) -> subprocess.CompletedProcess[str]:
        event = {
            "hook_event_name": "AfterTool",
            "tool_name": tool,
            "tool_input": {"file_path": file_path, "content": "x = 1\n"},
            "tool_response": {"llmContent": "ok"},
            **extra,
        }
        return self.run_hook("after_tool.py", event)

    def test_write_file_requests_guarded_map(self) -> None:
        result = self._edit("write_file", str(self.repo / "src" / "new.py"))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        maps = self.wait_for_map()
        self.assertEqual(["map", str(self.repo), "--silent"], maps[0]["argv"])

    def test_replace_requests_guarded_map(self) -> None:
        self.assertEqual(0, self._edit("replace", str(self.repo / "src" / "x.py")).returncode)
        self.assertEqual(["map", str(self.repo), "--silent"], self.wait_for_map()[0]["argv"])

    def test_relative_file_path_resolves_against_cwd(self) -> None:
        self.assertEqual(0, self._edit("replace", "src/x.py").returncode)
        self.assertEqual(["map", str(self.repo), "--silent"], self.wait_for_map()[0]["argv"])

    def test_failed_edit_does_not_map(self) -> None:
        result = self._edit(
            "replace", str(self.repo / "src" / "x.py"),
            tool_response={"llmContent": "", "error": {"message": "old_string not found"}},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], self.wait_for_map(timeout=0.5))


class BudgetTest(unittest.TestCase):
    """A slow backend costs at most the hook's budget, never Gemini's timeout."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        env = fake_ix.isolated_env(self.tmp)
        env["FAKE_IX_SLEEP"] = "20"
        patcher = patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.common = _load_common()

    def test_search_message_stops_at_the_deadline(self) -> None:
        start = time.monotonic()
        message = self.common.build_search_message(
            "verify_token", self.tmp, deadline=self.common.Deadline(1.0)
        )
        self.assertIsNone(message)
        self.assertLess(time.monotonic() - start, 3.0)

    def test_health_check_stops_at_the_deadline(self) -> None:
        start = time.monotonic()
        self.assertFalse(self.common.ix_healthy(self.tmp, deadline=self.common.Deadline(1.0)))
        self.assertLess(time.monotonic() - start, 3.0)

    def test_spent_deadline_runs_nothing(self) -> None:
        self.assertIsNone(self.common.Deadline(0).timeout(10))
        self.assertEqual({}, {
            k: v for k, v in self.common.run_parallel_json(
                [("text", ["ix", "text", "x"], 10)], self.tmp, deadline=self.common.Deadline(0)
            ).items() if v is not None
        })
        self.assertEqual([], fake_ix.read_log(Path(os.environ["FAKE_IX_LOG"])))


if __name__ == "__main__":
    unittest.main()
