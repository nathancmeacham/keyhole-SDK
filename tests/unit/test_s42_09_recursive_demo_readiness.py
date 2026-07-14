"""Tests for CE-V5-S42-09 - Recursive Demo Readiness Pack.

Validates that the developer kit contains a complete, scriptable,
deterministic, boundary-consuming recursive demo readiness pack.

Acceptance criteria:

AC-1: Demo flow is scripted end-to-end - no tribal memory required
AC-2: Demo flow is deterministic - same inputs produce same outputs
AC-3: Demo change is identified and documented
AC-4: Handoff boundary is clearly defined with scaffolded markers
AC-5: Evidence map connects participant actions to expected observations
AC-6: Entire demo pack is boundary-consuming, not boundary-defining
AC-7: Supported-now vs scaffolded-later is clearly distinguished
AC-8: Operator runbook exists with step-by-step instructions

Validation criteria:

VC-1: Scripted demo flow check
VC-2: Determinism check
VC-3: Demo change identification check
VC-4: Handoff boundary check
VC-5: Evidence mapping check
VC-6: Boundary-consuming posture check
VC-7: Supported vs scaffolded clarity check
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
DEMO_PKG = SDK_ROOT / "demo"
DOCS_DIR = REPO_ROOT / "docs"
RECURSIVE_DEMO_DOC = DOCS_DIR / "recursive-demo.md"
OPERATOR_NOTES_DOC = DOCS_DIR / "recursive-demo-operator-notes.md"
EVIDENCE_MAP_DOC = DOCS_DIR / "recursive-demo-evidence-map.md"

# -- Imports under test --------------------------------------
from keyhole_sdk.demo import (
    DemoFlowRunner,
    DemoPhase,
    DemoResult,
    DemoStepResult,
)
from keyhole_sdk.demo.models import DemoPhase as DemoPhaseModel
from keyhole_sdk.demo.runner import DemoFlowRunner as DemoFlowRunnerDirect
from keyhole_sdk.proof.models import (
    ProofBundlePlaceholder,
    SupportStatus,
    VerificationOutput,
)
from keyhole_sdk.proof.adapters import (
    AdapterResult,
    LocalProofSubmissionAdapter,
)


# --------------------------------------------------------------
# Validation 1 - Scripted Demo Flow Check (AC-1, VC-1)
# --------------------------------------------------------------

class TestScriptedFlowCheck:
    """Verify the demo flow is scripted end-to-end without tribal memory."""

    def test_demo_package_exists(self):
        """The demo subpackage must exist as a proper Python package."""
        assert DEMO_PKG.is_dir(), "keyhole_sdk/demo/ must exist"
        assert (DEMO_PKG / "__init__.py").is_file()

    def test_models_module_exists(self):
        """demo/models.py must exist with structured result types."""
        assert (DEMO_PKG / "models.py").is_file()

    def test_runner_module_exists(self):
        """demo/runner.py must exist with DemoFlowRunner."""
        assert (DEMO_PKG / "runner.py").is_file()

    def test_demo_flow_runner_importable(self):
        """DemoFlowRunner must be importable from keyhole_sdk.demo."""
        assert DemoFlowRunner is not None

    def test_demo_flow_runner_from_top_level(self):
        """DemoFlowRunner must be importable from keyhole_sdk."""
        from keyhole_sdk import DemoFlowRunner as TopLevel
        assert TopLevel is DemoFlowRunner

    def test_demo_result_from_top_level(self):
        """DemoResult must be importable from keyhole_sdk."""
        from keyhole_sdk import DemoResult as TopLevel
        assert TopLevel is DemoResult

    def test_runner_has_run_method(self):
        """DemoFlowRunner must have a run() method."""
        assert hasattr(DemoFlowRunner, "run")
        assert callable(getattr(DemoFlowRunner, "run"))

    def test_runner_has_run_verification_method(self):
        """DemoFlowRunner must have a run_verification() convenience method."""
        assert hasattr(DemoFlowRunner, "run_verification")

    def test_runner_has_assemble_proof_bundle_method(self):
        """DemoFlowRunner must have an assemble_proof_bundle() method."""
        assert hasattr(DemoFlowRunner, "assemble_proof_bundle")

    def test_runner_has_submit_proof_method(self):
        """DemoFlowRunner must have a submit_proof() method."""
        assert hasattr(DemoFlowRunner, "submit_proof")

    def test_runner_has_register_collector(self):
        """DemoFlowRunner must support verification collector registration."""
        assert hasattr(DemoFlowRunner, "register_collector")

    def test_recursive_demo_doc_exists(self):
        """docs/recursive-demo.md must exist describing the demo workflow."""
        assert RECURSIVE_DEMO_DOC.is_file()

    def test_operator_runbook_exists(self):
        """docs/recursive-demo-operator-notes.md must exist."""
        assert OPERATOR_NOTES_DOC.is_file()

    def test_evidence_map_exists(self):
        """docs/recursive-demo-evidence-map.md must exist."""
        assert EVIDENCE_MAP_DOC.is_file()


# --------------------------------------------------------------
# Validation 2 - Determinism Check (AC-2, VC-2)
# --------------------------------------------------------------

class TestDeterminismCheck:
    """Verify the demo flow produces deterministic results."""

    def test_demo_phase_enum_has_all_phases(self):
        """DemoPhase must enumerate all 7 phases."""
        expected = {
            "DISCOVERY", "IDENTITY", "CONTEXT", "POSTURE",
            "VERIFICATION", "BUNDLE", "HANDOFF",
        }
        actual = {p.name for p in DemoPhase}
        assert actual == expected

    def test_demo_phase_values_are_strings(self):
        """DemoPhase values must be string values."""
        for phase in DemoPhase:
            assert isinstance(phase.value, str)

    def test_demo_step_result_defaults(self):
        """DemoStepResult with defaults must be deterministic."""
        r1 = DemoStepResult(phase=DemoPhase.DISCOVERY)
        r2 = DemoStepResult(phase=DemoPhase.DISCOVERY)
        assert r1.success == r2.success == False  # noqa: E712
        assert r1.scaffolded == r2.scaffolded == False  # noqa: E712
        assert r1.data == r2.data == {}
        assert r1.error == r2.error == ""

    def test_demo_result_defaults(self):
        """DemoResult with defaults must be deterministic."""
        r1 = DemoResult()
        r2 = DemoResult()
        assert r1.steps == r2.steps == []
        assert r1.verification_outputs == r2.verification_outputs == []
        assert r1.proof_bundle is None
        assert r2.proof_bundle is None

    def test_demo_result_all_passed_empty(self):
        """DemoResult with no steps must not report all_passed."""
        r = DemoResult()
        assert r.all_passed is False

    def test_runner_constructor_deterministic(self):
        """DemoFlowRunner constructor with same args produces same state."""
        r1 = DemoFlowRunner(base_url="http://test", token="tok")
        r2 = DemoFlowRunner(base_url="http://test", token="tok")
        assert r1.base_url == r2.base_url == "http://test"
        assert r1.token == r2.token == "tok"
        assert r1.support_status == r2.support_status

    def test_posture_phase_is_deterministic(self):
        """Posture phase must produce identical results each time."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        r1 = runner._phase_posture()
        r2 = runner._phase_posture()
        assert r1.phase == r2.phase == DemoPhase.POSTURE
        assert r1.success == r2.success is True
        assert r1.data == r2.data
        assert r1.data["participant_name"] == "keyhole-developer-kit"


# --------------------------------------------------------------
# Validation 3 - Demo Change Identification (AC-3, VC-3)
# --------------------------------------------------------------

class TestDemoChangeCheck:
    """Verify the demo change is identified and documented."""

    def test_recursive_demo_doc_identifies_change(self):
        """recursive-demo.md must identify the demo-safe change."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "--governance" in content, "Must identify the --governance flag"

    def test_recursive_demo_doc_explains_safety(self):
        """recursive-demo.md must explain why the change is safe."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "safe" in content.lower(), "Must explain change safety"

    def test_recursive_demo_doc_has_verification_plan(self):
        """recursive-demo.md must explain how the change is verified."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "verif" in content.lower(), "Must describe verification plan"

    def test_operator_notes_has_steps(self):
        """Operator runbook must contain numbered execution steps."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "Step 1" in content
        assert "Step 2" in content

    def test_operator_notes_has_checkpoints(self):
        """Operator runbook must include checkpoints."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "Checkpoint" in content

    def test_operator_notes_has_failure_guidance(self):
        """Operator runbook must include failure guidance."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "fail" in content.lower()


# --------------------------------------------------------------
# Validation 4 - Handoff Boundary Check (AC-4, VC-4)
# --------------------------------------------------------------

class TestHandoffBoundaryCheck:
    """Verify the handoff boundary between participant and platform
    is clearly defined and scaffolded."""

    def test_handoff_phase_exists(self):
        """DemoPhase must include HANDOFF."""
        assert DemoPhase.HANDOFF is not None
        assert DemoPhase.HANDOFF.value == "handoff"

    def test_handoff_returns_scaffolded(self):
        """Handoff phase must return scaffolded=True when not supported."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        result = runner._phase_handoff(bundle=None)
        assert result.scaffolded is True
        assert result.data["supported"] is False

    def test_handoff_with_bundle_returns_scaffolded(self):
        """Handoff with a real bundle must still be scaffolded."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        bundle = ProofBundlePlaceholder(participant_name="test")
        result = runner._phase_handoff(bundle=bundle)
        assert result.scaffolded is True
        assert result.data["supported"] is False

    def test_submit_proof_returns_not_supported(self):
        """submit_proof() must return supported=False via local adapter."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        result = runner.submit_proof(
            bundle=ProofBundlePlaceholder(participant_name="test"),
        )
        assert isinstance(result, AdapterResult)
        assert result.supported is False

    def test_demo_step_result_has_scaffolded_field(self):
        """DemoStepResult must expose a scaffolded boolean."""
        step = DemoStepResult(phase=DemoPhase.HANDOFF, scaffolded=True)
        assert step.scaffolded is True

    def test_demo_result_all_passed_ignores_scaffolded(self):
        """all_passed must only consider non-scaffolded steps."""
        result = DemoResult(steps=[
            DemoStepResult(phase=DemoPhase.DISCOVERY, success=True),
            DemoStepResult(phase=DemoPhase.IDENTITY, success=True),
            DemoStepResult(phase=DemoPhase.HANDOFF, scaffolded=True, success=False),
        ])
        assert result.all_passed is True

    def test_handoff_boundary_documented(self):
        """recursive-demo.md must document the handoff boundary."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "handoff" in content.lower() or "hand off" in content.lower()

    def test_operator_notes_documents_scaffolded_handoff(self):
        """Operator runbook must note that handoff is scaffolded."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "scaffolded" in content.lower()


# --------------------------------------------------------------
# Validation 5 - Evidence Mapping Check (AC-5, VC-5)
# --------------------------------------------------------------

class TestEvidenceMappingCheck:
    """Verify the evidence map connects participant actions to expected
    platform-side evidence."""

    def test_evidence_map_doc_exists(self):
        """docs/recursive-demo-evidence-map.md must exist."""
        assert EVIDENCE_MAP_DOC.is_file()

    def test_evidence_map_covers_discovery(self):
        """Evidence map must cover the discovery phase."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "discovery" in content.lower()

    def test_evidence_map_covers_identity(self):
        """Evidence map must cover the identity phase."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "identity" in content.lower()

    def test_evidence_map_covers_context(self):
        """Evidence map must cover the context phase."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "context" in content.lower()

    def test_evidence_map_covers_verification(self):
        """Evidence map must cover the verification phase."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "verification" in content.lower()

    def test_evidence_map_covers_proof_bundle(self):
        """Evidence map must cover proof bundle assembly."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "bundle" in content.lower() or "proof" in content.lower()

    def test_evidence_map_covers_handoff(self):
        """Evidence map must cover the handoff boundary."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "handoff" in content.lower()

    def test_evidence_map_distinguishes_participant_vs_platform(self):
        """Evidence map must distinguish participant-side from platform-side."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "participant" in content.lower()
        assert "platform" in content.lower()

    def test_evidence_map_identifies_status_per_phase(self):
        """Evidence map must label each phase's status."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "executable now" in content.lower() or "scaffolded" in content.lower()


# --------------------------------------------------------------
# Validation 6 - Boundary-Consuming Posture Check (AC-6, VC-6)
# --------------------------------------------------------------

class TestBoundaryConsumingPostureCheck:
    """Verify the demo pack is boundary-consuming, not boundary-defining."""

    def test_demo_init_docstring_mentions_boundary_consuming(self):
        """demo/__init__.py must mention boundary-consuming posture."""
        init_content = (DEMO_PKG / "__init__.py").read_text()
        assert "boundary-consuming" in init_content.lower()

    def test_demo_runner_docstring_mentions_boundary_consuming(self):
        """demo/runner.py must mention boundary-consuming posture."""
        runner_content = (DEMO_PKG / "runner.py").read_text()
        assert "boundary-consuming" in runner_content.lower()

    def test_demo_models_no_platform_contract_definitions(self):
        """demo/models.py must not define platform contract shapes."""
        content = (DEMO_PKG / "models.py").read_text()
        # Should not contain patterns suggesting platform-side contract definition
        assert "platform_contract" not in content
        assert "governance_verdict" not in content

    def test_runner_no_undisclosed_endpoints(self):
        """Runner must not reference undisclosed platform endpoints."""
        content = (DEMO_PKG / "runner.py").read_text()
        # Only known public paths should appear
        assert "/mcp/v1/whoami" in content or "WHOAMI_PATH" in content
        # Must not contain internal platform paths
        assert "/internal/" not in content
        assert "/admin/" not in content
        assert "/private/" not in content

    def test_runner_uses_existing_sdk_clients(self):
        """Runner must compose existing boundary-consuming SDK clients."""
        content = (DEMO_PKG / "runner.py").read_text()
        assert "CapabilitiesClient" in content
        assert "ContextClient" in content

    def test_runner_uses_proof_scaffolding(self):
        """Runner must compose proof scaffolding from S42-08."""
        content = (DEMO_PKG / "runner.py").read_text()
        assert "VerificationRunner" in content
        assert "ProofBundlePlaceholder" in content
        assert "ParticipantContractPlaceholder" in content

    def test_recursive_demo_doc_boundary_consuming(self):
        """recursive-demo.md must describe boundary-consuming posture."""
        content = RECURSIVE_DEMO_DOC.read_text()
        # Must reference the participant side, not define platform side
        assert "participant" in content.lower()

    def test_no_hardcoded_internal_urls(self):
        """No source file in demo/ must hardcode internal platform URLs."""
        for py_file in DEMO_PKG.glob("*.py"):
            content = py_file.read_text()
            # Must not contain hardcoded internal URLs
            assert "localhost:8" not in content, f"{py_file.name} has hardcoded URL"
            assert "127.0.0.1:" not in content, f"{py_file.name} has hardcoded URL"


# --------------------------------------------------------------
# Validation 7 - Supported vs Scaffolded Clarity (AC-7, VC-7)
# --------------------------------------------------------------

class TestSupportedVsScaffoldedClarity:
    """Verify clear distinction between supported-now and scaffolded-later."""

    def test_runner_support_status_is_scaffolded(self):
        """DemoFlowRunner must declare support_status as SCAFFOLDED."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        assert runner.support_status == SupportStatus.SCAFFOLDED

    def test_demo_result_support_status_default(self):
        """DemoResult default support_status must be SCAFFOLDED."""
        result = DemoResult()
        assert result.support_status == SupportStatus.SCAFFOLDED

    def test_handoff_clearly_marked_scaffolded(self):
        """Handoff results must be clearly marked as scaffolded."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        result = runner._phase_handoff(bundle=None)
        assert result.scaffolded is True

    def test_posture_phase_is_supported(self):
        """Posture phase must execute successfully (supported now)."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        result = runner._phase_posture()
        assert result.success is True
        assert result.scaffolded is False

    def test_demo_phases_have_clear_values(self):
        """Each DemoPhase enum value must be a clear lowercase string."""
        for phase in DemoPhase:
            assert phase.value == phase.value.lower()
            assert "_" not in phase.value or phase.value.replace("_", "").isalpha()

    def test_step_result_captures_scaffolded_separately(self):
        """DemoStepResult must track scaffolded independently from success."""
        # A step can be scaffolded and "successful" in shape terms
        step = DemoStepResult(
            phase=DemoPhase.BUNDLE,
            success=True,
            scaffolded=True,
        )
        assert step.success is True
        assert step.scaffolded is True

    def test_demo_models_use_support_status_enum(self):
        """Demo models must use SupportStatus from proof module."""
        content = (DEMO_PKG / "models.py").read_text()
        assert "SupportStatus" in content

    def test_recursive_demo_doc_labels_status(self):
        """recursive-demo.md must label phases as executable or scaffolded."""
        content = RECURSIVE_DEMO_DOC.read_text()
        has_executable = "executable" in content.lower()
        has_scaffolded = "scaffolded" in content.lower()
        assert has_executable and has_scaffolded, \
            "Must distinguish executable-now from scaffolded-later"


# --------------------------------------------------------------
# Validation 8 - DemoFlowRunner Shape (AC-1, AC-2)
# --------------------------------------------------------------

class TestDemoFlowRunnerShape:
    """Verify DemoFlowRunner has the expected shape and interface."""

    def test_constructor_requires_base_url(self):
        """DemoFlowRunner must require base_url."""
        sig = inspect.signature(DemoFlowRunner.__init__)
        params = list(sig.parameters.keys())
        assert "base_url" in params

    def test_constructor_accepts_token(self):
        """DemoFlowRunner must accept a token parameter."""
        sig = inspect.signature(DemoFlowRunner.__init__)
        params = list(sig.parameters.keys())
        assert "token" in params

    def test_constructor_accepts_timeout(self):
        """DemoFlowRunner must accept a timeout parameter."""
        sig = inspect.signature(DemoFlowRunner.__init__)
        params = list(sig.parameters.keys())
        assert "timeout" in params

    def test_constructor_accepts_session(self):
        """DemoFlowRunner must accept a session parameter."""
        sig = inspect.signature(DemoFlowRunner.__init__)
        params = list(sig.parameters.keys())
        assert "session" in params

    def test_constructor_accepts_submission_adapter(self):
        """DemoFlowRunner must accept a submission_adapter parameter."""
        sig = inspect.signature(DemoFlowRunner.__init__)
        params = list(sig.parameters.keys())
        assert "submission_adapter" in params

    def test_base_url_strips_trailing_slash(self):
        """DemoFlowRunner must strip trailing slash from base_url."""
        runner = DemoFlowRunner(base_url="http://test/", token="tok")
        assert runner.base_url == "http://test"

    def test_default_timeout(self):
        """DemoFlowRunner must have a reasonable default timeout."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        assert runner.timeout == 15.0

    def test_has_seven_phase_methods(self):
        """DemoFlowRunner must have private methods for all 7 phases."""
        expected = [
            "_phase_discovery", "_phase_identity", "_phase_context",
            "_phase_posture", "_phase_verification", "_phase_bundle",
            "_phase_handoff",
        ]
        for method_name in expected:
            assert hasattr(DemoFlowRunner, method_name), \
                f"Missing phase method: {method_name}"


# --------------------------------------------------------------
# Validation 9 - DemoResult Shape
# --------------------------------------------------------------

class TestDemoResultShape:
    """Verify DemoResult has the expected shape and behavior."""

    def test_has_steps_field(self):
        """DemoResult must have a steps field."""
        r = DemoResult()
        assert isinstance(r.steps, list)

    def test_has_verification_outputs_field(self):
        """DemoResult must have a verification_outputs field."""
        r = DemoResult()
        assert isinstance(r.verification_outputs, list)

    def test_has_proof_bundle_field(self):
        """DemoResult must have a proof_bundle field."""
        r = DemoResult()
        assert r.proof_bundle is None

    def test_has_support_status_field(self):
        """DemoResult must have a support_status field."""
        r = DemoResult()
        assert r.support_status == SupportStatus.SCAFFOLDED

    def test_has_all_passed_property(self):
        """DemoResult must have an all_passed property."""
        r = DemoResult()
        assert hasattr(r, "all_passed")

    def test_has_verification_summary_property(self):
        """DemoResult must have a verification_summary property."""
        r = DemoResult()
        summary = r.verification_summary
        assert isinstance(summary, dict)
        assert "total_verifications" in summary

    def test_has_get_step_method(self):
        """DemoResult must have a get_step() method."""
        r = DemoResult()
        step = r.get_step(DemoPhase.DISCOVERY)
        assert step.phase == DemoPhase.DISCOVERY
        assert step.success is False

    def test_has_summary_method(self):
        """DemoResult must have a summary() method returning a string."""
        r = DemoResult(steps=[
            DemoStepResult(phase=DemoPhase.DISCOVERY, success=True),
        ])
        s = r.summary()
        assert isinstance(s, str)
        assert "discovery" in s.lower()

    def test_all_passed_with_mixed_steps(self):
        """all_passed must reflect only non-scaffolded step success."""
        r = DemoResult(steps=[
            DemoStepResult(phase=DemoPhase.DISCOVERY, success=True),
            DemoStepResult(phase=DemoPhase.POSTURE, success=True),
            DemoStepResult(phase=DemoPhase.HANDOFF, scaffolded=True),
        ])
        assert r.all_passed is True

    def test_all_passed_false_on_failure(self):
        """all_passed must be False if any non-scaffolded step failed."""
        r = DemoResult(steps=[
            DemoStepResult(phase=DemoPhase.DISCOVERY, success=True),
            DemoStepResult(phase=DemoPhase.IDENTITY, success=False),
        ])
        assert r.all_passed is False


# --------------------------------------------------------------
# Validation 10 - Document Completeness
# --------------------------------------------------------------

class TestDocumentCompleteness:
    """Verify all three documentation deliverables are complete."""

    def test_recursive_demo_has_workflow(self):
        """recursive-demo.md must contain step-by-step workflow."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "phase" in content.lower() or "step" in content.lower()

    def test_recursive_demo_has_prerequisites(self):
        """recursive-demo.md must list prerequisites."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "prerequisi" in content.lower()

    def test_recursive_demo_references_demo_flow_runner(self):
        """recursive-demo.md must reference DemoFlowRunner."""
        content = RECURSIVE_DEMO_DOC.read_text()
        assert "DemoFlowRunner" in content

    def test_operator_notes_has_preconditions(self):
        """Operator runbook must have a preconditions checklist."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "precondition" in content.lower() or "before" in content.lower()

    def test_operator_notes_has_troubleshooting(self):
        """Operator runbook must include troubleshooting guidance."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "troubleshoot" in content.lower()

    def test_operator_notes_references_story(self):
        """Operator runbook must reference the story ID."""
        content = OPERATOR_NOTES_DOC.read_text()
        assert "CE-V5-S42-09" in content

    def test_evidence_map_references_story(self):
        """Evidence map must reference the story ID."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "CE-V5-S42-09" in content

    def test_evidence_map_has_status_summary(self):
        """Evidence map must include an evidence status summary."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "status" in content.lower()

    def test_evidence_map_has_verification_classes(self):
        """Evidence map must list verification classes."""
        content = EVIDENCE_MAP_DOC.read_text()
        assert "verification class" in content.lower()


# --------------------------------------------------------------
# Validation 11 - Integration with S42-08
# --------------------------------------------------------------

class TestIntegrationWithS4208:
    """Verify the demo module integrates cleanly with proof scaffolding."""

    def test_demo_runner_composes_verification_runner(self):
        """DemoFlowRunner must compose VerificationRunner internally."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        assert hasattr(runner, "_verification_runner")

    def test_demo_runner_accepts_collectors(self):
        """DemoFlowRunner must accept verification collectors."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        collector = lambda: VerificationOutput(  # noqa: E731
            verification_class="test",
            passed=True,
            total_tests=1,
            passed_tests=1,
        )
        runner.register_collector("test-class", collector)

    def test_demo_runner_uses_local_submission_adapter(self):
        """DemoFlowRunner must default to LocalProofSubmissionAdapter."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        assert isinstance(runner._submission_adapter, LocalProofSubmissionAdapter)

    def test_demo_runner_accepts_custom_adapter(self):
        """DemoFlowRunner must accept a custom submission adapter."""
        adapter = LocalProofSubmissionAdapter()
        runner = DemoFlowRunner(
            base_url="http://test",
            token="tok",
            submission_adapter=adapter,
        )
        assert runner._submission_adapter is adapter

    def test_posture_phase_uses_participant_contract(self):
        """Posture phase must use ParticipantContractPlaceholder."""
        runner = DemoFlowRunner(base_url="http://test", token="tok")
        result = runner._phase_posture()
        assert result.data["participant_name"] == "keyhole-developer-kit"
        assert result.data["compatibility_posture"] == "boundary-consuming"

    def test_proof_module_still_importable(self):
        """S42-08 proof module must remain importable after S42-09."""
        from keyhole_sdk.proof import (
            ParticipantContractPlaceholder,
            ProofBundlePlaceholder,
            SupportStatus,
            VerificationOutput,
            VerificationRunner,
        )
        assert all([
            ParticipantContractPlaceholder,
            ProofBundlePlaceholder,
            SupportStatus,
            VerificationOutput,
            VerificationRunner,
        ])

    def test_top_level_sdk_exports_both_stories(self):
        """keyhole_sdk must export both S42-08 and S42-09 symbols."""
        import keyhole_sdk
        # S42-08
        assert hasattr(keyhole_sdk, "VerificationRunner")
        assert hasattr(keyhole_sdk, "ProofBundlePlaceholder")
        assert hasattr(keyhole_sdk, "SupportStatus")
        # S42-09
        assert hasattr(keyhole_sdk, "DemoFlowRunner")
        assert hasattr(keyhole_sdk, "DemoResult")
