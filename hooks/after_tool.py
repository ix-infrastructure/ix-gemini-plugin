#!/usr/bin/env python3
"""AfterTool hook — trigger background ix map after file-modifying shell commands."""
from __future__ import annotations

from common import (
    emit_json,
    find_workspace_root,
    ix_healthy,
    read_event,
    spawn_background_ix_map,
)


# Shell commands that modify files and should trigger a graph refresh.
_WRITE_COMMANDS = {"mv", "cp", "rm", "touch", "tee", "install", "patch"}


def _is_write_command(command: str) -> bool:
    parts = command.strip().split()
    if not parts:
        return False
    # Direct write redirections
    if ">" in command or ">>" in command:
        return True
    base = parts[0].split("/")[-1]
    return base in _WRITE_COMMANDS


def main() -> None:
    event = read_event()
    workspace_root = find_workspace_root(event.get("cwd"))
    if not ix_healthy(workspace_root):
        return

    tool_input = event.get("tool_input", {})
    command = str(tool_input.get("command") or tool_input.get("cmd") or "")

    if command and _is_write_command(command):
        spawn_background_ix_map(workspace_root)


if __name__ == "__main__":
    main()
