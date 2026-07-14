"""SDK-CLIENT-21 — Surface Negotiation and Compatibility Guardrails tests.

Validates all invariants sealed by the story:

  §8   Surface class taxonomy (required / optional / transitional)
  §9   Negotiation cycle (fetch → classify → result)
  §11  Minimum local model shape
  §12  Negotiation artifact writing
  §13  Command UX / surfaces
  §14  Fail-closed on missing required surfaces
  §15  Graceful degradation on missing optional surfaces
  §16  Per-command compatibility evaluation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

# ── Make packages importable ───────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[2]
_SDK = _ROOT / "packages" / "python" / "keyhole-sdk"
_CLI = _ROOT / "packages" / "python" / "keyhole-cli"
for _p in (_SDK, _CLI):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── Imports ────────────────────────────────────────────────────────────────

from keyhole_sdk.discovery.models import (
    AuthPosture,
    CapabilitiesResult,
    CompatibilityPosture,
    ContractIdentity,
    ContextAccessContract,
    DiscoveryMetadata,
    FeatureFlags,
    TransportPosture,
)
from keyhole_sdk.negotiation import (
    COMMAND_REQUIREMENTS,
    SURFACE_TAXONOMY,
    CompatibilitySummary,
    CommandCompatibilityResult,
    CommandStatus,
    NegotiatedFeatures,
    NegotiationResult,
    NegotiationStatus,
    SurfaceClass,
    SurfaceEntry,
    classify_surfaces,
    evaluate_all_commands,
    evaluate_command,
    map_negotiation_repair,
    negotiate,
    negotiate_from_raw,
    write_negotiation_artifacts,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixture factories
# ──────────────────────────────────────────────────────────────────────────

def _make_caps(
    *,
    identity_endpoint: str = "/mcp/v1/identity",
    run_dispatch_endpoint: str = "/mcp/v1/runs/dispatch",
    operations_implemented: int = 3,
    flags: Dict[str, bool] | None = None,
    implemented_surfaces: list[str] | None = None,
    digest: str = "sha256:abc123",
) -> CapabilitiesResult:
    """Build a CapabilitiesResult with controllable knobs."""
    return CapabilitiesResult(
        contract=ContractIdentity(
            contract="ce-v5",
            operations_declared=3,
            operations_implemented=operations_implemented,
        ),
        compatibility=CompatibilityPosture(min_sdk_version="0.3.0"),
        transport=TransportPosture(transport="https"),
        auth=AuthPosture(
            auth_flow="oidc-pkce",
            identity_endpoint=identity_endpoint,
            run_dispatch_endpoint=run_dispatch_endpoint,
        ),
        features=FeatureFlags(flags=flags or {}),
        context_access=ContextAccessContract(
            implemented_surfaces=implemented_surfaces or [],
            declared_count=len(implemented_surfaces or []),
            implemented_count=len(implemented_surfaces or []),
        ),
        metadata=DiscoveryMetadata(
            generated_at="2026-04-14T00:00:00Z",
            digest=digest,
        ),
        raw={"_fixture": True},
    )


def _full_caps() -> CapabilitiesResult:
    """All surfaces present — COMPATIBLE posture."""
    return _make_caps(
        flags={
            "run_async_accept": True,
            "context_compile": True,
            "explainability": True,
            "support_bundle": True,
            "run_tail": True,
            "budget_visibility": True,
            "context_required_for_runs": True,
            "idempotency_required": False,
        },
    )


def _minimal_caps() -> CapabilitiesResult:
    """Required surfaces only — DEGRADED posture."""
    return _make_caps()


def _empty_caps() -> CapabilitiesResult:
    """No endpoints, no flags — BLOCKED posture."""
    return _make_caps(
        identity_endpoint="",
        run_dispatch_endpoint="",
        operations_implemented=0,
    )


# ──────────────────────────────────────────────────────────────────────────
# §8 — Surface taxonomy
# ──────────────────────────────────────────────────────────────────────────


class TestSurfaceTaxonomy:
    """All 10 surfaces are declared in SURFACE_TAXONOMY with correct classes."""

    def test_taxonomy_has_all_ten_surfaces(self) -> None:
        assert len(SURFACE_TAXONOMY) == 10

    def test_required_surfaces_present(self) -> None:
        assert SURFACE_TAXONOMY["authenticated_identity"][0] == SurfaceClass.REQUIRED
        assert SURFACE_TAXONOMY["run_dispatch"][0] == SurfaceClass.REQUIRED

    def test_optional_surfaces_present(self) -> None:
        optionals = {
            "run_async_accept", "context_compile", "explainability",
            "support_bundle", "run_tail", "budget_visibility",
        }
        for name in optionals:
            assert name in SURFACE_TAXONOMY, f"Missing: {name}"
            assert SURFACE_TAXONOMY[name][0] == SurfaceClass.OPTIONAL, (
                f"{name} should be OPTIONAL"
            )

    def test_transitional_surfaces_present(self) -> None:
        transitional = {"context_required_for_runs", "idempotency_required"}
        for name in transitional:
            assert name in SURFACE_TAXONOMY, f"Missing: {name}"
            assert SURFACE_TAXONOMY[name][0] == SurfaceClass.TRANSITIONAL

    def test_all_values_have_description(self) -> None:
        for name, (cls, desc) in SURFACE_TAXONOMY.items():
            assert desc, f"Surface {name!r} has empty description"

    def test_taxonomy_keys_match_negotiated_features_fields(self) -> None:
        feature_fields = set(NegotiatedFeatures.model_fields.keys())
        for name in SURFACE_TAXONOMY:
            assert name in feature_fields, (
                f"SURFACE_TAXONOMY key {name!r} has no matching NegotiatedFeatures field"
            )


# ──────────────────────────────────────────────────────────────────────────
# §11 — NegotiationResult model
# ──────────────────────────────────────────────────────────────────────────


class TestNegotiationModels:
    """NegotiatedFeatures and NegotiationResult model shape (§11)."""

    def test_negotiated_features_defaults_all_false(self) -> None:
        f = NegotiatedFeatures()
        for field in NegotiatedFeatures.model_fields:
            assert getattr(f, field) is False, f"Field {field!r} should default to False"

    def test_negotiated_features_to_dict_has_required_keys(self) -> None:
        f = NegotiatedFeatures()
        d = f.to_dict()
        for key in (
            "authenticated_identity", "run_dispatch", "run_async_accept", "context_compile",
            "context_required_for_runs", "idempotency_required",
            "explainability", "support_bundle", "run_tail", "budget_visibility",
        ):
            assert key in d, f"Missing key {key!r} in NegotiatedFeatures.to_dict()"

    def test_negotiated_features_to_dict_values_are_bool(self) -> None:
        f = NegotiatedFeatures(run_dispatch=True, explainability=False)
        d = f.to_dict()
        for v in d.values():
            assert isinstance(v, bool)

    def test_negotiation_result_defaults(self) -> None:
        r = NegotiationResult()
        assert r.server_version == ""
        assert r.surface_fingerprint == ""
        assert r.operations == []
        assert r.negotiated_at == ""
        assert isinstance(r.features, NegotiatedFeatures)
        assert isinstance(r.compatibility, CompatibilitySummary)

    def test_negotiation_result_is_compatible(self) -> None:
        r = NegotiationResult(
            compatibility=CompatibilitySummary(status=NegotiationStatus.COMPATIBLE)
        )
        assert r.is_compatible()
        assert not r.is_degraded()
        assert not r.is_blocked()

    def test_negotiation_result_is_degraded(self) -> None:
        r = NegotiationResult(
            compatibility=CompatibilitySummary(
                status=NegotiationStatus.DEGRADED,
                optional_missing=["explainability"],
            )
        )
        assert r.is_degraded()
        assert not r.is_compatible()
        assert not r.is_blocked()

    def test_negotiation_result_is_blocked(self) -> None:
        r = NegotiationResult(
            compatibility=CompatibilitySummary(
                status=NegotiationStatus.BLOCKED,
                required_missing=["authenticated_identity"],
            )
        )
        assert r.is_blocked()
        assert not r.is_compatible()
        assert not r.is_degraded()

    def test_negotiation_result_to_dict_shape(self) -> None:
        r = NegotiationResult()
        d = r.to_dict()
        for key in (
            "server_version", "surface_fingerprint", "operations",
            "features", "compatibility", "negotiated_at",
        ):
            assert key in d, f"Missing {key!r} in NegotiationResult.to_dict()"

    def test_negotiation_result_to_dict_json_serializable(self) -> None:
        r = NegotiationResult(
            server_version="ce-v5",
            features=NegotiatedFeatures(run_dispatch=True),
            compatibility=CompatibilitySummary(
                status=NegotiationStatus.COMPATIBLE,
            ),
        )
        s = json.dumps(r.to_dict())
        assert "ce-v5" in s

    def test_command_compatibility_result_to_dict(self) -> None:
        r = CommandCompatibilityResult(
            command="keyhole run",
            status=CommandStatus.ALLOWED,
        )
        d = r.to_dict()
        assert d["command"] == "keyhole run"
        assert d["status"] == "allowed"
        assert d["required_missing"] == []
        assert d["optional_missing"] == []

    def test_command_compatibility_result_blocked(self) -> None:
        r = CommandCompatibilityResult(
            command="keyhole run",
            status=CommandStatus.BLOCKED,
            required_missing=["authenticated_identity"],
            reason="Identity surface absent.",
        )
        assert r.is_blocked()
        assert not r.is_degraded()

    def test_command_compatibility_result_degraded(self) -> None:
        r = CommandCompatibilityResult(
            command="keyhole run",
            status=CommandStatus.DEGRADED,
            optional_missing=["run_async_accept"],
        )
        assert r.is_degraded()
        assert not r.is_blocked()

    def test_negotiation_status_values(self) -> None:
        assert NegotiationStatus.COMPATIBLE.value == "compatible"
        assert NegotiationStatus.DEGRADED.value == "degraded"
        assert NegotiationStatus.BLOCKED.value == "blocked"

    def test_command_status_values(self) -> None:
        assert CommandStatus.ALLOWED.value == "allowed"
        assert CommandStatus.DEGRADED.value == "degraded"
        assert CommandStatus.BLOCKED.value == "blocked"

    def test_surface_class_values(self) -> None:
        assert SurfaceClass.REQUIRED.value == "required"
        assert SurfaceClass.OPTIONAL.value == "optional"
        assert SurfaceClass.TRANSITIONAL.value == "transitional"

    def test_surface_entry_fields(self) -> None:
        e = SurfaceEntry(
            name="run_dispatch",
            surface_class=SurfaceClass.REQUIRED,
            present=True,
        )
        assert e.name == "run_dispatch"
        assert e.surface_class == SurfaceClass.REQUIRED
        assert e.present is True


# ──────────────────────────────────────────────────────────────────────────
# §8 / §11 — classify_surfaces
# ──────────────────────────────────────────────────────────────────────────


class TestClassifySurfaces:
    """classify_surfaces() maps CapabilitiesResult → (NegotiatedFeatures, entries)."""

    def test_classify_full_caps_all_true(self) -> None:
        features, entries = classify_surfaces(_full_caps())
        assert features.authenticated_identity is True
        assert features.run_dispatch is True
        assert features.context_compile is True
        assert features.explainability is True
        assert features.run_async_accept is True
        assert features.budget_visibility is True
        assert features.run_tail is True
        assert features.support_bundle is True

    def test_classify_empty_caps_all_false(self) -> None:
        features, entries = classify_surfaces(_empty_caps())
        assert features.authenticated_identity is False
        assert features.run_dispatch is False
        assert features.context_compile is False
        assert features.explainability is False

    def test_classify_minimal_caps_required_only(self) -> None:
        features, entries = classify_surfaces(_minimal_caps())
        assert features.authenticated_identity is True
        assert features.run_dispatch is True
        assert features.context_compile is False
        assert features.explainability is False

    def test_classify_entries_length(self) -> None:
        _, entries = classify_surfaces(_full_caps())
        assert len(entries) == len(SURFACE_TAXONOMY)

    def test_classify_entries_have_correct_classes(self) -> None:
        _, entries = classify_surfaces(_full_caps())
        entry_map = {e.name: e for e in entries}
        assert entry_map["authenticated_identity"].surface_class == SurfaceClass.REQUIRED
        assert entry_map["run_dispatch"].surface_class == SurfaceClass.REQUIRED
        assert entry_map["explainability"].surface_class == SurfaceClass.OPTIONAL
        assert entry_map["context_required_for_runs"].surface_class == SurfaceClass.TRANSITIONAL

    def test_classify_context_compile_from_context_access(self) -> None:
        caps = _make_caps(implemented_surfaces=["context.compile"])
        features, _ = classify_surfaces(caps)
        assert features.context_compile is True

    def test_classify_context_compile_from_flag(self) -> None:
        caps = _make_caps(flags={"context_compile": True})
        features, _ = classify_surfaces(caps)
        assert features.context_compile is True

    def test_classify_run_dispatch_from_operations_implemented(self) -> None:
        caps = _make_caps(run_dispatch_endpoint="", operations_implemented=5)
        features, _ = classify_surfaces(caps)
        assert features.run_dispatch is True

    def test_classify_identity_from_endpoint(self) -> None:
        caps = _make_caps(identity_endpoint="/api/whoami")
        features, _ = classify_surfaces(caps)
        assert features.authenticated_identity is True

    def test_classify_identity_absent_when_no_endpoint(self) -> None:
        caps = _make_caps(identity_endpoint="", run_dispatch_endpoint="", operations_implemented=0)
        features, _ = classify_surfaces(caps)
        assert features.authenticated_identity is False

    def test_classify_transitional_shows_present(self) -> None:
        caps = _make_caps(flags={"context_required_for_runs": True})
        features, entries = classify_surfaces(caps)
        assert features.context_required_for_runs is True
        m = {e.name: e for e in entries}
        assert m["context_required_for_runs"].present is True

    def test_classify_transitional_shows_absent(self) -> None:
        caps = _make_caps(flags={})
        features, entries = classify_surfaces(caps)
        m = {e.name: e for e in entries}
        assert m["idempotency_required"].present is False


# ──────────────────────────────────────────────────────────────────────────
# §9 §11 §14 §15 — negotiate()
# ──────────────────────────────────────────────────────────────────────────


class TestNegotiate:
    """negotiate() produces correct NegotiationResult posture."""

    def test_negotiate_full_caps_compatible(self) -> None:
        result = negotiate(_full_caps())
        assert result.is_compatible()

    def test_negotiate_minimal_caps_degraded(self) -> None:
        result = negotiate(_minimal_caps())
        assert result.is_degraded()

    def test_negotiate_empty_caps_blocked(self) -> None:
        result = negotiate(_empty_caps())
        assert result.is_blocked()

    def test_negotiate_blocked_has_required_missing(self) -> None:
        result = negotiate(_empty_caps())
        assert len(result.compatibility.required_missing) > 0

    def test_negotiate_degraded_has_optional_missing(self) -> None:
        result = negotiate(_minimal_caps())
        assert len(result.compatibility.optional_missing) > 0

    def test_negotiate_degraded_no_required_missing(self) -> None:
        result = negotiate(_minimal_caps())
        assert result.compatibility.required_missing == []

    def test_negotiate_compatible_no_missing(self) -> None:
        result = negotiate(_full_caps())
        assert result.compatibility.required_missing == []
        assert result.compatibility.optional_missing == []

    def test_negotiate_sets_server_version(self) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        assert result.server_version == "ce-v5"

    def test_negotiate_sets_surface_fingerprint(self) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        assert result.surface_fingerprint == "sha256:abc123"

    def test_negotiate_sets_negotiated_at(self) -> None:
        result = negotiate(_full_caps())
        assert result.negotiated_at != ""
        assert "T" in result.negotiated_at  # ISO 8601

    def test_negotiate_transitional_always_listed(self) -> None:
        result = negotiate(_full_caps())
        assert len(result.compatibility.transitional) > 0

    def test_negotiate_deterministic(self) -> None:
        caps = _minimal_caps()
        r1 = negotiate(caps)
        r2 = negotiate(caps)
        assert r1.compatibility.status == r2.compatibility.status
        assert r1.compatibility.required_missing == r2.compatibility.required_missing
        assert r1.compatibility.optional_missing == r2.compatibility.optional_missing

    def test_negotiate_blocked_only_one_missing_required(self) -> None:
        # Only identity missing
        caps = _make_caps(
            identity_endpoint="",
            run_dispatch_endpoint="/mcp/v1/runs",
            operations_implemented=1,
            flags={
                "run_async_accept": True,
                "context_compile": True,
                "explainability": True,
                "support_bundle": True,
                "run_tail": True,
                "budget_visibility": True,
            },
        )
        result = negotiate(caps)
        assert result.is_blocked()
        assert "authenticated_identity" in result.compatibility.required_missing

    def test_negotiate_operations_list(self) -> None:
        caps = _make_caps(implemented_surfaces=["context.compile", "gaps.list"])
        result = negotiate(caps)
        assert "context.compile" in result.operations
        assert "gaps.list" in result.operations


# ──────────────────────────────────────────────────────────────────────────
# negotiate_from_raw()
# ──────────────────────────────────────────────────────────────────────────


class TestNegotiateFromRaw:
    """negotiate_from_raw() accepts a dict and returns a NegotiationResult."""

    def test_negotiate_from_raw_empty_dict_does_not_raise(self) -> None:
        result = negotiate_from_raw({})
        assert isinstance(result, NegotiationResult)

    def test_negotiate_from_raw_blocked_on_empty(self) -> None:
        result = negotiate_from_raw({})
        assert result.is_blocked()

    def test_negotiate_from_raw_with_full_raw(self) -> None:
        raw = {
            "contract": {"contract": "ce-v5", "operations_implemented": 5},
            "auth": {
                "identity_endpoint": "/mcp/v1/identity",
                "run_dispatch_endpoint": "/mcp/v1/runs/dispatch",
            },
            "features": {
                "flags": {
                    "run_async_accept": True,
                    "context_compile": True,
                    "explainability": True,
                    "support_bundle": True,
                    "run_tail": True,
                    "budget_visibility": True,
                }
            },
        }
        result = negotiate_from_raw(raw)
        assert isinstance(result, NegotiationResult)
        # Should at minimum not crash

    def test_negotiate_from_raw_returns_negotiation_result_type(self) -> None:
        result = negotiate_from_raw({"contract": {"contract": "test"}})
        assert isinstance(result, NegotiationResult)

    def test_negotiate_from_live_enveloped_capabilities_shape(self) -> None:
        raw = {
            "ok": True,
            "data": {
                "contract": "mcp/v1",
                "operations_declared": 30,
                "operations_implemented": 12,
                "feature_flags": {
                    "events_replay": True,
                    "runs_cancel": True,
                },
                "operations": [
                    {
                        "name": "ingest.submit",
                        "operation_id": "ingest.submit",
                        "path": "/mcp/v1/ingest",
                        "canonical_run_type": "governance.context.create",
                        "canonical_endpoint": {
                            "method": "POST",
                            "path": "/mcp/v1/runs/start",
                        },
                        "aliases": ["repo.register"],
                    }
                ],
                "governed_worker_sdk": {
                    "preflight": {
                        "whoami": {
                            "method": "GET",
                            "path": "/mcp/v1/whoami",
                            "required": True,
                        },
                        "capabilities": {
                            "method": "GET",
                            "path": "/mcp/v1/capabilities",
                            "required": True,
                        },
                    }
                },
            },
        }

        result = negotiate_from_raw(raw)

        assert result.features.authenticated_identity is True
        assert result.features.run_dispatch is True
        assert not result.is_blocked()
        assert "authenticated_identity" not in result.compatibility.required_missing
        assert "run_dispatch" not in result.compatibility.required_missing
        assert "ingest.submit" in result.operations
        assert "governance.context.create" in result.operations
        assert "repo.register" in result.operations


# ──────────────────────────────────────────────────────────────────────────
# §16 — evaluate_command() / evaluate_all_commands()
# ──────────────────────────────────────────────────────────────────────────


class TestEvaluateCommand:
    """evaluate_command() produces correct per-command compatibility."""

    def _full_features(self) -> NegotiatedFeatures:
        return NegotiatedFeatures(
            authenticated_identity=True,
            run_dispatch=True,
            run_async_accept=True,
            context_compile=True,
            explainability=True,
            support_bundle=True,
            run_tail=True,
            budget_visibility=True,
        )

    def test_keyhole_run_allowed_on_full_features(self) -> None:
        r = evaluate_command("keyhole run", self._full_features())
        assert r.status == CommandStatus.ALLOWED
        assert not r.is_blocked()

    def test_keyhole_run_blocked_without_dispatch(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=True, run_dispatch=False)
        r = evaluate_command("keyhole run", f)
        assert r.is_blocked()
        assert "run_dispatch" in r.required_missing

    def test_keyhole_run_blocked_without_identity(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=False, run_dispatch=True)
        r = evaluate_command("keyhole run", f)
        assert r.is_blocked()
        assert "authenticated_identity" in r.required_missing

    def test_keyhole_run_degraded_without_async(self) -> None:
        f = NegotiatedFeatures(
            authenticated_identity=True,
            run_dispatch=True,
            run_async_accept=False,
        )
        r = evaluate_command("keyhole run", f)
        assert r.status == CommandStatus.DEGRADED
        assert "run_async_accept" in r.optional_missing

    def test_keyhole_whoami_allowed_with_identity(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=True)
        r = evaluate_command("keyhole whoami", f)
        assert r.status == CommandStatus.ALLOWED

    def test_keyhole_whoami_blocked_without_identity(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=False)
        r = evaluate_command("keyhole whoami", f)
        assert r.is_blocked()

    def test_keyhole_surfaces_always_allowed(self) -> None:
        r = evaluate_command("keyhole surfaces", NegotiatedFeatures())
        assert r.status == CommandStatus.ALLOWED

    def test_keyhole_doctor_always_allowed(self) -> None:
        r = evaluate_command("keyhole doctor", NegotiatedFeatures())
        assert r.status == CommandStatus.ALLOWED

    def test_keyhole_explain_run_blocked_without_explainability(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=True, explainability=False)
        r = evaluate_command("keyhole explain run", f)
        assert r.is_blocked()
        assert "explainability" in r.required_missing

    def test_keyhole_explain_run_degraded_without_bundle(self) -> None:
        f = NegotiatedFeatures(
            authenticated_identity=True,
            explainability=True,
            support_bundle=False,
        )
        r = evaluate_command("keyhole explain run", f)
        assert r.status == CommandStatus.DEGRADED

    def test_keyhole_runs_tail_blocked_without_run_tail(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=True, run_tail=False)
        r = evaluate_command("keyhole runs tail", f)
        assert r.is_blocked()
        assert "run_tail" in r.required_missing

    def test_keyhole_runs_budget_blocked_without_budget_visibility(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=True, budget_visibility=False)
        r = evaluate_command("keyhole runs budget", f)
        assert r.is_blocked()

    def test_evaluate_command_has_repair_on_blocked(self) -> None:
        f = NegotiatedFeatures(authenticated_identity=False)
        r = evaluate_command("keyhole whoami", f)
        assert r.is_blocked()
        assert len(r.repair) > 0

    def test_evaluate_command_result_has_command_name(self) -> None:
        f = self._full_features()
        r = evaluate_command("keyhole run", f)
        assert r.command == "keyhole run"

    def test_evaluate_unknown_command_safe(self) -> None:
        # Unknown commands should not raise
        r = evaluate_command("keyhole unknown-xyz", NegotiatedFeatures())
        assert isinstance(r, CommandCompatibilityResult)


class TestEvaluateAllCommands:
    """evaluate_all_commands() returns a dict with all known commands."""

    def _full_features(self) -> NegotiatedFeatures:
        return NegotiatedFeatures(
            authenticated_identity=True,
            run_dispatch=True,
            run_async_accept=True,
            context_compile=True,
            explainability=True,
            support_bundle=True,
            run_tail=True,
            budget_visibility=True,
        )

    def test_returns_dict_with_all_known_commands(self) -> None:
        results = evaluate_all_commands(NegotiatedFeatures())
        for cmd in COMMAND_REQUIREMENTS:
            assert cmd in results, f"Missing {cmd!r} in evaluate_all_commands result"

    def test_all_results_are_command_compatibility_result(self) -> None:
        results = evaluate_all_commands(self._full_features())
        for cmd, r in results.items():
            assert isinstance(r, CommandCompatibilityResult), (
                f"Expected CommandCompatibilityResult for {cmd!r}, got {type(r)}"
            )

    def test_no_blocked_on_full_features(self) -> None:
        results = evaluate_all_commands(self._full_features())
        blocked = [cmd for cmd, r in results.items() if r.is_blocked()]
        # surfaces, doctor, validate, login require nothing — everything else allowed
        assert blocked == [], f"Unexpectedly blocked: {blocked}"

    def test_all_blocked_on_empty_features(self) -> None:
        results = evaluate_all_commands(NegotiatedFeatures())
        # All commands that require authenticated_identity should be blocked
        blocked = {cmd for cmd, r in results.items() if r.is_blocked()}
        # At minimum 'keyhole whoami' needs identity
        assert "keyhole whoami" in blocked

    def test_keyhole_surfaces_not_blocked_on_empty(self) -> None:
        results = evaluate_all_commands(NegotiatedFeatures())
        assert not results["keyhole surfaces"].is_blocked()


# ──────────────────────────────────────────────────────────────────────────
# §12 — write_negotiation_artifacts
# ──────────────────────────────────────────────────────────────────────────


class TestWriteNegotiationArtifacts:
    """write_negotiation_artifacts() produces 3 files in <state_dir>/compatibility/."""

    def test_creates_compatibility_directory(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        out = write_negotiation_artifacts(tmp_path, caps, result)
        assert out.is_dir()

    def test_capabilities_raw_json_exists(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        path = tmp_path / "compatibility" / "capabilities_raw.json"
        assert path.is_file()

    def test_negotiation_result_json_exists(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        path = tmp_path / "compatibility" / "negotiation_result.json"
        assert path.is_file()

    def test_summary_md_exists(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        path = tmp_path / "compatibility" / "summary.md"
        assert path.is_file()

    def test_capabilities_raw_json_is_valid_json(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        data = json.loads((tmp_path / "compatibility" / "capabilities_raw.json").read_text())
        assert isinstance(data, dict)

    def test_negotiation_result_json_is_valid_json(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        data = json.loads((tmp_path / "compatibility" / "negotiation_result.json").read_text())
        assert "server_version" in data
        assert "compatibility" in data

    def test_summary_md_contains_status(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, result)
        text = (tmp_path / "compatibility" / "summary.md").read_text()
        assert "COMPATIBLE" in text.upper() or "DEGRADED" in text.upper()

    def test_writes_to_string_path(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        # Should accept str as well as Path
        out = write_negotiation_artifacts(str(tmp_path / "str_state"), caps, result)
        assert out.is_dir()

    def test_overwrites_existing_artifacts(self, tmp_path: Path) -> None:
        caps = _minimal_caps()
        r1 = negotiate(caps)
        write_negotiation_artifacts(tmp_path, caps, r1)
        r2 = negotiate(_full_caps())
        write_negotiation_artifacts(tmp_path, _full_caps(), r2)
        data = json.loads((tmp_path / "compatibility" / "negotiation_result.json").read_text())
        assert data["compatibility"]["status"] == "compatible"

    def test_returns_path_object(self, tmp_path: Path) -> None:
        caps = _full_caps()
        result = negotiate(caps)
        out = write_negotiation_artifacts(tmp_path, caps, result)
        assert isinstance(out, Path)


# ──────────────────────────────────────────────────────────────────────────
# map_negotiation_repair
# ──────────────────────────────────────────────────────────────────────────


class TestMapNegotiationRepair:
    """map_negotiation_repair() returns non-empty repair steps for all surfaces."""

    _ALL_CODES = [
        "authenticated_identity", "run_dispatch",
        "run_async_accept", "context_compile", "explainability",
        "support_bundle", "run_tail", "budget_visibility",
        "context_required_for_runs", "idempotency_required",
        "transport_failure", "malformed_capabilities",
        "command_blocked", "command_degraded",
    ]

    def test_all_codes_return_list(self) -> None:
        for code in self._ALL_CODES:
            steps = map_negotiation_repair(code)
            assert isinstance(steps, list), f"{code!r}: expected list"

    def test_all_codes_non_empty(self) -> None:
        for code in self._ALL_CODES:
            steps = map_negotiation_repair(code)
            assert len(steps) > 0, f"{code!r}: repair steps must not be empty"

    def test_all_steps_are_strings(self) -> None:
        for code in self._ALL_CODES:
            for step in map_negotiation_repair(code):
                assert isinstance(step, str), f"{code!r}: repair step must be str"

    def test_all_steps_non_empty_string(self) -> None:
        for code in self._ALL_CODES:
            for step in map_negotiation_repair(code):
                assert step.strip(), f"{code!r}: repair step must not be blank"

    def test_unknown_code_returns_list(self) -> None:
        steps = map_negotiation_repair("totally_unknown_xyz")
        assert isinstance(steps, list)

    def test_surface_taxonomy_keys_have_repair(self) -> None:
        for name in SURFACE_TAXONOMY:
            steps = map_negotiation_repair(name)
            assert len(steps) > 0, f"No repair for taxonomy surface {name!r}"


# ──────────────────────────────────────────────────────────────────────────
# CLI command run_surfaces()
# ──────────────────────────────────────────────────────────────────────────


class TestRunSurfaces:
    """run_surfaces() exercises the CLI command delegate."""

    def test_transport_failure_returns_runtime_unavailable(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_RUNTIME_UNAVAILABLE
        from keyhole_sdk.exceptions import TransportError

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.side_effect = TransportError("connection refused")
            result = run_surfaces(mcp_url="https://mcp.example.com")

        assert not result.success
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE

    def test_schema_error_returns_runtime_unavailable(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_RUNTIME_UNAVAILABLE
        from keyhole_sdk.exceptions import SchemaError

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.side_effect = SchemaError("bad schema")
            result = run_surfaces(mcp_url="https://mcp.example.com")

        assert not result.success
        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE

    def test_blocked_posture_returns_contract_failure(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_CONTRACT_FAILURE

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _empty_caps()
            result = run_surfaces()

        assert not result.success
        assert result.exit_code == EXIT_CONTRACT_FAILURE

    def test_degraded_posture_returns_success(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_SUCCESS

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _minimal_caps()
            result = run_surfaces()

        assert result.success
        assert result.exit_code == EXIT_SUCCESS

    def test_compatible_posture_returns_success(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_SUCCESS

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _full_caps()
            result = run_surfaces()

        assert result.success
        assert result.exit_code == EXIT_SUCCESS

    def test_artifacts_written_when_state_dir_given(self, tmp_path: Path) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _minimal_caps()
            run_surfaces(state_dir=str(tmp_path))

        assert (tmp_path / "compatibility" / "negotiation_result.json").is_file()

    def test_artifacts_not_required_without_state_dir(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _full_caps()
            # No state_dir — should not raise
            result = run_surfaces()

        assert result is not None

    def test_result_data_has_compatibility_key(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _full_caps()
            result = run_surfaces()

        assert "compatibility" in result.data

    def test_unexpected_exception_returns_runtime_unavailable(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces
        from keyhole_cli.result import EXIT_RUNTIME_UNAVAILABLE

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.side_effect = RuntimeError("unexpected")
            result = run_surfaces()

        assert result.exit_code == EXIT_RUNTIME_UNAVAILABLE

    def test_next_steps_non_empty_on_blocked(self) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces

        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _empty_caps()
            result = run_surfaces()

        assert len(result.next_steps) > 0

    def test_state_dir_from_keyhole_home(self, tmp_path: Path) -> None:
        from keyhole_cli.commands.surfaces_cmd import run_surfaces

        home = tmp_path / "kh_home"
        home.mkdir()
        with patch(
            "keyhole_cli.commands.surfaces_cmd.CapabilitiesClient"
        ) as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.fetch.return_value = _full_caps()
            run_surfaces(keyhole_home=str(home))

        state = home / "state" / "compatibility"
        assert state.is_dir()


# ──────────────────────────────────────────────────────────────────────────
# §11 — Public API surface (SDK __init__.py)
# ──────────────────────────────────────────────────────────────────────────


class TestPublicAPISurface21:
    """All SDK-CLIENT-21 symbols must be in keyhole_sdk.__all__."""

    _EXPECTED: list[str] = [
        "CompatibilitySummary",
        "CommandCompatibilityResult",
        "CommandStatus",
        "NegotiatedFeatures",
        "NegotiationResult",
        "NegotiationStatus",
        "SurfaceClass",
        "SurfaceEntry",
        "SURFACE_TAXONOMY",
        "COMMAND_REQUIREMENTS",
        "classify_surfaces",
        "evaluate_command",
        "evaluate_all_commands",
        "negotiate",
        "negotiate_from_raw",
        "write_negotiation_artifacts",
        "map_negotiation_repair",
    ]

    def test_all_symbols_in_sdk_all(self) -> None:
        import keyhole_sdk
        for sym in self._EXPECTED:
            assert sym in keyhole_sdk.__all__, f"{sym!r} missing from keyhole_sdk.__all__"

    def test_all_symbols_importable_from_sdk(self) -> None:
        import keyhole_sdk
        for sym in self._EXPECTED:
            assert hasattr(keyhole_sdk, sym), f"{sym!r} not accessible on keyhole_sdk"

    def test_negotiate_callable(self) -> None:
        import keyhole_sdk
        assert callable(keyhole_sdk.negotiate)

    def test_negotiate_from_raw_callable(self) -> None:
        import keyhole_sdk
        assert callable(keyhole_sdk.negotiate_from_raw)

    def test_surface_taxonomy_is_dict(self) -> None:
        import keyhole_sdk
        assert isinstance(keyhole_sdk.SURFACE_TAXONOMY, dict)

    def test_command_requirements_is_dict(self) -> None:
        import keyhole_sdk
        assert isinstance(keyhole_sdk.COMMAND_REQUIREMENTS, dict)

    def test_negotiation_result_importable(self) -> None:
        from keyhole_sdk import NegotiationResult as NR
        assert NR is NegotiationResult

    def test_negotiation_status_importable(self) -> None:
        from keyhole_sdk import NegotiationStatus as NS
        assert NS is NegotiationStatus


# ──────────────────────────────────────────────────────────────────────────
# §7.1 §7.3 — Determinism and no silent assumption
# ──────────────────────────────────────────────────────────────────────────


class TestDeterminism21:
    """Same input always produces same negotiation output."""

    def test_same_full_caps_same_result(self) -> None:
        r1 = negotiate(_full_caps())
        r2 = negotiate(_full_caps())
        # negotiated_at is a live timestamp — compare structural content only
        d1 = {k: v for k, v in r1.to_dict().items() if k != "negotiated_at"}
        d2 = {k: v for k, v in r2.to_dict().items() if k != "negotiated_at"}
        assert d1 == d2

    def test_same_empty_caps_same_result(self) -> None:
        r1 = negotiate(_empty_caps())
        r2 = negotiate(_empty_caps())
        assert r1.compatibility.status == r2.compatibility.status
        assert r1.compatibility.required_missing == r2.compatibility.required_missing

    def test_classify_surfaces_deterministic(self) -> None:
        caps = _minimal_caps()
        f1, e1 = classify_surfaces(caps)
        f2, e2 = classify_surfaces(caps)
        assert f1.to_dict() == f2.to_dict()
        assert [e.name for e in e1] == [e.name for e in e2]

    def test_evaluate_all_commands_deterministic(self) -> None:
        features = NegotiatedFeatures(authenticated_identity=True, run_dispatch=True)
        r1 = evaluate_all_commands(features)
        r2 = evaluate_all_commands(features)
        assert set(r1.keys()) == set(r2.keys())
        for cmd in r1:
            assert r1[cmd].status == r2[cmd].status


class TestNoSilentAssumption:
    """§7.3 — absence is explicit, not inferred."""

    def test_all_features_default_false(self) -> None:
        f = NegotiatedFeatures()
        for field in NegotiatedFeatures.model_fields:
            assert getattr(f, field) is False

    def test_absent_flags_stay_false(self) -> None:
        caps = _make_caps(flags={})  # no feature flags declared
        features, _ = classify_surfaces(caps)
        assert features.context_compile is False
        assert features.explainability is False
        assert features.run_tail is False
        assert features.budget_visibility is False

    def test_negotiate_result_features_default_false_on_empty(self) -> None:
        result = negotiate(_empty_caps())
        assert result.features.run_async_accept is False
        assert result.features.context_compile is False
        assert result.features.explainability is False

    def test_negotiate_from_raw_empty_no_feature_assumed(self) -> None:
        result = negotiate_from_raw({})
        assert result.features.authenticated_identity is False
        assert result.features.run_dispatch is False
