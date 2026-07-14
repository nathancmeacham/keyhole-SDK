from __future__ import annotations

import json
import os
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Optional

import typer
from requests import RequestException

from keyhole_sdk import KeyholeClient

from keyhole_cli.result import CommandResult, EXIT_INVALID_INPUT, emit
from keyhole_cli.commands.context_cmd import run_context_compile, run_context_inspect
from keyhole_cli.commands.doctor import run_doctor
from keyhole_cli.commands.launch_doctor import run_launch_doctor
from keyhole_cli.commands.init_cmd import run_init
from keyhole_cli.commands.init_vertical import run_init_vertical
from keyhole_cli.commands.login import run_login
from keyhole_cli.commands.logout import run_logout
from keyhole_cli.commands.register import run_register
from keyhole_cli.commands.registration_status import run_registration_status
from keyhole_cli.commands.ingest_cmd import run_ingest
from keyhole_cli.commands.align_cmd import run_align
from keyhole_cli.commands.repo_register_cmd import run_repo_register
from keyhole_cli.commands.run_cmd import run_run
from keyhole_cli.commands.search_cmd import run_search
from keyhole_cli.commands.dependency_resolve_cmd import run_dependency_resolve
from keyhole_cli.commands.runs_cmd import (
    run_runs_list,
    run_runs_resume,
    run_runs_status,
    run_runs_tail,
    run_runs_wait,
)
from keyhole_cli.commands.budget_cmd import run_budget
from keyhole_cli.commands.validate_cmd import run_validate
from keyhole_cli.commands.explain_cmd import (
    run_explain_run,
    run_inspect_request,
    run_support_bundle,
)
from keyhole_cli.commands.surfaces_cmd import run_surfaces
from keyhole_cli.commands.passport_cmd import run_passport_generate, run_passport_show
from keyhole_cli.commands.capability_cmd import (
    run_capability_create,
    run_capability_register,
    run_capability_validate,
)
from keyhole_cli.commands.runtime import run_start, run_stop, run_status
from keyhole_cli.commands.smoke import run_smoke
from keyhole_cli.commands.verify import run_verify
from keyhole_cli.commands.whoami import run_whoami
from keyhole_cli.commands.auth_doctor import run_auth_doctor
from keyhole_cli.commands.deregister import run_deregister
from keyhole_cli.commands.connections_list import run_connections_list
from keyhole_cli.commands.connection_inspect import run_connection_inspect
from keyhole_cli.commands.connection_lineage import run_connection_lineage
from keyhole_cli.commands.connection_rebind import run_connection_rebind
from keyhole_cli.commands.connection_invalidate import run_connection_invalidate
from keyhole_cli.commands.host_list import run_host_list
from keyhole_cli.commands.host_inspect import run_host_inspect
from keyhole_cli.commands.host_install import run_host_install
from keyhole_cli.commands.host_attest import run_host_attest
from keyhole_cli.commands.mcp_proxy_cmd import run_mcp_proxy
from keyhole_cli.commands.auth_browser_check import run_auth_browser_check
from keyhole_cli.commands.auth_browser_support_bundle import run_auth_browser_support_bundle
from keyhole_cli.commands.auth_explain_browser import run_auth_explain_browser
from keyhole_cli.commands.runtime_contract import (
    run_runtime_check,
    run_runtime_profiles,
    run_runtime_surface,
)
from keyhole_cli.commands.gaps_cmd import (
    run_gaps_claim,
    run_gaps_close,
    run_gaps_create,
    run_gaps_list,
    run_gaps_next_open,
    run_gaps_revalidate,
)
from keyhole_cli.commands.workspace_cmd import run_workspace_provision
from keyhole_cli.commands.repo_attach_cmd import run_repo_attach
from keyhole_cli.commands.governed_demo_cmd import (
    is_first_app_repo,
    run_governed_demo_context_compile,
    run_governed_demo_register,
    run_governed_demo_run,
)
from keyhole_cli.commands.governed_flow_cmd import (
    run_governed_flow,
    run_governed_receipt,
    run_governed_resume,
    run_governed_status,
)
from keyhole_cli.commands.governance_context_cmd import run_governance_context_create
from keyhole_cli.commands.proof_cmd import run_proof_submit
from keyhole_cli.commands.receipt_cmd import run_receipt_verify

from keyhole_sdk.config import DEFAULT_AUTH_SERVER, DEFAULT_BASE_URL

DEFAULT_RUNTIME_URL = DEFAULT_BASE_URL

app = typer.Typer(
    help="Command-line interface for the Keyhole Developer Kit.",
    no_args_is_help=True,
)

doctor_app = typer.Typer(
    help="Diagnose environment and public launch readiness.",
    invoke_without_command=True,
)

runtime_app = typer.Typer(
    help="Interact with a Keyhole-compatible runtime.",
    no_args_is_help=True,
)

init_app = typer.Typer(
    help="Initialize workspaces and governed repo scaffolds.",
    invoke_without_command=True,
)

context_app = typer.Typer(
    help="Context lifecycle — compile, inspect, and manage governed context.",
    no_args_is_help=True,
)

runs_app = typer.Typer(
    help="Async run lifecycle — status, wait, tail, resume, and list.",
    no_args_is_help=True,
)

repo_app = typer.Typer(
    help="Repository management — register, status, and lifecycle.",
    no_args_is_help=True,
)

dependency_app = typer.Typer(
    help="Dependency management — resolve and inspect.",
    no_args_is_help=True,
)

explain_app = typer.Typer(
    help="Governance explainability — explain runs and inspect requests.",
    no_args_is_help=True,
)

capability_app = typer.Typer(
    help="Capability namespace — create and validate governed capability identifiers.",
    no_args_is_help=True,
)

passport_app = typer.Typer(
    help="Capability passport generation — generate and inspect governed passport artifacts.",
    no_args_is_help=True,
)

connection_app = typer.Typer(
    help="Connection identity — inspect, rebind, and invalidate MCP host connections.",
    no_args_is_help=True,
)

host_app = typer.Typer(
    help="Host management — list, inspect, and install Keyhole credentials into IDE hosts.",
    no_args_is_help=True,
)

auth_app = typer.Typer(
    help="Auth tools — browser OIDC compatibility check, support bundle, and explainability.",
    no_args_is_help=True,
)

gaps_app = typer.Typer(
    help="Gap lifecycle — list, create, and claim actionable capability gaps.",
    no_args_is_help=True,
)

workspace_app = typer.Typer(
    help="Workspace lifecycle — DEPRECATED for downstream flows. Use governance-context instead.",
    no_args_is_help=True,
)

governance_context_app = typer.Typer(
    help="Governance context — bind a claimed gap to the subject repo (repo-as-workspace model).",
    no_args_is_help=True,
)

proof_app = typer.Typer(
    help="Proof submission — submit local proof bundles for governed verdict.",
    no_args_is_help=True,
)

receipt_app = typer.Typer(
    help="Receipt verification — verify local governed receipts against proof bundles.",
    no_args_is_help=True,
)

governed_app = typer.Typer(
    help="Generic governed repository flow for forked SDK/client repos.",
    no_args_is_help=True,
)

app.add_typer(doctor_app, name="doctor")
app.add_typer(runtime_app, name="runtime")
app.add_typer(init_app, name="init")
app.add_typer(context_app, name="context")
app.add_typer(runs_app, name="runs")
app.add_typer(repo_app, name="repo")
app.add_typer(dependency_app, name="dependency")
app.add_typer(explain_app, name="explain")
app.add_typer(capability_app, name="capability")
app.add_typer(passport_app, name="passport")
app.add_typer(connection_app, name="connection")
app.add_typer(host_app, name="host")
app.add_typer(passport_app, name="passport")
app.add_typer(auth_app, name="auth")
app.add_typer(gaps_app, name="gaps")
app.add_typer(workspace_app, name="workspace")
app.add_typer(governance_context_app, name="governance-context")
app.add_typer(proof_app, name="proof")
app.add_typer(receipt_app, name="receipt")
app.add_typer(governed_app, name="governed")


@app.command("version")
def cmd_version(
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Print installed keyhole CLI and SDK versions."""
    data = {
        "cli_version": _package_version("keyhole-cli"),
        "sdk_version": _package_version("keyhole-sdk"),
    }
    if use_json:
        _print_json({"command": "version", "success": True, **data})
        return
    typer.echo(f"keyhole-cli {data['cli_version']}")
    typer.echo(f"keyhole-sdk {data['sdk_version']}")


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2))


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "unknown"


@governed_app.command("run")
def cmd_governed_run(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the repository to govern."),
    story_id: str = typer.Option("", "--story-id", help="Optional story label for gap discovery."),
    capability_id: str = typer.Option("", "--capability-id", help="Optional declared capability selector."),
    repo_class: str = typer.Option("", "--repo-class", help="Optional governed repo class override."),
    gap_id: str = typer.Option("", "--gap-id", help="Explicit canonical gap_* id supplied by the operator."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Resolve and explain without mutating MCP."),
    no_live: bool = typer.Option(False, "--no-live", help="Validate local declarations only; do not call MCP."),
    explain: bool = typer.Option(False, "--explain", help="Include resolution decisions in output."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Run the generic governed repository flow through MCP."""
    emit(
        run_governed_flow(
            repo_dir=repo_dir,
            story_id=story_id,
            capability_id=capability_id,
            repo_class=repo_class,
            gap_id=gap_id,
            dry_run=dry_run,
            no_live=no_live,
            explain=explain,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@governed_app.command("status")
def cmd_governed_status(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    last: bool = typer.Option(True, "--last", help="Read the latest local governed run state."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect the latest governed run state and poll MCP if needed."""
    _ = last
    emit(
        run_governed_status(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@governed_app.command("resume")
def cmd_governed_resume(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    last: bool = typer.Option(True, "--last", help="Resume from the latest local governed run state."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Resume the latest governed run from its last safe checkpoint."""
    _ = last
    emit(
        run_governed_resume(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@governed_app.command("receipt")
def cmd_governed_receipt(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    last: bool = typer.Option(True, "--last", help="Print the latest governed receipt from local state."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Print the latest governed receipt without rerunning the flow."""
    _ = last
    emit(
        run_governed_receipt(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


def _load_payload(payload_json: Optional[str], payload_file: Optional[Path]) -> dict[str, Any]:
    if payload_json and payload_file:
        raise typer.BadParameter("Use either --payload-json or --payload-file, not both.")

    if payload_json:
        try:
            value = json.loads(payload_json)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON passed to --payload-json: {exc}") from exc

        if not isinstance(value, dict):
            raise typer.BadParameter("--payload-json must decode to a JSON object.")

        return value

    if payload_file:
        try:
            value = json.loads(payload_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise typer.BadParameter(f"Payload file not found: {payload_file}") from exc
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON in payload file {payload_file}: {exc}") from exc

        if not isinstance(value, dict):
            raise typer.BadParameter("--payload-file must contain a JSON object.")

        return value

    return {}


def _handle_request_error(exc: Exception) -> None:
    typer.secho(f"Request failed: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-00: Identity Creation & Verification Commands
# ──────────────────────────────────────────────────────────────


@app.command()
def register(
    email: str = typer.Option(..., "--email", help="Builder email address."),
    username: str = typer.Option(..., "--username", help="Builder username."),
    display_name: str = typer.Option(..., "--display-name", help="Builder display name."),
    realm: str = typer.Option(
        "kh-dev",
        "--realm",
        help="Target realm: kh-prod, kh-dev, keyhole-mcp.",
    ),
    origin: str = typer.Option(
        "",
        "--origin",
        help="Origin classification (required for kh-dev). E.g.: smoke, test, integration.",
    ),
    purpose: str = typer.Option(
        "",
        "--purpose",
        help="Purpose classification (required for kh-dev). E.g.: sdk_onboarding, sdk_smoke.",
    ),
    tenant: str = typer.Option("", "--tenant", help="Tenant context."),
    org: str = typer.Option("", "--org", help="Organization context."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Register a new builder identity through the governed boundary."""
    emit(
        run_register(
            email=email,
            username=username,
            display_name=display_name,
            realm=realm,
            origin=origin,
            purpose=purpose,
            tenant=tenant,
            org=org,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@app.command()
def verify(
    registration_id: str = typer.Option(..., "--registration-id", help="Registration ID to verify."),
    code: str = typer.Option("", "--code", help="Verification code."),
    token: str = typer.Option("", "--token", help="Verification token."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Complete verification for a pending registration."""
    emit(
        run_verify(
            registration_id=registration_id,
            code=code,
            token=token,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@app.command(name="registration-status")
def registration_status(
    registration_id: str = typer.Option(..., "--registration-id", help="Registration ID to inspect."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect current onboarding state for a registration."""
    emit(
        run_registration_status(
            registration_id=registration_id,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-22: Account Deregistration and Deletion UX
# ──────────────────────────────────────────────────────────────


@app.command()
def deregister(
    registration_id: str = typer.Option(
        ..., "--registration-id", help="Registration/user ID of the account to delete.",
    ),
    yes: bool = typer.Option(
        False, "--yes", help="Skip destructive confirmation prompt.",
    ),
    realm: str = typer.Option(
        "kh-prod", "--realm", help="Target realm.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Request deletion of a builder account through the governed boundary."""
    # If --yes not supplied, prompt for destructive confirmation (§12)
    if not yes and not use_json:
        typer.echo(f"You are about to request deletion of account {registration_id}.")
        typer.echo("This will revoke future access if completed.")
        confirm = typer.prompt("Type DELETE to continue", default="")
        if confirm != "DELETE":
            typer.secho("Deletion cancelled.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        yes = True  # confirmation passed

    emit(
        run_deregister(
            registration_id=registration_id,
            yes=yes,
            realm=realm,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-01: Authentication Bootstrap Commands
# ──────────────────────────────────────────────────────────────


@app.command()
def login(
    flow: str = typer.Option(
        "device",
        "--flow",
        help="Auth flow type: device (default), pkce (browser), password (ROPC/dev-only), or passwordless (email code).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Force re-authentication even if a valid session exists.",
    ),
    auth_server: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Auth server URL.",
    ),
    client_id: str = typer.Option(
        "keyhole-cli",
        "--client-id",
        envvar="KEYHOLE_CLIENT_ID",
        help="OAuth2 client ID.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    username: Optional[str] = typer.Option(
        None,
        "--username",
        envvar="KEYHOLE_TEST_USERNAME",
        help="Username for password flow (dev/test only).",
    ),
    password: Optional[str] = typer.Option(
        None,
        "--password",
        envvar="KEYHOLE_TEST_PASSWORD",
        help="Password for password flow (dev/test only).",
    ),
    email: Optional[str] = typer.Option(
        None,
        "--email",
        envvar="KEYHOLE_EMAIL",
        help="Email address for passwordless login flow.",
    ),
    realm: str = typer.Option(
        "kh-prod",
        "--realm",
        envvar="KEYHOLE_REALM",
        help="Identity realm (default: kh-prod).",
    ),
    allow_split_identity: bool = typer.Option(
        False,
        "--allow-split-identity",
        help="Allow login even if host attestation shows a conflicting principal (SDK-CLIENT-23).",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Authenticate with the Keyhole boundary."""
    if flow.lower() == "password" and os.environ.get("KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN") != "1":
        emit(
            CommandResult(
                command="login",
                success=False,
                exit_code=EXIT_INVALID_INPUT,
                data={"error_class": "password_login_disabled", "flow": flow},
                summary=(
                    "Password login is disabled in the public SDK by default. "
                    "Use `keyhole login --flow device --force`, or set "
                    "KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN=1 for local/dev auth only."
                ),
                next_steps=[
                    "Use: keyhole login --flow device --force",
                    "For local/dev only: set KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN=1 and retry.",
                ],
            ),
            use_json=use_json,
        )
        raise typer.Exit(EXIT_INVALID_INPUT)

    # Detect if the user explicitly chose a non-default flow or provided
    # --email.  Bare `keyhole login` remains device-first for the public
    # MCP boundary path.
    flow_explicit = (flow != "device") or (email is not None)
    emit(
        run_login(
            flow=flow,
            force=force,
            auth_server_url=auth_server,
            client_id=client_id,
            mcp_base_url=mcp_url,
            username=username,
            password=password,
            email=email,
            realm=realm,
            allow_split_identity=allow_split_identity,
            _flow_explicit=flow_explicit,
        ),
        use_json=use_json,
    )


@app.command()
def whoami(
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    show_envelope: bool = typer.Option(
        False,
        "--show-envelope",
        help="Render the full server-resolved actor envelope (SDK-CLIENT-29).",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect your authenticated identity context."""
    result = run_whoami(mcp_base_url=mcp_url, show_envelope=show_envelope)

    # SDK-CLIENT-29: when --show-envelope is requested in human mode,
    # render a verbose envelope block before the standard summary so
    # operators can audit who the server believes is acting.
    if show_envelope and not use_json and result.success:
        env = result.data.get("actor_envelope")
        if env:
            typer.secho("\nActor envelope (server-resolved):", fg=typer.colors.CYAN, bold=True)
            hp = env.get("human_principal") or {}
            ap = env.get("acting_principal") or {}
            dl = env.get("delegation") or {}
            az = env.get("authorization") or {}
            typer.echo(f"  Human principal:")
            typer.echo(f"    realm:        {hp.get('realm')}")
            typer.echo(f"    subject_id:   {hp.get('subject_id')}")
            typer.echo(f"    tenant_id:    {hp.get('tenant_id')}")
            typer.echo(f"    display_name: {hp.get('display_name')}")
            typer.echo(f"  Acting principal:")
            typer.echo(f"    realm:        {ap.get('realm')}")
            typer.echo(f"    client_id:    {ap.get('client_id')}")
            typer.echo(f"    kind:         {ap.get('kind')}")
            typer.echo(f"  Delegation:")
            typer.echo(f"    kind:         {dl.get('kind')}")
            typer.echo(f"    assurance:    {dl.get('assurance')}")
            scopes = az.get("effective_scopes") or []
            grants = az.get("tool_grants") or []
            typer.echo(f"  Authorization:")
            typer.echo(f"    effective_scopes: {', '.join(scopes) if scopes else '(none)'}")
            typer.echo(f"    tool_grants:      {', '.join(grants) if grants else '(none)'}")
            typer.echo("")
        else:
            typer.secho(
                "\nActor envelope: (not returned by server)",
                fg=typer.colors.YELLOW,
            )

    emit(result, use_json=use_json)


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-25: Logout / sign-out and auth state hygiene
# ──────────────────────────────────────────────────────────────


@app.command()
def logout(
    auth_server: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Auth server URL (used for token revocation).",
    ),
    client_id: str = typer.Option(
        "keyhole-cli",
        "--client-id",
        envvar="KEYHOLE_CLIENT_ID",
        help="OAuth2 client ID.",
    ),
    skip_revocation: bool = typer.Option(
        False,
        "--skip-revocation",
        help="Clear local credentials only — skip remote revocation.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Sign out — revoke tokens and clear local auth state.

    Implements SDK-CLIENT-25 §8.1.  After sign-out, the next
    ``keyhole login`` begins a fresh auth transaction.
    """
    emit(
        run_logout(
            auth_server_url=auth_server,
            client_id=client_id,
            skip_revocation=skip_revocation,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-09: Governed Run Dispatch
# ──────────────────────────────────────────────────────────────


@app.command(name="run")
def cmd_run(
    run_type: str = typer.Option(
        "context.compile",
        "--run-type",
        help="Exact canonical run-type key.",
    ),
    shadow: bool = typer.Option(
        False,
        "--shadow",
        help="Execute in shadow (non-canonical) mode.",
    ),
    context: str = typer.Option(
        "",
        "--context",
        help="Context reference (path, digest, or 'auto').",
    ),
    input_file: str = typer.Option(
        "",
        "--input",
        help="Path to a JSON input file for the run.",
    ),
    output_path: str = typer.Option(
        "",
        "--output",
        help="Path to write run output.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Execute a governed run through the MCP boundary."""
    if context == "auto" and is_first_app_repo(repo_dir):
        emit(
            run_governed_demo_run(
                repo_dir=repo_dir,
                mcp_url=mcp_url,
            ),
            use_json=use_json,
        )
        return
    emit(
        run_run(
            run_type=run_type,
            shadow=shadow,
            context=context,
            input_file=input_file,
            output_path=output_path,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-10: Repository Ingestion and Graph
# ──────────────────────────────────────────────────────────────


@app.command(name="ingest")
def cmd_ingest(
    repo_path: str = typer.Argument(
        ".",
        help="Path to the repository to ingest.",
    ),
    shadow: bool = typer.Option(
        False,
        "--shadow",
        help="Execute in shadow (exploratory) mode.",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        help="Additional include glob patterns.",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        help="Additional exclude glob patterns.",
    ),
    max_bytes: int = typer.Option(
        0,
        "--max-bytes",
        help="Maximum total bytes to include (0 = unlimited).",
    ),
    summary_only: bool = typer.Option(
        False,
        "--summary-only",
        help="Scan and package only — do not submit.",
    ),
    gap_id: str = typer.Option(
        "",
        "--gap-id",
        envvar="KEYHOLE_GAP_ID",
        help="Canonical gap ID for governed repo registration.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Ingest an existing repository for graph analysis and alignment guidance."""
    emit(
        run_ingest(
            repo_path=repo_path,
            shadow=shadow,
            include=include,
            exclude=exclude,
            max_bytes=max_bytes,
            summary_only=summary_only,
            gap_id=gap_id,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-11: Alignment Guidance
# ──────────────────────────────────────────────────────────────


@app.command(name="align")
def cmd_align(
    repo_path: str = typer.Argument(
        ".",
        help="Path to the repository to align.",
    ),
    analysis_id: str = typer.Option(
        "",
        "--analysis-id",
        help="Analysis ID from a previous ingestion run.",
    ),
    from_ingestion: str = typer.Option(
        "",
        "--from-ingestion",
        help="Correlation ID from a previous ingestion to load saved artifacts.",
    ),
    shadow: bool = typer.Option(
        False,
        "--shadow",
        help="Execute in shadow (exploratory) mode.",
    ),
    local_only: bool = typer.Option(
        False,
        "--local-only",
        help="Render guidance from local artifacts only (no MCP call).",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Show alignment guidance for the current repository.

    Never mutates the repository. Guidance only.
    """
    emit(
        run_align(
            repo_path=repo_path,
            analysis_id=analysis_id,
            from_ingestion=from_ingestion,
            shadow=shadow,
            local_only=local_only,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# S41-02: First-Success Commands
# ──────────────────────────────────────────────────────────────


@doctor_app.callback(invoke_without_command=True)
def doctor(
    ctx: typer.Context,
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Operating mode: auto, local_only, governed, host_inventory, or live_reconciliation.",
    ),
    runtime_url: str = typer.Option(
        "",
        "--runtime-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Runtime URL for health checks (governed mode).",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Run verification-after-repair mode.",
    ),
    goal: str = typer.Option("", "--goal", help="Goal description for repair plan."),
    fix: bool = typer.Option(False, "--fix", help="Apply approved repairs (SDK-CLIENT-01-C)."),
    host: str = typer.Option("", "--host", help="Target host for fix (SDK-CLIENT-01-C)."),
    profile: str = typer.Option("", "--profile", help="Target profile for rebind (SDK-CLIENT-01-C)."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Disable interactive prompts."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
) -> None:
    """Diagnose environment, compute repair plan, and verify."""
    if ctx.invoked_subcommand is not None:
        return
    emit(
        run_doctor(
            mode=mode,
            runtime_url=runtime_url,
            verify=verify,
            goal=goal,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@doctor_app.command("launch")
def doctor_launch(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the governed repository."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Check public SDK launch readiness for a governed repository."""
    emit(run_launch_doctor(repo_dir=repo_dir, mcp_url=mcp_url), use_json=use_json)


@init_app.callback(invoke_without_command=True)
def init(
    ctx: typer.Context,
    directory: str = typer.Option(".", "--dir", "-d", help="Directory to initialize."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Initialize a first-success workspace (default), or use a subcommand."""
    if ctx.invoked_subcommand is None:
        emit(run_init(directory=directory), use_json=use_json)


@init_app.command("vertical")
def init_vertical(
    name: str = typer.Argument(default="", help="Name for the new repo scaffold directory."),
    path: str = typer.Option("", "--path", "-p", help="Explicit target directory path."),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing managed scaffold files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created without writing."),
    template: str = typer.Option("default", "--template", "-t", help="Scaffold template name."),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Disable interactive prompts."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Generate a canonical governed participant repo scaffold."""
    emit(
        run_init_vertical(
            name=name,
            path=path,
            force=force,
            dry_run=dry_run,
            template=template,
            non_interactive=non_interactive,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-16: Context Lifecycle Commands
# ──────────────────────────────────────────────────────────────


@context_app.command("compile")
def cmd_context_compile(
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    mode: str = typer.Option(
        "",
        "--mode",
        help="Compile mode.",
    ),
    origin: str = typer.Option(
        "",
        "--origin",
        help="Origin classification.",
    ),
    purpose: str = typer.Option(
        "",
        "--purpose",
        help="Purpose classification.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Compile governed context for the current repo and identity."""
    if is_first_app_repo(repo_dir):
        emit(
            run_governed_demo_context_compile(
                repo_dir=repo_dir,
                mcp_url=mcp_url,
            ),
            use_json=use_json,
        )
        return
    emit(
        run_context_compile(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            mode=mode,
            origin=origin,
            purpose=purpose,
        ),
        use_json=use_json,
    )


@context_app.command("inspect")
def cmd_context_inspect(
    digest: str = typer.Option(
        "",
        "--digest",
        help="The ctxpack_digest to inspect. Omit to use most recently compiled.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect a governed context digest to understand its state-of-truth."""
    emit(
        run_context_inspect(
            digest=digest,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@app.command()
def smoke(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Run the canonical first-success verification."""
    emit(run_smoke(endpoint=base_url), use_json=use_json)


@runtime_app.command("start")
def cmd_runtime_start(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Start the local public test runtime."""
    emit(run_start(endpoint=base_url), use_json=use_json)


@runtime_app.command("stop")
def cmd_runtime_stop(
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Stop the local public test runtime."""
    emit(run_stop(), use_json=use_json)


@runtime_app.command("status")
def cmd_runtime_status(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Report truthful runtime state and public mode."""
    emit(run_status(endpoint=base_url), use_json=use_json)


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-24: Runtime Contract Verification
# ──────────────────────────────────────────────────────────────


@runtime_app.command("profiles")
def cmd_runtime_profiles(
    mcp_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="Base URL of the MCP boundary.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """List runtime profiles disclosed by the MCP boundary (SDK-CLIENT-24)."""
    emit(run_runtime_profiles(mcp_url=mcp_url), use_json=use_json)


@runtime_app.command("surface")
def cmd_runtime_surface(
    mcp_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="Base URL of the MCP boundary.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Negotiate the authoritative runtime surface (SDK-CLIENT-24)."""
    emit(
        run_runtime_surface(mcp_url=mcp_url, keyhole_home=keyhole_home),
        use_json=use_json,
    )


@runtime_app.command("check")
def cmd_runtime_check(
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Runtime mode: auto | container | external.",
    ),
    runtime_kind: str = typer.Option(
        "local-python",
        "--runtime-kind",
        help="Runtime kind label for external-mode claims.",
    ),
    image_digest: str = typer.Option(
        "",
        "--image-digest",
        help="Container image digest (required for container mode).",
    ),
    negative: str = typer.Option(
        "",
        "--negative",
        help="Negative-test mode (e.g. nonportable-venv) — expects REJECT.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_BASE_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="Base URL of the MCP boundary.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Verify a runtime context against the MCP boundary (SDK-CLIENT-24)."""
    emit(
        run_runtime_check(
            mode=mode,
            runtime_kind=runtime_kind,
            image_digest=image_digest,
            negative=negative,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# Legacy / existing SDK-backed commands (preserved)
# ──────────────────────────────────────────────────────────────


@runtime_app.command("health")
def runtime_health(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
) -> None:
    """Check runtime health."""
    client = KeyholeClient(base_url=base_url)
    try:
        _print_json(client.health())
    except RequestException as exc:
        _handle_request_error(exc)
    finally:
        client.close()


@runtime_app.command("identity")
def runtime_identity(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
) -> None:
    """Return runtime identity and declared capabilities."""
    client = KeyholeClient(base_url=base_url)
    try:
        data = client.identity()
        _print_json(data)
    except RequestException as exc:
        _handle_request_error(exc)
    finally:
        client.close()


@runtime_app.command("state")
def runtime_state(
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
) -> None:
    """Return the current runtime-local state view."""
    client = KeyholeClient(base_url=base_url)
    try:
        _print_json(client.state())
    except RequestException as exc:
        _handle_request_error(exc)
    finally:
        client.close()


@runtime_app.command("realize")
def runtime_realize(
    candidate_digest: str = typer.Argument(
        ...,
        help="Candidate digest to submit to the runtime.",
    ),
    payload_json: Optional[str] = typer.Option(
        None,
        "--payload-json",
        help="Inline JSON object payload to include with the request.",
    ),
    payload_file: Optional[Path] = typer.Option(
        None,
        "--payload-file",
        exists=False,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to a JSON file containing the payload object.",
    ),
    base_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--base-url",
        envvar="KEYHOLE_RUNTIME_URL",
        help="Base URL of the Keyhole runtime.",
    ),
) -> None:
    """Submit a bounded realization request."""
    payload = _load_payload(payload_json, payload_file)

    client = KeyholeClient(base_url=base_url)
    try:
        data = client.realize(candidate_digest=candidate_digest, payload=payload)
        _print_json(data)
    except RequestException as exc:
        _handle_request_error(exc)
    finally:
        client.close()


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-17: Async Run Lifecycle Commands
# ──────────────────────────────────────────────────────────────


@runs_app.command("status")
def cmd_runs_status(
    run_id: str = typer.Argument(..., help="The run ID or correlation ID to check."),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Check the current state of a governed run."""
    emit(
        run_runs_status(
            run_id=run_id,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@runs_app.command("wait")
def cmd_runs_wait(
    run_id: str = typer.Argument(..., help="The run ID to wait for."),
    poll_interval: float = typer.Option(
        3.0,
        "--poll-interval",
        help="Seconds between status polls.",
    ),
    max_polls: int = typer.Option(
        200,
        "--max-polls",
        help="Maximum number of polls before timeout.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Poll until a governed run reaches a terminal state."""
    emit(
        run_runs_wait(
            run_id=run_id,
            poll_interval=poll_interval,
            max_polls=max_polls,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@runs_app.command("tail")
def cmd_runs_tail(
    run_id: str = typer.Argument(..., help="The run ID to follow."),
    poll_interval: float = typer.Option(
        2.0,
        "--poll-interval",
        help="Seconds between observation polls.",
    ),
    max_entries: int = typer.Option(
        100,
        "--max-entries",
        help="Maximum observation entries to collect.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Follow run observations using the best available method (currently status polling)."""
    emit(
        run_runs_tail(
            run_id=run_id,
            poll_interval=poll_interval,
            max_entries=max_entries,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@runs_app.command("resume")
def cmd_runs_resume(
    identifier: str = typer.Argument(..., help="Run ID, request ID, or correlation ID to resume."),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Reconnect to an existing governed run identity."""
    emit(
        run_runs_resume(
            identifier=identifier,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@runs_app.command("list")
def cmd_runs_list(
    limit: int = typer.Option(
        10,
        "--limit",
        help="Maximum number of recent runs to list.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """List recent local run records."""
    emit(
        run_runs_list(
            limit=limit,
            repo_dir=repo_dir,
        ),
        use_json=use_json,
    )


@runs_app.command("budget")
def cmd_runs_budget(
    run_id: str = typer.Argument(..., help="Run ID to inspect budget and limit posture for."),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        help="Override proof state directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Show budget and limit posture for a run."""
    emit(
        run_budget(
            run_id=run_id,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            state_dir=state_dir,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-20: Governance Explainability
# ──────────────────────────────────────────────────────────────


@explain_app.command("run")
def cmd_explain_run(
    run_id: str = typer.Argument(..., help="Run ID to explain."),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        help="Override proof state directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Explain a governed run — outcome, reason, evidence, and repair guidance."""
    emit(
        run_explain_run(
            run_id=run_id,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            state_dir=state_dir,
        ),
        use_json=use_json,
    )


@app.command("inspect")
def cmd_inspect(
    request_id: str = typer.Argument(..., help="Request ID to inspect."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        help="Override proof state directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect a request — execution status, replay disposition, and context ref."""
    emit(
        run_inspect_request(
            request_id=request_id,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            repo_dir=repo_dir,
            state_dir=state_dir,
        ),
        use_json=use_json,
    )


@app.command("support-bundle")
def cmd_support_bundle(
    identifier: str = typer.Argument(
        ...,
        help="Run ID or request ID for the support bundle.",
    ),
    run_id: str = typer.Option("", "--run-id", help="Explicit run ID (overrides identifier)."),
    request_id: str = typer.Option("", "--request-id", help="Explicit request ID (overrides identifier)."),
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the governed repo directory.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        help="Override proof state directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Assemble a portable support bundle for escalation and audit."""
    emit(
        run_support_bundle(
            run_id=run_id or identifier,
            request_id=request_id or identifier,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            state_dir=state_dir,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-07: Repository Registration
# ──────────────────────────────────────────────────────────────


@repo_app.command("register")
def cmd_repo_register(
    path: str = typer.Option(
        ".",
        "--path",
        help="Path to the repository to register.",
    ),
    shadow: bool = typer.Option(
        False,
        "--shadow",
        help="Shadow (observational) registration mode.",
    ),
    from_ingest: str = typer.Option(
        "",
        "--from-ingest",
        help="Register from a prior ingestion ID or correlation ID.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Disable interactive prompts.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Register a repository with the MCP boundary for governed participation."""
    if is_first_app_repo(path):
        emit(
            run_governed_demo_register(
                repo_path=path,
                mcp_url=mcp_url,
            ),
            use_json=use_json,
        )
        return
    emit(
        run_repo_register(
            repo_path=path,
            shadow=shadow,
            from_ingest=from_ingest,
            non_interactive=non_interactive,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@repo_app.command("attach")
def cmd_repo_attach(
    repo_dir: str = typer.Option(
        ".",
        "--repo-dir",
        help="Path to the repository to attach as the governed subject workspace.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Attach the current repo as the governed subject workspace (SDK-CLIENT-30).

    Detects the local Git repo identity (remote, owner, repo, branch, commit SHA,
    dirty status) and enrolls it as the governed subject workspace via the MCP
    boundary. Stores the resulting repo_binding_id in .keyhole/repo-binding.json.

    The repo is the workspace. The server creates governance context.
    This command never targets Keyhole-Solution/keyhole_platform.

    Example:
      keyhole repo attach
      keyhole repo attach --repo-dir /path/to/my-fork
    """
    emit(
        run_repo_attach(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-30: Governance Context Commands
# ──────────────────────────────────────────────────────────────


@governance_context_app.command("create")
def cmd_governance_context_create(
    gap_id: str = typer.Option(..., "--gap-id", help="Gap ID from `keyhole gaps claim`."),
    claim_token: str = typer.Option("", "--claim-token", help="Claim token from `keyhole gaps claim` (optional — server authorizes via JWT if omitted)."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Path to the subject repo directory."),
    repo_binding_id: str = typer.Option("", "--repo-binding-id", help="Override repo binding ID (default: from .keyhole/repo-binding.json)."),
    purpose: str = typer.Option("development", "--purpose", help="Context purpose (default: development)."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Bind a claimed gap to the subject repo as a governance context (SDK-CLIENT-30).

    Replaces `keyhole workspace provision` for downstream SDK/customer/forked
    repo workflows. Creates a governance context without creating a server-side
    persistent workspace or Git branch.

    The repo is the workspace. The server binds the gap to the subject repo and
    commit SHA. ToolRunner executions are ephemeral — not persistent workspaces.

    Server compatibility guards fail loudly if:
      - Server creates a persistent workspace (REPO_AS_WORKSPACE_CONTRACT_VIOLATION)
      - Server resolves subject repo to keyhole_platform (PLATFORM_REPO_TARGET_FORBIDDEN)
      - Server returns workspace_id without governance_context_id (GOVERNANCE_CONTEXT_REQUIRED)
      - Server response missing subject repo binding (SUBJECT_REPO_BINDING_REQUIRED)

    Expected output:
      Gap claimed: gap_...
      Governance context: gctx_...
      Repo: owner/repo
      Branch: main
      Commit: abc123...
      Workspace model: repo-as-workspace
      Persistent workspace created: no

    Example:
      keyhole governance-context create --gap-id <id> --claim-token <token>
    """
    emit(
        run_governance_context_create(
            gap_id=gap_id,
            claim_token=claim_token,
            repo_dir=repo_dir,
            repo_binding_id=repo_binding_id,
            purpose=purpose,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-08: Capability Discovery and Resolution
# ──────────────────────────────────────────────────────────────


@app.command(name="search")
def cmd_search(
    query: str = typer.Argument(..., help="Capability name or namespace prefix to search for."),
    provider: str = typer.Option(
        "",
        "--provider",
        help="Filter by provider name.",
    ),
    version: str = typer.Option(
        "",
        "--version",
        help="Filter by version constraint.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Search the governed capability registry."""
    emit(
        run_search(
            query=query,
            provider=provider,
            version=version,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@dependency_app.command("resolve")
def cmd_dependency_resolve(
    capability: str = typer.Argument(..., help="Capability to resolve as a dependency."),
    provider: str = typer.Option(
        "",
        "--provider",
        help="Pin a specific provider.",
    ),
    version: str = typer.Option(
        "",
        "--version",
        help="Pin a specific version.",
    ),
    write: bool = typer.Option(
        False,
        "--write",
        help="Write the resolved dependency to dependencies.yaml (native repos only).",
    ),
    advisory: bool = typer.Option(
        False,
        "--advisory",
        help="Emit advisory artifact only (no repo mutation). This is the default.",
    ),
    path: str = typer.Option(
        ".",
        "--path",
        help="Path to the repository.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override credential store directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Resolve a capability to a deterministic dependency."""
    emit(
        run_dependency_resolve(
            capability=capability,
            provider=provider,
            version=version,
            write=write,
            advisory=advisory,
            repo_path=path,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-18: Memory Boundary Enforcement
# Registers a 'memory' command group that always rejects with repair guidance.
# No sub-commands (query, write, get, delete) are registered.
# Direct canonical memory access is not exposed by the public CLI.
# ──────────────────────────────────────────────────────────────

memory_app = typer.Typer(
    help=(
        "[REJECTED] Direct canonical memory access is not exposed by the public CLI.\n\n"
        "Use governed context, governed runs, or proof/explain surfaces instead:\n"
        "  keyhole context compile\n"
        "  keyhole context inspect\n"
        "  keyhole run --context <digest>"
    ),
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(memory_app, name="memory")


@memory_app.callback(invoke_without_command=True)
def memory_boundary_reject(ctx: typer.Context) -> None:
    """[REJECTED] Direct canonical memory access is not exposed by the public CLI."""
    from keyhole_sdk.memory_boundary import MEMORY_BOUNDARY_REJECTION_MESSAGE

    typer.secho(
        MEMORY_BOUNDARY_REJECTION_MESSAGE,
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)



# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-03: Capability Namespace Commands
# ──────────────────────────────────────────────────────────────


@capability_app.command("create")
def cmd_capability_create(
    domain: str = typer.Option(..., "--domain", help="Top-level domain (e.g. payment)."),
    category: str = typer.Option(..., "--category", help="Category within domain (e.g. stripe)."),
    name: str = typer.Option(..., "--name", help="Capability name (e.g. integration)."),
    major: int = typer.Option(1, "--major", help="Major version number (positive integer)."),
    write: bool = typer.Option(False, "--write/--no-write", help="Write to governed artifact when in a native repo."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Target repository directory."),
    state_dir: str = typer.Option("", "--state-dir", envvar="KEYHOLE_STATE_DIR", help="Tool-owned state directory for proof artifacts."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Create a canonical capability name from structured parts.

    Validates parts, normalises obvious input issues, assembles the canonical
    name, and optionally writes to a governed local artifact.

    Example:
      keyhole capability create --domain payment --category stripe --name integration --major 1
    """
    emit(
        run_capability_create(
            domain=domain,
            category=category,
            name=name,
            major=major,
            repo_dir=repo_dir,
            write=write,
            state_dir=state_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@capability_app.command("validate")
def cmd_capability_validate(
    capability_name: str = typer.Argument(..., help="Capability name to validate (e.g. payment.stripe.integration.v1)."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Target repository directory."),
    state_dir: str = typer.Option("", "--state-dir", envvar="KEYHOLE_STATE_DIR", help="Tool-owned state directory for proof artifacts."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Validate a capability name against the canonical namespace contract.

    Accepts ``<domain>.<category>.<capability>.v<major>`` format.
    Advisory only — never mutates the repo.

    Example:
      keyhole capability validate payment.stripe.integration.v1
    """
    emit(
        run_capability_validate(
            capability_name=capability_name,
            repo_dir=repo_dir,
            state_dir=state_dir,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@capability_app.command("register")
def cmd_capability_register(
    capability_name: str = typer.Option(..., "--capability", help="Canonical capability name to register (e.g. my-first-app.greet.user.v1)."),
    invariant: str = typer.Option("", "--invariant", help="Invariant ID whose receipt authorises registration."),
    bundle: str = typer.Option("proof_bundle", "--bundle", help="Path to proof bundle directory."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Register a capability with a governed receipt.

    Receipt-backed registration: requires an ACCEPT receipt from
    `keyhole proof submit` before registration is allowed.

    Public contract: "No verified governed receipt, no registration."

    Example:
      keyhole capability register --capability my-first-app.greet.user.v1 --invariant MY-FIRST-APP-INV-01
    """
    emit(
        run_capability_register(
            capability_name=capability_name,
            invariant=invariant,
            bundle=bundle,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-PUBLIC-REPAIR-01: Gap Lifecycle Commands
# ──────────────────────────────────────────────────────────────


@gaps_app.command("list")
def cmd_gaps_list(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """List actionable capability gaps for the current repo and identity.

    Calls run_type=gaps.list through the MCP boundary.

    Example:
      keyhole gaps list
      keyhole gaps list --json
    """
    emit(
        run_gaps_list(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@gaps_app.command("create")
def cmd_gaps_create(
    capability: str = typer.Option(..., "--capability", help="Capability name for the gap (e.g. my-first-app.greet.user.v1)."),
    description: str = typer.Option("", "--description", help="Optional description for the gap."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Submit a new actionable capability-registration gap.

    Calls run_type=gaps.submit through the MCP boundary.
    If the server does not support this run type, returns a clear SERVER_BLOCKED verdict.

    Example:
      keyhole gaps create --capability my-first-app.greet.user.v1
    """
    emit(
        run_gaps_create(
            capability=capability,
            description=description,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@gaps_app.command("next-open")
def cmd_gaps_next_open(
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Return the next open canonical gap for the current identity.

    Calls run_type=gaps.next_open_canonical through the MCP boundary.

    Example:
      keyhole gaps next-open
    """
    emit(
        run_gaps_next_open(
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@gaps_app.command("claim")
def cmd_gaps_claim(
    gap_id: str = typer.Option(..., "--gap-id", help="Gap ID to claim (from `keyhole gaps list`)."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Claim a gap against the current subject repo and retrieve the claim token.

    Includes subject repo context (repo_remote, branch, commit_sha, repo_binding_id)
    in the claim request to bind the gap to the local governed repo.

    After claiming, use:
      keyhole governance-context create --gap-id <id> --claim-token <token>

    Do NOT follow claim with `keyhole workspace provision` — that flow is deprecated
    for downstream SDK/customer/forked repo workflows.

    Example:
      keyhole gaps claim --gap-id <gap_id>
    """
    emit(
        run_gaps_claim(
            gap_id=gap_id,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@gaps_app.command("revalidate")
def cmd_gaps_revalidate(
    gap_id: str = typer.Option(..., "--gap-id", help="Gap ID to revalidate (from `keyhole gaps list`)."),
    ctxpack_digest: str = typer.Option(..., "--ctxpack-digest", help="Context-pack digest from blocked_reasons.required_action.input."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Revalidate a gap against the current canonical context digest.

    Clears a STALE_REVALIDATION blocker so the gap becomes claimable.
    Calls run_type=gaps.revalidate through the MCP boundary.

    Example:
      keyhole gaps revalidate --gap-id <gap_id> --ctxpack-digest <digest>
    """
    emit(
        run_gaps_revalidate(
            gap_id=gap_id,
            ctxpack_digest=ctxpack_digest,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-PUBLIC-REPAIR-01: Workspace Lifecycle Commands
# ──────────────────────────────────────────────────────────────


@gaps_app.command("close")
def cmd_gaps_close(
    gap_id: str = typer.Option(..., "--gap-id", help="Gap ID to close through governed SDK evidence."),
    closure_reason: str = typer.Option(..., "--closure-reason", help="Closure reason."),
    closure_classification: str = typer.Option(..., "--closure-classification", help="Evidence-backed closure classification."),
    evidence_bundle_hash: str = typer.Option(..., "--evidence-bundle-hash", help="SHA-256 hash for the SDK evidence bundle."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    requested_by: str = typer.Option("", "--requested-by", help="Authenticated principal or operator label."),
    workspace_id: str = typer.Option("", "--workspace-id", help="Authenticated workspace id from whoami."),
    governed_run_id: str = typer.Option("", "--governed-run-id", help="Governed run id if available."),
    receipt_id: str = typer.Option("", "--receipt-id", help="Governed receipt id if available."),
    proof_id: str = typer.Option("", "--proof-id", help="Governed proof id if available."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Submit an SDK-originated governed gap closure request."""
    emit(
        run_gaps_close(
            gap_id=gap_id,
            closure_reason=closure_reason,
            closure_classification=closure_classification,
            evidence_bundle_hash=evidence_bundle_hash,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            requested_by=requested_by,
            workspace_id=workspace_id,
            governed_run_id=governed_run_id,
            receipt_id=receipt_id,
            proof_id=proof_id,
        ),
        use_json=use_json,
    )


@workspace_app.command("provision")
def cmd_workspace_provision(
    repo: str = typer.Option(..., "--repo", help="Public repo name (e.g. my-first-public-app)."),
    gap_id: str = typer.Option(..., "--gap-id", help="Gap ID from `keyhole gaps claim`."),
    claim_token: Optional[str] = typer.Option(None, "--claim-token", help="Claim token (optional — server authorizes via JWT identity)."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """DEPRECATED — provision is no longer used for downstream SDK/customer flows.

    Use ``keyhole governance-context create`` instead (SDK-CLIENT-30):

      keyhole governance-context create --gap-id <id> --claim-token <token>

    workspace.provision is retained for internal platform-maintenance workflows only.
    Normal forked/customer repo workflows must use governance-context create,
    which binds the gap to the subject repo without creating a persistent workspace.
    """
    typer.secho(
        "DEPRECATED: `keyhole workspace provision` is deprecated for downstream SDK/customer flows.\n"
        "Use: keyhole governance-context create --gap-id <id> --claim-token <token>\n"
        "(SDK-CLIENT-30: repo-as-workspace model)",
        fg=typer.colors.YELLOW,
        err=True,
    )
    emit(
        run_workspace_provision(
            repo=repo,
            gap_id=gap_id,
            claim_token=claim_token,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
            machine_mode=use_json,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-PUBLIC-REPAIR-01: Proof Submission Commands
# ──────────────────────────────────────────────────────────────


@proof_app.command("submit")
def cmd_proof_submit(
    invariant: str = typer.Option(..., "--invariant", help="Invariant ID to submit proof for (e.g. MY-FIRST-APP-INV-01)."),
    bundle: str = typer.Option("proof_bundle", "--bundle", help="Path to proof bundle directory."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    mcp_url: str = typer.Option(DEFAULT_RUNTIME_URL, "--mcp-url", envvar="KEYHOLE_MCP_URL", help="MCP boundary base URL."),
    keyhole_home: str = typer.Option("", "--keyhole-home", envvar="KEYHOLE_HOME", help="Keyhole home directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Submit a local proof bundle for governed verdict.

    Reads the local proof result for the given invariant, validates its shape,
    submits through run_type=proof.submit, and writes a local receipt artifact.

    Example:
      keyhole proof submit --invariant MY-FIRST-APP-INV-01
      keyhole proof submit --invariant MY-FIRST-APP-INV-01 --bundle ./proof_bundle
    """
    emit(
        run_proof_submit(
            invariant=invariant,
            bundle=bundle,
            repo_dir=repo_dir,
            mcp_url=mcp_url,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-PUBLIC-REPAIR-01: Receipt Verification Commands
# ──────────────────────────────────────────────────────────────


@receipt_app.command("verify")
def cmd_receipt_verify(
    invariant: str = typer.Option("", "--invariant", help="Invariant ID to verify receipt for. Omit to check all receipts."),
    bundle: str = typer.Option("proof_bundle", "--bundle", help="Path to proof bundle directory."),
    repo_dir: str = typer.Option(".", "--repo-dir", help="Repository root directory."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Verify local governed receipts against proof bundles.

    Loads the local receipt artifact(s) from proof_bundle/receipts/,
    cross-checks against the local proof result, and returns PASS or FAIL.
    This is a deterministic local integrity check — no network call.

    Example:
      keyhole receipt verify
      keyhole receipt verify --invariant MY-FIRST-APP-INV-01
    """
    emit(
        run_receipt_verify(
            invariant=invariant,
            bundle=bundle,
            repo_dir=repo_dir,
        ),
        use_json=use_json,
    )



# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-04: Governance Contract Validation
# ──────────────────────────────────────────────────────────────


@app.command("validate")
def cmd_validate(
    repo_dir: str = typer.Argument(
        ".",
        help="Repository directory to validate (default: current directory).",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="Validation mode: auto (detect posture), native (strict), advisory (always advisory).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Strict mode: elevate warnings to failures and run additional checks.",
    ),
    proof: bool = typer.Option(
        False,
        "--proof",
        help="Force local validation proof artifact emission even without --state-dir.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Suppress non-error output (next_steps, summary) on success.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        envvar="KEYHOLE_STATE_DIR",
        help="Tool-owned state directory for proof artifacts.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override Keyhole home directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Validate local governance contract and dependency schema.

    Reads keyhole.yaml, governance_contract.yaml, capability_passport.yaml,
    and dependencies.yaml if present.  Advisory-only for non-native repos.

    Exits 0 on PASS or WARN.  Exits 5 on REJECT.
    Never requires MCP connectivity.

    Examples:
      keyhole validate
      keyhole validate ./my-service
      keyhole validate --mode native
      keyhole validate --strict
      keyhole validate --proof --state-dir /tmp/kh-state
      keyhole validate --quiet --json
    """
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


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-21: Surface Negotiation
# ──────────────────────────────────────────────────────────────


@app.command("surfaces")
def cmd_surfaces(
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL to negotiate against.",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        envvar="KEYHOLE_STATE_DIR",
        help="Tool-owned state directory for negotiation artifacts.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override Keyhole home directory.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force fresh negotiation, ignoring any cached result.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect negotiated surface compatibility against the live MCP boundary.

    Fetches the live capabilities from the MCP boundary, classifies all
    surfaces as required / optional / transitional, and reports whether
    the client can operate at full, degraded, or blocked capability.

    Writes local negotiation artifacts to <state-dir>/compatibility/ when
    a state directory is configured.

    Exits 0 (PASS or DEGRADED).  Exits 5 if required surfaces are missing.
    Never requires a local governance contract.

    Examples:
      keyhole surfaces
      keyhole surfaces --mcp-url https://mcp.example.com
      keyhole surfaces --json
      keyhole surfaces --state-dir /tmp/kh-state --refresh
    """
    emit(
        run_surfaces(
            mcp_url=mcp_url,
            state_dir=state_dir,
            keyhole_home=keyhole_home,
            refresh=refresh,
        ),
        use_json=use_json,
    )


# ── keyhole passport ─────────────────────────────────────────────────────────


@passport_app.command("generate")
def cmd_passport_generate(
    repo_dir: str = typer.Argument(".", help="Repository directory to generate passport for."),
    write: bool = typer.Option(
        True,
        "--write/--no-write",
        help="Write capability_passport.yaml into the repo (default: write).",
    ),
    output: str = typer.Option(
        "",
        "--output",
        help="Override write path (absolute or relative).",
    ),
    state_dir: str = typer.Option(
        "",
        "--state-dir",
        envvar="KEYHOLE_STATE_DIR",
        help="Tool state directory for proof emission.",
    ),
    keyhole_home: str = typer.Option(
        "",
        "--keyhole-home",
        envvar="KEYHOLE_HOME",
        help="Override Keyhole home directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Generate a capability passport from declared local repo truth.

    Only works for native governed repos with valid declared capabilities.
    Foreign repos and repos without declared capabilities are rejected.
    Never requires MCP connectivity.

    Examples:
      keyhole passport generate
      keyhole passport generate ./my-service
      keyhole passport generate --no-write --json
    """
    emit(
        run_passport_generate(
            repo_path=repo_dir,
            write=write,
            output=output,
            state_dir=state_dir,
            keyhole_home=keyhole_home,
        ),
        use_json=use_json,
    )


@passport_app.command("show")
def cmd_passport_show(
    repo_dir: str = typer.Argument(".", help="Repository directory to read passport from."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Display the capability passport from the repo.

    Read-only.  Never generates or mutates.

    Examples:
      keyhole passport show
      keyhole passport show ./my-service --json
    """
    emit(
        run_passport_show(repo_path=repo_dir),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-01-C: Connection Identity Commands
# ──────────────────────────────────────────────────────────────


@app.command(name="connections")
def cmd_connections_list(
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """List visible MCP connections from the governed server."""
    emit(
        run_connections_list(mcp_url=mcp_url),
        use_json=use_json,
    )


@connection_app.command("inspect")
def cmd_connection_inspect(
    host: str = typer.Option("", "--host", help="Host identifier (e.g. vscode)."),
    connection_id: str = typer.Option("", "--connection-id", help="Connection ID."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect the active identity for a specific connection or host."""
    emit(
        run_connection_inspect(
            host=host,
            connection_id=connection_id,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@connection_app.command("lineage")
def cmd_connection_lineage(
    host: str = typer.Option("", "--host", help="Host identifier (e.g. vscode)."),
    connection_id: str = typer.Option("", "--connection-id", help="Connection ID."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Explain how the current connection identity came to be."""
    emit(
        run_connection_lineage(
            host=host,
            connection_id=connection_id,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@connection_app.command("rebind")
def cmd_connection_rebind(
    host: str = typer.Option("", "--host", help="Host identifier (e.g. vscode)."),
    connection_id: str = typer.Option("", "--connection-id", help="Connection ID."),
    profile: str = typer.Option("", "--profile", help="Target profile to rebind to."),
    yes: bool = typer.Option(False, "--yes", help="Confirm rebind without prompting."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Rebind a live host connection to a different profile."""
    if not yes and not use_json:
        typer.echo(
            f"You are about to rebind connection for "
            f"host '{host or connection_id}' to profile '{profile}'."
        )
        confirm = typer.prompt("Type REBIND to continue", default="")
        if confirm != "REBIND":
            typer.secho("Rebind cancelled.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        yes = True

    emit(
        run_connection_rebind(
            host=host,
            connection_id=connection_id,
            profile=profile,
            yes=yes,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


@connection_app.command("invalidate")
def cmd_connection_invalidate(
    host: str = typer.Option("", "--host", help="Host identifier (e.g. vscode)."),
    connection_id: str = typer.Option("", "--connection-id", help="Connection ID."),
    yes: bool = typer.Option(False, "--yes", help="Confirm invalidation without prompting."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Invalidate a stale or wrong-principal host connection."""
    if not yes and not use_json:
        typer.echo(
            f"You are about to invalidate connection for "
            f"host '{host or connection_id}'."
        )
        confirm = typer.prompt("Type INVALIDATE to continue", default="")
        if confirm != "INVALIDATE":
            typer.secho("Invalidation cancelled.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        yes = True

    emit(
        run_connection_invalidate(
            host=host,
            connection_id=connection_id,
            yes=yes,
            mcp_url=mcp_url,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-01-D: Host Management Commands
# ──────────────────────────────────────────────────────────────


@host_app.command("list")
def cmd_host_list(
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """List discovered IDE hosts and their Keyhole configuration status."""
    emit(run_host_list(), use_json=use_json)


@host_app.command("inspect")
def cmd_host_inspect(
    host: str = typer.Option(..., "--host", help="Host identifier (e.g. vscode, jetbrains)."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Inspect a specific host's Keyhole configuration."""
    emit(run_host_inspect(host=host), use_json=use_json)


@host_app.command("install")
def cmd_host_install(
    host: str = typer.Option(..., "--host", help="Host identifier (e.g. vscode, jetbrains)."),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    server_name: str = typer.Option(
        "keyhole",
        "--server-name",
        help="Name for the MCP server entry in host config.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing entry."),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Install Keyhole MCP credentials into a host IDE.

    INV-SDK-CLIENT-01-D-001: CLI is provisioner, NOT proxy.
    The host connects directly to the MCP boundary after install.
    """
    emit(
        run_host_install(
            host=host,
            mcp_url=mcp_url,
            server_name=server_name,
            force=force,
        ),
        use_json=use_json,
    )


@app.command(name="mcp-proxy")
def cmd_mcp_proxy(
    port: int = typer.Option(
        7878,
        "--port",
        envvar="KEYHOLE_MCP_PROXY_PORT",
        help="Local port for the proxy to listen on.",
    ),
    upstream: str = typer.Option(
        "",
        "--upstream",
        envvar="KEYHOLE_MCP_SSE_URL",
        help="Upstream MCP SSE endpoint URL. Defaults to $KEYHOLE_MCP_URL/sse.",
    ),
) -> None:
    """Local MCP HTTP/SSE proxy with automatic token refresh.

    Runs a real SSE server on localhost so VS Code and all agentic surfaces
    can connect using the standard HTTP transport without managing tokens.

    \b
    Configure in .vscode/mcp.json (on the Linux VM):
      {
        "servers": {
          "keyhole": {
            "type": "http",
            "url": "http://localhost:7878/sse"
          }
        }
      }

    Login once with 'keyhole login'. The proxy handles token refresh automatically.
    Keep running across sessions: systemctl --user enable --now keyhole-mcp-proxy.service
    """
    from keyhole_sdk.config import DEFAULT_BASE_URL
    effective_upstream = upstream or (DEFAULT_BASE_URL.rstrip("/") + "/sse")
    run_mcp_proxy(upstream=effective_upstream, port=port)


@host_app.command("attest")
def cmd_host_attest(
    host: str = typer.Option(
        "vscode",
        "--host",
        help="Host kind to attest (e.g. vscode, jetbrains).",
    ),
    integration: str = typer.Option(
        "keyhole",
        "--integration",
        help="Integration name within the host.",
    ),
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary URL.",
    ),
    realm: str = typer.Option(
        "kh-prod",
        "--realm",
        envvar="KEYHOLE_REALM",
        help="Identity realm.",
    ),
    workspace_scope: Optional[str] = typer.Option(
        None,
        "--workspace-scope",
        help="Optional workspace scope identifier.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Attest host identity via live whoami proof (SDK-CLIENT-23)."""
    emit(
        run_host_attest(
            host_kind=host,
            integration_name=integration,
            server_url=mcp_url,
            realm=realm,
            workspace_scope=workspace_scope,
        ),
        use_json=use_json,
    )


# ──────────────────────────────────────────────────────────────
# SDK-CLIENT-01-F: Browser OIDC Compatibility Commands
# ──────────────────────────────────────────────────────────────


@auth_app.command("browser-check")
def cmd_auth_browser_check(
    realm: str = typer.Option(
        "kh-prod",
        "--realm",
        envvar="KEYHOLE_REALM",
        help="Target identity realm (e.g. kh-prod, kh-dev, keyhole-mcp).",
    ),
    client_id: str = typer.Option(
        "keyhole-cli",
        "--client-id",
        envvar="KEYHOLE_CLIENT_ID",
        help="OIDC public client ID to validate.",
    ),
    auth_server: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Auth server base URL.",
    ),
    redirect_uri: Optional[str] = typer.Option(
        None,
        "--redirect-uri",
        help="Redirect URI to validate (e.g. http://127.0.0.1:33419/).",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Validate whether a browser OIDC client is compatible with the Keyhole auth boundary.

    Checks OIDC discovery, PKCE posture, redirect URI posture, passwordless
    browser continuation support, and detects unsupported proxy/detour paths.

    This command does NOT open a browser or attempt authentication.
    """
    emit(
        run_auth_browser_check(
            realm=realm,
            client_id=client_id,
            auth_server_url=auth_server,
            redirect_uri=redirect_uri,
        ),
        use_json=use_json,
    )


@auth_app.command("browser-support-bundle")
def cmd_auth_browser_support_bundle(
    realm: str = typer.Option(
        "kh-prod",
        "--realm",
        envvar="KEYHOLE_REALM",
        help="Target identity realm.",
    ),
    client_id: str = typer.Option(
        "keyhole-cli",
        "--client-id",
        envvar="KEYHOLE_CLIENT_ID",
        help="OIDC public client ID.",
    ),
    auth_server: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Auth server base URL.",
    ),
    redirect_uri: Optional[str] = typer.Option(
        None,
        "--redirect-uri",
        help="Redirect URI to capture (e.g. http://127.0.0.1:33419/).",
    ),
    failure_classification: Optional[str] = typer.Option(
        None,
        "--classification",
        help="Override failure classification (e.g. passwordless_browser_not_supported).",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Generate a deterministic support bundle for a browser auth failure.

    Captures OIDC discovery, client configuration, redirect posture, detour
    detection, compatibility verdict, and repair guidance into a repo-neutral
    artifact set at ~/.keyhole/auth/browser/<bundle-id>/.
    """
    emit(
        run_auth_browser_support_bundle(
            realm=realm,
            client_id=client_id,
            auth_server_url=auth_server,
            redirect_uri=redirect_uri,
            failure_classification=failure_classification,
        ),
        use_json=use_json,
    )


@auth_app.command("explain-browser")
def cmd_auth_explain_browser(
    bundle: str = typer.Option(
        ...,
        "--bundle",
        help="Path to the browser auth support bundle directory.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Explain a previously captured browser auth support bundle.

    Renders a concrete diagnosis, failure classification, and repair plan
    from the artifacts captured by `keyhole auth browser-support-bundle`.
    """
    emit(run_auth_explain_browser(bundle_path=bundle), use_json=use_json)


@auth_app.command("doctor")
def cmd_auth_doctor(
    mcp_url: str = typer.Option(
        DEFAULT_RUNTIME_URL,
        "--mcp-url",
        envvar="KEYHOLE_MCP_URL",
        help="MCP boundary base URL.",
    ),
    auth_server: str = typer.Option(
        DEFAULT_AUTH_SERVER,
        "--auth-server",
        envvar="KEYHOLE_AUTH_SERVER",
        help="Expected auth server base URL.",
    ),
    use_json: bool = typer.Option(False, "--json", help="Machine-readable JSON output."),
) -> None:
    """Diagnose CLI auth posture (SDK-CLIENT-29).

    Runs local checks (credential file, JWT diagnostics) and one
    authoritative server check (`/mcp/v1/whoami`).  JWT inspection is
    diagnostic only — the MCP boundary is the sole authority for actor
    truth.
    """
    result = run_auth_doctor(mcp_base_url=mcp_url, auth_server=auth_server)

    # Human-readable check rendering
    if not use_json:
        typer.secho("\nAuth doctor checks:", fg=typer.colors.CYAN, bold=True)
        for check in result.data.get("checks", []):
            status = check.get("status", "")
            color = {
                "pass": typer.colors.GREEN,
                "warn": typer.colors.YELLOW,
                "fail": typer.colors.RED,
            }.get(status, typer.colors.WHITE)
            marker = {"pass": "✓", "warn": "!", "fail": "✗"}.get(status, "·")
            typer.secho(f"  {marker} [{status:>4}] {check.get('name')}", fg=color)
            detail = check.get("detail")
            if detail:
                typer.echo(f"      {detail}")
        typer.echo("")

    emit(result, use_json=use_json)


if __name__ == "__main__":
    app()
