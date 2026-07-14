"""SDK-CLIENT-00 - Identity Creation & Verification (Client) unit tests.

Implements section19 of sdk-client-00.md.

Tests A-L:
  A - Dev/test registration succeeds
  B - Verification completes successfully
  C - Registration status works
  D - Mailhog-compatible verification works (dev verification path)
  E - Handoff to login is clear
  F - Missing origin/purpose rejected for kh-dev
  G - Invalid verification artifact rejected
  H - Expired verification rejected
  I - Duplicate registration rejected cleanly
  J - No secret leakage in proof
  K - Onboarding proof replay sufficiency
  L - Classification proof correctness
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from keyhole_sdk.onboarding.client import OnboardingClient
from keyhole_sdk.onboarding.errors import (
    DuplicateRegistrationError,
    MissingClassificationError,
    OnboardingNetworkError,
    RegistrationRejectedError,
    VerificationExpiredError,
    VerificationFailedError,
)
from keyhole_sdk.onboarding.models import (
    OnboardingRealm,
    OnboardingState,
    RegistrationRequest,
    RegistrationResponse,
    RegistrationStatusResponse,
    VerificationRequest,
    VerificationResponse,
)
from keyhole_sdk.onboarding.proof import OnboardingProofBundle


# -- Helpers --------------------------------------------------


def _mock_response(status_code: int, data: Dict[str, Any]) -> MagicMock:
    """Create a mock requests.Response with MCP envelope wrapping."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"ok": status_code < 400, "data": data}
    return resp


def _dev_registration_request(**overrides: Any) -> RegistrationRequest:
    defaults = {
        "email": "test-user@example.com",
        "username": "test-user-sdk00",
        "display_name": "Test User",
        "realm": OnboardingRealm.KH_DEV,
        "origin": "smoke",
        "purpose": "sdk_onboarding",
    }
    defaults.update(overrides)
    return RegistrationRequest(**defaults)


def _registration_response_data(**overrides: Any) -> Dict[str, Any]:
    defaults = {
        "registration_id": "reg-001",
        "state": "pending_verification",
        "realm": "kh-dev",
        "origin": "smoke",
        "purpose": "sdk_onboarding",
        "username": "test-user-sdk00",
        "email": "test-user@example.com",
        "verification_hint": "Check your email for a verification code.",
        "next_step": "keyhole verify --registration-id reg-001 --code <code>",
    }
    defaults.update(overrides)
    return defaults


def _verification_response_data(**overrides: Any) -> Dict[str, Any]:
    defaults = {
        "registration_id": "reg-001",
        "state": "active",
        "user_id": "user-001",
        "username": "test-user-sdk00",
        "realm": "kh-dev",
        "message": "Identity is now active.",
        "next_step": "keyhole login",
    }
    defaults.update(overrides)
    return defaults


def _status_response_data(**overrides: Any) -> Dict[str, Any]:
    defaults = {
        "registration_id": "reg-001",
        "state": "active",
        "realm": "kh-dev",
        "origin": "smoke",
        "purpose": "sdk_onboarding",
        "username": "test-user-sdk00",
        "email": "test-user@example.com",
        "user_id": "user-001",
        "next_step": "keyhole login",
    }
    defaults.update(overrides)
    return defaults


# --------------------------------------------------------------
# section19.1 Positive Tests
# --------------------------------------------------------------


class TestA_DevTestRegistrationSucceeds:
    """Test A - Dev/test registration succeeds."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_register_returns_pending_verification(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(200, _registration_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()
        response = client.register(request, correlation_id="corr-a")

        assert response.registration_id == "reg-001"
        assert response.state == OnboardingState.PENDING_VERIFICATION
        assert response.realm == OnboardingRealm.KH_DEV
        assert response.origin == "smoke"
        assert response.purpose == "sdk_onboarding"

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_register_sends_correct_payload(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(200, _registration_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()
        client.register(request, correlation_id="corr-a2")

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["email"] == "test-user@example.com"
        assert payload["username"] == "test-user-sdk00"
        assert payload["realm"] == "kh-dev"
        assert payload["origin"] == "smoke"
        assert payload["purpose"] == "sdk_onboarding"
        assert payload["correlation_id"] == "corr-a2"

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_register_proof_captures_classification(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(200, _registration_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()
        response = client.register(request, correlation_id="corr-a3")

        summary = response.safe_summary()
        assert summary["realm"] == "kh-dev"
        assert summary["origin"] == "smoke"
        assert summary["purpose"] == "sdk_onboarding"


class TestB_VerificationCompletesSuccessfully:
    """Test B - Verification completes successfully."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_verify_returns_active_state(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(200, _verification_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="123456")
        response = client.verify(request, correlation_id="corr-b")

        assert response.registration_id == "reg-001"
        assert response.state == OnboardingState.ACTIVE
        assert response.user_id == "user-001"
        assert response.username == "test-user-sdk00"

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_verify_proof_captures_completion(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(200, _verification_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="123456")
        response = client.verify(request, correlation_id="corr-b2")

        summary = response.safe_summary()
        assert summary["state"] == "active"
        assert summary["user_id"] == "user-001"


class TestC_RegistrationStatusWorks:
    """Test C - Registration status works."""

    @patch("keyhole_sdk.onboarding.client.requests.get")
    def test_status_returns_full_context(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, _status_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        response = client.get_status("reg-001", correlation_id="corr-c")

        assert response.registration_id == "reg-001"
        assert response.state == OnboardingState.ACTIVE
        assert response.realm == "kh-dev"
        assert response.origin == "smoke"
        assert response.purpose == "sdk_onboarding"
        assert response.user_id == "user-001"

    @patch("keyhole_sdk.onboarding.client.requests.get")
    def test_status_safe_summary(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, _status_response_data())

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        response = client.get_status("reg-001", correlation_id="corr-c2")

        summary = response.safe_summary()
        assert summary["state"] == "active"
        assert summary["realm"] == "kh-dev"
        assert summary["origin"] == "smoke"
        assert summary["purpose"] == "sdk_onboarding"


class TestD_DevVerificationPath:
    """Test D - Mailhog-compatible (dev) verification works."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_verify_with_token_works(self, mock_post: MagicMock) -> None:
        """Token-based verification supports dev/test flows without production email."""
        mock_post.return_value = _mock_response(
            200, _verification_response_data(state="verified"),
        )

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", token="dev-token-abc")
        response = client.verify(request, correlation_id="corr-d")

        assert response.state == OnboardingState.VERIFIED
        assert response.registration_id == "reg-001"


class TestE_HandoffToLoginIsClear:
    """Test E - Handoff to login is clear."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_active_verification_shows_login_next_step(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(
            200, _verification_response_data(next_step="keyhole login"),
        )

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="123456")
        response = client.verify(request, correlation_id="corr-e")

        assert response.next_step == "keyhole login"


# --------------------------------------------------------------
# section19.2 Negative Tests
# --------------------------------------------------------------


class TestF_MissingClassificationRejected:
    """Test F - Missing origin/purpose rejected for kh-dev."""

    def test_missing_origin_raises(self) -> None:
        request = RegistrationRequest(
            email="test@example.com",
            username="test-user",
            display_name="Test",
            realm=OnboardingRealm.KH_DEV,
            purpose="sdk_onboarding",
            # origin missing
        )
        client = OnboardingClient(mcp_base_url="https://test.example.com")

        with pytest.raises(MissingClassificationError) as exc_info:
            client.register(request)

        assert "origin" in exc_info.value.missing_fields
        assert exc_info.value.error_class == "missing_classification"
        assert len(exc_info.value.repair_suggestions) > 0

    def test_missing_purpose_raises(self) -> None:
        request = RegistrationRequest(
            email="test@example.com",
            username="test-user",
            display_name="Test",
            realm=OnboardingRealm.KH_DEV,
            origin="smoke",
            # purpose missing
        )
        client = OnboardingClient(mcp_base_url="https://test.example.com")

        with pytest.raises(MissingClassificationError) as exc_info:
            client.register(request)

        assert "purpose" in exc_info.value.missing_fields

    def test_missing_both_raises(self) -> None:
        request = RegistrationRequest(
            email="test@example.com",
            username="test-user",
            display_name="Test",
            realm=OnboardingRealm.KH_DEV,
        )
        client = OnboardingClient(mcp_base_url="https://test.example.com")

        with pytest.raises(MissingClassificationError) as exc_info:
            client.register(request)

        assert "origin" in exc_info.value.missing_fields
        assert "purpose" in exc_info.value.missing_fields

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_non_dev_realm_no_classification_required(self, mock_post: MagicMock) -> None:
        """kh-prod does not require origin/purpose."""
        mock_post.return_value = _mock_response(
            200, _registration_response_data(realm="kh-prod"),
        )

        request = RegistrationRequest(
            email="test@example.com",
            username="test-user",
            display_name="Test",
            realm=OnboardingRealm.KH_PROD,
        )
        client = OnboardingClient(mcp_base_url="https://test.example.com")
        response = client.register(request)

        assert response.registration_id == "reg-001"


class TestG_InvalidVerificationRejected:
    """Test G - Invalid verification artifact rejected."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_bad_code_raises_verification_failed(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(400, {
            "error_class": "verification_failed",
            "message": "Invalid verification code",
            "reason": "Code does not match",
        })

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="wrong")

        with pytest.raises(VerificationFailedError) as exc_info:
            client.verify(request)

        assert exc_info.value.error_class == "verification_failed"

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_bad_code_does_not_report_active(self, mock_post: MagicMock) -> None:
        """No false active state on bad verification."""
        mock_post.return_value = _mock_response(400, {
            "error_class": "verification_failed",
            "message": "Invalid code",
        })

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="wrong")

        with pytest.raises(VerificationFailedError):
            client.verify(request)


class TestH_ExpiredVerificationRejected:
    """Test H - Expired verification rejected."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_expired_raises_correct_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(410, {
            "message": "Verification token has expired",
        })

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="expired")

        with pytest.raises(VerificationExpiredError) as exc_info:
            client.verify(request)

        assert exc_info.value.error_class == "verification_expired"
        assert len(exc_info.value.repair_suggestions) > 0


class TestI_DuplicateRegistrationRejected:
    """Test I - Duplicate registration rejected cleanly."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_duplicate_raises_correct_error(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(409, {
            "message": "Username already registered",
        })

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()

        with pytest.raises(DuplicateRegistrationError) as exc_info:
            client.register(request)

        assert exc_info.value.error_class == "duplicate_registration"
        assert len(exc_info.value.repair_suggestions) > 0

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_duplicate_no_false_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(409, {
            "message": "Already exists",
        })

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()

        with pytest.raises(DuplicateRegistrationError):
            client.register(request)


# --------------------------------------------------------------
# section19.3 Proof Tests
# --------------------------------------------------------------


class TestJ_NoSecretLeakageInProof:
    """Test J - No secret leakage in proof."""

    def test_proof_bundle_contains_no_secrets(self) -> None:
        proof = OnboardingProofBundle(correlation_id="corr-j")
        proof.record_event("registration_initiated", {"realm": "kh-dev"})

        reg_summary = {
            "registration_id": "reg-001",
            "state": "pending_verification",
            "realm": "kh-dev",
            "origin": "smoke",
            "purpose": "sdk_onboarding",
            "username": "test-user-sdk00",
            "verification_hint": "Check email",
            "next_step": "keyhole verify ...",
        }
        ver_summary = {
            "registration_id": "reg-001",
            "state": "active",
            "user_id": "user-001",
            "username": "test-user-sdk00",
            "realm": "kh-dev",
            "next_step": "keyhole login",
        }

        bundle = proof.generate(
            registration=reg_summary,
            verification=ver_summary,
            success=True,
        )

        # Serialize entire bundle and check for forbidden secrets
        bundle_str = json.dumps(bundle, indent=2, default=str)
        forbidden = ["password", "secret", "bearer", "access_token", "refresh_token"]
        for word in forbidden:
            assert word not in bundle_str.lower(), f"Proof bundle contains forbidden word: {word}"

        # Verification codes must not appear
        assert "123456" not in bundle_str

    def test_verification_request_model_hides_token(self) -> None:
        req = VerificationRequest(
            registration_id="reg-001", token="secret-token-abc",
        )
        assert "secret-token-abc" not in repr(req)

    def test_proof_write_to_disk_is_secret_safe(self) -> None:
        proof = OnboardingProofBundle(correlation_id="corr-j2")
        reg_summary = {
            "registration_id": "reg-001",
            "state": "pending_verification",
            "realm": "kh-dev",
            "origin": "smoke",
            "purpose": "sdk_onboarding",
            "username": "test-user-sdk00",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = proof.write(
                registration=reg_summary,
                success=False,
                output_dir=Path(tmpdir),
            )

            # Verify all expected files exist
            expected_files = [
                "core.json", "request.json", "response.json",
                "event_chain.json", "registration_context.json",
                "verification_result.json", "identity_context.json",
                "correlation.json", "summary.md", "diff.json", "digest.txt",
            ]
            for f in expected_files:
                assert (bundle_dir / f).exists(), f"Missing proof file: {f}"

            # Verify extended dir exists
            assert (bundle_dir / "extended").is_dir()

            # Read all files and scan for secrets
            for f in expected_files:
                content = (bundle_dir / f).read_text()
                for word in ["password", "secret", "bearer", "access_token"]:
                    assert word not in content.lower(), (
                        f"Secret word '{word}' found in {f}"
                    )


class TestK_OnboardingProofReplaySufficiency:
    """Test K - Onboarding proof replay sufficiency."""

    def test_hot_proof_core_is_sufficient(self) -> None:
        proof = OnboardingProofBundle(correlation_id="corr-k")
        proof.record_event("registration_initiated", {
            "realm": "kh-dev", "origin": "smoke", "purpose": "sdk_onboarding",
        })
        proof.record_event("registration_accepted", {
            "registration_id": "reg-001", "state": "pending_verification",
        })
        proof.record_event("verification_completed", {
            "registration_id": "reg-001", "state": "active", "user_id": "user-001",
        })

        reg = {
            "registration_id": "reg-001",
            "state": "pending_verification",
            "realm": "kh-dev",
            "origin": "smoke",
            "purpose": "sdk_onboarding",
            "username": "test-user-sdk00",
        }
        ver = {
            "registration_id": "reg-001",
            "state": "active",
            "user_id": "user-001",
            "username": "test-user-sdk00",
            "realm": "kh-dev",
            "next_step": "keyhole login",
        }

        bundle = proof.generate(registration=reg, verification=ver, success=True)

        # Verify core has required fields
        core = bundle["core.json"]
        assert core["proof_type"] == "onboarding"
        assert core["story_id"] == "SDK-CLIENT-00"
        assert core["success"] is True
        assert core["realm"] == "kh-dev"
        assert core["origin"] == "smoke"
        assert core["purpose"] == "sdk_onboarding"
        assert core["registration_completed"] is True
        assert core["verification_completed"] is True

        # Verify event chain captures lifecycle
        events = bundle["event_chain.json"]["events"]
        event_types = [e["event_type"] for e in events]
        assert "registration_initiated" in event_types
        assert "registration_accepted" in event_types
        assert "verification_completed" in event_types

        # Verify registration context
        reg_ctx = bundle["registration_context.json"]
        assert reg_ctx["source"] == "server/register"
        assert reg_ctx["registration_id"] == "reg-001"
        assert reg_ctx["realm"] == "kh-dev"

        # Verify verification result
        ver_result = bundle["verification_result.json"]
        assert ver_result["verification_completed"] is True
        assert ver_result["identity_activated"] is True
        assert ver_result["user_id"] == "user-001"

        # Verify identity context
        id_ctx = bundle["identity_context.json"]
        assert id_ctx["identity_resolved"] is True
        assert id_ctx["user_id"] == "user-001"

        # Verify digest exists
        assert bundle["digest.txt"].startswith("sha256:")

        # Verify diff
        diff = bundle["diff.json"]
        assert diff["onboarding_state_transition"]["before"] == "pending_verification"
        assert diff["onboarding_state_transition"]["after"] == "active"

        # Verify summary contains handoff
        assert "keyhole login" in bundle["summary.md"]


class TestL_ClassificationProofCorrectness:
    """Test L - Classification proof correctness."""

    def test_realm_origin_purpose_in_proof(self) -> None:
        proof = OnboardingProofBundle(correlation_id="corr-l")

        reg = {
            "registration_id": "reg-l",
            "state": "pending_verification",
            "realm": "kh-dev",
            "origin": "integration",
            "purpose": "verification_test",
            "username": "test-l",
        }

        bundle = proof.generate(registration=reg, success=False)

        # Core must contain classification
        core = bundle["core.json"]
        assert core["realm"] == "kh-dev"
        assert core["origin"] == "integration"
        assert core["purpose"] == "verification_test"

        # Registration context must contain classification
        reg_ctx = bundle["registration_context.json"]
        assert reg_ctx["realm"] == "kh-dev"
        assert reg_ctx["origin"] == "integration"
        assert reg_ctx["purpose"] == "verification_test"

        # Request must contain classification
        request_doc = bundle["request.json"]
        assert request_doc["realm"] == "kh-dev"
        assert request_doc["origin"] == "integration"
        assert request_doc["purpose"] == "verification_test"

    def test_classification_in_summary(self) -> None:
        proof = OnboardingProofBundle(correlation_id="corr-l2")

        reg = {
            "registration_id": "reg-l2",
            "state": "pending_verification",
            "realm": "kh-dev",
            "origin": "smoke",
            "purpose": "sdk_onboarding",
            "username": "test-l2",
        }

        bundle = proof.generate(registration=reg, success=False)
        summary = bundle["summary.md"]

        assert "kh-dev" in summary
        assert "smoke" in summary
        assert "sdk_onboarding" in summary


# --------------------------------------------------------------
# Additional model and error tests
# --------------------------------------------------------------


class TestModelValidation:
    """Model validation and classification enforcement."""

    def test_registration_request_validate_classification_kh_dev(self) -> None:
        req = RegistrationRequest(
            email="t@e.com", username="t", display_name="T",
            realm=OnboardingRealm.KH_DEV,
        )
        missing = req.validate_classification()
        assert "origin" in missing
        assert "purpose" in missing

    def test_registration_request_validate_classification_complete(self) -> None:
        req = _dev_registration_request()
        missing = req.validate_classification()
        assert missing == []

    def test_registration_request_validate_prod_no_classification(self) -> None:
        req = RegistrationRequest(
            email="t@e.com", username="t", display_name="T",
            realm=OnboardingRealm.KH_PROD,
        )
        missing = req.validate_classification()
        assert missing == []

    def test_onboarding_state_enum_values(self) -> None:
        assert OnboardingState.PENDING_VERIFICATION.value == "pending_verification"
        assert OnboardingState.VERIFIED.value == "verified"
        assert OnboardingState.ACTIVE.value == "active"
        assert OnboardingState.FAILED.value == "failed"
        assert OnboardingState.BLOCKED.value == "blocked"

    def test_onboarding_realm_enum_values(self) -> None:
        assert OnboardingRealm.KH_PROD.value == "kh-prod"
        assert OnboardingRealm.KH_DEV.value == "kh-dev"
        assert OnboardingRealm.KEYHOLE_MCP.value == "keyhole-mcp"


class TestErrorHierarchy:
    """Error hierarchy and repair guidance."""

    def test_missing_classification_error_fields(self) -> None:
        err = MissingClassificationError(["origin", "purpose"])
        assert err.error_class == "missing_classification"
        assert "origin" in err.missing_fields
        assert "purpose" in err.missing_fields
        assert len(err.repair_suggestions) >= 2

    def test_duplicate_registration_error(self) -> None:
        err = DuplicateRegistrationError()
        assert err.error_class == "duplicate_registration"
        assert len(err.repair_suggestions) > 0

    def test_verification_expired_error(self) -> None:
        err = VerificationExpiredError()
        assert err.error_class == "verification_expired"
        assert len(err.repair_suggestions) > 0

    def test_verification_failed_error(self) -> None:
        err = VerificationFailedError()
        assert err.error_class == "verification_failed"
        assert len(err.repair_suggestions) > 0

    def test_registration_rejected_error(self) -> None:
        err = RegistrationRejectedError("Custom reason", reason="details")
        assert err.error_class == "registration_rejected"
        assert err.reason == "details"

    def test_network_error(self) -> None:
        err = OnboardingNetworkError("Connection refused")
        assert err.error_class == "onboarding_network_error"
        assert len(err.repair_suggestions) > 0


class TestNetworkFailures:
    """Network error handling."""

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_register_network_error(self, mock_post: MagicMock) -> None:
        import requests as req_lib
        mock_post.side_effect = req_lib.ConnectionError("Connection refused")

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = _dev_registration_request()

        with pytest.raises(OnboardingNetworkError):
            client.register(request)

    @patch("keyhole_sdk.onboarding.client.requests.post")
    def test_verify_network_error(self, mock_post: MagicMock) -> None:
        import requests as req_lib
        mock_post.side_effect = req_lib.ConnectionError("Connection refused")

        client = OnboardingClient(mcp_base_url="https://test.example.com")
        request = VerificationRequest(registration_id="reg-001", code="123")

        with pytest.raises(OnboardingNetworkError):
            client.verify(request)

    @patch("keyhole_sdk.onboarding.client.requests.get")
    def test_status_network_error(self, mock_get: MagicMock) -> None:
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("Connection refused")

        client = OnboardingClient(mcp_base_url="https://test.example.com")

        with pytest.raises(OnboardingNetworkError):
            client.get_status("reg-001")


# --------------------------------------------------------------
# CLI Command Tests
# --------------------------------------------------------------


class TestCLIRegisterCommand:
    """CLI register command result shape."""

    @patch("keyhole_cli.commands.register.OnboardingClient")
    def test_run_register_success(self, mock_client_class: MagicMock) -> None:
        from keyhole_cli.commands.register import run_register

        mock_client = mock_client_class.return_value
        mock_client.register.return_value = RegistrationResponse(
            registration_id="reg-cli",
            state=OnboardingState.PENDING_VERIFICATION,
            realm=OnboardingRealm.KH_DEV,
            origin="smoke",
            purpose="sdk_onboarding",
            username="cli-user",
            verification_hint="Check email",
            next_step="keyhole verify ...",
        )

        result = run_register(
            email="cli@example.com",
            username="cli-user",
            display_name="CLI User",
            realm="kh-dev",
            origin="smoke",
            purpose="sdk_onboarding",
            mcp_url="https://test.example.com",
        )

        assert result.success is True
        assert result.command == "register"
        assert result.data["registration_id"] == "reg-cli"
        assert result.data["state"] == "pending_verification"
        assert result.data["realm"] == "kh-dev"
        assert result.data["origin"] == "smoke"
        assert result.data["purpose"] == "sdk_onboarding"
        assert any("verify" in s.lower() for s in result.next_steps)

    @patch("keyhole_cli.commands.register.OnboardingClient")
    def test_run_register_failure(self, mock_client_class: MagicMock) -> None:
        from keyhole_cli.commands.register import run_register

        mock_client = mock_client_class.return_value
        mock_client.register.side_effect = DuplicateRegistrationError()

        result = run_register(
            email="dup@example.com",
            username="dup-user",
            display_name="Dup",
            realm="kh-dev",
            origin="smoke",
            purpose="sdk_onboarding",
            mcp_url="https://test.example.com",
        )

        assert result.success is False
        assert result.data["error_class"] == "duplicate_registration"

    def test_run_register_invalid_realm(self) -> None:
        from keyhole_cli.commands.register import run_register

        result = run_register(
            email="t@e.com",
            username="t",
            display_name="T",
            realm="invalid-realm",
            mcp_url="https://test.example.com",
        )

        assert result.success is False
        assert result.data["error_class"] == "invalid_realm"

    @patch("keyhole_cli.commands.register.OnboardingClient")
    def test_run_register_missing_classification(self, mock_client_class: MagicMock) -> None:
        from keyhole_cli.commands.register import run_register

        mock_client = mock_client_class.return_value
        mock_client.register.side_effect = MissingClassificationError(["origin", "purpose"])

        result = run_register(
            email="t@e.com",
            username="t",
            display_name="T",
            realm="kh-dev",
            mcp_url="https://test.example.com",
        )

        assert result.success is False
        assert result.data["error_class"] == "missing_classification"


class TestCLIVerifyCommand:
    """CLI verify command result shape."""

    @patch("keyhole_cli.commands.verify.OnboardingClient")
    def test_run_verify_success(self, mock_client_class: MagicMock) -> None:
        from keyhole_cli.commands.verify import run_verify

        mock_client = mock_client_class.return_value
        mock_client.verify.return_value = VerificationResponse(
            registration_id="reg-v",
            state=OnboardingState.ACTIVE,
            user_id="user-v",
            username="verify-user",
            realm="kh-dev",
            next_step="keyhole login",
        )

        result = run_verify(
            registration_id="reg-v",
            code="123456",
            mcp_url="https://test.example.com",
        )

        assert result.success is True
        assert result.command == "verify"
        assert result.data["state"] == "active"
        assert result.data["user_id"] == "user-v"
        assert any("login" in s.lower() for s in result.next_steps)

    def test_run_verify_missing_artifact(self) -> None:
        from keyhole_cli.commands.verify import run_verify

        result = run_verify(
            registration_id="reg-v2",
            mcp_url="https://test.example.com",
        )

        assert result.success is False
        assert result.data["error_class"] == "missing_verification_artifact"


class TestCLIRegistrationStatusCommand:
    """CLI registration-status command result shape."""

    @patch("keyhole_cli.commands.registration_status.OnboardingClient")
    def test_run_status_success(self, mock_client_class: MagicMock) -> None:
        from keyhole_cli.commands.registration_status import run_registration_status

        mock_client = mock_client_class.return_value
        mock_client.get_status.return_value = RegistrationStatusResponse(
            registration_id="reg-s",
            state=OnboardingState.ACTIVE,
            realm="kh-dev",
            origin="smoke",
            purpose="sdk_onboarding",
            username="status-user",
            user_id="user-s",
            next_step="keyhole login",
        )

        result = run_registration_status(
            registration_id="reg-s",
            mcp_url="https://test.example.com",
        )

        assert result.success is True
        assert result.command == "registration-status"
        assert result.data["state"] == "active"
        assert result.data["realm"] == "kh-dev"
        assert any("login" in s.lower() for s in result.next_steps)
