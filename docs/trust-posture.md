# Trust Posture — Keyhole Developer Kit

**Story:** CE-V5-S42-10  
**Purpose:** Public-safe summary of the developer kit's trust posture  
**Last Updated:** 2026-07-06

---

## What This Repository Is

**keyhole-developer-kit** is the first governed external participant
repository in the Keyhole ecosystem. It provides public SDKs, CLI tooling,
schemas, a local test runtime, and onboarding documentation for builders
who want to interact with Keyhole governance runtimes.

It is a **separate repository** from the Keyhole platform. It does not
contain, reference, or depend on private platform source code.

---

## Core Trust Properties

### 1. Boundary-First

This repository learns platform truth through the MCP boundary — not
through private platform source inspection, verbal lore, or internal
repository access.

The boundary begins at:

```
GET /mcp/v1/capabilities
```

This single unauthenticated endpoint is the initial source of truth for
any external participant. From it, a builder learns the current contract
version, transport posture, authentication requirements, and available
operations.

### 2. Discovery-First

Every participant interaction starts with live boundary discovery.
The developer kit does not hardcode platform assumptions. It discovers:

- contract version
- auth flow and realm
- transport mechanism
- minimum SDK version
- available operations and context surfaces

This means a builder's first action is always to ask the boundary what is
true — not to guess from documentation that may lag behind reality.

### 3. Context-Before-Assumption

Before making decisions about platform structure, run types, or supported
surfaces, the developer kit retrieves governed context through the
boundary. This prevents stale-assumption drift and ensures participant
behavior is aligned with current platform truth.

### 4. Exact Run-Type Discipline

Run types are exact canonical keys — not REST resource guesses. The SDK
enforces this through:

- `RunTypeValidator` — validates run-type names against known canonical keys
- `SchemaHelper` — retrieves request-shape guidance
- `DispatchPreflight` — composes validation and schema into a preflight gate

This prevents guessed names, pluralization errors, or improvised
run-type keys from reaching the boundary.

### 5. Reproducible Read-Only Smoke Path

The developer kit provides a 4-phase read-only smoke path that verifies
the full participant connection chain:

1. **Discover** — capabilities retrieval (unauthenticated)
2. **Identity** — participant identity inspection (authenticated)
3. **Context** — governed context retrieval
4. **Safe Run** — read-only run dispatch

This path is strictly read-only. It never mutates platform state.
When all four phases pass, the participant has a verified open path
to the governed boundary.

### 6. No Private Platform Intimacy Required

The repository is designed so that a builder can:

- clone the repo
- install the SDK and CLI
- start the local test runtime
- run the read-only smoke path
- begin governed development

without needing access to private platform source code, undocumented
setup procedures, or insider knowledge.

---

## What Is Supported Now

The developer kit provides production-backed governed repo proof for the
blessed public example and launch-grade client support for:

| Capability | SDK Surface | Status |
|-----------|-------------|--------|
| Capabilities discovery | `CapabilitiesClient` | Supported |
| Auth / identity bootstrap | `AuthProvider`, `BearerTokenProvider` | Supported |
| Identity inspection | `GET /mcp/v1/whoami` | Supported |
| Governed context retrieval | `ContextClient`, `ContextSnapshot` | Supported |
| Run-type validation | `RunTypeValidator`, `DispatchPreflight` | Supported |
| Read-only smoke path | `ReadOnlySmokeRunner` | Supported |
| Local test runtime | Docker Compose | Supported |
| CLI quickstart | `keyhole version`, `keyhole doctor` | Supported |
| Governed repo proof | `keyhole governed run/status/receipt` for `examples/second-governed-app` | Supported |

---

## What Is Scaffolded for Later

Some surfaces exist in shape but are not yet connected to live platform
flows. These are intentionally scaffolded and clearly marked:

| Capability | SDK Surface | Status | Depends On |
|-----------|-------------|--------|------------|
| Participant contract placeholders | `ParticipantContractPlaceholder` | Scaffolded | DEV-UX-03 |
| Repository registration command | `keyhole repo register --path <repo>` | Operational CLI path; requires live MCP credentials and boundary support | MCP boundary |
| Proof bundle submission | `ProofBundlePlaceholder` | Scaffolded | DEV-UX-04 |
| Verdict retrieval | `VerdictRetrievalAdapter` | Scaffolded | DEV-UX-06 |
| Recursive demo handoff | `DemoFlowRunner` (handoff phase) | Scaffolded | DEV-UX surfaces |

These scaffolded surfaces:

- exist as importable classes with deliberate shapes
- return `supported=False` from adapter operations
- declare `SupportStatus.SCAFFOLDED` explicitly
- will connect cleanly when platform-side surfaces stabilize
- do not claim to be operational

---

## What This Repository Does Not Claim

- **Proof submission is not operational.** Proof bundles can be assembled
  locally but cannot be submitted to the platform yet.
- **Recursive promotion is not complete.** The full governed change loop
  awaits platform-side DEV-UX closure.
- **Write authority is not granted by default.** Authentication alone does
  not confer write or proof-bearing authority.
- **Event Spine evidence is not produced in local-only mode.** Local-only
  realizations are useful for development but are not upstream-auditable.
- **Mocked governed-path tests are not live proof.** They verify runtime and
  SDK/CLI receipt handling without mutating MCP, Event Spine, ATP, or
  controller state.
- **my-first-app is governed only after the live boundary flow succeeds.**
  Local invariant proof can be submitted as input, but a governed claim
  requires MCP registration, context binding, a governed runtime receipt, and
  an MCP/Event Spine evidence reference returned by the platform.
- **Live verification is credential-gated.** `scripts/verify_s51_c02_live_boundary.py`
  skips when `KEYHOLE_MCP_URL` or `KEYHOLE_MCP_TOKEN` is absent and prints only
  redacted receipt fields when it runs.
- **Local CLI state is not source.** Governed CLI run state under
  `.keyhole/governed-runs/` is non-secret execution state for status, resume,
  and receipt recovery. It should not be treated as closure evidence by itself.
- **The public happy path is the governed CLI.** `keyhole governed run`,
  `status`, `resume`, and `receipt` are the supported operator path for
  external builders; ad hoc verifier scripts are supporting proof tools.
- **The public SDK/CLI is technical preview / early access until the product
  envelope is fully gated.** Core governed proof is real, but complete-product
  marketing still depends on clean-clone release proof, package launcher smoke,
  CI release gates, and server-advertised optional observability/support
  surfaces.
- **Optional surface degradation is not core-governance failure.**
  `keyhole surfaces` can report a degraded posture when optional explainability,
  support bundle, run tail, budget visibility, or async accept surfaces are not
  advertised. Missing required identity, repo registration, context compile,
  run dispatch, or governed realization surfaces are blockers.

---

## Who This Repository Is For

The developer kit is designed for:

- **Lance** and future external builders who need a governed participant
  entrypoint
- **Agent-assisted builder flows** that use Copilot or similar tools with
  the provided agent instructions
- **Future governed participants** who will build on this pattern
- **Anyone** who wants to interact with Keyhole governance runtimes
  through the public boundary

---

## How Trust Is Established

Trust in this repository rests on five pillars:

1. **Separation** — the repo is constitutionally separate from the platform
2. **Discovery** — it begins with live boundary truth, not assumptions
3. **Reproducibility** — the smoke path proves the connection chain works
4. **Honesty** — it clearly distinguishes what works now from what is planned
5. **Independence** — it can be used without private platform knowledge

These properties are verified through the launch readiness checklist,
smoke evidence bundle, and test suite.
