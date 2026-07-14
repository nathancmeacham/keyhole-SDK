"""Generic governed repository flow for forked SDK/client repos."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from keyhole_sdk.governed_demo import (
    ASYNC_ACTIVE_STATUSES,
    ASYNC_TERMINAL_STATUSES,
    GovernedDemoError,
    GovernedFirstAppClient,
    _candidate_digest,
    _extract_claim_id,
    _extract_claim_ref,
    _extract_context_digest,
    _extract_context_id,
    _file_digest,
    _first_string,
    _json_object,
    _load_yaml,
    _normalize_governance_receipt,
    _raise_for_mcp_error,
    _raise_for_response,
    _read_state,
    _redact,
    _repo_git_metadata,
    _run_local_invariant,
    _select_gap_id,
    _unwrap_mcp_envelope,
    _valid_ctxpack_digest,
    _validate_governed_receipt,
    _write_state,
    BoundaryOperation,
    CONTEXT_STATE,
    RECEIPT_STATE,
    REGISTRATION_STATE,
)
from keyhole_sdk.models import GovernanceReceipt


GENERIC_GAP_ID_OVERRIDE_ENV = "KEYHOLE_GOVERNED_GAP_ID"
GOVERNED_RUNS_DIRNAME = "governed-runs"
LATEST_STATE = "latest.json"
RUNS_DIR = "runs"


@dataclass
class RepoDeclaration:
    repo_dir: Path
    repo_name: str
    repo_remote: str
    commit_sha: str
    branch: str = ""
    repo_class: str = ""
    story_id: str = ""
    capability_id: str = ""
    declaration_file_digests: Dict[str, str] = field(default_factory=dict)
    native_artifacts: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class GovernedRunStateStore:
    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = repo_dir.resolve()
        self.state_dir = self.repo_dir / ".keyhole" / GOVERNED_RUNS_DIRNAME
        self.runs_dir = self.state_dir / RUNS_DIR

    def write(self, state: Dict[str, Any], *, update_latest: bool = True) -> Dict[str, Any]:
        payload = _sanitize_state(state)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        run_key = str(payload.get("run_record_id") or _safe_timestamp())
        payload["run_record_id"] = run_key
        latest_path = self.state_dir / LATEST_STATE
        run_path = self.runs_dir / f"{run_key}.json"
        body = json.dumps(payload, indent=2)
        if update_latest:
            latest_path.write_text(body, encoding="utf-8")
        run_path.write_text(body, encoding="utf-8")
        return payload

    def load_latest(self) -> Dict[str, Any]:
        path = self.state_dir / LATEST_STATE
        if not path.exists():
            raise GovernedDemoError(
                f"missing governed run state: {path}. Run 'keyhole governed run --repo-dir {self.repo_dir}' first."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise GovernedDemoError(f"invalid governed run state: {path}")
        return data


class GovernedRepoFlowClient(GovernedFirstAppClient):
    """Reusable governed flow client for arbitrary forked repositories."""

    def __init__(
        self,
        *,
        mcp_url: str,
        token: str,
        runtime_url: str = "",
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
        story_id: str = "",
        capability_id: str = "",
        repo_class: str = "",
        gap_id: str = "",
    ) -> None:
        super().__init__(
            mcp_url=mcp_url,
            token=token,
            runtime_url=runtime_url,
            session=session,
            timeout=timeout,
            story_id=story_id,
            capability_id=capability_id,
            repo_class=repo_class,
            gap_override_env=GENERIC_GAP_ID_OVERRIDE_ENV,
            purpose="generic governed forked SDK repo flow",
        )
        self.operator_gap_id = gap_id
        self.repo_declaration: Optional[RepoDeclaration] = None
        self.state_store: Optional[GovernedRunStateStore] = None
        self.current_state: Dict[str, Any] = {}
        self.current_repo: Optional[Path] = None
        self.gap_id_claimable_verified = False

    def _resolve_gap_id(self, repo: Path) -> str:
        if self.operator_gap_id:
            if not self.operator_gap_id.startswith("gap_"):
                raise GovernedDemoError("--gap-id must be a canonical gap_* id.")
            self.resolved_gap_id = self.operator_gap_id
            self.gap_id_source = "operator --gap-id"
            self.gap_id_claimable_verified = True
            return self.operator_gap_id
        try:
            gap_id = super()._resolve_gap_id(repo)
            self.gap_id_claimable_verified = self.gap_id_source == "gaps.list"
            return gap_id
        except GovernedDemoError as exc:
            raise GovernedDemoError(
                f"{exc} Run 'keyhole gaps list --json' to inspect claimable gaps, "
                "or pass an explicit canonical gap with --gap-id gap_..."
            ) from exc

    @classmethod
    def from_env(
        cls,
        *,
        runtime_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
        story_id: str = "",
        capability_id: str = "",
        repo_class: str = "",
        gap_id: str = "",
    ) -> "GovernedRepoFlowClient":
        return cls(
            mcp_url=os.environ.get("KEYHOLE_MCP_URL", ""),
            token=os.environ.get("KEYHOLE_MCP_TOKEN", ""),
            runtime_url=runtime_url or os.environ.get("KEYHOLE_RUNTIME_URL", ""),
            session=session,
            story_id=story_id,
            capability_id=capability_id,
            repo_class=repo_class,
            gap_id=gap_id,
        )

    def inspect_repo(self, repo_path: str | Path, *, persist_state: bool = True) -> RepoDeclaration:
        repo = Path(repo_path).resolve()
        declaration = read_repo_declaration(
            repo,
            story_id=self.story_id,
            capability_id=self.capability_id,
            repo_class=self.repo_class,
        )
        self.repo_declaration = declaration
        self.current_repo = declaration.repo_dir
        self.state_store = GovernedRunStateStore(declaration.repo_dir)
        self.story_id = declaration.story_id
        self.gap_label = declaration.story_id
        self.capability_id = declaration.capability_id
        self.repo_class = declaration.repo_class
        if persist_state:
            self._persist_state({
                "repo_dir": str(declaration.repo_dir),
                "repo_name": declaration.repo_name,
                "repo_remote": declaration.repo_remote,
                "commit_sha": declaration.commit_sha,
                "branch": declaration.branch,
                "repo_class": declaration.repo_class,
                "story_id": declaration.story_id,
                "capability_id": declaration.capability_id,
                "declaration_file_digests": declaration.declaration_file_digests,
                "status": "initialized",
                "terminal": False,
            })
        return declaration

    def load_last_state(self, repo_dir: str | Path) -> Dict[str, Any]:
        repo = Path(repo_dir).resolve()
        self.current_repo = repo
        self.state_store = GovernedRunStateStore(repo)
        self.current_state = self.state_store.load_latest()
        declaration = read_repo_declaration(
            repo,
            story_id=str(self.current_state.get("story_id") or self.story_id),
            capability_id=str(self.current_state.get("capability_id") or self.capability_id),
            repo_class=str(self.current_state.get("repo_class") or self.repo_class),
        )
        self.repo_declaration = declaration
        self.story_id = declaration.story_id
        self.capability_id = declaration.capability_id
        self.repo_class = declaration.repo_class
        if self.current_state.get("resolved_gap_id"):
            self.resolved_gap_id = str(self.current_state["resolved_gap_id"])
            self.gap_id_source = str(self.current_state.get("gap_id_source") or "")
            self.gap_id_claimable_verified = False
        return dict(self.current_state)

    def run_governed_repo_flow(
        self,
        repo_dir: str | Path,
        *,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        declaration = self.inspect_repo(repo_dir, persist_state=False)
        self.discover()
        if dry_run:
            gap_id = self.operator_gap_id or self._resolve_gap_id(declaration.repo_dir)
            return {
                "dry_run": True,
                "repo": _public_declaration(declaration),
                "resolved_gap_id": gap_id,
                "gap_id_source": self.gap_id_source,
                "would_mutate_mcp": False,
            }
        return self.resume_governed_repo_flow(repo_dir, use_last_state=True)

    def resume_governed_repo_flow(
        self,
        repo_dir: str | Path,
        *,
        use_last_state: bool = True,
    ) -> Dict[str, Any]:
        repo = Path(repo_dir).resolve()
        if use_last_state:
            try:
                self.load_last_state(repo)
            except GovernedDemoError:
                self.inspect_repo(repo)
        else:
            self.inspect_repo(repo)
        self.discover()
        self._recover_pending_run()
        declaration = self.repo_declaration or self.inspect_repo(repo)
        if not self.current_state.get("resolved_gap_id"):
            try:
                gap_id = self._resolve_gap_id(declaration.repo_dir)
            except GovernedDemoError as exc:
                self._persist_gap_resolution_error(exc)
                raise
            self._persist_state({
                "resolved_gap_id": gap_id,
                "gap_id_source": self.gap_id_source,
                "status": "gap_resolved",
                "step": "gap_resolved",
                "terminal": False,
            })
        if not (self.current_state.get("claim_id") or self.current_state.get("claim_ref")):
            claim = self.claim_gap(declaration.repo_dir)
            self._persist_state({
                "claim_id": claim.get("claim_id", ""),
                "claim_ref": claim.get("claim_ref", ""),
                "claim_ctxpack_digest": claim.get("ctxpack_digest", ""),
                "resolved_gap_id": claim.get("gap_id", self.resolved_gap_id),
                "gap_id_source": claim.get("gap_id_source", self.gap_id_source),
                "status": "claim_succeeded",
                "step": "claim_succeeded",
                "terminal": False,
            })
        if not self.current_state.get("registration_id"):
            registration = self.register_repo(declaration.repo_dir)
            self._persist_state({
                "registration_id": registration.get("registration_id", ""),
                "resolved_gap_id": registration.get("gap_id", self.resolved_gap_id),
                "gap_id_source": registration.get("gap_id_source", self.gap_id_source),
                "claim_id": registration.get("claim_id", self.current_state.get("claim_id", "")),
                "claim_ref": registration.get("claim_ref", self.current_state.get("claim_ref", "")),
                "claim_ctxpack_digest": registration.get(
                    "claim_ctxpack_digest",
                    self.current_state.get("claim_ctxpack_digest", ""),
                ),
                "status": "context_created",
                "step": "context_created",
                "terminal": False,
            })
        if not self.current_state.get("governance_context_id"):
            context = self.compile_context(declaration.repo_dir)
            self._persist_state({
                "governance_context_id": context.get("governance_context_id", ""),
                "ctxpack_digest": context.get("ctxpack_digest", context.get("governance_context_id", "")),
                "status": "context_compiled",
                "step": "context_compiled",
                "terminal": False,
            })
        if self.current_state.get("receipt_id") and self.current_state.get("terminal") is True:
            return self._result_from_state(declaration)
        receipt = self.run_governed_realization(declaration.repo_dir)
        receipt_dict = receipt.model_dump(mode="json")
        self._persist_state({
            "status": "succeeded",
            "step": "receipt_ready",
            "terminal": True,
            "live_confirmed": True,
            "run_id": "",
            "poll_url": "",
            **_receipt_state(receipt_dict),
        })
        return self._result_from_state(declaration)

    def status_governed_repo_flow(self, repo_dir: str | Path) -> Dict[str, Any]:
        state = self.load_last_state(repo_dir)
        self.discover()
        self._recover_pending_run()
        state = dict(self.current_state)
        state["live_confirmed"] = bool(state.get("live_confirmed", False))
        return _redact(state)

    def receipt_governed_repo_flow(self, repo_dir: str | Path) -> Dict[str, Any]:
        state = self.load_last_state(repo_dir)
        if not state.get("receipt_id") and not state.get("proof_id"):
            raise GovernedDemoError(
                f"no governed receipt found for {repo_dir}. Run 'keyhole governed run --repo-dir {repo_dir}' first."
            )
        return _redact({
            "live_confirmed": bool(state.get("live_confirmed", False)),
            "receipt": {
                "digest": state.get("digest", ""),
                "status": state.get("status", ""),
                "message": state.get("message", ""),
                "realized_at": state.get("realized_at", ""),
                "governed": state.get("governed", False),
                "event_spine_evidence": state.get("event_spine_evidence", False),
                "governance_verdict": state.get("governance_verdict", ""),
                "drift_state": state.get("drift_state", ""),
                "governance_context_id": state.get("governance_context_id", ""),
                "mcp_event_id": state.get("mcp_event_id", ""),
                "proof_id": state.get("proof_id", ""),
                "receipt_id": state.get("receipt_id", ""),
                "passport_digest": state.get("passport_digest", ""),
                "trust_digest": state.get("trust_digest", ""),
            },
        })

    def register_repo(self, repo_path: str | Path) -> Dict[str, Any]:
        self._ensure_discovered()
        op = self._require_operation("repo.register")
        repo = Path(repo_path).resolve()
        claim = {
            "claim_id": str(self.current_state.get("claim_id") or ""),
            "claim_ref": str(self.current_state.get("claim_ref") or ""),
            "gap_id": str(self.current_state.get("resolved_gap_id") or self.resolved_gap_id or self.story_id),
            "gap_id_source": str(self.current_state.get("gap_id_source") or self.gap_id_source),
            "ctxpack_digest": str(self.current_state.get("claim_ctxpack_digest") or ""),
        }
        if not (claim["claim_id"] or claim["claim_ref"]) and _requires_active_claim(self.capabilities):
            claim = self.claim_gap(repo)
        if not claim.get("ctxpack_digest"):
            claim["ctxpack_digest"] = self._current_canonical_digest(repo)
        payload = _build_generic_registration_payload(self, repo, op, claim)
        response = self.session.request(
            op.method,
            f"{self.mcp_url}{op.path}",
            headers=self._headers(idempotent=True),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_response(response, "repo registration")
        data = _json_object(response)
        _raise_for_mcp_error(data, "repo registration")
        data = self._resolve_async_result(data, "repo registration")
        registration_id = _first_string(
            data.get("registration_id"),
            data.get("repo_id"),
            data.get("declaration_id"),
            data.get("governance_context_id"),
            data.get("ctxpack_digest"),
            data.get("id"),
            (data.get("result") or {}).get("registration_id") if isinstance(data.get("result"), dict) else "",
            (data.get("result") or {}).get("repo_id") if isinstance(data.get("result"), dict) else "",
            (data.get("result") or {}).get("declaration_id") if isinstance(data.get("result"), dict) else "",
            (data.get("result") or {}).get("governance_context_id") if isinstance(data.get("result"), dict) else "",
            (data.get("data") or {}).get("registration_id") if isinstance(data.get("data"), dict) else "",
            ((data.get("data") or {}).get("result") or {}).get("registration_id")
            if isinstance((data.get("data") or {}).get("result"), dict) else "",
        )
        if not registration_id:
            raise GovernedDemoError(
                "repo.register response missing registration_id/repo_id/declaration_id/governance_context_id."
            )
        state = {
            "registration_id": registration_id,
            "claim_id": claim.get("claim_id", ""),
            "claim_ref": claim.get("claim_ref", ""),
            "claim_ctxpack_digest": claim.get("ctxpack_digest", ""),
            "gap_id": claim.get("gap_id", self.story_id),
            "story_id": self.story_id,
            "gap_id_source": claim.get("gap_id_source", self.gap_id_source),
            "upstream": _redact(data),
        }
        _write_state(repo, REGISTRATION_STATE, state)
        return state

    def claim_gap(self, repo_path: str | Path) -> Dict[str, Any]:
        repo = Path(repo_path).resolve()
        self._refresh_cached_gap_claimability(repo)
        return super().claim_gap(repo)

    def _refresh_cached_gap_claimability(self, repo: Path) -> None:
        if self.gap_id_claimable_verified or self.operator_gap_id:
            return
        cached_gap_id = str(self.current_state.get("resolved_gap_id") or self.resolved_gap_id or "")
        if not cached_gap_id:
            return
        self.resolved_gap_id = ""
        try:
            live_gap_id = self._resolve_gap_id(repo)
        except GovernedDemoError as exc:
            self.resolved_gap_id = cached_gap_id
            self._persist_state({
                "status": "no_claimable_gap",
                "step": "gap_resolved",
                "terminal": False,
                "error_code": "NO_CLAIMABLE_GAP",
                "error_message": str(exc),
            })
            raise
        if live_gap_id != cached_gap_id:
            self._persist_state({
                "resolved_gap_id": live_gap_id,
                "gap_id_source": self.gap_id_source,
                "status": "gap_resolved",
                "step": "gap_resolved",
                "terminal": False,
            })

    def _persist_gap_resolution_error(self, exc: GovernedDemoError) -> None:
        message = str(exc)
        self._persist_state({
            "status": "no_claimable_gap" if "NO_CLAIMABLE_GAP" in message else "gap_resolution_failed",
            "step": "gap_resolution",
            "terminal": False,
            "error_code": "NO_CLAIMABLE_GAP" if "NO_CLAIMABLE_GAP" in message else "GAP_RESOLUTION_FAILED",
            "error_message": message,
        })

    def compile_context(self, repo_path: str | Path) -> Dict[str, Any]:
        self._ensure_discovered()
        op = self._require_operation("context.compile")
        repo = Path(repo_path).resolve()
        registration_id = str(self.current_state.get("registration_id") or "")
        if not registration_id:
            registration = _read_state(repo, REGISTRATION_STATE)
            registration_id = str(registration.get("registration_id") or "")
        payload = {
            "run_type": op.run_type or "context.compile",
            "params": {
                "repo": repo.name,
                "registration_id": registration_id,
                "gap_id": str(self.current_state.get("resolved_gap_id") or self.story_id),
                "story_id": self.story_id,
            },
        }
        context_ref = _first_string(
            self.current_state.get("claim_ctxpack_digest"),
            self._current_canonical_digest(repo),
        )
        if context_ref:
            payload["ctxpack_digest"] = context_ref
            payload["context_ref"] = context_ref
            payload["params"]["ctxpack_digest"] = context_ref
        response = self.session.request(
            op.method,
            f"{self.mcp_url}{op.path}",
            headers=self._headers(idempotent=True),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_response(response, "context compile")
        data = _json_object(response)
        _raise_for_mcp_error(data, "context compile")
        data = self._resolve_async_result(data, "context compile")
        context_id = _extract_context_id(data)
        ctxpack_digest = _extract_context_digest(data) or context_id
        if not context_id:
            raise GovernedDemoError("context.compile response missing governance_context_id or context digest.")
        state = {
            "governance_context_id": context_id,
            "ctxpack_digest": ctxpack_digest,
            "registration_id": registration_id,
            "upstream": _redact(data),
        }
        _write_state(repo, CONTEXT_STATE, state)
        return state

    def run_governed_realization(self, repo_path: str | Path) -> GovernanceReceipt:
        self._ensure_discovered()
        repo = Path(repo_path).resolve()
        context_id = str(self.current_state.get("governance_context_id") or "")
        context_ref = _valid_ctxpack_digest(self.current_state.get("ctxpack_digest"))
        context_state: Dict[str, Any] = {}
        if not context_id:
            context_state = _read_state(repo, CONTEXT_STATE)
            context_id = str(context_state.get("governance_context_id") or "")
        if not context_ref:
            if not context_state:
                try:
                    context_state = _read_state(repo, CONTEXT_STATE)
                except GovernedDemoError:
                    context_state = {}
            context_ref = _first_string(
                _valid_ctxpack_digest(context_state.get("ctxpack_digest")),
                _extract_context_digest(context_state.get("upstream") if isinstance(context_state.get("upstream"), dict) else {}),
                _valid_ctxpack_digest(context_id),
            )
        local_invariant = _run_local_invariant(repo, self.capability_id)
        candidate_digest = _candidate_digest(repo, local_invariant, {"governance_context_id": context_id})
        state_update = {"candidate_digest": candidate_digest}
        if context_ref:
            state_update["ctxpack_digest"] = context_ref
        self._persist_state(state_update)
        op = self._require_operation("governed.realize")
        request = {
            "run_type": op.run_type or "governed.realize",
            "params": {
                "candidate_digest": candidate_digest,
                "require_governed": True,
                "governance_context_id": context_id,
                "local_invariant_result": local_invariant,
            },
        }
        if context_ref:
            request["ctxpack_digest"] = context_ref
            request["context_ref"] = context_ref
        if op.surface == "runtime":
            response = self.session.post(
                f"{self.runtime_url}/realize",
                json=dict(request["params"]),
                timeout=self.timeout,
            )
        else:
            response = self.session.request(
                op.method,
                f"{self.mcp_url}{op.path}",
                headers=self._headers(idempotent=True),
                json=request,
                timeout=self.timeout,
            )
        _raise_for_response(response, "governed runtime realization")
        data = _json_object(response)
        _raise_for_mcp_error(data, "governed runtime realization")
        data = self._resolve_async_result(data, "governed runtime realization")
        receipt = GovernanceReceipt.model_validate(_normalize_governance_receipt(data, candidate_digest))
        _validate_governed_receipt(receipt)
        _write_state(repo, RECEIPT_STATE, _redact(receipt.model_dump(mode="json")))
        return receipt

    def _resolve_async_result(self, data: Dict[str, Any], action: str) -> Dict[str, Any]:
        inner = data.get("data") if isinstance(data.get("data"), dict) else {}
        status = _first_string(inner.get("status"), data.get("status")).lower()
        if status not in ASYNC_ACTIVE_STATUSES:
            return data
        run_id = _first_string(inner.get("run_id"), data.get("run_id"))
        poll_url = _first_string(inner.get("poll_url"), data.get("poll_url"))
        correlation_id = _first_string(inner.get("correlation_id"), data.get("correlation_id"))
        self._persist_state({
            "step": _state_step(action),
            "status": status or "accepted",
            "terminal": False,
            "run_id": run_id,
            "poll_url": poll_url,
            "correlation_id": correlation_id or self.current_state.get("correlation_id", ""),
        })
        return super()._resolve_async_result(data, action)

    def _run_gap_discovery(self, op: BoundaryOperation, params: Dict[str, Any], repo: Path) -> str:
        payload = {
            "run_type": op.run_type,
            "params": params,
        }
        response = self.session.request(
            op.method,
            f"{self.mcp_url}{op.path}",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_response(response, "gap discovery")
        data = _json_object(response)
        _raise_for_mcp_error(data, "gap discovery")
        data = self._resolve_async_result(data, "gap discovery")
        return _select_gap_id(data, repo.name, self.story_id, self.capability_id)

    def _poll_saved_run(self) -> Dict[str, Any]:
        run_id = str(self.current_state.get("run_id") or "")
        poll_url = str(self.current_state.get("poll_url") or "")
        if not run_id and not poll_url:
            return dict(self.current_state)
        paths = []
        if poll_url:
            paths.append(poll_url)
        if run_id:
            paths.append(f"/mcp/v1/runs/{run_id}")
            paths.append(f"/mcp/v1/runs/{run_id}/status")
        last_error = ""
        for path in dict.fromkeys(paths):
            response = self.session.get(
                f"{self.mcp_url}{path}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if response.status_code == 404:
                self._persist_state({
                    "status": "RUN_NOT_FOUND",
                    "error_code": "RUN_NOT_FOUND",
                    "error_message": f"saved MCP run was not found: {run_id or poll_url}",
                    "terminal": False,
                })
                raise GovernedDemoError("RUN_NOT_FOUND: saved MCP run was not found; local state was preserved.")
            _raise_for_response(response, "governed run status")
            data = _json_object(response)
            _raise_for_mcp_error(data, "governed run status")
            inner = data.get("data") if isinstance(data.get("data"), dict) else {}
            status = _first_string(inner.get("status"), data.get("status")).lower()
            if status in ASYNC_TERMINAL_STATUSES or inner.get("is_terminal") is True:
                if status in {"failed", "canceled", "cancelled", "timed_out"}:
                    error = inner.get("error") if isinstance(inner.get("error"), dict) else {}
                    code = _first_string(error.get("code"), inner.get("terminal_reason"), "RUN_FAILED")
                    message = _first_string(error.get("message"), code)
                    self._persist_state({
                        "status": code,
                        "error_code": code,
                        "error_message": message,
                        "terminal": True,
                    })
                    raise GovernedDemoError(f"{code}: {message}")
                self._update_state_from_result(data)
                return dict(self.current_state)
            last_error = status or "pending"
        self._persist_state({"status": last_error or "pending", "terminal": False})
        return dict(self.current_state)

    def _recover_pending_run(self) -> None:
        if self.current_state.get("terminal") is True:
            return
        if self.current_state.get("run_id") or self.current_state.get("poll_url"):
            self._poll_saved_run()

    def _update_state_from_result(self, data: Dict[str, Any]) -> None:
        step = str(self.current_state.get("step") or "")
        updates: Dict[str, Any] = {
            "run_id": "",
            "poll_url": "",
            "terminal": False,
        }
        if step == "gap_discovery":
            if self.current_repo is not None:
                gap_id = _select_gap_id(data, self.current_repo.name, self.story_id, self.capability_id)
                if gap_id:
                    self.resolved_gap_id = gap_id
                    updates.update({
                        "resolved_gap_id": gap_id,
                        "gap_id_source": self.gap_id_source or "gaps.list",
                        "status": "gap_resolved",
                        "step": "gap_resolved",
                    })
        elif step == "gap_claim":
            updates.update({
                "claim_id": _extract_claim_id(data),
                "claim_ref": _extract_claim_ref(data),
                "status": "claim_succeeded",
                "step": "claim_succeeded",
            })
        elif step == "context_create":
            registration_id = _first_string(
                data.get("registration_id"),
                data.get("repo_id"),
                data.get("declaration_id"),
                ((data.get("result") or {}).get("registration_id") if isinstance(data.get("result"), dict) else ""),
            )
            updates.update({
                "registration_id": registration_id,
                "status": "context_created",
                "step": "context_created",
            })
        elif step in {"preclaim_context", "context_compile"}:
            context_id = _extract_context_id(data)
            ctxpack_digest = _extract_context_digest(data) or context_id
            updates.update({
                "governance_context_id": context_id,
                "ctxpack_digest": ctxpack_digest,
                "status": "context_compiled" if step == "context_compile" else "preclaim_context_ready",
                "step": "context_compiled" if step == "context_compile" else "preclaim_context_ready",
            })
        elif step == "governed_realize":
            candidate_digest = str(self.current_state.get("candidate_digest") or "")
            receipt = GovernanceReceipt.model_validate(_normalize_governance_receipt(data, candidate_digest))
            _validate_governed_receipt(receipt)
            updates.update({
                "status": "succeeded",
                "step": "receipt_ready",
                "terminal": True,
                "live_confirmed": True,
                **_receipt_state(receipt.model_dump(mode="json")),
            })
        self._persist_state(updates)

    def _result_from_state(self, declaration: RepoDeclaration) -> Dict[str, Any]:
        return {
            "dry_run": False,
            "repo": _public_declaration(declaration),
            "resolved_gap_id": self.current_state.get("resolved_gap_id", ""),
            "gap_id_source": self.current_state.get("gap_id_source", ""),
            "claim_id": self.current_state.get("claim_id", ""),
            "claim_ref": self.current_state.get("claim_ref", ""),
            "registration_id": self.current_state.get("registration_id", ""),
            "governance_context_id": self.current_state.get("governance_context_id", ""),
            "receipt": {
                "digest": self.current_state.get("digest", ""),
                "status": self.current_state.get("status", ""),
                "message": self.current_state.get("message", ""),
                "realized_at": self.current_state.get("realized_at", ""),
                "governed": self.current_state.get("governed", False),
                "event_spine_evidence": self.current_state.get("event_spine_evidence", False),
                "governance_verdict": self.current_state.get("governance_verdict", ""),
                "drift_state": self.current_state.get("drift_state", ""),
                "governance_context_id": self.current_state.get("governance_context_id", ""),
                "mcp_event_id": self.current_state.get("mcp_event_id", ""),
                "proof_id": self.current_state.get("proof_id", ""),
                "receipt_id": self.current_state.get("receipt_id", ""),
                "passport_digest": self.current_state.get("passport_digest", ""),
                "trust_digest": self.current_state.get("trust_digest", ""),
            },
        }

    def _persist_state(self, updates: Dict[str, Any], *, update_latest: bool = True) -> Dict[str, Any]:
        if self.current_repo is None and self.repo_declaration is not None:
            self.current_repo = self.repo_declaration.repo_dir
        if self.state_store is None and self.current_repo is not None:
            self.state_store = GovernedRunStateStore(self.current_repo)
        now = _iso_now()
        if not self.current_state:
            self.current_state = {
                "run_record_id": _safe_timestamp(),
                "created_at": now,
                "updated_at": now,
                "terminal": False,
            }
        merged = dict(self.current_state)
        merged.update({k: v for k, v in updates.items() if v is not None})
        merged["updated_at"] = now
        merged.setdefault("created_at", now)
        if self.state_store is not None:
            merged = self.state_store.write(merged, update_latest=update_latest)
        self.current_state = merged
        return merged


def run_governed_repo_flow(
    *,
    repo_dir: str | Path,
    mcp_url: str,
    token: str,
    runtime_url: str = "",
    story_id: str = "",
    capability_id: str = "",
    repo_class: str = "",
    gap_id: str = "",
    dry_run: bool = False,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    client = GovernedRepoFlowClient(
        mcp_url=mcp_url,
        token=token,
        runtime_url=runtime_url,
        story_id=story_id,
        capability_id=capability_id,
        repo_class=repo_class,
        gap_id=gap_id,
        session=session,
    )
    return client.run_governed_repo_flow(repo_dir, dry_run=dry_run)


def read_repo_declaration(
    repo: Path,
    *,
    story_id: str = "",
    capability_id: str = "",
    repo_class: str = "",
) -> RepoDeclaration:
    required = ["keyhole.yaml", "governance_contract.yaml", "capability_passport.yaml", "dependencies.yaml"]
    missing = [name for name in required if not (repo / name).exists()]
    if missing:
        raise GovernedDemoError("missing governance declaration file(s): " + ", ".join(missing))
    keyhole = _load_yaml(repo / "keyhole.yaml")
    contract = _load_yaml(repo / "governance_contract.yaml")
    passport = _load_yaml(repo / "capability_passport.yaml")
    dependencies = _load_yaml(repo / "dependencies.yaml")
    metadata = _repo_git_metadata(repo)
    derived_capability = capability_id or _first_capability(contract, passport)
    if not derived_capability:
        raise GovernedDemoError("cannot derive capability_id from declaration files; pass --capability-id.")
    derived_repo_class = repo_class or str(keyhole.get("repo_class") or keyhole.get("kind") or "")
    if not derived_repo_class:
        repo_meta = keyhole.get("repo_meta") if isinstance(keyhole.get("repo_meta"), dict) else {}
        derived_repo_class = str(repo_meta.get("kind") or "")
    if derived_repo_class.lower() == "vertical":
        derived_repo_class = "SDK_TEMPLATE"
    if not derived_repo_class:
        raise GovernedDemoError("cannot derive repo_class from declaration files; pass --repo-class.")
    derived_story_id = story_id or str(keyhole.get("story_id") or contract.get("story_id") or "")
    return RepoDeclaration(
        repo_dir=repo,
        repo_name=str(keyhole.get("repo") or repo.name),
        repo_remote=metadata["repo_remote"],
        commit_sha=metadata["commit_sha"],
        branch=metadata.get("branch", ""),
        repo_class=derived_repo_class,
        story_id=derived_story_id,
        capability_id=derived_capability,
        declaration_file_digests={
            "keyhole_yaml_digest": _file_digest(repo / "keyhole.yaml"),
            "governance_contract_digest": _file_digest(repo / "governance_contract.yaml"),
            "capability_passport_digest": _file_digest(repo / "capability_passport.yaml"),
            "dependencies_digest": _file_digest(repo / "dependencies.yaml"),
        },
        native_artifacts={
            "keyhole": keyhole,
            "governance_contract": contract,
            "capability_passport": passport,
            "dependencies": dependencies,
        },
    )


def _first_capability(contract: Dict[str, Any], passport: Dict[str, Any]) -> str:
    produces = contract.get("produces") if isinstance(contract.get("produces"), list) else []
    if produces:
        return str(produces[0])
    capabilities = passport.get("capabilities") if isinstance(passport.get("capabilities"), list) else []
    for capability in capabilities:
        if isinstance(capability, dict):
            name = str(capability.get("name") or capability.get("capability") or "")
            if name:
                return name
    return str(passport.get("capability") or "")


def _public_declaration(declaration: RepoDeclaration) -> Dict[str, Any]:
    return _redact({
        "repo_name": declaration.repo_name,
        "repo_remote": declaration.repo_remote,
        "commit_sha": declaration.commit_sha,
        "branch": declaration.branch,
        "repo_class": declaration.repo_class,
        "story_id": declaration.story_id,
        "capability_id": declaration.capability_id,
        "declaration_file_digests": declaration.declaration_file_digests,
    })


def _state_step(action: str) -> str:
    return {
        "gap discovery": "gap_discovery",
        "gap claim": "gap_claim",
        "repo registration": "context_create",
        "pre-claim context compile": "preclaim_context",
        "context compile": "context_compile",
        "governed runtime realization": "governed_realize",
    }.get(action, action.replace(" ", "_"))


def _receipt_state(receipt: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "digest": receipt.get("digest", ""),
        "status": receipt.get("status", ""),
        "message": receipt.get("message", ""),
        "realized_at": receipt.get("realized_at", ""),
        "governed": bool(receipt.get("governed", False)),
        "event_spine_evidence": bool(receipt.get("event_spine_evidence", False)),
        "governance_verdict": receipt.get("governance_verdict", ""),
        "drift_state": receipt.get("drift_state", ""),
        "governance_context_id": receipt.get("governance_context_id", ""),
        "mcp_event_id": receipt.get("mcp_event_id", ""),
        "proof_id": receipt.get("proof_id", ""),
        "receipt_id": receipt.get("receipt_id", ""),
        "passport_digest": receipt.get("passport_digest", ""),
        "trust_digest": receipt.get("trust_digest", ""),
    }


def _build_generic_registration_payload(
    client: GovernedRepoFlowClient,
    repo: Path,
    op: BoundaryOperation,
    claim: Dict[str, Any],
) -> Dict[str, Any]:
    declaration = client.repo_declaration or read_repo_declaration(
        repo,
        story_id=client.story_id,
        capability_id=client.capability_id,
        repo_class=client.repo_class,
    )
    params = {
        "gap_id": str(claim.get("gap_id") or client.story_id),
        "story_id": client.story_id,
        "repo_name": declaration.repo_name,
        "repo_remote": declaration.repo_remote,
        "commit_sha": declaration.commit_sha,
        "branch": declaration.branch,
        "declared_repo_class": declaration.repo_class,
        "purpose": client.purpose,
        "origin": "keyhole-sdk",
        "declaration_files": declaration.declaration_file_digests,
        "native_artifacts": declaration.native_artifacts,
    }
    if claim.get("claim_id"):
        params["claim_id"] = claim["claim_id"]
    if claim.get("claim_ref"):
        params["claim_ref"] = claim["claim_ref"]
    if not op.run_type:
        return {
            "repo": {
                "name": declaration.repo_name,
                "path_digest": _file_digest(repo / "keyhole.yaml"),
            },
            "native_artifacts": declaration.native_artifacts,
        }
    context_ref = str(claim.get("ctxpack_digest") or "")
    payload = {
        "run_type": op.run_type,
        "params": params,
    }
    if context_ref:
        params["ctxpack_digest"] = context_ref
        payload["ctxpack_digest"] = context_ref
        payload["context_ref"] = context_ref
    return payload


def _sanitize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    payload = _redact(dict(state))
    forbidden = {"token", "access_token", "refresh_token", "authorization"}
    for key in list(payload.keys()):
        if key.lower() in forbidden:
            payload.pop(key, None)
    return payload


def _safe_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _requires_active_claim(capabilities: Dict[str, Any]) -> bool:
    data = _unwrap_mcp_envelope(capabilities)
    sdk = data.get("governed_worker_sdk") if isinstance(data.get("governed_worker_sdk"), dict) else {}
    repo_governance = sdk.get("repo_governance") if isinstance(sdk.get("repo_governance"), dict) else {}
    return repo_governance.get("requires_active_claim") is True
