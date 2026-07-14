"""SDK-originated governed gap closure support."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests

from keyhole_sdk.governed_flow import read_repo_declaration
from keyhole_sdk.repo_identity import detect_repo_identity


ALLOWED_CLASSIFICATIONS = {
    "valid_unresolved",
    "locally_remediated_not_closed",
    "superseded_by_later_capability",
    "duplicate_sdk_submission",
    "invalid_gap_requires_governed_reclassification",
}
ALLOWED_REASONS = {
    "remediated",
    "already_satisfied",
    "superseded",
    "duplicate",
    "invalid_generated_gap",
}
ACCEPTABLE_EVENT_SPINE_STATUS = {"PASS", "PASS_WITH_LEGACY_WARNINGS"}


class GapClosureError(Exception):
    """Raised when a governed closure preflight or response is unsafe."""


@dataclass
class GapClosurePayload:
    gap_id: str
    created_via: str
    domain: str
    capability_id: str
    repo_url: str
    repo_owner: str
    repo_name: str
    branch: str
    commit_sha: str
    workspace_id: str
    sdk_version: str
    client_version: str
    closure_reason: str
    closure_classification: str
    evidence_bundle_hash: str
    local_test_result: Dict[str, Any]
    invariant_result: Dict[str, Any]
    capability_result: Dict[str, Any]
    governed_run_id: str = ""
    receipt_id: str = ""
    proof_id: str = ""
    proof_pointer: str = ""
    requested_by: str = ""
    requested_ts: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.__dict__)
        if not data["requested_ts"]:
            data["requested_ts"] = datetime.now(timezone.utc).isoformat()
        return data


def build_gap_closure_payload(
    *,
    repo_dir: str | Path,
    gap_id: str,
    closure_reason: str,
    closure_classification: str,
    evidence_bundle_hash: str,
    local_test_result: Optional[Dict[str, Any]] = None,
    invariant_result: Optional[Dict[str, Any]] = None,
    capability_result: Optional[Dict[str, Any]] = None,
    workspace_id: str = "",
    sdk_version: str = "",
    client_version: str = "",
    requested_by: str = "",
    governed_run_id: str = "",
    receipt_id: str = "",
    proof_id: str = "",
    proof_pointer: str = "",
) -> GapClosurePayload:
    """Build the explicit SDK closure payload; does not call MCP."""
    if not gap_id.startswith("gap_"):
        raise GapClosureError("gap_id must be a canonical gap_* id.")
    if closure_reason not in ALLOWED_REASONS:
        raise GapClosureError(f"closure_reason must be one of: {', '.join(sorted(ALLOWED_REASONS))}.")
    if closure_classification not in ALLOWED_CLASSIFICATIONS:
        raise GapClosureError(
            "closure_classification must be one of: "
            + ", ".join(sorted(ALLOWED_CLASSIFICATIONS))
            + "."
        )
    if not evidence_bundle_hash:
        raise GapClosureError("evidence_bundle_hash is required.")

    repo = Path(repo_dir).resolve()
    declaration = read_repo_declaration(repo)
    identity = detect_repo_identity(str(repo))
    sdk_version = sdk_version or _installed_version("keyhole-sdk")
    client_version = client_version or _installed_version("keyhole-cli")
    return GapClosurePayload(
        gap_id=gap_id,
        created_via="sdk.gaps.submit",
        domain=declaration.repo_name,
        capability_id=declaration.capability_id,
        repo_url=identity.repo_remote,
        repo_owner=identity.owner,
        repo_name=identity.repo or declaration.repo_name,
        branch=identity.current_branch,
        commit_sha=identity.commit_sha,
        workspace_id=workspace_id,
        sdk_version=sdk_version,
        client_version=client_version,
        closure_reason=closure_reason,
        closure_classification=closure_classification,
        evidence_bundle_hash=evidence_bundle_hash,
        local_test_result=local_test_result or {"status": "unknown"},
        invariant_result=invariant_result or {"status": "unknown"},
        capability_result=capability_result or {"status": "unknown"},
        governed_run_id=governed_run_id,
        receipt_id=receipt_id,
        proof_id=proof_id,
        proof_pointer=proof_pointer,
        requested_by=requested_by,
    )


class GapClosureClient:
    """Public MCP client for governed SDK-originated gap closure."""

    def __init__(
        self,
        *,
        mcp_url: str,
        token: str = "",
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
    ) -> None:
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout

    def preflight(self, *, gap_id: str) -> Dict[str, Any]:
        health = self._get_json("/health/event-spine", auth=False)
        assert_event_spine_safe(health)
        gap = self.get_gap(gap_id)
        assert_gap_open_for_closure(gap, gap_id)
        return {"event_spine": health, "target_gap": gap}

    def get_gap(self, gap_id: str) -> Dict[str, Any]:
        payload = {"run_type": "gaps.get", "params": {"gap_id": gap_id}}
        return self._post_run(payload)

    def submit_closure(self, payload: GapClosurePayload) -> Dict[str, Any]:
        request = {
            "run_type": "gaps.close",
            "params": {
                "gap_id": payload.gap_id,
                "closure": payload.to_dict(),
            },
        }
        response = self._post_run(request)
        assert_closure_response_governed(response)
        return response

    def _post_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.mcp_url}/mcp/v1/runs/start",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        return _json_response(response, f"run_type={payload.get('run_type')}")

    def _get_json(self, path: str, *, auth: bool) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.mcp_url}{path}",
            headers=self._headers() if auth else {},
            timeout=self.timeout,
        )
        return _json_response(response, path)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


def assert_event_spine_safe(health: Dict[str, Any]) -> None:
    status = _first_string(
        health.get("final_classification"),
        health.get("event_spine_status"),
        health.get("status"),
        (health.get("data") or {}).get("final_classification") if isinstance(health.get("data"), dict) else "",
    )
    if status not in ACCEPTABLE_EVENT_SPINE_STATUS:
        raise GapClosureError(f"event spine health is not safe for closure: {status or 'missing status'}")

    stream = _find_stream(health, "KH_VERDICTS")
    max_msgs = _first_int(stream.get("max_msgs"), health.get("max_msgs"))
    if max_msgs and max_msgs != 1_000_000:
        raise GapClosureError(f"KH_VERDICTS max_msgs is {max_msgs}, expected 1000000.")
    unpersisted = _first_int(
        health.get("unpersisted_message_count"),
        stream.get("unpersisted_message_count"),
    )
    if unpersisted != 0:
        raise GapClosureError(f"unpersisted_message_count is unsafe: {unpersisted}.")


def assert_gap_open_for_closure(gap: Dict[str, Any], gap_id: str) -> None:
    data = _unwrap(gap)
    if _first_string(data.get("gap_id"), data.get("id")) not in {"", gap_id}:
        raise GapClosureError("server returned a different gap_id during preflight.")
    status = _first_string(data.get("status"), data.get("state")).upper()
    if status != "OPEN":
        raise GapClosureError(f"target gap is not OPEN: {status or 'missing status'}.")
    if data.get("closed_ts") is not None:
        raise GapClosureError("target gap already has closed_ts before SDK closure.")
    if data.get("close_verdict_ref") is not None:
        raise GapClosureError("target gap already has close_verdict_ref before SDK closure.")
    if data.get("convergence_closure_lineage"):
        raise GapClosureError("open target gap unexpectedly already has closure lineage.")


def assert_closure_response_governed(response: Dict[str, Any]) -> None:
    data = _unwrap(response)
    missing = [
        name
        for name in (
            "closed_ts",
            "close_verdict_ref",
            "convergence_closure_lineage",
            "gap_closure_history",
        )
        if not data.get(name)
    ]
    if missing:
        raise GapClosureError("closure response missing governed lineage field(s): " + ", ".join(missing))


def hash_evidence_files(paths: Iterable[str | Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _json_response(response: requests.Response, action: str) -> Dict[str, Any]:
    if response.status_code >= 400:
        raise GapClosureError(f"{action} failed with HTTP {response.status_code}: {response.text[:300]}")
    try:
        data = response.json()
    except ValueError as exc:
        raise GapClosureError(f"{action} response was not JSON.") from exc
    if not isinstance(data, dict):
        raise GapClosureError(f"{action} response was not a JSON object.")
    return data


def _unwrap(data: Dict[str, Any]) -> Dict[str, Any]:
    current = data
    for key in ("data", "result", "gap", "closure"):
        value = current.get(key)
        if isinstance(value, dict):
            current = value
    return current


def _find_stream(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    streams = data.get("streams")
    if isinstance(streams, dict):
        stream = streams.get(name)
        if isinstance(stream, dict):
            return stream
    if isinstance(streams, list):
        for stream in streams:
            if isinstance(stream, dict) and stream.get("name") == name:
                return stream
    stream = data.get(name)
    return stream if isinstance(stream, dict) else {}


def _first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _first_int(*values: Any) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _installed_version(package_name: str) -> str:
    try:
        result = subprocess.run(
            ["python", "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    for line in result.stdout.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return ""


def write_closure_artifact(path: str | Path, data: Dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return target
