"""CLI adapters for the CE-V5-S51-C02 governed first-app demo."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from keyhole_cli.result import CommandResult, EXIT_FAILURE, EXIT_SUCCESS
from keyhole_sdk.auth_bootstrap.token_refresh import get_fresh_token
from keyhole_sdk.config import DEFAULT_BASE_URL
from keyhole_sdk.governed_demo import GovernedDemoError, GovernedFirstAppClient


def is_first_app_repo(path: str | Path) -> bool:
    repo = Path(path).resolve()
    return (
        repo.name == "my-first-app"
        and (repo / "keyhole.yaml").exists()
        and (repo / "governance_contract.yaml").exists()
    )


def run_governed_demo_register(
    *,
    repo_path: str = "my-first-app",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        result = client.register_repo(repo_path)
        return CommandResult(
            command="keyhole repo register",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed demo repo registered with MCP boundary.",
            data=_public_data(result),
        )
    except GovernedDemoError as exc:
        return _failure("keyhole repo register", exc)


def run_governed_demo_context_compile(
    *,
    repo_dir: str = "my-first-app",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        result = client.compile_context(repo_dir)
        return CommandResult(
            command="keyhole context compile",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed demo context compiled with MCP boundary.",
            data=_public_data(result),
            next_steps=[
                "For public launch, use: keyhole governed run --repo-dir examples/second-governed-app --json",
                "For legacy first-app diagnostics, use: keyhole run --context auto --repo-dir my-first-app --json",
            ],
        )
    except GovernedDemoError as exc:
        return _failure("keyhole context compile", exc)


def run_governed_demo_run(
    *,
    repo_dir: str = "my-first-app",
    mcp_url: str = DEFAULT_BASE_URL,
    runtime_url: str = "",
) -> CommandResult:
    try:
        client = _client(mcp_url=mcp_url, runtime_url=runtime_url)
        receipt = client.run_governed_realization(repo_dir)
        data = receipt.model_dump(mode="json")
        return CommandResult(
            command="keyhole run --context auto",
            success=True,
            exit_code=EXIT_SUCCESS,
            summary="Governed demo realization accepted by runtime bridge.",
            data=data,
        )
    except GovernedDemoError as exc:
        return _failure("keyhole run --context auto", exc)


def _client(*, mcp_url: str, runtime_url: str) -> GovernedFirstAppClient:
    token = os.environ.get("KEYHOLE_MCP_TOKEN", "")
    if not token:
        try:
            token = get_fresh_token()
        except Exception as exc:
            raise GovernedDemoError(
                "KEYHOLE_MCP_TOKEN is not set and no usable device-login "
                f"credential is available: {exc}"
            ) from exc
    return GovernedFirstAppClient(
        mcp_url=mcp_url,
        token=token,
        runtime_url=os.environ.get("KEYHOLE_RUNTIME_URL", runtime_url),
    )


def _public_data(data: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(data)
    public.pop("upstream", None)
    return public


def _failure(command: str, exc: Exception) -> CommandResult:
    return CommandResult(
        command=command,
        success=False,
        exit_code=EXIT_FAILURE,
        summary=str(exc),
        data={"error_class": type(exc).__name__, "is_local": False},
        next_steps=[
            "Set KEYHOLE_MCP_URL and KEYHOLE_MCP_TOKEN for governed mode.",
            "Check GET /mcp/v1/capabilities for required operations.",
        ],
    )
