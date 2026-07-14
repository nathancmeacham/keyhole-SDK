# sdk-client-05.md

# SDK-CLIENT-05 - Capability Passport Generation

**Story ID:** SDK-CLIENT-05 / sdk-client-05  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Local Passport Generation  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-05.md`  
**Depends On:** `sdk-client-02.md`, `sdk-client-03.md`, `sdk-client-04.md`, `sdk-client-10.md`, SDK-CLIENT master guidance  
**Precedes:** later registration, verification, lineage linking, and governed capability reuse  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-05 defines the client-side contract for deterministic **capability passport generation** from lawful local repo truth.

Its purpose is to let a builder generate a **portable governance artifact** that can later be verified, stored, lineage-linked, and reused by the MCP boundary.

This story must make the following true:

- a Keyhole-native repo can emit a deterministic capability passport from declared local truth,
- the passport is transport-safe and lineage-ready,
- the generated artifact is stable enough for proof, verification, and reuse,
- the client refuses to mint an authoritative passport from undeclared or purely inferred capability guesses,
- foreign repos are handled honestly rather than being silently treated as passport-ready.

This story is where a governed repo stops being only a directory with declarations and begins to emit a **portable capability artifact**.

---

## 2. Why This Story Exists

The scaffold, namespace, and contract stories establish the local ingredients of governed participation, but they do not yet produce the portable artifact that downstream repos and the MCP boundary need in order to reason about a repo's declared capabilities.

Without this story:

- capabilities remain trapped inside local repo declarations,
- there is no deterministic transport object for later boundary verification,
- lineage between repo, capability, and proof is not formalized,
- downstream capability reuse remains weaker and more ad hoc,
- builders cannot safely export reusable governed capability identity.

This story exists to turn local declarations into a **portable governance artifact**.

It is important, however, that the client does **not** overreach:

- a native repo may be ready to generate an authoritative passport,
- a foreign repo is usually **not**.

This story must preserve that distinction.

---

## 3. Core Thesis

A capability passport is a **portable governance artifact**.

It is not:

- a secret,
- a token,
- a freeform user-authored document,
- or a fuzzy inference summary.

It must be:

- generated from declared repo truth,
- deterministic,
- explicit in scope,
- transport-safe,
- suitable for server-side re-verification.

The client must not allow casual or ambiguous passport generation that depends on:

- hidden local state,
- machine-specific randomness,
- unstable ordering,
- or inferred capabilities that were never explicitly declared.

---

## 4. Strategic Role

SDK-CLIENT-05 sits after:

- **SDK-CLIENT-02** - scaffolded repo shape
- **SDK-CLIENT-03** - capability namespace enforcement
- **SDK-CLIENT-04** - local governance and dependency validation

It prepares for:

- later repo registration,
- capability verification and storage,
- lineage linking,
- downstream dependency resolution,
- governed capability reuse.

In practical terms:

```text
repo scaffold
  -> validated declarations
  -> capability passport generation
  -> later boundary verification + storage
  -> lineage linking
  -> governed reuse

For foreign repos, this story does not come immediately after ingestion.

A foreign repo must first move through alignment until it has enough declared capability truth to support authoritative passport generation.

5. Supported Repo Postures

This story must explicitly distinguish between repo postures.

5.1 Native governed repo

A repo is considered passport-generation eligible when it has enough governed local structure to support deterministic generation from declared truth.

Typical indicators include:

scaffolded repo shape
native governance files
valid declared capability names
usable repo identity metadata
successful local validation
5.2 Foreign or ingestion-backed repo

A repo built outside Keyhole is not passport-ready by default.

Even if ingestion inferred likely capabilities, the client must not treat those inferred capabilities as sufficient to mint an authoritative capability passport unless a later explicit alignment flow has converted them into declared truth.

5.3 Important rule

This story supports:

authoritative passport generation for native governed repos
honest refusal / readiness guidance for foreign repos that are not yet declaration-ready

The client must not blur those paths.

6. Scope
In Scope

Client-side implementation of:

repo posture detection for passport eligibility
repository inspection for passport inputs
deterministic passport generation
canonical transport-safe passport shape
stable digest / fingerprint generation
lineage-ready metadata fields
local validation before generation
local artifact emission and proof linkage
repair guidance when generation is not yet lawful
Out of Scope

This story does not include:

server verification logic
server storage logic
registry publication
dependency resolution
promotion or canonical minting
server-side signature authority
marketplace visibility behavior
authoritative passport generation from inference-only foreign repos

Those belong to the server zipper story or later client flows.

7. Command Surface

The client must expose explicit passport generation.

Recommended CLI shape:

keyhole passport generate

Reasonable extensions include:

keyhole passport generate --output capability_passport.generated.yaml
keyhole passport show
keyhole passport validate
keyhole passport generate --json

The exact command set may evolve, but generation must remain:

explicit,
inspectable,
deterministic,
and locally testable.
8. Source Inputs

Passport generation must read from declared repo truth, not fuzzy inference.

Possible local inputs include:

keyhole.yaml
governance_contract.yaml
declared capabilities in canonical repo files
dependency declarations where needed for lineage context
local proof-ready metadata where applicable
Important rule

Declared capabilities are authoritative for this story.

The client must not silently insert undeclared inferred capabilities into the passport.

If capabilities are only inferred from ingestion or graphing, the client must reject authoritative generation and explain the next alignment step instead.

9. Capability Discovery Rules for Passport Generation

The client must determine which capabilities belong in the passport from declared local repo artifacts.

Rules:

declared capabilities are authoritative
invalid capability names are rejected before generation
undeclared inferred capabilities are not included
duplicate declarations are rejected deterministically
capability ordering is deterministic

This keeps the artifact portable, governed, and reviewable.

10. Passport Output Shape

The generated artifact must follow a canonical transport-safe structure.

A reasonable minimum shape is:

schema_version: v1
artifact_kind: capability_passport
repo:
  repo_name: <name>
  repo_id: <id-or-null>
  owner: <owner>
identity:
  tenant_id: <optional-known>
  org_id: <optional-known>
capabilities:
  - name: payment.stripe.integration.v1
    visibility: private
    status: declared
lineage:
  parent_repo: <optional>
  parent_passport_digest: <optional>
proof:
  local_proof_ref: <optional>
transport:
  generated_at: <timestamp>
  digest: sha256:...

The exact schema can tighten during zipper closure, but the client must emit a stable artifact with these conceptual sections:

repo identity
capability declarations
optional lineage hints
proof reference
transport metadata
11. Deterministic Serialization Contract

Determinism is the core property of this story.

Required deterministic behaviors
stable field ordering
stable capability ordering
stable digest generation
no machine-specific absolute paths in digest basis
no uncontrolled timestamp influence in digest basis
same effective repo input -> same passport semantics and digest
Passport must change when

The passport must change when:

capability declarations change
repo identity metadata changes
lineage hints change
included proof-reference inputs change
schema version changes
Passport must remain stable across

The passport must remain stable across:

reruns on the same repo
different machines with the same effective repo state
repeated generation with no declared changes
12. Transport Safety Contract

The passport must be safe to submit to MCP without leaking sensitive or machine-local contamination.

Forbidden content

The passport must not include:

access tokens
raw API keys
local credential material
private machine usernames unrelated to governance identity
arbitrary absolute filesystem paths
local debug junk
host-specific ephemeral values with no governance meaning
Allowed content

The passport may include:

stable repo identity metadata
declared capability names
optional tenant/org identifiers when legitimately known
lineage hints
local proof references or digests
deterministic transport metadata
13. Local Persistence Rules
13.1 Native repo case

For a Keyhole-native repo, the client may write the generated passport into a predictable governed path such as:

capability_passport.yaml

or a clearly named generated equivalent.

13.2 Foreign repo case

For a foreign repo that is not passport-ready, the client must not write an authoritative capability_passport.yaml into the repo by default.

Instead, it must:

reject authoritative generation, or
emit an out-of-tree advisory artifact only if such behavior is explicitly supported later

This story should prefer honest refusal over pretending readiness.

13.3 No silent mutation

The client may create or update the passport artifact when the path is lawful, but it must not silently rewrite unrelated governance files as a side effect.

14. Lineage Requirements

The client does not perform final lineage linking, but it must emit enough lineage-ready material for the server to do so later.

At minimum, the passport must carry or support:

repo identity
declared capability names
parent repo reference if declared
parent passport or upstream lineage hints if declared
local proof references where available
deterministic passport digest

The client must not pretend lineage is final at this stage.

It must only make later verification and linking possible.

15. Validation Requirements Before Generation

Before writing the passport, the client must validate:

repo posture is passport-generation eligible
required schema files exist when the repo is native
capability names are valid
duplicates are rejected
required repo identity metadata is present
the artifact will remain transport-safe
the repo has enough declared truth to support authoritative generation

The client should reuse keyhole validate internals where possible rather than duplicating validation logic.

16. Success UX

On success, the client must tell the builder:

that the passport was generated
where it was written
which digest was produced
how many capabilities were included
whether it is ready for later boundary verification

Example:

Capability passport generated.
Path: capability_passport.yaml
Capabilities: 3
Digest: sha256:...
Next step: later verify or register with MCP

The exact next-step text may vary by the surrounding flow, but the client must remain concrete.

17. Failure UX

When generation fails, the client must provide deterministic repair guidance.

Example failure classes:

repo not passport-ready
invalid capability name
missing repo identity metadata
malformed governance contract
unsupported schema version
duplicate capability declaration
non-transport-safe input contamination

Each failure must include:

reason
affected file/field when possible
next-best repair action

Examples:

"Run keyhole validate and fix the invalid capability declaration."
"This repo is foreign and not ready for authoritative passport generation."
"Use ingestion/alignment flows before generating a capability passport."
"Add missing repo identity metadata to keyhole.yaml."
18. Artifact and Proof Placement

Because many target repos may still be foreign or partially aligned, proof and generation artifacts must not assume in-repo proof placement by default.

Default artifact path

By default, proof and generation-side artifacts should live in a tool-owned local state path.

A reasonable shape is:

<tool-owned-state>/
  passport/
    generation_result.json
    summary.md
    digest.txt
Native repo mirror path

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror supporting artifacts into canonical in-repo proof locations.

Required proof metadata

Proof should include at minimum:

passport digest
source files used
capability count
command invocation
generation result
repo posture
no-silent-mutation confirmation where relevant
19. Relationship to Server Zipper Story

The client story ends at deterministic generation of a transport-safe, lineage-ready passport artifact.

The server zipper partner is responsible for:

verification
persistence
lineage linking
acceptance/rejection
event emission

The client must therefore guarantee that the server receives an artifact that is:

predictable
verifiable
complete enough for lineage work
free of local contamination
20. Local Test Strategy
20.1 Happy path native repo
start from valid governed scaffold
declare one or more valid capabilities
generate passport
assert file created
assert digest created
assert stable output
20.2 Determinism on repeated runs
generate passport twice from identical repo state
assert identical digest
assert stable serialized content
20.3 Capability ordering stability
reorder declarations where order should not matter
assert passport capability ordering remains canonical
20.4 Invalid capability rejected
declare malformed capability name
run generation
assert deterministic failure
assert repair guidance
20.5 Missing metadata rejected
remove required repo identity field
assert generation fails with clear reason
20.6 Duplicate capability rejected
declare same capability twice
assert deterministic failure
20.7 Transport-safety enforcement
inject forbidden local contamination
assert generation rejects or strips according to contract
assert final passport remains safe
20.8 Foreign repo block
point generation at a foreign repo or foreign posture
assert authoritative generation is blocked
assert guidance points to ingestion/alignment rather than fake success
20.9 Proof artifact generation
generate passport with proof enabled
assert proof references include digest and source summary
21. Acceptance Criteria

This story is complete only when all of the following are true:

the client can generate a capability passport from a native governed repo
the generated passport is deterministic for the same effective input
the passport has a transport-safe shape
invalid capability declarations are rejected before generation
missing required repo/governance metadata is rejected deterministically
duplicate capability declarations are rejected
the passport artifact is written to a predictable local path when lawful
the passport includes sufficient identity and lineage-ready metadata for later server verification
the client emits clear repair guidance on failure
foreign repos are not silently treated as passport-ready
local proof artifacts can include the generated passport and digest
22. Non-Goals

This story does not:

publish capabilities into a shared registry
decide final visibility policy beyond local declaration fields
verify signatures server-side
grant trust or authority by generation alone
allow freeform manual passport authoring as a first-class path
replace local validation from sdk-client-04
turn inference-only foreign repo structure into authoritative passport truth
23. Closure Standard

SDK-CLIENT-05 is closed when the client can take a valid native governed repo and deterministically emit a portable capability passport that the server can later verify, store, and lineage-link without ambiguity.

It is equally important that the client can truthfully refuse to mint that artifact for foreign or insufficiently aligned repos that are not yet ready.

This story is not about making the repo merely describe itself.

It is about making the repo emit a governed reusable capability artifact only when that is lawful.

24. One-Line Summary

Generate deterministic, transport-safe capability passports from declared native repo truth while refusing to mint authoritative passports from foreign or inference-only repo state.