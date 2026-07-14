"""Ingestion data models — SDK-CLIENT-10 §3, §9, §10, §16.

Covers: compatibility posture, confidence, scan results, ingestion
packages, graph summaries, and ingestion outcomes. All models use
Pydantic v2 for validation and serialization.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────

class CompatibilityPosture(str, enum.Enum):
    """§9: Repository compatibility posture assessment."""

    FOREIGN = "foreign"
    PARTIALLY_ALIGNED = "partially_aligned"
    KEYHOLE_READY = "keyhole_ready"


class ConfidenceLevel(str, enum.Enum):
    """§16: Confidence annotation for inferred capabilities."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FileClassification(str, enum.Enum):
    """Classification bucket for scanned files."""

    SOURCE = "source"
    TEST = "test"
    DOC = "doc"
    MANIFEST = "manifest"
    BUILD = "build"
    CI = "ci"
    CONFIG = "config"
    DEPENDENCY = "dependency"
    INFRA = "infra"
    OTHER = "other"


# ── Scan-Level Models ────────────────────────────────────

class ScanSignal(BaseModel):
    """A single observed signal from the repository scan (§8)."""

    kind: str = Field(..., description="Signal type, e.g. 'manifest', 'language', 'framework'.")
    path: str = Field("", description="Relative path within the repo that produced this signal.")
    value: str = Field("", description="Signal value, e.g. 'python', 'fastapi'.")
    confidence: ConfidenceLevel = Field(
        ConfidenceLevel.MEDIUM,
        description="How confident we are that this signal is correct.",
    )


class RepoScanResult(BaseModel):
    """Deterministic result of a local repository scan (§8).

    Contains only observed facts — no inferred structure.
    """

    repo_root: str = Field(..., description="Absolute path to the scanned repo root.")
    languages: List[str] = Field(default_factory=list, description="Detected programming languages.")
    frameworks: List[str] = Field(default_factory=list, description="Detected frameworks.")
    manifests: List[str] = Field(default_factory=list, description="Relative paths to dependency manifests.")
    source_dirs: List[str] = Field(default_factory=list, description="Likely source directories.")
    test_dirs: List[str] = Field(default_factory=list, description="Likely test directories.")
    doc_files: List[str] = Field(default_factory=list, description="Documentation files found.")
    build_files: List[str] = Field(default_factory=list, description="Build/CI configuration files.")
    included_files: List[str] = Field(default_factory=list, description="Files included in the package.")
    excluded_files: List[str] = Field(default_factory=list, description="Files excluded by filter rules.")
    signals: List[ScanSignal] = Field(default_factory=list, description="Raw scan signals.")
    total_files: int = Field(0, description="Total files discovered before filtering.")
    total_included_bytes: int = Field(0, description="Total bytes of included files.")
    has_keyhole_scaffold: bool = Field(False, description="Whether the repo already has Keyhole scaffold.")
    scan_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the scan.",
    )


# ── Ingestion Package ───────────────────────────────────

class IngestionPackage(BaseModel):
    """Deterministic ingestion package built from scan results (§10).

    Ready for wire-format submission. Contains only what is needed
    for governed graphing and inference — no secrets, no mutation.
    """

    repo_identity: str = Field(..., description="Repo name or path identity.")
    local_path: str = Field(..., description="Absolute local path of the scanned repo.")
    languages: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    manifests: List[str] = Field(default_factory=list)
    source_dirs: List[str] = Field(default_factory=list)
    test_dirs: List[str] = Field(default_factory=list)
    doc_files: List[str] = Field(default_factory=list)
    build_files: List[str] = Field(default_factory=list)
    included_file_manifest: List[str] = Field(default_factory=list)
    exclusion_rules: List[str] = Field(default_factory=list)
    dependency_summaries: Dict[str, Any] = Field(default_factory=dict)
    signals: List[Dict[str, Any]] = Field(default_factory=list)
    scan_summary: Dict[str, Any] = Field(default_factory=dict)
    compatibility_inputs: Dict[str, Any] = Field(default_factory=dict)
    shadow: bool = Field(False)
    correlation_id: str = Field("")
    gap_id: str = Field("")
    repo_remote: str = Field("")
    commit_sha: str = Field("")
    current_branch: str = Field("")
    builder_hints: Dict[str, Any] = Field(default_factory=dict)
    package_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def to_payload(self) -> Dict[str, Any]:
        """Wire-format payload for ingestion submission."""
        return self.model_dump(mode="json")

    def to_proof_dict(self) -> Dict[str, Any]:
        """Proof-safe serialization — no local paths exposed."""
        d = self.model_dump(mode="json")
        d.pop("local_path", None)
        return d


# ── Ingestion Request ────────────────────────────────────

class IngestionRequest(BaseModel):
    """Shaped request for the ingestion boundary endpoint."""

    package: IngestionPackage
    identity_fingerprint: str = Field("")
    gap_id: str = Field("")
    repo_remote: str = Field("")
    commit_sha: str = Field("")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def to_payload(self) -> Dict[str, Any]:
        """Wire-format dict for transport dispatch."""
        return {
            "package": self.package.to_payload(),
            "identity_fingerprint": self.identity_fingerprint,
            "gap_id": self.gap_id or self.package.gap_id,
            "repo_remote": self.repo_remote or self.package.repo_remote,
            "commit_sha": self.commit_sha or self.package.commit_sha,
            "timestamp": self.timestamp,
        }

    def to_proof_dict(self) -> Dict[str, Any]:
        """Proof-safe serialization."""
        return {
            "package_summary": {
                "repo_identity": self.package.repo_identity,
                "languages": self.package.languages,
                "frameworks": self.package.frameworks,
                "total_included": len(self.package.included_file_manifest),
                "shadow": self.package.shadow,
                "correlation_id": self.package.correlation_id,
                "gap_id": self.gap_id or self.package.gap_id,
                "repo_remote": self.repo_remote or self.package.repo_remote,
                "commit_sha": self.commit_sha or self.package.commit_sha,
            },
            "identity_fingerprint": self.identity_fingerprint,
            "timestamp": self.timestamp,
        }


# ── Inference / Graph Response Models ────────────────────

class InferredCapability(BaseModel):
    """§16: A single capability inferred by the server.

    Explicitly marked as inferred — not declared truth.
    """

    name: str = Field(..., description="Inferred capability name.")
    confidence: ConfidenceLevel = Field(ConfidenceLevel.LOW)
    basis: str = Field("", description="What evidence led to this inference.")
    category: str = Field("", description="Optional categorization.")


class GraphSummary(BaseModel):
    """Server-returned graph summary from ingestion (§14, §16)."""

    node_count: int = Field(0, description="Number of nodes in the graph.")
    edge_count: int = Field(0, description="Number of edges in the graph.")
    components: int = Field(0, description="Number of connected components.")
    primary_language: str = Field("")
    topology_notes: List[str] = Field(default_factory=list)


class IngestionOutcome(BaseModel):
    """Complete ingestion outcome — honest rendering (§15).

    Preserves the observed/inferred/suggested distinction from §3.
    """

    status: str = Field(..., description="Outcome status: success, accepted, deferred, rejected, failed.")
    ingestion_id: Optional[str] = Field(None, description="Server-assigned ingestion/run ID.")
    repo_identity: str = Field("")
    shadow: bool = Field(False)
    correlation_id: str = Field("")

    # §9: Compatibility posture
    compatibility: CompatibilityPosture = Field(CompatibilityPosture.FOREIGN)

    # §16: Graph output
    graph_summary: Optional[GraphSummary] = Field(None)

    # §16: Inferred capabilities
    inferred_capabilities: List[InferredCapability] = Field(default_factory=list)

    # §16: Warnings and caveats
    warnings: List[str] = Field(default_factory=list)

    # §15: Suggested next actions
    suggested_actions: List[str] = Field(default_factory=list)

    # Transport/proof metadata
    http_status: int = Field(0)
    response_data: Dict[str, Any] = Field(default_factory=dict)

    # Error state
    error_class: str = Field("")
    reason: str = Field("")
    repair_guidance: List[str] = Field(default_factory=list)
    is_local_failure: bool = Field(False)

    def to_proof_dict(self) -> Dict[str, Any]:
        """Proof-safe rendering of the outcome."""
        d: Dict[str, Any] = {
            "status": self.status,
            "repo_identity": self.repo_identity,
            "shadow": self.shadow,
            "correlation_id": self.correlation_id,
            "compatibility": self.compatibility.value,
            "http_status": self.http_status,
        }
        if self.ingestion_id:
            d["ingestion_id"] = self.ingestion_id
        if self.graph_summary:
            d["graph_summary"] = self.graph_summary.model_dump(mode="json")
        if self.inferred_capabilities:
            d["inferred_capabilities"] = [
                c.model_dump(mode="json") for c in self.inferred_capabilities
            ]
        if self.warnings:
            d["warnings"] = self.warnings
        if self.suggested_actions:
            d["suggested_actions"] = self.suggested_actions
        if self.error_class:
            d["error_class"] = self.error_class
        if self.reason:
            d["reason"] = self.reason
        if self.repair_guidance:
            d["repair_guidance"] = self.repair_guidance
        return d
