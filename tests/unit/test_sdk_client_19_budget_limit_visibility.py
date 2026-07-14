"""Tests for SDK-CLIENT-19: Budget, Limit, and Overload Visibility.

Covers:
  - LimitOutcomeClass enum values and membership
  - BudgetSnapshot construction and to_dict
  - LimitResult construction, methods (is_pressure, is_retryable,
    is_hard_terminal, to_proof_dict)
  - BudgetPressureRequest construction
  - parse_limit_outcome: all 7 outcome families, HTTP codes, field shapes
  - is_pressure_outcome and classify_retry_posture classifiers
  - map_budget_repair: all known error codes
  - render_budget_summary: deterministic labels, no false claims
  - emit_budget_proof: artifact shape, directory structure, file content
  - Operation registry: run.budget is READ_ONLY
  - Public API surface: 10 symbols in budget.__all__, in keyhole_sdk.__all__
  - CLI: runs budget command exists and wires run_budget
  - section15.3 anti-collapse: overload / defer / rate-limit never rendered as success
  - section14 proof completeness: every artifact written on every outcome class
  - Negative inputs: empty run_id, None response_data, malformed snapshots
  - Forward-compatibility: unknown outcome classes handled gracefully

All tests are pure-unit - no network, no MCP calls.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# -------------------------------------------------------------
# Path bootstrapping
# -------------------------------------------------------------

_SDK_PKG = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-sdk"
_CLI_PKG = Path(__file__).resolve().parents[2] / "packages" / "python" / "keyhole-cli"

for _p in (_SDK_PKG, _CLI_PKG):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# -------------------------------------------------------------
# Imports
# -------------------------------------------------------------

from keyhole_sdk.budget import (
    BudgetPressureRequest,
    BudgetSnapshot,
    LimitOutcomeClass,
    LimitResult,
    classify_retry_posture,
    emit_budget_proof,
    is_pressure_outcome,
    map_budget_repair,
    parse_limit_outcome,
    render_budget_summary,
)
from keyhole_sdk.budget.models import _HARD_TERMINAL_OUTCOMES, _TEMPORARY_OUTCOMES
from keyhole_sdk.budget.classifier import (
    classify_retry_posture as _classify_direct,
    is_pressure_outcome as _is_pressure_direct,
)
from keyhole_sdk.budget.proof import emit_budget_proof as _proof_direct
from keyhole_sdk.budget.repair import map_budget_repair as _repair_direct
from keyhole_sdk.budget.renderer import render_budget_summary as _render_direct
from keyhole_sdk.budget.parser import parse_limit_outcome as _parse_direct


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

def _empty_result(**kw) -> LimitResult:
    return LimitResult(**kw)


def _parse(data: Dict[str, Any], *, http: int = 200, run_id: str = "run-01") -> LimitResult:
    return parse_limit_outcome(data, http_status_code=http, run_id=run_id)


# -------------------------------------------------------------
# TestLimitOutcomeClassEnum
# -------------------------------------------------------------


class TestLimitOutcomeClassEnum:
    def test_all_seven_members_exist(self):
        values = {m.value for m in LimitOutcomeClass}
        assert "success_with_budget_visibility" in values
        assert "budget_exhausted" in values
        assert "deferred" in values
        assert "rate_limited" in values
        assert "concurrency_limited" in values
        assert "unknown_pressure" in values
        assert "no_pressure_data" in values

    def test_enum_is_str_subclass(self):
        assert isinstance(LimitOutcomeClass.DEFERRED, str)
        assert LimitOutcomeClass.DEFERRED == "deferred"

    def test_temporary_outcomes_frozenset(self):
        assert LimitOutcomeClass.DEFERRED in _TEMPORARY_OUTCOMES
        assert LimitOutcomeClass.RATE_LIMITED in _TEMPORARY_OUTCOMES
        assert LimitOutcomeClass.CONCURRENCY_LIMITED in _TEMPORARY_OUTCOMES
        assert LimitOutcomeClass.BUDGET_EXHAUSTED not in _TEMPORARY_OUTCOMES
        assert LimitOutcomeClass.NO_PRESSURE_DATA not in _TEMPORARY_OUTCOMES

    def test_hard_terminal_outcomes_frozenset(self):
        assert LimitOutcomeClass.BUDGET_EXHAUSTED in _HARD_TERMINAL_OUTCOMES
        assert LimitOutcomeClass.DEFERRED not in _HARD_TERMINAL_OUTCOMES
        assert LimitOutcomeClass.RATE_LIMITED not in _HARD_TERMINAL_OUTCOMES


# -------------------------------------------------------------
# TestBudgetSnapshotModel
# -------------------------------------------------------------


class TestBudgetSnapshotModel:
    def test_default_construction(self):
        s = BudgetSnapshot()
        assert s.budget_class == ""
        assert s.budget_used is None
        assert s.budget_remaining is None
        assert s.budget_unit == ""
        assert s.near_limit is False
        assert s.retry_after is None

    def test_full_construction(self):
        s = BudgetSnapshot(
            budget_class="wall_time",
            budget_used=500.0,
            budget_remaining=2500.0,
            budget_unit="ms",
            near_limit=False,
            retry_after=None,
        )
        assert s.budget_class == "wall_time"
        assert s.budget_used == 500.0
        assert s.budget_remaining == 2500.0
        assert s.budget_unit == "ms"

    def test_near_limit_flag(self):
        s = BudgetSnapshot(
            budget_class="event",
            budget_used=95.0,
            budget_remaining=5.0,
            near_limit=True,
        )
        assert s.near_limit is True

    def test_retry_after(self):
        s = BudgetSnapshot(retry_after=30)
        assert s.retry_after == 30

    def test_to_dict_all_keys(self):
        s = BudgetSnapshot(budget_class="byte", budget_used=100.0)
        d = s.to_dict()
        assert "budget_class" in d
        assert "budget_used" in d
        assert "budget_remaining" in d
        assert "budget_unit" in d
        assert "near_limit" in d
        assert "retry_after" in d

    def test_to_dict_values(self):
        s = BudgetSnapshot(budget_class="byte", budget_used=100.0, near_limit=True)
        d = s.to_dict()
        assert d["budget_class"] == "byte"
        assert d["budget_used"] == 100.0
        assert d["near_limit"] is True


# -------------------------------------------------------------
# TestLimitResultModel
# -------------------------------------------------------------


class TestLimitResultModel:
    def test_default_outcome_is_no_pressure_data(self):
        r = LimitResult()
        assert r.outcome_class == LimitOutcomeClass.NO_PRESSURE_DATA

    def test_is_pressure_false_for_success(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY)
        assert r.is_pressure() is False

    def test_is_pressure_false_for_no_data(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.NO_PRESSURE_DATA)
        assert r.is_pressure() is False

    def test_is_pressure_true_for_budget_exhausted(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED)
        assert r.is_pressure() is True

    def test_is_pressure_true_for_deferred(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        assert r.is_pressure() is True

    def test_is_pressure_true_for_rate_limited(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED)
        assert r.is_pressure() is True

    def test_is_pressure_true_for_concurrency_limited(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.CONCURRENCY_LIMITED)
        assert r.is_pressure() is True

    def test_is_pressure_true_for_unknown_pressure(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.UNKNOWN_PRESSURE)
        assert r.is_pressure() is True

    def test_is_retryable_for_deferred(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        assert r.is_retryable() is True

    def test_is_retryable_for_rate_limited(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED)
        assert r.is_retryable() is True

    def test_is_retryable_for_concurrency_limited(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.CONCURRENCY_LIMITED)
        assert r.is_retryable() is True

    def test_is_retryable_false_for_budget_exhausted(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=False)
        assert r.is_retryable() is False

    def test_is_retryable_true_when_retry_safe_flag_set(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=True)
        assert r.is_retryable() is True

    def test_is_hard_terminal_for_budget_exhausted(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=False)
        assert r.is_hard_terminal() is True

    def test_is_hard_terminal_false_if_retry_safe(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=True)
        assert r.is_hard_terminal() is False

    def test_is_hard_terminal_false_for_deferred(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        assert r.is_hard_terminal() is False

    def test_to_proof_dict_required_keys(self):
        r = LimitResult(run_id="r1", request_id="req1", status="deferred")
        d = r.to_proof_dict()
        assert "run_id" in d
        assert "request_id" in d
        assert "status" in d
        assert "limit_outcome" in d
        assert "limit_class" in d
        assert "budget_snapshot" in d
        assert "retry_after" in d
        assert "repair_guidance" in d
        assert "correlation_id" in d
        assert "partial_execution" in d
        assert "is_terminal" in d
        assert "retry_safe" in d
        assert "parsed_at" in d

    def test_to_proof_dict_values(self):
        r = LimitResult(
            run_id="run-xyz",
            outcome_class=LimitOutcomeClass.DEFERRED,
            status="deferred",
        )
        d = r.to_proof_dict()
        assert d["run_id"] == "run-xyz"
        assert d["limit_outcome"] == "deferred"

    def test_parsed_at_is_set_automatically(self):
        r = LimitResult()
        assert isinstance(r.parsed_at, str)
        assert "T" in r.parsed_at  # ISO datetime

    def test_budget_snapshots_default_empty(self):
        r = LimitResult()
        assert r.budget_snapshots == []

    def test_budget_snapshots_in_to_proof_dict(self):
        snap = BudgetSnapshot(budget_class="wall_time", budget_used=100.0)
        r = LimitResult(budget_snapshots=[snap])
        d = r.to_proof_dict()
        assert len(d["budget_snapshot"]) == 1
        assert d["budget_snapshot"][0]["budget_class"] == "wall_time"


# -------------------------------------------------------------
# TestBudgetPressureRequest
# -------------------------------------------------------------


class TestBudgetPressureRequest:
    def test_defaults(self):
        req = BudgetPressureRequest()
        assert req.run_id == ""
        assert req.request_id == ""
        assert req.correlation_id == ""
        assert req.mcp_url == ""
        assert isinstance(req.queried_at, str)

    def test_construction(self):
        req = BudgetPressureRequest(
            run_id="run-01",
            mcp_url="https://mcp.example.com",
        )
        assert req.run_id == "run-01"
        assert req.mcp_url == "https://mcp.example.com"

    def test_queried_at_iso_format(self):
        req = BudgetPressureRequest()
        assert "T" in req.queried_at


# -------------------------------------------------------------
# TestParseLimitOutcome
# -------------------------------------------------------------


class TestParseLimitOutcome:
    def test_empty_response_is_no_pressure_data(self):
        r = _parse({})
        assert r.outcome_class == LimitOutcomeClass.NO_PRESSURE_DATA

    def test_none_response_is_no_pressure_data(self):
        r = _parse(None)
        assert r.outcome_class == LimitOutcomeClass.NO_PRESSURE_DATA

    def test_run_id_preserved(self):
        r = _parse({}, run_id="run-99")
        assert r.run_id == "run-99"

    def test_http_429_is_rate_limited(self):
        r = _parse({}, http=429)
        assert r.outcome_class == LimitOutcomeClass.RATE_LIMITED
        assert r.is_pressure() is True

    def test_http_503_is_deferred(self):
        r = _parse({}, http=503)
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_http_529_is_deferred(self):
        r = _parse({}, http=529)
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_explicit_limit_outcome_field_budget_exhausted(self):
        r = _parse({"limit_outcome": "budget_exhausted"})
        assert r.outcome_class == LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_explicit_limit_outcome_field_deferred(self):
        r = _parse({"limit_outcome": "deferred"})
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_explicit_limit_outcome_rate_limited(self):
        r = _parse({"limit_outcome": "rate_limited"})
        assert r.outcome_class == LimitOutcomeClass.RATE_LIMITED

    def test_explicit_limit_outcome_concurrency_limited(self):
        r = _parse({"limit_outcome": "concurrency_limited"})
        assert r.outcome_class == LimitOutcomeClass.CONCURRENCY_LIMITED

    def test_explicit_limit_outcome_success_with_visibility(self):
        r = _parse({"limit_outcome": "success_with_budget_visibility"})
        assert r.outcome_class == LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY

    def test_status_budget_exhausted(self):
        r = _parse({"status": "budget_exhausted"})
        assert r.outcome_class == LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_status_budget_exceeded(self):
        r = _parse({"status": "budget_exceeded"})
        assert r.outcome_class == LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_status_throttled(self):
        r = _parse({"status": "throttled"})
        assert r.outcome_class == LimitOutcomeClass.RATE_LIMITED

    def test_status_deferred(self):
        r = _parse({"status": "deferred"})
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_status_held(self):
        r = _parse({"status": "held"})
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_status_concurrency_exceeded(self):
        r = _parse({"status": "concurrency_exceeded"})
        assert r.outcome_class == LimitOutcomeClass.CONCURRENCY_LIMITED

    def test_budget_snapshots_extracted_from_budget_snapshots_key(self):
        r = _parse({"budget_snapshots": [{"budget_class": "wall_time", "budget_used": 100}]})
        assert len(r.budget_snapshots) == 1
        assert r.budget_snapshots[0].budget_class == "wall_time"

    def test_budget_snapshots_extracted_from_budget_key(self):
        r = _parse({"budget": {"budget_class": "event", "budget_used": 5}})
        assert len(r.budget_snapshots) == 1
        assert r.budget_snapshots[0].budget_class == "event"

    def test_budget_snapshot_near_limit(self):
        r = _parse({
            "budget_snapshots": [
                {"budget_class": "wall_time", "budget_used": 950.0,
                 "budget_remaining": 50.0, "near_limit": True}
            ]
        })
        assert r.budget_snapshots[0].near_limit is True

    def test_retry_after_from_top_level(self):
        r = _parse({"limit_outcome": "deferred", "retry_after": 30})
        assert r.retry_after == 30

    def test_retry_after_from_snapshot(self):
        r = _parse({
            "limit_outcome": "rate_limited",
            "budget_snapshots": [{"budget_class": "req_rate", "retry_after": 60}],
        })
        # Top-level retry_after may not be set, but snapshot has it
        assert r.budget_snapshots[0].retry_after == 60

    def test_limit_class_extracted_from_response(self):
        r = _parse({"limit_outcome": "budget_exhausted", "limit_class": "wall_time"})
        assert r.limit_class == "wall_time"

    def test_partial_execution_flag(self):
        r = _parse({"limit_outcome": "budget_exhausted", "partial_execution": True})
        assert r.partial_execution is True

    def test_repair_guidance_populated_for_pressure(self):
        r = _parse({"limit_outcome": "budget_exhausted"})
        assert isinstance(r.repair_guidance, list)
        assert len(r.repair_guidance) > 0

    def test_unknown_limit_outcome_value_maps_to_unknown_pressure(self):
        r = _parse({"limit_outcome": "future_unknown_category"})
        assert r.outcome_class == LimitOutcomeClass.UNKNOWN_PRESSURE

    def test_status_present_propagated(self):
        r = _parse({"status": "deferred", "limit_outcome": "deferred"}, run_id="run-42")
        assert r.status == "deferred"
        assert r.run_id == "run-42"

    def test_budget_present_but_no_pressure_still_classified(self):
        # Budget data present on a success-like response -> SUCCESS_WITH_BUDGET_VISIBILITY
        r = _parse({
            "status": "success",
            "budget_snapshots": [{"budget_class": "wall_time", "budget_used": 100}],
        })
        assert r.outcome_class == LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY

    def test_correlation_id_preserved(self):
        r = parse_limit_outcome(
            {"status": "deferred"},
            http_status_code=200,
            run_id="r",
            request_id="req",
            correlation_id="corr-123",
        )
        assert r.correlation_id == "corr-123"

    def test_raw_data_preserved(self):
        data = {"limit_outcome": "deferred", "extra_field": "value"}
        r = _parse(data)
        assert r.raw_data.get("extra_field") == "value"


# -------------------------------------------------------------
# TestClassifier
# -------------------------------------------------------------


class TestClassifier:
    def test_is_pressure_outcome_true_for_budget_exhausted(self):
        assert is_pressure_outcome(LimitOutcomeClass.BUDGET_EXHAUSTED) is True

    def test_is_pressure_outcome_true_for_deferred(self):
        assert is_pressure_outcome(LimitOutcomeClass.DEFERRED) is True

    def test_is_pressure_outcome_true_for_rate_limited(self):
        assert is_pressure_outcome(LimitOutcomeClass.RATE_LIMITED) is True

    def test_is_pressure_outcome_true_for_concurrency_limited(self):
        assert is_pressure_outcome(LimitOutcomeClass.CONCURRENCY_LIMITED) is True

    def test_is_pressure_outcome_true_for_unknown(self):
        assert is_pressure_outcome(LimitOutcomeClass.UNKNOWN_PRESSURE) is True

    def test_is_pressure_outcome_false_for_success(self):
        assert is_pressure_outcome(LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY) is False

    def test_is_pressure_outcome_false_for_no_data(self):
        assert is_pressure_outcome(LimitOutcomeClass.NO_PRESSURE_DATA) is False

    def test_classify_retry_posture_deferred_is_retry_later(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        assert classify_retry_posture(r) == "retry_later"

    def test_classify_retry_posture_rate_limited_is_retry_later(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED)
        assert classify_retry_posture(r) == "retry_later"

    def test_classify_retry_posture_concurrency_limited_is_retry_later(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.CONCURRENCY_LIMITED)
        assert classify_retry_posture(r) == "retry_later"

    def test_classify_retry_posture_budget_exhausted_is_do_not_retry(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=False)
        assert classify_retry_posture(r) == "do_not_retry"

    def test_classify_retry_posture_budget_exhausted_retry_safe_is_retry_safe(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, retry_safe=True)
        assert classify_retry_posture(r) == "retry_safe"

    def test_classify_retry_posture_unknown_is_unknown(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.UNKNOWN_PRESSURE)
        assert classify_retry_posture(r) == "unknown"

    def test_classify_retry_posture_success_is_unknown(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY)
        assert classify_retry_posture(r) == "unknown"

    def test_classify_retry_posture_no_data_is_unknown(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.NO_PRESSURE_DATA)
        assert classify_retry_posture(r) == "unknown"

    def test_direct_import_matches_package_import(self):
        assert is_pressure_outcome is _is_pressure_direct
        assert classify_retry_posture is _classify_direct


# -------------------------------------------------------------
# TestRepairGuidance
# -------------------------------------------------------------


class TestRepairGuidance:
    def test_repair_for_budget_exhausted_is_list(self):
        guidance = map_budget_repair("budget_exhausted")
        assert isinstance(guidance, list)
        assert len(guidance) > 0

    def test_repair_for_deferred_is_list(self):
        guidance = map_budget_repair("deferred")
        assert isinstance(guidance, list)
        assert len(guidance) > 0

    def test_repair_for_rate_limited_is_list(self):
        guidance = map_budget_repair("rate_limited")
        assert isinstance(guidance, list)
        assert len(guidance) > 0

    def test_repair_for_concurrency_limited_is_list(self):
        guidance = map_budget_repair("concurrency_limited")
        assert isinstance(guidance, list)
        assert len(guidance) > 0

    def test_repair_for_unknown_pressure_is_list(self):
        guidance = map_budget_repair("unknown_pressure")
        assert isinstance(guidance, list)
        assert len(guidance) > 0

    def test_repair_for_success_with_visibility_is_list(self):
        guidance = map_budget_repair("success_with_budget_visibility")
        assert isinstance(guidance, list)

    def test_repair_for_no_pressure_data_is_list(self):
        guidance = map_budget_repair("no_pressure_data")
        assert isinstance(guidance, list)

    def test_repair_for_unknown_code_returns_default(self):
        guidance = map_budget_repair("completely_made_up_code")
        assert isinstance(guidance, list)

    def test_repair_entries_are_strings(self):
        for code in ("budget_exhausted", "deferred", "rate_limited", "concurrency_limited"):
            guidance = map_budget_repair(code)
            assert all(isinstance(s, str) for s in guidance), f"Non-string entry for {code}"

    def test_direct_import_matches_package_import(self):
        assert map_budget_repair is _repair_direct


# -------------------------------------------------------------
# TestRenderBudgetSummary
# -------------------------------------------------------------


class TestRenderBudgetSummary:
    def test_returns_string(self):
        r = LimitResult()
        assert isinstance(render_budget_summary(r), str)

    def test_no_pressure_data_in_output(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.NO_PRESSURE_DATA)
        s = render_budget_summary(r)
        assert isinstance(s, str)
        assert len(s) > 0

    def test_budget_exhausted_label_present(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, run_id="run-42")
        s = render_budget_summary(r)
        assert "exhausted" in s.lower() or "budget" in s.lower()

    def test_deferred_label_present(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        s = render_budget_summary(r)
        assert "deferred" in s.lower() or "pressure" in s.lower()

    def test_rate_limited_label_present(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED)
        s = render_budget_summary(r)
        assert "rate" in s.lower() or "limit" in s.lower()

    def test_concurrency_limited_label_present(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.CONCURRENCY_LIMITED)
        s = render_budget_summary(r)
        assert "concurrency" in s.lower() or "limit" in s.lower()

    def test_success_with_visibility_label_present(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY)
        s = render_budget_summary(r)
        assert isinstance(s, str)

    def test_run_id_shown(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-555")
        s = render_budget_summary(r)
        assert "run-555" in s

    def test_retry_after_shown_when_present(self):
        r = LimitResult(
            outcome_class=LimitOutcomeClass.RATE_LIMITED,
            retry_after=60,
        )
        s = render_budget_summary(r)
        assert "60" in s

    def test_budget_snapshot_info_shown(self):
        snap = BudgetSnapshot(budget_class="wall_time", budget_used=500.0, budget_unit="ms")
        r = LimitResult(
            outcome_class=LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY,
            budget_snapshots=[snap],
        )
        s = render_budget_summary(r)
        assert "wall_time" in s

    def test_deferred_does_not_say_succeeded(self):
        """section15.3: Deferred must never be rendered as success."""
        r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        s = render_budget_summary(r)
        assert "succeeded" not in s.lower()
        assert "success" not in s.lower() or "budget" in s.lower()

    def test_rate_limited_does_not_say_succeeded(self):
        """section15.3: Rate-limited must never be rendered as success."""
        r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED)
        s = render_budget_summary(r)
        assert "succeeded" not in s.lower()

    def test_budget_exhausted_does_not_say_succeeded(self):
        """section15.3: Budget exhausted must never be rendered as success."""
        r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED)
        s = render_budget_summary(r)
        assert "succeeded" not in s.lower()

    def test_direct_import_matches_package_import(self):
        assert render_budget_summary is _render_direct

    def test_repair_steps_shown_when_present(self):
        r = LimitResult(
            outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED,
            repair_guidance=["Step A", "Step B"],
        )
        s = render_budget_summary(r)
        assert "Step A" in s


# -------------------------------------------------------------
# TestProofEmission
# -------------------------------------------------------------


class TestProofEmission:
    def test_returns_path(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-01")
            path = emit_budget_proof(Path(td), run_id="run-01", result=r)
            assert isinstance(path, Path)

    def test_outcome_json_written(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-01")
            proof_dir = emit_budget_proof(Path(td), run_id="run-01", result=r)
            assert (proof_dir / "outcome.json").is_file()

    def test_budget_json_written(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED, run_id="run-02")
            proof_dir = emit_budget_proof(Path(td), run_id="run-02", result=r)
            assert (proof_dir / "budget.json").is_file()

    def test_latest_status_json_written(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, run_id="run-03")
            proof_dir = emit_budget_proof(Path(td), run_id="run-03", result=r)
            assert (proof_dir / "latest-status.json").is_file()

    def test_summary_md_written(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.CONCURRENCY_LIMITED, run_id="run-04")
            proof_dir = emit_budget_proof(Path(td), run_id="run-04", result=r)
            assert (proof_dir / "summary.md").is_file()

    def test_request_json_written_when_request_provided(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-05")
            req = BudgetPressureRequest(run_id="run-05", mcp_url="https://mcp.example.com")
            proof_dir = emit_budget_proof(Path(td), run_id="run-05", result=r, request=req)
            assert (proof_dir / "request.json").is_file()

    def test_request_json_not_written_when_no_request(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-06")
            proof_dir = emit_budget_proof(Path(td), run_id="run-06", result=r)
            assert not (proof_dir / "request.json").is_file()

    def test_outcome_json_is_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-07")
            proof_dir = emit_budget_proof(Path(td), run_id="run-07", result=r)
            data = json.loads((proof_dir / "outcome.json").read_text())
            assert "limit_outcome" in data

    def test_budget_json_contains_outcome_class(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.RATE_LIMITED, run_id="run-08")
            proof_dir = emit_budget_proof(Path(td), run_id="run-08", result=r)
            data = json.loads((proof_dir / "budget.json").read_text())
            assert data.get("limit_outcome") == "rate_limited"

    def test_summary_md_has_budget_header(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED, run_id="run-09")
            proof_dir = emit_budget_proof(Path(td), run_id="run-09", result=r)
            content = (proof_dir / "summary.md").read_text()
            assert "Budget" in content

    def test_proof_dir_under_runs_subdirectory(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-10")
            proof_dir = emit_budget_proof(Path(td), run_id="run-10", result=r)
            assert "runs" in proof_dir.parts

    def test_run_id_used_in_directory_name(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED, run_id="run-ABCD")
            proof_dir = emit_budget_proof(Path(td), run_id="run-ABCD", result=r)
            assert "run-ABCD" in str(proof_dir)

    def test_safe_id_clamps_to_64_chars(self):
        with tempfile.TemporaryDirectory() as td:
            long_id = "x" * 100
            r = LimitResult(run_id=long_id)
            proof_dir = emit_budget_proof(Path(td), run_id=long_id, result=r)
            assert len(proof_dir.name) <= 64

    def test_budget_json_has_snapshots_key(self):
        with tempfile.TemporaryDirectory() as td:
            snap = BudgetSnapshot(budget_class="wall_time", budget_used=100.0)
            r = LimitResult(
                outcome_class=LimitOutcomeClass.SUCCESS_WITH_BUDGET_VISIBILITY,
                run_id="run-11",
                budget_snapshots=[snap],
            )
            proof_dir = emit_budget_proof(Path(td), run_id="run-11", result=r)
            data = json.loads((proof_dir / "budget.json").read_text())
            assert "budget_snapshots" in data
            assert data["budget_snapshots"][0]["budget_class"] == "wall_time"

    def test_direct_import_matches_package_import(self):
        assert emit_budget_proof is _proof_direct


# -------------------------------------------------------------
# TestOperationRegistry
# -------------------------------------------------------------


class TestOperationRegistry:
    def test_run_budget_is_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation
        op = get_operation("run.budget")
        assert op is not None

    def test_run_budget_is_read_only(self):
        from keyhole_sdk.transport.operation_registry import get_operation, OperationClass
        op = get_operation("run.budget")
        assert op.operation_class == OperationClass.READ_ONLY

    def test_run_budget_idempotency_not_required(self):
        from keyhole_sdk.transport.operation_registry import get_operation
        op = get_operation("run.budget")
        assert op.idempotency_required is False


# -------------------------------------------------------------
# TestPublicAPISurface
# -------------------------------------------------------------


class TestPublicAPISurface:
    _EXPECTED_BUDGET_SYMBOLS = {
        "LimitOutcomeClass",
        "BudgetSnapshot",
        "LimitResult",
        "BudgetPressureRequest",
        "parse_limit_outcome",
        "render_budget_summary",
        "emit_budget_proof",
        "map_budget_repair",
        "is_pressure_outcome",
        "classify_retry_posture",
    }

    def test_budget_package_all_has_ten_symbols(self):
        from keyhole_sdk.budget import __all__ as budget_all
        assert len(budget_all) == 10

    def test_budget_package_all_contains_expected_names(self):
        from keyhole_sdk.budget import __all__ as budget_all
        assert self._EXPECTED_BUDGET_SYMBOLS == set(budget_all)

    def test_all_symbols_importable_from_budget_package(self):
        import keyhole_sdk.budget as pkg
        for name in self._EXPECTED_BUDGET_SYMBOLS:
            assert hasattr(pkg, name), f"Missing: {name}"

    def test_ten_budget_symbols_in_keyhole_sdk_all(self):
        import keyhole_sdk
        sdk_all = set(keyhole_sdk.__all__)
        missing = self._EXPECTED_BUDGET_SYMBOLS - sdk_all
        assert not missing, f"Missing from keyhole_sdk.__all__: {missing}"

    def test_budget_symbols_importable_from_keyhole_sdk_toplevel(self):
        import keyhole_sdk as sdk
        for name in self._EXPECTED_BUDGET_SYMBOLS:
            assert hasattr(sdk, name), f"Not available at keyhole_sdk.{name}"


# -------------------------------------------------------------
# TestCLIBudgetCommand
# -------------------------------------------------------------


class TestCLIBudgetCommand:
    def test_runs_app_has_budget_command(self):
        from typer.testing import CliRunner
        from keyhole_cli.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["runs", "--help"])
        assert result.exit_code == 0
        assert "budget" in result.output

    def test_budget_command_requires_run_id(self):
        from typer.testing import CliRunner
        from keyhole_cli.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["runs", "budget"])
        # Should fail due to missing required argument
        assert result.exit_code != 0

    def test_budget_cmd_module_importable(self):
        from keyhole_cli.commands.budget_cmd import run_budget
        assert callable(run_budget)

    def test_run_budget_returns_failure_for_empty_run_id(self):
        from keyhole_cli.commands.budget_cmd import run_budget
        result = run_budget(run_id="", keyhole_home="")
        assert result.success is False
        assert result.exit_code != 0

    def test_run_budget_returns_failure_for_whitespace_run_id(self):
        from keyhole_cli.commands.budget_cmd import run_budget
        result = run_budget(run_id="   ", keyhole_home="")
        assert result.success is False


# -------------------------------------------------------------
# TestNoCollapsingAntiPattern
# -------------------------------------------------------------


class TestNoCollapsingAntiPattern:
    """section15.3: Overload must never be collapsed into generic failure."""

    def test_deferred_is_its_own_class(self):
        r = _parse({"limit_outcome": "deferred"})
        assert r.outcome_class == LimitOutcomeClass.DEFERRED
        assert r.outcome_class != LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_rate_limited_is_its_own_class(self):
        r = _parse({}, http=429)
        assert r.outcome_class == LimitOutcomeClass.RATE_LIMITED
        assert r.outcome_class != LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_concurrency_limited_is_its_own_class(self):
        r = _parse({"limit_outcome": "concurrency_limited"})
        assert r.outcome_class == LimitOutcomeClass.CONCURRENCY_LIMITED
        assert r.outcome_class != LimitOutcomeClass.BUDGET_EXHAUSTED

    def test_deferred_render_label_distinct(self):
        r_defer = LimitResult(outcome_class=LimitOutcomeClass.DEFERRED)
        r_exhaust = LimitResult(outcome_class=LimitOutcomeClass.BUDGET_EXHAUSTED)
        s_defer = render_budget_summary(r_defer)
        s_exhaust = render_budget_summary(r_exhaust)
        assert s_defer != s_exhaust

    def test_repair_guidance_distinct_for_deferred_vs_exhausted(self):
        deferred_guidance = map_budget_repair("deferred")
        exhausted_guidance = map_budget_repair("budget_exhausted")
        assert deferred_guidance != exhausted_guidance


# -------------------------------------------------------------
# TestNegativeInputs
# -------------------------------------------------------------


class TestNegativeInputs:
    def test_parse_none_response_does_not_raise(self):
        r = parse_limit_outcome(None, http_status_code=200, run_id="r")
        assert r is not None
        assert r.outcome_class == LimitOutcomeClass.NO_PRESSURE_DATA

    def test_parse_empty_dict_does_not_raise(self):
        r = parse_limit_outcome({}, http_status_code=200, run_id="r")
        assert r is not None

    def test_parse_malformed_snapshot_does_not_raise(self):
        r = parse_limit_outcome(
            {"budget_snapshots": "not-a-list"},
            http_status_code=200,
            run_id="r",
        )
        assert r is not None

    def test_parse_snapshot_with_invalid_float_does_not_raise(self):
        r = parse_limit_outcome(
            {"budget_snapshots": [{"budget_class": "x", "budget_used": "not-a-number"}]},
            http_status_code=200,
            run_id="r",
        )
        assert r is not None

    def test_emit_proof_with_empty_run_id_does_not_raise(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult()
            path = emit_budget_proof(Path(td), run_id="", result=r)
            assert path.is_dir()

    def test_classify_retry_posture_on_default_result(self):
        r = LimitResult()
        posture = classify_retry_posture(r)
        assert isinstance(posture, str)


# -------------------------------------------------------------
# TestForwardCompatibility
# -------------------------------------------------------------


class TestForwardCompatibility:
    def test_unknown_limit_outcome_does_not_raise(self):
        r = _parse({"limit_outcome": "future_pressure_class"})
        assert r.outcome_class == LimitOutcomeClass.UNKNOWN_PRESSURE

    def test_render_unknown_pressure_does_not_raise(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.UNKNOWN_PRESSURE)
        s = render_budget_summary(r)
        assert isinstance(s, str)

    def test_repair_for_unknown_outcome_returns_list(self):
        g = map_budget_repair("unknown_pressure")
        assert isinstance(g, list)

    def test_classify_unknown_pressure_is_unknown(self):
        r = LimitResult(outcome_class=LimitOutcomeClass.UNKNOWN_PRESSURE)
        posture = classify_retry_posture(r)
        assert posture == "unknown"

    def test_extra_response_fields_ignored_gracefully(self):
        r = _parse({
            "limit_outcome": "deferred",
            "extra_field_future": "new_value",
            "another_future_field": {"nested": True},
        })
        assert r.outcome_class == LimitOutcomeClass.DEFERRED

    def test_proof_emitted_for_unknown_pressure(self):
        with tempfile.TemporaryDirectory() as td:
            r = LimitResult(outcome_class=LimitOutcomeClass.UNKNOWN_PRESSURE, run_id="r")
            proof_dir = emit_budget_proof(Path(td), run_id="r", result=r)
            assert (proof_dir / "outcome.json").is_file()
