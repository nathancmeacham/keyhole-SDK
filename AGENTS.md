# Agent Instructions

This repository is the public Keyhole SDK/developer kit. Agents should be able
to prove the public path from a fresh clone without private platform source,
hidden local state, or machine-specific launcher paths.

## First Read

Start here:

1. `README.md`
2. `docs/guides/governed-sdk-quickstart.md`
3. `docs/guides/governed-sdk-troubleshooting.md`
4. `docs/AGENT.md`

## Non-Negotiable Boundary Rules

- Do not use private Keyhole platform source as truth.
- Do not mock live-governance acceptance.
- Do not invent governance outcomes client-side.
- Do not commit generated `.keyhole/`, `proof_bundle/`, credentials, tokens, or local receipts.
- Use the live MCP boundary for governed proof: `https://mcp.keyholesolution.com`.
- After authentication, run `keyhole whoami --json` before write-bearing or proof-bearing work.

## Blessed Public Launch Path

`examples/second-governed-app` is the blessed public launch example.
`my-first-app` is retained for legacy first-app and server-boundary evidence
work, not as the generic public quickstart.

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e packages/python/keyhole-sdk -e packages/python/keyhole-cli pytest

.\.venv\Scripts\keyhole.exe version
.\.venv\Scripts\keyhole.exe login --flow device --force
.\.venv\Scripts\keyhole.exe whoami --json

.\.venv\Scripts\keyhole.exe validate examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe doctor launch --repo-dir examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe governed run --repo-dir examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe governed status --repo-dir examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe governed receipt --repo-dir examples\second-governed-app --json
```

Acceptance requires:

- `success=true`
- `governed=true`
- `event_spine_evidence=true`
- `governance_verdict=ACCEPT`
- `drift_state=non_drifted`
- `governance_context_id` present
- `mcp_event_id` or `mcp_event_pointer` present
- `proof_id` present
- `receipt_id` present

## Windows Launcher Diagnostics

If a command behaves as if dependencies or new commands are missing, diagnose
launcher resolution before changing code:

```powershell
Get-Command keyhole -All
where.exe keyhole
keyhole version
python -m pip show keyhole-cli keyhole-sdk PyYAML
.\.venv\Scripts\keyhole.exe version
```

Prefer the active venv launcher. Never document another developer's absolute
launcher path.

## Validation Before Claiming Done

For code or docs that affect public launch:

```powershell
.\.venv\Scripts\keyhole.exe validate examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe validate my-first-app --json
python -m pytest tests/unit -q
```

Before publishing or finalizing, also search for generated state and local-path
confusion:

```powershell
rg -n "anaconda3|C:\\Users\\natha|\\.local\\bin|keyhole login --device|governed run --repo-dir \\.\\my-first-app|repo register --path my-first-app|context compile --repo-dir my-first-app|pyyaml is a soft dependency|not in pyproject\\.toml" README.md docs packages my-first-app examples tests scripts -g "!*__pycache__*"
```

No hits should remain except intentionally redacted evidence paths.
