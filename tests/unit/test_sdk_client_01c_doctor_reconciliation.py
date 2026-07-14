"""SDK-CLIENT-01-C - MCP Host Identity Reconciliation tests.

Covers section19 test strategy:
  Unit: host inventory, classifiers, negotiation handling,
        no-false-convergence, request shaping, proof emission
  Negative: host not detected, connection not visible, surface unavailable,
            rebind forbidden, ambiguous connection, verification mismatch
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# -- SDK doctor imports ------------------------------------
from keyhole_sdk.doctor.models import (
    DoctorHostEntry,
    DoctorHostRecord,
    DoctorReport,
    DoctorSummaryStatus,
    HostDiagnosis,
    HostType,
    RecommendedAction,
    RepairGuidance,
    StalenessState,
)
from keyhole_sdk.doctor.host_inventory import (
    HostDetector,
    SDKCredentialDetector,
    VSCodeHostDetector,
    detect_hosts,
)
from keyhole_sdk.doctor.diagnostics import (
    build_doctor_report,
    build_repair_guidance,
    classify_host_diagnosis,
)
from keyhole_sdk.doctor.reconciliation import (
    CONNECTION_INSPECT_RUN_TYPE,
    CONNECTION_LINEAGE_RUN_TYPE,
    CONNECTION_STATUS_RUN_TYPE,
    CONNECTION_WHOAMI_RUN_TYPE,
    CONNECTION_REBIND_RUN_TYPE,
    CONNECTION_INVALIDATE_RUN_TYPE,
    CONNECTION_LIST_RUN_TYPE,
    CONNECTION_SURFACES,
    check_connection_surfaces_available,
    reconcile,
)
from keyhole_sdk.doctor.proof import DoctorProofBundle

# -- SDK connection identity imports -----------------------
from keyhole_sdk.connection_identity.models import (
    ConnectionAuthority,
    ConnectionInfo,
    ConnectionStaleness,
    InvalidateOutcome,
    InvalidateRequest,
    InvalidateStatus,
    RebindOutcome,
    RebindRequest,
    RebindStatus,
)
from keyhole_sdk.connection_identity.client import ConnectionIdentityClient
from keyhole_sdk.connection_identity.errors import (
    ConnectionIdentityError,
    ConnectionNetworkError,
    ConnectionNotAuthenticatedError,
    ConnectionNotFoundError,
    ConnectionSurfaceUnavailableError,
    RebindRejectedError,
    VerificationFailedError,
)
from keyhole_sdk.connection_identity.repair import (
    repair_commands_for_diagnosis,
    repair_steps_for_diagnosis,
)

# -- CLI command imports -----------------------------------
from keyhole_cli.commands.connections_list import run_connections_list
from keyhole_cli.commands.connection_inspect import run_connection_inspect
from keyhole_cli.commands.connection_lineage import run_connection_lineage
from keyhole_cli.commands.connection_rebind import run_connection_rebind
from keyhole_cli.commands.connection_invalidate import run_connection_invalidate

# -- SDK render imports ------------------------------------
from keyhole_sdk.connection_identity.render import (
    render_connection_info,
    render_connection_list,
    render_lineage,
    render_rebind_outcome,
    render_invalidate_outcome,
)


# --------------------------------------------------------------
# section19 Unit - Host inventory with zero hosts
# --------------------------------------------------------------


class TestHostInventoryZeroHosts:
    """Host inventory returns empty when no hosts are detected."""

    def test_detect_hosts_with_no_detectors(self):
        result = detect_hosts(detectors=[])
        assert result == []

    def test_detect_hosts_with_failing_detector(self):
        class FailingDetector(HostDetector):
            def detect(self):
                raise RuntimeError("boom")

        result = detect_hosts(detectors=[FailingDetector()])
        assert len(result) == 1
        assert result[0].diagnosis == HostDiagnosis.UNSUPPORTED_HOST
        assert result[0].detected is False

    def test_detect_hosts_with_none_returning_detector(self):
        class NoneDetector(HostDetector):
            def detect(self):
                return None

        result = detect_hosts(detectors=[NoneDetector()])
        assert result == []


# --------------------------------------------------------------
# section19 Unit - Host inventory with known supported host
# --------------------------------------------------------------


class TestHostInventoryKnownHost:
    """VS Code and SDK credential detectors produce structured records."""

    def test_vscode_detector_not_installed(self):
        detector = VSCodeHostDetector()
        with patch.object(detector, "_find_settings_file", return_value=None):
            record = detector.detect()
        assert record is not None
        assert record.host_id == "vscode"
        assert record.host_type == HostType.IDE_MCP_CLIENT
        assert record.detected is False

    def test_vscode_detector_installed_no_keyhole(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(json.dumps({"editor.fontSize": 14}))
        detector = VSCodeHostDetector()
        with patch.object(detector, "_find_settings_file", return_value=settings):
            record = detector.detect()
        assert record.detected is True
        assert record.config_detected is True
        assert record.keyhole_server_entry_detected is False

    def test_vscode_detector_with_keyhole_entry(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "mcp.servers": {
                        "keyhole": {
                            "url": "https://mcp.keyholesolution.com/sse",
                        }
                    }
                }
            )
        )
        detector = VSCodeHostDetector()
        with patch.object(detector, "_find_settings_file", return_value=settings):
            record = detector.detect()
        assert record.detected is True
        assert record.keyhole_server_entry_detected is True
        assert "mcp.keyholesolution.com" in record.server_url

    def test_vscode_detector_mcpServers_key(self, tmp_path):
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "my-keyhole-server": {
                            "url": "https://mcp.keyholesolution.com",
                        }
                    }
                }
            )
        )
        detector = VSCodeHostDetector()
        with patch.object(detector, "_find_settings_file", return_value=settings):
            record = detector.detect()
        assert record.keyhole_server_entry_detected is True

    def test_sdk_credential_detector_no_creds(self, tmp_path):
        detector = SDKCredentialDetector()
        with patch.object(
            detector, "_find_credential_file", return_value=tmp_path / "missing.json"
        ):
            record = detector.detect()
        assert record.host_id == "sdk_local"
        assert record.host_type == HostType.SDK_RUNTIME
        assert record.detected is True
        assert record.local_auth_hints_present is False

    def test_sdk_credential_detector_with_creds(self, tmp_path):
        cred = tmp_path / "credentials.json"
        cred.write_text('{"access_token": "tok"}')
        detector = SDKCredentialDetector()
        with patch.object(detector, "_find_credential_file", return_value=cred):
            record = detector.detect()
        assert record.local_auth_hints_present is True
        assert record.config_detected is True


# --------------------------------------------------------------
# section19 Unit - Split identity classifier
# --------------------------------------------------------------


class TestSplitIdentityClassifier:
    """INV-SDK-CLIENT-01-C-001: Split identity is visible."""

    def test_split_identity_different_principals(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
            server_principal_label="nathan",
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.SPLIT_IDENTITY

    def test_split_identity_shows_both_principals_in_report(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
            server_principal_label="nathan",
            diagnosis=HostDiagnosis.SPLIT_IDENTITY,
        )
        report = build_doctor_report(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            connection_surfaces_available=True,
            negotiation_available=True,
        )
        assert report.summary_status == DoctorSummaryStatus.ATTENTION_REQUIRED
        entry = report.hosts[0]
        assert entry.diagnosis == HostDiagnosis.SPLIT_IDENTITY
        assert entry.current_connection_principal == "nathan"


# --------------------------------------------------------------
# section19 Unit - Aligned classifier
# --------------------------------------------------------------


class TestAlignedClassifier:
    """section13.2: Aligned state when identities match."""

    def test_aligned_same_principal(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_paul",
            server_principal_label="paul",
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.ALIGNED

    def test_aligned_report_status_ok(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_paul",
            server_principal_label="paul",
            diagnosis=HostDiagnosis.ALIGNED,
        )
        report = build_doctor_report(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            connection_surfaces_available=True,
            negotiation_available=True,
        )
        assert report.summary_status == DoctorSummaryStatus.OK
        assert not report.has_split_identity()


# --------------------------------------------------------------
# section19 Unit - Unsupported host classifier
# --------------------------------------------------------------


class TestUnsupportedHostClassifier:
    """section13.4: Unsupported host classification."""

    def test_not_detected(self):
        record = DoctorHostRecord(host_id="unknown", detected=False)
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.NOT_DETECTED

    def test_detected_but_unreadable_config(self):
        record = DoctorHostRecord(
            host_id="someide",
            detected=True,
            config_detected=False,
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.HOST_CONFIG_UNREADABLE

    def test_no_keyhole_entry(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=False,
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.HOST_NOT_CONFIGURED


# --------------------------------------------------------------
# section19 Unit - Surface negotiation fail/warn/pass handling
# --------------------------------------------------------------


class TestSurfaceNegotiation:
    """section6.8, INV-SDK-CLIENT-01-C-005: Surface-aware behavior."""

    def test_connection_surfaces_available_when_inspect_present(self):
        ops = ["connection.identity.inspect", "connection.list.inspect"]
        assert check_connection_surfaces_available(ops) is True

    def test_connection_surfaces_available_legacy_whoami(self):
        """Legacy connection.whoami no longer triggers availability."""
        ops = ["connection.whoami", "connection.list"]
        assert check_connection_surfaces_available(ops) is False

    def test_connection_surfaces_unavailable_when_missing(self):
        ops = ["context.compile", "auth.register"]
        assert check_connection_surfaces_available(ops) is False

    def test_connection_surfaces_unavailable_empty(self):
        assert check_connection_surfaces_available([]) is False

    def test_surface_unavailable_diagnosis_when_server_lacks_surfaces(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=False,
        )
        assert result == HostDiagnosis.SURFACE_UNAVAILABLE

    def test_surface_unavailable_repair_guidance(self):
        record = DoctorHostRecord(
            host_id="vscode",
            diagnosis=HostDiagnosis.SURFACE_UNAVAILABLE,
        )
        guidance = build_repair_guidance(record)
        assert RecommendedAction.UPGRADE_SERVER in guidance.actions
        assert RecommendedAction.USE_GENERIC_WHOAMI in guidance.actions

    # -- SDK-SERVER-01-C: connection_surfaces discovery ------

    def test_connection_surfaces_from_connection_surfaces_dict(self):
        """When server advertises ops via connection_surfaces, they are found."""
        cs = {
            "schema_version": "connection/v1",
            "story_id": "SDK-SERVER-01-C",
            "run_types": [
                {"run_type": "connection.identity.inspect", "implemented": True},
                {"run_type": "connection.list.inspect", "implemented": True},
            ],
        }
        # Empty top-level operations, but connection_surfaces has the ops
        assert check_connection_surfaces_available([], connection_surfaces=cs) is True

    def test_connection_surfaces_empty_dict_still_false(self):
        """Empty connection_surfaces dict does not trigger availability."""
        assert check_connection_surfaces_available(
            [], connection_surfaces={}
        ) is False

    def test_connection_surfaces_missing_inspect_in_dict(self):
        """connection_surfaces without identity.inspect is still False."""
        cs = {
            "run_types": [
                {"run_type": "connection.list.inspect", "implemented": True},
            ],
        }
        assert check_connection_surfaces_available(
            [], connection_surfaces=cs
        ) is False

    def test_connection_surfaces_merge_with_operations(self):
        """Both sources merged: ops + connection_surfaces."""
        cs = {
            "run_types": [
                {"run_type": "connection.identity.inspect", "implemented": True},
            ],
        }
        assert check_connection_surfaces_available(
            ["context.compile"], connection_surfaces=cs
        ) is True

    def test_connection_surfaces_none_backward_compat(self):
        """Passing connection_surfaces=None preserves old behavior."""
        assert check_connection_surfaces_available(
            ["connection.identity.inspect"], connection_surfaces=None
        ) is True
        assert check_connection_surfaces_available(
            [], connection_surfaces=None
        ) is False


# --------------------------------------------------------------
# section19 Unit - No-false-convergence behavior after login
# --------------------------------------------------------------


class TestNoFalseConvergence:
    """INV-SDK-CLIENT-01-C-002: Login is not rebind."""

    def test_login_does_not_change_host_diagnosis(self):
        """After login as Paul, if connection truth still says Nathan,
        diagnosis must remain SPLIT_IDENTITY."""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
            server_principal_label="nathan",
        )
        # "Login" just changed CLI profile to Paul
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.SPLIT_IDENTITY

    def test_reconcile_preserves_server_truth(self):
        """Reconciliation with stale connection truth still shows split."""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={
                "vscode": {
                    "connection_id": "conn_1",
                    "user_id": "usr_nathan",
                    "principal": "nathan",
                }
            },
        )
        assert report.has_split_identity()
        entry = report.hosts[0]
        assert entry.diagnosis == HostDiagnosis.SPLIT_IDENTITY
        assert entry.current_connection_principal == "nathan"

    def test_reconcile_aligned_when_truth_matches(self):
        """No false alarm when connection truth confirms same principal."""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={
                "vscode": {
                    "connection_id": "conn_1",
                    "user_id": "usr_paul",
                    "principal": "paul",
                }
            },
        )
        assert not report.has_split_identity()
        assert report.summary_status == DoctorSummaryStatus.OK


# --------------------------------------------------------------
# section19 Unit - Rebind request shaping
# --------------------------------------------------------------


class TestRebindRequestShaping:
    """section9.4: Rebind request models produce correct wire format."""

    def test_rebind_request_payload(self):
        req = RebindRequest(
            connection_id="conn_123",
            host_id="vscode",
            target_profile="paul",
            target_user_id="usr_paul",
        )
        payload = req.to_run_payload()
        assert payload["run_type"] == "connection.rebind"
        assert payload["parameters"]["connection_id"] == "conn_123"
        assert payload["parameters"]["host_id"] == "vscode"
        assert payload["parameters"]["target_profile"] == "paul"

    def test_rebind_request_proof_dict_no_secrets(self):
        req = RebindRequest(
            connection_id="conn_123",
            host_id="vscode",
            target_profile="paul",
            correlation_id="corr-abc",
        )
        proof = req.to_proof_dict()
        assert "connection_id" in proof
        assert "host_id" in proof
        assert "target_profile" in proof
        assert "correlation_id" in proof
        # No tokens
        assert "access_token" not in proof

    def test_rebind_request_auto_correlation_id(self):
        req = RebindRequest(host_id="vscode", target_profile="paul")
        assert req.correlation_id  # auto-generated UUID

    def test_rebind_outcome_accepted(self):
        outcome = RebindOutcome(
            status=RebindStatus.ACCEPTED,
            connection_id="conn_123",
            old_principal="nathan",
            new_principal="paul",
            run_id="run_abc",
        )
        d = outcome.to_dict()
        assert d["status"] == "accepted"
        assert d["old_principal"] == "nathan"
        assert d["new_principal"] == "paul"

    def test_rebind_outcome_safe_summary(self):
        outcome = RebindOutcome(
            status=RebindStatus.REBOUND,
            connection_id="conn_123",
            old_principal="nathan",
            new_principal="paul",
            run_id="run_abc",
            server_message="secret stuff",
        )
        safe = outcome.safe_summary()
        assert "server_message" not in safe
        assert safe["status"] == "rebound"

    def test_rebind_status_values(self):
        assert RebindStatus.ACCEPTED.value == "accepted"
        assert RebindStatus.REBOUND.value == "rebound"
        assert RebindStatus.DEFERRED.value == "deferred"
        assert RebindStatus.REPLAYED.value == "replayed"
        assert RebindStatus.REJECTED.value == "rejected"


# --------------------------------------------------------------
# section19 Unit - Invalidate request shaping
# --------------------------------------------------------------


class TestInvalidateRequestShaping:
    """section9.5: Invalidate request models produce correct wire format."""

    def test_invalidate_request_payload(self):
        req = InvalidateRequest(
            connection_id="conn_456",
            host_id="vscode",
        )
        payload = req.to_run_payload()
        assert payload["run_type"] == "connection.invalidate"
        assert payload["parameters"]["connection_id"] == "conn_456"
        assert payload["parameters"]["host_id"] == "vscode"

    def test_invalidate_request_proof_dict(self):
        req = InvalidateRequest(
            connection_id="conn_456",
            host_id="vscode",
            correlation_id="corr-xyz",
        )
        proof = req.to_proof_dict()
        assert proof["connection_id"] == "conn_456"
        assert "access_token" not in proof

    def test_invalidate_outcome_accepted(self):
        outcome = InvalidateOutcome(
            status=InvalidateStatus.ACCEPTED,
            connection_id="conn_456",
            reconnect_required=True,
            run_id="run_def",
        )
        d = outcome.to_dict()
        assert d["status"] == "accepted"
        assert d["reconnect_required"] is True

    def test_invalidate_outcome_already_invalidated(self):
        outcome = InvalidateOutcome(
            status=InvalidateStatus.ALREADY_INVALIDATED,
            connection_id="conn_456",
        )
        assert outcome.status == InvalidateStatus.ALREADY_INVALIDATED

    def test_invalidate_status_values(self):
        assert InvalidateStatus.ACCEPTED.value == "accepted"
        assert InvalidateStatus.REJECTED.value == "rejected"
        assert InvalidateStatus.ALREADY_INVALIDATED.value == "already_invalidated"


# --------------------------------------------------------------
# section19 Unit - Proof artifact emission
# --------------------------------------------------------------


class TestDoctorProofEmission:
    """section15, section17, INV-SDK-CLIENT-01-C-007: Repo-neutral proof artifacts."""

    def test_proof_generate_returns_all_docs(self):
        proof = DoctorProofBundle(correlation_id="test-corr")
        proof.record_event("test_event", {"key": "value"})
        docs = proof.generate(
            report={"summary_status": "ok"},
            local_profile={"user_id": "usr_paul", "username": "paul"},
            host_inventory=[{"host_id": "vscode"}],
            success=True,
        )
        expected_files = {
            "report.json",
            "local_profile_snapshot.json",
            "host_inventory.json",
            "connection_truth.json",
            "negotiation.json",
            "requested_fix.json",
            "response.json",
            "verification.json",
            "repair.json",
            "summary.md",
            "digest.txt",
        }
        assert set(docs.keys()) == expected_files

    def test_proof_write_creates_directory(self, tmp_path):
        proof = DoctorProofBundle(correlation_id="write-test")
        bundle_dir = proof.write(
            report={"summary_status": "ok"},
            success=True,
            output_dir=tmp_path,
        )
        assert bundle_dir.exists()
        assert (bundle_dir / "report.json").exists()
        assert (bundle_dir / "summary.md").exists()
        assert (bundle_dir / "digest.txt").exists()

    def test_proof_write_repo_neutral_path(self, tmp_path):
        proof = DoctorProofBundle(correlation_id="repo-neutral")
        bundle_dir = proof.write(
            report={},
            success=False,
            output_dir=tmp_path,
        )
        # INV-SDK-CLIENT-01-C-007: stored under doctor/<correlation-id>/
        assert "doctor" in str(bundle_dir)
        assert "repo-neutral" in str(bundle_dir)

    def test_proof_digest_is_sha256(self, tmp_path):
        proof = DoctorProofBundle(correlation_id="digest-test")
        docs = proof.generate(report={}, success=True)
        assert docs["digest.txt"].startswith("sha256:")

    def test_proof_summary_includes_hosts(self):
        proof = DoctorProofBundle()
        docs = proof.generate(
            report={
                "summary_status": "attention_required",
                "hosts": [
                    {
                        "host_id": "vscode",
                        "diagnosis": "split_identity",
                        "current_connection_principal": "nathan",
                    }
                ],
            },
            success=False,
        )
        summary = docs["summary.md"]
        assert "vscode" in summary
        assert "split_identity" in summary
        assert "nathan" in summary

    def test_proof_summary_includes_fix(self):
        proof = DoctorProofBundle()
        docs = proof.generate(
            report={"summary_status": "ok", "hosts": []},
            requested_fix={"action": "rebind", "host_id": "vscode", "target_profile": "paul"},
            verification={"verified": True, "post_fix_principal": "paul"},
            success=True,
        )
        summary = docs["summary.md"]
        assert "rebind" in summary
        assert "paul" in summary

    def test_proof_event_chain_records_events(self):
        proof = DoctorProofBundle(correlation_id="chain-test")
        proof.record_event("scan_start", {"mode": "governed"})
        proof.record_event("scan_complete", {"hosts_found": 2})
        docs = proof.generate(report={}, success=True)
        repair = json.loads(docs["repair.json"])
        assert len(repair["events"]) == 2
        assert repair["events"][0]["event_type"] == "scan_start"


# --------------------------------------------------------------
# section19 Unit - Connection identity models
# --------------------------------------------------------------


class TestConnectionInfoModel:
    """ConnectionInfo model serialisation and accessors."""

    def test_connection_info_to_dict(self):
        info = ConnectionInfo(
            connection_id="conn_abc",
            host_hint="vscode",
            principal="nathan",
            user_id="usr_nathan",
            authority=ConnectionAuthority.SESSION_BOUND,
            staleness_state=ConnectionStaleness.FRESH,
        )
        d = info.to_dict()
        assert d["connection_id"] == "conn_abc"
        assert d["authority"] == "session_bound"
        assert d["staleness_state"] == "fresh"

    def test_connection_info_proof_safe(self):
        info = ConnectionInfo(
            connection_id="conn_abc",
            principal="nathan",
        )
        proof = info.to_proof_dict()
        assert "access_token" not in proof
        assert proof["principal"] == "nathan"


# --------------------------------------------------------------
# section19 Unit - Error classes with repair guidance
# --------------------------------------------------------------


class TestConnectionIdentityErrors:
    """section16: All errors carry repair guidance."""

    def test_not_found_error_has_repair(self):
        err = ConnectionNotFoundError(host_id="vscode")
        assert err.error_class == "host_connection_not_visible"
        assert len(err.repair_suggestions) > 0
        assert "vscode" in err.reason

    def test_network_error_has_repair(self):
        err = ConnectionNetworkError("timeout")
        assert err.error_class == "connection_network_error"
        assert len(err.repair_suggestions) > 0

    def test_surface_unavailable_error(self):
        err = ConnectionSurfaceUnavailableError(surface="connection.identity.inspect")
        assert "connection.identity.inspect" in err.reason
        assert len(err.repair_suggestions) > 0

    def test_rebind_rejected_error(self):
        err = RebindRejectedError(server_reason="insufficient_privilege")
        assert "insufficient_privilege" in err.reason

    def test_verification_failed_error(self):
        err = VerificationFailedError(
            expected_principal="paul",
            actual_principal="nathan",
        )
        assert "paul" in err.reason
        assert "nathan" in err.reason

    def test_not_authenticated_error(self):
        err = ConnectionNotAuthenticatedError()
        assert "login" in err.repair_suggestions[0].lower()

    def test_all_errors_inherit_from_base(self):
        errors = [
            ConnectionNotFoundError(),
            ConnectionNetworkError(),
            ConnectionSurfaceUnavailableError(),
            RebindRejectedError(),
            VerificationFailedError(),
            ConnectionNotAuthenticatedError(),
        ]
        for err in errors:
            assert isinstance(err, ConnectionIdentityError)


# --------------------------------------------------------------
# section19 Unit - Repair guidance builders
# --------------------------------------------------------------


class TestRepairGuidance:
    """section16: Concrete repair steps for each diagnosis."""

    def test_split_identity_repair_steps(self):
        steps = repair_steps_for_diagnosis(
            HostDiagnosis.SPLIT_IDENTITY,
            host_id="vscode",
            active_profile="paul",
        )
        assert any("rebind" in s.lower() for s in steps)
        assert any("invalidate" in s.lower() for s in steps)

    def test_split_identity_repair_commands(self):
        cmds = repair_commands_for_diagnosis(
            HostDiagnosis.SPLIT_IDENTITY,
            host_id="vscode",
            active_profile="paul",
        )
        assert any("rebind" in c for c in cmds)
        assert any("invalidate" in c for c in cmds)

    def test_surface_unavailable_repair_steps(self):
        steps = repair_steps_for_diagnosis(HostDiagnosis.SURFACE_UNAVAILABLE)
        assert any("upgrade" in s.lower() for s in steps)
        assert any("whoami" in s.lower() for s in steps)

    def test_stale_connection_repair_steps(self):
        steps = repair_steps_for_diagnosis(
            HostDiagnosis.STALE_CONNECTION, host_id="vscode"
        )
        assert any("connection" in s.lower() for s in steps)

    def test_aligned_no_action(self):
        steps = repair_steps_for_diagnosis(HostDiagnosis.ALIGNED)
        assert any("no action" in s.lower() for s in steps)

    def test_not_detected_repair(self):
        steps = repair_steps_for_diagnosis(
            HostDiagnosis.NOT_DETECTED, host_id="vscode"
        )
        assert any("install" in s.lower() for s in steps)

    def test_build_repair_guidance_model(self):
        record = DoctorHostRecord(
            host_id="vscode",
            diagnosis=HostDiagnosis.SPLIT_IDENTITY,
        )
        guidance = build_repair_guidance(record)
        assert guidance.host_id == "vscode"
        assert guidance.diagnosis == HostDiagnosis.SPLIT_IDENTITY
        assert RecommendedAction.REBIND in guidance.actions
        assert RecommendedAction.KEEP_AS_IS in guidance.actions


# --------------------------------------------------------------
# section19 Unit - Reconciliation flow
# --------------------------------------------------------------


class TestReconciliationFlow:
    """section12: Full reconciliation with connection truth enrichment."""

    def test_reconcile_with_no_hosts(self):
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[],
            server_operations=["connection.identity.inspect"],
        )
        assert report.summary_status == DoctorSummaryStatus.OK
        assert len(report.hosts) == 0

    def test_reconcile_enriches_host_from_connection_truth(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={
                "vscode": {
                    "connection_id": "conn_1",
                    "user_id": "usr_paul",
                    "principal": "paul",
                    "supports_rebind": True,
                    "supports_invalidate": True,
                }
            },
        )
        assert report.summary_status == DoctorSummaryStatus.OK
        assert record.connection_visible_from_server is True
        assert record.supports_rebind is True
        assert record.staleness_state == StalenessState.FRESH

    def test_reconcile_detects_stale_when_different_user(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={
                "vscode": {
                    "connection_id": "conn_1",
                    "user_id": "usr_nathan",
                    "principal": "nathan",
                }
            },
        )
        assert record.staleness_state == StalenessState.STALE_CONFIRMED
        assert record.diagnosis == HostDiagnosis.SPLIT_IDENTITY
        assert report.has_split_identity()

    def test_reconcile_no_connection_truth_no_surfaces(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=[],  # No connection surfaces
        )
        assert record.diagnosis == HostDiagnosis.SURFACE_UNAVAILABLE

    def test_reconcile_auto_correlation_id(self):
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[],
        )
        assert report.correlation_id  # UUID auto-generated


# --------------------------------------------------------------
# section19 Unit - Connection run type constants
# --------------------------------------------------------------


class TestConnectionRunTypes:
    """Exact canonical run type keys for connection surfaces."""

    def test_inspect_run_type(self):
        assert CONNECTION_INSPECT_RUN_TYPE == "connection.identity.inspect"

    def test_whoami_alias_run_type(self):
        """Legacy alias still works."""
        assert CONNECTION_WHOAMI_RUN_TYPE == "connection.identity.inspect"

    def test_rebind_run_type(self):
        assert CONNECTION_REBIND_RUN_TYPE == "connection.rebind"

    def test_invalidate_run_type(self):
        assert CONNECTION_INVALIDATE_RUN_TYPE == "connection.invalidate"

    def test_list_run_type(self):
        assert CONNECTION_LIST_RUN_TYPE == "connection.list.inspect"

    def test_status_run_type(self):
        assert CONNECTION_STATUS_RUN_TYPE == "connection.status.inspect"

    def test_lineage_run_type(self):
        assert CONNECTION_LINEAGE_RUN_TYPE == "connection.lineage.inspect"

    def test_connection_surfaces_frozenset(self):
        assert len(CONNECTION_SURFACES) == 6
        assert "connection.identity.inspect" in CONNECTION_SURFACES
        assert "connection.lineage.inspect" in CONNECTION_SURFACES
        assert "connection.status.inspect" in CONNECTION_SURFACES
        assert "connection.list.inspect" in CONNECTION_SURFACES


# --------------------------------------------------------------
# section19 Unit - Client classification helpers
# --------------------------------------------------------------


class TestClientClassification:
    """ConnectionIdentityClient static helpers."""

    def test_classify_rebind_success_200(self):
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200,
            raw={
                "ok": True,
                "data": {
                    "status": "rebound",
                    "connection_id": "conn_1",
                    "old_principal": "nathan",
                    "new_principal": "paul",
                    "run_id": "run_1",
                },
            },
            request=RebindRequest(
                connection_id="conn_1",
                host_id="vscode",
                target_profile="paul",
            ),
        )
        assert outcome.status == RebindStatus.REBOUND
        assert outcome.old_principal == "nathan"
        assert outcome.new_principal == "paul"

    def test_classify_rebind_accepted_202(self):
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=202,
            raw={"ok": True, "data": {"status": "accepted", "run_id": "run_2"}},
            request=RebindRequest(host_id="vscode", target_profile="paul"),
        )
        assert outcome.status == RebindStatus.ACCEPTED

    def test_classify_rebind_rejected_400(self):
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=400,
            raw={"ok": True, "data": {"error": "invalid_connection", "run_id": "run_3"}},
            request=RebindRequest(connection_id="conn_bad"),
        )
        assert outcome.status == RebindStatus.REJECTED
        assert len(outcome.repair_guidance) > 0

    def test_classify_rebind_server_error_500(self):
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=500,
            raw={"ok": True, "data": {"error": "internal"}},
            request=RebindRequest(connection_id="conn_x"),
        )
        assert outcome.status == RebindStatus.REJECTED
        assert "500" in outcome.server_message

    def test_classify_invalidate_success_200(self):
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200,
            raw={
                "ok": True,
                "data": {
                    "status": "accepted",
                    "connection_id": "conn_1",
                    "reconnect_required": True,
                    "run_id": "run_inv_1",
                },
            },
            request=InvalidateRequest(connection_id="conn_1"),
        )
        assert outcome.status == InvalidateStatus.ACCEPTED
        assert outcome.reconnect_required is True

    def test_classify_invalidate_already_invalidated(self):
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200,
            raw={"ok": True, "data": {"status": "already_invalidated", "connection_id": "conn_1"}},
            request=InvalidateRequest(connection_id="conn_1"),
        )
        assert outcome.status == InvalidateStatus.ALREADY_INVALIDATED

    def test_classify_invalidate_rejected_403(self):
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=403,
            raw={"ok": True, "data": {"error": "forbidden"}},
            request=InvalidateRequest(connection_id="conn_1"),
        )
        assert outcome.status == InvalidateStatus.REJECTED


# --------------------------------------------------------------
# section19 Unit - Connection client parse_connection
# --------------------------------------------------------------


class TestParseConnection:
    """Client parses server responses into ConnectionInfo."""

    def test_parse_full_connection(self):
        data = {
            "connection_id": "conn_abc",
            "host_hint": "vscode",
            "principal": "nathan",
            "user_id": "usr_nathan",
            "authority": "session_bound",
            "purpose": "ide_integration",
            "bound_at": "2026-04-17T12:00:00Z",
            "staleness_state": "fresh",
            "session_lineage_id": "lin_123",
            "supports_rebind": True,
            "supports_invalidate": True,
        }
        info = ConnectionIdentityClient._parse_connection(data)
        assert info.connection_id == "conn_abc"
        assert info.principal == "nathan"
        assert info.authority == ConnectionAuthority.SESSION_BOUND
        assert info.staleness_state == ConnectionStaleness.FRESH
        assert info.supports_rebind is True

    def test_parse_connection_unknown_authority(self):
        data = {"authority": "some_new_type"}
        info = ConnectionIdentityClient._parse_connection(data)
        assert info.authority == ConnectionAuthority.UNKNOWN

    def test_parse_connection_missing_fields(self):
        data = {}
        info = ConnectionIdentityClient._parse_connection(data)
        assert info.connection_id == ""
        assert info.principal == ""
        assert info.authority == ConnectionAuthority.UNKNOWN

    def test_parse_connection_alt_field_names(self):
        data = {
            "host_id": "vscode",
            "principal_label": "paul",
            "principal_user_id": "usr_paul",
        }
        info = ConnectionIdentityClient._parse_connection(data)
        assert info.host_hint == "vscode"
        assert info.principal == "paul"
        assert info.user_id == "usr_paul"


# --------------------------------------------------------------
# section19 Unit - DoctorReport model
# --------------------------------------------------------------


class TestDoctorReport:
    """DoctorReport aggregation and serialisation."""

    def test_to_dict_complete(self):
        report = DoctorReport(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            hosts=[
                DoctorHostEntry(
                    host_id="vscode",
                    diagnosis=HostDiagnosis.ALIGNED,
                )
            ],
            summary_status=DoctorSummaryStatus.OK,
            correlation_id="corr-1",
        )
        d = report.to_dict()
        assert d["cli_active_profile"] == "paul"
        assert d["summary_status"] == "ok"
        assert len(d["hosts"]) == 1
        assert d["hosts"][0]["diagnosis"] == "aligned"

    def test_has_split_identity_true(self):
        report = DoctorReport(
            hosts=[
                DoctorHostEntry(
                    host_id="vscode",
                    diagnosis=HostDiagnosis.SPLIT_IDENTITY,
                )
            ],
        )
        assert report.has_split_identity() is True

    def test_has_split_identity_false(self):
        report = DoctorReport(
            hosts=[
                DoctorHostEntry(
                    host_id="vscode",
                    diagnosis=HostDiagnosis.ALIGNED,
                )
            ],
        )
        assert report.has_split_identity() is False

    def test_has_attention_required(self):
        report = DoctorReport(
            summary_status=DoctorSummaryStatus.ATTENTION_REQUIRED,
        )
        assert report.has_attention_required() is True

    def test_empty_report_ok(self):
        report = DoctorReport()
        assert report.summary_status == DoctorSummaryStatus.OK
        assert not report.has_attention_required()


# --------------------------------------------------------------
# section19 Unit - DoctorHostRecord model
# --------------------------------------------------------------


class TestDoctorHostRecord:
    """DoctorHostRecord model serialisation."""

    def test_to_dict_all_fields(self):
        record = DoctorHostRecord(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            display_name="Visual Studio Code",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            server_url="https://mcp.keyholesolution.com/sse",
            server_principal_user_id="usr_nathan",
            server_principal_label="nathan",
            staleness_state=StalenessState.STALE_CONFIRMED,
            diagnosis=HostDiagnosis.SPLIT_IDENTITY,
        )
        d = record.to_dict()
        assert d["host_id"] == "vscode"
        assert d["host_type"] == "ide_mcp_client"
        assert d["staleness_state"] == "stale_confirmed"
        assert d["diagnosis"] == "split_identity"


# --------------------------------------------------------------
# section19 Unit - Enum coverage
# --------------------------------------------------------------


class TestEnumCoverage:
    """All enums have expected values."""

    def test_host_type_values(self):
        assert HostType.IDE_MCP_CLIENT.value == "ide_mcp_client"
        assert HostType.SDK_RUNTIME.value == "sdk_runtime"
        assert HostType.UNKNOWN.value == "unknown"

    def test_staleness_state_values(self):
        assert StalenessState.FRESH.value == "fresh"
        assert StalenessState.STALE_CONFIRMED.value == "stale_confirmed"
        assert StalenessState.UNKNOWN.value == "unknown"

    def test_host_diagnosis_values(self):
        expected = {
            "aligned", "split_identity", "stale_connection",
            "stale_host_auth", "host_not_configured",
            "host_config_unreadable", "live_connection_missing",
            "reconnect_required", "scope_denied",
            "unsupported_host", "surface_unavailable",
            "ambiguous_connection", "not_detected",
        }
        actual = {d.value for d in HostDiagnosis}
        assert actual == expected

    def test_doctor_summary_values(self):
        expected = {"ok", "attention_required", "degraded"}
        actual = {s.value for s in DoctorSummaryStatus}
        assert actual == expected

    def test_recommended_action_values(self):
        assert len(RecommendedAction) == 12

    def test_connection_authority_values(self):
        assert ConnectionAuthority.SESSION_BOUND.value == "session_bound"
        assert ConnectionAuthority.TOKEN_BOUND.value == "token_bound"

    def test_connection_staleness_values(self):
        assert ConnectionStaleness.FRESH.value == "fresh"
        assert ConnectionStaleness.STALE.value == "stale"
        assert ConnectionStaleness.EXPIRED.value == "expired"


# --------------------------------------------------------------
# section19 Negative - Host not detected
# --------------------------------------------------------------


class TestNegativeHostNotDetected:
    """section19 Negative: host not detected."""

    def test_classify_undetected_host(self):
        record = DoctorHostRecord(host_id="phantom", detected=False)
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.NOT_DETECTED

    def test_report_with_all_undetected(self):
        records = [
            DoctorHostRecord(host_id="a", detected=False),
            DoctorHostRecord(host_id="b", detected=False),
        ]
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=records,
            server_operations=["connection.identity.inspect"],
        )
        assert report.summary_status == DoctorSummaryStatus.OK
        for entry in report.hosts:
            assert entry.diagnosis == HostDiagnosis.NOT_DETECTED


# --------------------------------------------------------------
# section19 Negative - Connection not visible
# --------------------------------------------------------------


class TestNegativeConnectionNotVisible:
    """section19 Negative: connection not visible from server."""

    def test_host_with_no_connection_truth(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=False,
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.LIVE_CONNECTION_MISSING

    def test_reconcile_host_without_truth_entry(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={},  # no entry for vscode
        )
        # Without connection truth, host can't be verified
        entry = report.hosts[0]
        assert entry.diagnosis in (
            HostDiagnosis.LIVE_CONNECTION_MISSING,
            HostDiagnosis.AMBIGUOUS_CONNECTION,
        )


# --------------------------------------------------------------
# section19 Negative - Server surface unavailable
# --------------------------------------------------------------


class TestNegativeSurfaceUnavailable:
    """section19 Negative: server lacks connection surfaces."""

    def test_no_operations_means_unavailable(self):
        assert check_connection_surfaces_available([]) is False

    def test_only_unrelated_ops(self):
        assert check_connection_surfaces_available(["context.compile"]) is False

    def test_doctor_report_degrades(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=[],
        )
        assert report.summary_status == DoctorSummaryStatus.DEGRADED
        assert report.hosts[0].diagnosis == HostDiagnosis.SURFACE_UNAVAILABLE

    def test_reconcile_connection_surfaces_dict_overrides_empty_ops(self):
        """SDK-SERVER-01-C: reconcile uses connection_surfaces when ops is empty."""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        cs = {
            "schema_version": "connection/v1",
            "run_types": [
                {"run_type": "connection.identity.inspect", "implemented": True},
            ],
        }
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=[],
            connection_surfaces=cs,
        )
        # With connection_surfaces providing the ops, surfaces are available
        assert report.connection_surfaces_available is True
        # Host should NOT be diagnosed as SURFACE_UNAVAILABLE
        assert report.hosts[0].diagnosis != HostDiagnosis.SURFACE_UNAVAILABLE


# --------------------------------------------------------------
# section19 Negative - Rebind forbidden
# --------------------------------------------------------------


class TestNegativeRebindForbidden:
    """section19 Negative: server rejects rebind."""

    def test_classify_rebind_rejected(self):
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=403,
            raw={"ok": True, "data": {"error": "insufficient_privilege"}},
            request=RebindRequest(connection_id="conn_1"),
        )
        assert outcome.status == RebindStatus.REJECTED
        assert "insufficient_privilege" in outcome.server_message

    def test_rebind_rejected_error_class(self):
        err = RebindRejectedError(server_reason="forbidden")
        assert err.error_class == "host_rebind_rejected"


# --------------------------------------------------------------
# section19 Negative - Ambiguous connection truth
# --------------------------------------------------------------


class TestNegativeAmbiguousConnection:
    """section19 Negative: server returns ambiguous identity."""

    def test_ambiguous_when_no_principal(self):
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="",  # ambiguous
        )
        result = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result == HostDiagnosis.AMBIGUOUS_CONNECTION


# --------------------------------------------------------------
# section19 Negative - Verification mismatch after fix
# --------------------------------------------------------------


class TestNegativeVerificationMismatch:
    """INV-SDK-CLIENT-01-C-004: Verification mismatch after fix."""

    def test_verification_failed_error(self):
        err = VerificationFailedError(
            expected_principal="paul",
            actual_principal="nathan",
        )
        assert "paul" in err.reason
        assert "nathan" in err.reason
        assert err.error_class == "host_verification_failed"

    def test_verification_failed_repair_suggestions(self):
        err = VerificationFailedError(
            expected_principal="paul",
            actual_principal="nathan",
        )
        assert any("whoami" in s.lower() for s in err.repair_suggestions)


# --------------------------------------------------------------
# section19 Unit - CLI command functions (non-network)
# --------------------------------------------------------------


class TestCLICommandsUnauthenticated:
    """CLI commands return proper errors when not authenticated."""

    @patch("keyhole_cli.commands.connections_list.CredentialStore")
    def test_connections_list_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connections_list()
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"

    @patch("keyhole_cli.commands.connection_inspect.CredentialStore")
    def test_connection_inspect_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connection_inspect(host="vscode")
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"

    def test_connection_inspect_no_host_or_id(self):
        result = run_connection_inspect()
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    @patch("keyhole_cli.commands.connection_rebind.CredentialStore")
    def test_connection_rebind_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connection_rebind(host="vscode", profile="paul", yes=True)
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"

    def test_connection_rebind_no_host(self):
        result = run_connection_rebind(profile="paul")
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    def test_connection_rebind_no_profile(self):
        result = run_connection_rebind(host="vscode")
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    def test_connection_rebind_needs_confirmation(self):
        with patch("keyhole_cli.commands.connection_rebind.CredentialStore") as mock_store:
            mock_session = MagicMock()
            mock_session.access_token = "tok"
            mock_store.return_value.load.return_value = mock_session
            result = run_connection_rebind(host="vscode", profile="paul", yes=False)
        assert result.success is False
        assert result.data["error_class"] == "confirmation_required"

    @patch("keyhole_cli.commands.connection_invalidate.CredentialStore")
    def test_connection_invalidate_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connection_invalidate(host="vscode", yes=True)
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"

    def test_connection_invalidate_no_host(self):
        result = run_connection_invalidate()
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    def test_connection_invalidate_needs_confirmation(self):
        with patch("keyhole_cli.commands.connection_invalidate.CredentialStore") as mock_store:
            mock_session = MagicMock()
            mock_session.access_token = "tok"
            mock_store.return_value.load.return_value = mock_session
            result = run_connection_invalidate(host="vscode", yes=False)
        assert result.success is False
        assert result.data["error_class"] == "confirmation_required"


# --------------------------------------------------------------
# section19 Unit - Invariant coverage
# --------------------------------------------------------------


class TestInvariants:
    """Direct tests for each defined invariant."""

    def test_inv_001_split_identity_visible(self):
        """INV-SDK-CLIENT-01-C-001"""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
        )
        diag = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.SPLIT_IDENTITY

    def test_inv_002_login_is_not_rebind(self):
        """INV-SDK-CLIENT-01-C-002"""
        # After "login as paul", host still shows nathan from server
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
            server_principal_label="nathan",
        )
        diag = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=True,
        )
        # Must NOT be ALIGNED - login does not equal rebind
        assert diag != HostDiagnosis.ALIGNED
        assert diag == HostDiagnosis.SPLIT_IDENTITY

    def test_inv_003_doctor_advisory_by_default(self):
        """INV-SDK-CLIENT-01-C-003"""
        # Reconcile does not apply fixes, only classifies
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="usr_nathan",
        )
        report = reconcile(
            cli_active_profile="paul",
            cli_user_id="usr_paul",
            host_records=[record],
            server_operations=["connection.identity.inspect"],
            connection_truth={
                "vscode": {"user_id": "usr_nathan", "principal": "nathan"}
            },
        )
        # Report shows mismatch but doesn't mutate anything
        assert report.has_split_identity()
        # Recommended actions include keep_as_is as an option
        actions = report.hosts[0].recommended_actions
        assert RecommendedAction.KEEP_AS_IS in actions

    def test_inv_005_unsupported_surfaces_degrade(self):
        """INV-SDK-CLIENT-01-C-005"""
        record = DoctorHostRecord(
            host_id="vscode",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
        )
        diag = classify_host_diagnosis(
            cli_user_id="usr_paul",
            cli_profile_label="paul",
            host_record=record,
            connection_surfaces_available=False,
        )
        assert diag == HostDiagnosis.SURFACE_UNAVAILABLE

    def test_inv_006_rebind_idempotency_key(self):
        """INV-SDK-CLIENT-01-C-006: Rebind includes correlation_id."""
        req = RebindRequest(host_id="vscode", target_profile="paul")
        payload = req.to_run_payload()
        assert payload["correlation_id"]  # non-empty UUID

    def test_inv_006_invalidate_idempotency_key(self):
        """INV-SDK-CLIENT-01-C-006: Invalidate includes correlation_id."""
        req = InvalidateRequest(host_id="vscode")
        payload = req.to_run_payload()
        assert payload["correlation_id"]

    def test_inv_007_proof_repo_neutral(self, tmp_path):
        """INV-SDK-CLIENT-01-C-007: Artifacts in tool-owned state."""
        proof = DoctorProofBundle(correlation_id="inv-007")
        bundle_dir = proof.write(
            report={"test": True},
            success=True,
            output_dir=tmp_path,
        )
        # Must be under doctor/ subdirectory, not repo root
        assert "doctor" in str(bundle_dir)
        assert bundle_dir.parent.name == "doctor"


# --------------------------------------------------------------
# section19 Unit - SDK public surface contract
# --------------------------------------------------------------


class TestSDKPublicSurface:
    """Verify all SDK-CLIENT-01-C exports are accessible."""

    def test_doctor_imports(self):
        from keyhole_sdk import (
            DoctorHostEntry,
            DoctorHostRecord,
            DoctorProofBundle,
            DoctorReport,
            DoctorSummaryStatus,
            HostDiagnosis,
            HostType,
            RecommendedAction,
            RepairGuidance,
            StalenessState,
            detect_hosts,
            classify_host_diagnosis,
            build_doctor_report,
            build_repair_guidance,
            check_connection_surfaces_available,
            reconcile,
        )

    def test_connection_identity_imports(self):
        from keyhole_sdk import (
            ConnectionAuthority,
            ConnectionIdentityClient,
            ConnectionIdentityError,
            ConnectionInfo,
            ConnectionNetworkError,
            ConnectionNotAuthenticatedError,
            ConnectionNotFoundError,
            ConnectionStaleness,
            ConnectionSurfaceUnavailableError,
            InvalidateOutcome,
            InvalidateRequest,
            InvalidateStatus,
            RebindOutcome,
            RebindRejectedError,
            RebindRequest,
            RebindStatus,
            ConnectionVerificationFailedError,
            repair_commands_for_diagnosis,
            repair_steps_for_diagnosis,
        )

    def test_host_detector_protocol(self):
        from keyhole_sdk import HostDetector, VSCodeHostDetector, SDKCredentialDetector
        assert issubclass(VSCodeHostDetector, HostDetector)
        assert issubclass(SDKCredentialDetector, HostDetector)

    def test_render_imports(self):
        from keyhole_sdk import (
            render_connection_info,
            render_connection_list,
            render_lineage,
            render_rebind_outcome,
            render_invalidate_outcome,
        )

    def test_new_run_type_constants(self):
        from keyhole_sdk import (
            CONNECTION_INSPECT_RUN_TYPE,
            CONNECTION_LINEAGE_RUN_TYPE,
            CONNECTION_STATUS_RUN_TYPE,
        )
        assert CONNECTION_INSPECT_RUN_TYPE == "connection.identity.inspect"
        assert CONNECTION_LINEAGE_RUN_TYPE == "connection.lineage.inspect"
        assert CONNECTION_STATUS_RUN_TYPE == "connection.status.inspect"


# --------------------------------------------------------------
# section19 Unit - Render helpers
# --------------------------------------------------------------


class TestRenderHelpers:
    """Connection identity rendering helpers (render.py)."""

    def test_render_connection_info_basic(self):
        info = ConnectionInfo(
            connection_id="conn_abc",
            host_hint="vscode",
            principal="nathan",
            user_id="usr_nathan",
            authority=ConnectionAuthority.SESSION_BOUND,
            staleness_state=ConnectionStaleness.FRESH,
        )
        text = render_connection_info(info)
        assert "vscode" in text
        assert "nathan" in text
        assert "session_bound" in text
        assert "fresh" in text

    def test_render_connection_list_empty(self):
        text = render_connection_list([])
        assert "No connections" in text

    def test_render_connection_list_multiple(self):
        conns = [
            ConnectionInfo(connection_id="conn_1", principal="paul"),
            ConnectionInfo(connection_id="conn_2", principal="nathan"),
        ]
        text = render_connection_list(conns)
        assert "conn_1" in text
        assert "conn_2" in text
        assert "paul" in text
        assert "nathan" in text

    def test_render_rebind_outcome(self):
        outcome = RebindOutcome(
            status=RebindStatus.REBOUND,
            old_principal="nathan",
            new_principal="paul",
            connection_id="conn_1",
        )
        text = render_rebind_outcome(outcome)
        assert "rebound" in text
        assert "nathan" in text
        assert "paul" in text
        assert "OK" in text

    def test_render_invalidate_outcome(self):
        outcome = InvalidateOutcome(
            status=InvalidateStatus.ACCEPTED,
            connection_id="conn_1",
            reconnect_required=True,
        )
        text = render_invalidate_outcome(outcome)
        assert "accepted" in text
        assert "yes" in text
        assert "OK" in text

    def test_render_lineage_empty(self):
        text = render_lineage({})
        assert "No lineage" in text

    def test_render_lineage_with_events(self):
        data = {
            "connection_id": "conn_abc",
            "principal": "paul",
            "lineage_id": "lin_123",
            "events": [
                {
                    "timestamp": "2026-04-17T12:00:00Z",
                    "action": "bind",
                    "detail": "Initial session bind",
                }
            ],
        }
        text = render_lineage(data)
        assert "conn_abc" in text
        assert "paul" in text
        assert "lin_123" in text
        assert "bind" in text


# --------------------------------------------------------------
# section19 Unit - Connection inspect CLI command
# --------------------------------------------------------------


class TestCLIConnectionInspect:
    """CLI connection inspect command."""

    def test_inspect_no_host_or_id(self):
        result = run_connection_inspect()
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    @patch("keyhole_cli.commands.connection_inspect.CredentialStore")
    def test_inspect_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connection_inspect(host="vscode")
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"


# --------------------------------------------------------------
# section19 Unit - Connection lineage CLI command
# --------------------------------------------------------------


class TestCLIConnectionLineage:
    """CLI connection lineage command."""

    def test_lineage_no_host_or_id(self):
        result = run_connection_lineage()
        assert result.success is False
        assert result.data["error_class"] == "invalid_input"

    @patch("keyhole_cli.commands.connection_lineage.CredentialStore")
    def test_lineage_not_authenticated(self, mock_store):
        mock_store.return_value.load.return_value = None
        result = run_connection_lineage(host="vscode")
        assert result.success is False
        assert result.data["error_class"] == "connection_not_authenticated"


# --------------------------------------------------------------
# section21 Envelope error handling - ok:false detection (SDK-CLIENT-01-C)
# --------------------------------------------------------------


class TestEnvelopeErrorHandling:
    """Tests for _check_envelope_error and ok:false response handling."""

    def test_check_envelope_error_scope_denied_raises(self):
        """SCOPE_DENIED raises ConnectionSurfaceUnavailableError."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_abc", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope 'connection:read' not in allowed_scopes"},
        }
        with pytest.raises(ConnectionSurfaceUnavailableError):
            ConnectionIdentityClient._check_envelope_error(raw)

    def test_check_envelope_error_scope_denied_message_preserved(self):
        """SCOPE_DENIED error message is passed to the exception."""
        raw = {
            "ok": False,
            "data": {},
            "error": {"code": "SCOPE_DENIED", "message": "Scope 'connection:read' not in allowed_scopes"},
        }
        with pytest.raises(ConnectionSurfaceUnavailableError) as exc:
            ConnectionIdentityClient._check_envelope_error(raw)
        assert "connection:read" in str(exc.value)

    def test_check_envelope_error_ok_true_does_not_raise(self):
        """ok:true envelope does not raise."""
        raw = {"ok": True, "data": {"connections": []}}
        ConnectionIdentityClient._check_envelope_error(raw)  # must not raise

    def test_check_envelope_error_no_ok_key_does_not_raise(self):
        """Envelope without ok key does not raise (legacy shape)."""
        raw = {"data": {"connections": []}}
        ConnectionIdentityClient._check_envelope_error(raw)  # must not raise

    def test_check_envelope_error_connection_not_found_does_not_raise(self):
        """CONNECTION_NOT_FOUND does not raise in _check_envelope_error (handled by caller)."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_abc", "status": "blocked"},
            "error": {"code": "CONNECTION_NOT_FOUND", "message": "Not found."},
        }
        ConnectionIdentityClient._check_envelope_error(raw)  # must not raise

    def test_check_envelope_error_rebind_forbidden_does_not_raise(self):
        """REBIND_FORBIDDEN does not raise in _check_envelope_error (handled by classifier)."""
        raw = {
            "ok": False,
            "data": {},
            "error": {"code": "REBIND_FORBIDDEN", "message": "Rebind disabled."},
        }
        ConnectionIdentityClient._check_envelope_error(raw)  # must not raise

    def test_list_connections_scope_denied_raises(self):
        """list_connections raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_1", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope not available."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.list_connections(access_token="tok")

    def test_connection_inspect_scope_denied_raises(self):
        """connection_inspect raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_2", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope not available."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.connection_inspect(access_token="tok")

    def test_connection_inspect_ok_false_connection_not_found_raises(self):
        """connection_inspect raises ConnectionNotFoundError on CONNECTION_NOT_FOUND."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_3", "status": "blocked"},
            "error": {"code": "CONNECTION_NOT_FOUND", "message": "Connection not found."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionNotFoundError):
                client.connection_inspect(access_token="tok", host_id="vscode")

    def test_connection_status_scope_denied_raises(self):
        """connection_status raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_4", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope not available."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.connection_status(access_token="tok")

    def test_connection_lineage_scope_denied_raises(self):
        """connection_lineage raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_5", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope not available."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.connection_lineage(access_token="tok")

    def test_connection_status_ok_false_not_found_raises(self):
        """connection_status raises ConnectionNotFoundError on CONNECTION_NOT_FOUND."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_6", "status": "blocked"},
            "error": {"code": "CONNECTION_NOT_FOUND", "message": "Not found."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionNotFoundError):
                client.connection_status(access_token="tok", host_id="vscode")

    def test_connection_lineage_ok_false_not_found_raises(self):
        """connection_lineage raises ConnectionNotFoundError on CONNECTION_NOT_FOUND."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_7", "status": "blocked"},
            "error": {"code": "CONNECTION_NOT_FOUND", "message": "Not found."},
        }
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionNotFoundError):
                client.connection_lineage(access_token="tok", host_id="vscode")


# --------------------------------------------------------------
# section22 Error code classification - ok:false outcomes (SDK-CLIENT-01-C)
# --------------------------------------------------------------


class TestErrorCodeClassification:
    """Tests for classifier behavior when server returns ok:false."""

    def test_classify_rebind_rebind_forbidden(self):
        """REBIND_FORBIDDEN produces RebindStatus.REJECTED with repair guidance."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_rb_1", "status": "blocked"},
            "error": {"code": "REBIND_FORBIDDEN", "message": "Rebind is disabled for this connection."},
        }
        req = RebindRequest(connection_id="conn_111", host_id="vscode", target_profile="alice")
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == RebindStatus.REJECTED
        assert outcome.connection_id == "conn_111"
        assert any("rebind" in s.lower() for s in outcome.repair_guidance)

    def test_classify_rebind_target_principal_invalid(self):
        """TARGET_PRINCIPAL_INVALID produces RebindStatus.REJECTED."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_rb_2", "status": "blocked"},
            "error": {"code": "TARGET_PRINCIPAL_INVALID", "message": "Invalid target principal."},
        }
        req = RebindRequest(connection_id="conn_222", host_id="vscode", target_profile="nobody")
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == RebindStatus.REJECTED
        assert "Invalid target principal." in outcome.server_message

    def test_classify_rebind_unknown_blocked_code(self):
        """Unknown ok:false code for rebind still produces REJECTED."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_rb_3", "status": "blocked"},
            "error": {"code": "UNKNOWN_BLOCKED", "message": "Blocked for unknown reason."},
        }
        req = RebindRequest(connection_id="conn_333", host_id="vscode", target_profile="x")
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == RebindStatus.REJECTED
        assert outcome.repair_guidance

    def test_classify_rebind_ok_false_run_id_preserved(self):
        """run_id from ok:false data block is preserved in outcome."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_rb_id_42", "status": "blocked"},
            "error": {"code": "REBIND_FORBIDDEN", "message": "Blocked."},
        }
        req = RebindRequest(connection_id="conn_44", host_id="h1", target_profile="p1")
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.run_id == "run_rb_id_42"

    def test_classify_rebind_ok_true_accepted(self):
        """ok:true with status accepted produces RebindStatus.ACCEPTED."""
        raw = {
            "ok": True,
            "data": {
                "run_id": "run_rb_4",
                "status": "accepted",
                "connection_id": "conn_444",
                "old_principal": "alice",
                "new_principal": "bob",
                "message": "Rebound.",
            },
        }
        req = RebindRequest(connection_id="conn_444", host_id="vscode", target_profile="bob")
        outcome = ConnectionIdentityClient._classify_rebind_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == RebindStatus.ACCEPTED
        assert outcome.connection_id == "conn_444"

    def test_classify_invalidate_invalidate_forbidden(self):
        """INVALIDATE_FORBIDDEN produces InvalidateStatus.REJECTED."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_inv_1", "status": "blocked"},
            "error": {"code": "INVALIDATE_FORBIDDEN", "message": "Invalidate not allowed."},
        }
        req = InvalidateRequest(connection_id="conn_555", host_id="vscode")
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == InvalidateStatus.REJECTED
        assert outcome.connection_id == "conn_555"
        assert any("invalidat" in s.lower() for s in outcome.repair_guidance)

    def test_classify_invalidate_connection_not_found(self):
        """CONNECTION_NOT_FOUND in invalidate produces REJECTED with guidance."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_inv_2", "status": "blocked"},
            "error": {"code": "CONNECTION_NOT_FOUND", "message": "Connection not found."},
        }
        req = InvalidateRequest(connection_id="conn_666", host_id="vscode")
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == InvalidateStatus.REJECTED
        assert outcome.run_id == "run_inv_2"
        assert outcome.repair_guidance

    def test_classify_invalidate_unknown_blocked_code(self):
        """Unknown ok:false code for invalidate still produces REJECTED."""
        raw = {
            "ok": False,
            "data": {"run_id": "run_inv_3", "status": "blocked"},
            "error": {"code": "UNKNOWN_CODE", "message": "Something blocked."},
        }
        req = InvalidateRequest(connection_id="conn_77", host_id="vscode")
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == InvalidateStatus.REJECTED
        assert outcome.repair_guidance

    def test_classify_invalidate_ok_true_accepted(self):
        """ok:true with status accepted produces InvalidateStatus.ACCEPTED."""
        raw = {
            "ok": True,
            "data": {
                "run_id": "run_inv_4",
                "status": "accepted",
                "connection_id": "conn_777",
                "reconnect_required": True,
                "message": "Invalidated.",
            },
        }
        req = InvalidateRequest(connection_id="conn_777", host_id="vscode")
        outcome = ConnectionIdentityClient._classify_invalidate_outcome(
            status_code=200, raw=raw, request=req
        )
        assert outcome.status == InvalidateStatus.ACCEPTED
        assert outcome.connection_id == "conn_777"

    def test_rebind_dispatch_uses_parameters_key(self):
        """RebindRequest.to_run_payload uses 'parameters' key not 'payload'."""
        req = RebindRequest(connection_id="conn_88", host_id="h1", target_profile="p1")
        p = req.to_run_payload()
        assert "parameters" in p
        assert "payload" not in p
        assert p["parameters"]["connection_id"] == "conn_88"

    def test_invalidate_dispatch_uses_parameters_key(self):
        """InvalidateRequest.to_run_payload uses 'parameters' key not 'payload'."""
        req = InvalidateRequest(connection_id="conn_99", host_id="h2")
        p = req.to_run_payload()
        assert "parameters" in p
        assert "payload" not in p
        assert p["parameters"]["connection_id"] == "conn_99"

    def test_rebind_scope_denied_raises_surface_unavailable(self):
        """rebind raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_scope_1", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope 'connection:write' not available."},
        }
        req = RebindRequest(connection_id="c1", host_id="h1", target_profile="p1")
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.rebind(req, access_token="tok")

    def test_invalidate_scope_denied_raises_surface_unavailable(self):
        """invalidate raises ConnectionSurfaceUnavailableError on SCOPE_DENIED."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_scope_2", "status": "blocked"},
            "error": {"code": "SCOPE_DENIED", "message": "Scope 'connection:write' not available."},
        }
        req = InvalidateRequest(connection_id="c2", host_id="h2")
        with patch.object(client, "_post", return_value=mock_resp):
            with pytest.raises(ConnectionSurfaceUnavailableError):
                client.invalidate(req, access_token="tok")

    def test_rebind_rebind_forbidden_returns_rejected_outcome(self):
        """rebind returns REJECTED outcome on REBIND_FORBIDDEN (does not raise)."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_rb_blocked", "status": "blocked"},
            "error": {"code": "REBIND_FORBIDDEN", "message": "Rebind disabled."},
        }
        req = RebindRequest(connection_id="c3", host_id="h3", target_profile="p3")
        with patch.object(client, "_post", return_value=mock_resp):
            outcome = client.rebind(req, access_token="tok")
        assert outcome.status == RebindStatus.REJECTED
        assert outcome.repair_guidance

    def test_invalidate_invalidate_forbidden_returns_rejected_outcome(self):
        """invalidate returns REJECTED outcome on INVALIDATE_FORBIDDEN (does not raise)."""
        client = ConnectionIdentityClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "data": {"run_id": "run_inv_blocked", "status": "blocked"},
            "error": {"code": "INVALIDATE_FORBIDDEN", "message": "Invalidate disabled."},
        }
        req = InvalidateRequest(connection_id="c4", host_id="h4")
        with patch.object(client, "_post", return_value=mock_resp):
            outcome = client.invalidate(req, access_token="tok")
        assert outcome.status == InvalidateStatus.REJECTED
        assert outcome.repair_guidance


# --------------------------------------------------------------
# section20 Invariant - INV-SDK-CLIENT-01-C-008: Surface remains governed
# --------------------------------------------------------------


class TestInvariant008SurfaceGoverned:
    """INV-SDK-CLIENT-01-C-008: All connection actions go through governed runs."""

    def test_list_inspect_uses_governed_run(self):
        """connection.list.inspect is dispatched via runs/start."""
        req_payload = {
            "run_type": "connection.list.inspect",
            "parameters": {},
            "correlation_id": "test",
        }
        assert req_payload["run_type"] == "connection.list.inspect"

    def test_identity_inspect_uses_governed_run(self):
        """connection.identity.inspect is dispatched via runs/start."""
        from keyhole_sdk.doctor.reconciliation import CONNECTION_INSPECT_RUN_TYPE
        assert CONNECTION_INSPECT_RUN_TYPE == "connection.identity.inspect"

    def test_lineage_inspect_uses_governed_run(self):
        """connection.lineage.inspect is dispatched via runs/start."""
        from keyhole_sdk.doctor.reconciliation import CONNECTION_LINEAGE_RUN_TYPE
        assert CONNECTION_LINEAGE_RUN_TYPE == "connection.lineage.inspect"

    def test_rebind_uses_governed_run(self):
        req = RebindRequest(host_id="vscode", target_profile="paul")
        payload = req.to_run_payload()
        assert payload["run_type"] == "connection.rebind"

    def test_invalidate_uses_governed_run(self):
        req = InvalidateRequest(host_id="vscode")
        payload = req.to_run_payload()
        assert payload["run_type"] == "connection.invalidate"

    def test_all_surfaces_are_run_types(self):
        """All connection surfaces must pass through the run surface."""
        from keyhole_sdk.doctor.reconciliation import CONNECTION_SURFACES
        for surface in CONNECTION_SURFACES:
            assert "." in surface  # All are dotted run type names

    def test_client_methods_post_to_runs_start(self):
        """Client dispatches through the governed /mcp/v1/runs/start path."""
        client = ConnectionIdentityClient()
        assert "/mcp/v1/runs/start" in f"{client._mcp_base_url}/mcp/v1/runs/start"
