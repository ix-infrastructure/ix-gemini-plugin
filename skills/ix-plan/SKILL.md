---
name: ix-plan
description: Generate a risk-ordered implementation plan for a set of targets. Assesses blast radius per target, finds data flows between them, and produces a safe change sequence.
---

## Goal

Answer: in what order should these changes be made, what will break, and what needs testing?

If the Ix runtime is unavailable, `ix_status` will report this; fall back to manual assessment.

## Preferred path — unified query

For most cases:

```
ix_query({ mode: "plan", targets: [$ARGUMENTS] })
```

Use the returned `preview_markdown` as the primary plan. Supplement below for high-risk targets.

## Phase 1 — Scope (always)

If `$ARGUMENTS` contains symbol names, proceed directly.
If `$ARGUMENTS` is a description, first call in parallel:
- `ix_text({ pattern: $ARGUMENTS, limit: 10 })`
- `ix_locate({ symbol: $ARGUMENTS })`

Identify the 1-4 most relevant symbols.

## Phase 2 — Impact per target (parallel)

For each target, call simultaneously:
- `ix_impact({ target: <target> })`
- `ix_callers({ symbol: <target> })`

Rank targets by risk level: critical > high > medium > low.

## Phase 3 — Data flow (only if 2+ targets)

Call: `ix_trace({ symbol: <highest-risk-target>, to: <second-target> })`

## Phase 4 — Shared dependents (only if high/critical targets exist)

Call: `ix_depends({ symbol: <highest-risk-target>, depth: 2 })`

## Output

```text
# Change Plan

## Targets & Risk

| Target | Risk | Dependents | Key Callers |
|--------|------|------------|-------------|
| <A>    | high | 12         | X, Y, Z     |
| <B>    | low  | 2          | P           |

## Change Order

Edit in this sequence to minimize breakage:
1. [target] — [reason]
2. ...

## Data Flow
[A -> trace path -> B — or "targets are independent"]

## Shared Risk
[Symbols affected by changes to multiple targets]

## Test Checkpoints
After [target A]: verify [specific callers]
After [target B]: verify [specific callers]

## Red Flags
- [any critical/high target needing extra care]
- [any cross-subsystem boundary being crossed]
```

Do not read source code unless a target cannot be resolved by `ix_locate`.
