# ix-gemini-plugin

This repo is the Gemini CLI extension for [Ix Memory](https://github.com/ix-infrastructure/Ix). When working in this repo, use `ix` commands to navigate it just like any other codebase.

---

## Cognitive Model

Gemini + Ix operates as a three-layer system:

```text
Ix Graph      = structured memory (code relationships, history, decisions)
Gemini        = reasoning engine (infers, synthesizes, decides)
Skills/Agents = cognition layer (task abstractions over the graph)
```

This means Gemini is not a command wrapper. Gemini uses Ix as memory to reason, then synthesizes answers. The graph provides facts; Gemini provides understanding.

---

## MCP Tools (primary interface)

The `ix-memory` MCP server is the Ix CLI's own: the extension launches `ix mcp --tools=all` in the workspace directory (Ix CLI >= 0.11.0). Prefer these tools over shell `ix` commands — they return the same graph data without a process per call.

| Tool | When to use |
|---|---|
| `ix_context({ target })` / `ix_context({ issue })` | First call on a task, issue, or unfamiliar symbol/file — ranked evidence and next calls |
| `ix_subsystems()` / `ix_rank({ by, kind, top })` | System map, most central components |
| `ix_overview({ target })` | One-call summary of a file, symbol or subsystem |
| `ix_search({ term })` / `ix_locate({ symbol })` | Find a definition by (part of) its name |
| `ix_explain({ symbol })` | Role and main users of a symbol |
| `ix_neighbors({ symbol, relation })` | Callers, callees, imports, importers (`ix_callers`, `ix_callees`, `ix_imports`, `ix_imported_by` are the single-relation forms) |
| `ix_trace({ symbol, to })` / `ix_depends({ symbol, depth })` | Call chains and dependent trees |
| `ix_impact({ target })` | **Before editing** — blast radius and risk level |
| `ix_read({ symbol })` | One symbol's source, without reading the whole file |
| `ix_smells()` / `ix_inventory({ kind, path })` / `ix_stats()` | Architecture smells, entity listings, graph size |
| `ix_health()` | Only when a result suggests the graph is missing or stale |
| `ix_map()` | After edits, when later answers must see the change (slow; whole workspace) |

With Ix Pro installed the server also offers `ix_briefing`, `ix_decisions` and `ix_decide` (records an architecture decision — it is not a pre-edit gate).

### Before editing

Call `ix_impact({ target: "<file or symbol>" })` on what you are about to change. If the risk is `high` or `critical`, tell the user what is at risk before proceeding.

### After editing

The hooks refresh an already-mapped project in the background after file-modifying shell commands and at session end. When an answer later in this session depends on the edit, call `ix_map()` once (no arguments — `ix map` maps a directory, never a single file).

---

## Behavioral Rules

### Always
- Start with `ix_context` (or `ix_subsystems` for a whole-system question) before reading source code
- Call `ix_impact` before a non-trivial edit
- Stop early once you can answer the question
- Label evidence and distinguish graph-backed facts from inferences

### Never
- Assume behavior without graph or code evidence
- Output raw JSON — summarize tool results
- Call `ix_map` for exploration — it re-ingests; read tools need no refresh

---

## Reasoning Strategy

When answering a question about a codebase:

```text
1. Orient       -> ix_context({ target }) or ix_subsystems()
2. Investigate  -> ix_explain / ix_neighbors / ix_trace on the resolved symbol
3. Impact       -> ix_impact({ target }) if an edit is planned
4. Act          -> make the change
5. Refresh      -> ix_map() only if later answers must see the change
6. Synthesize   -> answer, labelling graph-backed facts
```

Skip steps if earlier steps answer the question. Most read-only questions stop at step 2.

---

## Token Budget Rules

| Operation | Rule |
|---|---|
| Text search | `ix_text({ limit: 20 })` cap |
| Symbol rank | `ix_rank({ top: 10 })` cap |
| Callers/callees | results capped at 15 per call |
| Dependency tree | `ix_depends({ depth: 2 })` max unless the user asks for deeper |
| Code reads | Symbol-level only, max 2 per task |
| Traces | One `ix_trace` per investigation |

---

## Skill Reference

| Skill | Purpose | When to use |
|---|---|---|
| `ix-help <task or question>` | Route to the best Ix skill or direct `ix` command | When the right entry point is unclear |
| `ix-understand [target]` | Mental model of a system | Onboarding, architecture questions, "how does X work?" |
| `ix-investigate <symbol>` | Deep dive into a component | Before modifying, explaining, or debugging something |
| `ix-impact <target>` | Change risk analysis | Before any non-trivial edit |
| `ix-plan <targets...>` | Risk-ordered change plan | Multi-file changes, refactors |
| `ix-debug <symptom>` | Root cause analysis | Bug investigation, unexpected behavior |
| `ix-architecture [scope]` | Design health analysis | Code review, architecture discussions |
| `ix-docs <target> [--full] [--style narrative\|reference\|hybrid] [--split] [--single-doc] [--out <path>]` | Write narrative-first docs with a selective reference layer | Onboarding docs, handoffs, deep reference |

---

## Agent Playbooks

The `agents/` directory carries reusable playbook docs:
- `ix-explorer`
- `ix-system-explorer`
- `ix-bug-investigator`
- `ix-safe-refactor-planner`
- `ix-architecture-auditor`

---

## Hook Notes

The Gemini CLI extension uses these hook events:
- `SessionStart` injects Ix operating guidance
- `BeforeAgent` injects the Ix Pro briefing once per 10 minutes
- `BeforeTool` for `run_shell_command` front-runs `grep`/`rg` and read-style shell commands with Ix context
- `AfterTool` for `run_shell_command` requests a guarded background `ix map <git root> --silent` after file-modifying commands (only for an already-mapped repo, at most once per 5 minutes per repo)
- `SessionEnd` requests the same guarded refresh

---

## Repo Structure

```text
gemini-extension.json            - extension manifest; MCP server = `ix mcp --tools=all`
.gemini/
  settings.json                  - same MCP server, for developing in this repo
hooks/
  common.py                      - shared helpers
  session_start.py               - startup guidance
  before_agent.py                - Ix Pro briefing injection
  before_tool.py                 - shell search/read interception
  after_tool.py                  - background graph refresh on writes
  session_end.py                 - session end graph refresh
skills/
  ix-help/SKILL.md
  ix-understand/SKILL.md
  ix-investigate/SKILL.md
  ix-impact/SKILL.md
  ix-plan/SKILL.md
  ix-debug/SKILL.md
  ix-architecture/SKILL.md
  ix-docs/SKILL.md
agents/
  ix-explorer.md
  ix-system-explorer.md
  ix-bug-investigator.md
  ix-safe-refactor-planner.md
  ix-architecture-auditor.md
install.sh
install.ps1
```

---

## ix CLI Quick Reference

| Task | Command |
|---|---|
| Architecture overview | `ix subsystems --format llm` |
| Structural summary | `ix overview <name> --format llm` |
| Understand a symbol | `ix explain <symbol> --format llm` |
| Find definition | `ix locate <symbol> --format llm` |
| Read one symbol's source | `ix read <symbol> --format llm` |
| Trace call chain | `ix trace <symbol> --format llm` |
| Who calls it | `ix callers <symbol> --format llm` |
| Members of a class | `ix contains <symbol> --format llm` |
| Upstream dependents | `ix depends <symbol> --depth 2 --format llm` |
| Blast radius | `ix impact <target> --format llm` |
| List entities in path | `ix inventory --kind function --path <dir> --format llm` |
| Text search | `ix text <pattern> --limit 20 --format llm` |
| Code smells | `ix smells --format llm` |
| Rank key components | `ix rank --by dependents --kind class --top 10 --format llm` |
| Refresh graph | `ix map` |

Pass `--format llm` for token-optimized output the model reads directly; `--format json` remains available for programmatic parsing.

`ix rank` requires `--by` and `--kind`.
