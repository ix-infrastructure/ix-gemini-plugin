---
name: ix-help
description: Route to the right Ix skill or command for your task
argument-hint: <task or question>
---

## Role: strict router

This skill routes the user to the best Ix entry point and then stops.

You must not:
- perform the routed task
- gather evidence or run `ix` commands
- chain into the recommended skill
- add follow-on analysis after the routing block

If `$ARGUMENTS` is empty, return this menu:
- `ix-understand <target>` — architectural mental model
- `ix-investigate <symbol>` — deep dive on one symbol or feature
- `ix-impact <target>` — blast radius before editing
- `ix-plan <targets...>` — risk-ordered multi-file change plan
- `ix-debug <symptom>` — root-cause analysis for bugs
- `ix-architecture [scope]` — design health and structural smells
- `ix-docs <target>` — onboarding or reference documentation
- Raw `ix` commands — direct lookups like `ix locate <symbol> --format json`

If `$ARGUMENTS` is non-empty, classify the request and recommend exactly one best starting point:
- Architecture, onboarding, or "how does X work" -> `ix-understand <target>`
- Symbol deep dive, feature internals, or "what does X do" -> `ix-investigate <target>`
- Pre-edit risk or blast radius -> `ix-impact <target>`
- Multi-file change, refactor, or migration -> `ix-plan <targets or change description>`
- Bug, failure, regression, or unexpected behavior -> `ix-debug <symptom>`
- Design quality, coupling, complexity, or smells -> `ix-architecture <scope>`
- Documentation or onboarding/reference docs -> `ix-docs <target>`
- Simple lookup requests:
  - exact definition -> `ix locate <symbol> --format json`
  - fuzzy search -> `ix text "<term>" --limit 10 --format json`
  - incoming callers -> `ix callers <symbol> --limit 15 --format json`
  - outgoing callees -> `ix callees <symbol> --limit 15 --format json`
  - path inventory -> `ix inventory --kind file --path <path> --format json`

Return exactly this block and nothing else:

```text
Best start: <one sentence describing the recommended entry point>
Run: <exact copy-paste skill invocation or ix command>
Why: <one short sentence>
```

If the request is ambiguous, make the safest routing choice and say which placeholder to replace.
