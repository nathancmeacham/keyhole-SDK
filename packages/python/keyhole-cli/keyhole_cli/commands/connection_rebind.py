"""`keyhole connection rebind` - rebind connection to a profile (section9.4).

SDK-CLIENT-01-C: Explicit governed rebind of a live host connection
to a different principal.

INV-SDK-CLIENT-01-C-006: Rebind is idempotent.
"""
from __future__ import annotations

import uuid

from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.whoami import WhoamiClient
from keyhole_sdk.connection_identity.client import ConnectionIdentityClient
from keyhole_sdk.connection_identity.errors import (
    ConnectionIdentityError,
    ConnectionNetworkError,
)
from keyhole_sdk.connection_identity.models import RebindRequest, RebindStatus
from keyhole_sdk.doctor.proof import DoctorProofBundle

from keyhole_cli.result import CommandResult, EXIT_FAILURE, EXIT_SUCCESS
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_connection_rebind(
    *,
    host: str = "",
    connection_id: str = "",
    profile: str = "",
    yes: bool = False,
    mcp_url: str = DEFAULT_BASE_URL,
) -> CommandResult:
    """Rebind a connection to a target profile (section9.4).

    INV-SDK-CLIENT-01-C-004: Must verify post-fix against server truth.
    INV-SDK-CLIENT-01-C-006: Uses idempotent dispatch semantics.
    """
    correlation_id = str(uuid.uuid4())
    proof = DoctorProofBundle(correlation_id=correlation_id)

    if not host and not connection_id:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "invalid_input", "correlation_id": correlation_id},
            summary="Provide --host or --connection-id.",
            next_steps=["keyhole connection rebind --host vscode --profile paul"],
        )

    if not profile:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "invalid_input", "correlation_id": correlation_id},
            summary="Provide --profile to specify the target principal.",
            next_steps=["keyhole connection rebind --host vscode --profile paul"],
        )

    # 1. Auth check
    store = CredentialStore()
    session = store.load()
    if session is None:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "connection_not_authenticated", "correlation_id": correlation_id},
            summary="Not authenticated.",
            next_steps=["Run 'keyhole login' first."],
        )

    # 2. Identity snapshot
    identity_snapshot = {}
    try:
        whoami = WhoamiClient(mcp_base_url=mcp_url)
        resp = whoami.whoami(session.access_token)
        identity_snapshot = {
            "user_id": getattr(resp, "user_id", ""),
            "username": getattr(resp, "username", ""),
            "email": getattr(resp, "email", ""),
        }
    except Exception:
        pass  # non-fatal

    proof.record_event("identity_snapshot", identity_snapshot)

    # 3. Confirmation gate
    if not yes:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={
                "error_class": "confirmation_required",
                "host": host,
                "connection_id": connection_id,
                "target_profile": profile,
                "correlation_id": correlation_id,
            },
            summary=(
                f"Rebind requires confirmation. "
                f"Use --yes to confirm rebinding to profile '{profile}'."
            ),
            next_steps=[
                f"keyhole connection rebind --host {host or connection_id} --profile {profile} --yes"
            ],
        )

    # 4. Build request and dispatch
    request = RebindRequest(
        connection_id=connection_id,
        host_id=host,
        target_profile=profile,
        target_user_id=identity_snapshot.get("user_id", ""),
        correlation_id=correlation_id,
    )

    proof.record_event("rebind_request", request.to_proof_dict())

    client = ConnectionIdentityClient(mcp_base_url=mcp_url)
    try:
        outcome = client.rebind(request, access_token=session.access_token)
    except ConnectionNetworkError as exc:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": exc.error_class, "reason": exc.reason, "correlation_id": correlation_id},
            summary=f"Network error: {exc}",
            next_steps=exc.repair_suggestions,
        )
    except ConnectionIdentityError as exc:
        return CommandResult(
            command="connection_rebind",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": exc.error_class, "reason": exc.reason, "correlation_id": correlation_id},
            summary=str(exc),
            next_steps=exc.repair_suggestions,
        )

    proof.record_event("rebind_outcome", outcome.safe_summary())

    is_success = outcome.status in (RebindStatus.ACCEPTED, RebindStatus.REBOUND, RebindStatus.REPLAYED)

    # 5. Post-fix verification (section12.3, INV-SDK-CLIENT-01-C-004)
    verification = {}
    if is_success:
        try:
            verify_info = client.connection_inspect(
                access_token=session.access_token,
                host_id=host,
                connection_id=connection_id or outcome.connection_id,
                correlation_id=correlation_id,
            )
            verification = {
                "verified": verify_info.principal == profile or verify_info.user_id == identity_snapshot.get("user_id", ""),
                "post_fix_principal": verify_info.principal,
                "post_fix_user_id": verify_info.user_id,
            }
        except Exception:
            verification = {"verified": False, "error": "verification_failed"}

        proof.record_event("post_fix_verification", verification)

    # 6. Write proof artifacts
    try:
        proof.write(
            report=outcome.to_dict(),
            local_profile=identity_snapshot,
            requested_fix={"action": "rebind", "host_id": host, "target_profile": profile},
            verification=verification,
            success=is_success,
        )
    except Exception:
        pass  # proof write is non-fatal

    # 7. Build result
    status_icons = {
        RebindStatus.ACCEPTED: "OK",
        RebindStatus.REBOUND: "OK",
        RebindStatus.REPLAYED: "↻",
        RebindStatus.DEFERRED: "?",
        RebindStatus.REJECTED: "✗",
    }
    icon = status_icons.get(outcome.status, "?")

    next_steps = []
    if is_success:
        next_steps.append(f"keyhole connection inspect --host {host}" if host else "keyhole connections list")
    else:
        next_steps.extend(outcome.repair_guidance)

    return CommandResult(
        command="connection_rebind",
        success=is_success,
        exit_code=EXIT_SUCCESS if is_success else EXIT_FAILURE,
        data={
            "status": outcome.status.value,
            "connection_id": outcome.connection_id,
            "old_principal": outcome.old_principal,
            "new_principal": outcome.new_principal,
            "run_id": outcome.run_id,
            "verification": verification,
            "correlation_id": correlation_id,
        },
        summary=f"{icon} Rebind {outcome.status.value}: {outcome.old_principal} -> {outcome.new_principal}",
        next_steps=next_steps,
    )
