"""SDK-CLIENT-01-C - Connection identity rendering helpers (section9, section13).

Provides human-readable and machine-readable rendering for
connection identity inspection, rebind, and invalidate results.
"""
from __future__ import annotations

from typing import Any, Dict, List

from keyhole_sdk.connection_identity.models import (
    ConnectionInfo,
    InvalidateOutcome,
    RebindOutcome,
)


def render_connection_info(info: ConnectionInfo) -> str:
    """Render a single ConnectionInfo as a human-readable block (section9.3)."""
    lines = []
    if info.host_hint:
        lines.append(f"Host:       {info.host_hint}")
    lines.append(f"Connection: {info.connection_id or '(unknown)'}")
    lines.append(f"Principal:  {info.principal or '(none)'}")
    lines.append(f"User ID:    {info.user_id or '(none)'}")
    lines.append(f"Authority:  {info.authority.value}")
    if info.session_lineage_id:
        lines.append(f"Lineage:    {info.session_lineage_id}")
    if info.purpose:
        lines.append(f"Purpose:    {info.purpose}")
    if info.origin:
        lines.append(f"Origin:     {info.origin}")
    if info.bound_at:
        lines.append(f"Bound at:   {info.bound_at}")
    lines.append(f"Staleness:  {info.staleness_state.value}")
    lines.append(f"Rebind:     {'supported' if info.supports_rebind else 'not supported'}")
    lines.append(f"Invalidate: {'supported' if info.supports_invalidate else 'not supported'}")
    return "\n".join(lines)


def render_connection_list(connections: List[ConnectionInfo]) -> str:
    """Render a list of connections as a human-readable table (section9.2)."""
    if not connections:
        return "No connections visible."

    lines = []
    for i, c in enumerate(connections, 1):
        lines.append(f"[{i}] {c.connection_id or '(unknown)'}")
        lines.append(f"    Principal: {c.principal or '(none)'}")
        lines.append(f"    Authority: {c.authority.value}")
        lines.append(f"    Staleness: {c.staleness_state.value}")
        if c.host_hint:
            lines.append(f"    Host:      {c.host_hint}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_rebind_outcome(outcome: RebindOutcome) -> str:
    """Render a rebind outcome as human-readable text (section13.5)."""
    status_icons = {
        "accepted": "OK",
        "rebound": "OK",
        "replayed": "↻",
        "deferred": "?",
        "rejected": "✗",
    }
    icon = status_icons.get(outcome.status.value, "?")

    lines = [f"{icon} Rebind: {outcome.status.value}"]
    if outcome.old_principal:
        lines.append(f"  Old principal: {outcome.old_principal}")
    if outcome.new_principal:
        lines.append(f"  New principal: {outcome.new_principal}")
    if outcome.connection_id:
        lines.append(f"  Connection:    {outcome.connection_id}")
    if outcome.run_id:
        lines.append(f"  Run ID:        {outcome.run_id}")
    if outcome.server_message:
        lines.append(f"  Message:       {outcome.server_message}")
    if outcome.repair_guidance:
        lines.append("  Next steps:")
        for step in outcome.repair_guidance:
            lines.append(f"    - {step}")
    return "\n".join(lines)


def render_invalidate_outcome(outcome: InvalidateOutcome) -> str:
    """Render an invalidate outcome as human-readable text (section13.6)."""
    status_icons = {
        "accepted": "OK",
        "already_invalidated": "↻",
        "rejected": "✗",
    }
    icon = status_icons.get(outcome.status.value, "?")

    lines = [f"{icon} Invalidate: {outcome.status.value}"]
    if outcome.connection_id:
        lines.append(f"  Connection:         {outcome.connection_id}")
    lines.append(f"  Reconnect required: {'yes' if outcome.reconnect_required else 'no'}")
    if outcome.run_id:
        lines.append(f"  Run ID:             {outcome.run_id}")
    if outcome.server_message:
        lines.append(f"  Message:            {outcome.server_message}")
    if outcome.repair_guidance:
        lines.append("  Next steps:")
        for step in outcome.repair_guidance:
            lines.append(f"    - {step}")
    return "\n".join(lines)


def render_lineage(lineage_data: Dict[str, Any]) -> str:
    """Render connection lineage data as human-readable text (section9.4)."""
    if not lineage_data:
        return "No lineage data available."

    lines = []
    if "connection_id" in lineage_data:
        lines.append(f"Connection: {lineage_data['connection_id']}")
    if "principal" in lineage_data:
        lines.append(f"Principal:  {lineage_data['principal']}")
    if "lineage_id" in lineage_data or "session_lineage_id" in lineage_data:
        lid = lineage_data.get("lineage_id", lineage_data.get("session_lineage_id", ""))
        lines.append(f"Lineage ID: {lid}")

    events = lineage_data.get("events", lineage_data.get("history", []))
    if events and isinstance(events, list):
        lines.append("")
        lines.append("History:")
        for event in events:
            if isinstance(event, dict):
                ts = event.get("timestamp", event.get("at", ""))
                action = event.get("action", event.get("type", ""))
                detail = event.get("detail", event.get("message", ""))
                lines.append(f"  [{ts}] {action}: {detail}")
            else:
                lines.append(f"  - {event}")

    return "\n".join(lines) if lines else "No lineage data available."
