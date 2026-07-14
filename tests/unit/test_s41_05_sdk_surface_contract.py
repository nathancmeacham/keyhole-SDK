"""CE-V5-S41-05 - SDK Surface Contract tests.

Covers all 7 sealed invariants from the story:
  INV-SDK-PUBLIC-BOUNDARY-CLOSED      - public-safe operations only
  INV-SDK-INSTALLABLE                 - clean install + import
  INV-SDK-EXAMPLES-EXECUTABLE         - canonical examples exist + parseable
  INV-SDK-RUNTIME-COMPATIBILITY       - compatibility check deterministic
  INV-SDK-NO-HIDDEN-PRIVILEGE         - no fabricated scopes/authority
  INV-SDK-STABLE-FACADE               - public surface narrower than internals
  INV-SDK-VERSIONED-CONTRACT          - version declared + testable

Also covers acceptance test plan items section23.1-section23.10.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

# Ensure SDK is importable from the worktree
_SDK_PKG = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-sdk"
if str(_SDK_PKG) not in sys.path:
    sys.path.insert(0, str(_SDK_PKG))

from keyhole_sdk import __version__ as SDK_VERSION
from keyhole_sdk import (
    AuthProvider,
    BearerTokenProvider,
    CallbackTokenProvider,
    EnvironmentTokenProvider,
    KeyholeClient,
    KeyholeConfig,
    KeyholeError,
    KeyholeSDKError,
    RuntimeBridgeClient,
)
from keyhole_sdk.auth import AuthProvider as AuthProviderBase
from keyhole_sdk.client import KeyholeClient as ClientDirect
from keyhole_sdk.config import KeyholeConfig as ConfigDirect
from keyhole_sdk.exceptions import (
    AuthenticationError,
    CompatibilityError,
    ContractIncompatibleError,
    PublicEndpointError,
    RuntimeUnavailableError,
    SchemaError,
    TransportError,
)
from keyhole_sdk.models import (
    PRIVATE_FIELDS,
    CompatibilityResult,
    CompatibilityStatus,
    PublicError,
    RealizationReceipt,
    RealizationRequest,
    RuntimeHealth,
    RuntimeIdentity,
    RuntimeState,
    _strip_private,
)
from keyhole_sdk.compatibility import COMPATIBILITY_RULES


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

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk"
EXAMPLES_DIR = REPO_ROOT / "examples" / "python-client"


def _mock_response(
    status_code: int = 200,
    json_data: Any = None,
    text: str = "",
) -> MagicMock:
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
    session.headers = {}
    return KeyholeClient(base_url="http://test:8080", session=session)


# --------------------------------------------------------------
# INV-SDK-INSTALLABLE (section23.1 - Clean Install Proof)
# --------------------------------------------------------------


class TestInstallable:
    """The SDK must be importable from a clean environment."""

    def test_top_level_import(self) -> None:
        """import keyhole_sdk succeeds."""
        import keyhole_sdk
        assert hasattr(keyhole_sdk, "__version__")

    def test_client_importable(self) -> None:
        assert KeyholeClient is not None

    def test_config_importable(self) -> None:
        assert KeyholeConfig is not None

    def test_error_importable(self) -> None:
        assert KeyholeError is not None
        assert KeyholeSDKError is not None

    def test_auth_importable(self) -> None:
        assert AuthProvider is not None
        assert BearerTokenProvider is not None

    def test_models_importable(self) -> None:
        assert RuntimeIdentity is not None
        assert RuntimeHealth is not None
        assert RuntimeState is not None
        assert RealizationRequest is not None
        assert RealizationReceipt is not None

    def test_construct_config(self) -> None:
        config = KeyholeConfig(base_url="http://test:8080")
        assert config.base_url == "http://test:8080"

    def test_construct_client(self) -> None:
        session = MagicMock()
        session.headers = {}
        client = KeyholeClient("http://test:8080", session=session)
        assert client.base_url == "http://test:8080"

    def test_pyproject_exists(self) -> None:
        assert (SDK_ROOT / "pyproject.toml").exists()


# --------------------------------------------------------------
# INV-SDK-STABLE-FACADE (section23.2 - Public Import Surface Proof)
# --------------------------------------------------------------


class TestStableFacade:
    """Public import surface must be narrow and stable."""

    def test_all_exports_defined(self) -> None:
        import keyhole_sdk
        assert hasattr(keyhole_sdk, "__all__")
        exports = keyhole_sdk.__all__
        assert len(exports) >= 10, "Public surface must have meaningful exports"

    def test_documented_imports_work(self) -> None:
        """All documented top-level imports must work."""
        from keyhole_sdk import KeyholeClient
        from keyhole_sdk import KeyholeConfig
        from keyhole_sdk import KeyholeError
        from keyhole_sdk import AuthProvider
        from keyhole_sdk import RuntimeIdentity
        from keyhole_sdk import TransportError
        assert all([
            KeyholeClient, KeyholeConfig, KeyholeError,
            AuthProvider, RuntimeIdentity, TransportError,
        ])

    def test_backward_compat_alias(self) -> None:
        assert RuntimeBridgeClient is KeyholeClient

    def test_version_string_format(self) -> None:
        parts = SDK_VERSION.split(".")
        assert len(parts) == 3, "Version must be semver: MAJOR.MINOR.PATCH"
        for p in parts:
            assert p.isdigit()

    def test_surfaces_accessible(self) -> None:
        """Grouped surfaces must be accessible on client instance."""
        session = MagicMock()
        session.headers = {}
        client = KeyholeClient("http://test:8080", session=session)
        assert hasattr(client, "system")
        assert hasattr(client, "identity")
        assert hasattr(client, "declarations")
        assert hasattr(client, "runs")
        assert hasattr(client, "evidence")


# --------------------------------------------------------------
# INV-SDK-NO-HIDDEN-PRIVILEGE (section23.3 - Auth Injection Proof)
# --------------------------------------------------------------


class TestNoHiddenPrivilege:
    """SDK must not fabricate scopes or bypass server enforcement."""

    def test_bearer_token_provider(self) -> None:
        provider = BearerTokenProvider("test-token")
        headers = provider.get_headers()
        assert headers == {"Authorization": "Bearer test-token"}

    def test_bearer_token_empty_rejected(self) -> None:
        with pytest.raises(ValueError):
            BearerTokenProvider("")

    def test_env_token_provider(self) -> None:
        os.environ["KEYHOLE_TEST_TOKEN"] = "env-token"
        try:
            provider = EnvironmentTokenProvider("KEYHOLE_TEST_TOKEN")
            assert provider.get_token() == "env-token"
        finally:
            del os.environ["KEYHOLE_TEST_TOKEN"]

    def test_env_token_provider_missing(self) -> None:
        provider = EnvironmentTokenProvider("NONEXISTENT_VAR_XYZ")
        assert provider.get_token() is None

    def test_callback_token_provider(self) -> None:
        provider = CallbackTokenProvider(lambda: "dynamic-token")
        assert provider.get_token() == "dynamic-token"

    def test_auth_provider_no_fabricated_scopes(self) -> None:
        """AuthProvider headers must only contain Authorization."""
        provider = BearerTokenProvider("token")
        headers = provider.get_headers()
        assert list(headers.keys()) == ["Authorization"]
        assert "scope" not in headers.get("Authorization", "").lower()

    def test_no_hidden_privilege_in_config(self) -> None:
        """Config must not embed operator secrets."""
        config = KeyholeConfig(base_url="http://test:8080", token="user-token")
        provider = config.resolve_auth_provider()
        assert isinstance(provider, BearerTokenProvider)
        # Token is what user provided, not fabricated
        assert provider.get_token() == "user-token"

    def test_private_fields_blocked_on_models(self) -> None:
        """SDK models must not require private fields."""
        identity_fields = set(RuntimeIdentity.model_fields.keys())
        assert not identity_fields & PRIVATE_FIELDS

        state_fields = set(RuntimeState.model_fields.keys())
        assert not state_fields & PRIVATE_FIELDS

        receipt_fields = set(RealizationReceipt.model_fields.keys())
        assert not receipt_fields & PRIVATE_FIELDS


# --------------------------------------------------------------
# INV-SDK-PUBLIC-BOUNDARY-CLOSED (section9 - Public Boundary)
# --------------------------------------------------------------


class TestPublicBoundaryClosed:
    """SDK must expose only public-safe operations."""

    def test_private_fields_stripped_from_identity(self) -> None:
        data = {
            **CANONICAL_IDENTITY,
            "pointer_state": "prod-v80",
            "canonical_digest": "sha256:deadbeef",
            "governance_verdict": "ACCEPT",
        }
        model = RuntimeIdentity.model_validate(data)
        d = model.model_dump()
        for private_field in ["pointer_state", "canonical_digest", "governance_verdict"]:
            assert private_field not in d

    def test_private_fields_stripped_from_state(self) -> None:
        data = {
            **CANONICAL_STATE,
            "controller_state": "reconciling",
            "internal_lane": "staging",
        }
        model = RuntimeState.model_validate(data)
        d = model.model_dump()
        assert "controller_state" not in d
        assert "internal_lane" not in d

    def test_strip_private_function(self) -> None:
        data = {
            "runtime_id": "rt-1",
            "pointer_state": "secret",
            "drift_state": "clean",
        }
        clean = _strip_private(data)
        assert "runtime_id" in clean
        assert "pointer_state" not in clean
        assert "drift_state" not in clean

    def test_private_fields_constant_coverage(self) -> None:
        assert len(PRIVATE_FIELDS) >= 8
        expected = {
            "pointer_state", "promotion_state", "canonical_digest",
            "cluster_topology", "internal_lane", "controller_state",
            "governance_verdict", "drift_state",
        }
        assert expected <= PRIVATE_FIELDS


# --------------------------------------------------------------
# INV-SDK-RUNTIME-COMPATIBILITY (section23.9 - Compatibility Proof)
# --------------------------------------------------------------


class TestRuntimeCompatibility:
    """Compatibility check must be deterministic and produce correct outcomes."""

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

    def test_incompatible_missing_identity(self) -> None:
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
        session.headers = {}
        session.request.side_effect = _req.ConnectionError("refused")
        client = KeyholeClient(base_url="http://test:8080", session=session)
        result = client.check_compatibility()
        assert result.compatibility_status == CompatibilityStatus.INCOMPATIBLE

    def test_determinism(self) -> None:
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


# --------------------------------------------------------------
# INV-SDK-VERSIONED-CONTRACT (section21 + section23.9)
# --------------------------------------------------------------


class TestVersionedContract:
    """SDK must declare versioning posture explicitly."""

    def test_version_in_init(self) -> None:
        import keyhole_sdk
        assert hasattr(keyhole_sdk, "__version__")
        assert keyhole_sdk.__version__ == SDK_VERSION

    def test_version_matches_pyproject(self) -> None:
        pyproject = SDK_ROOT / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert f'version = "{SDK_VERSION}"' in content

    def test_semver_format(self) -> None:
        parts = SDK_VERSION.split(".")
        assert len(parts) == 3
        major, minor, patch = parts
        assert int(major) >= 0
        assert int(minor) >= 0
        assert int(patch) >= 0

    def test_compatibility_rules_defined(self) -> None:
        assert "compatible_changes" in COMPATIBILITY_RULES
        assert "incompatible_changes" in COMPATIBILITY_RULES
        assert "promotion_rule" in COMPATIBILITY_RULES

    def test_incompatible_rules_non_empty(self) -> None:
        assert len(COMPATIBILITY_RULES["incompatible_changes"]) >= 3

    def test_promotion_rule_mentions_reject(self) -> None:
        assert "REJECT" in COMPATIBILITY_RULES["promotion_rule"]


# --------------------------------------------------------------
# INV-SDK-EXAMPLES-EXECUTABLE (section23.10 - Example Execution Proof)
# --------------------------------------------------------------


class TestExamplesExecutable:
    """Every shipped canonical example must be parseable and use SDK imports."""

    REQUIRED_EXAMPLES = [
        "hello_world.py",
        "whoami.py",
        "submit_declaration.py",
        "get_result.py",
        "get_evidence.py",
        "example_typed.py",
    ]

    def test_all_required_examples_exist(self) -> None:
        for name in self.REQUIRED_EXAMPLES:
            path = EXAMPLES_DIR / name
            assert path.exists(), f"Required example missing: {name}"

    @pytest.mark.parametrize("example_name", REQUIRED_EXAMPLES)
    def test_example_parses(self, example_name: str) -> None:
        """Example must be valid Python (AST parseable)."""
        path = EXAMPLES_DIR / example_name
        if not path.exists():
            pytest.skip(f"{example_name} not found")
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert tree is not None

    @pytest.mark.parametrize("example_name", REQUIRED_EXAMPLES)
    def test_example_imports_sdk(self, example_name: str) -> None:
        """Example must import from keyhole_sdk."""
        path = EXAMPLES_DIR / example_name
        if not path.exists():
            pytest.skip(f"{example_name} not found")
        source = path.read_text(encoding="utf-8")
        assert "keyhole_sdk" in source

    def test_hello_world_uses_health(self) -> None:
        source = (EXAMPLES_DIR / "hello_world.py").read_text(encoding="utf-8")
        assert "get_health" in source or "health" in source

    def test_whoami_uses_identity(self) -> None:
        source = (EXAMPLES_DIR / "whoami.py").read_text(encoding="utf-8")
        assert "get_identity" in source or "whoami" in source

    def test_submit_uses_declarations(self) -> None:
        source = (EXAMPLES_DIR / "submit_declaration.py").read_text(encoding="utf-8")
        assert "declarations" in source or "realize" in source

    def test_get_result_uses_state(self) -> None:
        source = (EXAMPLES_DIR / "get_result.py").read_text(encoding="utf-8")
        assert "state" in source or "runs" in source

    def test_get_evidence_uses_evidence(self) -> None:
        source = (EXAMPLES_DIR / "get_evidence.py").read_text(encoding="utf-8")
        assert "evidence" in source


# --------------------------------------------------------------
# section23 Acceptance Tests - Client Behavior
# --------------------------------------------------------------


class TestClientBehavior:
    """Client must be stable, deterministic, and expose typed results."""

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

    def test_realize_typed_returns_receipt(self) -> None:
        client = _make_client([_mock_response(json_data=CANONICAL_RECEIPT)])
        result = client.realize_typed("sha256:abc", payload={"k": "v"})
        assert isinstance(result, RealizationReceipt)
        assert result.status == "ACCEPT"

    def test_context_manager_closes(self) -> None:
        session = MagicMock()
        session.headers = {}
        with KeyholeClient(base_url="http://test:8080", session=session):
            pass
        session.close.assert_called_once()

    def test_from_config_constructor(self) -> None:
        config = KeyholeConfig(
            base_url="http://config-test:8080",
            token="cfg-token",
            timeout=5.0,
        )
        session = MagicMock()
        session.headers = {}
        client = KeyholeClient.from_config(config, session=session)
        assert client.base_url == "http://config-test:8080"
        assert client.timeout == 5.0


# --------------------------------------------------------------
# section12.4 Error Surface - Predictable Error Classification
# --------------------------------------------------------------


class TestErrorSurface:
    """SDK must distinguish error classes per section12.4."""

    def test_exception_hierarchy_complete(self) -> None:
        assert issubclass(TransportError, KeyholeSDKError)
        assert issubclass(AuthenticationError, KeyholeSDKError)
        assert issubclass(RuntimeUnavailableError, KeyholeSDKError)
        assert issubclass(SchemaError, KeyholeSDKError)
        assert issubclass(CompatibilityError, KeyholeSDKError)
        assert issubclass(ContractIncompatibleError, KeyholeSDKError)
        assert issubclass(PublicEndpointError, KeyholeSDKError)

    def test_transport_error_on_connection(self) -> None:
        import requests as _req
        session = MagicMock()
        session.headers = {}
        session.request.side_effect = _req.ConnectionError("refused")
        client = KeyholeClient(base_url="http://test:8080", session=session)
        with pytest.raises(TransportError):
            client.get_identity()

    def test_runtime_unavailable_on_500(self) -> None:
        client = _make_client([_mock_response(status_code=500, text="Internal")])
        with pytest.raises(RuntimeUnavailableError):
            client.get_identity()

    def test_public_endpoint_error_on_4xx(self) -> None:
        resp = _mock_response(
            status_code=404,
            json_data={"error": "not_found", "detail": "missing"},
        )
        client = _make_client([resp])
        with pytest.raises(PublicEndpointError) as exc_info:
            client.get_identity()
        assert exc_info.value.status_code == 404

    def test_schema_error_on_bad_shape(self) -> None:
        client = _make_client([_mock_response(json_data={"bad": "shape"})])
        with pytest.raises(SchemaError):
            client.get_identity()

    def test_keyhole_error_alias(self) -> None:
        assert KeyholeError is KeyholeSDKError


# --------------------------------------------------------------
# section15 Configuration Contract
# --------------------------------------------------------------


class TestConfigurationContract:
    """Configuration must be narrow and explicit."""

    def test_default_config(self) -> None:
        config = KeyholeConfig()
        assert config.base_url == "https://mcp.keyholesolution.com"
        assert config.timeout == 10.0
        assert config.auth_provider is None
        assert config.token is None
        assert config.user_agent == "keyhole-sdk-python"

    def test_config_with_token(self) -> None:
        config = KeyholeConfig(token="my-token")
        provider = config.resolve_auth_provider()
        assert isinstance(provider, BearerTokenProvider)
        assert provider.get_token() == "my-token"

    def test_config_with_auth_provider(self) -> None:
        provider = BearerTokenProvider("explicit-provider")
        config = KeyholeConfig(auth_provider=provider)
        assert config.resolve_auth_provider() is provider

    def test_config_auth_provider_priority(self) -> None:
        """auth_provider takes priority over token."""
        provider = BearerTokenProvider("provider-token")
        config = KeyholeConfig(auth_provider=provider, token="shorthand-token")
        resolved = config.resolve_auth_provider()
        assert resolved is provider
        assert resolved.get_token() == "provider-token"

    def test_config_empty_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            KeyholeConfig(base_url="")

    def test_config_negative_timeout_rejected(self) -> None:
        with pytest.raises(ValueError):
            KeyholeConfig(timeout=-1)

    def test_config_immutable(self) -> None:
        """Config should be frozen (immutable)."""
        config = KeyholeConfig()
        with pytest.raises(Exception):
            config.base_url = "http://new-url"  # type: ignore


# --------------------------------------------------------------
# section6 Packaging Stance
# --------------------------------------------------------------


class TestPackagingStance:
    """Package structure must be correct."""

    def test_pyproject_toml_exists(self) -> None:
        assert (SDK_ROOT / "pyproject.toml").exists()

    def test_readme_exists(self) -> None:
        assert (SDK_ROOT / "README.md").exists()

    def test_package_init_exists(self) -> None:
        assert (SDK_ROOT / "keyhole_sdk" / "__init__.py").exists()

    def test_required_modules_exist(self) -> None:
        pkg = SDK_ROOT / "keyhole_sdk"
        required = ["client.py", "config.py", "auth.py", "exceptions.py",
                     "models.py", "compatibility.py"]
        for mod in required:
            assert (pkg / mod).exists(), f"Required module missing: {mod}"

    def test_surfaces_package_exists(self) -> None:
        surfaces = SDK_ROOT / "keyhole_sdk" / "surfaces"
        assert surfaces.is_dir()
        assert (surfaces / "__init__.py").exists()

    def test_transport_package_exists(self) -> None:
        transport = SDK_ROOT / "keyhole_sdk" / "transport"
        assert transport.is_dir()
        assert (transport / "__init__.py").exists()

    def test_pyproject_declares_python_39_plus(self) -> None:
        content = (SDK_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert ">=3.9" in content

    def test_pyproject_declares_dependencies(self) -> None:
        content = (SDK_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert "requests" in content
        assert "pydantic" in content
