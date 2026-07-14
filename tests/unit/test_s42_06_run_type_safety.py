"""Tests for CE-V5-S42-06 - Run-Type Safety & Schema Discovery Helpers.

Validates all 7 acceptance criteria and 8 functional requirements:

AC-1: developer kit refuses or warns on guessed/invalid run names before dispatch
AC-2: helpers guide users toward exact canonical run types
AC-3: schema discovery usage is documented where applicable
AC-4: client guidance from capabilities is reflected in helper behavior
AC-5: dispatch preflight checks catch obvious invalid names or malformed
      request assumptions before dispatch where possible
AC-6: error-path guidance tells users and agents how to recover
AC-7: no helper behavior depends on stale-source or private-source platform truth

FR-1: Run-type validation before dispatch
FR-2: Exact canonical guidance
FR-3: Schema-aware posture
FR-4: Preflight safety
FR-5: Capability-guidance reflection
FR-6: Conservative failure
FR-7: Human and agent usability
FR-8: No private-source dependency
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
DISPATCH_PKG = SDK_ROOT / "dispatch"
EXAMPLE_DIR = REPO_ROOT / "examples" / "python-client"
DOCS_DIR = REPO_ROOT / "docs"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"
AGENT_MD = DOCS_DIR / "AGENT.md"
README = REPO_ROOT / "README.md"


# -- Imports under test --------------------------------------
from keyhole_sdk.dispatch import (
    CANONICAL_RUN_TYPES,
    KNOWN_MISTAKES,
    DispatchPreflight,
    ErrorRecoveryGuidance,
    PreflightResult,
    PreflightStatus,
    RecoveryAction,
    RunTypeCheckResult,
    RunTypeStatus,
    RunTypeValidator,
    SchemaHelper,
    SchemaHint,
)


# --------------------------------------------------------------
# Test Helpers
# --------------------------------------------------------------

def _make_capabilities_result(
    surfaces=None, run_type_rule="", run_type_mistakes=None
):
    """Build a mock CapabilitiesResult-like object."""

    class _MockGuidance:
        def __init__(self):
            self.run_type_rule = run_type_rule
            self.run_type_mistakes = run_type_mistakes or []

    class _MockContextAccess:
        def __init__(self):
            self.implemented_surfaces = surfaces or []

    class _MockCaps:
        def __init__(self):
            self.guidance = _MockGuidance()
            self.context_access = _MockContextAccess()

    return _MockCaps()


# --------------------------------------------------------------
# 1. Run-Type Validation (AC-1, AC-2, FR-1, FR-2)
# --------------------------------------------------------------

class TestRunTypeValidation:
    """Verify run-type validation catches bad names and guides to canonical ones."""

    def test_valid_canonical_names(self):
        """Valid canonical names should pass validation."""
        validator = RunTypeValidator()
        for rt in [
            "context.compile", "gaps.list", "gaps.status",
            "gaps.next_open_canonical", "lineage.get.v0_1",
            "convergence.status.v0_1",
            "run.status", "run.explain", "request.inspect",
            "support.bundle", "run.tail", "run.budget",
        ]:
            result = validator.check(rt)
            assert result.is_valid, f"{rt} should be valid"
            assert result.status == RunTypeStatus.VALID

    def test_known_mistake_gaps_states(self):
        """'gaps.states' is a known mistake - should be rejected with suggestion."""
        result = RunTypeValidator().check("gaps.states")
        assert result.is_invalid
        assert "gaps.status" in result.suggestions

    def test_known_mistake_gaps_next(self):
        """'gaps.next' is a known mistake - should suggest full canonical name."""
        result = RunTypeValidator().check("gaps.next")
        assert result.is_invalid
        assert "gaps.next_open_canonical" in result.suggestions

    def test_known_mistake_gap_status(self):
        """'gap.status' (singular prefix) is a known mistake."""
        result = RunTypeValidator().check("gap.status")
        assert result.is_invalid
        assert "gaps.status" in result.suggestions

    def test_known_mistake_convergence_statuses(self):
        """Pluralized 'convergence.statuses' should be caught."""
        result = RunTypeValidator().check("convergence.statuses")
        assert result.is_invalid
        assert "convergence.status.v0_1" in result.suggestions

    def test_known_mistake_context_get(self):
        """'context.get' should suggest 'context.compile'."""
        result = RunTypeValidator().check("context.get")
        assert result.is_invalid
        assert "context.compile" in result.suggestions

    def test_unknown_run_type(self):
        """Completely unknown names return 'unknown' status."""
        result = RunTypeValidator().check("banana.split")
        assert result.status == RunTypeStatus.UNKNOWN
        assert "not recognized" in result.reason

    def test_empty_run_type_rejected(self):
        """Empty string is rejected as invalid."""
        result = RunTypeValidator().check("")
        assert result.is_invalid
        assert "non-empty" in result.reason

    def test_none_run_type_rejected(self):
        """None-like input is rejected."""
        result = RunTypeValidator().check(None)  # type: ignore
        assert result.is_invalid

    def test_close_match_same_prefix(self):
        """A name with a known prefix should get close-match suggestions."""
        result = RunTypeValidator().check("gaps.browse")
        assert result.status == RunTypeStatus.INVALID  # close match found
        assert any("gaps." in s for s in result.suggestions)

    def test_no_silent_autocorrect(self):
        """Validator should never silently return valid for invalid names."""
        for bad in ["gaps.states", "gap.status", "convergence.statuses"]:
            result = RunTypeValidator().check(bad)
            assert not result.is_valid, f"{bad} must not silently pass"

    def test_reason_includes_guidance(self):
        """Reason text should provide actionable guidance."""
        result = RunTypeValidator().check("gaps.states")
        assert "gaps.status" in result.reason or "canonical" in result.reason.lower()


# --------------------------------------------------------------
# 2. Schema Discovery (AC-3, FR-3)
# --------------------------------------------------------------

class TestSchemaDiscovery:
    """Verify schema hints are available and guide request construction."""

    def test_context_compile_schema(self):
        """context.compile has a known schema with no required params."""
        hint = SchemaHelper().get_hint("context.compile")
        assert hint.available
        assert hint.required_params == []
        assert "run_type" in str(hint.example)

    def test_lineage_requires_target(self):
        """lineage.get.v0_1 requires a 'target' parameter."""
        hint = SchemaHelper().get_hint("lineage.get.v0_1")
        assert hint.available
        assert "target" in hint.required_params

    def test_unknown_schema_unavailable(self):
        """Unknown run types return available=False with guidance."""
        hint = SchemaHelper().get_hint("invented.surface")
        assert not hint.available
        assert "re-discover" in hint.notes.lower()

    def test_validate_params_catches_missing_required(self):
        """Missing required params should generate warnings."""
        warnings = SchemaHelper().validate_params("lineage.get.v0_1", {})
        assert any("target" in w for w in warnings)

    def test_validate_params_empty_for_valid(self):
        """No warnings for run types with no required params."""
        warnings = SchemaHelper().validate_params("context.compile", {})
        assert warnings == []

    def test_schema_never_fabricates(self):
        """Schema hint for unknown type does not fabricate params."""
        hint = SchemaHelper().get_hint("invented.surface")
        assert hint.required_params == []
        assert hint.optional_params == []
        assert hint.example == {}

    def test_known_run_types_list(self):
        """known_run_types returns all types with schemas."""
        types = SchemaHelper().known_run_types
        assert "context.compile" in types
        assert "lineage.get.v0_1" in types
        assert "gaps.list" in types
        assert "run.explain" in types
        assert "request.inspect" in types
        assert "support.bundle" in types

    def test_all_canonical_have_schemas(self):
        """Every canonical run type should have a schema hint."""
        helper = SchemaHelper()
        for rt in CANONICAL_RUN_TYPES:
            hint = helper.get_hint(rt)
            assert hint.available, f"{rt} should have a schema hint"


# --------------------------------------------------------------
# 3. Capabilities Guidance Reflection (AC-4, FR-5)
# --------------------------------------------------------------

class TestCapabilitiesReflection:
    """Verify helpers consume capabilities guidance."""

    def test_validator_from_capabilities(self):
        """from_capabilities adds discovered surfaces to canonical set."""
        caps = _make_capabilities_result(
            surfaces=["context.compile", "custom.surface.v1"],
        )
        validator = RunTypeValidator.from_capabilities(caps)
        result = validator.check("custom.surface.v1")
        assert result.is_valid

    def test_validator_from_capabilities_mistakes(self):
        """from_capabilities incorporates published mistake entries."""
        caps = _make_capabilities_result(
            run_type_mistakes=["bad.name (use good.name)"],
        )
        validator = RunTypeValidator.from_capabilities(caps)
        result = validator.check("bad.name")
        assert result.is_invalid
        assert "good.name" in result.suggestions

    def test_schema_from_capabilities(self):
        """SchemaHelper.from_capabilities adds discovered surfaces."""
        caps = _make_capabilities_result(
            surfaces=["custom.surface.v1"],
        )
        helper = SchemaHelper.from_capabilities(caps)
        hint = helper.get_hint("custom.surface.v1")
        assert hint.available

    def test_preflight_from_capabilities(self):
        """DispatchPreflight.from_capabilities builds from live guidance."""
        caps = _make_capabilities_result(
            surfaces=["context.compile", "gaps.list"],
        )
        preflight = DispatchPreflight.from_capabilities(caps)
        result = preflight.check("context.compile")
        assert result.should_proceed

    def test_capabilities_mistakes_arrow_format(self):
        """Mistake entries with arrow format are parsed."""
        caps = _make_capabilities_result(
            run_type_mistakes=["wrong.name -> right.name"],
        )
        validator = RunTypeValidator.from_capabilities(caps)
        result = validator.check("wrong.name")
        assert result.is_invalid
        assert "right.name" in result.suggestions


# --------------------------------------------------------------
# 4. Preflight Checks (AC-5, FR-4)
# --------------------------------------------------------------

class TestPreflightChecks:
    """Verify preflight catches invalid names and missing params before dispatch."""

    def test_valid_dispatch_passes(self):
        """Valid run type with no required params passes preflight."""
        result = DispatchPreflight().check("context.compile")
        assert result.status == PreflightStatus.PASS
        assert result.should_proceed

    def test_invalid_name_rejected(self):
        """Known-bad name is rejected before dispatch."""
        result = DispatchPreflight().check("gaps.states")
        assert result.status == PreflightStatus.REJECT
        assert not result.should_proceed
        assert "gaps.status" in result.suggested_next_step

    def test_unknown_name_rejected(self):
        """Unknown name is rejected before dispatch."""
        result = DispatchPreflight().check("banana.split")
        assert result.status == PreflightStatus.REJECT
        assert "re-check" in result.suggested_next_step.lower()

    def test_missing_required_param_rejected(self):
        """Missing required param causes rejection."""
        result = DispatchPreflight().check("lineage.get.v0_1", params={})
        assert result.status == PreflightStatus.REJECT
        assert any("target" in w for w in result.warnings)

    def test_valid_with_required_param_passes(self):
        """Valid run type with required params passes."""
        result = DispatchPreflight().check(
            "lineage.get.v0_1",
            params={"target": "my-artifact"},
        )
        assert result.status == PreflightStatus.PASS
        assert result.should_proceed

    def test_empty_run_type_rejected(self):
        """Empty run type string is rejected."""
        result = DispatchPreflight().check("")
        assert result.status == PreflightStatus.REJECT

    def test_preflight_result_has_fields(self):
        """PreflightResult contains all required fields."""
        result = DispatchPreflight().check("gaps.states")
        assert result.run_type == "gaps.states"
        assert result.reason
        assert result.suggested_next_step
        assert isinstance(result.warnings, list)


# --------------------------------------------------------------
# 5. Error Recovery Guidance (AC-6)
# --------------------------------------------------------------

class TestErrorRecoveryGuidance:
    """Verify error recovery tells users how to recover from mistakes."""

    def test_invalid_name_recovery(self):
        """Recovery guidance for invalid names includes suggestions."""
        guidance = DispatchPreflight().get_recovery_guidance("gaps.states")
        assert guidance.error_class
        assert guidance.message
        assert len(guidance.actions) > 0
        action_texts = [a.action for a in guidance.actions]
        assert any("canonical" in a.lower() for a in action_texts)

    def test_unknown_name_recovery(self):
        """Recovery guidance for unknown names directs to discovery."""
        guidance = DispatchPreflight().get_recovery_guidance("banana.split")
        assert guidance.error_class == "unknown_run_type"
        action_texts = [a.action for a in guidance.actions]
        assert any("capabilities" in a.lower() or "discover" in a.lower()
                    for a in action_texts)

    def test_valid_name_recovery(self):
        """Recovery for a valid name points to params/connectivity."""
        guidance = DispatchPreflight().get_recovery_guidance("context.compile")
        assert guidance.message
        action_texts = [a.action for a in guidance.actions]
        assert any("connectivity" in a.lower() or "verify" in a.lower()
                    for a in action_texts)

    def test_stop_guessing_guidance(self):
        """Recovery for invalid names tells the user to stop guessing."""
        guidance = DispatchPreflight().get_recovery_guidance("gap.status")
        action_details = [a.detail for a in guidance.actions]
        assert any("guess" in d.lower() or "pluralize" in d.lower() or
                    "improvise" in d.lower() for d in action_details)

    def test_action_summary_helper(self):
        """action_summary() returns list of action strings."""
        guidance = DispatchPreflight().get_recovery_guidance("gaps.states")
        summary = guidance.action_summary()
        assert isinstance(summary, list)
        assert len(summary) > 0


# --------------------------------------------------------------
# 6. No Private-Source Dependency (AC-7, FR-8)
# --------------------------------------------------------------

class TestNoPrivateSourceDependency:
    """Verify helpers do not depend on private platform internals."""

    def test_no_private_imports_in_dispatch(self):
        """Dispatch package should not import from keyhole_platform or private paths."""
        for py_file in DISPATCH_PKG.glob("*.py"):
            content = py_file.read_text()
            assert "keyhole_platform" not in content, (
                f"{py_file.name} imports from private platform source"
            )
            assert "from keyhole_platform" not in content

    def test_no_file_system_reads(self):
        """Dispatch package should not read from file system for truth."""
        for py_file in DISPATCH_PKG.glob("*.py"):
            content = py_file.read_text()
            # Check for file-reading patterns (excluding normal imports)
            assert "open(" not in content or "# safe" in content, (
                f"{py_file.name} reads files - truth must come from boundary"
            )

    def test_no_hardcoded_private_paths(self):
        """No private cluster or API paths hardcoded."""
        forbidden = [
            "keyhole-system", "keyhole-storage", "keyhole-prod",
            "nats.nats.svc", "qdrant.keyhole-storage",
            "localhost:5000", "mcp-server-sandbox",
        ]
        for py_file in DISPATCH_PKG.glob("*.py"):
            content = py_file.read_text()
            for pattern in forbidden:
                assert pattern not in content, (
                    f"{py_file.name} contains forbidden pattern: {pattern}"
                )

    def test_validator_works_without_capabilities(self):
        """Validator works with static defaults - no live service needed."""
        validator = RunTypeValidator()
        result = validator.check("context.compile")
        assert result.is_valid

    def test_schema_works_without_capabilities(self):
        """SchemaHelper works with static defaults."""
        helper = SchemaHelper()
        hint = helper.get_hint("context.compile")
        assert hint.available


# --------------------------------------------------------------
# 7. Conservative Failure (FR-6)
# --------------------------------------------------------------

class TestConservativeFailure:
    """Verify helpers fail clearly rather than fabricating support."""

    def test_unknown_type_not_fabricated_as_valid(self):
        """Unknown types must not be silently accepted."""
        result = RunTypeValidator().check("fabricated.surface")
        assert not result.is_valid

    def test_schema_not_fabricated(self):
        """Schema for unknown type returned as unavailable."""
        hint = SchemaHelper().get_hint("fabricated.surface")
        assert not hint.available

    def test_preflight_rejects_unknown(self):
        """Preflight rejects unknown run types."""
        result = DispatchPreflight().check("fabricated.surface")
        assert result.status == PreflightStatus.REJECT

    def test_no_invented_aliases(self):
        """No run type is silently aliased to another."""
        validator = RunTypeValidator()
        for mistake in KNOWN_MISTAKES:
            result = validator.check(mistake)
            assert not result.is_valid, f"{mistake} must not silently pass"

    def test_honest_uncertainty(self):
        """Unknown results explicitly state uncertainty."""
        result = RunTypeValidator().check("unknown.workflow.v99")
        assert "not recognized" in result.reason


# --------------------------------------------------------------
# 8. SDK Integration (FR-7)
# --------------------------------------------------------------

class TestSDKIntegration:
    """Verify dispatch safety is accessible from the SDK."""

    def test_sdk_exports_validator(self):
        """RunTypeValidator is exported from keyhole_sdk."""
        from keyhole_sdk import RunTypeValidator as RTV
        assert RTV is RunTypeValidator

    def test_sdk_exports_preflight(self):
        """DispatchPreflight is exported from keyhole_sdk."""
        from keyhole_sdk import DispatchPreflight as DP
        assert DP is DispatchPreflight

    def test_sdk_exports_schema_helper(self):
        """SchemaHelper is exported from keyhole_sdk."""
        from keyhole_sdk import SchemaHelper as SH
        assert SH is SchemaHelper

    def test_dispatch_package_has_all_exports(self):
        """Dispatch __init__ exports all public symbols."""
        from keyhole_sdk import dispatch
        expected = [
            "RunTypeValidator", "SchemaHelper", "DispatchPreflight",
            "RunTypeCheckResult", "RunTypeStatus", "SchemaHint",
            "PreflightResult", "PreflightStatus",
            "ErrorRecoveryGuidance", "RecoveryAction",
            "CANONICAL_RUN_TYPES", "KNOWN_MISTAKES",
        ]
        for name in expected:
            assert hasattr(dispatch, name), f"dispatch missing: {name}"


# --------------------------------------------------------------
# 9. Models (unit)
# --------------------------------------------------------------

class TestModels:
    """Verify model shapes and defaults."""

    def test_run_type_check_result_defaults(self):
        """RunTypeCheckResult has sensible defaults."""
        r = RunTypeCheckResult()
        assert r.run_type == ""
        assert r.status == RunTypeStatus.UNKNOWN
        assert r.suggestions == []
        assert r.reason == ""

    def test_schema_hint_defaults(self):
        """SchemaHint has sensible defaults."""
        h = SchemaHint()
        assert h.run_type == ""
        assert not h.available
        assert h.required_params == []

    def test_preflight_result_defaults(self):
        """PreflightResult defaults to REJECT."""
        p = PreflightResult()
        assert p.status == PreflightStatus.REJECT
        assert not p.should_proceed

    def test_preflight_pass_should_proceed(self):
        """PASS status means should_proceed is True."""
        p = PreflightResult(status=PreflightStatus.PASS)
        assert p.should_proceed

    def test_preflight_warn_should_proceed(self):
        """WARN status means should_proceed is True."""
        p = PreflightResult(status=PreflightStatus.WARN)
        assert p.should_proceed

    def test_recovery_guidance_defaults(self):
        """ErrorRecoveryGuidance has sensible defaults."""
        g = ErrorRecoveryGuidance()
        assert g.error_class == ""
        assert g.actions == []

    def test_recovery_action_defaults(self):
        """RecoveryAction has sensible defaults."""
        a = RecoveryAction()
        assert a.action == ""
        assert a.detail == ""


# --------------------------------------------------------------
# 10. Documentation Consistency
# --------------------------------------------------------------

class TestDocumentation:
    """Verify docs reflect dispatch safety helpers."""

    def test_copilot_instructions_mention_dispatch_preflight(self):
        """Copilot instructions reference DispatchPreflight."""
        content = COPILOT_INSTRUCTIONS.read_text()
        assert "DispatchPreflight" in content

    def test_copilot_instructions_mention_run_type_validator(self):
        """Copilot instructions reference RunTypeValidator."""
        content = COPILOT_INSTRUCTIONS.read_text()
        assert "RunTypeValidator" in content

    def test_copilot_instructions_mention_schema_helper(self):
        """Copilot instructions reference SchemaHelper."""
        content = COPILOT_INSTRUCTIONS.read_text()
        assert "SchemaHelper" in content

    def test_agent_md_mentions_dispatch_safety(self):
        """AGENT.md references dispatch safety layer."""
        content = AGENT_MD.read_text()
        assert "DispatchPreflight" in content

    def test_readme_mentions_dispatch_safety(self):
        """README mentions dispatch safety."""
        content = README.read_text()
        assert "DispatchPreflight" in content

    def test_readme_shows_correct_vs_incorrect(self):
        """README shows examples of correct vs guessed names."""
        content = README.read_text()
        assert "gaps.states" in content

    def test_example_file_exists(self):
        """safe_dispatch.py example exists."""
        assert (EXAMPLE_DIR / "safe_dispatch.py").exists()

    def test_example_uses_dispatch_preflight(self):
        """Example uses DispatchPreflight."""
        content = (EXAMPLE_DIR / "safe_dispatch.py").read_text()
        assert "DispatchPreflight" in content

    def test_example_shows_four_steps(self):
        """Example demonstrates the 4-step sequence."""
        content = (EXAMPLE_DIR / "safe_dispatch.py").read_text()
        assert "Step 1" in content
        assert "Step 2" in content
        assert "Step 3" in content
        assert "Step 4" in content

    def test_copilot_instructions_show_preflight_from_capabilities(self):
        """Copilot instructions show from_capabilities pattern."""
        content = COPILOT_INSTRUCTIONS.read_text()
        assert "from_capabilities" in content

    def test_docs_teach_exact_names(self):
        """Docs teach run types are exact canonical keys."""
        content = COPILOT_INSTRUCTIONS.read_text()
        assert "exact canonical keys" in content


# --------------------------------------------------------------
# 11. Known Mistakes Coverage
# --------------------------------------------------------------

class TestKnownMistakesCoverage:
    """Verify known mistake patterns from boundary guidance are covered."""

    def test_gaps_states_covered(self):
        assert "gaps.states" in KNOWN_MISTAKES

    def test_gaps_next_covered(self):
        assert "gaps.next" in KNOWN_MISTAKES

    def test_gap_status_covered(self):
        assert "gap.status" in KNOWN_MISTAKES

    def test_convergence_statuses_covered(self):
        assert "convergence.statuses" in KNOWN_MISTAKES

    def test_known_mistakes_have_suggestions(self):
        """Every known mistake maps to at least one suggestion."""
        for mistake, suggestions in KNOWN_MISTAKES.items():
            assert len(suggestions) > 0, f"{mistake} has no suggestions"
            for s in suggestions:
                assert s in CANONICAL_RUN_TYPES, (
                    f"Suggestion '{s}' for '{mistake}' is not canonical"
                )

    def test_canonical_run_types_not_in_mistakes(self):
        """Canonical run types must not appear as known mistakes."""
        for rt in CANONICAL_RUN_TYPES:
            assert rt not in KNOWN_MISTAKES, (
                f"Canonical '{rt}' appears in KNOWN_MISTAKES"
            )


# --------------------------------------------------------------
# 12. Validator add_canonical
# --------------------------------------------------------------

class TestValidatorExtensibility:
    """Verify validator can be extended with new canonical names."""

    def test_add_canonical(self):
        """add_canonical makes a new name valid."""
        validator = RunTypeValidator()
        result = validator.check("custom.new.v1")
        assert not result.is_valid

        validator.add_canonical("custom.new.v1")
        result = validator.check("custom.new.v1")
        assert result.is_valid

    def test_canonical_run_types_property(self):
        """canonical_run_types returns immutable frozenset."""
        validator = RunTypeValidator()
        canonical = validator.canonical_run_types
        assert isinstance(canonical, frozenset)
        assert "context.compile" in canonical
