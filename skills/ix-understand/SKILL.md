---
name: ix-understand
description: Build a mental model of a system, subsystem, or the whole repo. Graph-first, no code reads unless necessary.
---

## Goal

Build an accurate mental model of the target's structure, purpose, and key components. Stop as soon as you can answer: what does this do, what are its key parts, and where should someone explore next?

If the Ix runtime is unavailable, `ix_status` will report this; proceed with best-effort analysis.

## Preferred path — unified query

For most cases, call `ix_query` once and use the `preview_markdown` result as the primary answer:

```
ix_query({ mode: "understand", targets: [$ARGUMENTS], depth: "medium" })
```

Supplement with specific tools below if the response needs more detail.

## Phase 1 — Orient (always run)

Call in parallel:
- `ix_subsystems()` — architectural regions, file counts, cohesion
- `ix_rank({ by: "dependents", kind: "class", top: 10 })` — most central classes
- `ix_rank({ by: "callers", kind: "function", top: 10 })` — most called functions

If `$ARGUMENTS` is non-empty, also call:
- `ix_locate({ symbol: $ARGUMENTS })` — resolve the target in the graph

Extract: region names, file counts, cohesion scores; top 3-5 structurally central components.

Stop here if: `$ARGUMENTS` is empty and rank + subsystems give a clear picture.

## Phase 2 — Key components (run only if needed)

Pick the 2-4 most central or unclear components from Phase 1. Call in parallel:
- `ix_overview({ target: <component> })` for each

Do NOT call `ix_explain` yet — `ix_overview` is cheaper and sufficient for most components.

Stop here if: you can describe what each component does and how they relate.

## Phase 3 — Clarify (run only if still unclear)

For at most 2 components still unclear after Phase 2:
- `ix_explain({ symbol: <component> })`

Hard limits: No source code reads. No `ix_map`. No `ix_trace`. This skill never reads source code.

## Output

```text
# [Target] — System Overview

## What it does
[One paragraph. Purpose, primary job, who uses it.]

## Key Components
- **X** (<kind>) — [role in one line, evidence: rank position / cohesion score]
- **Y** (<kind>) — [role in one line]
[3-5 max. Omit if fully explained by parent.]

## Structure
[Subsystem breakdown: name -> file count -> cohesion score -> what it owns]

## Where to explore next
- `ix-investigate <X>` — understand the most central component
- `ix-architecture` — analyze coupling and design health
- `ix-debug <X>` — if investigating a suspected bug
```

Evidence labels: Mark every claim as `[graph]` (direct tool data) or `[inferred]` (structural reasoning). Never state facts without one of these labels.
