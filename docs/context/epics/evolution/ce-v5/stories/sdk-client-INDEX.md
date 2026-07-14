# sdk-client-INDEX.md

# SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX

**Status:** MASTER GUIDANCE - REVISED FOR SCALE-SAFE EXTERNALIZATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (design + validation), Prod (promotion only)  
**Purpose:** Define the canonical client-side builder boundary for the Keyhole ecosystem, including CLI onboarding, repository scaffolding, declaration artifacts, capability discovery, registration, governed run UX, proof bundle generation, repository ingestion, repair guidance, and the client-side scaling disciplines required for safe external SDK expansion.

---

## 1. Mission

SDK-CLIENT establishes the **official builder entry point** into the Keyhole ecosystem.

This epic defines how a developer or organization:

1. discovers Keyhole,
2. creates an account,
3. authenticates through the governed boundary,
4. scaffolds a governed repository,
5. declares or infers capabilities and dependencies,
6. validates local contracts,
7. registers with the MCP server,
8. compiles or resolves governed context,
9. runs governed workflows safely,
10. inspects run status, events, proof, and governance decisions,
11. emits attributable events into the Event Spine,
12. produces replayable proof bundles,
13. ingests and graphs existing repositories,
14. receives deterministic remediation guidance,
15. gradually aligns legacy systems into Keyhole governance without unsafe direct mutation.

The SDK is **not** an alternate control plane.  
It is a **governed bridge** to the MCP spine.

---

## 2. Why This Epic Exists

The SDK is the first public builder surface that translates Keyhole doctrine into usable developer workflow.

It must make the following simultaneously true:

- the first builder experience is simple,
- the developer boundary remains governed,
- capabilities become reusable and discoverable,
- existing repositories can be brought under governance gradually,
- all participation remains attributable, replayable, and auditable,
- the platform accumulates capability knowledge and institutional intelligence rather than scattered tooling,
- client behavior remains safe under retries, flaky networks, long-running execution, concurrent runs, and external SDK scale.

This epic is not merely a packaging effort. It is the formal definition of how external builders enter the Keyhole ecosystem **without bypassing execution safety, context governance, or memory containment**.

---

## 2a. Implemented Baseline

The following stories are already sealed with passing tests and evidence:

| Story | Status | Evidence |
|-------|--------|----------|
| [sdk-client-00.md](sdk-client-00.md) | **COMPLETE** | `docs/evidence/sdk-client-00/COMPLETION_REPORT.md` - 85/85 tests |
| [sdk-client-01.md](sdk-client-01.md) | COMPLETE / INTEGRATED | `docs/evidence/sdk-client-01/COMPLETION_REPORT.md` - 85/85 tests |
| [sdk-client-01-a.md](sdk-client-01-a.md) | **COMPLETE** | `docs/evidence/sdk-client-01/HARDENING_REPORT.md` - 106/106 tests |
| [sdk-client-01-b.md](sdk-client-01-b.md) | **NOT STARTED** | Logout, profile listing, profile switching, token lifecycle - story file created, no tests yet |
| [sdk-client-01-c.md](sdk-client-01-c.md) | **COMPLETE** | 182/182 tests (`tests/unit/test_sdk_client_01c_doctor_reconciliation.py`) |
| [sdk-client-01-d.md](sdk-client-01-d.md) | **COMPLETE** | 64/64 tests (`tests/unit/test_sdk_client_01d_host_reconciliation.py`) |
| [sdk-client-01-e.md](sdk-client-01-e.md) | **COMPLETE** | 24/24 tests (`tests/unit/test_sdk_client_01e_auto_detection.py`) |
| [sdk-client-07.md](sdk-client-07.md) | **COMPLETE** | 95/95 tests (`tests/unit/test_sdk_client_07_repo_register.py`) |
| [sdk-client-08.md](sdk-client-08.md) | **COMPLETE** | 72/72 tests (`tests/unit/test_sdk_client_08_capability_discovery.py`) |
| [sdk-client-19.md](sdk-client-19.md) | **COMPLETE** | 150/150 tests (`tests/unit/test_sdk_client_19_budget_limit_visibility.py`) |
| [sdk-client-20.md](sdk-client-20.md) | **COMPLETE** | 212/212 tests (`tests/unit/test_sdk_client_20_explainability.py`) |
| [sdk-client-21.md](sdk-client-21.md) | **COMPLETE** | 115/115 tests (`tests/unit/test_sdk_client_21_surface_negotiation.py`) |
| [sdk-client-22.md](sdk-client-22.md) | **COMPLETE** | 73/73 tests (`tests/unit/test_sdk_client_22_deregister.py`) |
| [sdk-client-03.md](sdk-client-03.md) | **COMPLETE** | 154/154 tests (`tests/unit/test_sdk_client_03_capability_namespace.py`) |
| [sdk-client-04.md](sdk-client-04.md) | **COMPLETE** | 137/137 tests (`tests/unit/test_sdk_client_04_governance_contract.py`) |

The identity onboarding (`keyhole auth register` -> `keyhole verify`) and authentication bootstrap (`keyhole login` -> `keyhole whoami`) foundations are production-sealed. This epic is not a purely future-planned roadmap - the critical pre-auth and auth baseline is already closed.

---

## 3. Constitutional Anchors

SDK-CLIENT must preserve the following architectural truths:

- **Event Spine is canonical truth.**
- **Promotion is the sole canonical mutation path.**
- **The MCP boundary is the only approved public participation surface.**
- **Builders declare intent through artifacts; they do not directly mutate the platform.**
- **All governed participation must trace back to tenant, org, user, cohort, worker, repo, workspace, and purpose.**
- **A zipper is not closed until it produces a replayable proof bundle.**
- **Trust metadata must be representable now, even if enforcement is phased.**
- **Governed execution must be context-bound.**
- **Write-bearing participation must be idempotent and replay-safe.**
- **The client must not expose direct canonical memory access.**

---

## 4. Strategic Outcome

When this epic is complete, a builder must be able to do one of two things quickly and safely.

### 4.1 Greenfield path

```text
pip install keyhole-cli
keyhole auth register
keyhole verify
keyhole login
keyhole init vertical
keyhole validate
keyhole repo register
keyhole context compile
keyhole run --context auto
```

### 4.2 Existing repo path

```text
pip install keyhole-cli
keyhole login
keyhole ingest . --shadow
```

In both paths, the builder must receive immediate value and produce attributable, replayable, governed outcomes.

The client must also make the following possible without exposing raw platform internals:

- inspect active identity and scope,
- inspect governed context,
- inspect run status and proof,
- recover safely from retries, network flakes, and accepted async execution,
- understand why a command was accepted, deferred, rejected, or replayed.

---

## 5. Final Epic Success Criteria

SDK-CLIENT is complete only when all of the following are true:

- a new developer can authenticate without manual `.env` creation,
- the CLI owns credential bootstrap and the SDK consumes local credentials rather than demanding preconfiguration,
- a governed repository scaffold is generated automatically,
- declaration artifacts are standardized and tool-managed,
- capability naming, versioning, and dependency declaration rules are enforced,
- dependency resolution is deterministic and explainable,
- registration with MCP is deterministic, attributable, auditable, and idempotent,
- governed runs require context and cannot float without it,
- a governed run can execute end-to-end under accepted async semantics,
- the client supports run tracking, polling, and/or stream-safe status inspection,
- every write-bearing client action carries request identity and operation identity,
- retry, backoff, defer, and replay behavior are safe and explicit,
- every zipper emits a replayable proof bundle,
- repository ingestion can graph a repo and produce confidence-scored governance gap suggestions,
- identity context is present across registration, run, event, and proof flows,
- emitted events are classified and routed with retention hints,
- proof bundles are split into hot replay core and cold extended evidence,
- trust metadata hooks exist in passports and proof bundles,
- no SDK surface exposes direct canonical memory access,
- the first useful output appears within the first 10 minutes for a new builder,
- the platform remains adoption-friendly through progressive disclosure rather than exposing all governance complexity up front.

---

## 6. Non-Goals

SDK-CLIENT does **not**:

- expose cluster credentials,
- embed promotion kernel logic,
- allow direct canonical mutation,
- bypass the MCP boundary,
- silently rewrite builder repositories,
- auto-promote capabilities into canon,
- replace the governance kernel,
- implement final marketplace economics or royalty settlement in this epic,
- require every builder workflow to hard-gate on full SBOM / attestation / transparency verification on day one,
- expose Qdrant or internal memory primitives directly as public client APIs,
- hide long-running execution behind fake synchronous success semantics.

---

## 7. Design Principles

### 7.1 SDK is not the control plane

The SDK is a governed client. The MCP server remains the sole public control boundary.

### 7.2 Authentication belongs to the CLI layer

The SDK must not require a pre-existing `.env` for first connection. Authentication is handled by the CLI through approved auth flows.

### 7.3 Declarative participation only

Builders participate by editing or generating declaration artifacts, not by imperative platform mutation.

### 7.4 Repo shape is a governance primitive

Every governed repo must share a predictable file structure.

### 7.5 Capability naming and versioning must be globally legible

Capabilities must follow hierarchical namespace rules and explicit major-version semantics.

### 7.6 Capability proofs are portable

Descendants inherit upstream governance requirements, but proof satisfaction may be delegated via capability passports.

### 7.7 Existing repos must enter gradually

The system must support governance alignment by ingestion, graphing, and remediation guidance, not only greenfield scaffolds.

### 7.8 No floating execution

Every command, run, event, registration, and proof bundle must include deterministic identity context.

### 7.9 Version labels are insufficient by themselves

Capability safety requires version + provider + digest + compatibility semantics + deterministic resolution.

### 7.10 Not all evidence deserves equal weight

Replay-critical truth belongs on the hot path. Large auxiliary evidence belongs in referenced extended storage.

### 7.11 Progressive disclosure is mandatory

The SDK must feel easy first and reveal governance depth gradually. Builders should see value before complexity.

### 7.12 Failure must produce repair guidance

Every rejection path should surface deterministic reasons and next-best actions rather than dead ends.

### 7.13 Context is mandatory for governed execution

The client must not permit governed runs to float without explicit governed context. Convenience wrappers are allowed; hidden context bypass is not.

### 7.14 Write-bearing participation must be idempotent by default

Write-bearing commands must send `X-Request-Id` and `X-Idempotency-Key` automatically, preserve those across retries of the same attempt, and normalize replay/conflict/defer semantics.

### 7.15 Async run UX is first-class

The client must support accepted async execution patterns (`accepted + run_id`, polling, optional stream visibility) rather than assuming every governed run returns a final result inline.

### 7.16 No direct canonical memory access

The SDK must not expose direct canonical memory query/write as a primary public client primitive. Memory interaction must occur through governed run/context surfaces.

### 7.17 Explainability is part of the product

Builders must be able to inspect identity, context, runs, proof, budget posture, and repair guidance without reverse-engineering the platform.

---

## 8. Adoption-First Builder Experience

The architecture is strong enough to become adoption-hostile if exposed too bluntly. Therefore the SDK must be designed around progressive disclosure.

### 8.1 The first 10-minute rule

A new builder must be able to go from zero to first useful output in under 10 minutes.

### 8.2 The first wow moment

At least one of the following must appear quickly:

- a valid governed run result,
- an architecture graph of the current repository,
- confidence-scored inferred capabilities,
- deterministic remediation suggestions,
- a visible proof bundle summary,
- a visible governed context summary.

### 8.3 Progressive disclosure levels

```text
Level 0: install + login + run or ingest
Level 1: identity, context, and proof visibility
Level 2: validate and register explicitly
Level 3: edit contracts and capability declarations
Level 4: advanced dependency, trust, governance, and scaling controls
```

### 8.4 Shadow mode

The SDK must support shadow participation for low-risk onboarding.

Examples:

```text
keyhole run --shadow
keyhole ingest --shadow
```

Shadow mode may:

- simulate MCP participation,
- generate proof bundles,
- validate local behavior,
- avoid irreversible registration or production-side effect.

This allows builders to experience the platform before committing real state.

---

## 9. Identity, Binding, and Visibility

The identity model is only useful if builders can see it and the system can prove it.

### 9.1 Required identity context

Every registration, run, event, and proof bundle must carry:

```json
{
  "tenant_id": "...",
  "org_id": "...",
  "user_id": "...",
  "cohort_id": "...",
  "worker_id": "...",
  "repo_id": "...",
  "workspace_id": "...",
  "origin": "...",
  "purpose": "..."
}
```

### 9.2 Identity UX

The SDK must expose a clear identity inspection surface.

Example:

```text
keyhole whoami
```

This must return enough information for a builder to understand:

- who they are acting as,
- what tenant/org they are in,
- what cohort/worker is active,
- what workspace they are using,
- whether they are in shadow, dev, or real governed mode.

### 9.3 Principle

No floating execution. Ever.

---

## 10. Standard Repo Shape

Every governed repo created by the SDK must include a predictable structure.

```text
repo/
 --- keyhole.yaml
 --- governance_contract.yaml
 --- capability_passport.yaml
 --- dependencies.yaml
 --- capabilities/
 --- src/
 --- tests/
 --- docs/
 --- proof_bundle/
```

### 10.1 Required files

- `keyhole.yaml` - repo-level Keyhole identity and metadata
- `governance_contract.yaml` - local governance requirements and gates
- `capability_passport.yaml` - current declared/proven capability surface
- `dependencies.yaml` - consumed capabilities and versions/providers

### 10.2 Rule

These files are canonical and tool-managed where possible. Builders may inspect and edit them, but the CLI is responsible for generating and validating them.

---

## 11. Capability Naming, Versioning, and Compatibility

### 11.1 Canonical capability shape

```text
<domain>.<category>.<capability>.v<major>
```

### 11.2 Examples

- `payment.stripe.integration.v1`
- `crm.salesforce.sync.v1`
- `robotics.lidar.calibration.v2`
- `workorder.assignment.engine.v1`

### 11.3 Enforcement

The CLI must reject invalid names during creation and validation.

### 11.4 Versioning rule

- breaking changes require a new major version,
- a published major line must not silently change declared behavior,
- compatibility and deprecation semantics must be explicit,
- builder-facing tools must make upgrade boundaries obvious.

### 11.5 Compatibility contract requirement

Each capability line must support compatibility metadata sufficient to explain:

- what stays stable,
- what changed,
- what is deprecated,
- what upgrade path exists.

### 11.6 Capabilities are APIs

Treat capabilities the way serious platforms treat API surfaces: stability must be explicit, upgrade behavior must be intentional, and breaking changes must be named rather than hidden.

---

## 12. Dependency Declaration and Deterministic Resolution

Version labels alone are not enough.

### 12.1 Dependency declaration shape

```yaml
dependencies:
  - capability: payment.stripe.integration.v1
    provider: workorder-platform
    digest: sha256:...
  - capability: crm.salesforce.sync.v2
    provider: crm-platform
```

### 12.2 Deterministic resolution requirements

Each dependency must be resolvable by:

- capability name,
- major version,
- provider,
- immutable digest where pinned,
- compatibility/deprecation contract.

### 12.3 Resolver behavior

Production-safe resolution must be deterministic and fail-closed.

Priority order:

1. explicitly pinned provider + version,
2. tenant policy override,
3. org policy override,
4. platform default provider,
5. otherwise fail.

### 12.4 Resolution proof

Every resolution decision must be materializable and explainable.

Example resolution record:

```json
{
  "requested": "payment.stripe.integration.v1",
  "resolved_to": "repo://workorder-platform@sha256:abc...",
  "reason": "pinned provider + version"
}
```

### 12.5 Rule

No implicit capability dependency should be trusted for governed reuse unless it is declared or inferred and then explicitly accepted.

---

## 13. Capability Passport Model

Capability passports are the portable proof objects that let downstream repos inherit proven behavior without re-running every ancestor gate.

### 13.1 Passport responsibilities

A capability passport must declare:

- capability name,
- version,
- owner repo,
- visibility,
- proof references,
- delegated capabilities,
- parent lineage,
- signature / digest anchor,
- optional trust metadata references.

### 13.2 Draft shape

```yaml
capability: payment.stripe.integration.v1
owner_repo: workorder-platform
visibility: public
proofs:
  - event_ref: evt_12345
delegated_capabilities:
  - identity.auth.v1
parent_repo: keyhole-platform
signature: sha256:...
trust:
  sbom_digest: null
  attestation_digest: null
  rekor_entry_uuid: null
```

### 13.3 Design constraint

A passport is **not** a secret-bearing token. It is a transport-safe governance object.

---

## 14. Governance Contract Model

Governance contracts express what the repo promises locally beyond inherited platform invariants.

### 14.1 Governance contract responsibilities

A governance contract must declare:

- repo identity,
- parent repo / lineage,
- local capabilities produced,
- required tests,
- integration contracts,
- local invariants,
- deprecation or compatibility rules where applicable.

### 14.2 Draft shape

```yaml
repo: workorder-platform
parent_repo: keyhole-platform
produces:
  - payment.stripe.integration.v1
  - workorder.assignment.engine.v1
required_tests:
  - stripe_webhook_validation
  - apex_schema_consistency
local_invariants:
  - no_unversioned_dependencies
compatibility_contracts:
  - payment.stripe.integration.contract.v1
```

---

## 15. Repository Ingestion and Governance Alignment

The platform must meet builders where they already are.

### 15.1 Command

```text
keyhole ingest <path-or-url>
```

### 15.2 Responsibilities

The ingestion flow must:

1. scan repo structure,
2. inspect dependency manifests,
3. infer capabilities,
4. build an architecture/capability graph,
5. identify governance gaps,
6. write graph artifacts to the platform,
7. return suggested remediation/alignment actions.

### 15.3 Important constraints

The SDK must **not silently mutate the repo** during ingestion.

It may generate artifacts and suggestions, but builder-visible adoption of changes must remain explicit.

Inference must carry confidence and must not auto-register new capabilities without builder approval.

### 15.4 Example outputs

- inferred capabilities,
- inference confidence,
- architecture graph,
- missing tests,
- candidate governance contract,
- suggested capability substitutions,
- dependency versioning issues.

### 15.5 Ingestion safety principle

Suggest. Never assume.

---

## 16. Failure and Repair UX

A governed system that only says "no" will fail adoption.

### 16.1 Every reject path must include

- reject class,
- deterministic reason,
- affected artifact or dependency,
- next-best repair suggestions.

### 16.2 Example

```json
{
  "status": "REJECT",
  "reason": "missing dependency provider pin",
  "repair": [
    "pin payment.stripe.integration.v1 provider",
    "run keyhole search stripe"
  ]
}
```

### 16.3 Principle

Failure must produce repair guidance, not a dead end.

---

## 17. Event Classification, Retention, and Enforcement

Event growth must be handled as a design primitive, not a future optimization.

### 17.1 Every emitted event must include

- `event_class`
- `importance`
- `retention_hint`
- `correlation_id`
- identity context

### 17.2 Minimum classes

- `critical` - auth, gates, promotion, security, ACCEPT/REJECT
- `operational` - runs, registration, validation, ingestion summaries
- `noise` - heartbeat, debug, high-frequency progress telemetry

### 17.3 Routing principle

- truth events belong in long-retention governed streams,
- operational events belong in medium-retention streams,
- noise events belong in short-retention / sampled / aggressively expired paths.

### 17.4 Server enforcement requirements

The server must not trust SDK-provided classification blindly.

Required enforcement classes include:

- event class validation,
- event rate limiting,
- event size limits,
- rejection or deterministic defaulting when fields are missing.

### 17.5 Principle

Event classification is declarative at the edge and enforced at the spine.

---

## 18. Proof Bundle Contract

Proof bundles are table stakes for this epic.

### 18.1 Minimum proof bundle shape

```text
proof_bundle/
  --- core.json
  --- request.json
  --- response.json
  --- event_chain.json
  --- passport.json
  --- verification_result.json
  --- identity_context.json
  --- context.json
  --- correlation.json
  --- summary.md
  --- diff.json
  --- digest.txt
  --- extended/
```

### 18.2 Required semantics

- `core.json` contains replay-critical truth,
- `summary.md` is human-readable proof summary,
- `diff.json` explains what changed vs prior comparable execution when applicable,
- `context.json` captures governed context identity or references it,
- `extended/*` contains non-essential large artifacts.

### 18.3 Replay requirement

A zipper is replayable if the hot proof core contains enough information to reconstruct and verify the execution without requiring large extended artifacts.

### 18.4 Storage principle

- `core.json` -> hot, replay-required, queryable
- `extended/*` -> referenced, optional, cold-capable evidence

### 18.5 Principle

Not all evidence deserves equal weight.

---

## 19. Trust Readiness (SBOM / Attestation / Transparency)

Trust hardening must be schema-complete now, even if enforcement is phased.

### 19.1 This epic requires

- reserved SBOM fields,
- reserved attestation fields,
- reserved transparency-log / Rekor fields,
- digest-addressable references in passports and proof bundles.

### 19.2 This epic does not yet require

- universal builder-facing hard gates on trust verification,
- full launch-blocking submission workflows for every builder action.

### 19.3 Principle

Trust metadata must be schema-complete in this epic. Trust enforcement can be phased.

---

## 20. MCP Surface Expectations / Dependencies

SDK-CLIENT assumes the MCP surface supports the minimum necessary builder flow.

### 20.1 Required existing or parallel capabilities

- identity / `whoami`,
- auth bootstrap / approved auth flow,
- context compile / context get,
- governed run dispatch,
- accepted async execution contract for long-running work,
- run status / run inspection surface,
- event emission / query where used for provenance and analysis,
- proof core storage / retrieval,
- capability disclosure.

### 20.2 Strongly recommended parallel or near-term surface additions

- capability registry listing / discovery,
- dependency resolution / capability resolution,
- capability registration endpoint or equivalent governed run type,
- event emit completion if currently incomplete,
- cohort self-introspection if needed for local runtime context,
- run event stream or SSE compatibility,
- budget / limit inspection surface,
- explainability / support-bundle lookup surface.

### 20.3 Explicit tightening for scaling objectives

The client roadmap now assumes:

- no direct canonical memory query/write from SDK,
- governed execution requires context,
- write-bearing commands require request identity and idempotency identity,
- long-running work may return `accepted + run_id` instead of a final inline result,
- retries must be lawful under S46/S47 server guarantees rather than optimistic client resubmission.

This epic may depend on one or more adjacent MCP stories if the SDK builder journey cannot be completed without them.

---

## 21. Zippered Delivery Model

This epic is executed as **paired stories** across:

- **Server (Keyhole Platform / MCP boundary)**
- **Client (SDK / CLI / Repo)**

Each story pair must close a functional loop and produce proof artifacts demonstrating:

- end-to-end execution,
- attribution (tenant/org/user/cohort/worker/repo/workspace),
- event emission,
- deterministic behavior,
- replayable proof core,
- failure -> repair guidance where applicable.

A story is **not complete** unless both sides pass and emit proof.

In addition, broad write-bearing externalization is not complete unless the cross-cutting client scaling stories are sealed:

- request identity,
- idempotent transport,
- context-bound run UX,
- accepted async execution handling,
- no direct canonical memory access,
- budget and explainability visibility.

---

## 22. Zippered Story Outline

### Story File Registry

| File | Story / Discipline | Status | Summary |
|------|--------------------|--------|---------|
| [sdk-client-00.md](sdk-client-00.md) | SDK-CLIENT-00 | **COMPLETE** | Identity Creation & Verification (Client) |
| [sdk-client-01.md](sdk-client-01.md) | SDK-CLIENT-01 | COMPLETE / INTEGRATED | Authentication Bootstrap |
| [sdk-client-01-a.md](sdk-client-01-a.md) | SDK-CLIENT-01-A | **COMPLETE** | Auth Bootstrap Hardening (Server-Aligned Identity Governance) |
| [sdk-client-01-b.md](sdk-client-01-b.md) | SDK-CLIENT-01-B | **NOT STARTED** | Logout, Profile Listing, Profile Switching, Token Lifecycle |
| [sdk-client-01-c.md](sdk-client-01-c.md) | SDK-CLIENT-01-C | **COMPLETE** | MCP Host Identity Reconciliation, Doctor Discovery, Connection Binding UX (182/182 tests) |
| [sdk-client-01-d.md](sdk-client-01-d.md) | SDK-CLIENT-01-D | **COMPLETE** | Host Credential Installation, Extension Reconciliation, Live Principal Alignment (64/64 tests) |
| [sdk-client-01-e.md](sdk-client-01-e.md) | SDK-CLIENT-01-E | **COMPLETE** | Auto-Detection, MCP Boundary Probing, Governed Mode Auto-Promotion (24/24 tests) |
| [sdk-client-02.md](sdk-client-02.md) | SDK-CLIENT-02 | **COMPLETE** | Governed Repo Scaffold (`keyhole init vertical`) |
| [sdk-client-09.md](sdk-client-09.md) | SDK-CLIENT-09 | **COMPLETE** | Governed Run Dispatch (`keyhole run` / `keyhole run --shadow`) |
| [sdk-client-15.md](sdk-client-15.md) | SDK-CLIENT-15 | **COMPLETE** | Idempotent Transport, Retry, and Request Identity (Client) |
| [sdk-client-16.md](sdk-client-16.md) | SDK-CLIENT-16 | **COMPLETE** | Context Lifecycle and Governed Run Binding |
| [sdk-client-17.md](sdk-client-17.md) | SDK-CLIENT-17 | **COMPLETE** | Async Run Tracking, Polling, and Durable Run UX |
| [sdk-client-10.md](sdk-client-10.md) | SDK-CLIENT-10 | **COMPLETE** | Repository Ingestion and Graph (`keyhole ingest` / `keyhole ingest --shadow`) |
| [sdk-client-07.md](sdk-client-07.md) | SDK-CLIENT-07 | **COMPLETE** | Repository Registration with MCP (`keyhole repo register`) |
| [sdk-client-08.md](sdk-client-08.md) | SDK-CLIENT-08 | **COMPLETE** | Capability Discovery and Resolution (`keyhole search` / `keyhole dependency resolve`) |
| [sdk-client-18.md](sdk-client-18.md) | SDK-CLIENT-18 | **COMPLETE** | Memory Boundary Enforcement (77/77 tests) |
| [sdk-client-19.md](sdk-client-19.md) | SDK-CLIENT-19 | **COMPLETE** | Budget, Limit, and Overload Visibility (150/150 tests) |
| [sdk-client-20.md](sdk-client-20.md) | SDK-CLIENT-20 | **COMPLETE** | Governance Explainability and Support Bundles (212/212 tests) |
| [sdk-client-21.md](sdk-client-21.md) | SDK-CLIENT-21 | **COMPLETE** | Surface Negotiation & Compatibility Guardrails |
| [sdk-client-22.md](sdk-client-22.md) | SDK-CLIENT-22 | **COMPLETE** | Account Deregistration and Deletion UX |

---

### Implementation Gating Note

The story numbers are semantically organized, not a strict execution sequence. The cross-cutting scale/safety stories (15-21) gate earlier functional stories for broad externalization:

- **SDK-CLIENT-15** gates broad write-bearing work (02-14 can prototype locally, but safe external writes require 15)
- **SDK-CLIENT-16** and **SDK-CLIENT-17** gate broad governed run expansion (runs work functionally via 09, but context-binding and async safety require 16-17)
- **SDK-CLIENT-18** gates any client memory-facing ergonomics
- **SDK-CLIENT-19** and **SDK-CLIENT-20** gate production-grade externalization (budget visibility and explainability)
- **SDK-CLIENT-21** gates safe client behavior against evolving server surfaces
- **SDK-CLIENT-22** closes the builder identity lifecycle (enter via 00, exit via 22)

---

### SDK-CLIENT-00 - Identity Creation & Verification OK COMPLETE

**Client ([sdk-client-00.md](sdk-client-00.md))** - **COMPLETE**

- `keyhole auth register` - identity creation request shaping and submission
- `keyhole verify` - guided verification flow and verification status polling
- explicit dev/test origin and purpose stamping for `kh-dev` identities
- clear pending / verified / failed onboarding UX with repair guidance
- replayable onboarding proof bundle closure
- clean handoff to SDK-CLIENT-01 (auth bootstrap) upon verified active identity

**Server (sdk-server-00.md)**

- registration endpoint
- verification endpoint
- natural-key duplicate-identity protection

**Proof / Tests**

- new builder identity created end-to-end
- duplicate registration blocked deterministically
- verification completes and status reflects correctly
- onboarding proof bundle emitted and replayable
- event: `IDENTITY_CREATED`, `IDENTITY_VERIFIED`

---

### SDK-CLIENT-01 - Authentication Bootstrap OK COMPLETE / INTEGRATED

**Client (sdk-client-01.md)**

- implement `keyhole login`
- PKCE / device flow support
- secure local credential store
- `keyhole whoami`

**Server (sdk-server-01.md)**

- auth endpoints
- `/whoami` identity surface
- identity context issuance

**Proof / Tests**

- login -> token issued
- `whoami` returns correct identity context
- token usable across endpoints
- shadow vs real mode visible
- event: `AUTH_SUCCESS`

---

### SDK-CLIENT-02 - Governed Repo Scaffold OK COMPLETE

**Client ([sdk-client-02.md](sdk-client-02.md))** - **COMPLETE**

- `keyhole init vertical`
- generate canonical repo structure + files
- include context/proof-ready placeholders
- deterministic file plan with SHA-256 digest
- rerun safety (detect existing scaffold)
- `--force`, `--dry-run`, `--template`, `--non-interactive` flags
- local-only, offline-safe - no MCP interaction

**Server (sdk-server-02.md)**

- publish canonical schema definitions
- optional remote scaffold validation

**Proof / Tests**

- scaffold passes schema validation
- deterministic generation
- trust-ready placeholders included
- context/proof placeholders included where required

---

### SDK-CLIENT-03 - Capability Namespace Enforcement

**Client (sdk-client-03.md)** OK COMPLETE

- `validate_capability_name(name)` -> `CapabilityValidationResult` - section6.2, section8, section13
- `create_capability_name(domain, category, capability, major)` -> `str` - section6.1
- `normalize_capability_parts(domain, category, capability, major)` -> normalized tuple - section8.4
- `CapabilityNameParts` Pydantic model with `canonical_name` property
- `CapabilityValidationResult` with `is_valid`, `to_dict()`, `reject_reasons`
- `NamespaceRejectReason` enum - 7 deterministic codes (section8.5)
- `CapabilityNameError(ValueError)` exception with `reject_reasons`
- `emit_namespace_proof(state_dir, result, ...)` - section11, section16 out-of-tree artifacts
- `emit_namespace_batch_proof(state_dir, results, ...)` - batch ingestion filtering
- `keyhole capability create --domain X --category Y --name Z --major N` CLI command
- `keyhole capability validate <name>` CLI command
- Advisory-by-default for foreign repos; write mode for native repos (section9)
- Duplicate suppression in write mode (section10)
- 154 unit tests: 154/154 passed; 2487/2487 total (no regressions)

**Server (sdk-server-03.md)**

- registration-time namespace validation

**Proof / Tests**

- invalid names rejected client + server
- valid names accepted consistently
- version suffix enforcement works

---

### SDK-CLIENT-04 - Governance Contract + Dependency Schema

**Client (sdk-client-04.md)**

- local schema validation via `keyhole validate`

**Server (sdk-server-04.md)**

- contract ingestion + validation
- dependency normalization

**Proof / Tests**

- malformed contracts rejected
- valid contracts accepted and stored
- dependency/provider fields normalized
- event: `CONTRACT_REGISTERED`

---

### SDK-CLIENT-05 - Capability Passport Generation

**Client (sdk-client-05.md)**

- passport generation from repo

**Server (sdk-server-05.md)**

- passport verification + storage
- lineage linking

**Proof / Tests**

- passport deterministic for same input
- lineage correctly linked
- transport-safe shape enforced
- event: `PASSPORT_ACCEPTED`

---

### SDK-CLIENT-06 - Local Validation Pipeline

**Client (sdk-client-06.md)**

- `keyhole validate`
- schema + dependency + namespace + compatibility checks

**Server (sdk-server-06.md)**

- optional remote validation
- invariant enforcement hooks

**Proof / Tests**

- failing repo blocked
- passing repo emits validation success artifact
- compatibility violations rejected with repair suggestions

---

### SDK-CLIENT-07 - Repository Registration with MCP

**Implementation Status:** OK COMPLETE - 95/95 unit tests passing (`tests/unit/test_sdk_client_07_repo_register.py`). Registration modules: `keyhole_sdk/registration/{models,readiness,artifacts,payload,submitter,proof,repair}.py`. CLI command: `keyhole repo register` via `keyhole_cli/commands/repo_register_cmd.py`. Two registration sources: native (keyhole.yaml scaffold) and ingestion-backed (from SDK-CLIENT-10). Readiness preflight with 4-level model (native_ready/ingestion_ready/partially_ready/not_ready). Deterministic payload construction. MCP boundary submission via GovernedTransport with idempotent request identity. Identity binding extraction (tenant/org/cohort/worker/repo/workspace). Out-of-tree proof emission under `repo_register/<correlation_id>/`. Concrete repair guidance for all failure classes. Shadow mode support. No-silent-mutation guarantee. 16 new public SDK exports.

**Client (sdk-client-07.md)**

- `keyhole repo register`
- send contracts + passport + metadata

**Server (sdk-server-07.md)**

- registration endpoint
- identity binding (tenant/org/cohort/worker/repo/workspace)

**Proof / Tests**

- repo appears in registry
- identity bound correctly
- registration is idempotent
- event: `REPO_REGISTERED`

---

### SDK-CLIENT-08 - Capability Discovery and Resolution OK COMPLETE

**Client ([sdk-client-08.md](sdk-client-08.md))** - **COMPLETE**

- `keyhole search` - governed capability search
- `keyhole dependency resolve` - deterministic dependency resolution
- 72/72 tests (`tests/unit/test_sdk_client_08_capability_discovery.py`)

**Server (sdk-server-08.md)**

- capability registry endpoint
- deterministic resolver

**Proof / Tests**

- search returns correct capabilities
- resolution maps to valid providers deterministically
- ambiguous cases fail closed
- resolution record materialized
- event: `CAPABILITY_QUERY`

---

### SDK-CLIENT-09 - Governed Runtime Execution OK COMPLETE

**Client ([sdk-client-09.md](sdk-client-09.md))** - **COMPLETE**

- `keyhole run`
- `keyhole run --shadow`
- surface run outcome clearly under current contract

OK 76/76 unit tests passing (`tests/unit/test_sdk_client_09_governed_run.py`). Run dispatch modules: `keyhole_sdk/run_dispatch/{request_builder,preflight,dispatcher,proof_emitter,repair}.py`. CLI command: `keyhole run` / `keyhole run --shadow` with preflight validation, GovernedTransport dispatch, proof emission to proof_bundle/, outcome rendering (success/accepted/deferred/rejected/failed), and repair guidance.

**Server (sdk-server-09.md)**

- run dispatch
- traceable event emission

**Proof / Tests**

- run executes end-to-end
- correlation_id present across events
- event classification metadata stamped
- event chain verifiable
- failure paths emit repair guidance

**Note:** Broad write-bearing and long-running execution safety is tightened further by SDK-CLIENT-15 through SDK-CLIENT-20.

---

### SDK-CLIENT-10 - Repository Ingestion and Graph OK COMPLETE

**Client ([sdk-client-10.md](sdk-client-10.md))** - **COMPLETE**

- `keyhole ingest` - deterministic local scan, packaging, and submission
- `keyhole ingest --shadow` - exploratory ingestion mode
- `keyhole ingest --summary-only` - scan without submission
- `keyhole ingest --include/--exclude/--max-bytes` - bounded controls
- `IncludeExcludeFilter` - secret-safe defaults, conservative exclusion
- `scan_repo()` -> `build_ingestion_package()` -> `submit_ingestion()` pipeline
- `CompatibilityPosture` (foreign / partially_aligned / keyhole_ready)
- `ConfidenceLevel` (high / medium / low) for inferred capabilities
- Observed vs inferred distinction preserved throughout
- Proof artifacts emitted out-of-tree (`<state_dir>/ingest/<id>/`)
- No-silent-mutation guarantee - scan never modifies target repo
- 115/115 tests, full regression 1641 passed / 26 pre-existing fail

**Server (sdk-server-10.md)**

- ingestion endpoint
- graph builder
- capability inference

**Proof / Tests**

- repo graph created
- inferred capabilities stored with confidence scores
- no silent repo mutation
- event: `INGEST_COMPLETE`

---

### SDK-CLIENT-11 - Alignment Guidance

**Client (sdk-client-11.md)**

- render remediation suggestions and next-best actions

**Server (sdk-server-11.md)**

- gap analysis engine
- suggestion generation

**Proof / Tests**

- gaps identified deterministically
- suggestions reproducible
- inferred vs verified state clearly distinguished
- event: `GAP_ANALYSIS_COMPLETE`

---

### SDK-CLIENT-12 - Event Classification and Retention Routing

**Client (sdk-client-12.md)**

- emit classification metadata on SDK-originated events

**Server (sdk-server-12.md)**

- route events by class / retention policy
- enforce event envelope requirements

**Proof / Tests**

- events land in correct streams
- missing classification fields rejected or defaulted deterministically
- rate/size validation works

---

### SDK-CLIENT-13 - Proof Bundle Hot/Cold Split

**Client (sdk-client-13.md)**

- generate `core.json`, `summary.md`, `diff.json`, and `extended/*`

**Server (sdk-server-13.md)**

- store proof core hot
- store extended evidence by reference

**Proof / Tests**

- replay succeeds from core bundle only
- extended artifacts are addressable by digest
- large evidence does not block hot query path

---

### SDK-CLIENT-14 - Trust-Ready Metadata Hooks

**Client (sdk-client-14.md)**

- generate optional SBOM / attestation / transparency placeholders

**Server (sdk-server-14.md)**

- accept and persist trust metadata references

**Proof / Tests**

- trust-ready fields validate when present
- fields remain optional for first-run success
- digests / references preserved in passports and proof bundles

---

### SDK-CLIENT-15 - Idempotent Transport, Retry, and Request Identity

**Client ([sdk-client-15.md](sdk-client-15.md))**

- automatic `X-Request-Id` on every request
- automatic `X-Idempotency-Key` on all write-bearing commands
- retry/backoff discipline with jitter
- `Retry-After` handling
- typed replay / conflict / defer / missing-key errors
- local pending-operation journal for write-bearing attempts (request_id, idempotency_key, command, payload digest, created_at, last-known run_id) enabling safe resume after process crash

**Server (sdk-server-15.md)**

- platform-wide idempotency enforcement
- consistent problem-detail contract
- replay-safe registration / write-bearing semantics

**Proof / Tests**

- same write attempt + same key -> same outcome
- same key + different payload -> conflict
- retries preserve operation identity
- proof bundles include replay metadata

**Implementation Status:** OK COMPLETE - 79/79 unit tests passing (`tests/unit/test_sdk_client_15_idempotent_transport.py`). Transport modules: `keyhole_sdk/transport/{errors,operation_registry,idempotency,retry,proof_metadata,client}.py`. `GovernedTransport` wraps `requests.Session` with automatic `X-Request-Id`/`X-Idempotency-Key` injection, bounded retry with exponential backoff + jitter, `Retry-After` respect, conflict/defer/rate-limit/replay handling, and `TransportProofMetadata` capture. Central `OperationRegistry` with 16 built-in operations across 4 operation classes. 7 typed error classes with repair guidance.

---

### SDK-CLIENT-16 - Context Lifecycle and Governed Run Binding OK COMPLETE

**Client ([sdk-client-16.md](sdk-client-16.md))** - **COMPLETE**

- `keyhole context compile` - compile governed context, emit proof, track recent digest
- `keyhole context inspect` - inspect context for a digest, render human-readable summary
- `keyhole run --context <digest>` - explicit context binding with digest validation
- `keyhole run --context auto` - auto-compile before dispatch, digest visible in result
- no-floating-run enforcement: `keyhole run` without `--context` is rejected locally
- `keyhole_sdk/context_lifecycle/` package: compile, inspect, preflight, proof, repair, tracker, digest validation
- operation registry: `context.inspect` registered as READ_ONLY (context.compile already was)
- 13 new SDK exports (104 total __all__ entries)
- repair guidance for 15+ error classes with concrete next-best actions
- local context tracker under `.keyhole/state/recent-context.json`
- proof continuity: compile-request.json, compile-response.json, summary.md, inspect-output.json, context-binding.json

**Server (sdk-server-16.md)**

- context compile / get surfaces
- governed run admission requiring `ctxpack_digest`
- deterministic context validation

**Proof / Tests**

- 86/86 tests in `test_sdk_client_16_context_lifecycle.py`
- governed run without context rejected (section11)
- malformed digest rejected locally before dispatch (section6)
- valid context visible and inspectable (section9)
- context -> run linkage durable via context-binding proof (section15)
- repair guidance for missing / invalid / stale / incompatible context (section14)
- --context auto compiles, shows digest, binds with proof continuity (section5.4)
- SDK-CLIENT-09 tests updated to comply with no-floating-run rule
- full regression: 1437 passed, 26 pre-existing failures, zero new failures

---

### SDK-CLIENT-17 - Async Run Tracking, Polling, and Durable Run UX OK COMPLETE

**Client ([sdk-client-17.md](sdk-client-17.md))** - **COMPLETE**

- accepted async execution handling (`accepted + run_id`)
- `keyhole runs status <run-id>` - inspect current run state
- `keyhole runs wait <run-id>` - poll until terminal state
- `keyhole runs tail <run-id>` - follow observations (status_poll, honestly labeled)
- `keyhole runs resume <request-id|run-id>` - reconnect to existing run identity
- `keyhole runs list` - list recent local run records
- local run record persistence under `.keyhole/state/runs/`
- lifecycle proof continuity: accepted -> status -> outcome under `proof_bundle/core/runs/`
- classified run states: RunStatus, TerminalState, classify_status()
- repair guidance for 15+ error classes (section17)
- operation registry: `run.status` and `events.query` as READ_ONLY
- `keyhole run` ACCEPTED/DEFERRED next_steps point to `keyhole runs` commands
- 82 unit tests, full regression: 1519 passed, 26 pre-existing failures, zero new

**Server (sdk-server-17.md)**

- two-plane run dispatch
- run status endpoint
- optional stream / SSE compatibility

**Proof / Tests**

- long-running run returns accepted + run_id
- client tracks and resolves terminal state safely
- no transport ambiguity under accepted async execution
- proof bundles link request -> run -> events -> outcome

---

### SDK-CLIENT-18 - Memory Boundary Enforcement OK COMPLETE

**Implementation Status:** OK COMPLETE - 77/77 unit tests passing (`tests/unit/test_sdk_client_18_memory_boundary.py`). Memory boundary modules: `keyhole_sdk/memory_boundary/{__init__,enforcer,proof}.py`. `DirectMemoryAccessNotAllowed` exception added to `keyhole_sdk/exceptions.py`. CLI `memory_app` registered in `keyhole_cli/cli.py` with rejection callback (no query/write/get/delete sub-commands). Deterministic rejection with repair guidance. Proof bundle: `<state_dir>/memory_boundary/{attempted-surface.json,rejection.json,summary.md}`. Zero regressions (1885 passed / 26 pre-existing / 92 skipped).

**Client (sdk-client-18.md)**

- no direct canonical memory query/write surface exposed publicly
- context- or run-mediated helper APIs only
- clear developer messaging about governed memory access

**Server (sdk-server-18.md)**

- context-gated memory access
- elimination of unsafe direct memory surfaces
- explicit rejection of illegal client memory paths

**Proof / Tests**

- client cannot query canonical memory without lawful context/run path
- illegal direct memory attempts fail deterministically
- no direct SDK canonical memory bypass remains

---

### SDK-CLIENT-19 - Budget, Limit, and Overload Visibility

**Client (sdk-client-19.md)**

- surface run budget usage, limit posture, and overload outcomes
- deterministic UX for `budget_exhausted`, `deferred`, `rate_limited`, and similar outcomes

**Server (sdk-server-19.md)**

- budget/limit inspection surface
- overload-aware accepted/denied semantics
- stable machine-readable limit outcomes

**Proof / Tests**

- client can inspect or display budget posture
- overload does not appear as arbitrary failure
- budget/limit outcomes include repair guidance

---

### SDK-CLIENT-20 - Governance Explainability and Support Bundles

**Client (sdk-client-20.md)**

- `keyhole explain run <id>`
- `keyhole inspect <request-id>`
- `keyhole support-bundle <run-id|request-id>`
- human-readable explanation of context, events, proof, and rejection reason

**Server (sdk-server-20.md)**

- explainability / lineage lookup surfaces
- support bundle generation or retrieval
- stable reason / lineage contract

**Proof / Tests**

- users can recover why a run was accepted, rejected, replayed, or deferred
- support bundle contains request/run/context/event/proof linkage
- explainability is deterministic and replayable

---

### SDK-CLIENT-21 - Surface Negotiation & Compatibility Guardrails OK COMPLETE

**Implementation Status:** OK COMPLETE - 115/115 unit tests passing (`tests/unit/test_sdk_client_21_surface_negotiation.py`). Negotiation modules: `keyhole_sdk/negotiation/{models,classifier,evaluator,negotiator,artifact,repair,__init__}.py`. CLI command: `keyhole surfaces` via `keyhole_cli/commands/surfaces_cmd.py`. `SurfaceNegotiator` queries `GET /mcp/v1/capabilities`, classifies operations into `SurfaceClass` (REQUIRED / OPTIONAL / UNKNOWN), evaluates posture via `NegotiationEvaluator` (pass/warn/fail), emits `NegotiationArtifact` proof, and produces `RepairGuidance` with concrete next steps. `DispatchPreflight` composes validator + schema into a pre-dispatch gate. 17 new public SDK exports.

**Client ([sdk-client-21.md](sdk-client-21.md))**

- feature / capability negotiation at startup or first authenticated call
- version / surface compatibility checks against live server posture
- fail-closed behavior for unsupported required features (e.g. missing idempotency enforcement)
- graceful degraded UX for optional features (e.g. missing explainability surface)
- clear builder-facing messaging when a required surface is unavailable

**Server (sdk-server-21.md)**

- capability / surface declaration via `GET /mcp/v1/capabilities` or equivalent
- versioned feature flags or operation disclosure
- explicit async / context / idempotency / explainability support disclosure

**Proof / Tests**

- client detects missing required surface and fails closed with repair guidance
- client detects missing optional surface and degrades gracefully
- client does not assume accepted async, context enforcement, or explainability exist everywhere
- surface negotiation result is visible and inspectable

---

### SDK-CLIENT-22 - Account Deregistration and Deletion UX OK COMPLETE

**Implementation Status:** OK COMPLETE - 73/73 unit tests passing (`tests/unit/test_sdk_client_22_deregister.py`). Deregistration modules: `keyhole_sdk/deregister/{models,errors,client,proof,__init__}.py`. CLI command: `keyhole deregister` via `keyhole_cli/commands/deregister.py`. `DeregisterClient` dispatches `auth.remove` through `POST /mcp/v1/runs/start` with full idempotent transport (`X-Request-Id` / `X-Idempotency-Key`). `DeregistrationStatus` enum covers ACCEPTED / DEFERRED / REPLAYED / REJECTED. Interactive confirmation prompt required unless `--yes` supplied. Auth preflight validates session before dispatch. Local proof artifacts written to `<tool-owned-state>/deregister/<request-id>/` (identity-scoped, not repo-scoped): `request.json`, `response.json`, `identity_snapshot.json`, `summary.md`, `repair.json`, `correlation.json`. Concrete repair guidance for all failure classes: not-authenticated, ownership-mismatch, surface-unavailable, already-deleted, policy-blocked. Operates repo-neutrally - no `keyhole.yaml` required. `OperationRegistry` updated with `auth.remove` operation. 7 new public SDK exports.

**Client ([sdk-client-22.md](sdk-client-22.md))**

- `keyhole deregister --registration-id <id>` - governed account deletion dispatch
- `--yes` to bypass interactive confirmation in non-interactive mode
- `--json` for machine-readable output
- authentication and session preflight before dispatch
- interactive destructive confirmation prompt ("Type DELETE to continue")
- dispatches `auth.remove` through `POST /mcp/v1/runs/start` (governed mutation, not raw REST)
- idempotent transport with `X-Request-Id` + `X-Idempotency-Key`
- ACCEPTED / DEFERRED / REPLAYED / REJECTED outcome rendering
- next-step guidance pointing to `keyhole runs status`, `keyhole runs wait`, `keyhole explain run`
- identity-scoped local proof artifacts (not repo-scoped - repo-neutral by design)
- repair guidance for all failure classes
- surface negotiation integration: fails closed if deletion surface unavailable

**Server (sdk-server-22.md)**

- `auth.remove` governed run type via `POST /mcp/v1/runs/start`
- proof-of-ownership enforcement
- auth revocation on deletion completion
- deletion lifecycle events

**Proof / Tests**

- `keyhole deregister --registration-id <id>` parses and dispatches correctly
- `--yes` bypasses confirmation; omission requires explicit prompt
- unauthenticated deletion attempt blocked locally with repair guidance
- idempotency headers present on every deletion request
- replay-safe retry preserves same logical attempt identity
- ACCEPTED / DEFERRED / REPLAYED / REJECTED outcomes rendered honestly
- next-step commands point to run status / wait / explain
- client does not claim deletion completed when boundary only accepted it
- local proof artifacts created deterministically outside any repo
- surface negotiation failure blocks command cleanly
- already-deleted / ownership-mismatch / policy-blocked produce concrete repair guidance

---

## 23. Epic Closure Criteria

SDK-CLIENT is CLOSED only when:

- every story pair passes independently,
- every story pair produces verifiable events,
- every story pair produces a replayable proof bundle,
- the full loop works:

```text
auth register -> verify -> login -> init -> validate -> repo register -> context -> run -> ingest -> analyze
```

- all artifacts are:
  - attributable,
  - replayable,
  - queryable from the Event Spine,
  - identifiable by deterministic digest.

And, for scale-safe closure:

- write-bearing commands are idempotent,
- governed runs are context-bound,
- long-running runs are handled safely,
- no direct canonical memory bypass remains,
- budget / overload outcomes are visible and lawful,
- explainability and support surfaces exist for production use.

---

## 24. Proof Doctrine for This Epic

Each zipper must emit:

- correlation_id,
- tenant/org/user/cohort/worker/repo/workspace binding,
- ACCEPT/REJECT/DEFER artifact,
- persisted event chain,
- proof bundle core,
- human-readable proof summary,
- failure repair guidance where relevant,
- context identity where required,
- request identity and operation identity where write-bearing.

The epic is not complete without:

- replay validation,
- lineage validation,
- capability reuse validation,
- identity attribution validation,
- context binding validation,
- event class / retention validation,
- hot/cold proof storage validation,
- shadow-mode validation,
- async accepted-execution validation,
- explainability/support-bundle validation.

---

## 25. Final Summary

SDK-CLIENT is the master guidance for the governed builder boundary.

It defines a developer experience that must feel simple while remaining structurally correct and scale-safe.

It exists to ensure that every external builder-facing feature:

- begins at the developer,
- passes through the MCP boundary,
- resolves inside the governed platform,
- emits attributable events,
- produces replayable proof,
- returns deterministic outcomes,
- remains safe to adopt incrementally,
- remains safe under retry, long-running execution, and SDK fan-out.

No half-features.  
No one-sided implementations.  
No floating execution.  
No replayless closure.  
No contextless governed runs.  
No direct canonical memory bypass.  

Only zipper-closed capabilities that preserve identity, proof, governance, adoption quality, and scaling correctness at the same time.
