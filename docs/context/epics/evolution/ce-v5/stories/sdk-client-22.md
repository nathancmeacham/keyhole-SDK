# sdk-client-22.md

# SDK-CLIENT-22 - Account Deregistration and Deletion UX

**Story ID:** SDK-CLIENT-22 / sdk-client-22  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Identity Lifecycle Boundary  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-22.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-15.md`, `sdk-client-17.md`, `sdk-client-20.md`, `sdk-client-21.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** later identity-lifecycle administration, retention-aware support tooling, and broader organization offboarding flows  
**Last Updated:** 2026-04-14

---

## 1. Purpose

SDK-CLIENT-22 defines the client-side contract for **account deletion and deregistration**.

Its purpose is to let a human builder who already has an active, authenticated identity request deletion of that identity through a lawful, attributable, proof-bearing boundary.

This story must make the following true:

- a builder can initiate account deletion through the SDK/CLI,
- the client verifies enough local truth to avoid obviously invalid deletion attempts,
- the deletion request is sent through a governed mutation surface,
- the request is idempotent and replay-safe,
- the client never fakes synchronous completion,
- run/explain/support surfaces can still be used to understand what happened,
- proof artifacts are preserved locally,
- and the builder receives deterministic repair guidance when deletion is blocked or denied.

This story is not an onboarding story.

It is the **identity exit** story.

---

## 2. Why This Story Exists

The platform already supports:

- identity creation,
- verification,
- authentication bootstrap,
- governed runs,
- explainability,
- and support-bundle creation.

But without deletion, the builder identity lifecycle is incomplete.

Without this story:

- users can enter but not leave,
- support requests for account removal become operator-only ad hoc actions,
- privacy/compliance posture is weaker,
- lifecycle trust is incomplete,
- and deletion cannot be explained or proven through the same governed system the platform expects everywhere else.

This story ensures that deletion is not a secret backstage act.

It becomes:

- governed,
- attributable,
- replay-safe,
- explainable,
- and recoverable when blocked by policy.

---

## 3. Story Outcome

When this story is complete, the client must be able to:

- detect whether the live boundary supports account deletion,
- authenticate the builder before deletion is attempted,
- confirm which identity is about to be deleted,
- dispatch deletion through the canonical run surface,
- preserve request identity and idempotency identity,
- handle accepted/deferred lifecycle honestly,
- surface the resulting `run_id`,
- allow the builder to inspect, wait, resume, explain, and bundle the deletion outcome,
- and preserve proof locally even if the account becomes unusable after completion.

This story must support the builder experience:

```text
log in
-> confirm who you are
-> request deletion
-> receive accepted + run_id
-> inspect/explain outcome
-> later auth is no longer lawful
4. Scope
Included
keyhole deregister --registration-id <id>
optional non-interactive confirmation behavior such as --yes
local ownership-oriented preflight checks
governed deletion dispatch through the canonical boundary
request identity and idempotency handling
accepted/deferred run UX for deletion
integration with status, wait, resume, explain, and support-bundle
deterministic repair guidance
local proof and artifact emission
zipper expectations against sdk-server-22.md
Excluded
server-side deletion policy
server-side ownership validation logic
server-side auth revocation internals
org-wide admin deletion tooling
machine-user deletion
legal retention policy design
billing/marketplace offboarding behavior

Those belong to the server zipper story or later lifecycle work.

5. Constitutional Requirements

This story must preserve the following truths:

the MCP boundary is the only approved public participation surface
account deletion is a governed mutation, not a local shortcut
deletion must be attributable and replay-safe
the client must not expose a raw destructive REST shortcut when the governed run boundary is the lawful path
accepted/deferred execution must remain visible
failure must produce repair guidance rather than dead ends
the client must not fabricate successful deletion
the client must preserve proof locally even when the resulting account can no longer authenticate
direct account deletion must never bypass identity ownership checks, even if the server is the final authority for enforcement
6. Strategic Role

SDK-CLIENT-22 is a sibling to onboarding and authentication.

Layering
sdk-client-00
  -> identity creation and verification

sdk-client-01
  -> authentication bootstrap

sdk-client-22
  -> identity exit / deregistration / deletion

This story is intentionally not repo-centric.

Unlike many SDK stories, deletion is not primarily about:

scaffolded repos
repo registration
capability contracts
context digests tied to a repo

It is about the builder identity itself.

That means the client must remain usable even when invoked:

outside a governed repo
outside a repo entirely
or after repo state is irrelevant to the account lifecycle request
7. Repo Neutrality

This story must be repo-neutral.

The builder may invoke deletion from:

a native Keyhole repo,
a foreign repo,
a home directory,
or any other local path.

The client must not require:

keyhole.yaml
repo registration
capability declarations
proof_bundle directories inside a repo

Deletion is anchored in:

authenticated identity,
registration/account identity,
and the governed mutation boundary.

Not in repo posture.

8. Canonical Surface Contract

Account deletion must be dispatched through a governed run type, not a private REST shortcut.

Canonical mutation path

The client must target:

identity.delete.v1

through the canonical boundary surface:

POST /mcp/v1/runs/start
Why this is required

Deletion is:

write-bearing,
identity-sensitive,
potentially async,
explainability-worthy,
proof-bearing,
and audit-sensitive.

Therefore it must follow the same governed mutation doctrine as other important platform writes.

Explicitly not preferred

This client story must not be built around:

DELETE /auth/account

as the primary public surface.

That shape is too weak for:

accepted/deferred semantics,
run linkage,
Event Spine lineage,
explainability,
and consistent governed mutation behavior.
9. Command Surface
Canonical command
keyhole deregister --registration-id <id>
Recommended forms
keyhole deregister --registration-id <id>
keyhole deregister --registration-id <id> --yes
keyhole deregister --registration-id <id> --json
Optional future ergonomic extension

A later story may add:

keyhole deregister --self

But this story only requires the explicit --registration-id form.

Required behavior

The command must:

ensure the builder is authenticated,
inspect live surface posture,
confirm the current identity,
verify the request shape locally,
require destructive confirmation unless explicitly bypassed with --yes,
dispatch identity.delete.v1,
return accepted/deferred/run-linked output honestly,
preserve local proof and support artifacts.
10. Surface Negotiation Requirements

Before attempting deletion, the client must confirm the live boundary supports it.

This story must integrate with the surface-negotiation posture.

Required surface checks

At minimum, the client must know whether the boundary provides:

governed run dispatch
identity.delete.v1 or equivalent disclosed operation
required write-bearing transport guarantees for this command
explainability and support-bundle surfaces if they exist
Fail-closed rule

If the live boundary does not declare the required deletion surface, the client must fail closed and explain:

what is missing,
why the command is blocked,
and what the builder should do next.

The client must not guess that deletion exists.

11. Authentication and Ownership Preflight

The client is not the final ownership authority, but it must still prevent obviously invalid requests.

Required local checks

Before dispatching deletion, the client must:

ensure a valid auth context exists
run whoami or equivalent identity inspection
display the current acting identity clearly
require explicit target registration_id
preserve enough local data to help explain ownership mismatch later
Why this matters

The server will enforce final ownership rules.

But the client should still make it obvious when the user is about to say:

delete account X
while authenticated as Y

This is not a server replacement.
It is client-side safety and clarity.

Important rule

The client must never imply that a valid token alone automatically authorizes deletion of any arbitrary registration ID.

12. Confirmation UX

Deletion is destructive from the user's perspective and must not happen by accident.

Required confirmation behavior

If --yes is not supplied, the client must require an explicit confirmation prompt such as:

You are about to request deletion of account <registration-id>.
This will revoke future access if completed.
Type DELETE to continue:
Non-interactive mode

If --yes is supplied, the client may skip the prompt.

Forbidden behavior

The client must not:

delete silently
dispatch destructive mutation with no explicit user confirmation path
treat omission of confirmation as implied consent
13. Request Construction

The client must construct a deterministic governed deletion request.

Minimum logical request shape
{
  "run_type": "identity.delete.v1",
  "params": {
    "registration_id": "...",
    "confirm": true
  }
}
Client-side metadata requirements

The client must also preserve:

request identity
idempotency identity
acting identity snapshot from whoami
command invocation metadata
local correlation metadata
proof path references
Important rule

The client must not invent hidden admin fields, policy overrides, or unsupported parameters.

14. Transport Discipline

Deletion is write-bearing and must inherit the idempotent transport posture already sealed elsewhere.

That means:

every deletion request gets X-Request-Id
every deletion request gets X-Idempotency-Key
retries of the same logical deletion attempt preserve the same operation identity
the client must not bypass the centralized transport layer
replay/conflict/defer semantics must be normalized and rendered honestly
Required outcome families

The client must support, at minimum:

ACCEPTED
DEFERRED
REPLAYED
REJECTED

It must not collapse these into generic "success/failure."

15. Async Lifecycle Contract

Deletion must be treated as accepted/deferred governed work unless the boundary explicitly says otherwise.

Required UX

If deletion is accepted, the client must render something like:

✔ Deletion accepted
run_id: run_abc123
registration_id: reg_xyz789
next:
  keyhole runs status run_abc123
  keyhole runs wait run_abc123
  keyhole explain run run_abc123
Forbidden UX

The client must not print:

Account deleted successfully

unless the boundary has actually returned a terminal, truthful completion state.

Why this matters

Deletion may require:

identity locking
auth revocation
identity-provider updates
tombstone creation
event emission
proof assembly

The client must not hide that lifecycle.

16. Relationship to Explainability and Support

Deletion is a perfect example of why explainability and support bundles matter.

This story must integrate with:

keyhole runs status <run-id>
keyhole runs wait <run-id>
keyhole runs resume <request-id|run-id>
keyhole explain run <run-id>
keyhole support-bundle <run-id|request-id>

The builder must be able to answer:

was my deletion accepted?
did it complete?
was it blocked?
why did it fail?
what proof exists?

This story must not strand the builder after dispatch.

17. Local Artifact and Proof Placement

Deletion is identity-scoped, not repo-scoped.

Therefore proof and artifacts must not assume in-repo placement.

Default artifact location

Because this flow may run outside any governed repo, default artifacts must live in a tool-owned local state path.

A reasonable structure is:

<tool-owned-state>/
  deregister/
    <request-id-or-run-id>/
      request.json
      response.json
      identity_snapshot.json
      summary.md
      repair.json
      correlation.json
Optional repo mirroring

If the user happens to invoke deletion from a Keyhole-native repo and explicitly opts in, the client may additionally mirror support artifacts into canonical in-repo proof locations later.

That is optional and not required here.

Required semantics

Artifacts must preserve:

target registration_id
acting identity snapshot
command invocation
request identity
run_id if returned
outcome class
repair guidance
local generation metadata
18. Result Rendering
18.1 Successful acceptance

The client must render:

target registration_id
acting identity summary
accepted/deferred/replayed status
run_id or correlation reference
proof location
next-step commands
18.2 Replayed deletion

If the same logical attempt is replayed, the client must say so explicitly and not pretend it created a fresh deletion.

18.3 Rejection

If the server rejects deletion, the client must render:

reason class
whether the rejection is auth-related, ownership-related, policy-related, or lifecycle-related
concrete repair guidance
proof location
18.4 Already deleted

If the target is already deleted, the client must render a deterministic result such as:

already deleted
replay-safe no-op
inspect prior deletion run or support bundle

It must not mislead the user into thinking a new destructive mutation just happened.

19. Failure and Repair Guidance

Every non-successful or blocked path must include concrete next steps.

Example repair guidance classes
not authenticated
"Run keyhole login first."
ownership mismatch
"Log in as the account owner, then retry."
missing confirmation
"Re-run with confirmation or --yes."
surface unavailable
"The live boundary does not currently declare account deletion support."
already deleted
"Inspect the prior deletion outcome instead of retrying a new delete."
policy blocked
"Deletion is blocked by server policy; generate a support bundle or contact support/admin."

Repair guidance must be deterministic and action-oriented.

20. Local Test Strategy
20.1 Command parsing tests

Must verify:

keyhole deregister --registration-id <id> parses correctly
--yes works correctly
--json works correctly
missing --registration-id fails clearly
20.2 Preflight tests

Must verify:

unauthenticated deletion attempt is blocked locally
current identity is inspected before dispatch
confirmation is required when --yes is absent
confirmation is bypassed only when --yes is present
20.3 Transport tests

Must verify:

deletion uses governed transport
X-Request-Id is attached
X-Idempotency-Key is attached
replay-safe retries preserve the same logical attempt identity
20.4 Async lifecycle tests

Must verify:

accepted deletion renders correctly
deferred deletion renders correctly
replayed deletion renders correctly
next-step guidance points to status, wait, resume, and explain
the client does not fake synchronous completion
20.5 Proof tests

Must verify:

local proof artifacts are created deterministically
acting identity and target registration_id are preserved
run_id or correlation linkage is captured
rejection artifacts include repair guidance
20.6 Negative tests

Must verify:

missing auth is blocked
malformed registration_id is rejected locally where possible
surface negotiation failure blocks command cleanly
command does not silently proceed when boundary deletion is unavailable
client does not claim deletion completed when the boundary only accepted it
21. Acceptance Criteria

This story is complete only when all of the following are true:

the client exposes keyhole deregister --registration-id <id>
the client requires authentication before deletion dispatch
the client negotiates and confirms the live boundary supports deletion
the client requires explicit destructive confirmation unless --yes is supplied
deletion is dispatched through the governed run surface rather than a raw REST shortcut
the request is idempotent and replay-safe
accepted/deferred/replayed/rejected outcomes are rendered honestly
the client integrates with run status, wait, resume, explain, and support-bundle flows
local proof artifacts are generated deterministically outside the repo by default
failure paths produce repair guidance
the client does not strand the builder after deletion is accepted
the client story zippers cleanly with sdk-server-22.md
22. Zipper Expectations Against sdk-server-22.md

The paired server story must provide:

governed deletion run type
proof-of-ownership enforcement
deterministic deletion policy behavior
auth revocation
deletion lifecycle events
replayable deletion proof

SDK-CLIENT-22 closes only when paired proof demonstrates:

authenticated builder can request deletion of their own account
ownership mismatch is rejected deterministically
deletion is accepted/deferred/replayed/rejected honestly
later auth becomes unlawful after successful deletion
explainability and support flows can reconstruct the deletion lifecycle
23. Non-Goals

This story does not:

implement server-side deletion policy
decide whether deletion should be hard-delete vs tombstone
expose admin deletion tooling
support machine identity deletion
silently erase local credential stores without user awareness
turn deletion into a synchronous fake-success UX
bypass the governed run model for convenience
24. Story Closure Statement

SDK-CLIENT-22 closes when a human builder can request deletion of their own account through the SDK/CLI and receive a lawful, attributable, replay-safe, explainable outcome.

At that point, the builder experience must truthfully support:

log in
-> request deletion
-> receive accepted/deferred/replayed/rejected outcome
-> inspect what happened
-> prove what happened
-> later auth no longer works if deletion completed

That is the client-side completion of human account lifecycle.