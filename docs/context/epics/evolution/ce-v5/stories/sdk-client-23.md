## SDK-CLIENT-23 - Host Identity Attestation & Local Identity Coherence Guard (VS Code First)

**Status:** PLANNED
**Type:** New capability
**Priority:** High
**Scope:** Client-side, SDK/CLI-first, VS Code-first host attestation foundation

---

## Goal

Prevent hidden split-identity on a workstation by introducing a deterministic, host-proven identity attestation flow that the CLI can consume before binding or refreshing local credentials.

In plain terms:

* the CLI cannot directly inspect gallery-installed Keyhole hosts
* the host environment that can see the bound Keyhole connection must attest who it is actually acting as
* the CLI uses that attestation to decide whether a local login/bind is safe, conflicting, stale, or explicitly overridden

This story realizes the design we just settled on:

* **host-side proof**
* **shared contract**
* **CLI-side policy**
* **no mutation of IDE gallery entries**
* **no secret scraping**
* **no pretending the CLI owns host auth**

---

## Problem

Today, a machine can simultaneously hold:

* a **CLI/SDK identity** in `~/.keyhole/credentials.json`
* a **VS Code gallery-installed Keyhole host connection** authenticated independently through IDE-managed OAuth

Those can silently diverge.

Example:

* CLI is logged in as `paul@keyholesolution.com`
* VS Code MCP tools are still acting as `nathan@keyholesolution.com`

The system appears "healthy," but the effective principal differs by channel.

That creates a dangerous operator illusion:
the builder thinks they switched identity, but only one surface actually changed.

We do **not** want to solve this by mutating IDE installs.
We solve it by making the CLI **conflict-aware** and requiring a host-proven identity attestation when the host can see something the CLI cannot.

---

## Constitutional / Architectural Alignment

This story must honor the following doctrine:

* **Builders Out, Declarations In**
  No open-ended reasoning inside the control path. The host inspector follows a deterministic attestation protocol.

* **Token opacity**
  Clients do not decode or interpret auth state beyond supported identity surfaces. The proof source is the real host-bound `whoami` path.

* **Single Mint / Dual Lens discipline**
  Identity provenance must be explicit per surface. No silent cross-surface assumption.

* **Publish the laws, not the locks**
  We expose outcome and provenance, not IDE secret internals.

* **Client ergonomics, server truth**
  The CLI governs local bind behavior. The server remains the ultimate truth for effective principal through `whoami`.

---

## Story Summary

Introduce a three-part client capability:

### 1. Shared host identity attestation contract

A small schema in the SDK repo defines how a host inspector reports:

* which host it is
* which Keyhole integration it observed
* which principal is actually active
* how it proved that
* how fresh and trustworthy the result is

### 2. VS Code-first host inspector

A deterministic host-side helper runs inside the environment that can access the gallery-installed Keyhole host and performs a live `whoami` through the real bound Keyhole connection. It writes a local attestation file into the canonical Keyhole state directory.

### 3. CLI local identity coherence guard

`keyhole login` and `keyhole doctor` consume host attestations and classify the environment as:

* match
* conflict
* stale
* unknown
* intentional split

By default, the CLI refuses to silently create a fresh conflicting bind when a host has already proven a different live identity.

---

## Delivers

### A. SDK contract: Host identity attestation schema

Add a versioned attestation contract to the SDK repo.

Required fields:

* `schema_version`
* `host_kind`
  Example: `vscode`
* `host_display_name`
  Example: `VS Code`
* `integration_name`
  Example: `keyhole`
* `server_url`
* `realm`
* `effective_principal`
* `effective_subject`
  opaque server-returned subject if available
* `proof_method`
  Example: `live_whoami`
* `confidence`
  `confirmed | probable | unknown`
* `observed_at`
* `expires_at`
* `machine_scope`
* `workspace_scope`
  nullable
* `correlation_id`
  from the `whoami` or equivalent proof call if available
* `notes`
* `tool_version`

Nice-to-have but not required in first cut:

* `client_id`
* `issuer`
* `purpose`
* `origin`

---

### B. Canonical local storage for host attestations

Define a local directory under the Keyhole state root:

* Linux/macOS: `~/.keyhole/host_attestations/`
* Windows: platform-equivalent Keyhole state root

Each host writes one attestation file per logical host binding.

Suggested filename pattern:

```text
<host_kind>__<integration_name>__<machine_scope>.json
```

Example:

```text
vscode__keyhole__b7f4d2....json
```

Rules:

* attestation files are local workstation facts
* they are not server truth
* they are advisory for local bind policy
* freshness is TTL-based

---

### C. VS Code-first host inspector

Implement a deterministic helper for VS Code/Copilot environments that:

1. confirms a Keyhole host integration is present
2. performs a live `whoami` through that actual VS Code-bound Keyhole connection
3. builds a host attestation object
4. writes it to the canonical attestation directory
5. surfaces success/failure to the user

This is **not** an open-ended "agent skill."
It is a fixed host adapter with a narrow job.

The proof source must be the actual bound Keyhole connection, not cached UI labels or guessed account names.

---

### D. CLI coherence classification engine

Add a local policy engine to the CLI that reads:

* current CLI credentials
* discovered host attestations
* any recorded split-identity override

and produces a deterministic verdict.

Verdict states:

* `ACCEPT_MATCH`
* `WARNING_NO_HOST_ATTESTATION`
* `WARNING_STALE_HOST_ATTESTATION`
* `WARNING_UNKNOWN_HOST_IDENTITY`
* `REJECT_HOST_CONFLICT`
* `ACCEPT_INTENTIONAL_SPLIT`

---

### E. `keyhole doctor` host coherence report

Extend `keyhole doctor` to show a dedicated host identity section.

For each attested host, report:

* host
* integration
* effective host principal
* realm
* proof method
* freshness
* confidence
* CLI principal
* coherence verdict

Example shape:

```text
Host Identity Coherence
- VS Code / keyhole
  effective host principal: nathan@keyholesolution.com
  realm: kh-prod
  proof: live_whoami
  freshness: fresh
  confidence: confirmed

CLI Identity
- principal: paul@keyholesolution.com
  realm: kh-prod
  token: valid

Verdict
- REJECT_HOST_CONFLICT
  impact: IDE tool calls will act as nathan@keyholesolution.com while CLI/SDK calls would bind as paul@keyholesolution.com
  fix: re-authenticate VS Code as paul or use --allow-split-identity
```

Doctor must clearly distinguish:

* detected host app
* attested host identity
* CLI identity
* final coherence verdict

---

### F. `keyhole login` preflight guard

Before writing new CLI credentials or refreshing existing credentials, `keyhole login` must perform a host coherence preflight.

Default behavior:

* if a **fresh confirmed** host attestation exists with a conflicting principal, login does **not** silently bind the CLI to a different identity
* the command exits with a conflict verdict and exact remediation steps

Allowed behaviors:

* explicit override flag to allow intentional split
* optional host-ignore targeting if later needed

Minimum first-cut override:

```bash
keyhole login ... --allow-split-identity
```

On override:

* login succeeds
* the split is recorded locally
* doctor remains noisy and explicit

---

### G. Local split-identity override record

Add a small local override record under Keyhole state, for example:

```text
~/.keyhole/identity_policy.json
```

This records:

* override type
* created_at
* target principal
* conflicting host principal
* host kind
* optional reason
* optional expiry

This prevents the system from pretending the conflict vanished.

---

### H. Precise remediation guidance

When a conflict is detected, the CLI must print exact steps.

For VS Code first cut, guidance should look like:

1. Open VS Code where the Keyhole host is installed.
2. Run the Keyhole host identity attestation helper.
3. Confirm the host is acting as the intended user.
4. If the host is bound to the wrong user, sign out of the Keyhole host connection in VS Code.
5. Re-authenticate VS Code as the intended user.
6. Re-run `keyhole doctor`.
7. Retry `keyhole login`.

Do not print vague advice like "check your auth."
The steps must be host-specific and actionable.

---

## Scope

### In scope

* shared host attestation schema
* local attestation file format and storage
* VS Code-first host inspector
* CLI coherence engine
* doctor output
* login preflight refusal/warning logic
* intentional split override
* deterministic tests

### Out of scope

* automatic mutation of VS Code gallery entries
* reading IDE secret stores
* scraping OAuth caches
* JetBrains/Cursor/WinSCP implementations
* server-side cryptographic signing of host attestations
* forced cross-surface token sync
* new server endpoint if existing `whoami` is sufficient

---

## Proposed UX / Command Behavior

### 1. VS Code host inspector writes attestation

Host-side action produces a fresh file under:

```text
~/.keyhole/host_attestations/
```

### 2. Doctor shows coherence

```bash
keyhole doctor
```

Outputs:

* CLI identity
* host identities
* freshness/confidence
* verdict
* fix steps if needed

### 3. Login guard blocks conflicting bind

```bash
keyhole login --email paul@keyholesolution.com --flow email
```

If VS Code has fresh confirmed Nathan attestation:

* do not persist Paul credentials
* print conflict verdict
* exit non-zero

### 4. Explicit split mode

```bash
keyhole login --email paul@keyholesolution.com --flow email --allow-split-identity
```

Result:

* CLI binds Paul
* split recorded locally
* doctor shows `ACCEPT_INTENTIONAL_SPLIT`

---

## Attestation Contract Example

```json
{
  "schema_version": "1",
  "host_kind": "vscode",
  "host_display_name": "VS Code",
  "integration_name": "keyhole",
  "server_url": "https://mcp.keyholesolution.com/sse",
  "realm": "kh-prod",
  "effective_principal": "nathan@keyholesolution.com",
  "effective_subject": "0f9d2d0e-....",
  "proof_method": "live_whoami",
  "confidence": "confirmed",
  "observed_at": "2026-04-20T12:14:33Z",
  "expires_at": "2026-04-20T12:24:33Z",
  "machine_scope": "sha256:....",
  "workspace_scope": null,
  "correlation_id": "8b7b7f0c-....",
  "notes": "Attested via VS Code-bound Keyhole host connection",
  "tool_version": "keyhole-host-attest/0.1.0"
}
```

---

## Freshness / Trust Rules

### Freshness

First cut TTL:

* **10 minutes** for `confirmed` host attestations

Classification:

* `fresh` if `now <= expires_at`
* `stale` otherwise

### Trust model

* `confirmed`: proven by live `whoami` through actual host-bound connection
* `probable`: host exists but proof path degraded; never hard-block login
* `unknown`: host detected but no principal proven; never hard-block login

### Hard conflict rule

Only a **fresh confirmed** conflicting host attestation can trigger `REJECT_HOST_CONFLICT`.

Everything else warns, but does not hard-block.

---

## CLI Decision Logic

### If no host attestation exists

* login proceeds
* doctor warns if a host app is detectable but unattested

### If host attestation is stale

* login proceeds with warning
* doctor explains attestation must be refreshed for strong coherence checks

### If host attestation is fresh and confirmed and principal matches

* login proceeds
* doctor reports `ACCEPT_MATCH`

### If host attestation is fresh and confirmed and principal conflicts

* login fails by default
* doctor/login report `REJECT_HOST_CONFLICT`

### If override is supplied

* login proceeds
* split record is created
* doctor reports `ACCEPT_INTENTIONAL_SPLIT`

---

## Acceptance Criteria

### AC1 - SDK schema exists and validates

A versioned host identity attestation schema exists in the SDK repo and validates required fields, allowed enums, timestamps, and freshness-relevant structure.

### AC2 - VS Code-first attestation uses real host proof

The VS Code helper proves effective identity through a live `whoami` on the actual VS Code-bound Keyhole connection and writes a valid attestation file.

### AC3 - Doctor surfaces host and CLI identities separately

`keyhole doctor` clearly distinguishes:

* host-attested identity
* CLI identity
* final coherence verdict

No ambiguous "healthy" state is allowed when identities conflict.

### AC4 - Fresh confirmed conflict blocks CLI bind by default

If a fresh confirmed VS Code host attestation says `nathan@...` and the user attempts CLI bind as `paul@...`, `keyhole login` refuses the bind by default and prints exact remediation steps.

### AC5 - Match proceeds cleanly

If the fresh confirmed host attestation principal matches the requested CLI principal, login succeeds and doctor reports `ACCEPT_MATCH`.

### AC6 - Stale or unknown host identity does not hard-block

Stale, probable, or unknown host identity states warn, but do not hard-block login.

### AC7 - Explicit split override is possible and durable

`--allow-split-identity` permits the bind, records a local override, and causes doctor to report `ACCEPT_INTENTIONAL_SPLIT` until the split is resolved or override expires/is cleared.

### AC8 - No IDE mutation occurs

The implementation does not attempt to add, edit, or delete gallery-installed Keyhole entries, does not scrape secret stores, and does not claim to control IDE auth state.

### AC9 - Tests prove coherence engine behavior

Unit and integration tests cover:

* no-host
* fresh match
* fresh conflict
* stale attestation
* unknown/probable identity
* override path
* doctor rendering

### AC10 - VS Code-first design is extensible

The attestation contract and CLI policy are host-agnostic so future adapters can be added for Cursor, JetBrains, and other clients without redesigning the policy engine.

---

## Suggested Implementation Shape

### SDK repo

Add shared contract/types and local-state helpers.

Suggested areas:

* host attestation model
* schema validator
* local state path helpers
* coherence classification engine

### CLI

Extend:

* `doctor`
* `login`
* local policy/override handling

### VS Code-side helper

Add a deterministic helper/command that:

* performs `whoami`
* writes attestation
* reports success/failure

If the current `whoami` payload is missing stable identity fields, extend existing `whoami` output in-place rather than creating a new surface.

---

## Tests

### Unit tests

* schema validation
* freshness calculation
* conflict classification
* override precedence
* local state loading failures
* malformed attestation handling

### CLI integration tests

* login preflight with no host attestation
* login preflight with fresh matching attestation
* login preflight with fresh conflicting attestation
* login with explicit override
* doctor output rendering for each verdict

### VS Code helper tests

* valid attestation emitted on successful `whoami`
* failure path when host connection is unavailable
* failure path when `whoami` response is incomplete
* overwrite/update semantics for existing attestation file

### End-to-end smoke

1. Attest host as Nathan in VS Code
2. Attempt CLI login as Paul
3. Verify bind is rejected
4. Re-auth host as Paul or use override
5. Verify doctor reflects new state

---

## Failure Semantics

This story must fail loudly and specifically.

### Login conflict failure

* non-zero exit
* conflict verdict name printed
* host principal printed
* requested CLI principal printed
* remediation steps printed

### Malformed attestation

* ignore malformed file for hard-block purposes
* doctor reports malformed attestation warning
* login proceeds with warning unless another valid conflicting attestation exists

### Host inspector failure

* no attestation written
* clear host-side error shown
* doctor/login treat host as unattested or unknown, not confirmed

---

## Security / Trust Notes

* Host attestations are **local environment evidence**, not authoritative server truth
* Hard-blocking is only permitted on **fresh confirmed** host proof from supported path
* No credential scraping
* No secret-store introspection
* No invisible host auth mutation
* No assumption that IDE and CLI share tokens or sessions

---

## Dependencies

Depends on:

* existing CLI login flow
* existing `doctor`
* existing `whoami` capability through the Keyhole-bound surface

May require a tiny compatibility patch if current `whoami` output lacks enough stable identity fields.

---

## Unlocks

This story unlocks:

* Cursor host attestation story
* JetBrains host attestation story
* richer local identity governance
* machine-wide coherence diagnostics
* future brokered identity handoff without redesigning local policy
* clearer evidence for multi-surface auth bugs

---

## Non-Goals / Explicit Restraints

Do **not**:

* build a general "agent skill that figures it out"
* let the agent improvise host discovery or policy decisions
* make the SDK repo responsible for IDE mutation
* add a brand-new broad server surface for this
* over-engineer cryptographic signing in the first cut

This story is about deterministic host proof and deterministic CLI policy.

---

## Definition of Done

This story is done when:

* a VS Code-bound Keyhole connection can produce a fresh host identity attestation
* the CLI can consume that attestation deterministically
* `keyhole doctor` can expose real coherence state
* `keyhole login` refuses silent conflicting binds by default
* explicit split mode exists and remains visible
* no IDE gallery mutation is attempted
* tests cover the full classification matrix

---

## Recommended Story Title for the repo

**SDK-CLIENT-23 - Host Identity Attestation & Local Identity Coherence Guard (VS Code First)**
