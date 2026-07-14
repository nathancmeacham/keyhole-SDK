# Governed Forked Repo Flow

This guide describes the generic SDK path for a forked client repository to
enter Keyhole governance through MCP.

## Flow

1. Initialize or fork a repo with Keyhole declaration files.
2. Run local validation and invariant tests.
3. Discover MCP capabilities.
4. Resolve one canonical `gap_*` ID through server-advertised discovery.
5. Claim the canonical gap through MCP.
6. Create governed context with the claim reference and repo declarations.
7. Compile context when the server contract requires it.
8. Run governed realization.
9. Preserve the governed receipt summary.

Use:

```powershell
keyhole governed run --repo-dir . --json
```

Useful inspection modes:

```powershell
keyhole governed run --repo-dir . --dry-run --explain --json
keyhole governed run --repo-dir . --no-live --explain --json
```

## Required Declarations

The generic flow reads these files before it calls MCP:

```text
keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml
```

The SDK derives repo identity, capability IDs, local invariant gates, git
remote, commit SHA, branch, repo class, declaration digests, and optional
story labels from those files and git metadata. Missing required identity
fails closed.

## Proof Levels

`--no-live` is local-only declaration validation. It does not prove governance.

Fake-boundary tests prove SDK behavior against a mocked MCP boundary. They are
useful regression tests, but they do not prove production governance.

Diagnostic gap overrides are for troubleshooting only. They must not be used
as closure proof.

Live MCP governance proof requires a real authenticated actor, canonical gap
resolution, gap claim, governed context creation, governed realization, and a
receipt with governed Event Spine evidence.

## Live Verifier

The public launch path should use the CLI governed flow against the blessed
example:

```powershell
keyhole validate examples\second-governed-app
keyhole doctor launch --repo-dir examples\second-governed-app --json
keyhole governed run --repo-dir examples\second-governed-app --json
```

Verifier scripts are advanced diagnostics. They are not the public builder
happy path.

## Receipt Requirements

A repo should not be described as governed unless live MCP returns a receipt
with:

```text
governed=true
event_spine_evidence=true
governance_verdict=ACCEPT
drift_state=non_drifted, clean, or equivalent current state
governance_context_id=<real>
mcp_event_id or mcp_event_pointer=<real>
```

Optional returned proof IDs, receipt IDs, passport digests, trust digests,
claim IDs, and claim refs should be preserved in redacted summaries.
