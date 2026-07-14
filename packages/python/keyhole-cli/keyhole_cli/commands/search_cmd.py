"""`keyhole search` — capability search command.

SDK-CLIENT-08: Capability Discovery and Resolution.

Searches the governed capability registry for matching capabilities.
Returns candidates with metadata, confidence, and repair guidance.
Never mutates the local repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.capability.models import (
    CapabilitySearchRequest,
    CapabilitySearchResult,
    RepoPosture,
)
from keyhole_sdk.capability.proof import emit_search_proof
from keyhole_sdk.capability.repair import map_capability_repair
from keyhole_sdk.capability.search import submit_capability_search
from keyhole_sdk.transport.client import GovernedTransport
from keyhole_sdk.transport.idempotency import generate_request_id

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_search(
    *,
    query: str,
    provider: str = "",
    version: str = "",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole search <query>``.

    Returns a CommandResult for the CLI to render.
    """
    command_label = "keyhole search"

    # ── Resolve credentials ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    session = cred_store.load()
    if session is None:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated. Run: keyhole login",
            data={"error_class": "NotAuthenticated", "is_local": True},
            next_steps=map_capability_repair("NotAuthenticated"),
        )
    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = session.access_token if session else ""

    if not token:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated. Run: keyhole login",
            data={"error_class": "NotAuthenticated", "is_local": True},
            next_steps=map_capability_repair("NotAuthenticated"),
        )

    # ── Build search request ──
    correlation_id = generate_request_id()
    request = CapabilitySearchRequest(
        query=query,
        provider=provider,
        version=version,
        correlation_id=correlation_id,
    )

    # ── Build transport and submit ──
    auth_provider = BearerTokenProvider(token=token)
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    try:
        result = submit_capability_search(
            transport=transport,
            request=request,
        )
    finally:
        transport.close()

    # ── Emit proof ──
    state_dir = _resolve_state_dir(keyhole_home)
    proof_dir = _safe_emit_proof(
        state_dir=state_dir,
        correlation_id=correlation_id,
        request=request,
        result=result,
    )

    # ── Render ──
    return _result_to_command_result(
        result=result,
        command_label=command_label,
        proof_dir=proof_dir,
    )


def _result_to_command_result(
    *,
    result: CapabilitySearchResult,
    command_label: str,
    proof_dir: Optional[Path],
) -> CommandResult:
    """Convert a CapabilitySearchResult to a CommandResult."""
    is_success = not result.error_class

    data: Dict[str, Any] = {
        "query": result.query,
        "total_count": result.total_count,
        "is_empty": result.is_empty,
        "correlation_id": result.correlation_id,
    }

    if result.candidates:
        data["candidates"] = [c.to_dict() for c in result.candidates]

    if result.error_class:
        data["error_class"] = result.error_class
    if result.reason:
        data["reason"] = result.reason
    if proof_dir:
        data["proof_dir"] = str(proof_dir)

    # Summary
    if result.error_class:
        summary = f"Search failed: {result.reason or result.error_class}"
    elif result.is_empty:
        summary = f"No capabilities found for query '{result.query}'."
    else:
        summary = (
            f"Found {result.total_count} capability "
            f"{'candidate' if result.total_count == 1 else 'candidates'} "
            f"for '{result.query}'."
        )

    # Next steps
    next_steps: List[str] = list(result.next_steps) if result.next_steps else []
    if is_success and not result.is_empty:
        next_steps.append(
            "Run: keyhole dependency resolve <capability> — to resolve a dependency."
        )

    return CommandResult(
        command=command_label,
        success=is_success,
        exit_code=EXIT_SUCCESS if is_success else EXIT_FAILURE,
        summary=summary,
        data=data,
        warnings=result.warnings or None,
        next_steps=next_steps or None,
    )


def _resolve_state_dir(keyhole_home: str) -> Path:
    """Resolve the tool-owned state directory."""
    if keyhole_home:
        return Path(keyhole_home) / "state"
    return Path.home() / ".keyhole" / "state"


def _safe_emit_proof(
    *,
    state_dir: Path,
    correlation_id: str,
    request: CapabilitySearchRequest,
    result: CapabilitySearchResult,
) -> Optional[Path]:
    """Emit search proof artifacts, returning None on I/O failure."""
    try:
        return emit_search_proof(
            state_dir=state_dir,
            correlation_id=correlation_id,
            request_dict=request.to_proof_dict(),
            result_dict=result.to_proof_dict(),
        )
    except OSError:
        return None
