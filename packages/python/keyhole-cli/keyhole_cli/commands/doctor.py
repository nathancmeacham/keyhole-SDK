"""`keyhole doctor` — environment diagnosis and minimal repair guidance.

CE-V5-S41-08: Full structured diagnostics, root-failure classification,
minimal repair plan, machine-readable repair JSON, and
verification-after-repair flow.

SDK-CLIENT-23 §E: Host identity coherence reporting.

Backward compatible: run_doctor() still returns CommandResult.
"""

from __future__ import annotations

from keyhole_cli.doctor.contract import OperatingMode
from keyhole_cli.doctor.facts import collect_environment_facts
from keyhole_cli.doctor.handler import run_doctor_evaluation, run_doctor_verify
from keyhole_cli.profile import detect_profile
from keyhole_cli.result import (
    CommandResult,
    EXIT_SUCCESS,
    EXIT_FAILURE,
    EXIT_UNSUPPORTED,
)
from keyhole_sdk.auth_bootstrap.credential_store import CredentialStore
from keyhole_sdk.doctor.models import CoherenceVerdict
from keyhole_sdk.host.attestation_store import (
    load_attestations,
    load_identity_policy,
    load_principal_hint,
)
from keyhole_sdk.host.coherence_engine import classify_coherence


def run_doctor(
    *,
    mode: str = "auto",
    runtime_url: str = "",
    verify: bool = False,
    previous_diagnostic_ref: str = "",
    repair_plan_ref: str = "",
    goal: str = "",
    mcp_url: str = "",
) -> CommandResult:
    """Execute environment diagnosis and return structured result.

    When *verify* is True, runs verification-after-repair mode.
    """
    profile = detect_profile()
    profile_data = {
        "supported": profile.supported,
        "detected_profile": profile.detected_profile,
        "required_checks": profile.required_checks,
        "failed_checks": profile.failed_checks,
    }

    if not profile.supported:
        return CommandResult(
            command="doctor",
            success=False,
            exit_code=EXIT_UNSUPPORTED,
            data=profile_data,
            next_steps=profile.next_steps,
            summary="Environment doctor: unsupported profile",
        )

    op_mode = OperatingMode(mode)

    facts = collect_environment_facts(
        runtime_url=runtime_url,
        skip_runtime_check=(not runtime_url),
        mcp_url=mcp_url,
    )

    if verify:
        result = run_doctor_verify(
            facts,
            mode=op_mode,
            previous_diagnostic_ref=previous_diagnostic_ref,
            repair_plan_ref=repair_plan_ref,
        )
    else:
        result = run_doctor_evaluation(
            facts,
            mode=op_mode,
            goal=goal,
        )

    ok = result.get("ok", False)
    result.update(profile_data)

    # Build human-readable summary
    effective_mode = result.get("mode", mode)
    verdict = result.get("verdict", "UNKNOWN")
    reason_codes = result.get("reason_codes", [])

    auto_promoted = "DOCTOR_AUTO_PROMOTED_TO_GOVERNED" in reason_codes
    boundary_live = "DOCTOR_MCP_BOUNDARY_REACHABLE" in reason_codes

    if ok:
        summary = f"Environment doctor: {verdict} ({effective_mode} mode)"
        if auto_promoted:
            summary += " [auto-promoted from auto]"
    else:
        root_groups = result.get("root_failure_groups", [])
        n_root = len(root_groups)
        summary = (
            f"Environment doctor: {verdict} ({effective_mode} mode) — "
            f"{n_root} root failure(s) identified"
        )

    # Next steps from repair plan + provisioning
    next_steps = []
    repair_plan = result.get("repair_plan")
    if repair_plan and repair_plan.get("steps"):
        for step in repair_plan["steps"]:
            desc = step.get("description", "")
            cmd = step.get("command", "")
            if cmd and not cmd.startswith("http"):
                next_steps.append(f"{desc}: {cmd}")
            else:
                next_steps.append(desc)

    # Auto-suggest provisioning when MCP boundary is live
    if boundary_live:
        if not any("whoami" in s for s in next_steps):
            next_steps.append(
                "Verify CLI identity: keyhole whoami"
            )

    # SDK-CLIENT-23 §E: Host identity coherence report
    coherence_data = _build_coherence_report()
    if coherence_data:
        result["host_coherence"] = coherence_data
        verdict_val = coherence_data.get("verdict", "")
        if verdict_val == CoherenceVerdict.REJECT_HOST_CONFLICT.value:
            summary += " | HOST CONFLICT DETECTED"
            # fix_steps rendered inside the coherence section — not duplicated here
        elif verdict_val == CoherenceVerdict.ACCEPT_INTENTIONAL_SPLIT.value:
            summary += " | split-identity override active"
        elif verdict_val == CoherenceVerdict.WARNING_STALE_HOST_ATTESTATION.value:
            next_steps.append("Host attestation is stale. Run: keyhole host attest")
        elif verdict_val == CoherenceVerdict.WARNING_NO_HOST_ATTESTATION.value:
            if boundary_live:
                next_steps.append("No host attestation found. Run: keyhole host attest")
    elif boundary_live:
        next_steps.append("After identity is verified, run: keyhole host attest")

    # SDK-CLIENT-24 §9.8: Runtime contract section (advisory)
    runtime_contract_data = _build_runtime_contract_report(mcp_url=mcp_url)
    if runtime_contract_data:
        result["runtime_contract"] = runtime_contract_data

    return CommandResult(
        command="doctor",
        success=ok,
        exit_code=EXIT_SUCCESS if ok else EXIT_FAILURE,
        data=result,
        next_steps=next_steps,
        summary=summary,
    )


def _build_coherence_report():
    """SDK-CLIENT-23 §E: Build host identity coherence section.

    Returns dict or None if no meaningful data to report.
    """
    has_session = False
    try:
        store = CredentialStore()
        session = store.load()
        has_session = session is not None
    except Exception:
        pass

    # Determine CLI principal — prefer the hint file written at login time
    cli_principal = load_principal_hint()

    try:
        attestations = load_attestations()
        override = load_identity_policy()
    except Exception:
        attestations = []
        override = None

    # Show coherence section whenever credentials exist —
    # even with no hint/attestations, warn about missing attestations
    if not has_session and not cli_principal and not attestations:
        return None

    # When session exists but no principal hint, note credentials are
    # present but identity hasn't been verified through whoami yet
    if has_session and not cli_principal:
        cli_principal = ""  # coherence engine handles empty principal

    coherence = classify_coherence(
        cli_principal=cli_principal,
        attestations=attestations,
        override=override,
    )

    report = coherence.to_dict()

    # Flag for renderer: credentials exist but principal is unverified
    if has_session and not report.get("cli_principal"):
        report["cli_credentials_exist"] = True

    # Add per-attestation detail for doctor rendering
    report["attestations"] = []
    for att in attestations:
        report["attestations"].append({
            "host_kind": att.host_kind,
            "host_display_name": att.host_display_name,
            "integration_name": att.integration_name,
            "effective_principal": att.effective_principal,
            "realm": att.realm,
            "proof_method": att.proof_method,
            "confidence": att.confidence.value,
            "fresh": att.is_fresh(),
            "observed_at": att.observed_at,
            "expires_at": att.expires_at,
        })

    return report


def _build_runtime_contract_report(*, mcp_url: str = ""):
    """SDK-CLIENT-24 §9.8: Build runtime contract diagnostic section.

    Reads runtime profiles from capabilities (best-effort), collects local
    diagnostics, and reports without claiming canonical trust. Never fails
    the doctor run; missing Docker is advisory only (INVARIANT-5).
    """
    try:
        from keyhole_sdk.discovery.client import CapabilitiesClient
        from keyhole_sdk.runtime_contract import (
            CONTRACT_VERSION,
            collect_diagnostics,
        )
        from keyhole_sdk.runtime_contract.client import _extract_runtime_block
    except Exception:  # noqa: BLE001
        return None

    diag = collect_diagnostics()
    profiles_summary = []
    canonical_profile_id = ""
    external_profile_id = ""
    boundary_reachable = False

    if mcp_url:
        try:
            with CapabilitiesClient(base_url=mcp_url) as client:
                caps = client.fetch()
            boundary_reachable = True
            block = _extract_runtime_block(caps.raw)
            for item in block.get("profiles") or []:
                if not isinstance(item, dict):
                    continue
                pid = str(item.get("profile_id") or item.get("id") or "")
                kind = str(item.get("kind", ""))
                canonical = bool(item.get("canonical", False))
                profiles_summary.append(
                    {"profile_id": pid, "kind": kind, "canonical": canonical}
                )
                if canonical and kind == "container":
                    canonical_profile_id = pid
                if kind == "external" and not external_profile_id:
                    external_profile_id = pid
        except Exception:  # noqa: BLE001
            boundary_reachable = False

    return {
        "contract_version": CONTRACT_VERSION,
        "boundary_reachable": boundary_reachable,
        "canonical_profile_id": canonical_profile_id,
        "external_profile_id": external_profile_id,
        "profiles": profiles_summary,
        "diagnostics": {
            "container_runtime_detected": diag.container_runtime_detected,
            "container_runtime_kind": diag.container_runtime_kind,
            "inside_container": diag.inside_container,
            "local_venv_present": diag.local_venv_present,
            "local_venv_path": diag.local_venv_path,
            "local_venv_canonical": diag.local_venv_canonical,
            "platform": diag.platform,
            "python_version": diag.python_version,
        },
        "advisory": (
            "Docker is optional for SDK runtime contract discovery; "
            "trust classification is the boundary's sole authority."
        ),
    }
