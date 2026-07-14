"""CLI adapter for the generic governed repository flow."""
from __future__ import annotations

import os
from pathlib import Path

from keyhole_cli.result import CommandResult, EXIT_FAILURE, EXIT_SUCCESS
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.config import DEFAULT_BASE_URL
from keyhole_sdk.governed_demo import GovernedDemoError, _redact
from keyhole_sdk.governed_flow import GovernedRepoFlowClient, GovernedRunStateStore, read_repo_declaration


def run_governed_flow(
    *,
    repo_dir: str = ".",
    story_id: str = "",
    capability_id: str = "",
    repo_class: str = "",
    gap_id: str = "",
    dry_run: bool = False,
    no_live: bool = False,
    explain: bool = False,
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        if no_live:
            declaration = read_repo_declaration(
                Path(repo_dir).resolve(),
                story_id=story_id,
                capability_id=capability_id,
                repo_class=repo_class,
            )
            return CommandResult(
                command="keyhole governed run",
                success=True,
                exit_code=EXIT_SUCCESS,
                summary="Governed repo declaration validated locally; MCP was not mutated.",
                data=_redact({
                    "no_live": True,
                    "would_mutate_mcp": False,
                    "repo_name": declaration.repo_name,
                    "repo_remote": declaration.repo_remote,
                    "commit_sha": declaration.commit_sha,
                    "branch": declaration.branch,
                    "repo_class": declaration.repo_class,
                    "story_id": declaration.story_id,
                    "capability_id": declaration.capability_id,
                    "declaration_file_digests": declaration.declaration_file_digests,
                    "explain": "local declaration inspection only" if explain else "",
                }),
            )
        client = _client(
            mcp_url=mcp_url,
            runtime_url=runtime_url,
            story_id=story_id,
            capability_id=capability_id,
            repo_class=repo_class,
            gap_id=gap_id,
        )
        result = client.run_governed_repo_flow(repo_dir, dry_run=dry_run)
        if explain:
            repo_path = Path(repo_dir).resolve()
            result["explain"] = {
                "repo_identity": {
                    "repo_dir": str(repo_path),
                    "repo_remote": result.get("repo", {}).get("repo_remote", ""),
                    "commit_sha": result.get("repo", {}).get("commit_sha", ""),
                    "branch": result.get("repo", {}).get("branch", ""),
                },
                "candidate_gap_filters": {
                    "story_id": story_id or result.get("repo", {}).get("story_id", ""),
                    "capability_id": capability_id or result.get("repo", {}).get("capability_id", ""),
                    "repo_name": result.get("repo", {}).get("repo_name", ""),
                    "repo_class": repo_class or result.get("repo", {}).get("repo_class", ""),
                },
                "gap_id_source": result.get("gap_id_source", ""),
                "selected_gap_id": result.get("resolved_gap_id", ""),
                "story_id_is_label_only": True,
                "dry_run": dry_run,
                "operations_would_call": [
                    "GET /mcp/v1/capabilities",
                    "runs.start:gaps.list",
                    "runs.start:gaps.claim",
                    "runs.start:governance.context.create",
                    "runs.start:context.compile",
                    "runs.start:governed.realize",
                ],
                "local_state_path": str(repo_path / ".keyhole" / "governed-runs"),
            }
        return CommandResult(
            command="keyhole governed run",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed repo flow completed." if not dry_run else "Governed repo flow dry-run completed.",
            data=_redact(result),
        )
    except GovernedDemoError as exc:
        return _failure("keyhole governed run", exc, is_local=no_live)


def run_governed_status(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        repo = Path(repo_dir).resolve()
        try:
            local_state = GovernedRunStateStore(repo).load_latest()
        except GovernedDemoError:
            local_state = {}
        if local_state.get("terminal") is True:
            return CommandResult(
                command="keyhole governed status",
                success=True,
                exit_code=EXIT_SUCCESS,
                summary="Governed run status loaded from local terminal state.",
                data=_redact(local_state),
            )
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        state = client.status_governed_repo_flow(repo_dir)
        return CommandResult(
            command="keyhole governed status",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed run status loaded.",
            data=state,
        )
    except GovernedDemoError as exc:
        return _failure("keyhole governed status", exc)


def run_governed_resume(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        result = client.resume_governed_repo_flow(repo_dir)
        return CommandResult(
            command="keyhole governed resume",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed repo flow resumed.",
            data=_redact(result),
        )
    except GovernedDemoError as exc:
        return _failure("keyhole governed resume", exc)


def run_governed_receipt(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        repo = Path(repo_dir).resolve()
        local_state = GovernedRunStateStore(repo).load_latest()
        if local_state.get("receipt_id") or local_state.get("proof_id"):
            return CommandResult(
                command="keyhole governed receipt",
                success=True,
                exit_code=EXIT_SUCCESS,
                summary="Governed receipt loaded.",
                data=_redact({
                    "live_confirmed": bool(local_state.get("live_confirmed", False)),
                    "receipt": {
                        "digest": local_state.get("digest", ""),
                        "status": local_state.get("status", ""),
                        "message": local_state.get("message", ""),
                        "realized_at": local_state.get("realized_at", ""),
                        "governed": local_state.get("governed", False),
                        "event_spine_evidence": local_state.get("event_spine_evidence", False),
                        "governance_verdict": local_state.get("governance_verdict", ""),
                        "drift_state": local_state.get("drift_state", ""),
                        "governance_context_id": local_state.get("governance_context_id", ""),
                        "mcp_event_id": local_state.get("mcp_event_id", ""),
                        "proof_id": local_state.get("proof_id", ""),
                        "receipt_id": local_state.get("receipt_id", ""),
                        "passport_digest": local_state.get("passport_digest", ""),
                        "trust_digest": local_state.get("trust_digest", ""),
                    },
                }),
            )
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        result = client.receipt_governed_repo_flow(repo_dir)
        return CommandResult(
            command="keyhole governed receipt",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed receipt loaded.",
            data=result,
        )
    except GovernedDemoError as exc:
        return _failure("keyhole governed receipt", exc)


def _client(
    *,
    mcp_url: str,
    runtime_url: str,
    story_id: str = "",
    capability_id: str = "",
    repo_class: str = "",
    gap_id: str = "",
) -> GovernedRepoFlowClient:
    return GovernedRepoFlowClient(
        mcp_url=mcp_url,
        token=_token(),
        runtime_url=os.environ.get("KEYHOLE_RUNTIME_URL", runtime_url),
        story_id=story_id,
        capability_id=capability_id,
        repo_class=repo_class,
        gap_id=gap_id,
    )


def _token() -> str:
    token = os.environ.get("KEYHOLE_MCP_TOKEN", "")
    if token:
        return token
    try:
        return get_fresh_token()
    except Exception as exc:
        raise GovernedDemoError(
            "KEYHOLE_MCP_TOKEN is not set and no usable device-login credential is available: "
            f"{exc}"
        ) from exc


def _failure(command: str, exc: Exception, *, is_local: bool = False) -> CommandResult:
    message = str(exc)
    if "NO_CLAIMABLE_GAP" in message or "STATUS_NOT_CLAIMABLE" in message:
        next_steps = [
            "Run keyhole gaps list --repo-dir <path> --json and confirm at least one matching gap is claimable=true.",
            "Ask the server boundary to materialize or reopen an OPEN gap for this repo/capability/current commit.",
            "Use keyhole governed status --repo-dir <path> --last --json to inspect preserved local state.",
        ]
    else:
        next_steps = [
            "Run keyhole login --flow device --force if live MCP credentials are missing.",
            "Use keyhole governed status --repo-dir <path> --last --json to inspect saved state.",
        ]
    return CommandResult(
        command=command,
        success=False,
        exit_code=EXIT_FAILURE,
        summary=message,
        data={"error_class": type(exc).__name__, "is_local": is_local},
        next_steps=next_steps,
    )
