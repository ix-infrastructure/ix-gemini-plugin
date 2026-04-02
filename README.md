# ix-gemini-plugin

A Gemini CLI extension that turns Gemini into a graph-reasoning engineering agent using [Ix Memory](https://github.com/ix-infrastructure/IX-Memory) as its structured memory backend.

Gemini + Ix = reasoning engine + persistent code knowledge graph. Skills are cognitive abstractions, not CLI wrappers.

## Requirements

- [Ix Memory](https://github.com/ix-infrastructure/IX-Memory) installed and running (`ix status` returns ok)
- `python3` in PATH for hook scripts
- `ripgrep` (`rg`) is recommended

Ix Pro is optional. If present, the `BeforeAgent` hook injects the Ix session briefing once per 10 minutes.

## Skills

High-level cognitive skills:

| Skill | What it does | Key rule |
|-------|--------------|----------|
| `ix-understand [target]` | Build a mental model of a system or the whole repo | Graph only; no code reads |
| `ix-investigate <symbol>` | Deep dive: what it is, how it connects, execution path | Graph first; one symbol read max |
| `ix-impact <target>` | Change risk: blast radius, affected systems, test targets | Depth scales with risk |
| `ix-plan <targets...>` | Risk-ordered implementation plan for a set of changes | Parallel impact; finds shared dependents |
| `ix-debug <symptom>` | Root cause analysis from symptom to candidates | Minimal source reads at suspects only |
| `ix-architecture [scope]` | Design health: coupling, smells, hotspots | Graph only; never reads source |
| `ix-docs <target> [--full]` | Generate narrative-first documentation with selective reference | Default is onboarding-focused |

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
| Session starts | `SessionStart` | Injects Ix operating guidance and graph-first rules |
| Before agent plans | `BeforeAgent` | Injects `ix briefing` once per 10 min if Ix Pro is available |
| Before shell tool | `BeforeTool` | Front-runs `grep`/`rg`/`cat`/`head` with `ix text` + `ix locate` context |
| After shell tool | `AfterTool` | Triggers background `ix map` after file-modifying shell commands |
| Session ends | `SessionEnd` | Runs `ix map` asynchronously to refresh the graph |

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

### Repo-local install

```bash
./install.sh --repo /path/to/project
```

This copies the extension to `/path/to/project/.gemini/extensions/ix-memory/`.

## Repo Guidance

The repo-level operating guide lives in [`GEMINI.md`](./GEMINI.md). It carries the graph-first reasoning model, skill reference, and token-budget rules.
