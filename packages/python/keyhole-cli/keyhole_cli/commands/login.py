"""`keyhole login` — authentication bootstrap command.

Implements §8.1 of SDK-CLIENT-01: `keyhole login` command.

Hardened flow (server-aligned identity governance):
  1. Initiate auth bootstrap
  2. Complete auth flow (PKCE or device)
  3. Acquire governed identity via /whoami (mandatory)
  4. Persist credentials ONLY after identity confirmed
  5. Render success ONLY after governed closure

SDK-CLIENT-23 §F: Login preflight guard.
  Before persisting credentials, check host attestation coherence.
  Fresh confirmed conflict blocks bind by default unless
  --allow-split-identity is specified.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import typer

from keyhole_cli.result import CommandResult, EXIT_SUCCESS, EXIT_FAILURE
from keyhole_sdk.auth_bootstrap.client import AuthBootstrapClient
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.models import AuthFlowType, LoginResult
from keyhole_sdk.auth_bootstrap.proof import AuthProofBundle
from keyhole_sdk.config import DEFAULT_AUTH_SERVER, DEFAULT_BASE_URL
from keyhole_sdk.doctor.models import CoherenceVerdict, IdentityPolicyOverride
from keyhole_sdk.host.attestation_store import (
    load_attestations,
    load_identity_policy,
    save_identity_policy,
    save_principal_hint,
)
from keyhole_sdk.host.coherence_engine import classify_coherence


def _auto_detect_flow(
    client: AuthBootstrapClient,
    current_flow: AuthFlowType,
    current_email: Optional[str],
) -> tuple[AuthFlowType, Optional[str]]:
    """Auto-detect the best login flow from prior session state.

    When the user ran ``keyhole login`` without ``--flow``, check whether
    expired credentials exist from a prior passwordless login.  If so,
    re-use the passwordless flow and recover the email from the stored
    session.  This prevents sending users to a Keycloak browser form
    they can't complete (because their account was created through the
    MCP boundary's email-code path, not through Keycloak).

    Returns (flow_type, email) — potentially updated.
    """
    try:
        session = client.credential_store.load()
    except Exception:
        return current_flow, current_email

    if session is None:
        return current_flow, current_email

    # If the prior session used passwordless, switch to it
    if session.flow_type == AuthFlowType.PASSWORDLESS:
        # Try to recover the email from the stored session or whoami cache
        recovered_email = current_email
        if not recovered_email:
            recovered_email = _recover_email_from_state()

        if recovered_email:
            typer.echo(
                f"\nPrior session used passwordless login. "
                f"Re-using passwordless flow for {recovered_email}.\n"
                f"  (Override with: keyhole login --flow device)\n",
                err=True,
            )
            return AuthFlowType.PASSWORDLESS, recovered_email
        else:
            typer.echo(
                "\nPrior session used passwordless login but no email is available.\n"
                "  Use: keyhole login --flow passwordless --email you@example.com\n"
                "  Or:  keyhole login --flow device  (for device authorization)\n",
                err=True,
            )

    return current_flow, current_email


def _recover_email_from_state() -> Optional[str]:
    """Try to recover the user's email from local state artifacts.

    Checks (in order):
      1. Proof bundle identity_context.json (from last successful whoami)
      2. Principal hint (from SDK-CLIENT-23 host attestation)
    """
    import json
    import os
    from pathlib import Path

    keyhole_home = Path(os.environ.get("KEYHOLE_HOME", "")) if os.environ.get("KEYHOLE_HOME") else Path.home() / ".keyhole"

    # 1. Check proof bundle identity context
    identity_path = keyhole_home / "proof_bundle" / "identity_context.json"
    try:
        if identity_path.exists():
            data = json.loads(identity_path.read_text(encoding="utf-8"))
            email = data.get("email")
            if email and "@" in email:
                return email
            user_id = data.get("user_id", "")
            if user_id and "@" in user_id:
                return user_id
    except Exception:
        pass

    # 2. Check principal hint (SDK-CLIENT-23)
    try:
        hint = load_principal_hint(keyhole_home=keyhole_home)
        if hint and "@" in hint:
            return hint
    except Exception:
        pass

    return None


def _resolve_proof_dir() -> "Path":
    """Resolve KEYHOLE_HOME for proof bundle output."""
    import os
    from pathlib import Path
    keyhole_home = os.environ.get("KEYHOLE_HOME")
    if keyhole_home:
        return Path(keyhole_home)
    return Path.home() / ".keyhole"


def run_login(
    *,
    flow: str = "device",
    force: bool = False,
    auth_server_url: str = DEFAULT_AUTH_SERVER,
    client_id: str = "keyhole-cli",
    mcp_base_url: str = DEFAULT_BASE_URL,
    username: Optional[str] = None,
    password: Optional[str] = None,
    email: Optional[str] = None,
    realm: str = "kh-prod",
    allow_split_identity: bool = False,
    _flow_explicit: bool = False,
) -> CommandResult:
    """Execute the full login flow and return a structured result."""
    correlation_id = str(uuid.uuid4())
    proof = AuthProofBundle(correlation_id=correlation_id)

    # Resolve flow type
    try:
        flow_type = AuthFlowType(flow.lower())
    except ValueError:
        return CommandResult(
            command="login",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"error_class": "invalid_flow_type", "flow": flow},
            summary=f"Unknown flow type: {flow}. Use 'pkce', 'device', 'password', or 'passwordless'.",
            next_steps=["Use: keyhole login --flow device", "Or: keyhole login --flow passwordless --email you@example.com"],
        )

    proof.record_event("login_initiated", {
        "flow_type": flow_type.value,
        "force": force,
        "correlation_id": correlation_id,
    })

    client = AuthBootstrapClient(
        auth_server_url=auth_server_url,
        client_id=client_id,
        mcp_base_url=mcp_base_url,
    )

    # Smart flow auto-detection:
    # When the user didn't explicitly choose a flow and expired credentials
    # exist from a prior passwordless login, re-use passwordless + email.
    if not _flow_explicit and flow_type == AuthFlowType.DEVICE:
        flow_type, email = _auto_detect_flow(client, flow_type, email)

    status_messages: list[str] = []

    def on_status(msg: str) -> None:
        status_messages.append(msg)
        typer.echo(msg, err=True)

    def on_browser_url(url: str) -> None:
        proof.record_event("browser_url_presented", {"url_shown": True})
        typer.echo(f"\nOpen this URL in your browser to authenticate:\n  {url}\n", err=True)

    def on_device_code(device_resp) -> None:
        proof.record_event("device_code_presented", {
            "user_code": device_resp.user_code,
            "verification_uri": device_resp.verification_uri,
        })
        typer.echo(
            f"\n  Verification URL : {device_resp.verification_uri_complete or device_resp.verification_uri}"
            f"\n  User Code        : {device_resp.user_code}"
            f"\n\nVisit the URL above and enter the code to authenticate.\nWaiting...\n",
            err=True,
        )

    def on_code_prompt(login_resp) -> str:
        """Prompt the user for the 6-digit login code (passwordless flow)."""
        proof.record_event("passwordless_code_requested", {
            "user_id": login_resp.user_id,
            "email": login_resp.email,
        })
        return typer.prompt("Enter the 6-digit login code from your email")

    # Pre-flight notice: if no prior session exists at all, hint at registration.
    # Skip if we already auto-detected a flow (the user clearly has prior state).
    if not _flow_explicit and not client.credential_store.load():
        typer.echo(
            "\nNo existing session found. "
            "If you haven't registered yet, create an account first:\n"
            "  keyhole register --email you@example.com "
            "--username yourname --display-name 'Your Name'\n",
            err=True,
        )

    result = client.login(
        flow_type=flow_type,
        force=force,
        correlation_id=correlation_id,
        on_browser_url=on_browser_url,
        on_device_code=on_device_code,
        on_code_prompt=on_code_prompt,
        on_status=on_status,
        username=username,
        password=password,
        email=email,
        realm=realm,
    )

    proof.record_event("login_completed", result.safe_summary())

    if result.success:
        # SDK-CLIENT-23 §F: Host coherence preflight guard
        coherence_block = _check_host_coherence(
            result=result,
            allow_split_identity=allow_split_identity,
        )
        if coherence_block is not None:
            proof.record_event("coherence_preflight_blocked", {
                "verdict": coherence_block.data.get("verdict", ""),
            })
            return coherence_block

        # Determine auth path for proof lineage
        auth_path = "session_reuse" if not force and result.credential_persisted else "device_flow"
        proof.record_event("auth_path_resolved", {"auth_path": auth_path})

        # Persist proof bundle to KEYHOLE_HOME
        try:
            proof.write(result, _resolve_proof_dir())
        except Exception:
            pass  # proof write failure is not a login failure

        return _success_result(result, proof, correlation_id, auth_path=auth_path)
    else:
        return _failure_result(result, proof, correlation_id)


def _check_host_coherence(
    *,
    result: LoginResult,
    allow_split_identity: bool,
) -> Optional[CommandResult]:
    """SDK-CLIENT-23 §F: Check host coherence before accepting login.

    Returns a CommandResult blocking login if a fresh confirmed conflict
    is detected and --allow-split-identity was not specified.
    Returns None if login should proceed.
    """
    whoami = result.whoami
    if not whoami:
        return None

    cli_principal = whoami.display_name or whoami.email or whoami.user_id or ""
    if not cli_principal:
        return None

    try:
        attestations = load_attestations()
        override = load_identity_policy()
    except Exception:
        # Storage errors are non-blocking for login
        return None

    if not attestations:
        return None

    coherence = classify_coherence(
        cli_principal=cli_principal,
        attestations=attestations,
        override=override,
    )

    if coherence.verdict == CoherenceVerdict.REJECT_HOST_CONFLICT:
        if allow_split_identity:
            # Record the override and proceed
            try:
                host_principal = (
                    coherence.conflicting_attestations[0].effective_principal
                    if coherence.conflicting_attestations
                    else ""
                )
                host_kind = (
                    coherence.conflicting_attestations[0].host_kind
                    if coherence.conflicting_attestations
                    else "unknown"
                )
                now = datetime.now(timezone.utc)
                policy = IdentityPolicyOverride(
                    override_type="allow_split_identity",
                    created_at=now.isoformat(),
                    target_principal=cli_principal,
                    conflicting_host_principal=host_principal,
                    host_kind=host_kind,
                    reason="User explicitly allowed split identity via --allow-split-identity",
                )
                save_identity_policy(policy)
            except Exception:
                pass  # override persistence failure is non-fatal
            return None

        # Block login with remediation steps
        return CommandResult(
            command="login",
            success=False,
            exit_code=EXIT_FAILURE,
            data={
                "error_class": "host_identity_conflict",
                "verdict": coherence.verdict.value,
                "cli_principal": cli_principal,
                "conflicting_hosts": [
                    {
                        "host_kind": a.host_kind,
                        "effective_principal": a.effective_principal,
                    }
                    for a in coherence.conflicting_attestations
                ],
            },
            summary=coherence.description,
            next_steps=coherence.fix_steps,
        )

    return None


def _success_result(
    result: LoginResult,
    proof: AuthProofBundle,
    correlation_id: str,
    *,
    auth_path: str = "unknown",
) -> CommandResult:
    """Build CommandResult for successful login."""
    whoami = result.whoami
    data = {
        "correlation_id": correlation_id,
        "flow_type": result.flow_type.value if result.flow_type else None,
        "mode": result.mode.value if result.mode else None,
        "auth_path": auth_path,
        "credential_persisted": result.credential_persisted,
        "verification_passed": result.verification_passed,
    }
    if whoami:
        data.update({
            "user_id": whoami.user_id,
            "tenant_id": whoami.tenant_id,
            "org_id": whoami.org_id,
            "display_name": whoami.display_name,
        })
        # SDK-CLIENT-29: report whether the server returned a sanitized
        # actor envelope.  Absent envelope is allowed (back-compat) but
        # surfaced as a warning so operators can confirm SDK-SERVER-29
        # has been promoted.
        data["actor_envelope_present"] = whoami.actor_envelope is not None

    warnings: list[str] = []
    if whoami and whoami.actor_envelope is None:
        warnings.append(
            "actor_envelope_missing: server did not include actor_envelope in /whoami "
            "(SDK-SERVER-29 not yet active?)."
        )

    mode_label = result.mode.value if result.mode else "unknown"
    next_steps = [
        "Run 'keyhole whoami' to inspect your identity.",
        "Run 'keyhole init vertical' to scaffold a governed repository.",
        "Run 'keyhole ingest .' to analyze an existing repository.",
    ]

    return CommandResult(
        command="login",
        success=True,
        exit_code=EXIT_SUCCESS,
        data=data,
        warnings=warnings,
        summary=f"Logged in successfully (mode: {mode_label})",
        next_steps=next_steps,
    )


def _failure_result(
    result: LoginResult,
    proof: AuthProofBundle,
    correlation_id: str,
) -> CommandResult:
    """Build CommandResult for failed login."""
    data = {
        "correlation_id": correlation_id,
        "error_class": result.error_class,
        "credential_persisted": result.credential_persisted,
        "verification_passed": result.verification_passed,
    }

    next_steps = list(result.repair_suggestions or ["Retry: keyhole login"])

    # If the failure suggests the user might not have an account, add registration guidance
    _account_error_classes = {
        "login_denied",
        "invalid_token",
        "expired_challenge",
        "whoami_verification_error",
        "incomplete_identity",
    }
    if result.error_class in _account_error_classes:
        register_hint = (
            "No account yet? Register first: "
            "keyhole register --email you@example.com "
            "--username yourname --display-name 'Your Name'"
        )
        if register_hint not in next_steps:
            next_steps.append(register_hint)

    return CommandResult(
        command="login",
        success=False,
        exit_code=EXIT_FAILURE,
        data=data,
        summary=result.error_message or "Login failed",
        next_steps=next_steps,
    )
