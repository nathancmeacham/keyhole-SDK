"""`keyhole deregister` - account deletion command.

Implements SDK-CLIENT-22: Account Deregistration and Deletion UX.

Flow:
  1. Load stored credentials, check authentication
  2. Inspect acting identity via whoami
  3. Require explicit destructive confirmation unless --yes
  4. Dispatch auth.remove through governed run surface
  5. Record proof events, write proof bundle
  6. Return structured result with next-step guidance
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import typer

from keyhole_cli.result import CommandResult, EXIT_SUCCESS, EXIT_FAILURE
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.whoami import WhoamiClient
from keyhole_sdk.deregister.client import DeregistrationClient
from keyhole_sdk.deregister.errors import DeregistrationError
from keyhole_sdk.deregister.models import (
    DeregistrationRequest,
    DeregistrationStatus,
)
from keyhole_sdk.deregister.proof import DeregistrationProofBundle
from keyhole_sdk.config import DEFAULT_BASE_URL


def _resolve_proof_dir() -> Path:
    """Resolve KEYHOLE_HOME for proof bundle output."""
    keyhole_home = os.environ.get("KEYHOLE_HOME")
    if keyhole_home:
        return Path(keyhole_home)
    return Path.home() / ".keyhole"


# -- Status -> human-readable rendering ---------------------

_STATUS_ICONS = {
    DeregistrationStatus.ACCEPTED: "\u2714",      # ✔
    DeregistrationStatus.DEFERRED: "\u23F3",       # ?
    DeregistrationStatus.REPLAYED: "\u21A9",       # ↩
    DeregistrationStatus.REJECTED: "\u2717",       # ✗
    DeregistrationStatus.ALREADY_DELETED: "\u2139", # ℹ
    DeregistrationStatus.FAILED: "\u2717",         # ✗
    DeregistrationStatus.TRANSPORT_ERROR: "\u2717", # ✗
}

_STATUS_LABELS = {
    DeregistrationStatus.ACCEPTED: "Deletion accepted",
    DeregistrationStatus.DEFERRED: "Deletion deferred",
    DeregistrationStatus.REPLAYED: "Deletion replayed (prior request)",
    DeregistrationStatus.REJECTED: "Deletion rejected",
    DeregistrationStatus.ALREADY_DELETED: "Already deleted",
    DeregistrationStatus.FAILED: "Deletion failed",
    DeregistrationStatus.TRANSPORT_ERROR: "Transport error",
}


def run_deregister(
    *,
    registration_id: str,
    yes: bool = False,
    realm: str = "kh-prod",
    mcp_url: str = DEFAULT_BASE_URL,
) -> CommandResult:
    """Execute the deregistration flow and return a structured result."""
    correlation_id = str(uuid.uuid4())
    proof = DeregistrationProofBundle(correlation_id=correlation_id)

    # -- 1. Authentication check -----------------------------
    store = CredentialStore()
    session = store.load()

    if session is None:
        proof.record_event("deregistration_blocked", {"reason": "not_authenticated"})
        _write_proof_safe(proof, success=False)
        return CommandResult(
            command="deregister",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "deregistration_not_authenticated"},
            summary="Not authenticated - no stored credentials found.",
            next_steps=["Run 'keyhole login' first."],
        )

    if session.is_expired:
        proof.record_event("deregistration_blocked", {"reason": "session_expired"})
        _write_proof_safe(proof, success=False)
        return CommandResult(
            command="deregister",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "deregistration_not_authenticated", "expired": True},
            summary="Session expired.",
            next_steps=[
                "Run 'keyhole login' to re-authenticate.",
                "Run 'keyhole login --force' to force a fresh login.",
            ],
        )

    # -- 2. Identity inspection via whoami --------------------
    identity_snapshot = {}
    try:
        whoami_client = WhoamiClient(mcp_base_url=mcp_url)
        whoami = whoami_client.whoami(session.access_token)
        identity_snapshot = {
            "user_id": whoami.user_id,
            "tenant_id": whoami.tenant_id,
            "org_id": whoami.org_id,
            "mode": whoami.mode.value,
        }
        if whoami.display_name:
            identity_snapshot["display_name"] = whoami.display_name
        proof.record_event("identity_inspected", identity_snapshot)
    except Exception as exc:
        proof.record_event("identity_inspection_failed", {"error": str(exc)})
        # Non-fatal - server enforces ownership. Warn but proceed.

    # -- 3. Destructive confirmation -------------------------
    if not yes:
        proof.record_event("confirmation_required", {
            "registration_id": registration_id,
        })
        # Return a result that signals confirmation is needed
        # The CLI layer handles the interactive prompt
        return CommandResult(
            command="deregister",
            success=False,
            exit_code=EXIT_FAILURE,
            data={
                "error_class": "confirmation_required",
                "registration_id": registration_id,
                "identity_snapshot": identity_snapshot,
            },
            summary="Destructive confirmation required.",
            next_steps=[
                "Re-run with --yes to confirm deletion.",
                f"keyhole deregister --registration-id {registration_id} --yes",
            ],
        )

    # -- 4. Build request and dispatch -----------------------
    request = DeregistrationRequest(
        registration_id=registration_id,
        confirm=True,
        correlation_id=correlation_id,
        realm=realm,
    )

    proof.record_event("deregistration_dispatched", request.to_proof_dict())

    client = DeregistrationClient(mcp_base_url=mcp_url)

    try:
        outcome = client.deregister(
            request,
            access_token=session.access_token,
            correlation_id=correlation_id,
        )
    except DeregistrationError as exc:
        proof.record_event("deregistration_failed", {
            "error_class": exc.error_class,
            "reason": exc.reason,
        })
        _write_proof_safe(proof, success=False)
        return CommandResult(
            command="deregister",
            success=False,
            exit_code=EXIT_FAILURE,
            data={
                "correlation_id": correlation_id,
                "error_class": exc.error_class,
                "reason": exc.reason,
            },
            summary=str(exc),
            next_steps=exc.repair_suggestions or ["Retry: keyhole deregister --help"],
        )

    # -- 5. Record proof and write ---------------------------
    proof.record_event("deregistration_outcome", outcome.safe_summary())

    is_success = outcome.status in (
        DeregistrationStatus.ACCEPTED,
        DeregistrationStatus.ALREADY_DELETED,
        DeregistrationStatus.REPLAYED,
    )

    proof_dir = None
    try:
        proof_dir = proof.write(
            request=request.to_proof_dict(),
            outcome=outcome.safe_summary(),
            identity_snapshot=identity_snapshot,
            success=is_success,
            output_dir=_resolve_proof_dir(),
        )
    except Exception:
        pass

    # -- 6. Build result -------------------------------------
    icon = _STATUS_ICONS.get(outcome.status, "?")
    label = _STATUS_LABELS.get(outcome.status, outcome.status.value)

    data = {
        "correlation_id": correlation_id,
        "registration_id": registration_id,
        "status": outcome.status.value,
    }
    if outcome.run_id:
        data["run_id"] = outcome.run_id
    if outcome.reason:
        data["reason"] = outcome.reason
    if proof_dir:
        data["proof_path"] = str(proof_dir)

    # Build next-step guidance
    next_steps = list(outcome.repair_guidance) if outcome.repair_guidance else []

    run_ref = outcome.run_id or correlation_id
    if outcome.status == DeregistrationStatus.ACCEPTED:
        next_steps.extend([
            f"keyhole runs status {run_ref}",
            f"keyhole runs wait {run_ref}",
            f"keyhole explain run {run_ref}",
        ])
    elif outcome.status == DeregistrationStatus.DEFERRED:
        next_steps.extend([
            f"keyhole runs wait {run_ref}",
            f"keyhole runs status {run_ref}",
        ])
    elif outcome.status == DeregistrationStatus.ALREADY_DELETED:
        next_steps.append(f"keyhole explain run {run_ref}")

    if proof_dir:
        next_steps.append(f"Proof artifacts: {proof_dir}")

    return CommandResult(
        command="deregister",
        success=is_success,
        exit_code=EXIT_SUCCESS if is_success else EXIT_FAILURE,
        data=data,
        summary=f"{icon} {label}",
        next_steps=next_steps,
    )


def _write_proof_safe(proof: DeregistrationProofBundle, *, success: bool) -> None:
    """Best-effort proof write - never raises."""
    try:
        proof.write(success=success, output_dir=_resolve_proof_dir())
    except Exception:
        pass
