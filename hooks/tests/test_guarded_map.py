#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""The guarded automatic map, and the strict fake ix the hook tests run against.

An automatic map runs only for a git repository whose root is not $HOME, only
when Ix already reports that root as mapped (it must never create a
workspace), at most once per root per debounce window, and always as exactly
`ix map <root> --silent` with IX_AUTO_MAP=1 and cwd = root.
"""
from __future__ import annotations

import importlib.util
import json
import os
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


def _git_init(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path.resolve()


class _FakeIxCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        self.log_path = Path(self.env["FAKE_IX_LOG"])

    def calls(self, command: str | None = None) -> list[dict]:
        entries = fake_ix.read_log(self.log_path)
        if command is None:
            return entries
        return [e for e in entries if e["argv"][:1] == [command]]


class GuardedMapTest(_FakeIxCase):
    """request_guarded_map(), in process, against the fake ix on PATH."""

    def setUp(self) -> None:
        super().setUp()
        patcher = patch.dict(os.environ, self.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("ix_common_guard", HOOKS_DIR / "common.py")
        assert spec is not None and spec.loader is not None
        self.common = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.common)
        self.repo = _git_init(self.tmp / "repo")

    def _request(self, project_dir) -> subprocess.Popen | None:
        child = self.common.request_guarded_map(project_dir)
        if child is not None:
            child.wait(timeout=15)
        return child

    def test_non_git_dir_never_maps(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self.assertIsNone(self._request(plain))
        self.assertEqual([], self.calls("map"))

    def test_no_project_dir_never_maps(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self.assertIsNone(self._request(None))
        self.assertEqual([], self.calls())

    def test_root_equal_to_home_never_maps(self) -> None:
        home_repo = _git_init(Path(os.environ["HOME"]))
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self.assertIsNone(self._request(home_repo))
        self.assertEqual([], self.calls("map"))

    def test_unmapped_project_never_maps(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "0"
        self.assertIsNone(self._request(self.repo))
        self.assertEqual([], self.calls("map"))
        status = self.calls("status")
        self.assertEqual(1, len(status))
        self.assertEqual(["status", "--format", "json", "--root", str(self.repo)], status[0]["argv"])

    def test_status_failure_or_non_json_never_maps(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        for mode in ("fail", "garbage"):
            os.environ["FAKE_IX_STATUS"] = mode
            self.assertIsNone(self._request(self.repo), mode)
        self.assertEqual([], self.calls("map"))

    def test_mapped_project_maps_root_exactly(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        sub = self.repo / "src" / "pkg"
        sub.mkdir(parents=True)
        child = self._request(sub)
        self.assertIsNotNone(child)
        self.assertEqual(0, child.returncode)
        maps = self.calls("map")
        self.assertEqual(1, len(maps))
        self.assertEqual(["map", str(self.repo), "--silent"], maps[0]["argv"])
        self.assertEqual(str(self.repo), maps[0]["cwd"])
        self.assertEqual("1", maps[0]["IX_AUTO_MAP"])

    def test_second_request_inside_debounce_does_not_map(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self.assertIsNotNone(self._request(self.repo))
        self.assertIsNone(self._request(self.repo))
        self.assertEqual(1, len(self.calls("map")))

    def test_request_after_debounce_window_maps_again(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self.assertIsNotNone(self._request(self.repo))
        stamp = self.common._map_stamp_path(self.repo)
        old = time.time() - self.common.MAP_DEBOUNCE_SECONDS - 5
        os.utime(stamp, (old, old))
        self.assertIsNotNone(self._request(self.repo))
        self.assertEqual(2, len(self.calls("map")))

    def test_different_roots_do_not_debounce_each_other(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        other = _git_init(self.tmp / "other")
        self.assertIsNotNone(self._request(self.repo))
        self.assertIsNotNone(self._request(other))
        mapped = [entry["argv"][1] for entry in self.calls("map")]
        self.assertEqual([str(self.repo), str(other)], mapped)

    def test_debounce_state_is_private_and_per_user(self) -> None:
        os.environ["FAKE_IX_GRAPH_COMPLETED"] = "1"
        self._request(self.repo)
        stamp = self.common._map_stamp_path(self.repo)
        self.assertTrue(stamp.exists())
        state_root = Path(os.environ["XDG_STATE_HOME"])
        self.assertTrue(str(stamp).startswith(str(state_root)), stamp)
        self.assertEqual(0o700, stamp.parent.stat().st_mode & 0o777)

    def test_health_and_briefing_caches_are_keyed_by_root(self) -> None:
        other = _git_init(self.tmp / "other")
        self.assertTrue(self.common.ix_healthy(self.repo))
        self.assertTrue(self.common.ix_healthy(other))
        self.assertNotEqual(
            self.common._status_cache_path(self.repo), self.common._status_cache_path(other)
        )
        self.assertEqual(2, len(self.calls("status")))
        self.common.mark_briefing_sent(self.repo)
        self.assertFalse(self.common.briefing_due(self.repo))
        self.assertTrue(self.common.briefing_due(other))

    def test_home_gemini_settings_does_not_make_home_the_workspace(self) -> None:
        home = Path(os.environ["HOME"])
        (home / ".gemini").mkdir()
        (home / ".gemini" / "settings.json").write_text("{}")
        project = _git_init(home / "code" / "proj")
        self.assertEqual(project, self.common.find_workspace_root(str(project / "src")))

    def test_search_message_uses_valid_locate_argv(self) -> None:
        message = self.common.build_search_message("verify_token", self.repo)
        self.assertIsNotNone(message)
        self.assertIn("symbol: verify_token", message)
        locate = self.calls("locate")
        self.assertEqual(1, len(locate))
        self.assertNotIn("--limit", locate[0]["argv"])


class FakeIxStrictnessTest(_FakeIxCase):
    """The fake rejects what the real CLI rejects."""

    def _ix(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["ix", *args], env=self.env, cwd=cwd, capture_output=True, text=True, timeout=15
        )

    def test_map_rejects_a_file(self) -> None:
        target = self.tmp / "file.py"
        target.write_text("x = 1\n")
        result = self._ix("map", str(target), "--silent")
        self.assertEqual(1, result.returncode)
        self.assertIn("Map path is not a directory", result.stderr)

    def test_map_accepts_a_directory(self) -> None:
        self.assertEqual(0, self._ix("map", str(self.tmp), "--silent").returncode)

    def test_locate_rejects_limit(self) -> None:
        result = self._ix("locate", "foo", "--limit", "5")
        self.assertEqual(1, result.returncode)
        self.assertIn("unknown option '--limit'", result.stderr)

    def test_smells_rejects_path(self) -> None:
        result = self._ix("smells", "--path", "src")
        self.assertEqual(1, result.returncode)
        self.assertIn("unknown option '--path'", result.stderr)


class HookEndToEndTest(_FakeIxCase):
    """The real hook scripts, as Gemini runs them, against the fake ix."""

    def setUp(self) -> None:
        super().setUp()
        self.repo = _git_init(self.tmp / "repo")
        self.env["FAKE_IX_GRAPH_COMPLETED"] = "1"

    def _run(self, script: str, event: dict) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=json.dumps(event), env=self.env, capture_output=True, text=True, timeout=15,
        )

    def _wait_for_map(self, timeout: float = 10.0) -> list[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            maps = self.calls("map")
            if maps:
                return maps
            time.sleep(0.05)
        return []

    def test_after_tool_write_requests_guarded_map(self) -> None:
        event = {"cwd": str(self.repo), "tool_input": {"command": "sed -i s/a/b/ src/x.py"}}
        result = self._run("after_tool.py", event)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)
        maps = self._wait_for_map()
        self.assertEqual(["map", str(self.repo), "--silent"], maps[0]["argv"])
        self.assertEqual("1", maps[0]["IX_AUTO_MAP"])

    def test_after_tool_stderr_redirect_is_not_a_write(self) -> None:
        event = {"cwd": str(self.repo), "tool_input": {"command": "ls src 2>/dev/null"}}
        self.assertEqual(0, self._run("after_tool.py", event).returncode)
        # Not a write: no status probe, no map, nothing.
        self.assertEqual([], self.calls())

    def test_session_end_requests_guarded_map(self) -> None:
        result = self._run("session_end.py", {"cwd": str(self.repo)})
        self.assertEqual(0, result.returncode, result.stderr)
        maps = self._wait_for_map()
        self.assertEqual(["map", str(self.repo), "--silent"], maps[0]["argv"])

    def test_session_end_without_cwd_does_not_map(self) -> None:
        self.assertEqual(0, self._run("session_end.py", {}).returncode)
        self.assertEqual([], self.calls())


if __name__ == "__main__":
    unittest.main()
