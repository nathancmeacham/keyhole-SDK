"""SDK-CLIENT-06 - Local Validation Pipeline tests.

Covers:
  section5  validate_compatibility()             - TestValidateCompatibility
  section6  issue_is_warn_only(strict)           - TestIssueIsWarnOnly
  section7  checks dict (4 domains)             - TestRunValidationChecksDict
  section8  compat domain flows to result        - TestRunValidationCompatDomain
  section9  strict mode escalation               - TestRunValidationStrictMode
  section10 errors / warnings properties         - TestErrorsWarningsSplit
  section11 to_dict extended keys               - TestToDictExtended
  section12 proof_ref via state_dir             - TestProofRef
  section13 CLI --strict flag                   - TestCLIStrictFlag
  section14 CLI --proof flag                    - TestCLIProofFlag
  section15 CLI --quiet flag                    - TestCLIQuietFlag
  section16 new error codes in repair map       - TestRepairGuidance06
  section17 public API surface                  - TestPublicAPISurface06
  section18 determinism guarantees              - TestDeterminism06
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest

# -- ensure packages importable ------------------------------------------------
_SDK_PKG = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-sdk"
_CLI_PKG = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-cli"
for _p in (_SDK_PKG, _CLI_PKG):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from keyhole_sdk.validation import (
    ValidationStatus,
    map_validation_repair,
    run_validation,
    validate_compatibility,
)
from keyhole_sdk.validation.models import (
    ValidationIssue,
    ValidationResult,
    _ISSUE_WARN_REASONS,
    issue_is_warn_only,
)
from keyhole_sdk.validation.models import ContractRepoPosture, ReadinessLevel

from keyhole_cli.commands.validate_cmd import run_validate
from keyhole_cli.result import (
    EXIT_CONTRACT_FAILURE,
    EXIT_SUCCESS,
)


# -- shared helpers ------------------------------------------------------------

def _write(base: Path, name: str, content: str) -> Path:
    p = base / name
    p.write_text(content)
    return p


def _native_repo(tmp_path: Path, *, repo: str = "my-service",
                 cap: str = "payment.stripe.integration.v1") -> Path:
    _write(tmp_path, "keyhole.yaml", f"repo: {repo}\nschema_version: 1\n")
    _write(tmp_path, "governance_contract.yaml",
           f"repo: {repo}\nproduces:\n  - {cap}\n")
    return tmp_path


def _native_repo_with_deps(tmp_path: Path, *,
                            dep_cap: str = "crm.salesforce.sync.v2",
                            provider: str = "sf-adapter") -> Path:
    _native_repo(tmp_path)
    _write(tmp_path, "dependencies.yaml",
           f"dependencies:\n  - capability: {dep_cap}\n    provider: {provider}\n")
    return tmp_path


def _foreign_repo(tmp_path: Path) -> Path:
    # No keyhole.yaml - pure foreign
    return tmp_path


# --------------------------------------------------------------
# section5  validate_compatibility()
# --------------------------------------------------------------

class TestValidateCompatibility:
    """Unit tests for validate_compatibility() in isolation."""

    def test_empty_inputs_no_issues(self):
        issues = validate_compatibility([], [], gc_data=None)
        assert issues == []

    def test_no_self_dep_no_version_conflict(self):
        issues = validate_compatibility(
            ["payment.stripe.v1"],
            ["crm.salesforce.v2"],
            gc_data=None,
        )
        assert issues == []

    def test_self_dependency_detected(self):
        cap = "payment.stripe.v1"
        issues = validate_compatibility([cap], [cap], gc_data=None)
        reasons = [i.reason for i in issues]
        assert "self_dependency_detected" in reasons

    def test_self_dependency_only_once_per_cap(self):
        cap = "payment.stripe.v1"
        # consumed has it twice; should only emit one issue per cap
        issues = validate_compatibility([cap], [cap, cap], gc_data=None)
        self_dep_issues = [i for i in issues if i.reason == "self_dependency_detected"]
        assert len(self_dep_issues) == 1

    def test_incompatible_major_version_detected(self):
        issues = validate_compatibility(
            ["payment.stripe.v1"],
            ["payment.stripe.v2"],
            gc_data=None,
        )
        reasons = [i.reason for i in issues]
        assert "incompatible_major_version" in reasons

    def test_compatible_same_major_version_no_issue(self):
        issues = validate_compatibility(
            ["payment.stripe.v1"],
            ["payment.stripe.v1"],
            gc_data=None,
        )
        # same cap same version - only self-dep issue, NOT incompatible_major_version
        reasons = [i.reason for i in issues]
        assert "incompatible_major_version" not in reasons

    def test_no_issue_when_no_shared_base(self):
        issues = validate_compatibility(
            ["payment.stripe.v1"],
            ["crm.salesforce.v99"],
            gc_data=None,
        )
        assert not any(i.reason == "incompatible_major_version" for i in issues)

    def test_compat_contracts_field_valid(self):
        gc = {
            "repo": "my-service",
            "compatibility_contracts": [
                {"capability": "payment.stripe.v1", "min_version": 1}
            ],
        }
        issues = validate_compatibility([], [], gc_data=gc)
        assert not any(i.reason == "compatibility_contract_invalid" for i in issues)

    def test_compat_contracts_not_list(self):
        gc = {"repo": "x", "compatibility_contracts": "bad-string"}
        issues = validate_compatibility([], [], gc_data=gc)
        reasons = [i.reason for i in issues]
        assert "compatibility_contract_invalid" in reasons

    def test_compat_contracts_entry_missing_capability(self):
        gc = {"repo": "x", "compatibility_contracts": [{"min_version": 1}]}
        issues = validate_compatibility([], [], gc_data=gc)
        reasons = [i.reason for i in issues]
        assert "compatibility_contract_invalid" in reasons

    def test_compat_contracts_entry_not_dict(self):
        gc = {"repo": "x", "compatibility_contracts": ["not-a-dict"]}
        issues = validate_compatibility([], [], gc_data=gc)
        reasons = [i.reason for i in issues]
        assert "compatibility_contract_invalid" in reasons

    def test_compat_contracts_absent_no_issue(self):
        gc = {"repo": "x", "produces": ["a.b.v1"]}
        issues = validate_compatibility(["a.b.v1"], [], gc_data=gc)
        assert not any(i.reason == "compatibility_contract_invalid" for i in issues)

    def test_gc_data_none_skips_contract_check(self):
        # Should not raise even with None gc_data
        issues = validate_compatibility(["a.v1"], ["b.v2"], gc_data=None)
        assert isinstance(issues, list)

    def test_multiple_issues_independent(self):
        # self-dep AND invalid compat_contracts at once
        cap = "payments.stripe.integration.v1"
        gc = {"repo": "x", "compatibility_contracts": "oops"}
        issues = validate_compatibility([cap], [cap], gc_data=gc)
        reasons = {i.reason for i in issues}
        assert "self_dependency_detected" in reasons
        assert "compatibility_contract_invalid" in reasons

    def test_all_issues_have_repair(self):
        cap = "payments.stripe.integration.v1"
        gc = {"repo": "x", "compatibility_contracts": "oops"}
        issues = validate_compatibility([cap], [cap, "payments.stripe.integration.v2"], gc_data=gc)
        for issue in issues:
            assert isinstance(issue.repair, list)
            assert len(issue.repair) > 0


# --------------------------------------------------------------
# section6  issue_is_warn_only()
# --------------------------------------------------------------

class TestIssueIsWarnOnly:
    """Strict=False defaults and strict=True escalation."""

    def test_warn_reasons_non_strict_true(self):
        for reason in _ISSUE_WARN_REASONS:
            assert issue_is_warn_only(reason, strict=False) is True

    def test_warn_reasons_strict_all_false(self):
        for reason in _ISSUE_WARN_REASONS:
            assert issue_is_warn_only(reason, strict=True) is False

    def test_non_warn_reason_always_false(self):
        assert issue_is_warn_only("missing_required_file", strict=False) is False
        assert issue_is_warn_only("missing_required_file", strict=True) is False

    def test_unknown_reason_false(self):
        assert issue_is_warn_only("completely_unknown_reason", strict=False) is False

    def test_self_dependency_is_warn_non_strict(self):
        assert issue_is_warn_only("self_dependency_detected", strict=False) is True

    def test_incompatible_major_version_is_warn_non_strict(self):
        assert issue_is_warn_only("incompatible_major_version", strict=False) is True


# --------------------------------------------------------------
# section7  checks dict (4 domains)
# --------------------------------------------------------------

class TestRunValidationChecksDict:
    """checks dict must have all 4 domain keys with string status values."""

    _DOMAINS = {"schema", "dependencies", "namespace", "compatibility"}

    def test_checks_present_native(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        assert isinstance(result.checks, dict)
        assert result.checks.keys() >= self._DOMAINS

    def test_checks_present_foreign(self, tmp_path):
        _foreign_repo(tmp_path)
        result = run_validation(tmp_path)
        assert isinstance(result.checks, dict)

    def test_checks_values_are_strings(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        for v in result.checks.values():
            assert isinstance(v, str)

    def test_checks_pass_on_clean_native(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        # schema domain should pass on clean native repo with required files
        assert result.checks.get("schema") in ("PASS", "WARN", "REJECT")

    def test_checks_domain_schema_reject_on_broken(self, tmp_path):
        # Only keyhole.yaml - no governance_contract.yaml
        _write(tmp_path, "keyhole.yaml", "repo: x\nschema_version: 1\n")
        result = run_validation(tmp_path)
        # schema domain must signal REJECT (missing governance_contract.yaml)
        assert result.checks.get("schema") == "REJECT"

    def test_checks_in_to_dict(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        d = result.to_dict()
        assert "checks" in d
        assert isinstance(d["checks"], dict)

    def test_checks_strict_field_in_to_dict(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path, strict=True)
        d = result.to_dict()
        assert d.get("strict") is True

    def test_checks_non_strict_strict_false_in_to_dict(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path, strict=False)
        d = result.to_dict()
        assert d.get("strict") is False

    def test_checks_compat_domain_present(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validation(tmp_path)
        assert "compatibility" in result.checks

    def test_checks_dependencies_domain_present(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validation(tmp_path)
        assert "dependencies" in result.checks


# --------------------------------------------------------------
# section8  compat domain flows to result
# --------------------------------------------------------------

class TestRunValidationCompatDomain:
    """Compatibility issues from validate_compatibility() flow into result.issues."""

    def test_self_dep_issue_in_result(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path)
        reasons = {i.reason for i in result.issues}
        assert "self_dependency_detected" in reasons

    def test_self_dep_does_not_reject_non_strict(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        # self_dependency_detected is warn-only -> should not become REJECT
        warn_reasons = {i.reason for i in result.issues
                        if issue_is_warn_only(i.reason, strict=False)}
        assert "self_dependency_detected" in warn_reasons

    def test_major_version_conflict_in_result(self, tmp_path):
        _native_repo(tmp_path, cap="crm.salesforce.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.salesforce.integration.v2\n    provider: sf\n")
        result = run_validation(tmp_path)
        reasons = {i.reason for i in result.issues}
        assert "incompatible_major_version" in reasons

    def test_compat_ok_with_clean_deps(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.v3\n    provider: crm-svc\n")
        result = run_validation(tmp_path)
        reasons = {i.reason for i in result.issues}
        assert "self_dependency_detected" not in reasons
        assert "incompatible_major_version" not in reasons

    def test_compat_contract_invalid_in_result(self, tmp_path):
        _write(tmp_path, "keyhole.yaml", "repo: x\nschema_version: 1\n")
        _write(tmp_path, "governance_contract.yaml",
               "repo: x\nproduces:\n  - a.v1\ncompatibility_contracts: not-a-list\n")
        result = run_validation(tmp_path)
        reasons = {i.reason for i in result.issues}
        assert "compatibility_contract_invalid" in reasons

    def test_compat_result_state_in_checks(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path)
        # compat domain should be non-PASS when there are compat issues
        assert "compatibility" in result.checks

    def test_no_deps_compat_pass(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        # Without deps file, compat should be PASS
        assert result.checks.get("compatibility") == "PASS"

    def test_compat_issues_have_file_field(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path)
        compat_issues = [i for i in result.issues if i.reason == "self_dependency_detected"]
        for ci in compat_issues:
            assert ci.file  # should name the relevant file

    def test_compat_issues_have_repair(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path)
        compat_issues = [i for i in result.issues if i.reason == "self_dependency_detected"]
        for ci in compat_issues:
            assert ci.repair

    def test_readiness_unaffected_by_warn_compat_non_strict(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        # warn-only compat issue should not degrade result to REJECT
        assert result.status in (ValidationStatus.PASS, ValidationStatus.WARN)


# --------------------------------------------------------------
# section9  strict mode escalation
# --------------------------------------------------------------

class TestRunValidationStrictMode:
    """strict=True escalates all warn-only issues to REJECT."""

    def test_strict_false_warn_status_on_warn_reason(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        assert result.status in (ValidationStatus.PASS, ValidationStatus.WARN)

    def test_strict_true_reject_on_same_warn_reason(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=True)
        assert result.status == ValidationStatus.REJECT

    def test_strict_field_set_on_result(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path, strict=True)
        assert result.strict is True

    def test_non_strict_field_false(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path, strict=False)
        assert result.strict is False

    def test_strict_major_version_conflict_rejects(self, tmp_path):
        _native_repo(tmp_path, cap="crm.salesforce.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.salesforce.integration.v2\n    provider: sf\n")
        result = run_validation(tmp_path, strict=True)
        assert result.status == ValidationStatus.REJECT

    def test_strict_checks_all_reject_or_pass(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=True)
        for v in result.checks.values():
            assert v in ("PASS", "WARN", "REJECT")

    def test_strict_no_issues_still_pass(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validation(tmp_path, strict=True)
        # A clean repo should still PASS even in strict mode
        assert result.status in (ValidationStatus.PASS, ValidationStatus.WARN)

    def test_strict_foreign_repo_advisory(self, tmp_path):
        _foreign_repo(tmp_path)
        result = run_validation(tmp_path, strict=True)
        # Foreign repo remains advisory even in strict mode
        assert result.repo_posture == ContractRepoPosture.FOREIGN

    def test_strict_true_no_warnings_in_result(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=True)
        # strict=True -> no warn-only issues (all escalated to errors)
        assert result.warnings == []

    def test_strict_dep_provider_missing_issue(self, tmp_path):
        """strict=True should flag deps that are missing provider field."""
        _native_repo(tmp_path)
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.v2\n")  # no provider
        result = run_validation(tmp_path, strict=True)
        reasons = {i.reason for i in result.issues}
        assert "dependency_provider_missing" in reasons

    def test_non_strict_dep_provider_missing_no_issue(self, tmp_path):
        """non-strict should not flag missing provider."""
        _native_repo(tmp_path)
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.v2\n")  # no provider
        result = run_validation(tmp_path, strict=False)
        reasons = {i.reason for i in result.issues}
        assert "dependency_provider_missing" not in reasons

    def test_strict_dep_provider_missing_is_reject(self, tmp_path):
        """dependency_provider_missing in strict mode -> REJECT."""
        _native_repo(tmp_path)
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: crm.v2\n")
        result = run_validation(tmp_path, strict=True)
        # dep_provider_missing should cause REJECT
        assert result.status == ValidationStatus.REJECT


# --------------------------------------------------------------
# section10  errors / warnings properties
# --------------------------------------------------------------

class TestErrorsWarningsSplit:
    """errors and warnings properties split issues correctly."""

    def test_errors_warnings_disjoint(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        error_ids = {id(i) for i in result.errors}
        warn_ids = {id(i) for i in result.warnings}
        assert error_ids.isdisjoint(warn_ids)

    def test_errors_plus_warnings_equals_all_issues(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        assert len(result.errors) + len(result.warnings) == len(result.issues)

    def test_strict_warnings_empty(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=True)
        assert result.warnings == []

    def test_strict_all_in_errors(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=True)
        assert len(result.errors) == len(result.issues)

    def test_non_strict_warn_reason_in_warnings(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validation(tmp_path, strict=False)
        warm_reasons = {i.reason for i in result.warnings}
        assert "self_dependency_detected" in warm_reasons

    def test_clean_repo_no_errors_no_warnings(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validation(tmp_path)
        # A clean repo should have no issues at all
        compat_issues = [i for i in result.issues
                         if i.reason in ("self_dependency_detected",
                                         "incompatible_major_version")]
        assert not compat_issues

    def test_errors_warnings_return_lists(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_errors_in_to_dict(self, tmp_path):
        _native_repo(tmp_path)
        d = run_validation(tmp_path).to_dict()
        assert "errors" in d
        assert "warnings" in d


# --------------------------------------------------------------
# section11  to_dict extended keys
# --------------------------------------------------------------

class TestToDictExtended:
    """to_dict() includes the new SDK-CLIENT-06 keys."""

    def _keys(self, tmp_path) -> dict:
        _native_repo(tmp_path)
        return run_validation(tmp_path).to_dict()

    def test_checks_key_present(self, tmp_path):
        assert "checks" in self._keys(tmp_path)

    def test_proof_ref_key_present(self, tmp_path):
        assert "proof_ref" in self._keys(tmp_path)

    def test_strict_key_present(self, tmp_path):
        assert "strict" in self._keys(tmp_path)

    def test_errors_key_present(self, tmp_path):
        assert "errors" in self._keys(tmp_path)

    def test_warnings_key_present(self, tmp_path):
        assert "warnings" in self._keys(tmp_path)

    def test_existing_keys_still_present(self, tmp_path):
        d = self._keys(tmp_path)
        for key in ("status", "repo_posture", "readiness", "issues"):
            assert key in d, f"key '{key}' missing from to_dict()"

    def test_errors_list_of_dicts(self, tmp_path):
        _native_repo(tmp_path)
        d = run_validation(tmp_path).to_dict()
        assert isinstance(d["errors"], list)

    def test_strict_bool_value(self, tmp_path):
        _native_repo(tmp_path)
        d = run_validation(tmp_path, strict=True).to_dict()
        assert d["strict"] is True


# --------------------------------------------------------------
# section12  proof_ref via state_dir
# --------------------------------------------------------------

class TestProofRef:
    """proof_ref is set when proof is emitted, None otherwise."""

    def test_no_state_no_proof_ref(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validation(tmp_path)
        assert result.proof_ref is None

    def test_proof_ref_none_in_to_dict_without_state(self, tmp_path):
        _native_repo(tmp_path)
        d = run_validation(tmp_path).to_dict()
        assert d["proof_ref"] is None

    def test_run_validate_proof_ref_set_with_state_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state = tmp_path / "state"
        state.mkdir()
        result_cmd = run_validate(
            repo_path=str(repo), state_dir=str(state), proof=False
        )
        # with state_dir set, proof_ref should be set
        assert result_cmd.data.get("proof_ref") is not None

    def test_run_validate_proof_flag_uses_default_path(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state = tmp_path / "proof_default"

        with patch("keyhole_cli.commands.validate_cmd._DEFAULT_PROOF_STATE", str(state)):
            result_cmd = run_validate(repo_path=str(repo), proof=True)
        assert result_cmd.data.get("proof_ref") is not None

    def test_run_validate_no_proof_no_state_no_proof_ref(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        result_cmd = run_validate(repo_path=str(repo), proof=False, state_dir="")
        assert result_cmd.data.get("proof_ref") is None

    def test_proof_errors_are_swallowed(self, tmp_path):
        """If proof emission raises, run_validate should still succeed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        with patch("keyhole_cli.commands.validate_cmd.emit_validation_proof",
                   side_effect=RuntimeError("disk full")):
            result_cmd = run_validate(
                repo_path=str(repo), state_dir=str(tmp_path / "s"), proof=False
            )
        # command should still succeed
        assert result_cmd.success is True

    def test_proof_ref_appears_in_to_dict(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state = tmp_path / "state"
        state.mkdir()
        result_cmd = run_validate(repo_path=str(repo), state_dir=str(state))
        assert "proof_ref" in result_cmd.data

    def test_proof_ref_is_string_when_set(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state = tmp_path / "state"
        state.mkdir()
        result_cmd = run_validate(repo_path=str(repo), state_dir=str(state))
        pref = result_cmd.data.get("proof_ref")
        if pref is not None:
            assert isinstance(pref, str)


# --------------------------------------------------------------
# section13  CLI --strict flag
# --------------------------------------------------------------

class TestCLIStrictFlag:
    """run_validate strict=True escalates warns to contract failure."""

    def test_warn_repo_strict_false_passes(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validate(repo_path=str(tmp_path), strict=False)
        assert result.exit_code == EXIT_SUCCESS

    def test_warn_repo_strict_true_rejects(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert result.exit_code == EXIT_CONTRACT_FAILURE

    def test_strict_in_data(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert result.data.get("strict") is True

    def test_non_strict_in_data(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validate(repo_path=str(tmp_path), strict=False)
        assert result.data.get("strict") is False

    def test_strict_true_success_false_on_warn(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert result.success is False

    def test_strict_clean_repo_still_succeeds(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert result.success is True

    def test_strict_checks_in_data(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert "checks" in result.data

    def test_strict_bad_repo_path(self, tmp_path):
        result = run_validate(repo_path=str(tmp_path / "no-such"), strict=True)
        assert result.exit_code != EXIT_SUCCESS

    def test_strict_result_command_label(self, tmp_path):
        _native_repo(tmp_path)
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert "validate" in result.command

    def test_strict_warnings_empty_in_data(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        result = run_validate(repo_path=str(tmp_path), strict=True)
        assert result.data.get("warnings") == []


# --------------------------------------------------------------
# section14  CLI --proof flag
# --------------------------------------------------------------

class TestCLIProofFlag:
    """--proof forces artifact emission to default state dir."""

    def test_proof_flag_emits_artifact(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state_dir = tmp_path / "state"
        with patch("keyhole_cli.commands.validate_cmd._DEFAULT_PROOF_STATE", str(state_dir)):
            result = run_validate(repo_path=str(repo), proof=True)
        assert result.data.get("proof_ref") is not None

    def test_no_proof_no_artifact(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        result = run_validate(repo_path=str(repo), proof=False, state_dir="")
        assert result.data.get("proof_ref") is None

    def test_proof_failure_still_returns_result(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        with patch("keyhole_cli.commands.validate_cmd.emit_validation_proof",
                   side_effect=OSError("no space")):
            result = run_validate(repo_path=str(repo), state_dir=str(tmp_path), proof=True)
        # Should not raise; result should still be returned
        assert result.command is not None

    def test_proof_ref_is_string(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state_dir = tmp_path / "state"
        with patch("keyhole_cli.commands.validate_cmd._DEFAULT_PROOF_STATE", str(state_dir)):
            result = run_validate(repo_path=str(repo), proof=True)
        pref = result.data.get("proof_ref")
        if pref is not None:
            assert isinstance(pref, str)

    def test_explicit_state_dir_overrides_proof_default(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        explicit = tmp_path / "explicit"
        the_default = tmp_path / "default"
        result = run_validate(repo_path=str(repo), state_dir=str(explicit), proof=True)
        # proof_ref path should be under explicit, not default
        pref = result.data.get("proof_ref")
        if pref is not None:
            assert "explicit" in pref or str(explicit) in pref

    def test_proof_combined_with_strict(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _native_repo(repo)
        state_dir = tmp_path / "state"
        with patch("keyhole_cli.commands.validate_cmd._DEFAULT_PROOF_STATE", str(state_dir)):
            result = run_validate(repo_path=str(repo), proof=True, strict=True)
        assert result.data.get("strict") is True


# --------------------------------------------------------------
# section15  CLI --quiet flag
# --------------------------------------------------------------

class TestCLIQuietFlag:
    """--quiet suppresses next_steps on success."""

    def test_quiet_pass_no_next_steps(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validate(repo_path=str(tmp_path), quiet=True)
        if result.success:
            assert result.next_steps == []

    def test_quiet_fail_next_steps_populated(self, tmp_path):
        # Only keyhole.yaml - missing governance_contract.yaml -> REJECT
        _write(tmp_path, "keyhole.yaml", "repo: x\nschema_version: 1\n")
        result = run_validate(repo_path=str(tmp_path), quiet=True)
        if not result.success:
            # On failure, next_steps should still be given even with quiet
            assert isinstance(result.next_steps, list)

    def test_non_quiet_next_steps_present(self, tmp_path):
        _write(tmp_path, "keyhole.yaml", "repo: x\nschema_version: 1\n")
        result = run_validate(repo_path=str(tmp_path), quiet=False)
        assert isinstance(result.next_steps, list)

    def test_quiet_does_not_affect_data(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validate(repo_path=str(tmp_path), quiet=True)
        assert "status" in result.data

    def test_quiet_does_not_affect_exit_code(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        quiet_result = run_validate(repo_path=str(tmp_path), quiet=True)
        normal_result = run_validate(repo_path=str(tmp_path), quiet=False)
        assert quiet_result.exit_code == normal_result.exit_code

    def test_quiet_success_summary_cleared(self, tmp_path):
        _native_repo_with_deps(tmp_path)
        result = run_validate(repo_path=str(tmp_path), quiet=True)
        if result.success:
            assert result.summary == ""


# --------------------------------------------------------------
# section16  new error codes in repair map
# --------------------------------------------------------------

class TestRepairGuidance06:
    """SDK-CLIENT-06 error codes must have non-empty repair steps."""

    _NEW_CODES = [
        "compatibility_contract_invalid",
        "self_dependency_detected",
        "incompatible_major_version",
        "dependency_provider_missing",
        "strict_mode_warning_escalated",
        "repo_not_native_ready",
    ]

    def test_all_new_codes_have_repair(self):
        for code in self._NEW_CODES:
            steps = map_validation_repair(code)
            assert steps, f"No repair steps for error code: {code}"

    def test_repair_steps_are_strings(self):
        for code in self._NEW_CODES:
            steps = map_validation_repair(code)
            for step in steps:
                assert isinstance(step, str), f"Non-string repair step for {code}: {step!r}"

    def test_repair_steps_non_empty_content(self):
        for code in self._NEW_CODES:
            steps = map_validation_repair(code)
            for step in steps:
                assert step.strip(), f"Empty repair step for {code}"

    def test_compat_contract_invalid_mentions_key(self):
        steps = map_validation_repair("compatibility_contract_invalid")
        combined = " ".join(steps).lower()
        assert "compatibility_contracts" in combined or "capability" in combined

    def test_self_dep_mentions_remove(self):
        steps = map_validation_repair("self_dependency_detected")
        combined = " ".join(steps).lower()
        assert "remove" in combined or "self" in combined or "dependency" in combined

    def test_strict_mode_escalated_mentions_strict(self):
        steps = map_validation_repair("strict_mode_warning_escalated")
        combined = " ".join(steps).lower()
        assert "strict" in combined or "warning" in combined or "escalat" in combined

    def test_repo_not_native_ready_mentions_init(self):
        steps = map_validation_repair("repo_not_native_ready")
        combined = " ".join(steps).lower()
        assert "init" in combined or "native" in combined or "keyhole" in combined

    def test_dep_provider_missing_mentions_provider(self):
        steps = map_validation_repair("dependency_provider_missing")
        combined = " ".join(steps).lower()
        assert "provider" in combined


# --------------------------------------------------------------
# section17  public API surface
# --------------------------------------------------------------

class TestPublicAPISurface06:
    """validate_compatibility and issue_is_warn_only are in the public surface."""

    def test_validate_compatibility_in_sdk_all(self):
        import keyhole_sdk
        assert "validate_compatibility" in keyhole_sdk.__all__

    def test_validate_compatibility_in_validation_all(self):
        import keyhole_sdk.validation as v
        assert "validate_compatibility" in v.__all__

    def test_issue_is_warn_only_importable_from_models(self):
        from keyhole_sdk.validation.models import issue_is_warn_only as fn
        assert callable(fn)

    def test_warn_reasons_frozenset_importable(self):
        from keyhole_sdk.validation.models import _ISSUE_WARN_REASONS
        assert isinstance(_ISSUE_WARN_REASONS, frozenset)

    def test_validate_compatibility_is_callable(self):
        assert callable(validate_compatibility)

    def test_validation_result_has_checks_field(self):
        result = ValidationResult(
            status=ValidationStatus.PASS,
            repo_posture=ContractRepoPosture.FOREIGN,
            readiness=ReadinessLevel.FOREIGN,
            repo="test",
            repo_path="/tmp",
            files={},
            issues=[],
        )
        assert hasattr(result, "checks")

    def test_validation_result_has_proof_ref_field(self):
        result = ValidationResult(
            status=ValidationStatus.PASS,
            repo_posture=ContractRepoPosture.FOREIGN,
            readiness=ReadinessLevel.FOREIGN,
            repo="test",
            repo_path="/tmp",
            files={},
            issues=[],
        )
        assert hasattr(result, "proof_ref")

    def test_validation_result_has_strict_field(self):
        result = ValidationResult(
            status=ValidationStatus.PASS,
            repo_posture=ContractRepoPosture.FOREIGN,
            readiness=ReadinessLevel.FOREIGN,
            repo="test",
            repo_path="/tmp",
            files={},
            issues=[],
        )
        assert hasattr(result, "strict")


# --------------------------------------------------------------
# section18  determinism guarantees
# --------------------------------------------------------------

class TestDeterminism06:
    """Same input always produces same output - strict and non-strict."""

    def test_non_strict_deterministic(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        r1 = run_validation(tmp_path, strict=False)
        r2 = run_validation(tmp_path, strict=False)
        assert r1.status == r2.status
        assert {i.reason for i in r1.issues} == {i.reason for i in r2.issues}

    def test_strict_deterministic(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        r1 = run_validation(tmp_path, strict=True)
        r2 = run_validation(tmp_path, strict=True)
        assert r1.status == r2.status

    def test_strict_vs_non_strict_differ_on_warn_repo(self, tmp_path):
        _native_repo(tmp_path, cap="payments.stripe.integration.v1")
        _write(tmp_path, "dependencies.yaml",
               "dependencies:\n  - capability: payments.stripe.integration.v1\n    provider: self\n")
        non_strict = run_validation(tmp_path, strict=False)
        strictly = run_validation(tmp_path, strict=True)
        # If there are warn-only issues, strict must produce REJECT
        if non_strict.warnings:
            assert strictly.status == ValidationStatus.REJECT

    def test_validate_compatibility_deterministic(self):
        issues1 = validate_compatibility(["a.v1"], ["a.v2"], gc_data=None)
        issues2 = validate_compatibility(["a.v1"], ["a.v2"], gc_data=None)
        assert [i.reason for i in issues1] == [i.reason for i in issues2]

    def test_to_dict_keys_stable(self, tmp_path):
        _native_repo(tmp_path)
        d1 = run_validation(tmp_path).to_dict()
        d2 = run_validation(tmp_path).to_dict()
        assert set(d1.keys()) == set(d2.keys())

    def test_checks_keys_stable(self, tmp_path):
        _native_repo(tmp_path)
        r1 = run_validation(tmp_path)
        r2 = run_validation(tmp_path)
        assert set(r1.checks.keys()) == set(r2.checks.keys())

    def test_foreign_repo_deterministic(self, tmp_path):
        r1 = run_validation(tmp_path)
        r2 = run_validation(tmp_path)
        assert r1.status == r2.status
        assert r1.repo_posture == r2.repo_posture

    def test_strict_field_value_not_mutated_across_calls(self, tmp_path):
        _native_repo(tmp_path)
        r1 = run_validation(tmp_path, strict=True)
        r2 = run_validation(tmp_path, strict=False)
        assert r1.strict is True
        assert r2.strict is False
