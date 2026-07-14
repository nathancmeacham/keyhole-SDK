"""`keyhole explain run`, `keyhole inspect`, `keyhole support-bundle`.

SDK-CLIENT-20: Governance Explainability and Support Bundles.

Makes governed execution legible — explains what happened, why,
what artifacts exist, and what to do next.

§3: Never blur layers — request truth, run truth, context truth,
    event/proof truth, rendered explanation are distinct.
§10: Support bundles must not include secrets, tokens, or credential stores.
"""

from __future__ import annotations

import json
from pathlib import Path

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.explain import (
    RequestInspectionResult,
    RunExplanation,
    assemble_request_inspection,
    assemble_run_explanation,
    assemble_support_bundle,
    emit_bundle_proof,
    emit_explain_proof,
    map_explain_repair,
    render_explanation,
    render_inspection,
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
# keyhole explain run <run-id>
# ──────────────────────────────────────────────────────────────

def run_explain_run(
    *,
    run_id: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    state_dir: str = "",
) -> CommandResult:
    """Execute ``keyhole explain run <run-id>``.

    Fetches run status, assembles explanation, renders it, and
    emits proof artifacts to the state directory.

    §3: Explanation layers are kept distinct — status, context,
        event, proof each remain separate concern surfaces.
    §12.5: Non-terminal outcomes are never rendered as completed.
    §12.4: Repair guidance is always included on non-success.
    """
    command_label = "keyhole explain run"

    if not run_id or not run_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No run ID provided.",
            next_steps=map_explain_repair("missing_run_id"),
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

    response_data = status_result.response_data or {}

    explanation: RunExplanation = assemble_run_explanation(
        response_data,
        run_id=run_id,
        request_id=getattr(status_result, "request_id", "") or "",
        correlation_id=getattr(status_result, "correlation_id", "") or "",
    )

    rendered = render_explanation(explanation)

    resolved_state_dir = _resolve_state_dir(state_dir, repo_path)
    proof_dir: Path | None = None
    try:
        proof_dir = emit_explain_proof(
            state_dir=resolved_state_dir,
            run_id=run_id,
            explanation=explanation,
        )
    except OSError:
        pass  # Proof emission failure must not block the response

    data = explanation.to_proof_dict()
    if proof_dir is not None:
        data["proof_dir"] = str(proof_dir)

    if not status_result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=rendered,
            data=data,
            next_steps=explanation.repair_guidance or map_explain_repair("observation_failed"),
        )

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=rendered,
        data=data,
        next_steps=explanation.repair_guidance,
    )


# ──────────────────────────────────────────────────────────────
# keyhole inspect <request-id>
# ──────────────────────────────────────────────────────────────

def run_inspect_request(
    *,
    request_id: str,
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    state_dir: str = "",
    repo_dir: str = ".",
) -> CommandResult:
    """Execute ``keyhole inspect <request-id>``.

    Looks up a request by ID, assembles inspection result, and
    Returns an inspection-oriented CommandResult.

    §3: Request truth and run truth are separate concern surfaces.
    §7.2: Inspection shows whether request was executed, replayed, or deferred.
    """
    command_label = "keyhole inspect"

    if not request_id or not request_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No request ID provided.",
            next_steps=map_explain_repair("missing_request_id"),
        )

    request_id = request_id.strip()
    repo_path = Path(repo_dir).resolve()
    transport, _cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        # Attempt to retrieve run status by request_id lookup.
        # The server may return run metadata keyed by request_id.
        status_result = fetch_run_status(
            transport=transport,
            run_id=request_id,  # boundary: request_id may double as run_id
            repo_name=_repo_name(repo_path),
        )
    finally:
        transport.close()

    response_data = status_result.response_data or {}

    # Inject request_id context if server doesn't echo it
    if "request_id" not in response_data:
        response_data = dict(response_data, request_id=request_id)

    inspection: RequestInspectionResult = assemble_request_inspection(
        response_data,
        request_id=request_id,
    )

    rendered = render_inspection(inspection)

    resolved_state_dir = _resolve_state_dir(state_dir, repo_path)
    proof_dir: Path | None = None
    try:
        # Write inspection result to state dir
        state_path = Path(resolved_state_dir) / "inspect" / _safe_dir_name(request_id)
        state_path.mkdir(parents=True, exist_ok=True)
        (state_path / "inspection.json").write_text(
            json.dumps(inspection.to_proof_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        proof_dir = state_path
    except OSError:
        pass

    data = inspection.to_proof_dict()
    if proof_dir is not None:
        data["proof_dir"] = str(proof_dir)

    if not status_result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=rendered,
            data=data,
            next_steps=inspection.repair_guidance or map_explain_repair("request_not_found"),
        )

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=rendered,
        data=data,
        next_steps=inspection.repair_guidance,
    )


# ──────────────────────────────────────────────────────────────
# keyhole support-bundle <run-id|request-id>
# ──────────────────────────────────────────────────────────────

def run_support_bundle(
    *,
    run_id: str = "",
    request_id: str = "",
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    state_dir: str = "",
    cli_version: str = "0.2.0",
) -> CommandResult:
    """Execute ``keyhole support-bundle <run-id|request-id>``.

    Assembles a portable, bounded support artifact covering:
    summary, request, run, context, events, proof_refs, outcome,
    repair, and metadata.

    §10: Bundle must not include tokens, secrets, or credential stores.
    §14.2: Writes 9 artifact files to <state_dir>/support_bundle/<id>/.
    """
    command_label = "keyhole support-bundle"

    effective_id = (run_id or request_id or "").strip()
    if not effective_id:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="Provide a run ID or request ID for the support bundle.",
            next_steps=map_explain_repair("missing_run_id"),
        )

    repo_path = Path(repo_dir).resolve()
    transport, _cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        status_result = fetch_run_status(
            transport=transport,
            run_id=effective_id,
            repo_name=_repo_name(repo_path),
        )
    finally:
        transport.close()

    response_data = status_result.response_data or {}

    explanation: RunExplanation = assemble_run_explanation(
        response_data,
        run_id=run_id or effective_id,
        request_id=request_id or getattr(status_result, "request_id", "") or "",
        correlation_id=getattr(status_result, "correlation_id", "") or "",
    )

    # Request inspection from same data
    inspect_data = dict(response_data)
    if "request_id" not in inspect_data:
        inspect_data["request_id"] = request_id or effective_id

    inspection: RequestInspectionResult = assemble_request_inspection(
        inspect_data,
        request_id=request_id or effective_id,
    )

    bundle = assemble_support_bundle(
        run_id=run_id or effective_id,
        request_id=request_id or effective_id,
        explanation=explanation,
        inspection=inspection,
        cli_version=cli_version,
    )

    resolved_state_dir = _resolve_state_dir(state_dir, repo_path)
    proof_dir: Path | None = None
    try:
        proof_dir = emit_bundle_proof(
            state_dir=resolved_state_dir,
            run_id_or_request_id=effective_id,
            bundle=bundle,
        )
    except OSError:
        pass

    data = {
        "run_id": bundle.run_id,
        "request_id": bundle.request_id,
        "missing_sections": bundle.missing_sections,
        "omission_notes": bundle.omission_notes,
        "assembled_at": bundle.assembled_at,
    }
    if proof_dir is not None:
        data["bundle_dir"] = str(proof_dir)

    summary_lines = [f"Support bundle assembled for: {effective_id}"]
    if bundle.missing_sections:
        summary_lines.append(f"Missing sections: {', '.join(bundle.missing_sections)}")
    if proof_dir:
        summary_lines.append(f"Written to: {proof_dir}")
    summary = "\n".join(summary_lines)

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=summary,
        data=data,
        next_steps=[],
    )


# ──────────────────────────────────────────────────────────────
# Shared helpers (same pattern as budget_cmd.py)
# ──────────────────────────────────────────────────────────────

def _build_transport(
    mcp_url: str,
    keyhole_home: str,
) -> tuple[GovernedTransport, CredentialStore]:
    """Build a GovernedTransport from the credential store."""
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


def _safe_dir_name(raw: str, max_len: int = 64) -> str:
    """Convert an ID to a filesystem-safe directory name."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)
    return safe[:max_len] or "unknown"
