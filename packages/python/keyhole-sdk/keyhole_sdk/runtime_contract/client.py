"""Runtime contract MCP client — SDK-CLIENT-24 §10.3.

Submits runtime claims, calls the SDK-SERVER-24 runtime contract surfaces,
and returns typed results. The client never decides runtime trust; it
only carries the server's classification back to the caller.

The client must NOT:
  - import platform internals
  - call internal cluster services (NATS, k8s, vault, db)
  - resolve ``.venv`` symlinks as platform truth
  - replicate any control-plane decision logic
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from keyhole_sdk.discovery.client import CapabilitiesClient
from keyhole_sdk.discovery.models import CapabilitiesResult
from keyhole_sdk.exceptions import (
    PublicEndpointError,
    SchemaError,
    TransportError,
)
from keyhole_sdk.runtime_contract.models import (
    CONTRACT_VERSION,
    RuntimeCompatibilityResult,
    RuntimeCompatibilityStatus,
    RuntimeContext,
    RuntimeProfile,
    RuntimeProfileKind,
    RuntimeRepairGuidance,
    RuntimeSurfaceResult,
)
from keyhole_sdk.runtime_contract.repair import (
    fill_repair_defaults,
    map_runtime_repair,
)
from keyhole_sdk.transport.client import GovernedTransport


SURFACE_GET_RUN_TYPE = "sdk.runtime.surface.get.v1"
COMPATIBILITY_CHECK_RUN_TYPE = "sdk.runtime.compatibility.check.v1"
RUN_DISPATCH_PATH = "/mcp/v1/runs/start"


class RuntimeContractClient:
    """Client for the SDK-SERVER-24 runtime contract surfaces."""

    def __init__(
        self,
        *,
        transport: GovernedTransport,
        capabilities_client: Optional[CapabilitiesClient] = None,
        repo_name: str = "keyhole-sdk",
    ) -> None:
        self._transport = transport
        self._capabilities_client = capabilities_client or CapabilitiesClient(
            transport.base_url
        )
        self._repo_name = repo_name

    # ── Profiles via /mcp/v1/capabilities ────────────────────

    def get_runtime_profiles(
        self,
        *,
        capabilities: Optional[CapabilitiesResult] = None,
    ) -> List[RuntimeProfile]:
        """Read runtime profiles from the capabilities block (§9.1).

        Raises :class:`PublicEndpointError` if ``runtime_profiles`` is
        missing — surfaced with the canonical reason
        ``runtime_profiles_missing`` (§12.5).
        """
        caps = capabilities or self._capabilities_client.fetch()
        block = _extract_runtime_block(caps.raw)
        profiles_raw = block.get("profiles") if isinstance(block, dict) else None
        if not isinstance(profiles_raw, list) or not profiles_raw:
            raise PublicEndpointError(
                "runtime_profiles missing from capabilities",
                status_code=200,
                detail="runtime_profiles_missing",
            )
        return [RuntimeProfile.from_raw(item) for item in profiles_raw if isinstance(item, dict)]

    # ── Surface via sdk.runtime.surface.get.v1 ────────────────

    def get_runtime_surface(
        self,
        *,
        request_id: Optional[str] = None,
    ) -> RuntimeSurfaceResult:
        """Call ``sdk.runtime.surface.get.v1`` (§9.2)."""
        payload: Dict[str, Any] = {
            "run_type": SURFACE_GET_RUN_TYPE,
            "repo": self._repo_name,
            "shadow": False,
            "input": {"contract_version": CONTRACT_VERSION},
        }
        result = self._transport.execute(
            "POST",
            RUN_DISPATCH_PATH,
            operation_name=SURFACE_GET_RUN_TYPE,
            json=payload,
        )
        data = _unwrap(result.data)
        profiles_raw = data.get("profiles") or []
        if not isinstance(profiles_raw, list):
            profiles_raw = []
        profiles = [
            RuntimeProfile.from_raw(item)
            for item in profiles_raw
            if isinstance(item, dict)
        ]
        canonical_profile_id = ""
        external_profile_id = ""
        for p in profiles:
            if p.canonical and p.kind == RuntimeProfileKind.CONTAINER:
                canonical_profile_id = p.profile_id
            if p.kind == RuntimeProfileKind.EXTERNAL and not external_profile_id:
                external_profile_id = p.profile_id
        # Fall back to top-level disclosure if server emits aliases
        canonical_profile_id = (
            data.get("canonical_profile_id")
            or data.get("canonical")
            or canonical_profile_id
        )
        external_profile_id = (
            data.get("external_profile_id")
            or data.get("external")
            or external_profile_id
        )
        return RuntimeSurfaceResult(
            status=str(data.get("status", "ACCEPT")),
            contract_version=str(
                data.get("contract_version", CONTRACT_VERSION)
            ),
            canonical_profile_id=str(canonical_profile_id),
            external_profile_id=str(external_profile_id),
            profiles=profiles,
            raw=data,
        )

    # ── Compatibility via sdk.runtime.compatibility.check.v1 ──

    def check_compatibility(
        self,
        runtime_context: RuntimeContext,
        *,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: str = "",
    ) -> RuntimeCompatibilityResult:
        """Call ``sdk.runtime.compatibility.check.v1`` (§9.3)."""
        payload: Dict[str, Any] = {
            "run_type": COMPATIBILITY_CHECK_RUN_TYPE,
            "repo": self._repo_name,
            "shadow": False,
            "input": {"runtime_context": runtime_context.to_payload()},
        }
        if correlation_id:
            payload["correlation_id"] = correlation_id

        try:
            result = self._transport.execute(
                "POST",
                RUN_DISPATCH_PATH,
                operation_name=COMPATIBILITY_CHECK_RUN_TYPE,
                json=payload,
                idempotency_key=idempotency_key,
            )
        except PublicEndpointError as exc:
            # Translate explicit server rejection to a typed result so the
            # CLI can render server-provided repair guidance verbatim.
            return _result_from_endpoint_error(
                exc, correlation_id=correlation_id
            )

        data = _unwrap(result.data)
        outcome = RuntimeCompatibilityResult.from_raw(
            data, correlation_id=correlation_id
        )
        outcome.repair = fill_repair_defaults(outcome.repair)
        return outcome


# ──────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────


def _extract_runtime_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Locate the ``runtime_profiles`` block in raw capabilities."""
    if not isinstance(raw, dict):
        return {}
    # Top-level (current SDK-SERVER-24 contract)
    block = raw.get("runtime_profiles")
    if isinstance(block, dict):
        return block
    if isinstance(block, list):
        return {"profiles": block}
    # Nested under ``data``
    data = raw.get("data")
    if isinstance(data, dict):
        nested = data.get("runtime_profiles")
        if isinstance(nested, dict):
            return nested
        if isinstance(nested, list):
            return {"profiles": nested}
    return {}


def _unwrap(data: Any) -> Dict[str, Any]:
    """Unwrap a possible MCP envelope while tolerating raw responses."""
    if not isinstance(data, dict):
        return {}
    # Some MCP responses wrap content under "data" or "result"
    inner = data.get("data") if isinstance(data.get("data"), dict) else None
    if inner and any(
        k in inner for k in ("status", "selected_profile", "profiles")
    ):
        return inner
    inner = data.get("result") if isinstance(data.get("result"), dict) else None
    if inner and any(
        k in inner for k in ("status", "selected_profile", "profiles")
    ):
        return inner
    return data


def _result_from_endpoint_error(
    exc: PublicEndpointError,
    *,
    correlation_id: str,
) -> RuntimeCompatibilityResult:
    """Translate a 4xx into a typed REJECT outcome with repair guidance."""
    detail = getattr(exc, "detail", "") or ""
    reason = ""
    # Heuristic: the server may stamp a reason code in the detail.
    for token in (
        "missing_container_digest",
        "nonportable_runtime_coupling",
        "compatibility_check_failed",
    ):
        if token in detail:
            reason = token
            break
    if not reason:
        reason = "compatibility_check_failed"
    repair = RuntimeRepairGuidance(
        reason=reason,
        message=str(exc),
        repair=map_runtime_repair(reason),
    )
    return RuntimeCompatibilityResult(
        status=RuntimeCompatibilityStatus.REJECT,
        reason=reason,
        message=str(exc),
        repair=repair,
        correlation_id=correlation_id,
        raw={"error": str(exc), "detail": detail},
    )
