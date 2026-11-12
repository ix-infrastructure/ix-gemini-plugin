# ix-gemini-plugin

[![Sponsor](https://img.shields.io/badge/sponsor-%E2%9D%A4-db61a2)](https://github.com/sponsors/ix-infrastructure)

A Gemini CLI extension that turns Gemini into a graph-reasoning engineering agent using [Ix Memory](https://github.com/ix-infrastructure/Ix) as its structured memory backend.

Gemini + Ix = reasoning engine + persistent code knowledge graph. Skills are cognitive abstractions, not CLI wrappers.

## Requirements

- [Ix Memory](https://github.com/ix-infrastructure/Ix) CLI >= 0.11.0 installed and running (`ix status` returns ok)
- `python3` in PATH for hook scripts (on Windows, see below)
- `ripgrep` (`rg`) is recommended

### Windows

- Install Ix with its Windows installer, which puts `ix.cmd` on PATH. The hooks look `ix` up through PATH and PATHEXT, never in the current directory; if it is not there they treat Ix as not installed. For the installer's layout they start the CLI's script with the `node` on PATH directly, as its launcher would, with no `cmd.exe` in between. If either launcher does anything else before node runs (for example sets `NODE_OPTIONS`), they run it through `cmd.exe` instead, as written. For any other `ix.cmd` they go through `cmd.exe` with quoting that keeps every argument intact, and with `NoDefaultCurrentDirectoryInExePath=1` so the launcher's `node` is not taken from your workspace. An argument containing a line break is refused rather than passed.
- Python 3 must be on PATH. The python.org installer provides `python` and `py`, not `python3`.
  - `install.ps1` tries `python3`, `python` and `py -3` in that order and writes the first one that runs Python 3 into the installed `hooks.json`.
  - With `gemini extensions install`, `hooks.json` is used as shipped, so `python3` must exist (for example the Microsoft Store Python, or a `python3` of your own on PATH), or run `install.ps1` instead. `hooks.json` has one command per hook, shared by every platform, so the shipped file cannot name `python3` on macOS and Linux and `py` on Windows. The way around that would be to start every hook through one program that exists on every platform, such as a small `node` script (Gemini CLI itself runs on Node.js) that finds Python and runs the hook. The extension does not do that yet, so for now use one of the two options above.

Ix Pro is optional. If present, the `BeforeAgent` hook injects the Ix session briefing once per 10 minutes.

## Skills

High-level cognitive skills:

| Skill | What it does | Key rule |
|-------|--------------|----------|
| `ix-help <task or question>` | Route to the right Ix skill or direct `ix` command | Route only; do not execute |
| `ix-understand [target]` | Build a mental model of a system or the whole repo | Graph only; no code reads |
| `ix-investigate <symbol>` | Deep dive: what it is, how it connects, execution path | Graph first; one symbol read max |
| `ix-impact <target>` | Change risk: blast radius, affected systems, test targets | Depth scales with risk |
| `ix-plan <targets...>` | Risk-ordered implementation plan for a set of changes | Parallel impact; finds shared dependents |
| `ix-debug <symptom>` | Root cause analysis from symptom to candidates | Minimal source reads at suspects only |
| `ix-architecture [scope]` | Design health: coupling, smells, hotspots | Graph only; never reads source |
| `ix-docs <target> [--full]` | Generate narrative-first documentation with selective reference | Default is onboarding-focused |

## MCP Server

The extension registers one MCP server, `ix-memory`, which is the Ix CLI's own: `ix mcp --tools=all`, started in the workspace directory (`cwd: ${workspacePath}`) so it answers for the project you opened Gemini in. Nothing is built or bundled; tool names are the CLI's (`ix_context`, `ix_search`, `ix_impact`, `ix_neighbors`, `ix_read`, ...). `--tools` needs Ix >= 0.11.0.

`ix mcp install --host gemini` registers a server with the same name, `ix-memory`, in `~/.gemini/settings.json`. You do not need it with this extension. If both exist, Gemini merges them into one server and the settings entry's `command`/`args` win, so remove it (`gemini mcp remove --scope user ix-memory`) or keep its args at `mcp --tools=all`.

## Agent Playbooks

Reusable playbook docs in [`agents/`](./agents):

| Playbook | Purpose |
|----------|---------|
| `ix-explorer` | General-purpose graph exploration |
| `ix-system-explorer` | Full architectural model of a codebase or region |
| `ix-bug-investigator` | Root cause analysis from symptom to candidates |
| `ix-safe-refactor-planner` | Blast radius plus safe change sequencing |
| `ix-architecture-auditor` | Structural health report with ranked improvements |

## Automatic Hooks

| Trigger | Gemini hook | Effect |
|---------|-------------|--------|
| Before agent plans | `BeforeAgent` | Injects `ix briefing` (text, capped) once per 10 min if Ix Pro is available; an empty briefing injects nothing |
| After shell search/read | `AfterTool` (`run_shell_command`) | Appends `ix text` + `ix locate` (for `grep`/`rg`) or `ix overview` + `ix impact` (for `cat`/`head`/...) context to the tool result the model reads |
| After a file edit | `AfterTool` (`run_shell_command`, `write_file`, `replace`) | After a file-modifying shell command or a native edit, refreshes an already-mapped git repo in the background (`ix map <root> --silent`, at most once per 5 min per repo) |
| Session ends | `SessionEnd` | Same guarded background refresh of the project's git root |

## How It Works

- `gemini-extension.json` holds the extension's metadata and its one MCP server (see above). Gemini does not read hooks or skills from it.
- `hooks/hooks.json` maps each hook event above to a Python script in `hooks/`. `AfterTool` is matched by tool name; Gemini's shell tool is `run_shell_command`. Each script reads the event as JSON on stdin and runs `ix` within a time budget below its `timeout` in `hooks.json`, because Gemini drops the output of a hook that runs over. The shared helpers are in `hooks/common.py`.
- Context reaches the model only as `hookSpecificOutput.additionalContext`. `systemMessage` is shown to the user only, so there is no `BeforeTool` hook: it could reach the model only by blocking the tool.
- Hooks write diagnostics to stderr, never to stdout and never to a log file. `AfterTool` and `SessionEnd` catch any exception, log it and still exit 0.
- Gemini discovers skills from `skills/<name>/SKILL.md`. `agents/` holds playbook documents, and `GEMINI.md` is the context file Gemini loads into every session. The installers copy all three, with the manifest and hooks, into the extension directory.

The tests (see Local Validation) do not start Gemini CLI. With a real `gemini` and `ix`, check by hand that `gemini extensions install .` succeeds, the `ix-memory` tools appear and answer for the opened project, each hook fires without error (and without crashing Gemini when `ix` is missing), and the skills appear in `/skills list`.

## Install

### Quick install

```bash
gemini extensions install /path/to/ix-gemini-plugin
```

Or from GitHub:

```bash
gemini extensions install https://github.com/ix-infrastructure/ix-gemini-plugin
```

### Manual install

```bash
git clone git@github.com:ix-infrastructure/ix-gemini-plugin.git
cd ix-gemini-plugin
./install.sh
```

The installer copies the extension to `~/.gemini/extensions/ix-memory/`.

On Windows PowerShell:

```powershell
.\install.ps1
```

### Repo-local install

```bash
./install.sh --repo /path/to/project
```

This copies the extension to `/path/to/project/.gemini/extensions/ix-memory/`.

PowerShell equivalent:

```powershell
.\install.ps1 -Repo C:\path\to\project
```

## Local Validation

Run the hook and manifest tests with:

```bash
./test-local.sh
```

The tests run every hook against a strict fake `ix`, never a real backend, and skip live Gemini CLI validation when `gemini` is not installed.

## Always-on context

Every session carries, before the user asks anything:

- [`GEMINI.md`](./GEMINI.md), the extension's context file: the `ix-memory` tool table and four rules. CI fails if it is over 2,500 bytes.
- The name and description of each skill and agent.
- The MCP tool catalog of `ix mcp --tools=all`, which the Ix CLI provides and this repo does not measure.

CI also fails if the first two together are over 5,000 bytes. They came to 3,988 bytes (2,056 for `GEMINI.md`) when these ceilings were set; `python3 hooks/tests/test_context_size.py --report` prints the current sizes. There is no SessionStart message.

## Contributing

Notes for editing the extension (layout, hooks, checks) are in [`CONTRIBUTING.md`](./CONTRIBUTING.md), which Gemini does not load.
