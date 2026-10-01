#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""SessionEnd hook — request a guarded graph refresh when the session ends."""
from __future__ import annotations

from common import event_project_dir, log, read_event, request_guarded_map


def main() -> None:
    try:
        event = read_event()
        request_guarded_map(event_project_dir(event))
    except Exception as exc:
        log(f"[ix] session_end hook error (non-fatal): {exc}")


if __name__ == "__main__":
    main()
