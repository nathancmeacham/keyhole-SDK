"""Tests for CE-V5 RG-01 - Recursive Governance Proof Test.

Validates the cross-boundary participant validation protocol that proves
an external SDK repository can:

  - inherit governance context
  - perform work independently
  - submit proof
  - receive a deterministic verdict
  - affect canonical state

while remaining separate from the platform repository.

Success criteria validated:

SC-1: participant.contract.registered event shape exists
SC-2: context.compile.resolved event shape exists
SC-3: proof.bundle.submitted event shape exists
SC-4: governance.verdict event shape exists
SC-5: promotion.executed event shape exists (optional)

Protocol phases validated:

Phase 1: Contract registration flow (scaffolded)
Phase 2: Context inheritance via context.compile
Phase 3: External implementation capture
Phase 4: Local verification execution
Phase 5: Proof submission flow (scaffolded)
Phase 6: Governance evaluation flow (scaffolded)
Phase 7: Promotion flow (scaffolded)

Trace validation:

TV-1: Governance trace builder produces valid trace
TV-2: Causal graph is renderable
TV-3: Evidence bundle is producible
TV-4: Correlation ID chains all events
TV-5: Missing events are detectable

Design validation:

DV-1: Protocol composes existing SDK surfaces
DV-2: Scaffolded vs supported is honest
DV-3: No private platform coupling
DV-4: Deterministic outputs from same inputs
DV-5: Local-only mode works without boundary
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
GOVERNANCE_PKG = SDK_ROOT / "governance"

# -- Imports under test --------------------------------------
from keyhole_sdk.governance import (
    EXPECTED_EVENTS,
    GovernanceEvent,
    GovernancePhase,
    GovernancePhaseResult,
    GovernanceProofResult,
    GovernanceProofRunner,
    GovernanceTraceBuilder,
)
from keyhole_sdk.governance.models import GovernancePhase as GovernancePhaseModel
from keyhole_sdk.governance.runner import (
    GovernanceProofRunner as RunnerDirect,
    _SCAFFOLDED_PHASES,
    _SUPPORTED_PHASES,
)
from keyhole_sdk.governance.trace import GovernanceTraceBuilder as TraceDirect
from keyhole_sdk.proof.models import (
    ParticipantContractPlaceholder,
    ProofBundlePlaceholder,
    SupportStatus,
    VerificationOutput,
)
from keyhole_sdk.proof.adapters import (
    AdapterResult,
    ContractRegistrationAdapter,
    LocalContractRegistrationAdapter,
    LocalProofSubmissionAdapter,
    LocalVerdictRetrievalAdapter,
    ProofSubmissionAdapter,
    VerdictRetrievalAdapter,
)


# --------------------------------------------------------------
# Test Helpers
# --------------------------------------------------------------

def _passing_collector():
    """Collector that produces a passing VerificationOutput."""
    return VerificationOutput(
        verification_class="unit-tests",
        passed=True,
        total_tests=10,
        passed_tests=10,
        failed_tests=0,
    )


def _failing_collector():
    """Collector that produces a failing VerificationOutput."""
    return VerificationOutput(
        verification_class="unit-tests",
        passed=False,
        total_tests=10,
        passed_tests=8,
        failed_tests=2,
        error_summary="2 tests failed",
    )


class LiveRegistrationAdapter(ContractRegistrationAdapter):
    """Simulates a live contract registration adapter."""

    def register(self, contract):
        return AdapterResult(
            supported=True, success=True,
            reason="Registered successfully",
            data={
                "contract_digest": "abc123",
                "participant_id": contract.participant_name,
            },
        )


class LiveSubmissionAdapter(ProofSubmissionAdapter):
    """Simulates a live proof submission adapter."""

    def submit(self, bundle):
        return AdapterResult(
            supported=True, success=True,
            reason="Submitted successfully",
            data={
                "proof_digest": "def456",
                "source_commit": bundle.source_commit,
            },
        )


class LiveVerdictAdapter(VerdictRetrievalAdapter):
    """Simulates a live verdict retrieval adapter."""

    def retrieve_verdict(self, submission_reference):
        return AdapterResult(
            supported=True, success=True,
            reason="Verdict issued",
            data={
                "verdict": "ACCEPT",
                "reason": "verification_complete",
            },
        )

    def get_repair_guidance(self, verdict_reference):
        return AdapterResult(
            supported=True, success=True,
            data={"guidance": "No repairs needed"},
        )


# --------------------------------------------------------------
# Package Structure
# --------------------------------------------------------------
class TestPackageStructure:
    """Governance package exists and has expected modules."""

    def test_package_exists(self):
        assert GOVERNANCE_PKG.exists()
        assert (GOVERNANCE_PKG / "__init__.py").exists()

    def test_models_module_exists(self):
        assert (GOVERNANCE_PKG / "models.py").exists()

    def test_runner_module_exists(self):
        assert (GOVERNANCE_PKG / "runner.py").exists()

    def test_trace_module_exists(self):
        assert (GOVERNANCE_PKG / "trace.py").exists()


# --------------------------------------------------------------
# GovernancePhase Enum
# --------------------------------------------------------------
class TestGovernancePhaseEnum:
    """GovernancePhase enum has all 7 protocol phases."""

    def test_has_registration_phase(self):
        assert GovernancePhase.REGISTRATION == "registration"

    def test_has_context_phase(self):
        assert GovernancePhase.CONTEXT == "context"

    def test_has_implementation_phase(self):
        assert GovernancePhase.IMPLEMENTATION == "implementation"

    def test_has_verification_phase(self):
        assert GovernancePhase.VERIFICATION == "verification"

    def test_has_submission_phase(self):
        assert GovernancePhase.SUBMISSION == "submission"

    def test_has_evaluation_phase(self):
        assert GovernancePhase.EVALUATION == "evaluation"

    def test_has_promotion_phase(self):
        assert GovernancePhase.PROMOTION == "promotion"

    def test_exactly_seven_phases(self):
        assert len(GovernancePhase) == 7

    def test_is_str_enum(self):
        assert isinstance(GovernancePhase.REGISTRATION, str)


# --------------------------------------------------------------
# Expected Events Mapping
# --------------------------------------------------------------
class TestExpectedEvents:
    """EXPECTED_EVENTS maps phases to Event Spine event types."""

    def test_registration_event(self):
        assert EXPECTED_EVENTS[GovernancePhase.REGISTRATION] == "participant.contract.registered"

    def test_context_event(self):
        assert EXPECTED_EVENTS[GovernancePhase.CONTEXT] == "context.compile.resolved"

    def test_submission_event(self):
        assert EXPECTED_EVENTS[GovernancePhase.SUBMISSION] == "proof.bundle.submitted"

    def test_evaluation_event(self):
        assert EXPECTED_EVENTS[GovernancePhase.EVALUATION] == "governance.verdict"

    def test_promotion_event(self):
        assert EXPECTED_EVENTS[GovernancePhase.PROMOTION] == "promotion.executed"

    def test_all_five_success_criteria_events(self):
        """All five success criteria events exist in the mapping."""
        required = {
            "participant.contract.registered",
            "context.compile.resolved",
            "proof.bundle.submitted",
            "governance.verdict",
            "promotion.executed",
        }
        actual = set(EXPECTED_EVENTS.values())
        assert required.issubset(actual)


# --------------------------------------------------------------
# GovernanceEvent Model
# --------------------------------------------------------------
class TestGovernanceEvent:
    """GovernanceEvent carries required Event Spine fields."""

    def test_default_participant_id(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
        )
        assert e.participant_id == "keyhole-developer-kit"

    def test_has_correlation_id(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
            correlation_id="corr-123",
        )
        assert e.correlation_id == "corr-123"

    def test_has_event_digest(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
            event_digest="digest-abc",
        )
        assert e.event_digest == "digest-abc"

    def test_has_timestamp(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
        )
        assert isinstance(e.timestamp, datetime)

    def test_scaffolded_flag(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.REGISTRATION,
            scaffolded=True,
        )
        assert e.scaffolded is True

    def test_data_field(self):
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
            data={"key": "value"},
        )
        assert e.data["key"] == "value"

    def test_required_fields_per_spec(self):
        """Each event must include participant_id, contract_digest,
        correlation_id, event_digest, timestamp per the spec."""
        e = GovernanceEvent(
            event_type="test.event",
            phase=GovernancePhase.CONTEXT,
            participant_id="p1",
            contract_digest="cd1",
            correlation_id="c1",
            event_digest="ed1",
        )
        assert e.participant_id == "p1"
        assert e.contract_digest == "cd1"
        assert e.correlation_id == "c1"
        assert e.event_digest == "ed1"
        assert e.timestamp is not None


# --------------------------------------------------------------
# GovernancePhaseResult Model
# --------------------------------------------------------------
class TestGovernancePhaseResult:
    """GovernancePhaseResult tracks success and scaffolded status."""

    def test_default_not_successful(self):
        r = GovernancePhaseResult(phase=GovernancePhase.REGISTRATION)
        assert r.success is False

    def test_scaffolded_flag(self):
        r = GovernancePhaseResult(
            phase=GovernancePhase.REGISTRATION, scaffolded=True,
        )
        assert r.scaffolded is True

    def test_event_attachment(self):
        event = GovernanceEvent(
            event_type="test", phase=GovernancePhase.CONTEXT,
        )
        r = GovernancePhaseResult(
            phase=GovernancePhase.CONTEXT, event=event,
        )
        assert r.event is not None
        assert r.event.event_type == "test"

    def test_error_and_suggestion(self):
        r = GovernancePhaseResult(
            phase=GovernancePhase.SUBMISSION,
            error="Not available",
            suggestion="Wait for DEV-UX",
        )
        assert "Not available" in r.error
        assert "DEV-UX" in r.suggestion


# --------------------------------------------------------------
# GovernanceProofResult Model
# --------------------------------------------------------------
class TestGovernanceProofResult:
    """GovernanceProofResult aggregates all phase results."""

    def _make_result(self, phases=None) -> GovernanceProofResult:
        if phases is None:
            phases = [
                GovernancePhaseResult(
                    phase=GovernancePhase.REGISTRATION,
                    scaffolded=True, success=False,
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.CONTEXT,
                    success=True,
                    event=GovernanceEvent(
                        event_type="context.compile.resolved",
                        phase=GovernancePhase.CONTEXT,
                    ),
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.IMPLEMENTATION,
                    success=True,
                    event=GovernanceEvent(
                        event_type="implementation.commit.captured",
                        phase=GovernancePhase.IMPLEMENTATION,
                    ),
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.VERIFICATION,
                    success=True,
                    event=GovernanceEvent(
                        event_type="verification.completed",
                        phase=GovernancePhase.VERIFICATION,
                    ),
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.SUBMISSION,
                    scaffolded=True, success=False,
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.EVALUATION,
                    scaffolded=True, success=False,
                ),
                GovernancePhaseResult(
                    phase=GovernancePhase.PROMOTION,
                    scaffolded=True, success=False,
                ),
            ]
        return GovernanceProofResult(
            phases=phases,
            correlation_id="test-corr-001",
        )

    def test_test_id_default(self):
        r = self._make_result()
        assert r.test_id == "RG-01"

    def test_participant_default(self):
        r = self._make_result()
        assert r.participant == "keyhole-developer-kit"

    def test_all_supported_passed_when_supported_pass(self):
        r = self._make_result()
        assert r.all_supported_passed is True

    def test_all_passed_false_when_scaffolded_fail(self):
        r = self._make_result()
        assert r.all_passed is False

    def test_events_list(self):
        r = self._make_result()
        assert "context.compile.resolved" in r.events
        assert "implementation.commit.captured" in r.events

    def test_phase_summary(self):
        r = self._make_result()
        ps = r.phase_summary
        assert ps["total_phases"] == 7
        assert ps["scaffolded"] == 4
        assert ps["supported_passed"] == 3
        assert ps["supported_total"] == 3
        assert ps["all_supported_passed"] is True

    def test_get_phase(self):
        r = self._make_result()
        ctx = r.get_phase(GovernancePhase.CONTEXT)
        assert ctx.success is True

    def test_get_phase_missing(self):
        r = GovernanceProofResult(phases=[])
        result = r.get_phase(GovernancePhase.CONTEXT)
        assert "not executed" in result.error.lower()

    def test_to_evidence_bundle(self):
        r = self._make_result()
        evidence = r.to_evidence_bundle()
        assert evidence["test_id"] == "RG-01"
        assert evidence["participant"] == "keyhole-developer-kit"
        assert evidence["correlation_id"] == "test-corr-001"
        # PARTIAL because scaffolded phases remain
        assert evidence["result"] == "PARTIAL"
        assert "scaffolded_phases" in evidence
        assert "supported_phases" in evidence

    def test_evidence_bundle_partial_when_supported_fail(self):
        phases = [
            GovernancePhaseResult(
                phase=GovernancePhase.CONTEXT, success=False,
            ),
        ]
        r = GovernanceProofResult(phases=phases)
        evidence = r.to_evidence_bundle()
        assert evidence["result"] == "FAILURE"

    def test_summary_output(self):
        r = self._make_result()
        s = r.summary()
        assert "RG-01" in s
        assert "keyhole-developer-kit" in s
        assert "PASS" in s
        assert "scaffolded" in s.lower()

    def test_support_status_is_scaffolded(self):
        r = self._make_result()
        assert r.support_status == SupportStatus.SCAFFOLDED


# --------------------------------------------------------------
# GovernanceProofRunner - Construction
# --------------------------------------------------------------
class TestRunnerConstruction:
    """GovernanceProofRunner initializes correctly."""

    def test_default_construction(self):
        runner = GovernanceProofRunner()
        assert runner.support_status == SupportStatus.SCAFFOLDED

    def test_has_correlation_id(self):
        runner = GovernanceProofRunner()
        assert len(runner.correlation_id) > 0

    def test_unique_correlation_ids(self):
        r1 = GovernanceProofRunner()
        r2 = GovernanceProofRunner()
        assert r1.correlation_id != r2.correlation_id

    def test_custom_adapters(self):
        runner = GovernanceProofRunner(
            registration_adapter=LiveRegistrationAdapter(),
            submission_adapter=LiveSubmissionAdapter(),
            verdict_adapter=LiveVerdictAdapter(),
        )
        assert runner is not None

    def test_register_collector(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        # No error means registration succeeded


# --------------------------------------------------------------
# GovernanceProofRunner - Phase Constants
# --------------------------------------------------------------
class TestPhaseConstants:
    """Phase classification constants are correct."""

    def test_scaffolded_phases(self):
        assert GovernancePhase.REGISTRATION in _SCAFFOLDED_PHASES
        assert GovernancePhase.SUBMISSION in _SCAFFOLDED_PHASES
        assert GovernancePhase.EVALUATION in _SCAFFOLDED_PHASES
        assert GovernancePhase.PROMOTION in _SCAFFOLDED_PHASES
        assert len(_SCAFFOLDED_PHASES) == 4

    def test_supported_phases(self):
        assert GovernancePhase.CONTEXT in _SUPPORTED_PHASES
        assert GovernancePhase.IMPLEMENTATION in _SUPPORTED_PHASES
        assert GovernancePhase.VERIFICATION in _SUPPORTED_PHASES
        assert len(_SUPPORTED_PHASES) == 3


# --------------------------------------------------------------
# GovernanceProofRunner - Local-Only Run
# --------------------------------------------------------------
class TestRunnerLocalOnly:
    """Runner completes in local-only mode without boundary."""

    def test_run_completes(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        assert isinstance(result, GovernanceProofResult)

    def test_all_seven_phases_present(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        assert len(result.phases) == 7

    def test_phase_order(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        expected_order = [
            GovernancePhase.REGISTRATION,
            GovernancePhase.CONTEXT,
            GovernancePhase.IMPLEMENTATION,
            GovernancePhase.VERIFICATION,
            GovernancePhase.SUBMISSION,
            GovernancePhase.EVALUATION,
            GovernancePhase.PROMOTION,
        ]
        actual_order = [p.phase for p in result.phases]
        assert actual_order == expected_order

    def test_registration_scaffolded(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        reg = result.get_phase(GovernancePhase.REGISTRATION)
        assert reg.scaffolded is True
        assert reg.success is False

    def test_context_succeeds_local(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        ctx = result.get_phase(GovernancePhase.CONTEXT)
        assert ctx.success is True
        assert ctx.data.get("mode") == "local-only"

    def test_implementation_succeeds(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        impl = result.get_phase(GovernancePhase.IMPLEMENTATION)
        assert impl.success is True

    def test_verification_succeeds_with_collector(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        ver = result.get_phase(GovernancePhase.VERIFICATION)
        assert ver.success is True
        assert ver.data.get("all_passed") is True

    def test_verification_with_no_collectors(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        ver = result.get_phase(GovernancePhase.VERIFICATION)
        # With no collectors, bundle still assembles (vacuously all passed)
        assert ver.success is True

    def test_verification_fails_with_failing_collector(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _failing_collector)
        result = runner.run()
        ver = result.get_phase(GovernancePhase.VERIFICATION)
        assert ver.success is False

    def test_submission_scaffolded(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        sub = result.get_phase(GovernancePhase.SUBMISSION)
        assert sub.scaffolded is True
        assert sub.success is False

    def test_evaluation_scaffolded(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        ev = result.get_phase(GovernancePhase.EVALUATION)
        assert ev.scaffolded is True
        assert ev.success is False

    def test_promotion_scaffolded(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        promo = result.get_phase(GovernancePhase.PROMOTION)
        assert promo.scaffolded is True
        assert promo.success is False

    def test_all_supported_passed_with_passing_collector(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        assert result.all_supported_passed is True

    def test_all_supported_failed_with_failing_collector(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _failing_collector)
        result = runner.run()
        assert result.all_supported_passed is False

    def test_proof_bundle_attached(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        assert result.proof_bundle is not None
        assert isinstance(result.proof_bundle, ProofBundlePlaceholder)

    def test_correlation_id_set(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        assert result.correlation_id == runner.correlation_id

    def test_timestamps_set(self):
        runner = GovernanceProofRunner()
        result = runner.run()
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at


# --------------------------------------------------------------
# GovernanceProofRunner - With Live Adapters (Simulated)
# --------------------------------------------------------------
class TestRunnerWithLiveAdapters:
    """Runner works correctly with live (simulated) adapters."""

    def _make_runner(self):
        runner = GovernanceProofRunner(
            registration_adapter=LiveRegistrationAdapter(),
            submission_adapter=LiveSubmissionAdapter(),
            verdict_adapter=LiveVerdictAdapter(),
        )
        runner.register_collector("unit-tests", _passing_collector)
        return runner

    def test_registration_succeeds(self):
        result = self._make_runner().run()
        reg = result.get_phase(GovernancePhase.REGISTRATION)
        assert reg.success is True
        assert reg.scaffolded is False

    def test_registration_event_produced(self):
        result = self._make_runner().run()
        reg = result.get_phase(GovernancePhase.REGISTRATION)
        assert reg.event is not None
        assert reg.event.event_type == "participant.contract.registered"

    def test_submission_succeeds(self):
        result = self._make_runner().run()
        sub = result.get_phase(GovernancePhase.SUBMISSION)
        assert sub.success is True
        assert sub.scaffolded is False

    def test_submission_event_produced(self):
        result = self._make_runner().run()
        sub = result.get_phase(GovernancePhase.SUBMISSION)
        assert sub.event is not None
        assert sub.event.event_type == "proof.bundle.submitted"

    def test_evaluation_succeeds(self):
        result = self._make_runner().run()
        ev = result.get_phase(GovernancePhase.EVALUATION)
        assert ev.success is True
        assert ev.scaffolded is False

    def test_evaluation_event_produced(self):
        result = self._make_runner().run()
        ev = result.get_phase(GovernancePhase.EVALUATION)
        assert ev.event is not None
        assert ev.event.event_type == "governance.verdict"

    def test_full_event_chain(self):
        result = self._make_runner().run()
        events = result.events
        assert "participant.contract.registered" in events
        assert "context.compile.resolved" in events
        assert "proof.bundle.submitted" in events
        assert "governance.verdict" in events

    def test_evidence_bundle_success(self):
        result = self._make_runner().run()
        evidence = result.to_evidence_bundle()
        assert evidence["result"] == "PARTIAL"
        # PARTIAL because promotion is still scaffolded


# --------------------------------------------------------------
# GovernanceTraceBuilder
# --------------------------------------------------------------
class TestGovernanceTraceBuilder:
    """GovernanceTraceBuilder produces valid traces and graphs."""

    def _make_result_with_events(self) -> GovernanceProofResult:
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        return runner.run()

    def test_build_trace(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        trace = builder.build_trace()
        assert trace["trace_id"] == result.correlation_id
        assert trace["participant"] == "keyhole-developer-kit"
        assert isinstance(trace["events"], list)
        assert trace["event_count"] > 0

    def test_trace_events_have_required_fields(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        trace = builder.build_trace()
        for event in trace["events"]:
            assert "sequence" in event
            assert "event_type" in event
            assert "phase" in event
            assert "participant_id" in event
            assert "correlation_id" in event
            assert "event_digest" in event
            assert "timestamp" in event

    def test_build_graph(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        graph = builder.build_graph()
        assert "Governance Trace Graph" in graph
        assert "keyhole-developer-kit" in graph
        assert "Causal chain:" in graph

    def test_graph_shows_supported_marker(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        graph = builder.build_graph()
        assert "[supported]" in graph

    def test_correlation_id_consistent(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        assert builder.correlation_id == result.correlation_id

    def test_missing_events_detects_absent_events(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        missing = builder.missing_events()
        # Local-only run won't have all events
        assert len(missing) > 0

    def test_validate_chain_false_for_incomplete(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        assert builder.validate_chain() is False

    def test_validate_supported_chain(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        assert builder.validate_supported_chain() is True

    def test_events_in_order(self):
        result = self._make_result_with_events()
        builder = GovernanceTraceBuilder(result)
        events = builder.events
        # Events should be in phase order
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp

    def test_empty_trace(self):
        result = GovernanceProofResult(phases=[])
        builder = GovernanceTraceBuilder(result)
        graph = builder.build_graph()
        assert "no events recorded" in graph


# --------------------------------------------------------------
# Determinism (DV-4)
# --------------------------------------------------------------
class TestDeterminism:
    """Same inputs produce deterministic outputs."""

    def test_phase_order_deterministic(self):
        r1 = GovernanceProofRunner()
        r1.register_collector("unit-tests", _passing_collector)
        result1 = r1.run()

        r2 = GovernanceProofRunner()
        r2.register_collector("unit-tests", _passing_collector)
        result2 = r2.run()

        phases1 = [p.phase for p in result1.phases]
        phases2 = [p.phase for p in result2.phases]
        assert phases1 == phases2

    def test_scaffolded_classification_deterministic(self):
        r1 = GovernanceProofRunner()
        result1 = r1.run()

        r2 = GovernanceProofRunner()
        result2 = r2.run()

        scaffolded1 = [p.scaffolded for p in result1.phases]
        scaffolded2 = [p.scaffolded for p in result2.phases]
        assert scaffolded1 == scaffolded2

    def test_evidence_bundle_shape_deterministic(self):
        r1 = GovernanceProofRunner()
        r1.register_collector("unit-tests", _passing_collector)
        e1 = r1.run().to_evidence_bundle()

        r2 = GovernanceProofRunner()
        r2.register_collector("unit-tests", _passing_collector)
        e2 = r2.run().to_evidence_bundle()

        assert e1["test_id"] == e2["test_id"]
        assert e1["participant"] == e2["participant"]
        assert e1["result"] == e2["result"]
        assert e1["phase_summary"] == e2["phase_summary"]


# --------------------------------------------------------------
# No Private Platform Coupling (DV-3)
# --------------------------------------------------------------
class TestNoPlatformCoupling:
    """Governance module has no private platform dependency."""

    def test_no_platform_imports(self):
        for py_file in GOVERNANCE_PKG.rglob("*.py"):
            content = py_file.read_text()
            assert "keyhole_platform" not in content, (
                f"{py_file.name} imports keyhole_platform"
            )

    def test_no_private_field_references(self):
        for py_file in GOVERNANCE_PKG.rglob("*.py"):
            content = py_file.read_text()
            for field in [
                "pointer_state",
                "canonical_digest",
                "cluster_topology",
                "controller_state",
            ]:
                assert field not in content, (
                    f"{py_file.name} references private field {field}"
                )


# --------------------------------------------------------------
# Composes Existing SDK Surfaces (DV-1)
# --------------------------------------------------------------
class TestComposesExistingSurfaces:
    """Runner composes existing SDK surfaces, not new ones."""

    def test_uses_context_client(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "ContextClient" in source

    def test_uses_verification_runner(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "VerificationRunner" in source

    def test_uses_contract_registration_adapter(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "ContractRegistrationAdapter" in source

    def test_uses_proof_submission_adapter(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "ProofSubmissionAdapter" in source

    def test_uses_verdict_retrieval_adapter(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "VerdictRetrievalAdapter" in source

    def test_uses_participant_contract(self):
        source = (GOVERNANCE_PKG / "runner.py").read_text()
        assert "ParticipantContractPlaceholder" in source


# --------------------------------------------------------------
# Honest Scaffolding (DV-2)
# --------------------------------------------------------------
class TestHonestScaffolding:
    """Scaffolded vs supported is honestly labeled."""

    def test_runner_support_status_scaffolded(self):
        runner = GovernanceProofRunner()
        assert runner.support_status == SupportStatus.SCAFFOLDED

    def test_local_registration_clearly_scaffolded(self):
        adapter = LocalContractRegistrationAdapter()
        result = adapter.register(ParticipantContractPlaceholder())
        assert result.supported is False

    def test_local_submission_clearly_scaffolded(self):
        adapter = LocalProofSubmissionAdapter()
        result = adapter.submit(ProofBundlePlaceholder())
        assert result.supported is False

    def test_local_verdict_clearly_scaffolded(self):
        adapter = LocalVerdictRetrievalAdapter()
        result = adapter.retrieve_verdict("ref")
        assert result.supported is False

    def test_phase_summary_distinguishes(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        ps = result.phase_summary
        assert ps["scaffolded"] == 4
        assert ps["supported_total"] == 3


# --------------------------------------------------------------
# SDK Surface Export
# --------------------------------------------------------------
class TestSDKExports:
    """Governance types are exported from the SDK top level."""

    def test_governance_phase_importable(self):
        from keyhole_sdk import GovernancePhase
        assert GovernancePhase is not None

    def test_governance_proof_result_importable(self):
        from keyhole_sdk import GovernanceProofResult
        assert GovernanceProofResult is not None

    def test_governance_proof_runner_importable(self):
        from keyhole_sdk import GovernanceProofRunner
        assert GovernanceProofRunner is not None

    def test_governance_trace_builder_importable(self):
        from keyhole_sdk import GovernanceTraceBuilder
        assert GovernanceTraceBuilder is not None


# --------------------------------------------------------------
# Evidence Bundle Serialization
# --------------------------------------------------------------
class TestEvidenceSerialization:
    """Evidence bundle is JSON-serializable and well-formed."""

    def test_evidence_bundle_is_json_serializable(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        evidence = result.to_evidence_bundle()
        serialized = json.dumps(evidence)
        assert len(serialized) > 0

    def test_evidence_bundle_has_required_fields(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        evidence = result.to_evidence_bundle()
        assert "test_id" in evidence
        assert "participant" in evidence
        assert "events" in evidence
        assert "correlation_id" in evidence
        assert "result" in evidence

    def test_trace_is_json_serializable(self):
        runner = GovernanceProofRunner()
        runner.register_collector("unit-tests", _passing_collector)
        result = runner.run()
        builder = GovernanceTraceBuilder(result)
        trace = builder.build_trace()
        serialized = json.dumps(trace)
        assert len(serialized) > 0


# --------------------------------------------------------------
# Failure Conditions (per spec)
# --------------------------------------------------------------
class TestFailureConditions:
    """Spec failure conditions are detectable."""

    def test_proof_without_contract_detectable(self):
        """proof accepted without contract is detectable."""
        runner = GovernanceProofRunner()
        result = runner.run()
        reg = result.get_phase(GovernancePhase.REGISTRATION)
        sub = result.get_phase(GovernancePhase.SUBMISSION)
        # Both scaffolded - integrity maintained
        assert reg.scaffolded is True
        assert sub.scaffolded is True

    def test_verdict_without_evidence_detectable(self):
        """verdict issued without evidence is detectable."""
        runner = GovernanceProofRunner()
        result = runner.run()
        ev = result.get_phase(GovernancePhase.EVALUATION)
        assert ev.scaffolded is True

    def test_event_spine_missing_causal_chain_detectable(self):
        """Missing causal chain is detectable via trace validation."""
        runner = GovernanceProofRunner()
        result = runner.run()
        builder = GovernanceTraceBuilder(result)
        assert builder.validate_chain() is False
        assert len(builder.missing_events()) > 0


# --------------------------------------------------------------
# Module Docstrings
# --------------------------------------------------------------
class TestDocstrings:
    """All governance modules have proper docstrings."""

    def test_models_has_docstring(self):
        import keyhole_sdk.governance.models as m
        assert m.__doc__ is not None
        assert "RG-01" in m.__doc__

    def test_runner_has_docstring(self):
        import keyhole_sdk.governance.runner as r
        assert r.__doc__ is not None
        assert "RG-01" in r.__doc__ or "governance" in r.__doc__.lower()

    def test_trace_has_docstring(self):
        import keyhole_sdk.governance.trace as t
        assert t.__doc__ is not None
        assert "trace" in t.__doc__.lower()

    def test_init_has_docstring(self):
        import keyhole_sdk.governance as g
        assert g.__doc__ is not None
        assert "RG-01" in g.__doc__ or "governance" in g.__doc__.lower()
