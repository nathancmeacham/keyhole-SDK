# Copilot Instructions — Keyhole Developer Kit

## Repo Identity and Boundary Posture

**keyhole-developer-kit** is a separate governed participant repository — not
a subcomponent of the Keyhole platform source tree.

It contains:

- `keyhole-cli`
- `keyhole-sdk`
- the public test runtime
- public schemas and OpenAPI
- examples and onboarding docs
- deployment templates

It does **not** contain private Keyhole platform internals.

This repository learns platform truth through the **MCP boundary**, not
through private source inspection. See
[docs/boundary-constitution.md](../docs/boundary-constitution.md) for the
full boundary posture.

### Absolute Repository Separation

The SDK repo and the Keyhole platform repo may exist on the same VM, but they
must remain fully separate repositories.

Forbidden:

- nesting this repo inside `keyhole_platform`
- nesting `keyhole_platform` inside this repo
- direct imports from platform source into SDK code
- direct imports from SDK source into platform code
- symlinks, bind mounts, or shared source directories between the repos
- relative-path coupling across repo boundaries
- treating a local checkout of `keyhole_platform` as an SDK dependency

The SDK is an external participant surface. It must remain portable,
independently versioned, and boundary-governed.

### Control Plane Leakage — Forbidden

The SDK must not replicate, simulate, or embed any control-plane logic.

Forbidden behaviors include:

- implementing local "decision engines" that mimic governance outcomes
- caching or replaying decisions as if they were canonical truth
- performing validation that replaces or overrides MCP decisions

The SDK may:

- validate request shape
- enforce transport discipline
- prevent invalid dispatch

The SDK must NOT:

- decide ACCEPT/REJECT outcomes
- simulate promotion behavior
- act as a source of truth

All final decisions belong exclusively to the MCP boundary.

---

## Core Identity — SDK Is a Governed Protocol Client

The keyhole-sdk and keyhole-cli are not general-purpose libraries.

They are:

→ strict, opinionated protocol clients for the MCP boundary
→ enforcement surfaces for governed participation

They are NOT:

- helper libraries
- convenience wrappers around HTTP
- alternate control planes
- local execution engines

Every SDK call must be treated as:

→ a governed, attributable, replayable interaction with the MCP boundary

If a feature would allow a developer to:

- bypass identity context
- bypass governed context
- execute without attribution
- mutate state without proof

then that feature must be rejected or redesigned.

---

## First Truth Surface: Capabilities Discovery

Before making platform-structure, endpoint, run-type, or supported-surface
assumptions, consult the live boundary beginning with:

```
GET /mcp/v1/capabilities
```

This is the **initial source of truth** for any external participant — human
or agent. It is public-safe, read-only, and available before authentication.

From capabilities, you learn:

- the current contract version
- transport posture
- auth requirements
- minimum SDK version
- whether charter and workspace are required
- what operations are available

**Do not guess** platform structure, surfaces, or run types from repo docs,
old comments, or naming conventions. Capabilities is always fresher than
local docs.

### Canonical Connection Rule

For this repository, the only permitted integration path to the Keyhole
platform is the public MCP boundary over HTTP:

`https://mcp.keyholesolution.com`

All platform interaction must occur through:

- MCP endpoints
- authenticated HTTP requests
- governed run dispatch
- published contracts and compatibility metadata

Do not create SDK behavior that depends on private source access, local repo
co-location, or filesystem adjacency to the platform repo.

---

## Current Transport and Auth Posture

The MCP boundary uses **two parallel transports** that must not be conflated:

### VS Code / MCP Client Transport (CANONICAL MAIN)

| Aspect    | Value                                        |
|-----------|----------------------------------------------|
| Transport | **SSE** (Server-Sent Events + JSON-RPC)      |
| Endpoint  | `https://mcp.keyholesolution.com/sse`        |
| Used by   | VS Code MCP integration (`.vscode/mcp.json`) |
| Auth      | OIDC/PKCE token acquired by VS Code          |

This is the canonical main transport for AI agent ↔ Keyhole MCP integration.
`.vscode/mcp.json` with `"url": "https://mcp.keyholesolution.com/sse"` is **correct**.

### SDK / CLI API Transport (GOVERNED OPERATIONS)

| Aspect    | Current Value  |
|-----------|----------------|
| Transport | REST/HTTP      |
| Auth flow | OIDC/PKCE      |
| Realm     | `keyhole-mcp`  |
| Contract  | `mcp/v1`       |
| Min SDK   | `0.1.0`        |
| Charter   | required       |
| Workspace | supported      |

This transport is used by `keyhole-sdk` and `keyhole-cli` for governed API operations
(`GET /mcp/v1/capabilities`, `POST /mcp/v1/runs/start`, etc.).

### Surface Categories

Agents must distinguish these surface categories:

1. **Public discovery** (unauthenticated):
   - `GET /mcp/v1/capabilities` — discover boundary posture and operations

2. **Authenticated identity**:
   - `GET /mcp/v1/whoami` — inspect current participant identity

3. **Run dispatch** (authenticated):
   - `POST /mcp/v1/runs/start` — dispatch a named run type

4. **Event query** (authenticated):
   - `POST /mcp/v1/events/query` — query the Event Spine

5. **Memory surfaces** (authenticated, where relevant):
   - Used for governed context retrieval and storage

### Deprecated SDK-Internal Transports

The **old Keyhole SDK-internal SSE and JSON-RPC** transports are tombstoned.
They were used before S42 for
calling Keyhole API endpoints directly) are deprecated. Do not use them in SDK/CLI code.

This deprecation does **NOT** apply to:
- The VS Code MCP SSE server endpoint (`/sse`) — that is canonical and correct
- The VS Code MCP protocol (SSE + JSON-RPC between VS Code and the MCP server)

### Client Posture Reminder

The SDK and CLI are boundary clients, not internal platform packages.

That means:

- no direct Python imports from platform internals
- no shared module graph with `keyhole_platform`
- no local shortcut around auth, discovery, or governed dispatch
- no assumptions based on same-machine deployment

All valid behavior must remain correct even when the platform is hosted on a
different machine and reachable only through `https://mcp.keyholesolution.com`.

---

## Auth & Identity Bootstrap Posture

External participants must follow this sequence when connecting to the
governed boundary:

1. **Discover** — `GET /mcp/v1/capabilities` (unauthenticated, read-only)
2. **Authenticate** — acquire token via OIDC/PKCE for realm `keyhole-mcp`
3. **Inspect identity** — `GET /mcp/v1/whoami` (first authenticated check)
4. **Proceed** — context retrieval, run dispatch, etc.

### Key Rules

- Discovery comes **before** authentication. Never guess auth posture.
- `whoami` is the **first authenticated action** — do not skip it.
- Authentication does **not** grant write authority by default.
- Later governed flows may require charter and workspace posture.
- Public discovery does **not** equal governed participant readiness.

### Surface Distinction

| Category                     | Auth Required | Example                         |
|------------------------------|---------------|----------------------------------|
| Public discovery              | No            | `GET /mcp/v1/capabilities`      |
| Authenticated identity        | Yes           | `GET /mcp/v1/whoami`            |
| Authenticated read (governed) | Yes           | Context-access run types         |
| Write / proof-bearing         | Yes + charter | Later stories (S42-05+)         |

See [docs/auth-bootstrap.md](../docs/auth-bootstrap.md) for the full
bootstrap guidance.

---

## CLI Operating Model

`keyhole-cli` is a boundary client. It is not a privileged platform shell, not
a private control-plane companion, and not a shortcut into platform source.

The CLI must behave as an external governed participant at all times.

### Canonical CLI Sequence

When operating against the platform, the CLI must follow this order:

1. **Discover**
   - call `GET /mcp/v1/capabilities`
   - learn current contract posture before making assumptions

2. **Authenticate**
   - acquire token through the supported OIDC/PKCE flow
   - never assume cached auth posture is still valid without boundary checks

3. **Inspect identity**
   - call `GET /mcp/v1/whoami`
   - treat this as the first authenticated truth check

4. **Retrieve governed context**
   - use supported context-access run types where architectural certainty is needed

5. **Dispatch**
   - submit exact canonical run types through `POST /mcp/v1/runs/start`
   - never invent surface names, routes, or run-type keys

### CLI Boundary Rules

The CLI must not:

- read local platform source as a substitute for discovery
- import platform internals
- assume the platform repo is present on disk
- bypass MCP because both repos happen to live on the same VM
- treat same-machine deployment as a special integration mode

### Mode Labeling

The CLI must label its operating posture truthfully:

- **local-only** when MCP is not configured or not in use
- **governed** only when actually connected to the live MCP boundary

Local-only execution must never be described as upstream-governed,
Event-Spine-backed, or proof-bearing.

### Cache and Convenience Rules

The CLI may cache convenience data for UX, but cached values never outrank:

1. live capabilities
2. live `whoami`
3. live governed context

When cached assumptions conflict with live boundary truth, live boundary truth
wins immediately.

### Async Execution Truth

The platform operates on accepted async execution.

The CLI and SDK must NOT:

- pretend that long-running operations complete synchronously
- hide accepted execution behind blocking UX

Instead:

- write-bearing operations may return:

  → ACCEPTED
  → run_id

The SDK/CLI must support:

- polling
- status inspection
- optional streaming visibility (when available)

Example:

```text
keyhole run --context auto

→ ACCEPTED (run_id=abc123)
```

Not:

```text
→ SUCCESS (final result)
```

unless the operation is explicitly defined as synchronous.

---

## Context-Before-Assumption Rule

When capabilities alone are insufficient for architectural certainty:

1. Retrieve governed context before making assumptions.
2. Use context-access run types to compile truth from the live boundary.
3. Do not substitute stale repo docs, old comments, or remembered patterns
   for live boundary truth.

Current implemented read-only context-access run types include:

- `context.compile`
- `gaps.list`
- `lineage.get.v0_1`
- `convergence.status.v0_1`

Use these through `POST /mcp/v1/runs/start` with the exact run type key.

### SDK Context Retrieval

The SDK provides `ContextClient` for governed context retrieval:

```python
from keyhole_sdk import ContextClient

with ContextClient(base_url=url, token=token) as ctx:
    snapshot = ctx.compile_context()
```

Always retrieve context before implementation, dispatch, or
assumption-making.  The `ContextSnapshot` is a convenience artifact —
live boundary retrieval remains authoritative.

### Boundary-over-Source Rule

When platform behavior is unclear:

1. discover through `GET /mcp/v1/capabilities`
2. authenticate
3. inspect identity through `GET /mcp/v1/whoami`
4. retrieve governed context through supported MCP run types

Do not resolve uncertainty by opening, browsing, or depending on private
platform source code. The MCP boundary is the canonical source of truth for
external participants.

### No Floating Execution (Hard Rule)

No governed execution may occur without context.

The SDK must:

- reject attempts to run without context
- provide auto-context resolution helpers where possible

Allowed:

```text
keyhole run --context auto
```

Forbidden:

```text
keyhole run  (implicit / missing context)
```

If context cannot be resolved:

→ return REJECT with repair guidance

---

## Exact Run-Type Discipline

Run types are **exact canonical keys** — not REST resource guesses.

They are named workflows with precise identifiers. They are:

- singular when declared singular
- not discoverable by convention
- not safely guessable by pluralization or naming instinct

### Examples

| Correct             | Incorrect (do not use) |
|---------------------|------------------------|
| `gaps.status`       | `gaps.states`          |
| `gaps.list`         | `gap.status`           |
| `convergence.status.v0_1` | `convergence.statuses` |

### Rules

- Always use the **exact** run-type key from `operations[]` or published guidance.
- Do not pluralize, singularize, or improvise run-type names.
- Do not guess a run type exists because a similar name feels right.
- If you encounter an unknown run type, **re-discover** — consult
  capabilities or context. Do not improvise.

### SDK Dispatch Safety (CE-V5-S42-06)

The SDK provides participant-side dispatch safety helpers:

- `RunTypeValidator` — validates run-type names against canonical keys
- `SchemaHelper` — retrieves request-shape guidance for known run types
- `DispatchPreflight` — composes validation + schema into a preflight gate

All three can be built from a live `CapabilitiesResult`:

```python
from keyhole_sdk import DispatchPreflight

preflight = DispatchPreflight.from_capabilities(caps)
result = preflight.check("context.compile")
assert result.should_proceed
```

The preflight check returns `pass`, `warn`, or `reject` with recovery
guidance.  Use it before dispatch to prevent guessed names, missing
parameters, and invalid request shapes from reaching the boundary.

---

## Idempotent Transport and Request Identity (MANDATORY)

All write-bearing operations must include:

- `X-Request-Id`
- `X-Idempotency-Key`

These must be:

- generated once per logical operation
- reused across retries
- never regenerated during retry loops

### Rules

- No write-bearing request may be sent without idempotency headers
- Retries must preserve identity
- Duplicate requests must be safely replayable

### SDK Responsibility

The SDK must automatically:

- inject request identity headers
- manage retry-safe behavior
- surface replay vs new execution clearly

Failure to enforce this results in:

→ duplicate execution
→ Event Spine corruption
→ non-deterministic behavior

This is a blocking requirement for external-scale usage.

---

## Memory Boundary Enforcement

The SDK must never expose direct canonical memory access.

Forbidden:

- direct vector search APIs
- direct memory query endpoints
- raw access to Qdrant or memory primitives

Allowed:

- `context.compile`
- governed run types that encapsulate memory access

All memory interaction must occur:

→ through governed execution
→ with full identity and context binding

Any feature exposing direct memory access must be rejected.

---

## First 10-Minute Rule (Adoption Constraint)

All features must support a first successful outcome within 10 minutes.

Agents should prioritize:

- login success
- first governed run
- repo ingestion with visible output

Avoid:

- requiring full contract authoring upfront
- requiring deep platform knowledge before first success

Progressive disclosure is required:

→ simple first
→ governed depth later

---

## Truthfulness Rules

1. **Local-only is the default.** Unless the user has explicitly configured
   MCP connectivity, examples, smoke tests, and quickstart flows should be
   treated as running in local-only mode.

2. **Do not claim Event Spine evidence from local-only runs.** Local-only
   realizations are useful for first-run development and replay testing, but
   they are not upstream-auditable.

3. **Label runtime mode explicitly.** When showing example output or
   describing behavior, distinguish between:
   - `local-only`
   - `governed`

4. **Do not invent governed behavior.** Only describe governed-mode behavior
   when the relevant MCP configuration is actually present and the current
   runtime contract supports it.

5. **Do not expose private platform internals.** Never reference internal
   cluster topology, private governance engine details, promotion kernel
   internals, production secrets, or protected control-plane logic.

6. **Do not overclaim proof.** A working local developer loop is not, by
   itself, proof of full external runtime bridge closure.

## Public Contract Discipline

### `/identity`
Examples and docs should reflect the current public runtime contract:
`runtime_id`, `runtime_name`, `runtime_version`, `environment`, `capabilities`.
No `governance_mode` field exists in the current contract.

### `/realize`
Examples and docs must match the current public runtime receipt shape:
`digest`, `status`, `message`, `realized_at`.
Do not add `governance_verdict`, `result`, `version`, or `pointer` — these
are not emitted by the runtime today.

## Mode Model

### Local-only
Use this when MCP is not configured.
Do not imply governance gating, Event Spine evidence, or upstream auditability.

### Governed
Use this only when MCP is configured and the runtime is actually operating
against the public governance boundary.
Do not assume a successful verdict; show only what the current runtime
contract actually returns.

---

## Anti-Patterns — Forbidden Agent Behavior

Do not:

- **Guess run types** by pluralizing, singularizing, or constructing names
  from convention.
- **Assume internal platform code is authoritative** for external participant
  usage. Platform truth comes through the MCP boundary.
- **Use deprecated SDK-internal SSE/JSON-RPC** for calling Keyhole API endpoints.
  (Note: the VS Code MCP SSE endpoint `/sse` is canonical and correct — do not confuse these.)
- **Treat repo docs as fresher than live capabilities.** When in doubt,
  capabilities is the canonical source.
- **Browse or reference private platform source** as a discovery or
  onboarding method.
- **Assume co-location** with the platform repository, relative paths into
  platform source, or internal platform file structures.
- **Create direct repo-to-repo coupling** through imports, symlinks, bind
  mounts, shared source trees, or local path assumptions.
- **Treat a same-VM checkout of `keyhole_platform` as part of this repo's
  implementation surface.**
- **Bypass MCP** for SDK ↔ platform interaction.
- **Teach the CLI to inspect platform source** instead of discovering through
  capabilities, `whoami`, and governed context.
- **Fabricate hidden surface names** or undisclosed endpoints.
- **Claim Event Spine evidence** from local-only runs.
- **Add unimplemented fields** to example responses, schemas, or models.

## Additional Anti-Patterns — Critical

Do not:

- create SDK functions that hide MCP interaction
- allow silent retries without user visibility
- cache decisions as if they were authoritative
- execute logic locally that should be governed remotely
- introduce "magic" behavior that cannot be traced to MCP calls

All behavior must remain:

→ observable
→ attributable
→ replayable

---

## Behavior Under Uncertainty

When encountering unknown run types, auth ambiguity, or schema uncertainty:

1. **Re-check capabilities** — `GET /mcp/v1/capabilities`
2. **Consult governed context** — use context-access run types
3. **Consult schema discovery** where available
4. **Do not improvise** hidden surface names or run-type keys
5. **Prefer discovery over convention** — always

When uncertain about any claim, prefer conservative wording over ambitious
wording.

## Story Stream Ownership

This repository owns client-side SDK and CLI story work.

- `ce-v5-sdk-client` / `sdk-client-*` story work belongs here
- `ce-v5-sdk-server` / `sdk-server-*` story work belongs in the
  `keyhole_platform` repository

If a task spans both repos:

1. implement SDK-client or CLI changes here only
2. describe required server-side contract changes explicitly
3. do not solve cross-repo work by copying code across the boundary
4. do not place server-owned story implementation inside this repo

---

## No Private-Source Truth

Platform truth for external participants must not depend on:

- browsing private platform source code
- stale copied docs or old comments
- internal path assumptions or nested-repo conventions
- verbal lore or tribal knowledge

This prohibition also includes:

- importing directly from platform modules
- reading local platform source as an integration dependency
- using local symlinks or relative paths to access platform internals
- assuming the SDK and platform share a filesystem contract
- teaching the CLI to derive truth from platform checkout state

The platform may be developed in parallel, but this repository must treat it
as a remote governed system accessed only through the MCP boundary.

The canonical path to platform truth is the **MCP boundary** — beginning
with `GET /mcp/v1/capabilities`, then governed context retrieval as needed.

This is not optional. It is constitutional.

---

## Forkability and Verticalization

The SDK is expected to be forked for vertical-specific use cases.

Design must support:

- namespace isolation
- capability inheritance
- proof portability

Do not:

- hardcode assumptions about a single global use case
- couple SDK behavior to one vertical

The SDK must behave as:

→ a universal governed client layer
→ adaptable across domains without breaking invariants
