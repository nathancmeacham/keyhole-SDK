"""Governed first-app demo flow for CE-V5-S51-C02.

This module wires the forkable ``my-first-app`` demo through the public MCP
boundary and local runtime bridge. It fails closed when required boundary
operations or governed receipt evidence are absent.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

from keyhole_sdk.models import GovernanceReceipt
from keyhole_sdk.transport.idempotency import generate_idempotency_key, generate_request_id


REDACTED = "<redacted>"
STATE_DIRNAME = "governed-demo"
REGISTRATION_STATE = "registration.json"
CONTEXT_STATE = "context.json"
RECEIPT_STATE = "receipt.json"
GAP_ID = "CE-V5-S51-C02"
STORY_ID = "CE-V5-S51-C02"
GAP_ID_OVERRIDE_ENV = "KEYHOLE_C02_GAP_ID"
ASYNC_TERMINAL_STATUSES = {"completed", "succeeded", "success", "failed", "canceled", "cancelled", "timed_out"}
ASYNC_ACTIVE_STATUSES = {"accepted", "queued", "pending", "running", "started"}
CLAIMABLE_GAP_STATUSES = {"open", "claimable", "actionable"}
NON_CLAIMABLE_GAP_STATUSES = {
    "archived",
    "blocked",
    "cancelled",
    "canceled",
    "closed",
    "done",
    "rejected",
    "resolved",
    "stale",
}


class GovernedDemoError(RuntimeError):
    """Fail-closed error for governed demo operations."""


@dataclass
class BoundaryOperation:
    name: str
    path: str = ""
    method: str = "POST"
    surface: str = "http"
    run_type: str = ""


@dataclass
class GovernedDemoState:
    repo_path: Path
    state_dir: Path
    registration: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    receipt: Dict[str, Any] = field(default_factory=dict)


class GovernedFirstAppClient:
    """Client for the S51-C02 governed first-app flow."""

    def __init__(
        self,
        *,
        mcp_url: str,
        token: str,
        runtime_url: str = "",
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
        story_id: str = STORY_ID,
        capability_id: str = "greet.user.v1",
        repo_class: str = "SDK_TEMPLATE",
        gap_override_env: str = GAP_ID_OVERRIDE_ENV,
        purpose: str = "CE-V5-S51-C02 governed first app live verifier",
    ) -> None:
        if not mcp_url:
            raise GovernedDemoError("KEYHOLE_MCP_URL is required for governed demo flow.")
        if not token:
            raise GovernedDemoError("KEYHOLE_MCP_TOKEN is required for governed demo flow.")
        self.mcp_url = mcp_url.rstrip("/")
        self.runtime_url = runtime_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.session = session or requests.Session()
        self.raw_capabilities: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}
        self.operations: Dict[str, BoundaryOperation] = {}
        self.resolved_gap_id: str = ""
        self.gap_id_source: str = ""
        self.story_id = story_id
        self.gap_label = story_id
        self.capability_id = capability_id
        self.repo_class = repo_class
        self.gap_override_env = gap_override_env
        self.purpose = purpose

    @classmethod
    def from_env(
        cls,
        *,
        runtime_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> "GovernedFirstAppClient":
        return cls(
            mcp_url=os.environ.get("KEYHOLE_MCP_URL", ""),
            token=os.environ.get("KEYHOLE_MCP_TOKEN", ""),
            runtime_url=runtime_url or os.environ.get("KEYHOLE_RUNTIME_URL", ""),
            session=session,
        )

    def discover(self) -> Dict[str, BoundaryOperation]:
        response = self.session.get(
            f"{self.mcp_url}/mcp/v1/capabilities",
            timeout=self.timeout,
        )
        _raise_for_response(response, "capabilities discovery")
        raw = _json_object(response)
        data = _unwrap_mcp_envelope(raw)
        self.raw_capabilities = raw
        self.capabilities = data
        self.operations = _extract_operations(raw)
        if _requires_active_claim(data):
            self._require_operations("gaps.claim")
        self._require_operations("repo.register", "context.compile", "governed.realize")
        return dict(self.operations)

    def register_repo(self, repo_path: str | Path) -> Dict[str, Any]:
        self._ensure_discovered()
        op = self._require_operation("repo.register")
        repo = Path(repo_path).resolve()
        claim = self.claim_gap(repo) if _requires_active_claim(self.capabilities) else {}
        payload = _build_repo_registration_payload(
            repo,
            op,
            claim=claim,
            story_id=self.story_id,
            repo_class=self.repo_class,
            purpose=self.purpose,
        )
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
            (data.get("result") or {}).get("ctxpack_digest") if isinstance(data.get("result"), dict) else "",
            (data.get("data") or {}).get("registration_id") if isinstance(data.get("data"), dict) else "",
            (data.get("data") or {}).get("repo_id") if isinstance(data.get("data"), dict) else "",
            (data.get("data") or {}).get("declaration_id") if isinstance(data.get("data"), dict) else "",
            (data.get("data") or {}).get("governance_context_id") if isinstance(data.get("data"), dict) else "",
            (data.get("data") or {}).get("ctxpack_digest") if isinstance(data.get("data"), dict) else "",
            ((data.get("data") or {}).get("result") or {}).get("registration_id")
            if isinstance((data.get("data") or {}).get("result"), dict) else "",
            ((data.get("data") or {}).get("result") or {}).get("declaration_id")
            if isinstance((data.get("data") or {}).get("result"), dict) else "",
        )
        if not registration_id:
            raise GovernedDemoError(
                "repo.register response missing registration_id/repo_id/declaration_id/governance_context_id."
            )
        state = {
            "registration_id": registration_id,
            "repo": repo.name,
            "repo_path_digest": hashlib.sha256(str(repo).encode("utf-8")).hexdigest(),
            "boundary_operation": op.name,
            "path": op.path,
            "run_type": op.run_type,
            "claim_id": claim.get("claim_id", ""),
            "claim_ref": claim.get("claim_ref", ""),
            "claim_ctxpack_digest": claim.get("ctxpack_digest", ""),
            "gap_id": claim.get("gap_id", self.story_id),
            "story_id": self.story_id,
            "gap_id_source": self.gap_id_source,
            "upstream": _redact(data),
        }
        _write_state(repo, REGISTRATION_STATE, state)
        return state

    def claim_gap(self, repo_path: str | Path) -> Dict[str, Any]:
        self._ensure_discovered()
        op = self._require_operation("gaps.claim")
        repo = Path(repo_path).resolve()
        metadata = _repo_git_metadata(repo)
        ctxpack_digest = self._claim_context_digest(repo)
        gap_id = self._resolve_gap_id(repo)
        payload = {
            "run_type": op.run_type or "gaps.claim",
            "ctxpack_digest": ctxpack_digest,
            "params": {
                "gap_id": gap_id,
                "story_id": self.story_id,
                "ctxpack_digest": ctxpack_digest,
                "purpose": self.purpose,
                "repo_remote": metadata["repo_remote"],
                "commit_sha": metadata["commit_sha"],
                "branch": metadata.get("branch", ""),
            },
        }
        response = self.session.request(
            op.method,
            f"{self.mcp_url}{op.path}",
            headers=self._headers(idempotent=True),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_response(response, "gap claim")
        data = _json_object(response)
        _raise_for_mcp_error(data, "gap claim")
        data = self._resolve_async_result(data, "gap claim")
        claim_id = _extract_claim_id(data)
        claim_ref = _extract_claim_ref(data)
        if not claim_id and not claim_ref:
            raise GovernedDemoError("gap claim response missing claim_id/claim_ref.")
        return {
            "claim_id": claim_id,
            "claim_ref": claim_ref,
            "gap_id": gap_id,
            "gap_id_source": self.gap_id_source,
            "ctxpack_digest": ctxpack_digest,
            "upstream": _redact(data),
        }

    def _resolve_gap_id(self, repo: Path) -> str:
        if self.resolved_gap_id:
            return self.resolved_gap_id
        override = os.environ.get(self.gap_override_env, "").strip()
        if override:
            if not override.startswith("gap_"):
                raise GovernedDemoError(f"{self.gap_override_env} must be a canonical gap_* id.")
            self.resolved_gap_id = override
            self.gap_id_source = f"diagnostic override {self.gap_override_env}"
            return override
        explicit = _gap_id_from_capabilities(self.capabilities)
        if explicit:
            self.resolved_gap_id = explicit
            self.gap_id_source = "capabilities"
            return explicit
        discovered = self._discover_gap_id(repo)
        if discovered:
            self.resolved_gap_id = discovered
            self.gap_id_source = "gaps.list"
            return discovered
        raise GovernedDemoError(
            f"cannot resolve canonical claimable gap_id for story_id={self.story_id or '<unspecified>'}; "
            "capabilities did not provide one and gaps.list returned no matching gap."
        )

    def _discover_gap_id(self, repo: Path) -> str:
        op = _gap_discovery_operation(self.capabilities)
        params = {
            "status": "*",
            "limit": 50,
            "order_by": "actionable",
            "story_id": self.story_id,
            "repo": repo.name,
            "repo_name": repo.name,
            "domain": repo.name,
            "capability_id": self.capability_id,
            "capability": self.capability_id,
            "fingerprint_version": "sdk-v1",
        }
        discovery_error: Optional[GovernedDemoError] = None
        try:
            discovered = self._run_gap_discovery(op, params, repo)
        except GovernedDemoError as exc:
            if not self.story_id:
                raise
            discovery_error = exc
            discovered = ""
        if discovered:
            return discovered
        if self.story_id:
            fallback_params = dict(params)
            fallback_params.pop("story_id", None)
            try:
                return self._run_gap_discovery(op, fallback_params, repo)
            except GovernedDemoError:
                if discovery_error is not None:
                    raise discovery_error
                raise
        return ""

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

    def _compile_preclaim_context(self, repo: Path) -> str:
        op = self._require_operation("context.compile")
        payload = {
            "run_type": op.run_type or "context.compile",
            "params": {
                "repo": repo.name,
                "gap_id": self.story_id,
                "story_id": self.story_id,
            },
        }
        response = self.session.request(
            op.method,
            f"{self.mcp_url}{op.path}",
            headers=self._headers(idempotent=True),
            json=payload,
            timeout=self.timeout,
        )
        _raise_for_response(response, "pre-claim context compile")
        data = _json_object(response)
        _raise_for_mcp_error(data, "pre-claim context compile")
        data = self._resolve_async_result(data, "pre-claim context compile")
        context_id = _extract_context_id(data)
        if not context_id:
            raise GovernedDemoError("pre-claim context.compile response missing ctxpack digest.")
        return context_id

    def _claim_context_digest(self, repo: Path) -> str:
        canonical = self._current_canonical_digest(repo)
        if canonical:
            return canonical
        return self._compile_preclaim_context(repo)

    def _current_canonical_digest(self, repo: Path) -> str:
        payload = {
            "run_type": "gaps.status",
            "repo": repo.name,
            "shadow": False,
        }
        try:
            response = self.session.request(
                "POST",
                f"{self.mcp_url}/mcp/v1/runs/start",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                return ""
            data = _json_object(response)
            if data.get("ok") is False:
                return ""
            return _extract_current_canonical_digest(data)
        except Exception:
            return ""

    def compile_context(self, repo_path: str | Path) -> Dict[str, Any]:
        self._ensure_discovered()
        op = self._require_operation("context.compile")
        repo = Path(repo_path).resolve()
        registration = _read_state(repo, REGISTRATION_STATE)
        payload = {
            "run_type": op.run_type or "context.compile",
            "params": {
                "repo": repo.name,
                "registration_id": registration.get("registration_id", ""),
                "gap_id": registration.get("gap_id") or self.story_id,
                "story_id": self.story_id,
            },
        }
        context_ref = _first_string(
            registration.get("claim_ctxpack_digest"),
            registration.get("ctxpack_digest"),
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
            "repo": repo.name,
            "registration_id": registration.get("registration_id", ""),
            "boundary_operation": "context.compile",
            "upstream": _redact(data),
        }
        _write_state(repo, CONTEXT_STATE, state)
        return state

    def run_governed_realization(self, repo_path: str | Path) -> GovernanceReceipt:
        self._ensure_discovered()
        repo = Path(repo_path).resolve()
        context = _read_state(repo, CONTEXT_STATE)
        local_invariant = _run_local_invariant(repo, self.capability_id)
        candidate_digest = _candidate_digest(repo, local_invariant, context)
        context_ref = _first_string(
            _valid_ctxpack_digest(context.get("ctxpack_digest")),
            _extract_context_digest(context.get("upstream") if isinstance(context.get("upstream"), dict) else {}),
            _valid_ctxpack_digest(context.get("governance_context_id")),
        )
        op = self._require_operation("governed.realize")
        request = {
            "run_type": op.run_type or "governed.realize",
            "params": {
                "candidate_digest": candidate_digest,
                "require_governed": True,
                "governance_context_id": context.get("governance_context_id", ""),
                "local_invariant_result": local_invariant,
            },
        }
        if context_ref:
            request["ctxpack_digest"] = context_ref
            request["context_ref"] = context_ref
        if op.surface == "runtime":
            runtime_request = dict(request["params"])
            response = self.session.post(
                f"{self.runtime_url}/realize",
                json=runtime_request,
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

    def _headers(self, *, idempotent: bool = False) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if idempotent:
            headers["X-Idempotency-Key"] = generate_idempotency_key()
            headers["X-Request-Id"] = generate_request_id()
        return headers

    def _ensure_discovered(self) -> None:
        if not self.operations:
            self.discover()

    def _require_operation(self, name: str) -> BoundaryOperation:
        self._require_operations(name)
        return self.operations[name]

    def _require_operations(self, *names: str) -> None:
        missing = [name for name in names if name not in self.operations]
        if missing:
            raise GovernedDemoError(
                "MCP capabilities missing required operation(s): " + ", ".join(missing)
            )

    def _resolve_async_result(self, data: Dict[str, Any], action: str) -> Dict[str, Any]:
        inner = data.get("data") if isinstance(data.get("data"), dict) else {}
        status = _first_string(inner.get("status"), data.get("status")).lower()
        if status not in ASYNC_ACTIVE_STATUSES:
            return data
        run_id = _first_string(inner.get("run_id"), data.get("run_id"))
        poll_url = _first_string(inner.get("poll_url"), data.get("poll_url"))
        if not run_id and not poll_url:
            raise GovernedDemoError(f"{action} accepted asynchronously but returned no run_id or poll_url.")
        paths = []
        if poll_url:
            paths.append(poll_url)
        if run_id:
            paths.append(f"/mcp/v1/runs/{run_id}/status")
        deadline = time.monotonic() + max(self.timeout, 120.0)
        last: Dict[str, Any] = data
        while time.monotonic() < deadline:
            for path in dict.fromkeys(paths):
                response = self.session.get(
                    f"{self.mcp_url}{path}",
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                _raise_for_response(response, f"{action} status poll")
                polled = _json_object(response)
                _raise_for_mcp_error(polled, f"{action} status poll")
                last = polled
                polled_data = polled.get("data") if isinstance(polled.get("data"), dict) else {}
                polled_status = _first_string(polled_data.get("status"), polled.get("status")).lower()
                if polled_status in ASYNC_TERMINAL_STATUSES or polled_data.get("is_terminal") is True:
                    if polled_status in {"failed", "canceled", "cancelled", "timed_out"}:
                        error = polled_data.get("error") if isinstance(polled_data.get("error"), dict) else {}
                        code = _first_string(error.get("code"), polled_data.get("terminal_reason"))
                        message = _first_string(error.get("message"), code)
                        raise GovernedDemoError(f"{action} failed: {code}: {message}")
                    return polled
            time.sleep(2)
        raise GovernedDemoError(f"{action} did not reach a terminal run status before timeout: {_redact(last)}")


def _extract_operations(capabilities: Dict[str, Any]) -> Dict[str, BoundaryOperation]:
    found: Dict[str, BoundaryOperation] = {}

    def add(
        name: str,
        path: str = "",
        method: str = "POST",
        *,
        surface: str = "http",
        run_type: str = "",
    ) -> None:
        if name:
            if not path and (surface == "runs.start" or run_type):
                path = "/mcp/v1/runs/start"
            if path == "/realize":
                surface = "runtime"
            found[name] = BoundaryOperation(
                name=name,
                path=path,
                method=method.upper(),
                surface=surface,
                run_type=run_type,
            )

    data = _unwrap_mcp_envelope(capabilities)
    for raw_ops in (capabilities.get("operations"), data.get("operations")):
        if isinstance(raw_ops, dict):
            for name, spec in raw_ops.items():
                if isinstance(spec, dict):
                    add(
                        str(name),
                        str(spec.get("path", "")),
                        str(spec.get("method", "POST")),
                        surface=str(spec.get("surface", "http")),
                        run_type=str(spec.get("run_type", "")),
                    )
                elif spec:
                    add(str(name), "/mcp/v1/runs/start" if str(name).endswith(".realize") else "")
        elif isinstance(raw_ops, list):
            for item in raw_ops:
                if isinstance(item, str):
                    add(item)
                elif isinstance(item, dict):
                    path = str(item.get("path", ""))
                    method = str(item.get("method", "POST"))
                    operation_id = str(item.get("operation_id") or item.get("name") or item.get("operation") or "")
                    run_type = str(item.get("run_type") or "")
                    if operation_id and not item.get("run_types"):
                        add(operation_id, path, method, run_type=run_type)
                    run_types = item.get("run_types")
                    if isinstance(run_types, list):
                        for rt in run_types:
                            if isinstance(rt, str):
                                logical = _logical_name_for_run_type(rt)
                                add(logical, path, method, surface=operation_id or "runs.start", run_type=rt)

    sdk = data.get("governed_worker_sdk") if isinstance(data.get("governed_worker_sdk"), dict) else {}
    repo_governance = sdk.get("repo_governance") if isinstance(sdk.get("repo_governance"), dict) else {}
    canonical = str(repo_governance.get("canonical_run_type") or "")
    aliases = repo_governance.get("logical_aliases")
    if canonical:
        for alias in aliases if isinstance(aliases, list) else ["repo.register"]:
            if isinstance(alias, str):
                add(alias, "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=canonical)
        add("repo.register", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=canonical)

    logical_map = sdk.get("logical_operation_map") if isinstance(sdk.get("logical_operation_map"), dict) else {}
    for key, spec in logical_map.items():
        if not isinstance(spec, dict):
            continue
        run_type = str(spec.get("run_type") or "")
        path = str(spec.get("path") or "")
        method = str(spec.get("method") or "POST")
        surface = str(spec.get("surface") or spec.get("kind") or "runs.start")
        names = [str(key)]
        equivalents = spec.get("equivalent_to")
        if isinstance(equivalents, list):
            names.extend(str(item) for item in equivalents if isinstance(item, str))
        if run_type:
            names.append(_logical_name_for_run_type(run_type))
        for name in names:
            add(name, path, method, surface=surface, run_type=run_type)

    compile_block = sdk.get("governed_context_compile") if isinstance(sdk.get("governed_context_compile"), dict) else {}
    compile_rt = str(compile_block.get("canonical_run_type") or "")
    if compile_rt:
        add("context.compile", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=compile_rt)

    realize = logical_map.get("governed_realization") if isinstance(logical_map.get("governed_realization"), dict) else {}
    realize_rt = str(realize.get("run_type") or "")
    if realize_rt:
        add("governed.realize", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=realize_rt)

    for rt in _iter_run_types(data):
        if rt in {"governance.context.create", "repo.register", "participant.declare", "worker.repo.register"}:
            add("repo.register", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=rt)
        elif rt == "context.compile":
            add("context.compile", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=rt)
        elif rt == "governed.realize":
            add("governed.realize", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=rt)
        elif rt == "gaps.claim":
            add("gaps.claim", "/mcp/v1/runs/start", "POST", surface="runs.start", run_type=rt)

    return found


def _logical_name_for_run_type(run_type: str) -> str:
    if run_type in {"governance.context.create", "repo.register", "participant.declare", "worker.repo.register"}:
        return "repo.register"
    if run_type == "gaps.claim":
        return "gaps.claim"
    if run_type == "context.compile":
        return "context.compile"
    if run_type == "governed.realize":
        return "governed.realize"
    return run_type


def _unwrap_mcp_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("ok") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _extract_legacy_operations(capabilities: Dict[str, Any]) -> Dict[str, BoundaryOperation]:
    found: Dict[str, BoundaryOperation] = {}
    raw_ops = capabilities.get("operations")
    if isinstance(raw_ops, dict):
        for name, spec in raw_ops.items():
            if isinstance(spec, dict):
                found[str(name)] = BoundaryOperation(str(name), str(spec.get("path", "")), str(spec.get("method", "POST")))
            elif spec:
                found[str(name)] = BoundaryOperation(str(name))
    return found


def _iter_run_types(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in ("run_type", "name", "operation") and isinstance(nested, str):
                yield nested
            else:
                yield from _iter_run_types(nested)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
            else:
                yield from _iter_run_types(item)


def _requires_active_claim(capabilities: Dict[str, Any]) -> bool:
    sdk = capabilities.get("governed_worker_sdk") if isinstance(capabilities.get("governed_worker_sdk"), dict) else {}
    repo_governance = sdk.get("repo_governance") if isinstance(sdk.get("repo_governance"), dict) else {}
    return repo_governance.get("requires_active_claim") is True


def _gap_id_from_capabilities(capabilities: Dict[str, Any]) -> str:
    sdk = capabilities.get("governed_worker_sdk") if isinstance(capabilities.get("governed_worker_sdk"), dict) else {}
    candidates = [
        sdk.get("canonical_gap_id"),
        sdk.get("gap_id"),
    ]
    for block_name in ("gap_claim", "repo_governance"):
        block = sdk.get(block_name) if isinstance(sdk.get(block_name), dict) else {}
        candidates.extend([
            block.get("canonical_gap_id"),
            block.get("gap_id"),
        ])
        resolution = block.get("gap_id_resolution") if isinstance(block.get("gap_id_resolution"), dict) else {}
        candidates.extend([
            resolution.get("canonical_gap_id"),
            resolution.get("gap_id"),
        ])
        prerequisite = block.get("gap_prerequisite") if isinstance(block.get("gap_prerequisite"), dict) else {}
        candidates.extend([
            prerequisite.get("canonical_gap_id"),
            prerequisite.get("gap_id"),
        ])
    for value in candidates:
        if isinstance(value, str) and value.startswith("gap_"):
            return value
    return ""


def _gap_discovery_operation(capabilities: Dict[str, Any]) -> BoundaryOperation:
    sdk = capabilities.get("governed_worker_sdk") if isinstance(capabilities.get("governed_worker_sdk"), dict) else {}
    logical_map = sdk.get("logical_operation_map") if isinstance(sdk.get("logical_operation_map"), dict) else {}
    discovery = logical_map.get("gap_discovery") if isinstance(logical_map.get("gap_discovery"), dict) else {}
    run_type = str(discovery.get("start_with_run_type") or discovery.get("run_type") or "")
    if not run_type:
        claim = sdk.get("gap_claim") if isinstance(sdk.get("gap_claim"), dict) else {}
        resolution = claim.get("gap_id_resolution") if isinstance(claim.get("gap_id_resolution"), dict) else {}
        run_type = str(resolution.get("start_here_run_type") or "")
    if not run_type:
        raise GovernedDemoError("MCP capabilities missing gap discovery run type.")
    return BoundaryOperation(
        name="gap_discovery",
        path=str(discovery.get("path") or "/mcp/v1/runs/start"),
        method=str(discovery.get("method") or "POST"),
        surface=str(discovery.get("surface") or "runs.start"),
        run_type=run_type,
    )


def _select_gap_id(data: Dict[str, Any], repo_name: str, story_id: str = "", capability_id: str = "") -> str:
    gaps = list(_iter_gap_objects(data))
    if not gaps:
        return ""

    def score(gap: Dict[str, Any]) -> int:
        raw = json.dumps(gap, sort_keys=True).lower()
        value = 0
        if story_id and story_id.lower() in raw:
            value += 100
        if capability_id and capability_id.lower() in raw:
            value += 40
        if repo_name.lower() in raw:
            value += 20
        if "sdk-v1" in raw:
            value += 10
        status = str(gap.get("status") or gap.get("state") or "").lower()
        if status in {"open", "claimable", "actionable", "claimed"}:
            value += 5
        return value

    ranked = sorted(gaps, key=score, reverse=True)
    ranked = [gap for gap in ranked if score(gap) > 0]
    if not ranked:
        return ""
    claimable = [gap for gap in ranked if _is_claimable_gap(gap)]
    if not claimable:
        raise GovernedDemoError(_no_claimable_gap_message(ranked[0]))
    ranked = claimable
    best = ranked[0]
    best_score = score(best)
    tied = [gap for gap in ranked if score(gap) == best_score]
    if len(tied) > 1:
        raise GovernedDemoError("MULTIPLE_GAP_CANDIDATES: server returned multiple equally ranked canonical gaps.")
    return _first_string(best.get("gap_id"), best.get("id"))


def _is_claimable_gap(gap: Dict[str, Any]) -> bool:
    if _truthy(gap.get("blocked")):
        return False
    if _has_blocked_reasons(gap):
        return False
    claimable = gap.get("claimable")
    if _truthy(claimable):
        return True
    if _falsey(claimable):
        return False
    status = str(gap.get("status") or gap.get("state") or "").lower()
    if status in NON_CLAIMABLE_GAP_STATUSES:
        return False
    return status in CLAIMABLE_GAP_STATUSES


def _no_claimable_gap_message(gap: Dict[str, Any]) -> str:
    blocked_reasons = _summarize_blocked_reasons(gap.get("blocked_reasons"))
    required_action = _summarize_required_action(gap.get("blocked_reasons"))
    parts = [
        "NO_CLAIMABLE_GAP: gaps.list returned matching gaps but none are claimable.",
        f"best_gap_id={_first_string(gap.get('gap_id'), gap.get('id')) or '<unknown>'}",
        f"status={_first_string(gap.get('status'), gap.get('state')) or '<unknown>'}",
        f"claimable={_display_bool(gap.get('claimable'))}",
        f"blocked={_display_bool(gap.get('blocked'))}",
    ]
    if blocked_reasons:
        parts.append(f"blocked_reasons={blocked_reasons}")
    if required_action:
        parts.append(f"required_action={required_action}")
    parts.append("Run 'keyhole gaps list --json' and make the gap OPEN/claimable before running governed realization.")
    return " ".join(parts)


def _has_blocked_reasons(gap: Dict[str, Any]) -> bool:
    reasons = gap.get("blocked_reasons")
    if isinstance(reasons, list):
        return any(bool(item) for item in reasons)
    if isinstance(reasons, dict):
        return bool(reasons)
    if isinstance(reasons, str):
        return bool(reasons.strip())
    return False


def _summarize_blocked_reasons(reasons: Any) -> str:
    if isinstance(reasons, list):
        labels = []
        for item in reasons:
            if isinstance(item, dict):
                labels.append(_first_string(item.get("code"), item.get("reason"), item.get("message")))
            elif item:
                labels.append(str(item))
        return ",".join(label for label in labels if label)
    if isinstance(reasons, dict):
        return _first_string(reasons.get("code"), reasons.get("reason"), reasons.get("message"))
    if isinstance(reasons, str):
        return reasons.strip()
    return ""


def _summarize_required_action(reasons: Any) -> str:
    items = reasons if isinstance(reasons, list) else [reasons]
    for item in items:
        if not isinstance(item, dict):
            continue
        required = item.get("required_action")
        if isinstance(required, dict):
            return _first_string(required.get("type"), required.get("action"), required.get("message"))
        if isinstance(required, str):
            return required
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _falsey(value: Any) -> bool:
    if isinstance(value, bool):
        return value is False
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "no", "n"}
    return False


def _display_bool(value: Any) -> str:
    if _truthy(value):
        return "true"
    if _falsey(value):
        return "false"
    return "<unknown>"


def _iter_gap_objects(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        gap_id = _first_string(value.get("gap_id"), value.get("id"))
        if gap_id.startswith("gap_"):
            yield value
        for nested in value.values():
            yield from _iter_gap_objects(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_gap_objects(item)


def _build_repo_registration_payload(
    repo: Path,
    op: BoundaryOperation,
    *,
    claim: Optional[Dict[str, Any]] = None,
    story_id: str = STORY_ID,
    repo_class: str = "SDK_TEMPLATE",
    purpose: str = "CE-V5-S51-C02 governed first app live verifier",
) -> Dict[str, Any]:
    keyhole = _load_yaml(repo / "keyhole.yaml")
    contract = _load_yaml(repo / "governance_contract.yaml")
    passport = _load_yaml(repo / "capability_passport.yaml")
    dependencies = _load_yaml(repo / "dependencies.yaml")
    native_artifacts = {
        "keyhole": keyhole,
        "governance_contract": contract,
        "capability_passport": passport,
        "dependencies": dependencies,
    }
    legacy_payload = {
        "repo": {
            "name": str(keyhole.get("repo") or repo.name),
            "path_digest": hashlib.sha256(str(repo).encode("utf-8")).hexdigest(),
        },
        "native_artifacts": native_artifacts,
    }
    if not op.run_type:
        return legacy_payload
    metadata = _repo_git_metadata(repo)
    params = {
        "gap_id": str((claim or {}).get("gap_id") or story_id),
        "story_id": story_id,
        "repo_name": str(keyhole.get("repo") or repo.name),
        "repo_remote": metadata["repo_remote"],
        "commit_sha": metadata["commit_sha"],
        "branch": metadata.get("branch", ""),
        "declared_repo_class": str(keyhole.get("repo_class") or repo_class),
        "purpose": purpose,
        "origin": "keyhole-sdk",
        "declaration_files": {
            "keyhole_yaml_digest": _file_digest(repo / "keyhole.yaml"),
            "governance_contract_digest": _file_digest(repo / "governance_contract.yaml"),
            "capability_passport_digest": _file_digest(repo / "capability_passport.yaml"),
            "dependencies_digest": _file_digest(repo / "dependencies.yaml"),
        },
        "native_artifacts": native_artifacts,
    }
    if claim:
        if claim.get("claim_id"):
            params["claim_id"] = claim["claim_id"]
        if claim.get("claim_ref"):
            params["claim_ref"] = claim["claim_ref"]
    context_ref = str((claim or {}).get("ctxpack_digest") or "")
    payload = {
        "run_type": op.run_type,
        "params": params,
    }
    if context_ref:
        params["ctxpack_digest"] = context_ref
        payload["ctxpack_digest"] = context_ref
        payload["context_ref"] = context_ref
    return payload


def _repo_git_metadata(repo: Path) -> Dict[str, str]:
    repo_remote = _git_value(repo, "remote", "get-url", "origin")
    commit_sha = _git_value(repo, "rev-parse", "HEAD")
    branch = _git_value(repo, "branch", "--show-current")
    missing = []
    if not repo_remote:
        missing.append("repo_remote")
    if not commit_sha:
        missing.append("commit_sha")
    if missing:
        raise GovernedDemoError(
            "cannot build governance.context.create params; missing required git field(s): "
            + ", ".join(missing)
        )
    return {
        "repo_remote": repo_remote,
        "commit_sha": commit_sha,
        "branch": branch,
    }


def _file_digest(path: Path) -> str:
    if not path.exists():
        return ""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        data = _load_yaml_subset(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _load_yaml_subset(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    if not any(line.strip() for line in lines):
        return {}
    value, _ = _parse_yaml_block(lines, 0, 0)
    return value if isinstance(value, dict) else {}


def _parse_yaml_block(lines: list[str], start: int, indent: int) -> tuple[Any, int]:
    result: Dict[str, Any] = {}
    items: list[Any] = []
    index = start
    mode = ""
    while index < len(lines):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            index += 1
            continue
        current_indent = len(raw) - len(raw.lstrip(" "))
        if current_indent < indent:
            break
        if current_indent > indent and mode != "block":
            break
        stripped = raw.strip()
        if stripped.startswith("- "):
            mode = "list"
            value = stripped[2:]
            if ":" in value and not value.endswith(":"):
                key, _, rest = value.partition(":")
                item = {key.strip(): _yaml_scalar(rest.strip())}
                index += 1
                nested, index = _parse_yaml_block(lines, index, current_indent + 2)
                if isinstance(nested, dict):
                    item.update(nested)
                elif isinstance(nested, list) and nested:
                    item[key.strip()] = nested
                items.append(item)
                continue
            if value.endswith(":"):
                key = value[:-1].strip()
                index += 1
                nested, index = _parse_yaml_block(lines, index, current_indent + 2)
                items.append({key: nested})
                continue
            if value:
                items.append(_yaml_scalar(value))
                index += 1
                continue
            index += 1
            nested, index = _parse_yaml_block(lines, index, current_indent + 2)
            items.append(nested)
            continue
        mode = "block"
        key, sep, rest = stripped.partition(":")
        if not sep:
            index += 1
            continue
        key = key.strip()
        rest = rest.strip()
        if rest in {">", ">-", "|", "|-"}:
            block_lines: list[str] = []
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    block_lines.append("")
                    index += 1
                    continue
                next_indent = len(nxt) - len(nxt.lstrip(" "))
                if next_indent <= current_indent:
                    break
                block_lines.append(nxt[next_indent:])
                index += 1
            result[key] = " ".join(part.strip() for part in block_lines if part.strip())
            continue
        if rest:
            result[key] = _yaml_scalar(rest)
            index += 1
            continue
        index += 1
        nested, index = _parse_yaml_block(lines, index, current_indent + 2)
        result[key] = nested
    if mode == "list":
        return items, index
    return result, index


def _yaml_scalar(value: str) -> Any:
    text = value.strip()
    if text in {"null", "Null", "NULL"}:
        return None
    if text in {"true", "True", "TRUE"}:
        return True
    if text in {"false", "False", "FALSE"}:
        return False
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    try:
        if text.startswith("0") and text != "0" and not text.startswith("0."):
            raise ValueError
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _run_local_invariant(repo: Path, capability_id: str = "") -> Dict[str, Any]:
    gate = _declared_invariant_gate(repo, capability_id)
    if not gate.exists():
        raise GovernedDemoError(f"local invariant gate missing: {gate}")
    spec = importlib.util.spec_from_file_location(f"keyhole_invariant_{hashlib.sha256(str(gate).encode()).hexdigest()}", gate)
    if spec is None or spec.loader is None:
        raise GovernedDemoError("cannot load local invariant gate.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = module.run_gate()
    data = result.to_dict()
    if data.get("verdict") != "ACCEPT":
        raise GovernedDemoError("local invariant proof rejected; refusing governed realization.")
    return data


def _declared_invariant_gate(repo: Path, capability_id: str = "") -> Path:
    contract = _load_yaml(repo / "governance_contract.yaml")
    local_invariants = contract.get("local_invariants") if isinstance(contract.get("local_invariants"), list) else []
    wanted_ids: set[str] = set()
    if capability_id:
        passport = _load_yaml(repo / "capability_passport.yaml")
        capabilities = passport.get("capabilities") if isinstance(passport.get("capabilities"), list) else []
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            names = {str(capability.get("name") or ""), str(capability.get("capability") or "")}
            if capability_id in names:
                wanted_ids.update(str(item) for item in capability.get("invariants", []) if item)
    for invariant in local_invariants:
        if not isinstance(invariant, dict):
            continue
        invariant_id = str(invariant.get("id") or "")
        if wanted_ids and invariant_id not in wanted_ids:
            continue
        gate = str(invariant.get("gate") or "")
        if gate:
            return repo / gate
    if local_invariants:
        first = local_invariants[0]
        if isinstance(first, dict) and first.get("gate"):
            return repo / str(first["gate"])
    return repo / "tests" / "invariants" / "inv_greet.py"


def _candidate_digest(repo: Path, invariant: Dict[str, Any], context: Dict[str, Any]) -> str:
    material = {
        "repo": repo.name,
        "invariant": invariant,
        "governance_context_id": context.get("governance_context_id", ""),
    }
    raw = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_governed_receipt(receipt: GovernanceReceipt) -> None:
    if not receipt.governed:
        raise GovernedDemoError("runtime receipt did not report governed=true.")
    if not receipt.event_spine_evidence:
        raise GovernedDemoError("runtime receipt missing upstream event_spine_evidence=true.")
    if receipt.governance_verdict != "ACCEPT":
        raise GovernedDemoError("runtime receipt missing governance_verdict=ACCEPT.")
    if not receipt.drift_state:
        raise GovernedDemoError("runtime receipt missing drift_state.")
    if not receipt.governance_context_id:
        raise GovernedDemoError("runtime receipt missing governance_context_id.")
    if not receipt.mcp_event_id:
        raise GovernedDemoError("runtime receipt missing mcp_event_id or event pointer.")


def _normalize_governance_receipt(data: Dict[str, Any], candidate_digest: str) -> Dict[str, Any]:
    normalized = _unwrap_mcp_envelope(data)
    result = normalized.get("result") if isinstance(normalized.get("result"), dict) else {}
    inner = normalized.get("data") if isinstance(normalized.get("data"), dict) else {}
    receipt = result.get("receipt") if isinstance(result.get("receipt"), dict) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}

    governed = _first_bool(
        normalized.get("governed"),
        result.get("governed"),
        inner.get("governed"),
        receipt.get("governed"),
    )
    event_pointer = _first_string(
        normalized.get("mcp_event_id"),
        normalized.get("mcp_event_pointer"),
        normalized.get("event_id"),
        result.get("mcp_event_id"),
        result.get("mcp_event_pointer"),
        result.get("event_id"),
        result.get("event_pointer"),
        inner.get("mcp_event_id"),
        inner.get("mcp_event_pointer"),
        receipt.get("mcp_event_id"),
        receipt.get("mcp_event_pointer"),
        evidence.get("event_id"),
        evidence.get("event_pointer"),
    )
    return {
        "digest": _first_string(normalized.get("digest"), result.get("digest"), inner.get("digest"), candidate_digest),
        "status": _first_string(normalized.get("status"), result.get("status"), inner.get("status"), "ACCEPT"),
        "message": _first_string(normalized.get("message"), result.get("message"), inner.get("message")),
        "realized_at": _first_string(
            normalized.get("realized_at"),
            result.get("realized_at"),
            inner.get("realized_at"),
            datetime.now(timezone.utc).isoformat(),
        ),
        "governed": governed,
        "event_spine_evidence": _first_bool(
            normalized.get("event_spine_evidence"),
            result.get("event_spine_evidence"),
            inner.get("event_spine_evidence"),
            receipt.get("event_spine_evidence"),
        ),
        "governance_verdict": _first_string(
            normalized.get("governance_verdict"),
            normalized.get("verdict"),
            result.get("governance_verdict"),
            result.get("verdict"),
            inner.get("governance_verdict"),
            receipt.get("governance_verdict"),
            receipt.get("verdict"),
        ),
        "drift_state": _first_string(
            normalized.get("drift_state"),
            result.get("drift_state"),
            inner.get("drift_state"),
            receipt.get("drift_state"),
        ),
        "governance_context_id": _first_string(
            normalized.get("governance_context_id"),
            result.get("governance_context_id"),
            inner.get("governance_context_id"),
            receipt.get("governance_context_id"),
        ),
        "mcp_event_id": event_pointer,
        "proof_id": _first_string(normalized.get("proof_id"), result.get("proof_id"), receipt.get("proof_id")),
        "receipt_id": _first_string(
            normalized.get("receipt_id"),
            result.get("receipt_id"),
            receipt.get("receipt_id"),
            normalized.get("run_id"),
        ),
        "passport_digest": _first_string(
            normalized.get("passport_digest"),
            result.get("passport_digest"),
            receipt.get("passport_digest"),
        ),
        "trust_digest": _first_string(normalized.get("trust_digest"), result.get("trust_digest"), receipt.get("trust_digest")),
    }


def _extract_context_id(data: Dict[str, Any]) -> str:
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    keyhole = data.get("keyhole") if isinstance(data.get("keyhole"), dict) else {}
    run = inner.get("run") if isinstance(inner.get("run"), dict) else {}
    run_result = run.get("result") if isinstance(run.get("result"), dict) else {}
    nested_result = inner.get("result") if isinstance(inner.get("result"), dict) else {}
    context_card = run_result.get("context_card") if isinstance(run_result.get("context_card"), dict) else {}
    determinism = context_card.get("determinism") if isinstance(context_card.get("determinism"), dict) else {}
    return _first_string(
        data.get("governance_context_id"),
        data.get("ctxpack_digest"),
        data.get("digest"),
        data.get("ctx_ref_sha256"),
        result.get("governance_context_id"),
        result.get("ctxpack_digest"),
        inner.get("governance_context_id"),
        inner.get("ctxpack_digest"),
        nested_result.get("governance_context_id"),
        nested_result.get("ctxpack_digest"),
        run_result.get("governance_context_id"),
        run_result.get("ctxpack_digest"),
        run_result.get("ctx_ref_sha256"),
        determinism.get("digest"),
        keyhole.get("ctx_ref_sha256"),
    )


def _extract_context_digest(data: Dict[str, Any]) -> str:
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    keyhole = data.get("keyhole") if isinstance(data.get("keyhole"), dict) else {}
    run = inner.get("run") if isinstance(inner.get("run"), dict) else {}
    run_result = run.get("result") if isinstance(run.get("result"), dict) else {}
    nested_result = inner.get("result") if isinstance(inner.get("result"), dict) else {}
    output = inner.get("output") if isinstance(inner.get("output"), dict) else {}
    context_card = run_result.get("context_card") if isinstance(run_result.get("context_card"), dict) else {}
    determinism = context_card.get("determinism") if isinstance(context_card.get("determinism"), dict) else {}
    return _first_valid_ctxpack_digest(
        data.get("ctxpack_digest"),
        data.get("digest"),
        data.get("ctx_ref_sha256"),
        result.get("ctxpack_digest"),
        inner.get("ctxpack_digest"),
        nested_result.get("ctxpack_digest"),
        output.get("ctxpack_digest"),
        run_result.get("ctxpack_digest"),
        run_result.get("ctx_ref_sha256"),
        determinism.get("digest"),
        keyhole.get("ctx_ref_sha256"),
    )


def _first_valid_ctxpack_digest(*values: Any) -> str:
    for value in values:
        digest = _valid_ctxpack_digest(value)
        if digest:
            return digest
    return ""


def _valid_ctxpack_digest(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if text.startswith("sha256:"):
        text = text[len("sha256:"):]
    if len(text) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in text):
        return text
    return ""


def _extract_claim_id(data: Dict[str, Any]) -> str:
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    nested_result = inner.get("result") if isinstance(inner.get("result"), dict) else {}
    run = inner.get("run") if isinstance(inner.get("run"), dict) else {}
    return _first_string(
        data.get("claim_id"),
        result.get("claim_id"),
        inner.get("claim_id"),
        nested_result.get("claim_id"),
        run.get("claim_id"),
    )


def _extract_claim_ref(data: Dict[str, Any]) -> str:
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    nested_result = inner.get("result") if isinstance(inner.get("result"), dict) else {}
    run = inner.get("run") if isinstance(inner.get("run"), dict) else {}
    return _first_string(
        data.get("claim_ref"),
        data.get("claim_token"),
        result.get("claim_ref"),
        result.get("claim_token"),
        inner.get("claim_ref"),
        inner.get("claim_token"),
        nested_result.get("claim_ref"),
        nested_result.get("claim_token"),
        run.get("claim_ref"),
    )


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _first_bool(*values: Any) -> bool:
    for value in values:
        if isinstance(value, bool):
            return value
    return False


def _extract_current_canonical_digest(data: Dict[str, Any]) -> str:
    sections = [data]
    for key in ("data", "result"):
        child = data.get(key)
        if isinstance(child, dict):
            sections.append(child)
            nested = child.get("result")
            if isinstance(nested, dict):
                sections.append(nested)

    candidates = []
    for section in sections:
        canonical = section.get("canonical") if isinstance(section.get("canonical"), dict) else {}
        candidates.extend([
            canonical.get("current_canonical_digest"),
            section.get("current_canonical_digest"),
        ])
    raw = _first_string(*candidates).strip()
    if raw.startswith("sha256:"):
        raw = raw[len("sha256:"):]
    return raw


def _error_detail(body: Dict[str, Any]) -> str:
    candidates = [
        body.get("reason"),
        body.get("message"),
        body.get("detail"),
    ]
    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    candidates.extend([
        error.get("reason"),
        error.get("message"),
        error.get("detail"),
        error.get("code"),
    ])
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, (dict, list)) and candidate:
            return json.dumps(_redact(candidate), sort_keys=True, separators=(",", ":"))[:500]
    return json.dumps(_redact(body), sort_keys=True, separators=(",", ":"))[:500]


def _json_object(response: requests.Response) -> Dict[str, Any]:
    data = response.json()
    if not isinstance(data, dict):
        raise GovernedDemoError("upstream response was not a JSON object.")
    return data


def _raise_for_response(response: requests.Response, action: str) -> None:
    if response.status_code >= 400:
        detail = response.text[:500]
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = _error_detail(body)
        except ValueError:
            detail = response.text[:200]
        raise GovernedDemoError(f"{action} failed with HTTP {response.status_code}: {detail}")


def _raise_for_mcp_error(data: Dict[str, Any], action: str) -> None:
    if data.get("ok") is not False:
        return
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    code = _first_string(error.get("code"), inner.get("code"))
    message = _first_string(error.get("message"), inner.get("message"), data.get("message"))
    detail = f"{code}: {message}" if code and message else code or message or "MCP returned ok=false"
    raise GovernedDemoError(f"{action} rejected by MCP: {detail}")


def _raise_for_async_acceptance(data: Dict[str, Any], action: str) -> None:
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    status = _first_string(inner.get("status"), data.get("status")).lower()
    if status not in {"accepted", "queued", "pending", "running", "started"}:
        return
    run_id = _first_string(inner.get("run_id"), data.get("run_id"))
    poll_url = _first_string(inner.get("poll_url"), data.get("poll_url"))
    detail = f"run_id={run_id or '<missing>'}"
    if poll_url:
        detail += f", poll_url={poll_url}"
    raise GovernedDemoError(
        f"{action} accepted asynchronously but did not return a terminal result inline ({detail}). "
        "The live verifier requires the MCP run status endpoint to return the completed result before it can proceed."
    )


def _state_dir(repo: Path) -> Path:
    return repo / ".keyhole" / STATE_DIRNAME


def _write_state(repo: Path, filename: str, data: Dict[str, Any]) -> None:
    state_dir = _state_dir(repo)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / filename).write_text(json.dumps(_redact(data), indent=2), encoding="utf-8")


def _read_state(repo: Path, filename: str) -> Dict[str, Any]:
    path = _state_dir(repo) / filename
    if not path.exists():
        raise GovernedDemoError(f"missing governed demo state: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise GovernedDemoError(f"invalid governed demo state: {path}")
    return data


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): (REDACTED if "token" in str(k).lower() or "authorization" in str(k).lower() else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value
