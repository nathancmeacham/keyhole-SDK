"""``keyhole auth doctor`` — local auth diagnostics (SDK-CLIENT-29).

Diagnostic-only.  This command does not mint identity, decide
authorization, or override server truth.  All authoritative checks
go through ``GET /mcp/v1/whoami``.

Checks performed (each labeled pass / warn / fail):

  1. credential file exists and readable
  2. token not expired (JWT ``exp`` inspection — diagnostic only)
  3. issuer is the keyhole-mcp realm
  4. azp / client_id appears to be ``keyhole-cli``
  5. MCP /whoami reachable
  6. server returned ``actor_envelope``
  7. ``actor_envelope.human_principal.realm == 'kh-prod'``
  8. ``actor_envelope.acting_principal.realm == 'keyhole-mcp'``
  9. ``actor_envelope.acting_principal.client_id == 'keyhole-cli'``
 10. direct kh-prod token NOT in stored credential
 11. write idempotency headers available (registry probe)

JWT inspection is diagnostic only.  The MCP server is the sole
authority for actor truth.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, List, Optional, Tuple

from keyhole_cli.result import CommandResult, EXIT_FAILURE, EXIT_SUCCESS
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.errors import AuthBootstrapError
from keyhole_sdk.auth_bootstrap.whoami import WhoamiClient
from keyhole_sdk.config import (
    DEFAULT_AUTH_SERVER,
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_ID,
    DEFAULT_REALM,
)
from keyhole_sdk.transport.operation_registry import get_operation


_EXPECTED_REALM = "keyhole-mcp"
_EXPECTED_CLIENT_ID = DEFAULT_CLIENT_ID  # "keyhole-cli"
_EXPECTED_HUMAN_REALM = "kh-prod"


def _decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """Diagnostic-only JWT payload decoding.

    The decoded claims are NEVER used as authority. They are only
    surfaced to the operator to help diagnose CLI configuration drift.
    """
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None


def _check(name: str, status: str, detail: str) -> Dict[str, str]:
    """Build a single check record."""
    return {"name": name, "status": status, "detail": detail}


def _looks_like_kh_prod_issuer(iss: str) -> bool:
    """Heuristic: issuer string contains ``kh-prod`` realm path."""
    return "/realms/kh-prod" in (iss or "")


def _looks_like_keyhole_mcp_issuer(iss: str) -> bool:
    return "/realms/keyhole-mcp" in (iss or "")


def run_auth_doctor(
    *,
    mcp_base_url: str = DEFAULT_BASE_URL,
    auth_server: str = DEFAULT_AUTH_SERVER,
) -> CommandResult:
    """Run local auth diagnostics."""
    checks: List[Dict[str, str]] = []
    overall_pass = True

    # 1. Credential file exists ------------------------------------------------
    store = CredentialStore()
    session = store.load()
    if session is None:
        checks.append(_check(
            "credential_file",
            "fail",
            "No credentials found. Run `keyhole login`.",
        ))
        return CommandResult(
            command="auth doctor",
            success=False,
            exit_code=EXIT_FAILURE,
            data={"checks": checks, "auth_server_default": auth_server},
            summary="Auth doctor: not authenticated.",
            next_steps=["Run `keyhole login`."],
        )
    checks.append(_check(
        "credential_file",
        "pass",
        f"Loaded credentials from {store.credentials_path}",
    ))

    # 2. Token not expired -----------------------------------------------------
    if session.is_expired:
        overall_pass = False
        checks.append(_check(
            "token_not_expired",
            "fail",
            "Stored access token is expired. Run `keyhole login`.",
        ))
    else:
        checks.append(_check(
            "token_not_expired",
            "pass",
            "Stored access token is not expired (per local clock).",
        ))

    # 3-4. JWT issuer / azp diagnostics (NOT authoritative) --------------------
    payload = _decode_jwt_payload(session.access_token) or {}
    iss = str(payload.get("iss", ""))
    azp = str(payload.get("azp") or payload.get("client_id") or "")

    if _looks_like_keyhole_mcp_issuer(iss):
        checks.append(_check(
            "jwt_issuer_realm",
            "pass",
            f"JWT iss looks like keyhole-mcp realm ({iss}).",
        ))
    elif _looks_like_kh_prod_issuer(iss):
        overall_pass = False
        checks.append(_check(
            "jwt_issuer_realm",
            "fail",
            (
                f"JWT iss is the kh-prod issuer ({iss}). "
                "The CLI must use the keyhole-mcp realm. "
                "Run `keyhole login` to refresh through the brokered flow."
            ),
        ))
    else:
        checks.append(_check(
            "jwt_issuer_realm",
            "warn",
            f"Could not confirm JWT issuer realm (iss={iss or 'unknown'}). Diagnostic only.",
        ))

    if azp == _EXPECTED_CLIENT_ID:
        checks.append(_check(
            "jwt_azp_client_id",
            "pass",
            f"JWT azp/client_id is {_EXPECTED_CLIENT_ID}.",
        ))
    elif azp:
        checks.append(_check(
            "jwt_azp_client_id",
            "warn",
            f"JWT azp/client_id is {azp!r}, expected {_EXPECTED_CLIENT_ID!r}. Diagnostic only.",
        ))
    else:
        checks.append(_check(
            "jwt_azp_client_id",
            "warn",
            "JWT azp/client_id not present. Diagnostic only.",
        ))

    # 10. Direct kh-prod token NOT in stored credential ------------------------
    # (placed early so we surface it before contacting the server.)
    if _looks_like_kh_prod_issuer(iss):
        checks.append(_check(
            "no_direct_kh_prod_token",
            "fail",
            "Stored credential is a direct kh-prod token. CLI must use keyhole-mcp realm.",
        ))
        overall_pass = False
    else:
        checks.append(_check(
            "no_direct_kh_prod_token",
            "pass",
            "Stored credential is not a direct kh-prod token.",
        ))

    # 5. /whoami reachable + 6-9. envelope checks ------------------------------
    whoami_client = WhoamiClient(mcp_base_url=mcp_base_url)
    envelope_safe: Optional[Dict[str, Any]] = None
    try:
        whoami = whoami_client.whoami(session.access_token)
        checks.append(_check(
            "whoami_reachable",
            "pass",
            f"GET {mcp_base_url}/mcp/v1/whoami succeeded.",
        ))
    except AuthBootstrapError as exc:
        overall_pass = False
        checks.append(_check(
            "whoami_reachable",
            "fail",
            f"/whoami failed: {exc}",
        ))
        whoami = None
    except Exception as exc:
        overall_pass = False
        checks.append(_check(
            "whoami_reachable",
            "fail",
            f"/whoami request raised {type(exc).__name__}: {exc}",
        ))
        whoami = None

    if whoami is not None:
        env = whoami.actor_envelope
        if env is None:
            overall_pass = False
            checks.append(_check(
                "actor_envelope_present",
                "fail",
                "Server did not return actor_envelope. Confirm SDK-SERVER-29 promoted.",
            ))
        else:
            envelope_safe = env.safe_summary()
            checks.append(_check(
                "actor_envelope_present",
                "pass",
                "Server returned actor_envelope.",
            ))

            hp_realm = (env.human_principal.realm if env.human_principal else None) or ""
            ap_realm = (env.acting_principal.realm if env.acting_principal else None) or ""
            ap_client = (env.acting_principal.client_id if env.acting_principal else None) or ""

            if hp_realm == _EXPECTED_HUMAN_REALM:
                checks.append(_check(
                    "human_principal_realm",
                    "pass",
                    f"human_principal.realm == {_EXPECTED_HUMAN_REALM}",
                ))
            else:
                overall_pass = False
                checks.append(_check(
                    "human_principal_realm",
                    "fail",
                    f"human_principal.realm == {hp_realm!r}, expected {_EXPECTED_HUMAN_REALM!r}",
                ))

            if ap_realm == _EXPECTED_REALM:
                checks.append(_check(
                    "acting_principal_realm",
                    "pass",
                    f"acting_principal.realm == {_EXPECTED_REALM}",
                ))
            else:
                overall_pass = False
                checks.append(_check(
                    "acting_principal_realm",
                    "fail",
                    f"acting_principal.realm == {ap_realm!r}, expected {_EXPECTED_REALM!r}",
                ))

            if ap_client == _EXPECTED_CLIENT_ID:
                checks.append(_check(
                    "acting_principal_client_id",
                    "pass",
                    f"acting_principal.client_id == {_EXPECTED_CLIENT_ID}",
                ))
            else:
                overall_pass = False
                checks.append(_check(
                    "acting_principal_client_id",
                    "fail",
                    f"acting_principal.client_id == {ap_client!r}, expected {_EXPECTED_CLIENT_ID!r}",
                ))

    # 11. Write idempotency headers available ----------------------------------
    descriptor = get_operation("run.start")
    if descriptor and descriptor.idempotency_required:
        checks.append(_check(
            "write_idempotency_headers",
            "pass",
            "Operation registry confirms run.start requires idempotency headers.",
        ))
    else:
        overall_pass = False
        checks.append(_check(
            "write_idempotency_headers",
            "fail",
            "run.start descriptor missing or idempotency_required=False.",
        ))

    summary = "Auth doctor: all checks passed." if overall_pass else "Auth doctor: one or more checks failed."
    next_steps: List[str] = []
    if not overall_pass:
        next_steps.append("Run `keyhole login --force` to refresh credentials.")
        next_steps.append("Confirm SDK-SERVER-29 is promoted on the MCP boundary.")

    return CommandResult(
        command="auth doctor",
        success=overall_pass,
        exit_code=EXIT_SUCCESS if overall_pass else EXIT_FAILURE,
        data={
            "checks": checks,
            "actor_envelope": envelope_safe,
            "auth_server_default": auth_server,
            "mcp_base_url": mcp_base_url,
            "expected_realm": _EXPECTED_REALM,
            "expected_client_id": _EXPECTED_CLIENT_ID,
        },
        summary=summary,
        next_steps=next_steps,
    )
