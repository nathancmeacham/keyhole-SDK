"""Surface classifier — SDK-CLIENT-21 §8 §11.

Maps a live CapabilitiesResult to a classified surface inventory:
  - which surfaces are present or absent
  - which class (required / optional / transitional) each belongs to

§7.1 Truth before convenience: every feature defaults to False.
§7.3 No silent assumption: if the server did not declare it, it is absent.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from keyhole_sdk.discovery.models import CapabilitiesResult
from keyhole_sdk.negotiation.models import (
    NegotiatedFeatures,
    SurfaceClass,
    SurfaceEntry,
)


# ──────────────────────────────────────────────────────────────
# §8 — Surface taxonomy
# ──────────────────────────────────────────────────────────────

# Maps surface name → (SurfaceClass, description)
# The exact keying must match NegotiatedFeatures field names.
SURFACE_TAXONOMY: Dict[str, Tuple[SurfaceClass, str]] = {
    # §8.1 Required surfaces
    "authenticated_identity": (
        SurfaceClass.REQUIRED,
        "Identity/whoami endpoint declared by the boundary.",
    ),
    "run_dispatch": (
        SurfaceClass.REQUIRED,
        "Stable run dispatch contract declared by the boundary.",
    ),
    # §8.2 Optional surfaces
    "run_async_accept": (
        SurfaceClass.OPTIONAL,
        "Accepted/deferred async run semantics (SDK-CLIENT-17).",
    ),
    "context_compile": (
        SurfaceClass.OPTIONAL,
        "Context compile and inspect surfaces (SDK-CLIENT-16).",
    ),
    "explainability": (
        SurfaceClass.OPTIONAL,
        "Run explainability and inspection surfaces (SDK-CLIENT-20).",
    ),
    "support_bundle": (
        SurfaceClass.OPTIONAL,
        "Support bundle retrieval surface (SDK-CLIENT-20).",
    ),
    "run_tail": (
        SurfaceClass.OPTIONAL,
        "Run tail/follow observation surface (SDK-CLIENT-17).",
    ),
    "budget_visibility": (
        SurfaceClass.OPTIONAL,
        "Budget and limit visibility surface (SDK-CLIENT-19).",
    ),
    # §8.3 Transitional surfaces
    "context_required_for_runs": (
        SurfaceClass.TRANSITIONAL,
        "Server enforces context binding for governed runs (transitional).",
    ),
    "idempotency_required": (
        SurfaceClass.TRANSITIONAL,
        "Server declares idempotency required for write-bearing commands (transitional).",
    ),
}

# Canonical context-access surface key for context.compile
_CONTEXT_COMPILE_KEY = "context.compile"


def classify_surfaces(
    caps: CapabilitiesResult,
) -> Tuple[NegotiatedFeatures, List[SurfaceEntry]]:
    """§11 — Derive NegotiatedFeatures and classified surface list from capabilities.

    All features default to False — absence is explicit, not silent (§7.3).

    Returns:
        (features, entries):
          features — NegotiatedFeatures with presence flags
          entries  — ordered list of SurfaceEntry for inspection UX (§13)
    """
    flags: Dict[str, bool] = dict(caps.features.flags)
    implemented = set(caps.context_access.implemented_surfaces)
    operations = set(caps.get_all_run_types())

    # §8.1 Required: derive from structural endpoint declarations
    # authenticated_identity — identity endpoint declared
    has_identity = bool(caps.auth.identity_endpoint)
    # run_dispatch — run dispatch endpoint OR at least one operation implemented
    has_run_dispatch = bool(caps.auth.run_dispatch_endpoint) or (
        caps.contract.operations_implemented > 0
    )

    # §8.2 Optional: prefer feature flags; check context surfaces as fallback
    has_context_compile = (
        _CONTEXT_COMPILE_KEY in implemented
        or _CONTEXT_COMPILE_KEY in operations
        or bool(flags.get("context_compile", False))
    )

    features = NegotiatedFeatures(
        # Required
        authenticated_identity=has_identity,
        run_dispatch=has_run_dispatch,
        # Optional
        run_async_accept=bool(flags.get("run_async_accept", False)),
        context_compile=has_context_compile,
        explainability=bool(flags.get("explainability", False)),
        support_bundle=bool(flags.get("support_bundle", False)),
        run_tail=bool(flags.get("run_tail", False)),
        budget_visibility=bool(flags.get("budget_visibility", False)),
        # Transitional
        context_required_for_runs=bool(flags.get("context_required_for_runs", False)),
        idempotency_required=bool(flags.get("idempotency_required", False)),
    )

    entries: List[SurfaceEntry] = []
    for name, (cls, desc) in SURFACE_TAXONOMY.items():
        present = bool(getattr(features, name, False))
        entries.append(
            SurfaceEntry(
                name=name,
                surface_class=cls,
                present=present,
                description=desc,
            )
        )

    return features, entries
