"""Tests for SDK-CLIENT-07 - Repository Registration with MCP.

Covers:
  - Models (enums, serialization, proof dicts)
  - Readiness assessment (native, ingestion, not_ready)
  - Artifacts loading and snapshotting
  - Payload construction (determinism, both sources)
  - Submitter (success, replayed, accepted, deferred, rejected, transport error)
  - Proof emission (file structure, content)
  - Repair guidance (all mapped error classes)
  - CLI command (path validation, auth, blockers, success)
  - Identity binding extraction
  - Operation registry (repo.register)
  - Public API surface
  - No-silent-mutation guarantee
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
    """SDK-CLIENT-07 section6, section9, section10, section11 - Model basics."""

    def test_registration_source_values(self):
        from keyhole_sdk.registration.models import RegistrationSource

        assert RegistrationSource.NATIVE == "native"
        assert RegistrationSource.INGESTION == "ingestion"

    def test_registration_readiness_values(self):
        from keyhole_sdk.registration.models import RegistrationReadiness

        assert RegistrationReadiness.NATIVE_READY == "native_ready"
        assert RegistrationReadiness.INGESTION_READY == "ingestion_ready"
        assert RegistrationReadiness.PARTIALLY_READY == "partially_ready"
        assert RegistrationReadiness.NOT_READY == "not_ready"

    def test_native_artifacts_empty(self):
        from keyhole_sdk.registration.models import NativeArtifacts

        arts = NativeArtifacts()
        assert not arts.has_keyhole
        assert not arts.has_governance_contract
        assert not arts.has_capability_passport
        assert arts.artifact_count == 0

    def test_native_artifacts_with_data(self):
        from keyhole_sdk.registration.models import NativeArtifacts

        arts = NativeArtifacts(
            keyhole={"name": "test"},
            governance_contract={"version": "1"},
            capability_passport={"caps": []},
        )
        assert arts.has_keyhole
        assert arts.has_governance_contract
        assert arts.has_capability_passport
        assert arts.artifact_count == 3

    def test_native_artifacts_snapshot(self):
        from keyhole_sdk.registration.models import NativeArtifacts

        arts = NativeArtifacts(keyhole={"name": "test"})
        snap = arts.to_snapshot()
        assert snap["keyhole"] == {"name": "test"}
        assert snap["governance_contract"] is None
        assert snap["artifact_count"] == 1

    def test_ingestion_reference_snapshot(self):
        from keyhole_sdk.registration.models import IngestionReference

        ref = IngestionReference(
            ingest_id="ing_001",
            compatibility_posture="partially_aligned",
            repo_identity="my-repo",
        )
        snap = ref.to_snapshot()
        assert snap["ingest_id"] == "ing_001"
        assert snap["compatibility_posture"] == "partially_aligned"

    def test_registration_payload_to_payload(self):
        from keyhole_sdk.registration.models import (
            RegistrationPayload,
            RegistrationReadiness,
            RegistrationSource,
        )

        payload = RegistrationPayload(
            repo_name="workorder-platform",
            path_digest="sha256:abc",
            repo_digest="sha256:def",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            correlation_id="corr-001",
        )
        wire = payload.to_payload()
        assert wire["repo"]["name"] == "workorder-platform"
        assert wire["repo"]["registration_source"] == "native"
        assert wire["preflight"]["readiness"] == "native_ready"
        assert wire["correlation_id"] == "corr-001"

    def test_registration_payload_proof_dict_no_local_path(self):
        from keyhole_sdk.registration.models import (
            RegistrationPayload,
            RegistrationReadiness,
            RegistrationSource,
        )

        payload = RegistrationPayload(
            repo_name="test",
            registration_source=RegistrationSource.INGESTION,
            readiness=RegistrationReadiness.INGESTION_READY,
        )
        proof = payload.to_proof_dict()
        assert "local_path" not in proof
        assert proof["registration_source"] == "ingestion"

    def test_registration_request_to_payload(self):
        from keyhole_sdk.registration.models import (
            RegistrationPayload,
            RegistrationReadiness,
            RegistrationRequest,
            RegistrationSource,
        )

        payload = RegistrationPayload(
            repo_name="test",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
        )
        req = RegistrationRequest(payload=payload, identity_fingerprint="fp-123")
        wire = req.to_payload()
        assert "registration" in wire
        assert wire["identity_fingerprint"] == "fp-123"

    def test_registration_request_proof_dict(self):
        from keyhole_sdk.registration.models import (
            RegistrationPayload,
            RegistrationReadiness,
            RegistrationRequest,
            RegistrationSource,
        )

        payload = RegistrationPayload(
            repo_name="test",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
        )
        req = RegistrationRequest(payload=payload)
        proof = req.to_proof_dict()
        assert "payload_summary" in proof
        assert proof["payload_summary"]["repo_name"] == "test"

    def test_identity_binding_to_dict(self):
        from keyhole_sdk.registration.models import IdentityBinding

        binding = IdentityBinding(
            tenant_id="t-123",
            org_id="o-456",
            repo_id="r-789",
        )
        d = binding.to_dict()
        assert d["tenant_id"] == "t-123"
        assert d["org_id"] == "o-456"
        assert d["repo_id"] == "r-789"
        # Empty fields should be omitted
        assert "worker_id" not in d

    def test_identity_binding_empty(self):
        from keyhole_sdk.registration.models import IdentityBinding

        binding = IdentityBinding()
        d = binding.to_dict()
        assert d == {}

    def test_registration_outcome_proof_dict(self):
        from keyhole_sdk.registration.models import (
            IdentityBinding,
            RegistrationOutcome,
            RegistrationSource,
        )

        outcome = RegistrationOutcome(
            status="success",
            registration_id="reg-001",
            repo_name="my-repo",
            registration_source=RegistrationSource.INGESTION,
            identity_binding=IdentityBinding(tenant_id="t-1", repo_id="r-1"),
        )
        proof = outcome.to_proof_dict()
        assert proof["status"] == "success"
        assert proof["registration_id"] == "reg-001"
        assert proof["identity_binding"]["tenant_id"] == "t-1"

    def test_compute_path_digest_deterministic(self):
        from keyhole_sdk.registration.models import compute_path_digest

        d1 = compute_path_digest("/home/user/repo")
        d2 = compute_path_digest("/home/user/repo")
        assert d1 == d2
        assert d1.startswith("sha256:")

    def test_compute_repo_digest_deterministic(self):
        from keyhole_sdk.registration.models import compute_repo_digest

        d1 = compute_repo_digest("my-repo", "native", "extra")
        d2 = compute_repo_digest("my-repo", "native", "extra")
        assert d1 == d2
        assert d1.startswith("sha256:")

    def test_compute_repo_digest_different_inputs(self):
        from keyhole_sdk.registration.models import compute_repo_digest

        d1 = compute_repo_digest("repo-a", "native", "")
        d2 = compute_repo_digest("repo-b", "native", "")
        assert d1 != d2


# --------------------------------------------------------------
# 2. Readiness Assessment
# --------------------------------------------------------------


class TestReadiness:
    """SDK-CLIENT-07 section8, section9 - Registration readiness preflight."""

    def test_not_ready_no_auth(self, tmp_path: Path):
        from keyhole_sdk.registration.readiness import assess_readiness

        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=False,
        )
        assert check.readiness.value == "not_ready"
        assert not check.can_proceed
        assert any("login" in b.lower() for b in check.blockers)

    def test_not_ready_bad_path(self, tmp_path: Path):
        from keyhole_sdk.registration.readiness import assess_readiness

        bad_path = tmp_path / "nonexistent"
        check = assess_readiness(
            repo_path=bad_path,
            has_auth=True,
        )
        assert not check.can_proceed
        assert any("does not exist" in b for b in check.blockers)

    def test_not_ready_no_artifacts_no_ingest(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.readiness import assess_readiness

        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            native_artifacts=NativeArtifacts(),
        )
        assert check.readiness.value == "not_ready"
        assert not check.can_proceed
        assert any("ingest" in b.lower() for b in check.blockers)

    def test_native_ready_full_artifacts(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(
            keyhole={"name": "test"},
            governance_contract={"v": "1"},
            capability_passport={"caps": []},
            dependencies={"deps": {}},
        )
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            native_artifacts=arts,
        )
        assert check.readiness.value == "native_ready"
        assert check.source.value == "native"
        assert check.can_proceed

    def test_partially_ready_minimal_native(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(keyhole={"name": "test"})
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            native_artifacts=arts,
        )
        assert check.readiness.value == "partially_ready"
        assert check.source.value == "native"
        assert check.can_proceed
        # Warnings about missing artifacts
        assert len(check.warnings) > 0

    def test_ingestion_ready_with_ref(self, tmp_path: Path):
        from keyhole_sdk.registration.models import IngestionReference
        from keyhole_sdk.registration.readiness import assess_readiness

        ref = IngestionReference(
            ingest_id="ing_001",
            compatibility_posture="partially_aligned",
        )
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            ingestion_ref=ref,
        )
        assert check.readiness.value == "ingestion_ready"
        assert check.source.value == "ingestion"
        assert check.can_proceed

    def test_ingestion_ready_from_ingest_only(self, tmp_path: Path):
        from keyhole_sdk.registration.readiness import assess_readiness

        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            from_ingest="ing_002",
        )
        # from_ingest set but no ref object - still has a ref intent
        assert check.source.value == "ingestion"
        # Should be ingestion_ready since from_ingest is truthy
        assert check.readiness.value == "ingestion_ready"

    def test_ingestion_foreign_posture_warns(self, tmp_path: Path):
        from keyhole_sdk.registration.models import IngestionReference
        from keyhole_sdk.registration.readiness import assess_readiness

        ref = IngestionReference(
            ingest_id="ing_003",
            compatibility_posture="foreign",
        )
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            ingestion_ref=ref,
        )
        assert check.can_proceed
        assert any("foreign" in w.lower() for w in check.warnings)

    def test_preflight_status_pass_fail(self, tmp_path: Path):
        from keyhole_sdk.registration.readiness import assess_readiness

        passing = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            from_ingest="ing_004",
        )
        assert passing.preflight_status == "PASS"

        failing = assess_readiness(
            repo_path=tmp_path,
            has_auth=False,
        )
        assert failing.preflight_status == "FAIL"

    def test_readiness_to_dict(self, tmp_path: Path):
        from keyhole_sdk.registration.readiness import assess_readiness

        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            from_ingest="ing_005",
        )
        d = check.to_dict()
        assert "readiness" in d
        assert "source" in d
        assert "preflight_status" in d


# --------------------------------------------------------------
# 3. Artifacts
# --------------------------------------------------------------


class TestArtifacts:
    """SDK-CLIENT-07 section6, section16 - Artifact loading and snapshotting."""

    def test_load_native_artifacts_empty_dir(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_native_artifacts

        arts = load_native_artifacts(tmp_path)
        assert not arts.has_keyhole
        assert arts.artifact_count == 0

    def test_load_native_artifacts_with_keyhole_yaml(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_native_artifacts

        (tmp_path / "keyhole.yaml").write_text("name: my-repo\nversion: 1.0\n")
        arts = load_native_artifacts(tmp_path)
        assert arts.has_keyhole
        assert arts.keyhole is not None

    def test_load_native_artifacts_multiple_files(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_native_artifacts

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("version: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("caps: []\n")
        arts = load_native_artifacts(tmp_path)
        assert arts.artifact_count == 3

    def test_load_ingestion_reference_missing(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_ingestion_reference

        ref = load_ingestion_reference(state_dir=tmp_path, ingest_id="missing_001")
        assert ref is None

    def test_load_ingestion_reference_empty_id(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_ingestion_reference

        ref = load_ingestion_reference(state_dir=tmp_path, ingest_id="")
        assert ref is None

    def test_load_ingestion_reference_with_proof(self, tmp_path: Path):
        from keyhole_sdk.registration.artifacts import load_ingestion_reference

        # Create mock proof directory
        proof_dir = tmp_path / "ingest" / "ing_001"
        proof_dir.mkdir(parents=True)
        (proof_dir / "request.json").write_text(json.dumps({
            "package_summary": {
                "repo_identity": "test-repo",
                "languages": ["python"],
                "frameworks": ["fastapi"],
                "shadow": False,
            },
        }))
        (proof_dir / "response.json").write_text(json.dumps({
            "compatibility": "partially_aligned",
            "ingestion_id": "ing_001",
        }))

        ref = load_ingestion_reference(state_dir=tmp_path, ingest_id="ing_001")
        assert ref is not None
        assert ref.ingest_id == "ing_001"
        assert ref.compatibility_posture == "partially_aligned"
        assert ref.repo_identity == "test-repo"
        assert "python" in ref.languages

    def test_build_artifacts_snapshot_native(self):
        from keyhole_sdk.registration.artifacts import build_artifacts_snapshot
        from keyhole_sdk.registration.models import NativeArtifacts

        arts = NativeArtifacts(keyhole={"name": "test"})
        snap = build_artifacts_snapshot(native_artifacts=arts)
        assert snap["snapshot_type"] == "registration_inputs"
        assert snap["native_artifacts"] is not None
        assert snap["ingestion_reference"] is None

    def test_build_artifacts_snapshot_ingestion(self):
        from keyhole_sdk.registration.artifacts import build_artifacts_snapshot
        from keyhole_sdk.registration.models import IngestionReference

        ref = IngestionReference(ingest_id="ing_001")
        snap = build_artifacts_snapshot(ingestion_ref=ref)
        assert snap["native_artifacts"] is None
        assert snap["ingestion_reference"] is not None

    def test_build_artifacts_snapshot_both(self):
        from keyhole_sdk.registration.artifacts import build_artifacts_snapshot
        from keyhole_sdk.registration.models import IngestionReference, NativeArtifacts

        arts = NativeArtifacts(keyhole={"name": "test"})
        ref = IngestionReference(ingest_id="ing_001")
        snap = build_artifacts_snapshot(native_artifacts=arts, ingestion_ref=ref)
        assert snap["native_artifacts"] is not None
        assert snap["ingestion_reference"] is not None


# --------------------------------------------------------------
# 4. Payload Construction
# --------------------------------------------------------------


class TestPayload:
    """SDK-CLIENT-07 section10, section18 - Deterministic payload construction."""

    def test_native_payload_shape(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.payload import build_registration_payload
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(
            keyhole={"name": "test"},
            governance_contract={"v": "1"},
            capability_passport={"caps": []},
            dependencies={"deps": {}},
        )
        check = assess_readiness(repo_path=tmp_path, has_auth=True, native_artifacts=arts)
        payload = build_registration_payload(
            repo_path=tmp_path,
            readiness_check=check,
            native_artifacts=arts,
            correlation_id="corr-001",
        )
        assert payload.registration_source.value == "native"
        assert payload.native_artifacts is not None
        assert payload.ingestion is None
        assert payload.correlation_id == "corr-001"

    def test_ingestion_payload_shape(self, tmp_path: Path):
        from keyhole_sdk.registration.models import IngestionReference
        from keyhole_sdk.registration.payload import build_registration_payload
        from keyhole_sdk.registration.readiness import assess_readiness

        ref = IngestionReference(
            ingest_id="ing_001",
            compatibility_posture="partially_aligned",
        )
        check = assess_readiness(
            repo_path=tmp_path, has_auth=True, ingestion_ref=ref,
        )
        payload = build_registration_payload(
            repo_path=tmp_path,
            readiness_check=check,
            ingestion_ref=ref,
        )
        assert payload.registration_source.value == "ingestion"
        assert payload.ingestion is not None
        assert payload.native_artifacts is None

    def test_payload_determinism(self, tmp_path: Path):
        """section18: Same repo state + same mode -> same payload shape."""
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.payload import build_registration_payload
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(keyhole={"name": "test"}, governance_contract={"v": "1"},
                               capability_passport={"caps": []})
        check = assess_readiness(repo_path=tmp_path, has_auth=True, native_artifacts=arts)

        p1 = build_registration_payload(
            repo_path=tmp_path, readiness_check=check,
            native_artifacts=arts, correlation_id="c-1",
        )
        p2 = build_registration_payload(
            repo_path=tmp_path, readiness_check=check,
            native_artifacts=arts, correlation_id="c-1",
        )
        # Wire payloads should have same structure (timestamps may differ)
        w1 = p1.to_payload()
        w2 = p2.to_payload()
        assert w1["repo"] == w2["repo"]
        assert w1["preflight"] == w2["preflight"]
        assert w1["native_artifacts"] == w2["native_artifacts"]

    def test_shadow_mode_preserved(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.payload import build_registration_payload
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(
            keyhole={"name": "test"},
            governance_contract={"v": "1"},
            capability_passport={"caps": []},
        )
        check = assess_readiness(repo_path=tmp_path, has_auth=True, native_artifacts=arts)
        payload = build_registration_payload(
            repo_path=tmp_path, readiness_check=check,
            native_artifacts=arts, shadow=True,
        )
        assert payload.shadow is True
        wire = payload.to_payload()
        assert wire["shadow"] is True

    def test_cli_version_present(self, tmp_path: Path):
        from keyhole_sdk.registration.models import NativeArtifacts
        from keyhole_sdk.registration.payload import build_registration_payload
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = NativeArtifacts(
            keyhole={"name": "test"},
            governance_contract={"v": "1"},
            capability_passport={"caps": []},
        )
        check = assess_readiness(repo_path=tmp_path, has_auth=True, native_artifacts=arts)
        payload = build_registration_payload(
            repo_path=tmp_path, readiness_check=check, native_artifacts=arts,
        )
        wire = payload.to_payload()
        assert wire["client"]["cli_version"] != ""


# --------------------------------------------------------------
# 5. Submitter
# --------------------------------------------------------------


class TestSubmitter:
    """SDK-CLIENT-07 section12, section13 - Transport submission and outcome classification."""

    def _make_request(self) -> "RegistrationRequest":
        from keyhole_sdk.registration.models import (
            RegistrationPayload,
            RegistrationReadiness,
            RegistrationRequest,
            RegistrationSource,
        )

        payload = RegistrationPayload(
            repo_name="test-repo",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            correlation_id="corr-001",
        )
        return RegistrationRequest(payload=payload, identity_fingerprint="fp-1")

    @staticmethod
    def _mock_proof():
        from keyhole_sdk.transport.proof_metadata import TransportProofMetadata
        return TransportProofMetadata()

    def test_success_outcome(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=200,
            data={
                "status": "created",
                "registration_id": "reg-001",
                "repo_id": "r-123",
                "tenant_id": "t-1",
                "org_id": "o-1",
            },
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "success"
        assert outcome.registration_id == "reg-001"
        assert outcome.identity_binding is not None
        assert outcome.identity_binding.tenant_id == "t-1"

    def test_replayed_outcome(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=200,
            data={
                "status": "created",
                "registration_id": "reg-001",
                "is_replay": True,
                "tenant_id": "t-1",
            },
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "replayed"
        assert outcome.is_replay is True

    def test_accepted_outcome(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=202,
            data={"status": "accepted", "registration_id": "reg-002"},
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "accepted"

    def test_deferred_outcome(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=200,
            data={"status": "deferred", "registration_id": "reg-003"},
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "deferred"

    def test_rejected_outcome(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=400,
            data={
                "status": "rejected",
                "reason": "missing governance contract",
                "error_class": "invalid_repo",
            },
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "rejected"
        assert outcome.reason == "missing governance contract"
        assert outcome.error_class == "invalid_repo"

    def test_transport_exception(self):
        from keyhole_sdk.registration.submitter import submit_registration

        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("timeout")

        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.status == "failed"
        assert outcome.is_local_failure is True
        assert outcome.error_class == "ConnectionError"
        assert len(outcome.repair_guidance) > 0

    def test_identity_binding_from_nested_object(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=200,
            data={
                "status": "created",
                "identity_binding": {
                    "tenant_id": "t-x",
                    "org_id": "o-x",
                    "cohort_id": "c-x",
                    "worker_id": "w-x",
                    "repo_id": "r-x",
                },
            },
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.identity_binding is not None
        assert outcome.identity_binding.tenant_id == "t-x"
        assert outcome.identity_binding.worker_id == "w-x"

    def test_no_identity_binding_when_empty(self):
        from keyhole_sdk.registration.submitter import submit_registration
        from keyhole_sdk.transport.client import TransportResult

        transport = MagicMock()
        transport.execute.return_value = TransportResult(
            status_code=200,
            data={"status": "created"},
            proof=self._mock_proof(),
        )
        outcome = submit_registration(
            transport=transport,
            request=self._make_request(),
        )
        assert outcome.identity_binding is None


# --------------------------------------------------------------
# 6. Proof Emission
# --------------------------------------------------------------


class TestProof:
    """SDK-CLIENT-07 section15 - Proof emission."""

    def test_proof_directory_created(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-proof-001",
            request_dict={"payload_summary": {"repo_name": "test", "shadow": False}},
            artifacts_snapshot={"snapshot_type": "registration_inputs"},
            outcome_dict={"status": "success", "repo_name": "test"},
        )
        assert proof_dir.is_dir()
        assert (proof_dir / "request.json").is_file()
        assert (proof_dir / "artifacts_snapshot.json").is_file()
        assert (proof_dir / "response.json").is_file()
        assert (proof_dir / "correlation.json").is_file()
        assert (proof_dir / "summary.md").is_file()
        assert (proof_dir / "digest.txt").is_file()

    def test_proof_path_convention(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-002",
            request_dict={},
            artifacts_snapshot={},
            outcome_dict={"status": "rejected"},
        )
        # Must be under repo_register/
        assert "repo_register" in str(proof_dir)

    def test_proof_emitted_on_rejection(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-rejected",
            request_dict={"payload_summary": {"repo_name": "bad-repo"}},
            artifacts_snapshot={},
            outcome_dict={
                "status": "rejected",
                "error_class": "invalid_repo",
                "reason": "missing artifacts",
                "repair_guidance": ["Fix something"],
            },
        )
        response = json.loads((proof_dir / "response.json").read_text())
        assert response["status"] == "rejected"

    def test_proof_includes_identity_context(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-id",
            request_dict={},
            artifacts_snapshot={},
            outcome_dict={"status": "success"},
            identity_context={"tenant_id": "t-1", "repo_id": "r-1"},
        )
        assert (proof_dir / "identity_context.json").is_file()
        ctx = json.loads((proof_dir / "identity_context.json").read_text())
        assert ctx["tenant_id"] == "t-1"

    def test_proof_summary_md_content(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-summary",
            request_dict={"payload_summary": {
                "repo_name": "test-repo",
                "registration_source": "native",
                "shadow": False,
                "readiness": "native_ready",
            }},
            artifacts_snapshot={},
            outcome_dict={"status": "success", "registration_id": "reg-001"},
        )
        summary = (proof_dir / "summary.md").read_text()
        assert "test-repo" in summary
        assert "native" in summary
        assert "success" in summary

    def test_proof_digest_txt(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-digest",
            request_dict={},
            artifacts_snapshot={},
            outcome_dict={"status": "success"},
        )
        digest = (proof_dir / "digest.txt").read_text().strip()
        assert digest == "corr-digest"

    def test_proof_without_identity_context(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-no-id",
            request_dict={},
            artifacts_snapshot={},
            outcome_dict={"status": "success"},
        )
        assert not (proof_dir / "identity_context.json").is_file()

    def test_proof_artifacts_snapshot_captured(self, tmp_path: Path):
        from keyhole_sdk.registration.proof import emit_registration_proof

        snap = {
            "snapshot_type": "registration_inputs",
            "native_artifacts": {"keyhole": {"name": "test"}},
        }
        proof_dir = emit_registration_proof(
            state_dir=tmp_path,
            correlation_id="corr-snap",
            request_dict={},
            artifacts_snapshot=snap,
            outcome_dict={"status": "success"},
        )
        saved = json.loads((proof_dir / "artifacts_snapshot.json").read_text())
        assert saved["native_artifacts"]["keyhole"]["name"] == "test"


# --------------------------------------------------------------
# 7. Repair Guidance
# --------------------------------------------------------------


class TestRepair:
    """SDK-CLIENT-07 section14 - Repair guidance."""

    def test_auth_guidance(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("AuthenticationError")
        assert any("login" in g.lower() for g in guidance)

    def test_missing_native_artifacts_guidance(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("MissingNativeArtifacts")
        assert any("ingest" in g.lower() for g in guidance)

    def test_missing_ingestion_reference_guidance(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("MissingIngestionReference")
        assert any("ingest" in g.lower() for g in guidance)

    def test_server_rejection_guidance(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("ServerRejection")
        assert any("shadow" in g.lower() for g in guidance)

    def test_unknown_error_fallback(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("SomethingUnexpected")
        assert len(guidance) > 0
        assert any("SomethingUnexpected" in g for g in guidance)

    def test_invalid_repo_path_guidance(self):
        from keyhole_sdk.registration.repair import map_registration_repair

        guidance = map_registration_repair("InvalidRepoPath")
        assert any("path" in g.lower() for g in guidance)

    def test_all_known_classes_have_guidance(self):
        from keyhole_sdk.registration.repair import _REPAIR_MAP, map_registration_repair

        for error_class in _REPAIR_MAP:
            guidance = map_registration_repair(error_class)
            assert len(guidance) > 0, f"No guidance for {error_class}"


# --------------------------------------------------------------
# 8. CLI Command
# --------------------------------------------------------------


class TestCLICommand:
    """SDK-CLIENT-07 section7 - CLI command contract."""

    def test_invalid_path_fails_local(self):
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        result = run_repo_register(repo_path="/nonexistent/path/xyz")
        assert not result.success
        assert result.exit_code != 0
        assert "InvalidRepoPath" in str(result.data)

    def test_no_auth_fails_local(self, tmp_path: Path):
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh_home"),
        )
        assert not result.success
        # Should fail due to auth or readiness
        assert result.data.get("is_local", False) is True

    def test_no_scaffold_no_ingest_fails_local(self, tmp_path: Path):
        """Foreign repo with no ingest ref should fail locally."""
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        # Create a fake credential store so auth passes
        kh_home = tmp_path / "kh_home"
        _create_fake_session(kh_home)

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(kh_home),
        )
        assert not result.success
        assert "readiness" in result.data
        assert result.data["readiness"] == "not_ready"

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_success_with_native_artifacts(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            IdentityBinding,
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        # Create native artifact files
        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("version: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("caps: []\n")

        # Mock auth
        mock_session = MagicMock()
        mock_session.access_token = "test-token"
        mock_session.token_fingerprint = "fp-123"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        # Mock submit
        mock_submit.return_value = RegistrationOutcome(
            status="success",
            registration_id="reg-001",
            repo_name=tmp_path.name,
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            identity_binding=IdentityBinding(
                tenant_id="t-1",
                repo_id="r-1",
            ),
            http_status=200,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )
        assert result.success
        assert "registered" in result.summary.lower()
        assert result.data["status"] == "success"
        assert result.data.get("tenant_id") == "t-1"

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_success_with_from_ingest(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        # Mock auth
        mock_session = MagicMock()
        mock_session.access_token = "test-token"
        mock_session.token_fingerprint = "fp-123"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        # Mock submit
        mock_submit.return_value = RegistrationOutcome(
            status="accepted",
            registration_id="reg-002",
            repo_name=tmp_path.name,
            registration_source=RegistrationSource.INGESTION,
            readiness=RegistrationReadiness.INGESTION_READY,
            http_status=202,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            from_ingest="ing_001",
            keyhole_home=str(tmp_path / "kh"),
        )
        assert result.success
        assert result.data["status"] == "accepted"

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_shadow_mode(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        # Create native artifacts
        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")

        # Mock auth
        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="success",
            repo_name=tmp_path.name,
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            shadow=True,
            http_status=200,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            shadow=True,
            keyhole_home=str(tmp_path / "kh"),
        )
        assert result.success
        assert result.data["shadow"] is True
        assert "shadow" in result.summary.lower()

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_replayed_outcome_rendered(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")

        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="replayed",
            is_replay=True,
            repo_name=tmp_path.name,
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            http_status=200,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )
        # Replayed is a stable governed outcome - must be success
        assert result.success
        assert result.data["is_replay"] is True
        assert "replayed" in result.summary.lower()

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_deferred_outcome_rendered_honestly(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")

        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="deferred",
            repo_name=tmp_path.name,
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            http_status=200,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )
        assert not result.success  # deferred is not terminal success
        assert "deferred" in result.summary.lower()


# --------------------------------------------------------------
# 9. Outcome Rendering
# --------------------------------------------------------------


class TestOutcomeRendering:
    """SDK-CLIENT-07 section13 - Outcome rendering to CommandResult."""

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_proof_dir_in_data(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")

        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="success",
            repo_name="test",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            http_status=200,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )
        assert "proof_dir" in result.data

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_failure_shows_repair_guidance(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")

        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="rejected",
            repo_name="test",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            error_class="invalid_repo",
            reason="contract missing",
            repair_guidance=["Fix the contract"],
            http_status=400,
        )

        result = run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )
        assert not result.success
        assert result.next_steps is not None
        assert any("Fix the contract" in s for s in result.next_steps)


# --------------------------------------------------------------
# 10. Operation Registry
# --------------------------------------------------------------


class TestOperationRegistry:
    """SDK-CLIENT-07 section12 - repo.register in operation registry."""

    def test_repo_register_is_registered(self):
        from keyhole_sdk.transport.operation_registry import is_registered

        assert is_registered("repo.register")

    def test_repo_register_requires_idempotency(self):
        from keyhole_sdk.transport.operation_registry import requires_idempotency

        assert requires_idempotency("repo.register")

    def test_repo_register_is_write_class(self):
        from keyhole_sdk.transport.operation_registry import (
            OperationClass,
            get_operation,
        )

        op = get_operation("repo.register")
        assert op is not None
        assert op.operation_class == OperationClass.WRITE_IDEMPOTENT_REQUIRED
        assert op.proof_required is True


# --------------------------------------------------------------
# 11. Public API Surface
# --------------------------------------------------------------


class TestPublicAPI:
    """SDK-CLIENT-07 - All 17 exports accessible from top-level SDK."""

    @pytest.mark.parametrize("symbol", [
        "IdentityBinding",
        "IngestionReference",
        "NativeArtifacts",
        "RegistrationOutcome",
        "RegistrationPayload",
        "RegistrationReadiness",
        "RegistrationRequest",
        "RegistrationSource",
        "assess_readiness",
        "load_native_artifacts",
        "load_ingestion_reference",
        "build_artifacts_snapshot",
        "build_registration_payload",
        "submit_registration",
        "emit_registration_proof",
        "map_registration_repair",
    ])
    def test_export_accessible(self, symbol: str):
        import keyhole_sdk

        assert hasattr(keyhole_sdk, symbol), f"{symbol} not exported"
        assert symbol in keyhole_sdk.__all__, f"{symbol} not in __all__"


# --------------------------------------------------------------
# 12. No Silent Mutation Guarantee
# --------------------------------------------------------------


class TestNoSilentMutation:
    """SDK-CLIENT-07 section18, section20 - Registration must never mutate the target repo."""

    @patch("keyhole_cli.commands.repo_register_cmd.submit_registration")
    @patch("keyhole_cli.commands.repo_register_cmd.CredentialStore")
    def test_repo_files_unchanged_after_registration(
        self, mock_cred_cls, mock_submit, tmp_path: Path,
    ):
        from keyhole_sdk.registration.models import (
            RegistrationOutcome,
            RegistrationSource,
            RegistrationReadiness,
        )
        from keyhole_cli.commands.repo_register_cmd import run_repo_register

        # Create repo with known content
        (tmp_path / "keyhole.yaml").write_text("name: test\n")
        (tmp_path / "governance_contract.yaml").write_text("v: 1\n")
        (tmp_path / "capability_passport.yaml").write_text("c: []\n")
        (tmp_path / "README.md").write_text("# Test\n")

        # Snapshot before
        before = {}
        for f in tmp_path.iterdir():
            if f.is_file():
                before[f.name] = f.read_text()

        # Mock auth
        mock_session = MagicMock()
        mock_session.access_token = "tok"
        mock_session.token_fingerprint = "fp"
        mock_store = MagicMock()
        mock_store.load.return_value = mock_session
        mock_cred_cls.return_value = mock_store

        mock_submit.return_value = RegistrationOutcome(
            status="success",
            repo_name="test",
            registration_source=RegistrationSource.NATIVE,
            readiness=RegistrationReadiness.NATIVE_READY,
            http_status=200,
        )

        run_repo_register(
            repo_path=str(tmp_path),
            keyhole_home=str(tmp_path / "kh"),
        )

        # Snapshot after - must be identical
        after = {}
        for f in tmp_path.iterdir():
            if f.is_file():
                after[f.name] = f.read_text()

        assert before == after, "Registration silently mutated target repo files"


# --------------------------------------------------------------
# 13. Foreign Repo Negative Tests
# --------------------------------------------------------------


class TestForeignRepo:
    """SDK-CLIENT-07 section21.3 - Foreign repo is not treated as native-ready."""

    def test_foreign_repo_not_native_ready(self, tmp_path: Path):
        """A bare directory should not be considered native_ready."""
        from keyhole_sdk.registration.artifacts import load_native_artifacts
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = load_native_artifacts(tmp_path)
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            native_artifacts=arts,
        )
        assert check.readiness.value != "native_ready"
        assert not check.can_proceed

    def test_foreign_repo_needs_ingest_first(self, tmp_path: Path):
        """Foreign repo without ingestion should get repair guidance pointing to ingest."""
        from keyhole_sdk.registration.artifacts import load_native_artifacts
        from keyhole_sdk.registration.readiness import assess_readiness

        arts = load_native_artifacts(tmp_path)
        check = assess_readiness(
            repo_path=tmp_path,
            has_auth=True,
            native_artifacts=arts,
        )
        assert any("ingest" in b.lower() for b in check.blockers)


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------


def _create_fake_session(kh_home: Path) -> None:
    """Create a minimal fake credential store so auth loads a session."""
    from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
    from keyhole_sdk.auth_bootstrap.models import AuthFlowType, AuthSession
    store = CredentialStore(store_dir=kh_home)
    session = AuthSession(
        access_token="fake-token-for-test",
        flow_type=AuthFlowType.PKCE,
        token_type="Bearer",
        scope="openid",
        realm="test",
    )
    store.save(session)
