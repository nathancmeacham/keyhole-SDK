"""Tests for SDK-CLIENT-08 - Capability Discovery and Resolution.

Covers:
  - Models (enums, search request/result, resolution request/outcome, candidates)
  - Search submitter (success, empty, error, transport failure)
  - Resolver (resolved, ambiguous, incompatible, not_found, accepted, deferred, error)
  - Materializer (advisory, write native, foreign rejection, duplicate detection)
  - Proof emission (search proof, resolution proof, file structure)
  - Repair guidance (all mapped error classes, fallback)
  - CLI search command (auth, success, error)
  - CLI dependency resolve command (auth, path, resolved, ambiguous)
  - Operation registry (capability.search, capability.resolve)
  - Public API surface
  - Determinism guarantees
  - No-silent-mutation invariant
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# --------------------------------------------------------------
# 1. Models
# --------------------------------------------------------------


class TestModels:
    """SDK-CLIENT-08 section6, section8, section9 - Model basics."""

    def test_repo_posture_values(self):
        from keyhole_sdk.capability.models import RepoPosture

        assert RepoPosture.NATIVE == "native"
        assert RepoPosture.FOREIGN == "foreign"
        assert RepoPosture.INGESTION_BACKED == "ingestion_backed"

    def test_materialization_mode_values(self):
        from keyhole_sdk.capability.models import MaterializationMode

        assert MaterializationMode.ADVISORY == "advisory"
        assert MaterializationMode.WRITE == "write"

    def test_resolution_status_values(self):
        from keyhole_sdk.capability.models import ResolutionStatus

        assert ResolutionStatus.RESOLVED == "resolved"
        assert ResolutionStatus.AMBIGUOUS == "ambiguous"
        assert ResolutionStatus.INCOMPATIBLE == "incompatible"
        assert ResolutionStatus.NOT_FOUND == "not_found"
        assert ResolutionStatus.REJECTED == "rejected"
        assert ResolutionStatus.FAILED == "failed"
        assert ResolutionStatus.ACCEPTED == "accepted"
        assert ResolutionStatus.DEFERRED == "deferred"

    def test_search_request_to_payload(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest

        req = CapabilitySearchRequest(
            query="observability.tracing",
            provider="opentelemetry",
            version="1.0",
            correlation_id="corr-001",
        )
        payload = req.to_payload()
        assert payload["query"] == "observability.tracing"
        assert payload["provider"] == "opentelemetry"
        assert payload["version"] == "1.0"
        assert payload["context"]["repo_posture"] == "native"
        assert payload["correlation_id"] == "corr-001"

    def test_search_request_to_payload_minimal(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest

        req = CapabilitySearchRequest(query="auth")
        payload = req.to_payload()
        assert payload["query"] == "auth"
        assert "provider" not in payload
        assert "version" not in payload

    def test_search_request_proof_dict(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest

        req = CapabilitySearchRequest(
            query="auth",
            provider="keycloak",
            correlation_id="c-001",
        )
        proof = req.to_proof_dict()
        assert proof["query"] == "auth"
        assert proof["provider"] == "keycloak"
        assert proof["correlation_id"] == "c-001"
        # Must not leak local paths
        assert "repo_path" not in proof
        assert "local" not in str(proof).lower() or "repo_posture" in str(proof)

    def test_capability_candidate_to_dict(self):
        from keyhole_sdk.capability.models import CapabilityCandidate

        cand = CapabilityCandidate(
            capability="observability.tracing",
            provider="opentelemetry",
            version="1.2.0",
            visibility="public",
            summary="Distributed tracing.",
            digest="sha256:abc",
            matches_inferred_need=True,
        )
        d = cand.to_dict()
        assert d["capability"] == "observability.tracing"
        assert d["provider"] == "opentelemetry"
        assert d["version"] == "1.2.0"
        assert d["matches_inferred_need"] is True
        assert "already_pinned_locally" not in d

    def test_capability_candidate_minimal(self):
        from keyhole_sdk.capability.models import CapabilityCandidate

        cand = CapabilityCandidate(capability="auth.oidc")
        d = cand.to_dict()
        assert d["capability"] == "auth.oidc"
        assert "summary" not in d
        assert "digest" not in d

    def test_search_result_proof_dict(self):
        from keyhole_sdk.capability.models import (
            CapabilitySearchResult,
            CapabilityCandidate,
        )

        result = CapabilitySearchResult(
            query="auth",
            candidates=[CapabilityCandidate(capability="auth.oidc")],
            total_count=1,
            correlation_id="c-001",
            http_status=200,
        )
        proof = result.to_proof_dict()
        assert proof["query"] == "auth"
        assert proof["total_count"] == 1
        assert proof["candidate_count"] == 1
        assert proof["correlation_id"] == "c-001"

    def test_resolution_request_to_payload(self):
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            ResolutionRequest,
        )

        req = ResolutionRequest(
            capability="observability.tracing",
            provider="opentelemetry",
            mode=MaterializationMode.WRITE,
            correlation_id="c-002",
        )
        payload = req.to_payload()
        assert payload["capability"] == "observability.tracing"
        assert payload["provider"] == "opentelemetry"
        assert payload["mode"] == "write"
        assert payload["correlation_id"] == "c-002"

    def test_resolution_request_minimal(self):
        from keyhole_sdk.capability.models import ResolutionRequest

        req = ResolutionRequest(capability="auth.oidc")
        payload = req.to_payload()
        assert payload["capability"] == "auth.oidc"
        assert payload["mode"] == "advisory"
        assert "provider" not in payload

    def test_resolved_dependency_to_dict(self):
        from keyhole_sdk.capability.models import ResolvedDependency

        dep = ResolvedDependency(
            capability="auth.oidc",
            provider="keycloak",
            version="22.0",
            digest="sha256:abc",
            reason="Only matching provider.",
        )
        d = dep.to_dict()
        assert d["capability"] == "auth.oidc"
        assert d["provider"] == "keycloak"
        assert d["version"] == "22.0"
        assert d["reason"] == "Only matching provider."

    def test_resolved_dependency_entry(self):
        from keyhole_sdk.capability.models import ResolvedDependency

        dep = ResolvedDependency(
            capability="auth.oidc",
            provider="keycloak",
            version="22.0",
        )
        entry = dep.to_dependency_entry()
        assert entry["capability"] == "auth.oidc"
        assert entry["provider"] == "keycloak"
        assert entry["version"] == "22.0"
        assert "reason" not in entry

    def test_resolution_outcome_is_resolved(self):
        from keyhole_sdk.capability.models import (
            ResolutionOutcome,
            ResolvedDependency,
        )

        outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
            ),
        )
        assert outcome.is_resolved
        assert not outcome.is_ambiguous

    def test_resolution_outcome_is_ambiguous(self):
        from keyhole_sdk.capability.models import ResolutionOutcome

        outcome = ResolutionOutcome(status="ambiguous")
        assert outcome.is_ambiguous
        assert not outcome.is_resolved

    def test_resolution_outcome_proof_dict(self):
        from keyhole_sdk.capability.models import (
            ResolutionOutcome,
            ResolvedDependency,
        )

        outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
                version="22.0",
            ),
            correlation_id="c-003",
            http_status=200,
        )
        proof = outcome.to_proof_dict()
        assert proof["status"] == "resolved"
        assert proof["resolved"]["capability"] == "auth.oidc"
        assert proof["correlation_id"] == "c-003"

    def test_compute_resolution_digest(self):
        from keyhole_sdk.capability.models import compute_resolution_digest

        d1 = compute_resolution_digest("auth", "keycloak", "22.0")
        d2 = compute_resolution_digest("auth", "keycloak", "22.0")
        d3 = compute_resolution_digest("auth", "keycloak", "23.0")
        assert d1 == d2, "Deterministic: same input -> same digest"
        assert d1 != d3, "Different input -> different digest"
        assert d1.startswith("sha256:")


# --------------------------------------------------------------
# 2. Search Submitter
# --------------------------------------------------------------


class TestSearch:
    """SDK-CLIENT-08 section8.1, section11 - Search submitter."""

    def _mock_transport(self, *, data: Dict[str, Any], status_code: int = 200):
        transport = MagicMock()
        result = MagicMock()
        result.data = data
        result.status_code = status_code
        transport.execute.return_value = result
        return transport

    def test_search_success(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = self._mock_transport(data={
            "candidates": [
                {"capability": "auth.oidc", "provider": "keycloak", "version": "22.0"},
                {"capability": "auth.oidc", "provider": "auth0", "version": "4.0"},
            ],
            "total_count": 2,
        })

        request = CapabilitySearchRequest(
            query="auth.oidc",
            correlation_id="c-search-001",
        )
        result = submit_capability_search(transport=transport, request=request)

        assert not result.is_empty
        assert result.total_count == 2
        assert len(result.candidates) == 2
        assert result.candidates[0].capability == "auth.oidc"
        assert not result.error_class

    def test_search_empty(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = self._mock_transport(data={
            "candidates": [],
            "total_count": 0,
        })

        request = CapabilitySearchRequest(query="nonexistent")
        result = submit_capability_search(transport=transport, request=request)

        assert result.is_empty
        assert result.total_count == 0
        assert len(result.candidates) == 0
        assert result.next_steps

    def test_search_error_response(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = self._mock_transport(
            data={"error_class": "server_rejection", "reason": "Bad query"},
            status_code=400,
        )

        request = CapabilitySearchRequest(query="bad-query")
        result = submit_capability_search(transport=transport, request=request)

        assert result.is_empty
        assert result.error_class == "server_rejection"
        assert result.http_status == 400

    def test_search_transport_exception(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("No route to host")

        request = CapabilitySearchRequest(query="auth")
        result = submit_capability_search(transport=transport, request=request)

        assert result.is_empty
        assert result.error_class == "ConnectionError"
        assert "No route to host" in result.reason
        assert result.next_steps

    def test_search_uses_correct_endpoint(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = self._mock_transport(data={"candidates": []})
        request = CapabilitySearchRequest(query="auth")
        submit_capability_search(transport=transport, request=request)

        transport.execute.assert_called_once()
        call_args = transport.execute.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/mcp/v1/capabilities/search"
        assert call_args[1]["operation_name"] == "capability.search"

    def test_search_parses_results_key(self):
        """section11: Also accept 'results' instead of 'candidates'."""
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = self._mock_transport(data={
            "results": [
                {"name": "auth.oidc", "provider": "keycloak"},
            ],
            "total": 1,
        })

        request = CapabilitySearchRequest(query="auth")
        result = submit_capability_search(transport=transport, request=request)

        assert not result.is_empty
        assert result.candidates[0].capability == "auth.oidc"
        assert result.total_count == 1


# --------------------------------------------------------------
# 3. Resolver
# --------------------------------------------------------------


class TestResolver:
    """SDK-CLIENT-08 section8.2, section8.3, section12, section16 - Resolver."""

    def _mock_transport(self, *, data: Dict[str, Any], status_code: int = 200):
        transport = MagicMock()
        result = MagicMock()
        result.data = data
        result.status_code = status_code
        transport.execute.return_value = result
        return transport

    def test_resolved(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={
            "status": "resolved",
            "resolved": {
                "capability": "auth.oidc",
                "provider": "keycloak",
                "version": "22.0",
                "digest": "sha256:abc",
                "selection_reason": "Only matching provider.",
            },
        })

        request = ResolutionRequest(capability="auth.oidc", correlation_id="c-001")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.is_resolved
        assert outcome.resolved is not None
        assert outcome.resolved.capability == "auth.oidc"
        assert outcome.resolved.provider == "keycloak"
        assert outcome.resolved.version == "22.0"

    def test_ambiguous_fail_closed(self):
        """section8.3: Ambiguous -> fail-closed with repair guidance."""
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={
            "status": "ambiguous",
            "candidates": [
                {"capability": "auth.oidc", "provider": "keycloak"},
                {"capability": "auth.oidc", "provider": "auth0"},
            ],
        })

        request = ResolutionRequest(capability="auth.oidc")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.is_ambiguous
        assert not outcome.is_resolved
        assert len(outcome.candidates) == 2
        assert outcome.repair_guidance
        assert any("--provider" in g for g in outcome.repair_guidance)

    def test_incompatible(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={
            "status": "incompatible",
            "reason": "No provider meets version constraint.",
            "candidates": [],
        })

        request = ResolutionRequest(capability="auth.oidc", version="99.0")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.status == "incompatible"
        assert not outcome.is_resolved
        assert outcome.reason

    def test_not_found(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={
            "status": "not_found",
            "reason": "Capability 'nonexistent' not in registry.",
        })

        request = ResolutionRequest(capability="nonexistent")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.status == "not_found"
        assert not outcome.is_resolved
        assert outcome.repair_guidance

    def test_accepted_async(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(
            data={"status": "accepted"},
            status_code=202,
        )

        request = ResolutionRequest(capability="auth.oidc")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.status == "accepted"
        assert not outcome.is_resolved

    def test_deferred(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={"status": "deferred"})

        request = ResolutionRequest(capability="auth.oidc")
        outcome = submit_resolution(transport=transport, request=request)

        assert outcome.status == "deferred"

    def test_server_error(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(
            data={"error_class": "InternalServerError", "reason": "Timeout"},
            status_code=500,
        )

        request = ResolutionRequest(capability="auth.oidc")
        outcome = submit_resolution(transport=transport, request=request)

        assert not outcome.is_resolved
        assert outcome.http_status == 500

    def test_transport_exception(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("unreachable")

        request = ResolutionRequest(capability="auth.oidc")
        outcome = submit_resolution(transport=transport, request=request)

        assert not outcome.is_resolved
        assert outcome.error_class == "ConnectionError"

    def test_uses_correct_endpoint(self):
        from keyhole_sdk.capability.models import ResolutionRequest
        from keyhole_sdk.capability.resolver import submit_resolution

        transport = self._mock_transport(data={
            "status": "resolved",
            "resolved": {"capability": "a", "provider": "b"},
        })
        request = ResolutionRequest(capability="a")
        submit_resolution(transport=transport, request=request)

        transport.execute.assert_called_once()
        call_args = transport.execute.call_args
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/mcp/v1/capabilities/resolve"
        assert call_args[1]["operation_name"] == "capability.resolve"


# --------------------------------------------------------------
# 4. Materializer
# --------------------------------------------------------------


class TestMaterializer:
    """SDK-CLIENT-08 section13, section14 - Materializer."""

    def _resolved_outcome(self):
        from keyhole_sdk.capability.models import (
            ResolutionOutcome,
            ResolvedDependency,
        )

        return ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
                version="22.0",
                digest="sha256:abc",
            ),
            correlation_id="c-mat-001",
        )

    def test_advisory_mode_emits_artifact(self, tmp_path):
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
        )

        outcome = self._resolved_outcome()
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.ADVISORY,
        )

        assert result.success
        assert not result.is_write
        assert result.target
        target = Path(result.target)
        assert target.is_file()
        content = json.loads(target.read_text())
        assert content["capability"] == "auth.oidc"
        assert content["advisory"] is True

    def test_write_native_creates_deps(self, tmp_path):
        """section13.1: Native repo + --write -> creates dependencies.yaml."""
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
        )

        outcome = self._resolved_outcome()
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert result.success
        assert result.is_write
        dep_file = tmp_path / "dependencies.yaml"
        assert dep_file.is_file()
        content = dep_file.read_text()
        assert "auth.oidc" in content
        assert "keycloak" in content

    def test_write_native_detects_duplicate(self, tmp_path):
        """section13.1: Duplicate detection - no double-write."""
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
        )

        # Pre-populate
        dep_file = tmp_path / "dependencies.yaml"
        dep_file.write_text(
            "- capability: auth.oidc\n  provider: keycloak\n  version: 22.0\n"
        )

        outcome = self._resolved_outcome()
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert result.success
        assert not result.is_write  # No mutation on duplicate

    def test_foreign_repo_write_rejected(self, tmp_path):
        """section14.2: Foreign repo -> write is not lawful."""
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
        )

        outcome = self._resolved_outcome()
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.FOREIGN,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert not result.success
        assert result.error_class == "UnsupportedWriteTarget"
        assert result.repair_guidance

    def test_ingestion_backed_write_rejected(self, tmp_path):
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
        )

        outcome = self._resolved_outcome()
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.INGESTION_BACKED,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert not result.success
        assert result.error_class == "UnsupportedWriteTarget"

    def test_unresolved_outcome_rejected(self, tmp_path):
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
            ResolutionOutcome,
        )

        outcome = ResolutionOutcome(status="ambiguous")
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.ADVISORY,
        )

        assert not result.success
        assert result.error_class == "UnresolvedOutcome"

    def test_write_native_appends_to_existing(self, tmp_path):
        """section13.1: Append, not overwrite."""
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
            ResolutionOutcome,
            ResolvedDependency,
        )

        dep_file = tmp_path / "dependencies.yaml"
        dep_file.write_text(
            "- capability: logging.structured\n  provider: structlog\n"
        )

        outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
                version="22.0",
            ),
            correlation_id="c-002",
        )
        result = materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert result.success
        assert result.is_write
        content = dep_file.read_text()
        assert "logging.structured" in content  # Original preserved
        assert "auth.oidc" in content  # New appended

    def test_materialization_result_to_dict(self):
        from keyhole_sdk.capability.materializer import MaterializationResult

        r = MaterializationResult(
            success=True,
            target="/path/to/file",
            diff_summary="Added auth.oidc",
            is_write=True,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert d["target"] == "/path/to/file"
        assert d["is_write"] is True


# --------------------------------------------------------------
# 5. Proof Emission
# --------------------------------------------------------------


class TestProof:
    """SDK-CLIENT-08 section19 - Proof artifacts."""

    def test_search_proof_emitted(self, tmp_path):
        from keyhole_sdk.capability.proof import emit_search_proof

        proof_dir = emit_search_proof(
            state_dir=tmp_path,
            correlation_id="c-search-001",
            request_dict={"query": "auth"},
            result_dict={"total_count": 2, "is_empty": False},
        )

        assert proof_dir.is_dir()
        assert (proof_dir / "request.json").is_file()
        assert (proof_dir / "response.json").is_file()
        assert (proof_dir / "correlation.json").is_file()

        corr = json.loads((proof_dir / "correlation.json").read_text())
        assert corr["operation"] == "capability.search"
        assert corr["correlation_id"] == "c-search-001"

    def test_resolution_proof_emitted(self, tmp_path):
        from keyhole_sdk.capability.proof import emit_resolution_proof

        proof_dir = emit_resolution_proof(
            state_dir=tmp_path,
            correlation_id="c-resolve-001",
            request_dict={"capability": "auth.oidc"},
            outcome_dict={
                "status": "resolved",
                "resolved": {"capability": "auth.oidc", "provider": "keycloak"},
            },
            repo_posture="native",
            mode="advisory",
        )

        assert proof_dir.is_dir()
        assert (proof_dir / "request.json").is_file()
        assert (proof_dir / "response.json").is_file()
        assert (proof_dir / "correlation.json").is_file()
        assert (proof_dir / "summary.md").is_file()
        assert (proof_dir / "digest.txt").is_file()
        assert (proof_dir / "suggested-dependency.json").is_file()

        corr = json.loads((proof_dir / "correlation.json").read_text())
        assert corr["operation"] == "capability.resolve"
        assert corr["repo_posture"] == "native"
        assert corr["mode"] == "advisory"

    def test_resolution_proof_with_materialization(self, tmp_path):
        from keyhole_sdk.capability.proof import emit_resolution_proof

        proof_dir = emit_resolution_proof(
            state_dir=tmp_path,
            correlation_id="c-resolve-002",
            request_dict={"capability": "auth.oidc"},
            outcome_dict={"status": "resolved", "resolved": {"capability": "auth.oidc", "provider": "keycloak"}},
            materialization_dict={"success": True, "target": "/deps.yaml", "is_write": True},
        )

        assert (proof_dir / "diff.json").is_file()
        diff = json.loads((proof_dir / "diff.json").read_text())
        assert diff["is_write"] is True

    def test_search_proof_directory_structure(self, tmp_path):
        from keyhole_sdk.capability.proof import emit_search_proof

        proof_dir = emit_search_proof(
            state_dir=tmp_path,
            correlation_id="c-search-002",
            request_dict={},
            result_dict={},
        )

        # Must be under search/ subdirectory
        assert "search" in str(proof_dir)

    def test_resolution_proof_directory_structure(self, tmp_path):
        from keyhole_sdk.capability.proof import emit_resolution_proof

        proof_dir = emit_resolution_proof(
            state_dir=tmp_path,
            correlation_id="c-resolve-003",
            request_dict={},
            outcome_dict={"status": "not_found"},
        )

        # Must be under resolution/ subdirectory
        assert "resolution" in str(proof_dir)


# --------------------------------------------------------------
# 6. Repair Guidance
# --------------------------------------------------------------


class TestRepair:
    """SDK-CLIENT-08 section18 - Repair guidance."""

    def test_all_known_error_classes(self):
        from keyhole_sdk.capability.repair import map_capability_repair

        known_classes = [
            "AuthenticationError",
            "NotAuthenticated",
            "TransportUnknownError",
            "RetryExhaustedError",
            "RuntimeUnavailableError",
            "ConnectionError",
            "RateLimitedError",
            "IdempotencyConflictError",
            "AmbiguousResolution",
            "IncompatibleProviderSet",
            "CapabilityNotFound",
            "InvalidLocalDependencyState",
            "UnsupportedWriteTarget",
            "ServerRejection",
            "RegistryUnreachable",
        ]

        for cls in known_classes:
            guidance = map_capability_repair(cls)
            assert isinstance(guidance, list)
            assert len(guidance) > 0, f"No guidance for {cls}"
            # Verify it's a copy
            guidance.append("extra")
            assert "extra" not in map_capability_repair(cls)

    def test_unknown_error_class_fallback(self):
        from keyhole_sdk.capability.repair import map_capability_repair

        guidance = map_capability_repair("NeverHeardOfThis")
        assert isinstance(guidance, list)
        assert len(guidance) > 0
        assert "NeverHeardOfThis" in guidance[0]

    def test_auth_errors_suggest_login(self):
        from keyhole_sdk.capability.repair import map_capability_repair

        for cls in ("AuthenticationError", "NotAuthenticated"):
            guidance = map_capability_repair(cls)
            assert any("login" in g.lower() for g in guidance)

    def test_ambiguous_suggests_provider(self):
        from keyhole_sdk.capability.repair import map_capability_repair

        guidance = map_capability_repair("AmbiguousResolution")
        assert any("--provider" in g for g in guidance)


# --------------------------------------------------------------
# 7. CLI Search Command
# --------------------------------------------------------------


class TestCLISearch:
    """SDK-CLIENT-08 - CLI search command."""

    def test_unauthenticated(self):
        from keyhole_cli.commands.search_cmd import run_search

        with patch(
            "keyhole_cli.commands.search_cmd.CredentialStore"
        ) as MockStore:
            MockStore.return_value.load.return_value = None
            result = run_search(query="auth", keyhole_home="/tmp/fake")

        assert not result.success
        assert result.data.get("error_class") == "NotAuthenticated"
        assert result.next_steps

    def test_search_success(self):
        from keyhole_cli.commands.search_cmd import run_search

        mock_session = MagicMock()
        mock_session.access_token = "tok-123"
        mock_session.token_fingerprint = "fp-123"

        from keyhole_sdk.capability.models import (
            CapabilityCandidate,
            CapabilitySearchResult,
        )

        mock_result = CapabilitySearchResult(
            query="auth",
            candidates=[
                CapabilityCandidate(
                    capability="auth.oidc",
                    provider="keycloak",
                    version="22.0",
                )
            ],
            total_count=1,
            correlation_id="c-001",
            http_status=200,
        )

        with patch(
            "keyhole_cli.commands.search_cmd.CredentialStore"
        ) as MockStore, patch(
            "keyhole_cli.commands.search_cmd.submit_capability_search",
            return_value=mock_result,
        ), patch(
            "keyhole_cli.commands.search_cmd.GovernedTransport"
        ):
            MockStore.return_value.load.return_value = mock_session
            result = run_search(
                query="auth",
                keyhole_home="/tmp/fake",
            )

        assert result.success
        assert result.data["total_count"] == 1
        assert result.data["candidates"][0]["capability"] == "auth.oidc"
        assert "keyhole dependency resolve" in str(result.next_steps)

    def test_search_error(self):
        from keyhole_cli.commands.search_cmd import run_search
        from keyhole_sdk.capability.models import CapabilitySearchResult

        mock_session = MagicMock()
        mock_session.access_token = "tok-123"
        mock_session.token_fingerprint = "fp-123"

        mock_result = CapabilitySearchResult(
            query="auth",
            error_class="RegistryUnreachable",
            reason="timeout",
            is_empty=True,
        )

        with patch(
            "keyhole_cli.commands.search_cmd.CredentialStore"
        ) as MockStore, patch(
            "keyhole_cli.commands.search_cmd.submit_capability_search",
            return_value=mock_result,
        ), patch(
            "keyhole_cli.commands.search_cmd.GovernedTransport"
        ):
            MockStore.return_value.load.return_value = mock_session
            result = run_search(
                query="auth",
                keyhole_home="/tmp/fake",
            )

        assert not result.success
        assert result.data.get("error_class") == "RegistryUnreachable"


# --------------------------------------------------------------
# 8. CLI Dependency Resolve Command
# --------------------------------------------------------------


class TestCLIDependencyResolve:
    """SDK-CLIENT-08 - CLI dependency resolve command."""

    def test_unauthenticated(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import (
            run_dependency_resolve,
        )

        with patch(
            "keyhole_cli.commands.dependency_resolve_cmd.CredentialStore"
        ) as MockStore:
            MockStore.return_value.load.return_value = None
            result = run_dependency_resolve(
                capability="auth.oidc",
                repo_path=str(tmp_path),
                keyhole_home="/tmp/fake",
            )

        assert not result.success
        assert result.data.get("error_class") == "NotAuthenticated"

    def test_invalid_path(self):
        from keyhole_cli.commands.dependency_resolve_cmd import (
            run_dependency_resolve,
        )

        with patch(
            "keyhole_cli.commands.dependency_resolve_cmd.CredentialStore"
        ) as MockStore:
            mock_session = MagicMock()
            mock_session.access_token = "tok"
            mock_session.token_fingerprint = "fp"
            MockStore.return_value.load.return_value = mock_session
            result = run_dependency_resolve(
                capability="auth.oidc",
                repo_path="/nonexistent/repo",
                keyhole_home="/tmp/fake",
            )

        assert not result.success
        assert "InvalidRepoPath" in result.data.get("error_class", "")

    def test_resolved_advisory(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import (
            run_dependency_resolve,
        )
        from keyhole_sdk.capability.models import (
            ResolutionOutcome,
            ResolvedDependency,
        )

        mock_session = MagicMock()
        mock_session.access_token = "tok-123"
        mock_session.token_fingerprint = "fp-123"

        mock_outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
                version="22.0",
            ),
            correlation_id="c-001",
        )

        with patch(
            "keyhole_cli.commands.dependency_resolve_cmd.CredentialStore"
        ) as MockStore, patch(
            "keyhole_cli.commands.dependency_resolve_cmd.submit_resolution",
            return_value=mock_outcome,
        ), patch(
            "keyhole_cli.commands.dependency_resolve_cmd.GovernedTransport"
        ):
            MockStore.return_value.load.return_value = mock_session
            result = run_dependency_resolve(
                capability="auth.oidc",
                repo_path=str(tmp_path),
                keyhole_home=str(tmp_path / "home"),
            )

        assert result.success
        assert result.data["status"] == "resolved"
        assert result.data["resolved"]["capability"] == "auth.oidc"
        assert result.data["mode"] == "advisory"

    def test_ambiguous_not_success(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import (
            run_dependency_resolve,
        )
        from keyhole_sdk.capability.models import (
            CapabilityCandidate,
            ResolutionOutcome,
        )

        mock_session = MagicMock()
        mock_session.access_token = "tok-123"
        mock_session.token_fingerprint = "fp-123"

        mock_outcome = ResolutionOutcome(
            status="ambiguous",
            candidates=[
                CapabilityCandidate(capability="auth.oidc", provider="keycloak"),
                CapabilityCandidate(capability="auth.oidc", provider="auth0"),
            ],
            repair_guidance=["Specify --provider to pin."],
            correlation_id="c-002",
        )

        with patch(
            "keyhole_cli.commands.dependency_resolve_cmd.CredentialStore"
        ) as MockStore, patch(
            "keyhole_cli.commands.dependency_resolve_cmd.submit_resolution",
            return_value=mock_outcome,
        ), patch(
            "keyhole_cli.commands.dependency_resolve_cmd.GovernedTransport"
        ):
            MockStore.return_value.load.return_value = mock_session
            result = run_dependency_resolve(
                capability="auth.oidc",
                repo_path=str(tmp_path),
                keyhole_home=str(tmp_path / "home"),
            )

        assert not result.success
        assert result.data["status"] == "ambiguous"
        assert "Ambiguous" in result.summary

    def test_posture_detection_native(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import _detect_repo_posture
        from keyhole_sdk.capability.models import RepoPosture

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        assert _detect_repo_posture(tmp_path) == RepoPosture.NATIVE

    def test_posture_detection_ingestion(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import _detect_repo_posture
        from keyhole_sdk.capability.models import RepoPosture

        kh_dir = tmp_path / ".keyhole"
        kh_dir.mkdir()
        (kh_dir / "ingestion.json").write_text("{}")
        assert _detect_repo_posture(tmp_path) == RepoPosture.INGESTION_BACKED

    def test_posture_detection_foreign(self, tmp_path):
        from keyhole_cli.commands.dependency_resolve_cmd import _detect_repo_posture
        from keyhole_sdk.capability.models import RepoPosture

        assert _detect_repo_posture(tmp_path) == RepoPosture.FOREIGN


# --------------------------------------------------------------
# 9. Operation Registry
# --------------------------------------------------------------


class TestOperationRegistry:
    """SDK-CLIENT-08 - Operation registry entries."""

    def test_capability_search_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation

        op = get_operation("capability.search")
        assert op is not None
        assert op.name == "capability.search"
        assert op.operation_class.value == "READ_ONLY"
        assert not op.idempotency_required

    def test_capability_resolve_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation

        op = get_operation("capability.resolve")
        assert op is not None
        assert op.name == "capability.resolve"
        assert op.operation_class.value == "WRITE_IDEMPOTENT_REQUIRED"
        assert op.idempotency_required
        assert op.proof_required


# --------------------------------------------------------------
# 10. Public API Surface
# --------------------------------------------------------------


class TestPublicAPISurface:
    """SDK-CLIENT-08 - All symbols exported from keyhole_sdk."""

    EXPECTED_EXPORTS = [
        "CapabilityCandidate",
        "CapabilitySearchRequest",
        "CapabilitySearchResult",
        "MaterializationMode",
        "RepoPosture",
        "ResolutionOutcome",
        "ResolutionRequest",
        "ResolvedDependency",
        "submit_capability_search",
        "submit_resolution",
        "materialize_resolution",
        "emit_search_proof",
        "emit_resolution_proof",
        "map_capability_repair",
    ]

    def test_all_exports_present(self):
        import keyhole_sdk

        for name in self.EXPECTED_EXPORTS:
            assert hasattr(keyhole_sdk, name), f"Missing export: {name}"

    def test_all_exports_in__all__(self):
        import keyhole_sdk

        for name in self.EXPECTED_EXPORTS:
            assert name in keyhole_sdk.__all__, f"Not in __all__: {name}"


# --------------------------------------------------------------
# 11. Determinism Guarantees
# --------------------------------------------------------------


class TestDeterminism:
    """SDK-CLIENT-08 section16 - Deterministic behavior."""

    def test_search_payload_deterministic(self):
        from keyhole_sdk.capability.models import CapabilitySearchRequest

        req1 = CapabilitySearchRequest(
            query="auth",
            provider="keycloak",
            correlation_id="c-001",
            timestamp="2025-01-01T00:00:00Z",
        )
        req2 = CapabilitySearchRequest(
            query="auth",
            provider="keycloak",
            correlation_id="c-001",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert req1.to_payload() == req2.to_payload()

    def test_resolution_payload_deterministic(self):
        from keyhole_sdk.capability.models import ResolutionRequest

        req1 = ResolutionRequest(
            capability="auth",
            provider="keycloak",
            correlation_id="c-001",
            timestamp="2025-01-01T00:00:00Z",
        )
        req2 = ResolutionRequest(
            capability="auth",
            provider="keycloak",
            correlation_id="c-001",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert req1.to_payload() == req2.to_payload()

    def test_digest_computation_deterministic(self):
        from keyhole_sdk.capability.models import compute_resolution_digest

        d1 = compute_resolution_digest("a", "b", "1.0")
        d2 = compute_resolution_digest("a", "b", "1.0")
        assert d1 == d2


# --------------------------------------------------------------
# 12. No-Silent-Mutation Invariant
# --------------------------------------------------------------


class TestNoSilentMutation:
    """SDK-CLIENT-08 section13.3 - No silent repo mutation."""

    def test_advisory_mode_never_writes_repo(self, tmp_path):
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
            ResolutionOutcome,
            ResolvedDependency,
        )

        outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
            ),
            correlation_id="c-001",
        )

        before_files = set(tmp_path.iterdir())

        materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.NATIVE,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.ADVISORY,
        )

        after_files = set(tmp_path.iterdir())
        # Only the state dir should have appeared in tmp_path, not a dependencies.yaml
        new_in_repo = after_files - before_files
        # state/ might appear, but dependencies.yaml must not
        for f in new_in_repo:
            assert f.name != "dependencies.yaml", "Advisory mode must not create dependencies.yaml"

    def test_foreign_write_never_creates_deps(self, tmp_path):
        from keyhole_sdk.capability.materializer import materialize_resolution
        from keyhole_sdk.capability.models import (
            MaterializationMode,
            RepoPosture,
            ResolutionOutcome,
            ResolvedDependency,
        )

        outcome = ResolutionOutcome(
            status="resolved",
            resolved=ResolvedDependency(
                capability="auth.oidc",
                provider="keycloak",
            ),
            correlation_id="c-001",
        )

        materialize_resolution(
            outcome=outcome,
            repo_path=tmp_path,
            repo_posture=RepoPosture.FOREIGN,
            state_dir=tmp_path / "state",
            mode=MaterializationMode.WRITE,
        )

        assert not (tmp_path / "dependencies.yaml").exists()

    def test_search_never_writes_to_repo(self, tmp_path):
        """Search is read-only - it must never create files in the repo."""
        from keyhole_sdk.capability.models import CapabilitySearchRequest
        from keyhole_sdk.capability.search import submit_capability_search

        transport = MagicMock()
        result = MagicMock()
        result.data = {"candidates": []}
        result.status_code = 200
        transport.execute.return_value = result

        before = set(tmp_path.iterdir())

        submit_capability_search(
            transport=transport,
            request=CapabilitySearchRequest(query="auth"),
        )

        after = set(tmp_path.iterdir())
        assert before == after, "Search must not mutate the filesystem"


# --------------------------------------------------------------
# 13. CLI Wiring
# --------------------------------------------------------------


class TestCLIWiring:
    """SDK-CLIENT-08 - CLI commands wired correctly."""

    def test_search_command_exists(self):
        from keyhole_cli.cli import app

        command_names = [cmd.name for cmd in app.registered_commands]
        assert "search" in command_names

    def test_dependency_app_exists(self):
        from keyhole_cli.cli import dependency_app

        command_names = [cmd.name for cmd in dependency_app.registered_commands]
        assert "resolve" in command_names

    def test_dependency_app_added_to_main(self):
        from keyhole_cli.cli import app

        group_names = [g.name for g in app.registered_groups]
        assert "dependency" in group_names
