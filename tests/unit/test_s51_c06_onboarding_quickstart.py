from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from typer.testing import CliRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk"
CLI_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-cli"
TEST_DIR = Path(__file__).resolve().parent
SECOND_APP_ROOT = REPO_ROOT / "examples" / "second-governed-app"

for path in (SDK_ROOT, CLI_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import keyhole_sdk.governed_demo as governed_demo
import keyhole_sdk.governed_flow as governed_flow
from keyhole_cli.cli import app
import keyhole_cli.commands.governed_flow_cmd as governed_flow_cmd
from s51_c02_fakes import FakeBoundarySession


runner = CliRunner()


def test_quickstart_commands_are_documented() -> None:
    quickstart = (REPO_ROOT / "docs" / "guides" / "governed-sdk-quickstart.md").read_text(encoding="utf-8")

    assert "keyhole login --flow device --force" in quickstart
    assert "keyhole governed run --repo-dir examples\\second-governed-app --json" in quickstart
    assert "keyhole governed status --repo-dir examples\\second-governed-app --last --json" in quickstart
    assert "keyhole governed receipt --repo-dir examples\\second-governed-app --last --json" in quickstart


def test_governed_help_exposes_run_status_resume_receipt() -> None:
    result = runner.invoke(app, ["governed", "--help"])

    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "status" in result.stdout
    assert "resume" in result.stdout
    assert "receipt" in result.stdout


def test_governed_run_dry_run_explain_json_does_not_mutate_fake_mcp(monkeypatch, tmp_path) -> None:
    app_dir = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()
    monkeypatch.setattr(governed_flow_cmd, "_client", lambda **kwargs: governed_flow.GovernedRepoFlowClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    ))

    result = governed_flow_cmd.run_governed_flow(
        repo_dir=str(app_dir),
        dry_run=True,
        explain=True,
        mcp_url="https://mcp.fake",
    )
    payload = result.to_dict()

    assert result.success is True
    assert payload["would_mutate_mcp"] is False
    assert not any(call.get("json", {}).get("run_type") == "gaps.claim" for call in session.calls)
    assert not any(call.get("json", {}).get("run_type") == "governance.context.create" for call in session.calls)


def test_dry_run_output_includes_repo_identity_and_operation_plan(monkeypatch, tmp_path) -> None:
    app_dir = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()
    monkeypatch.setattr(governed_flow_cmd, "_client", lambda **kwargs: governed_flow.GovernedRepoFlowClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    ))

    payload = governed_flow_cmd.run_governed_flow(
        repo_dir=str(app_dir),
        dry_run=True,
        explain=True,
        mcp_url="https://mcp.fake",
    ).to_dict()

    assert payload["explain"]["repo_identity"]["repo_remote"] == "https://example.test/second-governed-app.git"
    assert payload["explain"]["candidate_gap_filters"]["capability_id"] == "second-governed-app.echo.user.v1"
    assert "runs.start:gaps.claim" in payload["explain"]["operations_would_call"]
    local_state_path = Path(payload["explain"]["local_state_path"])
    assert local_state_path.parts[-2:] == (".keyhole", "governed-runs")


def test_dry_run_redacts_credentials(monkeypatch, tmp_path) -> None:
    app_dir = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.setenv("KEYHOLE_MCP_TOKEN", "secret-token")
    session = _second_session()
    monkeypatch.setattr(governed_flow_cmd, "_client", lambda **kwargs: governed_flow.GovernedRepoFlowClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    ))

    payload = governed_flow_cmd.run_governed_flow(
        repo_dir=str(app_dir),
        dry_run=True,
        explain=True,
        mcp_url="https://mcp.fake",
    ).to_dict()

    assert "secret-token" not in json.dumps(payload)


def test_troubleshooting_guide_includes_known_failure_classes() -> None:
    troubleshooting = (REPO_ROOT / "docs" / "guides" / "governed-sdk-troubleshooting.md").read_text(encoding="utf-8")

    assert "GAP_NOT_FOUND" in troubleshooting
    assert "CLAIM_NOT_FOUND" in troubleshooting
    assert "RUN_NOT_FOUND" in troubleshooting
    assert "MULTIPLE_GAP_CANDIDATES" in troubleshooting


def test_quickstart_does_not_instruct_diagnostic_overrides() -> None:
    quickstart = (REPO_ROOT / "docs" / "guides" / "governed-sdk-quickstart.md").read_text(encoding="utf-8")

    assert "KEYHOLE_C02_GAP_ID" not in quickstart
    assert "KEYHOLE_GOVERNED_GAP_ID" not in quickstart


def test_quickstart_does_not_tell_users_to_commit_keyhole_artifacts() -> None:
    quickstart = (REPO_ROOT / "docs" / "guides" / "governed-sdk-quickstart.md").read_text(encoding="utf-8")

    assert ".keyhole/governed-runs/" in quickstart
    assert "should not normally be committed" in quickstart


def test_receipt_docs_list_required_governance_fields() -> None:
    quickstart = (REPO_ROOT / "docs" / "guides" / "governed-sdk-quickstart.md").read_text(encoding="utf-8")

    assert "governed=true" in quickstart
    assert "event_spine_evidence=true" in quickstart
    assert "mcp_event_id / mcp_event_pointer" in quickstart
    assert "receipt_id" in quickstart
    assert "proof_id" in quickstart


def _copy_second_app(tmp_path: Path) -> Path:
    target = tmp_path / "second-governed-app"
    shutil.copytree(SECOND_APP_ROOT, target, ignore=shutil.ignore_patterns(".keyhole", "proof_bundle"))
    return target


def _patch_git_metadata(monkeypatch) -> None:
    values = {
        ("remote", "get-url", "origin"): "https://example.test/second-governed-app.git",
        ("rev-parse", "HEAD"): "def456abc123",
        ("branch", "--show-current"): "feature/c06",
    }
    monkeypatch.setattr(governed_demo, "_git_value", lambda _repo, *args: values.get(tuple(args), ""))
    monkeypatch.setattr(governed_flow, "_repo_git_metadata", lambda repo: {
        "repo_remote": values[("remote", "get-url", "origin")],
        "commit_sha": values[("rev-parse", "HEAD")],
        "branch": values[("branch", "--show-current")],
    })


def _second_session() -> FakeBoundarySession:
    return FakeBoundarySession(
        capability_shape="storyless_gap",
        gap_id="gap_fake_c03_456",
        story_id="CE-V5-S51-C03",
        repo_name="second-governed-app",
        capability_id="second-governed-app.echo.user.v1",
    )
