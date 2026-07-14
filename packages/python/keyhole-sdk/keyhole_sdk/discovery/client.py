"""Capabilities fetch client — minimal discovery client.

CE-V5-S42-03: Capabilities Discovery Client.

Performs a read-only ``GET /mcp/v1/capabilities`` call, parses the
response, and returns a normalized :class:`CapabilitiesResult`.

This client is the first executable proof that the external participant
can discover the platform from the platform itself.

Failure mode: fail clearly when the response shape is unusable.
Do not fabricate missing surfaces or guess defaults.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from keyhole_sdk.exceptions import SchemaError, TransportError
from keyhole_sdk.discovery.models import (
    AuthPosture,
    CapabilitiesResult,
    ClientGuidance,
    CompatibilityPosture,
    ConnectionSurfaceContract,
    ConnectionSurfaceRunType,
    ContextAccessContract,
    ContractIdentity,
    DiscoveryMetadata,
    FeatureFlags,
    TransportPosture,
)


DEFAULT_DISCOVERY_TIMEOUT = 10.0
CAPABILITIES_PATH = "/mcp/v1/capabilities"


class CapabilitiesClient:
    """Minimal fetch client for ``GET /mcp/v1/capabilities``.

    Usage::

        client = CapabilitiesClient("https://boundary.example.com")
        result = client.fetch()
        print(result.get_contract_version())
        print(result.get_implemented_context_surfaces())
        client.close()

    Or as a context manager::

        with CapabilitiesClient("https://boundary.example.com") as client:
            result = client.fetch()
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = DEFAULT_DISCOVERY_TIMEOUT,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = "keyhole-sdk-discovery"

    def fetch(self) -> CapabilitiesResult:
        """Retrieve and normalize the mcp/v1 capabilities contract.

        Returns a :class:`CapabilitiesResult` with all sections
        normalized.  Raises :class:`TransportError` on network
        failure and :class:`SchemaError` when the response cannot
        be parsed into a usable capabilities document.
        """
        raw = self._fetch_raw()
        return self._normalize(raw)

    # ── Internal helpers ────────────────────────────────────

    def _fetch_raw(self) -> Dict[str, Any]:
        """Perform the HTTP GET and return raw JSON dict."""
        url = f"{self.base_url}{CAPABILITIES_PATH}"
        try:
            response = self._session.get(url, timeout=self.timeout)
        except (requests.ConnectionError, requests.Timeout, OSError) as exc:
            raise TransportError(
                f"Capabilities discovery failed: {exc}"
            ) from exc

        if response.status_code != 200:
            raise TransportError(
                f"Capabilities endpoint returned {response.status_code}: "
                f"{response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise SchemaError(
                "Capabilities response is not valid JSON", raw_data=None
            ) from exc

        if not isinstance(data, dict):
            raise SchemaError(
                "Capabilities response is not a JSON object",
                raw_data=None,
            )

        return data

    @staticmethod
    def _normalize(raw: Dict[str, Any]) -> CapabilitiesResult:
        """Normalize a raw capabilities response into a typed result.

        Tolerates missing sections gracefully — every sub-model
        defaults to empty/zero.  Never invents fields not present
        in the raw response.
        """
        body = _capabilities_body(raw)
        contract = _extract_contract(body)
        compatibility = _extract_compatibility(body)
        transport = _extract_transport(body)
        auth = _extract_auth(body)
        features = _extract_features(body)
        context_access = _extract_context_access(body)
        guidance = _extract_guidance(body)
        metadata = _extract_metadata(body, raw)
        connection_surfaces = _extract_connection_surfaces(body)

        return CapabilitiesResult(
            contract=contract,
            compatibility=compatibility,
            transport=transport,
            auth=auth,
            features=features,
            context_access=context_access,
            guidance=guidance,
            metadata=metadata,
            connection_surfaces=connection_surfaces,
            raw=raw,
        )

    # ── Lifecycle ───────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> "CapabilitiesClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ──────────────────────────────────────────────────────────────
# Extraction helpers — one per section
# ──────────────────────────────────────────────────────────────

def _safe_str(d: Any, key: str) -> str:
    """Safely extract a string value from a dict."""
    val = d.get(key) if isinstance(d, dict) else None
    return str(val) if val is not None else ""


def _safe_int(d: Any, key: str) -> int:
    """Safely extract an int value from a dict."""
    val = d.get(key) if isinstance(d, dict) else None
    if isinstance(val, int):
        return val
    return 0


def _safe_bool(d: Any, key: str) -> bool:
    """Safely extract a bool value from a dict."""
    val = d.get(key) if isinstance(d, dict) else None
    return bool(val) if val is not None else False


def _safe_list(d: Any, key: str) -> List[Any]:
    """Safely extract a list value from a dict."""
    val = d.get(key) if isinstance(d, dict) else None
    return list(val) if isinstance(val, list) else []


def _safe_dict(d: Any, key: str) -> Dict[str, Any]:
    """Safely extract a dict value from a dict."""
    val = d.get(key) if isinstance(d, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def _capabilities_body(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return the capabilities payload from either raw or MCP envelope form."""
    data = raw.get("data")
    return data if isinstance(data, dict) else raw


def _extract_contract(raw: Dict[str, Any]) -> ContractIdentity:
    """Extract contract identity from raw capabilities."""
    return ContractIdentity(
        contract=_safe_str(raw, "contract"),
        schema_versions=_safe_dict(raw, "schema_versions"),
        operations_declared=_safe_int(raw, "operations_declared"),
        operations_implemented=(
            _safe_int(raw, "operations_implemented")
            or _safe_int(raw, "implemented_ops_count")
        ),
    )


def _extract_compatibility(raw: Dict[str, Any]) -> CompatibilityPosture:
    """Extract compatibility posture from raw capabilities."""
    compat = _safe_dict(raw, "compatibility")
    return CompatibilityPosture(
        min_sdk_version=_safe_str(compat, "min_sdk_version"),
        envelope_version=_safe_str(compat, "envelope_version"),
        passport_version=_safe_str(compat, "passport_version"),
        charter_required=_safe_bool(compat, "charter_required"),
        workspace_supported=_safe_bool(compat, "workspace_supported"),
    )


def _extract_transport(raw: Dict[str, Any]) -> TransportPosture:
    """Extract transport posture from raw capabilities."""
    tp = _safe_dict(raw, "transport")
    return TransportPosture(
        transport=_safe_str(tp, "type") or _safe_str(raw, "transport"),
        tombstoned_transports=_safe_list(tp, "tombstoned"),
    )


def _extract_auth(raw: Dict[str, Any]) -> AuthPosture:
    """Extract auth posture from raw capabilities.

    SDK-CLIENT-25 extends extraction to capture ``supported_flows`` and
    ``preferred_interactive_flow`` per the SDK-SERVER-25 contract.
    """
    auth = _safe_dict(raw, "auth")
    endpoints = _safe_dict(raw, "endpoints")
    worker = _safe_dict(raw, "governed_worker_sdk")
    preflight = _safe_dict(worker, "preflight")
    whoami = _safe_dict(preflight, "whoami")
    capabilities = _safe_dict(preflight, "capabilities")
    supported_flows = [
        str(f) for f in _safe_list(auth, "supported_flows")
        if isinstance(f, str) and f
    ]
    identity_endpoint = (
        _safe_str(endpoints, "identity")
        or _safe_str(whoami, "path")
    )
    discovery_endpoint = (
        _safe_str(endpoints, "discovery")
        or _safe_str(capabilities, "path")
    )
    run_dispatch_endpoint = (
        _safe_str(endpoints, "run_dispatch")
        or _first_run_dispatch_endpoint(raw)
    )
    return AuthPosture(
        auth_flow=_safe_str(auth, "flow") or _safe_str(auth, "auth_flow"),
        auth_realm=_safe_str(auth, "realm") or _safe_str(auth, "auth_realm"),
        discovery_endpoint=discovery_endpoint,
        identity_endpoint=identity_endpoint,
        run_dispatch_endpoint=run_dispatch_endpoint,
        event_query_endpoint=_safe_str(endpoints, "event_query"),
        supported_flows=supported_flows,
        preferred_interactive_flow=_safe_str(auth, "preferred_interactive_flow"),
    )


def _extract_features(raw: Dict[str, Any]) -> FeatureFlags:
    """Extract feature flags from raw capabilities."""
    flags_raw = _safe_dict(raw, "feature_flags")
    flags = {k: bool(v) for k, v in flags_raw.items() if isinstance(v, bool)}
    return FeatureFlags(flags=flags)


def _extract_context_access(raw: Dict[str, Any]) -> ContextAccessContract:
    """Extract context-access contract from raw capabilities."""
    ctx = _safe_dict(raw, "context_access")
    return ContextAccessContract(
        implemented_surfaces=_safe_list(ctx, "implemented"),
        declared_count=_safe_int(ctx, "declared_count"),
        implemented_count=_safe_int(ctx, "implemented_count"),
    )


def _extract_guidance(raw: Dict[str, Any]) -> ClientGuidance:
    """Extract client guidance from raw capabilities."""
    guide = _safe_dict(raw, "client_guidance")
    return ClientGuidance(
        run_type_rule=_safe_str(guide, "run_type_rule"),
        run_type_mistakes=_safe_list(guide, "run_type_mistakes"),
        gap_workflow_guidance=_safe_str(guide, "gap_workflow_guidance"),
        event_query_guidance=_safe_str(guide, "event_query_guidance"),
    )


def _extract_metadata(raw: Dict[str, Any], envelope: Optional[Dict[str, Any]] = None) -> DiscoveryMetadata:
    """Extract discovery metadata from raw capabilities."""
    meta = _safe_dict(raw, "meta")
    envelope = envelope or raw
    envelope_meta = _safe_dict(envelope, "meta")
    return DiscoveryMetadata(
        generated_at=(
            _safe_str(meta, "generated_at")
            or _safe_str(envelope_meta, "generated_at")
            or _safe_str(raw, "generated_at")
            or _safe_str(envelope, "generated_at")
        ),
        digest=(
            _safe_str(meta, "digest")
            or _safe_str(envelope_meta, "digest")
            or _safe_str(raw, "digest")
            or _safe_str(envelope, "digest")
        ),
        ctx_ref_sha256=(
            _safe_str(meta, "ctx_ref_sha256")
            or _safe_str(envelope_meta, "ctx_ref_sha256")
            or _safe_str(raw, "ctx_ref_sha256")
            or _safe_str(envelope, "ctx_ref_sha256")
        ),
        correlation_id=(
            _safe_str(meta, "correlation_id")
            or _safe_str(envelope_meta, "correlation_id")
            or _safe_str(raw, "correlation_id")
            or _safe_str(envelope, "correlation_id")
        ),
        server_time=(
            _safe_str(meta, "server_time")
            or _safe_str(envelope_meta, "server_time")
            or _safe_str(raw, "server_time")
            or _safe_str(envelope, "server_time")
        ),
    )


def _extract_connection_surfaces(raw: Dict[str, Any]) -> ConnectionSurfaceContract:
    """Extract connection surface contract from raw capabilities.

    SDK-SERVER-01-C introduces ``connection_surfaces`` in the capabilities
    response.  The field may appear at the top level or nested under ``data``.
    """
    cs = _safe_dict(raw, "connection_surfaces")
    if not cs:
        # Also check under data.connection_surfaces (server envelope)
        data = _safe_dict(raw, "data")
        cs = _safe_dict(data, "connection_surfaces")
    if not cs:
        return ConnectionSurfaceContract()

    run_types_raw = cs.get("run_types", [])
    run_types = []
    if isinstance(run_types_raw, list):
        for rt in run_types_raw:
            if isinstance(rt, dict):
                run_types.append(ConnectionSurfaceRunType(
                    run_type=_safe_str(rt, "run_type"),
                    implemented=_safe_bool(rt, "implemented"),
                    read_only=_safe_bool(rt, "read_only"),
                    auth_required=_safe_bool(rt, "auth_required"),
                    scope=_safe_str(rt, "scope"),
                    description=_safe_str(rt, "description"),
                ))

    return ConnectionSurfaceContract(
        schema_version=_safe_str(cs, "schema_version"),
        story_id=_safe_str(cs, "story_id"),
        required_scopes=_safe_dict(cs, "required_scopes"),
        run_types=run_types,
    )


def _first_run_dispatch_endpoint(raw: Dict[str, Any]) -> str:
    for op in _safe_list(raw, "operations"):
        if not isinstance(op, dict):
            continue
        path = _safe_str(op, "path")
        canonical = _safe_dict(op, "canonical_endpoint")
        canonical_path = _safe_str(canonical, "path")
        if path == "/mcp/v1/runs/start" or canonical_path == "/mcp/v1/runs/start":
            return "/mcp/v1/runs/start"
    return ""
