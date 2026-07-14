"""Schema discovery helpers.

CE-V5-S42-06: Run-Type Safety & Schema Discovery Helpers.

Provides schema hints and request-shape guidance for known run types.
When schema information is unavailable, returns an explicit
"schema unavailable — re-discover first" posture.

Must never:
  - fabricate schema when discovery is unavailable
  - guess parameter structures from naming convention
  - depend on private platform source
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from keyhole_sdk.dispatch.models import SchemaHint


# ── Known request schemas ───────────────────────────────────
# Static schema hints for currently implemented run types.
# These reflect the published request shape for POST /mcp/v1/runs/start.
# The envelope is always {"run_type": "...", "params": {...}}.

_KNOWN_SCHEMAS: Dict[str, SchemaHint] = {
    "context.compile": SchemaHint(
        run_type="context.compile",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "context.compile", "params": {}},
        notes="Primary context bootstrap surface. No required parameters.",
    ),
    "gaps.list": SchemaHint(
        run_type="gaps.list",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "gaps.list", "params": {}},
        notes="Browse current gaps. No required parameters.",
    ),
    "gaps.status": SchemaHint(
        run_type="gaps.status",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "gaps.status", "params": {}},
        notes="Current gap status posture.",
    ),
    "gaps.next_open_canonical": SchemaHint(
        run_type="gaps.next_open_canonical",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "gaps.next_open_canonical", "params": {}},
        notes="Next open canonical gap.",
    ),
    "lineage.get.v0_1": SchemaHint(
        run_type="lineage.get.v0_1",
        available=True,
        required_params=["target"],
        optional_params=[],
        example={
            "run_type": "lineage.get.v0_1",
            "params": {"target": "<target-identifier>"},
        },
        notes="Causal lineage for a specific target. Requires 'target' parameter.",
    ),
    "convergence.status.v0_1": SchemaHint(
        run_type="convergence.status.v0_1",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.status.v0_1", "params": {}},
        notes="Current convergence posture. No required parameters.",
    ),
    "convergence.constraints.check": SchemaHint(
        run_type="convergence.constraints.check",
        available=True,
        required_params=[],
        optional_params=["target", "scope"],
        example={"run_type": "convergence.constraints.check", "params": {}},
        notes="Check convergence constraints. Optional: 'target' and 'scope' parameters.",
    ),
    # ── Additional canonical run-type stubs ──────────────────────────────────
    # Stubs provide availability signal. Re-discover via capabilities for
    # exact required parameters before dispatch.
    "promotion.submit": SchemaHint(
        run_type="promotion.submit",
        available=True,
        required_params=["repo_name"],
        optional_params=["ctxpack_digest"],
        example={"run_type": "promotion.submit", "params": {"repo_name": "<repo>"}},
        notes="Submit a promotion request. Re-discover capabilities for current shape.",
    ),
    "gaps.resolve": SchemaHint(
        run_type="gaps.resolve",
        available=True,
        required_params=["gap_id"],
        optional_params=[],
        example={"run_type": "gaps.resolve", "params": {"gap_id": "<gap_id>"}},
        notes="Resolve (close) an open gap.",
    ),
    "gaps.claim": SchemaHint(
        run_type="gaps.claim",
        available=True,
        required_params=["gap_id", "repo_name"],
        optional_params=["ctxpack_digest"],
        example={"run_type": "gaps.claim", "params": {"gap_id": "<gap_id>", "repo_name": "<repo>"}},
        notes="Claim an open gap for a repo.",
    ),
    "gaps.submit": SchemaHint(
        run_type="gaps.submit",
        available=True,
        required_params=["capability", "repo_name"],
        optional_params=["ctxpack_digest", "description"],
        example={"run_type": "gaps.submit", "params": {"capability": "<cap>", "repo_name": "<repo>"}},
        notes="Submit a new gap for a capability.",
    ),
    "gaps.get": SchemaHint(
        run_type="gaps.get",
        available=True,
        required_params=["gap_id"],
        optional_params=[],
        example={"run_type": "gaps.get", "params": {"gap_id": "<gap_id>"}},
        notes="Retrieve a specific gap by ID.",
    ),
    "gaps.evidence.submit": SchemaHint(
        run_type="gaps.evidence.submit",
        available=True,
        required_params=["gap_id", "evidence"],
        optional_params=[],
        example={"run_type": "gaps.evidence.submit", "params": {"gap_id": "<gap_id>", "evidence": {}}},
        notes="Submit evidence for an open gap.",
    ),
    "convergence.candidate": SchemaHint(
        run_type="convergence.candidate",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.candidate", "params": {}},
        notes="Current convergence candidate. Re-discover for exact shape.",
    ),
    "convergence.closure": SchemaHint(
        run_type="convergence.closure",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.closure", "params": {}},
        notes="Convergence closure posture.",
    ),
    "convergence.frontier.next": SchemaHint(
        run_type="convergence.frontier.next",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.frontier.next", "params": {}},
        notes="Next convergence frontier item.",
    ),
    "convergence.verdict": SchemaHint(
        run_type="convergence.verdict",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.verdict", "params": {}},
        notes="Current convergence verdict.",
    ),
    "convergence.gap.validate": SchemaHint(
        run_type="convergence.gap.validate",
        available=True,
        required_params=["gap_id"],
        optional_params=[],
        example={"run_type": "convergence.gap.validate", "params": {"gap_id": "<gap_id>"}},
        notes="Validate a gap against convergence constraints.",
    ),
    "convergence.gap.resolve": SchemaHint(
        run_type="convergence.gap.resolve",
        available=True,
        required_params=["gap_id"],
        optional_params=[],
        example={"run_type": "convergence.gap.resolve", "params": {"gap_id": "<gap_id>"}},
        notes="Resolve a gap through the convergence path.",
    ),
    "convergence.gap.explain": SchemaHint(
        run_type="convergence.gap.explain",
        available=True,
        required_params=["gap_id"],
        optional_params=[],
        example={"run_type": "convergence.gap.explain", "params": {"gap_id": "<gap_id>"}},
        notes="Explain the current state of a gap.",
    ),
    "convergence.loop": SchemaHint(
        run_type="convergence.loop",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.loop", "params": {}},
        notes="Convergence loop execution.",
    ),
    "convergence.execute": SchemaHint(
        run_type="convergence.execute",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.execute", "params": {}},
        notes="Execute a convergence cycle.",
    ),
    "convergence.operator_view": SchemaHint(
        run_type="convergence.operator_view",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.operator_view", "params": {}},
        notes="Operator view of current convergence state.",
    ),
    "convergence.status": SchemaHint(
        run_type="convergence.status",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "convergence.status", "params": {}},
        notes="Convergence status. Prefer convergence.status.v0_1 for versioned contract.",
    ),
    "promotion.candidate.from_verdict.v0_1": SchemaHint(
        run_type="promotion.candidate.from_verdict.v0_1",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "promotion.candidate.from_verdict.v0_1", "params": {}},
        notes="Build a promotion candidate from a convergence verdict.",
    ),
    "ops.pattern.acknowledge": SchemaHint(
        run_type="ops.pattern.acknowledge",
        available=True,
        required_params=["pattern_id"],
        optional_params=[],
        example={"run_type": "ops.pattern.acknowledge", "params": {"pattern_id": "<id>"}},
        notes="Acknowledge an ops pattern.",
    ),
    "ops.pattern.get": SchemaHint(
        run_type="ops.pattern.get",
        available=True,
        required_params=["pattern_id"],
        optional_params=[],
        example={"run_type": "ops.pattern.get", "params": {"pattern_id": "<id>"}},
        notes="Get a specific ops pattern.",
    ),
    "ops.pattern.list": SchemaHint(
        run_type="ops.pattern.list",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "ops.pattern.list", "params": {}},
        notes="List all ops patterns.",
    ),
    "connection.identity.inspect": SchemaHint(
        run_type="connection.identity.inspect",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.identity.inspect", "params": {}},
        notes="Inspect current connection identity.",
    ),
    "connection.status.inspect": SchemaHint(
        run_type="connection.status.inspect",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.status.inspect", "params": {}},
        notes="Inspect current connection status.",
    ),
    "connection.list.inspect": SchemaHint(
        run_type="connection.list.inspect",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.list.inspect", "params": {}},
        notes="List and inspect current connections.",
    ),
    "connection.lineage.inspect": SchemaHint(
        run_type="connection.lineage.inspect",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.lineage.inspect", "params": {}},
        notes="Inspect connection lineage.",
    ),
    "connection.rebind": SchemaHint(
        run_type="connection.rebind",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.rebind", "params": {}},
        notes="Rebind the current connection.",
    ),
    "connection.invalidate": SchemaHint(
        run_type="connection.invalidate",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "connection.invalidate", "params": {}},
        notes="Invalidate the current connection.",
    ),
    "flightcheck.v3": SchemaHint(
        run_type="flightcheck.v3",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "flightcheck.v3", "params": {}},
        notes="Pre-flight readiness check v3.",
    ),
    "auth.login_request": SchemaHint(
        run_type="auth.login_request",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.login_request", "params": {}},
        notes="Initiate auth login request.",
    ),
    "auth.login_complete": SchemaHint(
        run_type="auth.login_complete",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.login_complete", "params": {}},
        notes="Complete auth login flow.",
    ),
    "auth.register": SchemaHint(
        run_type="auth.register",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.register", "params": {}},
        notes="Register a new auth identity.",
    ),
    "auth.verify": SchemaHint(
        run_type="auth.verify",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.verify", "params": {}},
        notes="Verify current auth identity.",
    ),
    "auth.status": SchemaHint(
        run_type="auth.status",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.status", "params": {}},
        notes="Check current auth status.",
    ),
    "auth.remove": SchemaHint(
        run_type="auth.remove",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "auth.remove", "params": {}},
        notes="Remove an auth identity.",
    ),
    "context.constraints.build": SchemaHint(
        run_type="context.constraints.build",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "context.constraints.build", "params": {}},
        notes="Build context constraints.",
    ),
    "tool.patch.apply": SchemaHint(
        run_type="tool.patch.apply",
        available=True,
        required_params=["patch"],
        optional_params=[],
        example={"run_type": "tool.patch.apply", "params": {"patch": "<patch-content>"}},
        notes="Apply a patch via the tool surface.",
    ),
    "tool.git.commit_push_pr": SchemaHint(
        run_type="tool.git.commit_push_pr",
        available=True,
        required_params=["message"],
        optional_params=["branch", "title"],
        example={"run_type": "tool.git.commit_push_pr", "params": {"message": "<commit-msg>"}},
        notes="Commit, push, and open a PR via the tool surface.",
    ),
    "events.replay": SchemaHint(
        run_type="events.replay",
        available=True,
        required_params=[],
        optional_params=["from_cursor", "limit"],
        example={"run_type": "events.replay", "params": {}},
        notes="Replay events from the Event Spine.",
    ),
    "proofs.e2e.harness": SchemaHint(
        run_type="proofs.e2e.harness",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "proofs.e2e.harness", "params": {}},
        notes="Run the end-to-end proof harness.",
    ),
    "intent.compile": SchemaHint(
        run_type="intent.compile",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "intent.compile", "params": {}},
        notes="Compile current intent context.",
    ),
    "intent.submit": SchemaHint(
        run_type="intent.submit",
        available=True,
        required_params=[],
        optional_params=["intent_ref"],
        example={"run_type": "intent.submit", "params": {}},
        notes="Submit a governed intent for dispatch.",
    ),
    "workspace.provision": SchemaHint(
        run_type="workspace.provision",
        available=True,
        required_params=["repo_name", "gap_id", "claim_token"],
        optional_params=[],
        example={"run_type": "workspace.provision", "params": {"repo_name": "<repo>", "gap_id": "<gap_id>", "claim_token": "<token>"}},
        notes="Provision a governed workspace for a claimed gap.",
    ),
    "workspace.close": SchemaHint(
        run_type="workspace.close",
        available=True,
        required_params=["workspace_id"],
        optional_params=[],
        example={"run_type": "workspace.close", "params": {"workspace_id": "<ws_id>"}},
        notes="Close a provisioned workspace.",
    ),
    "readiness.explain": SchemaHint(
        run_type="readiness.explain",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "readiness.explain", "params": {}},
        notes="Explain current platform readiness state and invariant results.",
    ),
    "proof.bundle.emit": SchemaHint(
        run_type="proof.bundle.emit",
        available=True,
        required_params=["workspace_id"],
        optional_params=[],
        example={"run_type": "proof.bundle.emit", "params": {"workspace_id": "<ws_id>"}},
        notes="Emit a proof bundle for a workspace.",
    ),
    "proofbundle.build": SchemaHint(
        run_type="proofbundle.build",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "proofbundle.build", "params": {}},
        notes="Build a proof bundle.",
    ),
    "run.status": SchemaHint(
        run_type="run.status",
        available=True,
        required_params=[],
        optional_params=["run_id", "request_id", "correlation_id"],
        example={"run_type": "run.status", "params": {"run_id": "<run-id>"}},
        notes="Server-backed run status for a durable run, request, or correlation identifier.",
    ),
    "run.explain": SchemaHint(
        run_type="run.explain",
        available=True,
        required_params=[],
        optional_params=["run_id", "request_id", "correlation_id"],
        example={"run_type": "run.explain", "params": {"run_id": "<run-id>"}},
        notes="Server-backed run explanation for a durable run, request, or correlation identifier.",
    ),
    "request.inspect": SchemaHint(
        run_type="request.inspect",
        available=True,
        required_params=[],
        optional_params=["request_id", "run_id", "correlation_id"],
        example={"run_type": "request.inspect", "params": {"request_id": "<request-id>"}},
        notes="Server-backed request inspection linked to run, context, proof, and receipt evidence.",
    ),
    "support.bundle": SchemaHint(
        run_type="support.bundle",
        available=True,
        required_params=[],
        optional_params=["run_id", "request_id", "correlation_id"],
        example={"run_type": "support.bundle", "params": {"run_id": "<run-id>"}},
        notes="Server-backed support bundle or manifest for a durable run/request chain.",
    ),
    "run.tail": SchemaHint(
        run_type="run.tail",
        available=True,
        required_params=[],
        optional_params=["run_id", "request_id", "correlation_id", "cursor", "limit"],
        example={"run_type": "run.tail", "params": {"run_id": "<run-id>"}},
        notes="Server-backed ordered run observations for a durable run/request chain.",
    ),
    "run.budget": SchemaHint(
        run_type="run.budget",
        available=True,
        required_params=[],
        optional_params=["run_id", "request_id", "correlation_id"],
        example={"run_type": "run.budget", "params": {"run_id": "<run-id>"}},
        notes="Run-level budget and limit posture for a durable run/request chain.",
    ),
    "bindings.cohort.get": SchemaHint(
        run_type="bindings.cohort.get",
        available=True,
        required_params=[],
        optional_params=["cohort_id"],
        example={"run_type": "bindings.cohort.get", "params": {}},
        notes="Get cohort binding information.",
    ),
    "bindings.cohort.upsert": SchemaHint(
        run_type="bindings.cohort.upsert",
        available=True,
        required_params=["cohort_id"],
        optional_params=[],
        example={"run_type": "bindings.cohort.upsert", "params": {"cohort_id": "<cohort_id>"}},
        notes="Upsert a cohort binding.",
    ),
    "digest.register": SchemaHint(
        run_type="digest.register",
        available=True,
        required_params=["digest"],
        optional_params=[],
        example={"run_type": "digest.register", "params": {"digest": "<sha256-digest>"}},
        notes="Register a canonical digest.",
    ),
    "identity.binding.provision": SchemaHint(
        run_type="identity.binding.provision",
        available=True,
        required_params=[],
        optional_params=[],
        example={"run_type": "identity.binding.provision", "params": {}},
        notes="Provision an identity binding.",
    ),
    "eventvault.subject_stats.v1": SchemaHint(
        run_type="eventvault.subject_stats.v1",
        available=True,
        required_params=[],
        optional_params=["subject"],
        example={"run_type": "eventvault.subject_stats.v1", "params": {}},
        notes="Get Event Vault subject statistics.",
    ),
    "eventvault.verdicts.list": SchemaHint(
        run_type="eventvault.verdicts.list",
        available=True,
        required_params=[],
        optional_params=["cursor", "limit"],
        example={"run_type": "eventvault.verdicts.list", "params": {}},
        notes="List verdicts from the Event Vault.",
    ),
}


class SchemaHelper:
    """Schema discovery helper for run-type request shapes.

    Provides schema hints for known run types.  When a run type is
    not recognized, returns an explicit "unavailable" hint directing
    the participant to re-discover.

    Usage::

        helper = SchemaHelper()
        hint = helper.get_hint("lineage.get.v0_1")
        assert hint.available
        assert "target" in hint.required_params

    With capabilities::

        caps = client.fetch()
        helper = SchemaHelper.from_capabilities(caps)
        hint = helper.get_hint("context.compile")
    """

    def __init__(
        self,
        *,
        schemas: Optional[Dict[str, SchemaHint]] = None,
    ) -> None:
        self._schemas: Dict[str, SchemaHint] = dict(
            schemas if schemas is not None else _KNOWN_SCHEMAS
        )

    @classmethod
    def from_capabilities(cls, capabilities_result: object) -> "SchemaHelper":
        """Build a schema helper enriched with capabilities guidance.

        Incorporates implemented surfaces from the capabilities
        response as run types with known (possibly empty) schemas.
        """
        schemas = dict(_KNOWN_SCHEMAS)

        surfaces = getattr(
            getattr(capabilities_result, "context_access", None),
            "implemented_surfaces",
            [],
        )
        if isinstance(surfaces, list):
            for s in surfaces:
                if isinstance(s, str) and s and s not in schemas:
                    schemas[s] = SchemaHint(
                        run_type=s,
                        available=True,
                        notes=(
                            f"Discovered via capabilities. "
                            f"Consult schema discovery for parameter details."
                        ),
                    )

        return cls(schemas=schemas)

    def get_hint(self, run_type: str) -> SchemaHint:
        """Return schema guidance for a run type.

        Returns a hint with ``available=True`` for known run types,
        or a hint with ``available=False`` and guidance to re-discover
        for unknown run types.
        """
        if run_type in self._schemas:
            return self._schemas[run_type]

        return SchemaHint(
            run_type=run_type,
            available=False,
            notes=(
                f"No schema available for '{run_type}'. "
                "Re-discover via GET /mcp/v1/capabilities or "
                "consult published guidance before assuming request shape."
            ),
        )

    def validate_params(
        self,
        run_type: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Check params against known schema.

        Returns a list of warning strings.  An empty list means no
        issues were detected.  This does not guarantee server
        acceptance — it catches obvious participant-side mistakes.
        """
        warnings: List[str] = []
        hint = self.get_hint(run_type)

        if not hint.available:
            warnings.append(
                f"Schema unavailable for '{run_type}'. "
                "Cannot validate parameters. Re-discover first."
            )
            return warnings

        # If params is None, caller did not supply them yet — skip required checks.
        # Only validate when the caller explicitly provides a params dict.
        if params is None:
            return warnings

        actual_params = params

        # Check required params
        for req in hint.required_params:
            if req not in actual_params:
                warnings.append(
                    f"Required parameter '{req}' is missing for '{run_type}'."
                )

        return warnings

    @property
    def known_run_types(self) -> List[str]:
        """Return sorted list of run types with known schemas."""
        return sorted(self._schemas.keys())
