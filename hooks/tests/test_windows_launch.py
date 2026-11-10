#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""How the hooks start ix and how Gemini starts the hooks.

On POSIX ix is started exactly as before: the bare argv `["ix", ...]`, no
shell. On Windows the Ix installer puts a nested `ix.cmd` launcher on PATH
(`bin\\ix.cmd` runs `cli\\ix.cmd`, which runs `node "<main.js>" %*`), which
CreateProcess cannot start by the bare name, and through which arguments could
be interpreted by cmd.exe. The hooks start node directly for that layout and
otherwise quote for any cmd.exe depth. The Windows tests run on windows-latest
in CI; the quoting, PATH lookup and layout detection tests run everywhere.
"""
from __future__ import annotations

import importlib.util
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
REPO = HOOKS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))

import fake_ix  # noqa: E402

WINDOWS = os.name == "nt"

# `%IX_HOME%\bin\ix.cmd` exactly as the Ix Windows installer
# (scripts/install/install.ps1 in the Ix repo) writes it.
INSTALLER_BIN_IX_CMD = """\
@echo off
if not exist "%~dp0..\\cli\\ix.cmd" goto :ix_missing
"%~dp0..\\cli\\ix.cmd" %*
exit /b %errorlevel%

:ix_missing
echo(
echo   The Ix CLI is not at "%~dp0..\\cli\\ix.cmd".
exit /b 1
"""
# `%IX_HOME%\cli\ix.cmd` from the Ix release: the script is therefore at
# `%IX_HOME%\cli\cli\dist\cli\main.js`.
INSTALLER_CLI_IX_CMD = """\
@echo off
node "%~dp0cli\\dist\\cli\\main.js" %*
"""
INSTALLER_MAIN_JS = ("cli", "cli", "dist", "cli", "main.js")


def _load_common():
    spec = importlib.util.spec_from_file_location("ix_common_launch", HOOKS_DIR / "common.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _awkward_args(marker: Path) -> list[str]:
    """Arguments with every character cmd.exe treats specially, plus canaries."""
    return [
        "a&b", "a|b", "a<b", "a>b", "a^b", 'a"b', "a%b", "a!b", "(a)", "a)b",
        "two words", "  padded  ", "trailing\\", "C:\\dir with space\\", 'a\\"b', 'a\\\\"b',
        '"', '""', "", "%PATH%", "%PATH:a=b%", "!PATH!", "%%", "^", "^^", "&&", "||",
        "def run(a, b): return a | b & c", 'grep -E "x|y" > out',
        f'" & type nul > "{marker}" & "',
        f'& type nul > "{marker}"',
        f'\\" & type nul > "{marker}',
        f'^" & type nul > "{marker}" ^"',
        "%", "end%",
    ]


def _write_installer_layout(ix_home: Path, main_js_text: str = "", newline: str = "\n") -> tuple[Path, Path]:
    """The installer's layout, with the launchers' verbatim text: (bin\\ix.cmd, main.js)."""
    outer = ix_home / "bin" / "ix.cmd"
    inner = ix_home / "cli" / "ix.cmd"
    main_js = ix_home.joinpath(*INSTALLER_MAIN_JS)
    for path in (outer, inner, main_js):
        path.parent.mkdir(parents=True, exist_ok=True)
    outer.write_bytes(INSTALLER_BIN_IX_CMD.replace("\n", newline).encode("utf-8"))
    inner.write_bytes(INSTALLER_CLI_IX_CMD.replace("\n", newline).encode("utf-8"))
    main_js.write_text(main_js_text, encoding="utf-8")
    return outer, main_js


class QuotingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.common = _load_common()

    def test_each_argument_is_one_quoted_region(self) -> None:
        quote = self.common.quote_batch_arg
        self.assertEqual('"status"', quote("status"))
        self.assertEqual('"a&b|c<d>e"', quote("a&b|c<d>e"))
        self.assertEqual('"a""b"', quote('a"b'))
        self.assertEqual('""', quote(""))
        self.assertEqual('"a^b!c"', quote("a^b!c"))

    def test_backslashes_before_a_quote_or_the_end_are_doubled(self) -> None:
        quote = self.common.quote_batch_arg
        self.assertEqual('"x\\\\"', quote("x\\"))
        self.assertEqual('"a\\\\""b"', quote('a\\"b'))
        self.assertEqual('"a\\b"', quote("a\\b"))

    def test_percent_is_neutralised(self) -> None:
        quote = self.common.quote_batch_arg
        self.assertEqual('"%%cd:~,%PATH%%cd:~,%"', quote("%PATH%"))

    def test_no_carets_are_added(self) -> None:
        for arg in _awkward_args(Path("marker")):
            self.assertEqual(arg.count("^"), self.common.quote_batch_arg(arg).count("^"), arg)

    def test_line_breaks_are_refused(self) -> None:
        for arg in ("a\nb", "a\rb", "a\r\nb", "\n"):
            with self.assertRaises(self.common.IxArgumentError):
                self.common.quote_batch_arg(arg)

    def test_command_line_shape(self) -> None:
        line = self.common.batch_command_line(
            r"C:\Windows\System32\cmd.exe", r"C:\Ix Home\bin\ix.cmd", ["text", "a|b"]
        )
        self.assertEqual(
            r'"C:\Windows\System32\cmd.exe" /e:on /d /v:off /s /c '
            r'""C:\Ix Home\bin\ix.cmd" "text" "a|b""',
            line,
        )


class LaunchRouteTest(unittest.TestCase):
    """Which process is started, and with what environment, for each route."""

    def setUp(self) -> None:
        self.common = _load_common()

    def test_cmd_route_sets_no_current_directory_lookup(self) -> None:
        launch = self.common.ix_process_args(
            ["status"], ("batch", [r"C:\Ix\bin\ix.cmd"]),
            env={"IX_AUTO_MAP": "1"}, cmd_exe=r"C:\Windows\System32\cmd.exe",
        )
        self.assertEqual(r"C:\Windows\System32\cmd.exe", launch.executable)
        self.assertIn("/v:off", launch.args)
        self.assertEqual("1", launch.env["NoDefaultCurrentDirectoryInExePath"])
        # The caller's environment is kept, not replaced.
        self.assertEqual("1", launch.env["IX_AUTO_MAP"])

    def test_cmd_route_without_env_inherits_and_adds_the_setting(self) -> None:
        with patch.dict(os.environ, {"IX_TEST_MARK": "kept"}):
            launch = self.common.ix_process_args(["status"], ("batch", [r"C:\Ix\bin\ix.cmd"]))
        self.assertEqual("kept", launch.env["IX_TEST_MARK"])
        self.assertEqual("1", launch.env["NoDefaultCurrentDirectoryInExePath"])

    def test_direct_route_has_no_shell(self) -> None:
        launch = self.common.ix_process_args(
            ["text", "a|b"], ("direct", [r"C:\node\node.exe", r"C:\Ix\cli\main.js"]), env=None
        )
        self.assertEqual([r"C:\node\node.exe", r"C:\Ix\cli\main.js", "text", "a|b"], launch.args)
        self.assertIsNone(launch.executable)
        self.assertIsNone(launch.env)

    def test_missing_ix_is_not_started_by_bare_name(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.common.ix_process_args(["status"], None)
        self.common._ix_launcher_cache = None
        with self.assertRaises(FileNotFoundError):
            self.common.windows_launch(["ix", "status"])

    def test_other_commands_are_unchanged(self) -> None:
        launch = self.common.windows_launch(["git", "rev-parse", "--show-toplevel"])
        self.assertEqual((["git", "rev-parse", "--show-toplevel"], None, None), tuple(launch))


class PathLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.common = _load_common()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()

    def _touch(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        return path

    def test_never_looks_in_the_current_or_a_relative_directory(self) -> None:
        planted = self.tmp / "project"
        self._touch(planted / "ix.cmd")
        self._touch(planted / "rel" / "ix.cmd")
        empty = self.tmp / "empty"
        empty.mkdir()
        cwd = os.getcwd()
        os.chdir(planted)
        try:
            path_env = os.pathsep.join(["", ".", "rel", str(empty)])
            self.assertIsNone(self.common.find_on_path("ix", path_env=path_env, pathext=".CMD"))
            self.assertIsNone(self.common._resolve_ix_launcher(path_env=path_env))
        finally:
            os.chdir(cwd)

    def test_pathext_order_and_launchable_extensions_only(self) -> None:
        bin_dir = self.tmp / "bin"
        self._touch(bin_dir / "ix.ps1")
        self._touch(bin_dir / "ix.cmd")
        exe = self._touch(bin_dir / "ix.exe")
        found = self.common.find_on_path("ix", path_env=str(bin_dir), pathext=".PS1;.EXE;.CMD")
        self.assertEqual(str(exe), found)
        found = self.common.find_on_path("ix", path_env=str(bin_dir), pathext=".PS1;.CMD;.EXE")
        self.assertEqual(str(bin_dir / "ix.cmd"), found)

    def test_first_path_entry_wins(self) -> None:
        first = self._touch(self.tmp / "a" / "ix.cmd")
        self._touch(self.tmp / "b" / "ix.cmd")
        path_env = os.pathsep.join([str(self.tmp / "b-missing"), str(first.parent), str(self.tmp / "b")])
        self.assertEqual(str(first), self.common.find_on_path("ix", path_env=path_env, pathext=".CMD"))


class InstallerLayoutTest(unittest.TestCase):
    """Detection of the installer layout from the launchers' verbatim text."""

    def setUp(self) -> None:
        self.common = _load_common()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.node_dir = self.tmp / "node"
        self.node_dir.mkdir()
        self.node = self.node_dir / "node.exe"
        self.node.write_text("")
        self.ix_home = self.tmp / "ix home"
        self.outer, self.main_js = _write_installer_layout(self.ix_home)
        self.inner = self.ix_home / "cli" / "ix.cmd"

    def detect(self, outer: Path | None = None, path_env: str | None = None):
        return self.common.installer_node_command(
            str(outer or self.outer), path_env=str(self.node_dir) if path_env is None else path_env
        )

    def test_verbatim_installer_launchers_start_node_with_the_cli_script(self) -> None:
        self.assertEqual([str(self.node), str(self.main_js)], self.detect())

    def test_verbatim_installer_launchers_with_crlf_and_bom(self) -> None:
        for path, text in ((self.outer, INSTALLER_BIN_IX_CMD), (self.inner, INSTALLER_CLI_IX_CMD)):
            path.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual([str(self.node), str(self.main_js)], self.detect())

    def test_more_echo_lines_in_the_missing_cli_block(self) -> None:
        self.outer.write_text(
            INSTALLER_BIN_IX_CMD.replace(
                "exit /b 1\n", "echo   Reinstall Ix to fix this.\necho(\nexit /b 1\n"
            )
        )
        self.assertEqual([str(self.node), str(self.main_js)], self.detect())

    def test_resolver_picks_the_node_route_for_the_installer_layout(self) -> None:
        path_env = os.pathsep.join([str(self.outer.parent), str(self.node_dir)])
        with patch.dict(os.environ, {"PATHEXT": ".COM;.EXE;.BAT;.CMD"}):
            self.assertEqual(
                ("direct", [str(self.node), str(self.main_js)]),
                self.common._resolve_ix_launcher(path_env=path_env),
            )

    def test_absolute_node_in_the_inner_launcher(self) -> None:
        self.inner.write_text(f'@echo off\n"{self.node}" "%~dp0cli\\dist\\cli\\main.js" %*\n')
        self.assertEqual([str(self.node), str(self.main_js)], self.detect(path_env=""))

    def test_anything_else_falls_back_to_cmd(self) -> None:
        main_js = "%~dp0cli\\dist\\cli\\main.js"
        cases = {
            "outer runs something else": (
                self.outer, INSTALLER_BIN_IX_CMD.replace('"%~dp0..\\cli\\ix.cmd" %*', '"%~dp0..\\other\\ix.cmd" %*'),
            ),
            "inner has no node line": (self.inner, "@echo off\nexit /b 1\n"),
            "inner has two node lines": (
                self.inner, f'@echo off\nnode "{main_js}" %*\nnode "{main_js}" %*\n',
            ),
            "inner expands a variable": (self.inner, '@echo off\nnode "%IX_HOME%\\main.js" %*\n'),
            "inner script missing": (self.inner, '@echo off\nnode "%~dp0missing.js" %*\n'),
        }
        for name, (path, text) in cases.items():
            with self.subTest(name):
                original = path.read_bytes()
                path.write_text(text)
                try:
                    self.assertIsNone(self.detect())
                finally:
                    path.write_bytes(original)

    def test_missing_inner_launcher_falls_back_to_cmd(self) -> None:
        self.inner.unlink()
        self.assertIsNone(self.detect())

    def test_no_node_on_path_falls_back_to_cmd(self) -> None:
        self.assertIsNone(self.detect(path_env=""))

    def test_not_under_bin_is_not_the_installer_layout(self) -> None:
        other = self.ix_home / "elsewhere" / "ix.cmd"
        other.parent.mkdir()
        other.write_bytes(self.outer.read_bytes())
        self.assertIsNone(self.detect(other))


@unittest.skipIf(WINDOWS, "POSIX behaviour")
class PosixLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.common = _load_common()

    def test_run_command_passes_the_bare_argv_with_no_shell(self) -> None:
        completed = subprocess.CompletedProcess(["ix"], 0, "{}", "")
        with patch.object(self.common.subprocess, "run", return_value=completed) as run:
            self.common.run_command(["ix", "status"], cwd="/tmp", timeout=3)
        args, kwargs = run.call_args
        self.assertEqual((["ix", "status"],), args)
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("executable", kwargs)
        self.assertNotIn("env", kwargs)

    def test_ix_available_uses_path_lookup(self) -> None:
        with patch.object(self.common.shutil, "which", return_value=None) as which:
            self.assertFalse(self.common.ix_available())
        which.assert_called_once_with("ix")

    def test_fake_ix_receives_arguments_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = fake_ix.isolated_env(Path(tmp))
            args = _awkward_args(Path(tmp) / "marker")
            with patch.dict(os.environ, env, clear=True):
                result = self.common.run_command(["ix", "smells", *args], timeout=10)
            self.assertIsNotNone(result)
            self.assertEqual(["smells", *args], fake_ix.read_log(Path(env["FAKE_IX_LOG"]))[0]["argv"])
            self.assertFalse((Path(tmp) / "marker").exists())


_FAKE_MAIN_JS = """\
const fs = require('fs');
const args = process.argv.slice(2);
fs.writeFileSync(%s, JSON.stringify(args));
if (args[0] === 'exit-3') process.exitCode = 3;
"""


@unittest.skipUnless(WINDOWS, "Windows launcher")
class WindowsLaunchTest(unittest.TestCase):
    """The two-level installer launcher, started both ways, with canaries."""

    def setUp(self) -> None:
        self.common = _load_common()
        node = self.common.find_on_path("node", extensions=(".exe",))
        if node is None:
            self.skipTest("node is not on PATH")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.out = self.tmp / "argv.json"
        self.marker = self.tmp / "canary-marker"
        self.outer, self.main_js = _write_installer_layout(
            self.tmp / "ix home", _FAKE_MAIN_JS % json.dumps(str(self.out)), newline="\r\n"
        )
        self.path_env = os.pathsep.join([str(self.outer.parent), os.environ.get("PATH", "")])
        self.batch = ("batch", [str(self.outer)])
        self.args = _awkward_args(self.marker)
        # The hooks run with the user's workspace as cwd. A `node` planted there
        # must not be what the launcher's bare `node` resolves to.
        self.workspace = self.tmp / "workspace"
        self.workspace.mkdir()
        (self.workspace / "node.cmd").write_text(f'@type nul > "{self.marker}"\r\n')

    def run_ix(self, launcher, args: list[str]) -> subprocess.CompletedProcess[str]:
        launch = self.common.ix_process_args(args, launcher)
        return subprocess.run(
            launch.args, executable=launch.executable, env=launch.env, cwd=str(self.workspace),
            capture_output=True, text=True, timeout=60,
        )

    def received(self) -> list[str]:
        return json.loads(self.out.read_text(encoding="utf-8"))

    def test_installer_layout_is_started_without_cmd(self) -> None:
        kind, prefix = self.common._resolve_ix_launcher(path_env=self.path_env)
        self.assertEqual("direct", kind)
        self.assertEqual(os.path.normcase(str(self.main_js)), os.path.normcase(prefix[1]))
        result = self.run_ix((kind, prefix), self.args)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.args, self.received())
        self.assertFalse(self.marker.exists())

    def test_two_level_launcher_through_cmd(self) -> None:
        result = self.run_ix(self.batch, self.args)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.args, self.received())
        self.assertFalse(self.marker.exists())

    def test_each_argument_alone_through_cmd(self) -> None:
        for arg in self.args:
            with self.subTest(arg=arg):
                result = self.run_ix(self.batch, ["x", arg])
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(["x", arg], self.received())
                self.assertFalse(self.marker.exists())

    def test_exit_code_passes_through_both_routes(self) -> None:
        for launcher in (self.batch, self.common._resolve_ix_launcher(path_env=self.path_env)):
            with self.subTest(kind=launcher[0]):
                self.assertEqual(3, self.run_ix(launcher, ["exit-3"]).returncode)

    def test_run_command_resolves_the_installer_ix_cmd_from_path(self) -> None:
        with patch.dict(os.environ, {"PATH": self.path_env}):
            self.common._ix_launcher_cache = self.common._UNSET
            self.assertTrue(self.common.ix_available())
            self.assertEqual("direct", self.common._ix_launcher()[0])
            result = self.common.run_command(["ix", *self.args], cwd=self.workspace, timeout=60)
        self.assertIsNotNone(result)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.args, self.received())
        self.assertFalse(self.marker.exists())

    def test_line_break_is_refused_and_nothing_runs(self) -> None:
        self.common._ix_launcher_cache = self.batch
        self.assertIsNone(self.common.run_command(["ix", "text", "a\nb"], cwd=self.workspace))
        self.assertFalse(self.out.exists())

    def test_ix_missing_from_path_is_not_started_from_the_workspace(self) -> None:
        (self.workspace / "ix.cmd").write_text(f'@type nul > "{self.marker}"\r\n')
        with patch.dict(os.environ, {"PATH": str(self.tmp / "no-ix-here")}):
            self.common._ix_launcher_cache = self.common._UNSET
            self.assertFalse(self.common.ix_available())
            self.assertIsNone(self.common.run_command(["ix", "status"], cwd=self.workspace))
        self.assertFalse(self.marker.exists())

    def test_hooks_reach_a_one_level_fake_ix_cmd(self) -> None:
        env = fake_ix.isolated_env(self.tmp / "hook")
        repo = self.tmp / "hook" / "repo"
        repo.mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "session_start.py")],
            input=json.dumps({"cwd": str(repo)}), env=env, cwd=str(repo),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        calls = fake_ix.read_log(Path(env["FAKE_IX_LOG"]))
        self.assertIn(["status"], [call["argv"] for call in calls])
        self.assertIn("Ix Memory is available", result.stdout)


_HOOK_COMMAND_RE = re.compile(r'^python3 "\$\{extensionPath\}/hooks/[a-z_]+\.py"$')


def _hook_commands(hooks_json: Path) -> list[str]:
    config = json.loads(hooks_json.read_text(encoding="utf-8"))["hooks"]
    return [hook["command"] for definitions in config.values() for d in definitions for hook in d["hooks"]]


class HookCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.env = fake_ix.isolated_env(self.tmp)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()

    def test_commands_quote_the_extension_path(self) -> None:
        commands = _hook_commands(HOOKS_DIR / "hooks.json")
        self.assertEqual(4, len(commands))
        for command in commands:
            self.assertRegex(command, _HOOK_COMMAND_RE)

    def _run_all(self, commands: list[str], ext_dir: Path, shell) -> None:
        """Run each command line as ``shell(line)`` would start it."""
        for command in commands:
            with self.subTest(command=command):
                line = command.replace("${extensionPath}", str(ext_dir))
                result = subprocess.run(
                    shell(line), input=json.dumps({"cwd": str(self.repo)}),
                    cwd=str(self.repo), env=self.env, capture_output=True, text=True, timeout=60,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("can't open file", result.stderr)
        calls = fake_ix.read_log(Path(self.env["FAKE_IX_LOG"]))
        self.assertIn(["status"], [call["argv"] for call in calls])

    @unittest.skipIf(WINDOWS, "POSIX shell")
    def test_hooks_run_from_a_path_with_a_space(self) -> None:
        if shutil.which("python3", path=self.env["PATH"]) is None:
            self.skipTest("python3 is not on PATH")
        ext_dir = self.tmp / "extension dir"
        (ext_dir / "hooks").mkdir(parents=True)
        for script in HOOKS_DIR.glob("*.py"):
            shutil.copy(script, ext_dir / "hooks" / script.name)
        self._run_all(_hook_commands(HOOKS_DIR / "hooks.json"), ext_dir, lambda line: ["/bin/sh", "-c", line])

    @unittest.skipUnless(WINDOWS, "install.ps1 and PowerShell")
    def test_install_ps1_hooks_run_from_a_path_with_a_space(self) -> None:
        target = self.tmp / "project with space"
        target.mkdir()
        install = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(REPO / "install.ps1"), "-Repo", str(target), "-Force"],
            env=self.env, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(0, install.returncode, install.stdout + install.stderr)
        ext_dir = target / ".gemini" / "extensions" / "ix-memory"
        raw = (ext_dir / "hooks" / "hooks.json").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "hooks.json must not start with a BOM")
        commands = _hook_commands(ext_dir / "hooks" / "hooks.json")
        for command in commands:
            self.assertRegex(command, r'^(python3|python|py -3) "\$\{extensionPath\}/hooks/[a-z_]+\.py"$')
        shells = {
            "powershell": lambda line: ["powershell.exe", "-NoProfile", "-Command", line],
            # A verbatim command line: cmd.exe does not read `\"` as a quote.
            "cmd": lambda line: f'cmd.exe /d /s /c "{line}"',
        }
        for name, shell in shells.items():
            with self.subTest(shell=name):
                self._run_all(commands, ext_dir, shell)


if __name__ == "__main__":
    unittest.main()
