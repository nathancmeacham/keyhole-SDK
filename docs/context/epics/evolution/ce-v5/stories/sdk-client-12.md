# SDK-CLIENT-12 - Event Classification and Retention Routing

**Status:** DRAFT  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (design + validation), Prod (governed promotion only; no uncontrolled canonical mutation)  
**Surface:** Client  
**Zipper Pair:** `sdk-server-12.md`  
**Purpose:** Define the client-side event classification contract for SDK-originated events, including required metadata, retention hints, envelope shaping, deterministic fallback behavior, local validation, and proof expectations against server-side routing and envelope enforcement.

---

## 1. Story Purpose

SDK-CLIENT-12 defines how the SDK labels and emits **SDK-originated events** so they can be routed lawfully, retained appropriately, and audited consistently by the Event Spine.

This story must make the following true:

- SDK-originated events carry classification metadata intentionally
- event classes are shaped consistently before they reach the boundary
- retention hints are explicit rather than implied
- event envelopes are locally validated before submission where possible
- missing or malformed classification data is handled deterministically
- server-side routing and enforcement expectations are clear and testable
- event proof can reconstruct what the client claimed and what the server accepted, defaulted, or rejected

This story is not about giving the client unilateral control over Event Spine truth.

The client may declare classification intent. The server remains the final enforcement authority.

---

## 2. Why This Story Exists

Without event classification discipline, SDK-originated events become noisy, ambiguous, and expensive to govern.

The client is the first place where an SDK action can say what kind of event it believes it is producing:

- onboarding / identity event
- repo registration event
- run lifecycle event
- ingestion observation event
- alignment guidance event
- proof / validation event
- debug / noise telemetry

If that classification is absent, inconsistent, or ad hoc, then the server must guess too much or silently accept malformed envelopes.

This story exists to ensure the client participates in event governance by providing:

- stable classification metadata
- explicit retention hints
- event envelope completeness
- deterministic defaults or local rejection where appropriate
- inspectable local proof of what was emitted

SDK-CLIENT-12 therefore turns event emission from "just send JSON" into a governed part of the builder boundary.

---

## 3. Story Goals

The client must provide:

- emission of classification metadata on SDK-originated events
- stable local event envelope construction
- deterministic classification vocabulary
- explicit retention hints and importance markers
- local validation of required event envelope fields
- deterministic client behavior when classification is missing or malformed
- proof artifacts showing emitted event intent
- zipper expectations against `sdk-server-12.md`

This story does **not** assume the client becomes the final authority on routing or acceptance.

The server still decides:

- final stream routing
- retention enforcement
- size/rate limits
- required envelope constraints
- defaulting or rejection behavior

---

## 4. Scope

### Included

- local event envelope schema for SDK-originated events
- event class declaration by the client
- retention hint declaration by the client
- importance / severity declaration where applicable
- local validation rules for event metadata
- deterministic local defaults where explicitly allowed
- local proof artifacts for emitted event envelopes
- zipper test expectations against server routing / validation behavior

### Excluded

- Event Spine topology design
- server-side routing internals
- long-term event storage implementation
- server-only event generation not initiated by the SDK
- trust-center packaging of event streams
- generalized analytics/event BI design

---

## 5. Client Responsibilities

The client is responsible for:

1. constructing event envelopes for SDK-originated events
2. attaching classification metadata before emission
3. attaching retention hints before emission
4. attaching correlation and identity context already known locally
5. validating event envelopes locally where possible
6. refusing or warning on obviously malformed event emission attempts
7. capturing emitted envelope data in proof artifacts

The client is **not** responsible for:

- final retention enforcement
- final stream routing
- acceptance of out-of-policy events
- Event Spine persistence correctness
- server-side defaulting policy beyond declared contract expectations

---

## 6. Event Classes in Scope

At minimum, the client must support a deterministic vocabulary for the following SDK-originated event classes.

### 6.1 Governance / Critical

Examples:

- registration submitted
- registration accepted
- validation failed
- run accepted
- run rejected
- proof emitted

These are high-value, replay-relevant events.

### 6.2 Operational

Examples:

- repo ingestion submitted
- graph created
- capability query executed
- alignment guidance produced
- context compiled / referenced

These are medium-value workflow events.

### 6.3 Noise / Debug

Examples:

- local progress updates
- transient polling or diagnostics
- verbose instrumentation not required for replay truth

These should be easy to suppress, down-classify, or reject under policy.

### 6.4 Principle

The event class must reflect **governance importance**, not merely developer convenience.

---

## 7. Event Envelope Contract

The client must shape event envelopes consistently.

### 7.1 Minimum required fields

Each SDK-originated event envelope must include, at minimum:

```json
{
  "event_name": "...",
  "event_class": "...",
  "importance": "...",
  "retention_hint": "...",
  "correlation_id": "...",
  "timestamp": "...",
  "origin": "sdk_client",
  "purpose": "...",
  "tenant_id": "...",
  "org_id": "...",
  "user_id": "...",
  "cohort_id": "...",
  "worker_id": "...",
  "repo_id": "...",
  "workspace_id": "...",
  "payload": { }
}
```

### 7.2 Required identity context

The event envelope must carry deterministic identity context whenever that information is available locally from prior auth / repo binding.

### 7.3 Correlation requirement

Every emitted event must carry a `correlation_id` so the event chain can be tied back to:

- command execution
- run lifecycle
- proof bundle
- boundary response

### 7.4 Payload discipline

The client must not place arbitrary unbounded blobs into `payload` by default.

Large auxiliary details belong in proof artifacts, not blindly in the event body.

---

## 8. Retention Hint Contract

The client must attach a retention hint to each SDK-originated event.

### 8.1 Purpose

The retention hint communicates what the client believes the server should treat the event as:

- long-lived / replay-relevant
- medium-lived / operational
- short-lived / noise

### 8.2 Examples

Acceptable shapes may include values such as:

- `critical`
- `operational`
- `noise`
- or an equivalent canonical vocabulary agreed with the server zipper pair

### 8.3 Important rule

Retention hints are **advisory declarations**, not final authority.

The server may:

- accept them
- normalize them
- default them
- reject them

But the client must still send them intentionally.

---

## 9. Deterministic Local Validation

Before sending an event envelope, the client must validate:

- required fields present
- event class known
- importance value known
- retention hint known
- correlation_id present
- payload type valid
- event size within local preflight expectations where measurable

### 9.1 Missing required classification fields

If classification metadata is required and absent, the client must behave deterministically.

Allowed client behaviors:

- block emission locally with repair guidance, or
- apply an explicit documented local default **only if** the contract allows it

The client must not silently improvise arbitrary values.

### 9.2 Malformed values

If the user or local code supplies malformed event classification values, the client must reject locally where possible.

---

## 10. Defaulting Rules

Where the zipper contract permits defaulting, the client may provide deterministic defaults for selected event classes.

### 10.1 Example default posture

- command-level operational events -> default to `operational`
- replay-critical success/failure events -> default to `critical`
- verbose local instrumentation -> default to `noise`

### 10.2 Constraint

Defaults must be:

- documented
- deterministic
- testable
- consistent across runs

### 10.3 Forbidden behavior

The client must never silently downgrade a critical event to noise for convenience.

---

## 11. Event Emission Surfaces in Scope

This story covers SDK-originated events from flows such as:

- repo registration
- governed runtime execution
- repository ingestion
- capability discovery queries where evented
- validation outcomes where evented
- proof emission summaries where evented
- alignment guidance summaries where evented

This story does not require every local-only action to emit an event.

It only requires that when the SDK does emit an event toward the platform, it does so lawfully.

---

## 12. Local Proof Contract

The client must preserve enough local proof to explain what event envelope it attempted to emit.

### 12.1 Minimum proof outputs

Recommended minimum artifact set:

```text
proof_bundle/
  events/
    emitted_event.json
    event_summary.md
    correlation.json
```

If the client already uses a broader proof bundle structure, it may integrate into that structure instead.

### 12.2 Required semantics

The proof must allow later inspection of:

- event name
- event class
- importance
- retention hint
- correlation_id
- identity context used
- payload summary
- server accept/default/reject outcome if available

### 12.3 Success and failure

Both accepted and rejected event emission attempts must remain inspectable.

---

## 13. UX Requirements

The client must make event classification behavior understandable enough for builders without making them micromanage every envelope.

### 13.1 Normal builder UX

In normal flows, classification should be automatic and quiet.

### 13.2 Failure UX

If event emission fails because of classification or envelope errors, the client must show:

- what field was missing or invalid
- whether the problem is local or server-side
- what value is expected
- next-best repair step

### 13.3 Inspection UX

If the client exposes inspection commands later, event classification should be visible there.

---

## 14. Test Strategy

SDK-CLIENT-12 must support the following tests.

### 14.1 Local client tests

- valid event envelope generation
- deterministic class assignment
- deterministic retention hint assignment
- missing classification field rejection
- malformed field rejection
- local defaulting where allowed
- proof artifact emission for sent event
- proof artifact emission for rejected event

### 14.2 Zipper / boundary tests

- events land in correct streams
- missing classification fields rejected or defaulted deterministically
- rate/size validation works

### 14.3 Negative tests

- oversized event blocked or surfaced correctly
- unknown class rejected locally or server-side deterministically
- noise event does not masquerade as critical
- correlation_id not omitted accidentally

---

## 15. Acceptance Criteria

This story is complete only when all of the following are true:

1. the client emits classification metadata on SDK-originated events
2. the client emits retention hints on SDK-originated events
3. local envelope validation catches obviously malformed classification data
4. missing classification fields are rejected or defaulted deterministically
5. correlation_id is present on emitted SDK-originated events
6. identity context is attached where available
7. local proof artifacts preserve emitted envelope metadata
8. server zipper proof shows events land in correct streams
9. server zipper proof shows missing fields are rejected or defaulted deterministically
10. server zipper proof shows rate/size validation works

---

## 16. Zipper Expectations Against `sdk-server-12.md`

The paired server story must provide:

- routing by event class / retention policy
- envelope validation enforcement
- deterministic rejection or defaulting semantics
- rate and size enforcement
- attributable acceptance behavior

SDK-CLIENT-12 closes only when the paired server proof demonstrates:

- events land in correct streams
- missing classification fields are rejected or defaulted deterministically
- rate/size validation works

---

## 17. Forward-Compatibility Notes

This story must be implemented in a way that does **not** block later hardening around:

- stronger event rate controls
- event signing or trust metadata linkage
- support bundle explainability
- replay-critical event selection rules
- run-scoped and context-scoped event inspection surfaces

Therefore the client must avoid assumptions such as:

- every event is equally important
- retention is purely client-defined
- missing metadata can always be guessed safely
- debug instrumentation deserves canonical treatment

---

## 18. Non-Goals

SDK-CLIENT-12 does **not**:

- define server stream topology in full
- guarantee event acceptance on its own
- provide the final analytics model
- expose low-level Event Spine internals directly to builders
- replace proof bundles as the primary replay artifact

---

## 19. Story Closure Statement

SDK-CLIENT-12 ensures that SDK-originated events are not casual telemetry.

They become governed declarations with:

- explicit class
- explicit retention intent
- explicit correlation
- explicit proof of what the client sent

When this story closes, the SDK can participate in the Event Spine lawfully rather than noisily.
