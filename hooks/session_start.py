#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""SessionStart hook — inject Ix operating guidance at session start."""
from __future__ import annotations

from common import (
    HOOK_BUDGET_SECONDS,
    Deadline,
    emit_model_context,
    find_workspace_root,
    ix_healthy,
    read_event,
)


def main() -> None:
    deadline = Deadline(HOOK_BUDGET_SECONDS["SessionStart"])
    event = read_event()
    workspace_root = find_workspace_root(event.get("cwd"))
    if not ix_healthy(workspace_root, deadline):
        return

    lines = [
        "Ix Memory is available in this workspace.",
        "Prefer the ix-memory cognitive skills before ad hoc shell search or broad file reads:",
        "- `ix-understand [target]` for system mental models",
        "- `ix-investigate <symbol>` for deep dives",
        "- `ix-impact <target>` before non-trivial edits",
        "- `ix-plan <targets...>` for multi-file work",
        "- `ix-debug <symptom>` for root-cause analysis",
        "- `ix-architecture [scope]` for design health",
        "- `ix-docs <target>` for narrative-first documentation",
        "",
        "Behavioral rules:",
        "- Graph before code.",
        "- Read at symbol level only with `ix read <symbol>`.",
        "- Stop early once the question is answered.",
        "- Label graph-backed facts separately from inferences.",
    ]

    # Interactive Gemini adds this to history as the first turn; headless
    # Gemini prepends it to the prompt (AppContainer.tsx, gemini.tsx).
    emit_model_context("SessionStart", "\n".join(lines))


if __name__ == "__main__":
    main()
