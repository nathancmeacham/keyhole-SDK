# sdk-client-16.md

# SDK-CLIENT-16 - Context Lifecycle and Governed Run Binding

**Story ID:** SDK-CLIENT-16 / sdk-client-16  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Context Lifecycle  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-16.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-02.md`, `sdk-client-09.md`, `sdk-client-15.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** `sdk-client-17.md`, richer explainability and budget-aware execution stories  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-16 makes governed context a first-class, builder-visible execution boundary.

By the time a builder reaches this story, the client already knows how to:

- authenticate,
- establish active identity,
- scaffold a lawful governed repo,
- invoke governed runs,
- and use the centralized transport discipline for request identity, idempotency, retry, and replay-aware proof continuity.

What is still missing is the most important execution rule for external governed participation:

```text
no governed run may float without explicit governed context

This story introduces the client-side contract for:

compiling governed context,
inspecting governed context,
binding a run to a specific context digest,
making context explicit and inspectable instead of hidden,
preserving context lineage in proof artifacts,
rejecting contextless governed execution at the appropriate layer,
and remaining forward-compatible with later async, inspection, explainability, and budget-related stories.

This is not just a new command surface.

It is the story where the SDK teaches the builder:

execution happens against an explicit state-of-truth artifact
not against a vague "current environment"
2. Why This Story Exists

Without client-side context lifecycle support, builders naturally fall into unsafe patterns:

Context omission
Governed work is launched without understanding that context is required.
Context invisibility
The client compiles or selects context behind the scenes, but the builder cannot see which artifact actually governed execution.
Context churn
Builders repeatedly compile context without understanding digest identity, reuse, or whether the context changed.
Weak proof lineage
A run result exists, but it is unclear which context artifact governed it.

Those patterns are unacceptable because they weaken:

deterministic execution,
explainability,
repair guidance,
proof lineage,
memory containment,
and safe scale behavior.

This story closes that seam by making context an explicit, inspectable, durable client artifact.

3. Story Role

SDK-CLIENT-16 sits on top of the foundation already sealed:

sdk-client-00 / 01 / 01-a
  -> identity, auth bootstrap, active participant posture

sdk-client-02
  -> canonical local governed repo scaffold

sdk-client-09
  -> first governed run command surface

sdk-client-15
  -> request identity, transport discipline, retry/idempotency safety,
    replay-aware proof continuity

sdk-client-16
  -> explicit governed context lifecycle and no-floating-run enforcement

sdk-client-17+
  -> accepted/deferred run tracking, richer inspection, budget visibility,
    explainability, support surfaces

This story does not create a second control plane in the client.

The server remains authoritative for context validity and run admission.

The client is responsible for:

local preflight,
explicit context UX,
lawful request shaping,
durable proof linkage,
and honest repair guidance.
4. Scope
Included
keyhole context compile
keyhole context inspect
keyhole run --context <digest>
bounded helper UX such as --context auto
local validation for missing / malformed / conflicting context arguments
request shaping for context compile and context-bound run dispatch
explicit context-to-run lineage in local proof artifacts
durable local recording of the most recent known context reference, where appropriate
zipper expectations against sdk-server-16.md
Excluded
full async run tracking UX
final polling / wait / tail behavior
final explainability / support-bundle tooling
final budget / overload visibility
direct canonical memory access of any kind
server-side cache internals

Those belong to later stories.

5. Command Contract
5.1 keyhole context compile

Primary purpose:

compile or resolve a governed context artifact for the current repo and active identity context.

Expected behavior:

gather required local inputs,
shape a lawful compile request,
invoke the appropriate boundary surface,
receive a deterministic context result,
surface the resulting ctxpack_digest,
emit local proof artifacts,
optionally persist a local reference to the most recent successfully observed context digest.

The command must not frame context as a hidden debug artifact.

It is a runtime-boundary artifact.

5.2 keyhole context inspect

Primary purpose:

inspect a specific ctxpack_digest or an explicitly requested local recent reference.

Expected behavior:

render the digest clearly,
show a human-usable summary,
show repo / identity / lane / lens metadata when available,
show whether the context is suitable for governed run binding,
help the builder understand what state-of-truth the digest actually represents.
5.3 keyhole run --context <digest>

Primary purpose:

execute a governed run under an explicit builder-chosen context artifact.

Expected behavior:

require a digest argument,
include that digest in the governed run request,
preserve that digest in proof artifacts,
render the context binding in terminal output,
fail clearly if the digest is missing, malformed, rejected, stale, or incompatible.
5.4 Optional helper UX: --context auto

This story may support:

keyhole run --context auto

This is allowed only if explicit visibility is preserved.

Allowed behavior:

compile context automatically,
show the resulting digest,
bind the run to that digest,
record the compile -> bind transition in proof.

Forbidden behavior:

hiding the resulting digest,
silently choosing context without reporting it,
silently falling back to contextless execution,
changing the selected context digest later without making that visible.

The helper must never reduce to:

Running...

without showing which context governed the run.

6. Preconditions

Before compiling or binding context, the client must verify as applicable:

the user is authenticated,
active local credentials are present,
the repo contains the canonical scaffold,
required declaration artifacts exist in minimally valid form,
the repo is suitable for context compilation,
an explicit digest is present when --context <digest> is used,
--context auto is not combined with incompatible manual context flags,
the client can classify the command path correctly for transport handling.

The client must fail locally when the problem is obvious locally.

Examples:

missing authentication,
missing repo root markers,
malformed digest shape,
mutually exclusive flags,
absent scaffold files,
impossible local mode combination.

The client must not send obviously-invalid requests to the boundary merely to learn what it already knows.

7. Local Input Sources

The client may use these local sources to shape context-related requests:

keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml
active local identity / credential context
current repo metadata
optional local validation artifacts
the explicitly requested recent local context reference, when supported

The client must not fabricate repo identity, capability truth, or a context digest.

8. Context Compile Request Construction

When the builder runs keyhole context compile, the client must construct a deterministic compile request from:

active identity context,
repo identity,
requested mode or compile defaults,
local repo metadata,
declared origin / purpose where required,
correlation metadata,
proof seed metadata.

The compile request must be:

deterministic for the same local state,
attributable to the active builder and repo,
inspectable in local proof output,
compatible with later reuse, caching, and replay stories.

The client must preserve enough local metadata to explain later:

which repo state shaped the compile request,
which identity context initiated it,
which command triggered it,
which digest the boundary returned.
9. Context Inspect UX

keyhole context inspect must make context intelligible.

At minimum, inspection should surface:

ctxpack_digest
summary / display header
repo identity
tenant / org / workspace context where available
lane / lens where surfaced
artifact or evidence reference where available
local observation timestamp
whether this digest is the most recently compiled or most recently run-bound context, if known

The point is not to dump raw JSON only.

The point is to let the builder understand:

what state-of-truth this digest actually represents

Raw modes may still exist for automation.

10. Governed Run Binding Contract

When the builder executes:

keyhole run --context <digest>

the client must:

validate that a digest string is present,
include that digest in the governed run request,
preserve the digest in proof artifacts,
render the bound digest clearly in terminal output,
distinguish local-preflight failures from boundary admission failures.

This story does not require the client to prove remote digest existence locally if that authority belongs to the server.

But it does require the client to:

treat context binding as mandatory for governed runs,
preserve explicitness,
never silently drop or replace the digest.
11. No-Floating-Run Rule

This story hardens the client-side execution boundary:

governed runs must not proceed without explicit context,
the client must reject contextless governed execution at the appropriate layer,
helper UX may assist in creating or selecting context, but may not hide it.

That means all of the following are forbidden:

hidden context injection without visibility,
contextless fallback after compile failure,
silently selecting "latest" context unless the user explicitly asked for that behavior and the client surfaces the chosen digest,
presenting governed execution as though context were optional.
12. Transport Discipline Inheritance

All context lifecycle commands must inherit the transport discipline established in SDK-CLIENT-15.

That means:

every request gets X-Request-Id,
operations classified as WRITE_IDEMPOTENT_REQUIRED get X-Idempotency-Key,
retries of the same logical attempt preserve the same idempotency key,
the client must not bypass the centralized transport layer.
Operation-class expectations

At minimum:

keyhole context inspect is typically READ_ONLY,
keyhole context compile follows the live boundary contract and must be explicitly classified,
keyhole run --context <digest> must use the already-established run operation-class rules.

The client must not guess transport behavior ad hoc per command branch.

13. Result Rendering
13.1 Successful context compile

Must show at minimum:

success status,
ctxpack_digest,
repo identity,
proof artifact location,
useful next step, such as inspecting or running with that digest.
13.2 Successful context inspect

Must show:

digest,
summary,
relevant metadata,
whether it is recent / active / run-bound if known.
13.3 Successful run with explicit context

Must show:

run outcome,
bound ctxpack_digest,
correlation or run reference,
proof artifact location,
shadow mode if applicable.
13.4 Failure rendering

Must show:

failure class,
deterministic reason,
local-vs-remote distinction where possible,
concrete repair guidance,
proof artifact location when generated,
whether retrying the same attempt is appropriate.

A failure must never collapse into an opaque "bad request" or "something went wrong."

14. Repair Guidance Contract

The client must surface concrete next-best actions when context-related commands fail.

Acceptable examples include:

run keyhole context compile first
run keyhole context inspect <digest>
rerun with --context auto
repair scaffold or declaration files
reauthenticate
choose a valid digest from the recent local context reference
rerun after fixing an incompatible run/context combination

Repair guidance must distinguish between:

local misuse,
missing or malformed context input,
remote rejection,
unknown digest,
stale digest,
incompatible context/run combination.
15. Local Artifact and Proof Contract

The client must generate or update local proof artifacts for context lifecycle activity.

This story must build on the canonical proof structure established earlier:

proof_bundle/core/
proof_bundle/extended/

It must not invent a conflicting parallel proof root.

Recommended structure

A reasonable artifact layout is:

proof_bundle/
  core/
    context/
      <ctxpack_digest>/
        compile-request.json
        compile-response.json
        summary.md
    runs/
      <correlation-or-run-ref>/
        request.json
        response.json
        context-binding.json
        summary.md
  extended/
    context/
      <ctxpack_digest>/
        inspect-output.json
        debug.json
    runs/
      <correlation-or-run-ref>/
        render.log
        debug.json
Required semantics
context compile emits proof even on failure,
inspect may materialize local output for reproducibility,
run proof must include the bound ctxpack_digest,
--context auto must record the compile -> bind transition,
later stories must be able to reuse these artifacts for explainability and support.

Optional recent-context pointers may also live under .keyhole/state/ as local convenience metadata, but they must not be treated as authoritative platform truth.

16. Local Test Strategy
16.1 Local client tests

Must cover:

command parsing for keyhole context compile
command parsing for keyhole context inspect
command parsing for keyhole run --context <digest>
parsing and mutual-exclusion behavior for --context auto
malformed digest rejected locally
missing digest rejected locally when explicit digest is required
deterministic compile request shaping
proof artifact generation for compile
proof artifact generation for inspect
proof artifact generation for context-bound run
--context auto preserves explicit digest visibility
centralized transport layer is used instead of raw bypass logic
16.2 Boundary / zipper tests

Must prove:

governed run without context is rejected
valid context is visible and inspectable
context -> run linkage is durable and queryable
repair guidance is emitted for missing / invalid / stale / incompatible context
transport identity is present as required by SDK-CLIENT-15
16.3 Negative tests

Must cover:

hidden fallback from missing context to contextless run does not occur
--context auto does not hide the resulting digest
invalid or unknown digest produces clear failure UX
inspect on unknown digest produces deterministic repair guidance
client does not silently replace the requested digest
17. Acceptance Criteria

This story is complete only when all of the following are true:

the client exposes keyhole context compile
the client exposes keyhole context inspect
the client supports keyhole run --context <digest>
optional helper UX such as --context auto preserves explicit digest visibility
governed run without context is rejected at the appropriate layer
valid context is visible and inspectable to the builder
transport discipline from SDK-CLIENT-15 is inherited correctly
local proof artifacts preserve context compile and context-bound run lineage
context -> run linkage is durable and queryable through paired proof / server surfaces
repair guidance exists for missing, invalid, stale, or incompatible context
the story remains forward-compatible with later async, inspection, and explainability hardening
18. Zipper Expectations Against sdk-server-16.md

The paired server story must provide:

context compile / retrieval surfaces appropriate to the live boundary,
governed run admission requiring explicit context,
deterministic context validation,
durable context -> run linkage.

SDK-CLIENT-16 closes only when paired zipper proof demonstrates:

governed run without context is rejected,
valid context is visible and inspectable,
context -> run linkage is durable and queryable,
repair guidance exists for missing / invalid / stale / incompatible context.
19. Forward-Compatibility Notes

This story must not block later hardening.

Later stories will extend this surface for:

accepted / deferred run tracking,
polling / wait / tail flows,
richer inspection and explainability,
budget and overload visibility,
deeper proof and support tooling.

Therefore SDK-CLIENT-16 must avoid assumptions such as:

every run always returns final inline result,
--context auto can remain implicit,
context inspection never needs richer lineage,
proof can omit digest-level execution binding,
memory access belongs here.
20. Non-Goals

SDK-CLIENT-16 does not:

implement server-side cache internals,
provide final async run waiting/tailing UX,
expose direct canonical memory query/write APIs,
replace registration or validation,
implement final budget/overload visibility,
hide context from the builder in the name of convenience.
21. Story Closure Statement

SDK-CLIENT-16 is the story that makes governed context visible and binding at the client boundary.

When this story closes, a builder must be able to:

compile a governed context
inspect that context
run against that context explicitly
and prove afterward which context governed execution

without needing to guess what state-of-truth the platform actually used.