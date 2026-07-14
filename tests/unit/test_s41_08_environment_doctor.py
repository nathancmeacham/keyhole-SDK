"""S41-08 - Environment Doctor & Minimal Repair Guidance test suite.

Tests cover:
  - Contract types & schema validation
  - Environment fact collection (with mocks)
  - Structured diagnostics (determinism, mode awareness)
  - Root-failure clustering
  - Minimal repair plan computation
  - Repair JSON machine-readability
  - Verification-after-repair
  - Attestation
  - Handler orchestration
  - No-hidden-mutation invariant
  - CLI command wiring
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

# -- Make CLI package importable ------------------------------
CLI_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-cli"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))

from keyhole_cli.doctor.contract import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DOCTOR_INVARIANTS,
    DOCTOR_SCHEMA_VERSION,
    DiagnosticResult,
    DoctorAttestation,
    DoctorVerdict,
    EnvironmentFacts,
    MAX_PYTHON_VERSION,
    MIN_PYTHON_VERSION,
    OperatingMode,
    ReasonCode,
    RepairAuthority,
    RepairJson,
    RepairPlan,
    RepairStep,
    RepairStepKind,
    RootFailureGroup,
    SUPPORTED_PLATFORMS,
    VerificationResult,
    _canonical_json,
    _deterministic_digest,
)
from keyhole_cli.doctor.diagnostics import (
    check_cli_installed,
    check_compose_available,
    check_docker_available,
    check_mcp_config,
    check_platform,
    check_python_available,
    check_python_version,
    check_runtime_reachable,
    check_runtime_running,
    check_sdk_runtime_compatibility,
    run_diagnostics,
)
from keyhole_cli.doctor.facts import (
    build_facts_from_overrides,
    collect_environment_facts,
)
from keyhole_cli.doctor.root_cause import (
    annotate_diagnostic_with_roots,
    compute_root_failures,
)
from keyhole_cli.doctor.repair_plan import compute_repair_plan
from keyhole_cli.doctor.verify import verify_after_repair
from keyhole_cli.doctor.attestation import (
    build_attestation_event,
    build_doctor_attestation,
)
from keyhole_cli.doctor.handler import (
    run_doctor_evaluation,
    run_doctor_verify,
)
from keyhole_cli.commands.doctor import run_doctor
from keyhole_cli.result import EXIT_SUCCESS, EXIT_FAILURE


# --------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------


def _healthy_facts(**overrides: Any) -> EnvironmentFacts:
    """Return a fully healthy EnvironmentFacts for testing."""
    defaults = dict(
        platform="linux",
        python_available=True,
        python_version="3.11.5",
        python_version_tuple=(3, 11, 5),
        docker_available=True,
        docker_version="Docker version 24.0.6",
        compose_available=True,
        compose_version="Docker Compose version v2.21.0",
        cli_installed=True,
        cli_version="0.1.2",
        sdk_installed=True,
        sdk_version="0.1.2",
        runtime_running=True,
        runtime_reachable=True,
        runtime_url="http://localhost:8080",
        runtime_version="0.1.2",
        mcp_config_present=True,
        mcp_config_path="~/.keyhole/mcp.json",
        pipx_available=True,
        is_wsl=False,
        os_family="linux",
        shell="bash",
    )
    defaults.update(overrides)
    return build_facts_from_overrides(**defaults)


def _broken_facts(**overrides: Any) -> EnvironmentFacts:
    """Return an unhealthy EnvironmentFacts for testing."""
    defaults = dict(
        platform="linux",
        python_available=True,
        python_version="3.11.5",
        python_version_tuple=(3, 11, 5),
        docker_available=False,
        docker_version="",
        compose_available=False,
        compose_version="",
        cli_installed=False,
        cli_version="",
        sdk_installed=False,
        sdk_version="",
        runtime_running=False,
        runtime_reachable=False,
        runtime_url="",
        runtime_version="",
        mcp_config_present=False,
        mcp_config_path="",
        pipx_available=False,
        is_wsl=False,
        os_family="linux",
        shell="bash",
    )
    defaults.update(overrides)
    return build_facts_from_overrides(**defaults)


# --------------------------------------------------------------
# S41-08-INV-01 - Contract types & schema validation
# --------------------------------------------------------------


class TestContractTypes:
    """Contract types must be well-formed and deterministic."""

    def test_doctor_invariants_count(self):
        assert len(DOCTOR_INVARIANTS) == 8

    def test_schema_version(self):
        assert DOCTOR_SCHEMA_VERSION == "environment-doctor/v1.0"

    def test_supported_platforms(self):
        assert "linux" in SUPPORTED_PLATFORMS
        assert "darwin" in SUPPORTED_PLATFORMS
        assert "win32" in SUPPORTED_PLATFORMS

    def test_python_version_range(self):
        assert MIN_PYTHON_VERSION == (3, 9)
        assert MAX_PYTHON_VERSION == (3, 13)

    def test_environment_facts_to_dict(self):
        facts = _healthy_facts()
        d = facts.to_dict()
        assert d["platform"] == "linux"
        assert d["docker_available"] is True
        assert isinstance(d["python_version_tuple"], list)

    def test_check_result_to_dict(self):
        cr = CheckResult(
            check_name="test",
            category="platform",
            status="pass",
        )
        d = cr.to_dict()
        assert d["check_name"] == "test"
        assert d["status"] == "pass"

    def test_canonical_json_deterministic(self):
        d = {"b": 2, "a": 1, "c": [3, 1]}
        j1 = _canonical_json(d)
        j2 = _canonical_json(d)
        assert j1 == j2
        # Keys must be sorted
        parsed = json.loads(j1)
        assert list(parsed.keys()) == ["a", "b", "c"]

    def test_deterministic_digest(self):
        d = {"x": 1}
        h1 = _deterministic_digest(d)
        h2 = _deterministic_digest(d)
        assert h1 == h2
        assert len(h1) == 64

    def test_reason_codes_complete(self):
        assert len(ReasonCode) >= 24

    def test_operating_modes(self):
        assert OperatingMode.LOCAL_ONLY.value == "local_only"
        assert OperatingMode.GOVERNED.value == "governed"

    def test_repair_step_kinds(self):
        kinds = {k.value for k in RepairStepKind}
        assert "command" in kinds
        assert "install" in kinds
        assert "doc_link" in kinds


# --------------------------------------------------------------
# S41-08-INV-02 - Structured diagnostic evaluation
# --------------------------------------------------------------


class TestDiagnostics:
    """Diagnostics must produce structured, deterministic results."""

    def test_healthy_env_passes_all(self):
        facts = _healthy_facts()
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        assert result.final_posture == DoctorVerdict.ACCEPT.value
        for c in result.check_results:
            assert c.status in (CheckStatus.PASS.value, CheckStatus.SKIP.value)

    def test_healthy_governed_passes(self):
        facts = _healthy_facts()
        result = run_diagnostics(facts, OperatingMode.GOVERNED)
        assert result.final_posture == DoctorVerdict.ACCEPT.value

    def test_missing_docker_fails(self):
        facts = _healthy_facts(docker_available=False)
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        assert result.final_posture == DoctorVerdict.REJECT.value
        docker_check = [
            c for c in result.check_results if c.check_name == "docker_available"
        ][0]
        assert docker_check.status == CheckStatus.FAIL.value

    def test_compose_fails_when_docker_missing(self):
        facts = _healthy_facts(docker_available=False, compose_available=False)
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        compose_check = [
            c for c in result.check_results if c.check_name == "compose_available"
        ][0]
        assert compose_check.status == CheckStatus.FAIL.value
        assert compose_check.downstream_of == "docker_available"

    def test_unsupported_platform_fails(self):
        facts = _healthy_facts(platform="freebsd")
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        assert result.final_posture == DoctorVerdict.REJECT.value

    def test_python_version_below_min(self):
        facts = _healthy_facts(python_version="3.8.1", python_version_tuple=(3, 8, 1))
        cr = check_python_version(facts)
        assert cr.status == CheckStatus.FAIL.value

    def test_python_version_above_max(self):
        facts = _healthy_facts(python_version="3.14.0", python_version_tuple=(3, 14, 0))
        cr = check_python_version(facts)
        assert cr.status == CheckStatus.FAIL.value

    def test_python_version_at_min(self):
        facts = _healthy_facts(python_version="3.9.0", python_version_tuple=(3, 9, 0))
        cr = check_python_version(facts)
        assert cr.status == CheckStatus.PASS.value

    def test_python_version_at_max(self):
        facts = _healthy_facts(python_version="3.13.0", python_version_tuple=(3, 13, 0))
        cr = check_python_version(facts)
        assert cr.status == CheckStatus.PASS.value

    def test_cli_not_installed(self):
        facts = _healthy_facts(cli_installed=False, cli_version="")
        cr = check_cli_installed(facts)
        assert cr.status == CheckStatus.FAIL.value

    def test_mcp_config_skip_local_only(self):
        facts = _healthy_facts(mcp_config_present=False)
        cr = check_mcp_config(facts, OperatingMode.LOCAL_ONLY)
        assert cr.status == CheckStatus.SKIP.value

    def test_mcp_config_required_governed(self):
        facts = _healthy_facts(mcp_config_present=False)
        cr = check_mcp_config(facts, OperatingMode.GOVERNED)
        assert cr.status == CheckStatus.FAIL.value

    def test_sdk_compatibility_skip_no_sdk(self):
        facts = _healthy_facts(sdk_installed=False)
        cr = check_sdk_runtime_compatibility(facts)
        assert cr.status == CheckStatus.SKIP.value

    def test_sdk_compatibility_mismatch(self):
        facts = _healthy_facts(sdk_version="0.2.0", runtime_version="0.1.0")
        cr = check_sdk_runtime_compatibility(facts)
        assert cr.status == CheckStatus.FAIL.value

    def test_diagnostic_result_to_dict(self):
        facts = _healthy_facts()
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        d = result.to_dict()
        assert "schema_version" in d
        assert d["schema_version"] == DOCTOR_SCHEMA_VERSION
        assert "check_results" in d
        assert isinstance(d["check_results"], list)

    def test_no_hidden_mutation_reason_code(self):
        facts = _healthy_facts()
        result = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        assert ReasonCode.NO_HIDDEN_MUTATION_ENFORCED.value in result.reason_codes

    def test_determinism_same_input_same_output(self):
        facts = _healthy_facts()
        r1 = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        r2 = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        assert r1.final_posture == r2.final_posture
        assert len(r1.check_results) == len(r2.check_results)
        for c1, c2 in zip(r1.check_results, r2.check_results):
            assert c1.check_name == c2.check_name
            assert c1.status == c2.status


# --------------------------------------------------------------
# S41-08-INV-03 - Root-failure clustering
# --------------------------------------------------------------


class TestRootFailureClustering:
    """Root failures must be correctly identified, downstream symptoms grouped."""

    def test_no_root_failures_when_healthy(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        groups = compute_root_failures(diag)
        assert len(groups) == 0

    def test_docker_root_clusters_compose(self):
        facts = _broken_facts(docker_available=False, compose_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        docker_groups = [
            g for g in diag.root_failure_groups
            if g.root_check == "docker_available"
        ]
        assert len(docker_groups) == 1
        assert "compose_available" in docker_groups[0].downstream_checks

    def test_single_failure_is_root(self):
        facts = _healthy_facts(cli_installed=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        roots = [g for g in diag.root_failure_groups]
        assert len(roots) == 1
        assert roots[0].root_check == "cli_installed"

    def test_annotate_marks_root_and_downstream(self):
        facts = _broken_facts(docker_available=False, compose_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        docker_check = [
            c for c in diag.check_results if c.check_name == "docker_available"
        ][0]
        compose_check = [
            c for c in diag.check_results if c.check_name == "compose_available"
        ][0]
        assert docker_check.is_root is True
        assert compose_check.downstream_of == "docker_available"

    def test_root_failure_reason_code_added(self):
        facts = _broken_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        assert ReasonCode.DOCTOR_ROOT_FAILURE_IDENTIFIED.value in diag.reason_codes


# --------------------------------------------------------------
# S41-08-INV-04 - Minimal repair plan computation
# --------------------------------------------------------------


class TestRepairPlan:
    """Repair plans must be minimal, ordered, and role-safe."""

    def test_no_repair_when_healthy(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        assert len(plan.steps) == 0

    def test_docker_failure_produces_install_step(self):
        facts = _healthy_facts(docker_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        docker_steps = [
            s for s in plan.steps
            if s.addresses_reason_code == ReasonCode.DOCTOR_DOCKER_UNAVAILABLE.value
        ]
        assert len(docker_steps) == 1
        assert docker_steps[0].kind == RepairStepKind.INSTALL.value

    def test_repair_targets_root_only(self):
        """Downstream compose failure should NOT produce a separate step
        when docker is the root cause."""
        facts = _healthy_facts(docker_available=False, compose_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        compose_steps = [
            s for s in plan.steps
            if s.addresses_reason_code == ReasonCode.DOCTOR_COMPOSE_UNAVAILABLE.value
        ]
        assert len(compose_steps) == 0

    def test_repair_steps_ordered(self):
        facts = _broken_facts(cli_installed=False, docker_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        orders = [s.order for s in plan.steps]
        assert orders == sorted(orders)

    def test_admin_authority_noted(self):
        facts = _healthy_facts(docker_available=False)
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        docker_step = [
            s for s in plan.steps
            if s.addresses_reason_code == ReasonCode.DOCTOR_DOCKER_UNAVAILABLE.value
        ][0]
        assert docker_step.authority == RepairAuthority.ADMIN.value

    def test_verification_steps_present(self):
        facts = _broken_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        assert len(plan.verification_steps) > 0

    def test_plan_has_id(self):
        facts = _broken_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        diag = annotate_diagnostic_with_roots(diag)
        plan = compute_repair_plan(diag)
        assert plan.plan_id.startswith("repair-")


# --------------------------------------------------------------
# S41-08-INV-05 - Machine-readable repair JSON
# --------------------------------------------------------------


class TestRepairJson:
    """Repair JSON must be fully machine-readable and parseable."""

    def test_repair_json_structure(self):
        rj = RepairJson(
            mode="local_only",
            reason_codes=["DOCTOR_CLI_NOT_INSTALLED"],
            steps=[{"step_id": "step-1", "kind": "command"}],
        )
        d = rj.to_dict()
        assert d["doctor_version"] == DOCTOR_SCHEMA_VERSION
        assert isinstance(d["steps"], list)
        assert d["mode"] == "local_only"

    def test_repair_json_is_valid_json(self):
        rj = RepairJson(mode="local_only", reason_codes=["X"])
        s = json.dumps(rj.to_dict())
        parsed = json.loads(s)
        assert parsed["mode"] == "local_only"

    def test_handler_produces_repair_json_on_failure(self):
        facts = _broken_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["repair_json"] is not None
        rj = result["repair_json"]
        assert "steps" in rj
        assert "reason_codes" in rj

    def test_handler_no_repair_json_on_success(self):
        facts = _healthy_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["repair_json"] is None


# --------------------------------------------------------------
# S41-08-INV-06 - Verification-after-repair
# --------------------------------------------------------------


class TestVerification:
    """Verification checks must compare before/after state."""

    def test_verified_when_healthy(self):
        facts = _healthy_facts()
        vr = verify_after_repair(facts, OperatingMode.LOCAL_ONLY)
        assert vr.verified is True
        assert vr.checks_failed == 0

    def test_not_verified_when_broken(self):
        facts = _broken_facts()
        vr = verify_after_repair(facts, OperatingMode.LOCAL_ONLY)
        assert vr.verified is False
        assert vr.checks_failed > 0

    def test_remaining_failures_listed(self):
        facts = _healthy_facts(docker_available=False)
        vr = verify_after_repair(facts, OperatingMode.LOCAL_ONLY)
        assert "docker_available" in vr.remaining_failures

    def test_verification_result_has_id(self):
        facts = _healthy_facts()
        vr = verify_after_repair(facts, OperatingMode.LOCAL_ONLY)
        assert vr.verification_id.startswith("verify-")


# --------------------------------------------------------------
# S41-08-INV-07 - Attestation
# --------------------------------------------------------------


class TestAttestation:
    """Doctor attestation must capture final truth."""

    def test_accept_attestation_on_healthy(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(diagnostic=diag)
        assert att.final_outcome == DoctorVerdict.ACCEPT.value
        assert ReasonCode.DOCTOR_TRUTH_ACCEPTED.value in att.reason_codes

    def test_reject_attestation_on_broken(self):
        facts = _broken_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(diagnostic=diag)
        assert att.final_outcome == DoctorVerdict.REJECT.value
        assert ReasonCode.DOCTOR_TRUTH_REJECTED.value in att.reason_codes

    def test_attestation_with_verification(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        vr = verify_after_repair(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(
            diagnostic=diag, verification=vr
        )
        assert att.final_outcome == DoctorVerdict.ACCEPT.value
        assert ReasonCode.REPAIR_VERIFICATION_PASSED.value in att.reason_codes

    def test_attestation_event_structure(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(diagnostic=diag)
        evt = build_attestation_event(att)
        assert evt["schema"].startswith("keyhole/")
        assert "attestation_digest" in evt
        assert len(evt["attestation_digest"]) == 64

    def test_attestation_has_id(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(diagnostic=diag)
        assert att.attestation_id.startswith("doc-att-")

    def test_no_hidden_mutation_in_attestation(self):
        facts = _healthy_facts()
        diag = run_diagnostics(facts, OperatingMode.LOCAL_ONLY)
        att = build_doctor_attestation(diagnostic=diag)
        assert ReasonCode.NO_HIDDEN_MUTATION_ENFORCED.value in att.reason_codes


# --------------------------------------------------------------
# S41-08-INV-08 - Handler orchestration
# --------------------------------------------------------------


class TestHandler:
    """Handler must orchestrate the full pipeline correctly."""

    def test_healthy_evaluation(self):
        facts = _healthy_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["ok"] is True
        assert result["verdict"] == DoctorVerdict.ACCEPT.value
        assert result["repair_plan"] is None

    def test_broken_evaluation(self):
        facts = _broken_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["ok"] is False
        assert result["verdict"] == DoctorVerdict.REJECT.value
        assert result["repair_plan"] is not None
        assert len(result["repair_plan"]["steps"]) > 0

    def test_evaluation_includes_root_groups(self):
        facts = _broken_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert len(result["root_failure_groups"]) > 0

    def test_evaluation_includes_attestation(self):
        facts = _healthy_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["attestation"] is not None
        assert result["attestation"]["final_outcome"] == DoctorVerdict.ACCEPT.value

    def test_verify_healthy(self):
        facts = _healthy_facts()
        result = run_doctor_verify(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["ok"] is True
        assert result["verification"]["verified"] is True

    def test_verify_broken(self):
        facts = _broken_facts()
        result = run_doctor_verify(facts, mode=OperatingMode.LOCAL_ONLY)
        assert result["ok"] is False
        assert result["verification"]["verified"] is False

    def test_evaluation_governed_mode(self):
        facts = _healthy_facts()
        result = run_doctor_evaluation(facts, mode=OperatingMode.GOVERNED)
        assert result["mode"] == "governed"
        assert result["ok"] is True


# --------------------------------------------------------------
# S41-08-INV-09 - CLI command integration
# --------------------------------------------------------------


class TestCLICommand:
    """CLI wiring must work and produce CommandResult."""

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    def test_doctor_local_pass(self, mock_facts):
        mock_facts.return_value = _healthy_facts()
        result = run_doctor(mode="local_only")
        assert result.success is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.command == "doctor"

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    def test_doctor_local_fail(self, mock_facts):
        mock_facts.return_value = _broken_facts()
        result = run_doctor(mode="local_only")
        assert result.success is False
        assert result.exit_code == EXIT_FAILURE

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    def test_doctor_verify_mode(self, mock_facts):
        mock_facts.return_value = _healthy_facts()
        result = run_doctor(mode="local_only", verify=True)
        assert result.success is True

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    def test_doctor_json_output(self, mock_facts):
        mock_facts.return_value = _healthy_facts()
        result = run_doctor(mode="local_only")
        d = result.to_dict()
        s = json.dumps(d)
        parsed = json.loads(s)
        assert "command" in parsed
        assert parsed["command"] == "doctor"

    @patch("keyhole_cli.commands.doctor.collect_environment_facts")
    def test_doctor_repair_next_steps(self, mock_facts):
        mock_facts.return_value = _broken_facts()
        result = run_doctor(mode="local_only")
        assert len(result.next_steps) > 0


# --------------------------------------------------------------
# S41-08-INV-10 - Facts collection (mocked)
# --------------------------------------------------------------


class TestFactsCollection:
    """Fact collection must read system state without mutation."""

    def test_build_facts_from_overrides(self):
        facts = build_facts_from_overrides(
            platform="darwin",
            python_available=True,
            python_version="3.12.0",
            python_version_tuple=(3, 12, 0),
        )
        assert facts.platform == "darwin"
        assert facts.python_available is True

    @patch("keyhole_cli.doctor.facts._run_cmd")
    @patch("keyhole_cli.doctor.facts.shutil.which")
    def test_collect_skips_runtime_check(self, mock_which, mock_cmd):
        mock_cmd.return_value = None
        mock_which.return_value = None
        facts = collect_environment_facts(skip_runtime_check=True)
        assert facts.python_available is True
        assert facts.runtime_running is False

    @patch("keyhole_cli.doctor.facts._run_cmd")
    @patch("keyhole_cli.doctor.facts.shutil.which")
    def test_collect_detects_platform(self, mock_which, mock_cmd):
        mock_cmd.return_value = None
        mock_which.return_value = None
        facts = collect_environment_facts(skip_runtime_check=True)
        assert facts.platform != ""
        assert facts.os_family != ""
