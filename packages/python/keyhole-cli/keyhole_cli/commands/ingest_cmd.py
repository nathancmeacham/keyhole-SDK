"""`keyhole ingest` — repository ingestion command.

SDK-CLIENT-10: Repository Ingestion and Graph.

Scans a local repository, builds a deterministic ingestion package,
submits to the MCP boundary, and renders inferred capabilities with
confidence. Never mutates the target repo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.ingest.filter import IncludeExcludeFilter
from keyhole_sdk.ingest.models import (
    CompatibilityPosture,
    IngestionOutcome,
    IngestionRequest,
)
from keyhole_sdk.ingest.packager import build_ingestion_package
from keyhole_sdk.ingest.proof import emit_ingestion_proof
from keyhole_sdk.ingest.repair import map_ingestion_repair
from keyhole_sdk.ingest.scanner import scan_repo
from keyhole_sdk.ingest.submitter import submit_ingestion
from keyhole_sdk.repo_identity import RepoIdentityError, detect_repo_identity
from keyhole_sdk.transport.client import GovernedTransport
from keyhole_sdk.transport.idempotency import generate_request_id

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_ingest(
    *,
    repo_path: str = ".",
    shadow: bool = False,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    max_bytes: int = 0,
    summary_only: bool = False,
    gap_id: str = "",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole ingest`` or ``keyhole ingest --shadow``.

    Returns a CommandResult for the CLI to render.
    """
    command_label = "keyhole ingest --shadow" if shadow else "keyhole ingest"
    target = Path(repo_path).resolve()

    # ── Validate repo path ──
    if not target.is_dir():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=f"Repository path does not exist or is not a directory: {target}",
            data={"error_class": "InvalidRepoPath", "is_local": True},
            next_steps=map_ingestion_repair("InvalidRepoPath"),
        )

    # ── Build filter ──
    file_filter = IncludeExcludeFilter(
        extra_includes=include,
        extra_excludes=exclude,
    )

    # ── Local scan (§8) — never mutates target ──
    try:
        scan = scan_repo(target, file_filter=file_filter, max_bytes=max_bytes)
    except Exception as exc:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=f"Repository scan failed: {exc}",
            data={"error_class": "ScanError", "is_local": True},
            next_steps=[
                "Ensure the path is readable.",
                "Try: keyhole ingest --shadow — for a low-risk pass.",
            ],
        )

    # ── Check for empty package ──
    if not scan.included_files:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No files included after filtering. Nothing to ingest.",
            data={
                "error_class": "EmptyPackage",
                "is_local": True,
                "total_files": scan.total_files,
                "excluded_files": len(scan.excluded_files),
            },
            next_steps=map_ingestion_repair("EmptyPackage"),
        )

    # ── Build package (§10) ──
    correlation_id = generate_request_id()
    resolved_gap_id = gap_id.strip() or os.environ.get("KEYHOLE_GAP_ID", "").strip()
    repo_identity = None
    try:
        repo_identity = detect_repo_identity(str(target))
    except RepoIdentityError:
        repo_identity = None

    package = build_ingestion_package(
        scan,
        shadow=shadow,
        correlation_id=correlation_id,
        gap_id=resolved_gap_id,
        repo_remote=repo_identity.repo_remote if repo_identity else "",
        commit_sha=repo_identity.commit_sha if repo_identity else "",
        current_branch=repo_identity.current_branch if repo_identity else "",
        exclusion_rules=file_filter.exclude_rules,
    )

    # ── Summary-only mode — no submission ──
    if summary_only:
        return _render_summary_only(
            package=package,
            scan=scan,
            command_label=command_label,
        )

    # ── Resolve credentials ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    session = cred_store.load()
    if not session:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated. Run 'keyhole login' first.",
            data={"error_class": "AuthenticationError", "is_local": True},
            next_steps=map_ingestion_repair("AuthenticationError"),
        )

    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = session.access_token if session else ""
    identity_fp = session.token_fingerprint if session else ""

    if not token:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated. Run 'keyhole login' first.",
            data={"error_class": "AuthenticationError", "is_local": True},
            next_steps=map_ingestion_repair("AuthenticationError"),
        )

    # ── Build request ──
    request = IngestionRequest(
        package=package,
        identity_fingerprint=identity_fp,
        gap_id=resolved_gap_id,
        repo_remote=repo_identity.repo_remote if repo_identity else "",
        commit_sha=repo_identity.commit_sha if repo_identity else "",
    )

    # ── Build transport ──
    auth_provider = BearerTokenProvider(token=token)
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    # ── Submit (§12) ──
    try:
        outcome = submit_ingestion(transport=transport, request=request)
    finally:
        transport.close()

    # ── Emit proof (§17) — out-of-tree by default ──
    state_dir = _resolve_state_dir(keyhole_home)
    proof_dir = _safe_emit_proof(
        state_dir=state_dir,
        correlation_id=correlation_id,
        request=request,
        package=package,
        outcome=outcome,
    )

    # ── Render outcome (§15) ──
    return _outcome_to_result(
        outcome=outcome,
        command_label=command_label,
        proof_dir=proof_dir,
        scan=scan,
    )


def _render_summary_only(
    *,
    package: Any,
    scan: Any,
    command_label: str,
) -> CommandResult:
    """Render summary-only mode (no submission)."""
    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=f"Scan complete: {len(scan.included_files)} files included, "
                f"{len(scan.excluded_files)} excluded. Package ready but not submitted.",
        data={
            "mode": "summary_only",
            "repo_root": scan.repo_root,
            "repo_identity": package.repo_identity,
            "gap_id": package.gap_id,
            "repo_remote": package.repo_remote,
            "commit_sha": package.commit_sha,
            "languages": package.languages,
            "frameworks": package.frameworks,
            "manifests": package.manifests,
            "source_dirs": package.source_dirs,
            "test_dirs": package.test_dirs,
            "included_files": len(scan.included_files),
            "excluded_files": len(scan.excluded_files),
            "total_included_bytes": scan.total_included_bytes,
            "has_keyhole_scaffold": scan.has_keyhole_scaffold,
            "compatibility_inputs": package.compatibility_inputs,
            "shadow": package.shadow,
        },
        next_steps=[
            "Run without --summary-only to submit: keyhole ingest .",
            "Run with --shadow for an exploratory pass: keyhole ingest --shadow .",
        ],
    )


def _outcome_to_result(
    *,
    outcome: IngestionOutcome,
    command_label: str,
    proof_dir: Optional[Path],
    scan: Any,
) -> CommandResult:
    """Convert an IngestionOutcome to a CommandResult (§15)."""
    is_success = outcome.status in ("success", "accepted")

    data: Dict[str, Any] = {
        "status": outcome.status,
        "repo_identity": outcome.repo_identity,
        "shadow": outcome.shadow,
        "correlation_id": outcome.correlation_id,
        "compatibility": outcome.compatibility.value,
        # §15: Observed facts
        "observed": {
            "languages": scan.languages if scan else [],
            "frameworks": scan.frameworks if scan else [],
            "manifests": scan.manifests if scan else [],
            "source_dirs": scan.source_dirs if scan else [],
            "test_dirs": scan.test_dirs if scan else [],
            "included_files": len(scan.included_files) if scan else 0,
        },
    }

    if outcome.ingestion_id:
        data["ingestion_id"] = outcome.ingestion_id

    # §16: Graph output — clearly marked as inferred
    if outcome.graph_summary:
        data["graph_summary"] = outcome.graph_summary.model_dump(mode="json")

    # §16: Inferred capabilities — explicitly marked
    if outcome.inferred_capabilities:
        data["inferred_capabilities"] = [
            {
                "name": c.name,
                "confidence": c.confidence.value,
                "basis": c.basis,
                "category": c.category,
                "source": "inferred",  # §3, §16: explicit distinction
            }
            for c in outcome.inferred_capabilities
        ]

    if outcome.warnings:
        data["warnings"] = outcome.warnings

    if proof_dir:
        data["proof_dir"] = str(proof_dir)

    # Build summary line
    if is_success:
        cap_count = len(outcome.inferred_capabilities)
        mode_label = " (shadow)" if outcome.shadow else ""
        summary = (
            f"Ingestion{mode_label}: {outcome.status}. "
            f"Compatibility: {outcome.compatibility.value}. "
            f"Inferred capabilities: {cap_count}."
        )
    elif outcome.status == "deferred":
        summary = (
            f"Ingestion accepted (deferred). "
            f"Check status with: keyhole runs status {outcome.ingestion_id or outcome.correlation_id}"
        )
    else:
        summary = f"Ingestion failed: {outcome.reason or outcome.error_class or 'unknown error'}"
        if outcome.error_class:
            data["error_class"] = outcome.error_class

    # Next steps
    next_steps: List[str] = []
    if outcome.suggested_actions:
        next_steps.extend(outcome.suggested_actions)
    if outcome.status == "accepted" and outcome.ingestion_id:
        next_steps.append(
            f"Run: keyhole runs status {outcome.ingestion_id} — to check progress."
        )
    if outcome.repair_guidance:
        next_steps.extend(outcome.repair_guidance)
    if is_success and not outcome.shadow:
        next_steps.append("Run: keyhole run --context auto — to dispatch a governed run.")
    if is_success and outcome.shadow:
        next_steps.append("Run: keyhole ingest . — without --shadow for a governed pass.")

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
    request: IngestionRequest,
    package: Any,
    outcome: IngestionOutcome,
) -> Optional[Path]:
    """Emit proof artifacts, returning None on I/O failure."""
    try:
        return emit_ingestion_proof(
            state_dir=state_dir,
            correlation_id=correlation_id,
            request_dict=request.to_proof_dict(),
            package_manifest=package.to_proof_dict(),
            outcome_dict=outcome.to_proof_dict(),
        )
    except OSError:
        return None
