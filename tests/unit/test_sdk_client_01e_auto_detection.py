"""SDK-CLIENT-01-E - Auto-detection, MCP boundary probing, and provisioning hints.

Tests cover:
  section1  OperatingMode.AUTO enum presence
  section2  MCP boundary probing in fact collection
  section3  Auto-promotion logic in diagnostics
  section4  Runtime checks skip when boundary is live
  section5  MCP config expanded search (VS Code host paths)
  section6  Doctor command surfaces next steps
  section7  Backward compatibility (local_only still works)
  section8  EnvironmentFacts new fields
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

CLI_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-cli"
SDK_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-sdk"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))
if str(SDK_PKG) not in sys.path:
    sys.path.insert(0, str(SDK_PKG))

from keyhole_cli.doctor.contract import (
    CheckStatus,
    EnvironmentFacts,
    OperatingMode,
    ReasonCode,
)
from keyhole_cli.doctor.diagnostics import (
    check_mcp_boundary,
    check_mcp_config,
    check_runtime_reachable,
    check_runtime_running,
    run_diagnostics,
)
from keyhole_cli.doctor.facts import build_facts_from_overrides
from keyhole_cli.commands.doctor import run_doctor


# -- Fixtures --------------------------------------------------


def _base_facts(**overrides: Any) -> EnvironmentFacts:
    defaults = dict(
        platform="linux",
        python_available=True,
        python_version="3.11.5",
        python_version_tuple=(3, 11, 5),
        docker_available=True,
        docker_version="Docker 24",
        compose_available=True,
        compose_version="Compose 2.21",
        cli_installed=True,
        cli_version="0.1.2",
        sdk_installed=True,
        sdk_version="0.1.2",
        runtime_running=False,
        runtime_reachable=False,
        runtime_url="",
        runtime_version="",
        mcp_config_present=False,
        mcp_config_path="",
        mcp_boundary_reachable=False,
        mcp_boundary_url="",
        mcp_contract_version="",
        mcp_operations=[],
        pipx_available=False,
        is_wsl=False,
        os_family="linux",
        shell="bash",
    )
    defaults.update(overrides)
    return build_facts_from_overrides(**defaults)


# --------------------------------------------------------------
# section1 - OperatingMode.AUTO
# --------------------------------------------------------------


class TestOperatingModeAuto:
    def test_auto_enum_exists(self):
        assert OperatingMode.AUTO.value == "auto"

    def test_auto_is_valid_mode(self):
        assert OperatingMode("auto") == OperatingMode.AUTO

    def test_all_modes_present(self):
        values = {m.value for m in OperatingMode}
        assert "auto" in values
        assert "local_only" in values
        assert "governed" in values


# --------------------------------------------------------------
# section2 - MCP boundary probing
# --------------------------------------------------------------


class TestMCPBoundaryCheck:
    def test_boundary_pass_when_reachable(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://mcp.example.com",
            mcp_contract_version="mcp/v1",
        )
        result = check_mcp_boundary(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.PASS.value
        assert "reachable" in result.message.lower()
        assert result.reason_code == ReasonCode.DOCTOR_MCP_BOUNDARY_REACHABLE.value

    def test_boundary_fail_when_unreachable(self):
        facts = _base_facts(mcp_boundary_reachable=False)
        result = check_mcp_boundary(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.FAIL.value
        assert result.reason_code == ReasonCode.DOCTOR_MCP_BOUNDARY_UNREACHABLE.value

    def test_boundary_skip_in_local_only(self):
        facts = _base_facts(mcp_boundary_reachable=True)
        result = check_mcp_boundary(facts, OperatingMode.LOCAL_ONLY)
        assert result.status == CheckStatus.SKIP.value

    def test_boundary_includes_contract_version(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://mcp.example.com",
            mcp_contract_version="mcp/v1",
        )
        result = check_mcp_boundary(facts, OperatingMode.GOVERNED)
        assert "mcp/v1" in result.message


# --------------------------------------------------------------
# section3 - Auto-promotion logic
# --------------------------------------------------------------


class TestAutoPromotion:
    def test_auto_promotes_when_boundary_reachable(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://mcp.example.com",
        )
        diag = run_diagnostics(facts, OperatingMode.AUTO)
        assert diag.requested_mode == "governed"
        assert ReasonCode.DOCTOR_AUTO_PROMOTED_TO_GOVERNED.value in diag.reason_codes

    def test_auto_promotes_when_config_present(self):
        facts = _base_facts(
            mcp_config_present=True,
            mcp_config_path="/home/user/.keyhole/mcp.json",
        )
        diag = run_diagnostics(facts, OperatingMode.AUTO)
        assert diag.requested_mode == "governed"

    def test_auto_falls_back_to_local_when_nothing_found(self):
        facts = _base_facts(
            mcp_boundary_reachable=False,
            mcp_config_present=False,
        )
        diag = run_diagnostics(facts, OperatingMode.AUTO)
        assert diag.requested_mode == "local_only"
        assert ReasonCode.DOCTOR_LOCAL_MODE_READY.value in diag.reason_codes

    def test_auto_promotion_includes_reason_code(self):
        facts = _base_facts(mcp_boundary_reachable=True)
        diag = run_diagnostics(facts, OperatingMode.AUTO)
        assert ReasonCode.DOCTOR_AUTO_PROMOTED_TO_GOVERNED.value in diag.reason_codes


# --------------------------------------------------------------
# section4 - Runtime checks skip when MCP boundary is live
# --------------------------------------------------------------


class TestRuntimeSkipWhenBoundaryLive:
    def test_runtime_running_skip(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            runtime_running=False,
        )
        result = check_runtime_running(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.SKIP.value
        assert "MCP boundary" in result.message

    def test_runtime_reachable_skip(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            runtime_reachable=False,
        )
        result = check_runtime_reachable(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.SKIP.value

    def test_runtime_checked_when_no_boundary(self):
        facts = _base_facts(
            mcp_boundary_reachable=False,
            runtime_running=True,
            runtime_reachable=True,
        )
        result = check_runtime_running(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.PASS.value


# --------------------------------------------------------------
# section5 - MCP config expanded search
# --------------------------------------------------------------


class TestMCPConfigExpandedSearch:
    def test_config_pass_when_boundary_reachable_no_file(self):
        """When no config file exists but boundary is reachable, config check passes."""
        facts = _base_facts(
            mcp_config_present=False,
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://mcp.example.com",
        )
        result = check_mcp_config(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.PASS.value
        assert "boundary is reachable" in result.message.lower()

    def test_config_fail_when_nothing_found(self):
        facts = _base_facts(
            mcp_config_present=False,
            mcp_boundary_reachable=False,
        )
        result = check_mcp_config(facts, OperatingMode.GOVERNED)
        assert result.status == CheckStatus.FAIL.value


# --------------------------------------------------------------
# section6 - Doctor command surfaces next steps
# --------------------------------------------------------------


class TestDoctorNextSteps:
    def test_auto_mode_surfaces_whoami_hint(self):
        with patch(
            "keyhole_cli.commands.doctor.collect_environment_facts",
            return_value=_base_facts(
                mcp_boundary_reachable=True,
                mcp_boundary_url="https://mcp.example.com",
            ),
        ):
            result = run_doctor(mode="auto")
        assert any("whoami" in s for s in result.next_steps)

    def test_auto_mode_surfaces_host_attest_hint(self):
        with patch(
            "keyhole_cli.commands.doctor.collect_environment_facts",
            return_value=_base_facts(
                mcp_boundary_reachable=True,
                mcp_boundary_url="https://mcp.example.com",
            ),
        ):
            result = run_doctor(mode="auto")
        assert any("host attest" in s.lower() for s in result.next_steps)

    def test_auto_mode_whoami_hint_is_actionable(self):
        """Next step for whoami is a CLI command, not a URL."""
        with patch(
            "keyhole_cli.commands.doctor.collect_environment_facts",
            return_value=_base_facts(
                mcp_boundary_reachable=True,
                mcp_boundary_url="https://mcp.example.com",
                mcp_operations=["whoami", "runs.start", "events.query"],
            ),
        ):
            result = run_doctor(mode="auto")
        whoami_steps = [s for s in result.next_steps if "whoami" in s.lower()]
        assert len(whoami_steps) > 0
        # Must be a CLI command, not a URL
        assert not any("https://" in s for s in whoami_steps)


# --------------------------------------------------------------
# section7 - Backward compatibility
# --------------------------------------------------------------


class TestBackwardCompatibility:
    def test_local_only_still_works(self):
        with patch(
            "keyhole_cli.commands.doctor.collect_environment_facts",
            return_value=_base_facts(),
        ):
            result = run_doctor(mode="local_only")
        assert result.success is True
        assert "local_only" in result.summary

    def test_governed_mode_still_works(self):
        with patch(
            "keyhole_cli.commands.doctor.collect_environment_facts",
            return_value=_base_facts(
                mcp_boundary_reachable=True,
                mcp_boundary_url="https://mcp.example.com",
                mcp_config_present=True,
                mcp_config_path="/home/user/.keyhole/mcp.json",
            ),
        ):
            result = run_doctor(mode="governed")
        assert result.success is True


# --------------------------------------------------------------
# section8 - EnvironmentFacts new fields
# --------------------------------------------------------------


class TestEnvironmentFactsNewFields:
    def test_new_fields_default_to_empty(self):
        facts = EnvironmentFacts()
        assert facts.mcp_boundary_reachable is False
        assert facts.mcp_boundary_url == ""
        assert facts.mcp_contract_version == ""
        assert facts.mcp_operations == []

    def test_to_dict_includes_new_fields(self):
        facts = _base_facts(
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://mcp.example.com",
            mcp_contract_version="mcp/v1",
            mcp_operations=["whoami"],
        )
        d = facts.to_dict()
        assert d["mcp_boundary_reachable"] is True
        assert d["mcp_boundary_url"] == "https://mcp.example.com"
        assert d["mcp_contract_version"] == "mcp/v1"
        assert d["mcp_operations"] == ["whoami"]

    def test_build_from_overrides(self):
        facts = build_facts_from_overrides(
            mcp_boundary_reachable=True,
            mcp_boundary_url="https://test.com",
        )
        assert facts.mcp_boundary_reachable is True
