"""Run request construction — SDK-CLIENT-09 §8.

Deterministic request shaping from local repo identity, active
credentials, run type, execution mode, and optional context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class RunRequest:
    """Shaped governed run request ready for transport dispatch.

    Fields are deterministic for the same local input state (§8).
    """

    run_type: str
    repo_name: str
    shadow: bool = False
    context_ref: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    correlation_id: str = ""
    identity_fingerprint: str = ""
    timestamp: str = ""

    def to_payload(self) -> Dict[str, Any]:
        """Build the wire-format payload for POST /mcp/v1/runs/start."""
        payload: Dict[str, Any] = {
            "run_type": self.run_type,
            "repo": self.repo_name,
            "shadow": self.shadow,
        }
        if self.context_ref:
            payload["ctxpack_digest"] = self.context_ref
            payload["context_ref"] = self.context_ref
        if self.input_data:
            payload["input"] = self.input_data
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        return payload

    def to_proof_dict(self) -> Dict[str, Any]:
        """Proof-safe serialization — no secrets."""
        d: Dict[str, Any] = {
            "run_type": self.run_type,
            "repo": self.repo_name,
            "shadow": self.shadow,
            "correlation_id": self.correlation_id,
            "identity_fingerprint": self.identity_fingerprint,
            "timestamp": self.timestamp,
        }
        if self.context_ref:
            d["context_ref"] = self.context_ref
        if self.input_data:
            d["has_input"] = True
        return d


def build_run_request(
    *,
    run_type: str,
    repo_name: str,
    shadow: bool = False,
    context_ref: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
    correlation_id: str = "",
    identity_fingerprint: str = "",
) -> RunRequest:
    """Construct a deterministic RunRequest from local inputs.

    The timestamp is captured at construction so proof artifacts
    reflect the actual dispatch time.
    """
    return RunRequest(
        run_type=run_type,
        repo_name=repo_name,
        shadow=shadow,
        context_ref=context_ref,
        input_data=input_data,
        correlation_id=correlation_id,
        identity_fingerprint=identity_fingerprint,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
