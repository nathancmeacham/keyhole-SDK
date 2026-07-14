"""`keyhole dependency resolve` — dependency resolution command.

SDK-CLIENT-08: Capability Discovery and Resolution.

Resolves a capability to a deterministic dependency, optionally
materialising it into the local dependency model.

§8.3: Fail-closed on ambiguity — never silently picks a winner.
§13.3: Never silently mutates the target repo.
§14.2: Foreign repos use out-of-tree proof only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.capability.materializer import (
    MaterializationResult,
    materialize_resolution,
)
from keyhole_sdk.capability.models import (
    MaterializationMode,
    RepoPosture,
    ResolutionOutcome,
    ResolutionRequest,
)
from keyhole_sdk.capability.proof import emit_resolution_proof
from keyhole_sdk.capability.repair import map_capability_repair
from keyhole_sdk.capability.resolver import submit_resolution
from keyhole_sdk.transport.client import GovernedTransport
from keyhole_sdk.transport.idempotency import generate_request_id

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_dependency_resolve(
    *,
    capability: str,
    provider: str = "",
    version: str = "",
    write: bool = False,
    advisory: bool = False,
    repo_path: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole dependency resolve <capability>``.

    Returns a CommandResult for the CLI to render.
    """
    command_label = "keyhole dependency resolve"
    target = Path(repo_path).resolve()

    # ── Validate path ──
    if not target.is_dir():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=f"Repository path does not exist or is not a directory: {target}",
            data={"error_class": "InvalidRepoPath", "is_local": True},
            next_steps=map_capability_repair("InvalidLocalDependencyState"),
        )

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
    identity_fp = session.token_fingerprint if session else ""

    if not token:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary="Not authenticated. Run: keyhole login",
            data={"error_class": "NotAuthenticated", "is_local": True},
            next_steps=map_capability_repair("NotAuthenticated"),
        )

    # ── Determine mode ──
    mode = MaterializationMode.WRITE if write else MaterializationMode.ADVISORY

    # ── Detect repo posture ──
    repo_posture = _detect_repo_posture(target)

    # ── Build request ──
    correlation_id = generate_request_id()
    request = ResolutionRequest(
        capability=capability,
        provider=provider,
        version=version,
        repo_posture=repo_posture,
        mode=mode,
        identity_fingerprint=identity_fp,
        correlation_id=correlation_id,
    )

    # ── Build transport and submit ──
    auth_provider = BearerTokenProvider(token=token)
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    try:
        outcome = submit_resolution(
            transport=transport,
            request=request,
        )
    finally:
        transport.close()

    # ── Materialise if resolved ──
    state_dir = _resolve_state_dir(keyhole_home)
    mat_result: Optional[MaterializationResult] = None
    if outcome.is_resolved:
        mat_result = materialize_resolution(
            outcome=outcome,
            repo_path=target,
            repo_posture=repo_posture,
            state_dir=state_dir,
            mode=mode,
        )

    # ── Emit proof ──
    proof_dir = _safe_emit_proof(
        state_dir=state_dir,
        correlation_id=correlation_id,
        request=request,
        outcome=outcome,
        mat_result=mat_result,
        repo_posture=repo_posture,
        mode=mode,
    )

    # ── Render ──
    return _outcome_to_result(
        outcome=outcome,
        command_label=command_label,
        proof_dir=proof_dir,
        mat_result=mat_result,
        mode=mode,
        repo_posture=repo_posture,
    )


def _detect_repo_posture(repo_path: Path) -> RepoPosture:
    """Detect repo posture from local artifacts."""
    keyhole_yaml = repo_path / "keyhole.yaml"
    keyhole_yml = repo_path / "keyhole.yml"
    if keyhole_yaml.is_file() or keyhole_yml.is_file():
        return RepoPosture.NATIVE
    # Check for ingestion state
    keyhole_dir = repo_path / ".keyhole"
    if keyhole_dir.is_dir() and (keyhole_dir / "ingestion.json").is_file():
        return RepoPosture.INGESTION_BACKED
    return RepoPosture.FOREIGN


def _outcome_to_result(
    *,
    outcome: ResolutionOutcome,
    command_label: str,
    proof_dir: Optional[Path],
    mat_result: Optional[MaterializationResult],
    mode: MaterializationMode,
    repo_posture: RepoPosture,
) -> CommandResult:
    """Convert a ResolutionOutcome to a CommandResult."""
    is_success = outcome.is_resolved

    data: Dict[str, Any] = {
        "status": outcome.status,
        "mode": mode.value,
        "repo_posture": repo_posture.value,
        "correlation_id": outcome.correlation_id,
    }

    if outcome.resolved:
        data["resolved"] = outcome.resolved.to_dict()

    if outcome.candidates:
        data["candidates"] = [c.to_dict() for c in outcome.candidates]

    if mat_result:
        data["materialization"] = mat_result.to_dict()

    if outcome.error_class:
        data["error_class"] = outcome.error_class
    if outcome.reason:
        data["reason"] = outcome.reason
    if proof_dir:
        data["proof_dir"] = str(proof_dir)

    # Summary
    if outcome.status == "resolved" and outcome.resolved:
        dep = outcome.resolved
        mat_note = ""
        if mat_result and mat_result.is_write:
            mat_note = " Written to dependencies.yaml."
        elif mat_result and mat_result.success:
            mat_note = " Advisory artifact emitted."
        summary = (
            f"Resolved: {dep.capability} → {dep.provider}"
            f"{'@' + dep.version if dep.version else ''}."
            f"{mat_note}"
        )
    elif outcome.status == "ambiguous":
        count = len(outcome.candidates) if outcome.candidates else 0
        summary = (
            f"Ambiguous: {count} providers satisfy the capability — "
            f"no lawful tie-break. Specify --provider to pin."
        )
    elif outcome.status == "incompatible":
        summary = (
            f"Incompatible: no provider satisfies constraints. "
            f"{outcome.reason or ''}"
        )
    elif outcome.status == "not_found":
        summary = f"Not found: {outcome.reason or 'capability not in registry.'}."
    elif outcome.status in ("accepted", "deferred"):
        summary = f"Resolution {outcome.status}. Check status later."
    else:
        summary = f"Resolution failed: {outcome.reason or outcome.error_class or 'unknown'}"

    # Next steps
    next_steps: List[str] = []
    if outcome.repair_guidance:
        next_steps.extend(outcome.repair_guidance)
    if is_success and mat_result and mat_result.success and not mat_result.is_write:
        next_steps.append(
            "Run: keyhole dependency resolve <capability> --write — to commit to dependencies.yaml."
        )
    if mat_result and not mat_result.success and mat_result.repair_guidance:
        next_steps.extend(mat_result.repair_guidance)

    # Warnings
    warnings: List[str] = list(outcome.warnings) if outcome.warnings else []
    if mat_result and mat_result.error_class:
        warnings.append(f"Materialization: {mat_result.error_class} — {mat_result.reason}")

    return CommandResult(
        command=command_label,
        success=is_success,
        exit_code=EXIT_SUCCESS if is_success else EXIT_FAILURE,
        summary=summary,
        data=data,
        warnings=warnings or None,
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
    request: ResolutionRequest,
    outcome: ResolutionOutcome,
    mat_result: Optional[MaterializationResult],
    repo_posture: RepoPosture,
    mode: MaterializationMode,
) -> Optional[Path]:
    """Emit resolution proof, returning None on I/O failure."""
    try:
        return emit_resolution_proof(
            state_dir=state_dir,
            correlation_id=correlation_id,
            request_dict=request.to_proof_dict(),
            outcome_dict=outcome.to_proof_dict(),
            materialization_dict=mat_result.to_dict() if mat_result else None,
            repo_posture=repo_posture.value,
            mode=mode.value,
        )
    except OSError:
        return None
