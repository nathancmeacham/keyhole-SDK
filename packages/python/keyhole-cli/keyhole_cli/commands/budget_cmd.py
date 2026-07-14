"""`keyhole runs budget` — Budget, Limit, and Overload Visibility.

SDK-CLIENT-19: Turns runtime pressure into part of the product experience.

Makes existing server-side budget and overload behavior usable at
the client boundary: deterministic rendering, proof emission, and
repair-oriented next actions.
"""

from __future__ import annotations

from pathlib import Path

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.budget import (
    BudgetPressureRequest,
    LimitOutcomeClass,
    classify_retry_posture,
    emit_budget_proof,
    map_budget_repair,
    parse_limit_outcome,
    render_budget_summary,
)
from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
from keyhole_sdk.run_lifecycle.status import fetch_run_status
from keyhole_sdk.transport.client import GovernedTransport

from keyhole_cli.result import (
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
    CommandResult,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


# ──────────────────────────────────────────────────────────────
# keyhole runs budget <run-id>
# ──────────────────────────────────────────────────────────────

def run_budget(
    *,
    run_id: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    state_dir: str = "",
) -> CommandResult:
    """Execute ``keyhole runs budget <run-id>``.

    Fetches run status, parses budget/limit posture, emits proof, and
    returns a deterministic CommandResult with human-readable summary.

    §15.3: Never collapses overload into generic failure — classifies it.
    §14.4: Emits proof artifacts to tool-owned state dir.
    """
    command_label = "keyhole runs budget"

    if not run_id or not run_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No run ID provided.",
            next_steps=map_run_lifecycle_repair("missing_run_id"),
        )

    run_id = run_id.strip()
    repo_path = Path(repo_dir).resolve()
    transport, _cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        status_result = fetch_run_status(
            transport=transport,
            run_id=run_id,
            repo_name=_repo_name(repo_path),
        )
    finally:
        transport.close()

    # ── Parse budget posture from run status response ─────────────────────
    response_data = status_result.response_data if status_result.response_data else {}
    limit_result = parse_limit_outcome(
        response_data,
        http_status_code=status_result.http_status_code if hasattr(status_result, "http_status_code") else 200,
        run_id=run_id,
        request_id=getattr(status_result, "request_id", ""),
        correlation_id=getattr(status_result, "correlation_id", ""),
    )

    # ── Emit proof ────────────────────────────────────────────────────────
    resolved_state_dir = _resolve_state_dir(state_dir, repo_path)
    request_meta = BudgetPressureRequest(
        run_id=run_id,
        mcp_url=mcp_url,
    )
    proof_dir: Path | None = None
    try:
        proof_dir = emit_budget_proof(
            state_dir=resolved_state_dir,
            run_id=run_id,
            result=limit_result,
            request=request_meta,
        )
    except OSError:
        # Proof emission failure must not block the response
        pass

    # ── Render summary ────────────────────────────────────────────────────
    summary = render_budget_summary(limit_result)
    retry_posture = classify_retry_posture(limit_result)

    # ── Build response data ───────────────────────────────────────────────
    data = limit_result.to_proof_dict()
    data["retry_posture"] = retry_posture
    if proof_dir is not None:
        data["proof_dir"] = str(proof_dir)

    # ── Status-fetch errors still get budget output if available ─────────
    if not status_result.success and limit_result.outcome_class == LimitOutcomeClass.NO_PRESSURE_DATA:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=status_result.reason or "Run status retrieval failed.",
            data={
                "run_id": run_id,
                "error_class": getattr(status_result, "error_class", ""),
                "limit_outcome": limit_result.outcome_class.value,
            },
            next_steps=status_result.repair_guidance or map_run_lifecycle_repair("observation_failed"),
        )

    next_steps = limit_result.repair_guidance or map_budget_repair(limit_result.outcome_class.value)

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=summary,
        data=data,
        next_steps=next_steps,
    )


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _build_transport(
    mcp_url: str,
    keyhole_home: str,
) -> tuple[GovernedTransport, CredentialStore]:
    """Build a GovernedTransport from credential store."""
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = ""
    auth_provider = BearerTokenProvider(token=token) if token else None
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )
    return transport, cred_store


def _repo_name(repo_path: Path) -> str:
    """Best-effort repo name from .keyhole/config.json or directory name."""
    keyhole_config = repo_path / ".keyhole" / "config.json"
    if keyhole_config.exists():
        try:
            import json
            data = json.loads(keyhole_config.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("repo_name"):
                return data["repo_name"]
        except (ValueError, OSError):
            pass
    return repo_path.name


def _resolve_state_dir(state_dir: str, repo_path: Path) -> Path:
    """Resolve proof state directory."""
    if state_dir:
        return Path(state_dir)
    return repo_path / ".keyhole" / "runs"
