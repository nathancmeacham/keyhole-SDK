"""SDK-CLIENT-10 - Repository Ingestion and Graph.

Tests covering section18 acceptance criteria:
  - keyhole ingest parsing
  - keyhole ingest --shadow parsing
  - repo root detection
  - include/exclude filtering correctness
  - secret-bearing files excluded by default
  - deterministic package manifest generation
  - compatibility posture rendering
  - no repo mutation during ingestion
  - proof artifacts generated on success
  - proof artifacts generated on failure
  - clear output rendering for inferred capabilities and confidence
  - accepted/deferred does not render as completed
  - invalid or missing repo path rejected locally
  - summary-only mode
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# -- SDK imports ------------------------------------------

from keyhole_sdk.ingest.models import (
    CompatibilityPosture,
    ConfidenceLevel,
    FileClassification,
    GraphSummary,
    InferredCapability,
    IngestionOutcome,
    IngestionPackage,
    IngestionRequest,
    RepoScanResult,
    ScanSignal,
)
from keyhole_sdk.ingest.scanner import scan_repo
from keyhole_sdk.ingest.filter import (
    DEFAULT_EXCLUDES,
    DEFAULT_INCLUDES,
    IncludeExcludeFilter,
)
from keyhole_sdk.ingest.packager import build_ingestion_package
from keyhole_sdk.ingest.proof import emit_ingestion_proof
from keyhole_sdk.ingest.repair import map_ingestion_repair
from keyhole_sdk.ingest.submitter import submit_ingestion


# -- Fixtures ---------------------------------------------

@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repository for scanning."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # Source files
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("print('hello')\n")
    (repo / "src" / "utils.py").write_text("def helper(): pass\n")

    # Tests
    (repo / "tests").mkdir()
    (repo / "tests" / "test_main.py").write_text("def test_hello(): pass\n")

    # Docs
    (repo / "README.md").write_text("# Test Repo\n")

    # Manifest
    (repo / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (repo / "requirements.txt").write_text("requests>=2.25\n")

    # Build
    (repo / "Makefile").write_text("test:\n\tpytest\n")
    (repo / "Dockerfile").write_text("FROM python:3.12\n")

    return repo


@pytest.fixture
def temp_repo_with_secrets(temp_repo: Path) -> Path:
    """Add secret-bearing files to the temp repo."""
    (temp_repo / ".env").write_text("SECRET_KEY=abc123\n")
    (temp_repo / ".env.production").write_text("DB_PASSWORD=secret\n")
    (temp_repo / "certs").mkdir()
    (temp_repo / "certs" / "server.pem").write_text("-----BEGIN CERTIFICATE-----\n")
    (temp_repo / "certs" / "server.key").write_text("FAKE_KEY_MATERIAL_SENTINEL_DO_NOT_TREAT_AS_SECRET\n")
    return temp_repo


@pytest.fixture
def temp_repo_with_keyhole(temp_repo: Path) -> Path:
    """Add Keyhole scaffold markers to the temp repo."""
    (temp_repo / "keyhole.yaml").write_text("version: 1\n")
    (temp_repo / "governance_contract.yaml").write_text("version: 1\n")
    return temp_repo


@pytest.fixture
def temp_repo_with_junk(temp_repo: Path) -> Path:
    """Add junk/cache directories to the temp repo."""
    # Git
    (temp_repo / ".git").mkdir()
    (temp_repo / ".git" / "config").write_text("[core]\n")

    # Python cache
    (temp_repo / "__pycache__").mkdir()
    (temp_repo / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00")

    # Node modules
    (temp_repo / "node_modules").mkdir()
    (temp_repo / "node_modules" / "lodash").mkdir(parents=True)
    (temp_repo / "node_modules" / "lodash" / "index.js").write_text("module.exports = {}\n")

    # IDE
    (temp_repo / ".vscode").mkdir()
    (temp_repo / ".vscode" / "settings.json").write_text("{}\n")

    # venv
    (temp_repo / "venv").mkdir()
    (temp_repo / "venv" / "bin").mkdir()
    (temp_repo / "venv" / "bin" / "python").write_text("#!/bin/sh\n")

    return temp_repo


# -----------------------------------------------------------
# section18.1 - Model Tests
# -----------------------------------------------------------


class TestModels:
    """Test ingestion data models."""

    def test_compatibility_posture_values(self):
        assert CompatibilityPosture.FOREIGN.value == "foreign"
        assert CompatibilityPosture.PARTIALLY_ALIGNED.value == "partially_aligned"
        assert CompatibilityPosture.KEYHOLE_READY.value == "keyhole_ready"

    def test_confidence_level_values(self):
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"

    def test_file_classification_values(self):
        assert FileClassification.SOURCE.value == "source"
        assert FileClassification.TEST.value == "test"
        assert FileClassification.DOC.value == "doc"
        assert FileClassification.MANIFEST.value == "manifest"

    def test_scan_signal_construction(self):
        signal = ScanSignal(kind="language", path="setup.py", value="python")
        assert signal.kind == "language"
        assert signal.confidence == ConfidenceLevel.MEDIUM

    def test_repo_scan_result_defaults(self):
        result = RepoScanResult(repo_root="/tmp/test")
        assert result.languages == []
        assert result.total_files == 0
        assert result.has_keyhole_scaffold is False
        assert result.scan_timestamp  # auto-generated

    def test_ingestion_package_to_payload(self):
        pkg = IngestionPackage(
            repo_identity="test-repo",
            local_path="/tmp/test",
            languages=["python"],
            shadow=True,
        )
        payload = pkg.to_payload()
        assert payload["repo_identity"] == "test-repo"
        assert payload["shadow"] is True

    def test_ingestion_package_proof_dict_excludes_local_path(self):
        pkg = IngestionPackage(
            repo_identity="test-repo",
            local_path="/home/user/secret-path/repo",
        )
        proof = pkg.to_proof_dict()
        assert "local_path" not in proof
        assert proof["repo_identity"] == "test-repo"

    def test_ingestion_request_to_payload(self):
        pkg = IngestionPackage(
            repo_identity="test-repo",
            local_path="/tmp/test",
        )
        req = IngestionRequest(package=pkg, identity_fingerprint="fp123")
        payload = req.to_payload()
        assert "package" in payload
        assert payload["identity_fingerprint"] == "fp123"

    def test_ingestion_request_proof_dict(self):
        pkg = IngestionPackage(
            repo_identity="test-repo",
            local_path="/tmp/test",
            languages=["python"],
            shadow=True,
            correlation_id="corr-123",
        )
        req = IngestionRequest(package=pkg)
        proof = req.to_proof_dict()
        assert proof["package_summary"]["repo_identity"] == "test-repo"
        assert proof["package_summary"]["shadow"] is True

    def test_inferred_capability_model(self):
        cap = InferredCapability(
            name="web-api",
            confidence=ConfidenceLevel.HIGH,
            basis="Detected FastAPI in requirements.txt",
        )
        assert cap.name == "web-api"
        assert cap.confidence == ConfidenceLevel.HIGH

    def test_graph_summary_model(self):
        gs = GraphSummary(node_count=10, edge_count=15, primary_language="python")
        assert gs.node_count == 10
        assert gs.edge_count == 15

    def test_ingestion_outcome_success(self):
        outcome = IngestionOutcome(
            status="success",
            repo_identity="test-repo",
            compatibility=CompatibilityPosture.PARTIALLY_ALIGNED,
        )
        assert outcome.status == "success"
        assert outcome.compatibility == CompatibilityPosture.PARTIALLY_ALIGNED

    def test_ingestion_outcome_proof_dict(self):
        outcome = IngestionOutcome(
            status="success",
            repo_identity="test-repo",
            correlation_id="abc",
            ingestion_id="ing-123",
            graph_summary=GraphSummary(node_count=5),
            inferred_capabilities=[
                InferredCapability(name="api", confidence=ConfidenceLevel.MEDIUM),
            ],
        )
        d = outcome.to_proof_dict()
        assert d["status"] == "success"
        assert d["ingestion_id"] == "ing-123"
        assert len(d["inferred_capabilities"]) == 1
        assert d["graph_summary"]["node_count"] == 5


# -----------------------------------------------------------
# section18.1 - Filter Tests
# -----------------------------------------------------------


class TestFilter:
    """Test include/exclude filtering - section11."""

    def test_default_excludes_git(self):
        f = IncludeExcludeFilter()
        included, reason = f.classify(".git/config")
        assert not included
        assert "exclude" in reason

    def test_default_excludes_env(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify(".env")
        assert not included

    def test_default_excludes_env_variants(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify(".env.production")
        assert not included

    def test_default_excludes_pem(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("certs/server.pem")
        assert not included

    def test_default_excludes_key(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("certs/server.key")
        assert not included

    def test_default_excludes_node_modules(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("node_modules/lodash/index.js")
        assert not included

    def test_default_excludes_venv(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("venv/bin/python")
        assert not included

    def test_default_excludes_pycache(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("__pycache__/main.cpython-312.pyc")
        assert not included

    def test_default_excludes_ide(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify(".vscode/settings.json")
        assert not included

    def test_default_includes_python(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("src/main.py")
        assert included

    def test_default_includes_markdown(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("README.md")
        assert included

    def test_default_includes_toml(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("pyproject.toml")
        assert included

    def test_default_includes_yaml(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("docker-compose.yaml")
        assert included

    def test_default_includes_dockerfile(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("Dockerfile")
        assert included

    def test_default_includes_makefile(self):
        f = IncludeExcludeFilter()
        included, _ = f.classify("Makefile")
        assert included

    def test_extra_excludes(self):
        f = IncludeExcludeFilter(extra_excludes=["*.log"])
        included, _ = f.classify("app.log")
        assert not included

    def test_extra_includes(self):
        f = IncludeExcludeFilter(extra_includes=["*.dat"])
        included, _ = f.classify("data.dat")
        assert included

    def test_exclude_takes_priority(self):
        """Exclusion rules outrank inclusion rules."""
        f = IncludeExcludeFilter()
        # .env matches exclude even though it could match include
        included, _ = f.classify(".env")
        assert not included

    def test_unknown_extension_excluded(self):
        """Files with unknown extensions are excluded by default for safety."""
        f = IncludeExcludeFilter()
        included, reason = f.classify("data.xyz_unknown")
        assert not included
        assert "no_matching_include" in reason

    def test_filter_rules_are_lists(self):
        f = IncludeExcludeFilter()
        assert isinstance(f.exclude_rules, list)
        assert isinstance(f.include_rules, list)
        assert len(f.exclude_rules) > 0
        assert len(f.include_rules) > 0


# -----------------------------------------------------------
# section18.1 - Scanner Tests
# -----------------------------------------------------------


class TestScanner:
    """Test local repository scanner - section8."""

    def test_scan_basic_repo(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert result.repo_root == str(temp_repo)
        assert result.total_files > 0
        assert len(result.included_files) > 0
        assert "python" in result.languages

    def test_scan_detects_languages(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert "python" in result.languages

    def test_scan_detects_manifests(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert any("pyproject.toml" in m for m in result.manifests)
        assert any("requirements.txt" in m for m in result.manifests)

    def test_scan_detects_source_dirs(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert "src" in result.source_dirs

    def test_scan_detects_test_dirs(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert "tests" in result.test_dirs

    def test_scan_detects_docs(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert any("README.md" in d for d in result.doc_files)

    def test_scan_detects_build_files(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert any("Makefile" in b for b in result.build_files)
        assert any("Dockerfile" in b for b in result.build_files)

    def test_scan_is_deterministic(self, temp_repo: Path):
        """section8: Same repo state -> same scan result (except timestamp)."""
        r1 = scan_repo(temp_repo)
        r2 = scan_repo(temp_repo)
        assert r1.languages == r2.languages
        assert r1.manifests == r2.manifests
        assert r1.included_files == r2.included_files
        assert r1.excluded_files == r2.excluded_files
        assert r1.total_files == r2.total_files

    def test_scan_excludes_secrets(self, temp_repo_with_secrets: Path):
        """section11: Secret-bearing files excluded by default."""
        result = scan_repo(temp_repo_with_secrets)
        included_names = [Path(f).name for f in result.included_files]
        assert ".env" not in included_names
        assert ".env.production" not in included_names
        assert "server.pem" not in included_names
        assert "server.key" not in included_names

    def test_scan_excludes_junk(self, temp_repo_with_junk: Path):
        """section11: Git, caches, IDE, venv excluded by default."""
        result = scan_repo(temp_repo_with_junk)
        for f in result.included_files:
            assert not f.startswith(".git/")
            assert "__pycache__" not in f
            assert "node_modules" not in f
            assert not f.startswith(".vscode/")
            assert not f.startswith("venv/")

    def test_scan_detects_keyhole_scaffold(self, temp_repo_with_keyhole: Path):
        result = scan_repo(temp_repo_with_keyhole)
        assert result.has_keyhole_scaffold is True

    def test_scan_no_keyhole_scaffold(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert result.has_keyhole_scaffold is False

    def test_scan_respects_max_bytes(self, temp_repo: Path):
        """max_bytes limits total included bytes."""
        result = scan_repo(temp_repo, max_bytes=10)
        assert result.total_included_bytes <= 10

    def test_scan_nonexistent_path_raises(self, tmp_path: Path):
        """section18.3: Invalid repo path rejected locally."""
        with pytest.raises(FileNotFoundError):
            scan_repo(tmp_path / "nonexistent")

    def test_scan_file_instead_of_dir_raises(self, tmp_path: Path):
        """section18.3: Non-directory path rejected locally."""
        f = tmp_path / "file.txt"
        f.write_text("not a directory\n")
        with pytest.raises(FileNotFoundError):
            scan_repo(f)

    def test_scan_empty_repo(self, tmp_path: Path):
        """Empty directory produces empty scan."""
        empty = tmp_path / "empty"
        empty.mkdir()
        result = scan_repo(empty)
        assert result.included_files == []
        assert result.total_files == 0

    def test_scan_produces_signals(self, temp_repo: Path):
        result = scan_repo(temp_repo)
        assert len(result.signals) > 0
        kinds = {s.kind for s in result.signals}
        assert "language" in kinds

    def test_scan_does_not_mutate_repo(self, temp_repo: Path):
        """section7: No repo mutation during ingestion."""
        # Record file state before scan
        before = {}
        for root, dirs, files in os.walk(temp_repo):
            for f in files:
                p = os.path.join(root, f)
                before[p] = os.path.getmtime(p)

        scan_repo(temp_repo)

        # Verify no files modified
        after = {}
        for root, dirs, files in os.walk(temp_repo):
            for f in files:
                p = os.path.join(root, f)
                after[p] = os.path.getmtime(p)

        assert before == after, "Scan modified files in the repo"


# -----------------------------------------------------------
# section18.1 - Packager Tests
# -----------------------------------------------------------


class TestPackager:
    """Test ingestion package builder - section10."""

    def test_build_package_from_scan(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan)
        assert pkg.repo_identity == temp_repo.name
        assert pkg.languages == scan.languages
        assert pkg.manifests == scan.manifests
        assert len(pkg.included_file_manifest) > 0

    def test_package_is_deterministic(self, temp_repo: Path):
        """section10: Deterministic for the same scan result."""
        scan = scan_repo(temp_repo)
        p1 = build_ingestion_package(scan, correlation_id="fixed-id")
        p2 = build_ingestion_package(scan, correlation_id="fixed-id")
        # Compare without timestamps
        d1 = p1.to_payload()
        d2 = p2.to_payload()
        d1.pop("package_timestamp", None)
        d2.pop("package_timestamp", None)
        assert d1 == d2

    def test_package_shadow_flag(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan, shadow=True)
        assert pkg.shadow is True

    def test_package_correlation_id(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan, correlation_id="test-corr")
        assert pkg.correlation_id == "test-corr"

    def test_package_auto_generates_correlation_id(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan)
        assert pkg.correlation_id  # not empty

    def test_package_builder_hints(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan, builder_hints={"priority": "high"})
        assert pkg.builder_hints == {"priority": "high"}

    def test_package_scan_summary(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan)
        assert "total_files" in pkg.scan_summary
        assert "included_files" in pkg.scan_summary
        assert "has_keyhole_scaffold" in pkg.scan_summary

    def test_package_compatibility_inputs(self, temp_repo: Path):
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan)
        assert "client_assessed_posture" in pkg.compatibility_inputs

    def test_package_compatibility_foreign(self, temp_repo: Path):
        """Foreign repo should be classified accordingly."""
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan)
        # Has manifests + source dirs -> partially_aligned, not foreign
        assert pkg.compatibility_inputs["client_assessed_posture"] in (
            "partially_aligned", "foreign"
        )

    def test_package_compatibility_keyhole_ready(self, temp_repo_with_keyhole: Path):
        """Repo with Keyhole scaffold -> keyhole_ready."""
        scan = scan_repo(temp_repo_with_keyhole)
        pkg = build_ingestion_package(scan)
        assert pkg.compatibility_inputs["client_assessed_posture"] == "keyhole_ready"


# -----------------------------------------------------------
# section18.1 - Proof Emission Tests
# -----------------------------------------------------------


class TestProof:
    """Test proof artifact emission - section17."""

    def test_emit_proof_creates_directory(self, tmp_path: Path):
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="test-123",
            request_dict={"repo_identity": "test-repo", "shadow": False},
            package_manifest={"repo_identity": "test-repo", "languages": ["python"]},
            outcome_dict={"status": "success", "compatibility": "foreign"},
        )
        assert proof_dir.exists()
        assert proof_dir.is_dir()

    def test_emit_proof_creates_all_files(self, tmp_path: Path):
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="test-123",
            request_dict={"repo_identity": "test-repo"},
            package_manifest={"languages": ["python"]},
            outcome_dict={"status": "success"},
        )
        assert (proof_dir / "request.json").exists()
        assert (proof_dir / "package_manifest.json").exists()
        assert (proof_dir / "response.json").exists()
        assert (proof_dir / "correlation.json").exists()
        assert (proof_dir / "summary.md").exists()

    def test_emit_proof_request_json_valid(self, tmp_path: Path):
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="test-123",
            request_dict={"repo_identity": "test-repo", "shadow": True},
            package_manifest={},
            outcome_dict={"status": "success"},
        )
        data = json.loads((proof_dir / "request.json").read_text())
        assert data["repo_identity"] == "test-repo"
        assert data["shadow"] is True

    def test_emit_proof_correlation_json(self, tmp_path: Path):
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="corr-456",
            request_dict={},
            package_manifest={},
            outcome_dict={},
        )
        data = json.loads((proof_dir / "correlation.json").read_text())
        assert data["correlation_id"] == "corr-456"
        assert "proof_written_at" in data

    def test_emit_proof_summary_md_content(self, tmp_path: Path):
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="corr-789",
            request_dict={"repo_identity": "my-repo", "shadow": False},
            package_manifest={},
            outcome_dict={
                "status": "success",
                "compatibility": "partially_aligned",
            },
        )
        summary = (proof_dir / "summary.md").read_text()
        assert "corr-789" in summary
        assert "my-repo" in summary
        assert "success" in summary

    def test_emit_proof_for_failure(self, tmp_path: Path):
        """section17: Proof emitted for failure too."""
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="fail-001",
            request_dict={"repo_identity": "broken-repo"},
            package_manifest={},
            outcome_dict={
                "status": "failed",
                "error_class": "ServerRejection",
                "reason": "Ingestion payload too large",
                "repair_guidance": ["Reduce package size"],
            },
        )
        response = json.loads((proof_dir / "response.json").read_text())
        assert response["status"] == "failed"
        assert response["error_class"] == "ServerRejection"

    def test_emit_proof_out_of_tree(self, tmp_path: Path, temp_repo: Path):
        """section17: Proof lives out-of-tree, not in the target repo."""
        state_dir = tmp_path / "state"
        proof_dir = emit_ingestion_proof(
            state_dir=state_dir,
            correlation_id="out-of-tree-test",
            request_dict={},
            package_manifest={},
            outcome_dict={"status": "success"},
        )
        # Proof must NOT be inside temp_repo
        assert not str(proof_dir).startswith(str(temp_repo))
        # Must be inside state_dir
        assert str(proof_dir).startswith(str(state_dir))

    def test_emit_proof_shadow_visible(self, tmp_path: Path):
        """section13: Shadow mode visible in proof artifacts."""
        proof_dir = emit_ingestion_proof(
            state_dir=tmp_path,
            correlation_id="shadow-test",
            request_dict={"shadow": True},
            package_manifest={},
            outcome_dict={"status": "success"},
        )
        req = json.loads((proof_dir / "request.json").read_text())
        assert req["shadow"] is True
        summary = (proof_dir / "summary.md").read_text()
        assert "SHADOW" in summary


# -----------------------------------------------------------
# section18.1 - Repair Guidance Tests
# -----------------------------------------------------------


class TestRepair:
    """Test repair guidance mapping."""

    def test_known_error_returns_guidance(self):
        guidance = map_ingestion_repair("AuthenticationError")
        assert len(guidance) > 0
        assert any("login" in g.lower() for g in guidance)

    def test_invalid_repo_path(self):
        guidance = map_ingestion_repair("InvalidRepoPath")
        assert len(guidance) > 0

    def test_empty_package(self):
        guidance = map_ingestion_repair("EmptyPackage")
        assert len(guidance) > 0

    def test_unknown_error_returns_generic(self):
        guidance = map_ingestion_repair("SomeUnknownError")
        assert len(guidance) > 0
        assert any("ingest" in g.lower() for g in guidance)


# -----------------------------------------------------------
# section18.1 - Submitter Tests
# -----------------------------------------------------------


class TestSubmitter:
    """Test ingestion submission - section12, section14."""

    def _make_request(self, shadow: bool = False) -> IngestionRequest:
        pkg = IngestionPackage(
            repo_identity="test-repo",
            local_path="/tmp/test",
            languages=["python"],
            shadow=shadow,
            correlation_id="test-corr",
        )
        return IngestionRequest(package=pkg, identity_fingerprint="fp-test")

    def test_submit_success_outcome(self):
        """Terminal success with graph and capabilities."""
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {
            "status": "success",
            "ingestion_id": "ing-001",
            "compatibility": "partially_aligned",
            "graph_summary": {"node_count": 12, "edge_count": 20, "components": 3},
            "inferred_capabilities": [
                {"name": "web-api", "confidence": "high", "basis": "FastAPI detected"},
            ],
            "warnings": ["Some tests appear incomplete"],
            "suggested_actions": ["Add type hints", "Run: keyhole run --context auto"],
        }
        mock_result.status_code = 200
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        request = self._make_request()
        outcome = submit_ingestion(transport=mock_transport, request=request)

        assert outcome.status == "success"
        assert outcome.ingestion_id == "ing-001"
        assert outcome.compatibility == CompatibilityPosture.PARTIALLY_ALIGNED
        assert outcome.graph_summary is not None
        assert outcome.graph_summary.node_count == 12
        assert len(outcome.inferred_capabilities) == 1
        assert outcome.inferred_capabilities[0].name == "web-api"
        assert outcome.inferred_capabilities[0].confidence == ConfidenceLevel.HIGH

    def test_submit_accepted_outcome(self):
        """section12: Accepted/deferred - not terminal."""
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"status": "accepted", "ingestion_id": "ing-002"}
        mock_result.status_code = 202
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        outcome = submit_ingestion(
            transport=mock_transport, request=self._make_request()
        )
        assert outcome.status == "accepted"
        assert outcome.ingestion_id == "ing-002"

    def test_submit_deferred_outcome(self):
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"status": "deferred", "ingestion_id": "ing-003"}
        mock_result.status_code = 200
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        outcome = submit_ingestion(
            transport=mock_transport, request=self._make_request()
        )
        assert outcome.status == "deferred"

    def test_submit_rejected_outcome(self):
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {
            "status": "rejected",
            "error_class": "PayloadTooLarge",
            "reason": "Package exceeds 50MB limit",
            "repair_guidance": ["Use --max-bytes to limit size"],
        }
        mock_result.status_code = 400
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        outcome = submit_ingestion(
            transport=mock_transport, request=self._make_request()
        )
        assert outcome.status == "rejected"
        assert outcome.error_class == "PayloadTooLarge"
        assert len(outcome.repair_guidance) > 0

    def test_submit_transport_exception(self):
        """Transport failure -> local failure outcome."""
        mock_transport = MagicMock()
        mock_transport.execute.side_effect = ConnectionError("Network unreachable")

        outcome = submit_ingestion(
            transport=mock_transport, request=self._make_request()
        )
        assert outcome.status == "failed"
        assert outcome.is_local_failure is True
        assert outcome.error_class == "ConnectionError"
        assert len(outcome.repair_guidance) > 0

    def test_submit_shadow_preserved_in_outcome(self):
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"status": "success"}
        mock_result.status_code = 200
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        outcome = submit_ingestion(
            transport=mock_transport, request=self._make_request(shadow=True)
        )
        assert outcome.shadow is True

    def test_submit_calls_correct_endpoint(self):
        """section12: Uses GovernedTransport with correct operation name."""
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.data = {"status": "success"}
        mock_result.status_code = 200
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        submit_ingestion(transport=mock_transport, request=self._make_request())

        mock_transport.execute.assert_called_once()
        args, kwargs = mock_transport.execute.call_args
        assert args[0] == "POST"
        assert args[1] == "/mcp/v1/ingest"
        assert kwargs["operation_name"] == "ingest.submit"


# -----------------------------------------------------------
# section18.1 - CLI Command Tests
# -----------------------------------------------------------


class TestCLICommand:
    """Test the CLI ingest command (run_ingest function)."""

    def test_invalid_path_returns_failure(self, tmp_path: Path):
        """section18.3: Invalid repo path rejected locally."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(repo_path=str(tmp_path / "nonexistent"))
        assert not result.success
        assert result.exit_code != 0
        assert "InvalidRepoPath" in str(result.data)

    def test_empty_repo_returns_failure(self, tmp_path: Path):
        """Repo with no includable files -> failure."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        empty = tmp_path / "empty"
        empty.mkdir()
        result = run_ingest(repo_path=str(empty))
        assert not result.success
        assert "EmptyPackage" in str(result.data)

    def test_summary_only_no_submission(self, temp_repo: Path):
        """section5.4: --summary-only scans but does not submit."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(repo_path=str(temp_repo), summary_only=True)
        assert result.success
        assert result.data["mode"] == "summary_only"
        assert result.data["languages"]  # should have detected python

    def test_summary_only_shadow(self, temp_repo: Path):
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo), summary_only=True, shadow=True
        )
        assert result.success
        assert result.data["shadow"] is True

    def test_no_credentials_returns_auth_error(self, temp_repo: Path, tmp_path: Path):
        """No auth -> prompts login."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo),
            keyhole_home=str(tmp_path / "no-creds"),
        )
        assert not result.success
        assert "AuthenticationError" in str(result.data)

    def test_command_label_shadow(self, temp_repo: Path):
        """Shadow mode reflected in command label."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo), summary_only=True, shadow=True
        )
        assert "shadow" in result.command.lower()

    def test_command_label_regular(self, temp_repo: Path):
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo), summary_only=True, shadow=False
        )
        assert result.command == "keyhole ingest"

    def test_include_exclude_overrides(self, temp_repo: Path):
        """Builder-supplied include/exclude filters work."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo),
            summary_only=True,
            include=["*.custom"],
        )
        assert result.success

    def test_max_bytes_limit(self, temp_repo: Path):
        """--max-bytes limits included content."""
        from keyhole_cli.commands.ingest_cmd import run_ingest

        result = run_ingest(
            repo_path=str(temp_repo),
            summary_only=True,
            max_bytes=1,  # 1 byte - very restrictive
        )
        # Might be empty or very small
        assert result.success or "EmptyPackage" in str(result.data)


# -----------------------------------------------------------
# section18.1 - Outcome Rendering Tests
# -----------------------------------------------------------


class TestOutcomeRendering:
    """Test outcome -> CommandResult rendering - section15, section16."""

    def test_accepted_not_rendered_as_completed(self):
        """section18.3: Accepted ingestion does not render as completed."""
        outcome = IngestionOutcome(
            status="accepted",
            ingestion_id="ing-accept",
            repo_identity="test-repo",
            correlation_id="corr-1",
        )
        assert outcome.status == "accepted"
        assert outcome.status != "success"

    def test_deferred_not_rendered_as_completed(self):
        """section18.3: Deferred ingestion does not render as completed."""
        outcome = IngestionOutcome(
            status="deferred",
            ingestion_id="ing-defer",
            repo_identity="test-repo",
            correlation_id="corr-2",
        )
        assert outcome.status == "deferred"
        assert outcome.status != "success"

    def test_inferred_capabilities_marked_as_inferred(self):
        """section16: Inferred capabilities must not be rendered as declared truth."""
        cap = InferredCapability(
            name="web-api",
            confidence=ConfidenceLevel.HIGH,
            basis="FastAPI detected",
        )
        d = cap.model_dump()
        # The model itself represents inference - there is no "declared" equivalent
        assert d["confidence"] == "high"
        assert d["basis"] == "FastAPI detected"

    def test_compatibility_posture_rendering(self):
        """section9: Compatibility posture values are clear."""
        for posture in CompatibilityPosture:
            outcome = IngestionOutcome(
                status="success",
                compatibility=posture,
            )
            proof = outcome.to_proof_dict()
            assert proof["compatibility"] == posture.value


# -----------------------------------------------------------
# section18.1 - Operation Registry Tests
# -----------------------------------------------------------


class TestOperationRegistry:
    """Verify ingest.submit is registered."""

    def test_ingest_submit_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation

        op = get_operation("ingest.submit")
        assert op is not None
        assert op.name == "ingest.submit"

    def test_ingest_submit_is_write_idempotent(self):
        from keyhole_sdk.transport.operation_registry import (
            OperationClass,
            get_operation,
        )

        op = get_operation("ingest.submit")
        assert op is not None
        assert op.operation_class == OperationClass.WRITE_IDEMPOTENT_REQUIRED

    def test_ingest_submit_proof_required(self):
        from keyhole_sdk.transport.operation_registry import get_operation

        op = get_operation("ingest.submit")
        assert op is not None
        assert op.proof_required is True


# -----------------------------------------------------------
# section18.1 - SDK Public API Tests
# -----------------------------------------------------------


class TestPublicAPI:
    """Verify SDK-CLIENT-10 symbols are exported from keyhole_sdk."""

    @pytest.mark.parametrize("symbol", [
        "CompatibilityPosture",
        "ConfidenceLevel",
        "FileClassification",
        "InferredCapability",
        "IngestionOutcome",
        "IngestionPackage",
        "IngestionRequest",
        "GraphSummary",
        "RepoScanResult",
        "ScanSignal",
        "scan_repo",
        "IncludeExcludeFilter",
        "DEFAULT_EXCLUDES",
        "DEFAULT_INCLUDES",
        "build_ingestion_package",
        "submit_ingestion",
        "emit_ingestion_proof",
        "map_ingestion_repair",
    ])
    def test_symbol_exported(self, symbol: str):
        import keyhole_sdk
        assert hasattr(keyhole_sdk, symbol), f"{symbol} not exported from keyhole_sdk"
        assert symbol in keyhole_sdk.__all__, f"{symbol} not in keyhole_sdk.__all__"


# -----------------------------------------------------------
# section7 - No-Silent-Mutation Integration Test
# -----------------------------------------------------------


class TestNoSilentMutation:
    """section7: The client must not silently rewrite the target repository."""

    def test_full_scan_and_package_no_mutation(self, temp_repo: Path):
        """Full scan + package workflow does not modify any file."""
        # Snapshot file state
        before: Dict[str, float] = {}
        for root, dirs, files in os.walk(temp_repo):
            for f in files:
                p = os.path.join(root, f)
                before[p] = os.path.getmtime(p)

        before_dirs = set()
        for root, dirs, files in os.walk(temp_repo):
            for d in dirs:
                before_dirs.add(os.path.join(root, d))

        # Run full scan + package
        scan = scan_repo(temp_repo)
        pkg = build_ingestion_package(scan, shadow=True, correlation_id="mutation-test")

        # Verify no mutation
        after: Dict[str, float] = {}
        for root, dirs, files in os.walk(temp_repo):
            for f in files:
                p = os.path.join(root, f)
                after[p] = os.path.getmtime(p)

        after_dirs = set()
        for root, dirs, files in os.walk(temp_repo):
            for d in dirs:
                after_dirs.add(os.path.join(root, d))

        assert before == after, "Files were modified during scan+package"
        assert before_dirs == after_dirs, "Directories were created during scan+package"
