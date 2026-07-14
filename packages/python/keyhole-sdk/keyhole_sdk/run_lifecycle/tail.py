"""Run tail — SDK-CLIENT-17 §5.4/§12.

Follow the best available observation surface: repeated status
retrieval under current boundary posture.

Rules:
  - Render chronology clearly
  - Label observation method honestly
  - Never present polling snapshots as a true stream
  - Degrade cleanly if live-follow is unavailable
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, List, Optional

from keyhole_sdk.run_lifecycle.models import (
    RunStatus,
    RunTailEntry,
    RunTailResult,
)
from keyhole_sdk.run_lifecycle.status import fetch_run_status


DEFAULT_TAIL_INTERVAL = 2.0
DEFAULT_MAX_ENTRIES = 100


def tail_run(
    *,
    transport: Any,  # GovernedTransport
    run_id: str,
    repo_name: str = "",
    poll_interval: float = DEFAULT_TAIL_INTERVAL,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    on_entry: Optional[Any] = None,  # callable(RunTailEntry) -> bool; return True to stop
) -> RunTailResult:
    """Tail a run using the best available observation surface.

    Under current boundary posture, this uses repeated status polling.
    This is labeled honestly as ``status_poll`` — not a true stream.

    §12: The client must not present polling snapshots as a true stream.
    """
    entries: List[RunTailEntry] = []
    terminal_status: Optional[RunStatus] = None
    last_status = ""
    interrupted = False
    polls = 0

    while polls < max_entries:
        polls += 1
        status_result = fetch_run_status(
            transport=transport,
            run_id=run_id,
            repo_name=repo_name,
        )

        now = datetime.now(timezone.utc).isoformat()

        if not status_result.success:
            entries.append(RunTailEntry(
                timestamp=now,
                status="error",
                message=f"Observation failed: {status_result.reason}",
                source="status_poll",
                raw={"error_class": status_result.error_class},
            ))
            return RunTailResult(
                success=False,
                run_id=run_id,
                observation_method="status_poll",
                entries=entries,
                error_class=status_result.error_class or "observation_failed",
                reason=f"Tail observation failed: {status_result.reason}",
                repair_guidance=status_result.repair_guidance or [
                    f"Retry: keyhole runs tail {run_id}",
                    "Observation failure does not mean execution failed.",
                ],
            )

        current_status = status_result.status.value

        # Only record new entries when status changes or on first poll
        if current_status != last_status or not entries:
            entry = RunTailEntry(
                timestamp=now,
                status=current_status,
                message=status_result.summary or f"Status: {current_status}",
                source="status_poll",
                raw=status_result.response_data,
            )
            entries.append(entry)
            last_status = current_status

            if on_entry is not None:
                try:
                    if on_entry(entry):
                        interrupted = True
                        break
                except KeyboardInterrupt:
                    interrupted = True
                    break

        if status_result.status.is_terminal:
            terminal_status = status_result.status
            break

        time.sleep(poll_interval)

    return RunTailResult(
        success=True,
        run_id=run_id,
        observation_method="status_poll",
        entries=entries,
        terminal_status=terminal_status,
        interrupted=interrupted,
    )
