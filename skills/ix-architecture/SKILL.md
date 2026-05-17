---
name: ix-architecture
description: Analyze system design — structure, coupling, code smells, and high-risk hotspots. Purely graph-based, no code reads.
---

## Goal

Answer: how healthy is this system's design, where are the weak boundaries, and what should be improved? Never reads source code.

If the Ix runtime is unavailable, `ix_status` will report this; this skill cannot proceed without the graph.

## Preferred path — unified query

For most cases:

```
ix_query({ mode: "architecture", targets: [$ARGUMENTS] })
```

Use the returned `preview_markdown` as the primary analysis. Supplement below for deeper investigation.

## Phase 1 — Structure (always)

Call in parallel:
- `ix_subsystems()` — region hierarchy, cohesion scores, external coupling, crosscut scores

If `$ARGUMENTS` is provided, also call:
- `ix_inventory({ kind: "file", path: $ARGUMENTS })` — file composition of the target

Extract: region hierarchy, cohesion scores, external coupling, crosscut scores, confidence.

## Phase 2 — Smells

Call: `ix_smells()`

If `$ARGUMENTS` is scoped: `ix_smells({ path: $ARGUMENTS })`

Classify each finding: `orphan` / `god-module` / `weak-component`.

## Phase 3 — Hotspots (only if smells are found or coupling is high)

Call in parallel:
- `ix_rank({ by: "dependents", kind: "class", top: 10 })`
- `ix_rank({ by: "dependents", kind: "function", top: 10 })`

Correlate: are the most-depended-on entities also in poorly-bounded subsystems?

## Output

```text
## Architecture Analysis

### System Structure
[Region hierarchy with file counts. Flag: low-confidence boundaries, high-coupling regions, cross-cutting modules.]

### Health Scores
| Region | Cohesion | Ext. Coupling | Boundary Ratio | Flag |
|--------|----------|---------------|----------------|------|
| [name] | [0-1]    | [0-1]         | [ratio]        | [warning if bad] |

### Code Smells
**High severity:** ...
**Medium severity:** ...

### Hotspots
[Top components where structural debt + centrality combine]

### Improvement Areas
1. [specific issue] — [concrete suggestion]

### What's healthy
[Briefly note well-structured areas]
```

Every number must come directly from tool output.
