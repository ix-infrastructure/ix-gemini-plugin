# Copyright 2026 Ix Infrastructure Inc.

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple


def _state_dir() -> Path:
    """Per-user state directory for hook caches and the map debounce.

    It used to be ``$TMPDIR/ix-gemini-hooks``: one predictable directory shared
    by every user on the machine and by every workspace, so a health answer or a
    briefing stamp for one project was served to the next one opened within the
    TTL. ``$XDG_STATE_HOME`` (default ``~/.local/state``) is per-user; anything
    that is per-project data is additionally keyed by the workspace root.
    """
    xdg = os.environ.get("XDG_STATE_HOME", "")
    base = Path(xdg) if xdg and os.path.isabs(xdg) else Path.home() / ".local" / "state"
    return base / "ix-gemini-plugin"


CACHE_DIR = _state_dir()
# Whether @ix/pro is installed is a property of the user's ix install, not of a
# project, so this one cache is per-user only.
PRO_CACHE_PATH = CACHE_DIR / "ix-pro.json"

HEALTH_TTL_SECONDS = 30
# Whether @ix/pro is installed changes only when someone installs or removes it,
# and the probe now runs a real command rather than `--help`, so it is cached far
# longer than the health check it used to borrow its TTL from.
PRO_TTL_SECONDS = 3600
BRIEFING_TTL_SECONDS = 600
# The text form: it is what the model reads, and it is several times smaller
# than the JSON document of the same briefing.
BRIEFING_ARGV = ["ix", "briefing", "--format", "text"]
# Longest briefing BeforeAgent adds to a prompt, in characters.
BRIEFING_MAX_CHARS = 4000
# At most one automatic map per workspace root per window. Ix itself holds a
# per-workspace map lock, so this only stops a burst of edits from queueing a
# burst of maps.
MAP_DEBOUNCE_SECONDS = 300

# Wall-clock budget for all the ix calls one run of each hook makes. Each sits
# under that hook's `timeout` in hooks.json (milliseconds), leaving room for
# Python start-up. Gemini kills a hook that outlives its timeout and drops its
# output (hookRunner.ts), so an unbounded hook loses its context entirely and
# holds up the turn or tool result for the full timeout before it does.
HOOK_BUDGET_SECONDS = {
    "SessionStart": 10,
    "BeforeAgent": 12,
    "AfterTool": 8,
    "SessionEnd": 3,
}
# Not worth starting an ix call with less than this left.
MIN_CALL_SECONDS = 0.5
# Longest a timed-out ix call on Windows may spend having its process tree
# killed. It is spent after the budget, so every hook's budget plus this stays
# under the timeout hooks.json gives Gemini (test_windows_launch checks this).
KILL_TREE_SECONDS = 1.0

SHELL_OPERATORS = ("|", "&&", "||", ";", "$(", "`")
SEARCH_COMMANDS = {"grep", "rg"}
READ_COMMANDS = {"cat", "head", "tail", "sed", "awk"}
# The search hint answers "where is this symbol defined", so it runs only for a
# pattern that could be one: a plain identifier, never a phrase, a regular
# expression or a path, and never one that is too short to be specific.
IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
MIN_PATTERN_CHARS = 3
# Grep patterns shaped like credentials are neither sent to ix nor echoed back.
# Known token formats first, then generic high-entropy runs: a long hex string,
# or a long letters-and-digits run that switches between upper case, lower case
# and digits far more often than a camelCase name does.
_SECRET_PREFIX_RE = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[A-Z0-9]{16}"
    r"|[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"
    r"|xox[abposr][-_][A-Za-z0-9_-]{10,}"
    r"|glpat[-_][A-Za-z0-9_-]{20,}"
    r"|AIza[A-Za-z0-9_-]{30,}"
    r"|npm_[A-Za-z0-9]{30,}"
)
_HEX_RUN_RE = re.compile(r"[0-9a-fA-F]{32,}")
_ALNUM_RUN_RE = re.compile(r"[A-Za-z0-9]{20,}")
# Share of adjacent characters that change class (upper/lower/digit): about 0.6
# for a random token, well under 0.5 for an identifier made of words.
_TOKEN_SWITCH_RATIO = 0.5
# One switch per hint. Unset or any other value leaves the hint on.
SEARCH_HINT_ENV = "IX_HOOK_SEARCH_HINT"
READ_HINT_ENV = "IX_HOOK_READ_HINT"
_HINT_OFF_VALUES = {"0", "off", "false", "no"}
# Cap on the one ix lookup a hint makes.
HINT_LOOKUP_SECONDS = 10
SEARCH_VALUE_OPTIONS = {
    "-A", "-B", "-C", "-e", "-f", "-g", "-m", "-t",
    "--context", "--file", "--glob", "--max-count",
    "--regexp", "--type", "--type-add",
}
READ_SKIP_SUFFIXES = (
    ".bin", ".exe", ".gif", ".gz", ".ico", ".jpeg",
    ".jpg", ".pdf", ".png", ".tar", ".zip",
)
READ_SKIP_SEGMENTS = (
    "/.git/", "/__pycache__/", "/build/", "/dist/",
    "/generated/", "/node_modules/",
)
READ_SKIP_BASENAMES = {
    "cargo.lock", "go.sum", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock",
}


# ── IO helpers ───────────────────────────────────────────────────────────────

def read_event() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def emit_json(payload: dict) -> None:
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")


def emit_model_context(event_name: str, context: str) -> None:
    """Print `context` on the channel Gemini hands to the model.

    Gemini reads only ``hookSpecificOutput.additionalContext``
    (DefaultHookOutput.getAdditionalContext in packages/core/src/hooks/types.ts):
    SessionStart adds it to history, BeforeAgent to the prompt, AfterTool to
    the tool result. A top-level ``additionalContext`` is ignored, and
    ``systemMessage`` is shown to the user only.
    """
    emit_json({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    })


class Deadline:
    """The wall-clock budget one hook run shares across its ix calls."""

    def __init__(self, seconds: float) -> None:
        self._end = time.monotonic() + seconds

    def remaining(self) -> float:
        return max(0.0, self._end - time.monotonic())

    def timeout(self, cap: float) -> float | None:
        """``min(cap, remaining)``, or None when too little is left to start a call."""
        left = self.remaining()
        if left < MIN_CALL_SECONDS:
            return None
        return min(cap, left)


def _call_timeout(cap: float, deadline: Deadline | None) -> float | None:
    return cap if deadline is None else deadline.timeout(cap)


def log(msg: str) -> None:
    """Debug logging — always to stderr so it never corrupts JSON stdout."""
    print(msg, file=sys.stderr)


# ── Workspace ────────────────────────────────────────────────────────────────

def find_workspace_root(cwd: str | None) -> Path:
    start = Path(cwd or os.getcwd()).resolve()
    home = Path.home().resolve()
    for candidate in (start, *start.parents):
        # ~/.gemini/settings.json is Gemini's *user* settings file, present for
        # every Gemini user, so it never marks a workspace. Without this check
        # every project under $HOME that lacks its own .gemini/ resolved to $HOME.
        if candidate == home:
            continue
        if (candidate / ".gemini" / "settings.json").exists():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


# ── Command execution ────────────────────────────────────────────────────────

def run_command(
    argv: list[str], cwd: str | Path | None = None, timeout: float = 10
) -> subprocess.CompletedProcess[str] | None:
    if os.name != "nt":
        try:
            return subprocess.run(
                argv,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
    try:
        launch = windows_launch(argv)
    except IxArgumentError as exc:
        log(f"[ix] {exc}")
        return None
    except OSError:
        # ix is not on PATH: report it as missing, never start a bare `ix`.
        return None
    try:
        return _run_windows(launch, cwd, timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def ix_available() -> bool:
    if os.name != "nt":
        return shutil.which("ix") is not None
    return _ix_launcher() is not None


# ── Starting ix on Windows ───────────────────────────────────────────────────
#
# CreateProcess does not resolve the bare name `ix` to the `ix.cmd` the Ix
# Windows installer puts on PATH, so on Windows the hooks resolve it themselves.
# That `ix.cmd` is a nested launcher: `<IX_HOME>\bin\ix.cmd` runs
# `<IX_HOME>\cli\ix.cmd`, which runs `node "%~dp0cli\dist\cli\main.js" %*`.
# Started through cmd.exe, an argument is parsed by cmd.exe once per level, and
# arguments here come from the agent's tool calls (search patterns, file
# paths), so they could be interpreted by cmd.exe through the installer's
# nested launcher. Two routes, in order:
#
# A. For the installer layout, start node with the CLI's script directly, with
#    no shell at all. This is the normal route.
# B. Otherwise start the .cmd through cmd.exe with quoting that holds at any
#    depth (the scheme Rust's standard library uses for batch files): every
#    argument in double quotes, `"` doubled, backslashes before a quote or the
#    end doubled, `%` neutralised, CR/LF refused, no carets, `/v:off`. The
#    child gets NoDefaultCurrentDirectoryInExePath=1 so a bare `node` inside
#    the launcher is not looked up in the workspace (the hook's cwd).
#
# If PATH has no ix, ix is reported as not installed; a bare `ix` is never
# started (Windows would look in the current directory first).
#
# POSIX is untouched: the bare argv, no shell.

class IxArgumentError(ValueError):
    """An argument cmd.exe cannot carry intact, so ix is not started."""


class WindowsLaunch(NamedTuple):
    """What to hand subprocess on Windows.

    ``args`` is a list (started with no shell) or, for route B, the verbatim
    cmd.exe command line. ``env`` None inherits the caller's environment.
    """

    args: list[str] | str
    executable: str | None
    env: dict[str, str] | None


# Only what CreateProcess (.exe/.com) or cmd.exe (.cmd/.bat) can start.
_LAUNCHABLE_EXTENSIONS = (".com", ".exe", ".bat", ".cmd")
_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"
_UNSET = object()
_ix_launcher_cache: object = _UNSET

# The launch line of the installer's `bin\ix.cmd`:
#   "%~dp0..\cli\ix.cmd" %*
# The file around it is several lines (`@echo off`, an `if not exist ... goto`
# guard, `exit /b %errorlevel%`, and a `:ix_missing` block of `echo` lines).
_OUTER_LAUNCH_RE = re.compile(
    r'^@?\s*(?:call\s+)?"%~dp0\.\.\\cli\\ix\.cmd"\s+%\*\s*$', re.IGNORECASE
)
# The launch line of `cli\ix.cmd` from the Ix release:
#   node "%~dp0cli\dist\cli\main.js" %*
_INNER_LAUNCH_RE = re.compile(
    r'^@?\s*(?:"(?P<quoted>[^"]+)"|(?P<bare>node(?:\.exe)?))\s+"(?P<script>[^"]+)"\s+%\*\s*$',
    re.IGNORECASE,
)
# The other lines a launcher may have and still be skipped by starting node
# directly: blank, `@echo off`, a plain comment, and `setlocal`/`endlocal` with
# nothing set. After the launch line, `exit /b [%errorlevel%|<n>]` too. Anything
# else (`set`, `call`, NODE_OPTIONS, ...) could change how node runs, so such a
# launcher goes through cmd.exe instead, which runs it as written.
_INERT_LINE_RE = re.compile(
    r"^(?:|@?\s*echo\s+off|@?\s*rem(?:\s[^&|<>^%!]*)?|::[^&|<>^%!]*"
    r"|@?\s*(?:setlocal|endlocal))\s*$",
    re.IGNORECASE,
)
_EXIT_LINE_RE = re.compile(r"^@?\s*exit\s+/b(?:\s+(?:%errorlevel%|\d+))?\s*$", re.IGNORECASE)
# The installer's guard before its launch line in `bin\ix.cmd`.
_OUTER_GUARD_RE = re.compile(
    r'^@?\s*if\s+not\s+exist\s+"%~dp0\.\.\\cli\\ix\.cmd"\s+goto\s+:?ix_missing\s*$',
    re.IGNORECASE,
)


def _launcher_is_plain(
    lines: list[str], launch_re: re.Pattern[str], extra: tuple[re.Pattern[str], ...] = ()
) -> bool:
    """True when exactly one line matches ``launch_re`` and nothing else runs before it ends.

    Lines are allowed before the launch line only when inert (or in ``extra``).
    After it, inert lines up to an ``exit /b``; once that exit is reached, the
    rest of the file is only reachable through a label (the installer's
    ``:ix_missing`` block), so it does not affect a normal run.
    """
    launches = 0
    exited = False
    for line in lines:
        if exited:
            continue
        if launch_re.match(line):
            launches += 1
        elif launches and _EXIT_LINE_RE.match(line):
            exited = True
        elif not (_INERT_LINE_RE.match(line) or any(r.match(line) for r in extra)):
            return False
    return launches == 1


def find_on_path(
    name: str,
    path_env: str | None = None,
    pathext: str | None = None,
    extensions: tuple[str, ...] = _LAUNCHABLE_EXTENSIONS,
) -> str | None:
    """Windows-style PATH x PATHEXT lookup that never looks in the current directory.

    Empty and relative PATH entries are skipped, so a launcher planted in the
    project cannot stand in for ix. Only ``extensions`` (in PATHEXT order) count.
    """
    if path_env is None:
        path_env = os.environ.get("PATH", "")
    if pathext is None:
        pathext = os.environ.get("PATHEXT") or _DEFAULT_PATHEXT
    allowed = {ext.lower() for ext in extensions}
    # Lower case: the Windows file system ignores case either way.
    exts = [ext.lower() for ext in pathext.split(";") if ext.lower() in allowed]
    for entry in path_env.split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        for ext in exts:
            candidate = os.path.join(entry, name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None


def _batch_lines(path: str) -> list[str] | None:
    try:
        # utf-8-sig: a launcher written by Windows PowerShell may start with a BOM.
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    return [line.strip() for line in text.splitlines()]


def _expand_dp0(value: str, directory: str) -> str | None:
    """Substitute `%~dp0` with ``directory``; None if cmd.exe would expand anything else."""
    expanded = re.sub(r"%~dp0", lambda _m: directory + "\\", value, flags=re.IGNORECASE)
    if "%" in expanded or "!" in expanded:
        return None
    # The launchers use `\`; on Windows this changes nothing.
    return os.path.normpath(expanded.replace("\\", os.sep))


def installer_node_command(ix_cmd: str, path_env: str | None = None) -> list[str] | None:
    """``[node, main.js]`` for the Ix installer layout, or None if it is not that.

    The layout is ``<dir>\\bin\\ix.cmd`` that runs ``"%~dp0..\\cli\\ix.cmd" %*``,
    and ``<dir>\\cli\\ix.cmd`` with exactly one ``node "<script>" %*`` line whose
    script exists. Neither may have a line that could change how node runs
    (see ``_launcher_is_plain``); such a launcher goes through cmd.exe. Starting
    node with that script directly is what the two launchers end up doing,
    without cmd.exe parsing the arguments.
    """
    bin_dir = os.path.dirname(ix_cmd)
    if os.path.basename(ix_cmd).lower() != "ix.cmd" or os.path.basename(bin_dir).lower() != "bin":
        return None
    cli_dir = os.path.join(os.path.dirname(bin_dir), "cli")
    inner_path = os.path.join(cli_dir, "ix.cmd")
    if not os.path.isfile(inner_path):
        return None
    outer = _batch_lines(ix_cmd)
    if outer is None or not _launcher_is_plain(outer, _OUTER_LAUNCH_RE, (_OUTER_GUARD_RE,)):
        return None
    inner = _batch_lines(inner_path) or []
    if not _launcher_is_plain(inner, _INNER_LAUNCH_RE):
        return None
    match = next(m for m in map(_INNER_LAUNCH_RE.match, inner) if m)
    script = _expand_dp0(match.group("script"), cli_dir)
    if script is None or not os.path.isabs(script) or not os.path.isfile(script):
        return None
    if match.group("quoted"):
        node = _expand_dp0(match.group("quoted"), cli_dir)
        if node is None or not os.path.isabs(node) or not os.path.isfile(node):
            return None
        if os.path.splitext(node)[1].lower() not in (".exe", ".com"):
            return None
    else:
        node = find_on_path("node", path_env=path_env, extensions=(".exe", ".com"))
        if node is None:
            return None
    return [node, script]


def _resolve_ix_launcher(path_env: str | None = None) -> tuple[str, list[str]] | None:
    """``("direct", argv prefix)`` or ``("batch", [ix.cmd])``; None when ix is absent."""
    resolved = find_on_path("ix", path_env=path_env)
    if resolved is None:
        return None
    if os.path.splitext(resolved)[1].lower() in (".exe", ".com"):
        return "direct", [resolved]
    node_command = installer_node_command(resolved, path_env=path_env)
    if node_command is not None:
        return "direct", node_command
    return "batch", [resolved]


def _ix_launcher() -> tuple[str, list[str]] | None:
    """The launcher for ix, resolved once per process."""
    global _ix_launcher_cache
    if _ix_launcher_cache is _UNSET:
        _ix_launcher_cache = _resolve_ix_launcher()
    return _ix_launcher_cache  # type: ignore[return-value]


def quote_batch_arg(arg: str) -> str:
    """Quote one argument for a .cmd/.bat command line, at any cmd.exe depth.

    Wrapped in double quotes with every inner `"` doubled, so each cmd.exe pass
    sees one quoted region and no character in it is special. Backslashes
    before a quote or the end are doubled for the C runtime that finally splits
    the line. `%` becomes `%%cd:~,%`, which expands back to `%` instead of to a
    variable. No carets: one pass would consume them and the next would not.
    """
    if "\r" in arg or "\n" in arg or "\0" in arg:
        raise IxArgumentError(
            "an ix argument contains a line break, which cmd.exe cannot pass intact; ix was not started"
        )
    out = ['"']
    backslashes = 0
    for ch in arg:
        if ch == "\\":
            backslashes += 1
        else:
            if ch == '"':
                out.append("\\" * backslashes + '"')
            elif ch == "%":
                out.append("%%cd:~,")
            backslashes = 0
        out.append(ch)
    out.append("\\" * backslashes + '"')
    return "".join(out)


def _system32(name: str) -> str:
    root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    return os.path.join(root, "System32", name)


def batch_command_line(cmd_exe: str, script: str, args: list[str]) -> str:
    """The verbatim CreateProcess command line that runs ``script args`` via cmd.exe."""
    line = " ".join(quote_batch_arg(part) for part in [script, *args])
    # /s strips exactly the outer quotes; /v:off so delayed expansion enabled in
    # the registry cannot act on `!`; /d skips AutoRun; /e:on for `%cd:~,%`.
    return f'"{cmd_exe}" /e:on /d /v:off /s /c "{line}"'


def ix_process_args(
    args: list[str],
    launcher: tuple[str, list[str]] | None,
    env: dict[str, str] | None = None,
    cmd_exe: str | None = None,
) -> WindowsLaunch:
    """How to start ``ix <args>`` with ``launcher``; FileNotFoundError when there is none."""
    if launcher is None:
        raise FileNotFoundError("ix not found on PATH")
    kind, prefix = launcher
    if kind == "direct":
        return WindowsLaunch([*prefix, *args], None, env)
    cmd_exe = cmd_exe or _system32("cmd.exe")
    command_line = batch_command_line(cmd_exe, prefix[0], list(args))
    child_env = dict(os.environ if env is None else env)
    # cmd.exe looks a bare name (the launcher's `node`) up in the current
    # directory before PATH unless this is set; the cwd is the user's workspace.
    child_env["NoDefaultCurrentDirectoryInExePath"] = "1"
    return WindowsLaunch(command_line, cmd_exe, child_env)


def windows_launch(argv: list[str], env: dict[str, str] | None = None) -> WindowsLaunch:
    """What to hand subprocess on Windows for ``argv``: changed only when it is ix."""
    if not argv or argv[0] != "ix":
        return WindowsLaunch(list(argv), None, env)
    return ix_process_args(list(argv[1:]), _ix_launcher(), env=env)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    # Killing cmd.exe or node alone could leave a child holding the pipes open.
    # taskkill /T must run first: it finds the children through the live parent.
    # Bounded by KILL_TREE_SECONDS, then the parent is killed regardless.
    try:
        subprocess.run(
            [_system32("taskkill.exe"), "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=KILL_TREE_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run_windows(
    launch: WindowsLaunch, cwd: str | Path | None, timeout: float
) -> subprocess.CompletedProcess[str]:
    # A string `args` is the verbatim command line for cmd.exe, and
    # `executable` names cmd.exe by absolute path, so nothing is looked up.
    proc = subprocess.Popen(
        launch.args,
        executable=launch.executable,
        cwd=str(cwd) if cwd else None,
        env=launch.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)


# ── Caching ──────────────────────────────────────────────────────────────────

def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _root_key(root: str | Path | None) -> str:
    """Stable per-workspace cache key: a hash of the canonical root path."""
    canonical = str(Path(root or os.getcwd()).resolve())
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _write_cache(path: Path, payload: dict) -> None:
    _ensure_private_dir(path.parent)
    path.write_text(json.dumps(payload))


def _status_cache_path(root: str | Path | None) -> Path:
    return CACHE_DIR / "health" / f"{_root_key(root)}.json"


def _briefing_cache_path(root: str | Path | None) -> Path:
    return CACHE_DIR / "briefing" / f"{_root_key(root)}.txt"


def _cached_health(cwd: str | Path | None) -> bool | None:
    """The health answer cached for this workspace, or None if none is fresh."""
    cache_path = _status_cache_path(cwd)
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cached, dict):
        return None
    timestamp = float(cached.get("timestamp", 0))
    if time.time() - timestamp >= HEALTH_TTL_SECONDS:
        return None
    return bool(cached.get("ok", False))


def ix_healthy(cwd: str | Path | None, deadline: Deadline | None = None) -> bool:
    if not ix_available():
        return False
    cached = _cached_health(cwd)
    if cached is not None:
        return cached
    timeout = _call_timeout(8, deadline)
    if timeout is None:
        return False
    result = run_command(["ix", "status"], cwd=cwd, timeout=timeout)
    ok = bool(result and result.returncode == 0)
    try:
        _write_cache(_status_cache_path(cwd), {"timestamp": time.time(), "ok": ok})
    except OSError:
        pass
    return ok


def _hint_backoff_path(root: str | Path | None) -> Path:
    return CACHE_DIR / "hint-backoff" / f"{_root_key(root)}.stamp"


def _start_hint_backoff(cwd: str | Path | None) -> None:
    path = _hint_backoff_path(cwd)
    try:
        _ensure_private_dir(path.parent)
        path.write_text(str(time.time()))
    except OSError as exc:
        log(f"[ix] hint back-off stamp failed (non-fatal): {exc}")


def ix_known_unhealthy(cwd: str | Path | None) -> bool:
    """True when the shell hints should not call ix here for now.

    That is when a fresh cached health answer says ix is not healthy, or a hint
    lookup timed out in this workspace within HEALTH_TTL_SECONDS. The shell
    hints check only this, not ``ix status``, so a hinted command starts at
    most the one lookup it needs. The health answer is written by
    ``ix_healthy``: by SessionStart, and by BeforeAgent only when a briefing is
    due, so most hinted commands find no fresh answer and run the lookup. A
    hint timeout is kept apart from that answer, so a slow lookup never turns
    off SessionStart guidance or the BeforeAgent briefing.
    """
    if _cached_health(cwd) is False:
        return True
    try:
        return time.time() - _hint_backoff_path(cwd).stat().st_mtime < HEALTH_TTL_SECONDS
    except OSError:
        return False


def _is_pro_stub_response(result: subprocess.CompletedProcess[str]) -> bool:
    """True when ix answered with the Pro stub — a definitive 'not a Pro install'.

    The stub's contract is the literal string `The '<name>' command requires Ix
    Pro.` on exit 1. Matching it is what separates "Pro is absent" from "the
    probe happened to fail", which is the difference between a cacheable answer
    and one that must not be cached.
    """
    blob = f"{result.stdout or ''}{result.stderr or ''}"
    return "requires Ix Pro" in blob


def ix_pro_briefing(
    cwd: str | Path | None, deadline: Deadline | None = None
) -> tuple[bool, str | None]:
    """Whether Ix Pro is installed, plus the briefing text if this call ran it.

    The probe is `ix briefing` itself, so when it runs and succeeds its output
    is the briefing; BeforeAgent uses it instead of starting the CLI again. The
    text is None when the answer came from the cache or Pro is not available.
    """
    if PRO_CACHE_PATH.exists():
        try:
            cached = json.loads(PRO_CACHE_PATH.read_text())
        except (OSError, json.JSONDecodeError):
            cached = None
        if isinstance(cached, dict):
            timestamp = float(cached.get("timestamp", 0))
            ok = bool(cached.get("ok", False))
            if time.time() - timestamp < PRO_TTL_SECONDS:
                return ok, None
    # Probe with the real command, not `--help`.
    #
    # Pro commands are always *registered*: without @ix/pro the CLI installs a
    # stub for each one whose action prints "The 'briefing' command requires Ix
    # Pro." and sets exit 1. But `--help` is handled by the arg parser before any
    # action runs, so `ix briefing --help` exits 0 on a stub exactly as it does
    # on the real command. Probing with it reported Pro as available on every
    # OSS install, and the hooks then ran Pro commands that could only fail.
    #
    # Running the command itself is the discriminator: the stub exits 1, the real
    # command exits 0. ix_healthy() is checked before this (before_agent.py), so
    # the backend is already known reachable.
    timeout = _call_timeout(8, deadline)
    if timeout is None:
        return False, None
    result = run_command(BRIEFING_ARGV, cwd=cwd, timeout=timeout)
    if result is None:
        # Could not run ix at all (timeout, OSError). Says nothing about Pro.
        return False, None
    ok = result.returncode == 0
    if not ok and not _is_pro_stub_response(result):
        # A non-zero exit that is NOT the Pro stub is a transient failure — a
        # backend hiccup, an expired session, a slow first call. Returning False
        # for this run is right, but caching it is not: PRO_TTL_SECONDS is an
        # hour, so one blip would suppress every Pro feature for a Pro user
        # until it expires. Leave the cache alone and re-probe next time.
        return False, None
    _write_cache(PRO_CACHE_PATH, {"timestamp": time.time(), "ok": ok})
    return ok, (result.stdout or "") if ok else None


def briefing_due(root: str | Path | None, ttl_seconds: int = BRIEFING_TTL_SECONDS) -> bool:
    path = _briefing_cache_path(root)
    try:
        last_sent = float(path.read_text().strip())
    except (OSError, ValueError):
        return True
    return time.time() - last_sent >= ttl_seconds


def mark_briefing_sent(root: str | Path | None) -> None:
    path = _briefing_cache_path(root)
    try:
        _ensure_private_dir(path.parent)
        path.write_text(str(time.time()))
    except OSError:
        pass


# ── JSON parsing ─────────────────────────────────────────────────────────────

def extract_json_fragment(text: str) -> str | None:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass
    lines = text.splitlines()
    for index, line in enumerate(lines):
        candidate = "\n".join(lines[index:]).strip()
        if not candidate:
            continue
        if candidate[0] not in {"{", "["}:
            continue
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue
    return None


def parse_json_output(text: str) -> dict | list | None:
    fragment = extract_json_fragment(text)
    if not fragment:
        return None
    try:
        return json.loads(fragment)
    except json.JSONDecodeError:
        return None


def run_ix_json(
    argv: list[str], cwd: str | Path | None = None, timeout: float = 10
) -> dict | list | None:
    result = run_command(argv, cwd=cwd, timeout=timeout)
    if not result or result.returncode != 0:
        return None
    return parse_json_output(result.stdout)


def fetch_briefing(cwd: str | Path | None, timeout: float) -> str | None:
    """`ix briefing` output, "" when it printed nothing, None when it failed."""
    result = run_command(BRIEFING_ARGV, cwd=cwd, timeout=timeout)
    if not result or result.returncode != 0:
        return None
    return result.stdout or ""


# ── Session briefing ─────────────────────────────────────────────────────────
#
# A briefing is worth injecting only if one of its sections (goals, plans,
# decisions, bugs, changes) has something in it. The check reads the text form,
# and when it cannot tell, it injects: a line it does not recognise as a
# section heading or a "none" placeholder counts as content.

_BRIEFING_SECTION = r"(?:goals?|plans?|decisions?|bugs?|(?:recent\s+)?changes?)"
_BRIEFING_NONE = r"(?:\(?\s*(?:none|nothing|n/a|empty|-|—)\s*\)?|0)"
_BRIEFING_EMPTY_LINE_RES = (
    # A placeholder on its own line: "(none)", "- none", "_none_", "—".
    re.compile(rf"^[-*•_\s]*{_BRIEFING_NONE}[_.\s]*$", re.IGNORECASE),
    # "No recent changes.", "No decisions recorded"
    re.compile(rf"^no\b.*\b{_BRIEFING_SECTION}\b[^:]*$", re.IGNORECASE),
)
# An unindented, unbulleted heading: "Goals", "## Open bugs: 0", "Plans (2)",
# "Active plans: none", or the title, "Ix briefing (revision 7)".
_BRIEFING_HEADING_RE = re.compile(
    r"^#*\s*(?:"
    rf"(?:(?:open|active|recent|pending|current|known|latest|new)\s+)?{_BRIEFING_SECTION}"
    rf"\s*(?:\(\d+\))?\s*(?::\s*(?:{_BRIEFING_NONE})?)?"
    r"|(?:ix\s+|session\s+)*briefing\b[^:]{0,60}:?"
    r")\s*$",
    re.IGNORECASE,
)


def _briefing_line_is_empty(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if any(regex.match(stripped) for regex in _BRIEFING_EMPTY_LINE_RES):
        return True
    return line[:1] not in (" ", "\t", "-", "*", "•") and bool(_BRIEFING_HEADING_RE.match(stripped))


def format_briefing(text: str | None) -> str | None:
    """The briefing to inject, capped at BRIEFING_MAX_CHARS; None if it is empty."""
    if not text or all(_briefing_line_is_empty(line) for line in text.splitlines()):
        return None
    text = text.strip()
    if len(text) <= BRIEFING_MAX_CHARS:
        return text
    cut = text.rfind("\n", 0, BRIEFING_MAX_CHARS + 1)
    body = text[: cut if cut > 0 else BRIEFING_MAX_CHARS].rstrip()
    return f"{body}\n[ix] Briefing truncated; run `ix briefing` for the rest."


# ── Graph lookups ────────────────────────────────────────────────────────────
#
# A graph lookup (`locate`, `overview`, `impact`, ...) that could not resolve
# its target still answers on stdout (Ix #853): exit 2 with the candidates when
# the target is ambiguous, 3 with suggestions when it is not found, 4 when the
# workspace is not mapped. Before #853 all of these exited 1, so on exit 1 the
# record's slug decides. Anything else non-zero is a real error.

LOOKUP_OK = "ok"
LOOKUP_AMBIGUOUS = "ambiguous"
LOOKUP_NOT_FOUND = "not_found"
LOOKUP_NOT_MAPPED = "not_mapped"
LOOKUP_ERROR = "error"

_LOOKUP_EXIT_OUTCOMES = {2: LOOKUP_AMBIGUOUS, 3: LOOKUP_NOT_FOUND, 4: LOOKUP_NOT_MAPPED}
_LOOKUP_SLUG_OUTCOMES = {
    "ambiguous_target": LOOKUP_AMBIGUOUS,
    "unresolved_target": LOOKUP_NOT_FOUND,
    "workspace_not_mapped": LOOKUP_NOT_MAPPED,
}
# The not-mapped line is shown at most once per workspace in this window.
NOT_MAPPED_TTL_SECONDS = 1800
NOT_MAPPED_LINE = (
    "this workspace is not mapped in Ix yet, so graph lookups are off;"
    " ask the user before running `ix map` at the project root"
)
_MAX_LISTED = 5


def run_ix_lookup(
    argv: list[str], cwd: str | Path | None = None, timeout: float = 10
) -> tuple[str, dict | list | None]:
    """Run a graph lookup and say how ix answered: ``(outcome, payload)``.

    Exit 0 is ``LOOKUP_OK`` with whatever ``run_ix_json`` would have returned.
    A timeout, a real error or stdout that is not a JSON object is
    ``(LOOKUP_ERROR, None)``, which callers treat as they always have.
    """
    result = run_command(argv, cwd=cwd, timeout=timeout)
    if result is None:
        return LOOKUP_ERROR, None
    payload = parse_json_output(result.stdout)
    if result.returncode == 0:
        return (LOOKUP_OK, payload) if payload is not None else (LOOKUP_ERROR, None)
    if not isinstance(payload, dict):
        return LOOKUP_ERROR, None
    outcome = _LOOKUP_EXIT_OUTCOMES.get(result.returncode)
    if outcome is None and result.returncode == 1:
        # `locate` names an ambiguity under `code`; everything else under `error`.
        slug = payload.get("error") or payload.get("code")
        outcome = _LOOKUP_SLUG_OUTCOMES.get(slug) if isinstance(slug, str) else None
    if outcome is None:
        return LOOKUP_ERROR, None
    return outcome, payload


def _not_mapped_stamp_path(root: str | Path | None) -> Path:
    return CACHE_DIR / "not-mapped" / f"{_root_key(root)}.stamp"


def not_mapped_line(root: str | Path | None) -> str:
    """NOT_MAPPED_LINE, or "" if it was shown for this workspace in the window.

    The search and read hooks share the stamp, so an unmapped workspace hears
    about it once rather than on every grep and cat.
    """
    path = _not_mapped_stamp_path(root)
    try:
        if time.time() - path.stat().st_mtime < NOT_MAPPED_TTL_SECONDS:
            return ""
    except OSError:
        pass
    try:
        _ensure_private_dir(path.parent)
        path.write_text(str(time.time()))
    except OSError as exc:
        log(f"[ix] not-mapped stamp failed (non-fatal): {exc}")
    return NOT_MAPPED_LINE


def _entity_label(item: object) -> str:
    """`name (kind, path:line)` for a candidate or suggestion; "" if unusable."""
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict) or not item.get("name"):
        return ""
    where = str(item.get("path") or "")
    line = item.get("line") or item.get("startLine")
    if where and isinstance(line, int):
        where += f":{line}"
    details = [part for part in (str(item.get("kind") or ""), where) if part]
    return str(item["name"]) + (f" ({', '.join(details)})" if details else "")


def _numbered_candidates(payload: dict | list | None) -> list[tuple[int, dict, str]]:
    """``(pick, candidate, label)`` for each usable candidate, in ix's order."""
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        return []
    numbered = []
    for position, candidate in enumerate(payload["candidates"], start=1):
        label = _entity_label(candidate) if isinstance(candidate, dict) else ""
        if not label:
            continue
        pick = candidate.get("pick")
        numbered.append((pick if isinstance(pick, int) else position, candidate, label))
    return numbered


def summarize_ambiguous(payload: dict | list | None, command: str) -> str:
    """The candidates of an ambiguous lookup and how to retry ``command``."""
    numbered = _numbered_candidates(payload)
    if not numbered:
        return ""
    listed = "; ".join(f"[{pick}] {label}" for pick, _, label in numbered[:_MAX_LISTED])
    if len(numbered) > _MAX_LISTED:
        listed += f" (+{len(numbered) - _MAX_LISTED} more)"
    return f"ambiguous: {listed}; retry with {command} --pick <n>, or --path <file>"


def summarize_unresolved(payload: dict | list | None, target: str) -> str:
    """Not-found line with ix's suggestions; "" when there are none to show."""
    if not isinstance(payload, dict) or not isinstance(payload.get("suggestions"), list):
        return ""
    labels = [label for label in map(_entity_label, payload["suggestions"]) if label]
    if not labels:
        return ""
    return f"no symbol '{target}'; did you mean: " + "; ".join(labels[:_MAX_LISTED])


def _summarize_read_ambiguity(
    payload: dict | list | None, filename: str, file_path: str, root: str | Path | None
) -> str:
    """Point an ambiguous bare filename at the file actually read.

    The hook knows which file was read, so it names that file's candidate
    rather than listing every file with the same name.
    """
    base = Path(root or os.getcwd()).resolve()
    read_path = Path(file_path)
    absolute = (read_path if read_path.is_absolute() else base / read_path).resolve()
    try:
        rel = absolute.relative_to(base).as_posix()
    except ValueError:
        rel = str(absolute)
    target = shlex.quote(filename)
    for pick, candidate, label in _numbered_candidates(payload):
        where = Path(str(candidate.get("path") or ""))
        if where.parts and (where if where.is_absolute() else base / where).resolve() == absolute:
            return (
                f"several graph entries are named {filename}; this file is [{pick}] {label}:"
                f" ix overview {target} --pick {pick}, or --path {shlex.quote(rel)}"
            )
    return (
        f"several graph entries are named {filename}:"
        f" ix overview {target} --path {shlex.quote(rel)}"
    )


# ── Pattern detection ────────────────────────────────────────────────────────

def hint_enabled(env_name: str) -> bool:
    """False when ``env_name`` is set to 0, off, false or no."""
    return os.environ.get(env_name, "").strip().lower() not in _HINT_OFF_VALUES


def looks_like_identifier(pattern: str) -> bool:
    return len(pattern) >= MIN_PATTERN_CHARS and IDENTIFIER_RE.fullmatch(pattern) is not None


def _class_switch_ratio(run: str) -> float:
    classes = ["d" if c.isdigit() else "u" if c.isupper() else "l" for c in run]
    switches = sum(1 for a, b in zip(classes, classes[1:]) if a != b)
    return switches / (len(run) - 1)


def looks_like_secret(pattern: str) -> bool:
    """True when ``pattern`` contains something shaped like a token or key."""
    if _SECRET_PREFIX_RE.search(pattern):
        return True
    for run in _HEX_RUN_RE.findall(pattern):
        if any(c.isdigit() for c in run) and any(c.isalpha() for c in run):
            return True
    for run in _ALNUM_RUN_RE.findall(pattern):
        if (
            any(c.isdigit() for c in run)
            and any(c.isupper() for c in run)
            and any(c.islower() for c in run)
            and _class_switch_ratio(run) >= _TOKEN_SWITCH_RATIO
        ):
            return True
    return False


def extract_search_pattern(command: str) -> str | None:
    if not command or any(op in command for op in SHELL_OPERATORS):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    if tokens[0] == "git" and len(tokens) > 1 and tokens[1] == "grep":
        tokens = tokens[1:]
    if tokens[0] not in SEARCH_COMMANDS:
        return None
    for index, token in enumerate(tokens[1:], start=1):
        if token in {"-e", "--regexp"} and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith("--regexp="):
            return token.split("=", 1)[1]
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in SEARCH_VALUE_OPTIONS:
            skip_next = True
            continue
        if any(token.startswith(p) for p in ("--glob=", "--max-count=", "--type=")):
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def extract_read_path(command: str) -> str | None:
    if not command or any(op in command for op in SHELL_OPERATORS):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0] not in READ_COMMANDS:
        return None
    candidates = [t for t in tokens[1:] if not t.startswith("-")]
    if not candidates:
        return None
    if tokens[0] == "awk" and len(candidates) >= 2:
        return candidates[-1]
    if tokens[0] == "sed" and len(candidates) >= 2:
        return candidates[-1]
    return candidates[-1]


def skip_read_path(file_path: str) -> bool:
    lowered = file_path.lower()
    if lowered.endswith(READ_SKIP_SUFFIXES):
        return True
    if any(seg in lowered for seg in READ_SKIP_SEGMENTS):
        return True
    if Path(lowered).name in READ_SKIP_BASENAMES:
        return True
    return False


# ── Result summarizers ───────────────────────────────────────────────────────

def summarize_locate_results(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    resolved = payload.get("resolvedTarget")
    if isinstance(resolved, dict) and resolved.get("name"):
        kind = str(resolved.get("kind") or "")
        path = Path(str(resolved.get("path") or "")).name
        suffix = ""
        if kind and path:
            suffix = f" ({kind}, {path})"
        elif kind:
            suffix = f" ({kind})"
        elif path:
            suffix = f" ({path})"
        return f"symbol: {resolved['name']}{suffix}"
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        return ""
    names: list[str] = []
    for c in candidates[:3]:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        label = c["name"]
        kind = str(c.get("kind") or "")
        if kind:
            label += f" ({kind})"
        names.append(label)
    return "candidates: " + ", ".join(names) if names else ""


def summarize_overview(payload: dict | list | None) -> str:
    if not isinstance(payload, dict):
        return ""
    key_items = payload.get("keyItems", [])
    names = [
        str(item.get("name"))
        for item in key_items[:5]
        if isinstance(item, dict) and item.get("name")
    ]
    children = payload.get("childrenByKind", {})
    parts = []
    if isinstance(children, dict):
        for kind, count in children.items():
            parts.append(f"{count} {kind}")
    if not names:
        return ""
    summary = "key: " + ", ".join(names)
    if parts:
        summary += " (" + ", ".join(parts) + ")"
    return summary


# ── Hint lookup ──────────────────────────────────────────────────────────────

def _hint_lookup(
    argv: list[str], cwd: str | Path | None, deadline: Deadline | None = None
) -> tuple[str, dict | list | None]:
    """The one ix call a shell hint makes, read as ``run_ix_lookup`` reads it.

    Not run when the deadline leaves no time for it. A call that runs out its
    whole timeout pauses the shell hints in this workspace for
    HEALTH_TTL_SECONDS, so a hung backend costs one wait per window rather
    than one per command. Only the hints pause: the shared health answer
    SessionStart and BeforeAgent read is left alone.
    """
    timeout = _call_timeout(HINT_LOOKUP_SECONDS, deadline)
    if timeout is None:
        return LOOKUP_ERROR, None
    started = time.monotonic()
    answer = run_ix_lookup(argv, cwd=cwd, timeout=timeout)
    if answer == (LOOKUP_ERROR, None) and time.monotonic() - started >= timeout:
        _start_hint_backoff(cwd)
    return answer


# ── Message builders ─────────────────────────────────────────────────────────

def build_search_message(
    pattern: str, cwd: str | Path | None, deadline: Deadline | None = None
) -> str | None:
    """Where the grepped symbol is defined, from one ``ix locate``.

    Only for a plain identifier that does not look like a token; anything else
    starts no ix process. The grep's own matches are not repeated.
    """
    if not looks_like_identifier(pattern) or looks_like_secret(pattern):
        return None
    # `ix locate` has no --limit: it returns one resolved target (or candidates).
    outcome, payload = _hint_lookup(["ix", "locate", pattern, "--format", "json"], cwd, deadline)
    callers = ""
    if outcome == LOOKUP_AMBIGUOUS:
        locate_part = summarize_ambiguous(payload, f"ix locate '{pattern}'")
    elif outcome == LOOKUP_NOT_FOUND:
        locate_part = summarize_unresolved(payload, pattern)
    elif outcome == LOOKUP_NOT_MAPPED:
        locate_part = not_mapped_line(cwd)
    elif outcome == LOOKUP_OK:
        locate_part = summarize_locate_results(payload)
        resolved = payload.get("resolvedTarget") if isinstance(payload, dict) else None
        if locate_part and isinstance(resolved, dict):
            callers = f"callers: ix callers {shlex.quote(str(resolved.get('name') or pattern))}"
    else:
        locate_part = ""
    if not locate_part:
        return None
    pieces = [f"[ix] shell grep intercepted for '{pattern}'", locate_part]
    if callers:
        pieces.append(callers)
    return " | ".join(pieces)


def build_read_message(
    file_path: str, cwd: str | Path | None, deadline: Deadline | None = None
) -> str | None:
    """The read file's key items from one ``ix overview``."""
    if not file_path or skip_read_path(file_path):
        return None
    filename = Path(file_path).name
    if not filename:
        return None
    outcome, payload = _hint_lookup(["ix", "overview", filename, "--format", "json"], cwd, deadline)
    # A file the graph does not know (exit 3) is ordinary for a read, so it
    # stays silent; ambiguity and an unmapped workspace are worth a line.
    if outcome == LOOKUP_OK:
        entity_part = summarize_overview(payload)
        if not entity_part:
            return None
        return f"[ix] {filename} | {entity_part} | Use ix read <symbol> to get just a symbol's source"
    if outcome == LOOKUP_AMBIGUOUS:
        lookup_part = _summarize_read_ambiguity(payload, filename, file_path, cwd)
    elif outcome == LOOKUP_NOT_MAPPED:
        lookup_part = not_mapped_line(cwd)
    else:
        return None
    return f"[ix] {filename} | {lookup_part}" if lookup_part else None


# ── Guarded automatic map ────────────────────────────────────────────────────

def event_project_dir(event: dict) -> str | None:
    """The user's project directory for this hook event.

    Gemini sends it as ``cwd`` in the payload and as ``$GEMINI_PROJECT_DIR``.
    Deliberately no ``os.getcwd()`` fallback: the hook process's own cwd is not
    a statement about which project the user is in.
    """
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd
    env_dir = os.environ.get("GEMINI_PROJECT_DIR", "")
    return env_dir or None


def project_git_root(
    project_dir: str | Path | None, deadline: Deadline | None = None
) -> Path | None:
    """`git rev-parse --show-toplevel` for the project, or None to skip mapping.

    None when there is no project dir, it is not inside a git repository, or the
    repository root is $HOME (a dotfiles repo would otherwise map the whole home
    directory).
    """
    if not project_dir:
        return None
    timeout = _call_timeout(3, deadline)
    if timeout is None:
        return None
    result = run_command(
        ["git", "-C", str(project_dir), "rev-parse", "--show-toplevel"], timeout=timeout
    )
    if not result or result.returncode != 0:
        return None
    top = result.stdout.strip()
    if not top:
        return None
    root = Path(top).resolve()
    if root == Path.home().resolve():
        return None
    return root


def _map_stamp_path(root: Path) -> Path:
    return CACHE_DIR / "map" / f"{_root_key(root)}.stamp"


def _map_debounced(root: Path) -> bool:
    try:
        window = float(os.environ.get("IX_MAP_DEBOUNCE_SECONDS", MAP_DEBOUNCE_SECONDS))
    except ValueError:
        window = MAP_DEBOUNCE_SECONDS
    try:
        last = _map_stamp_path(root).stat().st_mtime
    except OSError:
        return False
    return time.time() - last < window


def _mark_map_requested(root: Path) -> None:
    path = _map_stamp_path(root)
    _ensure_private_dir(path.parent)
    path.write_text(str(time.time()))


def workspace_mapped(root: Path, deadline: Deadline | None = None) -> bool:
    """True only when Ix reports this root's graph as complete.

    Any failure, timeout or non-JSON answer reads as "not mapped": an automatic
    map must never be the thing that creates a workspace.
    """
    timeout = _call_timeout(3, deadline)
    if timeout is None:
        return False
    payload = run_ix_json(
        ["ix", "status", "--format", "json", "--root", str(root)], cwd=root, timeout=timeout
    )
    return isinstance(payload, dict) and payload.get("graphCompleted") is True


# Windows process creation flags (subprocess only defines them on Windows).
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def detached_popen_kwargs(windows: bool) -> dict[str, object]:
    """Popen options that detach a child from the hook's session or console.

    POSIX: a new session, so the terminal's signals and the hook's process
    group do not reach it. Windows ignores ``start_new_session``; there the
    child gets its own process group, so Ctrl+C/Ctrl+Break in Gemini's console
    is not delivered to it, and its own hidden console, so it does not share
    Gemini's console. A hidden console rather than DETACHED_PROCESS, because
    under a detached cmd.exe the console-mode node would open a visible window.
    """
    if windows:
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


def request_guarded_map(
    project_dir: str | Path | None, deadline: Deadline | None = None
) -> subprocess.Popen | None:
    """Start a detached `ix map <root> --silent` if, and only if, it is safe.

    Runs only when the project is a git repo whose root is not $HOME, the root
    is already mapped, and no automatic map was requested for that root inside
    the debounce window. The map itself is detached, so it never runs inside a
    hook timeout. Returns the child (tests wait on it) or None when skipped.

    The debounce stamp is written before `ix status` is asked, so an unmapped
    root or an unreachable backend costs one status call per window, not one
    per edit.
    """
    if not ix_available():
        return None
    root = project_git_root(project_dir, deadline)
    if root is None:
        return None
    if _map_debounced(root):
        return None
    try:
        _mark_map_requested(root)
    except OSError as exc:
        log(f"[ix] map debounce stamp failed (non-fatal): {exc}")
        return None
    if not workspace_mapped(root, deadline):
        return None
    env = dict(os.environ)
    # Ix skips an automatic map against a remote backend when this is set.
    env["IX_AUTO_MAP"] = "1"
    argv: list[str] | str = ["ix", "map", str(root), "--silent"]
    executable = None
    windows = os.name == "nt"
    try:
        if windows:
            # The resolved launcher, as in run_command; POSIX keeps the bare argv.
            argv, executable, env = windows_launch(argv, env)  # type: ignore[assignment]
        return subprocess.Popen(
            argv,
            executable=executable,
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **detached_popen_kwargs(windows),
        )
    except Exception as exc:
        log(f"[ix] guarded ix map failed to start (non-fatal): {exc}")
        return None
