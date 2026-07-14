"""Ingestion packager — SDK-CLIENT-10 §10.

Transforms a RepoScanResult into a deterministic IngestionPackage
ready for wire submission. Privacy-safe: no secrets, no mutation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from keyhole_sdk.ingest.models import (
    CompatibilityPosture,
    IngestionPackage,
    RepoScanResult,
)
from keyhole_sdk.transport.idempotency import generate_request_id


def build_ingestion_package(
    scan: RepoScanResult,
    *,
    shadow: bool = False,
    correlation_id: str = "",
    gap_id: str = "",
    repo_remote: str = "",
    commit_sha: str = "",
    current_branch: str = "",
    builder_hints: Optional[Dict[str, Any]] = None,
    exclusion_rules: Optional[list[str]] = None,
) -> IngestionPackage:
    """Build a deterministic ingestion package from scan results (§10).

    The package is deterministic for the same scan result — same input
    always produces the same package structure (timestamps aside).

    Args:
        scan: The completed repo scan result.
        shadow: Whether this is a shadow/exploratory ingestion.
        correlation_id: Correlation ID for tracing. Auto-generated if empty.
        gap_id: Canonical gap identifier for governed repo registration.
        repo_remote: Git origin URL for the subject repository.
        commit_sha: Current Git HEAD SHA for the subject repository.
        current_branch: Current Git branch for the subject repository.
        builder_hints: Optional builder-supplied hints for the server.
        exclusion_rules: Exclusion rules applied during scan.

    Returns:
        IngestionPackage ready for submission.
    """
    if not correlation_id:
        correlation_id = generate_request_id()

    # Build scan summary
    scan_summary: Dict[str, Any] = {
        "total_files": scan.total_files,
        "included_files": len(scan.included_files),
        "excluded_files": len(scan.excluded_files),
        "total_included_bytes": scan.total_included_bytes,
        "has_keyhole_scaffold": scan.has_keyhole_scaffold,
        "scan_timestamp": scan.scan_timestamp,
    }

    # Build compatibility inputs
    compatibility_inputs = _assess_compatibility_inputs(scan)

    # Build dependency summaries from manifests
    dependency_summaries: Dict[str, Any] = {}
    for m in scan.manifests:
        name = Path(m).name
        dependency_summaries[name] = {"path": m}

    return IngestionPackage(
        repo_identity=Path(scan.repo_root).name,
        local_path=scan.repo_root,
        languages=scan.languages,
        frameworks=scan.frameworks,
        manifests=scan.manifests,
        source_dirs=scan.source_dirs,
        test_dirs=scan.test_dirs,
        doc_files=scan.doc_files,
        build_files=scan.build_files,
        included_file_manifest=scan.included_files,
        exclusion_rules=exclusion_rules or [],
        dependency_summaries=dependency_summaries,
        signals=[s.model_dump(mode="json") for s in scan.signals],
        scan_summary=scan_summary,
        compatibility_inputs=compatibility_inputs,
        shadow=shadow,
        correlation_id=correlation_id,
        gap_id=gap_id,
        repo_remote=repo_remote,
        commit_sha=commit_sha,
        current_branch=current_branch,
        builder_hints=builder_hints or {},
    )


def _assess_compatibility_inputs(scan: RepoScanResult) -> Dict[str, Any]:
    """Compute compatibility posture inputs from scan data (§9).

    This is NOT the final posture — the server may override.
    These are client-side inputs to assist the server.
    """
    posture = CompatibilityPosture.FOREIGN

    if scan.has_keyhole_scaffold:
        posture = CompatibilityPosture.KEYHOLE_READY
    elif scan.manifests and scan.source_dirs:
        # Some structural signals exist
        posture = CompatibilityPosture.PARTIALLY_ALIGNED

    return {
        "client_assessed_posture": posture.value,
        "has_keyhole_scaffold": scan.has_keyhole_scaffold,
        "has_manifests": bool(scan.manifests),
        "has_source_dirs": bool(scan.source_dirs),
        "has_test_dirs": bool(scan.test_dirs),
        "has_docs": bool(scan.doc_files),
        "language_count": len(scan.languages),
        "framework_count": len(scan.frameworks),
    }
