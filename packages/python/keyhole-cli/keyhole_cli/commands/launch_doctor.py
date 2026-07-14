"""Public launch readiness checks for the governed SDK happy path."""
from __future__ import annotations

import os
import tempfile
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Dict, List

from keyhole_cli.commands.governed_flow_cmd import _client
from keyhole_cli.commands.validate_cmd import run_validate
from keyhole_cli.commands.whoami import run_whoami
from keyhole_cli.result import CommandResult, EXIT_FAILURE, EXIT_SUCCESS
from keyhole_sdk.config import DEFAULT_BASE_URL
from keyhole_sdk.governed_demo import GovernedDemoError
from keyhole_sdk.governed_flow import read_repo_declaration


REQUIRED_DECLARATIONS = (
    "keyhole.yaml",
    "governance_contract.yaml",
    "capability_passport.yaml",
    "dependencies.yaml",
)


def run_launch_doctor(
    *,
    repo_dir: str = ".",
    mcp_url: str = DEFAULT_BASE_URL,
) -> CommandResult:
    repo = Path(repo_dir).resolve()
    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, **data: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), **data})

    add(
        "version",
        True,
        cli_version=_pkg("keyhole-cli"),
        sdk_version=_pkg("keyhole-sdk"),
    )
    add("mcp_url", bool(mcp_url), mcp_url=mcp_url)

    whoami = run_whoami(mcp_base_url=mcp_url)
    add(
        "login",
        whoami.success,
        mode=whoami.data.get("mode", ""),
        actor_envelope_present=whoami.data.get("actor_envelope_present", False),
        summary=whoami.summary,
    )

    missing = [name for name in REQUIRED_DECLARATIONS if not (repo / name).exists()]
    add("governance_files", not missing, repo_dir=str(repo), missing=missing)

    declaration: Any = None
    try:
        declaration = read_repo_declaration(repo)
        add(
            "repo_facts",
            True,
            repo_name=declaration.repo_name,
            repo_remote=declaration.repo_remote,
            commit_sha=declaration.commit_sha,
            branch=declaration.branch,
            capability_id=declaration.capability_id,
            repo_class=declaration.repo_class,
        )
        dependency_entries = declaration.native_artifacts.get("dependencies", {}).get("dependencies", [])
        missing_capability = [
            idx for idx, dep in enumerate(dependency_entries)
            if not isinstance(dep, dict) or not str(dep.get("capability") or "").strip()
        ]
        add("dependency_capability_fields", not missing_capability, missing_indexes=missing_capability)
    except Exception as exc:  # noqa: BLE001
        add("repo_facts", False, error_class=type(exc).__name__, summary=str(exc))
        add("dependency_capability_fields", False, summary="Repo declaration could not be read.")

    validation = run_validate(repo_path=str(repo), quiet=True)
    add("local_invariants", validation.success, status=validation.data.get("status", ""), issues=validation.data.get("issues", []))

    try:
        state_dir = repo / ".keyhole" / "launch-doctor"
        state_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=state_dir, delete=True) as handle:
            handle.write("ok")
        add("keyhole_writable", True, path=str(repo / ".keyhole"))
    except Exception as exc:  # noqa: BLE001
        add("keyhole_writable", False, error_class=type(exc).__name__, summary=str(exc))

    ignore_text = _read_ignore(repo / ".gitignore") + "\n" + _read_ignore(Path.cwd() / ".gitignore")
    add(
        "ignore_posture",
        ".keyhole/" in ignore_text and "proof_bundle/" in ignore_text,
        required=[".keyhole/", "proof_bundle/"],
    )

    gap_ok = False
    gap_detail: Dict[str, Any] = {}
    if whoami.success and declaration is not None:
        try:
            client = _client(
                mcp_url=mcp_url,
                runtime_url=os.environ.get("KEYHOLE_RUNTIME_URL", "http://localhost:8080"),
                story_id=declaration.story_id,
                capability_id=declaration.capability_id,
                repo_class=declaration.repo_class,
                gap_id="",
            )
            client.inspect_repo(repo, persist_state=False)
            client.discover()
            gap_id = client._resolve_gap_id(repo)
            gap_ok = bool(gap_id)
            gap_detail = {"resolved_gap_id": gap_id, "gap_id_source": client.gap_id_source}
        except GovernedDemoError as exc:
            gap_detail = {"error_class": type(exc).__name__, "summary": str(exc)}
        except Exception as exc:  # noqa: BLE001
            gap_detail = {"error_class": type(exc).__name__, "summary": str(exc)}
    add("claimable_gap_availability", gap_ok, **gap_detail)

    ok = all(check["ok"] for check in checks)
    return CommandResult(
        command="keyhole doctor launch",
        success=ok,
        exit_code=EXIT_SUCCESS if ok else EXIT_FAILURE,
        summary="Launch readiness passed." if ok else "Launch readiness failed.",
        data={
            "repo_dir": str(repo),
            "mcp_url": mcp_url,
            "checks": checks,
            "generated_state_is_local_only": True,
            "proof_level": "live_mcp_readiness" if gap_ok else "local_plus_auth_readiness",
        },
        next_steps=[] if ok else [
            "Run keyhole login --flow device --force if login or live MCP checks failed.",
            "Run keyhole validate <repo> to inspect local declaration issues.",
            "Run keyhole gaps list --json to inspect claimable gaps if gap discovery failed.",
        ],
    )


def _pkg(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "unknown"


def _read_ignore(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""
