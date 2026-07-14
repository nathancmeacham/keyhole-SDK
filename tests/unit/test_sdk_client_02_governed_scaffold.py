"""SDK-CLIENT-02 - Governed Repo Scaffold test suite.

Tests cover:
  - Scaffold generation (fresh directory)
  - Idempotent rerun detection
  - --force overwrite behavior
  - --dry-run preview
  - Invalid template rejection
  - Missing name/path rejection
  - Deterministic file plan digest
  - All expected files and directories created
  - YAML content correctness
  - README content correctness
  - .gitkeep presence in all managed directories
  - CommandResult contract (exit codes, fields, next_steps)
  - No private/platform internals leaked in output
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

# -- Make CLI package importable ------------------------------
CLI_PKG = Path(__file__).resolve().parent.parent.parent / "packages" / "python" / "keyhole-cli"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))

from keyhole_cli.result import (
    CommandResult,
    EXIT_SUCCESS,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
)
from keyhole_cli.commands.init_vertical import (
    run_init_vertical,
    MANAGED_DIRS,
    MANAGED_FILES,
    SCHEMA_VERSION,
    _build_file_plan,
    _compute_plan_digest,
)


# --------------------------------------------------------------
# Helper
# --------------------------------------------------------------

def _scaffold_in_tmp(**kwargs: Any) -> CommandResult:
    """Run init vertical in a fresh temp directory."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / kwargs.pop("name", "test-repo")
        return run_init_vertical(name=target.name, path=str(target), **kwargs)


def _scaffold_fresh(name: str = "test-repo") -> tuple[CommandResult, Path]:
    """Create a scaffold in a temp dir and return result + base path."""
    tmp = tempfile.mkdtemp()
    target = Path(tmp) / name
    result = run_init_vertical(name=name, path=str(target))
    return result, target


# --------------------------------------------------------------
# Fresh scaffold - happy path
# --------------------------------------------------------------

class TestFreshScaffold:
    """Scaffold generation in a fresh directory must succeed."""

    def test_success(self) -> None:
        result, base = _scaffold_fresh()
        assert result.success is True
        assert result.exit_code == EXIT_SUCCESS
        assert result.command == "init vertical"

    def test_keyhole_yaml_exists(self) -> None:
        result, base = _scaffold_fresh()
        assert (base / "keyhole.yaml").exists()

    def test_governance_contract_exists(self) -> None:
        result, base = _scaffold_fresh()
        assert (base / "governance_contract.yaml").exists()

    def test_capability_passport_exists(self) -> None:
        result, base = _scaffold_fresh()
        assert (base / "capability_passport.yaml").exists()

    def test_dependencies_exists(self) -> None:
        result, base = _scaffold_fresh()
        assert (base / "dependencies.yaml").exists()

    def test_all_managed_dirs(self) -> None:
        result, base = _scaffold_fresh()
        for d in MANAGED_DIRS:
            assert (base / d).is_dir(), f"Missing directory: {d}"
            assert (base / d / ".gitkeep").exists(), f"Missing .gitkeep in {d}"

    def test_all_managed_files(self) -> None:
        result, base = _scaffold_fresh()
        for f in MANAGED_FILES:
            assert (base / f).exists(), f"Missing managed file: {f}"

    def test_data_contains_created_list(self) -> None:
        result, base = _scaffold_fresh()
        assert "created" in result.data
        assert len(result.data["created"]) == len(MANAGED_FILES)

    def test_data_contains_plan_digest(self) -> None:
        result, base = _scaffold_fresh()
        assert "plan_digest" in result.data
        assert result.data["plan_digest"].startswith("sha256:")

    def test_next_steps_present(self) -> None:
        result, base = _scaffold_fresh()
        assert len(result.next_steps) > 0


# --------------------------------------------------------------
# YAML content correctness
# --------------------------------------------------------------

class TestYAMLContent:
    """Generated YAML files must contain correct schema version and fields."""

    def test_keyhole_yaml_schema_version(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "keyhole.yaml").read_text()
        assert f"schema_version: {SCHEMA_VERSION}" in content

    def test_keyhole_yaml_repo_name(self) -> None:
        _, base = _scaffold_fresh("my-vertical")
        content = (base / "keyhole.yaml").read_text()
        assert "name: my-vertical" in content

    def test_keyhole_yaml_kind(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "keyhole.yaml").read_text()
        assert "kind: vertical" in content

    def test_governance_contract_schema_version(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "governance_contract.yaml").read_text()
        assert f"schema_version: {SCHEMA_VERSION}" in content

    def test_governance_contract_repo(self) -> None:
        _, base = _scaffold_fresh("my-repo")
        content = (base / "governance_contract.yaml").read_text()
        assert "repo: my-repo" in content

    def test_capability_passport_schema_version(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "capability_passport.yaml").read_text()
        assert f"schema_version: {SCHEMA_VERSION}" in content

    def test_dependencies_schema_version(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "dependencies.yaml").read_text()
        assert f"schema_version: {SCHEMA_VERSION}" in content


# --------------------------------------------------------------
# README content correctness
# --------------------------------------------------------------

class TestREADMEContent:
    """Generated README files must contain accurate guidance."""

    def test_docs_readme_contains_scaffold_notice(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "docs" / "README.md").read_text()
        assert "keyhole init vertical" in content

    def test_docs_readme_contains_local_only_notice(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "docs" / "README.md").read_text()
        assert "local only" in content.lower()

    def test_proof_readme_hot_extended_split(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "proof_bundle" / "README.md").read_text()
        assert "core/" in content
        assert "extended/" in content

    def test_context_readme_references_context(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / "context" / "README.md").read_text()
        assert "requests/" in content
        assert "resolved/" in content

    def test_keyhole_readme_warns_not_authoritative(self) -> None:
        _, base = _scaffold_fresh()
        content = (base / ".keyhole" / "README.md").read_text()
        assert "not" in content.lower() and "authoritative" in content.lower()


# --------------------------------------------------------------
# Rerun safety - already initialized
# --------------------------------------------------------------

class TestRerunSafety:
    """Running init vertical twice without --force must fail safely."""

    def test_second_run_fails(self) -> None:
        result1, base = _scaffold_fresh()
        assert result1.success is True
        # Run again at same path
        result2 = run_init_vertical(name=base.name, path=str(base))
        assert result2.success is False
        assert result2.exit_code == EXIT_FAILURE
        assert "already_initialized" in str(result2.data.get("error", ""))

    def test_second_run_lists_conflicts(self) -> None:
        result1, base = _scaffold_fresh()
        result2 = run_init_vertical(name=base.name, path=str(base))
        assert "existing_files" in result2.data
        assert len(result2.data["existing_files"]) > 0

    def test_second_run_suggests_force(self) -> None:
        result1, base = _scaffold_fresh()
        result2 = run_init_vertical(name=base.name, path=str(base))
        assert any("--force" in s for s in result2.next_steps)


# --------------------------------------------------------------
# --force overwrite behavior
# --------------------------------------------------------------

class TestForceOverwrite:
    """--force must overwrite managed files without error."""

    def test_force_succeeds_after_init(self) -> None:
        result1, base = _scaffold_fresh()
        assert result1.success is True
        result2 = run_init_vertical(name=base.name, path=str(base), force=True)
        assert result2.success is True
        assert result2.exit_code == EXIT_SUCCESS

    def test_force_overwrites_keyhole_yaml(self) -> None:
        _, base = _scaffold_fresh()
        # Modify keyhole.yaml
        (base / "keyhole.yaml").write_text("corrupted: true\n")
        result2 = run_init_vertical(name=base.name, path=str(base), force=True)
        assert result2.success is True
        content = (base / "keyhole.yaml").read_text()
        assert "corrupted" not in content
        assert "schema_version" in content


# --------------------------------------------------------------
# --dry-run preview
# --------------------------------------------------------------

class TestDryRun:
    """--dry-run must preview the scaffold without writing anything."""

    def test_dry_run_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dry-repo"
            result = run_init_vertical(name="dry-repo", path=str(target), dry_run=True)
            assert result.success is True
            assert result.exit_code == EXIT_SUCCESS
            assert result.data.get("dry_run") is True

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dry-repo"
            run_init_vertical(name="dry-repo", path=str(target), dry_run=True)
            assert not target.exists()

    def test_dry_run_lists_managed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dry-repo"
            result = run_init_vertical(name="dry-repo", path=str(target), dry_run=True)
            assert "managed_files" in result.data
            assert len(result.data["managed_files"]) == len(MANAGED_FILES)

    def test_dry_run_lists_managed_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dry-repo"
            result = run_init_vertical(name="dry-repo", path=str(target), dry_run=True)
            assert "managed_dirs" in result.data
            assert len(result.data["managed_dirs"]) == len(MANAGED_DIRS)

    def test_dry_run_includes_plan_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dry-repo"
            result = run_init_vertical(name="dry-repo", path=str(target), dry_run=True)
            assert result.data.get("plan_digest", "").startswith("sha256:")


# --------------------------------------------------------------
# Invalid template
# --------------------------------------------------------------

class TestInvalidTemplate:
    """Only 'default' template is supported."""

    def test_unknown_template_fails(self) -> None:
        result = run_init_vertical(name="x", path="/tmp/x", template="nonexistent")
        assert result.success is False
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "invalid_template" in str(result.data.get("error", ""))


# --------------------------------------------------------------
# Missing name/path
# --------------------------------------------------------------

class TestMissingNameOrPath:
    """Must fail with clear guidance if neither name nor path is given."""

    def test_no_name_no_path(self) -> None:
        result = run_init_vertical()
        assert result.success is False
        assert result.exit_code == EXIT_INVALID_INPUT
        assert "missing_name" in str(result.data.get("error", ""))


# --------------------------------------------------------------
# Deterministic digest
# --------------------------------------------------------------

class TestDeterministicDigest:
    """The file plan digest must be deterministic for the same inputs."""

    def test_same_inputs_same_digest(self) -> None:
        ts = "2025-01-01T00:00:00+00:00"
        plan1 = _build_file_plan("test-repo", ts)
        plan2 = _build_file_plan("test-repo", ts)
        assert _compute_plan_digest(plan1) == _compute_plan_digest(plan2)

    def test_different_name_different_digest(self) -> None:
        ts = "2025-01-01T00:00:00+00:00"
        plan1 = _build_file_plan("repo-a", ts)
        plan2 = _build_file_plan("repo-b", ts)
        assert _compute_plan_digest(plan1) != _compute_plan_digest(plan2)


# --------------------------------------------------------------
# CommandResult contract
# --------------------------------------------------------------

class TestCommandResultContract:
    """CommandResult must follow the shared CLI result contract."""

    def test_command_field(self) -> None:
        result, _ = _scaffold_fresh()
        assert result.command == "init vertical"

    def test_success_type(self) -> None:
        result, _ = _scaffold_fresh()
        assert isinstance(result.success, bool)

    def test_exit_code_type(self) -> None:
        result, _ = _scaffold_fresh()
        assert isinstance(result.exit_code, int)

    def test_data_type(self) -> None:
        result, _ = _scaffold_fresh()
        assert isinstance(result.data, dict)

    def test_timestamp_present(self) -> None:
        result, _ = _scaffold_fresh()
        assert result.timestamp is not None


# --------------------------------------------------------------
# No leakage - no platform internals in output
# --------------------------------------------------------------

class TestNoLeakage:
    """Scaffold must not reference platform internals or private surfaces."""

    FORBIDDEN_STRINGS = [
        "keyhole_platform",
        "governance_engine",
        "promotion_kernel",
        "nats://",
        "qdrant",
        "keyhole-system",
    ]

    def test_no_forbidden_strings_in_data(self) -> None:
        result, base = _scaffold_fresh()
        data_str = str(result.data)
        for forbidden in self.FORBIDDEN_STRINGS:
            assert forbidden not in data_str, f"Leaked: {forbidden}"

    def test_no_forbidden_strings_in_files(self) -> None:
        _, base = _scaffold_fresh()
        for f in MANAGED_FILES:
            fpath = base / f
            if fpath.exists():
                content = fpath.read_text()
                for forbidden in self.FORBIDDEN_STRINGS:
                    assert forbidden not in content, f"Leaked {forbidden} in {f}"
