# sdk-client-17.md

# SDK-CLIENT-17 - Async Run Tracking, Polling, and Durable Run UX

**Story ID:** SDK-CLIENT-17 / sdk-client-17  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Run Observation Lifecycle  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-17.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-02.md`, `sdk-client-09.md`, `sdk-client-15.md`, `sdk-client-16.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** richer explainability, budget-aware run observation, and support-bundle stories  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-17 defines the canonical client-side contract for governed runs that do not always complete inline.

This story makes accepted/deferred execution feel first-class rather than awkward.

By the time a builder reaches this story, the client already knows how to:

- authenticate,
- stand in a lawful governed repo,
- invoke governed runtime work,
- bind governed execution to explicit context,
- and use the centralized transport discipline for request identity, idempotency, retry, and replay-aware proof continuity.

What is still missing is durable client UX for the case where a governed run is:

- accepted but not yet terminal,
- deferred for later completion,
- still in progress,
- resumed after client interruption,
- or observed over time instead of finished in the submit response.

This story introduces that client-side lifecycle.

It defines how builders can:

- start a governed run,
- receive a durable run identity,
- inspect current state,
- wait for terminal outcome,
- reconnect after interruption,
- preserve proof continuity from admission through terminal resolution,
- and avoid mistaking observation failure for execution failure.

---

## 2. Why This Story Exists

A governed runtime that only supports:

```text
submit request
block
hope it finishes inline

is not sufficient for real external participation.

As Keyhole moves into:

long-running governed execution,
ingestion,
convergence,
declaration submission,
repair workflows,
and bounded execution under load,

the client must stop assuming every run finishes inside a single synchronous request/response cycle.

Without this story:

long-running runs feel broken,
users retry when they should resume,
ambiguous client interruption is confused with failed execution,
proof continuity breaks across admission vs terminal resolution,
async behavior looks like instability rather than design.

SDK-CLIENT-17 closes that seam by teaching builders the correct runtime model:

a governed run may be accepted before it is complete
a durable run identity survives interruption
status observation is separate from admission
proof spans the full run lifecycle
3. Story Role

SDK-CLIENT-17 sits on top of the foundation already established:

sdk-client-00 / 01 / 01-a
  -> identity, auth bootstrap, active participant posture

sdk-client-02
  -> canonical local governed repo scaffold

sdk-client-09
  -> governed run entrypoint

sdk-client-15
  -> request identity, idempotency, retry safety, replay-aware proof continuity

sdk-client-16
  -> explicit governed context lifecycle and no-floating-run enforcement

sdk-client-17
  -> accepted/deferred run tracking, polling, wait, resume, and durable run UX

This story does not redefine run submission.

Run submission already exists.

This story extends that surface so builders can observe and continue the same governed run identity over time.

The server remains authoritative for run state.

The client is responsible for:

durable local continuity,
honest rendering of non-terminal states,
lawful observation commands,
resume behavior that never duplicates execution,
proof continuity across lifecycle stages.
4. Scope
Included
accepted / deferred governed run handling
durable local run record support
keyhole runs status <run-id>
keyhole runs wait <run-id>
keyhole runs tail <run-id>
keyhole runs resume <request-id|run-id>
mixed inline-terminal vs accepted/deferred outcome handling
proof continuity across submit -> observe -> terminal outcome
deterministic terminal state rendering
zipper expectations against sdk-server-17.md
Excluded
final explainability / support-bundle UX
final budget / overload UX
direct canonical memory access
server-side scheduling internals
transport policy redesign
context compilation behavior itself

Those belong to other stories.

5. Command Contract
5.1 Submit path inheritance

keyhole run continues to be the submission command introduced earlier.

This story extends the outcome handling for that command when the boundary returns a non-terminal response such as:

accepted
deferred
running with durable run identity
another explicit non-terminal state under the paired server contract

The client must preserve:

run_id
request correlation metadata
context binding metadata
execution mode (shadow or governed)
proof continuity from submit time

The client must never misrepresent:

accepted as completed,
deferred as failed,
observation loss as execution loss.
5.2 Run status
keyhole runs status <run-id>

This command must:

retrieve the current known state of a governed run,
render current status clearly,
remain safe for repeated polling,
preserve raw output modes where useful,
update local proof continuity as appropriate.
5.3 Wait for terminal outcome
keyhole runs wait <run-id>

This command must:

observe the run until terminal state or explicit user interruption,
stop on terminal result,
render success / failure / denial / cancellation / defer-state clearly,
update proof artifacts under the same run lineage,
avoid changing the run itself.
5.4 Tail
keyhole runs tail <run-id>

This command must:

follow the best available observation surface supported by the live boundary,
present chronology clearly,
degrade honestly if live follow behavior is not available,
never pretend that polling snapshots are a real stream.

Under current repo posture, this story must not assume SSE.

If the boundary only supports status/event retrieval over REST, tail must use that honestly.

5.5 Resume
keyhole runs resume <request-id|run-id>

This command must:

reconnect the builder to the same governed execution identity,
use known local records and/or server-visible run lookup surfaces,
avoid accidental duplicate execution,
preserve original proof lineage.

Resume is not "run again."

Resume is "reconnect to the same governed execution."

5.6 Mixed fast-path vs accepted/deferred behavior

The client must support both:

immediate terminal responses
accepted/deferred responses

without forcing users to learn two unrelated runtime models.

The surrounding UX must remain coherent.

6. Runtime Outcome Model

This story must support, at minimum, these outcome families.

6.1 Inline terminal result
submit run
-> boundary returns terminal result inline

The client must:

render terminal state clearly,
preserve proof,
expose run/correlation metadata if present,
avoid forcing the user into wait/resume flows unnecessarily.
6.2 Accepted or deferred result
submit run
-> boundary returns accepted/deferred + run identity
-> client may later status / wait / tail / resume
-> terminal result is resolved later

The client must:

record the run identity,
preserve proof continuity,
suggest next-step commands,
avoid blocking indefinitely unless the user explicitly chose wait behavior.
6.3 Client obligation

The builder experience should remain conceptually unified:

I started a run.
I can inspect it.
I can wait for it.
I can resume it.
I can prove what happened.
7. Preconditions

Before using async run observation surfaces, the client must verify:

the user is authenticated,
the requested run identity is present and well-formed,
local proof output can be updated safely,
status / wait / tail / resume are not operating on impossible IDs or conflicting options,
the client has enough local or remote identity to reconnect without ambiguity.

If those conditions fail obviously, the client must fail locally and clearly.

Examples:

malformed run_id,
missing run_id and no recoverable request_id,
incompatible flags,
invalid local run record shape.
8. Local Run Record Contract

The client should maintain a minimal local run record to support continuity.

A reasonable local record includes:

{
  "request_id": "...",
  "run_id": "...",
  "command": "keyhole run",
  "mode": "shadow|regular",
  "ctxpack_digest": "...",
  "submitted_at": "...",
  "last_known_status": "accepted",
  "proof_path": "...",
  "repo_name": "...",
  "repo_path": "..."
}

This local run record is not the source of truth.

It exists to support:

resume,
wait,
tail,
proof continuity,
clean UX after interruption.

A suitable storage location is local state under .keyhole/state/, not a new competing root.

9. Accepted / Deferred Response Handling

When the boundary returns a non-terminal accepted/deferred response, the client must:

capture run_id,
preserve request and context linkage,
write or update the local run record,
emit proof showing non-terminal accepted/deferred state,
present next-step commands,
avoid blocking unless explicitly asked.
Example terminal UX
✔ Run accepted
run_id: run_abc123
mode: shadow
context: ctx_456def
next:
  keyhole runs status run_abc123
  keyhole runs wait run_abc123
  keyhole runs tail run_abc123

The client must not say "completed" when the boundary only said "accepted."

10. Status UX Contract

keyhole runs status <run-id> must render at minimum:

run ID
current status
last update time where available
mode (shadow / regular) if known
repo identity if known
bound context digest if known
terminal summary if complete
next-step hint if still non-terminal

It must never imply finality when the run remains active or unresolved.

11. Wait UX Contract

keyhole runs wait <run-id> is a client convenience command.

It must:

continue observation until terminal state or explicit client interruption,
surface intermediate progress only when the boundary actually provides it,
end cleanly on success / failure / denial / cancellation / terminal defer,
update the same proof lineage instead of forking a new one.

Important rule:

Waiting does not change the run.

It only observes it.

12. Tail UX Contract

keyhole runs tail <run-id> must use the best available observation method supported by the boundary.

Under current posture, acceptable methods include:

repeated status retrieval,
repeated event-query retrieval,
bounded REST-based follow patterns supported by the paired server contract.

Rules:

the client must render chronology clearly,
the client must label the observation method honestly,
the client must not present polling snapshots as a true stream,
missing follow support must degrade cleanly instead of masquerading as client failure.
13. Resume UX Contract

keyhole runs resume <request-id|run-id> exists for interrupted workflows.

It must:

locate the correct governed run identity using local records and/or boundary lookup,
reconnect the builder to current state,
preserve existing proof lineage,
avoid accidentally starting a new run.

If ambiguity exists, the client must surface it clearly and propose repair steps rather than guessing.

14. Mixed Fast-Path vs Accepted/Deferred UX

The client must make these feel like one governed runtime system.

Fast-path example
✔ Run completed
Accepted/deferred example
✔ Run accepted

The wording must be different because the states are different.

But the surrounding UX should still feel unified:

both preserve proof,
both preserve context linkage,
both preserve request identity,
both can later be inspected,
both use run-oriented terminology.
15. Proof Contract

Every governed run under this story must preserve proof continuity across the full lifecycle.

This story must build on the canonical proof structure established earlier:

proof_bundle/core/
proof_bundle/extended/

It must not invent a parallel proof root outside that structure.

Recommended proof layout
proof_bundle/
  core/
    runs/
      <run-id-or-request-id>/
        request.json
        accepted.json
        latest-status.json
        outcome.json
        correlation.json
        summary.md
  extended/
    runs/
      <run-id-or-request-id>/
        events.json
        render.log
        debug.json
Required semantics
accepted/deferred runs produce proof immediately,
later status / wait / tail / resume operations extend the same lineage,
terminal resolution does not fork into a disconnected artifact tree,
request_id, run_id, mode, and ctxpack_digest remain linked,
missing terminal outcome due to observation interruption is represented honestly.
16. Event and Traceability Expectations

This story assumes the paired server story provides attributable run observation surfaces.

The client must preserve enough local state to relate:

request
run
context
execution mode
status observations
tail/follow observations
terminal outcome
proof path

This is necessary so later explainability and support tooling can reconstruct the lifecycle without ambiguity.

17. Failure Handling and Repair Guidance

The client must distinguish at least these failure classes:

17.1 Submission outcome is non-terminal

The run exists, but is not complete.

This is not failure.
It must be rendered as accepted/deferred state with next-step guidance.

17.2 Observation failure

The run may exist, but status/tail retrieval failed.

The client must avoid implying that execution itself failed.

17.3 Terminal failure

The run completed with governed failure, denial, or other terminal non-success result.

17.4 Resume ambiguity

The client cannot determine which run to reconnect to confidently.

17.5 Protocol failure

The boundary returned an invalid accepted/deferred envelope, such as missing run_id.

Each class must provide concrete next-best actions.

Examples:

retry status lookup
use keyhole runs resume <request-id>
inspect the local proof artifact
wait again
tail again
rerun only if the original request was not accepted
use richer explain/support surfaces once those stories land
18. Local Test Strategy
18.1 Client-only tests

Must cover:

accepted/deferred response parsed correctly
inline terminal response parsed correctly
local run record written deterministically
status renders active and terminal states clearly
wait polls until terminal state
tail reports its observation mode honestly
resume reconnects to existing run identity rather than creating a new one
proof artifacts update across lifecycle stages
context linkage remains preserved across all stages
centralized transport and proof paths are used consistently
18.2 Boundary / zipper tests

Must prove:

long-running run returns accepted/deferred + durable run_id
client tracks and resolves terminal state safely
no transport ambiguity remains under accepted/deferred execution
proof bundles link request -> run -> context -> outcome
18.3 Negative tests

Must cover:

malformed run_id rejected locally
accepted/deferred response missing run_id treated as protocol error
resume without matching identity fails clearly
interrupted wait can be resumed without losing continuity
tail does not pretend polling is streaming
19. Acceptance Criteria

This story is complete only when all of the following are true:

the client recognizes and handles accepted/deferred run responses
keyhole runs status <run-id> works against the paired server contract
keyhole runs wait <run-id> resolves terminal state safely
keyhole runs tail <run-id> follows the best available observation surface and degrades honestly
keyhole runs resume <request-id|run-id> reconnects to prior execution instead of duplicating it
mixed inline-terminal and accepted/deferred behavior is handled coherently
local proof lineage spans request -> run -> context -> outcome
no transport ambiguity remains when the boundary accepts or defers async execution
repair guidance exists for observation and resume failures
zipper proof demonstrates durable async run handling end-to-end
20. Zipper Expectations Against sdk-server-17.md

The paired server story must provide:

accepted/deferred run response contract with run_id
durable run status retrieval
stable terminal outcome retrieval
correlation continuity
observation surfaces sufficient for status / wait / tail / resume behavior

SDK-CLIENT-17 closes only when paired proof demonstrates:

long-running run returns accepted/deferred + run_id
client tracks and resolves terminal outcome safely
run/context/request linkage remains intact
proof bundles link request -> run -> context -> outcome
no transport ambiguity remains
21. Forward-Compatibility Notes

This story must be implemented so later stories can extend it without breaking public UX.

Later stories may add or tighten:

richer explainability
support bundles
budget and overload visibility
improved observation surfaces
stronger admission/execution state semantics

SDK-CLIENT-17 must therefore avoid assumptions such as:

every accepted run has a true live stream,
resume is purely local,
observation loss means execution loss,
inline and accepted/deferred outcomes can share identical wording,
proof can omit context linkage.
22. Non-Goals

SDK-CLIENT-17 does not:

redefine idempotency policy
redefine context compilation
expose direct canonical memory access
force SSE support
provide final explainability UI
replace canonical proof structure

It defines the client-side accepted/deferred run lifecycle UX.

23. Story Closure Statement

SDK-CLIENT-17 is the story that teaches builders how governed execution behaves when it does not finish immediately.

When this story closes, a builder must be able to:

start a governed run
receive a durable run identity
inspect it
wait for it
tail it honestly
resume it after interruption
and preserve proof continuity the entire time

That is the minimum accepted/deferred runtime UX required for real external participation.


Main fixes: REST-first observation instead of SSE assumptions, proof layout aligned with the scaffold, explicit inheritance from 15 and 16, and cleaner distinction between non-terminal accepted/deferred state vs actual failure. :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9} :contentReference[oaicite:10]{index=10} :contentReference[oaicite:11]{index=11}