# sdk-client-07.md

# SDK-CLIENT-07 - Repository Registration with MCP

**Story ID:** SDK-CLIENT-07 / sdk-client-07  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Repository Registration  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-07.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-10.md`, `sdk-client-15.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** richer capability resolution, alignment guidance, and governed participation workflows built on registered repos  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-07 defines the client-side contract for **repository registration with the MCP boundary**.

Its purpose is to let a builder take a repository that has already been **observed and assessed** and formally bind it to the Keyhole platform through a governed registration flow.

This story answers the question:

```text
how does a repo stop being "something we observed locally"
and become "a known governed participant recognized by MCP"?

The client must be able to:

determine whether the repo is ready for registration,
gather the right local and server-returned metadata,
shape a deterministic registration payload,
preserve request identity and idempotency semantics,
surface the resolved registration outcome clearly,
emit replayable proof whether the request was accepted, replayed, deferred, or rejected.

This story is not the server enforcement story.

This is the client half of the zipper: command shape, preflight, payload construction, transport discipline, proof, and repair guidance.

2. Why This Story Exists

A repo does not become a Keyhole participant merely because it exists on disk.

And for many real repos, especially foreign repos built without Keyhole, local structure alone is not enough to justify registration.

By the time registration happens, the system must already have enough understanding to answer:

what repo is this,
what did we observe,
how compatible is it,
what is being registered,
under whose identity is it being registered,
and is the builder asking for observation-only behavior or actual governed participation?

This story exists to prevent two bad assumptions:

1. local files mean the repo is already registered
2. ingestion means the repo is automatically accepted into governance

Neither is true.

Registration is a governed act.

It is explicit, attributable, replay-aware, and inspectable.

3. Core Thesis

Repository registration must support both of these source realities:

3.1 Keyhole-native repo path

A repo may already be scaffolded and locally aligned enough to register directly.

3.2 Foreign repo path

A repo may have arrived through ingestion first, with:

no scaffold,
no governance contract,
no capability passport,
unclear boundaries,
and low compatibility posture.

For those repos, registration must occur only after the client has enough information to form a lawful registration request.

That means this story must not assume every repo registering with MCP already has:

keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml

Those are one possible source of truth for registration inputs, not the only one.

The real requirement is:

the client must submit a deterministic, attributable registration request
based on known local and observed repo truth
without inventing missing governance state
4. Strategic Role

SDK-CLIENT-07 is the bridge between:

observed repo reality, and
platform-recognized governed participation.

Its place in the flow is now:

login
  ↓
ingest / observe repo
  ↓
compatibility + alignment understanding
  ↓
repo register   ? THIS STORY
  ↓
capability resolution / alignment / governed participation

For Keyhole-native repos, the ingest step may be structurally lighter.

For foreign repos, ingestion is the normal prerequisite because the repo is unlikely to be registration-ready on first contact.

Without this story, the builder can learn about the repo locally or through ingestion but cannot bind it formally into the MCP ecosystem as a recognized participant.

5. Client Responsibilities

The client is responsible for:

determining whether the target repo is registration-eligible,
verifying local and observed prerequisites before registration is attempted,
loading the right registration inputs from local repo state and/or prior ingestion artifacts,
constructing the registration payload deterministically,
attaching identity and request metadata,
sending the payload through the MCP boundary,
rendering the result clearly,
emitting replayable proof of the registration attempt,
surfacing repair guidance on rejection or incompatibility.

The client is not responsible for:

inventing canonical tenant/org binding on its own,
inventing missing governance state,
accepting a repo into the platform by itself,
bypassing the MCP boundary,
silently mutating the repo to "make registration work."
6. Supported Registration Inputs

This story must support two lawful input families.

6.1 Native governed repo registration

The repo already has enough declared structure locally.

Typical sources may include:

keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml
local validation results
6.2 Ingestion-backed registration

The repo was previously ingested and assessed as:

foreign,
partially_aligned,
or keyhole_ready

and the client now has enough non-invented truth to submit a registration request based on:

observed repo identity,
ingestion ID or ingestion artifact reference,
compatibility posture,
inferred structure where clearly marked,
builder-confirmed registration intent.
Important rule

The client must never blur the difference between:

declared local Keyhole truth,
observed repo facts,
inferred structure,
and server-recognized registration.
7. Command Contract
7.1 Primary command
keyhole repo register
7.2 Common forms
keyhole repo register
keyhole repo register --path ./my-repo
keyhole repo register --shadow
keyhole repo register --json
keyhole repo register --non-interactive
keyhole repo register --from-ingest <ingest-id>
7.3 Minimum expectations

The command must:

locate the repo or confirm the target path,
determine whether the registration source is native or ingestion-backed,
verify minimum prerequisites,
build a deterministic registration payload,
call the MCP registration surface,
emit replayable proof,
show whether the registration:
succeeded,
replayed,
was accepted/deferred,
or was rejected.
8. Precondition Contract

Before sending a registration request, the client must verify what it can locally.

8.1 Required baseline conditions

At minimum:

the user is authenticated,
the target repo path exists and is readable,
the repo identity can be determined,
the registration source is known,
there is enough local and/or prior-ingestion information to build a lawful registration request.
8.2 Native governed repo case

If the repo is registering as a Keyhole-native governed repo, the client should verify the required declaration artifacts exist and are minimally valid.

Typical expected files may include:

keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml when applicable
8.3 Ingestion-backed case

If the repo is registering from prior ingestion, the client should verify:

a valid ingestion reference exists,
the ingestion result is available locally or retrievable,
compatibility posture and observed repo identity are available,
the builder is not being misled into believing inference equals declared truth.
8.4 Fail-local rule

The client must fail locally when problems are obvious locally.

Examples:

no auth session
unreadable path
impossible CLI option combination
missing required native artifacts in a native registration path
missing ingestion reference in an ingestion-backed path

The client must not send obviously-invalid requests to the boundary merely to learn what it already knows.

9. Registration Readiness Model

The client should present a clear readiness model before registration.

Reasonable readiness states include:

native_ready
ingestion_ready
partially_ready
not_ready

This is not canonical server truth.

It is client-side preflight guidance.

Examples:

a scaffolded repo with valid declarations may be native_ready
an ingested foreign repo with enough observed identity and acceptable posture may be ingestion_ready
a foreign repo with only low-confidence inferred structure may be partially_ready
a repo with missing identity/auth/path truth may be not_ready

This keeps the registration UX honest.

10. Payload Construction

The client must construct a deterministic registration payload from known repo truth.

10.1 Required payload sections

At minimum, the payload should include some combination of:

repo identity metadata
registration source (native or ingestion)
native declaration artifacts when present
ingestion reference and observed compatibility posture when present
local validation or preflight summary where applicable
request/proof correlation metadata
client version / command metadata
10.2 Example shape
{
  "repo": {
    "name": "workorder-platform",
    "path_digest": "sha256:...",
    "repo_digest": "sha256:...",
    "registration_source": "ingestion"
  },
  "native_artifacts": {
    "keyhole": null,
    "governance_contract": null,
    "capability_passport": null,
    "dependencies": null
  },
  "ingestion": {
    "ingest_id": "ing_123",
    "compatibility_posture": "partially_aligned"
  },
  "preflight": {
    "status": "PASS",
    "readiness": "ingestion_ready"
  },
  "client": {
    "command": "keyhole repo register",
    "cli_version": "0.x.y"
  }
}

The exact wire contract may evolve with the server zipper pair, but the client must keep serialization stable enough for proof and replay.

11. Identity Context Requirements

This story must preserve the no-floating-execution rule.

Every registration attempt must carry deterministic identity context.

The client must be ready to bind or receive binding for:

tenant_id
org_id
user_id
cohort_id
worker_id
repo_id
workspace_id
origin
purpose

The client may not invent authoritative tenant/org truth, but it must:

send what it knows,
preserve what the server resolves,
render returned identity binding clearly,
include it in proof.
12. Transport Discipline

Registration is a public write-bearing client operation and must inherit SDK-CLIENT-15 from day one.

That means:

every request gets X-Request-Id,
write-bearing registration attempts use X-Idempotency-Key,
retries of the same logical attempt preserve the same key,
the client must not bypass the centralized transport layer,
replay-aware outcomes must be preserved in proof.

Registration must be treated as:

same repo + same request identity + same attempt
-> replay-safe outcome
Accepted/deferred note

If the boundary returns non-terminal accepted/deferred registration behavior under load, the client must render that honestly and preserve follow-up identity rather than faking terminal completion.

13. UX Contract
13.1 Success rendering

On success, the client must display:

repo name or path
registration state
registration source (native or ingestion)
resolved identity binding returned by the server
whether the result was fresh or replayed
proof location

Example:

✔ Repository registered
repo: workorder-platform
source: ingestion
tenant: tenant-123
org: org-456
cohort: builder-default
worker: worker-abc
repo_id: repo-789
proof: <tool-owned-state>/repo_register/...
13.2 Replayed outcome

If the same logical registration attempt replays safely, the client must treat that as a stable governed outcome, not a confusing failure.

13.3 Accepted/deferred outcome

If the server returns accepted/deferred registration, the client must render that honestly and surface the next observation step.

13.4 Failure rendering

On rejection, the client must surface:

reject reason
source of the problem when known
whether the issue is native-artifact-related, ingestion-related, auth-related, or boundary-related
next-best repair guidance
proof location
13.5 Non-interactive mode

A machine-readable mode must exist:

keyhole repo register --json
14. Repair Guidance Rules

The client must always offer the next-best action.

Examples:

If auth is missing:

Run: keyhole login
Then re-run: keyhole repo register

If native artifacts are missing:

This repo is not ready for native registration.
Run: keyhole ingest .
Review compatibility posture and alignment guidance.
Then re-run: keyhole repo register --from-ingest <ingest-id>

If ingestion posture is too weak:

This repo is not yet registration-ready.
Review inferred structure and compatibility posture.
Address the suggested alignment steps.
Then retry registration.

If a native passport is missing but the repo is otherwise valid:

Generate or repair the capability passport, then re-run registration.

Repair guidance must be concrete, not generic.

15. Proof Contract

Every registration attempt must emit replayable client-side proof, even when rejected.

15.1 Proof placement rule

Because many repos will still be foreign at registration time, proof must not be written into the target repo by default.

Default proof should live in an explicit tool-owned local state path.

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror proof into in-repo canonical proof paths.

15.2 Minimum proof contents

A reasonable structure is:

<tool-owned-state>/
  repo_register/
    <request-id-or-registration-ref>/
      request.json
      response.json
      identity_context.json
      artifacts_snapshot.json
      summary.md
      digest.txt
15.3 Required semantics

The proof must capture:

repo path / digest
registration source
command invocation
request identity
server response
resolved identity binding if returned
whether the registration was accepted, replayed, deferred, or rejected
repair guidance when applicable

The proof core must be sufficient to explain the registration attempt later without re-reading the entire repo.

16. Local Artifact Snapshot Rules

The client must capture a deterministic snapshot of the inputs used for registration.

Native path snapshot sources

When applicable:

keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml
validation or preflight artifact
Ingestion-backed path snapshot sources

When applicable:

ingestion reference
ingestion summary
compatibility posture
observed repo identity summary
any builder-confirmed hints used to shape registration

This ensures proof is tied to the exact information presented to MCP.

17. Server Zipper Expectations

The paired server story is expected to provide:

registration endpoint
identity binding resolution
repo registry presence
deterministic acceptance / rejection
replay-safe behavior
registration evidence emission
returned bound fields sufficient for client proof and display

At minimum, the client should expect the server to return:

registration status
repo ID
resolved tenant/org/cohort/worker/workspace binding
correlation or request reference
whether the result was created, replayed, deferred, or rejected

The client must preserve all of that in proof and UX.

18. Determinism Requirements

The client-side registration flow must be deterministic everywhere it has authority.

Required stable behaviors
same repo state + same registration source -> same payload shape
same input snapshot -> same local digest behavior
proof layout is stable
human and JSON output modes are stable
failure categories and repair guidance formats are stable
Forbidden behavior
silently inventing missing artifact fields
silently mutating repo declarations to make registration succeed
emitting unstable proof structure for the same outcome
19. Shadow Mode Considerations

Registration may support:

keyhole repo register --shadow

This story should be structured so shadow registration can be added or expanded without changing the command model.

If shadow registration is supported by the paired server surface, the client must:

mark it explicitly,
preserve it in proof,
render it clearly,
avoid implying full governed participation when the result is observational or low-risk only.
20. Acceptance Criteria

This story is complete only when all of the following are true:

keyhole repo register exists and targets the current repo or explicit --path
the client supports registration from native repo state and/or ingestion-backed state
the client blocks registration when obvious prerequisites are missing
the client assembles a deterministic payload
the client includes request identity and idempotency metadata
the client renders accepted, replayed, deferred, and rejected outcomes clearly
the client emits replayable proof for every registration attempt
the proof captures the exact input snapshot used for registration
the client preserves server-returned identity binding in proof and UX
the client never silently mutates the target repo during registration
21. Tests
21.1 Local deterministic tests
same repo state + same mode -> same payload shape
same input snapshot -> same artifact snapshot digest behavior
missing prerequisites -> deterministic local block
successful response -> proof emitted with expected fields
replayed response -> rendered as stable outcome
accepted/deferred response -> rendered honestly
21.2 Zipper tests
repo appears in registry
identity bound correctly
registration is replay-safe
registration evidence emitted under the paired server contract
21.3 Negative tests
malformed native artifact blocks before network call when required
missing ingestion reference blocks clearly on ingestion-backed path
invalid local input state yields repair guidance
rejected registration still emits proof artifact
foreign repo is not treated as native-ready by default
22. Non-Goals

This story does not:

define capability resolution
define governed runtime execution
define context lifecycle
rewrite repo artifacts silently
insert scaffold files into foreign repos by default
expose direct canonical memory access
finalize alignment on behalf of the builder
replace later explainability or async observation stories

This story is specifically about:

taking a repo that is sufficiently understood
and binding it lawfully to MCP