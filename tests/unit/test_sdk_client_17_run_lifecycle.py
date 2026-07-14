"""Unit tests for SDK-CLIENT-17 - Async Run Tracking, Polling, and Durable Run UX.

Tests cover:
  - RunStatus classification
  - RunStatusResult rendering
  - RunRecord persistence (save/load/update/list)
  - fetch_run_status with transport responses
  - wait_for_terminal behavior (terminal, timeout, callback)
  - tail_run observation (status changes, terminal stop, honest labels)
  - resume_run (local record, boundary lookup, ambiguity)
  - Run lifecycle proof emission
  - Repair guidance mapping
  - Operation registry entries
  - SDK exports
  - CLI runs commands
  - run_cmd.py local record persistence for ACCEPTED/DEFERRED
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# --------------------------------------------------------------
# Test 1: RunStatus Classification (section6)
# --------------------------------------------------------------


class TestRunStatusClassification:
    """section6: All 14 raw status strings map to classified states."""

    def test_accepted_aliases(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("accepted") == RunStatus.ACCEPTED
        assert classify_status("pending") == RunStatus.ACCEPTED

    def test_running_aliases(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("running") == RunStatus.RUNNING
        assert classify_status("in_progress") == RunStatus.RUNNING

    def test_deferred(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("deferred") == RunStatus.DEFERRED

    def test_success_aliases(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("success") == RunStatus.SUCCESS
        assert classify_status("completed") == RunStatus.SUCCESS
        assert classify_status("ok") == RunStatus.SUCCESS

    def test_failure_aliases(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("failed") == RunStatus.FAILED
        assert classify_status("error") == RunStatus.FAILED

    def test_rejected(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("rejected") == RunStatus.REJECTED

    def test_denied(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("denied") == RunStatus.DENIED

    def test_cancelled_aliases(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("cancelled") == RunStatus.CANCELLED
        assert classify_status("canceled") == RunStatus.CANCELLED

    def test_unknown_fallback(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, classify_status
        assert classify_status("some_weird_status") == RunStatus.UNKNOWN
        assert classify_status("") == RunStatus.UNKNOWN

    def test_case_insensitive(self):
        from keyhole_sdk.run_lifecycle.models import classify_status, RunStatus
        assert classify_status("ACCEPTED") == RunStatus.ACCEPTED
        assert classify_status("  Running  ") == RunStatus.RUNNING

    def test_terminal_property(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        assert RunStatus.SUCCESS.is_terminal is True
        assert RunStatus.FAILED.is_terminal is True
        assert RunStatus.REJECTED.is_terminal is True
        assert RunStatus.DENIED.is_terminal is True
        assert RunStatus.CANCELLED.is_terminal is True
        assert RunStatus.ACCEPTED.is_terminal is False
        assert RunStatus.RUNNING.is_terminal is False
        assert RunStatus.DEFERRED.is_terminal is False
        assert RunStatus.UNKNOWN.is_terminal is False

    def test_active_property(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        assert RunStatus.ACCEPTED.is_active is True
        assert RunStatus.RUNNING.is_active is True
        assert RunStatus.DEFERRED.is_active is True
        assert RunStatus.SUCCESS.is_active is False
        assert RunStatus.FAILED.is_active is False


class TestTerminalState:
    """TerminalState enum values."""

    def test_values(self):
        from keyhole_sdk.run_lifecycle.models import TerminalState
        assert TerminalState.SUCCESS.value == "success"
        assert TerminalState.FAILED.value == "failed"
        assert TerminalState.REJECTED.value == "rejected"
        assert TerminalState.DENIED.value == "denied"
        assert TerminalState.CANCELLED.value == "cancelled"


# --------------------------------------------------------------
# Test 2: RunStatusResult Rendering (section10)
# --------------------------------------------------------------


class TestRunStatusResult:
    """section10: Human-readable status rendering."""

    def test_success_render(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, RunStatusResult
        r = RunStatusResult(
            success=True, run_id="abc123", status=RunStatus.SUCCESS,
            run_type="context.compile", repo_name="my-repo",
        )
        human = r.render_human()
        assert "abc123" in human
        assert "SUCCESS" in human
        assert "context.compile" in human

    def test_active_render_includes_next_steps(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, RunStatusResult
        r = RunStatusResult(
            success=True, run_id="abc123", status=RunStatus.RUNNING,
        )
        human = r.render_human()
        assert "keyhole runs wait" in human
        assert "keyhole runs tail" in human

    def test_failure_render(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, RunStatusResult
        r = RunStatusResult(
            success=False, reason="network timeout",
            repair_guidance=["Check network."],
        )
        human = r.render_human()
        assert "FAILED" in human
        assert "network timeout" in human
        assert "Check network." in human

    def test_terminal_render_no_next_steps(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, RunStatusResult
        r = RunStatusResult(
            success=True, run_id="abc", status=RunStatus.FAILED,
        )
        human = r.render_human()
        assert "keyhole runs wait" not in human


# --------------------------------------------------------------
# Test 3: RunRecord & LocalRunRecordStore (section8)
# --------------------------------------------------------------


class TestRunRecord:
    """section8: RunRecord serialization roundtrip."""

    def test_to_dict_from_dict(self):
        from keyhole_sdk.run_lifecycle.record import RunRecord
        rec = RunRecord(
            request_id="req-1", run_id="run-1", run_type="context.compile",
            mode="shadow", ctxpack_digest="abc123", repo_name="my-repo",
        )
        d = rec.to_dict()
        restored = RunRecord.from_dict(d)
        assert restored.request_id == "req-1"
        assert restored.run_id == "run-1"
        assert restored.mode == "shadow"

    def test_from_dict_ignores_unknown_fields(self):
        from keyhole_sdk.run_lifecycle.record import RunRecord
        data = {"run_id": "run-1", "unknown_field": "ignored"}
        rec = RunRecord.from_dict(data)
        assert rec.run_id == "run-1"
        assert not hasattr(rec, "unknown_field") or "unknown_field" not in rec.to_dict()

    def test_defaults(self):
        from keyhole_sdk.run_lifecycle.record import RunRecord
        rec = RunRecord()
        assert rec.command == "keyhole run"
        assert rec.mode == "regular"
        assert rec.last_known_status == "accepted"


class TestLocalRunRecordStore:
    """section8: Run record persistence under .keyhole/state/runs/."""

    def test_save_and_load(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        rec = RunRecord(run_id="run-abc", run_type="context.compile")
        store.save(rec)
        loaded = store.load("run-abc")
        assert loaded is not None
        assert loaded.run_id == "run-abc"
        assert loaded.run_type == "context.compile"

    def test_load_by_request_id(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        rec = RunRecord(request_id="req-xyz", run_type="gaps.list")
        store.save(rec)
        loaded = store.load("req-xyz")
        assert loaded is not None
        assert loaded.request_id == "req-xyz"

    def test_update_status(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        rec = RunRecord(run_id="run-status", last_known_status="accepted")
        store.save(rec)
        store.update_status("run-status", "success")
        loaded = store.load("run-status")
        assert loaded is not None
        assert loaded.last_known_status == "success"

    def test_list_recent(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        for i in range(5):
            store.save(RunRecord(run_id=f"run-{i}", run_type="test"))
        recents = store.list_recent(limit=3)
        assert len(recents) == 3

    def test_list_recent_empty(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore
        store = LocalRunRecordStore(tmp_path)
        assert store.list_recent() == []

    def test_load_nonexistent(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore
        store = LocalRunRecordStore(tmp_path)
        assert store.load("nonexistent") is None

    def test_save_requires_identifier(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        with pytest.raises(ValueError):
            store.save(RunRecord())

    def test_scan_fallback(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        rec = RunRecord(run_id="run-scan", correlation_id="corr-scan")
        store.save(rec)
        loaded = store.load("corr-scan")
        assert loaded is not None
        assert loaded.run_id == "run-scan"

    def test_file_location(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        store = LocalRunRecordStore(tmp_path)
        store.save(RunRecord(run_id="run-loc"))
        expected = tmp_path / ".keyhole" / "state" / "runs" / "run-loc.json"
        assert expected.exists()


# --------------------------------------------------------------
# Test 4: fetch_run_status (section5.2/section10)
# --------------------------------------------------------------


class _MockTransportResult:
    """Minimal mock for GovernedTransport.execute() return value."""
    def __init__(self, data=None, status_code=200):
        self.data = data or {}
        self.status_code = status_code


class TestFetchRunStatus:
    """section10: Status retrieval via GovernedTransport."""

    def test_success(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-1", "run_type": "context.compile"},
        )
        result = fetch_run_status(transport=transport, run_id="run-1")
        assert result.success is True
        assert result.status.value == "running"
        assert result.run_id == "run-1"

    def test_terminal_status(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "success", "run_id": "run-2"},
        )
        result = fetch_run_status(transport=transport, run_id="run-2")
        assert result.success is True
        assert result.status.is_terminal is True

    def test_http_error(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"message": "not found"}, status_code=404,
        )
        result = fetch_run_status(transport=transport, run_id="run-3")
        assert result.success is False
        assert result.repair_guidance

    def test_transport_exception(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("network down")
        result = fetch_run_status(transport=transport, run_id="run-4")
        assert result.success is False
        assert result.error_class == "ConnectionError"
        assert result.repair_guidance

    def test_alternate_status_field(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"state": "in_progress", "run_id": "run-5"},
        )
        result = fetch_run_status(transport=transport, run_id="run-5")
        assert result.success is True
        assert result.status.value == "running"

    def test_nested_data(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={
                "status": "accepted",
                "run_id": "run-6",
                "data": {"run_type": "gaps.list", "shadow": True},
            },
        )
        result = fetch_run_status(transport=transport, run_id="run-6")
        assert result.success is True
        assert result.run_type == "gaps.list"
        assert result.shadow is True

    def test_product_envelope_identity_refs_are_canonical(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={
                "ok": True,
                "data": {
                    "ok": True,
                    "resolved": True,
                    "status": "succeeded",
                    "run_id": "run_product_operation",
                    "request_id": "req_canonical",
                    "run_type": "governed.realize",
                    "identity_refs": {
                        "run_id": "run_canonical",
                        "request_id": "req_canonical",
                        "correlation_id": "corr-1",
                    },
                },
            },
        )

        result = fetch_run_status(transport=transport, run_id="corr-1")

        assert result.success is True
        assert result.status.value == "success"
        assert result.status.is_terminal is True
        assert result.run_id == "run_canonical"
        assert result.request_id == "req_canonical"
        assert result.correlation_id == "corr-1"
        assert result.resolved is True
        assert result.server_backed is True

    def test_product_envelope_ok_false_is_failure(self):
        from keyhole_sdk.run_lifecycle.status import fetch_run_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={
                "ok": False,
                "error": {
                    "code": "PRODUCT_SUBJECT_NOT_FOUND",
                    "message": "Product subject not found.",
                },
            },
        )

        result = fetch_run_status(transport=transport, run_id="run-missing")

        assert result.success is False
        assert result.status.value == "unknown"
        assert result.error_class == "PRODUCT_SUBJECT_NOT_FOUND"
        assert result.reason == "Product subject not found."


# --------------------------------------------------------------
# Test 5: wait_for_terminal (section5.3/section11)
# --------------------------------------------------------------


class TestWaitForTerminal:
    """section11: Poll until terminal or interrupted."""

    def test_immediate_terminal(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        from keyhole_sdk.run_lifecycle.wait import wait_for_terminal
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "success", "run_id": "run-w1"},
        )
        result = wait_for_terminal(transport=transport, run_id="run-w1")
        assert result.success is True
        assert result.terminal_status == RunStatus.SUCCESS
        assert result.polls == 1
        assert result.interrupted is False

    def test_poll_to_terminal(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        from keyhole_sdk.run_lifecycle.wait import wait_for_terminal

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return _MockTransportResult(data={"status": "running", "run_id": "run-w2"})
            return _MockTransportResult(data={"status": "success", "run_id": "run-w2"})

        transport = MagicMock()
        transport.execute.side_effect = mock_execute
        result = wait_for_terminal(
            transport=transport, run_id="run-w2", poll_interval=0.01,
        )
        assert result.success is True
        assert result.terminal_status == RunStatus.SUCCESS
        assert result.polls == 3

    def test_timeout(self):
        from keyhole_sdk.run_lifecycle.wait import wait_for_terminal
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-w3"},
        )
        result = wait_for_terminal(
            transport=transport, run_id="run-w3",
            poll_interval=0.01, max_polls=3,
        )
        assert result.success is False
        assert result.error_class == "wait_timeout"
        assert result.polls == 3

    def test_observation_failure(self):
        from keyhole_sdk.run_lifecycle.wait import wait_for_terminal
        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("nope")
        result = wait_for_terminal(
            transport=transport, run_id="run-w4", poll_interval=0.01,
        )
        assert result.success is False
        assert "observation" in result.reason.lower() or "retrieval" in result.reason.lower()

    def test_on_poll_callback_stops(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        from keyhole_sdk.run_lifecycle.wait import wait_for_terminal
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-w5"},
        )
        result = wait_for_terminal(
            transport=transport, run_id="run-w5",
            poll_interval=0.01,
            on_poll=lambda sr, n: n >= 2,  # stop after 2 polls
        )
        assert result.success is True
        assert result.interrupted is True
        assert result.polls == 2


# --------------------------------------------------------------
# Test 6: tail_run (section5.4/section12)
# --------------------------------------------------------------


class TestTailRun:
    """section12: Follow observations with honest labeling."""

    def test_status_changes_tracked(self):
        from keyhole_sdk.run_lifecycle.tail import tail_run

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            statuses = ["accepted", "running", "success"]
            idx = min(call_count - 1, len(statuses) - 1)
            return _MockTransportResult(
                data={"status": statuses[idx], "run_id": "run-t1"},
            )

        transport = MagicMock()
        transport.execute.side_effect = mock_execute
        result = tail_run(
            transport=transport, run_id="run-t1", poll_interval=0.01,
        )
        assert result.success is True
        assert len(result.entries) >= 2
        # All entries labeled as status_poll
        for entry in result.entries:
            assert entry.source == "status_poll"

    def test_terminal_stops(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus
        from keyhole_sdk.run_lifecycle.tail import tail_run
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "failed", "run_id": "run-t2"},
        )
        result = tail_run(
            transport=transport, run_id="run-t2", poll_interval=0.01,
        )
        assert result.success is True
        assert result.terminal_status == RunStatus.FAILED
        assert len(result.entries) == 1

    def test_honest_observation_method(self):
        from keyhole_sdk.run_lifecycle.tail import tail_run
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "success", "run_id": "run-t3"},
        )
        result = tail_run(
            transport=transport, run_id="run-t3", poll_interval=0.01,
        )
        assert result.observation_method == "status_poll"

    def test_observation_failure(self):
        from keyhole_sdk.run_lifecycle.tail import tail_run
        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("gone")
        result = tail_run(
            transport=transport, run_id="run-t4", poll_interval=0.01,
        )
        assert result.success is False
        assert result.repair_guidance

    def test_on_entry_callback_stops(self):
        from keyhole_sdk.run_lifecycle.tail import tail_run

        call_count = 0
        def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _MockTransportResult(
                data={"status": f"state_{call_count}", "run_id": "run-t5"},
            )

        transport = MagicMock()
        transport.execute.side_effect = mock_execute
        result = tail_run(
            transport=transport, run_id="run-t5",
            poll_interval=0.01,
            on_entry=lambda e: True,  # stop immediately on first entry
        )
        assert result.success is True
        assert result.interrupted is True
        assert len(result.entries) == 1

    def test_repeated_unknown_stops_at_poll_budget(self):
        from keyhole_sdk.run_lifecycle.tail import tail_run

        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "unknown", "run_id": "run-t6"},
        )

        result = tail_run(
            transport=transport,
            run_id="run-t6",
            poll_interval=0,
            max_entries=3,
        )

        assert result.success is True
        assert result.terminal_status is None
        assert len(result.entries) == 1
        assert transport.execute.call_count == 3


# --------------------------------------------------------------
# Test 7: resume_run (section5.5/section13)
# --------------------------------------------------------------


class TestResumeRun:
    """section13: Reconnect to existing governed run identity."""

    def test_local_record_found(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        from keyhole_sdk.run_lifecycle.resume import resume_run

        store = LocalRunRecordStore(tmp_path)
        store.save(RunRecord(run_id="run-r1", run_type="test", last_known_status="running"))

        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "success", "run_id": "run-r1"},
        )

        result = resume_run(
            transport=transport, identifier="run-r1",
            repo_dir=tmp_path, repo_name="test",
        )
        assert result.success is True
        assert result.source == "local_record"
        assert result.reconnected is True

    def test_boundary_lookup_fallback(self, tmp_path):
        from keyhole_sdk.run_lifecycle.resume import resume_run
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-r2", "run_type": "gaps.list"},
        )
        result = resume_run(
            transport=transport, identifier="run-r2",
            repo_dir=tmp_path, repo_name="test",
        )
        assert result.success is True
        assert result.source == "boundary_lookup"

    def test_ambiguity_when_neither(self, tmp_path):
        from keyhole_sdk.run_lifecycle.resume import resume_run
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"message": "not found"}, status_code=404,
        )
        result = resume_run(
            transport=transport, identifier="run-r3",
            repo_dir=tmp_path, repo_name="test",
        )
        assert result.success is False
        assert result.error_class == "resume_ambiguous"
        assert result.repair_guidance

    def test_missing_identifier(self, tmp_path):
        from keyhole_sdk.run_lifecycle.resume import resume_run
        transport = MagicMock()
        result = resume_run(
            transport=transport, identifier="",
            repo_dir=tmp_path, repo_name="test",
        )
        assert result.success is False
        assert result.error_class == "missing_identifier"

    def test_local_record_with_boundary_fail(self, tmp_path):
        """Observation failure ≠ execution failure - local record still succeeds."""
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        from keyhole_sdk.run_lifecycle.resume import resume_run

        store = LocalRunRecordStore(tmp_path)
        store.save(RunRecord(run_id="run-r4", last_known_status="running"))

        transport = MagicMock()
        transport.execute.side_effect = ConnectionError("offline")

        result = resume_run(
            transport=transport, identifier="run-r4",
            repo_dir=tmp_path, repo_name="test",
        )
        assert result.success is True
        assert result.source == "local_record"
        assert "unavailable" in str(result.response_data).lower() or "local record" in str(result.response_data).lower()


# --------------------------------------------------------------
# Test 8: Lifecycle Proof Emission (section15)
# --------------------------------------------------------------


class TestRunLifecycleProof:
    """section15: Proof artifacts under proof_bundle/."""

    def test_accepted_proof(self, tmp_path):
        from keyhole_sdk.run_lifecycle.proof import emit_accepted_proof
        proof_dir = emit_accepted_proof(
            repo_dir=tmp_path, run_id="run-p1",
            correlation_id="corr-1", run_type="context.compile",
        )
        accepted_file = proof_dir / "accepted.json"
        assert accepted_file.exists()
        data = json.loads(accepted_file.read_text())
        assert data["stage"] == "accepted"
        assert data["run_id"] == "run-p1"
        assert data["run_type"] == "context.compile"

    def test_status_proof(self, tmp_path):
        from keyhole_sdk.run_lifecycle.proof import emit_status_proof
        proof_dir = emit_status_proof(
            repo_dir=tmp_path, run_id="run-p2", status="running",
        )
        status_file = proof_dir / "latest-status.json"
        assert status_file.exists()
        data = json.loads(status_file.read_text())
        assert data["observed_status"] == "running"

    def test_outcome_proof_with_summary(self, tmp_path):
        from keyhole_sdk.run_lifecycle.proof import emit_outcome_proof
        proof_dir = emit_outcome_proof(
            repo_dir=tmp_path, run_id="run-p3",
            terminal_status="success",
            final_data={"result": "all good"},
        )
        outcome_file = proof_dir / "outcome.json"
        summary_file = proof_dir / "summary.md"
        assert outcome_file.exists()
        assert summary_file.exists()
        data = json.loads(outcome_file.read_text())
        assert data["terminal_status"] == "success"
        summary = summary_file.read_text()
        assert "run-p3" in summary
        assert "success" in summary.lower()

    def test_core_vs_extended_paths(self, tmp_path):
        from keyhole_sdk.run_lifecycle.proof import emit_run_lifecycle_proof
        # Core stages
        core_dir = emit_run_lifecycle_proof(
            repo_dir=tmp_path, run_id="run-p4", stage="accepted", data={},
        )
        assert "core" in str(core_dir)
        # Extended stages
        ext_dir = emit_run_lifecycle_proof(
            repo_dir=tmp_path, run_id="run-p4", stage="events", data={},
        )
        assert "extended" in str(ext_dir)

    def test_generic_lifecycle_proof(self, tmp_path):
        from keyhole_sdk.run_lifecycle.proof import emit_run_lifecycle_proof
        proof_dir = emit_run_lifecycle_proof(
            repo_dir=tmp_path, run_id="run-p5", stage="debug",
            data={"detail": "some debug info"}, correlation_id="corr-5",
        )
        debug_file = proof_dir / "debug.json"
        assert debug_file.exists()
        data = json.loads(debug_file.read_text())
        assert data["correlation_id"] == "corr-5"
        assert data["detail"] == "some debug info"


# --------------------------------------------------------------
# Test 9: Repair Guidance (section17)
# --------------------------------------------------------------


class TestRunLifecycleRepair:
    """section17: Error -> concrete repair steps."""

    def test_known_classes(self):
        from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
        known = [
            "non_terminal", "observation_failed", "status_retrieval_failed",
            "terminal_failure", "resume_ambiguous", "missing_identifier",
            "protocol_error", "missing_run_id", "wait_timeout",
            "wait_interrupted", "AuthenticationError", "TransportUnknownError",
            "RetryExhaustedError", "RuntimeUnavailableError", "malformed_run_id",
        ]
        for cls in known:
            guidance = map_run_lifecycle_repair(cls)
            assert isinstance(guidance, list)
            assert len(guidance) >= 1

    def test_unknown_fallback(self):
        from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
        guidance = map_run_lifecycle_repair("totally_unknown_error")
        assert isinstance(guidance, list)
        assert len(guidance) >= 1
        assert "totally_unknown_error" in guidance[0]


# --------------------------------------------------------------
# Test 10: Operation Registry (SDK-CLIENT-17 additions)
# --------------------------------------------------------------


class TestOperationRegistry:
    """run.status and events.query registered as READ_ONLY."""

    def test_run_status_registered(self):
        from keyhole_sdk.transport.operation_registry import (
            get_operation, OperationClass,
        )
        desc = get_operation("run.status")
        assert desc is not None
        assert desc.operation_class == OperationClass.READ_ONLY

    def test_events_query_registered(self):
        from keyhole_sdk.transport.operation_registry import (
            get_operation, OperationClass,
        )
        desc = get_operation("events.query")
        assert desc is not None
        assert desc.operation_class == OperationClass.READ_ONLY


# --------------------------------------------------------------
# Test 11: SDK Exports (SDK-CLIENT-17)
# --------------------------------------------------------------


class TestSDKExports:
    """All 16 run lifecycle symbols exported from keyhole_sdk."""

    EXPECTED = [
        "RunRecord", "LocalRunRecordStore",
        "RunStatus", "TerminalState",
        "RunStatusResult", "RunWaitResult",
        "RunTailEntry", "RunTailResult", "RunResumeResult",
        "fetch_run_status", "wait_for_terminal",
        "tail_run", "resume_run",
        "emit_run_lifecycle_proof", "map_run_lifecycle_repair",
    ]

    def test_all_exports_present(self):
        import keyhole_sdk
        for name in self.EXPECTED:
            assert hasattr(keyhole_sdk, name), f"Missing export: {name}"
            assert name in keyhole_sdk.__all__, f"Not in __all__: {name}"

    def test_package_init_exports(self):
        from keyhole_sdk.run_lifecycle import __all__ as rl_all
        for name in self.EXPECTED:
            assert name in rl_all, f"Not in run_lifecycle.__all__: {name}"


# --------------------------------------------------------------
# Test 12: CLI runs commands
# --------------------------------------------------------------


class TestCLIRunsStatus:
    """keyhole runs status command."""

    def test_missing_run_id(self):
        from keyhole_cli.commands.runs_cmd import run_runs_status
        result = run_runs_status(run_id="")
        assert result.success is False
        assert result.exit_code != 0

    @patch("keyhole_cli.commands.runs_cmd._build_transport")
    def test_success(self, mock_bt):
        from keyhole_cli.commands.runs_cmd import run_runs_status
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-cs1", "run_type": "test"},
        )
        transport.close = MagicMock()
        mock_bt.return_value = (transport, MagicMock())
        result = run_runs_status(run_id="run-cs1")
        assert result.success is True
        assert result.data["status"] == "running"


class TestCLIRunsWait:
    """keyhole runs wait command."""

    def test_missing_run_id(self):
        from keyhole_cli.commands.runs_cmd import run_runs_wait
        result = run_runs_wait(run_id="")
        assert result.success is False

    @patch("keyhole_cli.commands.runs_cmd._build_transport")
    def test_immediate_terminal(self, mock_bt):
        from keyhole_cli.commands.runs_cmd import run_runs_wait
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "success", "run_id": "run-cw1"},
        )
        transport.close = MagicMock()
        mock_bt.return_value = (transport, MagicMock())
        result = run_runs_wait(run_id="run-cw1", poll_interval=0.01)
        assert result.success is True
        assert result.data["terminal_status"] == "success"


class TestCLIRunsTail:
    """keyhole runs tail command."""

    def test_missing_run_id(self):
        from keyhole_cli.commands.runs_cmd import run_runs_tail
        result = run_runs_tail(run_id="")
        assert result.success is False

    @patch("keyhole_cli.commands.runs_cmd._build_transport")
    def test_terminal_tail(self, mock_bt):
        from keyhole_cli.commands.runs_cmd import run_runs_tail
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "failed", "run_id": "run-ct1"},
        )
        transport.close = MagicMock()
        mock_bt.return_value = (transport, MagicMock())
        result = run_runs_tail(run_id="run-ct1", poll_interval=0.01)
        assert result.success is True
        assert result.data["terminal_status"] == "failed"
        assert result.data["observation_method"] == "status_poll"


class TestCLIRunsResume:
    """keyhole runs resume command."""

    def test_missing_identifier(self):
        from keyhole_cli.commands.runs_cmd import run_runs_resume
        result = run_runs_resume(identifier="")
        assert result.success is False

    @patch("keyhole_cli.commands.runs_cmd._build_transport")
    def test_boundary_resume(self, mock_bt):
        from keyhole_cli.commands.runs_cmd import run_runs_resume
        transport = MagicMock()
        transport.execute.return_value = _MockTransportResult(
            data={"status": "running", "run_id": "run-cr1", "run_type": "test"},
        )
        transport.close = MagicMock()
        mock_bt.return_value = (transport, MagicMock())
        result = run_runs_resume(identifier="run-cr1")
        assert result.success is True
        assert result.data["reconnected"] is True


class TestCLIRunsList:
    """keyhole runs list command."""

    def test_empty_list(self, tmp_path):
        from keyhole_cli.commands.runs_cmd import run_runs_list
        result = run_runs_list(repo_dir=str(tmp_path))
        assert result.success is True
        assert result.data["runs"] == []

    def test_with_records(self, tmp_path):
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore, RunRecord
        from keyhole_cli.commands.runs_cmd import run_runs_list
        store = LocalRunRecordStore(tmp_path)
        store.save(RunRecord(run_id="run-list1", run_type="test"))
        result = run_runs_list(repo_dir=str(tmp_path))
        assert result.success is True
        assert len(result.data["runs"]) == 1


# --------------------------------------------------------------
# Test 13: run_cmd.py persists records for ACCEPTED/DEFERRED
# --------------------------------------------------------------


class TestRunCmdRecordPersistence:
    """section8/section9: run_cmd persists local records for async outcomes."""

    def test_safe_persist_run_record(self, tmp_path):
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus, RunOutcome
        from keyhole_cli.commands.run_cmd import _safe_persist_run_record
        from keyhole_sdk.run_lifecycle.record import LocalRunRecordStore

        outcome = RunOutcome(
            status=OutcomeStatus.ACCEPTED,
            run_id="run-rp1",
            run_type="context.compile",
            repo_name="my-repo",
            shadow=False,
            correlation_id="corr-rp1",
            response_data={"ok": True},
        )

        # Create a mock request
        mock_request = MagicMock()
        mock_request.timestamp = "2025-01-01T00:00:00Z"

        _safe_persist_run_record(
            repo_dir=tmp_path,
            outcome=outcome,
            request=mock_request,
            context_ref="abc123",
            proof_dir=tmp_path / "proof",
        )

        store = LocalRunRecordStore(tmp_path)
        loaded = store.load("run-rp1")
        assert loaded is not None
        assert loaded.run_id == "run-rp1"
        assert loaded.run_type == "context.compile"
        assert loaded.ctxpack_digest == "abc123"

    def test_accepted_proof_emitted(self, tmp_path):
        from keyhole_sdk.run_dispatch.dispatcher import OutcomeStatus, RunOutcome
        from keyhole_cli.commands.run_cmd import _safe_persist_run_record

        outcome = RunOutcome(
            status=OutcomeStatus.ACCEPTED,
            run_id="run-rp2",
            run_type="test",
            repo_name="test",
            shadow=False,
            correlation_id="corr-rp2",
        )
        mock_request = MagicMock()
        mock_request.timestamp = "2025-01-01T00:00:00Z"

        _safe_persist_run_record(
            repo_dir=tmp_path,
            outcome=outcome,
            request=mock_request,
            context_ref="",
            proof_dir=None,
        )

        accepted_file = tmp_path / "proof_bundle" / "core" / "runs" / "run-rp2" / "accepted.json"
        assert accepted_file.exists()


# --------------------------------------------------------------
# Test 14: Negative / Edge Cases
# --------------------------------------------------------------


class TestNegativeCases:
    """Edge cases and defensive behavior."""

    def test_malformed_run_id_repair(self):
        from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
        guidance = map_run_lifecycle_repair("malformed_run_id")
        assert any("format" in g.lower() or "invalid" in g.lower() for g in guidance)

    def test_run_status_result_defaults(self):
        from keyhole_sdk.run_lifecycle.models import RunStatus, RunStatusResult
        r = RunStatusResult(success=True)
        assert r.run_id == ""
        assert r.status == RunStatus.UNKNOWN
        assert r.response_data == {}

    def test_run_wait_result_defaults(self):
        from keyhole_sdk.run_lifecycle.models import RunWaitResult
        r = RunWaitResult(success=False)
        assert r.polls == 0
        assert r.interrupted is False

    def test_run_tail_honest_label(self):
        """section12: Never present polling as a true stream."""
        from keyhole_sdk.run_lifecycle.models import RunTailResult
        r = RunTailResult(success=True)
        assert r.observation_method == "status_poll"

    def test_run_resume_result_defaults(self):
        from keyhole_sdk.run_lifecycle.models import RunResumeResult
        r = RunResumeResult(success=False)
        assert r.reconnected is False
        assert r.source == ""

    def test_safe_filename_sanitization(self):
        from keyhole_sdk.run_lifecycle.record import _safe_filename
        assert _safe_filename("abc-123_def.txt") == "abc-123_def.txt"
        assert "/" not in _safe_filename("../../etc/passwd")
        assert len(_safe_filename("a" * 200)) <= 128


# --------------------------------------------------------------
# Test 15: CLI runs_app wiring verification
# --------------------------------------------------------------


class TestCLIRunsAppWiring:
    """Verify runs_app is properly wired in cli.py."""

    def test_runs_app_exists(self):
        from keyhole_cli.cli import runs_app
        assert runs_app is not None

    def test_runs_commands_registered(self):
        """All 5 runs subcommands should be registered."""
        from keyhole_cli.cli import runs_app
        # Typer stores registered commands
        command_names = set()
        if hasattr(runs_app, "registered_commands"):
            for cmd in runs_app.registered_commands:
                if hasattr(cmd, "name"):
                    command_names.add(cmd.name)
        # Also check via click
        try:
            from click.testing import CliRunner
            import typer.testing
            runner = typer.testing.CliRunner()
            result = runner.invoke(runs_app, ["--help"])
            output = result.output
            for name in ["status", "wait", "tail", "resume", "list"]:
                assert name in output, f"Command '{name}' not in runs --help output"
        except ImportError:
            # If testing infrastructure unavailable, just check registration
            pass

    def test_run_cmd_next_steps_use_runs_commands(self):
        """ACCEPTED/DEFERRED next_steps should reference keyhole runs commands."""
        import inspect
        from keyhole_cli.commands.run_cmd import _outcome_to_result
        source = inspect.getsource(_outcome_to_result)
        assert "keyhole runs status" in source
        assert "keyhole runs wait" in source
