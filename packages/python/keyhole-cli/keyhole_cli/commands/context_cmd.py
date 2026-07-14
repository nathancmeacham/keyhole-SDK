"""`keyhole context compile` and `keyhole context inspect` — context lifecycle commands.

SDK-CLIENT-16: Context Lifecycle and Governed Run Binding.

Surfaces context as a first-class, builder-visible execution boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.context_lifecycle.compile import (
    ContextCompileResult,
    build_compile_request,
    compile_context,
)
from keyhole_sdk.context_lifecycle.inspect import (
    ContextInspectResult,
    inspect_context,
)
from keyhole_sdk.context_lifecycle.preflight import (
    ContextPreflight,
    ContextPreflightFailure,
)
from keyhole_sdk.context_lifecycle.proof import (
    emit_context_proof,
    emit_inspect_proof,
)
from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
from keyhole_sdk.run_dispatch.preflight import RunPreflight
from keyhole_sdk.transport.client import GovernedTransport
from keyhole_sdk.transport.idempotency import generate_request_id

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_RUNTIME_UNAVAILABLE,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


def run_context_compile(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    mode: str = "",
    origin: str = "",
    purpose: str = "",
) -> CommandResult:
    """Execute ``keyhole context compile``.

    Compiles governed context for the current repo and identity.
    Returns a CommandResult for CLI rendering.
    """
    repo_path = Path(repo_dir).resolve()
    command_label = "keyhole context compile"

    # ── Resolve credential store ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)

    # ── Preflight ──
    preflight = ContextPreflight(credential_store=cred_store)
    failure = preflight.check_compile(repo_dir=repo_path)
    if failure is not None:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=failure.reason,
            data={
                "error_class": "ContextPreflightFailure",
                "is_local": failure.is_local,
            },
            next_steps=failure.repair_guidance,
        )

    # ── Resolve repo name ──
    run_preflight = RunPreflight(credential_store=cred_store)
    repo_name = run_preflight.load_repo_name(repo_path) or repo_path.name

    # ── Resolve identity ──
    session = cred_store.load()
    identity_fp = session.token_fingerprint if session else ""
    token = session.access_token if session else ""

    # ── Build compile request ──
    correlation_id = generate_request_id()
    request = build_compile_request(
        repo_name=repo_name,
        identity_fingerprint=identity_fp,
        correlation_id=correlation_id,
        mode=mode,
        origin=origin,
        purpose=purpose,
    )

    # ── Build transport ──
    auth_provider = BearerTokenProvider(token=token) if token else None
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    # ── Dispatch ──
    try:
        result = compile_context(transport=transport, request=request)
    finally:
        transport.close()

    # ── Emit proof ──
    proof_dir = _safe_emit_compile_proof(
        repo_dir=repo_path,
        request=request,
        result=result,
    )

    # ── Track recent context ──
    if result.success and result.ctxpack_digest:
        _safe_track_context(
            repo_dir=repo_path,
            ctxpack_digest=result.ctxpack_digest,
            repo_name=repo_name,
            correlation_id=correlation_id,
        )

    # ── Render result ──
    return _compile_to_result(
        result=result,
        command_label=command_label,
        proof_dir=proof_dir,
    )


def run_context_inspect(
    *,
    digest: str = "",
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole context inspect``.

    Inspects a context digest to make it intelligible to the builder.
    """
    repo_path = Path(repo_dir).resolve()
    command_label = "keyhole context inspect"

    # ── Resolve credential store ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)

    # ── Resolve digest — may use local recent tracker ──
    actual_digest = digest
    from_recent = False
    if not actual_digest:
        tracker = LocalContextTracker(repo_path)
        recent = tracker.get_recent_digest()
        if recent:
            actual_digest = recent
            from_recent = True

    # ── Preflight ──
    preflight = ContextPreflight(credential_store=cred_store)
    failure = preflight.check_inspect(digest=actual_digest)
    if failure is not None:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=failure.reason,
            data={
                "error_class": "ContextPreflightFailure",
                "is_local": failure.is_local,
            },
            next_steps=failure.repair_guidance,
        )

    # ── Resolve identity ──
    session = cred_store.load()
    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = session.access_token if session else ""

    # ── Resolve repo name ──
    run_preflight = RunPreflight(credential_store=cred_store)
    repo_name = run_preflight.load_repo_name(repo_path) or repo_path.name

    # ── Build transport ──
    auth_provider = BearerTokenProvider(token=token) if token else None
    transport = GovernedTransport(
        base_url=mcp_url,
        auth_provider=auth_provider,
    )

    # ── Dispatch ──
    try:
        result = inspect_context(
            transport=transport,
            ctxpack_digest=actual_digest,
            repo_name=repo_name,
        )
    finally:
        transport.close()

    # ── Record inspect ──
    if from_recent:
        result.is_recent = True

    _safe_emit_inspect_proof(
        repo_dir=repo_path,
        ctxpack_digest=actual_digest,
        result=result,
    )

    # ── Render result ──
    return _inspect_to_result(
        result=result,
        command_label=command_label,
        from_recent=from_recent,
    )


# ── Internal helpers ──────────────────────────────────────────


def _safe_emit_compile_proof(
    *,
    repo_dir: Path,
    request: Any,
    result: ContextCompileResult,
) -> Optional[Path]:
    """Emit compile proof, returning None on I/O failure."""
    try:
        return emit_context_proof(
            repo_dir=repo_dir,
            request=request,
            result=result,
        )
    except OSError:
        return None


def _safe_emit_inspect_proof(
    *,
    repo_dir: Path,
    ctxpack_digest: str,
    result: ContextInspectResult,
) -> Optional[Path]:
    """Emit inspect proof, returning None on I/O failure."""
    try:
        inspect_data: Dict[str, Any] = {
            "success": result.success,
            "ctxpack_digest": result.ctxpack_digest,
            "summary": result.summary,
            "repo_name": result.repo_name,
            "observed_at": result.observed_at,
        }
        if result.error_class:
            inspect_data["error_class"] = result.error_class
        if result.reason:
            inspect_data["reason"] = result.reason
        return emit_inspect_proof(
            repo_dir=repo_dir,
            ctxpack_digest=ctxpack_digest,
            inspect_data=inspect_data,
        )
    except OSError:
        return None


def _safe_track_context(
    *,
    repo_dir: Path,
    ctxpack_digest: str,
    repo_name: str,
    correlation_id: str,
) -> None:
    """Track recent context, swallowing I/O errors."""
    try:
        tracker = LocalContextTracker(repo_dir)
        tracker.save(
            ctxpack_digest=ctxpack_digest,
            repo_name=repo_name,
            correlation_id=correlation_id,
        )
    except OSError:
        pass


def _compile_to_result(
    *,
    result: ContextCompileResult,
    command_label: str,
    proof_dir: Optional[Path],
) -> CommandResult:
    """Convert a ContextCompileResult to a CommandResult."""
    proof_location = str(proof_dir) if proof_dir else "(proof not written)"

    if result.success:
        data: Dict[str, Any] = {
            "status": "success",
            "ctxpack_digest": result.ctxpack_digest,
            "repo": result.repo_name,
            "proof": proof_location,
        }
        if result.summary:
            data["summary"] = result.summary
        if result.metadata:
            data["metadata"] = result.metadata
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"Context compiled: {result.ctxpack_digest}",
            data=data,
            next_steps=[
                f"Inspect: keyhole context inspect --digest {result.ctxpack_digest}",
                f"Run: keyhole run --context {result.ctxpack_digest} --run-type <type>",
            ],
        )

    # Failure
    data = {
        "status": "failed",
        "repo": result.repo_name,
        "error_class": result.error_class,
        "reason": result.reason,
        "proof": proof_location,
    }

    exit_code = (
        EXIT_RUNTIME_UNAVAILABLE
        if result.error_class in ("TransportUnknownError", "RetryExhaustedError", "RuntimeUnavailableError")
        else EXIT_FAILURE
    )

    return CommandResult(
        command=command_label,
        success=False,
        exit_code=exit_code,
        summary=f"Context compile failed: {result.reason[:120]}" if result.reason else "Context compile failed.",
        data=data,
        next_steps=result.repair_guidance or [
            "Run: keyhole context compile — to retry.",
        ],
    )


def _inspect_to_result(
    *,
    result: ContextInspectResult,
    command_label: str,
    from_recent: bool = False,
) -> CommandResult:
    """Convert a ContextInspectResult to a CommandResult."""
    if result.success:
        data: Dict[str, Any] = {
            "status": "success",
            "ctxpack_digest": result.ctxpack_digest,
        }
        if result.summary:
            data["summary"] = result.summary
        if result.repo_name:
            data["repo"] = result.repo_name
        if result.tenant:
            data["tenant"] = result.tenant
        if result.org:
            data["org"] = result.org
        if result.workspace:
            data["workspace"] = result.workspace
        if result.lane:
            data["lane"] = result.lane
        if result.lens:
            data["lens"] = result.lens
        if result.generated_at:
            data["generated_at"] = result.generated_at
        if result.observed_at:
            data["observed_at"] = result.observed_at
        if from_recent:
            data["source"] = "recent (most recently compiled)"

        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"Context: {result.ctxpack_digest}",
            data=data,
            next_steps=[
                f"Run: keyhole run --context {result.ctxpack_digest} --run-type <type>",
            ],
        )

    # Failure
    data = {
        "status": "failed",
        "ctxpack_digest": result.ctxpack_digest,
        "error_class": result.error_class,
        "reason": result.reason,
    }

    return CommandResult(
        command=command_label,
        success=False,
        exit_code=EXIT_FAILURE,
        summary=f"Context inspect failed: {result.reason[:120]}" if result.reason else "Context inspect failed.",
        data=data,
        next_steps=result.repair_guidance or [
            "Run: keyhole context compile — to get a valid digest.",
        ],
    )
