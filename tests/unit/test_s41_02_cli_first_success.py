"""S41-02 - CLI First-Success Governance test suite.

Tests cover:
  - Profile detection determinism
  - Doctor command logic
  - Init command idempotency
  - Runtime lifecycle truthfulness
  - Smoke end-to-end path
  - JSON output contract stability
  - Exit code semantics
  - Public/private boundary (no forbidden fields)
"""

from __future__ import annotations

import json
import os
import platform
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest

# -- Make CLI package importable ------------------------------
import sys

CLI_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-cli"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))

from keyhole_cli.profile import detect_profile, ProfileResult, SUPPORTED_PROFILES
from keyhole_cli.doctor.contract import EnvironmentFacts
from keyhole_cli.result import (
    CommandResult,
    EXIT_SUCCESS,
    EXIT_FAILURE,
    EXIT_UNSUPPORTED,
    EXIT_RUNTIME_UNAVAILABLE,
    EXIT_INVALID_INPUT,
    EXIT_CONTRACT_FAILURE,
)
from keyhole_cli.commands.doctor import run_doctor
from keyhole_cli.commands.init_cmd import run_init
from keyhole_cli.commands.runtime import (
    run_start,
    run_stop,
    run_status,
    _PRIVATE_FIELDS,
)
from keyhole_cli.commands.smoke import run_smoke


# --------------------------------------------------------------
# S41-02-INV-02 - Profile detection determinism
# --------------------------------------------------------------

class TestProfileDetection:
    """Profile detection must be deterministic and reproducible."""

    def test_deterministic_repeated_calls(self) -> None:
        """Same environment -> same profile result."""
        r1 = detect_profile()
        r2 = detect_profile()
        assert r1.detected_profile == r2.detected_profile
        assert r1.supported == r2.supported
        assert r1.os_family == r2.os_family
        assert r1.is_wsl == r2.is_wsl

    def test_profile_result_to_dict(self) -> None:
        """ProfileResult.to_dict() includes all required keys."""
        r = detect_profile()
        d = r.to_dict()
        required = {
            "supported", "detected_profile", "os_family", "shell",
            "is_wsl", "docker_available", "compose_available",
            "required_checks", "failed_checks", "warnings", "next_steps",
        }
        assert required.issubset(d.keys())

    def test_supported_profiles_constant(self) -> None:
        """Supported profiles set is well-defined."""
        assert "linux" in SUPPORTED_PROFILES
        assert "wsl" in SUPPORTED_PROFILES
        assert "windows-powershell" in SUPPORTED_PROFILES

    @patch("keyhole_cli.profile._detect_os_family", return_value="linux")
    @patch("keyhole_cli.profile._detect_wsl", return_value=False)
    @patch("keyhole_cli.profile._detect_shell", return_value="bash")
    @patch("keyhole_cli.profile._check_docker", return_value=True)
    @patch("keyhole_cli.profile._check_compose", return_value=True)
    def test_linux_profile_supported(self, *_: Any) -> None:
        r = detect_profile()
        assert r.detected_profile == "linux"
        assert r.supported is True
        assert r.failed_checks == []

    @patch("keyhole_cli.profile._detect_os_family", return_value="linux")
    @patch("keyhole_cli.profile._detect_wsl", return_value=True)
    @patch("keyhole_cli.profile._detect_shell", return_value="bash")
    @patch("keyhole_cli.profile._check_docker", return_value=True)
    @patch("keyhole_cli.profile._check_compose", return_value=True)
    def test_wsl_profile_supported(self, *_: Any) -> None:
        r = detect_profile()
        assert r.detected_profile == "wsl"
        assert r.supported is True

    @patch("keyhole_cli.profile._detect_os_family", return_value="linux")
    @patch("keyhole_cli.profile._detect_wsl", return_value=False)
    @patch("keyhole_cli.profile._detect_shell", return_value="bash")
    @patch("keyhole_cli.profile._check_docker", return_value=False)
    @patch("keyhole_cli.profile._check_compose", return_value=False)
    def test_missing_docker_fails_check(self, *_: Any) -> None:
        r = detect_profile()
        assert "docker_available" in r.failed_checks
        assert "compose_available" in r.failed_checks

    @patch("keyhole_cli.profile._detect_os_family", return_value="macos")
    @patch("keyhole_cli.profile._detect_shell", return_value="zsh")
    @patch("keyhole_cli.profile._check_docker", return_value=True)
    @patch("keyhole_cli.profile._check_compose", return_value=True)
    def test_unsupported_macos_profile(self, *_: Any) -> None:
        r = detect_profile()
        assert r.detected_profile == "macos"
        assert r.supported is False
        assert "os_supported" in r.failed_checks


# --------------------------------------------------------------
# S41-02-INV-01 - Doctor command
# --------------------------------------------------------------

class TestDoctorCommand:

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    @patch("keyhole_cli.commands.doctor.detect_profile")
    def test_doctor_success(self, mock_detect: MagicMock, mock_facts: MagicMock) -> None:
        mock_detect.return_value = ProfileResult(
            supported=True,
            detected_profile="linux",
            os_family="linux",
            shell="bash",
            is_wsl=False,
            docker_available=True,
            compose_available=True,
            required_checks=["os_supported", "docker_available", "compose_available"],
            failed_checks=[],
        )
        mock_facts.return_value = EnvironmentFacts(
            platform=sys.platform,
            python_available=True,
            python_version=platform.python_version(),
            python_version_tuple=tuple(sys.version_info[:3]),
            docker_available=True,
            docker_version="Docker 25.0.0",
            compose_available=True,
            compose_version="Docker Compose v2.0.0",
            cli_installed=True,
            cli_version="test",
            sdk_installed=True,
            sdk_version="test",
            os_family="linux",
            shell="bash",
        )
        result = run_doctor()
        assert result.success is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.data["supported"] is True
        assert result.data["detected_profile"] == "linux"

    @patch("keyhole_cli.commands.doctor.detect_profile")
    def test_doctor_unsupported(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = ProfileResult(
            supported=False,
            detected_profile="macos",
            os_family="macos",
            shell="zsh",
            is_wsl=False,
            docker_available=True,
            compose_available=True,
            required_checks=["os_supported"],
            failed_checks=["os_supported"],
            next_steps=["Unsupported"],
        )
        result = run_doctor()
        assert result.success is False
        assert result.exit_code == EXIT_UNSUPPORTED

    def test_doctor_json_contract(self) -> None:
        """Doctor JSON output must include minimum required keys."""
        result = run_doctor()
        d = result.to_dict()
        required_keys = {
            "command", "success", "supported", "detected_profile",
            "required_checks", "failed_checks", "timestamp",
        }
        assert required_keys.issubset(d.keys()), f"Missing: {required_keys - d.keys()}"


# --------------------------------------------------------------
# S41-02: Init command
# --------------------------------------------------------------

class TestInitCommand:

    def test_init_creates_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_init(directory=tmpdir)
            assert result.success is True
            assert result.exit_code == EXIT_SUCCESS
            assert result.data["initialized"] is True
            assert "docker-compose.yml" in result.data["created_paths"]
            assert (Path(tmpdir) / "docker-compose.yml").exists()

    def test_init_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            r1 = run_init(directory=tmpdir)
            r2 = run_init(directory=tmpdir)
            assert r2.success is True
            # Second run should skip already-existing files
            assert len(r2.data["skipped_paths"]) > 0
            assert len(r2.data["created_paths"]) == 0

    def test_init_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_init(directory=tmpdir)
            d = result.to_dict()
            required_keys = {
                "command", "success", "initialized",
                "created_paths", "skipped_paths", "timestamp",
            }
            assert required_keys.issubset(d.keys())


# --------------------------------------------------------------
# S41-02-INV-05 - Runtime lifecycle truthfulness
# --------------------------------------------------------------

class TestRuntimeLifecycle:

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=False)
    @patch("keyhole_cli.commands.runtime._is_compose_running", return_value=False)
    def test_status_unreachable(self, *_: Any) -> None:
        result = run_status(endpoint="http://localhost:9999")
        assert result.data["reachable"] is False
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.runtime._query_identity", return_value={
        "name": "test-runtime", "version": "0.1.0", "environment": "local",
        "capabilities": ["realize"],
    })
    def test_status_reachable(self, *_: Any) -> None:
        result = run_status(endpoint="http://localhost:8080")
        assert result.data["reachable"] is True
        assert result.data["runtime_name"] == "test-runtime"
        assert result.data["mode_truth_source"] == "identity_endpoint"
        assert result.exit_code == EXIT_SUCCESS

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.runtime._query_identity", return_value=None)
    def test_status_reachable_no_identity(self, *_: Any) -> None:
        result = run_status(endpoint="http://localhost:8080")
        assert result.data["reachable"] is True
        assert result.data["mode_truth_source"] == "healthz_only"

    @patch("keyhole_cli.commands.runtime._is_compose_running", return_value=False)
    def test_stop_already_stopped(self, _: Any) -> None:
        result = run_stop()
        assert result.success is True
        assert result.data["prior_state"] == "stopped"
        assert result.data["runtime_stopped"] is True

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.runtime._query_identity", return_value={
        "name": "test-runtime", "version": "0.1.0", "environment": "local",
    })
    def test_start_already_running(self, *_: Any) -> None:
        result = run_start(endpoint="http://localhost:8080")
        assert result.success is True
        assert result.data["already_running"] is True

    def test_status_json_contract(self) -> None:
        with patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=False):
            result = run_status(endpoint="http://localhost:9999")
            d = result.to_dict()
            required = {
                "command", "success", "reachable", "runtime_name",
                "runtime_version", "runtime_environment",
                "capabilities", "mode_truth_source", "timestamp",
            }
            assert required.issubset(d.keys()), f"Missing: {required - d.keys()}"

    def test_stop_json_contract(self) -> None:
        with patch("keyhole_cli.commands.runtime._is_compose_running", return_value=False):
            result = run_stop()
            d = result.to_dict()
            required = {
                "command", "success", "runtime_stopped",
                "prior_state", "current_state", "timestamp",
            }
            assert required.issubset(d.keys())

    def test_start_json_contract(self) -> None:
        with patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True):
            with patch("keyhole_cli.commands.runtime._query_identity", return_value={
                "name": "rt", "version": "1", "environment": "local",
            }):
                result = run_start(endpoint="http://localhost:8080")
                d = result.to_dict()
                required = {
                    "command", "success", "runtime_started",
                    "runtime_name", "runtime_endpoint", "health_status",
                    "detected_mode", "timestamp",
                }
                assert required.issubset(d.keys())


# --------------------------------------------------------------
# S41-02-INV-07 - Public/private boundary
# --------------------------------------------------------------

class TestPublicPrivateBoundary:
    """CLI output must never leak private governance/control-plane data."""

    FORBIDDEN_KEYS = {
        "pointer_state", "promotion_state", "canonical_digest",
        "cluster_topology", "internal_lane", "controller_state",
        "governance_verdict", "drift_state",
    }

    def _assert_no_forbidden(self, d: Dict[str, Any]) -> None:
        for key in self.FORBIDDEN_KEYS:
            assert key not in d, f"Forbidden private field '{key}' leaked into output"
            for v in d.values():
                if isinstance(v, dict):
                    assert key not in v, f"Forbidden '{key}' in nested output"

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.runtime._query_identity", return_value={
        "name": "test-runtime", "version": "0.1.0", "environment": "local",
        "capabilities": ["realize"],
        # inject forbidden fields to ensure they are stripped
        "pointer_state": "active",
        "canonical_digest": "sha256:secret",
        "governance_verdict": "ACCEPT",
    })
    def test_status_strips_private_fields(self, *_: Any) -> None:
        result = run_status(endpoint="http://localhost:8080")
        self._assert_no_forbidden(result.to_dict())

    def test_doctor_no_private_fields(self) -> None:
        result = run_doctor()
        self._assert_no_forbidden(result.to_dict())

    def test_init_no_private_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_init(directory=tmpdir)
            self._assert_no_forbidden(result.to_dict())

    def test_private_fields_constant(self) -> None:
        """Verify the forbidden fields set is non-empty and matches."""
        assert len(_PRIVATE_FIELDS) >= 5
        assert "pointer_state" in _PRIVATE_FIELDS
        assert "governance_verdict" in _PRIVATE_FIELDS


# --------------------------------------------------------------
# S41-02-INV-03 - Mode truthfulness
# --------------------------------------------------------------

class TestModeTruthfulness:
    """Runtime mode reporting must be bounded to public truth."""

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.runtime._query_identity", return_value={
        "name": "test-runtime", "version": "0.1.0", "environment": "local",
    })
    def test_mode_from_identity(self, *_: Any) -> None:
        result = run_status(endpoint="http://localhost:8080")
        assert result.data["runtime_environment"] == "local"
        assert result.data["mode_truth_source"] == "identity_endpoint"

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=False)
    def test_mode_unknown_when_unreachable(self, _: Any) -> None:
        result = run_status(endpoint="http://localhost:9999")
        assert result.data["runtime_environment"] == "unknown"
        assert result.data["mode_truth_source"] == "none"


# --------------------------------------------------------------
# S41-02-INV-04 - JSON contract stability
# --------------------------------------------------------------

class TestJsonContract:
    """All first-success commands must have stable JSON output."""

    def test_result_to_dict_always_has_timestamp(self) -> None:
        r = CommandResult(command="test", success=True)
        d = r.to_dict()
        assert "timestamp" in d
        assert "command" in d
        assert "success" in d

    def test_result_to_dict_includes_data(self) -> None:
        r = CommandResult(command="test", success=True, data={"foo": "bar"})
        d = r.to_dict()
        assert d["foo"] == "bar"

    def test_result_json_serializable(self) -> None:
        r = CommandResult(
            command="test", success=True,
            data={"list": [1, 2], "nested": {"a": True}},
            warnings=["w1"], next_steps=["s1"],
        )
        serialized = json.dumps(r.to_dict())
        parsed = json.loads(serialized)
        assert parsed["command"] == "test"
        assert parsed["success"] is True


# --------------------------------------------------------------
# S41-02: Exit code semantics
# --------------------------------------------------------------

class TestExitCodes:
    """Exit codes must be deterministic and documented."""

    def test_exit_code_values(self) -> None:
        assert EXIT_SUCCESS == 0
        assert EXIT_FAILURE == 1
        assert EXIT_UNSUPPORTED == 2
        assert EXIT_RUNTIME_UNAVAILABLE == 3
        assert EXIT_INVALID_INPUT == 4
        assert EXIT_CONTRACT_FAILURE == 5

    @patch("keyhole_cli.commands.doctor.detect_profile")
    def test_doctor_exit_unsupported(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = ProfileResult(
            supported=False,
            detected_profile="unsupported",
            os_family="weird",
            shell="unknown",
            is_wsl=False,
            docker_available=False,
            compose_available=False,
            required_checks=["os_supported"],
            failed_checks=["os_supported"],
        )
        result = run_doctor()
        assert result.exit_code == EXIT_UNSUPPORTED

    @patch("keyhole_cli.commands.runtime._runtime_reachable", return_value=False)
    def test_status_exit_runtime_unavailable(self, _: Any) -> None:
        result = run_status(endpoint="http://localhost:9999")
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE


# --------------------------------------------------------------
# S41-02-INV-08 - Unsupported environment truthfulness
# --------------------------------------------------------------

class TestUnsupportedEnvironment:

    @patch("keyhole_cli.commands.doctor.detect_profile")
    def test_unsupported_env_clear_failure(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = ProfileResult(
            supported=False,
            detected_profile="macos",
            os_family="macos",
            shell="zsh",
            is_wsl=False,
            docker_available=True,
            compose_available=True,
            required_checks=["os_supported"],
            failed_checks=["os_supported"],
            next_steps=["Use a supported profile."],
        )
        result = run_doctor()
        assert result.success is False
        assert result.data["supported"] is False
        assert "os_supported" in result.data["failed_checks"]
        assert len(result.next_steps) > 0


# --------------------------------------------------------------
# S41-02: Smoke command
# --------------------------------------------------------------

class TestSmokeCommand:

    @patch("keyhole_cli.commands.smoke.run_doctor")
    def test_smoke_fails_on_unsupported_env(self, mock_doctor: MagicMock) -> None:
        mock_doctor.return_value = CommandResult(
            command="doctor", success=False, exit_code=EXIT_UNSUPPORTED,
            data={"detected_profile": "macos", "supported": False},
        )
        result = run_smoke(endpoint="http://localhost:8080")
        assert result.success is False
        assert result.data["first_success"] is False
        assert result.data["doctor_result"] == "fail"
        assert result.exit_code == EXIT_UNSUPPORTED

    @patch("keyhole_cli.commands.smoke.run_doctor")
    @patch("keyhole_cli.commands.smoke._runtime_reachable", return_value=False)
    def test_smoke_fails_on_unreachable(
        self, _mock_reach: Any, mock_doctor: MagicMock
    ) -> None:
        mock_doctor.return_value = CommandResult(
            command="doctor", success=True, exit_code=EXIT_SUCCESS,
            data={"detected_profile": "linux", "supported": True},
        )
        result = run_smoke(endpoint="http://localhost:9999")
        assert result.success is False
        assert result.data["runtime_result"] == "unreachable"
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE

    @patch("keyhole_cli.commands.smoke.run_doctor")
    @patch("keyhole_cli.commands.smoke._runtime_reachable", return_value=True)
    @patch("keyhole_cli.commands.smoke._query_identity", return_value={
        "name": "test-runtime", "version": "0.1.0", "environment": "local",
    })
    @patch("requests.get")
    def test_smoke_full_success(
        self, mock_get: MagicMock, *_: Any
    ) -> None:
        # Mock doctor
        _[1].return_value = CommandResult(
            command="doctor", success=True, exit_code=EXIT_SUCCESS,
            data={"detected_profile": "linux", "supported": True},
        )
        # Mock healthz OK
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = run_smoke(endpoint="http://localhost:8080")
        assert result.success is True
        assert result.data["first_success"] is True
        assert result.data["doctor_result"] == "pass"
        assert result.data["runtime_result"] == "reachable"
        assert result.data["identity_result"] == "pass"
        assert result.data["smoke_action_result"] == "pass"
        assert result.exit_code == EXIT_SUCCESS

    def test_smoke_json_contract(self) -> None:
        """Smoke JSON output must include minimum required keys."""
        with patch("keyhole_cli.commands.smoke.run_doctor") as md:
            md.return_value = CommandResult(
                command="doctor", success=False, exit_code=EXIT_UNSUPPORTED,
                data={"detected_profile": "unknown", "supported": False},
            )
            result = run_smoke(endpoint="http://localhost:9999")
            d = result.to_dict()
            required = {
                "command", "success", "first_success", "profile",
                "doctor_result", "runtime_result", "identity_result",
                "smoke_action_result", "timestamp",
            }
            assert required.issubset(d.keys()), f"Missing: {required - d.keys()}"
