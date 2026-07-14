"""`keyhole runs` — async run lifecycle commands.

SDK-CLIENT-17: Async Run Tracking, Polling, and Durable Run UX.

Surfaces: status, wait, tail, resume for governed async runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.run_lifecycle.models import RunStatus
from keyhole_sdk.run_lifecycle.proof import (
    emit_outcome_proof,
    emit_status_proof,
)
from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore
from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
from keyhole_sdk.run_lifecycle.resume import resume_run
from keyhole_sdk.run_lifecycle.status import fetch_run_status
from keyhole_sdk.run_lifecycle.tail import tail_run
from keyhole_sdk.run_lifecycle.wait import wait_for_terminal
from keyhole_sdk.transport.client import GovernedTransport

from keyhole_cli.result import (
    CommandResult,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_SUCCESS,
)
from keyhole_sdk.config import DEFAULT_BASE_URL


# ──────────────────────────────────────────────────────────────
# keyhole runs status <run-id>
# ──────────────────────────────────────────────────────────────

def run_runs_status(
    *,
    run_id: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole runs status <run-id>``."""
    command_label = "keyhole runs status"

    if not run_id or not run_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No run ID provided.",
            next_steps=map_run_lifecycle_repair("missing_run_id"),
        )

    repo_path = Path(repo_dir).resolve()
    transport, cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        result = fetch_run_status(
            transport=transport,
            run_id=run_id.strip(),
            repo_name=_repo_name(repo_path),
        )
    finally:
        transport.close()

    if not result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=result.reason or "Status retrieval failed.",
            data={
                "error_class": result.error_class,
                "run_id": run_id,
            },
            next_steps=result.repair_guidance or map_run_lifecycle_repair("observation_failed"),
        )

    # Emit status proof
    _safe_status_proof(repo_path, run_id, result.status.value, result.response_data)

    # Update local record if exists
    _safe_update_local_record(repo_path, run_id, result.status.value)

    data = {
        "run_id": result.run_id,
        "request_id": result.request_id,
        "status": result.status.value,
        "is_terminal": result.status.is_terminal,
        "run_type": result.run_type,
        "repo": result.repo_name,
        "shadow": result.shadow,
        "resolved": result.resolved,
        "server_backed": result.server_backed,
    }
    if result.correlation_id:
        data["correlation_id"] = result.correlation_id
    if result.ctxpack_digest:
        data["ctxpack_digest"] = result.ctxpack_digest
    if result.last_updated:
        data["last_updated"] = result.last_updated
    if result.terminal_summary:
        data["terminal_summary"] = result.terminal_summary

    next_steps = []
    if not result.status.is_terminal:
        next_steps = [
            f"Wait for result: keyhole runs wait {run_id}",
            f"Follow: keyhole runs tail {run_id}",
        ]

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=result.render_human().split("\n")[0],
        data=data,
        next_steps=next_steps,
    )


# ──────────────────────────────────────────────────────────────
# keyhole runs wait <run-id>
# ──────────────────────────────────────────────────────────────

def run_runs_wait(
    *,
    run_id: str,
    poll_interval: float = 3.0,
    max_polls: int = 200,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole runs wait <run-id>``."""
    command_label = "keyhole runs wait"

    if not run_id or not run_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No run ID provided.",
            next_steps=map_run_lifecycle_repair("missing_run_id"),
        )

    repo_path = Path(repo_dir).resolve()
    transport, cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        result = wait_for_terminal(
            transport=transport,
            run_id=run_id.strip(),
            repo_name=_repo_name(repo_path),
            poll_interval=poll_interval,
            max_polls=max_polls,
        )
    except KeyboardInterrupt:
        transport.close()
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"Wait interrupted for run {run_id}.",
            data={"run_id": run_id, "interrupted": True},
            next_steps=[
                f"Resume waiting: keyhole runs wait {run_id}",
                f"Check status: keyhole runs status {run_id}",
            ],
        )
    finally:
        transport.close()

    if not result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=result.reason or "Wait failed.",
            data={
                "error_class": result.error_class,
                "run_id": run_id,
                "polls": result.polls,
                "elapsed_seconds": round(result.elapsed_seconds, 2),
            },
            next_steps=result.repair_guidance or map_run_lifecycle_repair(result.error_class or "observation_failed"),
        )

    terminal_val = result.terminal_status.value if result.terminal_status else "unknown"

    # Emit outcome proof for terminal result
    _safe_outcome_proof(repo_path, run_id, terminal_val, result.final_data)

    # Update local record
    _safe_update_local_record(repo_path, run_id, terminal_val)

    summary = f"Run {run_id}: {terminal_val.upper()}"
    if result.interrupted:
        summary += " (interrupted)"

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=summary,
        data={
            "run_id": run_id,
            "terminal_status": terminal_val,
            "polls": result.polls,
            "elapsed_seconds": round(result.elapsed_seconds, 2),
            "interrupted": result.interrupted,
        },
    )


# ──────────────────────────────────────────────────────────────
# keyhole runs tail <run-id>
# ──────────────────────────────────────────────────────────────

def run_runs_tail(
    *,
    run_id: str,
    poll_interval: float = 2.0,
    max_entries: int = 100,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole runs tail <run-id>``."""
    command_label = "keyhole runs tail"

    if not run_id or not run_id.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No run ID provided.",
            next_steps=map_run_lifecycle_repair("missing_run_id"),
        )

    repo_path = Path(repo_dir).resolve()
    transport, cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        result = tail_run(
            transport=transport,
            run_id=run_id.strip(),
            repo_name=_repo_name(repo_path),
            poll_interval=poll_interval,
            max_entries=max_entries,
        )
    except KeyboardInterrupt:
        transport.close()
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"Tail interrupted for run {run_id}.",
            data={"run_id": run_id, "interrupted": True, "observation_method": "status_poll"},
            next_steps=[
                f"Resume: keyhole runs tail {run_id}",
                f"Check status: keyhole runs status {run_id}",
            ],
        )
    finally:
        transport.close()

    if not result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=result.reason or "Tail observation failed.",
            data={
                "error_class": result.error_class,
                "run_id": run_id,
                "observation_method": result.observation_method,
                "entries_collected": len(result.entries),
            },
            next_steps=result.repair_guidance or map_run_lifecycle_repair("observation_failed"),
        )

    terminal_val = result.terminal_status.value if result.terminal_status else None

    entries_data = [
        {"timestamp": e.timestamp, "status": e.status, "message": e.message, "source": e.source}
        for e in result.entries
    ]

    summary = f"Tailed run {run_id} ({result.observation_method})"
    if terminal_val:
        summary += f" — terminal: {terminal_val.upper()}"
        _safe_outcome_proof(repo_path, run_id, terminal_val, {})
        _safe_update_local_record(repo_path, run_id, terminal_val)

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=summary,
        data={
            "run_id": run_id,
            "observation_method": result.observation_method,
            "entries": entries_data,
            "terminal_status": terminal_val,
            "interrupted": result.interrupted,
        },
    )


# ──────────────────────────────────────────────────────────────
# keyhole runs resume <identifier>
# ──────────────────────────────────────────────────────────────

def run_runs_resume(
    *,
    identifier: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole runs resume <identifier>``."""
    command_label = "keyhole runs resume"

    if not identifier or not identifier.strip():
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="No identifier provided.",
            next_steps=map_run_lifecycle_repair("missing_identifier"),
        )

    repo_path = Path(repo_dir).resolve()
    transport, cred_store = _build_transport(mcp_url, keyhole_home)

    try:
        result = resume_run(
            transport=transport,
            identifier=identifier.strip(),
            repo_dir=repo_path,
            repo_name=_repo_name(repo_path),
        )
    finally:
        transport.close()

    if not result.success:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=result.reason or "Resume failed.",
            data={
                "error_class": result.error_class,
                "identifier": identifier,
            },
            next_steps=result.repair_guidance or map_run_lifecycle_repair("resume_ambiguous"),
        )

    data = {
        "run_id": result.run_id,
        "status": result.status.value,
        "is_terminal": result.status.is_terminal,
        "reconnected": result.reconnected,
        "source": result.source,
    }

    next_steps = []
    if not result.status.is_terminal:
        next_steps = [
            f"Wait for result: keyhole runs wait {result.run_id}",
            f"Follow: keyhole runs tail {result.run_id}",
        ]

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=f"Resumed run {result.run_id}: {result.status.value.upper()} (via {result.source})",
        data=data,
        next_steps=next_steps,
    )


# ──────────────────────────────────────────────────────────────
# keyhole runs list — local recent runs
# ──────────────────────────────────────────────────────────────

def run_runs_list(
    *,
    limit: int = 10,
    repo_dir: str = ".",
) -> CommandResult:
    """Execute ``keyhole runs list`` — list recent local run records."""
    command_label = "keyhole runs list"

    repo_path = Path(repo_dir).resolve()
    store = LocalRunRecordStore(repo_path)
    records = store.list_recent(limit=limit)

    if not records:
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="No local run records found.",
            data={"runs": []},
            next_steps=[
                "Execute a run first: keyhole run --context auto --run-type <type>",
            ],
        )

    runs_data = [
        {
            "run_id": r.run_id,
            "run_type": r.run_type,
            "status": r.last_known_status,
            "submitted_at": r.submitted_at,
            "repo_name": r.repo_name,
            "mode": r.mode,
        }
        for r in records
    ]

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary=f"{len(records)} recent run(s).",
        data={"runs": runs_data},
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
    """Best-effort repo name from .keyhole or directory name."""
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


def _safe_status_proof(
    repo_dir: Path,
    run_id: str,
    status: str,
    response_data: dict,
) -> None:
    """Emit status proof, swallowing I/O errors."""
    try:
        emit_status_proof(
            repo_dir=repo_dir,
            run_id=run_id,
            status=status,
            response_data=response_data,
        )
    except OSError:
        pass


def _safe_outcome_proof(
    repo_dir: Path,
    run_id: str,
    terminal_status: str,
    final_data: dict,
) -> None:
    """Emit outcome proof, swallowing I/O errors."""
    try:
        emit_outcome_proof(
            repo_dir=repo_dir,
            run_id=run_id,
            terminal_status=terminal_status,
            final_data=final_data,
        )
    except OSError:
        pass


def _safe_update_local_record(
    repo_path: Path,
    run_id: str,
    status: str,
) -> None:
    """Update local run record status, swallowing errors."""
    try:
        store = LocalRunRecordStore(repo_path)
        store.update_status(run_id, status)
    except (OSError, ValueError):
        pass
