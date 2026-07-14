"""Tests for CE-V5-S42-08 - Proof-Ready Participant Scaffolding.

Validates all 7 acceptance criteria:

AC-1: developer kit contains explicit proof-ready scaffolding
AC-2: scaffolding is clearly marked as boundary-consuming, not boundary-defining
AC-3: no unstable platform internals are hardcoded
AC-4: future integration points are isolated behind adapters
AC-5: verification runner scaffolding exists
AC-6: proof-bundle placeholder shape exists and is clearly marked provisional
AC-7: current supported flows remain clearly separated from proof-ready
      future flows; docs explain what is supported now versus scaffolded

Functional requirements:

FR-1: Explicit proof-ready scaffolding
FR-2: Boundary-consuming posture
FR-3: No unstable hardcoding
FR-4: Adapter isolation
FR-5: Supported vs future distinction
FR-6: Verification runner shape
FR-7: Proof placeholder shape
FR-8: Human and agent clarity
"""

from __future__ import annotations

import ast
import inspect
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
PROOF_PKG = SDK_ROOT / "proof"
DOCS_DIR = REPO_ROOT / "docs"
PROOF_READY_DOC = DOCS_DIR / "proof-ready.md"

# -- Imports under test --------------------------------------
from keyhole_sdk.proof import (
    ContractRegistrationAdapter,
    ParticipantContractPlaceholder,
    ProofBundlePlaceholder,
    ProofSubmissionAdapter,
    SupportStatus,
    VerdictRetrievalAdapter,
    VerificationOutput,
    VerificationRunner,
)
from keyhole_sdk.proof.adapters import (
    AdapterResult,
    LocalContractRegistrationAdapter,
    LocalProofSubmissionAdapter,
    LocalVerdictRetrievalAdapter,
)


# --------------------------------------------------------------
# Validation 1 - Scaffolding Visibility Check (AC-1, FR-1)
# --------------------------------------------------------------

class TestScaffoldingVisibility:
    """Verify the developer kit contains explicit proof-ready scaffolding
    rather than vague TODO comments or ad hoc notes."""

    def test_proof_package_exists(self):
        """The proof subpackage must exist as a proper Python package."""
        assert PROOF_PKG.is_dir(), "keyhole_sdk/proof/ must exist"
        assert (PROOF_PKG / "__init__.py").is_file()

    def test_models_module_exists(self):
        """proof/models.py must exist with placeholder shapes."""
        assert (PROOF_PKG / "models.py").is_file()

    def test_runner_module_exists(self):
        """proof/runner.py must exist with verification runner scaffold."""
        assert (PROOF_PKG / "runner.py").is_file()

    def test_adapters_module_exists(self):
        """proof/adapters.py must exist with adapter interfaces."""
        assert (PROOF_PKG / "adapters.py").is_file()

    def test_proof_ready_doc_exists(self):
        """docs/proof-ready.md must exist explaining the posture."""
        assert PROOF_READY_DOC.is_file()

    def test_participant_contract_placeholder_importable(self):
        """ParticipantContractPlaceholder must be importable from keyhole_sdk.proof."""
        contract = ParticipantContractPlaceholder()
        assert contract is not None

    def test_proof_bundle_placeholder_importable(self):
        """ProofBundlePlaceholder must be importable from keyhole_sdk.proof."""
        bundle = ProofBundlePlaceholder()
        assert bundle is not None

    def test_verification_runner_importable(self):
        """VerificationRunner must be importable from keyhole_sdk.proof."""
        runner = VerificationRunner()
        assert runner is not None

    def test_support_status_enum_importable(self):
        """SupportStatus enum must be importable from keyhole_sdk.proof."""
        assert SupportStatus.SUPPORTED.value == "supported"
        assert SupportStatus.SCAFFOLDED.value == "scaffolded"
        assert SupportStatus.NOT_YET_AVAILABLE.value == "not_yet_available"


# --------------------------------------------------------------
# Validation 2 - Boundary-Consuming Check (AC-2, FR-2)
# --------------------------------------------------------------

class TestBoundaryConsumingPosture:
    """Verify the scaffolding is clearly described as boundary-consuming
    rather than boundary-defining."""

    def test_models_docstring_says_boundary_consuming(self):
        """models.py module docstring must reference boundary-consuming posture."""
        source = (PROOF_PKG / "models.py").read_text()
        assert "boundary-consuming" in source.lower()

    def test_adapters_docstring_says_boundary_consuming(self):
        """adapters.py must not define platform contract shapes authoritatively."""
        source = (PROOF_PKG / "adapters.py").read_text()
        assert "boundary-consuming" in source.lower() or "not define" in source.lower()

    def test_contract_placeholder_says_non_authoritative(self):
        """ParticipantContractPlaceholder must signal non-authoritative posture."""
        doc = ParticipantContractPlaceholder.__doc__ or ""
        assert "non-authoritative" in doc.lower() or "provisional" in doc.lower()

    def test_proof_bundle_says_provisional(self):
        """ProofBundlePlaceholder must signal provisional posture."""
        doc = ProofBundlePlaceholder.__doc__ or ""
        assert "provisional" in doc.lower()

    def test_contract_compatibility_posture(self):
        """Default compatibility posture must be boundary-consuming."""
        contract = ParticipantContractPlaceholder()
        assert contract.compatibility_posture == "boundary-consuming"

    def test_proof_ready_doc_says_boundary_consuming(self):
        """docs/proof-ready.md must reference boundary-consuming posture."""
        content = PROOF_READY_DOC.read_text()
        assert "boundary-consuming" in content.lower()


# --------------------------------------------------------------
# Validation 3 - No Unstable Hardcoding Check (AC-3, FR-3)
# --------------------------------------------------------------

class TestNoUnstableHardcoding:
    """Verify no unstable platform internals are hardcoded as if they were
    sealed participant contracts."""

    # Private platform fields that must never appear in proof scaffolding
    FORBIDDEN_FIELDS = [
        "pointer_state",
        "promotion_state",
        "canonical_digest",
        "cluster_topology",
        "internal_lane",
        "controller_state",
        "governance_verdict",
        "drift_state",
    ]

    def test_models_no_private_fields(self):
        """proof/models.py must not reference private platform fields."""
        source = (PROOF_PKG / "models.py").read_text()
        for field in self.FORBIDDEN_FIELDS:
            assert field not in source, (
                f"Private field '{field}' found in proof/models.py"
            )

    def test_runner_no_private_fields(self):
        """proof/runner.py must not reference private platform fields."""
        source = (PROOF_PKG / "runner.py").read_text()
        for field in self.FORBIDDEN_FIELDS:
            assert field not in source, (
                f"Private field '{field}' found in proof/runner.py"
            )

    def test_adapters_no_private_fields(self):
        """proof/adapters.py must not reference private platform fields."""
        source = (PROOF_PKG / "adapters.py").read_text()
        for field in self.FORBIDDEN_FIELDS:
            assert field not in source, (
                f"Private field '{field}' found in proof/adapters.py"
            )

    def test_no_hardcoded_platform_endpoints(self):
        """Proof scaffolding must not hardcode platform-internal URLs."""
        for module_file in ["models.py", "runner.py", "adapters.py"]:
            source = (PROOF_PKG / module_file).read_text()
            # Should not contain hardcoded MCP endpoint paths
            # (those belong to the transport / client layers)
            assert "/mcp/v1/runs/" not in source, (
                f"Hardcoded MCP endpoint in proof/{module_file}"
            )
            assert "/mcp/v1/contracts" not in source
            assert "/mcp/v1/proofs" not in source

    def test_support_status_always_scaffolded(self):
        """Default support status must be SCAFFOLDED for all proof models."""
        contract = ParticipantContractPlaceholder()
        bundle = ProofBundlePlaceholder()
        runner = VerificationRunner()
        assert contract.support_status == SupportStatus.SCAFFOLDED
        assert bundle.support_status == SupportStatus.SCAFFOLDED
        assert runner.support_status == SupportStatus.SCAFFOLDED


# --------------------------------------------------------------
# Validation 4 - Adapter Isolation Check (AC-4, FR-4)
# --------------------------------------------------------------

class TestAdapterIsolation:
    """Verify future integration points are isolated behind adapters
    or equivalent seam boundaries."""

    def test_contract_registration_adapter_is_abstract(self):
        """ContractRegistrationAdapter must be an abstract base class."""
        assert inspect.isabstract(ContractRegistrationAdapter)

    def test_proof_submission_adapter_is_abstract(self):
        """ProofSubmissionAdapter must be an abstract base class."""
        assert inspect.isabstract(ProofSubmissionAdapter)

    def test_verdict_retrieval_adapter_is_abstract(self):
        """VerdictRetrievalAdapter must be an abstract base class."""
        assert inspect.isabstract(VerdictRetrievalAdapter)

    def test_local_contract_adapter_returns_not_available(self):
        """Local contract adapter must return not-yet-available."""
        adapter = LocalContractRegistrationAdapter()
        result = adapter.register(ParticipantContractPlaceholder())
        assert isinstance(result, AdapterResult)
        assert result.supported is False
        assert "not yet available" in result.reason.lower()

    def test_local_proof_adapter_returns_not_available(self):
        """Local proof adapter must return not-yet-available."""
        adapter = LocalProofSubmissionAdapter()
        result = adapter.submit(ProofBundlePlaceholder())
        assert isinstance(result, AdapterResult)
        assert result.supported is False
        assert "not yet available" in result.reason.lower()

    def test_local_verdict_adapter_returns_not_available(self):
        """Local verdict adapter must return not-yet-available."""
        adapter = LocalVerdictRetrievalAdapter()
        result = adapter.retrieve_verdict("some-ref")
        assert result.supported is False
        assert "not yet available" in result.reason.lower()

    def test_local_repair_guidance_returns_not_available(self):
        """Local repair guidance must return not-yet-available."""
        adapter = LocalVerdictRetrievalAdapter()
        result = adapter.get_repair_guidance("some-ref")
        assert result.supported is False
        assert "not yet available" in result.reason.lower()

    def test_adapter_support_status_is_scaffolded(self):
        """All adapter support statuses must be SCAFFOLDED."""
        for adapter_cls in [
            LocalContractRegistrationAdapter,
            LocalProofSubmissionAdapter,
            LocalVerdictRetrievalAdapter,
        ]:
            adapter = adapter_cls()
            assert adapter.support_status == SupportStatus.SCAFFOLDED

    def test_adapters_do_not_import_transport(self):
        """Adapter module must not import transport or HTTP layers directly."""
        source = (PROOF_PKG / "adapters.py").read_text()
        assert "from keyhole_sdk.transport" not in source
        assert "import requests" not in source
        assert "import httpx" not in source


# --------------------------------------------------------------
# Validation 5 - Supported-vs-Future Separation Check (AC-7, FR-5)
# --------------------------------------------------------------

class TestSupportedVsFutureSeparation:
    """Verify the repo and docs clearly separate current supported flows
    from future proof-bearing flows."""

    def test_proof_ready_doc_lists_supported_now(self):
        """docs/proof-ready.md must list what is supported now."""
        content = PROOF_READY_DOC.read_text()
        assert "supported now" in content.lower()
        # Must mention the four supported flow categories
        assert "capabilities discovery" in content.lower()
        assert "context retrieval" in content.lower()
        assert "smoke" in content.lower() or "read-only" in content.lower()

    def test_proof_ready_doc_lists_scaffolded_later(self):
        """docs/proof-ready.md must list what is scaffolded for later."""
        content = PROOF_READY_DOC.read_text()
        assert "scaffolded" in content.lower()
        assert "participant contract" in content.lower()
        assert "proof" in content.lower()
        assert "verification" in content.lower()

    def test_proof_ready_doc_lists_not_yet_claimed(self):
        """docs/proof-ready.md must list what is not yet claimed."""
        content = PROOF_READY_DOC.read_text()
        assert "not yet claimed" in content.lower()

    def test_proof_package_init_documents_separation(self):
        """proof/__init__.py docstring must separate supported from scaffolded."""
        source = (PROOF_PKG / "__init__.py").read_text()
        assert "supported now" in source.lower()
        assert "not yet claimed" in source.lower()

    def test_support_status_enum_has_three_levels(self):
        """SupportStatus must distinguish supported, scaffolded, and not-yet-available."""
        values = {s.value for s in SupportStatus}
        assert "supported" in values
        assert "scaffolded" in values
        assert "not_yet_available" in values

    def test_proof_modules_do_not_pollute_existing_surfaces(self):
        """Proof scaffolding must not modify or patch existing SDK surfaces."""
        # Verify proof modules don't import and modify existing clients
        for module_file in ["models.py", "runner.py", "adapters.py"]:
            source = (PROOF_PKG / module_file).read_text()
            assert "keyhole_sdk.client" not in source
            assert "keyhole_sdk.smoke" not in source
            assert "keyhole_sdk.discovery" not in source
            assert "keyhole_sdk.context" not in source


# --------------------------------------------------------------
# Validation 6 - Verification Runner Shape Check (AC-5, FR-6)
# --------------------------------------------------------------

class TestVerificationRunnerShape:
    """Verify a verification runner scaffold exists and is structured
    for later local verification flow integration."""

    def test_runner_has_register_collector(self):
        """Runner must have register_collector method for extension."""
        runner = VerificationRunner()
        assert hasattr(runner, "register_collector")
        assert callable(runner.register_collector)

    def test_runner_has_run_method(self):
        """Runner must have a run() method that produces a proof bundle."""
        runner = VerificationRunner()
        assert hasattr(runner, "run")
        assert callable(runner.run)

    def test_runner_captures_environment(self):
        """Runner must capture environment metadata."""
        runner = VerificationRunner()
        env = runner.capture_environment()
        assert "python_version" in env
        assert "platform_info" in env
        assert "sdk_version" in env

    def test_runner_produces_proof_bundle(self):
        """Runner.run() must return a ProofBundlePlaceholder."""
        runner = VerificationRunner()
        bundle = runner.run()
        assert isinstance(bundle, ProofBundlePlaceholder)

    def test_runner_collects_verification_outputs(self):
        """Runner must collect outputs from registered collectors."""
        runner = VerificationRunner()

        def passing_collector():
            return VerificationOutput(
                verification_class="unit-tests",
                passed=True,
                total_tests=10,
                passed_tests=10,
            )

        runner.register_collector("unit-tests", passing_collector)
        bundle = runner.run()
        assert len(bundle.verification_outputs) == 1
        assert bundle.verification_outputs[0].passed is True
        assert bundle.verification_outputs[0].verification_class == "unit-tests"

    def test_runner_handles_collector_failure(self):
        """Runner must handle collector exceptions gracefully."""
        runner = VerificationRunner()

        def failing_collector():
            raise RuntimeError("boom")

        runner.register_collector("broken", failing_collector)
        bundle = runner.run()
        assert len(bundle.verification_outputs) == 1
        assert bundle.verification_outputs[0].passed is False
        assert "boom" in bundle.verification_outputs[0].error_summary

    def test_runner_populates_environment_in_bundle(self):
        """Bundle from runner must contain environment metadata."""
        runner = VerificationRunner()
        bundle = runner.run()
        assert bundle.python_version != ""
        assert bundle.platform_info != ""
        assert bundle.sdk_version != ""

    def test_runner_populates_assembled_at(self):
        """Bundle from runner must have assembled_at timestamp."""
        runner = VerificationRunner()
        bundle = runner.run()
        assert bundle.assembled_at is not None
        assert isinstance(bundle.assembled_at, datetime)

    def test_runner_accepts_context_digest(self):
        """Runner.run() must accept optional context_digest."""
        runner = VerificationRunner()
        bundle = runner.run(context_digest="abc123")
        assert bundle.context_digest == "abc123"

    def test_runner_accepts_contract_version(self):
        """Runner.run() must accept optional capabilities_contract_version."""
        runner = VerificationRunner()
        bundle = runner.run(capabilities_contract_version="mcp/v1")
        assert bundle.capabilities_contract_version == "mcp/v1"

    def test_runner_support_status_is_scaffolded(self):
        """Runner support status must be SCAFFOLDED."""
        runner = VerificationRunner()
        assert runner.support_status == SupportStatus.SCAFFOLDED

    def test_runner_multiple_collectors(self):
        """Runner must handle multiple registered collectors."""
        runner = VerificationRunner()

        def unit_collector():
            return VerificationOutput(passed=True, total_tests=5, passed_tests=5)

        def smoke_collector():
            return VerificationOutput(passed=True, total_tests=3, passed_tests=3)

        runner.register_collector("unit-tests", unit_collector)
        runner.register_collector("smoke-tests", smoke_collector)
        bundle = runner.run()
        assert len(bundle.verification_outputs) == 2


# --------------------------------------------------------------
# Validation 7 - Proof Placeholder Shape Check (AC-6, FR-7)
# --------------------------------------------------------------

class TestProofPlaceholderShape:
    """Verify a proof-bundle placeholder model exists and is clearly
    marked provisional."""

    def test_bundle_has_participant_metadata(self):
        """Bundle must have participant_name and participant_type."""
        bundle = ProofBundlePlaceholder(
            participant_name="test",
            participant_type="external",
        )
        assert bundle.participant_name == "test"
        assert bundle.participant_type == "external"

    def test_bundle_has_provenance_fields(self):
        """Bundle must have source provenance fields."""
        bundle = ProofBundlePlaceholder(
            source_repository="https://example.com/repo",
            source_commit="abc123",
            source_ref="main",
        )
        assert bundle.source_repository == "https://example.com/repo"
        assert bundle.source_commit == "abc123"
        assert bundle.source_ref == "main"

    def test_bundle_has_verification_outputs(self):
        """Bundle must hold a list of VerificationOutput."""
        output = VerificationOutput(passed=True, total_tests=1, passed_tests=1)
        bundle = ProofBundlePlaceholder(verification_outputs=[output])
        assert len(bundle.verification_outputs) == 1

    def test_bundle_has_environment_metadata(self):
        """Bundle must have environment, python_version, sdk_version, platform_info."""
        bundle = ProofBundlePlaceholder(
            environment="local-only",
            python_version="3.12.0",
            sdk_version="0.3.0",
            platform_info="Linux",
        )
        assert bundle.environment == "local-only"
        assert bundle.python_version == "3.12.0"

    def test_bundle_has_context_references(self):
        """Bundle must have context_digest and capabilities_contract_version."""
        bundle = ProofBundlePlaceholder(
            context_digest="sha256:abc",
            capabilities_contract_version="mcp/v1",
        )
        assert bundle.context_digest == "sha256:abc"

    def test_bundle_has_traceability_fields(self):
        """Bundle must have assembled_at and bundle_digest."""
        now = datetime.now(timezone.utc)
        bundle = ProofBundlePlaceholder(assembled_at=now, bundle_digest="xyz")
        assert bundle.assembled_at == now
        assert bundle.bundle_digest == "xyz"

    def test_bundle_has_future_signature_fields(self):
        """Bundle must have signature and attestation_chain placeholders."""
        bundle = ProofBundlePlaceholder()
        assert bundle.signature == ""
        assert bundle.attestation_chain == []

    def test_bundle_support_status_is_scaffolded(self):
        """Bundle support status must be SCAFFOLDED."""
        bundle = ProofBundlePlaceholder()
        assert bundle.support_status == SupportStatus.SCAFFOLDED

    def test_bundle_all_passed_property(self):
        """Bundle.all_passed must reflect verification results."""
        passing = VerificationOutput(passed=True, total_tests=1, passed_tests=1)
        failing = VerificationOutput(passed=False, total_tests=1, failed_tests=1)

        assert ProofBundlePlaceholder(verification_outputs=[passing]).all_passed
        assert not ProofBundlePlaceholder(verification_outputs=[failing]).all_passed
        assert not ProofBundlePlaceholder(verification_outputs=[passing, failing]).all_passed
        assert not ProofBundlePlaceholder().all_passed  # empty = not passed

    def test_bundle_verification_summary(self):
        """Bundle.verification_summary must report totals."""
        outputs = [
            VerificationOutput(passed=True, total_tests=5, passed_tests=5),
            VerificationOutput(passed=False, total_tests=3, failed_tests=3),
        ]
        bundle = ProofBundlePlaceholder(verification_outputs=outputs)
        summary = bundle.verification_summary
        assert summary["total_verifications"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["all_passed"] is False

    def test_bundle_add_verification(self):
        """Bundle.add_verification must append an output."""
        bundle = ProofBundlePlaceholder()
        output = VerificationOutput(passed=True)
        bundle.add_verification(output)
        assert len(bundle.verification_outputs) == 1

    def test_bundle_docstring_says_provisional(self):
        """ProofBundlePlaceholder docstring must say 'provisional'."""
        doc = ProofBundlePlaceholder.__doc__ or ""
        assert "provisional" in doc.lower()

    def test_bundle_notes_default_says_provisional(self):
        """Default notes field must indicate provisional status."""
        bundle = ProofBundlePlaceholder()
        assert "provisional" in bundle.notes.lower()


# --------------------------------------------------------------
# Participant Contract Placeholder Shape (FR-1, FR-2)
# --------------------------------------------------------------

class TestParticipantContractPlaceholder:
    """Verify participant contract placeholder has the required shape."""

    def test_has_participant_identity(self):
        """Must have participant_name and participant_type."""
        contract = ParticipantContractPlaceholder()
        assert contract.participant_name == "keyhole-developer-kit"
        assert contract.participant_type == "external-developer-kit"

    def test_has_verification_classes(self):
        """Must list future verification classes."""
        contract = ParticipantContractPlaceholder()
        assert isinstance(contract.verification_classes, list)
        assert len(contract.verification_classes) > 0

    def test_has_supported_environments(self):
        """Must list supported environments."""
        contract = ParticipantContractPlaceholder()
        assert "local-only" in contract.supported_environments
        assert "governed" in contract.supported_environments

    def test_has_scope_hint(self):
        """Must have a scope or blast-radius hint."""
        contract = ParticipantContractPlaceholder()
        assert contract.scope_hint != ""

    def test_has_repository_url(self):
        """Must have a repository URL for provenance."""
        contract = ParticipantContractPlaceholder()
        assert "github.com" in contract.repository_url

    def test_support_status_is_scaffolded(self):
        """Contract support status must be SCAFFOLDED."""
        contract = ParticipantContractPlaceholder()
        assert contract.support_status == SupportStatus.SCAFFOLDED

    def test_notes_indicate_provisional(self):
        """Default notes must indicate provisional status."""
        contract = ParticipantContractPlaceholder()
        assert "provisional" in contract.notes.lower()


# --------------------------------------------------------------
# Human and Agent Clarity Check (FR-8)
# --------------------------------------------------------------

class TestHumanAndAgentClarity:
    """Verify docs and repo structure make the future-proofing posture
    understandable to both humans and agents."""

    def test_proof_ready_doc_has_overview(self):
        """docs/proof-ready.md must have an overview section."""
        content = PROOF_READY_DOC.read_text()
        assert "## overview" in content.lower() or "# proof-ready" in content.lower()

    def test_proof_ready_doc_has_architecture_section(self):
        """docs/proof-ready.md must explain the adapter architecture."""
        content = PROOF_READY_DOC.read_text()
        assert "adapter" in content.lower()

    def test_proof_ready_doc_has_usage_examples(self):
        """docs/proof-ready.md must have code examples."""
        content = PROOF_READY_DOC.read_text()
        assert "```python" in content

    def test_proof_ready_doc_mentions_dev_ux_dependencies(self):
        """docs/proof-ready.md must mention DEV-UX dependency stories."""
        content = PROOF_READY_DOC.read_text()
        assert "DEV-UX-03" in content
        assert "DEV-UX-04" in content
        assert "DEV-UX-06" in content

    def test_all_proof_modules_have_docstrings(self):
        """All proof package modules must have module-level docstrings."""
        for module_file in ["__init__.py", "models.py", "runner.py", "adapters.py"]:
            source = (PROOF_PKG / module_file).read_text()
            tree = ast.parse(source)
            docstring = ast.get_docstring(tree)
            assert docstring is not None, (
                f"proof/{module_file} must have a module docstring"
            )

    def test_proof_init_exports_all_public_surfaces(self):
        """proof/__init__.py must export all placeholder and adapter surfaces."""
        from keyhole_sdk import proof
        expected = [
            "ParticipantContractPlaceholder",
            "ProofBundlePlaceholder",
            "VerificationOutput",
            "SupportStatus",
            "VerificationRunner",
            "ContractRegistrationAdapter",
            "ProofSubmissionAdapter",
            "VerdictRetrievalAdapter",
        ]
        for name in expected:
            assert hasattr(proof, name), f"proof must export {name}"
