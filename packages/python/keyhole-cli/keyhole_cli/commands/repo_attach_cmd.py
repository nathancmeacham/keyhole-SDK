"""`keyhole repo attach` — bind the current repo as the governed subject workspace.

SDK-CLIENT-30: Repo-as-Workspace Governance Model

Detects the local Git repository identity and sends a repo enrollment/binding
request to the server. Stores the resulting repo_binding_id locally in
.keyhole/repo-binding.json for use by subsequent gap claim and governance
context operations.

The server resolves the repo class (CUSTOMER_FORK, etc.). The SDK rejects
attachment if the server returns PLATFORM_CONTROL for the repo class.

Expected server result:
  {
    "repo_binding_id": "repo_...",
    "repo_remote": "https://github.com/customer/forked-repo",
    "repo_class": "CUSTOMER_FORK",
    "status": "attached"
  }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.repo_identity import RepoIdentity, RepoIdentityError, detect_repo_identity
from keyhole_sdk.run_dispatch.dispatcher import dispatch_run, OutcomeStatus
from keyhole_sdk.run_dispatch.request_builder import build_run_request
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

# Repo class returned by server that is forbidden for SDK/customer mode
_FORBIDDEN_REPO_CLASS = "PLATFORM_CONTROL"


# ──────────────────────────────────────────────────────────────
# Local binding persistence
# ──────────────────────────────────────────────────────────────


def _save_repo_binding(
    repo_dir: Path,
    binding_id: str,
    identity: RepoIdentity,
    mcp_url: str,
) -> Path:
    """Write .keyhole/repo-binding.json with the binding result.

    Does not store secrets, credentials, or server-side governance internals.
    Returns the path written.
    """
    keyhole_dir = repo_dir / ".keyhole"
    keyhole_dir.mkdir(exist_ok=True)
    binding_file = keyhole_dir / "repo-binding.json"
    data: Dict[str, Any] = {
        "repo_binding_id": binding_id,
        "repo_remote": identity.repo_remote,
        "owner": identity.owner,
        "repo": identity.repo,
        "repo_class": "CUSTOMER_FORK",
        "attached_at": datetime.now(timezone.utc).isoformat(),
        "server": mcp_url,
    }
    binding_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return binding_file


# ──────────────────────────────────────────────────────────────
# Command implementation
# ──────────────────────────────────────────────────────────────


def run_repo_attach(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole repo attach``.

    Detects the local Git repo identity and enrolls it as the governed
    subject workspace via the MCP boundary. Stores repo_binding_id
    in .keyhole/repo-binding.json.

    Returns a CommandResult for the CLI to render.
    """
    command_label = "keyhole repo attach"
    repo_path = Path(repo_dir).resolve()

    # ── Auth check ──
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    session = cred_store.load()
    if not session or not session.access_token:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_RUNTIME_UNAVAILABLE,
            summary="Not authenticated. Run: keyhole login",
            next_steps=["keyhole login", f"Then: {command_label}"],
        )

    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = session.access_token

    # ── Detect local Git repo identity ──
    try:
        identity = detect_repo_identity(str(repo_path))
    except RepoIdentityError as exc:
        error_code = getattr(exc, "error_code", "REPO_IDENTITY_ERROR")
        next_steps = ["Ensure you are inside a Git repository with an 'origin' remote."]
        if error_code == "PLATFORM_REPO_TARGET_FORBIDDEN":
            next_steps = [
                "The subject repo must be your own forked or customer repository.",
                "Do not use the Keyhole platform control repo as the workspace.",
            ]
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary=str(exc),
            data={"error_code": error_code},
            next_steps=next_steps,
        )

    # ── Dispatch repo.attach to MCP boundary ──
    auth_provider = BearerTokenProvider(token=token) if token else None
    transport = GovernedTransport(base_url=mcp_url, auth_provider=auth_provider)

    input_data: Dict[str, Any] = {
        "repo_remote": identity.repo_remote,
        "owner": identity.owner,
        "repo": identity.repo,
        "branch": identity.current_branch,
        "commit_sha": identity.commit_sha,
        "dirty_worktree": identity.dirty_worktree,
    }
    if identity.repo_binding_id:
        input_data["existing_repo_binding_id"] = identity.repo_binding_id

    request = build_run_request(
        run_type="repo.attach",
        repo_name=identity.repo,
        context_ref=None,
        input_data=input_data,
        correlation_id=generate_request_id(),
    )

    try:
        outcome = dispatch_run(transport=transport, request=request)
    finally:
        transport.close()

    # ── Evaluate result ──
    if outcome.status not in (OutcomeStatus.SUCCESS, OutcomeStatus.ACCEPTED):
        error_class = outcome.error_class or "unknown"
        reason = outcome.reason or "repo.attach rejected by server."
        next_steps: list[str] = outcome.repair_guidance or []

        if error_class == "NOT_IMPLEMENTED":
            next_steps = [
                "repo.attach is not yet available on this server.",
                "Ensure the server supports SDK-CLIENT-30.",
            ] + next_steps
        elif error_class == "PLATFORM_REPO_TARGET_FORBIDDEN":
            next_steps = [
                "The server rejected this repo as the platform control repo.",
                "Use your own forked or customer repository.",
            ]

        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=reason,
            data={"error_class": error_class, "run_type": "repo.attach"},
            next_steps=next_steps,
        )

    result_data: Dict[str, Any] = outcome.response_data or {}

    # ── Guard: server must not return PLATFORM_CONTROL repo class ──
    repo_class = result_data.get("repo_class", "")
    if repo_class == _FORBIDDEN_REPO_CLASS:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_FAILURE,
            summary=(
                "PLATFORM_REPO_TARGET_FORBIDDEN: server classified this repo as "
                "PLATFORM_CONTROL. SDK/customer workflows must use a customer or "
                "forked repository, not the platform control repo."
            ),
            data={
                "error_code": "PLATFORM_REPO_TARGET_FORBIDDEN",
                "repo_class": repo_class,
            },
            next_steps=[
                "Use your own forked or customer repository, not keyhole_platform.",
            ],
        )

    # ── Persist binding locally ──
    repo_binding_id = result_data.get("repo_binding_id", "")
    binding_file: Optional[Path] = None
    if repo_binding_id:
        try:
            binding_file = _save_repo_binding(
                repo_path, repo_binding_id, identity, mcp_url
            )
        except OSError as exc:
            # Non-fatal — warn but do not fail the command
            result_data["binding_file_warning"] = (
                f"Could not write .keyhole/repo-binding.json: {exc}"
            )

    summary_parts = [
        f"Repo attached: {identity.slug}",
        f"Branch: {identity.current_branch}",
        f"Commit: {identity.commit_sha[:12]}",
        f"Workspace model: repo-as-workspace",
    ]
    if repo_binding_id:
        summary_parts.insert(1, f"Binding: {repo_binding_id}")

    next_steps_ok = [
        "Run: keyhole gaps claim --gap-id <id> — to claim a gap against this repo.",
        "Run: keyhole governance-context create --gap-id <id> --claim-token <token> — to bind governance context.",
    ]
    if binding_file:
        result_data["binding_file"] = str(binding_file)

    return CommandResult(
        command=command_label,
        success=True,
        exit_code=EXIT_SUCCESS,
        summary="\n".join(summary_parts),
        data={
            "repo_binding_id": repo_binding_id,
            "repo_remote": identity.repo_remote,
            "owner": identity.owner,
            "repo": identity.repo,
            "slug": identity.slug,
            "current_branch": identity.current_branch,
            "commit_sha": identity.commit_sha,
            "dirty_worktree": identity.dirty_worktree,
            "repo_class": repo_class or "CUSTOMER_FORK",
            "workspace_model": "repo-as-workspace",
            "persistent_workspace_created": False,
            **({"binding_file": str(binding_file)} if binding_file else {}),
        },
        next_steps=next_steps_ok,
    )
