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
