#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""BeforeAgent hook — inject Ix Pro session briefing once per 10 minutes."""
from __future__ import annotations

from common import (
    HOOK_BUDGET_SECONDS,
    Deadline,
    briefing_due,
    emit_model_context,
    find_workspace_root,
    ix_healthy,
    ix_pro_available,
    mark_briefing_sent,
    read_event,
    run_ix_text,
)


def main() -> None:
    # Gemini waits on this hook before the turn starts, so every ix call below
    # shares one budget (status, the Pro probe and the briefing could
    # otherwise take 8s each against a 15s hook timeout).
    deadline = Deadline(HOOK_BUDGET_SECONDS["BeforeAgent"])
    event = read_event()
    workspace_root = find_workspace_root(event.get("cwd"))
    if not briefing_due(workspace_root):
        return
    if not ix_healthy(workspace_root, deadline):
        return
    if not ix_pro_available(workspace_root, deadline):
        return

    timeout = deadline.timeout(8)
    if timeout is None:
        return
    briefing = run_ix_text(
        ["ix", "briefing", "--format", "json"], cwd=workspace_root, timeout=timeout
    )
    if not briefing:
        return

    mark_briefing_sent(workspace_root)
    # Gemini appends this to the user's prompt for this turn (core/client.ts).
    emit_model_context("BeforeAgent", f"[ix] Session briefing:\n{briefing}")


if __name__ == "__main__":
    main()
