from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from keyhole_sdk import gap_closure
from keyhole_sdk.gap_closure import (
    GapClosureClient,
    GapClosureError,
    assert_closure_response_governed,
    assert_event_spine_safe,
    assert_gap_open_for_closure,
    build_gap_closure_payload,
)


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict:
        return self._body


class FakeSession:
    def __init__(self, *, health: dict, gap: dict, closure: dict):
        self.health = health
        self.gap = gap
        self.closure = closure
        self.posts = []

    def get(self, url, headers=None, timeout=None):
        return FakeResponse(200, self.health)

    def post(self, url, headers=None, json=None, timeout=None):
        self.posts.append(json)
        if json["run_type"] == "gaps.get":
            return FakeResponse(200, self.gap)
        return FakeResponse(200, self.closure)


def test_build_gap_closure_payload_includes_required_identity(monkeypatch, tmp_path: Path):
    declaration = SimpleNamespace(
        repo_name="second-governed-app",
        capability_id="second-governed-app.echo.user.v1",
    )
    identity = SimpleNamespace(
        repo_remote="https://github.com/Keyhole-Solution/keyhole-SDK.git",
        owner="Keyhole-Solution",
        repo="keyhole-SDK",
        current_branch="main",
        commit_sha="abc123",
    )
    monkeypatch.setattr(gap_closure, "read_repo_declaration", lambda repo: declaration)
    monkeypatch.setattr(gap_closure, "detect_repo_identity", lambda repo: identity)
    monkeypatch.setattr(gap_closure, "_installed_version", lambda name: "0.4.1")

    payload = build_gap_closure_payload(
        repo_dir=tmp_path,
        gap_id="gap_8488f30fb4e1ef82",
        closure_reason="remediated",
        closure_classification="locally_remediated_not_closed",
        evidence_bundle_hash="sha256-test",
        workspace_id="workspace-1",
        requested_by="builder@example.test",
    ).to_dict()

    assert payload["gap_id"] == "gap_8488f30fb4e1ef82"
    assert payload["created_via"] == "sdk.gaps.submit"
    assert payload["domain"] == "second-governed-app"
    assert payload["capability_id"] == "second-governed-app.echo.user.v1"
    assert payload["repo_url"] == "https://github.com/Keyhole-Solution/keyhole-SDK.git"
    assert payload["repo_owner"] == "Keyhole-Solution"
    assert payload["repo_name"] == "keyhole-SDK"
    assert payload["branch"] == "main"
    assert payload["commit_sha"] == "abc123"
    assert payload["evidence_bundle_hash"] == "sha256-test"
    assert payload["closure_classification"] == "locally_remediated_not_closed"
    assert payload["requested_ts"]


def test_event_spine_fail_refuses_closure():
    with pytest.raises(GapClosureError, match="event spine health"):
        assert_event_spine_safe({"final_classification": "FAIL"})


def test_event_spine_requires_unpersisted_zero():
    with pytest.raises(GapClosureError, match="unpersisted_message_count"):
        assert_event_spine_safe(
            {
                "final_classification": "PASS_WITH_LEGACY_WARNINGS",
                "streams": {"KH_VERDICTS": {"max_msgs": 1_000_000}},
                "unpersisted_message_count": 2,
            }
        )


def test_target_gap_must_be_open_and_unclosed():
    with pytest.raises(GapClosureError, match="not OPEN"):
        assert_gap_open_for_closure({"data": {"gap_id": "gap_1", "status": "CLOSED"}}, "gap_1")

    with pytest.raises(GapClosureError, match="close_verdict_ref"):
        assert_gap_open_for_closure(
            {"data": {"gap_id": "gap_1", "status": "OPEN", "closed_ts": None, "close_verdict_ref": "KH:1"}},
            "gap_1",
        )


def test_closure_response_requires_lineage_fields():
    with pytest.raises(GapClosureError, match="close_verdict_ref"):
        assert_closure_response_governed(
            {
                "data": {
                    "gap_id": "gap_1",
                    "closed_ts": "2026-06-23T10:00:00Z",
                    "convergence_closure_lineage": {"verdict": "KH:2"},
                    "gap_closure_history": [{"closure_id": "closure-1"}],
                }
            }
        )


def test_client_submits_gaps_close_after_safe_preflight(monkeypatch, tmp_path: Path):
    declaration = SimpleNamespace(
        repo_name="second-governed-app",
        capability_id="second-governed-app.echo.user.v1",
    )
    identity = SimpleNamespace(
        repo_remote="https://github.com/Keyhole-Solution/keyhole-SDK.git",
        owner="Keyhole-Solution",
        repo="keyhole-SDK",
        current_branch="main",
        commit_sha="abc123",
    )
    monkeypatch.setattr(gap_closure, "read_repo_declaration", lambda repo: declaration)
    monkeypatch.setattr(gap_closure, "detect_repo_identity", lambda repo: identity)
    monkeypatch.setattr(gap_closure, "_installed_version", lambda name: "0.4.1")
    payload = build_gap_closure_payload(
        repo_dir=tmp_path,
        gap_id="gap_8488f30fb4e1ef82",
        closure_reason="remediated",
        closure_classification="locally_remediated_not_closed",
        evidence_bundle_hash="hash",
    )
    session = FakeSession(
        health={
            "final_classification": "PASS_WITH_LEGACY_WARNINGS",
            "unpersisted_message_count": 0,
            "streams": {"KH_VERDICTS": {"max_msgs": 1_000_000}},
        },
        gap={"data": {"gap_id": payload.gap_id, "status": "OPEN", "closed_ts": None, "close_verdict_ref": None}},
        closure={
            "data": {
                "gap_id": payload.gap_id,
                "closed_ts": "2026-06-23T10:00:00Z",
                "close_verdict_ref": "KH_VERDICTS:19170000",
                "convergence_closure_lineage": {"verdict": "KH_VERDICTS:19170000"},
                "gap_closure_history": [{"closure_id": "closure-1"}],
            }
        },
    )

    client = GapClosureClient(mcp_url="https://mcp.keyholesolution.com", token="token", session=session)
    client.preflight(gap_id=payload.gap_id)
    response = client.submit_closure(payload)

    assert response["data"]["close_verdict_ref"] == "KH_VERDICTS:19170000"
    assert session.posts[-1]["run_type"] == "gaps.close"
    assert session.posts[-1]["params"]["closure"]["evidence_bundle_hash"] == "hash"
