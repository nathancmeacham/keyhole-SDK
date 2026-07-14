from __future__ import annotations

from typing import Any, Dict, List


class FakeResponse:
    def __init__(self, status_code: int, data: Dict[str, Any]) -> None:
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self) -> Dict[str, Any]:
        return self._data


class FakeBoundarySession:
    def __init__(
        self,
        *,
        missing_operation: str = "",
        capability_shape: str = "legacy",
        gap_id: str = "gap_fake_c02_123",
        story_id: str = "CE-V5-S51-C02",
        repo_name: str = "my-first-app",
        capability_id: str = "my-first-app.greet.user.v1",
    ) -> None:
        self.missing_operation = missing_operation
        self.capability_shape = capability_shape
        self.gap_id = gap_id
        self.story_id = story_id
        self.repo_name = repo_name
        self.capability_id = capability_id
        self.calls: List[Dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, **kwargs})
        if "/mcp/v1/runs/" in url:
            if self.capability_shape == "async_claim":
                return FakeResponse(200, {
                    "ok": True,
                    "data": {
                        "run_id": "run_fake_claim_123",
                        "status": "completed",
                        "is_terminal": True,
                        "result": {
                            "claim_id": "claim_fake_123",
                            "claim_ref": "claim_ref_fake_123",
                        },
                    },
                    "error": None,
                })
            return FakeResponse(200, {
                "ok": True,
                "data": {
                    "run_id": "run_fake_async_123",
                    "status": "completed",
                    "is_terminal": True,
                    "result": {
                        "declaration_id": "reg_fake_123",
                        "governance_context_id": "gctx_fake_reg_123",
                    },
                },
                "error": None,
            })
        if self.capability_shape in {
            "live_envelope",
            "async_accept",
            "async_claim",
            "claim_reject",
            "no_gap_discovery",
            "multiple_gaps",
            "storyless_gap",
            "story_filter_error",
            "stale_gap",
            "canonical_status",
        }:
            logical_operation_map = {
                "gap_claim": {
                    "surface": "runs.start",
                    "run_type": "gaps.claim",
                },
                "gap_discovery": {
                    "kind": "workflow",
                    "surface": "runs.start",
                    "path": "/mcp/v1/runs/start",
                    "method": "POST",
                    "start_with_run_type": "gaps.list",
                },
                "repo.register": {
                    "surface": "runs.start",
                    "run_type": "governance.context.create",
                },
                "context.compile": {
                    "surface": "runs.start",
                    "run_type": "context.compile",
                },
                "governed.realize": {
                    "surface": "runs.start",
                    "run_type": "governed.realize",
                },
            }
            if self.missing_operation == "gaps.claim":
                logical_operation_map.pop("gap_claim", None)
            if self.capability_shape == "no_gap_discovery":
                logical_operation_map.pop("gap_discovery", None)
            logical_operation_map.pop(self.missing_operation, None)
            required_run_types = [
                "gaps.claim",
                "governance.context.create",
                "context.compile",
                "governed.realize",
            ]
            if self.missing_operation == "gaps.claim":
                required_run_types.remove("gaps.claim")
            return FakeResponse(200, {
                "ok": True,
                "data": {
                    "operations": [],
                    "governed_worker_sdk": {
                        "repo_governance": {
                            "requires_active_claim": True,
                            "canonical_run_type": "governance.context.create",
                            "gap_prerequisite": {
                                "required": True,
                                "canonical_discovery_run_type": "gaps.list",
                            },
                        },
                        "gap_claim": {
                            "canonical_run_type": "gaps.claim",
                            "gap_id_resolution": {} if self.capability_shape == "no_gap_discovery" else {
                                "start_here_run_type": "gaps.list",
                            },
                        },
                        "logical_operation_map": logical_operation_map,
                        "required_run_types": required_run_types,
                    },
                },
            })
        if self.capability_shape == "run_types":
            run_types = [
                "gaps.claim",
                "governance.context.create",
                "context.compile",
                "governed.realize",
            ]
            blocked = {
                "repo.register": "governance.context.create",
                "context.compile": "context.compile",
                "governed.realize": "governed.realize",
            }.get(self.missing_operation)
            if blocked:
                run_types.remove(blocked)
            return FakeResponse(200, {
                "ok": True,
                "data": {
                    "operations": [
                        {
                            "operation_id": "runs.start",
                            "path": "/mcp/v1/runs/start",
                            "method": "POST",
                            "run_types": run_types,
                        }
                    ]
                },
            })
        operations = {
            "repo.register": {"path": "/mcp/v1/repos/register", "method": "POST"},
            "context.compile": {"path": "/mcp/v1/runs/start", "method": "POST"},
            "governed.realize": {"path": "/realize", "method": "POST"},
        }
        operations.pop(self.missing_operation, None)
        return FakeResponse(200, {"operations": operations})

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/mcp/v1/repos/register"):
            auth = kwargs.get("headers", {}).get("Authorization", "")
            if not auth.startswith("Bearer "):
                return FakeResponse(401, {"reason": "missing bearer token"})
            return FakeResponse(
                200,
                {
                    "registration_id": "reg_fake_123",
                    "repo_id": "repo_fake_123",
                    "status": "success",
                },
            )
        if url.endswith("/mcp/v1/runs/start"):
            payload = kwargs.get("json", {})
            if payload.get("run_type") == "gaps.status":
                if self.capability_shape == "canonical_status":
                    return FakeResponse(200, {
                        "ok": True,
                        "data": {
                            "canonical": {
                                "current_canonical_digest": "sha256:canonical_digest_fake",
                            },
                        },
                    })
                return FakeResponse(400, {"reason": "unsupported run_type"})
            if payload.get("run_type") == "gaps.list":
                params = payload.get("params", {})
                if self.capability_shape == "storyless_gap" and params.get("story_id"):
                    return FakeResponse(200, {"ok": True, "result": {"gaps": []}})
                if self.capability_shape == "story_filter_error" and params.get("story_id"):
                    return FakeResponse(200, {
                        "ok": False,
                        "error": {
                            "code": "NEON_QUERY_FAILED",
                            "message": "Binding query failed unexpectedly.",
                        },
                    })
                gaps = [
                    {
                        "gap_id": self.gap_id,
                        "status": "STALE" if self.capability_shape == "stale_gap" else "OPEN",
                        "claimable": False if self.capability_shape == "stale_gap" else True,
                        "blocked": True if self.capability_shape == "stale_gap" else False,
                        "blocked_reasons": [
                            {
                                "code": "STATUS_NOT_CLAIMABLE",
                                "message": "Gap status 'STALE' does not permit claiming.",
                            }
                        ] if self.capability_shape == "stale_gap" else [],
                        "story_id": None if self.capability_shape == "storyless_gap" else self.story_id,
                        "repo": self.repo_name,
                        "capability_id": self.capability_id,
                        "fingerprint_version": "sdk-v1",
                    }
                ]
                if self.capability_shape == "multiple_gaps":
                    gaps.append({
                        "gap_id": "gap_fake_second_candidate",
                        "status": "OPEN",
                        "story_id": self.story_id,
                        "repo": self.repo_name,
                        "capability_id": self.capability_id,
                        "fingerprint_version": "sdk-v1",
                    })
                return FakeResponse(200, {
                    "ok": True,
                    "result": {
                        "gaps": gaps
                    },
                })
            if payload.get("run_type") == "gaps.claim":
                if self.capability_shape == "claim_reject":
                    return FakeResponse(200, {
                        "ok": False,
                        "error": {
                            "code": "CLAIM_REJECTED",
                            "message": "claim rejected",
                        },
                    })
                if self.capability_shape == "async_claim":
                    return FakeResponse(202, {
                        "ok": True,
                        "data": {
                            "run_id": "run_fake_claim_123",
                            "status": "accepted",
                            "poll_url": "/mcp/v1/runs/run_fake_claim_123",
                        },
                        "error": None,
                    })
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "result": {
                            "claim_id": "claim_fake_123",
                            "claim_ref": "claim_ref_fake_123",
                        },
                    },
                )
            if self.capability_shape == "async_accept":
                return FakeResponse(
                    202,
                    {
                        "ok": True,
                        "data": {
                            "run_id": "run_fake_async_123",
                            "status": "accepted",
                            "poll_url": "/mcp/v1/runs/run_fake_async_123",
                            "message": f"Run {payload.get('run_type')} accepted for background execution.",
                        },
                        "error": None,
                    },
                )
            if payload.get("run_type") == "governance.context.create":
                params = payload.get("params", {})
                if self.capability_shape != "run_types" and not (params.get("claim_id") or params.get("claim_ref")):
                    return FakeResponse(200, {
                        "ok": False,
                        "error": {
                            "code": "CLAIM_NOT_FOUND",
                            "message": "No active claim found for this gap_id.",
                        },
                    })
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "result": {
                            "declaration_id": "reg_fake_123",
                            "governance_context_id": "gctx_fake_reg_123",
                        },
                    },
                )
            if payload.get("run_type") == "governed.realize":
                params = payload.get("params", {})
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "result": {
                            "digest": params["candidate_digest"],
                            "status": "ACCEPT",
                            "message": "Digest realized successfully.",
                            "realized_at": "2026-06-09T00:00:00+00:00",
                            "governed": True,
                            "event_spine_evidence": True,
                            "governance_verdict": "ACCEPT",
                            "drift_state": "clean",
                            "governance_context_id": params["governance_context_id"],
                            "mcp_event_id": "evt_fake_123",
                            "proof_id": "proof_fake_123",
                            "receipt_id": "receipt_fake_123",
                        },
                    },
                )
            if payload.get("run_type") != "context.compile":
                return FakeResponse(400, {"reason": "unsupported run_type"})
            return FakeResponse(
                200,
                {
                    "status": "success",
                    "result": {
                        "governance_context_id": "gctx_fake_123",
                        "ctxpack_digest": "c" * 64,
                    },
                },
            )
        return FakeResponse(404, {"reason": "unknown path"})

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        if url.endswith("/realize"):
            payload = kwargs.get("json", {})
            if not payload.get("require_governed"):
                return FakeResponse(400, {"reason": "require_governed missing"})
            return FakeResponse(
                200,
                {
                    "digest": payload["candidate_digest"],
                    "status": "ACCEPT",
                    "message": "Digest realized successfully.",
                    "realized_at": "2026-06-09T00:00:00+00:00",
                    "governed": True,
                    "event_spine_evidence": True,
                    "governance_verdict": "ACCEPT",
                    "drift_state": "clean",
                    "governance_context_id": payload["governance_context_id"],
                    "mcp_event_id": "evt_fake_123",
                    "proof_id": "proof_fake_123",
                    "receipt_id": "receipt_fake_123",
                },
            )
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        pass
