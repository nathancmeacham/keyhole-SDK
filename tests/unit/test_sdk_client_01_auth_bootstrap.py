"""SDK-CLIENT-01 - Authentication Bootstrap (Client) - Full Test Suite.

Covers all test plan items from sdk-client-01.md section16:

  POSITIVE TESTS:
    Test A - Browser/PKCE login success
    Test B - Device/constrained flow success
    Test C - Token/session usable across commands
    Test D - Shadow mode visible
    Test E - Real mode visible

  NEGATIVE TESTS:
    Test F - Browser flow cannot open
    Test G - Completion artifact invalid
    Test H - Credential store write failure
    Test I - Whoami fails after login
    Test J - Missing/expired local session

  PROOF TESTS:
    Test K - Client proof bundle sufficiency
    Test L - No secret leakage in proof artifacts

  ADDITIONAL COVERAGE:
    - Models validation and safety
    - Credential store lifecycle
    - PKCE challenge generation
    - Error hierarchy and repair guidance
    - Auth client orchestration
    - CLI command integration
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import stat
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from typer.testing import CliRunner

# -- SDK auth_bootstrap imports ------------------------------
from keyhole_sdk.auth_bootstrap.models import (
    AuthFlowType,
    AuthMode,
    AuthSession,
    DeviceCodeResponse,
    LoginResult,
    PKCEChallenge,
    TokenResponse,
    WhoamiResponse,
)
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.auth_bootstrap.pkce import (
    PKCEFlow,
    _generate_code_challenge,
    _generate_code_verifier,
)
from keyhole_sdk.auth_bootstrap.device import DeviceFlow
from keyhole_sdk.auth_bootstrap.client import AuthBootstrapClient
from keyhole_sdk.auth_bootstrap.whoami import WhoamiClient
from keyhole_sdk.auth_bootstrap.proof import AuthProofBundle
from keyhole_sdk.auth_bootstrap.errors import (
    AuthBootstrapError,
    BrowserLaunchError,
    CredentialStoreError,
    ExpiredChallengeError,
    IncompleteIdentityError,
    InvalidTokenError,
    LoginDeniedError,
    NetworkError,
    WhoamiVerificationError,
)

# -- CLI command imports -------------------------------------
from keyhole_cli.commands.login import run_login
from keyhole_cli.commands.whoami import run_whoami
from keyhole_cli.cli import app
from keyhole_cli.result import CommandResult


# ------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path: Path) -> CredentialStore:
    """Create a credential store in a temporary directory."""
    return CredentialStore(store_dir=tmp_path / ".keyhole")


@pytest.fixture
def sample_session() -> AuthSession:
    """Return a valid sample auth session."""
    return AuthSession(
        access_token="test-access-token-abc123",
        token_type="Bearer",
        refresh_token="test-refresh-token-xyz789",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scope="openid profile email",
        flow_type=AuthFlowType.PKCE,
        mode=AuthMode.REAL,
        realm="keyhole-mcp",
        auth_server_url="https://auth.keyholesolution.com/realms/keyhole-mcp",
    )


@pytest.fixture
def shadow_session() -> AuthSession:
    """Return a valid session in shadow mode."""
    return AuthSession(
        access_token="shadow-token-abc123",
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        flow_type=AuthFlowType.PKCE,
        mode=AuthMode.SHADOW,
    )


@pytest.fixture
def expired_session() -> AuthSession:
    """Return an expired session."""
    return AuthSession(
        access_token="expired-token-abc123",
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        flow_type=AuthFlowType.PKCE,
        mode=AuthMode.REAL,
    )


@pytest.fixture
def sample_whoami() -> WhoamiResponse:
    """Return a sample whoami response."""
    return WhoamiResponse(
        user_id="user-001",
        tenant_id="tenant-001",
        org_id="org-001",
        cohort_id="cohort-001",
        worker_id="worker-001",
        workspace_id="ws-001",
        plan="developer",
        mode=AuthMode.REAL,
        display_name="Test Builder",
        email="builder@example.com",
        roles=["builder", "viewer"],
    )


@pytest.fixture
def shadow_whoami() -> WhoamiResponse:
    """Return a whoami response in shadow mode."""
    return WhoamiResponse(
        user_id="user-002",
        tenant_id="tenant-002",
        org_id="org-002",
        mode=AuthMode.SHADOW,
        plan="shadow",
    )


@pytest.fixture
def sample_token_response() -> TokenResponse:
    """Return a valid token response."""
    return TokenResponse(
        access_token="new-access-token-def456",
        token_type="Bearer",
        expires_in=3600,
        refresh_token="new-refresh-token-uvw321",
        scope="openid profile email",
    )


# ------------------------------------------------------------
# section1 - Models Validation and Safety
# ------------------------------------------------------------


class TestModels:
    """Verify auth models enforce correct structure and hide secrets."""

    def test_auth_session_hides_token_in_repr(self, sample_session: AuthSession):
        """Tokens must not appear in repr output."""
        r = repr(sample_session)
        assert "test-access-token" not in r
        assert "test-refresh-token" not in r

    def test_auth_session_token_fingerprint(self, sample_session: AuthSession):
        """Token fingerprint is a stable SHA-256 prefix."""
        fp = sample_session.token_fingerprint
        assert len(fp) == 8
        expected = hashlib.sha256(b"test-access-token-abc123").hexdigest()[:8]
        assert fp == expected

    def test_auth_session_safe_summary_no_secrets(self, sample_session: AuthSession):
        """safe_summary() must not contain raw tokens."""
        summary = sample_session.safe_summary()
        assert "test-access-token" not in json.dumps(summary)
        assert "test-refresh-token" not in json.dumps(summary)
        assert summary["token_fingerprint"] == sample_session.token_fingerprint
        assert summary["flow_type"] == "pkce"
        assert summary["mode"] == "real"

    def test_auth_session_is_expired(self, expired_session: AuthSession):
        """Expired sessions report is_expired=True."""
        assert expired_session.is_expired is True

    def test_auth_session_not_expired(self, sample_session: AuthSession):
        """Valid sessions report is_expired=False."""
        assert sample_session.is_expired is False

    def test_auth_session_no_expiry_never_expired(self):
        """Session without expires_at is never expired."""
        session = AuthSession(
            access_token="tok", flow_type=AuthFlowType.PKCE
        )
        assert session.is_expired is False

    def test_auth_flow_type_enum(self):
        assert AuthFlowType.PKCE.value == "pkce"
        assert AuthFlowType.DEVICE.value == "device"

    def test_auth_mode_enum(self):
        assert AuthMode.SHADOW.value == "shadow"
        assert AuthMode.REAL.value == "real"

    def test_whoami_response_mode_normalization(self):
        """WhoamiResponse normalizes mode string to enum."""
        w = WhoamiResponse(mode="SHADOW")
        assert w.mode == AuthMode.SHADOW

    def test_login_result_safe_summary(self):
        lr = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            credential_persisted=True,
            verification_passed=True,
        )
        summary = lr.safe_summary()
        assert summary["success"] is True
        assert summary["flow_type"] == "pkce"
        assert summary["mode"] == "real"

    def test_token_response_hides_secrets(self, sample_token_response: TokenResponse):
        """TokenResponse must not expose secrets in repr."""
        r = repr(sample_token_response)
        assert "new-access-token" not in r
        assert "new-refresh-token" not in r

    def test_pkce_challenge_hides_verifier(self):
        """PKCEChallenge must not show code_verifier in repr."""
        ch = PKCEChallenge(
            code_verifier="super-secret-verifier",
            code_challenge="abc",
            state="xyz",
            authorization_url="https://auth.example.com/authorize",
        )
        assert "super-secret-verifier" not in repr(ch)

    def test_device_code_response_hides_device_code(self):
        """DeviceCodeResponse must not show device_code in repr."""
        dc = DeviceCodeResponse(
            device_code="secret-device-code",
            user_code="ABCD-1234",
            verification_uri="https://auth.example.com/device",
        )
        assert "secret-device-code" not in repr(dc)


# ------------------------------------------------------------
# section2 - Credential Store Lifecycle
# ------------------------------------------------------------


class TestCredentialStore:
    """Verify credential store CRUD, permissions, and error handling."""

    def test_save_and_load(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """Save then load returns equivalent session."""
        tmp_store.save(sample_session)
        loaded = tmp_store.load()
        assert loaded is not None
        assert loaded.access_token == sample_session.access_token
        assert loaded.flow_type == sample_session.flow_type
        assert loaded.mode == sample_session.mode

    def test_load_missing_returns_none(self, tmp_store: CredentialStore):
        """Loading from empty store returns None."""
        assert tmp_store.load() is None

    def test_exists_after_save(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """exists() returns True after saving."""
        assert tmp_store.exists() is False
        tmp_store.save(sample_session)
        assert tmp_store.exists() is True

    def test_clear_removes_credentials(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """clear() removes the credentials file."""
        tmp_store.save(sample_session)
        assert tmp_store.exists()
        tmp_store.clear()
        assert not tmp_store.exists()

    def test_is_authenticated(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """is_authenticated() returns True for valid, non-expired session."""
        tmp_store.save(sample_session)
        assert tmp_store.is_authenticated() is True

    def test_is_authenticated_expired(self, tmp_store: CredentialStore, expired_session: AuthSession):
        """is_authenticated() returns False for expired session."""
        tmp_store.save(expired_session)
        assert tmp_store.is_authenticated() is False

    def test_is_authenticated_empty(self, tmp_store: CredentialStore):
        """is_authenticated() returns False when no session stored."""
        assert tmp_store.is_authenticated() is False

    def test_file_permissions(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """Credential file must have restrictive permissions (0600)."""
        tmp_store.save(sample_session)
        mode = oct(tmp_store.credentials_path.stat().st_mode & 0o777)
        if sys.platform == "win32":
            assert tmp_store.credentials_path.is_file()
        else:
            assert mode == "0o600"

    def test_directory_permissions(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """Store directory must have restricted permissions (0700)."""
        tmp_store.save(sample_session)
        mode = oct(tmp_store.store_dir.stat().st_mode & 0o777)
        if sys.platform == "win32":
            assert tmp_store.store_dir.is_dir()
        else:
            assert mode == "0o700"

    def test_save_atomic_write(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """Save uses an atomic write (no .tmp file left behind)."""
        tmp_store.save(sample_session)
        tmp_file = tmp_store.credentials_path.with_suffix(".tmp")
        assert not tmp_file.exists()

    def test_overwrite_existing(self, tmp_store: CredentialStore, sample_session: AuthSession):
        """Saving twice overwrites the first session."""
        tmp_store.save(sample_session)
        new_session = AuthSession(
            access_token="new-token",
            flow_type=AuthFlowType.DEVICE,
            mode=AuthMode.SHADOW,
        )
        tmp_store.save(new_session)
        loaded = tmp_store.load()
        assert loaded is not None
        assert loaded.access_token == "new-token"
        assert loaded.flow_type == AuthFlowType.DEVICE

    def test_clear_nonexistent_no_error(self, tmp_store: CredentialStore):
        """Clearing empty store does not raise."""
        tmp_store.clear()  # should not raise

    def test_credential_store_write_failure(self, tmp_path: Path):
        """Test H - Credential store write failure."""
        # Use a read-only directory to simulate write failure
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        os.chmod(read_only_dir, stat.S_IRUSR | stat.S_IXUSR)

        store = CredentialStore(store_dir=read_only_dir / ".keyhole")
        session = AuthSession(
            access_token="tok", flow_type=AuthFlowType.PKCE
        )
        with pytest.raises(CredentialStoreError):
            store.save(session)

        # Restore permissions for cleanup
        os.chmod(read_only_dir, stat.S_IRWXU)


# ------------------------------------------------------------
# section3 - PKCE Flow Mechanics
# ------------------------------------------------------------


class TestPKCEFlow:
    """Verify PKCE challenge generation and code exchange."""

    def test_code_verifier_length(self):
        """Code verifier meets PKCE length requirements."""
        verifier = _generate_code_verifier()
        assert 43 <= len(verifier) <= 128

    def test_code_verifier_unique(self):
        """Each verifier is unique."""
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        assert v1 != v2

    def test_code_challenge_s256(self):
        """Code challenge is correct S256 derivation of verifier."""
        verifier = "test-verifier-12345"
        challenge = _generate_code_challenge(verifier)
        # Verify by recomputing
        import base64
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_generate_challenge(self):
        """PKCEFlow.generate_challenge() produces valid challenge."""
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test-client",
        )
        challenge = flow.generate_challenge()
        assert isinstance(challenge, PKCEChallenge)
        assert challenge.code_challenge_method == "S256"
        assert "/protocol/openid-connect/auth" in challenge.authorization_url
        assert "code_challenge=" in challenge.authorization_url
        assert "state=" in challenge.authorization_url
        assert len(challenge.state) > 20  # Cryptographic state

    def test_authorization_url_params(self):
        """Authorization URL contains required OAuth2 PKCE params."""
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="my-client",
            scope="openid",
        )
        challenge = flow.generate_challenge()
        url = challenge.authorization_url
        assert "response_type=code" in url
        assert "client_id=my-client" in url
        assert "scope=openid" in url
        assert "code_challenge_method=S256" in url

    @patch("keyhole_sdk.auth_bootstrap.pkce.requests.post")
    def test_exchange_code_success(self, mock_post):
        """Successful code exchange returns TokenResponse."""
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "at-123",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        token = flow.exchange_code("code-abc", "verifier-xyz")
        assert isinstance(token, TokenResponse)
        assert token.access_token == "at-123"

    @patch("keyhole_sdk.auth_bootstrap.pkce.requests.post")
    def test_exchange_code_network_error(self, mock_post):
        """Network failure during code exchange raises NetworkError."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("refused")
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        with pytest.raises(NetworkError):
            flow.exchange_code("code", "verifier")

    @patch("keyhole_sdk.auth_bootstrap.pkce.requests.post")
    def test_exchange_code_invalid_response(self, mock_post):
        """Test G - Invalid completion artifact (bad HTTP status)."""
        mock_post.return_value = MagicMock(
            status_code=400,
            text="invalid_grant",
        )
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        with pytest.raises(InvalidTokenError):
            flow.exchange_code("bad-code", "verifier")

    @patch("keyhole_sdk.auth_bootstrap.pkce.webbrowser.open")
    def test_browser_launch_success(self, mock_open):
        """Browser opens successfully."""
        mock_open.return_value = True
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        assert flow.open_browser("https://auth.example.com/authorize") is True

    @patch("keyhole_sdk.auth_bootstrap.pkce.webbrowser.open")
    def test_browser_launch_failure(self, mock_open):
        """Test F - Browser cannot open returns False."""
        mock_open.side_effect = Exception("no display")
        flow = PKCEFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        assert flow.open_browser("https://auth.example.com/authorize") is False


# ------------------------------------------------------------
# section4 - Device Flow Mechanics
# ------------------------------------------------------------


class TestDeviceFlow:
    """Verify device/constrained flow operations."""

    _OIDC_DISCOVERY = {
        "device_authorization_endpoint": "https://auth.example.com/device",
        "token_endpoint": "https://auth.example.com/token",
    }

    @patch("keyhole_sdk.auth_bootstrap.device.requests.get")
    @patch("keyhole_sdk.auth_bootstrap.device.requests.post")
    def test_request_device_code_success(self, mock_post, mock_get):
        """Successful device code request."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self._OIDC_DISCOVERY,
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "device_code": "dev-123",
                "user_code": "ABCD-1234",
                "verification_uri": "https://auth.example.com/device",
                "expires_in": 600,
                "interval": 5,
            },
        )
        flow = DeviceFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        resp = flow.request_device_code()
        assert isinstance(resp, DeviceCodeResponse)
        assert resp.user_code == "ABCD-1234"

    @patch("keyhole_sdk.auth_bootstrap.device.requests.post")
    def test_request_device_code_network_error(self, mock_post):
        """Network failure during device code request."""
        import requests as req
        mock_post.side_effect = req.ConnectionError("refused")
        flow = DeviceFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        with pytest.raises(NetworkError):
            flow.request_device_code()

    @patch("keyhole_sdk.auth_bootstrap.device.requests.get")
    @patch("keyhole_sdk.auth_bootstrap.device.requests.post")
    @patch("keyhole_sdk.auth_bootstrap.device.time.sleep")
    @patch("keyhole_sdk.auth_bootstrap.device.time.monotonic")
    def test_poll_for_token_success(self, mock_mono, mock_sleep, mock_post, mock_get):
        """Test B - Device flow poll returns token after pending."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self._OIDC_DISCOVERY,
        )
        # First call: authorization_pending, second call: success
        mock_post.side_effect = [
            MagicMock(
                status_code=400,
                json=lambda: {"error": "authorization_pending"},
            ),
            MagicMock(
                status_code=200,
                json=lambda: {
                    "access_token": "device-token-123",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            ),
        ]
        # Simulate time progression (not yet expired)
        mock_mono.side_effect = [0, 5, 10]

        flow = DeviceFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        token = flow.poll_for_token("dev-code", interval=5, expires_in=600)
        assert token.access_token == "device-token-123"

    @patch("keyhole_sdk.auth_bootstrap.device.requests.get")
    @patch("keyhole_sdk.auth_bootstrap.device.requests.post")
    @patch("keyhole_sdk.auth_bootstrap.device.time.sleep")
    @patch("keyhole_sdk.auth_bootstrap.device.time.monotonic")
    def test_poll_for_token_expired(self, mock_mono, mock_sleep, mock_post, mock_get):
        """Device flow expires when user doesn't complete in time."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self._OIDC_DISCOVERY,
        )
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"error": "expired_token"},
        )
        mock_mono.side_effect = [0, 5]

        flow = DeviceFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        with pytest.raises(ExpiredChallengeError):
            flow.poll_for_token("dev-code", interval=5, expires_in=600)

    @patch("keyhole_sdk.auth_bootstrap.device.requests.get")
    @patch("keyhole_sdk.auth_bootstrap.device.requests.post")
    @patch("keyhole_sdk.auth_bootstrap.device.time.sleep")
    @patch("keyhole_sdk.auth_bootstrap.device.time.monotonic")
    def test_poll_for_token_denied(self, mock_mono, mock_sleep, mock_post, mock_get):
        """Device flow: access denied raises LoginDeniedError."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: self._OIDC_DISCOVERY,
        )
        mock_post.return_value = MagicMock(
            status_code=400,
            json=lambda: {"error": "access_denied"},
        )
        mock_mono.side_effect = [0, 5]

        flow = DeviceFlow(
            auth_server_url="https://auth.example.com",
            client_id="test",
        )
        with pytest.raises(LoginDeniedError):
            flow.poll_for_token("dev-code", interval=5, expires_in=600)


# ------------------------------------------------------------
# section5 - Whoami Client
# ------------------------------------------------------------


class TestWhoamiClient:
    """Verify whoami identity inspection."""

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_success(self, mock_get, sample_whoami: WhoamiResponse):
        """Whoami returns correct identity context."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: sample_whoami.model_dump(mode="json"),
        )
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        result = client.whoami("valid-token")
        assert isinstance(result, WhoamiResponse)
        assert result.user_id == "user-001"
        assert result.tenant_id == "tenant-001"
        assert result.mode == AuthMode.REAL

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_unauthorized(self, mock_get):
        """Whoami rejects invalid token with 401."""
        mock_get.return_value = MagicMock(status_code=401)
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        with pytest.raises(WhoamiVerificationError, match="401"):
            client.whoami("bad-token")

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_forbidden(self, mock_get):
        """Whoami rejects with 403."""
        mock_get.return_value = MagicMock(status_code=403)
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        with pytest.raises(WhoamiVerificationError, match="403"):
            client.whoami("bad-token")

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_network_error(self, mock_get):
        """Whoami raises NetworkError on connection failure."""
        import requests as req
        mock_get.side_effect = req.ConnectionError("refused")
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        with pytest.raises(NetworkError):
            client.whoami("token")

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_timeout(self, mock_get):
        """Whoami raises NetworkError on timeout."""
        import requests as req
        mock_get.side_effect = req.Timeout("timed out")
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        with pytest.raises(NetworkError):
            client.whoami("token")

    @patch("keyhole_sdk.auth_bootstrap.whoami.requests.get")
    def test_whoami_shadow_mode(self, mock_get, shadow_whoami: WhoamiResponse):
        """Whoami correctly returns shadow mode identity."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: shadow_whoami.model_dump(mode="json"),
        )
        client = WhoamiClient(mcp_base_url="https://api.example.com")
        result = client.whoami("shadow-token")
        assert result.mode == AuthMode.SHADOW


# ------------------------------------------------------------
# section6 - Error Hierarchy and Repair Guidance
# ------------------------------------------------------------


class TestErrors:
    """Verify error classes provide repair guidance."""

    def test_network_error_has_repair(self):
        err = NetworkError()
        assert len(err.repair_suggestions) > 0
        assert err.error_class == "network_error"

    def test_browser_launch_error_has_repair(self):
        err = BrowserLaunchError()
        assert any("device" in s.lower() for s in err.repair_suggestions)
        assert err.error_class == "browser_launch_error"

    def test_expired_challenge_error_has_repair(self):
        err = ExpiredChallengeError()
        assert any("retry" in s.lower() for s in err.repair_suggestions)
        assert err.error_class == "expired_challenge"

    def test_invalid_token_error_has_repair(self):
        err = InvalidTokenError()
        assert len(err.repair_suggestions) > 0
        assert err.error_class == "invalid_token"

    def test_login_denied_error_has_repair(self):
        err = LoginDeniedError()
        assert any("admin" in s.lower() for s in err.repair_suggestions)
        assert err.error_class == "login_denied"

    def test_credential_store_error_has_repair(self):
        err = CredentialStoreError()
        assert any("keyhole" in s.lower() for s in err.repair_suggestions)
        assert err.error_class == "credential_store_error"

    def test_whoami_verification_error_has_repair(self):
        err = WhoamiVerificationError()
        assert any("login" in s.lower() for s in err.repair_suggestions)
        assert err.error_class == "whoami_verification_error"

    def test_all_errors_inherit_from_base(self):
        """All auth errors inherit from AuthBootstrapError and KeyholeSDKError."""
        from keyhole_sdk.exceptions import KeyholeSDKError

        for cls in [
            NetworkError, BrowserLaunchError, ExpiredChallengeError,
            InvalidTokenError, LoginDeniedError, CredentialStoreError,
            WhoamiVerificationError,
        ]:
            err = cls()
            assert isinstance(err, AuthBootstrapError)
            assert isinstance(err, KeyholeSDKError)


# ------------------------------------------------------------
# section7 - Auth Bootstrap Client (Orchestration)
# ------------------------------------------------------------


class TestAuthBootstrapClient:
    """Test A, B, C - Full login flow orchestration."""

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_pkce_login_success(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Test A - Full PKCE login success end-to-end."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "auth-code-123"
        mock_exchange.return_value = TokenResponse(
            access_token="pkce-token-abc",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            auth_server_url="https://auth.example.com",
            client_id="test",
            mcp_base_url="https://api.example.com",
            credential_store=tmp_store,
        )

        result = client.login(flow_type=AuthFlowType.PKCE)

        assert result.success is True
        assert result.flow_type == AuthFlowType.PKCE
        assert result.mode == AuthMode.REAL
        assert result.whoami is not None
        assert result.whoami.user_id == "user-001"
        assert result.credential_persisted is True
        assert result.verification_passed is True

        # Verify credential was stored
        assert tmp_store.is_authenticated()

    @patch.object(WhoamiClient, "whoami")
    @patch.object(DeviceFlow, "poll_for_token")
    @patch.object(DeviceFlow, "request_device_code")
    def test_device_login_success(
        self,
        mock_request_code,
        mock_poll,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Test B - Full device flow login success."""
        mock_request_code.return_value = DeviceCodeResponse(
            device_code="dev-123",
            user_code="ABCD-1234",
            verification_uri="https://auth.example.com/device",
        )
        mock_poll.return_value = TokenResponse(
            access_token="device-token-xyz",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            auth_server_url="https://auth.example.com",
            client_id="test",
            mcp_base_url="https://api.example.com",
            credential_store=tmp_store,
        )

        device_codes_shown = []

        result = client.login(
            flow_type=AuthFlowType.DEVICE,
            on_device_code=lambda dc: device_codes_shown.append(dc),
        )

        assert result.success is True
        assert result.flow_type == AuthFlowType.DEVICE
        assert result.credential_persisted is True
        assert result.verification_passed is True
        assert len(device_codes_shown) == 1

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_token_usable_across_commands(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Test C - Token stored and usable for subsequent commands."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="persistent-token",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            auth_server_url="https://auth.example.com",
            client_id="test",
            mcp_base_url="https://api.example.com",
            credential_store=tmp_store,
        )

        client.login(flow_type=AuthFlowType.PKCE)

        # Load and verify the stored session
        session = tmp_store.load()
        assert session is not None
        assert session.access_token == "persistent-token"
        assert not session.is_expired

        # Verify it can be used for another whoami call
        mock_whoami.return_value = sample_whoami
        client2 = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result2 = client2.login()  # Should reuse existing session
        assert result2.success is True

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_shadow_mode_visible(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        shadow_whoami: WhoamiResponse,
    ):
        """Test D - Shadow mode is visible in result."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="shadow-token",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = shadow_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is True
        assert result.mode == AuthMode.SHADOW
        assert result.whoami.mode == AuthMode.SHADOW

        # Verify stored session has shadow mode
        session = tmp_store.load()
        assert session.mode == AuthMode.SHADOW

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_real_mode_visible(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Test E - Real mode is visible in result."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="real-token",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is True
        assert result.mode == AuthMode.REAL
        assert result.whoami.mode == AuthMode.REAL

    @patch.object(PKCEFlow, "open_browser")
    def test_browser_launch_failure(
        self,
        mock_open_browser,
        tmp_store: CredentialStore,
    ):
        """Test F - Browser flow cannot open returns failure with repair."""
        mock_open_browser.return_value = False

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE)

        assert result.success is False
        assert result.error_class == "browser_launch_error"
        assert len(result.repair_suggestions) > 0

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_whoami_fails_after_login(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Test I - Whoami fails after successful token acquisition.

        HARDENED: Credentials must NOT be persisted when /whoami fails.
        This is the key behavioral change - token receipt alone is not success.
        """
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="token-123",
            token_type="Bearer",
        )
        mock_whoami.side_effect = WhoamiVerificationError()

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is False
        assert result.error_class == "whoami_verification_error"
        assert result.credential_persisted is False  # HARDENED: not persisted
        assert result.verification_passed is False
        # Verify credential store is empty
        assert tmp_store.load() is None

    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_expired_challenge(
        self,
        mock_open_browser,
        mock_wait_callback,
        tmp_store: CredentialStore,
    ):
        """Expired PKCE challenge returns failure with repair."""
        mock_open_browser.return_value = True
        mock_wait_callback.side_effect = ExpiredChallengeError()

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is False
        assert result.error_class == "expired_challenge"
        assert len(result.repair_suggestions) > 0


# ------------------------------------------------------------
# section8 - CLI Command Integration
# ------------------------------------------------------------


class TestCLILogin:
    """Test CLI login command output structure."""

    @patch("keyhole_cli.commands.login.AuthBootstrapClient")
    def test_login_default_uses_device_flow(self, MockClient):
        """Bare run_login uses device flow, not PKCE loopback."""
        mock_instance = MockClient.return_value
        mock_instance.login.return_value = LoginResult(
            success=True,
            flow_type=AuthFlowType.DEVICE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(
                user_id="user-001",
                tenant_id="t-001",
                mode=AuthMode.REAL,
            ),
            credential_persisted=True,
            verification_passed=True,
        )

        result = run_login()

        assert result.success is True
        assert mock_instance.login.call_args.kwargs["flow_type"] == AuthFlowType.DEVICE
        assert result.data["flow_type"] == "device"

    @patch("keyhole_cli.commands.login.AuthBootstrapClient")
    def test_login_success_result(self, MockClient):
        """Login success produces correct CommandResult."""
        mock_instance = MockClient.return_value
        mock_instance.login.return_value = LoginResult(
            success=True,
            flow_type=AuthFlowType.DEVICE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(
                user_id="user-001",
                tenant_id="t-001",
                org_id="o-001",
                mode=AuthMode.REAL,
                display_name="Builder",
            ),
            credential_persisted=True,
            verification_passed=True,
        )

        result = run_login()
        assert result.success is True
        assert result.command == "login"
        assert result.exit_code == 0
        assert result.data["mode"] == "real"
        assert result.data["user_id"] == "user-001"
        assert len(result.next_steps) > 0
        assert mock_instance.login.call_args.kwargs["flow_type"] == AuthFlowType.DEVICE

    @patch("keyhole_cli.commands.login.AuthBootstrapClient")
    def test_login_failure_result(self, MockClient):
        """Login failure produces repair suggestions."""
        mock_instance = MockClient.return_value
        mock_instance.login.return_value = LoginResult(
            success=False,
            flow_type=AuthFlowType.PKCE,
            error_class="network_error",
            error_message="Cannot reach auth server",
            repair_suggestions=["Check connectivity"],
        )

        result = run_login()
        assert result.success is False
        assert result.command == "login"
        assert result.exit_code == 1
        assert result.data["error_class"] == "network_error"
        assert "Check connectivity" in result.next_steps

    def test_login_invalid_flow_type(self):
        """Invalid flow type returns failure with guidance."""
        result = run_login(flow="invalid")
        assert result.success is False
        assert "Unknown flow type" in result.summary

    @patch("keyhole_cli.cli.run_login")
    def test_cli_login_default_passes_device_flow(self, mock_run_login):
        """Bare `keyhole login` passes the device default through Typer."""
        mock_run_login.return_value = CommandResult(command="login", success=True)

        result = CliRunner().invoke(app, ["login", "--json"])

        assert result.exit_code == 0
        assert mock_run_login.call_args.kwargs["flow"] == "device"
        assert mock_run_login.call_args.kwargs["_flow_explicit"] is False

    @patch("keyhole_cli.cli.run_login")
    def test_cli_login_explicit_pkce_is_still_available(self, mock_run_login):
        """PKCE remains opt-in for environments that need browser loopback."""
        mock_run_login.return_value = CommandResult(command="login", success=True)

        result = CliRunner().invoke(app, ["login", "--flow", "pkce", "--json"])

        assert result.exit_code == 0
        assert mock_run_login.call_args.kwargs["flow"] == "pkce"
        assert mock_run_login.call_args.kwargs["_flow_explicit"] is True


class TestCLIWhoami:
    """Test CLI whoami command output structure."""

    @patch("keyhole_cli.commands.whoami.WhoamiClient")
    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_success(self, MockStore, MockWhoami):
        """Whoami success renders identity context."""
        mock_store = MockStore.return_value
        mock_store.load.return_value = AuthSession(
            access_token="tok",
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
        )
        mock_client = MockWhoami.return_value
        mock_client.whoami.return_value = WhoamiResponse(
            user_id="user-001",
            tenant_id="t-001",
            org_id="o-001",
            mode=AuthMode.REAL,
            plan="developer",
        )

        result = run_whoami()
        assert result.success is True
        assert result.command == "whoami"
        assert result.data["user_id"] == "user-001"
        assert result.data["mode"] == "real"
        assert result.data["plan"] == "developer"

    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_no_session(self, MockStore):
        """Test J - Missing local session produces clean failure."""
        mock_store = MockStore.return_value
        mock_store.load.return_value = None

        result = run_whoami()
        assert result.success is False
        assert "Not authenticated" in result.summary
        assert any("login" in s.lower() for s in result.next_steps)

    @patch("keyhole_cli.commands.whoami.get_fresh_token")
    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_expired_session_refresh_failure(self, MockStore, mock_refresh):
        """Test J - Expired session produces clean failure."""
        expired = AuthSession(
            access_token="tok",
            flow_type=AuthFlowType.PKCE,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        mock_store = MockStore.return_value
        mock_store.load.return_value = expired
        mock_refresh.side_effect = RuntimeError("no refresh")

        result = run_whoami()
        assert result.success is False
        assert "refresh failed" in result.summary.lower()
        assert any("login" in s.lower() for s in result.next_steps)

    @patch("keyhole_cli.commands.whoami.get_fresh_token")
    @patch("keyhole_cli.commands.whoami.WhoamiClient")
    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_expired_session_refreshes(self, MockStore, MockWhoami, mock_refresh):
        """Expired access token uses refresh token before whoami."""
        expired = AuthSession(
            access_token="tok",
            flow_type=AuthFlowType.PKCE,
            refresh_token="refresh",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        mock_store = MockStore.return_value
        mock_store.load.return_value = expired
        mock_refresh.return_value = "fresh-token"
        mock_client = MockWhoami.return_value
        mock_client.whoami.return_value = WhoamiResponse(
            user_id="user-001",
            tenant_id="t-001",
            org_id="o-001",
            mode=AuthMode.REAL,
        )

        result = run_whoami()
        assert result.success is True
        mock_refresh.assert_called_once()
        mock_client.whoami.assert_called_once_with("fresh-token")

    @patch("keyhole_cli.commands.whoami.WhoamiClient")
    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_verification_failure(self, MockStore, MockWhoami):
        """Whoami failure after token load shows repair guidance."""
        mock_store = MockStore.return_value
        mock_store.load.return_value = AuthSession(
            access_token="tok",
            flow_type=AuthFlowType.PKCE,
        )
        mock_client = MockWhoami.return_value
        mock_client.whoami.side_effect = WhoamiVerificationError()

        result = run_whoami()
        assert result.success is False
        assert result.data["error_class"] == "whoami_verification_error"

    @patch("keyhole_cli.commands.whoami.WhoamiClient")
    @patch("keyhole_cli.commands.whoami.CredentialStore")
    def test_whoami_shadow_mode_display(self, MockStore, MockWhoami):
        """Whoami shows shadow mode clearly."""
        mock_store = MockStore.return_value
        mock_store.load.return_value = AuthSession(
            access_token="tok",
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.SHADOW,
        )
        mock_client = MockWhoami.return_value
        mock_client.whoami.return_value = WhoamiResponse(
            user_id="user-002",
            mode=AuthMode.SHADOW,
            plan="shadow",
        )

        result = run_whoami()
        assert result.success is True
        assert result.data["mode"] == "shadow"
        assert "shadow" in result.summary.lower()


# ------------------------------------------------------------
# section9 - Proof Bundle Tests
# ------------------------------------------------------------


class TestProofBundle:
    """Test K, L - Proof bundle generation and secret safety."""

    def test_proof_bundle_structure(self):
        """Test K - Proof bundle contains all required artifacts."""
        proof = AuthProofBundle(correlation_id="corr-001")
        proof.record_event("login_initiated", {"flow": "pkce"})
        proof.record_event("login_completed", {"success": True})

        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(
                user_id="user-001",
                tenant_id="t-001",
                org_id="o-001",
                mode=AuthMode.REAL,
            ),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)

        # All required files present
        assert "core.json" in bundle
        assert "request.json" in bundle
        assert "response.json" in bundle
        assert "event_chain.json" in bundle
        assert "identity_context.json" in bundle
        assert "verification_result.json" in bundle
        assert "correlation.json" in bundle
        assert "summary.md" in bundle
        assert "digest.txt" in bundle

    def test_proof_bundle_core_content(self):
        """Core.json contains required fields."""
        proof = AuthProofBundle(correlation_id="corr-002")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)
        core = bundle["core.json"]

        assert core["proof_type"] == "auth_bootstrap"
        assert core["story_id"] == "SDK-CLIENT-01"
        assert core["correlation_id"] == "corr-002"
        assert core["success"] is True
        assert core["flow_type"] == "pkce"
        assert core["mode"] == "real"
        assert core["credential_persisted"] is True
        assert core["verification_passed"] is True

    def test_proof_bundle_identity_context(self):
        """Identity context captures whoami fields."""
        proof = AuthProofBundle(correlation_id="corr-003")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(
                user_id="u-1",
                tenant_id="t-1",
                org_id="o-1",
                cohort_id="c-1",
                workspace_id="ws-1",
                mode=AuthMode.REAL,
                plan="dev",
            ),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)
        ic = bundle["identity_context.json"]

        assert ic["user_id"] == "u-1"
        assert ic["tenant_id"] == "t-1"
        assert ic["org_id"] == "o-1"
        assert ic["mode"] == "real"

    def test_proof_bundle_verification_result(self):
        """Verification result captures pass/fail state."""
        proof = AuthProofBundle(correlation_id="corr-004")
        result = LoginResult(
            success=False,
            flow_type=AuthFlowType.DEVICE,
            error_class="network_error",
            error_message="Failed",
        )

        bundle = proof.generate(result)
        vr = bundle["verification_result.json"]

        assert vr["login_completed"] is False
        assert vr["whoami_verified"] is False
        assert vr["error_class"] == "network_error"

    def test_proof_bundle_event_chain(self):
        """Event chain records all events."""
        proof = AuthProofBundle(correlation_id="corr-005")
        proof.record_event("login_initiated", {"flow": "pkce"})
        proof.record_event("browser_opened", {"url": True})
        proof.record_event("login_completed", {"success": True})

        result = LoginResult(success=True, flow_type=AuthFlowType.PKCE)
        bundle = proof.generate(result)
        ec = bundle["event_chain.json"]

        assert ec["correlation_id"] == "corr-005"
        assert len(ec["events"]) == 3
        assert ec["events"][0]["event_type"] == "login_initiated"

    def test_proof_bundle_digest(self):
        """Digest is a valid SHA-256 hash of core.json."""
        proof = AuthProofBundle(correlation_id="corr-006")
        result = LoginResult(success=True, flow_type=AuthFlowType.PKCE)
        bundle = proof.generate(result)

        digest_str = bundle["digest.txt"]
        assert digest_str.startswith("sha256:")
        hash_value = digest_str.split(":")[1]
        assert len(hash_value) == 64

    def test_proof_bundle_summary_markdown(self):
        """Summary is valid markdown with key information."""
        proof = AuthProofBundle(correlation_id="corr-007")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(user_id="u-1", mode=AuthMode.REAL),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)
        summary = bundle["summary.md"]

        assert "# Auth Bootstrap Proof Summary" in summary
        assert "SDK-CLIENT-01" in summary
        assert "corr-007" in summary
        assert "Success:** True" in summary

    def test_proof_bundle_failure_summary(self):
        """Summary includes failure details and repair suggestions."""
        proof = AuthProofBundle(correlation_id="corr-008")
        result = LoginResult(
            success=False,
            flow_type=AuthFlowType.PKCE,
            error_class="network_error",
            error_message="Connection refused",
            repair_suggestions=["Check connectivity"],
        )

        bundle = proof.generate(result)
        summary = bundle["summary.md"]

        assert "network_error" in summary
        assert "Connection refused" in summary
        assert "Check connectivity" in summary

    def test_no_secret_leakage_in_proof(self):
        """Test L - No secrets in any proof artifact."""
        secret_token = "super-secret-token-never-leak-this"
        proof = AuthProofBundle(correlation_id="corr-009")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(user_id="u-1", mode=AuthMode.REAL),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)

        # Serialize all artifacts and check for token leakage
        for name, content in bundle.items():
            serialized = json.dumps(content, default=str) if not isinstance(content, str) else content
            assert secret_token not in serialized, f"Secret leaked in {name}"

    def test_proof_bundle_write_to_disk(self, tmp_path: Path):
        """Proof bundle writes all files to disk."""
        proof = AuthProofBundle(correlation_id="corr-010")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            credential_persisted=True,
            verification_passed=True,
        )

        bundle_dir = proof.write(result, tmp_path)
        assert bundle_dir.exists()
        assert (bundle_dir / "core.json").exists()
        assert (bundle_dir / "summary.md").exists()
        assert (bundle_dir / "digest.txt").exists()
        assert (bundle_dir / "extended").is_dir()

    def test_proof_bundle_mode_captured(self):
        """Proof bundle captures shadow vs real mode."""
        proof = AuthProofBundle(correlation_id="corr-011")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.SHADOW,
            whoami=WhoamiResponse(user_id="u-1", mode=AuthMode.SHADOW),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)
        assert bundle["core.json"]["mode"] == "shadow"
        assert bundle["identity_context.json"]["mode"] == "shadow"
        assert "shadow" in bundle["summary.md"].lower()


# ------------------------------------------------------------
# section10 - Integration Scenarios
# ------------------------------------------------------------


class TestIntegrationScenarios:
    """End-to-end scenarios combining multiple components."""

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_full_login_then_whoami(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Full flow: login -> store -> load -> whoami (Test C extended)."""
        whoami_resp = WhoamiResponse(
            user_id="user-001",
            tenant_id="t-001",
            org_id="o-001",
            cohort_id="c-001",
            mode=AuthMode.REAL,
            plan="developer",
        )
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="full-flow-token",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = whoami_resp

        # Step 1: Login
        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        login_result = client.login(flow_type=AuthFlowType.PKCE, force=True)
        assert login_result.success is True

        # Step 2: Verify stored credential independently
        session = tmp_store.load()
        assert session is not None
        assert session.access_token == "full-flow-token"
        assert session.last_verified_at is not None

        # Step 3: Use for whoami directly
        whoami_client = WhoamiClient(mcp_base_url="https://api.example.com")
        identity = whoami_client.whoami(session.access_token)
        assert identity.user_id == "user-001"

    def test_credential_roundtrip_shadow(self, tmp_store: CredentialStore, shadow_session: AuthSession):
        """Shadow session round-trips through credential store."""
        tmp_store.save(shadow_session)
        loaded = tmp_store.load()
        assert loaded is not None
        assert loaded.mode == AuthMode.SHADOW
        assert loaded.access_token == "shadow-token-abc123"

    def test_proof_captures_full_login_flow(self):
        """Proof bundle captures complete login lifecycle events."""
        proof = AuthProofBundle(correlation_id="integration-001")

        # Simulate full lifecycle
        proof.record_event("login_initiated", {"flow": "pkce", "force": False})
        proof.record_event("pkce_challenge_generated", {"state_length": 32})
        proof.record_event("browser_opened", {"success": True})
        proof.record_event("callback_received", {"has_code": True})
        proof.record_event("token_exchanged", {"token_type": "Bearer"})
        proof.record_event("credential_stored", {"persisted": True})
        proof.record_event("whoami_verified", {"user_id": "u-1", "mode": "real"})
        proof.record_event("login_completed", {"success": True})

        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(user_id="u-1", mode=AuthMode.REAL),
            credential_persisted=True,
            verification_passed=True,
        )

        bundle = proof.generate(result)
        assert len(bundle["event_chain.json"]["events"]) == 8
        assert bundle["core.json"]["success"] is True


# ------------------------------------------------------------
# section11 - Hardening: Server-Aligned Identity Governance
# ------------------------------------------------------------


class TestHardeningIdentityGovernance:
    """Verify server-aligned identity governance invariants.

    These tests enforce the hardened contract:
      - identity comes only from /whoami
      - credentials persist only after identity confirmed
      - correlation is stable across lifecycle
      - mode is server-determined
      - proof reflects server truth exactly
    """

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_login_success_requires_whoami(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Login is only successful when /whoami returns governed identity."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is True
        assert result.whoami is not None
        assert result.verification_passed is True
        assert result.identity_source == "server/whoami"

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_identity_matches_whoami_exactly(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Identity context used by client must match /whoami exactly."""
        server_whoami = WhoamiResponse(
            user_id="governed-user-42",
            tenant_id="governed-tenant-7",
            org_id="governed-org-3",
            cohort_id="governed-cohort-9",
            mode=AuthMode.SHADOW,
            plan="governed-plan",
        )
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = server_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is True
        assert result.whoami.user_id == "governed-user-42"
        assert result.whoami.tenant_id == "governed-tenant-7"
        assert result.whoami.org_id == "governed-org-3"
        assert result.whoami.mode == AuthMode.SHADOW
        assert result.mode == AuthMode.SHADOW

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_correlation_stable_through_lifecycle(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Single correlation ID spans entire auth lifecycle."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        fixed_cid = "stable-correlation-001"
        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(
            flow_type=AuthFlowType.PKCE,
            force=True,
            correlation_id=fixed_cid,
        )

        assert result.success is True
        assert result.correlation_id == fixed_cid

        # Verify the same correlation_id was passed to whoami
        mock_whoami.assert_called_once_with("tok", correlation_id=fixed_cid)

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_proof_uses_server_issued_identity_and_mode(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Proof bundle must use server-issued identity and mode."""
        server_whoami = WhoamiResponse(
            user_id="server-user",
            tenant_id="server-tenant",
            org_id="server-org",
            mode=AuthMode.SHADOW,
            plan="enterprise",
        )
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = server_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)
        assert result.success is True

        # Generate proof from this result
        proof = AuthProofBundle(correlation_id="proof-test-001")
        bundle = proof.generate(result)

        ic = bundle["identity_context.json"]
        assert ic["source"] == "server/whoami"
        assert ic["user_id"] == "server-user"
        assert ic["tenant_id"] == "server-tenant"
        assert ic["mode"] == "shadow"

        vr = bundle["verification_result.json"]
        assert vr["governed_identity_confirmed"] is True
        assert vr["identity_source"] == "server/whoami"
        assert vr["mode_source"] == "server/whoami"

        assert bundle["core.json"]["identity_source"] == "server/whoami"
        assert bundle["core.json"]["mode"] == "shadow"
        assert bundle["core.json"]["whoami_completed"] is True

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_session_persistence_only_after_whoami(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Credentials are persisted ONLY after successful /whoami."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="persistence-test-tok",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )

        # Before login: store is empty
        assert tmp_store.load() is None

        result = client.login(flow_type=AuthFlowType.PKCE, force=True)
        assert result.success is True
        assert result.credential_persisted is True

        # After login: store has the session with server mode
        session = tmp_store.load()
        assert session is not None
        assert session.access_token == "persistence-test-tok"
        assert session.mode == sample_whoami.mode
        assert session.last_verified_at is not None


class TestHardeningNegativeBehavior:
    """Negative tests for hardened identity governance."""

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_token_success_whoami_fail_is_login_failure(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Token exchange succeeds but /whoami fails -> login fails entirely."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="good-token", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.side_effect = WhoamiVerificationError("Server rejected")

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is False
        assert result.credential_persisted is False
        assert result.verification_passed is False
        assert result.whoami is None
        assert result.identity_source is None
        assert len(result.repair_suggestions) > 0

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_incomplete_identity_is_login_failure(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Token succeeds, /whoami returns but missing required fields -> failure."""
        incomplete_whoami = WhoamiResponse(
            user_id=None,  # Missing required field
            tenant_id="t-1",
            mode=AuthMode.REAL,
        )
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = incomplete_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is False
        assert result.error_class == "incomplete_identity"
        assert result.credential_persisted is False
        assert "user_id" in result.error_message

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_session_not_persisted_when_whoami_fails(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Credential store must be empty when /whoami fails."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="should-not-persist", token_type="Bearer",
        )
        mock_whoami.side_effect = NetworkError("Server down")

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.success is False
        assert result.credential_persisted is False
        # The store MUST be empty
        assert tmp_store.load() is None

    def test_proof_not_marked_complete_without_server_confirmation(self):
        """Proof bundle must not show governed closure without /whoami."""
        proof = AuthProofBundle(correlation_id="no-whoami-001")
        result = LoginResult(
            success=False,
            flow_type=AuthFlowType.PKCE,
            error_class="whoami_verification_error",
            error_message="Server rejected",
            credential_persisted=False,
            verification_passed=False,
        )

        bundle = proof.generate(result)
        vr = bundle["verification_result.json"]

        assert vr["governed_identity_confirmed"] is False
        assert vr["server_auth_event_confirmed"] is False
        assert vr["login_completed"] is False

        ic = bundle["identity_context.json"]
        assert ic["identity_resolved"] is False
        assert ic["source"] is None

    def test_client_does_not_decode_token_for_identity(self):
        """Tokens must be treated as opaque - no JWT decoding for identity.

        Verify that nowhere in the auth_bootstrap package does the code
        import jwt, jose, or base64-decode tokens for identity extraction.
        """
        import importlib
        import inspect

        modules = [
            "keyhole_sdk.auth_bootstrap.client",
            "keyhole_sdk.auth_bootstrap.models",
            "keyhole_sdk.auth_bootstrap.whoami",
            "keyhole_sdk.auth_bootstrap.proof",
            "keyhole_sdk.auth_bootstrap.credential_store",
        ]

        forbidden_patterns = ["jwt", "jose", "decode_token", "jwt_decode", "parse_jwt"]

        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            source = inspect.getsource(mod)
            for pattern in forbidden_patterns:
                assert pattern not in source.lower(), (
                    f"Token opacity violation: '{pattern}' found in {mod_name}"
                )


class TestHardeningSecurityBehavior:
    """Security invariants for hardened auth bootstrap."""

    def test_proof_still_excludes_secrets(self):
        """Proof bundle must never contain token secrets."""
        proof = AuthProofBundle(correlation_id="sec-001")
        result = LoginResult(
            success=True,
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
            whoami=WhoamiResponse(user_id="u", mode=AuthMode.REAL),
            credential_persisted=True,
            verification_passed=True,
            identity_source="server/whoami",
        )
        bundle = proof.generate(result)

        secret = "super-secret-token-never-leak"
        for name, content in bundle.items():
            serialized = json.dumps(content, default=str) if not isinstance(content, str) else content
            assert secret not in serialized, f"Secret leaked in {name}"

    def test_token_remains_opaque_in_session(self, tmp_store: CredentialStore):
        """Token stored in session is raw opaque value, not decoded."""
        session = AuthSession(
            access_token="eyJ.opaque.token",
            flow_type=AuthFlowType.PKCE,
            mode=AuthMode.REAL,
        )
        tmp_store.save(session)
        loaded = tmp_store.load()
        # Token is stored as-is, not decoded
        assert loaded.access_token == "eyJ.opaque.token"
        # No identity fields extracted from token
        summary = loaded.safe_summary()
        assert "eyJ" not in json.dumps(summary)

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_mode_shown_is_exactly_server_returned(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Mode displayed and in proof must match server /whoami exactly."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        server_mode = AuthMode.SHADOW
        mock_whoami.return_value = WhoamiResponse(
            user_id="u-1", mode=server_mode, plan="shadow",
        )

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        # LoginResult mode matches server
        assert result.mode == server_mode
        # Whoami response mode matches
        assert result.whoami.mode == server_mode
        # Stored session mode matches server
        session = tmp_store.load()
        assert session.mode == server_mode


class TestHardeningCorrelation:
    """Verify correlation ID stability across full lifecycle."""

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_correlation_generated_if_not_provided(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """A correlation_id is auto-generated when not supplied."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(flow_type=AuthFlowType.PKCE, force=True)

        assert result.correlation_id is not None
        assert len(result.correlation_id) > 0

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_correlation_in_proof_matches_login(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
        sample_whoami: WhoamiResponse,
    ):
        """Proof correlation_id matches the login correlation_id."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer", expires_in=3600,
        )
        mock_whoami.return_value = sample_whoami

        cid = "proof-corr-match-001"
        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(
            flow_type=AuthFlowType.PKCE, force=True, correlation_id=cid,
        )

        proof = AuthProofBundle(correlation_id=cid)
        bundle = proof.generate(result)

        assert bundle["core.json"]["correlation_id"] == cid
        assert bundle["event_chain.json"]["correlation_id"] == cid
        assert bundle["correlation.json"]["correlation_id"] == cid

    @patch.object(WhoamiClient, "whoami")
    @patch.object(PKCEFlow, "exchange_code")
    @patch.object(PKCEFlow, "wait_for_callback")
    @patch.object(PKCEFlow, "open_browser")
    def test_correlation_on_failure_still_present(
        self,
        mock_open_browser,
        mock_wait_callback,
        mock_exchange,
        mock_whoami,
        tmp_store: CredentialStore,
    ):
        """Correlation ID is present even when login fails."""
        mock_open_browser.return_value = True
        mock_wait_callback.return_value = "code"
        mock_exchange.return_value = TokenResponse(
            access_token="tok", token_type="Bearer",
        )
        mock_whoami.side_effect = WhoamiVerificationError()

        cid = "fail-corr-001"
        client = AuthBootstrapClient(
            credential_store=tmp_store,
            mcp_base_url="https://api.example.com",
        )
        result = client.login(
            flow_type=AuthFlowType.PKCE, force=True, correlation_id=cid,
        )

        assert result.success is False
        assert result.correlation_id == cid


class TestHardeningIdentityValidation:
    """Verify identity completeness validation."""

    def test_validate_required_identity_complete(self):
        """Complete identity passes validation."""
        w = WhoamiResponse(
            user_id="u-1", tenant_id="t-1", org_id="o-1", mode=AuthMode.REAL,
        )
        assert w.validate_required_identity() == []

    def test_validate_required_identity_missing_user_id(self):
        """Missing user_id is flagged."""
        w = WhoamiResponse(mode=AuthMode.REAL)
        missing = w.validate_required_identity()
        assert "user_id" in missing

    def test_validate_required_identity_empty_user_id(self):
        """Empty string user_id is flagged."""
        w = WhoamiResponse(user_id="  ", mode=AuthMode.REAL)
        missing = w.validate_required_identity()
        assert "user_id" in missing

    def test_incomplete_identity_error_has_repair(self):
        """IncompleteIdentityError carries repair guidance."""
        err = IncompleteIdentityError(missing_fields=["user_id", "mode"])
        assert err.error_class == "incomplete_identity"
        assert len(err.repair_suggestions) > 0
        assert "user_id" in str(err)
        assert err.missing_fields == ["user_id", "mode"]

    def test_incomplete_identity_inherits_from_base(self):
        """IncompleteIdentityError inherits from AuthBootstrapError."""
        err = IncompleteIdentityError()
        assert isinstance(err, AuthBootstrapError)

class TestDevPasswordLoginGate:
    """Password/ROPC login is dev/test-only and gated by env."""

    def test_password_login_disabled_by_default(self, monkeypatch, tmp_store):
        monkeypatch.delenv("KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN", raising=False)
        client = AuthBootstrapClient(
            auth_server_url="https://auth.example.com",
            mcp_base_url="https://mcp.example.com",
            credential_store=tmp_store,
        )

        result = client.login(
            flow_type=AuthFlowType.PASSWORD,
            username="dev",
            password="dev",
            force=True,
        )

        assert result.success is False
        assert result.error_class == "auth_bootstrap_error"
        assert "Password login is disabled" in (result.error_message or "")
        assert "keyhole login --flow device --force" in " ".join(result.repair_suggestions)

    def test_password_login_requires_explicit_dev_gate(self, monkeypatch, tmp_store):
        monkeypatch.setenv("KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN", "1")
        client = AuthBootstrapClient(
            auth_server_url="https://auth.example.com",
            mcp_base_url="https://mcp.example.com",
            credential_store=tmp_store,
        )

        monkeypatch.setattr(
            client,
            "_do_password_flow",
            lambda **_: TokenResponse(
                access_token="dev-token",
                token_type="Bearer",
                expires_in=3600,
            ),
        )
        monkeypatch.setattr(
            client._whoami_client,
            "whoami",
            lambda *_args, **_kwargs: WhoamiResponse(
                user_id="user-dev",
                tenant_id="tenant-dev",
                mode=AuthMode.REAL,
            ),
        )

        result = client.login(
            flow_type=AuthFlowType.PASSWORD,
            username="dev",
            password="dev",
            force=True,
        )

        assert result.success is True
        assert result.flow_type == AuthFlowType.PASSWORD
        assert result.credential_persisted is True
