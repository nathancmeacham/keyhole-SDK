from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

import keyhole_sdk
from keyhole_cli.cli import app
from keyhole_sdk import KeyholeConfig


ROOT = Path(__file__).resolve().parents[1]


def test_public_sdk_top_level_surface_is_client_side() -> None:
    assert keyhole_sdk.KeyholeClient
    assert keyhole_sdk.GovernanceReceipt
    assert keyhole_sdk.run_validation
    assert "GovernanceProofRunner" not in keyhole_sdk.__all__
    assert "MEMORY_BOUNDARY_REJECTION_MESSAGE" not in keyhole_sdk.__all__


def test_default_config_has_no_private_server() -> None:
    config = KeyholeConfig()
    assert config.base_url == ""


def test_public_cli_surface_is_intentional() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output
    for expected in ["version", "doctor", "validate", "login", "repo", "context", "run", "governed"]:
        assert expected in output
    for hidden in ["mcp-proxy", "workspace", "memory", "connections"]:
        assert hidden not in output


def test_login_help_is_public() -> None:
    result = CliRunner().invoke(app, ["login", "--help"])
    assert result.exit_code == 0
    assert "--flow" in result.output
    assert "--device" in result.output
    assert "--force" in result.output


def test_login_device_force_syntax_parses(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("KEYHOLE_AUTH_SERVER", "https://auth.example.test")

    def fake_run_login(**kwargs):
        captured.update(kwargs)
        from keyhole_cli.result import CommandResult

        return CommandResult(command="login", success=True, summary="stubbed")

    monkeypatch.setattr("keyhole_cli.cli.run_login", fake_run_login)
    result = CliRunner().invoke(app, ["login", "--flow", "device", "--force"])
    assert result.exit_code == 0
    assert captured["flow"] == "device"
    assert captured["force"] is True
    assert captured["auth_server_url"] == "https://auth.example.test"
    assert captured["_flow_explicit"] is True


def test_login_device_alias_parses(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("KEYHOLE_AUTH_SERVER", "https://auth.example.test")

    def fake_run_login(**kwargs):
        captured.update(kwargs)
        from keyhole_cli.result import CommandResult

        return CommandResult(command="login", success=True, summary="stubbed")

    monkeypatch.setattr("keyhole_cli.cli.run_login", fake_run_login)
    result = CliRunner().invoke(app, ["login", "--device", "--force"])
    assert result.exit_code == 0
    assert captured["flow"] == "device"
    assert captured["force"] is True
    assert captured["auth_server_url"] == "https://auth.example.test"
    assert captured["_flow_explicit"] is True


def test_login_device_force_requires_auth_server(monkeypatch) -> None:
    monkeypatch.delenv("KEYHOLE_AUTH_SERVER", raising=False)
    result = CliRunner().invoke(app, ["login", "--flow", "device", "--force"])
    assert result.exit_code != 0
    assert "KEYHOLE_AUTH_SERVER is required" in result.output
    assert "--auth-server-url" in result.output
    assert "Traceback" not in result.output
    assert "MissingSchema" not in result.output


def test_login_device_alias_requires_auth_server(monkeypatch) -> None:
    monkeypatch.delenv("KEYHOLE_AUTH_SERVER", raising=False)
    result = CliRunner().invoke(app, ["login", "--device", "--force"])
    assert result.exit_code != 0
    assert "KEYHOLE_AUTH_SERVER is required" in result.output
    assert "--auth-server-url" in result.output
    assert "Traceback" not in result.output
    assert "MissingSchema" not in result.output


def test_no_live_governed_flow_is_available() -> None:
    result = CliRunner().invoke(
        app,
        ["governed", "run", "--repo-dir", str(ROOT / "my-first-app"), "--no-live", "--json"],
    )
    assert result.exit_code == 0
    assert "would_mutate_mcp" in result.output


def test_live_governed_flow_fails_closed_without_token_or_stored_credentials(monkeypatch) -> None:
    monkeypatch.delenv("KEYHOLE_MCP_TOKEN", raising=False)
    monkeypatch.setenv("KEYHOLE_HOME", str(Path("C:/tmp") / f"keyhole-test-home-{uuid4().hex}"))
    result = CliRunner().invoke(app, ["governed", "run", "--repo-dir", str(ROOT / "my-first-app"), "--json"])
    assert result.exit_code != 0
    assert "no usable device-login credential" in result.output
    assert "keyhole login --flow device --force" in result.output
