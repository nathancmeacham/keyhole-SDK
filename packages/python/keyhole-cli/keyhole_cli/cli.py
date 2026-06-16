from __future__ import annotations

import json
import os
from importlib.metadata import PackageNotFoundError, version as package_version

import typer

from keyhole_cli.commands.context_cmd import run_context_compile, run_context_inspect
from keyhole_cli.commands.governed_flow_cmd import (
    run_governed_flow,
    run_governed_receipt,
    run_governed_resume,
    run_governed_status,
)
from keyhole_cli.commands.login import run_login
from keyhole_cli.commands.repo_register_cmd import run_repo_register
from keyhole_cli.commands.run_cmd import run_run
from keyhole_cli.commands.validate_cmd import run_validate
from keyhole_cli.result import CommandResult, EXIT_INVALID_INPUT, emit
from keyhole_sdk.config import DEFAULT_AUTH_SERVER, DEFAULT_BASE_URL, DEFAULT_REALM


app = typer.Typer(
    help="Public CLI for validating and running Keyhole-governed SDK projects.",
    no_args_is_help=True,
)
repo_app = typer.Typer(help="Repository registration commands.", no_args_is_help=True)
context_app = typer.Typer(help="Governed context commands.", no_args_is_help=True)
governed_app = typer.Typer(help="End-to-end governed repository flow.", no_args_is_help=True)

app.add_typer(repo_app, name="repo")
app.add_typer(context_app, name="context")
app.add_typer(governed_app, name="governed")


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "unknown"


def _configured_mcp_url(value: str = "") -> str:
    return value or os.environ.get("KEYHOLE_MCP_URL", "")


@app.command("version")
def version(use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output.")) -> None:
    """Print installed package versions."""
    data = {
        "cli_version": _package_version("keyhole-cli"),
        "sdk_version": _package_version("keyhole-sdk"),
    }
    if use_json:
        typer.echo(json.dumps({"command": "version", "success": True, **data}, indent=2))
        return
    typer.echo(f"keyhole-cli {data['cli_version']}")
    typer.echo(f"keyhole-sdk {data['sdk_version']}")


@app.command("doctor")
def doctor(use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output.")) -> None:
    """Check local public SDK readiness without contacting a private server."""
    mcp_url = os.environ.get("KEYHOLE_MCP_URL", "")
    token_present = bool(os.environ.get("KEYHOLE_MCP_TOKEN", ""))
    result = {
        "command": "doctor",
        "success": True,
        "mode": "governed" if mcp_url else "local-only",
        "mcp_url_configured": bool(mcp_url),
        "mcp_token_configured": token_present,
        "summary": (
            "Local SDK tooling is available. Governed server credentials are configured."
            if mcp_url and token_present
            else "Local SDK tooling is available. Governed server credentials are not configured; live governed commands will fail closed."
        ),
    }
    if use_json:
        typer.echo(json.dumps(result, indent=2))
        return
    typer.echo(result["summary"])


@app.command("validate")
def validate(
    repo_dir: str = typer.Argument(".", help="Repository directory to validate."),
    mode: str = typer.Option("auto", "--mode", help="Validation mode: auto, native, or advisory."),
    strict: bool = typer.Option(False, "--strict", help="Elevate warnings to failures."),
    proof: bool = typer.Option(False, "--proof", help="Emit local validation proof into tool state."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress success details."),
    state_dir: str = typer.Option("", "--state-dir", envvar="KEYHOLE_STATE_DIR", help="Tool state directory."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Override Keyhole home."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Validate local governance declaration files. Never requires server access."""
    emit(
        run_validate(
            repo_path=repo_dir,
            mode=mode,
            strict=strict,
            proof=proof,
            quiet=quiet,
            state_dir=state_dir,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@app.command("login")
def login(
    flow: str = typer.Option("pkce", "--flow", help="Authentication flow: pkce, device, password, or passwordless."),
    device: bool = typer.Option(False, "--device", help="Convenience alias for --flow device."),
    force: bool = typer.Option(False, "--force", help="Force a fresh login instead of reusing stored credentials."),
    auth_server_url: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server-url",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Auth server URL.",
    ),
    client_id: str = typer.Option("keyhole-cli", "--client-id", envvar="KEYHOLE_CLIENT_ID", help="Auth client ID."),
    mcp_base_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="Governed server base URL.",
    ),
    username: str = typer.Option("", "--username", help="Username for password flow."),
    password: str = typer.Option("", "--password", help="Password for password flow. Avoid shell history in shared environments."),
    email: str = typer.Option("", "--email", help="Email for passwordless flow."),
    realm: str = typer.Option(DEFAULT_REALM, "--realm", envvar="KEYHOLE_REALM", help="Auth realm."),
    allow_split_identity: bool = typer.Option(
        False,
        "--allow-split-identity",
        help="Allow CLI identity to differ from host attestation identity.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Authenticate and store local credentials for live governed commands."""
    selected_flow = "device" if device else flow
    if device and flow.lower() != "pkce" and flow.lower() != "device":
        emit(
            CommandResult(
                command="login",
                success=False,
                exit_code=EXIT_INVALID_INPUT,
                data={"error_class": "conflicting_login_flow", "flow": flow},
                summary="--device is an alias for --flow device and cannot be combined with another flow.",
                next_steps=["Use: keyhole login --device --force", "Or: keyhole login --flow device --force"],
            ),
            use_json=use_json,
        )
    if selected_flow.lower() in {"pkce", "device", "password", "passwordless"} and not auth_server_url:
        emit(
            CommandResult(
                command="login",
                success=False,
                exit_code=EXIT_INVALID_INPUT,
                data={"error_class": "missing_auth_server", "flow": selected_flow},
                summary="KEYHOLE_AUTH_SERVER is required for login; set it or pass --auth-server-url.",
                next_steps=[
                    "Set KEYHOLE_AUTH_SERVER to your auth server URL.",
                    "Or run: keyhole login --flow device --force --auth-server-url <url>",
                ],
            ),
            use_json=use_json,
        )
    emit(
        run_login(
            flow=selected_flow,
            force=force,
            auth_server_url=auth_server_url,
            client_id=client_id,
            mcp_base_url=mcp_base_url,
            username=username or None,
            password=password or None,
            email=email or None,
            realm=realm,
            allow_split_identity=allow_split_identity,
            _flow_explicit=device or flow.lower() != "pkce",
        ),
        use_json=use_json,
    )


@repo_app.command("register")
def repo_register(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the repository to register."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Register a repository with a configured governed server."""
    emit(run_repo_register(repo_dir=repo_dir, mcp_url=_configured_mcp_url(mcp_url)), use_json=use_json)


@context_app.command("compile")
def context_compile(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository directory."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Override Keyhole home."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Compile governed context through a configured governed server."""
    emit(
        run_context_compile(repo_dir=repo_dir, mcp_url=_configured_mcp_url(mcp_url), keyhole_home=keyhole_home),
        use_json=use_json,
    )


@context_app.command("inspect")
def context_inspect(
    digest: str = typer.Argument(..., help="Governed context digest."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository directory."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Override Keyhole home."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect a governed context digest through a configured governed server."""
    emit(
        run_context_inspect(
            digest=digest,
            repo_dir=repo_dir,
            mcp_url=_configured_mcp_url(mcp_url),
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@app.command("run")
def run(
    run_type: str = typer.Option("context.compile", "--run-type", help="Exact canonical run-type key."),
    context: str = typer.Option("", "--context", help="Context reference, digest, or 'auto'."),
    input_file: str = typer.Option("", "--input", help="Path to a JSON input file."),
    output_path: str = typer.Option("", "--output", help="Path to write run output."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repo directory."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Override Keyhole home."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Execute a governed run. Fails closed when credentials or context are missing."""
    emit(
        run_run(
            run_type=run_type,
            shadow=False,
            context=context,
            input_file=input_file,
            output_path=output_path,
            repo_dir=repo_dir,
            mcp_url=_configured_mcp_url(mcp_url),
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@governed_app.command("run")
def governed_run(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the repository to govern."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve and explain without mutating the server."),
    no_live: bool = typer.Option(False, "--no-live", help="Validate local declarations only; do not call a server."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Run the public governed repository flow."""
    emit(
        run_governed_flow(repo_dir=repo_dir, dry_run=dry_run, no_live=no_live, mcp_url=_configured_mcp_url(mcp_url)),
        use_json=use_json,
    )


@governed_app.command("status")
def governed_status(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect latest governed run state."""
    emit(run_governed_status(repo_dir=repo_dir, mcp_url=_configured_mcp_url(mcp_url)), use_json=use_json)


@governed_app.command("resume")
def governed_resume(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Resume latest governed run from local state."""
    emit(run_governed_resume(repo_dir=repo_dir, mcp_url=_configured_mcp_url(mcp_url)), use_json=use_json)


@governed_app.command("receipt")
def governed_receipt(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    mcp_url: str = typer.Option("", "--mcp-url", envvar="KEYHOLE_MCP_URL", help="Governed server base URL."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Print latest governed receipt from local state or configured server."""
    emit(run_governed_receipt(repo_dir=repo_dir, mcp_url=_configured_mcp_url(mcp_url)), use_json=use_json)


if __name__ == "__main__":
    app()
