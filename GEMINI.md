# Ix Memory

Ix keeps a graph of this workspace's code: definitions, calls, imports and dependents. Ask it before you read source.

| `ix-memory` tool | Use it for |
|---|---|
| `ix_context({ target })` / `ix_context({ issue })` | First call on a task, issue, symbol or file: ranked evidence and next calls |
| `ix_subsystems()` / `ix_rank({ by, kind, top })` | Map of the system; most central components |
| `ix_overview({ target })` / `ix_explain({ symbol })` | Summary of a file, symbol or subsystem; role and main users of a symbol |
| `ix_search({ term })` / `ix_locate({ symbol })` / `ix_text` | Find a definition by name; text search |
| `ix_neighbors({ symbol, relation })` / `ix_trace({ symbol, to })` / `ix_depends({ symbol, depth })` | Callers, callees, imports; call chains; dependents |
| `ix_impact({ target })` | Before an edit: blast radius and risk |
| `ix_read({ symbol })` | One symbol's source instead of the whole file |
| `ix_smells()` / `ix_inventory({ kind, path })` | Architecture smells; entity listings |
| `ix_map()` | Only when a later answer must see your edits (slow; maps the whole workspace) |

With Ix Pro there are also `ix_briefing`, `ix_decisions` and `ix_decide` (records a decision; it is not a pre-edit check). The `ix-*` skills package these steps for common tasks; `ix-help` picks one.

Rules:
- Start with `ix_context` (or `ix_subsystems` for a whole-system question) before reading files, and read one symbol at a time with `ix_read`.
- Call `ix_impact` before a non-trivial edit; if the risk is high or critical, tell the user what is at risk first.
- Keep calls small (`ix_depends` depth 2, `ix_rank` top 10, `ix_text` limit 20) and stop once you can answer. Summarize results rather than pasting JSON, and say which facts came from the graph and which you inferred.
- Never call `ix_map` to explore. If a tool says the workspace is not mapped, ask the user before running `ix map` at the project root.

Lines starting with `[ix]` after a shell `grep`, `rg` or `cat` are graph context added by this extension.
