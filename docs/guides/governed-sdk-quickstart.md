# Governed SDK Quickstart

This guide is the fastest public path for a new builder to go from a fresh SDK
clone to a live governed receipt.

Current public posture: the governed proof path is production-backed, while the
SDK/CLI should be treated as technical preview / early access until the release
gate in `docs/launch-readiness.md` passes from a clean clone.

## Prerequisites

- Python 3.10 to 3.12
- Git
- PowerShell on Windows or Bash/WSL on Linux/macOS
- Network access to `https://mcp.keyholesolution.com`
- Editable installs of `keyhole-sdk` and `keyhole-cli`
- Device-login access for `keyhole login --flow device`

Local validation is not governance. Fake-boundary tests are not governance.
Live governance requires a real MCP receipt.

## Install

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e packages/python/keyhole-sdk -e packages/python/keyhole-cli pytest
keyhole version
```

Bash / WSL:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e packages/python/keyhole-sdk -e packages/python/keyhole-cli pytest
keyhole version
```

## Login

```powershell
keyhole login --flow device --force
keyhole whoami --json
```

Expected identity fields:

```text
success=true
mode=real
tenant_id
org_id
cohort_id
workspace_id
```

## Set The MCP Boundary

PowerShell:

```powershell
$env:KEYHOLE_MCP_URL = "https://mcp.keyholesolution.com"
Remove-Item Env:\KEYHOLE_MCP_TOKEN -ErrorAction SilentlyContinue
```

Bash:

```bash
export KEYHOLE_MCP_URL="https://mcp.keyholesolution.com"
unset KEYHOLE_MCP_TOKEN
```

Prefer the saved device-login credential over pasting bearer tokens. Do not
commit or share tokens.

## Use The Existing Example

`examples/second-governed-app` is the blessed public launch path for new
external builders. `my-first-app` is retained for legacy first-app and
server-boundary evidence work; do not use it as the public launch quickstart.

Current validate syntax uses a positional repo path:

```powershell
keyhole validate examples\second-governed-app
keyhole governed run --repo-dir examples\second-governed-app --json
keyhole governed status --repo-dir examples\second-governed-app --last --json
keyhole governed receipt --repo-dir examples\second-governed-app --last --json
```

Success means the governed receipt includes:

```text
success=true
governed=true
event_spine_evidence=true
governance_verdict=ACCEPT
drift_state=non_drifted
resolved_gap_id
claim_id / claim_ref
governance_context_id
mcp_event_id / mcp_event_pointer
receipt_id
proof_id
```

## Windows Launcher Diagnostics

If PowerShell resolves an older global `keyhole.exe`, the CLI can appear to
ignore a fresh editable install or miss dependencies such as `PyYAML`. Check
the resolved executable before debugging the SDK:

```powershell
Get-Command keyhole -All
where.exe keyhole
keyhole version
python -m pip show keyhole-cli keyhole-sdk PyYAML
```

Prefer the active virtual environment launcher:

```powershell
.\.venv\Scripts\keyhole.exe version
.\.venv\Scripts\keyhole.exe validate examples\second-governed-app
```

Do not copy machine-specific launcher paths from another developer's
workstation into docs, scripts, or support instructions.

## Scaffold A Fresh Repo

```powershell
mkdir scratch-governed-app
cd scratch-governed-app
keyhole init vertical
keyhole validate
keyhole governed run --repo-dir . --json
```

A freshly scaffolded repo may validate locally before it has a claimable live
gap. Live governance still requires MCP gap discovery or materialization.

## Dry Run And Explain

Use this to inspect what the CLI would do without mutating MCP:

```powershell
keyhole governed run --repo-dir examples\second-governed-app --dry-run --explain --json
```

Dry-run may perform:

- Local declaration inspection
- Capabilities discovery
- Read-only gap discovery

Dry-run must not perform:

- `gaps.submit`
- `gaps.claim`
- `governance.context.create`
- `context.compile`
- `governed.realize`

`--explain` includes repo identity, declaration digests, candidate gap filters,
the selected gap when one exists, the planned MCP operations, and the local
state path.

## Interpret The Receipt

A live governed receipt should include:

```text
governed=true
event_spine_evidence=true
governance_verdict=ACCEPT
drift_state=non_drifted
resolved_gap_id=<canonical gap_* id>
claim_id / claim_ref=<real>
governance_context_id=<real>
mcp_event_id / mcp_event_pointer=<real>
receipt_id=<real>
proof_id=<real>
```

If those fields are missing, the proof is not closure-ready.

## Generated Artifacts

The governed CLI stores non-secret local run state under:

```text
<repo>/.keyhole/governed-runs/
```

That state must not contain tokens. It is local execution state and should not normally be committed unless a sanitized pointer policy exists.

Before publishing or handing off a release candidate, run:

```powershell
.\scripts\public-release-gate.ps1
```

If Windows script policy blocks direct execution, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\public-release-gate.ps1
```

After device login, add `-IncludeLiveProof` to verify live identity, surface
negotiation, launch doctor, governed status, and governed receipt.

## What Is Not Governance

- `keyhole validate` is local-only validation.
- Fake-boundary unit tests prove SDK behavior, not production governance.
- Diagnostic overrides are troubleshooting tools, not closure proof.
- The happy path for builders is `keyhole governed run`, not ad hoc verifier scripts.
