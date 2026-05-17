---
name: ix-impact
description: Change risk analysis — blast radius, affected systems, and what to test. Depth scales with risk level; low-risk targets stop early.
---

## Goal

Answer: what breaks if this changes, and is it safe to proceed? Stop as early as the risk level allows.

If the Ix runtime is unavailable, `ix_status` will report this; estimate impact from available context.

## Preferred path — unified query

For most cases:

```
ix_query({ mode: "impact", targets: [$ARGUMENTS] })
```

Use the returned `preview_markdown` as the primary answer. Supplement below if risk classification needs detail.

## Phase 1 — Risk score (always)

Call: `ix_impact({ target: $ARGUMENTS })`

Immediately classify on `risk_level` and `dependents`:

| Risk level | Action |
|---|---|
| `low` + < 3 dependents | STOP — safe to proceed. Report and suggest verification targets. |
| `medium` OR 3-10 dependents | Go to Phase 2 |
| `high` or `critical` OR > 10 dependents | Go to Phase 2 + 3 |

## Phase 2 — Callers and dependents (medium/high/critical)

Call in parallel:
- `ix_callers({ symbol: $ARGUMENTS })`
- `ix_depends({ symbol: $ARGUMENTS, depth: 2 })`

Stop here if risk is `medium`.

## Phase 3 — Import chain and subsystem spread (high/critical only)

Call: `ix_imported_by({ symbol: $ARGUMENTS })`

Cross-reference callers + dependents + importers to identify subsystems in the blast radius.

## Output

```text
## Impact: [target]

**Risk level:** <critical | high | medium | low>
**Verdict:** <SAFE TO PROCEED | REVIEW CALLERS FIRST | NEEDS CHANGE PLAN>

**Blast radius:**
- Direct dependents: N
- Transitive (depth 2): M
- Subsystems affected: [list — only if phase 3 ran]

**Key callers:** [top 5, with subsystem label]
**At-risk behaviors:** [from ix_impact at_risk_behavior field]

**Recommended action:**
- low: proceed, verify [specific callers]
- medium: test [caller list] after change
- high/critical: run `ix-plan $ARGUMENTS` before editing
```

Never read source code in this skill.
