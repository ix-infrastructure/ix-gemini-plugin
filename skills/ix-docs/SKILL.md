---
name: ix-docs
description: Generate narrative-first, importance-weighted documentation for a repo, system, or subsystem with a selective reference layer. Use --full for deeper module/class/method coverage.
---

## Goal

Produce documentation that helps a new engineer understand the system quickly.

If the Ix runtime is unavailable, `ix_status` will report this; this skill cannot proceed without the graph.

## Core model

Every `ix-docs` run produces two layers:
1. Narrative layer (always first) — human-readable, onboarding-focused
2. Reference layer (always present, but selective) — compressed summaries of important components

Mode: default = narrative-heavy; `--full` = deeper coverage.
Style: `--style narrative` (default) / `--style reference` / `--style hybrid`.

## Non-negotiable rules

1. Graph first — start with `ix_subsystems`, `ix_overview`, `ix_rank`, `ix_explain`
2. Importance-weighted — expand detail by centrality, risk, coupling
3. Selective low-level detail — never exhaustive
4. No raw dumps — use `preview_markdown` from tool responses
5. No redundancy — group repeated patterns
6. Code reads are rare — default: max 2; full: max 5

## Preferred path — unified query

For most cases:

```
ix_query({ mode: "docs", targets: [$ARGUMENTS], depth: "medium" })
```

Use the returned `preview_markdown` as the base documentation. Supplement with phases below for `--full` coverage.

## Phases

### Phase 1 — Scope

Call in parallel:
- `ix_stats()` — graph size, file count
- `ix_subsystems()` — top-level architecture

### Phase 2 — Architecture

Call in parallel:
- `ix_overview({ target: $ARGUMENTS })`
- `ix_rank({ by: "dependents", kind: "class", top: 10 })`

### Phase 3 — Behavior

Call `ix_explain({ symbol: <component> })` for the most important components (top 3-5 by rank).

### Phase 4 — Relationships

For key components:
- `ix_callers({ symbol: <component> })`
- `ix_callees({ symbol: <component> })`
- `ix_depends({ symbol: <component>, depth: 2 })`

### Phase 5 — Risk

Call: `ix_impact({ target: $ARGUMENTS })`

### Phase 6 — Health

Call: `ix_smells()`

### Phase 7 — Optional reads (max 2-5 source reads for `--full`)

## Output structure

```markdown
# [Target] — Documentation

## Part 1 — Narrative
1. Overview
2. Architecture
3. How It Works
4. Key Components
5. Dependencies & Relationships
6. Risk & Complexity
7. How to Work With This Repo
8. Where to Go Deeper

## Part 2 — Selective Reference
- Module Summary
- Class / Service Summary
- Method Summary (--full only, key classes only)
```
