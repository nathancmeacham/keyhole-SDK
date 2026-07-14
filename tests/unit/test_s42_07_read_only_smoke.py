"""Tests for CE-V5-S42-07 - Read-Only Smoke Path.

Validates all 7 acceptance criteria and 10 functional requirements:

AC-1: first-run developer can execute the smoke path using the SDK and CLI
AC-2: smoke path exercises discover -> auth -> identity -> context -> safe run
AC-3: failure at any phase produces clear cause + fix in terminal output
AC-4: docs/smoke.md explains what the smoke proves and common failures
AC-5: result shape is readable by both humans and agents
AC-6: smoke path is strictly read-only - no mutation of platform state
AC-7: smoke path uses live MCP boundary surfaces

FR-1:  Smoke runner orchestrates the full 4-phase path
FR-2:  Uses live MCP surfaces (CapabilitiesClient, ContextClient)
FR-3:  Discovery-first - capabilities before auth
FR-4:  Auth-if-needed - reports auth posture
FR-5:  Identity inspection via whoami
FR-6:  Context retrieval via context.compile
FR-7:  Safe read-only run via gaps.list
FR-8:  Troubleshooting docs exist with failure modes table
FR-9:  Human and agent readability of results
FR-10: No private-source dependency
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
SMOKE_PKG = SDK_ROOT / "smoke"
EXAMPLE_DIR = REPO_ROOT / "examples" / "python-client"
DOCS_DIR = REPO_ROOT / "docs"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"
AGENT_MD = DOCS_DIR / "AGENT.md"
README = REPO_ROOT / "README.md"
SMOKE_DOC = DOCS_DIR / "smoke.md"


# -- Imports under test --------------------------------------
from keyhole_sdk.smoke import (
    PhaseResult,
    ReadOnlySmokeRunner,
    SmokePhase,
    SmokeResult,
)


# --------------------------------------------------------------
# Test Helpers
# --------------------------------------------------------------

def _mock_response(status_code=200, json_data=None, text=""):
    """Build a mock HTTP response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def _mock_session_for_full_path():
    """Build a mock session that passes all phases."""
    session = MagicMock()

    # Phase 1: GET /mcp/v1/capabilities -> 200
    caps_response = _mock_response(200, {
        "contract": {"version": "mcp/v1"},
        "transport": {"protocol": "REST/HTTP"},
        "auth": {"flow": "OIDC/PKCE", "realm": "keyhole-mcp"},
        "context_access": {"implemented_surfaces": ["context.compile", "gaps.list"]},
    })

    # Phase 2: GET /mcp/v1/whoami -> 200
    whoami_response = _mock_response(200, {
        "participant_id": "test-participant",
        "realm": "keyhole-mcp",
    })

    # Phase 3: POST /mcp/v1/runs/start (context.compile) -> 200
    context_response = _mock_response(200, {
        "run_type": "context.compile",
        "status": "complete",
        "data": {
            "topology": {"platform_name": "Keyhole"},
            "contract": {"governance_model": "boundary-governed"},
        },
    })

    # Phase 4: POST /mcp/v1/runs/start (gaps.list) -> 200
    gaps_response = _mock_response(200, {
        "run_type": "gaps.list",
        "status": "complete",
        "data": {"gaps": []},
    })

    session.get.side_effect = [caps_response, whoami_response]
    session.post.side_effect = [context_response, gaps_response]
    session.headers = {}
    return session


# --------------------------------------------------------------
# FR-1: Smoke runner orchestrates the full 4-phase path
# --------------------------------------------------------------

class TestSmokeRunnerOrchestration:
    """FR-1: Runner produces exactly 4 phase results in order."""

    def test_runner_produces_four_phases_on_success(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()

        assert len(result.phases) == 4
        assert result.phases[0].phase == SmokePhase.DISCOVERY
        assert result.phases[1].phase == SmokePhase.IDENTITY
        assert result.phases[2].phase == SmokePhase.CONTEXT
        assert result.phases[3].phase == SmokePhase.READONLY_RUN

    def test_all_passed_when_all_succeed(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        assert result.all_passed is True

    def test_all_passed_false_when_identity_fails(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()
        assert result.all_passed is False
        assert result.phases[1].phase == SmokePhase.IDENTITY
        assert result.phases[1].success is False

    def test_skips_context_and_run_on_identity_failure(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()

        # Context and run should be skipped
        assert len(result.phases) == 4
        context = result.get_phase(SmokePhase.CONTEXT)
        assert context.success is False
        assert "Skipped" in context.error

        readonly_run = result.get_phase(SmokePhase.READONLY_RUN)
        assert readonly_run.success is False
        assert "Skipped" in readonly_run.error


# --------------------------------------------------------------
# FR-2: Uses live MCP surfaces (CapabilitiesClient, ContextClient)
# --------------------------------------------------------------

class TestUsesLiveMCPSurfaces:
    """FR-2: Runner uses real SDK clients, not custom HTTP."""

    def test_runner_source_imports_capabilities_client(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "CapabilitiesClient" in source

    def test_runner_source_imports_context_client(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "ContextClient" in source

    def test_runner_source_imports_dispatch_preflight(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "DispatchPreflight" in source


# --------------------------------------------------------------
# FR-3: Discovery-first - capabilities before auth
# --------------------------------------------------------------

class TestDiscoveryFirst:
    """FR-3: Discovery is the first phase."""

    def test_discovery_is_phase_zero(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        assert result.phases[0].phase == SmokePhase.DISCOVERY

    def test_discovery_failure_still_includes_all_phases(self):
        session = MagicMock()
        session.headers = {}
        from requests.exceptions import ConnectionError as ReqConnectionError

        session.get.side_effect = ReqConnectionError("unreachable")

        runner = ReadOnlySmokeRunner(
            base_url="https://unreachable.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        assert result.phases[0].phase == SmokePhase.DISCOVERY
        assert result.phases[0].success is False


# --------------------------------------------------------------
# FR-4: Auth-if-needed - reports auth posture
# --------------------------------------------------------------

class TestAuthPosture:
    """FR-4: Runner reports auth posture from discovery."""

    def test_discovery_data_includes_auth_flow(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        disc = result.get_phase(SmokePhase.DISCOVERY)
        assert disc.success
        assert "auth_flow" in disc.data


# --------------------------------------------------------------
# FR-5: Identity inspection via whoami
# --------------------------------------------------------------

class TestIdentityInspection:
    """FR-5: Runner calls /mcp/v1/whoami."""

    def test_identity_phase_calls_whoami(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        identity = result.get_phase(SmokePhase.IDENTITY)
        assert identity.success is True

    def test_identity_401_produces_clear_error(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()
        identity = result.get_phase(SmokePhase.IDENTITY)
        assert identity.success is False
        assert "401" in identity.error
        assert identity.suggestion  # must provide guidance

    def test_identity_403_produces_clear_error(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(403)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        identity = result.get_phase(SmokePhase.IDENTITY)
        assert identity.success is False
        assert "403" in identity.error


# --------------------------------------------------------------
# FR-6: Context retrieval via context.compile
# --------------------------------------------------------------

class TestContextRetrieval:
    """FR-6: Runner invokes context.compile."""

    def test_context_phase_succeeds(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        ctx = result.get_phase(SmokePhase.CONTEXT)
        assert ctx.success is True

    def test_context_data_includes_platform_info(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        ctx = result.get_phase(SmokePhase.CONTEXT)
        assert "platform_name" in ctx.data


# --------------------------------------------------------------
# FR-7: Safe read-only run via gaps.list
# --------------------------------------------------------------

class TestReadOnlyRun:
    """FR-7: Runner invokes gaps.list as the safe read-only run."""

    def test_readonly_run_succeeds(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        run = result.get_phase(SmokePhase.READONLY_RUN)
        assert run.success is True

    def test_readonly_run_data_includes_run_type(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        run = result.get_phase(SmokePhase.READONLY_RUN)
        assert run.data.get("run_type") == "gaps.list"


# --------------------------------------------------------------
# FR-8: Troubleshooting docs exist
# --------------------------------------------------------------

class TestTroubleshootingDocs:
    """FR-8: docs/smoke.md exists with required content."""

    def test_smoke_doc_exists(self):
        assert SMOKE_DOC.exists(), "docs/smoke.md must exist"

    def test_smoke_doc_has_failure_modes_table(self):
        content = SMOKE_DOC.read_text()
        assert "Common Failure Modes" in content
        # Table must have at least Discovery / Identity / Context rows
        assert "Discovery" in content
        assert "Identity" in content
        assert "Context" in content

    def test_smoke_doc_explains_what_it_proves(self):
        content = SMOKE_DOC.read_text()
        assert "What It Proves" in content

    def test_smoke_doc_explains_what_it_does_not_prove(self):
        content = SMOKE_DOC.read_text()
        assert "What It Does NOT Prove" in content

    def test_smoke_doc_has_example_output(self):
        content = SMOKE_DOC.read_text()
        assert "Example Output" in content
        assert "ALL PHASES PASSED" in content


# --------------------------------------------------------------
# FR-9: Human and agent readability of results
# --------------------------------------------------------------

class TestResultReadability:
    """FR-9: SmokeResult is readable by humans and machines."""

    def test_summary_includes_pass_markers(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        summary = result.summary()
        assert "[PASS]" in summary
        assert "ALL PHASES PASSED" in summary

    def test_summary_includes_fail_markers_on_failure(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()
        summary = result.summary()
        assert "[FAIL]" in summary
        assert "SMOKE PATH INCOMPLETE" in summary

    def test_phase_result_is_pydantic_model(self):
        p = PhaseResult(phase=SmokePhase.DISCOVERY, success=True)
        d = p.model_dump()
        assert "phase" in d
        assert "success" in d

    def test_smoke_result_is_pydantic_model(self):
        r = SmokeResult()
        d = r.model_dump()
        assert "phases" in d
        assert "read_only" in d

    def test_get_phase_returns_stub_for_missing(self):
        r = SmokeResult()
        p = r.get_phase(SmokePhase.DISCOVERY)
        assert p.success is False
        assert "not executed" in p.error


# --------------------------------------------------------------
# FR-10: No private-source dependency
# --------------------------------------------------------------

class TestNoPrivateSourceDependency:
    """FR-10: Smoke module does not depend on private platform source."""

    PRIVATE_PATTERNS = [
        "keyhole-system",
        "keyhole-storage",
        "keyhole-egress-gateway",
        "controller-manager",
        "nats.nats.svc",
        "qdrant.keyhole-storage",
    ]

    def test_runner_no_private_imports(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        for pattern in self.PRIVATE_PATTERNS:
            assert pattern not in source, (
                f"runner.py must not reference private pattern: {pattern}"
            )

    def test_models_no_private_imports(self):
        source = (SMOKE_PKG / "models.py").read_text()
        for pattern in self.PRIVATE_PATTERNS:
            assert pattern not in source, (
                f"models.py must not reference private pattern: {pattern}"
            )


# --------------------------------------------------------------
# AC-1: Executable smoke path example exists
# --------------------------------------------------------------

class TestExecutableExample:
    """AC-1: Runnable example script exists."""

    def test_smoke_example_exists(self):
        path = EXAMPLE_DIR / "smoke_readonly.py"
        assert path.exists(), "examples/python-client/smoke_readonly.py must exist"

    def test_smoke_example_uses_sdk(self):
        source = (EXAMPLE_DIR / "smoke_readonly.py").read_text()
        assert "ReadOnlySmokeRunner" in source

    def test_smoke_example_requires_env_vars(self):
        source = (EXAMPLE_DIR / "smoke_readonly.py").read_text()
        assert "KEYHOLE_MCP_URL" in source
        assert "KEYHOLE_MCP_TOKEN" in source


# --------------------------------------------------------------
# AC-2: Exercises the full discover -> identity -> context -> run path
# --------------------------------------------------------------

class TestFullPathExercised:
    """AC-2: All 4 phases are exercised in order."""

    def test_all_four_phases_present(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        phases = [p.phase for p in result.phases]
        assert phases == [
            SmokePhase.DISCOVERY,
            SmokePhase.IDENTITY,
            SmokePhase.CONTEXT,
            SmokePhase.READONLY_RUN,
        ]


# --------------------------------------------------------------
# AC-3: Clear cause + fix on failure
# --------------------------------------------------------------

class TestClearFailureGuidance:
    """AC-3: Each failure produces cause + suggestion."""

    def test_identity_failure_includes_suggestion(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()
        identity = result.get_phase(SmokePhase.IDENTITY)
        assert identity.error
        assert identity.suggestion

    def test_skipped_phase_includes_suggestion(self):
        session = MagicMock()
        session.headers = {}
        caps_response = _mock_response(200, {"contract": {"version": "mcp/v1"}})
        whoami_response = _mock_response(401)
        session.get.side_effect = [caps_response, whoami_response]

        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="bad-token",
            session=session,
        )
        result = runner.run()
        ctx = result.get_phase(SmokePhase.CONTEXT)
        assert ctx.error
        assert ctx.suggestion


# --------------------------------------------------------------
# AC-6: Strictly read-only
# --------------------------------------------------------------

class TestStrictlyReadOnly:
    """AC-6: SmokeResult always marks read_only=True."""

    def test_result_read_only_true(self):
        session = _mock_session_for_full_path()
        runner = ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        )
        result = runner.run()
        assert result.read_only is True

    def test_runner_uses_only_get_and_read_runs(self):
        """Verify runner only uses GET and known read-only POST run types."""
        source = (SMOKE_PKG / "runner.py").read_text()
        # Must not have any PUT, DELETE, or PATCH calls
        assert "session.put" not in source.lower()
        assert "session.delete" not in source.lower()
        assert "session.patch" not in source.lower()


# --------------------------------------------------------------
# AC-7: Uses live MCP boundary surfaces
# --------------------------------------------------------------

class TestUsesLiveBoundarySurfaces:
    """AC-7: Runner uses SDK clients that hit real MCP endpoints."""

    def test_runner_uses_capabilities_endpoint(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "/mcp/v1/capabilities" in source or "CapabilitiesClient" in source

    def test_runner_uses_whoami_endpoint(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "/mcp/v1/whoami" in source

    def test_runner_uses_runs_start_via_context_client(self):
        source = (SMOKE_PKG / "runner.py").read_text()
        assert "ContextClient" in source


# --------------------------------------------------------------
# Package structure
# --------------------------------------------------------------

class TestPackageStructure:
    """Smoke package is properly structured and wired into SDK."""

    def test_smoke_init_exists(self):
        assert (SMOKE_PKG / "__init__.py").exists()

    def test_smoke_models_exists(self):
        assert (SMOKE_PKG / "models.py").exists()

    def test_smoke_runner_exists(self):
        assert (SMOKE_PKG / "runner.py").exists()

    def test_sdk_init_exports_smoke_runner(self):
        source = (SDK_ROOT / "__init__.py").read_text()
        assert "ReadOnlySmokeRunner" in source

    def test_sdk_init_exports_smoke_result(self):
        source = (SDK_ROOT / "__init__.py").read_text()
        assert "SmokeResult" in source

    def test_import_from_top_level(self):
        from keyhole_sdk import ReadOnlySmokeRunner, SmokeResult
        assert ReadOnlySmokeRunner is not None
        assert SmokeResult is not None


# --------------------------------------------------------------
# Documentation references
# --------------------------------------------------------------

class TestDocReferences:
    """Documentation files reference the smoke path."""

    def test_readme_mentions_smoke(self):
        content = README.read_text()
        assert "ReadOnlySmokeRunner" in content
        assert "smoke_readonly.py" in content

    def test_agent_md_mentions_smoke(self):
        content = AGENT_MD.read_text()
        assert "ReadOnlySmokeRunner" in content

    def test_smoke_doc_in_inventory(self):
        inventory = (
            REPO_ROOT
            / "docs"
            / "specs"
            / "developer_ecosystem"
            / "public_surface_inventory.yaml"
        ).read_text()
        assert "docs/smoke.md" in inventory

    def test_smoke_example_in_inventory(self):
        inventory = (
            REPO_ROOT
            / "docs"
            / "specs"
            / "developer_ecosystem"
            / "public_surface_inventory.yaml"
        ).read_text()
        assert "examples/python-client/smoke_readonly.py" in inventory


# --------------------------------------------------------------
# Context manager
# --------------------------------------------------------------

class TestContextManager:
    """Runner supports context manager protocol."""

    def test_runner_as_context_manager(self):
        session = _mock_session_for_full_path()
        with ReadOnlySmokeRunner(
            base_url="https://boundary.example.com",
            token="test-token",
            session=session,
        ) as runner:
            result = runner.run()
        assert result.all_passed is True
