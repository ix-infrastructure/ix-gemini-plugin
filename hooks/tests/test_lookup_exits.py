#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""Graph lookups that exit 2, 3 or 4 (Ix #853) are answers, not failures.

`ix locate` (search hook) and `ix overview`/`ix impact` (read hook) print why
they could not resolve a target on stdout: the candidates (exit 2), the
suggestions (exit 3) or that the workspace is not mapped (exit 4). An older ix
prints the same records on exit 1. A real error, a timeout or non-JSON stdout
must leave the hooks exactly as they were.
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

PATTERN = "verify_token"
# What the search hook says today when `ix locate` adds nothing.
TEXT_ONLY_SEARCH = (
    f"[ix] shell grep intercepted for '{PATTERN}' | 1 text hits in fake.py"
    f" | Prefer: ix text '{PATTERN}' or ix locate '{PATTERN}' over shell grep"
)


def _load_common():
    spec = importlib.util.spec_from_file_location("ix_common_lookup", HOOKS_DIR / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _LookupCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        patcher = patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Loaded after the env patch so CACHE_DIR sits in this test's tmp dir.
        self.common = _load_common()

    def lookup(self, mode: str, legacy: bool = False) -> None:
        os.environ["FAKE_IX_LOOKUP"] = mode
        if legacy:
            os.environ["FAKE_IX_LEGACY_EXIT"] = "1"

    def search(self) -> str | None:
        return self.common.build_search_message(PATTERN, self.tmp)

    def read(self, path: str = "src/auth.py") -> str | None:
        return self.common.build_read_message(path, self.tmp)


class RunIxLookupTest(_LookupCase):
    def outcome(self, argv: list[str]) -> str:
        return self.common.run_ix_lookup(argv, cwd=self.tmp)[0]

    def test_exit_codes_map_to_outcomes(self) -> None:
        c = self.common
        argv = ["ix", "impact", "auth.py", "--format", "json"]
        self.assertEqual(c.LOOKUP_OK, self.outcome(argv))
        for mode, expected in (
            ("ambiguous", c.LOOKUP_AMBIGUOUS),
            ("not_found", c.LOOKUP_NOT_FOUND),
            ("not_mapped", c.LOOKUP_NOT_MAPPED),
            ("error", c.LOOKUP_ERROR),
            ("garbage", c.LOOKUP_ERROR),
        ):
            with self.subTest(mode=mode):
                self.lookup(mode)
                self.assertEqual(expected, self.outcome(argv))

    def test_old_ix_exit_1_is_read_by_its_slug(self) -> None:
        c = self.common
        for mode, expected in (
            ("ambiguous", c.LOOKUP_AMBIGUOUS),
            ("not_found", c.LOOKUP_NOT_FOUND),
            ("not_mapped", c.LOOKUP_NOT_MAPPED),
            ("error", c.LOOKUP_ERROR),
            ("garbage", c.LOOKUP_ERROR),
        ):
            with self.subTest(mode=mode):
                self.lookup(mode, legacy=True)
                # `locate` names its ambiguity under `code`, not `error`.
                self.assertEqual(expected, self.outcome(["ix", "locate", PATTERN, "--format", "json"]))

    def test_run_ix_json_still_drops_every_non_zero_exit(self) -> None:
        """status, briefing, the Pro probe and workspace_mapped rely on this."""
        for mode in ("ambiguous", "not_found", "not_mapped"):
            with self.subTest(mode=mode):
                self.lookup(mode)
                self.assertIsNone(self.common.run_ix_json(
                    ["ix", "impact", "auth.py", "--format", "json"], cwd=self.tmp))


class SearchMessageTest(_LookupCase):
    def test_ambiguous_lists_candidates_with_pick_numbers(self) -> None:
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.lookup("ambiguous", legacy)
                message = self.search()
                self.assertIsNotNone(message)
                self.assertIn(f"[1] {PATTERN} (function, src/{PATTERN}:12)", message)
                self.assertIn(f"[2] {PATTERN} (method, lib/{PATTERN}:40)", message)
                self.assertIn(f"ix locate '{PATTERN}' --pick <n>", message)
                self.assertIn("--path", message)
                self.assertIn("1 text hits in fake.py", message)

    def test_not_found_shows_suggestions(self) -> None:
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.lookup("not_found", legacy)
                message = self.search()
                self.assertIsNotNone(message)
                self.assertIn(f"no symbol '{PATTERN}'", message)
                self.assertIn(f"{PATTERN}_v2 (function, src/fake.py:3)", message)
                self.assertIn(f"{PATTERN}s", message)

    def test_not_found_without_suggestions_adds_nothing(self) -> None:
        self.lookup("not_found")
        os.environ["FAKE_IX_SUGGESTIONS"] = "0"
        self.assertEqual(TEXT_ONLY_SEARCH, self.search())

    def test_not_mapped_line_once_per_workspace_window(self) -> None:
        self.lookup("not_mapped")
        first = self.search()
        self.assertIsNotNone(first)
        self.assertIn(self.common.NOT_MAPPED_LINE, first)
        self.assertNotIn("error", first.lower())
        # Shown once per workspace per window, shared with the read hook.
        self.assertEqual(TEXT_ONLY_SEARCH, self.search())
        self.assertIsNone(self.read())

    def test_old_ix_not_mapped_on_exit_1(self) -> None:
        self.lookup("not_mapped", legacy=True)
        self.assertIn(self.common.NOT_MAPPED_LINE, self.search() or "")

    def test_real_error_and_bad_json_behave_as_today(self) -> None:
        for mode in ("error", "garbage"):
            for legacy in (False, True):
                with self.subTest(mode=mode, legacy=legacy):
                    self.lookup(mode, legacy)
                    self.assertEqual(TEXT_ONLY_SEARCH, self.search())

    def test_timeout_behaves_as_today(self) -> None:
        self.lookup("ambiguous")
        os.environ["FAKE_IX_SLEEP"] = "20"
        self.assertIsNone(self.common.build_search_message(
            PATTERN, self.tmp, deadline=self.common.Deadline(1.0)))


class ReadMessageTest(_LookupCase):
    def test_exit_0_unchanged(self) -> None:
        self.assertEqual(
            "[ix] auth.py | key: auth (1 function) | Use ix read <symbol> to get just a symbol's source",
            self.read(),
        )

    def test_ambiguous_names_the_read_files_candidate(self) -> None:
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.lookup("ambiguous", legacy)
                message = self.read("src/auth.py")
                self.assertIsNotNone(message)
                self.assertIn("[1] auth.py (function, src/auth.py:12)", message)
                self.assertIn("--pick 1", message)
                self.assertIn("--path src/auth.py", message)
                self.assertNotIn("lib/auth.py", message)

    def test_ambiguous_absolute_read_path_matches_its_candidate(self) -> None:
        self.lookup("ambiguous")
        message = self.read(str(self.tmp / "lib" / "auth.py"))
        self.assertIn("[2] auth.py (method, lib/auth.py:40)", message or "")
        self.assertIn("--pick 2", message or "")
        self.assertIn("--path lib/auth.py", message or "")

    def test_ambiguous_without_a_matching_candidate_gives_only_path_hint(self) -> None:
        self.lookup("ambiguous")
        message = self.read("other/auth.py")
        self.assertIsNotNone(message)
        self.assertIn("--path other/auth.py", message)
        self.assertNotIn("--pick", message)
        self.assertNotIn("src/auth.py", message)

    def test_not_found_stays_silent(self) -> None:
        """Reading a file the graph does not index is normal: no line for it."""
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.lookup("not_found", legacy)
                self.assertIsNone(self.read())

    def test_not_mapped_line_once_per_workspace_window(self) -> None:
        self.lookup("not_mapped")
        message = self.read()
        self.assertEqual(f"[ix] auth.py | {self.common.NOT_MAPPED_LINE}", message)
        self.assertIsNone(self.read())

    def test_old_ix_not_mapped_on_exit_1(self) -> None:
        self.lookup("not_mapped", legacy=True)
        self.assertEqual(f"[ix] auth.py | {self.common.NOT_MAPPED_LINE}", self.read())

    def test_real_error_and_bad_json_behave_as_today(self) -> None:
        for mode in ("error", "garbage"):
            for legacy in (False, True):
                with self.subTest(mode=mode, legacy=legacy):
                    self.lookup(mode, legacy)
                    self.assertIsNone(self.read())

    def test_timeout_behaves_as_today(self) -> None:
        self.lookup("ambiguous")
        os.environ["FAKE_IX_SLEEP"] = "20"
        self.assertIsNone(self.common.build_read_message(
            "src/auth.py", self.tmp, deadline=self.common.Deadline(1.0)))


class SummarizerTest(_LookupCase):
    def test_explicit_pick_numbers_win_and_the_list_is_capped(self) -> None:
        payload = {
            "error": "ambiguous_target",
            "candidates": [
                {"name": f"f{i}", "kind": "function", "path": f"src/f{i}.py", "pick": i + 10}
                for i in range(8)
            ],
        }
        line = self.common.summarize_ambiguous(payload, "ix locate 'f'")
        self.assertIn("[10] f0 (function, src/f0.py)", line)
        self.assertIn("(+3 more)", line)
        self.assertNotIn("f5", line)

    def test_unusable_payloads_say_nothing(self) -> None:
        for payload in (None, [], {"candidates": "x"}, {"candidates": [1, None]}):
            with self.subTest(payload=payload):
                self.assertEqual("", self.common.summarize_ambiguous(payload, "ix locate 'f'"))
                self.assertEqual("", self.common.summarize_unresolved(payload, "f"))


class AfterToolHookTest(_LookupCase):
    def test_candidates_reach_the_model_after_a_grep(self) -> None:
        self.lookup("ambiguous")
        event = {
            "hook_event_name": "AfterTool",
            "cwd": str(self.tmp),
            "tool_name": "run_shell_command",
            "tool_input": {"command": f"grep -rn {PATTERN} src"},
            "tool_response": {"llmContent": "..."},
        }
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "after_tool.py")],
            input=json.dumps(event), env=dict(os.environ),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("--pick <n>", context)
        self.assertNotIn("failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
