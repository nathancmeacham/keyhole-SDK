from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "packages" / "python" / "keyhole-sdk"
APP_ROOT = REPO_ROOT / "my-first-app"
TEST_DIR = Path(__file__).resolve().parent

for path in (SDK_ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from keyhole_sdk.governed_demo import GovernedDemoError, GovernedFirstAppClient
import keyhole_sdk.governed_demo as governed_demo
from s51_c02_fakes import FakeBoundarySession, FakeResponse


def test_sdk_discovers_capabilities_and_required_operations() -> None:
    session = FakeBoundarySession()
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    operations = client.discover()

    assert "repo.register" in operations
    assert "context.compile" in operations
    assert "governed.realize" in operations


def test_sdk_unwraps_live_envelope_and_resolves_logical_operations() -> None:
    session = FakeBoundarySession(capability_shape="live_envelope")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    operations = client.discover()

    assert client.capabilities == client.raw_capabilities["data"]
    assert operations["repo.register"].path == "/mcp/v1/runs/start"
    assert operations["repo.register"].run_type == "governance.context.create"
    assert operations["context.compile"].run_type == "context.compile"
    assert operations["governed.realize"].run_type == "governed.realize"
    assert operations["gaps.claim"].run_type == "gaps.claim"


def test_sdk_resolves_operations_run_types_shape() -> None:
    session = FakeBoundarySession(capability_shape="run_types")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    operations = client.discover()

    assert operations["repo.register"].path == "/mcp/v1/runs/start"
    assert operations["repo.register"].run_type == "governance.context.create"


def test_sdk_repo_registration_calls_boundary_and_stores_identity(tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    session = FakeBoundarySession()
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    result = client.register_repo(app)

    assert result["registration_id"] == "reg_fake_123"
    assert (app / ".keyhole" / "governed-demo" / "registration.json").exists()
    assert any(call["url"].endswith("/mcp/v1/repos/register") for call in session.calls)


def test_sdk_live_repo_registration_uses_typed_run(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = FakeBoundarySession(capability_shape="live_envelope")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    result = client.register_repo(app)

    run_calls = [call for call in session.calls if call["url"].endswith("/mcp/v1/runs/start")]
    status_probe_call = run_calls[0]
    preclaim_context_call = run_calls[1]
    discovery_call = run_calls[2]
    claim_call = run_calls[3]
    register_call = run_calls[4]
    assert result["registration_id"] == "reg_fake_123"
    assert status_probe_call["json"]["run_type"] == "gaps.status"
    assert "X-Idempotency-Key" not in status_probe_call["headers"]
    assert preclaim_context_call["json"]["run_type"] == "context.compile"
    assert "X-Idempotency-Key" in preclaim_context_call["headers"]
    assert discovery_call["json"]["run_type"] == "gaps.list"
    assert "X-Idempotency-Key" not in discovery_call["headers"]
    assert claim_call["json"]["run_type"] == "gaps.claim"
    assert "X-Idempotency-Key" in claim_call["headers"]
    assert claim_call["json"]["params"]["gap_id"] == "gap_fake_c02_123"
    assert claim_call["json"]["params"]["story_id"] == "CE-V5-S51-C02"
    assert "ctxpack_digest" in claim_call["json"]
    assert register_call["json"]["run_type"] == "governance.context.create"
    assert "X-Idempotency-Key" in register_call["headers"]
    assert register_call["json"]["ctxpack_digest"] == claim_call["json"]["ctxpack_digest"]
    assert register_call["json"]["context_ref"] == claim_call["json"]["ctxpack_digest"]
    assert register_call["json"]["params"]["ctxpack_digest"] == claim_call["json"]["ctxpack_digest"]
    assert register_call["json"]["params"]["gap_id"] == "gap_fake_c02_123"
    assert register_call["json"]["params"]["story_id"] == "CE-V5-S51-C02"
    assert register_call["json"]["params"]["claim_id"] == "claim_fake_123"
    assert register_call["json"]["params"]["claim_ref"] == "claim_ref_fake_123"
    assert register_call["json"]["params"]["repo_remote"] == "https://example.test/keyhole-SDK.git"
    assert register_call["json"]["params"]["commit_sha"] == "abc123def456"
    assert register_call["json"]["params"]["branch"] == "main"
    assert register_call["json"]["params"]["declared_repo_class"] == "SDK_TEMPLATE"
    assert register_call["json"]["params"]["declaration_files"]["keyhole_yaml_digest"].startswith("sha256:")


def test_sdk_http_error_preserves_nested_detail_without_tokens() -> None:
    response = FakeResponse(422, {
        "detail": {
            "code": "STATUS_NOT_CLAIMABLE",
            "message": "Gap status does not permit claiming.",
            "required_action": {"type": "materialize_or_reopen_gap"},
            "claim_token": "secret-token-value",
        }
    })

    with pytest.raises(GovernedDemoError) as exc_info:
        governed_demo._raise_for_response(response, "gap claim")

    message = str(exc_info.value)
    assert "STATUS_NOT_CLAIMABLE" in message
    assert "materialize_or_reopen_gap" in message
    assert "secret-token-value" not in message
    assert "<redacted>" in message


def test_sdk_async_repo_registration_polls_terminal_result(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = FakeBoundarySession(capability_shape="async_accept")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    result = client.register_repo(app)

    assert result["registration_id"] == "reg_fake_123"
    assert any("/mcp/v1/runs/run_fake_async_123" in call["url"] for call in session.calls)


def test_sdk_polls_async_claim_and_passes_claim_ref(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = FakeBoundarySession(capability_shape="async_claim")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    result = client.register_repo(app)

    assert result["claim_id"] == "claim_fake_123"
    poll_calls = [call for call in session.calls if "/mcp/v1/runs/run_fake_claim_123" in call["url"]]
    assert poll_calls
    register_call = [
        call for call in session.calls
        if call["url"].endswith("/mcp/v1/runs/start")
        and call["json"]["run_type"] == "governance.context.create"
    ][0]
    assert register_call["json"]["params"]["claim_ref"] == "claim_ref_fake_123"


def test_gap_id_diagnostic_override_is_used(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.setenv("KEYHOLE_C02_GAP_ID", "gap_override_123")
    session = FakeBoundarySession(capability_shape="live_envelope")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    client.register_repo(app)

    claim_call = [
        call for call in session.calls
        if call["url"].endswith("/mcp/v1/runs/start")
        and call["json"]["run_type"] == "gaps.claim"
    ][0]
    assert claim_call["json"]["params"]["gap_id"] == "gap_override_123"
    assert client.gap_id_source == "diagnostic override KEYHOLE_C02_GAP_ID"


def test_invalid_gap_id_diagnostic_override_fails_closed(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    monkeypatch.setenv("KEYHOLE_C02_GAP_ID", "CE-V5-S51-C02")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(capability_shape="live_envelope"),
    )

    with pytest.raises(GovernedDemoError, match="canonical gap_"):
        client.register_repo(app)


def test_sdk_live_repo_registration_requires_git_metadata(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    monkeypatch.setattr(governed_demo, "_git_value", lambda _repo, *args: "")
    session = FakeBoundarySession(capability_shape="live_envelope")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )

    with pytest.raises(GovernedDemoError, match="repo_remote, commit_sha"):
        client.register_repo(app)


def test_missing_claim_operation_fails_when_required() -> None:
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(capability_shape="live_envelope", missing_operation="gaps.claim"),
    )

    with pytest.raises(GovernedDemoError, match="gaps.claim"):
        client.discover()


def test_missing_gap_discovery_fails_closed(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(capability_shape="no_gap_discovery"),
    )

    with pytest.raises(GovernedDemoError, match="gap discovery"):
        client.register_repo(app)


def test_claim_rejection_fails_closed(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(capability_shape="claim_reject"),
    )

    with pytest.raises(GovernedDemoError, match="CLAIM_REJECTED"):
        client.register_repo(app)


def test_sdk_context_compile_returns_governance_context_id(tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    session = FakeBoundarySession()
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )
    client.register_repo(app)

    result = client.compile_context(app)

    assert result["governance_context_id"] == "gctx_fake_123"
    assert result["ctxpack_digest"] == "c" * 64
    assert (app / ".keyhole" / "governed-demo" / "context.json").exists()
    assert any(call["url"].endswith("/mcp/v1/runs/start") for call in session.calls)
    compile_call = [call for call in session.calls if call["url"].endswith("/mcp/v1/runs/start")][-1]
    assert compile_call["json"]["run_type"] == "context.compile"


def test_sdk_governed_realization_sends_require_governed_and_returns_receipt(tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    session = FakeBoundarySession()
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )
    client.register_repo(app)
    client.compile_context(app)

    receipt = client.run_governed_realization(app)

    realize_call = [call for call in session.calls if call["url"].endswith("/realize")][0]
    assert realize_call["json"]["require_governed"] is True
    assert realize_call["json"]["local_invariant_result"]["verdict"] == "ACCEPT"
    assert receipt.governed is True
    assert receipt.event_spine_evidence is True
    assert receipt.governance_verdict == "ACCEPT"
    assert receipt.drift_state == "clean"


def test_sdk_live_governed_realization_uses_typed_run(monkeypatch, tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    _patch_git_metadata(monkeypatch)
    session = FakeBoundarySession(capability_shape="live_envelope")
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )
    client.register_repo(app)
    client.compile_context(app)

    receipt = client.run_governed_realization(app)

    realize_call = [call for call in session.calls if call["url"].endswith("/mcp/v1/runs/start")][-1]
    assert realize_call["json"]["run_type"] == "governed.realize"
    assert realize_call["json"]["params"]["require_governed"] is True
    assert realize_call["json"]["params"]["local_invariant_result"]["verdict"] == "ACCEPT"
    assert receipt.mcp_event_id == "evt_fake_123"


def test_missing_required_mcp_operation_fails_closed() -> None:
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(missing_operation="context.compile"),
    )

    with pytest.raises(GovernedDemoError, match="context.compile"):
        client.discover()


def test_missing_governed_realization_operation_fails_closed() -> None:
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=FakeBoundarySession(missing_operation="governed.realize"),
    )

    with pytest.raises(GovernedDemoError, match="governed.realize"):
        client.discover()


def test_missing_event_spine_evidence_fails_closed(tmp_path) -> None:
    app = _copy_first_app(tmp_path)
    session = FakeBoundarySession()
    client = GovernedFirstAppClient(
        mcp_url="https://mcp.fake",
        token="secret-token",
        runtime_url="http://runtime.fake",
        session=session,
    )
    client.register_repo(app)
    client.compile_context(app)

    original_post = session.post

    def post_without_evidence(url: str, **kwargs):
        response = original_post(url, **kwargs)
        data = response.json()
        data["event_spine_evidence"] = False
        data.pop("mcp_event_id", None)
        return type(response)(response.status_code, data)

    session.post = post_without_evidence

    with pytest.raises(GovernedDemoError, match="event_spine_evidence"):
        client.run_governed_realization(app)


def test_missing_token_fails_closed() -> None:
    with pytest.raises(GovernedDemoError, match="KEYHOLE_MCP_TOKEN"):
        GovernedFirstAppClient(mcp_url="https://mcp.fake", token="")


def _copy_first_app(tmp_path: Path) -> Path:
    target = tmp_path / "my-first-app"
    import shutil

    shutil.copytree(APP_ROOT, target, ignore=shutil.ignore_patterns(".keyhole", "proof_bundle"))
    return target


def _patch_git_metadata(monkeypatch) -> None:
    values = {
        ("remote", "get-url", "origin"): "https://example.test/keyhole-SDK.git",
        ("rev-parse", "HEAD"): "abc123def456",
        ("branch", "--show-current"): "main",
    }
    monkeypatch.setattr(governed_demo, "_git_value", lambda _repo, *args: values.get(tuple(args), ""))
