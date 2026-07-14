"""Run-type validation helpers.

CE-V5-S42-06: Run-Type Safety & Schema Discovery Helpers.

Validates intended run types against known canonical names and
published guidance.  Detects common mistake classes including
pluralization, naming drift, and guessed dispatch names.

Must never:
  - silently auto-correct guessed names
  - fabricate support for unknown run types
  - depend on private platform source

Sources of truth (in priority order):
  1. Live capabilities guidance (via CapabilitiesResult)
  2. Published canonical run types from context-access surfaces
  3. Conservative rejection for everything else
"""

from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Set

from keyhole_sdk.dispatch.models import (
    RunTypeCheckResult,
    RunTypeStatus,
)


# ── Known canonical run types ───────────────────────────────
# Run types disclosed by the live MCP boundary scope mapping.
# Updated from server response 2026-05-20 (full scope list).

CANONICAL_RUN_TYPES: FrozenSet[str] = frozenset({
    # Auth
    "auth.login_complete",
    "auth.login_request",
    "auth.register",
    "auth.remove",
    "auth.status",
    "auth.verify",
    # Bindings
    "bindings.cohort.get",
    "bindings.cohort.upsert",
    # Connection
    "connection.identity.inspect",
    "connection.invalidate",
    "connection.lineage.inspect",
    "connection.list.inspect",
    "connection.rebind",
    "connection.status.inspect",
    # Context
    "context.compile",
    "context.constraints.build",
    # Convergence
    "convergence.candidate",
    "convergence.closure",
    "convergence.constraints.check",
    "convergence.execute",
    "convergence.frontier.next",
    "convergence.gap.explain",
    "convergence.gap.resolve",
    "convergence.gap.validate",
    "convergence.loop",
    "convergence.operator_view",
    "convergence.status",
    "convergence.status.v0_1",
    "convergence.verdict",
    # Digest
    "digest.register",
    # Events
    "events.replay",
    "eventvault.subject_stats.v1",
    "eventvault.verdicts.list",
    # Flight check
    "flightcheck.v3",
    # Gaps
    "gaps.claim",
    "gaps.evidence.submit",
    "gaps.get",
    "gaps.list",
    "gaps.next_open_canonical",
    "gaps.resolve",
    "gaps.status",
    "gaps.submit",
    # Identity
    "identity.binding.provision",
    # Intent
    "intent.compile",
    "intent.submit",
    # Lineage
    "lineage.get.v0_1",
    # Ops
    "ops.pattern.acknowledge",
    "ops.pattern.get",
    "ops.pattern.list",
    # Proof / promotion
    "promotion.candidate.from_verdict.v0_1",
    "promotion.submit",
    "proof.bundle.emit",
    "proofbundle.build",
    "proofs.e2e.harness",
    # Product envelope observability
    "request.inspect",
    "run.budget",
    "run.explain",
    "run.status",
    "run.tail",
    "support.bundle",
    # Readiness
    "readiness.explain",
    # Tools
    "tool.git.commit_push_pr",
    "tool.patch.apply",
    # Workspace
    "workspace.close",
    "workspace.provision",
})

# ── Known mistake mappings ──────────────────────────────────
# Maps common incorrect forms to their canonical corrections.
# Sourced from published boundary client guidance.

KNOWN_MISTAKES: Dict[str, List[str]] = {
    "gaps.states": ["gaps.status"],
    "gaps.next": ["gaps.next_open_canonical"],
    "gap.status": ["gaps.status"],
    "gap.list": ["gaps.list"],
    "gap.states": ["gaps.status"],
    "context.get": ["context.compile"],
    "context.fetch": ["context.compile"],
    "context.retrieve": ["context.compile"],
    "convergence.statuses": ["convergence.status.v0_1"],
    "lineage.get": ["lineage.get.v0_1"],
}


class RunTypeValidator:
    """Validates intended run types before dispatch.

    Accepts known canonical names from two sources:

    1. The static set of published canonical run types.
    2. Additional canonical names learned from a live
       ``CapabilitiesResult`` (via ``from_capabilities()``).

    The validator never invents support.  When it does not recognize
    a run type, it returns ``unknown`` rather than guessing.

    Usage::

        validator = RunTypeValidator()
        result = validator.check("gaps.states")
        assert not result.is_valid
        assert "gaps.status" in result.suggestions

    With capabilities::

        caps = client.fetch()
        validator = RunTypeValidator.from_capabilities(caps)
        result = validator.check("context.compile")
        assert result.is_valid
    """

    def __init__(
        self,
        *,
        canonical: Optional[Set[str]] = None,
        mistakes: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._canonical: Set[str] = set(canonical or CANONICAL_RUN_TYPES)
        self._mistakes: Dict[str, List[str]] = dict(mistakes or KNOWN_MISTAKES)

    @classmethod
    def from_capabilities(cls, capabilities_result: object) -> "RunTypeValidator":
        """Build a validator enriched with live capabilities guidance.

        Accepts a ``CapabilitiesResult`` and incorporates:
          - implemented context surfaces as canonical names
          - published run-type mistakes from client guidance

        Note: ``capabilities_result`` is typed as ``object`` to avoid
        a circular import.  It must be a ``CapabilitiesResult`` instance
        with ``context_access.implemented_surfaces``, ``guidance``,
        and related attributes.
        """
        canonical: Set[str] = set(CANONICAL_RUN_TYPES)
        mistakes: Dict[str, List[str]] = dict(KNOWN_MISTAKES)

        # Incorporate implemented surfaces from capabilities
        surfaces = getattr(
            getattr(capabilities_result, "context_access", None),
            "implemented_surfaces",
            [],
        )
        if isinstance(surfaces, list):
            for s in surfaces:
                if isinstance(s, str) and s:
                    canonical.add(s)

        # Incorporate run-type mistakes from client guidance
        guidance = getattr(capabilities_result, "guidance", None)
        if guidance is not None:
            raw_mistakes = getattr(guidance, "run_type_mistakes", [])
            if isinstance(raw_mistakes, list):
                for item in raw_mistakes:
                    if isinstance(item, str):
                        _incorporate_mistake(item, canonical, mistakes)

        return cls(canonical=canonical, mistakes=mistakes)

    def check(self, run_type: str) -> RunTypeCheckResult:
        """Validate an intended run type.

        Returns a :class:`RunTypeCheckResult` with one of:
          - ``valid``: the run type matches a known canonical key
          - ``invalid``: the run type matches a known mistake with
            suggestions toward the correct form
          - ``unknown``: the run type is not recognized — the
            participant should re-discover before dispatch
        """
        if not isinstance(run_type, str) or not run_type.strip():
            return RunTypeCheckResult(
                run_type=str(run_type) if run_type is not None else "",
                status=RunTypeStatus.INVALID,
                reason="Run type must be a non-empty string.",
            )

        run_type = run_type.strip()

        # Check exact canonical match
        if run_type in self._canonical:
            return RunTypeCheckResult(
                run_type=run_type,
                status=RunTypeStatus.VALID,
                reason="Canonical run type.",
            )

        # Check known mistakes
        if run_type in self._mistakes:
            suggestions = self._mistakes[run_type]
            return RunTypeCheckResult(
                run_type=run_type,
                status=RunTypeStatus.INVALID,
                suggestions=list(suggestions),
                reason=_mistake_reason(run_type, suggestions),
            )

        # Check for close matches via simple heuristics
        close = self._find_close_matches(run_type)
        if close:
            return RunTypeCheckResult(
                run_type=run_type,
                status=RunTypeStatus.INVALID,
                suggestions=close,
                reason=(
                    f"'{run_type}' is not a canonical run type. "
                    f"Did you mean: {', '.join(close)}?"
                ),
            )

        # Unknown — not recognized at all
        return RunTypeCheckResult(
            run_type=run_type,
            status=RunTypeStatus.UNKNOWN,
            reason=(
                f"'{run_type}' is not recognized. "
                "Re-check capabilities or schema discovery. "
                "Do not guess run-type names."
            ),
        )

    def add_canonical(self, run_type: str) -> None:
        """Register an additional canonical run type."""
        self._canonical.add(run_type)

    @property
    def canonical_run_types(self) -> FrozenSet[str]:
        """Return the current set of known canonical run types."""
        return frozenset(self._canonical)

    def _find_close_matches(self, run_type: str) -> List[str]:
        """Find canonical names that are close to the given run type.

        Uses simple prefix/suffix and edit-distance heuristics.
        Returns at most 3 suggestions grounded in known canonical names.
        """
        candidates: List[str] = []
        rt_lower = run_type.lower()
        prefix = rt_lower.split(".")[0] if "." in rt_lower else rt_lower

        for canonical in sorted(self._canonical):
            c_lower = canonical.lower()
            # Same prefix family (e.g., "gaps." matches "gaps.list")
            if c_lower.startswith(prefix + ".") or rt_lower.startswith(
                c_lower.split(".")[0] + "."
            ):
                candidates.append(canonical)

        # Deduplicate and limit
        seen: Set[str] = set()
        result: List[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                result.append(c)
            if len(result) >= 3:
                break
        return result


def _mistake_reason(run_type: str, suggestions: List[str]) -> str:
    """Build a human-readable reason for a known mistake."""
    if len(suggestions) == 1:
        return (
            f"'{run_type}' is not canonical. "
            f"Use '{suggestions[0]}' instead."
        )
    return (
        f"'{run_type}' is not canonical. "
        f"Consider: {', '.join(suggestions)}."
    )


def _incorporate_mistake(
    item: str,
    canonical: Set[str],
    mistakes: Dict[str, List[str]],
) -> None:
    """Parse a mistake string from capabilities guidance.

    The boundary may publish mistake entries as:
      - "gaps.states (use gaps.status)"
      - "gap.status → gaps.status"
      - simple invalid names like "gaps.next"

    This parser extracts the incorrect form and the suggested
    correction where available.
    """
    # Handle "incorrect (use correct)" format
    if "(" in item and ")" in item:
        bad = item[: item.index("(")].strip()
        good_part = item[item.index("(") + 1 : item.index(")")]
        good = good_part.replace("use ", "").strip()
        if bad and good and bad not in canonical:
            mistakes.setdefault(bad, [])
            if good not in mistakes[bad]:
                mistakes[bad].append(good)
        return

    # Handle "incorrect → correct" format
    for sep in ("→", "->", "=>"):
        if sep in item:
            parts = item.split(sep, 1)
            bad = parts[0].strip()
            good = parts[1].strip()
            if bad and good and bad not in canonical:
                mistakes.setdefault(bad, [])
                if good not in mistakes[bad]:
                    mistakes[bad].append(good)
            return

    # Simple string — just mark as known-bad if not canonical
    stripped = item.strip()
    if stripped and stripped not in canonical and stripped not in mistakes:
        # Cannot suggest a correction — leave as unknown
        pass
