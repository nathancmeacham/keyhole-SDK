"""SDK-CLIENT-23 - Host Identity Attestation & Local Identity Coherence Guard.

Tests covering:
  AC1 - SDK schema exists and validates
  AC2 - VS Code-first attestation uses real host proof
  AC3 - Doctor surfaces host and CLI identities separately
  AC4 - Fresh confirmed conflict blocks CLI bind by default
  AC5 - Match proceeds cleanly
  AC6 - Stale or unknown host identity does not hard-block
  AC7 - Explicit split override is possible and durable
  AC8 - No IDE mutation occurs (structural assertion)
  AC9 - Coherence engine behavior tests
  AC10 - Host-agnostic design is extensible
"""
from __future__ import annotations

import json
import os
import sys
import stat
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from keyhole_sdk.doctor.models import (
    ATTESTATION_TTL_SECONDS,
    AttestationConfidence,
    CoherenceVerdict,
    HostIdentityAttestation,
    IdentityPolicyOverride,
)
from keyhole_sdk.host.attestation_store import (
    write_attestation,
    load_attestations,
    load_identity_policy,
    save_identity_policy,
    clear_identity_policy,
    save_principal_hint,
)
from keyhole_sdk.host.coherence_engine import (
    CoherenceResult,
    classify_coherence,
)


# -- Helpers ----------------------------------------------


def _fresh_attestation(
    *,
    principal: str = "nathan@keyholesolution.com",
    subject: str = "aa07e5b5-7d28-4354-ae5c-6c1c452bb929",
    host_kind: str = "vscode",
    confidence: AttestationConfidence = AttestationConfidence.CONFIRMED,
    server_url: str = "https://mcp.keyholesolution.com",
    realm: str = "kh-prod",
    ttl_seconds: int = ATTESTATION_TTL_SECONDS,
) -> HostIdentityAttestation:
    """Build a fresh attestation for testing."""
    now = datetime.now(timezone.utc)
    return HostIdentityAttestation(
        schema_version="1",
        host_kind=host_kind,
        host_display_name="VS Code" if host_kind == "vscode" else host_kind,
        integration_name="keyhole",
        server_url=server_url,
        realm=realm,
        effective_principal=principal,
        effective_subject=subject,
        proof_method="live_whoami",
        confidence=confidence,
        observed_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=ttl_seconds)).isoformat(),
        machine_scope="abc123",
        correlation_id="test-corr-001",
        notes="test attestation",
        tool_version="test/0.1.0",
    )


def _stale_attestation(
    *,
    principal: str = "nathan@keyholesolution.com",
    host_kind: str = "vscode",
) -> HostIdentityAttestation:
    """Build a stale (expired) attestation for testing."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    return HostIdentityAttestation(
        schema_version="1",
        host_kind=host_kind,
        host_display_name="VS Code",
        integration_name="keyhole",
        server_url="https://mcp.keyholesolution.com",
        realm="kh-prod",
        effective_principal=principal,
        effective_subject="stale-sub",
        proof_method="live_whoami",
        confidence=AttestationConfidence.CONFIRMED,
        observed_at=(past - timedelta(minutes=10)).isoformat(),
        expires_at=past.isoformat(),
        machine_scope="abc123",
    )


def _override(
    *,
    target: str = "paul@keyholesolution.com",
    conflicting: str = "nathan@keyholesolution.com",
    host_kind: str = "vscode",
    expired: bool = False,
) -> IdentityPolicyOverride:
    """Build a split-identity override for testing."""
    now = datetime.now(timezone.utc)
    expiry = None
    if expired:
        expiry = (now - timedelta(hours=1)).isoformat()
    return IdentityPolicyOverride(
        override_type="allow_split_identity",
        created_at=now.isoformat(),
        target_principal=target,
        conflicting_host_principal=conflicting,
        host_kind=host_kind,
        reason="test override",
        expiry=expiry,
    )


# ----------------------------------------------------------
# AC1 - SDK schema exists and validates
# ----------------------------------------------------------


class TestAC1_AttestationSchema:
    """AC1: Schema validation for HostIdentityAttestation."""

    def test_required_fields_construct(self):
        att = _fresh_attestation()
        assert att.schema_version == "1"
        assert att.host_kind == "vscode"
        assert att.effective_principal == "nathan@keyholesolution.com"

    def test_confidence_enum_validates(self):
        for c in ["confirmed", "probable", "unknown"]:
            att = _fresh_attestation(confidence=AttestationConfidence(c))
            assert att.confidence.value == c

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValueError):
            AttestationConfidence("bogus")

    def test_coherence_verdict_enum(self):
        expected = {
            "ACCEPT_MATCH",
            "WARNING_NO_HOST_ATTESTATION",
            "WARNING_STALE_HOST_ATTESTATION",
            "WARNING_UNKNOWN_HOST_IDENTITY",
            "REJECT_HOST_CONFLICT",
            "ACCEPT_INTENTIONAL_SPLIT",
        }
        actual = {v.value for v in CoherenceVerdict}
        assert actual == expected

    def test_attestation_to_dict_roundtrip(self):
        att = _fresh_attestation()
        d = att.to_dict()
        assert d["schema_version"] == "1"
        assert d["host_kind"] == "vscode"
        assert d["effective_principal"] == "nathan@keyholesolution.com"
        assert d["confidence"] == "confirmed"
        # Can reconstruct from dict
        att2 = HostIdentityAttestation(**d)
        assert att2.effective_principal == att.effective_principal

    def test_freshness_check_fresh(self):
        att = _fresh_attestation()
        assert att.is_fresh() is True
        assert att.is_confirmed() is True

    def test_freshness_check_stale(self):
        att = _stale_attestation()
        assert att.is_fresh() is False

    def test_ttl_constant(self):
        assert ATTESTATION_TTL_SECONDS == 600

    def test_identity_policy_override_to_dict(self):
        ov = _override()
        d = ov.to_dict()
        assert d["override_type"] == "allow_split_identity"
        assert d["target_principal"] == "paul@keyholesolution.com"
        assert d["conflicting_host_principal"] == "nathan@keyholesolution.com"

    def test_identity_policy_override_expiry(self):
        ov = _override(expired=False)
        assert ov.is_expired() is False

        ov_exp = _override(expired=True)
        assert ov_exp.is_expired() is True


# ----------------------------------------------------------
# AC2 - Attestation storage I/O
# ----------------------------------------------------------


class TestAC2_AttestationStorage:
    """AC2: Read/write attestation files using secure local storage."""

    def test_write_and_load_attestation(self, tmp_path):
        att = _fresh_attestation()
        path = write_attestation(att, keyhole_home=tmp_path)
        assert path.exists()
        assert "vscode__keyhole__abc123.json" == path.name

        loaded = load_attestations(keyhole_home=tmp_path)
        assert len(loaded) == 1
        assert loaded[0].effective_principal == "nathan@keyholesolution.com"
        assert loaded[0].host_kind == "vscode"

    def test_write_attestation_file_permissions(self, tmp_path):
        att = _fresh_attestation()
        path = write_attestation(att, keyhole_home=tmp_path)
        mode = os.stat(path).st_mode
        if sys.platform == "win32":
            assert path.is_file()
        else:
            assert mode & stat.S_IRWXO == 0  # no other permissions
            assert mode & stat.S_IRWXG == 0  # no group permissions

    def test_multiple_attestations(self, tmp_path):
        att1 = _fresh_attestation(host_kind="vscode")
        att2 = _fresh_attestation(host_kind="jetbrains")
        write_attestation(att1, keyhole_home=tmp_path)
        write_attestation(att2, keyhole_home=tmp_path)

        loaded = load_attestations(keyhole_home=tmp_path)
        assert len(loaded) == 2
        kinds = {a.host_kind for a in loaded}
        assert kinds == {"vscode", "jetbrains"}

    def test_overwrite_attestation(self, tmp_path):
        att1 = _fresh_attestation(principal="alice@example.com")
        write_attestation(att1, keyhole_home=tmp_path)

        att2 = _fresh_attestation(principal="bob@example.com")
        write_attestation(att2, keyhole_home=tmp_path)

        loaded = load_attestations(keyhole_home=tmp_path)
        assert len(loaded) == 1
        assert loaded[0].effective_principal == "bob@example.com"

    def test_load_empty_dir(self, tmp_path):
        loaded = load_attestations(keyhole_home=tmp_path)
        assert loaded == []

    def test_load_skips_malformed(self, tmp_path):
        att_dir = tmp_path / "host_attestations"
        att_dir.mkdir()
        bad = att_dir / "bad__keyhole__xxx.json"
        bad.write_text("{not valid json")
        good_att = _fresh_attestation()
        write_attestation(good_att, keyhole_home=tmp_path)

        loaded = load_attestations(keyhole_home=tmp_path)
        assert len(loaded) == 1

    def test_identity_policy_round_trip(self, tmp_path):
        ov = _override()
        path = save_identity_policy(ov, keyhole_home=tmp_path)
        assert path.exists()

        loaded = load_identity_policy(keyhole_home=tmp_path)
        assert loaded is not None
        assert loaded.target_principal == "paul@keyholesolution.com"

    def test_identity_policy_not_found(self, tmp_path):
        assert load_identity_policy(keyhole_home=tmp_path) is None

    def test_clear_identity_policy(self, tmp_path):
        ov = _override()
        save_identity_policy(ov, keyhole_home=tmp_path)
        assert load_identity_policy(keyhole_home=tmp_path) is not None

        result = clear_identity_policy(keyhole_home=tmp_path)
        assert result is True
        assert load_identity_policy(keyhole_home=tmp_path) is None

    def test_clear_nonexistent_policy(self, tmp_path):
        result = clear_identity_policy(keyhole_home=tmp_path)
        assert result is False


# ----------------------------------------------------------
# AC4 - Fresh confirmed conflict blocks CLI bind
# ----------------------------------------------------------


class TestAC4_FreshConflictBlocks:
    """AC4: Fresh confirmed host conflict triggers REJECT_HOST_CONFLICT."""

    def test_fresh_confirmed_conflict_rejects(self):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.REJECT_HOST_CONFLICT
        assert len(result.conflicting_attestations) == 1
        assert result.fix_steps  # must include remediation

    def test_conflict_includes_description(self):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert "nathan" in result.description.lower()
        assert "paul" in result.description.lower()

    def test_conflict_fix_steps_actionable(self):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        # Must include specific recovery advice
        steps_text = " ".join(result.fix_steps).lower()
        assert "vs code" in steps_text or "vscode" in steps_text
        assert "keyhole doctor" in steps_text or "keyhole login" in steps_text


# ----------------------------------------------------------
# AC5 - Match proceeds cleanly
# ----------------------------------------------------------


class TestAC5_MatchProceeds:
    """AC5: Matching identities yield ACCEPT_MATCH."""

    def test_exact_match(self):
        att = _fresh_attestation(principal="paul@keyholesolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_MATCH
        assert len(result.matching_attestations) == 1

    def test_case_insensitive_match(self):
        att = _fresh_attestation(principal="Paul@KeyholeSolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_MATCH

    def test_match_description(self):
        att = _fresh_attestation(principal="paul@keyholesolution.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert "match" in result.description.lower()


# ----------------------------------------------------------
# AC6 - Stale or unknown does not hard-block
# ----------------------------------------------------------


class TestAC6_StaleDoesNotBlock:
    """AC6: Stale, probable, or unknown attestations warn but don't block."""

    def test_stale_attestation_warns(self):
        att = _stale_attestation(principal="different@example.com")
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.WARNING_STALE_HOST_ATTESTATION
        assert result.verdict != CoherenceVerdict.REJECT_HOST_CONFLICT

    def test_probable_confidence_warns(self):
        att = _fresh_attestation(
            principal="different@example.com",
            confidence=AttestationConfidence.PROBABLE,
        )
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.WARNING_UNKNOWN_HOST_IDENTITY

    def test_unknown_confidence_warns(self):
        att = _fresh_attestation(
            principal="different@example.com",
            confidence=AttestationConfidence.UNKNOWN,
        )
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.WARNING_UNKNOWN_HOST_IDENTITY

    def test_no_attestations_warns(self):
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[],
        )
        assert result.verdict == CoherenceVerdict.WARNING_NO_HOST_ATTESTATION

    def test_no_cli_principal_warns(self):
        result = classify_coherence(
            cli_principal="",
            attestations=[],
        )
        assert result.verdict == CoherenceVerdict.WARNING_NO_HOST_ATTESTATION


# ----------------------------------------------------------
# AC7 - Explicit split override is possible and durable
# ----------------------------------------------------------


class TestAC7_SplitOverride:
    """AC7: --allow-split-identity records override; doctor shows ACCEPT_INTENTIONAL_SPLIT."""

    def test_override_permits_conflicting_bind(self):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        ov = _override(
            target="paul@keyholesolution.com",
            conflicting="nathan@keyholesolution.com",
        )
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
            override=ov,
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_INTENTIONAL_SPLIT

    def test_expired_override_does_not_permit(self):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        ov = _override(expired=True)
        result = classify_coherence(
            cli_principal="paul@keyholesolution.com",
            attestations=[att],
            override=ov,
        )
        assert result.verdict == CoherenceVerdict.REJECT_HOST_CONFLICT

    def test_override_stored_to_disk(self, tmp_path):
        ov = _override()
        save_identity_policy(ov, keyhole_home=tmp_path)
        loaded = load_identity_policy(keyhole_home=tmp_path)
        assert loaded is not None
        assert loaded.override_type == "allow_split_identity"

    def test_override_cleared(self, tmp_path):
        ov = _override()
        save_identity_policy(ov, keyhole_home=tmp_path)
        clear_identity_policy(keyhole_home=tmp_path)
        assert load_identity_policy(keyhole_home=tmp_path) is None


# ----------------------------------------------------------
# AC8 - No IDE mutation occurs
# ----------------------------------------------------------


class TestAC8_NoIDEMutation:
    """AC8: Implementation never touches gallery entries or scrapes secrets."""

    def test_attestation_store_writes_only_to_keyhole_home(self, tmp_path):
        """Attestation files land in ~/.keyhole/host_attestations/."""
        att = _fresh_attestation()
        path = write_attestation(att, keyhole_home=tmp_path)
        assert "host_attestations" in str(path)
        assert str(tmp_path) in str(path)

    def test_no_vscode_settings_mutation(self, tmp_path):
        """Write attestation does not create/modify any VS Code config files."""
        att = _fresh_attestation()
        write_attestation(att, keyhole_home=tmp_path)
        # The only directory under tmp_path should be host_attestations
        children = list(tmp_path.iterdir())
        assert all(c.name == "host_attestations" for c in children)


# ----------------------------------------------------------
# AC9 - Coherence engine behavior (comprehensive matrix)
# ----------------------------------------------------------


class TestAC9_CoherenceEngineMatrix:
    """AC9: Full matrix of coherence engine verdicts."""

    def test_no_cli_no_attestations(self):
        r = classify_coherence(cli_principal="", attestations=[])
        assert r.verdict == CoherenceVerdict.WARNING_NO_HOST_ATTESTATION

    def test_cli_only_no_attestations(self):
        r = classify_coherence(cli_principal="paul@example.com", attestations=[])
        assert r.verdict == CoherenceVerdict.WARNING_NO_HOST_ATTESTATION

    def test_fresh_confirmed_match(self):
        att = _fresh_attestation(principal="paul@example.com")
        r = classify_coherence(cli_principal="paul@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.ACCEPT_MATCH

    def test_fresh_confirmed_conflict(self):
        att = _fresh_attestation(principal="alice@example.com")
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.REJECT_HOST_CONFLICT

    def test_fresh_confirmed_conflict_with_override(self):
        att = _fresh_attestation(principal="alice@example.com")
        ov = _override(target="bob@example.com", conflicting="alice@example.com")
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att], override=ov)
        assert r.verdict == CoherenceVerdict.ACCEPT_INTENTIONAL_SPLIT

    def test_stale_conflicting(self):
        att = _stale_attestation(principal="alice@example.com")
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.WARNING_STALE_HOST_ATTESTATION

    def test_stale_matching(self):
        att = _stale_attestation(principal="bob@example.com")
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.WARNING_STALE_HOST_ATTESTATION

    def test_probable_confidence(self):
        att = _fresh_attestation(
            principal="alice@example.com",
            confidence=AttestationConfidence.PROBABLE,
        )
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.WARNING_UNKNOWN_HOST_IDENTITY

    def test_unknown_confidence(self):
        att = _fresh_attestation(
            principal="alice@example.com",
            confidence=AttestationConfidence.UNKNOWN,
        )
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        assert r.verdict == CoherenceVerdict.WARNING_UNKNOWN_HOST_IDENTITY

    def test_mixed_match_and_stale(self):
        """Fresh match + stale = ACCEPT_MATCH (fresh wins)."""
        fresh = _fresh_attestation(principal="paul@example.com", host_kind="vscode")
        stale = _stale_attestation(principal="other@example.com", host_kind="jetbrains")
        r = classify_coherence(
            cli_principal="paul@example.com",
            attestations=[fresh, stale],
        )
        assert r.verdict == CoherenceVerdict.ACCEPT_MATCH
        assert len(r.stale_attestations) == 1

    def test_mixed_conflict_and_match(self):
        """Fresh conflict + fresh match = REJECT (conflict wins)."""
        conflict = _fresh_attestation(principal="alice@example.com", host_kind="vscode")
        match = _fresh_attestation(principal="bob@example.com", host_kind="jetbrains")
        r = classify_coherence(
            cli_principal="bob@example.com",
            attestations=[conflict, match],
        )
        assert r.verdict == CoherenceVerdict.REJECT_HOST_CONFLICT

    def test_result_to_dict(self):
        att = _fresh_attestation(principal="alice@example.com")
        r = classify_coherence(cli_principal="bob@example.com", attestations=[att])
        d = r.to_dict()
        assert d["verdict"] == "REJECT_HOST_CONFLICT"
        assert d["cli_principal"] == "bob@example.com"
        assert "vscode" in d["conflicting_hosts"]


# ----------------------------------------------------------
# AC10 - Host-agnostic extensibility
# ----------------------------------------------------------


class TestAC10_Extensibility:
    """AC10: Attestation and coherence work with any host kind."""

    def test_jetbrains_attestation(self):
        att = _fresh_attestation(
            principal="dev@example.com",
            host_kind="jetbrains",
        )
        result = classify_coherence(
            cli_principal="dev@example.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_MATCH

    def test_cursor_attestation(self):
        att = _fresh_attestation(
            principal="dev@example.com",
            host_kind="cursor",
        )
        result = classify_coherence(
            cli_principal="dev@example.com",
            attestations=[att],
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_MATCH

    def test_multi_host_coherence(self):
        """Multiple hosts with same principal = ACCEPT_MATCH."""
        att_vs = _fresh_attestation(principal="dev@example.com", host_kind="vscode")
        att_jb = _fresh_attestation(principal="dev@example.com", host_kind="jetbrains")
        result = classify_coherence(
            cli_principal="dev@example.com",
            attestations=[att_vs, att_jb],
        )
        assert result.verdict == CoherenceVerdict.ACCEPT_MATCH
        assert len(result.matching_attestations) == 2


# ----------------------------------------------------------
# Login Preflight Guard Tests
# ----------------------------------------------------------


class TestLoginPreflightGuard:
    """Login preflight guard behavior (SDK-CLIENT-23 sectionF)."""

    def test_login_blocked_on_conflict(self, tmp_path):
        """run_login returns failure when fresh confirmed conflict exists."""
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        write_attestation(att, keyhole_home=tmp_path)

        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.login import _check_host_coherence
            from keyhole_sdk.auth_bootstrap.models import LoginResult, AuthFlowType, AuthMode
            from keyhole_sdk.auth_bootstrap.models import WhoamiResponse

            whoami = WhoamiResponse(
                user_id="test-user",
                display_name="paul@keyholesolution.com",
                mode=AuthMode.REAL,
            )
            lr = LoginResult(
                success=True,
                flow_type=AuthFlowType.PKCE,
                mode=AuthMode.REAL,
                whoami=whoami,
                credential_persisted=True,
                verification_passed=True,
            )
            result = _check_host_coherence(
                result=lr,
                allow_split_identity=False,
            )
            assert result is not None
            assert result.success is False
            assert result.data["verdict"] == "REJECT_HOST_CONFLICT"

    def test_login_proceeds_with_split_override(self, tmp_path):
        """run_login proceeds when --allow-split-identity is set."""
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        write_attestation(att, keyhole_home=tmp_path)

        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.login import _check_host_coherence
            from keyhole_sdk.auth_bootstrap.models import LoginResult, AuthFlowType, AuthMode
            from keyhole_sdk.auth_bootstrap.models import WhoamiResponse

            whoami = WhoamiResponse(
                user_id="test-user",
                display_name="paul@keyholesolution.com",
                mode=AuthMode.REAL,
            )
            lr = LoginResult(
                success=True,
                flow_type=AuthFlowType.PKCE,
                mode=AuthMode.REAL,
                whoami=whoami,
                credential_persisted=True,
                verification_passed=True,
            )
            result = _check_host_coherence(
                result=lr,
                allow_split_identity=True,
            )
            # Should return None (proceed with login)
            assert result is None

            # Override should have been saved
            policy = load_identity_policy(keyhole_home=tmp_path)
            assert policy is not None
            assert policy.override_type == "allow_split_identity"

    def test_login_proceeds_when_no_attestations(self, tmp_path):
        """No attestations = login proceeds (no block)."""
        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.login import _check_host_coherence
            from keyhole_sdk.auth_bootstrap.models import LoginResult, AuthFlowType, AuthMode
            from keyhole_sdk.auth_bootstrap.models import WhoamiResponse

            whoami = WhoamiResponse(
                user_id="test-user",
                display_name="paul@keyholesolution.com",
                mode=AuthMode.REAL,
            )
            lr = LoginResult(
                success=True,
                flow_type=AuthFlowType.PKCE,
                mode=AuthMode.REAL,
                whoami=whoami,
                credential_persisted=True,
                verification_passed=True,
            )
            result = _check_host_coherence(
                result=lr,
                allow_split_identity=False,
            )
            assert result is None

    def test_login_proceeds_on_match(self, tmp_path):
        """Matching attestation = login proceeds."""
        att = _fresh_attestation(principal="paul@keyholesolution.com")
        write_attestation(att, keyhole_home=tmp_path)

        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.login import _check_host_coherence
            from keyhole_sdk.auth_bootstrap.models import LoginResult, AuthFlowType, AuthMode
            from keyhole_sdk.auth_bootstrap.models import WhoamiResponse

            whoami = WhoamiResponse(
                user_id="test-user",
                display_name="paul@keyholesolution.com",
                mode=AuthMode.REAL,
            )
            lr = LoginResult(
                success=True,
                flow_type=AuthFlowType.PKCE,
                mode=AuthMode.REAL,
                whoami=whoami,
                credential_persisted=True,
                verification_passed=True,
            )
            result = _check_host_coherence(
                result=lr,
                allow_split_identity=False,
            )
            assert result is None


# ----------------------------------------------------------
# Doctor Coherence Integration Tests
# ----------------------------------------------------------


class TestDoctorCoherenceIntegration:
    """Doctor output includes host coherence section."""

    def test_doctor_builds_coherence_report(self, tmp_path):
        """Doctor result includes host_coherence when attestations exist."""
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        write_attestation(att, keyhole_home=tmp_path)
        save_principal_hint(
            principal="paul@keyholesolution.com",
            user_id="test-user-id",
            realm="kh-prod",
            keyhole_home=tmp_path,
        )

        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.doctor import _build_coherence_report
            # Mock credential store
            with patch(
                "keyhole_cli.commands.doctor.CredentialStore"
            ) as MockStore:
                mock_instance = MagicMock()
                mock_session = MagicMock()
                mock_instance.load.return_value = mock_session
                MockStore.return_value = mock_instance

                report = _build_coherence_report()

            assert report is not None
            assert report["verdict"] == "REJECT_HOST_CONFLICT"
            assert len(report["attestations"]) == 1
            assert report["attestations"][0]["effective_principal"] == "nathan@keyholesolution.com"

    def test_doctor_no_credentials_returns_none(self, tmp_path):
        """Doctor returns None coherence when no credentials stored."""
        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.doctor import _build_coherence_report

            with patch(
                "keyhole_cli.commands.doctor.CredentialStore"
            ) as MockStore:
                mock_instance = MagicMock()
                mock_instance.load.return_value = None
                MockStore.return_value = mock_instance

                report = _build_coherence_report()
            assert report is None

    def test_doctor_match_verdict(self, tmp_path):
        att = _fresh_attestation(principal="nathan@keyholesolution.com")
        write_attestation(att, keyhole_home=tmp_path)
        save_principal_hint(
            principal="nathan@keyholesolution.com",
            user_id="test-user-id",
            realm="kh-prod",
            keyhole_home=tmp_path,
        )

        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            from keyhole_cli.commands.doctor import _build_coherence_report

            with patch(
                "keyhole_cli.commands.doctor.CredentialStore"
            ) as MockStore:
                mock_instance = MagicMock()
                mock_session = MagicMock()
                mock_instance.load.return_value = mock_session
                MockStore.return_value = mock_instance

                report = _build_coherence_report()

            assert report is not None
            assert report["verdict"] == "ACCEPT_MATCH"


# ----------------------------------------------------------
# Host Attest Command Tests
# ----------------------------------------------------------


class TestHostAttestCommand:
    """Tests for the keyhole host attest command."""

    def test_attest_no_credentials(self):
        """Attest fails when no credentials stored."""
        with patch(
            "keyhole_cli.commands.host_attest.CredentialStore"
        ) as MockStore:
            mock_instance = MagicMock()
            mock_instance.load.return_value = None
            MockStore.return_value = mock_instance

            from keyhole_cli.commands.host_attest import run_host_attest
            result = run_host_attest()
            assert result.success is False
            assert "Not authenticated" in result.summary

    def test_attest_expired_credentials(self):
        """Attest fails when credentials are expired."""
        with patch(
            "keyhole_cli.commands.host_attest.CredentialStore"
        ) as MockStore:
            mock_instance = MagicMock()
            mock_session = MagicMock()
            mock_session.is_expired = True
            mock_instance.load.return_value = mock_session
            MockStore.return_value = mock_instance

            from keyhole_cli.commands.host_attest import run_host_attest
            result = run_host_attest()
            assert result.success is False
            assert "expired" in result.summary.lower()

    def test_attest_success(self, tmp_path):
        """Attest succeeds with valid credentials and whoami response."""
        with patch.dict(os.environ, {"KEYHOLE_HOME": str(tmp_path)}):
            with patch(
                "keyhole_cli.commands.host_attest.CredentialStore"
            ) as MockStore:
                mock_instance = MagicMock()
                mock_session = MagicMock()
                mock_session.is_expired = False
                mock_session.access_token = "test-token"
                mock_instance.load.return_value = mock_session
                MockStore.return_value = mock_instance

                with patch(
                    "keyhole_cli.commands.host_attest.WhoamiClient"
                ) as MockWhoami:
                    from keyhole_sdk.auth_bootstrap.models import (
                        WhoamiResponse,
                        AuthMode,
                    )

                    whoami = WhoamiResponse(
                        user_id="aa07e5b5",
                        display_name="nathan@keyholesolution.com",
                        mode=AuthMode.REAL,
                    )
                    mock_client = MagicMock()
                    mock_client.whoami.return_value = whoami
                    MockWhoami.return_value = mock_client

                    from keyhole_cli.commands.host_attest import run_host_attest
                    result = run_host_attest(server_url="https://mcp.keyholesolution.com")

            assert result.success is True
            assert "nathan@keyholesolution.com" in result.summary
            assert result.data["effective_principal"] == "nathan@keyholesolution.com"
            assert result.data["confidence"] == "confirmed"

            # Verify attestation was written
            loaded = load_attestations(keyhole_home=tmp_path)
            assert len(loaded) == 1
            assert loaded[0].effective_principal == "nathan@keyholesolution.com"
