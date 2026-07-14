# Public Release Sanitization

The Keyhole SDK intentionally targets the live Keyhole MCP boundary for public proof and discovery.

The live MCP endpoint is not a secret:

```text
https://mcp.keyholesolution.com
```

This repository does not include credentials, generated proof bundles, local governance state, historical receipts, or operator probe scripts.

Safe discovery and self-inspection may use the canonical MCP endpoint. Authenticated governed operations require explicit user login or token configuration.

Generated `.keyhole/` and `proof_bundle/` outputs are local runtime artifacts and must not be committed.

Public safety rules:

- Public live boundary: allowed.
- Public credentials: forbidden.
- Public generated operational state: forbidden.
- Public mutable live operations without explicit auth: forbidden.

Recommended public flow:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e packages/python/keyhole-sdk -e packages/python/keyhole-cli pytest
keyhole version
keyhole login --flow device --force
keyhole whoami --json
```

For live governed proof:

```powershell
$env:KEYHOLE_MCP_URL = "https://mcp.keyholesolution.com"
keyhole validate examples\second-governed-app
keyhole doctor launch --repo-dir examples\second-governed-app --json
keyhole governed run --repo-dir examples\second-governed-app --json
keyhole governed status --repo-dir examples\second-governed-app --last --json
keyhole governed receipt --repo-dir examples\second-governed-app --last --json
```

`examples/second-governed-app` is the blessed public launch path.
`my-first-app` is retained for legacy first-app/server-boundary evidence and
must not be documented as the generic builder quickstart.

If Windows resolves an unexpected CLI executable, diagnose the launcher before
debugging the SDK:

```powershell
Get-Command keyhole -All
where.exe keyhole
keyhole version
python -m pip show keyhole-cli keyhole-sdk PyYAML
.\.venv\Scripts\keyhole.exe version
```

Password/ROPC login is dev/test-only and disabled by default. To use it in a local development environment, set:

```powershell
$env:KEYHOLE_ENABLE_DEV_PASSWORD_LOGIN = "1"
```

## Release Gate

Before publishing, run the local public release gate from a clean working tree:

```powershell
.\scripts\public-release-gate.ps1
```

If Windows script policy blocks direct execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\public-release-gate.ps1
```

For a release-candidate live proof after device login:

```powershell
.\scripts\public-release-gate.ps1 -IncludeLiveProof
```

The gate covers editable package install, wheel build smoke, `tests/unit`,
validation for `examples/second-governed-app` and `my-first-app`, public text
sanitation, and generated-state checks. Live proof also verifies `whoami`,
surface negotiation, launch doctor, governed status, and governed receipt.
Use `-RunGoverned` only when a new live governed receipt is intended.

If local generated proof state exists because of operator testing, the gate
will stop by default. Passing `-AllowLocalGeneratedState` is acceptable for
diagnostics, but publishing requires those artifacts to be absent from the
release tree and from Git.
