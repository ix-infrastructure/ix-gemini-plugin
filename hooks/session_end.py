#!/usr/bin/env python3
"""SessionEnd hook — refresh the Ix graph when the session ends."""
from __future__ import annotations

from common import find_workspace_root, ix_healthy, log, read_event, spawn_background_ix_map


def main() -> None:
    try:
        event = read_event()
        workspace_root = find_workspace_root(event.get("cwd"))
        if ix_healthy(workspace_root):
            spawn_background_ix_map(workspace_root)
    except Exception as exc:
        log(f"[ix] session_end hook error (non-fatal): {exc}")


if __name__ == "__main__":
    main()
