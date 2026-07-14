# Agent Alignment — Keyhole Developer Kit

This document defines alignment rules for any AI agent, copilot, or automated
contributor working in this repository.

For the current public launch path, root-level [AGENTS.md](../AGENTS.md) is
the shortest operational contract. This document gives additional background
and boundary posture.

## Current Public Launch Path

`examples/second-governed-app` is the blessed public launch example.
`my-first-app` is retained for legacy first-app and server-boundary evidence
work, not as the generic public quickstart.

Agents proving the SDK should use:

```powershell
.\.venv\Scripts\keyhole.exe login --flow device --force
.\.venv\Scripts\keyhole.exe whoami --json
.\.venv\Scripts\keyhole.exe validate examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe doctor launch --repo-dir examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe governed run --repo-dir examples\second-governed-app --json
.\.venv\Scripts\keyhole.exe governed receipt --repo-dir examples\second-governed-app --json
```

Do not use lower-level `repo register`, `context compile`, or `run --context`
commands as the public happy path unless the task is explicitly about legacy
first-app diagnostics.

## Boundary Posture

**keyhole-developer-kit** is a separate governed participant repository — not
a subcomponent of keyhole_Platform.

1. **Boundary-first discovery.** The first truth surface is
   `GET /mcp/v1/capabilities`. Begin there before making assumptions about
   platform structure, interfaces, or supported behavior.

2. **No source intimacy.** Do not browse, reference, or depend on private
   platform source code. Platform truth is retrieved through the MCP
   boundary, not through source inspection.

3. **No nested-repo assumptions.** Do not assume co-location with the
   platform repository, relative paths into platform source, or internal
   platform file structures.

See [boundary-constitution.md](boundary-constitution.md) for the full
boundary constitution.

## Current Transport and Auth Posture

The MCP boundary uses two parallel transports that must not be conflated:

**VS Code / MCP Client Transport (CANONICAL MAIN)**

| Aspect    | Value                                        |
|-----------|----------------------------------------------|
| Transport | **SSE** (Server-Sent Events + JSON-RPC)      |
| Endpoint  | `https://mcp.keyholesolution.com/sse`        |
| Used by   | VS Code MCP integration (`.vscode/mcp.json`) |

`.vscode/mcp.json` with `"url": "https://mcp.keyholesolution.com/sse"` is **correct**.
Do not change this URL. Do not diagnose `/sse` as an error.

**SDK / CLI API Transport (GOVERNED OPERATIONS)**

| Aspect    | Current Value  |
|-----------|----------------|
| Transport | REST/HTTP      |
| Auth flow | OIDC/PKCE      |
| Realm     | `keyhole-mcp`  |
| Contract  | `mcp/v1`       |

The **old Keyhole SDK-internal SSE transport** (pre-S42, for calling API endpoints
directly) is deprecated. Do not use it in SDK/CLI code. This deprecation does NOT
apply to the VS Code MCP SSE server endpoint.

## Auth & Identity Bootstrap

Agents must follow this bootstrap sequence when connecting to the governed
boundary:

```
1. GET  /mcp/v1/capabilities     → discover (unauthenticated)
2. OIDC/PKCE token acquisition   → realm: keyhole-mcp
3. GET  /mcp/v1/whoami           → inspect identity (first authenticated check)
4. Proceed                       → context retrieval, run dispatch, etc.
```

**Rules:**
- Discovery comes before authentication — never guess auth posture.
- `whoami` is the first authenticated action — do not skip it.
- Authentication does not grant write authority by default.
- Public discovery ≠ governed participant readiness.
- Later governed flows may require charter enrollment and workspace posture.

**Surface categories (read vs write):**

| Category               | Auth Required | Mutates State |
|------------------------|---------------|---------------|
| Public discovery       | No            | No            |
| Identity inspection    | Yes           | No            |
| Context-access reads   | Yes           | No            |
| Write / proof-bearing  | Yes + charter | Yes           |

See [auth-bootstrap.md](auth-bootstrap.md) for full guidance.

## Context-Before-Assumption Rule

When capabilities alone are insufficient:

1. Retrieve governed context before making assumptions.
2. Use context-access run types (`context.compile`, `gaps.list`,
   `lineage.get.v0_1`, `convergence.status.v0_1`) through
   `POST /mcp/v1/runs/start`.
3. Do not substitute stale repo docs or remembered patterns for live
   boundary truth.

The SDK provides `ContextClient` for programmatic context retrieval.
Use `compile_context()` as the primary bootstrap surface before
implementation, dispatch, or architecture decisions.

A `ContextSnapshot` is a normalized convenience artifact.
Live boundary retrieval remains authoritative.

## Exact Run-Type Discipline

Run types are **exact canonical keys** — not REST resource guesses.

| Correct             | Incorrect (do not use) |
|---------------------|------------------------|
| `gaps.status`       | `gaps.states`          |
| `gaps.list`         | `gap.status`           |
| `convergence.status.v0_1` | `convergence.statuses` |

- Do not pluralize, singularize, or improvise run-type names.
- If you encounter an unknown run type, re-discover from capabilities.

## Dispatch Safety — Preflight Before Dispatch

The SDK provides `RunTypeValidator`, `SchemaHelper`, and `DispatchPreflight`
for participant-side dispatch safety (CE-V5-S42-06).

Before dispatching a run type:

1. **Validate** the run-type name against known canonical keys.
2. **Consult schema** for required parameters and request shape.
3. **Preflight** the full dispatch — run type + params.
4. **Dispatch only** after preflight passes.

```python
from keyhole_sdk import DispatchPreflight

preflight = DispatchPreflight.from_capabilities(caps)
result = preflight.check("context.compile")
assert result.should_proceed
```

Do not treat server rejection as the primary teacher.  Use the dispatch
safety layer to catch mistakes before they reach the boundary.

See [examples/python-client/safe_dispatch.py](../examples/python-client/safe_dispatch.py)
for the full sequence.

## Read-Only Smoke Path — End-to-End Verification

The SDK provides `ReadOnlySmokeRunner` (CE-V5-S42-07) to verify the full
read-only participant entrance flow in one call:

  discover → identity → context → safe read-only run

```python
from keyhole_sdk import ReadOnlySmokeRunner

with ReadOnlySmokeRunner(base_url=url, token=token) as runner:
    result = runner.run()

if result.all_passed:
    print("Read-only path is fully open.")
else:
    print(result.summary())
```

Each phase produces a `PhaseResult` with success/failure, error detail,
and a actionable suggestion.  See [docs/smoke.md](smoke.md) for failure
modes and troubleshooting.

## Core Principles

1. **Truth over aspiration.** Only describe behavior that the current codebase
   implements. Do not describe planned features as if they already work.

2. **Mode awareness is prose-only.** The test runtime operates in two modes:
   - **local-only** (default): no MCP governance gating.
   - **governed**: MCP governance gating active.
   Mode is an operational distinction described in prose. It is **not** a
   response field. Do not add `governance_mode` to example responses.

3. **Contract fidelity.** The current runtime contract is minimal:
   - `/identity` returns: `runtime_id`, `runtime_name`, `runtime_version`,
     `environment`, `capabilities`.
   - `/realize` receipt returns: `digest`, `status`, `message`, `realized_at`.
   Do not add fields that the runtime does not actually emit. Specifically,
   do **not** add `governance_mode`, `governance_verdict`, `result`, `version`,
   or `pointer` to example responses — these are planned for S41 but not
   implemented today.

4. **Public boundary discipline.** This repository is the public developer
   surface. Do not add references to private cluster topology, internal
   Keyhole namespaces, production credentials, or protected control-plane
   APIs.

5. **Schema fidelity.** The OpenAPI spec, JSON schemas, and SDK/CLI models
   must match what the runtime actually returns. If the runtime changes,
   update all surfaces.

## Forbidden Patterns

- Example `/realize` response with `governance_verdict`, `result`, `version`, or `pointer`
- Example `/identity` response with `governance_mode`
- Claiming Event Spine evidence from a local-only run
- Describing the test runtime as "the Keyhole governance engine"
- Implying production-grade persistence or audit in local-only mode
- Adding unimplemented fields to schemas or models
- Guessing run types by pluralizing, singularizing, or convention
- Using tombstoned transports (SSE, JSON-RPC)
- Treating repo docs as fresher than live capabilities
- Browsing or referencing private platform source as a discovery method
- Fabricating hidden surface names or undisclosed endpoints
- Skipping `whoami` after authenticating — always inspect identity first
- Confusing public discovery with governed participant readiness
- Assuming authentication alone grants write or mutation authority

## Behavior Under Uncertainty

When encountering unknown run types, auth ambiguity, or schema uncertainty:

1. Re-check capabilities — `GET /mcp/v1/capabilities`
2. Consult governed context — use context-access run types
3. Do not improvise hidden surface names or run-type keys
4. Prefer discovery over convention

When uncertain about any claim, prefer conservative wording over ambitious
wording.

## File Governance

When modifying any of the following files, verify that example responses
and schemas match the current minimal contract:

- `README.md`
- `docs/auth-bootstrap.md`
- `docs/boundary-constitution.md`
- `docs/quickstart.md`
- `docs/test-runtime.md`
- `docs/bridge-contract.md`
- `docs/architecture.md`
- `openapi/test-runtime.openapi.yaml`
- `packages/python/keyhole-sdk/keyhole_sdk/models.py`
- `examples/bridge-smoke-test/smoke-test.sh`
- `examples/bridge-smoke-test/smoke-test.ps1`
- `examples/bridge-smoke-test/README.md`
