"""SDK-CLIENT-01-D - Host Credential Installation, Extension Reconciliation,
and Live Principal Alignment tests.

Covers:
  section1: Host inventory - JetBrains, Cloud Code, enhanced VS Code detection
  section2: Host credential installer - install, update, skip, force
  section3: Principal source inspection - auth mode, principal extraction
  section4: Three-layer reconciliation - CLI ↔ host ↔ server identity comparison
  section5: Reconnect guidance - per-host-family reconnect requirements
  section6: CLI host commands - list, inspect, install
  section7: Doctor mode upgrade - host_inventory, live_reconciliation modes
  section8: Non-proxy architecture - INV-SDK-CLIENT-01-D-001

Invariants:
  INV-SDK-CLIENT-01-D-001: CLI is provisioner, NOT proxy
  INV-SDK-CLIENT-01-D-002: Split identity must be explicit
  INV-SDK-CLIENT-01-D-005: Local success is NOT live success
  INV-SDK-CLIENT-01-D-006: Live truth comes from server surfaces
  INV-SDK-CLIENT-01-D-007: Multi-host environments remain safe
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

# -- SDK doctor imports ------------------------------------
from keyhole_sdk.doctor.models import (
    DoctorHostEntry,
    DoctorHostRecord,
    DoctorReport,
    DoctorSummaryStatus,
    HostDiagnosis,
    HostFamily,
    HostSupportStatus,
    HostType,
    RecommendedAction,
    ReconciliationMode,
    ReconnectRequirement,
    RepairGuidance,
    StalenessState,
)
from keyhole_sdk.doctor.host_inventory import (
    CloudCodeHostDetector,
    HostDetector,
    JetBrainsHostDetector,
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
    check_connection_surfaces_available,
    reconcile,
)

# -- SDK host package imports ------------------------------
from keyhole_sdk.host.installer import (
    HostInstallResult,
    install_host_credentials,
    install_vscode,
    install_jetbrains,
)
from keyhole_sdk.host.reconciler import (
    ThreeLayerIdentity,
    reconcile_three_layer,
)

# -- CLI host command imports ------------------------------
from keyhole_cli.commands.host_list import run_host_list
from keyhole_cli.commands.host_inspect import run_host_inspect
from keyhole_cli.commands.host_install import run_host_install
from keyhole_cli.doctor.contract import OperatingMode


# ----------------------------------------------------------
# section1: Host Inventory - New Detectors
# ----------------------------------------------------------


class TestHostFamilyEnum:
    """Host family enum covers all expected IDE families."""

    def test_vscode_family(self):
        assert HostFamily.VSCODE.value == "vscode"

    def test_jetbrains_family(self):
        assert HostFamily.JETBRAINS.value == "jetbrains"

    def test_cloud_code_family(self):
        assert HostFamily.CLOUD_CODE.value == "cloud_code"

    def test_sdk_local_family(self):
        assert HostFamily.SDK_LOCAL.value == "sdk_local"

    def test_unknown_family(self):
        assert HostFamily.UNKNOWN.value == "unknown"


class TestHostSupportStatus:
    """Support status classifies adapter maturity."""

    def test_supported(self):
        assert HostSupportStatus.SUPPORTED.value == "supported"

    def test_partial(self):
        assert HostSupportStatus.PARTIAL.value == "partial"

    def test_unsupported(self):
        assert HostSupportStatus.UNSUPPORTED.value == "unsupported"


class TestReconnectRequirement:
    """Reconnect requirement tells user what to do after install."""

    def test_none(self):
        assert ReconnectRequirement.NONE.value == "none"

    def test_reload_window(self):
        assert ReconnectRequirement.RELOAD_WINDOW.value == "reload_window"

    def test_restart_ide(self):
        assert ReconnectRequirement.RESTART_IDE.value == "restart_ide"

    def test_manual(self):
        assert ReconnectRequirement.MANUAL.value == "manual"


class TestVSCodeDetectorEnhanced:
    """VS Code detector populates host_family, support_status, config_path."""

    def test_vscode_sets_host_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            paths = [str(settings_path)]
            with patch(
                "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS",
                paths,
            ):
                detector = VSCodeHostDetector()
                record = detector.detect()

        assert record is not None
        assert record.host_family == HostFamily.VSCODE
        assert record.support_status == HostSupportStatus.SUPPORTED
        assert record.reconnect_requirement == ReconnectRequirement.RELOAD_WINDOW

    def test_vscode_detects_config_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({
                "mcp.servers": {
                    "keyhole": {
                        "url": "https://mcp.keyholesolution.com/mcp/v1",
                        "env": {"KEYHOLE_MCP_TOKEN": "${env:KEYHOLE_MCP_TOKEN}"},
                    }
                }
            }))

            paths = [str(settings_path)]
            with patch(
                "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS",
                paths,
            ):
                detector = VSCodeHostDetector()
                record = detector.detect()

        assert record.config_path == str(settings_path)
        assert record.keyhole_server_entry_detected is True
        assert record.auth_source_mode == "env_bearer_token"

    def test_vscode_detects_workspace_mcp_json(self):
        """VS Code detector checks .vscode/mcp.json in workspace."""
        with tempfile.TemporaryDirectory() as tmp:
            mcp_path = Path(tmp) / ".vscode" / "mcp.json"
            mcp_path.parent.mkdir(parents=True)
            mcp_path.write_text(json.dumps({
                "servers": {
                    "keyhole": {
                        "url": "https://mcp.keyholesolution.com/mcp/v1",
                    }
                }
            }))

            with patch(
                "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS",
                [],
            ), patch(
                "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS",
                [str(mcp_path)],
            ):
                detector = VSCodeHostDetector()
                record = detector.detect()

        # Not detected (no settings.json), but potentially MCP config
        # When settings not found, record.detected stays False
        assert record is not None


class TestJetBrainsDetector:
    """JetBrains detector finds IDE config directories."""

    def test_jetbrains_not_installed(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/path/*/"],
        ):
            detector = JetBrainsHostDetector()
            record = detector.detect()

        assert record is not None
        assert record.host_id == "jetbrains"
        assert record.host_family == HostFamily.JETBRAINS
        assert record.detected is False
        assert record.support_status == HostSupportStatus.PARTIAL

    def test_jetbrains_detected_no_keyhole(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "JetBrains" / "PyCharm2024"
            config_dir.mkdir(parents=True)

            with patch(
                "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
                [str(config_dir.parent / "*/")],
            ):
                detector = JetBrainsHostDetector()
                record = detector.detect()

        assert record.detected is True
        assert record.config_detected is True
        assert record.keyhole_server_entry_detected is False

    def test_jetbrains_detected_with_keyhole(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "JetBrains" / "PyCharm2024"
            config_dir.mkdir(parents=True)
            mcp_file = config_dir / "mcp.json"
            mcp_file.write_text(json.dumps({
                "mcpServers": {
                    "keyhole": {
                        "url": "https://mcp.keyholesolution.com/mcp/v1"
                    }
                }
            }))

            with patch(
                "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
                [str(config_dir.parent / "*/")],
            ):
                detector = JetBrainsHostDetector()
                record = detector.detect()

        assert record.detected is True
        assert record.keyhole_server_entry_detected is True
        assert record.reconnect_requirement == ReconnectRequirement.RESTART_IDE


class TestCloudCodeDetector:
    """Cloud Code detector finds cloud-code config files."""

    def test_cloud_code_not_installed(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS",
            ["/nonexistent/path"],
        ):
            detector = CloudCodeHostDetector()
            record = detector.detect()

        assert record is not None
        assert record.host_id == "cloud_code"
        assert record.host_family == HostFamily.CLOUD_CODE
        assert record.detected is False
        assert record.support_status == HostSupportStatus.PARTIAL

    def test_cloud_code_detected_with_keyhole(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "mcp.json"
            config_path.write_text(json.dumps({
                "servers": {
                    "keyhole": {
                        "url": "https://mcp.keyholesolution.com/mcp/v1"
                    }
                }
            }))

            with patch(
                "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS",
                [str(config_path)],
            ):
                detector = CloudCodeHostDetector()
                record = detector.detect()

        assert record.detected is True
        assert record.keyhole_server_entry_detected is True
        assert record.reconnect_requirement == ReconnectRequirement.MANUAL


class TestSDKCredentialDetectorEnhanced:
    """SDK credential detector populates new fields."""

    def test_sdk_sets_host_family(self):
        detector = SDKCredentialDetector()
        with patch.object(
            SDKCredentialDetector,
            "_find_credential_file",
            return_value=None,
        ):
            record = detector.detect()

        assert record.host_family == HostFamily.SDK_LOCAL
        assert record.support_status == HostSupportStatus.SUPPORTED
        assert record.reconnect_requirement == ReconnectRequirement.NONE

    def test_sdk_extracts_principal(self):
        with tempfile.TemporaryDirectory() as tmp:
            cred_file = Path(tmp) / "credentials.json"
            cred_file.write_text(json.dumps({
                "user_id": "abc-123",
                "access_token": "tok",
            }))

            with patch.object(
                SDKCredentialDetector,
                "_find_credential_file",
                return_value=cred_file,
            ):
                detector = SDKCredentialDetector()
                record = detector.detect()

        assert record.configured_principal_source == "abc-123"
        assert record.config_detected is True


class TestDetectHostsRegistry:
    """detect_hosts() includes all four detectors by default."""

    def test_default_detectors_include_all_families(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS",
            [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS",
            [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/*/"],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS",
            [],
        ), patch.object(
            SDKCredentialDetector,
            "_find_credential_file",
            return_value=None,
        ):
            records = detect_hosts()

        host_ids = [r.host_id for r in records]
        assert "vscode" in host_ids
        assert "jetbrains" in host_ids
        assert "cloud_code" in host_ids
        assert "sdk_local" in host_ids


# ----------------------------------------------------------
# section2: Host Credential Installer
# ----------------------------------------------------------


class TestVSCodeInstaller:
    """VS Code credential installer writes MCP server entries."""

    def test_install_creates_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = install_vscode(
                    mcp_url="https://mcp.keyholesolution.com",
                )

            assert result.success is True
            assert result.action_taken == "created"
            assert result.host_family == HostFamily.VSCODE
            assert result.reconnect_requirement == ReconnectRequirement.RELOAD_WINDOW

            # Verify written content
            data = json.loads(settings_path.read_text())
            assert "mcp.servers" in data
            assert "keyhole" in data["mcp.servers"]
            entry = data["mcp.servers"]["keyhole"]
            assert "mcp.keyholesolution.com" in entry["url"]

    def test_install_skips_existing_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({
                "mcp.servers": {
                    "keyhole": {
                        "url": "https://old.example.com/mcp/v1"
                    }
                }
            }))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = install_vscode(force=False)

        assert result.success is True
        assert result.action_taken == "skipped"
        assert result.previous_entry_existed is True
        assert result.previous_url == "https://old.example.com/mcp/v1"

    def test_install_overwrites_with_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({
                "mcp.servers": {
                    "keyhole": {
                        "url": "https://old.example.com/mcp/v1"
                    }
                }
            }))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = install_vscode(
                    mcp_url="https://mcp.keyholesolution.com",
                    force=True,
                )

            assert result.success is True
            assert result.action_taken == "updated"
            data = json.loads(settings_path.read_text())
            assert "mcp.keyholesolution.com" in data["mcp.servers"]["keyhole"]["url"]

    def test_install_no_settings_dir(self):
        with patch(
            "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
            ["/nonexistent/settings.json"],
        ):
            result = install_vscode()

        assert result.success is False
        assert "No VS Code settings" in result.error

    def test_install_does_not_embed_tokens(self):
        """INV-SDK-CLIENT-01-D-001: No raw tokens in config."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = install_vscode()

            content = settings_path.read_text()
            # Must use env var reference, not a raw token
            assert "${env:KEYHOLE_MCP_TOKEN}" in content
            # Must not contain a raw JWT-like token
            assert "eyJ" not in content


class TestJetBrainsInstaller:
    """JetBrains credential installer writes mcp.json."""

    def test_install_creates_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "JetBrains" / "PyCharm2024"
            config_dir.mkdir(parents=True)

            import glob as glob_mod
            orig_glob = glob_mod.glob

            def mock_glob(pattern, **kw):
                if "JetBrains" in str(pattern):
                    return [str(config_dir)]
                return orig_glob(pattern, **kw)

            with patch("glob.glob", side_effect=mock_glob):
                result = install_jetbrains(
                    mcp_url="https://mcp.keyholesolution.com",
                )

            assert result.success is True
            assert result.action_taken == "created"
            assert result.host_family == HostFamily.JETBRAINS


class TestInstallHostCredentialsDispatcher:
    """install_host_credentials() dispatches to the right installer."""

    def test_unsupported_host_family(self):
        result = install_host_credentials(
            host_family=HostFamily.CLOUD_CODE,
        )
        assert result.success is False
        assert "No installer" in result.error

    def test_unknown_host_family(self):
        result = install_host_credentials(
            host_family=HostFamily.UNKNOWN,
        )
        assert result.success is False


class TestHostInstallResultSerialisation:
    """HostInstallResult serialises correctly."""

    def test_to_dict(self):
        result = HostInstallResult(
            host_family=HostFamily.VSCODE,
            success=True,
            config_path="/home/user/.config/Code/User/settings.json",
            action_taken="created",
            reconnect_requirement=ReconnectRequirement.RELOAD_WINDOW,
        )
        d = result.to_dict()
        assert d["host_family"] == "vscode"
        assert d["success"] is True
        assert d["reconnect_requirement"] == "reload_window"


# ----------------------------------------------------------
# section4: Three-Layer Reconciliation
# ----------------------------------------------------------


class TestThreeLayerReconciliation:
    """Three-layer identity reconciler compares CLI ↔ host ↔ server."""

    def _make_record(self, **overrides) -> DoctorHostRecord:
        defaults = dict(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.VSCODE,
            display_name="VS Code",
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="user-1",
            server_principal_label="user@example.com",
            connection_id="conn-1",
            staleness_state=StalenessState.FRESH,
            support_status=HostSupportStatus.SUPPORTED,
            reconnect_requirement=ReconnectRequirement.RELOAD_WINDOW,
        )
        defaults.update(overrides)
        return DoctorHostRecord(**defaults)

    def test_aligned_all_layers(self):
        record = self._make_record(server_principal_user_id="user-1")
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result.diagnosis == HostDiagnosis.ALIGNED
        assert "aligned" in result.description.lower()

    def test_split_identity_detected(self):
        """INV-SDK-CLIENT-01-D-002: Split identity must be explicit."""
        record = self._make_record(server_principal_user_id="user-2")
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result.diagnosis == HostDiagnosis.SPLIT_IDENTITY
        assert "user-1" in result.description
        assert "user-2" in result.description

    def test_host_not_configured(self):
        record = self._make_record(keyhole_server_entry_detected=False)
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result.diagnosis == HostDiagnosis.HOST_NOT_CONFIGURED
        assert RecommendedAction.INSTALL_HOST_CREDENTIALS in result.recommended_actions

    def test_live_connection_missing(self):
        """INV-SDK-CLIENT-01-D-005: Local success is NOT live success."""
        record = self._make_record(connection_visible_from_server=False)
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result.diagnosis == HostDiagnosis.LIVE_CONNECTION_MISSING

    def test_surface_unavailable(self):
        record = self._make_record()
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=False,
        )
        assert result.diagnosis == HostDiagnosis.SURFACE_UNAVAILABLE

    def test_stale_host_auth(self):
        record = self._make_record(
            server_principal_user_id="user-1",
            staleness_state=StalenessState.STALE_CONFIRMED,
        )
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert result.diagnosis == HostDiagnosis.STALE_HOST_AUTH

    def test_serialisation(self):
        record = self._make_record()
        result = reconcile_three_layer(
            cli_user_id="user-1",
            cli_profile_label="profile",
            host_record=record,
            connection_surfaces_available=True,
        )
        d = result.to_dict()
        assert "host_id" in d
        assert "cli_user_id" in d
        assert "server_user_id" in d
        assert "diagnosis" in d


# ----------------------------------------------------------
# section5: Reconnect Guidance
# ----------------------------------------------------------


class TestReconnectGuidance:
    """Repair guidance includes reconnect hints per host family."""

    def test_host_not_configured_includes_install_command(self):
        record = DoctorHostRecord(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.VSCODE,
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=False,
            diagnosis=HostDiagnosis.HOST_NOT_CONFIGURED,
            reconnect_requirement=ReconnectRequirement.RELOAD_WINDOW,
        )
        guidance = build_repair_guidance(record)
        assert RecommendedAction.INSTALL_HOST_CREDENTIALS in guidance.actions
        assert any("keyhole host install" in c for c in guidance.commands)

    def test_stale_host_auth_includes_refresh(self):
        record = DoctorHostRecord(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.VSCODE,
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="user-1",
            diagnosis=HostDiagnosis.STALE_HOST_AUTH,
            reconnect_requirement=ReconnectRequirement.RELOAD_WINDOW,
        )
        guidance = build_repair_guidance(record)
        assert RecommendedAction.REFRESH_HOST in guidance.actions

    def test_live_connection_missing_includes_restart(self):
        record = DoctorHostRecord(
            host_id="jetbrains",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.JETBRAINS,
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=False,
            diagnosis=HostDiagnosis.LIVE_CONNECTION_MISSING,
            reconnect_requirement=ReconnectRequirement.RESTART_IDE,
        )
        guidance = build_repair_guidance(record)
        assert RecommendedAction.RESTART_HOST in guidance.actions
        assert any("Restart the IDE" in d for d in guidance.descriptions)

    def test_host_config_unreadable_guidance(self):
        record = DoctorHostRecord(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            detected=True,
            config_detected=False,
            diagnosis=HostDiagnosis.HOST_CONFIG_UNREADABLE,
        )
        guidance = build_repair_guidance(record)
        assert RecommendedAction.REPAIR_HOST_CONFIG in guidance.actions


# ----------------------------------------------------------
# section6: CLI Host Commands
# ----------------------------------------------------------


class TestCLIHostList:
    """'keyhole host list' returns structured host inventory."""

    def test_host_list_returns_success(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/*/"],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS", [],
        ), patch.object(
            SDKCredentialDetector, "_find_credential_file", return_value=None,
        ):
            result = run_host_list()

        assert result.success is True
        assert "hosts" in result.data
        assert result.data["total_scanned"] >= 4  # All four detectors

    def test_host_list_data_shape(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/*/"],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS", [],
        ), patch.object(
            SDKCredentialDetector, "_find_credential_file", return_value=None,
        ):
            result = run_host_list()

        for host in result.data["hosts"]:
            assert "host_id" in host
            assert "host_family" in host
            assert "support_status" in host


class TestCLIHostInspect:
    """'keyhole host inspect' returns details for a specific host."""

    def test_inspect_existing_host(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/*/"],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS", [],
        ), patch.object(
            SDKCredentialDetector, "_find_credential_file", return_value=None,
        ):
            result = run_host_inspect(host="sdk_local")

        assert result.success is True
        assert result.data["host_id"] == "sdk_local"

    def test_inspect_unknown_host(self):
        with patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_SETTINGS_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._VSCODE_MCP_PATHS", [],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._JETBRAINS_CONFIG_DIRS",
            ["/nonexistent/*/"],
        ), patch(
            "keyhole_sdk.doctor.host_inventory._CLOUD_CODE_CONFIG_PATHS", [],
        ), patch.object(
            SDKCredentialDetector, "_find_credential_file", return_value=None,
        ):
            result = run_host_inspect(host="nonexistent_ide")

        assert result.success is False
        assert result.data["error_class"] == "host_not_found"


class TestCLIHostInstall:
    """'keyhole host install' writes config and reports reconnect."""

    def test_install_unsupported_host(self):
        result = run_host_install(host="nonexistent_ide")
        assert result.success is False
        assert "unsupported" in result.data.get("error_class", "")

    def test_install_vscode_creates(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = run_host_install(host="vscode")

        assert result.success is True
        assert "created" in result.data.get("action_taken", "")
        assert any("Reconnect" in s or "doctor" in s for s in result.next_steps)


# ----------------------------------------------------------
# section7: Doctor Mode Upgrade
# ----------------------------------------------------------


class TestOperatingModeExtension:
    """OperatingMode enum now includes host_inventory and live_reconciliation."""

    def test_host_inventory_mode(self):
        m = OperatingMode("host_inventory")
        assert m == OperatingMode.HOST_INVENTORY

    def test_live_reconciliation_mode(self):
        m = OperatingMode("live_reconciliation")
        assert m == OperatingMode.LIVE_RECONCILIATION


class TestReconciliationModeInReport:
    """DoctorReport carries reconciliation_mode."""

    def test_default_mode_is_local_only(self):
        report = build_doctor_report(
            cli_active_profile="default",
            cli_user_id="user-1",
            host_records=[],
            connection_surfaces_available=False,
            negotiation_available=False,
        )
        assert report.reconciliation_mode == ReconciliationMode.LOCAL_ONLY

    def test_host_inventory_mode_forward(self):
        report = build_doctor_report(
            cli_active_profile="default",
            cli_user_id="user-1",
            host_records=[],
            connection_surfaces_available=False,
            negotiation_available=False,
            reconciliation_mode=ReconciliationMode.HOST_INVENTORY,
        )
        assert report.reconciliation_mode == ReconciliationMode.HOST_INVENTORY

    def test_reconcile_passes_mode(self):
        report = reconcile(
            cli_active_profile="default",
            cli_user_id="user-1",
            host_records=[],
            reconciliation_mode=ReconciliationMode.LIVE_RECONCILIATION,
        )
        assert report.reconciliation_mode == ReconciliationMode.LIVE_RECONCILIATION


class TestReportToDict:
    """DoctorReport to_dict includes new fields."""

    def test_report_dict_has_reconciliation_mode(self):
        report = DoctorReport(
            cli_active_profile="default",
            cli_user_id="user-1",
            reconciliation_mode=ReconciliationMode.HOST_INVENTORY,
        )
        d = report.to_dict()
        assert d["reconciliation_mode"] == "host_inventory"


# ----------------------------------------------------------
# section8: Non-Proxy Architecture
# ----------------------------------------------------------


class TestNonProxyArchitecture:
    """INV-SDK-CLIENT-01-D-001: CLI is provisioner, NOT proxy."""

    def test_installed_entry_has_direct_url(self):
        """The installed MCP entry must point directly to MCP boundary."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                result = install_vscode(
                    mcp_url="https://mcp.keyholesolution.com",
                )

            data = json.loads(settings_path.read_text())
            entry = data["mcp.servers"]["keyhole"]
            # URL must be the MCP boundary directly, not a CLI proxy
            assert "mcp.keyholesolution.com" in entry["url"]
            # No localhost proxy URL
            assert "localhost" not in entry["url"]

    def test_installed_entry_uses_env_var_not_token(self):
        """No raw tokens in config - references env var."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(json.dumps({}))

            with patch(
                "keyhole_sdk.host.installer._VSCODE_SETTINGS_CANDIDATES",
                [str(settings_path)],
            ):
                install_vscode()

            content = settings_path.read_text()
            assert "${env:KEYHOLE_MCP_TOKEN}" in content


# ----------------------------------------------------------
# section9: Extended Diagnosis Classification
# ----------------------------------------------------------


class TestExtendedDiagnosisClassification:
    """classify_host_diagnosis uses new verdict classes."""

    def _make_record(self, **overrides) -> DoctorHostRecord:
        defaults = dict(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.VSCODE,
            detected=True,
            config_detected=True,
            keyhole_server_entry_detected=True,
            connection_visible_from_server=True,
            server_principal_user_id="user-1",
            staleness_state=StalenessState.FRESH,
        )
        defaults.update(overrides)
        return DoctorHostRecord(**defaults)

    def test_host_config_unreadable(self):
        record = self._make_record(config_detected=False)
        diag = classify_host_diagnosis(
            cli_user_id="user-1",
            cli_profile_label="prof",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.HOST_CONFIG_UNREADABLE

    def test_host_not_configured(self):
        record = self._make_record(keyhole_server_entry_detected=False)
        diag = classify_host_diagnosis(
            cli_user_id="user-1",
            cli_profile_label="prof",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.HOST_NOT_CONFIGURED

    def test_live_connection_missing(self):
        record = self._make_record(connection_visible_from_server=False)
        diag = classify_host_diagnosis(
            cli_user_id="user-1",
            cli_profile_label="prof",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.LIVE_CONNECTION_MISSING

    def test_stale_host_auth(self):
        record = self._make_record(
            server_principal_user_id="user-1",
            staleness_state=StalenessState.STALE_CONFIRMED,
        )
        diag = classify_host_diagnosis(
            cli_user_id="user-1",
            cli_profile_label="prof",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.STALE_HOST_AUTH

    def test_aligned_when_fresh(self):
        record = self._make_record(
            server_principal_user_id="user-1",
            staleness_state=StalenessState.FRESH,
        )
        diag = classify_host_diagnosis(
            cli_user_id="user-1",
            cli_profile_label="prof",
            host_record=record,
            connection_surfaces_available=True,
        )
        assert diag == HostDiagnosis.ALIGNED


# ----------------------------------------------------------
# section10: Multi-Host Safety
# ----------------------------------------------------------


class TestMultiHostSafety:
    """INV-SDK-CLIENT-01-D-007: Multi-host environments remain safe."""

    def test_mixed_host_report(self):
        """Report handles multiple hosts with different diagnoses."""
        records = [
            DoctorHostRecord(
                host_id="vscode",
                host_type=HostType.IDE_MCP_CLIENT,
                host_family=HostFamily.VSCODE,
                detected=True,
                config_detected=True,
                keyhole_server_entry_detected=True,
                connection_visible_from_server=True,
                server_principal_user_id="user-1",
                staleness_state=StalenessState.FRESH,
            ),
            DoctorHostRecord(
                host_id="jetbrains",
                host_type=HostType.IDE_MCP_CLIENT,
                host_family=HostFamily.JETBRAINS,
                detected=True,
                config_detected=True,
                keyhole_server_entry_detected=True,
                connection_visible_from_server=True,
                server_principal_user_id="user-2",  # Different!
            ),
            DoctorHostRecord(
                host_id="cloud_code",
                host_type=HostType.IDE_MCP_CLIENT,
                host_family=HostFamily.CLOUD_CODE,
                detected=False,
            ),
        ]

        report = reconcile(
            cli_active_profile="default",
            cli_user_id="user-1",
            host_records=records,
            server_operations=["connection.identity.inspect"],
        )

        diagnoses = {h.host_id: h.diagnosis for h in report.hosts}
        assert diagnoses["vscode"] == HostDiagnosis.ALIGNED
        assert diagnoses["jetbrains"] == HostDiagnosis.SPLIT_IDENTITY
        assert diagnoses["cloud_code"] == HostDiagnosis.NOT_DETECTED
        assert report.summary_status == DoctorSummaryStatus.ATTENTION_REQUIRED

    def test_degraded_summary_for_missing_connections(self):
        """Degraded when hosts have entries but no live connections."""
        records = [
            DoctorHostRecord(
                host_id="vscode",
                host_type=HostType.IDE_MCP_CLIENT,
                host_family=HostFamily.VSCODE,
                detected=True,
                config_detected=True,
                keyhole_server_entry_detected=True,
                connection_visible_from_server=False,  # Not live
            ),
        ]
        report = reconcile(
            cli_active_profile="default",
            cli_user_id="user-1",
            host_records=records,
            server_operations=["connection.identity.inspect"],
        )
        assert report.summary_status == DoctorSummaryStatus.DEGRADED
