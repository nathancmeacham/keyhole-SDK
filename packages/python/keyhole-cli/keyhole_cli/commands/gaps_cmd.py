"""`keyhole gaps` — gap lifecycle commands.

SDK-CLIENT-PUBLIC-REPAIR-01

Surfaces the gap lifecycle through the MCP boundary:
  gaps list   → calls run_type=gaps.list
  gaps create → calls run_type=gaps.create (if server supports it)
  gaps claim  → calls run_type=gaps.claim  (if server supports it)

If the server does not yet support create/claim, the command returns a
clean SERVER_BLOCKED verdict with repair guidance. It does not crash.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from keyhole_sdk.auth import BearerTokenProvider
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.context_lifecycle.compile import compile_context, build_compile_request
from keyhole_sdk.gap_closure import (
    GapClosureClient,
    GapClosureError,
    assert_closure_response_governed,
    build_gap_closure_payload,
    write_closure_artifact,
)
from keyhole_sdk.repo_identity import detect_repo_identity, RepoIdentityError
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


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────

def _build_transport(
    mcp_url: str, keyhole_home: str
) -> tuple[GovernedTransport, CredentialStore]:
    store_dir = Path(keyhole_home) if keyhole_home else None
    cred_store = CredentialStore(store_dir=store_dir)
    try:
        token = get_fresh_token(keyhole_home=keyhole_home or None)
    except (FileNotFoundError, RuntimeError):
        token = ""
    auth_provider = BearerTokenProvider(token=token) if token else None
    transport = GovernedTransport(base_url=mcp_url, auth_provider=auth_provider)
    return transport, cred_store


def _repo_name(repo_path: Path) -> str:
    keyhole_yaml = repo_path / "keyhole.yaml"
    if keyhole_yaml.exists():
        try:
            import yaml  # pyyaml is now a hard dep
            data = yaml.safe_load(keyhole_yaml.read_text(encoding="utf-8"))
            return (data or {}).get("name", repo_path.name)
        except Exception:
            pass
    return repo_path.name


def _preflight_check(
    cred_store: CredentialStore, command_label: str
) -> Optional[CommandResult]:
    session = cred_store.load()
    if not session or not session.access_token:
        return CommandResult(
            command=command_label,
            success=False,
            exit_code=EXIT_RUNTIME_UNAVAILABLE,
            summary="Not authenticated. Run: keyhole login",
            next_steps=["keyhole login", f"Then: {command_label}"],
        )
    return None


def _get_canonical_digest(transport: GovernedTransport, repo_name: str) -> str:
    """Fetch the current canonical ctxpack_digest from gaps.status.

    Returns the hex digest string (without 'sha256:' prefix) or empty string
    if the canonical cannot be retrieved. Falls back gracefully.
    """
    try:
        status_req = build_run_request(
            run_type="gaps.status",
            repo_name=repo_name,
            context_ref=None,
            input_data=None,
            correlation_id=generate_request_id(),
        )
        outcome = dispatch_run(transport=transport, request=status_req)
        if outcome.status == OutcomeStatus.SUCCESS and outcome.response_data:
            data = outcome.response_data
            # data may be nested under 'data' key
            canonical_section = data.get("canonical") or (data.get("data") or {}).get("canonical") or {}
            raw = canonical_section.get("current_canonical_digest", "")
            # Strip 'sha256:' prefix if present
            if raw.startswith("sha256:"):
                raw = raw[len("sha256:"):]
            return raw.strip()
    except Exception:
        pass
    return ""


def _dispatch_gaps_run(
    *,
    run_type: str,
    input_data: Optional[Dict[str, Any]],
    command_label: str,
    mcp_url: str,
    keyhole_home: str,
    repo_dir: str,
) -> CommandResult:
    repo_path = Path(repo_dir).resolve()
    transport, cred_store = _build_transport(mcp_url, keyhole_home)

    gate = _preflight_check(cred_store, command_label)
    if gate is not None:
        transport.close()
        return gate

    # Auto-resolve context digest for write-bearing run types.
    # Prefer the server's canonical digest from gaps.status over the per-request
    # ctx_ref_sha256 returned by context.compile (which changes each call and
    # never matches the canonical used by the gap reconciler).
    _READ_ONLY_RUNS = {"gaps.list", "gaps.next_open_canonical", "gaps.get", "gaps.status"}
    context_ref: Optional[str] = None
    if run_type not in _READ_ONLY_RUNS:
        repo_name = _repo_name(repo_path)
        # Primary: use canonical digest from gaps.status
        canonical = _get_canonical_digest(transport, repo_name)
        if canonical:
            context_ref = canonical
        else:
            # Fallback: use context.compile (may return unstable per-request hash)
            try:
                compile_req = build_compile_request(
                    repo_name=repo_name,
                    correlation_id=generate_request_id(),
                )
                compile_result = compile_context(transport=transport, request=compile_req)
                if compile_result.ctxpack_digest:
                    context_ref = compile_result.ctxpack_digest
            except Exception:
                pass  # compile failure is non-fatal; server will reject with guidance

    correlation_id = generate_request_id()
    # For read-only runs, repo_name may not be set yet
    if run_type in _READ_ONLY_RUNS:
        repo_name = _repo_name(repo_path)
    request = build_run_request(
        run_type=run_type,
        repo_name=repo_name,
        context_ref=context_ref,
        input_data=input_data,
        correlation_id=correlation_id,
    )

    try:
        outcome = dispatch_run(transport=transport, request=request)
    finally:
        transport.close()

    if outcome.status == OutcomeStatus.SUCCESS:
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"{command_label} succeeded.",
            data=outcome.response_data,
        )

    if outcome.status == OutcomeStatus.ACCEPTED:
        # Include response_data so run-type-specific payloads (e.g. claim_token
        # from gaps.claim) are surfaced to the caller even in the ACCEPTED case.
        data: Dict[str, Any] = {
            "status": "ACCEPTED",
            "run_id": outcome.run_id,
            "run_type": run_type,
        }
        if outcome.response_data:
            data.update(outcome.response_data)
        return CommandResult(
            command=command_label,
            success=True,
            exit_code=EXIT_SUCCESS,
            summary=f"Accepted. run_id={outcome.run_id}",
            data=data,
        )

    # Rejected or failed — return clean error, never crash
    reason = outcome.reason or "Server returned a non-success outcome."
    error_class = outcome.error_class or "unknown"
    is_server_blocked = error_class in (
        "BINDING_NOT_FOUND",
        "NO_ENABLED_BINDING",
        "BLOCKED",
        "NOT_IMPLEMENTED",
        "METHOD_NOT_ALLOWED",
    )
    next_steps = outcome.repair_guidance or []
    if is_server_blocked:
        next_steps = [
            "This gap operation is not yet available for your workspace.",
            "Contact your Keyhole operator to enable gap lifecycle for this binding.",
            "Check: keyhole context compile — to confirm workspace binding status.",
        ] + next_steps

    return CommandResult(
        command=command_label,
        success=False,
        exit_code=EXIT_FAILURE,
        summary=reason,
        data={
            "error_class": error_class,
            "run_type": run_type,
            "http_status": outcome.http_status,
        },
        next_steps=next_steps,
    )


# ──────────────────────────────────────────────────────────────
# keyhole gaps list
# ──────────────────────────────────────────────────────────────

def run_gaps_list(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps list``.

    Lists all actionable gaps for the current repo and identity.
    Calls run_type=gaps.list through the MCP boundary.
    """
    return _dispatch_gaps_run(
        run_type="gaps.list",
        input_data=None,
        command_label="keyhole gaps list",
        mcp_url=mcp_url,
        keyhole_home=keyhole_home,
        repo_dir=repo_dir,
    )


# ──────────────────────────────────────────────────────────────
# keyhole gaps create
# ──────────────────────────────────────────────────────────────

def run_gaps_create(
    *,
    capability: str,
    description: str = "",
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps create`` (submits a new gap via gaps.submit).

    Submits a new actionable capability-registration gap.
    Calls run_type=gaps.submit through the MCP boundary.
    If the server does not yet support this run type, returns SERVER_BLOCKED.
    """
    if not capability or not capability.strip():
        return CommandResult(
            command="keyhole gaps create",
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="--capability is required.",
            next_steps=["keyhole gaps create --capability <name>"],
        )

    input_data: Dict[str, Any] = {"capability": capability.strip()}
    if description:
        input_data["description"] = description

    return _dispatch_gaps_run(
        run_type="gaps.submit",
        input_data=input_data,
        command_label="keyhole gaps create",
        mcp_url=mcp_url,
        keyhole_home=keyhole_home,
        repo_dir=repo_dir,
    )


# ──────────────────────────────────────────────────────────────
# keyhole gaps next-open
# ──────────────────────────────────────────────────────────────

def run_gaps_next_open(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps next-open``.

    Returns the next open canonical gap for the current identity.
    Calls run_type=gaps.next_open_canonical through the MCP boundary.
    """
    return _dispatch_gaps_run(
        run_type="gaps.next_open_canonical",
        input_data=None,
        command_label="keyhole gaps next-open",
        mcp_url=mcp_url,
        keyhole_home=keyhole_home,
        repo_dir=repo_dir,
    )


# ──────────────────────────────────────────────────────────────
# keyhole gaps claim
# ──────────────────────────────────────────────────────────────

def run_gaps_claim(
    *,
    gap_id: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps claim``.

    Claims a gap against the current subject repo and retrieves the
    gap_id + claim_token for governance context creation.

    Includes subject repo context (repo_remote, branch, commit_sha,
    repo_binding_id) in the claim request.

    Calls run_type=gaps.claim through the MCP boundary.
    """
    if not gap_id or not gap_id.strip():
        return CommandResult(
            command="keyhole gaps claim",
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="--gap-id is required.",
            next_steps=[
                "keyhole gaps list — to find available gap IDs.",
                "keyhole gaps claim --gap-id <id>",
            ],
        )

    # ── Collect subject repo context ──
    # Included in the claim so the server can bind gap → repo + commit.
    # These fields are distinct from capability name / app name / ctxpack.
    repo_context: Dict[str, Any] = {}
    try:
        identity = detect_repo_identity(repo_dir)
        repo_context = {
            "repo_remote": identity.repo_remote,
            "branch": identity.current_branch,
            "commit_sha": identity.commit_sha,
        }
        if identity.repo_binding_id:
            repo_context["repo_binding_id"] = identity.repo_binding_id
    except RepoIdentityError:
        # Non-fatal — proceed without repo context; server will validate
        pass

    input_data: Dict[str, Any] = {"gap_id": gap_id.strip(), **repo_context}

    return _dispatch_gaps_run(
        run_type="gaps.claim",
        input_data=input_data,
        command_label="keyhole gaps claim",
        mcp_url=mcp_url,
        keyhole_home=keyhole_home,
        repo_dir=repo_dir,
    )


# ──────────────────────────────────────────────────────────────
# keyhole gaps revalidate
# ──────────────────────────────────────────────────────────────

def run_gaps_revalidate(
    *,
    gap_id: str,
    ctxpack_digest: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps revalidate``.

    Revalidates a gap against the current canonical context digest,
    clearing a STALE_REVALIDATION blocker so the gap becomes claimable.
    Calls run_type=gaps.revalidate through the MCP boundary.
    """
    if not gap_id or not gap_id.strip():
        return CommandResult(
            command="keyhole gaps revalidate",
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="--gap-id is required.",
            next_steps=["keyhole gaps list — to find blocked gap IDs.", "keyhole gaps revalidate --gap-id <id> --ctxpack-digest <digest>"],
        )
    if not ctxpack_digest or not ctxpack_digest.strip():
        return CommandResult(
            command="keyhole gaps revalidate",
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="--ctxpack-digest is required. Use the digest from the blocked_reasons.required_action.input field.",
            next_steps=["keyhole gaps list --json — to find the required ctxpack_digest."],
        )

    return _dispatch_gaps_run(
        run_type="gaps.revalidate",
        input_data={"gap_id": gap_id.strip(), "ctxpack_digest": ctxpack_digest.strip()},
        command_label="keyhole gaps revalidate",
        mcp_url=mcp_url,
        keyhole_home=keyhole_home,
        repo_dir=repo_dir,
    )


def run_gaps_close(
    *,
    gap_id: str,
    closure_reason: str,
    closure_classification: str,
    evidence_bundle_hash: str,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
    keyhole_home: str = "",
    requested_by: str = "",
    workspace_id: str = "",
    governed_run_id: str = "",
    receipt_id: str = "",
    proof_id: str = "",
) -> CommandResult:
    """Execute ``keyhole gaps close`` through governed MCP closure."""
    if not gap_id or not gap_id.strip():
        return CommandResult(
            command="keyhole gaps close",
            success=False,
            exit_code=EXIT_INVALID_INPUT,
            summary="--gap-id is required.",
        )
    transport, cred_store = _build_transport(mcp_url, keyhole_home)
    gate = _preflight_check(cred_store, "keyhole gaps close")
    transport.close()
    if gate is not None:
        return gate
    try:
        token = getattr(transport.auth_provider, "token", "") if transport.auth_provider else ""
        payload = build_gap_closure_payload(
            repo_dir=repo_dir,
            gap_id=gap_id.strip(),
            closure_reason=closure_reason,
            closure_classification=closure_classification,
            evidence_bundle_hash=evidence_bundle_hash,
            workspace_id=workspace_id,
            requested_by=requested_by,
            governed_run_id=governed_run_id,
            receipt_id=receipt_id,
            proof_id=proof_id,
        )
        client = GapClosureClient(mcp_url=mcp_url, token=token)
        preflight = client.preflight(gap_id=payload.gap_id)
        response = client.submit_closure(payload)
        assert_closure_response_governed(response)
        repo_path = Path(repo_dir).resolve()
        state_dir = repo_path / ".keyhole" / "gap-closures" / payload.gap_id
        write_closure_artifact(state_dir / "closure_request.json", payload.to_dict())
        write_closure_artifact(state_dir / "server_preflight.json", preflight)
        write_closure_artifact(state_dir / "closure_response.json", response)
        return CommandResult(
            command="keyhole gaps close",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed gap closure accepted by server.",
            data={
                "gap_id": payload.gap_id,
                "closure_request": payload.to_dict(),
                "server_preflight": preflight,
                "closure_response": response,
                "local_state_dir": str(state_dir),
            },
        )
    except GapClosureError as exc:
        return CommandResult(
            command="keyhole gaps close",
            success=False,
            exit_code=EXIT_FAILURE,
            summary=str(exc),
            data={"error_class": "GapClosureError"},
            next_steps=[
                "Confirm /health/event-spine is PASS or PASS_WITH_LEGACY_WARNINGS.",
                "Confirm the target gap is still OPEN with no closure lineage.",
                "Do not treat local test success as closure without server close_verdict_ref.",
            ],
        )
