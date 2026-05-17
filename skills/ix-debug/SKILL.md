---
name: ix-debug
description: Root cause analysis — trace execution path to a failure, narrow candidates, read minimal source only at suspected failure points.
---

## Goal

Answer: where in the execution path is this likely failing, and why? Stop once you have 1-3 root cause candidates with supporting evidence.

If the Ix runtime is unavailable, `ix_status` will report this; fall back to grep + file reads.

## Preferred path — unified query

For most cases:

```
ix_query({ mode: "debug", targets: [$ARGUMENTS], query: $ARGUMENTS })
```

Use the returned `preview_markdown` as the primary analysis. Supplement below if candidates need confirmation.

## Phase 1 — Locate the entry point (always)

Call: `ix_locate({ symbol: $ARGUMENTS })`

If `$ARGUMENTS` is a symptom description, also call:
- `ix_text({ pattern: $ARGUMENTS, limit: 10 })`

## Phase 2 — Explain (always)

Call: `ix_explain({ symbol: <entry-point> })`

Classify: boundary (unexpected input), orchestrator (wrong sequencing), utility (wrong assumptions by caller).
Stop if: the explanation makes the failure source obvious.

## Phase 3 — Trace the execution path

Call: `ix_trace({ symbol: <entry-point> })`

Look for: state validation, cross-subsystem calls, high-callee-count functions.
Narrow to 1-3 most suspicious nodes.

## Phase 4 — Callers (if failure might come from upstream)

Call: `ix_callers({ symbol: <entry-point> })`

## Phase 5 — Targeted code read (at most 2 calls)

For each root cause candidate (max 2), read the source file at the relevant line range.

Hard limit: 2 source reads maximum.

## Output

```text
## Debug: [entry point]

**Execution path:**
[entry-point] -> [step] -> [step] -> [suspected failure point]

**Root cause candidates:**
1. [function/file] — [reason: what assumption might be wrong]
2. [function/file] — [reason]

**Evidence:**
- [what graph data supports each candidate]
- [what code read revealed, if any]

**Confidence:** [high / medium / low] — [why]

**Next steps:**
- Add logging at [specific point] to confirm
- Check [specific edge case] in [function]
```
