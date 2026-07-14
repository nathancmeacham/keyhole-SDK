from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


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
import keyhole_cli.commands.governed_flow_cmd as governed_flow_cmd
import keyhole_cli.commands.launch_doctor as launch_doctor
from keyhole_cli.commands.governed_flow_cmd import run_governed_flow
from keyhole_cli.result import CommandResult, EXIT_SUCCESS
from keyhole_sdk.governed_demo import GovernedDemoError
from keyhole_sdk.governed_flow import GovernedRepoFlowClient, GovernedRunStateStore, read_repo_declaration
from s51_c02_fakes import FakeBoundarySession


def test_generic_flow_reads_repo_declarations_and_digests(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)

    declaration = read_repo_declaration(app)

    assert declaration.repo_name == "second-governed-app"
    assert declaration.story_id == "CE-V5-S51-C03"
    assert declaration.capability_id == "second-governed-app.echo.user.v1"
    assert declaration.declaration_file_digests["keyhole_yaml_digest"].startswith("sha256:")
    deps = declaration.native_artifacts["dependencies"]["dependencies"]
    assert deps[0]["capability"] == "keyhole.mcp.governance-boundary.v1"


def test_generic_flow_resolves_non_c02_canonical_gap(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()
    client = _client(session)

    result = client.run_governed_repo_flow(app)

    assert result["resolved_gap_id"] == "gap_fake_c03_456"
    assert result["repo"]["story_id"] == "CE-V5-S51-C03"
    assert result["repo"]["capability_id"] == "second-governed-app.echo.user.v1"
    assert result["receipt"]["governed"] is True


def test_generic_flow_honors_explicit_gap_id_in_live_path(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()
    client = GovernedRepoFlowClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
        gap_id="gap_operator_123",
    )

    result = client.run_governed_repo_flow(app)

    assert result["resolved_gap_id"] == "gap_operator_123"
    claim_call = [call for call in session.calls if call.get("json", {}).get("run_type") == "gaps.claim"][0]
    assert claim_call["json"]["params"]["gap_id"] == "gap_operator_123"


def test_generic_flow_claims_gap_before_context_create(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()

    _client(session).run_governed_repo_flow(app)

    run_types = [
        call["json"]["run_type"]
        for call in session.calls
        if call["method"] == "POST" and call["url"].endswith("/mcp/v1/runs/start")
    ]
    assert run_types.index("gaps.claim") < run_types.index("governance.context.create")
    context_call = [
        call for call in session.calls
        if call.get("json", {}).get("run_type") == "governance.context.create"
    ][0]
    assert context_call["json"]["params"]["gap_id"] == "gap_fake_c03_456"
    assert context_call["json"]["params"]["claim_id"] == "claim_fake_123"
    assert context_call["json"]["params"]["claim_ref"] == "claim_ref_fake_123"
    assert context_call["json"]["params"]["story_id"] == "CE-V5-S51-C03"


def test_generic_flow_does_not_use_story_label_as_gap_id(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()

    _client(session).run_governed_repo_flow(app)

    claim_call = [call for call in session.calls if call.get("json", {}).get("run_type") == "gaps.claim"][0]
    assert claim_call["json"]["params"]["story_id"] == "CE-V5-S51-C03"
    assert claim_call["json"]["params"]["gap_id"] == "gap_fake_c03_456"
    assert claim_call["json"]["params"]["gap_id"] != "CE-V5-S51-C03"


def test_generic_flow_falls_back_when_materialized_gap_has_no_story_id(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session(capability_shape="storyless_gap")

    result = _client(session).run_governed_repo_flow(app)

    discovery_calls = [
        call for call in session.calls
        if call.get("json", {}).get("run_type") == "gaps.list"
    ]
    assert len(discovery_calls) == 2
    assert discovery_calls[0]["json"]["params"]["story_id"] == "CE-V5-S51-C03"
    assert "story_id" not in discovery_calls[1]["json"]["params"]
    assert result["resolved_gap_id"] == "gap_fake_c03_456"


def test_generic_flow_falls_back_when_story_filtered_gap_query_errors(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session(capability_shape="story_filter_error")

    result = _client(session).run_governed_repo_flow(app)

    discovery_calls = [
        call for call in session.calls
        if call.get("json", {}).get("run_type") == "gaps.list"
    ]
    assert len(discovery_calls) >= 2
    assert discovery_calls[0]["json"]["params"]["story_id"] == "CE-V5-S51-C03"
    assert "story_id" not in discovery_calls[1]["json"]["params"]
    assert result["resolved_gap_id"] == "gap_fake_c03_456"


def test_multiple_gap_candidates_fail_closed(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session(capability_shape="multiple_gaps")

    with pytest.raises(GovernedDemoError, match="MULTIPLE_GAP_CANDIDATES"):
        _client(session).run_governed_repo_flow(app)


def test_stale_gap_fails_before_claim(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session(capability_shape="stale_gap")

    with pytest.raises(GovernedDemoError, match="NO_CLAIMABLE_GAP"):
        _client(session).run_governed_repo_flow(app)

    assert not any(call.get("json", {}).get("run_type") == "gaps.claim" for call in session.calls)
    assert _latest_state(app)["status"] == "no_claimable_gap"


def test_launch_doctor_reports_stale_gap_not_claimable(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.setattr(
        launch_doctor,
        "run_whoami",
        lambda mcp_base_url: CommandResult(
            command="keyhole whoami",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="OK",
            data={"mode": "real", "actor_envelope_present": True},
        ),
    )
    monkeypatch.setattr(
        launch_doctor,
        "_client",
        lambda **kwargs: _client(_second_session(capability_shape="stale_gap")),
    )

    result = launch_doctor.run_launch_doctor(repo_dir=str(app), mcp_url="https://mcp.fake")
    claimable = next(check for check in result.data["checks"] if check["name"] == "claimable_gap_availability")

    assert result.success is False
    assert claimable["ok"] is False
    assert "NO_CLAIMABLE_GAP" in claimable["summary"]


def test_generic_dry_run_resolves_without_claim_or_context_mutation(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = _second_session()

    result = _client(session).run_governed_repo_flow(app, dry_run=True)

    assert result["dry_run"] is True
    assert result["resolved_gap_id"] == "gap_fake_c03_456"
    assert not any(call.get("json", {}).get("run_type") == "gaps.claim" for call in session.calls)
    assert not any(call.get("json", {}).get("run_type") == "governance.context.create" for call in session.calls)


def test_cli_no_live_validates_local_declarations_without_token(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.delenv("KEYHOLE_MCP_TOKEN", raising=False)

    result = run_governed_flow(repo_dir=str(app), no_live=True, explain=True)

    assert result.success is True
    data = result.to_dict()
    assert data["no_live"] is True
    assert data["would_mutate_mcp"] is False
    assert "token" not in json.dumps(result.to_dict()).lower()


def test_cli_json_data_redacts_and_returns_proof_fields(monkeypatch, tmp_path) -> None:
    app = _copy_second_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.setenv("KEYHOLE_MCP_TOKEN", "secret-token")
    session = _second_session()

    monkeypatch.setattr(governed_flow_cmd, "GovernedRepoFlowClient", lambda **kwargs: _client(session))
    result = run_governed_flow(repo_dir=str(app), story_id="CE-V5-S51-C03", capability_id="second-governed-app.echo.user.v1")

    payload = result.to_dict()
    assert result.success is True
    assert payload["receipt"]["receipt_id"] == "receipt_fake_123"
    assert payload["receipt"]["proof_id"] == "proof_fake_123"
    assert "secret-token" not in json.dumps(payload)


def _copy_second_app(tmp_path: Path) -> Path:
    target = tmp_path / "not-my-first-app"
    shutil.copytree(SECOND_APP_ROOT, target, ignore=shutil.ignore_patterns(".keyhole", "proof_bundle"))
    return target


def _patch_git_metadata(monkeypatch) -> None:
    values = {
        ("remote", "get-url", "origin"): "https://example.test/second-governed-app.git",
        ("rev-parse", "HEAD"): "def456abc123",
        ("branch", "--show-current"): "feature/c03",
    }
    monkeypatch.setattr(governed_demo, "_git_value", lambda _repo, *args: values.get(tuple(args), ""))
    monkeypatch.setattr(governed_flow, "_repo_git_metadata", lambda repo: {
        "repo_remote": values[("remote", "get-url", "origin")],
        "commit_sha": values[("rev-parse", "HEAD")],
        "branch": values[("branch", "--show-current")],
    })


def _second_session(capability_shape: str = "live_envelope") -> FakeBoundarySession:
    return FakeBoundarySession(
        capability_shape=capability_shape,
        gap_id="gap_fake_c03_456",
        story_id="CE-V5-S51-C03",
        repo_name="second-governed-app",
        capability_id="second-governed-app.echo.user.v1",
    )


def _client(session: FakeBoundarySession) -> GovernedRepoFlowClient:
    return GovernedRepoFlowClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )


def _latest_state(app: Path) -> dict:
    return GovernedRunStateStore(app).load_latest()
