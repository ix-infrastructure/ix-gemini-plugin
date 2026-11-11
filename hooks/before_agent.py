#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""BeforeAgent hook — inject Ix Pro session briefing once per 10 minutes."""
from __future__ import annotations

from common import (
    HOOK_BUDGET_SECONDS,
    Deadline,
    briefing_due,
    emit_model_context,
    fetch_briefing,
    find_workspace_root,
    format_briefing,
    ix_healthy,
    ix_pro_briefing,
    mark_briefing_sent,
    read_event,
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
    # The Pro check runs `ix briefing` itself unless its answer is cached; when
    # it does, its output is this turn's briefing.
    pro, briefing = ix_pro_briefing(workspace_root, deadline)
    if not pro:
        return
    if briefing is None:
        timeout = deadline.timeout(8)
        if timeout is None:
            return
        briefing = fetch_briefing(workspace_root, timeout)
        if briefing is None:
            return

    # ix answered, so the window starts even when the briefing is empty:
    # otherwise every prompt would start the CLI again to learn the same thing.
    mark_briefing_sent(workspace_root)
    briefing = format_briefing(briefing)
    if not briefing:
        return
    # Gemini appends this to the user's prompt for this turn (core/client.ts).
    emit_model_context("BeforeAgent", f"[ix] Session briefing:\n{briefing}")


if __name__ == "__main__":
    main()
