"""Unit tests for SDK-CLIENT-16 - Context Lifecycle and Governed Run Binding.

Tests cover:
  - digest validation
  - compile request construction
  - compile result classification
  - inspect result classification
  - context preflight
  - proof artifact generation
  - local context tracker
  - repair guidance
  - no-floating-run enforcement
  - --context auto behavior
  - context binding in run proof
  - CLI command flows
  - SDK exports
  - transport discipline inheritance
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


# --------------------------------------------------------------
# Test 1: Digest Validation (section6/section10)
# --------------------------------------------------------------


class TestDigestValidation:
    """section6/section10: Malformed digests rejected locally."""

    def test_valid_hex_digest(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        assert validate_digest("a" * 64) is None

    def test_valid_prefixed_digest(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        assert validate_digest("sha256:" + "a" * 64) is None

    def test_valid_short_hex(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        assert validate_digest("abcdef1234567890") is None

    def test_auto_keyword_valid(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        assert validate_digest("auto") is None

    def test_empty_rejected(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        error = validate_digest("")
        assert error is not None
        assert "empty" in error.lower()

    def test_too_short_rejected(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        error = validate_digest("abc")
        assert error is not None
        assert "malformed" in error.lower()

    def test_special_chars_rejected(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        error = validate_digest("abc!@#$%^&*()")
        assert error is not None

    def test_is_auto(self):
        from keyhole_sdk.context_lifecycle.digest import is_auto
        assert is_auto("auto") is True
        assert is_auto("AUTO") is True
        assert is_auto("  auto  ") is True
        assert is_auto("abc123") is False

    def test_url_safe_base64_valid(self):
        from keyhole_sdk.context_lifecycle.digest import validate_digest
        assert validate_digest("A" * 32 + "_-" + "b" * 30) is None


# --------------------------------------------------------------
# Test 2: Compile Request Construction (section8)
# --------------------------------------------------------------


class TestCompileRequestConstruction:
    """section8: Deterministic compile request shaping."""

    def test_basic_request(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req = build_compile_request(repo_name="my-repo")
        assert req.repo_name == "my-repo"
        assert req.timestamp

    def test_payload_shape(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req = build_compile_request(
            repo_name="test-repo",
            correlation_id="corr-1",
            mode="full",
            origin="test",
            purpose="sdk_smoke",
        )
        payload = req.to_payload()
        assert payload["run_type"] == "context.compile"
        assert payload["params"]["repo"] == "test-repo"
        assert payload["params"]["mode"] == "full"
        assert payload["params"]["origin"] == "test"
        assert payload["params"]["purpose"] == "sdk_smoke"
        assert payload["params"]["correlation_id"] == "corr-1"

    def test_proof_dict_no_secrets(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req = build_compile_request(
            repo_name="test",
            identity_fingerprint="fp123",
        )
        proof = req.to_proof_dict()
        assert proof["repo"] == "test"
        assert proof["identity_fingerprint"] == "fp123"
        assert "token" not in str(proof).lower()
        assert "password" not in str(proof).lower()

    def test_timestamp_is_iso(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req = build_compile_request(repo_name="test")
        dt = datetime.fromisoformat(req.timestamp)
        assert dt.tzinfo is not None

    def test_deterministic_for_same_input(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req1 = build_compile_request(repo_name="x", mode="a")
        req2 = build_compile_request(repo_name="x", mode="a")
        # Same fields except timestamp
        assert req1.repo_name == req2.repo_name
        assert req1.mode == req2.mode

    def test_empty_optional_fields_omitted(self):
        from keyhole_sdk.context_lifecycle.compile import build_compile_request
        req = build_compile_request(repo_name="test")
        payload = req.to_payload()
        assert "mode" not in payload["params"]
        assert "origin" not in payload["params"]


# --------------------------------------------------------------
# Test 3: Compile Result Classification
# --------------------------------------------------------------


class TestCompileResultClassification:
    """Classify boundary responses into compile results."""

    def _make_transport_result(self, status_code=200, data=None):
        mock = MagicMock()
        mock.status_code = status_code
        mock.data = data or {}
        mock.proof = None
        return mock

    def test_success_with_digest(self):
        from keyhole_sdk.context_lifecycle.compile import _classify_compile_result, ContextCompileRequest
        req = ContextCompileRequest(repo_name="test")
        result = self._make_transport_result(200, {
            "status": "success",
            "ctxpack_digest": "abc123def456" * 4,
            "summary": "Context compiled",
        })
        r = _classify_compile_result(result, req)
        assert r.success is True
        assert r.ctxpack_digest == "abc123def456" * 4
        assert r.summary == "Context compiled"

    def test_success_digest_from_nested_data(self):
        from keyhole_sdk.context_lifecycle.compile import _classify_compile_result, ContextCompileRequest
        req = ContextCompileRequest(repo_name="test")
        result = self._make_transport_result(200, {
            "status": "ok",
            "data": {"ctxpack_digest": "nested_digest" * 3},
        })
        r = _classify_compile_result(result, req)
        assert r.success is True
        assert r.ctxpack_digest == "nested_digest" * 3

    def test_rejected_compile(self):
        from keyhole_sdk.context_lifecycle.compile import _classify_compile_result, ContextCompileRequest
        req = ContextCompileRequest(repo_name="test")
        result = self._make_transport_result(400, {
            "status": "rejected",
            "reason": "bad request",
            "error_class": "compile_rejected",
        })
        r = _classify_compile_result(result, req)
        assert r.success is False
        assert r.error_class == "compile_rejected"
        assert "bad request" in r.reason

    def test_failed_compile(self):
        from keyhole_sdk.context_lifecycle.compile import _classify_compile_result, ContextCompileRequest
        req = ContextCompileRequest(repo_name="test")
        result = self._make_transport_result(500, {"status": "failed", "message": "server down"})
        r = _classify_compile_result(result, req)
        assert r.success is False


# --------------------------------------------------------------
# Test 4: Inspect Result Classification
# --------------------------------------------------------------


class TestInspectResultClassification:
    """Classify inspect responses - section9 intelligibility."""

    def _make_transport_result(self, status_code=200, data=None):
        mock = MagicMock()
        mock.status_code = status_code
        mock.data = data or {}
        mock.proof = None
        return mock

    def test_success_inspect(self):
        from keyhole_sdk.context_lifecycle.inspect import _classify_inspect_result
        result = self._make_transport_result(200, {
            "status": "ok",
            "ctxpack_digest": "abc" * 16,
            "summary": "Test context",
            "repo": "my-repo",
            "lane": "dev",
        })
        r = _classify_inspect_result(result, "abc" * 16)
        assert r.success is True
        assert r.ctxpack_digest == "abc" * 16
        assert r.summary == "Test context"
        assert r.repo_name == "my-repo"
        assert r.lane == "dev"

    def test_failed_inspect(self):
        from keyhole_sdk.context_lifecycle.inspect import _classify_inspect_result
        result = self._make_transport_result(404, {
            "status": "not_found",
            "reason": "Digest not found",
        })
        r = _classify_inspect_result(result, "abc" * 16)
        assert r.success is False
        assert r.repair_guidance  # must have repair guidance

    def test_human_rendering(self):
        from keyhole_sdk.context_lifecycle.inspect import ContextInspectResult
        r = ContextInspectResult(
            success=True,
            ctxpack_digest="abc" * 16,
            summary="Test",
            repo_name="my-repo",
            lane="dev",
        )
        text = r.render_human()
        assert "abc" * 16 in text
        assert "my-repo" in text

    def test_failed_human_rendering(self):
        from keyhole_sdk.context_lifecycle.inspect import ContextInspectResult
        r = ContextInspectResult(
            success=False,
            ctxpack_digest="bad",
            reason="Not found",
            repair_guidance=["Try again"],
        )
        text = r.render_human()
        assert "FAILED" in text
        assert "Not found" in text


# --------------------------------------------------------------
# Test 5: Context Preflight (section6)
# --------------------------------------------------------------


class TestContextPreflight:
    """section6: Fail locally when the problem is obvious locally."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        return store

    def test_compile_passes_when_ok(self, tmp_path):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_compile(repo_dir=tmp_path)
        assert result is None

    def test_compile_fails_unauthenticated(self, tmp_path):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        pf = ContextPreflight(credential_store=self._make_cred_store(False))
        result = pf.check_compile(repo_dir=tmp_path)
        assert result is not None
        assert "authenticated" in result.reason.lower()
        assert result.repair_guidance

    def test_compile_fails_no_scaffold(self, tmp_path):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_compile(repo_dir=tmp_path)
        assert result is not None
        assert "keyhole.yaml" in result.reason

    def test_inspect_fails_empty_digest(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_inspect(digest="")
        assert result is not None
        assert "no digest" in result.reason.lower()

    def test_inspect_fails_malformed_digest(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_inspect(digest="!bad!")
        assert result is not None
        assert "malformed" in result.reason.lower()

    def test_inspect_passes_valid_digest(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_inspect(digest="a" * 64)
        assert result is None

    def test_run_context_rejects_missing(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_run_context(context="")
        assert result is not None
        assert "require explicit context" in result.reason.lower()

    def test_run_context_accepts_auto(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_run_context(context="auto")
        assert result is None

    def test_run_context_accepts_valid_digest(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_run_context(context="abcdef" * 10)
        assert result is None

    def test_run_context_rejects_malformed(self):
        from keyhole_sdk.context_lifecycle.preflight import ContextPreflight
        pf = ContextPreflight(credential_store=self._make_cred_store(True))
        result = pf.check_run_context(context="<script>bad</script>")
        assert result is not None


# --------------------------------------------------------------
# Test 6: Proof Artifacts (section15)
# --------------------------------------------------------------


class TestContextProofArtifacts:
    """section15: Proof emitted for compile, inspect, and context binding."""

    def test_compile_proof_success(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_proof
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest, ContextCompileResult
        req = ContextCompileRequest(
            repo_name="test",
            correlation_id="corr-1",
            timestamp="2026-04-13T00:00:00Z",
        )
        result = ContextCompileResult(
            success=True,
            ctxpack_digest="abc" * 16,
            repo_name="test",
            correlation_id="corr-1",
        )
        proof_dir = emit_context_proof(repo_dir=tmp_path, request=req, result=result)
        assert (proof_dir / "compile-request.json").exists()
        assert (proof_dir / "compile-response.json").exists()
        assert (proof_dir / "summary.md").exists()

    def test_compile_proof_failure(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_proof
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest, ContextCompileResult
        req = ContextCompileRequest(repo_name="test", correlation_id="fail-1")
        result = ContextCompileResult(
            success=False,
            repo_name="test",
            error_class="compile_rejected",
            reason="bad request",
            correlation_id="fail-1",
        )
        proof_dir = emit_context_proof(repo_dir=tmp_path, request=req, result=result)
        assert (proof_dir / "compile-response.json").exists()
        resp = json.loads((proof_dir / "compile-response.json").read_text())
        assert resp["success"] is False

    def test_inspect_proof(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_inspect_proof
        path = emit_inspect_proof(
            repo_dir=tmp_path,
            ctxpack_digest="abc" * 16,
            inspect_data={"success": True, "ctxpack_digest": "abc" * 16},
        )
        assert (path / "inspect-output.json").exists()

    def test_context_binding_proof(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_binding_proof
        path = emit_context_binding_proof(
            repo_dir=tmp_path,
            correlation_id="run-1",
            ctxpack_digest="abc" * 16,
            run_type="context.compile",
            shadow=False,
            auto_compiled=False,
        )
        binding_file = path / "context-binding.json"
        assert binding_file.exists()
        data = json.loads(binding_file.read_text())
        assert data["ctxpack_digest"] == "abc" * 16
        assert data["auto_compiled"] is False

    def test_auto_compiled_recorded(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_binding_proof
        path = emit_context_binding_proof(
            repo_dir=tmp_path,
            correlation_id="auto-1",
            ctxpack_digest="def" * 16,
            run_type="context.compile",
            shadow=True,
            auto_compiled=True,
        )
        data = json.loads((path / "context-binding.json").read_text())
        assert data["auto_compiled"] is True
        assert data["shadow"] is True

    def test_summary_has_next_steps(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_proof
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest, ContextCompileResult
        req = ContextCompileRequest(repo_name="test", correlation_id="c1")
        result = ContextCompileResult(
            success=True,
            ctxpack_digest="abc" * 16,
            repo_name="test",
            correlation_id="c1",
        )
        proof_dir = emit_context_proof(repo_dir=tmp_path, request=req, result=result)
        summary = (proof_dir / "summary.md").read_text()
        assert "keyhole context inspect" in summary
        assert "keyhole run" in summary

    def test_extended_debug_json(self, tmp_path):
        from keyhole_sdk.context_lifecycle.proof import emit_context_proof
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest, ContextCompileResult
        req = ContextCompileRequest(repo_name="test", correlation_id="c2")
        result = ContextCompileResult(
            success=True,
            ctxpack_digest="xx" * 16,
            repo_name="test",
            correlation_id="c2",
        )
        emit_context_proof(repo_dir=tmp_path, request=req, result=result)
        debug_path = tmp_path / "proof_bundle" / "extended" / "context" / ("xx" * 16) / "debug.json"
        assert debug_path.exists()


# --------------------------------------------------------------
# Test 7: Local Context Tracker
# --------------------------------------------------------------


class TestLocalContextTracker:
    """Track most recently compiled digest locally."""

    def test_save_and_load(self, tmp_path):
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="abc123" * 8, repo_name="test", correlation_id="c1")
        data = tracker.load()
        assert data is not None
        assert data["ctxpack_digest"] == "abc123" * 8

    def test_get_recent_digest(self, tmp_path):
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="d" * 64)
        assert tracker.get_recent_digest() == "d" * 64

    def test_load_empty(self, tmp_path):
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        assert tracker.load() is None
        assert tracker.get_recent_digest() is None

    def test_clear(self, tmp_path):
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="x" * 64)
        tracker.clear()
        assert tracker.get_recent_digest() is None

    def test_overwrites_previous(self, tmp_path):
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="a" * 64)
        tracker.save(ctxpack_digest="b" * 64)
        assert tracker.get_recent_digest() == "b" * 64


# --------------------------------------------------------------
# Test 8: Repair Guidance (section14)
# --------------------------------------------------------------


class TestContextRepairGuidance:
    """section14: Concrete next-best actions for context failures."""

    def test_auth_error(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("AuthenticationError")
        assert any("login" in g.lower() for g in guidance)

    def test_unknown_digest(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("unknown_digest")
        assert any("compile" in g.lower() for g in guidance)

    def test_stale_digest(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("stale_digest")
        assert guidance

    def test_missing_context(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("missing_context")
        assert any("compile" in g.lower() for g in guidance)

    def test_malformed_digest(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("malformed_digest")
        assert guidance

    def test_scaffold_missing(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("ScaffoldMissing")
        assert any("init vertical" in g.lower() for g in guidance)

    def test_unknown_error_fallback(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("SomethingUnknown")
        assert guidance  # never empty
        assert any("compile" in g.lower() for g in guidance)

    def test_incompatible_context(self):
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("incompatible_context")
        assert any("compile" in g.lower() for g in guidance)


# --------------------------------------------------------------
# Test 9: No-Floating-Run Rule (section11)
# --------------------------------------------------------------


class TestNoFloatingRunRule:
    """section11: Governed runs must not proceed without explicit context."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        session.is_expired = False
        store.load.return_value = session
        return store

    def test_run_without_context_rejected(self, tmp_path):
        """section11: No context -> rejected locally."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(True)
            result = run_run(
                run_type="context.compile",
                context="",  # no context
                repo_dir=str(tmp_path),
            )
        assert result.success is False
        assert result.exit_code == 4  # EXIT_INVALID_INPUT
        assert "missing_context" in str(result.data.get("error_class", ""))

    def test_run_with_explicit_context_allowed(self, tmp_path):
        """section10: Explicit digest passes preflight."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "a" * 64
        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success", "run_id": "r1"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context=digest,
                repo_dir=str(tmp_path),
            )
        assert result.success is True
        assert result.data.get("ctxpack_digest") == digest

    def test_contextless_fallback_does_not_occur(self, tmp_path):
        """section11: No hidden fallback from missing context."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(True)
            result = run_run(
                run_type="context.compile",
                context="",
                repo_dir=str(tmp_path),
            )
        # Must NOT have dispatched - no transport call
        assert result.success is False
        assert "context" in result.summary.lower()

    def test_malformed_digest_rejected_locally(self, tmp_path):
        """section6: Malformed digest fails preflight before dispatch."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(True)
            result = run_run(
                run_type="context.compile",
                context="!bad!digest!",
                repo_dir=str(tmp_path),
            )
        assert result.success is False
        assert "malformed" in result.data.get("error_class", "")


# --------------------------------------------------------------
# Test 10: --context auto Behavior (section5.4)
# --------------------------------------------------------------


class TestContextAuto:
    """section5.4: --context auto compiles, shows digest, binds."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        session.is_expired = False
        store.load.return_value = session
        return store

    def test_auto_compiles_and_binds(self, tmp_path):
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "d" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.run_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            # Mock compile result
            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=True,
                ctxpack_digest=digest,
                repo_name="test",
            )

            # Mock run transport
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success", "run_id": "r2"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context="auto",
                repo_dir=str(tmp_path),
            )

        assert result.success is True
        assert result.data.get("ctxpack_digest") == digest
        assert result.data.get("context_auto_compiled") is True

    def test_auto_compile_failure_blocks_run(self, tmp_path):
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.run_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=False,
                repo_name="test",
                error_class="compile_rejected",
                reason="bad scaffold",
            )
            MockTransport.return_value = MagicMock()

            result = run_run(
                run_type="context.compile",
                context="auto",
                repo_dir=str(tmp_path),
            )

        assert result.success is False
        assert "compile failed" in result.summary.lower()

    def test_auto_does_not_hide_digest(self, tmp_path):
        """section5.4: auto must never hide the resulting digest."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "e" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.run_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=True,
                ctxpack_digest=digest,
                repo_name="test",
            )

            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context="auto",
                repo_dir=str(tmp_path),
            )

        # The digest must be visible in the result
        assert result.data.get("ctxpack_digest") == digest


# --------------------------------------------------------------
# Test 11: CLI Context Compile Command
# --------------------------------------------------------------


class TestCLIContextCompile:
    """CLI context compile command flow."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        session.is_expired = False
        store.load.return_value = session
        return store

    def test_blocks_unauthenticated(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_compile
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(False)
            result = run_context_compile(repo_dir=str(tmp_path))
        assert result.success is False
        assert "authenticated" in result.summary.lower()

    def test_blocks_no_scaffold(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_compile
        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(True)
            result = run_context_compile(repo_dir=str(tmp_path))
        assert result.success is False
        assert "keyhole.yaml" in result.summary

    def test_success_flow(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_compile
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "f" * 64

        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.context_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.context_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=True,
                ctxpack_digest=digest,
                repo_name="test",
                summary="Context compiled",
            )
            MockTransport.return_value = MagicMock()

            result = run_context_compile(repo_dir=str(tmp_path))

        assert result.success is True
        assert result.data.get("ctxpack_digest") == digest
        assert any("inspect" in s.lower() for s in result.next_steps)

    def test_proof_emitted(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_compile
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")

        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.context_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.context_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=True,
                ctxpack_digest="g" * 64,
                repo_name="test",
            )
            MockTransport.return_value = MagicMock()

            result = run_context_compile(repo_dir=str(tmp_path))

        assert result.success is True
        assert "proof" in result.data


# --------------------------------------------------------------
# Test 12: CLI Context Inspect Command
# --------------------------------------------------------------


class TestCLIContextInspect:
    """CLI context inspect command flow."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        store.load.return_value = session
        return store

    def test_blocks_unauthenticated(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_inspect
        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(False)
            result = run_context_inspect(digest="a" * 64, repo_dir=str(tmp_path))
        assert result.success is False

    def test_blocks_no_digest(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_inspect
        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore:
            MockStore.return_value = self._make_cred_store(True)
            result = run_context_inspect(digest="", repo_dir=str(tmp_path))
        assert result.success is False
        assert "digest" in result.summary.lower()

    def test_success_flow(self, tmp_path):
        from keyhole_cli.commands.context_cmd import run_context_inspect
        digest = "b" * 64

        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.context_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.context_cmd.inspect_context") as mock_inspect:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.inspect import ContextInspectResult
            mock_inspect.return_value = ContextInspectResult(
                success=True,
                ctxpack_digest=digest,
                summary="Test context",
                repo_name="test",
            )
            MockTransport.return_value = MagicMock()

            result = run_context_inspect(digest=digest, repo_dir=str(tmp_path))

        assert result.success is True
        assert result.data.get("ctxpack_digest") == digest

    def test_uses_recent_when_no_digest(self, tmp_path):
        """If no digest, inspect uses most recently compiled."""
        from keyhole_cli.commands.context_cmd import run_context_inspect
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker

        # Save a recent digest
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="c" * 64, repo_name="test")

        with patch("keyhole_cli.commands.context_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.context_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.context_cmd.inspect_context") as mock_inspect:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.inspect import ContextInspectResult
            mock_inspect.return_value = ContextInspectResult(
                success=True,
                ctxpack_digest="c" * 64,
                summary="Recent",
            )
            MockTransport.return_value = MagicMock()

            result = run_context_inspect(digest="", repo_dir=str(tmp_path))

        assert result.success is True
        assert result.data.get("ctxpack_digest") == "c" * 64


# --------------------------------------------------------------
# Test 13: Context Binding in Run (section10/section15)
# --------------------------------------------------------------


class TestContextBindingInRun:
    """section10: Context binding preserved in results and proof."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        store.load.return_value = session
        return store

    def test_run_result_includes_digest(self, tmp_path):
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "a" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context=digest,
                repo_dir=str(tmp_path),
            )

        assert result.data.get("ctxpack_digest") == digest

    def test_accepted_result_includes_digest(self, tmp_path):
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "b" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 202
            mock_result.data = {"status": "accepted", "run_id": "r3"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context=digest,
                repo_dir=str(tmp_path),
            )

        assert result.data.get("ctxpack_digest") == digest

    def test_context_binding_proof_exists(self, tmp_path):
        """section15: context-binding.json written for context-bound runs."""
        from keyhole_sdk.context_lifecycle.proof import emit_context_binding_proof
        path = emit_context_binding_proof(
            repo_dir=tmp_path,
            correlation_id="run-test",
            ctxpack_digest="x" * 64,
            run_type="context.compile",
        )
        assert (path / "context-binding.json").exists()

    def test_digest_not_silently_replaced(self, tmp_path):
        """section10: Client does not silently replace the requested digest."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "c" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context=digest,
                repo_dir=str(tmp_path),
            )

        # Verify the request payload sent to transport contains the digest
        call_args = mock_transport.execute.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json", {})
        assert payload.get("context_ref") == digest


# --------------------------------------------------------------
# Test 14: Transport Discipline (section12)
# --------------------------------------------------------------


class TestTransportDiscipline:
    """section12: Context commands use centralized transport."""

    def test_context_compile_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation
        op = get_operation("context.compile")
        assert op is not None
        assert op.operation_class.value == "READ_ONLY"

    def test_context_inspect_registered(self):
        from keyhole_sdk.transport.operation_registry import get_operation
        op = get_operation("context.inspect")
        assert op is not None
        assert op.operation_class.value == "READ_ONLY"

    def test_run_start_still_write_idempotent(self):
        from keyhole_sdk.transport.operation_registry import get_operation
        op = get_operation("run.start")
        assert op is not None
        assert op.operation_class.value == "WRITE_IDEMPOTENT_REQUIRED"
        assert op.idempotency_required is True

    def test_compile_uses_governed_transport(self):
        """Ensure compile dispatches through GovernedTransport, not raw HTTP."""
        from keyhole_sdk.context_lifecycle.compile import compile_context
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest
        req = ContextCompileRequest(repo_name="test")
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.status_code = 200
        mock_result.data = {"status": "ok", "ctxpack_digest": "x" * 64}
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        compile_context(transport=mock_transport, request=req)

        mock_transport.execute.assert_called_once()
        call_args = mock_transport.execute.call_args
        assert call_args[0][0] == "POST"
        assert "runs/start" in call_args[0][1]

    def test_inspect_uses_governed_transport(self):
        from keyhole_sdk.context_lifecycle.inspect import inspect_context
        mock_transport = MagicMock()
        mock_result = MagicMock()
        mock_result.status_code = 200
        mock_result.data = {"status": "ok", "ctxpack_digest": "y" * 64}
        mock_result.proof = None
        mock_transport.execute.return_value = mock_result

        inspect_context(transport=mock_transport, ctxpack_digest="y" * 64)

        mock_transport.execute.assert_called_once()


# --------------------------------------------------------------
# Test 15: SDK Exports and Invariants
# --------------------------------------------------------------


class TestSDKExportsAndInvariants:
    """Verify SDK public surface includes context lifecycle."""

    def test_sdk_exports_context_lifecycle(self):
        import keyhole_sdk
        expected = [
            "ContextCompileRequest", "ContextCompileResult",
            "build_compile_request", "compile_context",
            "ContextInspectResult", "inspect_context",
            "ContextPreflight", "ContextPreflightFailure",
            "emit_context_proof", "emit_context_binding_proof",
            "map_context_repair", "validate_digest",
            "LocalContextTracker",
        ]
        for name in expected:
            assert name in keyhole_sdk.__all__, f"{name} missing from __all__"
            assert hasattr(keyhole_sdk, name), f"{name} not importable"

    def test_no_direct_memory_access(self):
        """section20: No direct canonical memory query/write APIs."""
        import keyhole_sdk.context_lifecycle as cl
        # Should not have any memory/vector/qdrant access
        for name in dir(cl):
            lower = name.lower()
            assert "qdrant" not in lower
            assert "vector_search" not in lower
            assert "memory_query" not in lower

    def test_canonical_proof_paths(self, tmp_path):
        """section15: Proof under proof_bundle/core/ and proof_bundle/extended/."""
        from keyhole_sdk.context_lifecycle.proof import emit_context_proof
        from keyhole_sdk.context_lifecycle.compile import ContextCompileRequest, ContextCompileResult
        req = ContextCompileRequest(repo_name="test", correlation_id="c1")
        result = ContextCompileResult(
            success=True, ctxpack_digest="z" * 32, repo_name="test", correlation_id="c1",
        )
        emit_context_proof(repo_dir=tmp_path, request=req, result=result)
        assert (tmp_path / "proof_bundle" / "core" / "context").exists()
        assert (tmp_path / "proof_bundle" / "extended" / "context").exists()

    def test_tracker_under_keyhole_state(self, tmp_path):
        """section15: Tracker lives under .keyhole/state/."""
        from keyhole_sdk.context_lifecycle.tracker import LocalContextTracker
        tracker = LocalContextTracker(tmp_path)
        tracker.save(ctxpack_digest="z" * 64)
        assert (tmp_path / ".keyhole" / "state" / "recent-context.json").exists()


# --------------------------------------------------------------
# Test 16: Negative Tests
# --------------------------------------------------------------


class TestNegativeTests:
    """Cover forbidden behaviors explicitly."""

    def _make_cred_store(self, authenticated=True):
        store = MagicMock()
        store.is_authenticated.return_value = authenticated
        session = MagicMock()
        session.access_token = "test-token"
        session.token_fingerprint = "fp"
        store.load.return_value = session
        return store

    def test_hidden_fallback_does_not_occur(self, tmp_path):
        """section11: No hidden fallback from missing context to contextless run."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            MockTransport.return_value = mock_transport
            result = run_run(
                run_type="context.compile",
                context="",
                repo_dir=str(tmp_path),
            )
        # Transport should NOT have been called
        mock_transport.execute.assert_not_called()
        assert result.success is False

    def test_client_does_not_replace_digest(self, tmp_path):
        """section10: Client does not silently replace the requested digest."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        original_digest = "a" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport:
            MockStore.return_value = self._make_cred_store(True)
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context=original_digest,
                repo_dir=str(tmp_path),
            )

        assert result.data.get("ctxpack_digest") == original_digest

    def test_inspect_unknown_digest_has_guidance(self):
        """section14: Unknown digest produces deterministic repair guidance."""
        from keyhole_sdk.context_lifecycle.inspect import ContextInspectResult
        r = ContextInspectResult(
            success=False,
            ctxpack_digest="unknown",
            error_class="inspect_failed",
            reason="Digest not found",
        )
        # Must have guidance
        from keyhole_sdk.context_lifecycle.repair import map_context_repair
        guidance = map_context_repair("unknown_digest")
        assert guidance
        assert any("compile" in g.lower() for g in guidance)

    def test_auto_does_not_hide_resulting_digest(self, tmp_path):
        """section5.4: --context auto must not hide resulting digest."""
        from keyhole_cli.commands.run_cmd import run_run
        (tmp_path / "keyhole.yaml").write_text("repo:\n  name: test\n")
        digest = "h" * 64

        with patch("keyhole_cli.commands.run_cmd.CredentialStore") as MockStore, \
             patch("keyhole_cli.commands.run_cmd.GovernedTransport") as MockTransport, \
             patch("keyhole_cli.commands.run_cmd.compile_context") as mock_compile:
            MockStore.return_value = self._make_cred_store(True)

            from keyhole_sdk.context_lifecycle.compile import ContextCompileResult
            mock_compile.return_value = ContextCompileResult(
                success=True, ctxpack_digest=digest, repo_name="test",
            )
            mock_transport = MagicMock()
            mock_result = MagicMock()
            mock_result.status_code = 200
            mock_result.data = {"status": "success"}
            mock_result.proof = None
            mock_transport.execute.return_value = mock_result
            MockTransport.return_value = mock_transport

            result = run_run(
                run_type="context.compile",
                context="auto",
                repo_dir=str(tmp_path),
            )

        assert result.data.get("ctxpack_digest") == digest
        assert result.data.get("context_auto_compiled") is True

    def test_no_memory_access_in_context(self):
        """section20: Context lifecycle does not expose direct memory access."""
        import keyhole_sdk.context_lifecycle as cl
        all_names = dir(cl)
        forbidden = ["qdrant", "vector_search", "memory_write", "memory_query"]
        for f in forbidden:
            assert not any(f in n.lower() for n in all_names), \
                f"Found forbidden '{f}' in context_lifecycle"
