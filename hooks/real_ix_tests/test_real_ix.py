#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""The hooks and the MCP entry point against a RELEASED `ix` CLI, no fake.

hooks/tests use a strict fake ix that mirrors the CLI's options by hand, so a
renamed flag or a changed output key in Ix would leave them green while the
plugin broke. This suite runs only in CI's `real-ix` job, which puts a pinned
`ix` release first on PATH (see .github/workflows/ci.yml). Nothing here talks
to a backend: IX_ENDPOINT is forced to http://127.0.0.1:1, so every
graph-backed command fails the way it does for a user whose backend is down.

    IX_EXPECTED_VERSION=0.12.0 python3 -m unittest discover -s hooks/real_ix_tests -v

It fails, rather than skips, when the real CLI is missing: a skipped job reads
as green.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
HOOKS_DIR = TESTS_DIR.parent
REPO_ROOT = HOOKS_DIR.parent
UNREACHABLE = "http://127.0.0.1:1"

# Commander's own usage errors, which is what ix prints for an argv it does not
# accept. Backend failures are "Error: ..." (capital E) or a JSON error record.
USAGE_ERROR_RE = re.compile(
    r"^error: (unknown option|unknown command|too many arguments|"
    r"option .* argument missing|missing required argument)",
    re.MULTILINE,
)

_TMP = tempfile.TemporaryDirectory(prefix="ix-real-")
SANDBOX = Path(_TMP.name)
# Never mapped: graph commands answer with the `workspace_not_mapped` JSON record.
PROJECT = SANDBOX / "project"
# Registered by the plugin's own `ix map` argv in test_02 (the map itself fails
# on the dead backend): graph commands then fail with "backend unreachable".
REGISTERED = SANDBOX / "registered"
sys.path.insert(0, str(HOOKS_DIR))


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "IX_ENDPOINT": UNREACHABLE,
        "IX_HOME": str(SANDBOX / "ix-home"),
        "IX_NO_UPDATE_CHECK": "1",
        "HOME": str(SANDBOX / "home"),
        "XDG_STATE_HOME": str(SANDBOX / "state"),
        "NO_COLOR": "1",
    })
    return env


ENV = _env()


def setUpModule() -> None:  # noqa: N802 - unittest hook
    for name in ("ix-home", "home", "state"):
        (SANDBOX / name).mkdir(parents=True, exist_ok=True)
    for root in (PROJECT, REGISTERED):
        root.mkdir(parents=True, exist_ok=True)
        (root / "widget.py").write_text("def frobnicate_widget():\n    return 1\n")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    # In-process imports of the hooks read these at import time.
    os.environ.update(ENV)


def tearDownModule() -> None:  # noqa: N802 - unittest hook
    _TMP.cleanup()


def run(
    argv: list[str], stdin: str = "", timeout: float = 30, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, input=stdin, capture_output=True, text=True,
        timeout=timeout, cwd=cwd or PROJECT, env=ENV, check=False,
    )


def run_hook(script: str, event: dict) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, str(HOOKS_DIR / script)], json.dumps(event))


def plugin_ix_argvs() -> list[list[str]]:
    """Every `["ix", ...]` list literal in the hooks, with sample values filled in.

    A non-literal element (a pattern, a path) becomes a value of the same role,
    so the argv's shape -- subcommand, flags, flag values -- is exactly what the
    hook sends.
    """
    argvs: list[list[str]] = []
    for path in sorted(HOOKS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.List) or not node.elts:
                continue
            first = node.elts[0]
            if not (isinstance(first, ast.Constant) and first.value == "ix"):
                continue
            argv: list[str] = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    argv.append(elt.value)
                else:
                    # str(root) for status/map, pattern for text/locate,
                    # filename for inventory/overview/impact.
                    argv.append(str(REGISTERED) if argv[1:2] in (["status"], ["map"]) else "widget.py")
            argvs.append(argv)
    return argvs


class RealIxTests(unittest.TestCase):
    def test_01_real_ix_is_on_path_at_the_pinned_version(self) -> None:
        ix = shutil.which("ix", path=ENV.get("PATH"))
        self.assertIsNotNone(ix, "no `ix` on PATH: this suite needs the real CLI")
        self.assertNotIn("fake_ix", Path(ix).read_text(errors="ignore")[:4096])
        result = run(["ix", "--version"])
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = os.environ.get("IX_EXPECTED_VERSION")
        if expected:
            self.assertEqual(result.stdout.strip(), expected)

    def test_02_every_ix_argv_the_plugin_sends_is_accepted(self) -> None:
        """A flag or subcommand this ix release lacks turns this red."""
        argvs = plugin_ix_argvs()
        # The MCP server the extension registers (gemini-extension.json).
        manifest = json.loads((REPO_ROOT / "gemini-extension.json").read_text())
        for server in manifest.get("mcpServers", {}).values():
            if server.get("command") == "ix":
                self.assertTrue(server.get("args"), "ix MCP server has no args")
        subcommands = {argv[1] for argv in argvs}
        # Guard the scan itself: if it stops finding the hooks' calls, it must
        # not pass by checking nothing.
        self.assertTrue(
            {"status", "text", "locate", "inventory", "overview", "impact", "map", "briefing"}
            <= subcommands,
            f"argv scan found only {sorted(subcommands)}",
        )
        for argv in argvs:
            with self.subTest(argv=argv):
                result = run(argv)
                self.assertIsNone(
                    USAGE_ERROR_RE.search(result.stderr),
                    f"ix rejected the plugin's argv {argv}: {result.stderr.strip()}",
                )

    def test_03_mcp_server_starts_and_lists_tools(self) -> None:
        manifest = json.loads((REPO_ROOT / "gemini-extension.json").read_text())
        server = manifest["mcpServers"]["ix-memory"]
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "real-ix-ci", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        result = run(
            [server["command"], *server["args"]],
            "".join(json.dumps(r) + "\n" for r in requests),
        )
        self.assertIsNone(USAGE_ERROR_RE.search(result.stderr), result.stderr)
        replies = {}
        for line in result.stdout.splitlines():
            if line.strip().startswith("{"):
                msg = json.loads(line)
                replies[msg.get("id")] = msg
        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "ix-memory", result.stderr)
        tools = replies[2]["result"]["tools"]
        self.assertTrue(tools and all("name" in t for t in tools))

    def test_04_hooks_stay_silent_and_exit_0_when_the_backend_is_down(self) -> None:
        """No context, no traceback, exit 0 -- Gemini treats anything else as a hook failure."""
        cwd = str(PROJECT)
        cases = [
            ("session_start.py", {"hook_event_name": "SessionStart", "cwd": cwd}),
            ("before_agent.py", {"hook_event_name": "BeforeAgent", "cwd": cwd, "prompt": "hi"}),
            ("after_tool.py", {"hook_event_name": "AfterTool", "cwd": cwd,
                               "tool_name": "run_shell_command",
                               "tool_input": {"command": "grep -rn frobnicate_widget ."}}),
            ("after_tool.py", {"hook_event_name": "AfterTool", "cwd": cwd,
                               "tool_name": "write_file",
                               "tool_input": {"file_path": "widget.py"}}),
            ("session_end.py", {"hook_event_name": "SessionEnd", "cwd": cwd}),
        ]
        for script, event in cases:
            with self.subTest(script=script, tool=event.get("tool_name")):
                result = run_hook(script, event)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout.strip(), "", "context emitted with no backend")

    def test_05_real_unreachable_status_reads_as_unhealthy_and_blocks_map(self) -> None:
        import common  # noqa: PLC0415 - after setUpModule set the env
        status = run(["ix", "status"])
        self.assertNotEqual(status.returncode, 0, "ix status succeeded with no backend")
        for root in (PROJECT, REGISTERED):
            with self.subTest(root=root.name):
                self.assertFalse(common.ix_healthy(root))
                self.assertIsNone(common.request_guarded_map(str(root)))

    def test_06_real_pro_stub_is_recognised(self) -> None:
        """The OSS release's `briefing` stub must read as 'not Pro', and be cached."""
        import common  # noqa: PLC0415
        result = run(["ix", "briefing", "--format", "json"])
        if result.returncode == 0:
            self.skipTest("this ix has Ix Pro installed")
        self.assertTrue(common._is_pro_stub_response(result), result.stdout + result.stderr)
        self.assertFalse(common.ix_pro_available(PROJECT))
        cached = json.loads(common.PRO_CACHE_PATH.read_text())
        self.assertIs(cached["ok"], False)

    def test_07_after_tool_parses_real_text_output_and_real_error_records(self) -> None:
        """`ix text` works without a backend (ripgrep); `ix locate` fails with a real error.

        Unmapped dir: locate prints the `workspace_not_mapped` JSON record on
        stdout. Registered workspace: locate prints "Error: ..." on stderr.
        Health is forced true so the hook reaches its ix calls; it must
        summarise the real `ix text` JSON, drop the locate failure, and print
        the result on the channel Gemini hands the model.
        """
        import after_tool  # noqa: PLC0415
        import common  # noqa: PLC0415

        unmapped = run(["ix", "locate", "frobnicate_widget", "--format", "json"], cwd=PROJECT)
        self.assertNotEqual(unmapped.returncode, 0)
        self.assertEqual(json.loads(unmapped.stdout).get("error"), "workspace_not_mapped")

        for root in (PROJECT, REGISTERED):
            with self.subTest(root=root.name):
                self.assertIsNone(common.run_ix_json(
                    ["ix", "locate", "frobnicate_widget", "--format", "json"], cwd=root))
                event = {"hook_event_name": "AfterTool", "cwd": str(root),
                         "tool_name": "run_shell_command",
                         "tool_input": {"command": "grep -rn frobnicate_widget ."}}
                out = io.StringIO()
                with patch.object(after_tool, "ix_healthy", return_value=True), \
                        patch("sys.stdin", io.StringIO(json.dumps(event))), \
                        contextlib.redirect_stdout(out):
                    after_tool.main()
                hso = json.loads(out.getvalue())["hookSpecificOutput"]
                self.assertEqual(hso["hookEventName"], "AfterTool")
                self.assertIn("1 text hits in widget.py", hso["additionalContext"])
                self.assertNotIn("error", hso["additionalContext"].lower())

if __name__ == "__main__":
    unittest.main()
