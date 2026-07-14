"""`keyhole whoami` — identity inspection command.

Implements §8.2 of SDK-CLIENT-01 and SDK-CLIENT-29: surfaces the
sanitized ``actor_envelope`` returned by the MCP boundary.

Flow:
  1. Load local credential/session
  2. Call the server identity endpoint (single source of actor truth)
  3. Render returned identity context, including actor envelope
  4. Surface mode and workspace context

The CLI never decodes the JWT to derive identity. JWT inspection is
diagnostic only; ``GET /mcp/v1/whoami`` is authoritative.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from keyhole_cli.result import CommandResult, EXIT_SUCCESS, EXIT_FAILURE
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.auth_bootstrap.actor_envelope import ActorEnvelope
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.errors import AuthBootstrapError
from keyhole_sdk.auth_bootstrap.whoami import WhoamiClient
from keyhole_sdk.config import DEFAULT_BASE_URL


def _envelope_to_data(envelope: Optional[ActorEnvelope]) -> Optional[Dict[str, Any]]:
    """Render the envelope into a redaction-safe dict for the data block."""
    if envelope is None:
        return None
    return envelope.safe_summary()


def run_whoami(
    *,
    mcp_base_url: str = DEFAULT_BASE_URL,
    show_envelope: bool = False,
) -> CommandResult:
    """Load stored credentials and inspect identity via whoami."""
    store = CredentialStore()

    # Check for stored session
    session = store.load()
    if session is None:
        return CommandResult(
            command="whoami",
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated — no stored credentials found.",
            next_steps=["Run 'keyhole login' to authenticate."],
        )

    access_token = session.access_token
    if session.is_expired:
        try:
            access_token = get_fresh_token()
            refreshed = store.load()
            if refreshed is not None:
                session = refreshed
        except Exception:
            return CommandResult(
                command="whoami",
                success=False,
                exit_code=EXIT_FAILURE,
                data={"expired": True},
                summary="Session expired and refresh failed.",
                next_steps=[
                    "Run 'keyhole login' to re-authenticate.",
                    "Run 'keyhole login --force' to force a fresh login.",
                ],
            )

    # Call whoami
    client = WhoamiClient(mcp_base_url=mcp_base_url)
    try:
        whoami = client.whoami(access_token)
    except AuthBootstrapError as exc:
        return CommandResult(
            command="whoami",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": exc.error_class},
            summary=str(exc),
            next_steps=exc.repair_suggestions or [
                "Run 'keyhole login' to re-authenticate."
            ],
        )

    # Build identity data for display
    data = {
        "user_id": whoami.user_id,
        "tenant_id": whoami.tenant_id,
        "org_id": whoami.org_id,
        "cohort_id": whoami.cohort_id,
        "worker_id": whoami.worker_id,
        "workspace_id": whoami.workspace_id,
        "plan": whoami.plan,
        "mode": whoami.mode.value,
    }

    if whoami.display_name:
        data["display_name"] = whoami.display_name
    if whoami.roles:
        data["roles"] = whoami.roles
    if whoami.limits:
        data["limits"] = whoami.limits

    # SDK-CLIENT-29: surface the server-resolved actor envelope.
    envelope_data = _envelope_to_data(whoami.actor_envelope)
    warnings: list[str] = []
    if envelope_data is not None:
        data["actor_envelope"] = envelope_data
        data["actor_envelope_present"] = True
    else:
        data["actor_envelope_present"] = False
        warnings.append(
            "actor_envelope_missing: the server did not return an actor "
            "envelope. Confirm SDK-SERVER-29 is deployed and promoted."
        )

    data["show_envelope"] = bool(show_envelope)

    mode_label = whoami.mode.value
    next_steps = [
        "Run 'keyhole init vertical' to scaffold a governed repository.",
        "Run 'keyhole ingest .' to analyze an existing repository.",
        "Run 'keyhole validate' to validate your workspace.",
    ]

    return CommandResult(
        command="whoami",
        success=True,
        exit_code=EXIT_SUCCESS,
        data=data,
        warnings=warnings,
        summary=f"Identity verified (mode: {mode_label})",
        next_steps=next_steps,
    )
