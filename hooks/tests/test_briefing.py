#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""BeforeAgent's Ix Pro briefing: one `ix briefing` per injection, as capped text.

The Pro check runs `ix briefing` itself (only the real command tells Pro from
the OSS stub), so on a probe that succeeds the hook reuses that output rather
than starting the CLI a second time inside the hook that holds up the turn.
Every case runs before_agent.py against the strict fake ix.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
HOOKS_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

import fake_ix  # noqa: E402


def _load_common():
    spec = importlib.util.spec_from_file_location("ix_common_briefing", HOOKS_DIR / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BeforeAgentBriefingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.state = self.tmp / "state" / "ix-gemini-plugin"

    def run_hook(self, **env: str) -> str | None:
        """Run BeforeAgent once; the context it hands the model, or None."""
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "before_agent.py")],
            input=json.dumps({"hook_event_name": "BeforeAgent", "prompt": "hi", "cwd": str(self.repo)}),
            env={**self.env, **env}, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    def briefing_calls(self) -> list[list[str]]:
        log = fake_ix.read_log(Path(self.env["FAKE_IX_LOG"]))
        return [entry["argv"] for entry in log if entry["argv"][:1] == ["briefing"]]

    def forget_last_briefing(self) -> None:
        shutil.rmtree(self.state / "briefing", ignore_errors=True)

    def test_probe_output_is_reused_not_fetched_again(self) -> None:
        context = self.run_hook()
        self.assertIsNotNone(context)
        self.assertEqual(1, len(self.briefing_calls()), self.briefing_calls())

    def test_cached_pro_answer_still_runs_one_briefing(self) -> None:
        self.run_hook()
        self.forget_last_briefing()  # the Pro answer stays cached
        context = self.run_hook()
        self.assertIsNotNone(context)
        self.assertEqual(2, len(self.briefing_calls()), self.briefing_calls())

    def test_briefing_is_requested_and_injected_as_text(self) -> None:
        context = self.run_hook()
        self.assertEqual([["briefing", "--format", "text"]], self.briefing_calls())
        assert context is not None
        self.assertTrue(context.startswith("[ix] Session briefing:\n"), context)
        self.assertIn("Ship the session-token rewrite", context)
        self.assertNotIn('"revision"', context)

    def test_long_briefing_is_capped(self) -> None:
        common = _load_common()
        context = self.run_hook(FAKE_IX_BRIEFING="long")
        assert context is not None
        self.assertLessEqual(len(context), common.BRIEFING_MAX_CHARS + 200)
        self.assertIn("truncated", context)
        self.assertIn("Ship the session-token rewrite", context)

    def test_empty_briefing_injects_nothing_and_waits_for_the_window(self) -> None:
        self.assertIsNone(self.run_hook(FAKE_IX_BRIEFING="empty"))
        # Answered, so the next prompt in the window does not ask again.
        self.assertIsNone(self.run_hook(FAKE_IX_BRIEFING="empty"))
        self.assertEqual(1, len(self.briefing_calls()))

    def test_blank_briefing_injects_nothing(self) -> None:
        self.assertIsNone(self.run_hook(FAKE_IX_BRIEFING="blank"))

    def test_oss_stub_injects_nothing(self) -> None:
        self.assertIsNone(self.run_hook(FAKE_IX_BRIEFING="stub"))
        self.assertIsNone(self.run_hook(FAKE_IX_BRIEFING="stub"))
        # The stub answer is cached, so the second prompt does not probe again.
        self.assertEqual(1, len(self.briefing_calls()))


class BriefingTextTest(unittest.TestCase):
    """format_briefing: what counts as empty, and the cap."""

    def setUp(self) -> None:
        self.common = _load_common()

    def test_all_sections_empty_is_empty(self) -> None:
        for text in (
            "",
            "  \n\n",
            "Ix briefing (revision 7)\n\nGoals\n  (none)\nPlans\n  (none)\nDecisions\n  none\n"
            "Bugs\n  -\nRecent changes\n  (none)\n",
            "## Goals\n_none_\n## Open bugs: 0\n## Plans: none\nNo recent changes.\nNo decisions recorded.\n",
            "Session briefing\nActive plans (0)\nGoals:\nKnown bugs: -\n",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.common.format_briefing(text))

    def test_any_item_is_content(self) -> None:
        for text in (
            "Goals\n  - Ship it\nPlans\n  (none)\n",
            "Goals\n  (none)\nBugs\n  - Fix login bug\n",
            # A lone item that happens to start with "No" is still an item.
            "Decisions\n  - No caching in the auth layer\n",
            # A layout this check does not recognise is injected, not dropped.
            "Something new the CLI prints\n",
            "Goals:\nFix the login bug\n",
            "Plans: migrate sessions\n",
        ):
            with self.subTest(text=text):
                self.assertEqual(text.strip(), self.common.format_briefing(text))

    def test_cap_cuts_at_a_line_and_says_so(self) -> None:
        text = "Goals\n" + "".join(f"  - goal {n}\n" for n in range(2000))
        out = self.common.format_briefing(text)
        assert out is not None
        body, _, note = out.rpartition("\n")
        self.assertLessEqual(len(body), self.common.BRIEFING_MAX_CHARS)
        self.assertTrue(body.endswith(tuple(f"goal {n}" for n in range(2000))), body[-40:])
        self.assertIn("truncated", note)
        self.assertIn("ix briefing", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
