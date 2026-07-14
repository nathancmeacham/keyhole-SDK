"""Run status retrieval — SDK-CLIENT-17 §5.2/§10.

Retrieves current run state from the boundary via GovernedTransport.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from keyhole_sdk.run_lifecycle.models import (
    RunStatus,
    RunStatusResult,
    classify_status,
)


def fetch_run_status(
    *,
    transport: Any,  # GovernedTransport
    run_id: str,
    repo_name: str = "",
) -> RunStatusResult:
    """Retrieve the current state of a governed run.

    §10: Safe for repeated polling, uses READ_ONLY transport class.
    """
    try:
        result = transport.execute(
            "POST",
            "/mcp/v1/runs/start",
            operation_name="run.status",
            json={
                "run_type": "run.status",
                "params": {"run_id": run_id},
            },
        )
    except Exception as exc:
        return _handle_status_exception(exc, run_id)

    return _classify_status_result(result, run_id, repo_name)


def _classify_status_result(
    result: Any,
    run_id: str,
    repo_name: str,
) -> RunStatusResult:
    """Classify the boundary response into a RunStatusResult."""
    data = result.data if hasattr(result, "data") else {}
    status_code = result.status_code if hasattr(result, "status_code") else 0

    if status_code >= 400:
        from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair
        return RunStatusResult(
            success=False,
            run_id=run_id,
            status=RunStatus.UNKNOWN,
            error_class=data.get("error_class", "status_retrieval_failed"),
            reason=data.get("reason", data.get("message", f"HTTP {status_code}")),
            repair_guidance=map_run_lifecycle_repair("status_retrieval_failed"),
            response_data=data,
        )

    nested = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    identity_refs = _safe_dict(nested.get("identity_refs"))
    receipt = _safe_dict(nested.get("receipt"))
    run_info = _safe_dict(nested.get("run"))
    request_info = _safe_dict(nested.get("request"))

    product_error = _product_error(data, nested)
    if product_error is not None:
        from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair

        code = _safe_str(product_error.get("code")) or "PRODUCT_ENVELOPE_INCOMPLETE"
        reason = _safe_str(product_error.get("message")) or "Product envelope did not resolve."
        return RunStatusResult(
            success=False,
            run_id=run_id,
            status=RunStatus.UNKNOWN,
            error_class=code,
            reason=reason,
            repair_guidance=map_run_lifecycle_repair("status_retrieval_failed"),
            http_status_code=status_code,
            response_data=data,
        )

    raw_status = (
        _safe_str(data.get("status"))
        or _safe_str(data.get("state"))
        or _safe_str(data.get("run_status"))
        or _safe_str(nested.get("status"))
        or _safe_str(nested.get("state"))
        or _safe_str(nested.get("run_status"))
        or _safe_str(run_info.get("status"))
        or _safe_str(receipt.get("status"))
    )
    classified = classify_status(raw_status)

    canonical_run_id = (
        _safe_str(identity_refs.get("run_id"))
        or _safe_str(receipt.get("run_id"))
        or _safe_str(run_info.get("run_id"))
        or _safe_str(data.get("run_id"))
        or run_id
    )
    canonical_request_id = (
        _safe_str(identity_refs.get("request_id"))
        or _safe_str(receipt.get("request_id"))
        or _safe_str(nested.get("request_id"))
        or _safe_str(data.get("request_id"))
    )
    correlation_id = (
        _safe_str(identity_refs.get("correlation_id"))
        or _safe_str(receipt.get("correlation_id"))
        or _safe_str(nested.get("correlation_id"))
        or _safe_str(data.get("correlation_id"))
    )
    terminal_summary = data.get("terminal_summary")
    if terminal_summary is None:
        terminal_summary = nested.get("result")
    if terminal_summary is None and nested:
        terminal_summary = nested

    return RunStatusResult(
        success=True,
        run_id=canonical_run_id,
        request_id=canonical_request_id,
        correlation_id=correlation_id,
        status=classified,
        run_type=_safe_str(data.get("run_type")) or _safe_str(nested.get("run_type")) or _safe_str(request_info.get("run_type")),
        repo_name=data.get("repo", nested.get("repo", repo_name)),
        shadow=data.get("shadow", nested.get("shadow", False)),
        ctxpack_digest=data.get("ctxpack_digest", nested.get("ctxpack_digest", "")),
        last_updated=data.get("updated_at", data.get("last_updated", "")),
        summary=data.get("summary", nested.get("summary", "")),
        terminal_summary=terminal_summary,
        resolved=bool(nested.get("resolved") or identity_refs or receipt),
        server_backed=bool(nested.get("server_backed") or identity_refs or receipt),
        http_status_code=status_code,
        response_data=_flatten_product_status_data(data, nested, canonical_run_id, canonical_request_id, correlation_id),
    )


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _product_error(data: Dict[str, Any], nested: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if data.get("ok") is False:
        return _safe_dict(data.get("error")) or {
            "code": "PRODUCT_ENVELOPE_INCOMPLETE",
            "message": "Product operation returned ok=false.",
        }
    if nested.get("ok") is False:
        return _safe_dict(nested.get("error")) or {
            "code": "PRODUCT_ENVELOPE_INCOMPLETE",
            "message": "Product operation data returned ok=false.",
        }
    return None


def _flatten_product_status_data(
    data: Dict[str, Any],
    nested: Dict[str, Any],
    run_id: str,
    request_id: str,
    correlation_id: str,
) -> Dict[str, Any]:
    """Expose product-envelope fields at the boundary while preserving raw data."""
    if not nested:
        return data

    flattened = dict(nested)
    flattened.setdefault("run_id", run_id)
    if request_id:
        flattened.setdefault("request_id", request_id)
    if correlation_id:
        flattened.setdefault("correlation_id", correlation_id)
    flattened["_raw_envelope"] = data
    return flattened


def _handle_status_exception(
    exc: Exception,
    run_id: str,
) -> RunStatusResult:
    """Convert transport exceptions into RunStatusResult."""
    from keyhole_sdk.run_lifecycle.repair import map_run_lifecycle_repair

    error_class = type(exc).__name__
    return RunStatusResult(
        success=False,
        run_id=run_id,
        error_class=error_class,
        reason=str(exc),
        repair_guidance=map_run_lifecycle_repair(error_class),
    )
