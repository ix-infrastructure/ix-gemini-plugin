# Copyright 2026 Ix Infrastructure Inc.

"""A strict fake `ix` for the hook tests.

Tests put it first on PATH so no test can reach a real ix (a real `ix map`
writes to the shared backend). It is strict where the real CLI is strict, so a
hook that builds an argv the real CLI rejects fails here too:

- `ix map <path>` exits 1 with "Map path is not a directory" when <path> is not
  a directory (Ix >= 0.10.6).
- Unknown options exit 1 with "error: unknown option '<opt>'" for the commands
  the hooks call (`locate --limit`, `smells --path`, ...).

Every call is appended as one JSON line ({argv, cwd, IX_AUTO_MAP}) to
$FAKE_IX_LOG. `ix status --format json` reports graphCompleted from
$FAKE_IX_GRAPH_COMPLETED ("1" = true); $FAKE_IX_STATUS=fail|garbage makes it
exit 1 or print non-JSON. $FAKE_IX_SLEEP=<seconds> makes every call (after it
is logged) sleep first, to stand in for a slow or hung backend.

$FAKE_IX_LOOKUP makes the graph lookups (`locate`, `overview`, `impact`) answer
the way Ix #853 does, on stdout: `ambiguous` exits 2 with candidates,
`not_found` exits 3 with suggestions (none when $FAKE_IX_SUGGESTIONS=0),
`not_mapped` exits 4 (and also covers `inventory`), `error` exits 1 with a
non-lookup error record and `garbage` exits 2 with non-JSON. With
$FAKE_IX_LEGACY_EXIT=1 every one of them exits 1, as ix did before #853.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

# Options per command: name -> takes a value. Mirrors `ix <cmd> --help` on
# v0.11.1 and on the merged #732/#733/#734/#739 tree, which agree on these.
_COMMON = {"--format": True, "--pretty": False, "--quiet": False, "--fields": True}
_OPTIONS: dict[str, dict[str, bool]] = {
    "status": {**_COMMON, "--root": True},
    "map": {
        **_COMMON, "--level": True, "--min-confidence": True, "--max-items": True,
        "--all-items": False, "--sort": True, "--graph": False, "--list": False,
        "--full": False, "--verbose": False, "--silent": False,
    },
    "locate": {**_COMMON, "--kind": True, "--path": True, "--pick": True},
    "text": {**_COMMON, "--limit": True, "--path": True, "--language": True, "--root": True},
    "inventory": {**_COMMON, "--kind": True, "--path": True, "--limit": True},
    "overview": {**_COMMON, "--kind": True, "--path": True, "--pick": True},
    "impact": {
        **_COMMON, "--kind": True, "--path": True, "--pick": True,
        "--depth": True, "--limit": True,
    },
    "smells": {**_COMMON},
}


_LOOKUP_COMMANDS = {"locate", "overview", "impact"}


def _lookup_answer(command: str, target: str) -> None:
    """Answer a graph lookup per $FAKE_IX_LOOKUP; return only when it is unset."""
    mode = os.environ.get("FAKE_IX_LOOKUP", "")
    if not mode or not (command in _LOOKUP_COMMANDS or (command == "inventory" and mode == "not_mapped")):
        return
    legacy = os.environ.get("FAKE_IX_LEGACY_EXIT") == "1"
    if mode == "ambiguous":
        # `locate` reports the ambiguity under `code`, the others under `error`.
        key = "code" if command == "locate" else "error"
        body, code = {
            key: "ambiguous_target",
            "message": f"'{target}' matches 2 entities",
            "candidates": [
                {"name": target, "kind": "function", "path": f"src/{target}", "line": 12},
                {"name": target, "kind": "method", "path": f"lib/{target}", "line": 40},
            ],
        }, 2
    elif mode == "not_found":
        suggestions: list = []
        if os.environ.get("FAKE_IX_SUGGESTIONS") != "0":
            suggestions = [
                {"name": f"{target}_v2", "kind": "function", "path": "src/fake.py", "line": 3},
                f"{target}s",
            ]
        body, code = {
            "error": "unresolved_target",
            "message": f"No entity named '{target}'",
            "suggestions": suggestions,
        }, 3
    elif mode == "not_mapped":
        body, code = {
            "error": "workspace_not_mapped",
            "message": "This workspace has not been mapped. Run `ix map` first.",
        }, 4
    elif mode == "error":
        body, code = {"error": "backend_unreachable", "message": "Ix backend unreachable"}, 1
    elif mode == "garbage":
        print("not json at all")
        sys.exit(1 if legacy else 2)
    else:
        return
    print(json.dumps(body))
    sys.exit(1 if legacy else code)


def _fail(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.exit(1)


def _parse(command: str, args: list[str]) -> tuple[dict[str, str | bool], list[str]]:
    known = _OPTIONS[command]
    opts: dict[str, str | bool] = {}
    positionals: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name not in known:
                _fail(f"error: unknown option '{name}'")
            if known[name] and not eq:
                index += 1
                if index >= len(args):
                    _fail(f"error: option '{name}' argument missing")
                value = args[index]
            opts[name] = value if known[name] else True
        else:
            positionals.append(arg)
        index += 1
    return opts, positionals


def main(argv: list[str]) -> None:
    log_path = os.environ.get("FAKE_IX_LOG")
    if log_path:
        with open(log_path, "a") as fh:
            fh.write(json.dumps({
                "argv": argv,
                "cwd": os.getcwd(),
                "IX_AUTO_MAP": os.environ.get("IX_AUTO_MAP"),
            }) + "\n")

    delay = os.environ.get("FAKE_IX_SLEEP")
    if delay:
        time.sleep(float(delay))

    if not argv or "--help" in argv or "-h" in argv:
        return
    command, args = argv[0], argv[1:]
    if command not in _OPTIONS:
        print("{}")
        return
    opts, positionals = _parse(command, args)
    _lookup_answer(command, positionals[0] if positionals else "fake")

    if command == "status":
        mode = os.environ.get("FAKE_IX_STATUS", "")
        if mode == "fail":
            _fail("Ix backend unreachable")
        if opts.get("--format") == "json":
            if mode == "garbage":
                print("not json at all")
                return
            completed = os.environ.get("FAKE_IX_GRAPH_COMPLETED") == "1"
            print(json.dumps({"backend": "ok", "graphCompleted": completed}))
        else:
            print("Ix Memory  ok")
        return

    if command == "map":
        if len(positionals) > 1:
            _fail("error: too many arguments for 'map'")
        target = Path(positionals[0]) if positionals else Path.cwd()
        if not target.is_dir():
            _fail(f"Map path is not a directory: {target}")
        print("mapped 0 files")
        return

    if command == "locate":
        if len(positionals) != 1:
            _fail("error: missing required argument 'symbol'")
        print(json.dumps({
            "resolvedTarget": {"name": positionals[0], "kind": "function", "path": "src/fake.py"},
        }))
        return

    if command == "text":
        print(json.dumps({"results": [{"path": "src/fake.py", "line": 1}]}))
        return

    if command == "overview":
        target = positionals[0] if positionals else "fake"
        print(json.dumps({
            "keyItems": [{"name": Path(target).stem}], "childrenByKind": {"function": 1},
        }))
        return

    print("{}")


def install(bin_dir: Path) -> Path:
    """Write an executable `ix` into bin_dir that runs this fake."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "ix"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
        "import fake_ix\n"
        "fake_ix.main(sys.argv[1:])\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def isolated_env(tmp: Path) -> dict[str, str]:
    """Environment for running hooks: fake ix first on PATH, private HOME/state."""
    bin_dir = tmp / "bin"
    install(bin_dir)
    home = tmp / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("FAKE_IX_", "IX_", "GEMINI_"))
    }
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "HOME": str(home),
        "XDG_STATE_HOME": str(tmp / "state"),
        "FAKE_IX_LOG": str(tmp / "ix-calls.jsonl"),
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return env


def read_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    main(sys.argv[1:])
