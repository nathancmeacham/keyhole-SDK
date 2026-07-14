"""CE-V5-S41-03 - SDK / Runtime Compatibility Governance tests.

Covers all 9 proposed invariants:
  S41-03-INV-01  SDK-RUNTIME-COMPATIBLE
  S41-03-INV-02  SDK-TYPED-PUBLIC-MODELS-CLOSED
  S41-03-INV-03  SDK-CLIENT-BEHAVIOR-STABLE
  S41-03-INV-04  SDK-COMPATIBILITY-CHECK-CLOSED
  S41-03-INV-05  SDK-EXAMPLES-NO-AD-HOC-DRIFT
  S41-03-INV-06  SDK-RECEIPT-SEMANTICS-TRUTHFUL
  S41-03-INV-07  SDK-MODE-SEMANTICS-TRUTHFUL
  S41-03-INV-08  SDK-PUBLIC-PRIVATE-BOUNDARY-CLOSED
  S41-03-INV-09  SDK-RELEASE-COMPATIBILITY-GATED
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from keyhole_sdk import __version__ as SDK_VERSION
from keyhole_sdk.client import KeyholeClient
from keyhole_sdk.models import (
    CompatibilityResult,
    CompatibilityStatus,
    PRIVATE_FIELDS,
    PublicError,
    RealizationReceipt,
    RealizationRequest,
    RuntimeHealth,
    RuntimeIdentity,
    RuntimeState,
    _strip_private,
)
from keyhole_sdk.exceptions import (
    CompatibilityError,
    KeyholeSDKError,
    PublicEndpointError,
    RuntimeUnavailableError,
    SchemaError,
    TransportError,
)
from keyhole_sdk.compatibility import COMPATIBILITY_RULES, check


# --------------------------------------------------------------
# Fixtures - canonical public contract data
# --------------------------------------------------------------

CANONICAL_IDENTITY = {
    "runtime_id": "keyhole-test-runtime",
    "runtime_name": "Keyhole Test Runtime",
    "runtime_version": "0.1.0",
    "environment": "dev",
    "capabilities": ["realize", "state", "health"],
}

CANONICAL_RECEIPT = {
    "digest": "sha256:abc123",
    "status": "ACCEPT",
    "message": "Digest realized successfully.",
    "realized_at": "2026-03-06T12:01:00+00:00",
}

CANONICAL_HEALTH = {"status": "ok"}

CANONICAL_STATE = {
    "current_digest": None,
    "realized_digests": [],
    "updated_at": "2026-03-06T12:00:00+00:00",
}


def _mock_response(status_code: int = 200, json_data: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text or json.dumps(json_data or {})
    resp.reason = "OK" if status_code < 400 else "Error"
    resp.json.return_value = json_data or {}
    return resp


def _make_client(responses: list[MagicMock]) -> KeyholeClient:
    """Create a client whose session returns *responses* in order."""
    session = MagicMock()
    session.request = MagicMock(side_effect=responses)
    return KeyholeClient(base_url="http://test:8080", session=session)


# --------------------------------------------------------------
# INV-02: SDK-TYPED-PUBLIC-MODELS-CLOSED
# --------------------------------------------------------------


class TestTypedPublicModels:
    """Typed models must exist for all declared public surfaces."""

    def test_runtime_identity_parses_canonical(self) -> None:
        model = RuntimeIdentity.model_validate(CANONICAL_IDENTITY)
        assert model.runtime_id == "keyhole-test-runtime"
        assert model.runtime_name == "Keyhole Test Runtime"
        assert model.runtime_version == "0.1.0"
        assert model.environment == "dev"
        assert model.capabilities == ["realize", "state", "health"]

    def test_runtime_health_parses(self) -> None:
        model = RuntimeHealth.model_validate(CANONICAL_HEALTH)
        assert model.status == "ok"

    def test_runtime_state_parses_canonical(self) -> None:
        model = RuntimeState.model_validate(CANONICAL_STATE)
        assert model.current_digest is None
        assert model.realized_digests == []
        assert isinstance(model.updated_at, datetime)

    def test_realization_request_builds(self) -> None:
        req = RealizationRequest(
            candidate_digest="sha256:abc",
            payload={"key": "val"},
        )
        assert req.candidate_digest == "sha256:abc"
        assert req.payload == {"key": "val"}

    def test_realization_receipt_parses_canonical(self) -> None:
        model = RealizationReceipt.model_validate(CANONICAL_RECEIPT)
        assert model.digest == "sha256:abc123"
        assert model.status == "ACCEPT"
        assert model.message == "Digest realized successfully."
        assert isinstance(model.realized_at, datetime)

    def test_compatibility_result_parses(self) -> None:
        cr = CompatibilityResult(
            sdk_version="0.2.0",
            runtime_name="test",
            runtime_version="0.1.0",
            compatibility_status=CompatibilityStatus.COMPATIBLE,
            checked_at="2026-03-10T00:00:00Z",
        )
        assert cr.compatibility_status == CompatibilityStatus.COMPATIBLE
        assert cr.failures == []
        assert cr.warnings == []

    def test_public_error_parses(self) -> None:
        err = PublicError(error="not_found", detail="resource missing", status_code=404)
        assert err.error == "not_found"
        assert err.status_code == 404

    def test_identity_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeIdentity.model_validate({"runtime_id": "x"})

    def test_receipt_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            RealizationReceipt.model_validate({"digest": "x"})

    def test_identity_extra_fields_tolerated(self) -> None:
        """Adding optional public fields is a compatible change."""
        data = {**CANONICAL_IDENTITY, "new_optional": "future_field"}
        model = RuntimeIdentity.model_validate(data)
        assert model.runtime_id == "keyhole-test-runtime"


# --------------------------------------------------------------
# INV-08: SDK-PUBLIC-PRIVATE-BOUNDARY-CLOSED
# --------------------------------------------------------------


class TestPublicPrivateBoundary:
    """SDK must not require, expose, or infer private fields."""

    def test_private_fields_constant_is_defined(self) -> None:
        assert len(PRIVATE_FIELDS) >= 8
        assert "pointer_state" in PRIVATE_FIELDS
        assert "governance_verdict" in PRIVATE_FIELDS
        assert "drift_state" in PRIVATE_FIELDS

    def test_strip_private_removes_forbidden_fields(self) -> None:
        data = {
            "runtime_id": "rt-1",
            "pointer_state": "secret",
            "governance_verdict": "ACCEPT",
            "drift_state": "clean",
            "environment": "dev",
        }
        clean = _strip_private(data)
        assert "runtime_id" in clean
        assert "environment" in clean
        assert "pointer_state" not in clean
        assert "governance_verdict" not in clean
        assert "drift_state" not in clean

    def test_identity_model_strips_private_on_parse(self) -> None:
        data = {
            **CANONICAL_IDENTITY,
            "pointer_state": "prod-v80",
            "canonical_digest": "sha256:deadbeef",
        }
        model = RuntimeIdentity.model_validate(data)
        d = model.model_dump()
        assert "pointer_state" not in d
        assert "canonical_digest" not in d

    def test_state_model_strips_private_on_parse(self) -> None:
        data = {
            **CANONICAL_STATE,
            "controller_state": "reconciling",
            "internal_lane": "staging",
        }
        model = RuntimeState.model_validate(data)
        d = model.model_dump()
        assert "controller_state" not in d
        assert "internal_lane" not in d


# --------------------------------------------------------------
# INV-03: SDK-CLIENT-BEHAVIOR-STABLE
# --------------------------------------------------------------


class TestStableClientBehavior:
    """Public client must be deterministic, fail truthfully, and expose typed results."""

    def test_get_identity_returns_typed(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_IDENTITY)])
        result = client.get_identity()
        assert isinstance(result, RuntimeIdentity)
        assert result.runtime_name == "Keyhole Test Runtime"

    def test_get_health_returns_typed(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_HEALTH)])
        result = client.get_health()
        assert isinstance(result, RuntimeHealth)
        assert result.status == "ok"

    def test_get_state_returns_typed(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_STATE)])
        result = client.get_state()
        assert isinstance(result, RuntimeState)
        assert result.current_digest is None

    def test_realize_typed_returns_receipt(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_RECEIPT)])
        result = client.realize_typed("sha256:abc", payload={"k": "v"})
        assert isinstance(result, RealizationReceipt)
        assert result.status == "ACCEPT"

    def test_legacy_identity_returns_dict(self) -> None:
        """Backward-compatible untyped methods still return dicts."""
        client = _make_client([_mock_response(json_data=CANONICAL_IDENTITY)])
        result = client.identity()
        assert isinstance(result, dict)
        assert result["runtime_name"] == "Keyhole Test Runtime"

    def test_legacy_realize_returns_dict(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_RECEIPT)])
        result = client.realize("sha256:abc")
        assert isinstance(result, dict)

    def test_context_manager(self) -> None:
        session = MagicMock()
        with KeyholeClient(base_url="http://test:8080", session=session):
            pass
        session.close.assert_called_once()


# --------------------------------------------------------------
# INV-01 + INV-04: SDK-COMPATIBILITY-CHECK-CLOSED
# --------------------------------------------------------------


class TestCompatibilityCheck:
    """Compatibility checker must be deterministic and produce correct outcomes."""

    def test_compatible_runtime(self) -> None:
        client = _make_client([
            _mock_response(json_data=CANONICAL_IDENTITY),
            _mock_response(json_data=CANONICAL_HEALTH),
            _mock_response(json_data=CANONICAL_STATE),
        ])
        result = client.check_compatibility()
        assert isinstance(result, CompatibilityResult)
        assert result.compatibility_status == CompatibilityStatus.COMPATIBLE
        assert result.sdk_version == SDK_VERSION
        assert result.runtime_name == "Keyhole Test Runtime"
        assert result.failures == []

    def test_incompatible_missing_identity_field(self) -> None:
        bad_identity = {"runtime_id": "x", "runtime_name": "Y"}
        client = _make_client([
            _mock_response(json_data=bad_identity),
            _mock_response(json_data=CANONICAL_HEALTH),
            _mock_response(json_data=CANONICAL_STATE),
        ])
        result = client.check_compatibility()
        assert result.compatibility_status == CompatibilityStatus.INCOMPATIBLE
        assert len(result.failures) > 0

    def test_transport_failure_returns_incompatible(self) -> None:
        import requests as _req
        session = MagicMock()
        session.request.side_effect = _req.ConnectionError("refused")
        client = KeyholeClient(base_url="http://test:8080", session=session)
        result = client.check_compatibility()
        assert result.compatibility_status == CompatibilityStatus.INCOMPATIBLE
        assert "transport" in result.failures[0]

    def test_state_warning_still_compatible(self) -> None:
        """If state endpoint fails, compatible-with-warnings."""
        import requests as _req
        responses = [
            _mock_response(json_data=CANONICAL_IDENTITY),
            _mock_response(json_data=CANONICAL_HEALTH),
        ]
        session = MagicMock()
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            if call_count < len(responses):
                r = responses[call_count]
                call_count += 1
                return r
            raise _req.ConnectionError("state refused")

        session.request.side_effect = side_effect
        client = KeyholeClient(base_url="http://test:8080", session=session)
        result = client.check_compatibility()
        assert result.compatibility_status == CompatibilityStatus.COMPATIBLE_WITH_WARNINGS
        assert len(result.warnings) > 0

    def test_determinism_same_input_same_output(self) -> None:
        """Same runtime surface -> same result."""
        for _ in range(3):
            client = _make_client([
                _mock_response(json_data=CANONICAL_IDENTITY),
                _mock_response(json_data=CANONICAL_HEALTH),
                _mock_response(json_data=CANONICAL_STATE),
            ])
            result = client.check_compatibility()
            assert result.compatibility_status == CompatibilityStatus.COMPATIBLE

    def test_result_fields_complete(self) -> None:
        client = _make_client([
            _mock_response(json_data=CANONICAL_IDENTITY),
            _mock_response(json_data=CANONICAL_HEALTH),
            _mock_response(json_data=CANONICAL_STATE),
        ])
        result = client.check_compatibility()
        assert result.sdk_version
        assert result.runtime_name
        assert result.runtime_version
        assert result.checked_at
        assert isinstance(result.failures, list)
        assert isinstance(result.warnings, list)


# --------------------------------------------------------------
# INV-06: SDK-RECEIPT-SEMANTICS-TRUTHFUL
# --------------------------------------------------------------


class TestReceiptSemantics:
    """Receipt parsing must preserve public field truth without inventing private fields."""

    def test_receipt_preserves_all_public_fields(self) -> None:
        receipt = RealizationReceipt.model_validate(CANONICAL_RECEIPT)
        assert receipt.digest == "sha256:abc123"
        assert receipt.status == "ACCEPT"
        assert receipt.message == "Digest realized successfully."
        assert receipt.realized_at.year == 2026

    def test_receipt_does_not_fabricate_defaults(self) -> None:
        """message can be empty but must not be fabricated."""
        data = {
            "digest": "sha256:x",
            "status": "ACCEPT",
            "realized_at": "2026-01-01T00:00:00Z",
        }
        receipt = RealizationReceipt.model_validate(data)
        assert receipt.message == ""

    def test_receipt_does_not_expose_private_governance(self) -> None:
        d = RealizationReceipt.model_validate(CANONICAL_RECEIPT).model_dump()
        assert "governance_verdict" not in d
        assert "pointer_state" not in d
        assert "promotion_state" not in d

    def test_receipt_already_realized_truthful(self) -> None:
        data = {
            "digest": "sha256:abc123",
            "status": "ALREADY_REALIZED",
            "message": "Digest was previously realized.",
            "realized_at": "2026-03-06T12:01:00+00:00",
        }
        receipt = RealizationReceipt.model_validate(data)
        assert receipt.status == "ALREADY_REALIZED"


# --------------------------------------------------------------
# INV-07: SDK-MODE-SEMANTICS-TRUTHFUL
# --------------------------------------------------------------


class TestModeSemantics:
    """Runtime mode/environment must remain bounded to public truth."""

    def test_identity_environment_exposed(self) -> None:
        model = RuntimeIdentity.model_validate(CANONICAL_IDENTITY)
        assert model.environment == "dev"

    def test_identity_does_not_expose_lane(self) -> None:
        data = {**CANONICAL_IDENTITY, "internal_lane": "staging"}
        model = RuntimeIdentity.model_validate(data)
        d = model.model_dump()
        assert "internal_lane" not in d

    def test_identity_unknown_environment_preserved(self) -> None:
        data = {**CANONICAL_IDENTITY, "environment": "unknown"}
        model = RuntimeIdentity.model_validate(data)
        assert model.environment == "unknown"


# --------------------------------------------------------------
# Error Handling - transport vs runtime vs schema vs API
# --------------------------------------------------------------


class TestErrorHandling:
    """SDK must distinguish error classes so callers know root cause."""

    def test_transport_error_on_connection_failure(self) -> None:
        import requests as _req
        session = MagicMock()
        session.request.side_effect = _req.ConnectionError("refused")
        client = KeyholeClient(base_url="http://test:8080", session=session)
        with pytest.raises(TransportError):
            client.get_identity()

    def test_transport_error_on_timeout(self) -> None:
        import requests as _req
        session = MagicMock()
        session.request.side_effect = _req.Timeout("timed out")
        client = KeyholeClient(base_url="http://test:8080", session=session)
        with pytest.raises(TransportError):
            client.get_health()

    def test_runtime_unavailable_on_500(self) -> None:
        client = _make_client([_mock_response(status_code=500, text="Internal")])
        with pytest.raises(RuntimeUnavailableError):
            client.get_identity()

    def test_public_endpoint_error_on_4xx(self) -> None:
        resp = _mock_response(status_code=404, json_data={"error": "not_found", "detail": "missing"})
        client = _make_client([resp])
        with pytest.raises(PublicEndpointError) as exc_info:
            client.get_identity()
        assert exc_info.value.status_code == 404

    def test_schema_error_on_bad_shape(self) -> None:
        client = _make_client([_mock_response(json_data={"bad": "shape"})])
        with pytest.raises(SchemaError):
            client.get_identity()

    def test_exception_hierarchy(self) -> None:
        assert issubclass(TransportError, KeyholeSDKError)
        assert issubclass(RuntimeUnavailableError, KeyholeSDKError)
        assert issubclass(SchemaError, KeyholeSDKError)
        assert issubclass(CompatibilityError, KeyholeSDKError)
        assert issubclass(PublicEndpointError, KeyholeSDKError)


# --------------------------------------------------------------
# INV-05: SDK-EXAMPLES-NO-AD-HOC-DRIFT
# --------------------------------------------------------------


class TestExampleConvergence:
    """Public examples must use SDK surfaces, not ad hoc raw shapes."""

    def test_typed_example_exists(self) -> None:
        example = Path(__file__).resolve().parents[2] / "examples" / "python-client" / "example_typed.py"
        assert example.exists(), f"Typed example missing: {example}"

    def test_typed_example_imports_sdk(self) -> None:
        example = Path(__file__).resolve().parents[2] / "examples" / "python-client" / "example_typed.py"
        content = example.read_text(encoding="utf-8")
        assert "from keyhole_sdk import" in content
        assert "KeyholeClient" in content

    def test_typed_example_uses_typed_methods(self) -> None:
        example = Path(__file__).resolve().parents[2] / "examples" / "python-client" / "example_typed.py"
        content = example.read_text(encoding="utf-8")
        assert "get_identity" in content
        assert "check_compatibility" in content
        assert "realize_typed" in content

    def test_typed_example_uses_error_handling(self) -> None:
        example = Path(__file__).resolve().parents[2] / "examples" / "python-client" / "example_typed.py"
        content = example.read_text(encoding="utf-8")
        assert "TransportError" in content
        assert "SchemaError" in content


# --------------------------------------------------------------
# INV-09: SDK-RELEASE-COMPATIBILITY-GATED
# --------------------------------------------------------------


class TestReleaseCompatibilityRules:
    """Release rules must exist and be explicit."""

    def test_rules_defined(self) -> None:
        assert "compatible_changes" in COMPATIBILITY_RULES
        assert "conditionally_compatible_changes" in COMPATIBILITY_RULES
        assert "incompatible_changes" in COMPATIBILITY_RULES
        assert "promotion_rule" in COMPATIBILITY_RULES

    def test_incompatible_rules_non_empty(self) -> None:
        assert len(COMPATIBILITY_RULES["incompatible_changes"]) >= 3

    def test_promotion_rule_mentions_reject(self) -> None:
        assert "REJECT" in COMPATIBILITY_RULES["promotion_rule"]

    def test_sdk_version_matches_pyproject(self) -> None:
        pyproject = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-sdk" / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert f'version = "{SDK_VERSION}"' in content


# --------------------------------------------------------------
# Contract Tests - SDK models against public evidence fixtures
# --------------------------------------------------------------


class TestContractAgainstEvidence:
    """SDK models must parse real evidence artifacts successfully."""

    def test_identity_parses_evidence_fixture(self) -> None:
        """Parse the canonical identity from the public surface contract doc."""
        data = {
            "runtime_id": "keyhole-test-runtime",
            "runtime_name": "Keyhole Test Runtime",
            "runtime_version": "0.1.0",
            "environment": "dev",
            "capabilities": ["realize", "state", "health"],
        }
        model = RuntimeIdentity.model_validate(data)
        assert model.runtime_id == "keyhole-test-runtime"

    def test_receipt_parses_evidence_fixture(self) -> None:
        data = {
            "digest": "sha256:abc123",
            "status": "ACCEPT",
            "message": "Digest realized successfully.",
            "realized_at": "2026-03-06T12:01:00+00:00",
        }
        model = RealizationReceipt.model_validate(data)
        assert model.status == "ACCEPT"

    def test_health_parses_evidence_fixture(self) -> None:
        model = RuntimeHealth.model_validate({"status": "ok"})
        assert model.status == "ok"

    def test_state_parses_evidence_fixture(self) -> None:
        data = {
            "current_digest": None,
            "realized_digests": [],
            "updated_at": "2026-03-06T12:00:00+00:00",
        }
        model = RuntimeState.model_validate(data)
        assert model.current_digest is None


# --------------------------------------------------------------
# Negative-path tests
# --------------------------------------------------------------


class TestNegativePaths:
    """Validate failures are caught and classified correctly."""

    def test_malformed_identity_response(self) -> None:
        client = _make_client([_mock_response(json_data={"unexpected": True})])
        with pytest.raises(SchemaError):
            client.get_identity()

    def test_incomplete_receipt_response(self) -> None:
        """Missing required receipt fields."""
        client = _make_client([_mock_response(json_data={"digest": "x"})])
        with pytest.raises(SchemaError):
            client.realize_typed("sha256:x")

    def test_private_field_dependency_forbidden(self) -> None:
        """SDK models must not require private fields."""
        identity_fields = set(RuntimeIdentity.model_fields.keys())
        assert not identity_fields & PRIVATE_FIELDS, "Identity model must not use private fields"

        state_fields = set(RuntimeState.model_fields.keys())
        assert not state_fields & PRIVATE_FIELDS, "State model must not use private fields"

        receipt_fields = set(RealizationReceipt.model_fields.keys())
        assert not receipt_fields & PRIVATE_FIELDS, "Receipt model must not use private fields"
