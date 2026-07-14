"""Run lifecycle models - SDK-CLIENT-17 section6/section10.

Classified run states, status results, and observation types.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class TerminalState(enum.Enum):
    """Terminal run states - these end observation."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    DENIED = "denied"
    CANCELLED = "cancelled"


class RunStatus(enum.Enum):
    """Classified run status families - section6."""

    ACCEPTED = "accepted"
    RUNNING = "running"
    DEFERRED = "deferred"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    DENIED = "denied"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"

    @property
    def is_terminal(self) -> bool:
        """Whether this status represents a final outcome."""
        return self in _TERMINAL_STATUSES

    @property
    def is_active(self) -> bool:
        """Whether the run is still in progress."""
        return self in (RunStatus.ACCEPTED, RunStatus.RUNNING, RunStatus.DEFERRED)


_TERMINAL_STATUSES = frozenset({
    RunStatus.SUCCESS,
    RunStatus.FAILED,
    RunStatus.REJECTED,
    RunStatus.DENIED,
    RunStatus.CANCELLED,
})

_STATUS_MAP: Dict[str, RunStatus] = {
    "accepted": RunStatus.ACCEPTED,
    "pending": RunStatus.ACCEPTED,
    "running": RunStatus.RUNNING,
    "in_progress": RunStatus.RUNNING,
    "deferred": RunStatus.DEFERRED,
    "success": RunStatus.SUCCESS,
    "succeeded": RunStatus.SUCCESS,
    "completed": RunStatus.SUCCESS,
    "ok": RunStatus.SUCCESS,
    "failed": RunStatus.FAILED,
    "error": RunStatus.FAILED,
    "rejected": RunStatus.REJECTED,
    "denied": RunStatus.DENIED,
    "cancelled": RunStatus.CANCELLED,
    "canceled": RunStatus.CANCELLED,
}


def classify_status(raw: str) -> RunStatus:
    """Map a raw server status string to a classified RunStatus."""
    return _STATUS_MAP.get(raw.lower().strip(), RunStatus.UNKNOWN)


@dataclass
class RunStatusResult:
    """Result of a run status query - section10."""

    success: bool
    run_id: str = ""
    request_id: str = ""
    correlation_id: str = ""
    status: RunStatus = RunStatus.UNKNOWN
    run_type: str = ""
    repo_name: str = ""
    shadow: bool = False
    ctxpack_digest: str = ""
    last_updated: str = ""
    summary: str = ""
    terminal_summary: str = ""
    resolved: bool = False
    server_backed: bool = False
    http_status_code: int = 0
    response_data: Dict[str, Any] = field(default_factory=dict)
    error_class: str = ""
    reason: str = ""
    repair_guidance: List[str] = field(default_factory=list)

    def render_human(self) -> str:
        """Render a human-readable status line."""
        if not self.success:
            lines = [f"FAILED: {self.reason or 'status retrieval failed'}"]
            if self.repair_guidance:
                lines.append("Repair guidance:")
                for g in self.repair_guidance:
                    lines.append(f"  - {g}")
            return "\n".join(lines)

        icon = "✔" if self.status.is_terminal else "?"
        label = self.status.value.upper()
        lines = [f"{icon} Run {self.run_id}: {label}"]
        if self.run_type:
            lines.append(f"  run_type: {self.run_type}")
        if self.repo_name:
            lines.append(f"  repo: {self.repo_name}")
        if self.shadow:
            lines.append("  mode: SHADOW")
        if self.ctxpack_digest:
            lines.append(f"  context: {self.ctxpack_digest}")
        if self.last_updated:
            lines.append(f"  last_updated: {self.last_updated}")
        if self.terminal_summary:
            lines.append(f"  result: {self.terminal_summary}")
        if self.summary:
            lines.append(f"  summary: {self.summary}")
        if not self.status.is_terminal:
            lines.append("  next:")
            lines.append(f"    keyhole runs wait {self.run_id}")
            lines.append(f"    keyhole runs tail {self.run_id}")
        return "\n".join(lines)


@dataclass
class RunWaitResult:
    """Result of waiting for terminal state - section11."""

    success: bool
    run_id: str = ""
    terminal_status: RunStatus = RunStatus.UNKNOWN
    polls: int = 0
    elapsed_seconds: float = 0.0
    final_data: Dict[str, Any] = field(default_factory=dict)
    interrupted: bool = False
    error_class: str = ""
    reason: str = ""
    repair_guidance: List[str] = field(default_factory=list)


@dataclass
class RunTailEntry:
    """A single observation entry from tailing a run - section12."""

    timestamp: str = ""
    status: str = ""
    message: str = ""
    source: str = ""  # "status_poll" or "event_query"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunTailResult:
    """Result of tailing a run - section12."""

    success: bool
    run_id: str = ""
    observation_method: str = "status_poll"
    entries: List[RunTailEntry] = field(default_factory=list)
    terminal_status: Optional[RunStatus] = None
    interrupted: bool = False
    error_class: str = ""
    reason: str = ""
    repair_guidance: List[str] = field(default_factory=list)


@dataclass
class RunResumeResult:
    """Result of resuming connection to an existing run - section13."""

    success: bool
    run_id: str = ""
    status: RunStatus = RunStatus.UNKNOWN
    reconnected: bool = False
    source: str = ""  # "local_record", "boundary_lookup"
    error_class: str = ""
    reason: str = ""
    repair_guidance: List[str] = field(default_factory=list)
    response_data: Dict[str, Any] = field(default_factory=dict)
