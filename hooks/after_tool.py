#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""AfterTool hook — Ix context for shell searches and reads, graph refresh after edits.

Matched in hooks.json to `run_shell_command`, `write_file` and `replace` (the
tool names in gemini-cli's packages/core/src/tools/definitions/
base-declarations.ts).

- A shell `grep`/`rg`/`cat`/... gets Ix context appended to its result through
  `hookSpecificOutput.additionalContext`, which Gemini adds to the tool result
  the model reads (core/coreToolHookTriggers.ts). This used to be a BeforeTool
  hook printing `systemMessage`, which Gemini shows the user and never the
  model; a BeforeTool hook has no channel to the model short of blocking the
  tool (scheduler/hook-utils.ts).
- A file-modifying shell command, or a successful `write_file`/`replace`,
  requests the guarded background `ix map`.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from common import (
    HOOK_BUDGET_SECONDS,
    Deadline,
    build_read_message,
    build_search_message,
    emit_model_context,
    event_project_dir,
    extract_read_path,
    extract_search_pattern,
    find_workspace_root,
    ix_healthy,
    log,
    read_event,
    request_guarded_map,
)

SHELL_TOOL = "run_shell_command"
# Gemini's native file-editing tools; both take `file_path`.
EDIT_TOOLS = {"write_file", "replace"}


# Commands whose plain invocation modifies files.
_WRITE_COMMANDS = {
    "mv", "cp", "rm", "touch", "install", "patch", "ln", "truncate", "rsync",
}
# `git` subcommands that rewrite the working tree.
_GIT_WRITE_SUBCOMMANDS = {
    "am", "apply", "checkout", "cherry-pick", "merge", "mv", "pull", "rebase",
    "reset", "restore", "revert", "rm", "stash", "switch",
}
# Words that run the next word as the command.
_COMMAND_PREFIXES = {"sudo", "env", "nohup", "time", "command", "exec", "nice"}
_PREFIX_VALUE_OPTIONS = {
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-U"},
    "env": {"-u", "-C", "-S"},
    "nice": {"-n"},
}
_SEGMENT_SEPARATORS = {";", "&&", "||", "|", "&", "|&", ";;"}
# Output redirections. `>&` / `<&` are only a write when followed by a file,
# not a file descriptor (`2>&1`).
_REDIRECT_WRITE_OPS = {">", ">>", ">|", "&>", "&>>"}
# Targets that are not files in the project.
_NON_FILE_TARGET_PREFIXES = ("/dev/",)
# In-place edit switches, alone or clustered: `sed -i`, `sed -ni`, `sed -i.bak`,
# `perl -pi -e`. Anchored so `perl -Mstrict` or `sed -n` do not count.
_SED_INPLACE_RE = re.compile(r"^(-[nErsuz]*i|--in-place)")
_PERL_INPLACE_RE = re.compile(r"^-[pnlaw0-9]*i")


def _is_file_target(target: str) -> bool:
    return bool(target) and not target.startswith(_NON_FILE_TARGET_PREFIXES)


def _tokenize(command: str) -> list[str] | None:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return None


def _segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in _SEGMENT_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [seg for seg in segments if seg]


def _has_write_redirect(tokens: list[str]) -> bool:
    for index, token in enumerate(tokens):
        target = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token in _REDIRECT_WRITE_OPS and _is_file_target(target):
            return True
        if token == ">&" and not target.isdigit() and target != "-" and _is_file_target(target):
            return True
    return False


def _strip_prefixes(words: list[str]) -> list[str]:
    index = 0
    while index < len(words):
        word = words[index]
        name, eq, _ = word.partition("=")
        if eq and name and name.replace("_", "a").isalnum() and not name[0].isdigit():
            index += 1  # VAR=value assignment
            continue
        prefix = word.rsplit("/", 1)[-1]
        if prefix in _COMMAND_PREFIXES:
            index += 1
            # Skip the prefix's own options (`sudo -u x`, `nice -n 5`).
            takes_value = _PREFIX_VALUE_OPTIONS.get(prefix, set())
            while index < len(words) and words[index].startswith("-"):
                index += 2 if words[index] in takes_value else 1
            continue
        break
    return words[index:]


def _segment_writes(words: list[str]) -> bool:
    words = _strip_prefixes(words)
    if not words:
        return False
    base = words[0].rsplit("/", 1)[-1]
    args = words[1:]
    if base in _WRITE_COMMANDS:
        return True
    if base == "tee":
        return any(_is_file_target(a) for a in args if not a.startswith("-"))
    if base == "sed":
        return any(_SED_INPLACE_RE.match(a) for a in args)
    if base == "perl":
        return any(_PERL_INPLACE_RE.match(a) for a in args)
    if base == "dd":
        return any(a.startswith("of=") and _is_file_target(a[3:]) for a in args)
    if base == "git":
        index = 0
        while index < len(args) and args[index].startswith("-"):
            # `git -C <dir>` / `git -c <key=value>` take a separate value.
            index += 2 if args[index] in {"-C", "-c"} else 1
        return index < len(args) and args[index] in _GIT_WRITE_SUBCOMMANDS
    return False


def _is_write_command(command: str) -> bool:
    if not command or not command.strip():
        return False
    # shlex treats a newline as plain whitespace; a newline separates commands.
    tokens = _tokenize(command.replace("\n", " ; "))
    if tokens is None:
        return False
    if _has_write_redirect(tokens):
        return True
    return any(_segment_writes(seg) for seg in _segments(tokens))


def _edited_file_dir(event: dict, tool_input: dict) -> str | None:
    """Directory of the file a native edit tool wrote, for the guarded map."""
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path.strip():
        return None
    path = Path(file_path)
    if not path.is_absolute():
        base = event_project_dir(event)
        if not base:
            return None
        path = Path(base) / path
    return str(path.parent)


def _tool_failed(event: dict) -> bool:
    response = event.get("tool_response")
    return isinstance(response, dict) and bool(response.get("error"))


def _shell_context(event: dict, command: str, deadline: Deadline) -> str | None:
    pattern = extract_search_pattern(command)
    file_path = None if pattern else extract_read_path(command)
    if not pattern and not file_path:
        return None
    workspace_root = find_workspace_root(event.get("cwd"))
    if not ix_healthy(workspace_root, deadline):
        return None
    if pattern:
        return build_search_message(pattern, workspace_root, deadline)
    return build_read_message(file_path, workspace_root, deadline)


def main() -> None:
    try:
        deadline = Deadline(HOOK_BUDGET_SECONDS["AfterTool"])
        event = read_event()
        tool_input = event.get("tool_input", {})
        if not isinstance(tool_input, dict):
            return
        tool_name = event.get("tool_name")

        if tool_name in EDIT_TOOLS:
            if not _tool_failed(event):
                request_guarded_map(_edited_file_dir(event, tool_input), deadline)
            return
        if tool_name not in (None, SHELL_TOOL):
            return

        command = str(tool_input.get("command") or "")
        if not command:
            return
        if _is_write_command(command):
            request_guarded_map(event_project_dir(event), deadline)
            return
        context = _shell_context(event, command, deadline)
        if context:
            emit_model_context("AfterTool", context)
    except Exception as exc:
        log(f"[ix] after_tool hook error (non-fatal): {exc}")


if __name__ == "__main__":
    main()
