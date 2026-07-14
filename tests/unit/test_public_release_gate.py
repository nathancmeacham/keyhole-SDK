from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_public_release_gate_script_covers_required_lanes() -> None:
    content = (REPO_ROOT / "scripts" / "public-release-gate.ps1").read_text()

    assert "tests/unit" in content
    assert "packages/python/keyhole-sdk" in content
    assert "packages/python/keyhole-cli" in content
    assert "setuptools" in content
    assert "services/test-runtime/requirements.txt" in content
    assert "examples/second-governed-app" in content
    assert "my-first-app" in content
    assert "Assert-NoForbiddenPublicText" in content
    assert "Assert-GeneratedStatePolicy" in content
    assert "ls-files" in content
    assert "Generated governance artifacts are tracked by Git" in content
    assert "keyhole_cli.cli" in content
    assert "IncludeLiveProof" in content
    assert "RunGoverned" in content


def test_public_release_gate_workflow_runs_on_windows_and_linux() -> None:
    content = (REPO_ROOT / ".github" / "workflows" / "public-release-gate.yml").read_text()

    assert "ubuntu-latest" in content
    assert "windows-latest" in content
    assert "scripts/public-release-gate.ps1" in content
    assert "actions/setup-python" in content
    assert "Install ripgrep on Ubuntu" in content
    assert "Install ripgrep on Windows" in content
    assert "choco install ripgrep" in content


def test_product_posture_docs_do_not_claim_complete_product() -> None:
    launch_readiness = (REPO_ROOT / "docs" / "launch-readiness.md").read_text()
    trust_posture = (REPO_ROOT / "docs" / "trust-posture.md").read_text()

    combined = f"{launch_readiness}\n{trust_posture}".lower()
    assert "technical preview" in combined
    assert "early access" in combined
    assert "complete product marketing gate" in combined
    assert "optional surface degradation is not core-governance failure" in combined
