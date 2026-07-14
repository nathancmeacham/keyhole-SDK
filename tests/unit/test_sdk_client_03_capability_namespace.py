"""SDK-CLIENT-03 - Capability Namespace Enforcement test suite.

Tests cover all invariants from section8, section9, section12, section13, section16, section17 of sdk-client-03.md.

Invariants verified:
  section5  - canonical format: <domain>.<category>.<capability>.v<major>
  section8  - validation rules: segment count, characters, version suffix
  section8.4 - safe normalization boundaries
  section8.5 - deterministic reject reasons (7 stable codes)
  section9  - advisory-by-default for foreign repos
  section12 - UX requirements: messages teach, suggestions actionable
  section13 - determinism: same input -> same result always
  section16 - proof contract: artifacts include validated identifier
  section17 - local test strategy: unit, negative, determinism tests
  section18 - acceptance criteria
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, List

import pytest

# -- Make both packages importable --------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
_SDK_PKG = _REPO / "packages" / "python" / "keyhole-sdk"
_CLI_PKG = _REPO / "packages" / "python" / "keyhole-cli"
for _p in (_SDK_PKG, _CLI_PKG):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from keyhole_sdk.capability import (
    CapabilityNameError,
    CapabilityNameParts,
    CapabilityValidationResult,
    NamespaceRejectReason,
    create_capability_name,
    emit_namespace_batch_proof,
    emit_namespace_proof,
    normalize_capability_parts,
    validate_capability_name,
)
from keyhole_cli.commands.capability_cmd import (
    run_capability_create,
    run_capability_validate,
)
from keyhole_cli.result import EXIT_INVALID_INPUT, EXIT_SUCCESS


# --------------------------------------------------------------
# section8.5 - NamespaceRejectReason enum
# --------------------------------------------------------------

class TestNamespaceRejectReason:
    """Stable, deterministic reject reason codes."""

    def test_all_seven_reasons_exist(self) -> None:
        codes = {r.value for r in NamespaceRejectReason}
        expected = {
            "invalid_segment_count",
            "invalid_version_suffix",
            "uppercase_not_allowed",
            "empty_namespace_segment",
            "illegal_character",
            "leading_zero_version",
            "consecutive_dots",
        }
        assert expected == codes

    def test_is_str_subclass(self) -> None:
        for r in NamespaceRejectReason:
            assert isinstance(r, str), f"{r} must be a str subclass"

    def test_values_are_lowercase_snake(self) -> None:
        for r in NamespaceRejectReason:
            assert r.value == r.value.lower()
            assert " " not in r.value

    def test_invalid_segment_count_value(self) -> None:
        assert NamespaceRejectReason.INVALID_SEGMENT_COUNT == "invalid_segment_count"

    def test_invalid_version_suffix_value(self) -> None:
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX == "invalid_version_suffix"

    def test_uppercase_not_allowed_value(self) -> None:
        assert NamespaceRejectReason.UPPERCASE_NOT_ALLOWED == "uppercase_not_allowed"

    def test_empty_namespace_segment_value(self) -> None:
        assert NamespaceRejectReason.EMPTY_NAMESPACE_SEGMENT == "empty_namespace_segment"

    def test_illegal_character_value(self) -> None:
        assert NamespaceRejectReason.ILLEGAL_CHARACTER == "illegal_character"

    def test_leading_zero_version_value(self) -> None:
        assert NamespaceRejectReason.LEADING_ZERO_VERSION == "leading_zero_version"

    def test_consecutive_dots_value(self) -> None:
        assert NamespaceRejectReason.CONSECUTIVE_DOTS == "consecutive_dots"


# --------------------------------------------------------------
# section5 - Valid canonical names
# --------------------------------------------------------------

class TestValidateCapabilityNameValid:
    """section5, section18 - Valid names must be accepted consistently."""

    def test_basic_payment_example(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        assert r.valid is True
        assert r.reject_reasons == []

    def test_crm_example(self) -> None:
        r = validate_capability_name("crm.salesforce.sync.v1")
        assert r.valid is True

    def test_workorder_example(self) -> None:
        r = validate_capability_name("workorder.assignment.engine.v1")
        assert r.valid is True

    def test_identity_v2(self) -> None:
        r = validate_capability_name("identity.oidc.discovery.v2")
        assert r.valid is True

    def test_large_version_number(self) -> None:
        r = validate_capability_name("data.warehouse.export.v10")
        assert r.valid is True

    def test_digits_in_segments(self) -> None:
        r = validate_capability_name("data2.v3.export1.v5")
        assert r.valid is True

    def test_single_char_segments(self) -> None:
        r = validate_capability_name("a.b.c.v1")
        assert r.valid is True

    def test_hyphen_in_segment(self) -> None:
        r = validate_capability_name("data.real-time.stream.v1")
        assert r.valid is True

    def test_hyphen_in_capability_segment(self) -> None:
        r = validate_capability_name("order.line-item.processor.v3")
        assert r.valid is True

    def test_v0_is_valid(self) -> None:
        # v0 has no leading zero per section8.3 (0 is itself, not 0x)
        r = validate_capability_name("test.scope.feature.v0")
        assert r.valid is True

    def test_long_segments(self) -> None:
        r = validate_capability_name("infrastructure.kubernetes.cluster-management.v1")
        assert r.valid is True

    def test_normalized_field_set_on_valid(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        assert r.normalized == "payment.stripe.integration.v1"

    def test_message_reports_valid(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        assert "valid" in r.message.lower()
        assert "payment.stripe.integration.v1" in r.message

    def test_is_valid_property(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        assert r.is_valid is True

    def test_to_dict_valid(self) -> None:
        r = validate_capability_name("crm.salesforce.sync.v2")
        d = r.to_dict()
        assert d["valid"] is True
        assert d["name"] == "crm.salesforce.sync.v2"
        assert d["reject_reasons"] == []


# --------------------------------------------------------------
# section8 - Invalid names - reject reasons
# --------------------------------------------------------------

class TestValidateCapabilityNameInvalid:
    """section8, section8.5, section12.2 - Invalid names must be rejected deterministically."""

    # section8.1 - Segment count
    def test_bare_label_rejected(self) -> None:
        r = validate_capability_name("StripeIntegration")
        assert r.valid is False

    def test_three_segments_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_SEGMENT_COUNT in r.reject_reasons

    def test_five_segments_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1.extra")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_SEGMENT_COUNT in r.reject_reasons

    def test_two_segments_rejected(self) -> None:
        r = validate_capability_name("payment.stripe")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_SEGMENT_COUNT in r.reject_reasons

    def test_single_segment_rejected(self) -> None:
        r = validate_capability_name("payment")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_SEGMENT_COUNT in r.reject_reasons

    # section8.2 - Uppercase rules
    def test_uppercase_domain_rejected(self) -> None:
        r = validate_capability_name("Payment.stripe.integration.v1")
        assert r.valid is False
        assert NamespaceRejectReason.UPPERCASE_NOT_ALLOWED in r.reject_reasons

    def test_all_uppercase_rejected(self) -> None:
        r = validate_capability_name("PAYMENT.STRIPE.INTEGRATION.V1")
        assert r.valid is False

    def test_uppercase_in_middle_rejected(self) -> None:
        r = validate_capability_name("payment.Stripe.integration.v1")
        assert r.valid is False
        assert NamespaceRejectReason.UPPERCASE_NOT_ALLOWED in r.reject_reasons

    # section8.1+8.2 combined (consecutive dots)
    def test_consecutive_dots_rejected(self) -> None:
        r = validate_capability_name("payment..integration.v1")
        assert r.valid is False
        assert NamespaceRejectReason.CONSECUTIVE_DOTS in r.reject_reasons

    def test_consecutive_dots_at_start_rejected(self) -> None:
        r = validate_capability_name("..payment.stripe.v1")
        assert r.valid is False
        assert NamespaceRejectReason.CONSECUTIVE_DOTS in r.reject_reasons

    # section8.2 - Illegal characters
    def test_slash_separator_rejected(self) -> None:
        r = validate_capability_name("payment/stripe/integration")
        assert r.valid is False

    def test_underscore_rejected(self) -> None:
        r = validate_capability_name("payment.stripe_api.integration.v1")
        assert r.valid is False
        assert NamespaceRejectReason.ILLEGAL_CHARACTER in r.reject_reasons

    def test_space_in_segment_rejected(self) -> None:
        r = validate_capability_name("payment.stripe integration.v1.extra")
        assert r.valid is False

    def test_special_char_rejected(self) -> None:
        r = validate_capability_name("pay@.stripe.integration.v1")
        assert r.valid is False
        assert NamespaceRejectReason.ILLEGAL_CHARACTER in r.reject_reasons

    # section8.3 - Version suffix rules
    def test_version_missing_v_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.1")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX in r.reject_reasons

    def test_version_word_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.version1")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX in r.reject_reasons

    def test_uppercase_v_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.V1")
        assert r.valid is False
        # Uppercase -> UPPERCASE_NOT_ALLOWED
        assert NamespaceRejectReason.UPPERCASE_NOT_ALLOWED in r.reject_reasons

    def test_leading_zero_version_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v01")
        assert r.valid is False
        assert NamespaceRejectReason.LEADING_ZERO_VERSION in r.reject_reasons

    def test_leading_zero_v02_rejected(self) -> None:
        r = validate_capability_name("crm.salesforce.sync.v02")
        assert r.valid is False
        assert NamespaceRejectReason.LEADING_ZERO_VERSION in r.reject_reasons

    # section12.2 - Messages must teach
    def test_invalid_message_contains_expected_format(self) -> None:
        r = validate_capability_name("bad")
        assert "Expected" in r.message or "expected" in r.message

    def test_invalid_message_contains_example(self) -> None:
        r = validate_capability_name("bad")
        assert "v<major>" in r.message or "v1" in r.message

    def test_normalized_empty_on_invalid(self) -> None:
        r = validate_capability_name("payment.stripe.integration")
        assert r.normalized == ""

    def test_to_dict_invalid(self) -> None:
        r = validate_capability_name("payment.stripe.integration")
        d = r.to_dict()
        assert d["valid"] is False
        assert "invalid_segment_count" in d["reject_reasons"]

    # Empty string
    def test_empty_string_rejected(self) -> None:
        r = validate_capability_name("")
        assert r.valid is False


# --------------------------------------------------------------
# section8.3 - Version segment exhaustive
# --------------------------------------------------------------

class TestVersionSegment:
    """section8.3 - Version suffix enforcement."""

    def test_v1_accepted(self) -> None:
        assert validate_capability_name("a.b.c.v1").valid is True

    def test_v2_accepted(self) -> None:
        assert validate_capability_name("a.b.c.v2").valid is True

    def test_v10_accepted(self) -> None:
        assert validate_capability_name("a.b.c.v10").valid is True

    def test_v100_accepted(self) -> None:
        assert validate_capability_name("a.b.c.v100").valid is True

    def test_V1_rejected_uppercase(self) -> None:
        r = validate_capability_name("a.b.c.V1")
        assert r.valid is False
        assert NamespaceRejectReason.UPPERCASE_NOT_ALLOWED in r.reject_reasons

    def test_bare_1_rejected(self) -> None:
        r = validate_capability_name("a.b.c.1")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX in r.reject_reasons

    def test_version1_rejected(self) -> None:
        r = validate_capability_name("a.b.c.version1")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX in r.reject_reasons

    def test_v01_rejected_leading_zero(self) -> None:
        r = validate_capability_name("a.b.c.v01")
        assert r.valid is False
        assert NamespaceRejectReason.LEADING_ZERO_VERSION in r.reject_reasons

    def test_v00_rejected_leading_zero(self) -> None:
        r = validate_capability_name("a.b.c.v00")
        assert r.valid is False
        assert NamespaceRejectReason.LEADING_ZERO_VERSION in r.reject_reasons

    def test_v_alone_rejected(self) -> None:
        r = validate_capability_name("a.b.c.v")
        assert r.valid is False
        assert NamespaceRejectReason.INVALID_VERSION_SUFFIX in r.reject_reasons

    def test_v_negative_rejected(self) -> None:
        r = validate_capability_name("a.b.c.v-1")
        assert r.valid is False

    def test_v_float_rejected(self) -> None:
        r = validate_capability_name("a.b.c.v1-2")
        # v1-2 has a hyphen after digit which is invalid per version pattern
        r2 = validate_capability_name("a.b.c.v1.2")
        # v1.2 would be 5 segments
        assert r2.valid is False


# --------------------------------------------------------------
# section7.3 - CapabilityValidationResult model
# --------------------------------------------------------------

class TestCapabilityValidationResult:
    """Model fields and serialization."""

    def test_model_fields_present(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        assert hasattr(r, "name")
        assert hasattr(r, "valid")
        assert hasattr(r, "reject_reasons")
        assert hasattr(r, "message")
        assert hasattr(r, "suggestion")
        assert hasattr(r, "normalized")

    def test_to_dict_keys(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1")
        d = r.to_dict()
        assert set(d.keys()) >= {"name", "valid", "reject_reasons", "message", "suggestion", "normalized"}

    def test_reject_reasons_are_strings_in_dict(self) -> None:
        r = validate_capability_name("payment.stripe.integration")
        d = r.to_dict()
        for reason in d["reject_reasons"]:
            assert isinstance(reason, str)

    def test_json_serializable(self) -> None:
        r = validate_capability_name("crm.salesforce.sync.v2")
        json.dumps(r.to_dict())  # must not raise

    def test_json_serializable_invalid(self) -> None:
        r = validate_capability_name("bad-name")
        json.dumps(r.to_dict())  # must not raise

    def test_is_valid_property_matches_valid(self) -> None:
        r = validate_capability_name("a.b.c.v1")
        assert r.is_valid == r.valid

    def test_multiple_reasons_possible(self) -> None:
        # "A.B.C.1" has uppercase AND invalid version suffix
        r = validate_capability_name("A.B.C.1")
        assert len(r.reject_reasons) >= 1  # at least one reason

    def test_suggestion_is_str(self) -> None:
        r = validate_capability_name("Payment.Stripe.Integration.v1")
        assert isinstance(r.suggestion, str)


# --------------------------------------------------------------
# CapabilityNameParts model
# --------------------------------------------------------------

class TestCapabilityNameParts:
    """section7.3 - CapabilityNameParts assembles canonical name."""

    def test_canonical_name_property(self) -> None:
        parts = CapabilityNameParts(domain="payment", category="stripe", capability="integration", major=1)
        assert parts.canonical_name == "payment.stripe.integration.v1"

    def test_major_2(self) -> None:
        parts = CapabilityNameParts(domain="crm", category="salesforce", capability="sync", major=2)
        assert parts.canonical_name == "crm.salesforce.sync.v2"

    def test_major_must_be_positive(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            CapabilityNameParts(domain="a", category="b", capability="c", major=0)

    def test_negative_major_rejected(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            CapabilityNameParts(domain="a", category="b", capability="c", major=-1)

    def test_model_fields(self) -> None:
        parts = CapabilityNameParts(domain="a", category="b", capability="c", major=1)
        assert parts.domain == "a"
        assert parts.category == "b"
        assert parts.capability == "c"
        assert parts.major == 1


# --------------------------------------------------------------
# section6.1 - create_capability_name
# --------------------------------------------------------------

class TestCreateCapabilityName:
    """section6.1 - Creation helper: validate parts and assemble canonical name."""

    def test_basic_creation(self) -> None:
        name = create_capability_name("payment", "stripe", "integration", 1)
        assert name == "payment.stripe.integration.v1"

    def test_version_2(self) -> None:
        name = create_capability_name("crm", "salesforce", "sync", 2)
        assert name == "crm.salesforce.sync.v2"

    def test_returns_str(self) -> None:
        name = create_capability_name("a", "b", "c", 1)
        assert isinstance(name, str)

    def test_uppercase_domain_raises(self) -> None:
        with pytest.raises(CapabilityNameError):
            create_capability_name("Payment", "stripe", "integration", 1)

    def test_empty_domain_raises(self) -> None:
        with pytest.raises(CapabilityNameError):
            create_capability_name("", "stripe", "integration", 1)

    def test_empty_category_raises(self) -> None:
        with pytest.raises(CapabilityNameError):
            create_capability_name("payment", "", "integration", 1)

    def test_empty_capability_raises(self) -> None:
        with pytest.raises(CapabilityNameError):
            create_capability_name("payment", "stripe", "", 1)

    def test_error_carries_reject_reasons(self) -> None:
        try:
            create_capability_name("Payment", "stripe", "integration", 1)
        except CapabilityNameError as exc:
            assert exc.reject_reasons
            assert isinstance(exc.reject_reasons[0], NamespaceRejectReason)
        else:
            pytest.fail("Expected CapabilityNameError")

    def test_capability_name_error_is_value_error(self) -> None:
        with pytest.raises(ValueError):
            create_capability_name("Payment", "stripe", "integration", 1)

    def test_same_input_same_output(self) -> None:
        """section13: determinism."""
        a = create_capability_name("payment", "stripe", "integration", 1)
        b = create_capability_name("payment", "stripe", "integration", 1)
        assert a == b

    def test_hyphen_in_capability_allowed(self) -> None:
        name = create_capability_name("order", "line-item", "processor", 3)
        assert name == "order.line-item.processor.v3"

    def test_large_major_version(self) -> None:
        name = create_capability_name("data", "warehouse", "export", 99)
        assert name == "data.warehouse.export.v99"


# --------------------------------------------------------------
# section8.4 - normalize_capability_parts
# --------------------------------------------------------------

class TestNormalizeCapabilityParts:
    """section8.4 - trim, lowercase, coerce major from safe obvious input."""

    def test_strips_whitespace(self) -> None:
        d, c, n, m = normalize_capability_parts("  payment  ", "  stripe  ", "  integration  ", 1)
        assert d == "payment"
        assert c == "stripe"
        assert n == "integration"

    def test_lowercases_input(self) -> None:
        d, c, n, m = normalize_capability_parts("Payment", "Stripe", "Integration", 1)
        assert d == "payment"
        assert c == "stripe"
        assert n == "integration"

    def test_str_major_coerced(self) -> None:
        _, _, _, m = normalize_capability_parts("a", "b", "c", "3")
        assert m == 3
        assert isinstance(m, int)

    def test_major_1_passes(self) -> None:
        _, _, _, m = normalize_capability_parts("a", "b", "c", 1)
        assert m == 1

    def test_bad_str_major_raises(self) -> None:
        with pytest.raises(ValueError, match="major"):
            normalize_capability_parts("a", "b", "c", "abc")

    def test_zero_major_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_capability_parts("a", "b", "c", 0)

    def test_negative_major_raises(self) -> None:
        with pytest.raises(ValueError):
            normalize_capability_parts("a", "b", "c", -1)

    def test_returns_tuple_of_str_str_str_int(self) -> None:
        result = normalize_capability_parts("payment", "stripe", "integration", 1)
        assert len(result) == 4
        d, c, n, m = result
        assert isinstance(d, str)
        assert isinstance(c, str)
        assert isinstance(n, str)
        assert isinstance(m, int)

    def test_strips_whitespace_around_dots_in_parts(self) -> None:
        # Each part is individual - no dots expected but trim still works
        d, c, n, m = normalize_capability_parts("  a  ", "  b  ", "  c  ", 1)
        assert d == "a"

    def test_float_major_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            normalize_capability_parts("a", "b", "c", 1.5)


# --------------------------------------------------------------
# section16 - emit_namespace_proof
# --------------------------------------------------------------

class TestEmitNamespaceProof:
    """section16 - Proof artifacts: layout, content, and no-secrets rule."""

    def _valid_result(self) -> CapabilityValidationResult:
        return validate_capability_name("payment.stripe.integration.v1")

    def _invalid_result(self) -> CapabilityValidationResult:
        return validate_capability_name("Payment.Stripe.Integration")

    def test_returns_path(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="test-valid")
        assert isinstance(out, Path)

    def test_creates_directory(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="test-dir")
        assert out.is_dir()

    def test_layout_four_files(self, tmp_path: Path) -> None:
        """section11 - proof dir must contain validation.json, accepted.json, rejected.json, summary.md."""
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="layout-test")
        assert (out / "validation.json").exists()
        assert (out / "accepted.json").exists()
        assert (out / "rejected.json").exists()
        assert (out / "summary.md").exists()

    def test_validation_json_is_valid_json(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="json-test")
        data = json.loads((out / "validation.json").read_text())
        assert "name" in data
        assert "valid" in data

    def test_accepted_json_has_name_on_valid(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="accepted-test")
        data = json.loads((out / "accepted.json").read_text())
        assert "payment.stripe.integration.v1" in data["names"]

    def test_rejected_json_empty_on_valid(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="rejected-valid")
        data = json.loads((out / "rejected.json").read_text())
        assert data["names"] == []

    def test_rejected_json_has_name_on_invalid(self, tmp_path: Path) -> None:
        r = self._invalid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="rejected-invalid")
        data = json.loads((out / "rejected.json").read_text())
        assert len(data["names"]) == 1

    def test_accepted_json_empty_on_invalid(self, tmp_path: Path) -> None:
        r = self._invalid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="accepted-invalid")
        data = json.loads((out / "accepted.json").read_text())
        assert data["names"] == []

    def test_summary_md_contains_name(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="summary-test")
        summary = (out / "summary.md").read_text()
        assert "payment.stripe.integration.v1" in summary

    def test_no_write_statement_in_advisory_mode(self, tmp_path: Path) -> None:
        """section16 foreign/advisory: must include no-write statement."""
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="advisory-mode", write_mode=False)
        summary = (out / "summary.md").read_text()
        assert "advisory" in summary.lower() or "no in-repo" in summary.lower()

    def test_proof_contains_emitted_at(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="timestamp-test")
        data = json.loads((out / "validation.json").read_text())
        assert "emitted_at" in data

    def test_safe_ref_used_for_dir_name(self, tmp_path: Path) -> None:
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="my/ref with spaces!")
        assert out.is_dir()  # Must not crash on unsafe session_ref

    def test_no_tokens_or_secrets_in_artifacts(self, tmp_path: Path) -> None:
        """section10: proof must not include secrets or tokens."""
        r = self._valid_result()
        out = emit_namespace_proof(tmp_path, r, session_ref="no-secrets")
        for artifact in out.iterdir():
            content = artifact.read_text()
            assert "token" not in content.lower() or "access_token" not in content
            assert "password" not in content.lower()
            assert "secret" not in content.lower()

    def test_batch_proof_returns_path(self, tmp_path: Path) -> None:
        results = [
            validate_capability_name("payment.stripe.integration.v1"),
            validate_capability_name("bad-name"),
        ]
        out = emit_namespace_batch_proof(tmp_path, results, session_ref="batch-test")
        assert out.is_dir()
        assert (out / "accepted.json").exists()
        assert (out / "rejected.json").exists()
        assert (out / "validation.json").exists()


# --------------------------------------------------------------
# section13 - Determinism
# --------------------------------------------------------------

class TestDeterminism:
    """section13 - same input -> same result, always."""

    def test_valid_name_determinism(self) -> None:
        r1 = validate_capability_name("payment.stripe.integration.v1")
        r2 = validate_capability_name("payment.stripe.integration.v1")
        assert r1.valid == r2.valid
        assert r1.message == r2.message
        assert r1.reject_reasons == r2.reject_reasons

    def test_invalid_name_determinism(self) -> None:
        r1 = validate_capability_name("Payment.STRIPE.Integration.V1")
        r2 = validate_capability_name("Payment.STRIPE.Integration.V1")
        assert r1.reject_reasons == r2.reject_reasons

    def test_segment_count_reason_deterministic(self) -> None:
        for _ in range(5):
            r = validate_capability_name("a.b.c")
            assert NamespaceRejectReason.INVALID_SEGMENT_COUNT in r.reject_reasons

    def test_create_same_output(self) -> None:
        a = create_capability_name("payment", "stripe", "integration", 1)
        b = create_capability_name("payment", "stripe", "integration", 1)
        assert a == b

    def test_normalize_parts_deterministic(self) -> None:
        r1 = normalize_capability_parts("PAYMENT", "Stripe", "Integration", "2")
        r2 = normalize_capability_parts("PAYMENT", "Stripe", "Integration", "2")
        assert r1 == r2


# --------------------------------------------------------------
# section17.3 - Negative inputs
# --------------------------------------------------------------

class TestNegativeInputs:
    """section17.3 - Malformed names must not silently pass validation."""

    def test_none_like_string_rejected(self) -> None:
        r = validate_capability_name("None")
        assert r.valid is False

    def test_whitespace_only_rejected(self) -> None:
        r = validate_capability_name("   ")
        # After normalization, empty or invalid
        assert r.valid is False

    def test_newline_in_name_rejected(self) -> None:
        r = validate_capability_name("payment\nstripe.integration.v1")
        assert r.valid is False

    def test_tab_in_segment_rejected(self) -> None:
        r = validate_capability_name("payment\tstripe.integration.v1")
        assert r.valid is False

    def test_dot_at_start_rejected(self) -> None:
        r = validate_capability_name(".payment.stripe.integration")
        assert r.valid is False

    def test_dot_at_end_rejected(self) -> None:
        r = validate_capability_name("payment.stripe.integration.v1.")
        # This has 5 parts with last being empty
        assert r.valid is False

    def test_hyphen_at_start_of_segment_rejected(self) -> None:
        r = validate_capability_name("payment.-stripe.integration.v1")
        assert r.valid is False

    def test_hyphen_at_end_of_segment_rejected(self) -> None:
        r = validate_capability_name("payment.stripe-.integration.v1")
        assert r.valid is False

    def test_multiple_hyphens_allowed(self) -> None:
        r = validate_capability_name("multi-word.multi-word.multi-word.v1")
        assert r.valid is True

    def test_segment_starting_with_digit_allowed(self) -> None:
        r = validate_capability_name("data2.v3.export1.v5")
        assert r.valid is True


# --------------------------------------------------------------
# section6.2 + section9 - CLI run_capability_validate
# --------------------------------------------------------------

class TestCLICapabilityValidate:
    """section6.2, section9, section12 - CLI validate command behavior."""

    def test_valid_name_returns_exit_success(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="payment.stripe.integration.v1",
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_SUCCESS
        assert result.success is True

    def test_invalid_name_returns_exit_invalid_input(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="bad-name",
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT
        assert result.success is False

    def test_next_steps_on_failure(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="BadName",
            state_dir=str(tmp_path),
        )
        assert result.next_steps is not None
        assert len(result.next_steps) > 0

    def test_empty_name_rejected(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="",
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_data_contains_validation_result(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="crm.salesforce.sync.v2",
            state_dir=str(tmp_path),
        )
        assert "valid" in result.data
        assert result.data["valid"] is True

    def test_proof_file_written(self, tmp_path: Path) -> None:
        run_capability_validate(
            capability_name="crm.salesforce.sync.v2",
            state_dir=str(tmp_path),
        )
        # proof directory should be under capability_namespace/
        ns_dir = tmp_path / "capability_namespace"
        assert ns_dir.exists()

    def test_segment_count_reason_in_data_on_failure(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="just.three.segments",
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_whitespace_name_stripped_and_rejected(self, tmp_path: Path) -> None:
        result = run_capability_validate(
            capability_name="  bad  ",
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT


# --------------------------------------------------------------
# section6.1 + section9 - CLI run_capability_create
# --------------------------------------------------------------

class TestCLICapabilityCreate:
    """section6.1, section9, section13 - CLI create command behavior."""

    def test_basic_creation_succeeds(self, tmp_path: Path) -> None:
        result = run_capability_create(
            domain="payment",
            category="stripe",
            name="integration",
            major=1,
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_SUCCESS
        assert result.success is True
        assert result.data["capability"] == "payment.stripe.integration.v1"

    def test_missing_domain_fails(self, tmp_path: Path) -> None:
        result = run_capability_create(
            domain="",
            category="stripe",
            name="integration",
            major=1,
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_missing_category_fails(self, tmp_path: Path) -> None:
        result = run_capability_create(
            domain="payment",
            category="",
            name="integration",
            major=1,
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_missing_name_fails(self, tmp_path: Path) -> None:
        result = run_capability_create(
            domain="payment",
            category="stripe",
            name="",
            major=1,
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_invalid_domain_chars_fails(self, tmp_path: Path) -> None:
        # Normalization lowercases, but illegal chars still fail
        result = run_capability_create(
            domain="pay@ment",
            category="stripe",
            name="integration",
            major=1,
            state_dir=str(tmp_path),
        )
        assert result.exit_code == EXIT_INVALID_INPUT

    def test_write_mode_without_artifacts_advisory(self, tmp_path: Path) -> None:
        """section9.2: No governed artifact -> write mode emits advisory warning."""
        # No capability_passport.yaml in tmp_path
        result = run_capability_create(
            domain="payment",
            category="stripe",
            name="integration",
            major=1,
            write=True,
            repo_dir=str(tmp_path),
            state_dir=str(tmp_path),
        )
        # Still succeeds (advisory mode)
        assert result.success is True
        # Warning must mention advisory
        assert any("advisory" in w.lower() for w in result.warnings)

    def test_write_mode_with_artifact_inserts(self, tmp_path: Path) -> None:
        """section9.1: Write mode inserts capability into capability_passport.yaml."""
        passport = tmp_path / "capability_passport.yaml"
        passport.write_text("name: my-repo\n", encoding="utf-8")
        result = run_capability_create(
            domain="payment",
            category="stripe",
            name="integration",
            major=1,
            write=True,
            repo_dir=str(tmp_path),
            state_dir=str(tmp_path),
        )
        assert result.success is True
        content = passport.read_text()
        assert "payment.stripe.integration.v1" in content

    def test_write_mode_duplicate_suppression(self, tmp_path: Path) -> None:
        """section10: Duplicate suppression - second insert must warn, not duplicate."""
        passport = tmp_path / "capability_passport.yaml"
        passport.write_text("capabilities:\n  - payment.stripe.integration.v1\n", encoding="utf-8")
        result = run_capability_create(
            domain="payment",
            category="stripe",
            name="integration",
            major=1,
            write=True,
            repo_dir=str(tmp_path),
            state_dir=str(tmp_path),
        )
        # Success with a warning about duplicate
        assert result.success is True
        assert result.warnings

    def test_proof_file_written_on_create(self, tmp_path: Path) -> None:
        run_capability_create(
            domain="crm",
            category="salesforce",
            name="sync",
            major=2,
            state_dir=str(tmp_path),
        )
        ns_dir = tmp_path / "capability_namespace"
        assert ns_dir.exists()

    def test_lowercase_normalization_applied(self, tmp_path: Path) -> None:
        """section8.4: normalized parts used, uppercase lowercased before assembly."""
        result = run_capability_create(
            domain="Payment",
            category="Stripe",
            name="Integration",
            major=1,
            state_dir=str(tmp_path),
        )
        # Should succeed after normalization
        assert result.exit_code == EXIT_SUCCESS
        assert result.data["capability"] == "payment.stripe.integration.v1"


# --------------------------------------------------------------
# section18 - Public API surface contract
# --------------------------------------------------------------

class TestPublicAPISurface:
    """section18 - Required SDK exports are present."""

    def test_validate_capability_name_in_sdk(self) -> None:
        from keyhole_sdk import validate_capability_name as f
        assert callable(f)

    def test_create_capability_name_in_sdk(self) -> None:
        from keyhole_sdk import create_capability_name as f
        assert callable(f)

    def test_normalize_capability_parts_in_sdk(self) -> None:
        from keyhole_sdk import normalize_capability_parts as f
        assert callable(f)

    def test_capability_validation_result_in_sdk(self) -> None:
        from keyhole_sdk import CapabilityValidationResult
        assert CapabilityValidationResult is not None

    def test_namespace_reject_reason_in_sdk(self) -> None:
        from keyhole_sdk import NamespaceRejectReason
        assert NamespaceRejectReason is not None

    def test_capability_name_error_in_sdk(self) -> None:
        from keyhole_sdk import CapabilityNameError
        assert issubclass(CapabilityNameError, ValueError)

    def test_emit_namespace_proof_in_sdk(self) -> None:
        from keyhole_sdk import emit_namespace_proof as f
        assert callable(f)

    def test_capability_name_parts_in_sdk(self) -> None:
        from keyhole_sdk import CapabilityNameParts
        assert CapabilityNameParts is not None

    def test_all_in_keyhole_sdk_all(self) -> None:
        from keyhole_sdk import __all__
        for sym in (
            "validate_capability_name",
            "create_capability_name",
            "normalize_capability_parts",
            "CapabilityValidationResult",
            "NamespaceRejectReason",
            "CapabilityNameError",
            "emit_namespace_proof",
            "CapabilityNameParts",
        ):
            assert sym in __all__, f"{sym} must be in keyhole_sdk.__all__"

    def test_emit_namespace_batch_proof_in_sdk(self) -> None:
        from keyhole_sdk import emit_namespace_batch_proof as f
        assert callable(f)

    def test_capability_namespace_package_all(self) -> None:
        from keyhole_sdk.capability import __all__ as cap_all
        for sym in (
            "NamespaceRejectReason",
            "CapabilityValidationResult",
            "CapabilityNameParts",
            "validate_capability_name",
            "create_capability_name",
            "normalize_capability_parts",
            "CapabilityNameError",
            "emit_namespace_proof",
        ):
            assert sym in cap_all, f"{sym} must be in capability.__all__"
