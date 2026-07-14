# sdk-client-03.md

# SDK-CLIENT-03 - Capability Namespace Enforcement

**Story ID:** SDK-CLIENT-03 / sdk-client-03  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Local Validation and Creation Helper  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-03.md`  
**Depends On:** `sdk-client-02.md`, `sdk-client-10.md`, SDK-CLIENT master guidance  
**Precedes:** local schema validation, dependency resolution, alignment guidance, and registration workflows that depend on stable capability identifiers  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-03 defines the client-side contract for **capability namespace enforcement**.

Its purpose is to ensure that every capability identifier the client creates, validates, filters, suggests, or submits is shaped according to the canonical Keyhole namespace contract **before** it reaches registration-time or resolver-time server validation.

This story must support both:

- **greenfield Keyhole-native repos**, where the builder may create a new capability and insert it into governed local artifacts,
- **foreign or ingested repos**, where the client may only need to validate or filter inferred capability names without mutating the target repo.

This story exists to make capability names:

- predictable,
- portable,
- globally legible,
- version-aware,
- validation-friendly,
- and consistent across greenfield and foreign-repo paths.

The client must make the correct path easy, the incorrect path hard, and silent naming entropy unacceptable.

---

## 2. Why This Story Exists

Without this story:

- builders invent inconsistent names,
- the same capability appears under multiple spellings,
- major-version semantics drift,
- dependency resolution becomes noisy,
- ingestion inference produces low-trust suggestions,
- and the server becomes the first place builders learn that their names were malformed.

That is the wrong developer experience.

This story exists so the client can:

- generate correct capability names,
- reject malformed names early,
- normalize only the safest obvious mistakes during guided input,
- and reuse one stable validation model across:
  - creation,
  - local validation,
  - ingestion filtering,
  - capability discovery inputs,
  - dependency resolution,
  - alignment guidance,
  - and eventual registration.

This is a local discipline story with ecosystem consequences.

---

## 3. Core Thesis

Capability identifiers are not labels.

They are **governed identifiers**.

A capability name must be stable enough to support:

- declaration,
- dependency resolution,
- provider pinning,
- compatibility review,
- proof and passport binding,
- ingestion inference,
- registration-time validation,
- and long-term ecosystem reuse.

Therefore the client must never treat capability names as arbitrary strings.

---

## 4. Strategic Role

SDK-CLIENT-03 is one of the earliest client-governance stories because stable naming is foundational whether the repo is:

- greenfield and scaffolded, or
- foreign and only beginning alignment.

Its role differs slightly by path.

### 4.1 Greenfield path

The builder may create a capability intentionally and insert it into governed local artifacts.

### 4.2 Foreign repo path

The client may validate or reject inferred capability names, but must not assume the repo is ready for in-repo governed declarations.

That means namespace enforcement must be reusable without requiring immediate artifact mutation.

### Position in the broader client flow

```text id="8ghhja"
greenfield:
login
  ↓
init vertical
  ↓
create / validate capability namespace   ? this story
  ↓
validate contracts
  ↓
later registration / resolution / runs

foreign:
login
  ↓
ingest / observe repo
  ↓
infer candidate capabilities
  ↓
validate capability namespace   ? this story
  ↓
alignment / registration / resolution
5. Canonical Naming Contract

The canonical capability name format is:

<domain>.<category>.<capability>.v<major>

Examples of valid names:

payment.stripe.integration.v1
crm.salesforce.sync.v1
workorder.assignment.engine.v1
identity.oidc.discovery.v2

Examples of invalid names:

StripeIntegration
payment/stripe/integration
payment.stripe.integration
payment.stripe.integration.v01
payment..integration.v1
payment.stripe.integration.V1

This format is canonical and non-optional.

6. Client Deliverables

This story delivers two primary client capabilities.

6.1 Capability creation helper

A CLI and SDK helper that assists the builder in generating a valid capability name from structured input.

Example CLI shape:

keyhole capability create

Example non-interactive form:

keyhole capability create --domain payment --category stripe --name integration --major 1

The helper must:

validate parts,
normalize only safe obvious input issues before confirmation,
assemble the canonical name,
optionally write to a lawful target,
refuse malformed identifiers.
6.2 Namespace validator

A reusable validator that can be invoked by:

capability creation flows,
keyhole validate,
ingestion inference filtering,
alignment guidance rendering,
dependency resolution prechecks,
registration prechecks,
passport/contract generation helpers where applicable.

The validator must:

accept canonical names,
reject malformed names,
explain what failed,
suggest corrected shapes where safe,
enforce major-version semantics.
7. Supported Command Surfaces
7.1 Capability creation

At minimum, the client should support one of:

keyhole capability create

or

keyhole capability add

The exact verb can be finalized during implementation, but behavior must include:

canonical name generation,
local validation,
explicit write/advisory mode behavior,
deterministic failure on invalid input.
7.2 Namespace validation

A direct validation surface is recommended, such as:

keyhole capability validate <name>

or equivalent validation support through existing commands.

This helps foreign-repo and ingestion flows use the validator without pretending the repo is already native.

7.3 SDK surface

At minimum, the SDK should expose helper functions conceptually equivalent to:

create_capability_name(domain: str, category: str, capability: str, major: int) -> str
validate_capability_name(name: str) -> ValidationResult

The validation result should support:

CLI-friendly messages,
deterministic test assertions,
ingestion filtering,
alignment guidance,
and future editor/LSP integration.
8. Validation Rules

The validator must enforce these minimum rules.

8.1 Segment count

A capability identifier must contain exactly four dot-separated segments:

domain
category
capability
version segment
8.2 Character rules

The first three segments must:

be lowercase,
contain no whitespace,
contain no empty segments,
use only allowed characters.

Default-safe policy:

lowercase letters a-z
digits 0-9
optional internal hyphen -
8.3 Version segment rules

The final segment must match:

v<major>

Where:

v is lowercase,
<major> is a positive integer,
no leading-zero form is allowed by default.

Valid examples:

v1
v2
v10

Invalid examples:

V1
1
version1
v01
8.4 Safe normalization boundaries

The client may safely normalize only where builder intent is obvious during guided input, such as:

trimming leading/trailing whitespace,
lowercasing interactive parts before final confirmation,
replacing obvious internal spaces before confirmation.

The client must not silently rewrite already-declared malformed names in repo artifacts without explicit builder action.

8.5 Deterministic reject reasons

Every invalid name must produce a stable reject reason such as:

invalid_segment_count
invalid_version_suffix
uppercase_not_allowed
empty_namespace_segment
illegal_character
9. Native Repo vs Foreign Repo Behavior

This story must explicitly support both repo realities.

9.1 Native repo behavior

If the repo is already Keyhole-native and the builder explicitly chooses write behavior, the helper may insert the capability into lawful governed local artifacts.

9.2 Foreign repo behavior

If the repo is foreign or ingestion-backed, namespace enforcement should default to:

advisory validation,
inference filtering,
out-of-tree suggestion artifacts,
no in-repo declaration mutation by default.

The client must not assume that every validated capability name should immediately appear inside the target repo.

9.3 Important rule

Validation is universal.

In-repo declaration mutation is conditional.

10. Artifact Integration Rules

When the helper is used in an explicit write mode against a Keyhole-native repo, lawful insertion points may include:

capability_passport.yaml
governance_contract.yaml
a future governed declaration file under capabilities/

The client must update artifacts deterministically.

Required behavior
insert in the correct location,
preserve stable ordering where required,
avoid duplicate insertion,
show what changed,
fail safely if the target artifact is missing or malformed.
Duplicate handling

If the capability already exists:

do not insert a duplicate,
surface a deterministic warning or reject outcome,
allow override only if an explicit later behavior is defined.
11. Foreign-Repo Artifact Behavior

For foreign repos, the client must not write Keyhole-native declarations into the repo by default.

Instead, it may emit out-of-tree advisory artifacts such as:

validated candidate capability lists,
rejected candidate capability reports,
suggested normalized names,
alignment-ready summaries.

A reasonable tool-owned path is:

<tool-owned-state>/
  capability_namespace/
    <request-id-or-session-ref>/
      validation.json
      accepted.json
      rejected.json
      summary.md

This preserves replayability without silently "Keyholifying" the repo.

12. UX Requirements
12.1 Guided creation must feel easy

The point of this story is to make correct names easy and incorrect names hard.

A builder should not need to memorize the grammar on day one.

12.2 Validation messages must teach

Bad:

invalid capability

Good:

Invalid capability namespace.
Expected: <domain>.<category>.<capability>.v<major>
Example: payment.stripe.integration.v1
12.3 Repair suggestions must be actionable

Where safe, the client should suggest a corrected form:

Did you mean: payment.stripe.integration.v1 ?
12.4 Foreign-repo caution

For foreign repos, successful validation must not imply:

registration,
acceptance,
capability publication,
or in-repo declaration.

It only means the proposed identifier is namespace-valid.

13. Determinism Requirements

The client-side behavior must be deterministic where it has authority.

Required stable behaviors
same input parts -> same canonical name
same invalid input -> same reject reason
same artifact state -> same insertion behavior
same foreign-repo candidate set -> same accepted/rejected validation results
same validation result -> same proof/artifact structure
Forbidden behavior
silent in-place rewriting of malformed repo declarations
random suggestion ordering
inconsistent validation messaging for the same invalid input
14. Relationship to Neighboring Stories

This story supports later work but does not depend on all of it to be useful.

It should integrate cleanly with:

greenfield scaffolded repos from sdk-client-02
ingestion filtering from sdk-client-10
alignment guidance from sdk-client-11
capability discovery/resolution from sdk-client-08
registration prechecks from sdk-client-07

Its role is foundational naming law, not remote ecosystem interaction.

15. Zipper Expectations with sdk-server-03.md

The client is responsible for:

capability generation UX,
local namespace validation,
deterministic messages,
lawful artifact update behavior when allowed,
preventing obviously malformed names from reaching MCP.

The server is responsible for:

final boundary validation,
rejecting malformed or conflicting names at the boundary,
keeping server and client validation semantics aligned.

This zipper closes only when:

invalid names are rejected consistently client and server side,
valid names are accepted consistently client and server side,
version suffix rules do not drift.
16. Proof Contract

This story must produce deterministic evidence for namespace behavior.

Native repo write-mode proof

If the helper writes into a Keyhole-native repo, it should preserve:

validated capability identifier
artifact diff or insertion summary
duplicate suppression behavior
command invocation
timestamp and local repo identity
Foreign/advisory proof

For foreign repos or no-write mode, artifacts should preserve:

candidate capability names examined
accepted vs rejected names
deterministic reasons
suggested normalized forms where applicable
no-write/no-mutation statement
Minimum artifact semantics

The client should emit or materialize evidence for:

namespace validation pass/fail,
artifact mutation preview or diff when applicable,
created or validated capability identifier,
duplicate suppression behavior,
local proof summary for the test run or command invocation.
17. Local Test Strategy
17.1 Unit tests

Must verify:

valid canonical names are accepted
malformed names are rejected
version suffix is required
uppercase forms are rejected or normalized only in explicitly allowed guided-input paths
duplicate insertion is blocked
artifact update is deterministic
interactive helper output matches expected normalized form
17.2 Fixture tests

Must verify:

scaffolded repos accept lawful capability insertion
malformed declaration files fail safely
foreign repo candidate validation remains advisory
validation output remains stable across reruns
17.3 Negative tests

Must verify:

malformed names do not silently reach artifact insertion
malformed existing artifact state does not cause silent repair
foreign repos are not mutated by default
invalid candidate names in ingestion/alignment flows are filtered deterministically
17.4 Zipper tests

Must verify:

invalid names rejected client + server
valid names accepted consistently
version suffix enforcement works
client and server reject reasons remain aligned enough for stable UX
18. Acceptance Criteria

This story is complete only when all of the following are true:

the client provides a capability creation helper
the client provides a reusable namespace validator
the canonical format <domain>.<category>.<capability>.v<major> is enforced locally
invalid names are rejected deterministically
valid names are accepted consistently
version suffix enforcement works locally
artifact insertion into Keyhole-native repo declarations is deterministic when explicitly invoked
duplicate insertion is prevented or surfaced deterministically
validation messages include clear repair guidance
foreign repos are not silently mutated by default
client behavior aligns with boundary validation semantics
proof demonstrates invalid names rejected client + server, valid names accepted consistently, and version suffix enforcement works
19. Non-Goals

This story does not:

implement remote capability registry discovery
solve provider resolution
infer capabilities from arbitrary repo code by itself
auto-register capabilities with MCP
silently rewrite malformed declared capabilities in-place
convert foreign repos into Keyhole-native repos automatically

It establishes correct capability naming and local creation/validation discipline.