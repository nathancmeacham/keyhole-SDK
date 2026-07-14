# sdk-client-19.md

# SDK-CLIENT-19 - Budget, Limit, and Overload Visibility

**Story ID:** SDK-CLIENT-19 / sdk-client-19  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Run Budget and Limit Visibility  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-19.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-09.md`, `sdk-client-15.md`, `sdk-client-16.md`, `sdk-client-17.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** richer explainability and support-bundle surfaces that may summarize runtime pressure and budget history  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-19 makes runtime pressure visible, intelligible, and trustworthy at the client boundary.

A governed platform cannot feel arbitrary under load.

When a governed run is:

- deferred,
- rate limited,
- partially admitted,
- rejected for concurrency posture,
- terminated because a runtime budget was exhausted,
- or completed with budget warnings,

the client must not render that outcome as a vague failure, transport mystery, or unexplained instability.

This story ensures that builders can:

- inspect budget and limit posture when the server provides it,
- distinguish runtime pressure from user error or contract failure,
- understand whether retrying is useful,
- preserve proof of what happened,
- and reason about next-best action under pressure.

This story does not invent budgets.

It makes existing and future server-side budget and overload behavior **usable at the client boundary**.

---

## 2. Why This Story Exists

By the time SDK-CLIENT-19 matters, the client already supports:

- governed run submission,
- explicit context-bound execution,
- replay-safe and idempotent transport,
- accepted/deferred lifecycle handling,
- proof continuity across runs.

But unless the client can surface budget and pressure conditions clearly, builders will experience lawful runtime behavior as:

```text
random failure

instead of:

governed backpressure with an explainable reason

This story exists because a platform that enforces limits but cannot explain them will feel unstable even when it is behaving correctly.

SDK-CLIENT-19 turns runtime pressure into part of the product experience.

3. Core Thesis

Budget and overload outcomes are not generic errors.

They are governed runtime outcomes that must be rendered with the same discipline as any other execution result.

The client must clearly distinguish between:

Admission pressure
The request was not fully admitted yet.
In-run budget exhaustion
The run began lawfully but could not finish within allowed resource bounds.
Rate/concurrency limits
The request was throttled or gated by policy or capacity.
Observation or transport failure
The client could not observe or retrieve state, but that is not the same as a budget decision.

The client must not collapse these into one vague "failed" bucket.

4. Strategic Role

SDK-CLIENT-19 sits on top of the already-sealed run lifecycle:

sdk-client-09
  -> governed run entrypoint

sdk-client-15
  -> request identity, idempotency, retry safety, replay-aware transport

sdk-client-16
  -> explicit governed context binding

sdk-client-17
  -> accepted/deferred run tracking, wait, tail, resume

sdk-client-19
  -> budget, limit, and overload visibility across that same lifecycle

This story does not redefine run behavior.

It makes pressure and runtime limits intelligible across the run surfaces that already exist.

5. Scope
Included
budget posture display when the server provides it
deterministic CLI rendering for overload and limit outcomes
stable rendering across run, status, wait, tail, and resume
proof integration for budget/limit metadata
repair-oriented next actions
generic fallback rendering for future limit categories
zipper expectations against sdk-server-19.md
Excluded
creation of new server budget categories
client-side prediction of future capacity
hidden retries that mask overload
local override of server limits
full support-bundle UX
direct canonical memory access
server-side policy tuning

Those belong elsewhere.

6. Supported UX Surfaces

SDK-CLIENT-19 affects these client surfaces.

6.1 Inline run outcomes

When a run returns terminal or non-terminal pressure information, the client must surface:

run status
limit or budget classification
concise explanation
next-best action
proof location or run reference
6.2 Run inspection

Budget and limit posture should be visible through one or more run inspection surfaces such as:

keyhole runs status <run-id>
keyhole runs inspect <run-id>

or equivalent integrated output.

6.3 Wait / tail / resume

Where async run tracking already exists, budget and pressure outcomes must appear coherently in:

status
wait
tail
resume

The builder must not have to infer overload from disconnected logs or transport behavior.

7. Outcome Families

The client must render the following families clearly.

7.1 Success with budget visibility

The run completed successfully and the server returned budget posture or near-limit information.

7.2 Deferred / temporarily held

The request was not arbitrarily rejected.
The platform deferred or paused work due to governed pressure handling.

7.3 Rate limited / concurrency limited

The request was constrained by rate or concurrency law rather than semantic invalidity.

7.4 Budget exhausted in-run

The request was admitted and began execution, but one or more runtime budgets were exhausted before completion.

7.5 Unknown or future pressure categories

The client must remain intelligible even when the server introduces new limit classes later.

8. Core Rendering Rules

The client must make these distinctions obvious.

8.1 Hard reject vs temporary pressure

The client must clearly distinguish:

hard reject - retrying immediately will not help
temporary defer / rate limit - retry later or follow retry guidance
budget exhausted in-run - the request started, but a budget ended execution early
8.2 Runtime pressure vs transport failure

The client must never misclassify:

a network failure as a budget outcome
a budget outcome as a generic transport failure
8.3 Non-terminal vs terminal pressure states

The client must distinguish:

accepted/deferred and still active
terminal rate/limit result
terminal budget exhaustion result

It must never fake completion.

9. Budget Posture Visibility

When the server provides budget posture, the client should surface a concise, useful summary.

Reasonable fields include:

budget class
budget used
budget remaining
near-limit signal
retry guidance if present

The client should show enough to help the builder reason, without overwhelming normal success output.

Example budget classes may include:

wall-time budget
event budget
memory/query budget
byte/output budget
concurrency slot budget

The client must not invent budget classes or values the server did not provide.

10. Rendering Requirements by Outcome
10.1 Success with budget visibility

The client should render:

final success state
concise budget summary if available
near-limit warnings if present
next-step suggestion only when useful
10.2 budget_exhausted

The client must render:

the exhausted budget class
whether the run partially executed
whether retrying unchanged is likely to fail again
repair suggestions
10.3 deferred

The client must render:

that the request was deferred due to governed pressure handling
whether the run still exists for later observation
whether retry timing or wait/resume is recommended
10.4 rate_limited / concurrency_limited

The client must render:

what class of limit applied
whether Retry-After or equivalent guidance was returned
how and when to retry
that the request did not fail because the builder's declaration was semantically invalid
10.5 Unknown future limit outcome

The client must support a fallback rendering contract that preserves:

top-level status
limit class if supplied
machine-readable metadata
repair guidance if supplied

This story must remain extensible without CLI redesign.

11. Repair Guidance Contract

Every overload or limit outcome must map to one or more concrete next actions when the server provides enough information.

Examples:

retry after the indicated interval
wait for current runs to complete
use resume or status instead of resubmitting
narrow the run scope
reduce output volume or target set
use --shadow for exploratory work
inspect context or dependency shape if runaway work is suspected
contact admin or inspect tenant posture where appropriate

The client must never leave the user with only:

Request failed

Repair guidance must be concrete whenever possible.

12. Transport and Lifecycle Alignment

This story must inherit the client posture already sealed elsewhere.

12.1 Transport inheritance

Budget/limit outcomes must preserve:

X-Request-Id continuity
run_id continuity where applicable
replay-aware proof continuity
honest handling of accepted/deferred outcomes
12.2 Async lifecycle inheritance

Where accepted/deferred behavior already exists, limit and budget outcomes must integrate cleanly with:

status
wait
tail
resume

The client must not treat pressure metadata as an afterthought bolted onto only one of those surfaces.

12.3 No hidden retry masking

The client must not silently retry until the limit clears and then pretend nothing happened.

Pressure must remain visible.

13. Foreign Repo and Native Repo Neutrality

This story should remain neutral to repo origin.

Whether the run originated from:

a Keyhole-native scaffolded repo, or
a foreign/ingested/partially aligned repo,

runtime budget and overload behavior must remain understandable.

However, artifact placement must still follow the broader client doctrine:

out-of-tree proof/state by default
optional in-repo mirroring only when the repo is already Keyhole-native and the builder explicitly opts in

This matters because budget evidence should not assume the repo is already fully governed locally.

14. Proof Contract

The client must preserve budget and overload information in local proof artifacts whenever present.

14.1 Required proof semantics

Budget/limit data must be preserved even on:

failure
defer
partial execution
resumed observation
14.2 Minimum fields

Reasonable proof fields include:

run_id
request_id
status
limit_outcome
limit_class
budget_snapshot
retry_after
repair_guidance
correlation_id
14.3 Summary requirements

Human-readable proof output must explain:

whether the run was accepted, deferred, limited, or budget exhausted
whether the platform remained lawful under pressure
what the builder should do next
14.4 Default artifact location

Because not every target repo is Keyhole-native, default proof should live in a tool-owned local state path.

A reasonable structure is:

<tool-owned-state>/
  runs/
    <run-id-or-request-id>/
      request.json
      latest-status.json
      outcome.json
      budget.json
      summary.md

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror proof into canonical in-repo proof locations.

15. Client Responsibilities

The client must:

parse machine-readable limit outcomes from the server
preserve them in proof
render them deterministically
respect Retry-After or equivalent guidance where applicable
keep terminology stable across commands
avoid wrapping pressure outcomes in generic opaque exceptions

The client must not:

silently retry until the limit clears
collapse overload into generic transport failure
invent unsupported budget numbers
tell the builder a request "succeeded" when it was actually deferred or terminated by budget law
16. Server Expectations (sdk-server-19.md)

The paired server story must provide:

budget/limit inspection or response metadata
overload-aware accepted/deferred/denied semantics
stable machine-readable outcome classes
optional Retry-After or equivalent retry guidance
durable run-linked limit metadata where relevant

The client side closes only when those server signals exist and the full UX is proven end to end.

17. Local Test Strategy
17.1 Rendering tests

Must verify:

budget_exhausted renders correctly
deferred renders correctly
rate_limited renders correctly
concurrency_limited renders correctly
unknown future limit code renders through generic fallback
repair guidance appears consistently
proof stores limit metadata
17.2 Inspection tests

Must verify:

budget posture is visible in run inspection output
budget warnings do not overwhelm ordinary success output
limit outcomes remain consistent across status, wait, and resume
17.3 Lifecycle tests

Must verify:

accepted/deferred run later terminating with budget law preserves one continuous lineage
resumed observation does not lose pressure metadata
retry guidance remains stable across repeated observation calls
17.4 Negative tests

Must verify:

malformed limit payload handled safely
missing optional budget fields degrade gracefully
generic transport failure is not misclassified as overload
client does not present deferred or limited state as success
18. Acceptance Criteria

This story is complete only when all of the following are true:

the client can surface budget usage when the server provides it
the client can surface limit posture in a stable, human-readable way
budget_exhausted outcomes render deterministically
deferred outcomes render deterministically
rate_limited and similar outcomes render deterministically
overload outcomes do not appear as arbitrary or generic failure
repair guidance is present for pressure outcomes
budget/limit metadata is preserved in proof artifacts
inspection surfaces can display budget posture where available
lifecycle surfaces preserve budget/limit meaning consistently
zipper proof shows request -> run -> budget/limit outcome clearly
19. Forward-Compatibility Requirements

This story must be implemented so new budget categories can be added without redesigning the client model.

The client must therefore treat pressure outcomes as:

a stable top-level category
optional structured metadata
optional retry guidance
optional quantitative budget fields

The rendering layer must be extensible rather than hard-coded to a tiny fixed set forever.

20. Non-Goals

SDK-CLIENT-19 does not:

decide runtime budgets
tune server overload control
replace server-side pressure handling
provide full support-bundle UX
predict future capacity precisely
override rate limits locally
expose raw server internals outside the governed client contract