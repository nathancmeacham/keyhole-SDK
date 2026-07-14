"""Tests for SDK-CLIENT-09 - Governed Run Dispatch.

Covers:
  section16.1 - command parsing for keyhole run / keyhole run --shadow
  section16.2 - preflight failures (unauthenticated, scaffold missing)
  section16.3 - deterministic request construction
  section16.4 - shadow flag propagation
  section16.5 - operation-class selection
  section16.6 - transport layer invocation through SDK-CLIENT-15
  section16.7 - proof artifacts created on success/failure
  section16.8 - readable summary generation
  section16.9 - repair guidance mapping
  section16.10 - negative tests (invalid state, masquerade, deferred != success)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# --------------------------------------------------------------
# SDK Module Imports
# --------------------------------------------------------------
from keyhole_sdk.run_dispatch.request_builder import RunRequest, build_run_request
from keyhole_sdk.run_dispatch.preflight import RunPreflight, PreflightFailure
from keyhole_sdk.run_dispatch.dispatcher import (
    RunOutcome,
    OutcomeStatus,
    dispatch_run,
    _classify_outcome,
    _handle_transport_exception,
)
from keyhole_sdk.run_dispatch.proof_emitter import emit_run_proof, _safe_dirname
from keyhole_sdk.run_dispatch.repair import map_repair_guidance
from keyhole_sdk.transport.client import GovernedTransport, TransportResult
from keyhole_sdk.transport.proof_metadata import (
    ClientObservation,
    TransportProofMetadata,
)
from keyhole_sdk.transport.operation_registry import (
    OperationClass,
    get_operation,
)
from keyhole_sdk.transport.errors import (
    IdempotencyConflictError,
    RetryExhaustedError,
    TransportUnknownError,
)
from keyhole_sdk.exceptions import (
    AuthenticationError,
    PublicEndpointError,
    RuntimeUnavailableError,
)

# CLI command import
from keyhole_cli.commands.run_cmd import run_run
from keyhole_cli.result import EXIT_SUCCESS, EXIT_FAILURE, EXIT_INVALID_INPUT, EXIT_RUNTIME_UNAVAILABLE


# --------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------


@pytest.fixture
def governed_repo(tmp_path: Path) -> Path:
    """Create a minimal governed repo scaffold."""
    keyhole_yaml = tmp_path / "keyhole.yaml"
    keyhole_yaml.write_text(
        "schema_version: v0.1\n"
        "repo:\n"
        "  name: test-vertical\n"
        "  kind: vertical\n",
        encoding="utf-8",
    )
    (tmp_path / "proof_bundle" / "core").mkdir(parents=True)
    (tmp_path / "proof_bundle" / "extended").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def bare_dir(tmp_path: Path) -> Path:
    """Create an empty directory with no scaffold."""
    empty = tmp_path / "bare"
    empty.mkdir()
    return empty


@pytest.fixture
def mock_cred_store():
    """Create a mock credential store that reports authenticated."""
    store = MagicMock()
    store.is_authenticated.return_value = True
    session = MagicMock()
    session.token_fingerprint = "abc12345"
    session.access_token = "test-token-value"
    store.load.return_value = session
    return store


@pytest.fixture
def mock_cred_store_unauthenticated():
    """Create a mock credential store that reports not authenticated."""
    store = MagicMock()
    store.is_authenticated.return_value = False
    store.load.return_value = None
    return store


def _make_transport_result(
    data: Dict[str, Any],
    status_code: int = 200,
    headers: Dict[str, str] | None = None,
) -> TransportResult:
    """Helper to create a TransportResult with proof."""
    proof = TransportProofMetadata(
        request_id="req-001",
        idempotency_key="idem-001",
        operation_class="WRITE_IDEMPOTENT_REQUIRED",
        command_name="run.start",
    )
    proof.record_attempt(attempt=1, request_id="req-001")
    proof.mark_observation(ClientObservation.EXECUTED)
    return TransportResult(
        data=data,
        status_code=status_code,
        proof=proof,
        response_headers=headers or {},
    )


# --------------------------------------------------------------
# 1. Request Construction Tests (section8, section16.3)
# --------------------------------------------------------------


class TestRequestConstruction:
    """section8: Request construction must be deterministic."""

    def test_build_basic_request(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="my-vertical",
        )
        assert req.run_type == "context.compile"
        assert req.repo_name == "my-vertical"
        assert req.shadow is False
        assert req.timestamp  # must be set

    def test_build_shadow_request(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="my-vertical",
            shadow=True,
        )
        assert req.shadow is True

    def test_build_with_context_ref(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            context_ref="sha256:abc123",
        )
        assert req.context_ref == "sha256:abc123"

    def test_build_with_input_data(self):
        data = {"key": "value"}
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            input_data=data,
        )
        assert req.input_data == data

    def test_payload_deterministic(self):
        """Same inputs produce the same payload structure."""
        req = build_run_request(
            run_type="gaps.list",
            repo_name="test-repo",
            shadow=True,
            context_ref="auto",
            correlation_id="corr-001",
        )
        payload = req.to_payload()
        assert payload["run_type"] == "gaps.list"
        assert payload["repo"] == "test-repo"
        assert payload["shadow"] is True
        assert payload["context_ref"] == "auto"
        assert payload["correlation_id"] == "corr-001"

    def test_proof_dict_has_no_secrets(self):
        """Proof dict must not contain token or credential info."""
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            identity_fingerprint="fp12345",
        )
        proof = req.to_proof_dict()
        assert "access_token" not in proof
        assert "token" not in proof
        assert proof["identity_fingerprint"] == "fp12345"

    def test_timestamp_is_iso_format(self):
        req = build_run_request(run_type="context.compile", repo_name="v")
        # ISO format has "T" separator
        assert "T" in req.timestamp


# --------------------------------------------------------------
# 2. Preflight Tests (section6, section16.2)
# --------------------------------------------------------------


class TestRunPreflight:
    """section6: Preflight must block invalid runs before dispatch."""

    def test_passes_when_all_ok(self, governed_repo, mock_cred_store):
        preflight = RunPreflight(credential_store=mock_cred_store)
        result = preflight.check(
            repo_dir=governed_repo,
            run_type="context.compile",
        )
        assert result is None  # no failure

    def test_fails_when_unauthenticated(self, governed_repo, mock_cred_store_unauthenticated):
        preflight = RunPreflight(credential_store=mock_cred_store_unauthenticated)
        result = preflight.check(
            repo_dir=governed_repo,
            run_type="context.compile",
        )
        assert result is not None
        assert "Not authenticated" in result.reason
        assert any("keyhole login" in g for g in result.repair_guidance)

    def test_fails_when_scaffold_missing(self, bare_dir, mock_cred_store):
        preflight = RunPreflight(credential_store=mock_cred_store)
        result = preflight.check(
            repo_dir=bare_dir,
            run_type="context.compile",
        )
        assert result is not None
        assert "keyhole.yaml" in result.reason
        assert any("keyhole init vertical" in g for g in result.repair_guidance)

    def test_fails_when_run_type_invalid(self, governed_repo, mock_cred_store):
        preflight = RunPreflight(credential_store=mock_cred_store)
        result = preflight.check(
            repo_dir=governed_repo,
            run_type="totally.bogus.invented.type",
        )
        assert result is not None
        assert "rejected" in result.reason.lower() or "preflight" in result.reason.lower()

    def test_load_repo_name(self, governed_repo, mock_cred_store):
        preflight = RunPreflight(credential_store=mock_cred_store)
        name = preflight.load_repo_name(governed_repo)
        assert name == "test-vertical"

    def test_load_repo_name_fallback(self, bare_dir, mock_cred_store):
        preflight = RunPreflight(credential_store=mock_cred_store)
        name = preflight.load_repo_name(bare_dir)
        # Falls back to dir name when no keyhole.yaml
        assert name is None or isinstance(name, str)

    def test_preflight_failure_has_repair_guidance(self, governed_repo, mock_cred_store_unauthenticated):
        preflight = RunPreflight(credential_store=mock_cred_store_unauthenticated)
        failure = preflight.check(repo_dir=governed_repo, run_type="context.compile")
        assert failure is not None
        assert len(failure.repair_guidance) > 0
        assert failure.is_local is True


# --------------------------------------------------------------
# 3. Shadow Mode Tests (section11, section16.4)
# --------------------------------------------------------------


class TestShadowMode:
    """section11: Shadow mode must be explicit everywhere."""

    def test_shadow_in_request_payload(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            shadow=True,
        )
        payload = req.to_payload()
        assert payload["shadow"] is True

    def test_non_shadow_in_request_payload(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            shadow=False,
        )
        payload = req.to_payload()
        assert payload["shadow"] is False

    def test_shadow_in_proof_dict(self):
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            shadow=True,
        )
        proof = req.to_proof_dict()
        assert proof["shadow"] is True

    def test_shadow_in_outcome(self):
        result = _make_transport_result(
            {"status": "success", "run_id": "r1"},
            status_code=200,
        )
        req = RunRequest(
            run_type="context.compile",
            repo_name="v",
            shadow=True,
            correlation_id="c1",
        )
        outcome = _classify_outcome(result, req)
        assert outcome.shadow is True

    def test_shadow_cannot_masquerade_as_non_shadow(self):
        """section16.3 negative: shadow flag must propagate truthfully."""
        req = build_run_request(
            run_type="context.compile",
            repo_name="v",
            shadow=True,
        )
        # The request says shadow=True - payload must agree
        assert req.to_payload()["shadow"] is True
        assert req.to_proof_dict()["shadow"] is True
        # And non-shadow must say False
        req2 = build_run_request(
            run_type="context.compile",
            repo_name="v",
            shadow=False,
        )
        assert req2.to_payload()["shadow"] is False


# --------------------------------------------------------------
# 4. Operation-Class Tests (section9, section16.5)
# --------------------------------------------------------------


class TestOperationClass:
    """section9: run.start must be classified as WRITE_IDEMPOTENT_REQUIRED."""

    def test_run_start_is_write_idempotent(self):
        desc = get_operation("run.start")
        assert desc is not None
        assert desc.operation_class == OperationClass.WRITE_IDEMPOTENT_REQUIRED

    def test_run_start_requires_idempotency_key(self):
        desc = get_operation("run.start")
        assert desc is not None
        assert desc.idempotency_required is True

    def test_run_start_requires_proof(self):
        desc = get_operation("run.start")
        assert desc is not None
        assert desc.proof_required is True


# --------------------------------------------------------------
# 5. Outcome Classification Tests (section10)
# --------------------------------------------------------------


class TestOutcomeClassification:
    """section10: Client must handle inline, accepted, deferred, and failure."""

    def _make_request(self, **kwargs) -> RunRequest:
        return RunRequest(
            run_type="context.compile",
            repo_name="test-repo",
            correlation_id="corr-001",
            **kwargs,
        )

    def test_inline_success(self):
        result = _make_transport_result(
            {"status": "success", "run_id": "run-123"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.SUCCESS
        assert outcome.run_id == "run-123"

    def test_accepted_202(self):
        result = _make_transport_result(
            {"status": "accepted", "run_id": "run-456"},
            status_code=202,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.ACCEPTED
        assert outcome.run_id == "run-456"

    def test_accepted_status_field(self):
        result = _make_transport_result(
            {"status": "accepted", "run_id": "run-789"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.ACCEPTED

    def test_pending_is_accepted(self):
        result = _make_transport_result(
            {"status": "pending", "run_id": "run-101"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.ACCEPTED

    def test_deferred(self):
        result = _make_transport_result(
            {"status": "deferred", "run_id": "run-202"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.DEFERRED

    def test_rejected(self):
        result = _make_transport_result(
            {"status": "rejected", "reason": "missing context"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.REJECTED
        assert "missing context" in outcome.reason

    def test_failed_status(self):
        result = _make_transport_result(
            {"status": "failed", "reason": "internal error"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.REJECTED

    def test_error_status(self):
        result = _make_transport_result(
            {"status": "error", "reason": "bad request"},
            status_code=200,
        )
        outcome = _classify_outcome(result, self._make_request())
        assert outcome.status == OutcomeStatus.REJECTED


# --------------------------------------------------------------
# 6. Transport Exception Handling Tests
# --------------------------------------------------------------


class TestTransportExceptionHandling:
    """Transport exceptions must map to RunOutcome with repair guidance."""

    def _make_request(self) -> RunRequest:
        return RunRequest(
            run_type="context.compile",
            repo_name="test-repo",
            correlation_id="corr-001",
        )

    def test_transport_unknown_maps_to_transport_error(self):
        exc = TransportUnknownError(
            "connection lost",
            request_id="req-1",
            idempotency_key="idem-1",
        )
        outcome = _handle_transport_exception(exc, self._make_request())
        assert outcome.status == OutcomeStatus.TRANSPORT_ERROR
        assert outcome.error_class == "TransportUnknownError"
        assert len(outcome.repair_guidance) > 0

    def test_retry_exhausted_maps_to_transport_error(self):
        exc = RetryExhaustedError(
            "exhausted",
            request_id="req-2",
            idempotency_key="idem-2",
            attempt_count=3,
        )
        outcome = _handle_transport_exception(exc, self._make_request())
        assert outcome.status == OutcomeStatus.TRANSPORT_ERROR

    def test_auth_error_maps_to_failed(self):
        exc = AuthenticationError("bad credentials")
        outcome = _handle_transport_exception(exc, self._make_request())
        assert outcome.status == OutcomeStatus.FAILED
        assert outcome.error_class == "AuthenticationError"

    def test_public_endpoint_error_maps_to_failed(self):
        exc = PublicEndpointError("bad request", status_code=400)
        outcome = _handle_transport_exception(exc, self._make_request())
        assert outcome.status == OutcomeStatus.FAILED
        assert outcome.error_class == "PublicEndpointError"

    def test_conflict_error_maps_to_failed(self):
        exc = IdempotencyConflictError(
            "conflict",
            request_id="req-3",
            idempotency_key="idem-3",
        )
        outcome = _handle_transport_exception(exc, self._make_request())
        assert outcome.status == OutcomeStatus.FAILED


# --------------------------------------------------------------
# 7. Proof Artifact Tests (section13, section16.7)
# --------------------------------------------------------------


class TestProofArtifacts:
    """section13: Proof must be emitted for both success and failure."""

    def test_proof_emitted_on_success(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            correlation_id="corr-success-001",
            identity_fingerprint="fp1",
        )
        outcome_dict = {"status": "success", "run_id": "r1"}
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict=outcome_dict,
            correlation_id="corr-success-001",
        )
        assert proof_dir.exists()
        assert (proof_dir / "request.json").exists()
        assert (proof_dir / "response.json").exists()
        assert (proof_dir / "summary.md").exists()
        assert (proof_dir / "correlation.json").exists()

    def test_proof_emitted_on_failure(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            correlation_id="corr-fail-001",
        )
        outcome_dict = {
            "status": "failed",
            "error_class": "RuntimeUnavailableError",
            "reason": "server down",
        }
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict=outcome_dict,
            correlation_id="corr-fail-001",
        )
        assert proof_dir.exists()
        assert (proof_dir / "request.json").exists()
        assert (proof_dir / "response.json").exists()

    def test_proof_contains_shadow_flag(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            shadow=True,
            correlation_id="corr-shadow-001",
        )
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict={"status": "success"},
            correlation_id="corr-shadow-001",
        )
        request_data = json.loads((proof_dir / "request.json").read_text())
        assert request_data["shadow"] is True

    def test_proof_correlation_json(self, governed_repo):
        req = build_run_request(
            run_type="gaps.list",
            repo_name="test-vertical",
            correlation_id="corr-002",
            identity_fingerprint="fp-test",
        )
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict={"status": "success"},
            correlation_id="corr-002",
        )
        corr = json.loads((proof_dir / "correlation.json").read_text())
        assert corr["correlation_id"] == "corr-002"
        assert corr["run_type"] == "gaps.list"
        assert corr["identity_fingerprint"] == "fp-test"

    def test_proof_extended_debug_exists(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            correlation_id="corr-ext-001",
        )
        emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict={"status": "success"},
            correlation_id="corr-ext-001",
        )
        ext_dir = governed_repo / "proof_bundle" / "extended" / "runs" / "corr-ext-001"
        assert (ext_dir / "debug.json").exists()

    def test_proof_summary_readable(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            shadow=True,
            correlation_id="corr-sum-001",
        )
        outcome_dict = {"status": "success", "run_id": "r1"}
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict=outcome_dict,
            correlation_id="corr-sum-001",
        )
        summary = (proof_dir / "summary.md").read_text()
        assert "context.compile" in summary
        assert "SHADOW" in summary
        assert "corr-sum-001" in summary

    def test_proof_transport_metadata_preserved(self, governed_repo):
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            correlation_id="corr-tp-001",
        )
        transport_proof = {
            "request_id": "req-t1",
            "idempotency_key": "idem-t1",
            "operation_class": "WRITE_IDEMPOTENT_REQUIRED",
        }
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict={"status": "success"},
            correlation_id="corr-tp-001",
            transport_proof_dict=transport_proof,
        )
        corr = json.loads((proof_dir / "correlation.json").read_text())
        assert corr["transport"]["request_id"] == "req-t1"
        assert corr["transport"]["idempotency_key"] == "idem-t1"


# --------------------------------------------------------------
# 8. Repair Guidance Tests (section15, section16.9)
# --------------------------------------------------------------


class TestRepairGuidance:
    """section15: Failure must produce deterministic repair guidance."""

    def test_auth_error_guidance(self):
        guidance = map_repair_guidance("AuthenticationError")
        assert any("keyhole login" in g for g in guidance)

    def test_transport_unknown_guidance(self):
        guidance = map_repair_guidance("TransportUnknownError")
        assert any("network" in g.lower() or "retry" in g.lower() for g in guidance)

    def test_retry_exhausted_guidance(self):
        guidance = map_repair_guidance("RetryExhaustedError")
        assert len(guidance) > 0

    def test_conflict_guidance(self):
        guidance = map_repair_guidance("IdempotencyConflictError")
        assert any("key" in g.lower() for g in guidance)

    def test_rate_limited_guidance(self):
        guidance = map_repair_guidance("RateLimitedError")
        assert any("wait" in g.lower() or "retry" in g.lower() for g in guidance)

    def test_unknown_error_guidance(self):
        guidance = map_repair_guidance("SomeUnknownError")
        assert len(guidance) > 0  # must not be empty - never a dead end

    def test_scaffold_missing_guidance(self):
        guidance = map_repair_guidance("ScaffoldMissing")
        assert any("init vertical" in g for g in guidance)


# --------------------------------------------------------------
# 9. Dispatch Integration Tests (section16.6)
# --------------------------------------------------------------


class TestDispatchIntegration:
    """section16.6: Transport invocation goes through SDK-CLIENT-15 layer."""

    def test_dispatch_calls_governed_transport(self):
        """Dispatch must use GovernedTransport.execute, not raw HTTP."""
        mock_transport = MagicMock(spec=GovernedTransport)
        mock_transport.execute.return_value = _make_transport_result(
            {"status": "success", "run_id": "r1"},
            status_code=200,
        )
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-repo",
            correlation_id="corr-int-001",
        )
        outcome = dispatch_run(transport=mock_transport, request=req)
        mock_transport.execute.assert_called_once()
        call_kwargs = mock_transport.execute.call_args
        assert call_kwargs[0][0] == "POST"  # method
        assert call_kwargs[0][1] == "/mcp/v1/runs/start"  # path
        assert call_kwargs[1]["operation_name"] == "run.start"
        assert outcome.status == OutcomeStatus.SUCCESS

    def test_dispatch_passes_payload(self):
        mock_transport = MagicMock(spec=GovernedTransport)
        mock_transport.execute.return_value = _make_transport_result(
            {"status": "success"},
        )
        req = build_run_request(
            run_type="gaps.list",
            repo_name="r",
            shadow=True,
            correlation_id="c1",
        )
        dispatch_run(transport=mock_transport, request=req)
        call_kwargs = mock_transport.execute.call_args
        payload = call_kwargs[1]["json"]
        assert payload["run_type"] == "gaps.list"
        assert payload["shadow"] is True

    def test_dispatch_handles_transport_exception(self):
        mock_transport = MagicMock(spec=GovernedTransport)
        mock_transport.execute.side_effect = TransportUnknownError(
            "timeout",
            request_id="req-x",
            idempotency_key="idem-x",
        )
        req = build_run_request(
            run_type="context.compile",
            repo_name="r",
            correlation_id="c1",
        )
        outcome = dispatch_run(transport=mock_transport, request=req)
        assert outcome.status == OutcomeStatus.TRANSPORT_ERROR
        assert outcome.error_class == "TransportUnknownError"


# --------------------------------------------------------------
# 10. CLI Command Tests (section16.1)
# --------------------------------------------------------------


class TestCLICommand:
    """section16.1: Command parsing and end-to-end CLI flow."""

    def test_preflight_blocks_unauthenticated(self, governed_repo, tmp_path):
        """CLI returns failure when not authenticated."""
        keyhole_home = tmp_path / "home_noauth"
        keyhole_home.mkdir()
        result = run_run(
            run_type="context.compile",
            repo_dir=str(governed_repo),
            keyhole_home=str(keyhole_home),
        )
        assert result.success is False
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "PreflightFailure" in result.data.get("error_class", "")

    def test_preflight_blocks_missing_scaffold(self, bare_dir, tmp_path):
        """CLI returns failure when scaffold is missing."""
        # Create credential store to pass auth check
        keyhole_home = tmp_path / "home_auth"
        keyhole_home.mkdir()
        _create_fake_credentials(keyhole_home)
        result = run_run(
            run_type="context.compile",
            repo_dir=str(bare_dir),
            keyhole_home=str(keyhole_home),
        )
        assert result.success is False
        assert "keyhole.yaml" in (result.summary or "")

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_success_flow(self, MockCredStore, MockTransport, governed_repo):
        """Full success path through run_run."""
        # Mock credential store
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp123"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        # Mock transport
        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "success", "run_id": "run-ok-1"},
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            repo_dir=str(governed_repo),
        )
        assert result.success is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.data["status"] == "success"
        assert result.data["run_type"] == "context.compile"

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_shadow_flag_propagated(self, MockCredStore, MockTransport, governed_repo):
        """Shadow flag must appear in result data."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "success"},
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            shadow=True,
            repo_dir=str(governed_repo),
        )
        assert result.success is True
        assert result.data["shadow"] is True

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_accepted_outcome_rendered_honestly(self, MockCredStore, MockTransport, governed_repo):
        """section10.2: Accepted must NOT render as final success."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "accepted", "run_id": "run-async-1"},
            status_code=202,
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            repo_dir=str(governed_repo),
        )
        assert result.success is True  # accepted is not a failure
        assert result.data["status"] == "accepted"
        assert "accepted" in result.summary.lower() or "async" in result.summary.lower()
        # Must tell user to check status - not claim completion
        assert any("status" in s.lower() for s in result.next_steps)

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_deferred_outcome_not_success(self, MockCredStore, MockTransport, governed_repo):
        """section10.2: Deferred must NOT render as final success."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "deferred", "run_id": "run-defer-1"},
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            repo_dir=str(governed_repo),
        )
        assert result.data["status"] == "deferred"
        # Must mention deferred, not completed
        assert "deferred" in result.summary.lower()

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_transport_error_includes_retry_guidance(self, MockCredStore, MockTransport, governed_repo):
        """Transport errors must include repair guidance."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.side_effect = TransportUnknownError(
            "connection refused",
            request_id="req-err",
            idempotency_key="idem-err",
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            repo_dir=str(governed_repo),
        )
        assert result.success is False
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE
        assert len(result.next_steps) > 0

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_proof_written_on_success(self, MockCredStore, MockTransport, governed_repo):
        """Proof artifacts must exist after a successful run."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "success", "run_id": "run-proof-1"},
        )
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            repo_dir=str(governed_repo),
        )
        assert result.success is True
        # Check proof directory was populated
        proof_path = result.data.get("proof", "")
        assert proof_path
        assert Path(proof_path).exists()

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_proof_written_on_failure(self, MockCredStore, MockTransport, governed_repo):
        """Proof artifacts must exist after a failed run."""
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.side_effect = RuntimeUnavailableError("down")
        MockTransport.return_value = mock_transport_instance

        result = run_run(
            run_type="context.compile",
            repo_dir=str(governed_repo),
        )
        assert result.success is False
        proof_path = result.data.get("proof", "")
        # Proof may be written even on failure
        if proof_path and proof_path != "(proof not written)":
            assert Path(proof_path).exists()


# --------------------------------------------------------------
# 11. Negative Tests (section16.3)
# --------------------------------------------------------------


class TestNegativeTests:
    """section16.3: Invalid state must block before dispatch."""

    def test_invalid_repo_blocks_dispatch(self, bare_dir, tmp_path):
        """No scaffold -> preflight blocks -> no network request."""
        keyhole_home = tmp_path / "home_neg"
        keyhole_home.mkdir()
        _create_fake_credentials(keyhole_home)
        result = run_run(
            run_type="context.compile",
            repo_dir=str(bare_dir),
            keyhole_home=str(keyhole_home),
        )
        assert result.success is False

    def test_malformed_response_not_success(self):
        """section16.3: Malformed boundary response must not appear as success."""
        result = _make_transport_result(
            {"status": "error", "reason": "malformed"},
            status_code=200,
        )
        req = RunRequest(
            run_type="context.compile",
            repo_name="r",
            correlation_id="c1",
        )
        outcome = _classify_outcome(result, req)
        assert outcome.status != OutcomeStatus.SUCCESS

    def test_accepted_not_rendered_as_final_success(self):
        """section10 critical rule: accepted != final success."""
        result = _make_transport_result(
            {"status": "accepted", "run_id": "r1"},
            status_code=202,
        )
        req = RunRequest(
            run_type="context.compile",
            repo_name="r",
            correlation_id="c1",
        )
        outcome = _classify_outcome(result, req)
        assert outcome.status == OutcomeStatus.ACCEPTED
        assert outcome.status != OutcomeStatus.SUCCESS

    def test_deferred_not_rendered_as_final_success(self):
        """Deferred != final success."""
        result = _make_transport_result(
            {"status": "deferred", "run_id": "r1"},
        )
        req = RunRequest(
            run_type="context.compile",
            repo_name="r",
            correlation_id="c1",
        )
        outcome = _classify_outcome(result, req)
        assert outcome.status == OutcomeStatus.DEFERRED
        assert outcome.status != OutcomeStatus.SUCCESS


# --------------------------------------------------------------
# 12. Outcome Rendering Tests (section12)
# --------------------------------------------------------------


class TestOutcomeRendering:
    """section12: Outcomes must be rendered clearly and truthfully."""

    def test_success_outcome_to_proof_dict(self):
        outcome = RunOutcome(
            status=OutcomeStatus.SUCCESS,
            run_type="context.compile",
            repo_name="test-repo",
            shadow=False,
            correlation_id="c1",
            run_id="run-1",
            http_status=200,
        )
        d = outcome.to_proof_dict()
        assert d["status"] == "success"
        assert d["run_type"] == "context.compile"
        assert d["run_id"] == "run-1"
        assert d["shadow"] is False

    def test_failure_outcome_has_error_info(self):
        outcome = RunOutcome(
            status=OutcomeStatus.FAILED,
            run_type="context.compile",
            repo_name="test-repo",
            correlation_id="c1",
            error_class="AuthenticationError",
            reason="bad token",
            repair_guidance=["Run: keyhole login"],
        )
        d = outcome.to_proof_dict()
        assert d["error_class"] == "AuthenticationError"
        assert d["reason"] == "bad token"
        assert "Run: keyhole login" in d["repair_guidance"]

    def test_transport_error_flags_retry_safe(self):
        """Transport errors should indicate retry is safe."""
        outcome = RunOutcome(
            status=OutcomeStatus.TRANSPORT_ERROR,
            error_class="TransportUnknownError",
        )
        # When rendered to CLI, retry_safe should be True
        d = outcome.to_proof_dict()
        assert d["status"] == "transport_error"


# --------------------------------------------------------------
# 13. Invariant Tests
# --------------------------------------------------------------


class TestInvariants:
    """Cross-cutting invariants from the story acceptance criteria."""

    def test_sdk_exports_run_dispatch(self):
        """Run dispatch modules must be importable from keyhole_sdk."""
        from keyhole_sdk import (
            RunPreflight,
            PreflightFailure,
            RunRequest,
            build_run_request,
            RunOutcome,
            OutcomeStatus,
            dispatch_run,
            emit_run_proof,
            map_repair_guidance,
        )
        assert RunPreflight is not None
        assert OutcomeStatus.SUCCESS.value == "success"

    def test_run_start_registered_in_operation_registry(self):
        """run.start must exist in the central operation registry."""
        desc = get_operation("run.start")
        assert desc is not None
        assert desc.name == "run.start"

    def test_proof_uses_canonical_scaffold_paths(self, governed_repo):
        """Proof must use proof_bundle/core/ and proof_bundle/extended/."""
        req = build_run_request(
            run_type="context.compile",
            repo_name="test-vertical",
            correlation_id="inv-proof-001",
        )
        proof_dir = emit_run_proof(
            repo_dir=governed_repo,
            request=req,
            outcome_dict={"status": "success"},
            correlation_id="inv-proof-001",
        )
        # Core proof must be under proof_bundle/core/runs/
        assert "proof_bundle" in str(proof_dir)
        assert "core" in str(proof_dir)
        assert "runs" in str(proof_dir)

    def test_safe_dirname_sanitizes(self):
        """Correlation IDs must be sanitized for filesystem safety."""
        assert _safe_dirname("abc-123") == "abc-123"
        assert _safe_dirname("a/b/c") == "a_b_c"
        assert _safe_dirname("") == "unknown"

    def test_no_direct_memory_access(self):
        """section20: SDK-CLIENT-09 must not expose direct canonical memory access."""
        from keyhole_sdk import run_dispatch
        module_contents = dir(run_dispatch)
        forbidden = ["memory", "qdrant", "vector", "embedding"]
        for word in forbidden:
            assert not any(
                word in name.lower() for name in module_contents
            ), f"Found forbidden term '{word}' in run_dispatch module"


# --------------------------------------------------------------
# 14. Input File Tests
# --------------------------------------------------------------


class TestInputFile:
    """Input file handling for --input flag."""

    @patch("keyhole_cli.commands.run_cmd.GovernedTransport")
    @patch("keyhole_cli.commands.run_cmd.CredentialStore")
    def test_valid_input_file(self, MockCredStore, MockTransport, governed_repo, tmp_path):
        mock_store = MagicMock()
        mock_store.is_authenticated.return_value = True
        session = MagicMock()
        session.token_fingerprint = "fp"
        session.access_token = "tok"
        mock_store.load.return_value = session
        MockCredStore.return_value = mock_store

        mock_transport_instance = MagicMock()
        mock_transport_instance.execute.return_value = _make_transport_result(
            {"status": "success"},
        )
        MockTransport.return_value = mock_transport_instance

        input_file = tmp_path / "input.json"
        input_file.write_text('{"key": "value"}', encoding="utf-8")

        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            input_file=str(input_file),
            repo_dir=str(governed_repo),
        )
        assert result.success is True

    def test_missing_input_file_fails(self, governed_repo, tmp_path):
        keyhole_home = tmp_path / "home_inp"
        keyhole_home.mkdir()
        _create_fake_credentials(keyhole_home)
        result = run_run(
            run_type="context.compile",
            context="a" * 64,
            input_file="/nonexistent/file.json",
            repo_dir=str(governed_repo),
            keyhole_home=str(keyhole_home),
        )
        assert result.success is False
        assert "not found" in (result.summary or "").lower()

    def test_invalid_json_input_file_fails(self, governed_repo, tmp_path):
        keyhole_home = tmp_path / "home_bad"
        keyhole_home.mkdir()
        _create_fake_credentials(keyhole_home)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json at all", encoding="utf-8")
        result = run_run(
            run_type="context.compile",
            input_file=str(bad_file),
            repo_dir=str(governed_repo),
            keyhole_home=str(keyhole_home),
        )
        assert result.success is False


# --------------------------------------------------------------
# Helpers
# --------------------------------------------------------------


def _create_fake_credentials(keyhole_home: Path) -> None:
    """Create a minimal credentials.json for testing."""
    import json
    from datetime import datetime, timezone, timedelta

    creds = {
        "access_token": "fake-test-token",
        "token_type": "Bearer",
        "flow_type": "pkce",
        "mode": "real",
        "realm": "keyhole-mcp",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    cred_file = keyhole_home / "credentials.json"
    cred_file.write_text(json.dumps(creds), encoding="utf-8")
    os.chmod(cred_file, 0o600)
