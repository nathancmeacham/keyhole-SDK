"""Surface negotiator — SDK-CLIENT-21 §9 §11 §16.

Orchestrates the full negotiation cycle:
  1. Accept a live CapabilitiesResult (already fetched).
  2. Classify surfaces (§8) via the classifier.
  3. Compute overall compatibility status (§11 §16).
  4. Return a deterministic NegotiationResult.

§7.1 Truth before convenience: required surfaces must all be present
     before declaring COMPATIBLE status.
§9   Negotiation occurs at startup or first authenticated call.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from keyhole_sdk.discovery.models import CapabilitiesResult
from keyhole_sdk.negotiation.classifier import SURFACE_TAXONOMY, classify_surfaces
from keyhole_sdk.negotiation.models import (
    CompatibilitySummary,
    NegotiationResult,
    NegotiationStatus,
    NegotiatedFeatures,
    SurfaceClass,
    SurfaceEntry,
)


def negotiate(caps: CapabilitiesResult) -> NegotiationResult:
    """§9 §11 — Perform surface negotiation from a live CapabilitiesResult.

    Produces a deterministic :class:`NegotiationResult` that encodes:
      - which surfaces the server declares
      - which required surfaces are missing (→ BLOCKED)
      - which optional surfaces are missing (→ DEGRADED)
      - which surfaces are transitional
      - the overall compatibility status

    This function is pure and deterministic — same input → same output.
    It does not perform I/O.  The caller is responsible for fetching
    capabilities and writing artifacts.

    §7.3 No silent assumption: all features default to False.
    §7.1 Truth before convenience: COMPATIBLE only when required surfaces present.
    """
    features, entries = classify_surfaces(caps)

    required_missing = _collect_by_class(entries, SurfaceClass.REQUIRED, present=False)
    optional_missing = _collect_by_class(entries, SurfaceClass.OPTIONAL, present=False)
    transitional = _collect_by_class(entries, SurfaceClass.TRANSITIONAL, present=None)

    if required_missing:
        status = NegotiationStatus.BLOCKED
    elif optional_missing:
        status = NegotiationStatus.DEGRADED
    else:
        status = NegotiationStatus.COMPATIBLE

    return NegotiationResult(
        server_version=caps.get_contract_version(),
        surface_fingerprint=caps.metadata.digest,
        operations=caps.get_all_run_types(),
        features=features,
        compatibility=CompatibilitySummary(
            status=status,
            required_missing=required_missing,
            optional_missing=optional_missing,
            transitional=transitional,
        ),
        negotiated_at=datetime.now(timezone.utc).isoformat(),
    )


def negotiate_from_raw(raw: dict) -> NegotiationResult:
    """Negotiate from a raw capabilities dict (e.g. from cache).

    Convenience wrapper for callers that hold a raw dict rather than
    a pre-normalized CapabilitiesResult.
    """
    from keyhole_sdk.discovery.client import CapabilitiesClient
    caps = CapabilitiesClient._normalize(raw)  # type: ignore[attr-defined]
    return negotiate(caps)


# ── Internal helpers ──────────────────────────────────────────

def _collect_by_class(
    entries: List[SurfaceEntry],
    cls: SurfaceClass,
    *,
    present: bool | None,
) -> List[str]:
    """Collect surface names matching a class and optional presence filter.

    Args:
        entries: list of SurfaceEntry to filter.
        cls: surface class to match.
        present: if True/False, filter by presence flag; if None, ignore presence.
    """
    result = []
    for entry in entries:
        if entry.surface_class != cls:
            continue
        if present is not None and entry.present != present:
            continue
        result.append(entry.name)
    return result
