---
name: ix-investigate
description: Deep dive into a symbol, feature, or bug. Graph-first, minimal code reads, early stopping when sufficient evidence found.
---

## Goal

Answer: what is this, how does it connect, and what's the execution path? Stop as soon as those three questions can be answered accurately.

If the Ix runtime is unavailable, `ix_status` will report this; fall back to file reads as needed.

## Preferred path — unified query

For most cases, call `ix_query` once:

```
ix_query({ mode: "investigate", targets: [$ARGUMENTS] })
```

Use the returned `preview_markdown` as the primary answer. Supplement with specific tools below if needed.

## Phase 1 — Locate (always)

Call: `ix_locate({ symbol: $ARGUMENTS })`

If no match: try `ix_text({ pattern: $ARGUMENTS, limit: 10 })`

Do not proceed until the entity is unambiguous.

## Phase 2 — Explain (always)

Call: `ix_explain({ symbol: <resolved-symbol> })`

Extract: role, importance, caller count, callee count, confidence score.
Stop if: explain gave clear role, purpose, and connection summary → skip to Output.

## Phase 3 — Connections (run only if caller/callee detail needed)

- If "who uses this" matters: `ix_callers({ symbol: <symbol> })`
- If "what does this do internally" matters: `ix_callees({ symbol: <symbol> })`

Stop if: you now know who uses it and what it depends on.

## Phase 4 — Trace (run only if execution flow is unclear)

Call: `ix_trace({ symbol: <symbol> })`

One trace only. Pick the most representative direction.

## Phase 5 — Code read (last resort only)

Only if the above steps leave a specific implementation question unanswered: read the source file at the line range from `ix_locate`.

Hard limit: One source read maximum.

## Output

```text
## [Symbol] — Investigation

**What it is:** [kind, file, subsystem — from graph]
**Role:** [orchestrator / boundary / helper / utility / etc.]

**Execution flow:**
[downstream: what it calls -> what those call, 2 levels max]
[upstream: who calls it, top 5]

**Key connections:**
- Depends on: [top 3 callees]
- Used by: [top 3 callers with their subsystem]

**Evidence quality:** [strong / partial / uncertain] — [one-line reason]

**Next step:**
- [most useful follow-up based on findings]
```
