# Governed SDK Troubleshooting

Use these commands first when a governed run does not finish cleanly:

```powershell
keyhole governed status --repo-dir <repo> --last --json
keyhole governed resume --repo-dir <repo> --last --json
keyhole governed receipt --repo-dir <repo> --last --json
```

## Failure Guide

| Failure | Meaning | Fix |
|---------|---------|-----|
| `Session expired` | Device credential expired | `keyhole login --flow device --force` |
| `MCP capabilities missing operation` | Server surface not deployed or SDK parser stale | Recheck `GET /mcp/v1/capabilities`, then update SDK or server mapping |
| `GAP_NOT_FOUND` | No canonical gap discoverable | Server gap materialization or discovery is still needed |
| `CLAIM_NOT_FOUND` | Context create was attempted without an active claim | Use `gaps.claim`; the SDK/CLI should do this automatically when supported |
| `EXECUTION_SCOPE_NOT_GRANTED` | Identity lacks the scope to perform the run | Backend or identity scope issue |
| `INVALID_PARAMETERS` | Payload shape mismatch or server dropped a required field | Inspect the request path and poll the run status for details |
| `RUN_NOT_FOUND` | Async run was not materialized or has expired | Server async run store issue; local state is preserved for debugging |
| `INTERNAL_ERROR` | Server bug | Capture `correlation_id` and report it |
| `event_spine_evidence=false` | No real upstream evidence was returned | Not closure-ready |
| missing `mcp_event_id` | Receipt is incomplete | Not closure-ready |
| `MULTIPLE_GAP_CANDIDATES` | Gap discovery is ambiguous | Server needs deterministic metadata or the operator must select a canonical gap |
| `keyhole surfaces` is `degraded` | Optional observability/support surfaces are absent | Core proof can still pass; do not market missing optional surfaces as complete |
| `keyhole surfaces` is `blocked` | Required identity, context, repo, or run-dispatch surfaces are absent | Stop and capture the missing required surfaces |
| Command resolves to an old launcher | PowerShell found a global CLI before the venv CLI | Run launcher diagnostics and prefer the active venv executable |
| Dependency import failure | The active launcher is not using the installed package set | Reinstall in the active environment and re-run `keyhole version` |

## Common Recovery Path

If a run was interrupted:

```powershell
keyhole governed status --repo-dir <repo> --last --json
keyhole governed resume --repo-dir <repo> --last --json
```

If the proof already completed:

```powershell
keyhole governed receipt --repo-dir <repo> --last --json
```

## Interpretation Notes

- Local validation is not governance.
- Fake-boundary tests are not live proof.
- Diagnostic overrides are not closure proof.
- A live governed proof requires an MCP-backed receipt with governed Event Spine evidence.
- Generated `.keyhole` state is local execution state and should not usually be committed.
- `keyhole surfaces` may degrade gracefully when optional explainability,
  support-bundle, run-tail, budget, or async-accept surfaces are absent.
  Missing required identity, repo registration, context compile, run dispatch,
  or governed realization is a blocker.
