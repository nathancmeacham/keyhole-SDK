"""Shared result model and output rendering for keyhole-cli.

Every CLI command produces a ``CommandResult``, which is the single
truth source for both human and JSON rendering.  Exit codes are
derived deterministically from the result.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import typer


# --------------------------------------------------------------
# Exit codes - deterministic and documented
# --------------------------------------------------------------
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_UNSUPPORTED = 2
EXIT_RUNTIME_UNAVAILABLE = 3
EXIT_INVALID_INPUT = 4
EXIT_CONTRACT_FAILURE = 5


class CommandResult:
    """Structured result produced by every CLI command.

    Both ``render_human`` and ``render_json`` read from the same data,
    so outputs are always semantically equivalent.
    """

    def __init__(
        self,
        command: str,
        success: bool,
        *,
        exit_code: int = EXIT_SUCCESS,
        data: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        next_steps: Optional[List[str]] = None,
        summary: Optional[str] = None,
    ) -> None:
        self.command = command
        self.success = success
        self.exit_code = exit_code
        self.data: Dict[str, Any] = data or {}
        self.warnings: List[str] = warnings or []
        self.next_steps: List[str] = next_steps or []
        self.summary = summary
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Full machine-readable dict for JSON output."""
        base: Dict[str, Any] = {
            "command": self.command,
            "success": self.success,
        }
        base.update(self.data)
        if self.warnings:
            base["warnings"] = self.warnings
        if self.next_steps:
            base["next_steps"] = self.next_steps
        if self.summary:
            base["summary"] = self.summary
        base["timestamp"] = self.timestamp
        return base


def emit(result: CommandResult, *, use_json: bool) -> None:
    """Render a ``CommandResult`` to the terminal.

    When *use_json* is ``True``, output is pure JSON (no ANSI).
    Otherwise, human-friendly text is written to stdout.
    """
    if use_json:
        typer.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _render_human(result)
    raise typer.Exit(code=result.exit_code)


def _render_human(result: CommandResult) -> None:
    """Write a concise human-readable summary to stdout."""
    ok = _glyph("OK", "OK") if result.success else _glyph("✗", "ERROR")
    color = typer.colors.GREEN if result.success else typer.colors.RED
    typer.secho(f"{ok} {result.command}", fg=color, bold=True)

    if result.summary:
        typer.echo(f"  {result.summary}")

    for key, value in result.data.items():
        if isinstance(value, (dict, list)):
            continue  # skip complex sub-structures in human view
        typer.echo(f"  {key}: {value}")

    # SDK-CLIENT-23 sectionE: Render host identity coherence section loudly
    hc = result.data.get("host_coherence")
    if hc:
        _render_host_coherence(hc)

    if result.warnings:
        typer.secho("  Warnings:", fg=typer.colors.YELLOW)
        for w in result.warnings:
            typer.echo(f"    - {w}")

    if result.next_steps:
        typer.echo("  Next steps:")
        for s in result.next_steps:
            typer.echo(f"    {_glyph('->', '->')} {s}")


def _glyph(preferred: str, fallback: str) -> str:
    """Return a terminal-safe glyph for human output."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        preferred.encode(encoding)
    except UnicodeEncodeError:
        return fallback
    return preferred


# --------------------------------------------------------------
# SDK-CLIENT-23 sectionE: Structured host identity coherence rendering
# --------------------------------------------------------------

_VERDICT_COLORS = {
    "ACCEPT_MATCH": typer.colors.GREEN,
    "ACCEPT_INTENTIONAL_SPLIT": typer.colors.YELLOW,
    "WARNING_NO_HOST_ATTESTATION": typer.colors.YELLOW,
    "WARNING_STALE_HOST_ATTESTATION": typer.colors.YELLOW,
    "WARNING_UNKNOWN_HOST_IDENTITY": typer.colors.YELLOW,
    "REJECT_HOST_CONFLICT": typer.colors.RED,
}


def _render_host_coherence(hc: Dict[str, Any]) -> None:
    """Render the host identity coherence section for human output.

    Must be noisy, structured, and prescriptive per SDK-CLIENT-23 sectionE/H.
    """
    typer.echo("")
    typer.secho(
        "  -----------------------------------------------",
        fg=typer.colors.CYAN,
    )
    typer.secho(
        "  -         Host Identity Coherence              -",
        fg=typer.colors.CYAN,
    )
    typer.secho(
        "  -----------------------------------------------",
        fg=typer.colors.CYAN,
    )

    # Per-attestation host detail
    attestations = hc.get("attestations", [])
    if attestations:
        for att in attestations:
            host = att.get("host_display_name") or att.get("host_kind", "unknown")
            integration = att.get("integration_name", "")
            principal = att.get("effective_principal", "unknown")
            realm = att.get("realm", "")
            proof = att.get("proof_method", "")
            confidence = att.get("confidence", "unknown")
            fresh = att.get("fresh", False)

            typer.echo(f"  Host: {host} / {integration}")
            typer.echo(f"    effective host principal : {principal}")
            typer.echo(f"    realm                   : {realm}")
            typer.echo(f"    proof                   : {proof}")
            freshness_label = "fresh" if fresh else "STALE"
            fresh_color = typer.colors.GREEN if fresh else typer.colors.YELLOW
            typer.echo("    freshness               : ", nl=False)
            typer.secho(freshness_label, fg=fresh_color)
            typer.echo(f"    confidence              : {confidence}")
    else:
        typer.secho("  No host attestations found.", fg=typer.colors.YELLOW)

    # CLI identity
    cli_principal = hc.get("cli_principal", "")
    typer.echo("")
    typer.echo("  CLI Identity")
    if cli_principal:
        typer.echo(f"    principal               : {cli_principal}")
    elif hc.get("cli_credentials_exist"):
        typer.secho(
            "    principal               : (credentials exist - run 'keyhole whoami' to verify)",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.secho("    principal               : (none - not logged in)", fg=typer.colors.YELLOW)

    # Verdict - loud and colored
    verdict = hc.get("verdict", "UNKNOWN")
    v_color = _VERDICT_COLORS.get(verdict, typer.colors.WHITE)
    description = hc.get("description", "")

    typer.echo("")
    typer.echo("  Verdict")
    typer.echo("    ", nl=False)
    typer.secho(verdict, fg=v_color, bold=True)
    if description:
        typer.echo(f"    {description}")

    # Impact line for conflicts
    if verdict == "REJECT_HOST_CONFLICT" and attestations:
        host_princ = attestations[0].get("effective_principal", "?")
        typer.secho(
            f"    impact: IDE tool calls act as {host_princ} "
            f"while CLI/SDK calls would bind as {cli_principal}",
            fg=typer.colors.RED,
        )

    # Override status
    if hc.get("has_override"):
        typer.secho("    override: active (split-identity allowed)", fg=typer.colors.YELLOW)

    # Fix steps - prescriptive and numbered
    fix_steps = hc.get("fix_steps", [])
    if fix_steps:
        typer.echo("")
        typer.secho("  Remediation Steps:", bold=True)
        for i, step in enumerate(fix_steps, 1):
            typer.echo(f"    {i}. {step}")

    typer.echo("")
