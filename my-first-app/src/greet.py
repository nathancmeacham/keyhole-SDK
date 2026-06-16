"""Governed greeting capability implementations.

Capabilities:
  my-first-app.greet.user.v1
  my-first-app.greet.user.v2

Response shapes are versioned, stable contracts. Do not remove or rename
fields from a declared version without incrementing the capability version and
updating the matching INV gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Response contract (shape is what INV-01 guards) ─────────────────────────

@dataclass(frozen=True)
class GreetResponse:
    """Stable, versioned response for my-first-app.greet.user.v1."""

    greeting: str
    name: str
    capability: str = "my-first-app.greet.user.v1"


@dataclass(frozen=True)
class GreetV2Response:
    """Stable, versioned response for my-first-app.greet.user.v2."""

    greeting: str
    name: str
    defaulted: bool
    capability: str = "my-first-app.greet.user.v2"


# ── Capability implementation ────────────────────────────────────────────────

def greet(name: Optional[str] = None) -> GreetResponse:
    """Return a governed greeting for the supplied name.

    Parameters
    ----------
    name:
        Caller-supplied display name.  Defaults to "World" when absent or blank.

    Returns
    -------
    GreetResponse
        Stable response shape enforced by MY-FIRST-APP-INV-01.
    """
    resolved = (name or "").strip() or "World"
    return GreetResponse(
        greeting=f"Hello, {resolved}!",
        name=resolved,
    )


def greet_v2(name: Optional[str] = None) -> GreetV2Response:
    """Return a governed v2 greeting with explicit fallback metadata.

    Parameters
    ----------
    name:
        Caller-supplied display name. Defaults to "World" when absent or blank.

    Returns
    -------
    GreetV2Response
        Stable response shape enforced by MY-FIRST-APP-INV-02.
    """
    cleaned = (name or "").strip()
    defaulted = not bool(cleaned)
    resolved = cleaned or "World"
    return GreetV2Response(
        greeting=f"Hello, {resolved}!",
        name=resolved,
        defaulted=defaulted,
    )
