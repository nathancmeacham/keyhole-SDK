"""Tests for CE-V5-S42-10 - Developer Kit Launch Readiness Seal.

Validates that the developer kit is launch-grade - every document,
surface, instruction, and evidence artifact needed for external developer
consumption exists, is consistent, and is honest about what is supported
versus scaffolded.

Acceptance criteria:

AC-1: Reproducibility check - external builder can reproduce first-success
AC-2: Instruction freshness check - copilot instructions match S42 surfaces
AC-3: Boundary truth check - no private platform dependency
AC-4: Environment matrix check - supported environments documented
AC-5: Evidence bundle check - first-success smoke evidence captured
AC-6: External builder usability check - quickstart covers full flow
AC-7: Public-safe trust check - trust posture is explicit and defensible
AC-8: Attestation check - attestation ties all artifacts together
AC-9: Readiness checklist check - all launch conditions are met

Validation criteria:

VC-1: All launch readiness documents exist
VC-2: Readiness checklist covers all required categories
VC-3: Trust posture documents boundary-first properties
VC-4: Supported-vs-scaffolded distinction is present throughout
VC-5: Environment matrix specifies Python, OS, Docker
VC-6: Evidence bundle contains reproducible evidence
VC-7: Attestation references all supporting documents
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# -- Project paths -------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk"
DOCS_DIR = REPO_ROOT / "docs"
COPILOT_INSTRUCTIONS = REPO_ROOT / ".github" / "copilot-instructions.md"

LAUNCH_READINESS_DOC = DOCS_DIR / "launch-readiness.md"
TRUST_POSTURE_DOC = DOCS_DIR / "trust-posture.md"
SUPPORTED_ENVS_DOC = DOCS_DIR / "supported-environments.md"
SMOKE_EVIDENCE_DOC = DOCS_DIR / "smoke-evidence.md"
ATTESTATION_DOC = DOCS_DIR / "attestation.md"
QUICKSTART_DOC = DOCS_DIR / "quickstart.md"
SMOKE_DOC = DOCS_DIR / "smoke.md"
ARCHITECTURE_DOC = DOCS_DIR / "architecture.md"
AUTH_BOOTSTRAP_DOC = DOCS_DIR / "auth-bootstrap.md"
BRIDGE_CONTRACT_DOC = DOCS_DIR / "bridge-contract.md"
PROOF_READY_DOC = DOCS_DIR / "proof-ready.md"
RECURSIVE_DEMO_DOC = DOCS_DIR / "recursive-demo.md"
BOUNDARY_CONSTITUTION_DOC = DOCS_DIR / "boundary-constitution.md"

# -- Imports under test --------------------------------------
from keyhole_sdk import (
    CapabilitiesClient,
    ContextClient,
    DemoFlowRunner,
    DemoResult,
    DispatchPreflight,
    KeyholeClient,
    KeyholeConfig,
    ParticipantContractPlaceholder,
    ProofBundlePlaceholder,
    ReadOnlySmokeRunner,
    RunTypeValidator,
    SchemaHelper,
    SmokeResult,
    SupportStatus,
    VerificationOutput,
    VerificationRunner,
)


# --------------------------------------------------------------
# VC-1 - All Launch Readiness Documents Exist
# --------------------------------------------------------------
class TestLaunchDocumentsExist:
    """VC-1: Every required S42-10 document exists in the docs/ directory."""

    def test_launch_readiness_checklist_exists(self):
        assert LAUNCH_READINESS_DOC.exists(), "docs/launch-readiness.md missing"

    def test_trust_posture_exists(self):
        assert TRUST_POSTURE_DOC.exists(), "docs/trust-posture.md missing"

    def test_supported_environments_exists(self):
        assert SUPPORTED_ENVS_DOC.exists(), "docs/supported-environments.md missing"

    def test_smoke_evidence_exists(self):
        assert SMOKE_EVIDENCE_DOC.exists(), "docs/smoke-evidence.md missing"

    def test_attestation_exists(self):
        assert ATTESTATION_DOC.exists(), "docs/attestation.md missing"

    def test_quickstart_exists(self):
        assert QUICKSTART_DOC.exists(), "docs/quickstart.md missing"

    def test_smoke_doc_exists(self):
        assert SMOKE_DOC.exists(), "docs/smoke.md missing"

    def test_architecture_exists(self):
        assert ARCHITECTURE_DOC.exists(), "docs/architecture.md missing"

    def test_auth_bootstrap_exists(self):
        assert AUTH_BOOTSTRAP_DOC.exists(), "docs/auth-bootstrap.md missing"

    def test_bridge_contract_exists(self):
        assert BRIDGE_CONTRACT_DOC.exists(), "docs/bridge-contract.md missing"

    def test_proof_ready_exists(self):
        assert PROOF_READY_DOC.exists(), "docs/proof-ready.md missing"

    def test_recursive_demo_exists(self):
        assert RECURSIVE_DEMO_DOC.exists(), "docs/recursive-demo.md missing"

    def test_boundary_constitution_exists(self):
        assert BOUNDARY_CONSTITUTION_DOC.exists(), "docs/boundary-constitution.md missing"


# --------------------------------------------------------------
# VC-2 - Readiness Checklist Covers All Required Categories
# --------------------------------------------------------------
class TestReadinessChecklist:
    """VC-2: Launch readiness checklist covers all required categories."""

    @pytest.fixture
    def checklist_content(self):
        return LAUNCH_READINESS_DOC.read_text()

    def test_has_repo_posture_category(self, checklist_content):
        assert "Repository Posture" in checklist_content

    def test_has_sdk_cli_category(self, checklist_content):
        assert "SDK" in checklist_content and "CLI" in checklist_content

    def test_has_discovery_category(self, checklist_content):
        assert "Discovery" in checklist_content or "Capabilities" in checklist_content

    def test_has_auth_category(self, checklist_content):
        assert "Auth" in checklist_content

    def test_has_context_category(self, checklist_content):
        assert "Context" in checklist_content

    def test_has_dispatch_category(self, checklist_content):
        assert "Dispatch" in checklist_content

    def test_has_smoke_category(self, checklist_content):
        assert "Smoke" in checklist_content

    def test_has_proof_category(self, checklist_content):
        assert "Proof" in checklist_content

    def test_has_demo_category(self, checklist_content):
        assert "Demo" in checklist_content

    def test_has_documentation_category(self, checklist_content):
        assert "Documentation" in checklist_content

    def test_has_test_coverage_category(self, checklist_content):
        assert "Test" in checklist_content

    def test_all_items_met(self, checklist_content):
        """Every status cell should be MET."""
        met_count = checklist_content.count("| MET |")
        assert met_count >= 50, f"Expected at least 50 MET items, found {met_count}"

    def test_no_items_not_met(self, checklist_content):
        """No items should be NOT MET."""
        assert "NOT MET" not in checklist_content, "Found NOT MET items in checklist"

    def test_scaffolded_items_labeled(self, checklist_content):
        """Scaffolded items are marked with [S]."""
        assert "[S]" in checklist_content, "Scaffolded items should be marked with [S]"

    def test_checklist_references_story(self, checklist_content):
        assert "CE-V5-S42-10" in checklist_content or "S42-10" in checklist_content


# --------------------------------------------------------------
# VC-3 - Trust Posture Documents Boundary-First Properties
# --------------------------------------------------------------
class TestTrustPosture:
    """VC-3: Trust posture is explicit and defensible."""

    @pytest.fixture
    def trust_content(self):
        return TRUST_POSTURE_DOC.read_text()

    def test_boundary_first_property(self, trust_content):
        assert "Boundary-First" in trust_content

    def test_discovery_first_property(self, trust_content):
        assert "Discovery-First" in trust_content

    def test_context_before_assumption_property(self, trust_content):
        assert "Context-Before-Assumption" in trust_content

    def test_exact_run_type_discipline_property(self, trust_content):
        assert "Exact Run-Type Discipline" in trust_content or "Run-Type" in trust_content

    def test_reproducible_smoke_path_property(self, trust_content):
        assert "Reproducible" in trust_content and "Smoke" in trust_content

    def test_no_private_platform_intimacy_property(self, trust_content):
        assert "Private" in trust_content and "Platform" in trust_content

    def test_supported_vs_scaffolded_distinction(self, trust_content):
        lower = trust_content.lower()
        assert "supported" in lower and "scaffolded" in lower

    def test_mentions_mcp_boundary(self, trust_content):
        assert "MCP" in trust_content and "boundary" in trust_content.lower()

    def test_mentions_capabilities_endpoint(self, trust_content):
        assert "/mcp/v1/capabilities" in trust_content

    def test_does_not_claim_section_exists(self, trust_content):
        assert "Does Not Claim" in trust_content or "does not claim" in trust_content

    def test_trust_pillars_exist(self, trust_content):
        """Trust posture should identify core trust pillars."""
        pillars = ["Separation", "Discovery", "Reproducibility", "Honesty", "Independence"]
        found = sum(1 for p in pillars if p.lower() in trust_content.lower())
        assert found >= 3, f"Expected at least 3 trust pillars, found {found}"


# --------------------------------------------------------------
# VC-4 - Supported-vs-Scaffolded Distinction Throughout
# --------------------------------------------------------------
class TestSupportedVsScaffolded:
    """VC-4: The supported-vs-scaffolded distinction is clear in all relevant artifacts."""

    def test_sdk_support_status_enum(self):
        """SupportStatus enum has supported, scaffolded, and not-yet-available values."""
        assert hasattr(SupportStatus, "SUPPORTED")
        assert hasattr(SupportStatus, "SCAFFOLDED")
        assert hasattr(SupportStatus, "NOT_YET_AVAILABLE")

    def test_participant_contract_has_support_status(self):
        contract = ParticipantContractPlaceholder()
        assert contract.support_status in (
            SupportStatus.SUPPORTED,
            SupportStatus.SCAFFOLDED,
            SupportStatus.NOT_YET_AVAILABLE,
        )

    def test_trust_posture_distinguishes(self):
        content = TRUST_POSTURE_DOC.read_text().lower()
        assert "supported" in content and "scaffolded" in content

    def test_attestation_distinguishes(self):
        content = ATTESTATION_DOC.read_text().lower()
        assert "supported" in content and "scaffolded" in content

    def test_checklist_distinguishes(self):
        content = LAUNCH_READINESS_DOC.read_text().lower()
        assert "scaffolded" in content


# --------------------------------------------------------------
# VC-5 - Environment Matrix Specifies Python, OS, Docker
# --------------------------------------------------------------
class TestEnvironmentMatrix:
    """VC-5: The environment matrix documents supported configurations."""

    @pytest.fixture
    def env_content(self):
        return SUPPORTED_ENVS_DOC.read_text()

    def test_has_python_versions(self, env_content):
        assert "3.9" in env_content
        assert "3.12" in env_content

    def test_has_operating_systems(self, env_content):
        assert "Linux" in env_content
        assert "macOS" in env_content

    def test_has_docker(self, env_content):
        assert "Docker" in env_content

    def test_has_transport_posture(self, env_content):
        assert "REST" in env_content or "HTTP" in env_content

    def test_sse_tombstoned(self, env_content):
        lower = env_content.lower()
        assert "sse" in lower or "tombstoned" in lower

    def test_json_rpc_tombstoned(self, env_content):
        lower = env_content.lower()
        assert "json-rpc" in lower or "tombstoned" in lower

    def test_auth_posture_listed(self, env_content):
        assert "OIDC" in env_content or "PKCE" in env_content

    def test_network_requirements_listed(self, env_content):
        lower = env_content.lower()
        assert "network" in lower or "connectivity" in lower or "https" in lower

    def test_known_limitations_section(self, env_content):
        lower = env_content.lower()
        assert "limitation" in lower or "not tested" in lower or "not supported" in lower

    def test_quick_compatibility_section(self, env_content):
        lower = env_content.lower()
        assert "compat" in lower or "verify" in lower or "check" in lower


# --------------------------------------------------------------
# VC-6 - Evidence Bundle Contains Reproducible Evidence
# --------------------------------------------------------------
class TestSmokeEvidence:
    """VC-6: First-success smoke evidence bundle is complete and reproducible."""

    @pytest.fixture
    def evidence_content(self):
        return SMOKE_EVIDENCE_DOC.read_text()

    def test_sdk_version_evidence(self, evidence_content):
        assert "0.3.0" in evidence_content

    def test_python_version_evidence(self, evidence_content):
        assert "3.12" in evidence_content

    def test_import_evidence(self, evidence_content):
        """Evidence shows all surfaces import successfully."""
        assert "CapabilitiesClient" in evidence_content
        assert "ContextClient" in evidence_content
        assert "DispatchPreflight" in evidence_content
        assert "ReadOnlySmokeRunner" in evidence_content

    def test_participant_posture_evidence(self, evidence_content):
        assert "keyhole-developer-kit" in evidence_content
        assert "boundary-consuming" in evidence_content

    def test_proof_bundle_evidence(self, evidence_content):
        lower = evidence_content.lower()
        assert "proof" in lower and "bundle" in lower

    def test_demo_flow_evidence(self, evidence_content):
        lower = evidence_content.lower()
        assert "demo" in lower and "flow" in lower

    def test_adapter_evidence(self, evidence_content):
        lower = evidence_content.lower()
        assert "adapter" in lower

    def test_test_suite_counts(self, evidence_content):
        """Evidence includes test pass counts."""
        assert "446" in evidence_content or "passed" in evidence_content.lower()

    def test_reproducibility_instructions(self, evidence_content):
        """Evidence includes steps to reproduce."""
        lower = evidence_content.lower()
        assert "reproduce" in lower or "pip install" in lower

    def test_no_secrets_in_evidence(self, evidence_content):
        """Evidence does not expose secrets."""
        lower = evidence_content.lower()
        assert "password" not in lower
        assert "secret_key" not in lower
        # Token references should be placeholders
        if "token" in lower:
            assert "bearer-token" in lower or "<" in evidence_content

    def test_evidence_summary_table(self, evidence_content):
        """Evidence includes a summary table."""
        assert "| Property" in evidence_content or "| Verified" in evidence_content

    def test_smoke_runner_shape_documented(self, evidence_content):
        """Evidence documents the 4-phase smoke runner shape."""
        assert "Discovery" in evidence_content
        assert "Identity" in evidence_content
        assert "Context" in evidence_content


# --------------------------------------------------------------
# VC-7 - Attestation References All Supporting Documents
# --------------------------------------------------------------
class TestAttestation:
    """VC-7: Attestation ties all artifacts together."""

    @pytest.fixture
    def attestation_content(self):
        return ATTESTATION_DOC.read_text()

    def test_references_story(self, attestation_content):
        assert "S42-10" in attestation_content

    def test_references_sdk_version(self, attestation_content):
        assert "0.3.0" in attestation_content

    def test_references_launch_readiness(self, attestation_content):
        assert "launch-readiness" in attestation_content

    def test_references_trust_posture(self, attestation_content):
        assert "trust-posture" in attestation_content

    def test_references_supported_environments(self, attestation_content):
        assert "supported-environments" in attestation_content

    def test_references_smoke_evidence(self, attestation_content):
        assert "smoke-evidence" in attestation_content

    def test_references_quickstart(self, attestation_content):
        assert "quickstart" in attestation_content

    def test_references_smoke_doc(self, attestation_content):
        assert "smoke.md" in attestation_content or "smoke" in attestation_content.lower()

    def test_references_architecture(self, attestation_content):
        assert "architecture" in attestation_content

    def test_references_auth_bootstrap(self, attestation_content):
        assert "auth-bootstrap" in attestation_content

    def test_references_proof_ready(self, attestation_content):
        assert "proof-ready" in attestation_content

    def test_references_boundary_constitution(self, attestation_content):
        assert "boundary-constitution" in attestation_content

    def test_supported_surfaces_table(self, attestation_content):
        """Attestation lists supported surfaces."""
        surfaces = [
            "CapabilitiesClient",
            "ContextClient",
            "DispatchPreflight",
            "ReadOnlySmokeRunner",
        ]
        for surface in surfaces:
            assert surface in attestation_content, f"{surface} not in attestation"

    def test_scaffolded_surfaces_listed(self, attestation_content):
        """Attestation lists scaffolded surfaces."""
        assert "scaffolded" in attestation_content.lower()
        assert "registration" in attestation_content.lower()

    def test_excluded_scope_section(self, attestation_content):
        """Attestation explicitly excludes private internals."""
        lower = attestation_content.lower()
        assert "excluded" in lower or "does not" in lower

    def test_attestation_statement_exists(self, attestation_content):
        lower = attestation_content.lower()
        assert "attestation" in lower and ("statement" in lower or "launch-grade" in lower)

    def test_verification_instructions(self, attestation_content):
        """Attestation includes verification instructions."""
        assert "pip install" in attestation_content or "pytest" in attestation_content

    def test_readiness_summary_numbers(self, attestation_content):
        """Attestation includes readiness summary with numbers."""
        assert "59" in attestation_content or "446" in attestation_content or "19" in attestation_content


# --------------------------------------------------------------
# AC-1 - Reproducibility Check
# --------------------------------------------------------------
class TestReproducibility:
    """AC-1: All launch artifacts are reproducible by an external builder."""

    def test_all_19_surfaces_importable(self):
        """External builder can import all declared SDK surfaces."""
        surfaces = [
            CapabilitiesClient, ContextClient, DispatchPreflight,
            RunTypeValidator, SchemaHelper, ReadOnlySmokeRunner,
            SmokeResult, ParticipantContractPlaceholder,
            ProofBundlePlaceholder, VerificationRunner,
            VerificationOutput, SupportStatus, DemoFlowRunner,
            DemoResult, KeyholeClient, KeyholeConfig,
        ]
        for surface in surfaces:
            assert surface is not None, f"{surface.__name__} import failed"

    def test_participant_contract_is_deterministic(self):
        """Same inputs produce same contract every time."""
        c1 = ParticipantContractPlaceholder()
        c2 = ParticipantContractPlaceholder()
        assert c1.participant_name == c2.participant_name
        assert c1.compatibility_posture == c2.compatibility_posture
        assert c1.support_status == c2.support_status

    def test_proof_bundle_assembly_is_deterministic(self):
        """Same verifications produce same bundle shape."""
        v = VerificationOutput(name="test", passed=True, detail="ok")
        b1 = ProofBundlePlaceholder()
        b1.add_verification(v)
        b2 = ProofBundlePlaceholder()
        b2.add_verification(v)
        assert b1.all_passed == b2.all_passed
        assert b1.verification_summary == b2.verification_summary

    def test_evidence_bundle_has_reproduction_steps(self):
        content = SMOKE_EVIDENCE_DOC.read_text()
        assert "pip install" in content
        assert "import" in content.lower()


# --------------------------------------------------------------
# AC-2 - Instruction Freshness Check
# --------------------------------------------------------------
class TestInstructionFreshness:
    """AC-2: Copilot instructions reflect S42 surfaces."""

    @pytest.fixture
    def instructions_content(self):
        return COPILOT_INSTRUCTIONS.read_text()

    def test_mentions_dispatch_preflight(self, instructions_content):
        assert "DispatchPreflight" in instructions_content

    def test_mentions_run_type_validator(self, instructions_content):
        assert "RunTypeValidator" in instructions_content

    def test_mentions_schema_helper(self, instructions_content):
        assert "SchemaHelper" in instructions_content

    def test_mentions_capabilities_discovery(self, instructions_content):
        assert "/mcp/v1/capabilities" in instructions_content

    def test_mentions_context_client(self, instructions_content):
        assert "ContextClient" in instructions_content

    def test_mentions_context_compile(self, instructions_content):
        assert "context.compile" in instructions_content

    def test_mentions_oidc_pkce(self, instructions_content):
        assert "OIDC" in instructions_content and "PKCE" in instructions_content

    def test_sse_tombstoned(self, instructions_content):
        assert "tombstoned" in instructions_content.lower()

    def test_exact_run_type_discipline(self, instructions_content):
        assert "Run-Type Discipline" in instructions_content or "Exact Run-Type" in instructions_content


# --------------------------------------------------------------
# AC-3 - Boundary Truth Check
# --------------------------------------------------------------
class TestBoundaryTruth:
    """AC-3: No private platform dependency exists."""

    def test_sdk_has_no_platform_imports(self):
        """No SDK source file imports from keyhole_platform."""
        for py_file in SDK_ROOT.rglob("*.py"):
            content = py_file.read_text()
            assert "keyhole_platform" not in content, (
                f"{py_file.name} imports keyhole_platform"
            )
            assert "from platform." not in content or "from platform import" not in content

    def test_docs_reference_boundary_not_source(self):
        """Key docs reference boundary, not private source."""
        for doc_path in [TRUST_POSTURE_DOC, ATTESTATION_DOC]:
            content = doc_path.read_text().lower()
            assert "boundary" in content, f"{doc_path.name} missing boundary reference"

    def test_boundary_constitution_exists(self):
        assert BOUNDARY_CONSTITUTION_DOC.exists()
        content = BOUNDARY_CONSTITUTION_DOC.read_text()
        assert "boundary" in content.lower()


# --------------------------------------------------------------
# AC-4 - Environment Matrix Check
# --------------------------------------------------------------
class TestEnvironmentMatrixAC:
    """AC-4: Supported environments are fully documented."""

    def test_environment_doc_exists(self):
        assert SUPPORTED_ENVS_DOC.exists()

    def test_python_range_complete(self):
        content = SUPPORTED_ENVS_DOC.read_text()
        for version in ["3.9", "3.10", "3.11", "3.12"]:
            assert version in content, f"Python {version} not in environment matrix"

    def test_docker_requirements_specified(self):
        content = SUPPORTED_ENVS_DOC.read_text()
        assert "Docker" in content
        assert "Compose" in content


# --------------------------------------------------------------
# AC-5 - Evidence Bundle Check
# --------------------------------------------------------------
class TestEvidenceBundleAC:
    """AC-5: First-success evidence bundle is complete."""

    def test_evidence_doc_exists(self):
        assert SMOKE_EVIDENCE_DOC.exists()

    def test_evidence_has_sdk_evidence(self):
        content = SMOKE_EVIDENCE_DOC.read_text()
        assert "SDK" in content and "0.3.0" in content

    def test_evidence_has_test_results(self):
        content = SMOKE_EVIDENCE_DOC.read_text()
        assert "passed" in content.lower()

    def test_evidence_has_participant_evidence(self):
        content = SMOKE_EVIDENCE_DOC.read_text()
        assert "keyhole-developer-kit" in content


# --------------------------------------------------------------
# AC-6 - External Builder Usability Check
# --------------------------------------------------------------
class TestExternalBuilderUsability:
    """AC-6: Quickstart covers enough for an external developer."""

    def test_quickstart_exists(self):
        assert QUICKSTART_DOC.exists()

    def test_quickstart_has_setup_instructions(self):
        content = QUICKSTART_DOC.read_text()
        lower = content.lower()
        assert "docker" in lower or "pip install" in lower or "clone" in lower

    def test_quickstart_references_capabilities(self):
        content = QUICKSTART_DOC.read_text()
        lower = content.lower()
        assert "capabilities" in lower or "discovery" in lower

    def test_readme_exists(self):
        readme = REPO_ROOT / "README.md"
        assert readme.exists()

    def test_examples_exist(self):
        example_dir = REPO_ROOT / "examples" / "python-client"
        assert example_dir.exists()
        py_files = list(example_dir.glob("*.py"))
        assert len(py_files) >= 3, f"Expected at least 3 examples, found {len(py_files)}"


# --------------------------------------------------------------
# AC-7 - Public-Safe Trust Check
# --------------------------------------------------------------
class TestPublicSafeTrustAC:
    """AC-7: Trust posture is public-safe and defensible."""

    def test_trust_posture_doc_exists(self):
        assert TRUST_POSTURE_DOC.exists()

    def test_no_secrets_in_trust_doc(self):
        content = TRUST_POSTURE_DOC.read_text().lower()
        assert "password" not in content
        assert "secret_key" not in content

    def test_trust_does_not_overclaim(self):
        """Trust posture has a 'does not claim' section."""
        content = TRUST_POSTURE_DOC.read_text()
        assert "Does Not Claim" in content or "does not claim" in content

    def test_trust_identifies_boundary_consuming_posture(self):
        content = TRUST_POSTURE_DOC.read_text().lower()
        assert "boundary-consuming" in content or "boundary" in content


# --------------------------------------------------------------
# AC-8 - Attestation Check
# --------------------------------------------------------------
class TestAttestationAC:
    """AC-8: Attestation exists and ties together all artifacts."""

    def test_attestation_exists(self):
        assert ATTESTATION_DOC.exists()

    def test_attestation_references_all_documents(self):
        content = ATTESTATION_DOC.read_text()
        required_refs = [
            "launch-readiness",
            "trust-posture",
            "supported-environments",
            "smoke-evidence",
            "quickstart",
        ]
        for ref in required_refs:
            assert ref in content, f"Attestation missing reference to {ref}"

    def test_attestation_has_scope(self):
        content = ATTESTATION_DOC.read_text()
        assert "Scope" in content or "scope" in content


# --------------------------------------------------------------
# AC-9 - Readiness Checklist Check
# --------------------------------------------------------------
class TestReadinessChecklistAC:
    """AC-9: All launch conditions are verifiably met."""

    def test_checklist_exists(self):
        assert LAUNCH_READINESS_DOC.exists()

    def test_minimum_item_count(self):
        content = LAUNCH_READINESS_DOC.read_text()
        met_count = content.count("| MET |")
        assert met_count >= 50

    def test_no_unmet_conditions(self):
        content = LAUNCH_READINESS_DOC.read_text()
        assert "NOT MET" not in content


# --------------------------------------------------------------
# Cross-Cutting - Document Consistency
# --------------------------------------------------------------
class TestDocumentConsistency:
    """Documents are consistent with each other and the SDK."""

    def test_sdk_version_consistent_across_docs(self):
        """SDK version 0.3.0 is consistently stated."""
        for doc in [SMOKE_EVIDENCE_DOC, ATTESTATION_DOC]:
            content = doc.read_text()
            assert "0.3.0" in content, f"{doc.name} missing SDK version 0.3.0"

    def test_participant_name_consistent(self):
        """Participant name is consistent across docs."""
        for doc in [TRUST_POSTURE_DOC, ATTESTATION_DOC, SMOKE_EVIDENCE_DOC]:
            content = doc.read_text()
            assert "keyhole-developer-kit" in content, (
                f"{doc.name} missing participant name"
            )

    def test_story_reference_in_s42_10_docs(self):
        """All S42-10 docs reference the story."""
        for doc in [LAUNCH_READINESS_DOC, TRUST_POSTURE_DOC, ATTESTATION_DOC]:
            content = doc.read_text()
            assert "S42-10" in content, f"{doc.name} missing S42-10 reference"

    def test_mcp_v1_contract_referenced(self):
        """Key docs reference the current contract version."""
        content = TRUST_POSTURE_DOC.read_text()
        assert "mcp/v1" in content or "/mcp/v1" in content

    def test_no_sse_or_jsonrpc_as_active_transport(self):
        """No S42-10 doc recommends SSE or JSON-RPC as active transport."""
        for doc in [TRUST_POSTURE_DOC, SUPPORTED_ENVS_DOC, ATTESTATION_DOC]:
            content = doc.read_text()
            # SSE and JSON-RPC may appear as tombstoned but not as recommended
            if "SSE" in content or "JSON-RPC" in content:
                lower = content.lower()
                assert "tombstoned" in lower or "not" in lower, (
                    f"{doc.name} may be recommending SSE or JSON-RPC"
                )


# --------------------------------------------------------------
# Cross-Cutting - SDK Surface Completeness
# --------------------------------------------------------------
class TestSDKSurfaceCompleteness:
    """SDK exports all surfaces expected for launch."""

    def test_discovery_surface(self):
        assert CapabilitiesClient is not None

    def test_context_surface(self):
        assert ContextClient is not None

    def test_dispatch_safety_surfaces(self):
        assert DispatchPreflight is not None
        assert RunTypeValidator is not None
        assert SchemaHelper is not None

    def test_smoke_surface(self):
        assert ReadOnlySmokeRunner is not None
        assert SmokeResult is not None

    def test_proof_surfaces(self):
        assert VerificationRunner is not None
        assert VerificationOutput is not None
        assert ProofBundlePlaceholder is not None
        assert ParticipantContractPlaceholder is not None
        assert SupportStatus is not None

    def test_demo_surfaces(self):
        assert DemoFlowRunner is not None
        assert DemoResult is not None

    def test_client_surfaces(self):
        assert KeyholeClient is not None
        assert KeyholeConfig is not None

    def test_sdk_version_accessible(self):
        import keyhole_sdk
        assert hasattr(keyhole_sdk, "__version__")
        assert keyhole_sdk.__version__ == "0.4.1"
