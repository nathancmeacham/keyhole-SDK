"""Typed public models for the Keyhole SDK.

Every model reflects the **public** runtime contract only.
Private governance fields (pointer state, canonical digest,
cluster topology, drift state, etc.) are explicitly forbidden.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────
# Private-field boundary
# ──────────────────────────────────────────────────────────────
PRIVATE_FIELDS: frozenset[str] = frozenset(
    {
        "pointer_state",
        "promotion_state",
        "canonical_digest",
        "cluster_topology",
        "internal_lane",
        "controller_state",
        "governance_verdict",
        "drift_state",
    }
)


def _strip_private(data: dict[str, Any]) -> dict[str, Any]:
    """Return *data* with all private/governance fields removed."""
    return {k: v for k, v in data.items() if k not in PRIVATE_FIELDS}


# ──────────────────────────────────────────────────────────────
# Runtime Identity
# ──────────────────────────────────────────────────────────────
class RuntimeIdentity(BaseModel):
    """Public runtime identity response (``GET /identity``)."""

    runtime_id: str
    runtime_name: str
    runtime_version: str
    environment: str
    capabilities: List[str]
    governance_mode: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def reject_private_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _strip_private(values)
        return values


# ──────────────────────────────────────────────────────────────
# Runtime Health
# ──────────────────────────────────────────────────────────────
class RuntimeHealth(BaseModel):
    """Public runtime health response (``GET /healthz``)."""

    status: str
    timestamp: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Runtime State
# ──────────────────────────────────────────────────────────────
class RuntimeState(BaseModel):
    """Public runtime-local state view (``GET /state``)."""

    current_digest: Optional[str] = None
    realized_digests: List[str] = Field(default_factory=list)
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def reject_private_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            return _strip_private(values)
        return values


# ──────────────────────────────────────────────────────────────
# Realization Request / Receipt
# ──────────────────────────────────────────────────────────────
class RealizationRequest(BaseModel):
    """Public realization request (``POST /realize``)."""

    candidate_digest: str
    payload: dict[str, Any] = Field(default_factory=dict)


class RealizationReceipt(BaseModel):
    """Public realization receipt (``POST /realize`` response)."""

    digest: str
    status: str
    message: str = ""
    realized_at: datetime


class GovernanceReceipt(BaseModel):
    """Bounded public receipt for governed runtime realizations.

    This model carries governance posture fields that prove whether a runtime
    realization was MCP-gated and whether upstream evidence was referenced.
    It intentionally does not expose pointer/controller internals.
    """

    digest: str
    status: str
    message: str = ""
    realized_at: datetime
    governed: bool = False
    event_spine_evidence: bool = False
    governance_verdict: Optional[str] = None
    drift_state: Optional[str] = None
    governance_context_id: Optional[str] = None
    mcp_event_id: Optional[str] = None
    proof_id: Optional[str] = None
    receipt_id: Optional[str] = None
    passport_digest: Optional[str] = None
    trust_digest: Optional[str] = None


# ──────────────────────────────────────────────────────────────
# Compatibility
# ──────────────────────────────────────────────────────────────
class CompatibilityStatus(str, Enum):
    """Deterministic compatibility outcome classes."""

    COMPATIBLE = "compatible"
    COMPATIBLE_WITH_WARNINGS = "compatible_with_warnings"
    INCOMPATIBLE = "incompatible"


class CompatibilityResult(BaseModel):
    """Result of an SDK / runtime compatibility check."""

    sdk_version: str
    runtime_name: str
    runtime_version: str
    compatibility_status: CompatibilityStatus
    checked_contract_version: Optional[str] = None
    failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checked_at: str  # ISO-8601


# ──────────────────────────────────────────────────────────────
# Public Error Envelope
# ──────────────────────────────────────────────────────────────
class PublicError(BaseModel):
    """Public error envelope for runtime error responses."""

    error: str
    detail: str = ""
    status_code: int = 0
