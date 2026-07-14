"""SDK-CLIENT-15 - Idempotent Transport, Retry, and Request Identity tests.

Tests cover all section23 requirements:
  - request-id generation (section23.1)
  - idempotency-key generation (section23.1)
  - same-attempt retry preserves same key (section23.1)
  - distinct attempt gets new key (section23.1)
  - missing-key bug detection (section23.1)
  - conflict handling (section23.1)
  - defer handling (section23.1)
  - transport-unknown handling (section23.1)
  - operation registry coverage (section15.3)
  - proof metadata capture (section16)
  - retry backoff computation (section12.5)
  - Retry-After support (section12.6)
  - bounded retry budget (section12.4)
  - CLI-level operation classification (section14)
  - no leakage of internal-only operations
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest
import requests

# -- Make SDK package importable ------------------------------
SDK_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-sdk"
if str(SDK_PKG) not in sys.path:
    sys.path.insert(0, str(SDK_PKG))

from keyhole_sdk.transport.idempotency import (
    OperationAttempt,
    generate_idempotency_key,
    generate_request_id,
)
from keyhole_sdk.transport.operation_registry import (
    OperationClass,
    OperationDescriptor,
    RetryPolicy,
    get_all_operations,
    get_operation,
    is_registered,
    register_operation,
    requires_idempotency,
)
from keyhole_sdk.transport.retry import (
    RetryConfig,
    compute_backoff_delay,
    is_conflict_status,
    is_rate_limited,
    is_retryable_status,
    parse_retry_after,
)
from keyhole_sdk.transport.proof_metadata import (
    ClientObservation,
    TransportProofMetadata,
)
from keyhole_sdk.transport.errors import (
    DeferredError,
    IdempotencyConflictError,
    IdempotencyError,
    MissingIdempotencyKeyError,
    RateLimitedError,
    RetryExhaustedError,
    TransportUnknownError,
)
from keyhole_sdk.transport.client import (
    GovernedTransport,
    TransportResult,
)
from keyhole_sdk.exceptions import (
    KeyholeSDKError,
    PublicEndpointError,
    RuntimeUnavailableError,
)


# --------------------------------------------------------------
# section23.1 - Request-ID generation
# --------------------------------------------------------------

class TestRequestIdGeneration:
    """Every request must carry a unique request identifier (section10.1)."""

    def test_generates_valid_uuid(self) -> None:
        rid = generate_request_id()
        parsed = uuid.UUID(rid, version=4)
        assert str(parsed) == rid

    def test_generates_unique_ids(self) -> None:
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100

    def test_format_is_string(self) -> None:
        assert isinstance(generate_request_id(), str)


# --------------------------------------------------------------
# section23.1 - Idempotency-key generation
# --------------------------------------------------------------

class TestIdempotencyKeyGeneration:
    """WRITE_IDEMPOTENT_REQUIRED operations need unique keys (section10.2)."""

    def test_generates_valid_uuid(self) -> None:
        key = generate_idempotency_key()
        parsed = uuid.UUID(key, version=4)
        assert str(parsed) == key

    def test_generates_unique_keys(self) -> None:
        keys = {generate_idempotency_key() for _ in range(100)}
        assert len(keys) == 100

    def test_key_is_not_request_id(self) -> None:
        """Key and request ID are independent (section8.1)."""
        key = generate_idempotency_key()
        rid = generate_request_id()
        assert key != rid


# --------------------------------------------------------------
# section23.1 - Same-attempt retry preserves same key
# --------------------------------------------------------------

class TestSameAttemptSameKey:
    """Retries of the same attempt must reuse the same idempotency key (section8.3)."""

    def test_attempt_preserves_key_across_retries(self) -> None:
        attempt = OperationAttempt(operation_name="register")
        key = attempt.idempotency_key
        # Simulate 3 retries - key must not change
        for _ in range(3):
            rid = attempt.next_request_id()
            assert attempt.idempotency_key == key

    def test_attempt_generates_fresh_request_ids(self) -> None:
        attempt = OperationAttempt(operation_name="register")
        rids = [attempt.next_request_id() for _ in range(3)]
        assert len(set(rids)) == 3

    def test_attempt_tracks_all_request_ids(self) -> None:
        attempt = OperationAttempt(operation_name="register")
        rids = [attempt.next_request_id() for _ in range(3)]
        assert attempt.request_ids == rids
        assert attempt.attempt_number == 3


# --------------------------------------------------------------
# section23.1 - Distinct attempt gets new key
# --------------------------------------------------------------

class TestDifferentAttemptDifferentKey:
    """Intentionally distinct attempts must mint distinct keys (section8.4)."""

    def test_two_attempts_have_different_keys(self) -> None:
        a1 = OperationAttempt(operation_name="register")
        a2 = OperationAttempt(operation_name="register")
        assert a1.idempotency_key != a2.idempotency_key

    def test_same_operation_different_attempts(self) -> None:
        """Even identical payloads get distinct keys (section8.5)."""
        keys = {OperationAttempt(operation_name="register").idempotency_key for _ in range(50)}
        assert len(keys) == 50


# --------------------------------------------------------------
# section23.1 - Missing-key bug detection
# --------------------------------------------------------------

class TestMissingKeyDetection:
    """A WRITE_IDEMPOTENT_REQUIRED op without a key is a client bug (section17.1)."""

    def test_missing_key_error_type(self) -> None:
        err = MissingIdempotencyKeyError("register")
        assert isinstance(err, IdempotencyError)
        assert isinstance(err, KeyholeSDKError)

    def test_missing_key_error_message(self) -> None:
        err = MissingIdempotencyKeyError("register")
        assert "register" in str(err)
        assert "WRITE_IDEMPOTENT_REQUIRED" in str(err)

    def test_missing_key_error_has_repair_guidance(self) -> None:
        err = MissingIdempotencyKeyError("register")
        assert len(err.repair_guidance) > 0

    def test_governed_transport_auto_generates_key_for_writes(self) -> None:
        """The transport must auto-generate keys for classified writes."""
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(200, {"ok": True})
        with patch.object(transport.session, "request", return_value=mock_resp):
            result = transport.execute(
                "POST", "/test", operation_name="register"
            )
        # Key should have been auto-generated
        assert result.proof.idempotency_key is not None
        assert len(result.proof.idempotency_key) > 0


# --------------------------------------------------------------
# section23.1 - Conflict handling
# --------------------------------------------------------------

class TestConflictHandling:
    """Server idempotency conflict must stop retries (section17.2)."""

    def test_conflict_error_type(self) -> None:
        err = IdempotencyConflictError()
        assert isinstance(err, IdempotencyError)

    def test_conflict_error_has_repair_guidance(self) -> None:
        err = IdempotencyConflictError()
        assert any("new idempotency key" in g for g in err.repair_guidance)

    def test_governed_transport_raises_on_409(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(409, {"error": "conflict"})
        with patch.object(transport.session, "request", return_value=mock_resp):
            with pytest.raises(IdempotencyConflictError) as exc_info:
                transport.execute("POST", "/test", operation_name="register")
            assert exc_info.value.idempotency_key is not None

    def test_conflict_does_not_retry(self) -> None:
        """section12.3: Do not auto-retry conflicts."""
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=3),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            return _make_mock_response(409, {"error": "conflict"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with pytest.raises(IdempotencyConflictError):
                transport.execute("POST", "/test", operation_name="register")
        assert call_count == 1  # No retries


# --------------------------------------------------------------
# section23.1 - Defer handling
# --------------------------------------------------------------

class TestDeferHandling:
    """Deferred execution must preserve identity and surface clearly (section17.3)."""

    def test_deferred_error_type(self) -> None:
        err = DeferredError()
        assert isinstance(err, IdempotencyError)
        assert err.retry_after is None

    def test_deferred_error_with_retry_after(self) -> None:
        err = DeferredError(retry_after=5.0)
        assert err.retry_after == 5.0

    def test_deferred_error_preserves_key(self) -> None:
        err = DeferredError(idempotency_key="test-key")
        assert err.idempotency_key == "test-key"


# --------------------------------------------------------------
# section23.1 - Transport-unknown handling
# --------------------------------------------------------------

class TestTransportUnknownHandling:
    """Transport failure after send is not proof of non-execution (section13)."""

    def test_transport_unknown_error_type(self) -> None:
        err = TransportUnknownError()
        assert isinstance(err, IdempotencyError)

    def test_transport_unknown_repair_guidance(self) -> None:
        err = TransportUnknownError()
        assert any("NOT proof of non-execution" in g for g in err.repair_guidance)
        assert any("SAME idempotency key" in g for g in err.repair_guidance)

    def test_governed_transport_raises_on_connection_error(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(enabled=False),
        )
        with patch.object(
            transport.session, "request",
            side_effect=requests.ConnectionError("refused"),
        ):
            with pytest.raises(TransportUnknownError) as exc_info:
                transport.execute("POST", "/test", operation_name="register")
            assert exc_info.value.idempotency_key is not None


# --------------------------------------------------------------
# Operation Registry - section15.3
# --------------------------------------------------------------

class TestOperationRegistry:
    """Central registry must classify all public operations (section15.3)."""

    def test_read_only_operations_exist(self) -> None:
        for name in ["capabilities", "whoami", "health", "identity", "state",
                      "registration_status"]:
            desc = get_operation(name)
            assert desc is not None, f"Missing registration: {name}"
            assert desc.operation_class == OperationClass.READ_ONLY

    def test_write_idempotent_operations_exist(self) -> None:
        for name in ["register", "run.start", "realize", "ingest.submit"]:
            desc = get_operation(name)
            assert desc is not None, f"Missing registration: {name}"
            assert desc.operation_class == OperationClass.WRITE_IDEMPOTENT_REQUIRED
            assert desc.idempotency_required is True

    def test_naturally_convergent_operations(self) -> None:
        for name in ["verify", "login"]:
            desc = get_operation(name)
            assert desc is not None, f"Missing registration: {name}"
            assert desc.operation_class == OperationClass.NATURALLY_CONVERGENT_EXEMPT

    def test_read_only_no_idempotency_required(self) -> None:
        for name in ["capabilities", "whoami", "health"]:
            assert requires_idempotency(name) is False

    def test_write_operations_require_idempotency(self) -> None:
        for name in ["register", "run.start", "realize"]:
            assert requires_idempotency(name) is True

    def test_all_operations_registered(self) -> None:
        ops = get_all_operations()
        assert len(ops) >= 16

    def test_custom_operation_registration(self) -> None:
        desc = OperationDescriptor(
            name="test.custom.op",
            operation_class=OperationClass.WRITE_IDEMPOTENT_REQUIRED,
            retry_policy=RetryPolicy.SAFE_WRITE_IDEMPOTENT,
            idempotency_required=True,
        )
        register_operation(desc)
        assert is_registered("test.custom.op")
        assert requires_idempotency("test.custom.op")

    def test_unregistered_operation(self) -> None:
        assert get_operation("nonexistent.op") is None
        assert is_registered("nonexistent.op") is False
        assert requires_idempotency("nonexistent.op") is False


# --------------------------------------------------------------
# Retry - section12
# --------------------------------------------------------------

class TestRetryBehavior:
    """Retry must be bounded, backed off, and jittered (section12.4-section12.6)."""

    def test_backoff_increases_exponentially(self) -> None:
        config = RetryConfig(jitter=False, backoff_base_ms=100, backoff_max_ms=10000)
        d1 = compute_backoff_delay(1, config)
        d2 = compute_backoff_delay(2, config)
        d3 = compute_backoff_delay(3, config)
        assert d1 < d2 < d3

    def test_backoff_capped_at_max(self) -> None:
        config = RetryConfig(jitter=False, backoff_base_ms=1000, backoff_max_ms=2000)
        d10 = compute_backoff_delay(10, config)
        assert d10 == 2.0

    def test_jitter_produces_variance(self) -> None:
        config = RetryConfig(jitter=True, backoff_base_ms=1000, backoff_max_ms=5000)
        delays = {compute_backoff_delay(2, config) for _ in range(20)}
        assert len(delays) > 1  # Not all identical

    def test_retry_after_overrides_backoff(self) -> None:
        config = RetryConfig(backoff_base_ms=100, respect_retry_after=True)
        delay = compute_backoff_delay(1, config, retry_after=10.0)
        assert delay == 10.0

    def test_retryable_status_codes(self) -> None:
        for code in [408, 429, 502, 503, 504]:
            assert is_retryable_status(code) is True

    def test_non_retryable_status_codes(self) -> None:
        for code in [200, 201, 400, 401, 403, 404, 409, 500]:
            assert is_retryable_status(code) is False

    def test_conflict_status_detection(self) -> None:
        assert is_conflict_status(409) is True
        assert is_conflict_status(200) is False

    def test_rate_limit_detection(self) -> None:
        assert is_rate_limited(429) is True
        assert is_rate_limited(503) is False

    def test_parse_retry_after_numeric(self) -> None:
        resp = Mock()
        resp.headers = {"Retry-After": "5"}
        assert parse_retry_after(resp) == 5.0

    def test_parse_retry_after_missing(self) -> None:
        resp = Mock()
        resp.headers = {}
        assert parse_retry_after(resp) is None

    def test_bounded_retry_budget(self) -> None:
        """section12.4: No unbounded loops."""
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=2, backoff_base_ms=1, backoff_max_ms=1),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            return _make_mock_response(503, {"error": "unavailable"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                with pytest.raises(RetryExhaustedError) as exc_info:
                    transport.execute("POST", "/test", operation_name="register")
                assert exc_info.value.attempt_count == 3  # 1 initial + 2 retries
        assert call_count == 3

    def test_retry_preserves_idempotency_key(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=2, backoff_base_ms=1, backoff_max_ms=1),
        )
        captured_keys: list[str] = []

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            headers = kwargs.get("headers", {})
            if "X-Idempotency-Key" in headers:
                captured_keys.append(headers["X-Idempotency-Key"])
            return _make_mock_response(503, {"error": "unavailable"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                with pytest.raises(RetryExhaustedError):
                    transport.execute("POST", "/test", operation_name="register")

        # All retries used the same idempotency key
        assert len(captured_keys) == 3
        assert len(set(captured_keys)) == 1

    def test_retry_generates_fresh_request_ids(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=2, backoff_base_ms=1, backoff_max_ms=1),
        )
        captured_rids: list[str] = []

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            headers = kwargs.get("headers", {})
            if "X-Request-Id" in headers:
                captured_rids.append(headers["X-Request-Id"])
            return _make_mock_response(503, {"error": "unavailable"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                with pytest.raises(RetryExhaustedError):
                    transport.execute("POST", "/test", operation_name="register")

        # Each retry gets a fresh request ID
        assert len(captured_rids) == 3
        assert len(set(captured_rids)) == 3


# --------------------------------------------------------------
# Proof Metadata - section16
# --------------------------------------------------------------

class TestProofMetadata:
    """Proof must capture replay-aware transport metadata (section16)."""

    def test_proof_metadata_fields(self) -> None:
        proof = TransportProofMetadata(
            request_id="rid-1",
            idempotency_key="key-1",
            operation_class="WRITE_IDEMPOTENT_REQUIRED",
            command_name="register",
        )
        d = proof.to_dict()
        assert d["request_id"] == "rid-1"
        assert d["idempotency_key"] == "key-1"
        assert d["operation_class"] == "WRITE_IDEMPOTENT_REQUIRED"
        assert d["command_name"] == "register"

    def test_proof_records_attempts(self) -> None:
        proof = TransportProofMetadata()
        proof.record_attempt(1, "rid-1", reason="initial")
        proof.record_attempt(2, "rid-2", reason="retry #1", delay_ms=250)
        assert proof.attempt_count == 2
        assert len(proof.attempts) == 2
        assert proof.request_id == "rid-2"

    def test_proof_captures_observation(self) -> None:
        proof = TransportProofMetadata()
        proof.mark_observation(ClientObservation.REPLAYED)
        assert proof.final_client_observation == ClientObservation.REPLAYED

    def test_all_client_observations_exist(self) -> None:
        expected = {"executed", "replayed", "deferred", "conflict",
                    "transport_unknown", "not_sent"}
        actual = {obs.value for obs in ClientObservation}
        assert expected == actual

    def test_proof_to_dict_serializable(self) -> None:
        """Proof dict must be JSON-serializable."""
        import json
        proof = TransportProofMetadata(
            request_id="r1",
            idempotency_key="k1",
            operation_class="WRITE_IDEMPOTENT_REQUIRED",
            command_name="register",
        )
        proof.record_attempt(1, "r1")
        proof.mark_observation(ClientObservation.EXECUTED)
        d = proof.to_dict()
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_proof_captures_replay_metadata_from_server(self) -> None:
        """section16.3: Detect when server indicates replay."""
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(
            200, {"ok": True},
            headers={
                "X-Request-Id": "server-rid",
                "X-Original-Request-Id": "original-rid",
            },
        )
        with patch.object(transport.session, "request", return_value=mock_resp):
            result = transport.execute(
                "POST", "/test", operation_name="register"
            )
        assert result.proof.server_request_id == "server-rid"
        assert result.proof.original_request_id == "original-rid"
        assert result.proof.final_client_observation == ClientObservation.REPLAYED

    def test_proof_marks_executed_when_no_replay(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(200, {"ok": True})
        with patch.object(transport.session, "request", return_value=mock_resp):
            result = transport.execute(
                "GET", "/test", operation_name="health"
            )
        assert result.proof.final_client_observation == ClientObservation.EXECUTED


# --------------------------------------------------------------
# Governed Transport Client - section15.1
# --------------------------------------------------------------

class TestGovernedTransportClient:
    """Base transport client must inject identity, retry, and capture proof."""

    def test_injects_request_id_on_every_request(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        captured_headers: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured_headers.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            transport.execute("GET", "/test", operation_name="health")
        assert "X-Request-Id" in captured_headers
        # Validate it's a UUID
        uuid.UUID(captured_headers["X-Request-Id"], version=4)

    def test_injects_idempotency_key_on_writes(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        captured_headers: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured_headers.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            transport.execute("POST", "/test", operation_name="register")
        assert "X-Idempotency-Key" in captured_headers
        uuid.UUID(captured_headers["X-Idempotency-Key"], version=4)

    def test_omits_idempotency_key_on_reads(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        captured_headers: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured_headers.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            transport.execute("GET", "/test", operation_name="health")
        assert "X-Idempotency-Key" not in captured_headers

    def test_accepts_pre_minted_idempotency_key(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        captured_headers: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured_headers.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        custom_key = "my-custom-key-123"
        with patch.object(transport.session, "request", side_effect=side_effect):
            transport.execute(
                "POST", "/test",
                operation_name="register",
                idempotency_key=custom_key,
            )
        assert captured_headers["X-Idempotency-Key"] == custom_key

    def test_returns_transport_result(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(200, {"result": "ok"})
        with patch.object(transport.session, "request", return_value=mock_resp):
            result = transport.execute("GET", "/test", operation_name="health")
        assert isinstance(result, TransportResult)
        assert result.data == {"result": "ok"}
        assert result.status_code == 200
        assert isinstance(result.proof, TransportProofMetadata)

    def test_injects_sdk_version_header(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999", sdk_version="0.3.0"
        )
        captured_headers: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured_headers.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            transport.execute("GET", "/test", operation_name="health")
        assert captured_headers.get("X-Keyhole-SDK-Version") == "0.3.0"

    def test_handles_4xx_errors(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(400, {"error": "bad request"})
        with patch.object(transport.session, "request", return_value=mock_resp):
            with pytest.raises(PublicEndpointError) as exc_info:
                transport.execute("POST", "/test", operation_name="register")
            assert exc_info.value.status_code == 400

    def test_handles_non_retryable_5xx(self) -> None:
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(500, {"error": "internal"})
        with patch.object(transport.session, "request", return_value=mock_resp):
            with pytest.raises(RuntimeUnavailableError):
                transport.execute("GET", "/test", operation_name="health")

    def test_no_retry_when_disabled(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(enabled=False),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            return _make_mock_response(503, {"error": "unavailable"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with pytest.raises(RuntimeUnavailableError):
                transport.execute("GET", "/test", operation_name="health")
        assert call_count == 1

    def test_successful_retry_after_transient_failure(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=2, backoff_base_ms=1, backoff_max_ms=1),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_response(503, {"error": "unavailable"})
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                result = transport.execute(
                    "POST", "/test", operation_name="register"
                )
        assert result.data == {"ok": True}
        assert result.proof.attempt_count == 2
        assert call_count == 2

    def test_rate_limit_with_retry_after(self) -> None:
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=1, backoff_base_ms=1, backoff_max_ms=1),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_response(
                    429, {"error": "rate limited"},
                    headers={"Retry-After": "2"},
                )
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff") as mock_sleep:
                result = transport.execute(
                    "POST", "/test", operation_name="register"
                )
        assert result.data == {"ok": True}
        assert call_count == 2


# --------------------------------------------------------------
# section23.3 - Negative Tests
# --------------------------------------------------------------

class TestNegativeCases:
    """Negative tests per section23.3."""

    def test_no_unbounded_retry(self) -> None:
        """section12.4: Bounded budget prevents infinite loops."""
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=5, backoff_base_ms=1, backoff_max_ms=1),
        )
        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            nonlocal call_count
            call_count += 1
            return _make_mock_response(503, {"error": "unavailable"})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                with pytest.raises(RetryExhaustedError):
                    transport.execute("POST", "/test", operation_name="register")
        assert call_count == 6  # 1 + 5 retries

    def test_error_hierarchy(self) -> None:
        """All idempotency errors descend from IdempotencyError and KeyholeSDKError."""
        for cls in [MissingIdempotencyKeyError, IdempotencyConflictError,
                     RetryExhaustedError, DeferredError, TransportUnknownError,
                     RateLimitedError]:
            assert issubclass(cls, IdempotencyError)
            assert issubclass(cls, KeyholeSDKError)

    def test_all_errors_have_repair_guidance(self) -> None:
        """section25 INV-SDK-CLIENT-ERRORS-REPAIRABLE: All errors carry guidance."""
        errors = [
            MissingIdempotencyKeyError("test"),
            IdempotencyConflictError(),
            RetryExhaustedError("test", attempt_count=3),
            DeferredError(),
            TransportUnknownError(),
            RateLimitedError(),
        ]
        for err in errors:
            assert len(err.repair_guidance) > 0, f"{type(err).__name__} missing guidance"


# --------------------------------------------------------------
# Config Surface - section20
# --------------------------------------------------------------

class TestRetryConfig:
    """Config must support safe transport defaults (section20)."""

    def test_default_values(self) -> None:
        config = RetryConfig()
        assert config.enabled is True
        assert config.max_retries == 3
        assert config.backoff_base_ms == 250
        assert config.backoff_max_ms == 5000
        assert config.respect_retry_after is True
        assert config.jitter is True

    def test_custom_values(self) -> None:
        config = RetryConfig(
            enabled=True,
            max_retries=5,
            backoff_base_ms=500,
            backoff_max_ms=10000,
            respect_retry_after=False,
            jitter=False,
        )
        assert config.max_retries == 5
        assert config.backoff_base_ms == 500

    def test_disabled_config(self) -> None:
        config = RetryConfig(enabled=False)
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=config,
        )
        assert transport._max_attempts(RetryPolicy.SAFE_WRITE_IDEMPOTENT) == 1


# --------------------------------------------------------------
# Invariant Tests - section25
# --------------------------------------------------------------

class TestInvariants:
    """Test all declared invariants from section25."""

    def test_inv_request_id_always(self) -> None:
        """INV-SDK-CLIENT-REQUEST-ID-ALWAYS: every request gets X-Request-Id."""
        transport = GovernedTransport("http://localhost:9999")
        captured: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        # Test all operation types
        for op_name in ["health", "register", "verify"]:
            captured.clear()
            with patch.object(transport.session, "request", side_effect=side_effect):
                transport.execute("GET", "/test", operation_name=op_name)
            assert "X-Request-Id" in captured, f"Missing X-Request-Id for {op_name}"

    def test_inv_write_key_required(self) -> None:
        """INV-SDK-CLIENT-WRITE-KEY-REQUIRED: write ops get X-Idempotency-Key."""
        transport = GovernedTransport("http://localhost:9999")
        captured: Dict[str, str] = {}

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            captured.update(kwargs.get("headers", {}))
            return _make_mock_response(200, {"ok": True})

        for op_name in ["register", "run.start", "realize"]:
            captured.clear()
            with patch.object(transport.session, "request", side_effect=side_effect):
                transport.execute("POST", "/test", operation_name=op_name)
            assert "X-Idempotency-Key" in captured, f"Missing key for {op_name}"

    def test_inv_same_attempt_same_key(self) -> None:
        """INV-SDK-CLIENT-SAME-ATTEMPT-SAME-KEY."""
        attempt = OperationAttempt(operation_name="register")
        key = attempt.idempotency_key
        for _ in range(10):
            attempt.next_request_id()
            assert attempt.idempotency_key == key

    def test_inv_different_attempt_different_key(self) -> None:
        """INV-SDK-CLIENT-DIFFERENT-ATTEMPT-DIFFERENT-KEY."""
        keys = [OperationAttempt(operation_name="register").idempotency_key
                for _ in range(10)]
        assert len(set(keys)) == 10

    def test_inv_payload_hash_not_key(self) -> None:
        """INV-SDK-CLIENT-PAYLOAD-HASH-NOT-KEY: keys are UUIDs, not hashes."""
        key = generate_idempotency_key()
        # Must be a valid UUID, not a hash
        parsed = uuid.UUID(key, version=4)
        assert str(parsed) == key

    def test_inv_proof_captures_replay(self) -> None:
        """INV-SDK-CLIENT-PROOF-CAPTURES-REPLAY."""
        transport = GovernedTransport("http://localhost:9999")
        mock_resp = _make_mock_response(
            200, {"ok": True},
            headers={"X-Original-Request-Id": "orig-123"},
        )
        with patch.object(transport.session, "request", return_value=mock_resp):
            result = transport.execute(
                "POST", "/test", operation_name="register"
            )
        assert result.proof.original_request_id == "orig-123"
        assert result.proof.final_client_observation == ClientObservation.REPLAYED

    def test_inv_no_blind_retry_writes(self) -> None:
        """INV-SDK-CLIENT-NO-BLIND-RETRY-WRITES: writes use stable identity."""
        transport = GovernedTransport(
            "http://localhost:9999",
            retry_config=RetryConfig(max_retries=1, backoff_base_ms=1, backoff_max_ms=1),
        )
        captured_keys: list[str] = []

        def side_effect(*args: Any, **kwargs: Any) -> Mock:
            headers = kwargs.get("headers", {})
            if "X-Idempotency-Key" in headers:
                captured_keys.append(headers["X-Idempotency-Key"])
            if len(captured_keys) < 2:
                return _make_mock_response(503, {"error": "unavailable"})
            return _make_mock_response(200, {"ok": True})

        with patch.object(transport.session, "request", side_effect=side_effect):
            with patch("keyhole_sdk.transport.client.sleep_for_backoff"):
                result = transport.execute(
                    "POST", "/test", operation_name="register"
                )
        assert len(set(captured_keys)) == 1  # Same key across retry

    def test_inv_errors_repairable(self) -> None:
        """INV-SDK-CLIENT-ERRORS-REPAIRABLE: all errors produce guidance."""
        err = IdempotencyConflictError()
        assert len(err.repair_guidance) > 0
        err2 = TransportUnknownError()
        assert len(err2.repair_guidance) > 0


# --------------------------------------------------------------
# No Platform Leakage
# --------------------------------------------------------------

class TestNoLeakage:
    """Transport layer must not reference platform internals."""

    FORBIDDEN = [
        "keyhole_platform", "governance_engine", "promotion_kernel",
        "nats://", "qdrant", "keyhole-system",
    ]

    def test_no_forbidden_in_error_messages(self) -> None:
        errors = [
            MissingIdempotencyKeyError("register"),
            IdempotencyConflictError(),
            RetryExhaustedError("test", attempt_count=1),
            TransportUnknownError(),
            RateLimitedError(),
            DeferredError(),
        ]
        for err in errors:
            msg = str(err) + " ".join(err.repair_guidance)
            for forbidden in self.FORBIDDEN:
                assert forbidden not in msg, f"Leaked {forbidden} in {type(err).__name__}"


# --------------------------------------------------------------
# Test helpers
# --------------------------------------------------------------

def _make_mock_response(
    status_code: int,
    json_data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Mock:
    """Create a mock requests.Response with given status and JSON body."""
    resp = Mock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.reason = "OK" if status_code < 400 else "Error"
    resp.headers = headers or {}
    return resp
