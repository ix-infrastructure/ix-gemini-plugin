#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""AfterTool hook — request a guarded graph refresh after file-modifying shell commands."""
from __future__ import annotations

import re
import shlex

from common import event_project_dir, log, read_event, request_guarded_map


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


def main() -> None:
    try:
        event = read_event()
        tool_input = event.get("tool_input", {})
        if not isinstance(tool_input, dict):
            return
        command = str(tool_input.get("command") or tool_input.get("cmd") or "")
        if command and _is_write_command(command):
            request_guarded_map(event_project_dir(event))
    except Exception as exc:
        log(f"[ix] after_tool hook error (non-fatal): {exc}")


if __name__ == "__main__":
    main()
