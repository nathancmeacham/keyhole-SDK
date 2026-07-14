"""Surface negotiation models — SDK-CLIENT-21 §11.

Defines the normalized client-side negotiation result, surface
classification types, and command-compatibility result.

The NegotiationResult is the single inspectable object that answers:
  - what the server declares
  - what the client requires for a command
  - what is blocked (required surface absent)
  - what is degraded (optional surface absent)
  - why

§11 Minimum local model shapes this module.
§8  Surface classes (required / optional / transitional) are enforced here.
§16 CommandCompatibilityResult encodes per-command evaluation output.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# §8 — Surface class taxonomy
# ──────────────────────────────────────────────────────────────


class SurfaceClass(str, enum.Enum):
    """Classification of a surface by its necessity (§8)."""

    REQUIRED = "required"
    """Absence causes fail-closed behavior for affected commands (§8.1)."""

    OPTIONAL = "optional"
    """Absence causes graceful degradation, not a hard block (§8.2)."""

    TRANSITIONAL = "transitional"
    """Surface exists but is declared preview, partial, or environment-specific (§8.3)."""


# ──────────────────────────────────────────────────────────────
# §11 — Negotiation status
# ──────────────────────────────────────────────────────────────


class NegotiationStatus(str, enum.Enum):
    """Overall negotiated compatibility posture (§11 §16)."""

    COMPATIBLE = "compatible"
    """All required surfaces are present; all optional surfaces present."""

    DEGRADED = "degraded"
    """All required surfaces are present; one or more optional surfaces absent."""

    BLOCKED = "blocked"
    """One or more required surfaces are absent; affected workflows are fail-closed."""


# ──────────────────────────────────────────────────────────────
# §16 — Command-level evaluation status
# ──────────────────────────────────────────────────────────────


class CommandStatus(str, enum.Enum):
    """Per-command compatibility status (§16)."""

    ALLOWED = "allowed"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


# ──────────────────────────────────────────────────────────────
# Surface entry
# ──────────────────────────────────────────────────────────────


class SurfaceEntry(BaseModel):
    """A single classified surface with presence information."""

    name: str
    surface_class: SurfaceClass
    present: bool
    description: str = ""


# ──────────────────────────────────────────────────────────────
# §11 — Normalized feature presence map
# ──────────────────────────────────────────────────────────────


class NegotiatedFeatures(BaseModel):
    """Normalized feature presence map derived from CapabilitiesResult (§11).

    Each field corresponds to one entry in the §11 minimum local model.
    The client must never silently assume any of these are True without
    a live boundary declaration (§7.3).

    Fields default to False — absence is explicit, not silent.
    """

    # §8.1 Required surfaces
    authenticated_identity: bool = Field(
        False,
        description="Identity/whoami endpoint is declared by the boundary.",
    )
    run_dispatch: bool = Field(
        False,
        description="Stable run dispatch contract is declared by the boundary.",
    )

    # §8.2 Optional surfaces
    run_async_accept: bool = Field(
        False,
        description="Accepted/deferred async run semantics are available.",
    )
    context_compile: bool = Field(
        False,
        description="Context compile and inspect surfaces are available.",
    )
    explainability: bool = Field(
        False,
        description="Run explainability and inspection surfaces are available.",
    )
    support_bundle: bool = Field(
        False,
        description="Support bundle retrieval is available.",
    )
    run_tail: bool = Field(
        False,
        description="Run tail/follow observation surface is available.",
    )
    budget_visibility: bool = Field(
        False,
        description="Budget and limit visibility is available.",
    )

    # §8.3 Transitional surfaces
    context_required_for_runs: bool = Field(
        False,
        description="Server enforces explicit context binding for governed runs.",
    )
    idempotency_required: bool = Field(
        False,
        description="Server declares idempotency as required for write-bearing commands.",
    )

    def to_dict(self) -> Dict[str, bool]:
        """Return the features as a plain dict (§11 minimum local model shape)."""
        return {
            "authenticated_identity": self.authenticated_identity,
            "run_dispatch": self.run_dispatch,
            "run_async_accept": self.run_async_accept,
            "context_compile": self.context_compile,
            "context_required_for_runs": self.context_required_for_runs,
            "idempotency_required": self.idempotency_required,
            "explainability": self.explainability,
            "support_bundle": self.support_bundle,
            "run_tail": self.run_tail,
            "budget_visibility": self.budget_visibility,
        }


# ──────────────────────────────────────────────────────────────
# §11 — Compatibility summary inside NegotiationResult
# ──────────────────────────────────────────────────────────────


class CompatibilitySummary(BaseModel):
    """Inner compatibility summary — mirrors §11 minimum local model."""

    status: NegotiationStatus = NegotiationStatus.COMPATIBLE
    required_missing: List[str] = Field(default_factory=list)
    optional_missing: List[str] = Field(default_factory=list)
    transitional: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "required_missing": list(self.required_missing),
            "optional_missing": list(self.optional_missing),
            "transitional": list(self.transitional),
        }


# ──────────────────────────────────────────────────────────────
# §11 — Top-level NegotiationResult
# ──────────────────────────────────────────────────────────────


class NegotiationResult(BaseModel):
    """§11 — Normalized client-side surface negotiation result.

    This is the deterministic artifact that:
      - commands consume to decide if they are allowed (§16),
      - the ``keyhole surfaces`` command renders (§13),
      - proof/support artifacts write locally (§12).

    All fields default to empty/safe values so consumers tolerate
    any server maturity level without crashing.

    §7.3 No silent assumption: every feature defaults to False.
    §18 Every field supports later proof queries.
    """

    # §11 top-level fields
    server_version: str = Field("", description="Contract version from server declaration.")
    surface_fingerprint: str = Field("", description="Digest from server discovery metadata.")
    operations: List[str] = Field(
        default_factory=list,
        description="Implemented context-access operations disclosed by the server.",
    )

    # §11 features dict (normalized from CapabilitiesResult)
    features: NegotiatedFeatures = Field(default_factory=NegotiatedFeatures)

    # §11 compatibility summary
    compatibility: CompatibilitySummary = Field(default_factory=CompatibilitySummary)

    # Proof/audit fields (§18 §12)
    negotiated_at: str = Field("", description="ISO timestamp when negotiation occurred.")

    # ── Accessors (§13 §16) ────────────────────────────────

    def is_blocked(self) -> bool:
        """True when one or more required surfaces are missing (§14)."""
        return self.compatibility.status == NegotiationStatus.BLOCKED

    def is_degraded(self) -> bool:
        """True when optional surfaces are absent but required are present (§15)."""
        return self.compatibility.status == NegotiationStatus.DEGRADED

    def is_compatible(self) -> bool:
        """True when all required and optional surfaces are present."""
        return self.compatibility.status == NegotiationStatus.COMPATIBLE

    def to_dict(self) -> Dict[str, Any]:
        """§11 minimum local model shape, suitable for JSON serialization."""
        return {
            "server_version": self.server_version,
            "surface_fingerprint": self.surface_fingerprint,
            "operations": list(self.operations),
            "features": self.features.to_dict(),
            "compatibility": self.compatibility.to_dict(),
            "negotiated_at": self.negotiated_at,
        }


# ──────────────────────────────────────────────────────────────
# §16 — Per-command compatibility result
# ──────────────────────────────────────────────────────────────


class CommandCompatibilityResult(BaseModel):
    """Per-command compatibility evaluation result (§16).

    Produced by :func:`~keyhole_sdk.negotiation.evaluator.evaluate_command`.
    """

    command: str
    status: CommandStatus
    required_missing: List[str] = Field(default_factory=list)
    optional_missing: List[str] = Field(default_factory=list)
    reason: str = ""
    repair: List[str] = Field(default_factory=list)

    def is_blocked(self) -> bool:
        """True when the command must fail closed (§14)."""
        return self.status == CommandStatus.BLOCKED

    def is_degraded(self) -> bool:
        """True when the command may proceed with reduced UX (§15)."""
        return self.status == CommandStatus.DEGRADED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status.value,
            "required_missing": list(self.required_missing),
            "optional_missing": list(self.optional_missing),
            "reason": self.reason,
            "repair": list(self.repair),
        }
