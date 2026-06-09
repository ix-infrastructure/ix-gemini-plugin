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

The `ix-memory` MCP server exposes these tools. Always prefer MCP tools over shell commands — MCP tools call the runtime API directly, return structured evidence, and include `canonical_revision` so answers are reproducible.

| Tool | When to use |
|---|---|
| `ix_status` | Session start — check graph health before any work |
| `ix_query` (mode: `understand`) | System map, data flows, coupling summary |
| `ix_query` (mode: `investigate`) | Deep dive on a specific symbol or file |
| `ix_query` (mode: `impact`) | Blast radius before editing |
| `ix_query` (mode: `plan`) | Risk-ordered change sequencing |
| `ix_query` (mode: `debug`) | Root-cause trace from symptom |
| `ix_query` (mode: `architecture`) | Cohesion, coupling, smells, hotspots |
| `ix_query` (mode: `docs`) | Generate or look up documentation |
| `ix_query` (mode: `locate`) | Find files or symbols matching a query |
| `ix_decide` | **Before writing or editing any file** — get allow/warn/block verdict |
| `ix_ingest` | **After writing or editing any file** — keep graph current |

### Pre-edit gate (required)

Before writing to any file, call `ix_decide` with the file path and operation:

```
ix_decide({ paths: ["src/foo.ts"], operation: "edit", context: "Adding retry logic" })
```

- `allow` → proceed normally
- `warn` → proceed, but document your rationale
- `block` → do not proceed without explicit user confirmation

If the runtime is unavailable, `ix_decide` returns `allow` automatically (non-blocking).

### Post-edit ingest (required)

After writing to any file, call `ix_ingest` with all touched paths:

```
ix_ingest({ paths: ["src/foo.ts", "src/bar.ts"] })
```

At session end, call `ix_ingest({ paths: [], full_workspace: true })` for a complete graph refresh.

---

## Behavioral Rules

### Always
- Call `ix_status` at session start to check graph readiness
- Call `ix_decide` before any file write or edit
- Call `ix_ingest` after any file write or edit
- Use `ix_query` MCP tools before reading source code
- Stop early once you can answer the question
- Label evidence and distinguish graph-backed facts from inferences
- Check `canonical_revision` in tool responses — pin it when citing graph data

### Never
- Skip `ix_decide` before file writes, even for small edits
- Skip `ix_ingest` after file writes
- Assume behavior without graph or code evidence
- Output raw JSON — use `preview_markdown` from tool responses
- Run `ix map` for exploration (use `ix_ingest` instead)

---

## Reasoning Strategy

When answering a question about a codebase:

```text
1. Orient       -> ix_query(mode: "understand") or ix_query(mode: "locate")
2. Investigate  -> ix_query(mode: "investigate", targets: [symbol])
3. Impact       -> ix_query(mode: "impact", targets: [file]) if edit is planned
4. Decide       -> ix_decide(paths, operation) before any write
5. Act          -> make the change
6. Ingest       -> ix_ingest(paths) after the change
7. Synthesize   -> answer citing canonical_revision from tool responses
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
- `AfterTool` for `run_shell_command` triggers `ix_ingest` after file-modifying commands
- `SessionEnd` calls `ix_ingest({ paths: [], full_workspace: true })` for a complete graph refresh

---

## Repo Structure

```text
gemini-extension.json            - extension manifest
mcp/
  server.ts                      - MCP server entry point (stdio transport)
  lib/
    config.ts                    - runtime URL, surface ID, timeouts
    errors.ts                    - IxError class, error log
    parser.ts                    - ToolResult types (canonical_revision, preview_markdown)
    runtime-client.ts            - HTTP client for Ix Core Runtime API
  shared/
    secrets.ts                   - secret redaction
  tools/
    ix_query.ts                  - unified query (9 modes)
    ix_decide.ts                 - pre-edit policy gate
    ix_ingest.ts                 - post-edit graph ingest
    ix_status.ts                 - health and graph readiness check
.gemini/
  settings.json                  - mcpServers config (example / project override)
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
