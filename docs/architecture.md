# Keyhole Developer Kit Architecture

## Overview

The **Keyhole Developer Kit** is the first governed external participant
repository in the Keyhole ecosystem. It is separate from **keyhole_Platform**
and learns platform truth through the MCP boundary - beginning with
capabilities discovery - rather than through private platform source intimacy.

It exists to let external builders:

- understand the public Keyhole integration model,
- develop against stable public contracts,
- run a real local runtime target,
- validate SDK, bridge, and realization behavior without requiring access to a private Keyhole deployment.

This repository is intentionally **not** the full Keyhole platform. It does **not** expose the private governance engine, promotion kernel internals, production credentials, or protected control-plane logic.

For the full boundary posture, see [boundary-constitution.md](boundary-constitution.md).

---

## Architectural Intent

This repository is designed around a strict public/private boundary.

The public repository should provide everything an external builder needs to:

1. learn the public integration model,
2. test against a deterministic runtime,
3. integrate through stable contracts,
4. deploy the public test runtime on their own infrastructure.

The repository should **not** leak or imply access to private platform internals.

---

## Public Boundary

### Included in this repository

The public developer kit includes:

- **SDK surfaces** for programmatic interaction,
- **public contracts and schemas**,
- a **test runtime** container that can be run locally or deployed publicly,
- **bridge examples** showing how external systems can interact with Keyhole-compatible surfaces,
- deployment examples and supporting documentation.

### Explicitly excluded

This repository does **not** include:

- the private Keyhole governance engine,
- promotion kernel internals,
- protected control-plane logic,
- production secrets,
- private policy evaluation internals,
- internal event-spine or promotion orchestration mechanisms.

That separation is intentional. The public surface is for builders. The protected control plane remains private.

---

## Top-Level Component Model

The repository is organized into a small set of public-facing architectural surfaces.

### 1. SDK Layer

The SDK layer gives builders a stable client surface for interacting with Keyhole-compatible runtimes.

Responsibilities:

- wrap HTTP interaction with the runtime,
- normalize request/response handling,
- support integration tests and examples,
- provide a foundation for future CLI and automation tooling.

The SDK is a **consumer-facing layer**, not a control-plane implementation.

---

### 2. Contract Layer

The contract layer defines the public integration shape.

Responsibilities:

- document public JSON and HTTP expectations,
- stabilize request and response formats,
- give builders a durable interface to target,
- enable repeatable validation across local and remote environments.

Public contracts are the compatibility surface between builder tooling and Keyhole-compatible runtimes.

---

### 3. Test Runtime Layer

The **Keyhole Test Runtime** is the first public Runtime Bridge in the ecosystem.

It is a small HTTP service that:

- exposes a health surface,
- exposes a runtime identity surface,
- exposes a local state surface,
- gates every bounded realization request through the Keyhole MCP governance controller before applying any local mutation (when configured).

Its primary purpose is to give developers a **real, governance-connected, HTTP-addressable target** for integration and deployment testing.

When `KEYHOLE_MCP_URL` and `KEYHOLE_MCP_TOKEN` are configured, `POST /realize` calls the Keyhole MCP governance controller and only applies the realization locally if governance returns an `ACCEPT` verdict.

When those env vars are absent, the runtime operates in **local-only mode** for initial SDK and tooling development. Local-only mode does not gate realizations through governance and is not suitable for production use.

---

### 4. Bridge / Example Layer

The bridge and example layer demonstrates how external systems can interact with the public Keyhole surface.

Responsibilities:

- show integration patterns,
- validate end-to-end request flows,
- serve as smoke-test references,
- reduce ambiguity for builders implementing their own tooling.

Examples should remain simple, executable, and directly tied to public contracts.

---

### 5. Deployment Layer

The deployment layer shows how the public runtime can be run:

- locally with Docker Compose,
- remotely behind Traefik using a Compose deployment template.

This layer exists to help builders move from "it runs on my machine" to "it is reachable as a real service."

---

## Architecture Diagram

```text
+--------------------------------------------------------------+
|                    Keyhole Developer Kit                     |
+--------------------------------------------------------------+
|                                                              |
|  +----------------+     +-------------------------------+    |
|  | SDK / Client   | --> | Public Runtime HTTP Surface   |    |
|  | Layer          |     |  (Keyhole Test Runtime)       |    |
|  |                |     |                               |    |
|  | - Python SDK   |     |  GET  /healthz                |    |
|  | - Future SDKs  |     |  GET  /identity               |    |
|  +----------------+     |  GET  /state                  |    |
|                         |  POST /realize  ---------->   |    |
|                         +-------------------------------+    |
|                                                      |       |
|                             MCP Governance Bridge    |       |
|                             (bridge.py)              |       |
|                                                      v       |
|                         +-------------------------------+    |
|                         | Keyhole MCP Governance        |    |
|                         | Controller (external)         |    |
|                         |                               |    |
|                         |  POST /mcp/v1/runs/start      |    |
|                         |  run_type: convergence.status |    |
|                         |                               |    |
|                         |  verdict: ACCEPT | REJECT     |    |
|                         +-------------------------------+    |
|                                      |                       |
|                   ACCEPT only        v                       |
|                         +-------------------------------+    |
|                         | Local Runtime State           |    |
|                         |                               |    |
|                         | - current_digest              |    |
|                         | - realized_digests            |    |
|                         +-------------------------------+    |
|                                                              |
|  +----------------+                                          |
|  | Bridge /       | --------------------------------------+  |
|  | Example Layer  | demonstrates public integration      |  |
|  +----------------+ --------------------------------------+  |
|                                                              |
|  +----------------+                                          |
|  | Deploy Layer   | --> Local Docker / Traefik / GHCR       |
|  +----------------+                                          |
|                                                              |
+--------------------------------------------------------------+

         Public Builder Surface
         -----------------------------------------
         POST /realize is gated by MCP governance
         when KEYHOLE_MCP_URL is configured (governed mode).
         In local-only mode (the default), realization
         executes immediately without governance gating.
         Private governance internals remain inside
         the Keyhole platform - only verdicts cross
         the public/private boundary.
```

The runtime is designed for a small, clear request model.

Health Flow

A caller sends:

GET /healthz

The runtime answers with a simple health response indicating availability.

Identity Flow

A caller sends:

GET /identity

The runtime returns its declared identity and capabilities.
This allows SDKs, tests, and operators to confirm they are talking to the expected runtime.

State Flow

A caller sends:

GET /state

The runtime returns its current local state representation.

Realization Flow

A caller sends:

POST /realize

with a bounded request containing a candidate digest and optional payload.

The runtime:

1. calls the Keyhole MCP governance controller (when `KEYHOLE_MCP_URL` is configured),
2. waits for a governance verdict (`ACCEPT` or `REJECT`),
3. applies the local mutation **only** if governance returns `ACCEPT`,
4. checks whether the digest has already been realized (idempotency gate),
5. returns the receipt to the caller.

When `KEYHOLE_MCP_URL` is not configured the runtime runs in local-only mode:
the governance check is bypassed and the digest is applied unconditionally.
Local-only mode is for initial SDK and tooling development only - not for
production use.

Replay of the same digest does not produce an additional state mutation regardless of mode.

Idempotency Model

The test runtime enforces deterministic replay behavior.

First submission of a digest

- governance check passes (or local-only mode),
- state mutates,
- the digest is recorded,
- the runtime returns status `ACCEPT`.

Replay of the same digest

- no new state mutation occurs,
- the runtime returns status `ALREADY_REALIZED`,
- the runtime remains stable and deterministic.

This makes the runtime useful for:

integration tests,

deployment validation,

bridge smoke tests,

safe repeated calls during development.

Governance Configuration

The MCP governance bridge is controlled by two required env vars:

| Variable | Purpose |
|---|---|
| `KEYHOLE_MCP_URL` | Base URL of the Keyhole MCP governance controller |
| `KEYHOLE_MCP_TOKEN` | Bearer token issued by Keyhole for this runtime identity |

Optional vars:

| Variable | Default | Purpose |
|---|---|---|
| `KEYHOLE_MCP_RUN_TYPE` | `convergence.status.v0_1` | run_type used for candidate verification |
| `KEYHOLE_MCP_TIMEOUT` | `10` | HTTP timeout in seconds |

Obtain credentials from the Keyhole tenant portal before deploying to production.

Deployment Modes
Local Development Mode (local-only, no governance)

The primary local development path is:

run the runtime with Docker Compose (no env vars required),

call the HTTP endpoints directly on localhost,

validate behavior from SDKs, curl, or example integrations.

In local-only mode all realize requests succeed locally without a governance gate.
This is the fastest path for external builders to verify SDK and tooling compatibility.

Governed Mode (connected to MCP)

Set `KEYHOLE_MCP_URL` and `KEYHOLE_MCP_TOKEN` before starting the runtime:

```sh
KEYHOLE_MCP_URL=https://mcp.keyholesolution.com \
KEYHOLE_MCP_TOKEN=<your-token> \
docker compose up
```

In governed mode every `POST /realize` is evaluated by the Keyhole governance controller
before any local mutation is applied.

Internet-Addressable Mode

The runtime can also be deployed behind Traefik using the provided deployment template.

In that model:

the runtime container is pulled from GHCR,

Traefik provides hostname routing and TLS termination,

`KEYHOLE_MCP_URL` and `KEYHOLE_MCP_TOKEN` are supplied via the host environment,

the service becomes reachable through a public domain,

the same runtime contract remains intact.

This is useful for:

remote integration testing,

shared team environments,

public demonstration environments,

external smoke-test targets.

Trust and Responsibility Boundaries

The architecture deliberately separates public interaction surfaces from private control-plane authority.

Builder-facing responsibility

This repository is responsible for:

stable public interfaces,

reproducible local testing,

clear integration guidance,

executable examples,

deployable public runtime artifacts.

Private platform responsibility

Private Keyhole control-plane systems are responsible for:

governance enforcement,

promotion and policy evaluation,

protected identity and authorization internals,

canonical change orchestration,

private operational logic.

That separation keeps the public surface clean, safe, and reusable.

Repository Design Principles
1. Public-first clarity

Every surface in this repository should be understandable by an external builder without insider knowledge.

2. Stable contracts over hidden magic

The repository should favor explicit request/response models and documented behavior over implicit assumptions.

3. Small executable surfaces

The public runtime should remain narrow, deterministic, and easy to reason about.

4. Real deployment path

Public artifacts should not be documentation-only. Builders should be able to run and deploy what the repo describes.

5. Clean boundary discipline

The repository should expose only what belongs on the public side of the Keyhole boundary.

What This Architecture Is Not

This architecture is not:

a full production platform topology,

a private governance architecture dump,

a replacement for protected Keyhole control-plane systems,

a persistence-heavy production runtime,

a complete description of internal platform orchestration.

It is a public developer architecture.

Its purpose is to provide a stable, understandable, deployable integration surface for builders.

Intended Evolution

This architecture is intentionally small at first.

It is expected to evolve by expanding the public developer surface in a controlled way, such as:

additional language SDKs,

richer public schemas,

CLI support,

more bridge examples,

broader integration smoke tests,

more deployment templates.

As the repository grows, the same rule should hold:

public developer capability grows, while private governance internals remain outside the public boundary.

Summary

The Keyhole Developer Kit architecture is built around one central idea:

Provide a real public integration surface without exposing private governance internals.

That means this repository should remain:

executable,

documented,

contract-driven,

deployment-capable,

boundary-disciplined.

The result is a public builder entry point that is strong enough to support real integration work while remaining cleanly separated from the protected internals of the wider Keyhole platform.

---

## Boundary Posture

This repository is a **separate governed participant** - not a nested
subtree of the platform source. The canonical relationship is:

- **keyhole_Platform** is the governor.
- **keyhole-developer-kit** is a governed participant.
- Governance crosses the boundary through the MCP surface.
- The first discovery surface is `GET /mcp/v1/capabilities`.
- Private platform source intimacy is non-canonical.

See [boundary-constitution.md](boundary-constitution.md) for the full
boundary constitution.
