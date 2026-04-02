# ix-gemini-plugin

This repo is the Gemini CLI extension for [Ix Memory](https://github.com/ix-infrastructure/IX-Memory). When working in this repo, use `ix` commands to navigate it just like any other codebase.

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

## Behavioral Rules

### Always
- Use Ix graph data before reading source code
- Read at symbol level only with `ix read <symbol>`, never whole files unless the whole file is the explicit subject
- Use high-level skills (`ix-investigate`, `ix-understand`) not raw command dumps
- Stop early once you can answer the question
- Label evidence and distinguish graph-backed facts from inferences

### Never
- Scan entire files unless the whole file is the question
- Call `ix depends --depth 3+` or `ix trace` without a specific question
- Assume behavior without graph or code evidence
- Output raw JSON
- Run `ix map` for exploration
- Run `ix rank` without both `--by` and `--kind`

---

## Reasoning Strategy

When answering a question about a codebase:

```text
1. Orient       -> ix subsystems or ix overview
2. Locate       -> ix locate
3. Explain      -> ix explain
4. Trace/Depend -> ix trace or ix depends only if needed
5. Read         -> ix read <symbol> only if implementation detail is still unclear
6. Synthesize   -> answer the question, cite evidence
7. Suggest      -> one useful next step
```

Skip steps if earlier steps answer the question. Most questions should stop by step 3.

---

## Token Budget Rules

| Operation | Rule |
|---|---|
| Text search | `--limit 20` cap |
| Symbol rank | `--top 10` cap, always `--exclude-path test` |
| Callers/callees | `--limit 15` cap |
| Dependency tree | `--depth 2` max unless the user asks for deeper |
| Code reads | Symbol-level only, max 2 per task |
| Traces | One trace per investigation |

---

## Skill Reference

| Skill | Purpose | When to use |
|---|---|---|
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
- `BeforeTool` for `shell` front-runs `grep`/`rg` and read-style shell commands with Ix context
- `AfterTool` for `shell` triggers background `ix map` after file-modifying commands
- `SessionEnd` runs `ix map` asynchronously

---

## Repo Structure

```text
gemini-extension.json            - extension manifest
hooks/
  common.py                      - shared helpers
  session_start.py               - startup guidance
  before_agent.py                - Ix Pro briefing injection
  before_tool.py                 - shell search/read interception
  after_tool.py                  - background graph refresh on writes
  session_end.py                 - session end graph refresh
skills/
  ix-understand.toml
  ix-investigate.toml
  ix-impact.toml
  ix-plan.toml
  ix-debug.toml
  ix-architecture.toml
  ix-docs.toml
agents/
  ix-explorer.md
  ix-system-explorer.md
  ix-bug-investigator.md
  ix-safe-refactor-planner.md
  ix-architecture-auditor.md
```

---

## ix CLI Quick Reference

| Task | Command |
|---|---|
| Architecture overview | `ix subsystems --format json` |
| Structural summary | `ix overview <name> --format json` |
| Understand a symbol | `ix explain <symbol> --format json` |
| Find definition | `ix locate <symbol> --format json` |
| Read one symbol's source | `ix read <symbol> --format json` |
| Trace call chain | `ix trace <symbol> --format json` |
| Who calls it | `ix callers <symbol> --format json` |
| Members of a class | `ix contains <symbol> --format json` |
| Upstream dependents | `ix depends <symbol> --depth 2 --format json` |
| Blast radius | `ix impact <target> --format json` |
| List entities in path | `ix inventory --kind function --path <dir> --format json` |
| Text search | `ix text <pattern> --limit 20 --format json` |
| Code smells | `ix smells --format json` |
| Rank key components | `ix rank --by dependents --kind class --top 10 --format json` |
| Refresh graph | `ix map` |

`ix rank` requires `--by` and `--kind`.
