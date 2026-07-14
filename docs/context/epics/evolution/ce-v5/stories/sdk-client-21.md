# sdk-client-21.md

# SDK-CLIENT-21 - Surface Negotiation and Compatibility Guardrails

**Story ID:** SDK-CLIENT-21 / sdk-client-21  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Boundary Compatibility Layer  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-21.md`  
**Depends On:** `sdk-client-15.md`, `sdk-client-16.md`, `sdk-client-17.md`, `sdk-client-18.md`, `sdk-client-19.md`, `sdk-client-20.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** broad external rollout where mixed server maturity must be handled truthfully  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-21 establishes the client-side discipline for **surface negotiation**.

Its purpose is to ensure the SDK behaves like a governed client rather than an optimistic API wrapper.

The client must:

- discover what the live MCP boundary actually supports,
- distinguish required safety surfaces from optional convenience surfaces,
- fail closed when required guarantees are absent,
- degrade gracefully when optional surfaces are absent,
- surface the negotiated result clearly to the builder,
- and carry that negotiated result forward into later commands instead of silently re-assuming unsupported behavior.

This story exists because the client roadmap now depends on surfaces that may not arrive everywhere at the same time, including:

- explicit context enforcement,
- accepted/deferred async execution,
- idempotency expectations,
- explainability surfaces,
- support-bundle retrieval,
- budget/limit visibility,
- tail/follow observation surfaces,
- and memory-boundary-safe behavior.

The client must not guess.

---

## 2. Why This Story Exists

Without compatibility guardrails, the SDK drifts into a dangerous pattern:

```text id="yu7pp9"
the client assumes the platform is more complete than it is

That creates three classes of failure:

2.1 False safety

The client assumes:

idempotent writes are enforced,
governed runs require context,
accepted/deferred run semantics exist,
explainability is available,
or budget visibility is present,

when the live boundary does not actually provide those guarantees.

2.2 False breakage

The client treats the absence of optional surfaces as fatal, even when core governed participation is still possible.

2.3 Opaque mismatch

The same SDK behaves differently across environments and the builder gets no clean explanation of why.

SDK-CLIENT-21 prevents those failures by forcing the client to negotiate reality before it leans on advanced behavior.

3. Core Thesis

Surface negotiation is the layer that separates:

architecture intent
from
live boundary truth.

The client must know, for the active environment:

what the server declares,
what the client requires for a given command,
what is blocked,
what is degraded,
and why.

The client must not silently substitute wishful architecture for actual capability disclosure.

4. Strategic Role

SDK-CLIENT-21 is cross-cutting and sits on top of the already-sealed client posture:

sdk-client-15
  -> request identity, idempotency, retry safety

sdk-client-16
  -> explicit context lifecycle and governed run binding

sdk-client-17
  -> accepted/deferred run lifecycle and observation

sdk-client-18
  -> no public direct-memory bypass

sdk-client-19
  -> budget, limit, and overload visibility

sdk-client-20
  -> explainability and support bundles

sdk-client-21
  -> truthfully determine which of those surfaces actually exist on the live boundary

This story does not create those surfaces.

It prevents the client from pretending they exist when they do not.

5. Scope
Included
negotiation against GET /mcp/v1/capabilities or equivalent declared surface
startup or lazy first-auth negotiation behavior
deterministic compatibility evaluation rules
required vs optional vs transitional surface classification
fail-closed behavior for missing required surfaces
degraded UX behavior for missing optional surfaces
builder-facing inspection of negotiated posture
local artifact/cached record of the negotiation result
zipper expectations against sdk-server-21.md
Excluded
implementation of async execution itself
implementation of idempotency itself
implementation of context enforcement itself
implementation of explainability itself
implementation of support bundles themselves
long-term full-version migration policy for every future SDK major

This story consumes declared boundary truth. It does not create it.

6. Repo Neutrality

This story must be repo-neutral.

Whether the user is operating on:

a fresh scaffolded Keyhole-native repo,
a foreign repo,
an ingested repo,
or a partially aligned repo,

surface negotiation must behave the same way.

It is about boundary compatibility, not repo identity.

That means the negotiated posture must describe:

environment truth,
command safety,
and feature availability,

not whether the local repo "deserves" those features.

7. Negotiation Principles
7.1 Truth before convenience

The client must prefer accurate capability detection over optimistic fallback.

7.2 Required vs optional must be explicit

The client must classify capabilities into at least:

required
optional
transitional / degraded but present
7.3 No silent assumption

The client must never silently assume:

accepted/deferred async execution exists,
context enforcement exists,
idempotency guarantees exist,
explainability exists,
support-bundle retrieval exists,
tail/follow exists,
budget visibility exists.
7.4 Stable messaging

A builder should be able to inspect one surface and understand:

what the server supports,
what the client expected,
what is blocked,
what is degraded,
and what to do next.
8. Capability Classes

The client must maintain a compatibility model with at least these categories.

8.1 Required surfaces

These are features whose absence must cause fail-closed behavior for relevant commands.

Examples include:

authenticated identity surface
stable run dispatch contract
explicit context support for commands that require context binding
idempotency guarantees for write-bearing commands once the client policy treats them as mandatory
registration surface when using repo register
8.2 Optional surfaces

These are features whose absence should degrade gracefully but not necessarily block core participation.

Examples include:

explainability
support-bundle retrieval
run tail/follow
budget/limit inspection
richer capability discovery enrichment
optional trust metadata lookup
8.3 Transitional surfaces

These are surfaces that exist but are declared preview, partial, degraded, or environment-specific.

This matters especially while environments may differ in:

inline terminal vs accepted/deferred run behavior
optional explainability depth
optional observation/tail support

The client must render transitional posture honestly.

9. Negotiation Trigger

The client may negotiate in one of two patterns.

9.1 Startup negotiation

At CLI startup or session bootstrap:

fetch server posture,
normalize it,
evaluate compatibility,
cache it for the active profile/session.
9.2 First authenticated call negotiation

If startup negotiation is too early or too expensive, the client may negotiate on the first authenticated command that depends on boundary truth.

In either case, the user must not be left unaware that negotiation happened.

10. Canonical Server Source

The canonical source for negotiation is:

GET /mcp/v1/capabilities

or an explicitly equivalent declared capability surface.

The server response must provide enough information for the client to determine support for surfaces such as:

run dispatch contract
accepted/deferred async behavior
context compile / inspect / binding support
context-required-for-runs posture
idempotency expectations
explainability
support-bundle retrieval
tail/follow observation
budget/limit visibility
version or operation disclosure

The client must not require hidden endpoints to infer these.

11. Normalized Client Negotiation Model

The client must normalize the server response into a local compatibility object.

Minimum local model
{
  "server_version": "...",
  "surface_fingerprint": "...",
  "operations": ["..."],
  "features": {
    "run_dispatch": true,
    "run_async_accept": true,
    "context_compile": true,
    "context_required_for_runs": false,
    "idempotency_required": false,
    "explainability": false,
    "support_bundle": false,
    "run_tail": false,
    "budget_visibility": false
  },
  "compatibility": {
    "status": "compatible | degraded | blocked",
    "required_missing": [],
    "optional_missing": [],
    "transitional": []
  }
}

The exact field set may evolve, but the normalized result must remain deterministic and inspectable.

12. Local Artifact and Cache Rules

The normalized negotiation result must be cached locally for the active profile/session and be inspectable.

Because this is not repo-specific and may apply even when the repo is foreign, the artifact should live in a tool-owned local state path by default.

A reasonable structure is:

<tool-owned-state>/
  compatibility/
    capabilities_raw.json
    negotiation_result.json
    summary.md
Required semantics
capabilities_raw.json preserves the raw server response
negotiation_result.json preserves normalized client interpretation
summary.md explains builder-facing posture
Freshness

The client may cache negotiation briefly, but must support deterministic refresh.

13. Command UX

The client should provide at least one explicit inspection surface such as:

keyhole surfaces

or an equivalently clear compatibility-inspection command.

This surface should display:

server identity/version when available
negotiated surface set
required missing features
optional missing features
transitional/degraded features
resulting posture:
compatible
degraded
blocked

It may also surface recommended repair steps.

14. Fail-Closed Rules

If a required surface is missing, the client must fail closed for the affected workflow.

Examples

If write-bearing commands require idempotency guarantees but the live boundary does not declare them, the client must not proceed with those commands.

If a context-bound run command requires explicit context support and the boundary does not provide the required context surfaces, the client must block that workflow rather than silently weakening it.

If repo registration depends on a registration surface that is missing or incompatible, keyhole repo register must fail closed.

Required UX

Fail-closed messaging must explain:

what surface is missing,
why it is required,
which command is blocked,
how the builder may recover.
15. Graceful Degradation Rules

If an optional surface is missing, the client must degrade gracefully.

Examples

If explainability is missing:

keyhole explain run may return a deterministic "surface unavailable" message
core run commands may still remain available

If support-bundle retrieval is missing:

local support artifacts may still be generated
server-enriched bundle behavior may be unavailable

If tail/follow is missing:

keyhole runs tail may degrade to polling if the contract allows it
or become unavailable with a clear message if no lawful fallback exists
Required UX

Degraded mode must be explicit and bounded, not random.

16. Compatibility Evaluation Rules

The client must define deterministic rules for deciding whether a command is allowed.

Recommended evaluation flow:

determine the command's required surfaces
compare them against negotiated posture
if any required surface is missing:
block
if only optional surfaces are missing:
degrade
otherwise:
proceed

This evaluation must be stable enough for local tests and user-facing explanation.

17. Relationship to Other Stories

SDK-CLIENT-21 must interoperate cleanly with:

15 - request identity, idempotency, retry safety
16 - context lifecycle and governed run binding
17 - accepted/deferred run lifecycle
18 - memory boundary enforcement
19 - budget/limit visibility
20 - explainability and support bundles

Its job is to ensure the client only attempts to use those surfaces when the live boundary truth says they exist.

18. Proof Contract

Every negotiation cycle must be able to prove:

what the server declared,
how the client interpreted it,
which required surfaces were missing,
which optional surfaces were missing,
which surfaces were transitional,
why a command was blocked or degraded.

This proof must support later questions such as:

why did this client refuse to run?
why did a feature appear degraded?
what did the server claim at the time?
19. Local Test Strategy
19.1 Positive tests
capabilities response parsed successfully
normalized negotiation object created deterministically
fully compatible posture yields compatible
missing optional feature yields degraded
missing required feature yields blocked
19.2 Negative tests
malformed capabilities response rejected deterministically
unknown version/feature shapes handled safely
client does not silently assume unavailable features
stale cached negotiation can be refreshed deterministically
19.3 Command-level tests
blocked command fails closed with repair guidance
degraded command surfaces reduced UX clearly
inspection command shows current posture accurately
negotiation artifact is written locally
19.4 Zipper tests
client detects missing required surface and fails closed with repair guidance
client detects missing optional surface and degrades gracefully
client does not assume accepted/deferred runs, context enforcement, or explainability exist everywhere
negotiation result is visible and inspectable
20. Acceptance Criteria

This story is complete only when all of the following are true:

the client negotiates live server posture at startup or first authenticated call
the client normalizes server capability declarations deterministically
required feature absence causes fail-closed behavior
optional feature absence causes graceful degraded behavior
transitional feature posture is surfaced honestly
builder-facing messaging explains why a feature is blocked or degraded
the client does not assume accepted/deferred async, context enforcement, idempotency guarantees, explainability, or budget visibility exist everywhere
surface negotiation results are visible and inspectable
negotiation artifacts are written locally for proof/support use
command-level compatibility checks are deterministic
zipper proof demonstrates truthful compatibility behavior against the paired server story
21. Non-Goals

SDK-CLIENT-21 does not:

replace long-term version negotiation for every future SDK major
hide incompatibility behind best-effort guesses
invent missing server features
make optional features mandatory prematurely
weaken required safety guarantees for convenience
22. Zipper Expectations Against sdk-server-21.md

The paired server story must provide:

capability/surface declaration via GET /mcp/v1/capabilities or equivalent
versioned feature flags or operation disclosure
explicit async/context/idempotency/explainability/support/budget surface disclosure

SDK-CLIENT-21 closes only when paired proof shows:

client detects missing required surfaces and fails closed with repair guidance
client detects missing optional surfaces and degrades gracefully
client does not assume advanced features exist everywhere
negotiation result is visible and inspectable on both sides of the zipper
23. Story Closure Statement

SDK-CLIENT-21 is the story that stops the SDK from confusing wishful architecture with live boundary truth.

When this story closes, the client must be able to say:

this is what the server actually supports
this is what I require for this command
this is what I can still do safely
and this is why

That is the minimum honest posture required before broad externalization.