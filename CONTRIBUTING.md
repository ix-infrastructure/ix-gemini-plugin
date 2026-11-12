# Contributing to ix-gemini-plugin

This repo is the Gemini CLI extension for [Ix Memory](https://github.com/ix-infrastructure/Ix). When working in it, use `ix` commands to navigate it like any other codebase.

This file is for people editing the extension. Gemini does not load it. `GEMINI.md` is the extension's context file, which Gemini loads into every user session, so keep it to what a user's session needs and within the ceilings in README ("Always-on context"); `hooks/tests/test_context_size.py` checks that.

## Layout

```text
gemini-extension.json   extension manifest; one MCP server, `ix mcp --tools=all` in the workspace
GEMINI.md               context file loaded into every session (user-facing, size-checked)
.gemini/settings.json   the same MCP server, for developing in this repo
hooks/
  hooks.json            hook events -> scripts, with their timeouts
  common.py             shared helpers: ix launch, time budgets, caches, lookups
  before_agent.py       Ix Pro briefing injection
  after_tool.py         Ix context for shell search/read; graph refresh on edits
  session_end.py        guarded graph refresh at session end
  tests/                unit tests against a strict fake `ix`
  real_ix_tests/        tests against a released `ix` (CI job)
skills/<name>/SKILL.md  the eight `ix-*` skills
agents/*.md             the five agent playbooks
install.sh, install.ps1 copy the manifest, GEMINI.md, hooks, skills and agents into a project
```

## Hooks

- `BeforeAgent` injects the Ix Pro briefing (text, capped) once per 10 minutes, and nothing when every section is empty.
- `AfterTool` for `run_shell_command` appends Ix context to the result of `grep`/`rg` and read-style shell commands. When a lookup is ambiguous it lists ix's candidates with their `--pick` numbers; when a symbol is not found it lists ix's suggestions; in an unmapped workspace it says so at most once every 30 minutes.
- `AfterTool` for `run_shell_command`, `write_file` and `replace` requests a guarded background `ix map <git root> --silent` after a file edit (only for an already-mapped repo, at most once per 5 minutes per repo).
- `SessionEnd` requests the same guarded refresh.

There is no `SessionStart` hook: it repeated what `GEMINI.md` already says and cost an `ix status` call per session. Context reaches the model only as `hookSpecificOutput.additionalContext` (BeforeAgent, AfterTool). `systemMessage` is shown to the user only, and a BeforeTool hook has no channel to the model short of blocking the tool, so there is no BeforeTool hook.

## Checks

```bash
./test-local.sh
python3 hooks/tests/test_context_size.py --report   # size of the always-on context
```

Use Conventional Commits, and put the copyright header on every new source file (CI checks it with the script in `.github/scripts/`).
