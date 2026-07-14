"""Normalized capabilities model for the MCP boundary contract.

CE-V5-S42-03: Capabilities Discovery Client.

Every model reflects the **public-safe** capabilities contract only.
The normalized structure is shaped around participant needs:
  - How do I connect?
  - What contract am I talking to?
  - What context surfaces exist?
  - What guidance did the boundary publish?

Discovery metadata (generated_at, digest, ctx_ref_sha256, correlation_id,
server_time) is preserved — never stripped during normalization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# A) Contract Identity
# ──────────────────────────────────────────────────────────────
class ContractIdentity(BaseModel):
    """Contract identity from the capabilities surface."""

    contract: str = ""
    schema_versions: Dict[str, str] = Field(default_factory=dict)
    operations_declared: int = 0
    operations_implemented: int = 0


# ──────────────────────────────────────────────────────────────
# B) Compatibility Posture
# ──────────────────────────────────────────────────────────────
class CompatibilityPosture(BaseModel):
    """Compatibility posture disclosed by the boundary."""

    min_sdk_version: str = ""
    envelope_version: str = ""
    passport_version: str = ""
    charter_required: bool = False
    workspace_supported: bool = False


# ──────────────────────────────────────────────────────────────
# C) Auth / Transport Posture
# ──────────────────────────────────────────────────────────────
class TransportPosture(BaseModel):
    """Transport posture from the capabilities surface."""

    transport: str = ""
    tombstoned_transports: List[str] = Field(default_factory=list)


class AuthPosture(BaseModel):
    """Authentication posture from the capabilities surface.

    Extended in SDK-CLIENT-25 to surface ``supported_flows`` and
    ``preferred_interactive_flow`` advertised by SDK-SERVER-25.
    """

    auth_flow: str = ""
    auth_realm: str = ""
    discovery_endpoint: str = ""
    identity_endpoint: str = ""
    run_dispatch_endpoint: str = ""
    event_query_endpoint: str = ""
    supported_flows: List[str] = Field(default_factory=list)
    preferred_interactive_flow: str = ""

    def supports_device_authorization(self) -> bool:
        """Whether the boundary advertises OAuth Device Authorization Grant."""
        return "device_authorization" in self.supported_flows

    def supports_pkce(self) -> bool:
        """Whether the boundary advertises Authorization Code + PKCE."""
        return "authorization_code_pkce" in self.supported_flows


# ──────────────────────────────────────────────────────────────
# D) Feature Flags
# ──────────────────────────────────────────────────────────────
class FeatureFlags(BaseModel):
    """Feature flags disclosed by the boundary.

    Preserves all flags from the raw response without inventing
    flags that are not present.
    """

    flags: Dict[str, bool] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# E) Context Access Contract
# ──────────────────────────────────────────────────────────────
class ContextAccessContract(BaseModel):
    """Implemented context-access surfaces from the capabilities contract."""

    implemented_surfaces: List[str] = Field(default_factory=list)
    declared_count: int = 0
    implemented_count: int = 0

    @property
    def all_implemented(self) -> bool:
        """True when all declared context surfaces are implemented."""
        return (
            self.declared_count > 0
            and self.declared_count == self.implemented_count
        )


# ──────────────────────────────────────────────────────────────
# F) Client Guidance
# ──────────────────────────────────────────────────────────────
class ClientGuidance(BaseModel):
    """Public-safe client guidance published by the boundary."""

    run_type_rule: str = ""
    run_type_mistakes: List[str] = Field(default_factory=list)
    gap_workflow_guidance: str = ""
    event_query_guidance: str = ""


# ──────────────────────────────────────────────────────────────
# G) Connection Surface Contract (SDK-SERVER-01-C)
# ──────────────────────────────────────────────────────────────
class ConnectionSurfaceRunType(BaseModel):
    """A single connection surface run-type entry as advertised by the boundary."""

    run_type: str = ""
    implemented: bool = False
    read_only: bool = True
    auth_required: bool = True
    scope: str = ""
    description: str = ""


class ConnectionSurfaceContract(BaseModel):
    """Connection surface contract advertised via ``data.connection_surfaces``.

    Introduced in SDK-SERVER-01-C.  The boundary may advertise connection
    run types outside the top-level ``operations`` array.  This section
    captures those ops so the SDK can discover them correctly.
    """

    schema_version: str = ""
    story_id: str = ""
    required_scopes: Dict[str, str] = Field(default_factory=dict)
    run_types: List[ConnectionSurfaceRunType] = Field(default_factory=list)

    def get_run_type_names(self) -> List[str]:
        """Return the run-type name strings for surface availability checks."""
        return [rt.run_type for rt in self.run_types if rt.run_type]


# ──────────────────────────────────────────────────────────────
# H) Discovery Metadata
# ──────────────────────────────────────────────────────────────
class DiscoveryMetadata(BaseModel):
    """Discovery metadata preserved from the raw capabilities response."""

    generated_at: str = ""
    digest: str = ""
    ctx_ref_sha256: str = ""
    correlation_id: str = ""
    server_time: str = ""


# ──────────────────────────────────────────────────────────────
# Top-level Normalized Result
# ──────────────────────────────────────────────────────────────
class CapabilitiesResult(BaseModel):
    """Normalized capabilities result from ``GET /mcp/v1/capabilities``.

    This is the first-class, stable representation that downstream
    consumers use.  It is shaped around participant needs rather than
    mirroring the raw response 1:1.

    Every section is optional so the model tolerates evolving
    responses within contract bounds.
    """

    contract: ContractIdentity = Field(default_factory=ContractIdentity)
    compatibility: CompatibilityPosture = Field(default_factory=CompatibilityPosture)
    transport: TransportPosture = Field(default_factory=TransportPosture)
    auth: AuthPosture = Field(default_factory=AuthPosture)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    context_access: ContextAccessContract = Field(
        default_factory=ContextAccessContract
    )
    guidance: ClientGuidance = Field(default_factory=ClientGuidance)
    metadata: DiscoveryMetadata = Field(default_factory=DiscoveryMetadata)
    connection_surfaces: ConnectionSurfaceContract = Field(
        default_factory=ConnectionSurfaceContract
    )
    raw: Dict[str, Any] = Field(
        default_factory=dict,
        description="Full raw capabilities response preserved for traceability.",
    )

    # ── Helper accessors ────────────────────────────────────

    def is_charter_required(self) -> bool:
        """Whether the boundary requires charter."""
        return self.compatibility.charter_required

    def is_workspace_supported(self) -> bool:
        """Whether the boundary supports workspace."""
        return self.compatibility.workspace_supported

    def get_min_sdk_version(self) -> str:
        """Return the minimum SDK version from compatibility posture."""
        return self.compatibility.min_sdk_version

    def get_implemented_context_surfaces(self) -> List[str]:
        """Return the list of implemented context-access surfaces."""
        return list(self.context_access.implemented_surfaces)

    def get_auth_flow(self) -> str:
        """Return the expected auth flow."""
        return self.auth.auth_flow

    def get_transport(self) -> str:
        """Return the transport type."""
        return self.transport.transport

    def get_contract_version(self) -> str:
        """Return the contract identifier."""
        return self.contract.contract

    def get_feature_flag(self, name: str) -> Optional[bool]:
        """Return a feature flag value, or None if not disclosed."""
        return self.features.flags.get(name)

    def get_run_type_rule(self) -> str:
        """Return the published run-type discipline rule."""
        return self.guidance.run_type_rule

    def get_gap_workflow_guidance(self) -> str:
        """Return the published gap-workflow guidance."""
        return self.guidance.gap_workflow_guidance

    def get_event_query_guidance(self) -> str:
        """Return the published event-query guidance."""
        return self.guidance.event_query_guidance

    def get_all_run_types(self) -> List[str]:
        """Return all run-type names from all advertised sources.

        Merges the top-level ``operations`` list (if exposed) with the
        ``connection_surfaces.run_types`` list introduced in SDK-SERVER-01-C.
        Callers should prefer this method over reading raw capabilities
        directly when building the ``server_operations`` list for
        ``check_connection_surfaces_available()``.
        """
        body = self.raw.get("data") if isinstance(self.raw.get("data"), dict) else self.raw
        operations = body.get("operations", []) if isinstance(body, dict) else []
        top_ops: List[str] = []
        if isinstance(operations, list):
            for op in operations:
                if isinstance(op, str) and op:
                    top_ops.append(op)
                elif isinstance(op, dict):
                    for key in ("operation_id", "name", "canonical_run_type"):
                        value = op.get(key)
                        if isinstance(value, str) and value:
                            top_ops.append(value)
                    aliases = op.get("aliases")
                    if isinstance(aliases, list):
                        top_ops.extend(alias for alias in aliases if isinstance(alias, str) and alias)
        if isinstance(body, dict):
            top_ops.extend(_extract_nested_run_types(body.get("governed_worker_sdk")))
        top_ops.extend(self.get_implemented_context_surfaces())
        # Connection surface ops
        cs_ops = self.connection_surfaces.get_run_type_names()
        # Merge, deduplicate, preserve order
        seen: set = set()
        merged: List[str] = []
        for op in top_ops + cs_ops:
            if op not in seen:
                seen.add(op)
                merged.append(op)
        return merged


def _extract_nested_run_types(value: Any) -> List[str]:
    """Collect run type declarations from nested governed-worker capabilities."""
    found: List[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"run_type", "canonical_run_type", "compatibility_check_run_type"}:
                if isinstance(item, str) and item:
                    found.append(item)
            elif key in {"logical_aliases", "aliases"} and isinstance(item, list):
                found.extend(alias for alias in item if isinstance(alias, str) and alias)
            else:
                found.extend(_extract_nested_run_types(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_nested_run_types(item))
    return found
