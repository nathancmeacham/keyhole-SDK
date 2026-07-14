"""`keyhole repo register` — repository registration command.

SDK-CLIENT-07: Repository Registration with MCP.

Binds a repository to the Keyhole platform through a governed
registration flow. Supports both native Keyhole-scaffolded repos
and ingestion-backed foreign repos.

Never silently mutates the target repo during registration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.registration.artifacts import (
    build_artifacts_snapshot,
    load_ingestion_reference,
    load_native_artifacts,
)
from keyhole_sdk.registration.models import (
    RegistrationOutcome,
    RegistrationRequest,
)
from keyhole_sdk.registration.payload import build_registration_payload
from keyhole_sdk.registration.proof import emit_registration_proof
from keyhole_sdk.registration.readiness import assess_readiness
from keyhole_sdk.registration.repair import map_registration_repair
from keyhole_sdk.registration.submitter import submit_registration
from keyhole_sdk.transport.client import GovernedTransport
from keyhole_sdk.transport.idempotency import generate_request_id

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_repo_register(
    *,
    repo_path: str = ".",
    shadow: bool = False,
    from_ingest: str = "",
    non_interactive: bool = False,
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole repo register``.

    Returns a CommandResult for the CLI to render.
    """
    command_label = "keyhole repo register --shadow" if shadow else "keyhole repo register"
    target = Path(repo_path).resolve()

    # ── §8.4: Fail-local — validate path ──
    if not target.is_dir():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=f"Repository path does not exist or is not a directory: {target}",
            data={"error_class": "InvalidRepoPath", "is_local": True},
            next_steps=map_registration_repair("InvalidRepoPath"),
        )

    # ── Resolve credentials ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    session = cred_store.load()
    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = session.access_token if session else ""
    identity_fp = session.token_fingerprint if session else ""
    has_auth = bool(token)

    # ── §6: Load registration inputs ──
    native_artifacts = load_native_artifacts(target)

    ingestion_ref = None
    if from_ingest:
        state_dir = _resolve_state_dir(keyhole_home)
        ingestion_ref = load_ingestion_reference(
            state_dir=state_dir,
            ingest_id=from_ingest,
        )

    # ── §8, §9: Assess readiness ──
    readiness_check = assess_readiness(
        repo_path=target,
        has_auth=has_auth,
        native_artifacts=native_artifacts,
        ingestion_ref=ingestion_ref,
        from_ingest=from_ingest,
    )

    # ── §8.4: Fail-local on blockers ──
    if not readiness_check.can_proceed:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=f"Registration blocked: {readiness_check.blockers[0]}",
            data={
                "readiness": readiness_check.readiness.value,
                "source": readiness_check.source.value,
                "blockers": readiness_check.blockers,
                "is_local": True,
            },
            next_steps=readiness_check.blockers,
        )

    # ── §10: Build payload ──
    correlation_id = generate_request_id()
    payload = build_registration_payload(
        repo_path=target,
        readiness_check=readiness_check,
        native_artifacts=native_artifacts,
        ingestion_ref=ingestion_ref,
        shadow=shadow,
        correlation_id=correlation_id,
    )

    # ── Build request ──
    request = RegistrationRequest(
        payload=payload,
        identity_fingerprint=identity_fp,
    )

    # ── §12: Build transport ──
    auth_provider = BearerTokenProvider(token=token)
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    # ── §12: Submit ──
    try:
        outcome = submit_registration(transport=transport, request=request)
    finally:
        transport.close()

    # ── §15: Emit proof — out-of-tree by default ──
    state_dir = _resolve_state_dir(keyhole_home)
    artifacts_snapshot = build_artifacts_snapshot(
        native_artifacts=native_artifacts,
        ingestion_ref=ingestion_ref,
    )
    identity_context = (
        outcome.identity_binding.to_dict()
        if outcome.identity_binding else None
    )
    proof_dir = _safe_emit_proof(
        state_dir=state_dir,
        correlation_id=correlation_id,
        request=request,
        artifacts_snapshot=artifacts_snapshot,
        outcome=outcome,
        identity_context=identity_context,
    )

    # ── §13: Render outcome ──
    return _outcome_to_result(
        outcome=outcome,
        command_label=command_label,
        proof_dir=proof_dir,
        readiness_check=readiness_check,
    )


def _outcome_to_result(
    *,
    outcome: RegistrationOutcome,
    command_label: str,
    proof_dir: Optional[Path],
    readiness_check: Any,
) -> CommandResult:
    """Convert a RegistrationOutcome to a CommandResult (§13)."""
    is_success = outcome.status in ("success", "accepted", "replayed")

    data: Dict[str, Any] = {
        "status": outcome.status,
        "repo_name": outcome.repo_name,
        "registration_source": outcome.registration_source.value,
        "readiness": outcome.readiness.value,
        "shadow": outcome.shadow,
        "correlation_id": outcome.correlation_id,
        "is_replay": outcome.is_replay,
    }

    if outcome.registration_id:
        data["registration_id"] = outcome.registration_id

    # §11: Identity binding
    if outcome.identity_binding:
        binding = outcome.identity_binding.to_dict()
        data["identity_binding"] = binding
        # Also surface key fields at top level for human display
        for key in ("tenant_id", "org_id", "cohort_id", "worker_id", "repo_id"):
            val = getattr(outcome.identity_binding, key, "")
            if val:
                data[key] = val

    if outcome.warnings:
        data["warnings"] = outcome.warnings

    if proof_dir:
        data["proof_dir"] = str(proof_dir)

    # Build summary
    if outcome.status == "success":
        mode_label = " (shadow)" if outcome.shadow else ""
        summary = (
            f"Repository registered{mode_label}. "
            f"Source: {outcome.registration_source.value}. "
            f"Repo: {outcome.repo_name}."
        )
    elif outcome.status == "replayed":
        summary = (
            f"Repository registration replayed (stable governed outcome). "
            f"Repo: {outcome.repo_name}."
        )
    elif outcome.status == "accepted":
        summary = (
            f"Registration accepted (processing). "
            f"Repo: {outcome.repo_name}."
        )
    elif outcome.status == "deferred":
        summary = (
            f"Registration deferred. "
            f"Repo: {outcome.repo_name}. "
            f"Check status later."
        )
    else:
        summary = (
            f"Registration failed: "
            f"{outcome.reason or outcome.error_class or 'unknown error'}"
        )
        if outcome.error_class:
            data["error_class"] = outcome.error_class

    # Next steps
    next_steps: List[str] = []
    if outcome.suggested_actions:
        next_steps.extend(outcome.suggested_actions)
    if outcome.status == "accepted" and outcome.registration_id:
        next_steps.append(
            f"Check status with: keyhole registration-status --registration-id {outcome.registration_id}"
        )
    if outcome.repair_guidance:
        next_steps.extend(outcome.repair_guidance)
    if is_success and not outcome.shadow:
        next_steps.append("Run: keyhole run --context auto — to dispatch a governed run.")
    if is_success and outcome.shadow:
        next_steps.append("Run: keyhole repo register — without --shadow for full registration.")

    return CommandResult(
        command=command_label,
        success=is_success,
        exit_code=EXIT_SUCCESS if is_success else EXIT_FAILURE,
        summary=summary,
        data=data,
        warnings=outcome.warnings or None,
        next_steps=next_steps or None,
    )


def _resolve_state_dir(keyhole_home: str) -> Path:
    """Resolve the tool-owned state directory for proof artifacts."""
    if keyhole_home:
        return Path(keyhole_home) / "state"
    return Path.home() / ".keyhole" / "state"


def _safe_emit_proof(
    *,
    state_dir: Path,
    correlation_id: str,
    request: RegistrationRequest,
    artifacts_snapshot: Dict[str, Any],
    outcome: RegistrationOutcome,
    identity_context: Optional[Dict[str, Any]],
) -> Optional[Path]:
    """Emit proof artifacts, returning None on I/O failure."""
    try:
        return emit_registration_proof(
            state_dir=state_dir,
            correlation_id=correlation_id,
            request_dict=request.to_proof_dict(),
            artifacts_snapshot=artifacts_snapshot,
            outcome_dict=outcome.to_proof_dict(),
            identity_context=identity_context,
        )
    except OSError:
        return None
