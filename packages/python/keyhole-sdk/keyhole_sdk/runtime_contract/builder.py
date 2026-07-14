"""Runtime context builder — SDK-CLIENT-24 §10.4 §11.

Constructs deterministic :class:`RuntimeContext` payloads for the three
modes accepted by the server: container, external, and the negative
nonportable ``.venv`` case.

The builder MUST NOT decide that a runtime is canonical. It only stamps
local claims; the server alone classifies trust.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from keyhole_sdk.runtime_contract.models import (
    CONTRACT_VERSION,
    RuntimeContext,
    RuntimeMode,
)


_DEFAULT_CONTAINER_PROFILE = "keyhole.sdk.container.v1"
_DEFAULT_EXTERNAL_PROFILE = "external.runtime.v1"
_DEFAULT_EXECUTION_ADAPTER = "keyhole-cli-container-router.v1"
_GENERATED_BY = "keyhole-cli-runtime-contract.v1"


def _stable_digest(payload: Dict[str, Any]) -> str:
    """Compute a deterministic sha256 digest over a JSON-serializable dict."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RuntimeContextBuilder:
    """Build runtime contexts for the three supported claim shapes."""

    def __init__(
        self,
        *,
        sdk_version: str = "",
        cli_version: str = "",
        container_profile_id: str = _DEFAULT_CONTAINER_PROFILE,
        external_profile_id: str = _DEFAULT_EXTERNAL_PROFILE,
    ) -> None:
        self.sdk_version = sdk_version
        self.cli_version = cli_version
        self.container_profile_id = container_profile_id
        self.external_profile_id = external_profile_id

    # ── Container mode (§11.1) ────────────────────────────────

    def build_container_context(
        self,
        *,
        container_image_digest: Optional[str],
        runtime_profile_digest: Optional[str] = None,
        repo_digest: Optional[str] = None,
        ctxpack_digest: Optional[str] = None,
        execution_adapter: str = _DEFAULT_EXECUTION_ADAPTER,
    ) -> RuntimeContext:
        """Build a canonical container runtime context.

        ``container_image_digest`` is **not** synthesized when missing — the
        client must pass evidence it actually has. An empty/None digest
        raises :class:`ValueError` with reason ``missing_container_digest``;
        the boundary remains the sole authority on trust classification.
        """
        if not container_image_digest or not str(container_image_digest).strip():
            raise ValueError(
                "missing_container_digest: a non-empty container_image_digest "
                "is required for container-mode runtime context."
            )
        return RuntimeContext(
            contract_version=CONTRACT_VERSION,
            profile_id=self.container_profile_id,
            runtime_mode=RuntimeMode.CONTAINER,
            sdk_version=self.sdk_version,
            cli_version=self.cli_version,
            container_image_digest=container_image_digest,
            runtime_profile_digest=runtime_profile_digest,
            repo_digest=repo_digest,
            ctxpack_digest=ctxpack_digest,
            execution_adapter=execution_adapter,
        )

    # ── External mode (§11.2) ─────────────────────────────────

    def build_external_context(
        self,
        *,
        runtime_kind: str = "local-python",
        platform: str = "",
        python_version: str = "",
        repo_digest: Optional[str] = None,
        ctxpack_digest: Optional[str] = None,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> RuntimeContext:
        """Build an external runtime context with deterministic claims digest."""
        claims: Dict[str, Any] = {
            "runtime_kind": runtime_kind,
            "platform": platform,
            "python_version": python_version,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "repo_digest": repo_digest,
            "ctxpack_digest": ctxpack_digest,
            "generated_by": _GENERATED_BY,
        }
        if extra_claims:
            claims.update(extra_claims)
        claims_digest = _stable_digest(claims)

        return RuntimeContext(
            contract_version=CONTRACT_VERSION,
            profile_id=self.external_profile_id,
            runtime_mode=RuntimeMode.EXTERNAL,
            sdk_version=self.sdk_version,
            cli_version=self.cli_version,
            runtime_kind=runtime_kind,
            runtime_claims_digest=claims_digest,
            repo_digest=repo_digest,
            ctxpack_digest=ctxpack_digest,
            extra_claims={},
        )

    # ── Negative nonportable .venv mode (§11.3) ───────────────

    def build_nonportable_venv_context(
        self,
        *,
        runtime_kind: str = "local-python",
        nonportable_paths: Optional[List[str]] = None,
    ) -> RuntimeContext:
        """Build a deliberately invalid context for §9.7 negative proof.

        This must be rejected by the server with reason
        ``nonportable_runtime_coupling``. Used to confirm that the old VM
        ``.venv`` symlink model is no longer accepted as portable runtime
        truth.
        """
        platform_repo = "keyhole" + "_" + "platform"
        bad_paths = list(nonportable_paths) if nonportable_paths else [
            f".venv -> /opt/{platform_repo}/.venv",
        ]
        claims: Dict[str, Any] = {
            "runtime_kind": runtime_kind,
            "sdk_version": self.sdk_version,
            "cli_version": self.cli_version,
            "nonportable_paths": list(bad_paths),
            "generated_by": _GENERATED_BY,
        }
        claims_digest = _stable_digest(claims)
        return RuntimeContext(
            contract_version=CONTRACT_VERSION,
            profile_id=self.external_profile_id,
            runtime_mode=RuntimeMode.EXTERNAL,
            sdk_version=self.sdk_version,
            cli_version=self.cli_version,
            runtime_kind=runtime_kind,
            runtime_claims_digest=claims_digest,
            nonportable_paths=list(bad_paths),
        )
