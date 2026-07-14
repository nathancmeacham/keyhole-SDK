# sdk-client-15.md

# SDK-CLIENT-15 - Idempotent Transport, Retry, and Request Identity (Client)

**Story ID:** SDK-CLIENT-15 / sdk-client-15  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only)  
**Surface:** Keyhole SDK / CLI / MCP REST Boundary Transport Layer  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-15.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-server-15.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** `sdk-client-16.md`, broad write-bearing client expansion  
**Applies To:** Python SDK, CLI commands, onboarding flows, auth bootstrap, governed run dispatch, repo registration flows, ingestion flows, proof builders, support / inspection tooling  
**Last Updated:** 2026-04-13

---

## 1. Purpose

This story defines the canonical **client-side transport discipline** for request identity, idempotency, retry behavior, and replay-aware proof continuity across the Keyhole SDK and CLI.

Its purpose is to make public client behavior safe and predictable when builders encounter real-world failures such as:

- network interruption,
- lost responses,
- transient upstream errors,
- rate limits,
- deferred execution,
- repeated CLI submission,
- agent retry loops,
- process restart during an in-flight write,
- ambiguous "did it execute?" outcomes.

The SDK must not behave like a thin convenience wrapper that forwards requests blindly and leaves duplicate safety to luck.

Instead, the SDK and CLI must:

- assign identity to each transport request,
- assign stable idempotency identity to each logical write attempt that requires it,
- preserve that identity across retries of the same attempt,
- clearly distinguish replay from fresh execution,
- normalize retry / defer / conflict behavior,
- capture proof-relevant metadata,
- make the safe path the default path.

This story turns idempotency from a server-side strength the client happens to benefit from into a **client-side discipline the platform can depend on**.

---

## 2. Why This Story Exists

SDK-CLIENT-00, SDK-CLIENT-01, and SDK-CLIENT-02 proved that the public builder surface is real:

- onboarding exists,
- authentication exists,
- identity inspection exists,
- local governed scaffolding exists,
- the CLI is now a real product surface.

That changes the next failure mode.

The question is no longer:

> can the client reach the boundary?

The question is now:

> can the client behave lawfully when the network lies, retries happen, and builders begin using write-bearing flows at scale?

Without this story, the SDK will eventually fail in familiar ways:

- a successful write looks failed because the response was lost,
- a retry becomes a duplicate execution because a new key was minted,
- a second intentional action is accidentally collapsed into a replay,
- proof cannot explain whether the server executed, replayed, deferred, or never received the request,
- new commands inherit ad hoc retry behavior route by route,
- the Event Spine receives unnecessary duplicate pressure from careless public clients.

This story exists to prevent those failure classes before write-bearing SDK surfaces expand further.

---

## 3. Story Role in the Client Stream

This story is the transport-safety gate between early access flows and broad write-bearing externalization.

### Layering

```text
sdk-client-00 / sdk-client-01 / sdk-client-02
  -> identity, auth bootstrap, local governed scaffold

SDK-CLIENT-15
  -> request identity, operation-attempt identity, retry discipline,
    replay handling, proof continuity, transport safety

SDK-CLIENT-16+
  -> governed context binding, async run tracking, memory boundary,
    explainability, budget visibility, broader execution UX

The purpose of this story is not to move replay authority into the client.

The server remains authoritative.

The purpose of this story is to ensure that the client:

speaks the duplicate-protection protocol correctly,
does not sabotage server guarantees through careless resend behavior,
makes safe retries automatic,
emits enough metadata for support and proof continuity,
creates a stable transport foundation for all later write-bearing stories.
4. Core Thesis

Keyhole client surfaces must treat:

request identity as first-class,
retry as normal,
blind duplication as forbidden.

For operations that require idempotent write protection:

one logical operation attempt gets one idempotency identity,
retries of that same attempt reuse that same identity,
intentionally distinct actions mint distinct identities even if payloads match,
proof preserves the difference between:
executed,
replayed,
deferred,
conflicted,
transport-unknown,
not-sent.

The client is responsible for preserving the operation-attempt boundary.

The server is responsible for deciding whether that attempt executes, replays, conflicts, or remains in progress.

5. What This Story Is

This story implements:

a REST transport identity contract for X-Request-Id,
a classified idempotency contract for X-Idempotency-Key,
bounded retry behavior with backoff and Retry-After support,
replay-aware proof and support metadata,
a central operation-class discipline for SDK and CLI methods,
a safe default path for builders and agents.
What This Story Is Not

This story is not:

a replacement for server-side duplicate protection,
permission for the client to decide replay outcomes,
a claim that every command or every POST requires idempotency,
a universal retry policy for every failure,
a context lifecycle story,
a memory contract,
a control-plane decision engine,
a guarantee of exactly-once delivery.
6. Constitutional Anchors

This story must preserve the following truths:

The MCP boundary is the only approved public participation surface. Transport discipline must be expressed through the boundary, not around it.
Event Spine is canonical truth. The client must not invent duplicate-protection truth from local assumptions.
Builders declare; the platform decides. The client carries request and operation identity; the server decides execution outcome.
The SDK is not the control plane. The client may validate, classify, and retry, but it must not simulate final governance outcomes.
A zipper is not closed until it emits replay-aware proof. Client proof artifacts must capture transport and replay metadata.
Failure must produce repair guidance. Conflict, defer, missing-key, and transport-unknown states must all guide the builder safely.
Progressive disclosure is mandatory. Builders should benefit from safe retry behavior without needing to understand the full wire protocol on day one.
7. Current State and Motivation
7.1 What Already Exists and Is Strong

Several client flows are already relatively safe:

unauthenticated discovery is read-only,
whoami is read-only,
registration is partially protected by server-side natural-key rules,
login already avoids unnecessary work in common cases,
verification flows are naturally convergent in many cases.
7.2 What Is Not Yet Strong Enough

The current client transport posture still has major gaps:

X-Request-Id is not yet uniformly enforced across all requests,
write-bearing operations do not yet uniformly classify and apply idempotency,
retry behavior exists conceptually but is not yet the canonical transport discipline,
proof does not yet consistently preserve replay-aware transport metadata,
future write-bearing commands would currently inherit inconsistent patterns.

This story closes that gap.

8. Design Principles
8.1 Request Identity and Operation Identity Are Different

The client must distinguish:

X-Request-Id - identity for a single HTTP request,
X-Idempotency-Key - identity for one logical write attempt that may span multiple request retries.

These are not interchangeable.

8.2 Idempotency Is Classified, Not Blanket

Not every operation needs an idempotency key.

Idempotency requirements must be driven by explicit operation classes, not by ad hoc instinct and not by "every POST gets a key" as an unexamined rule.

8.3 Same Attempt, Same Key

Retries of the same logical write attempt must reuse the same idempotency key.

8.4 Different Attempt, Different Key

Intentionally distinct operations must mint a fresh idempotency key even if payloads are identical.

8.5 Payload Equality Is Not Attempt Identity

The client must not use payload hashing as the idempotency key itself.

Payloads may be identical across legitimate distinct actions. Collapsing them would destroy intentional repeated action.

8.6 Safe Behavior Must Be Automatic

Builders should not need to manually mint UUIDs or reason through retry semantics on every command.

8.7 The Client Must Preserve Ambiguity Honestly

A transport failure after send is not proof of non-execution.

The SDK must preserve that ambiguity and handle it safely.

9. Operation Classes

All public SDK and CLI operations must belong to one of these classes.

9.1 READ_ONLY

Examples:

capabilities
whoami
registration_status
read-only query/list/search surfaces

Behavior:

X-Request-Id required
X-Idempotency-Key omitted
retry allowed according to safe read policy
9.2 WRITE_IDEMPOTENT_REQUIRED

Examples:

register
write-bearing run.start
future repo registration
future contract submission
future capability publication
future ingestion submission
future mutation-bearing execution submission

Behavior:

X-Request-Id required
X-Idempotency-Key required
retries of the same attempt must reuse the same idempotency key
9.3 NATURALLY_CONVERGENT_EXEMPT

Examples:

specific domain flows where the server contract explicitly declares that duplicate safety is guaranteed by route/domain semantics

Behavior:

X-Request-Id required
X-Idempotency-Key recommended when feasible
omission is allowed only when the exemption is explicit in the server contract
the client must not infer exemption from verb or route shape alone
9.4 INTERNAL_ONLY_NOT_EXPOSED

Not for public SDK use.

The SDK must not expose operations that depend on hidden duplicate-protection assumptions.

10. Required Headers
10.1 X-Request-Id

Every SDK request must carry a request identifier.

Purpose:

supportability,
tracing,
correlation,
proof continuity,
inspection after ambiguous failures.

Properties:

unique per HTTP request,
generated client-side by default,
opaque except for correlation.
10.2 X-Idempotency-Key

Every public operation classified as WRITE_IDEMPOTENT_REQUIRED must carry an idempotency key.

Purpose:

same-attempt replay safety,
duplicate protection,
lawful retry after ambiguous transport failure.

Properties:

unique per logical write attempt,
stable across retries of that attempt,
not reused for intentionally different actions,
not derived solely from payload equality.
10.3 Optional Supporting Headers

Where useful and safe, the client may also emit:

X-Keyhole-Command
X-Keyhole-Attempt
X-Keyhole-SDK-Version
X-Keyhole-Repo-Id
X-Keyhole-Shadow-Mode

These are supplemental only.

11. Key Generation Rules
11.1 Request IDs

Generate a fresh request ID for every transport request.

Recommended format:

UUIDv4 or equivalent opaque collision-resistant identifier.
11.2 Idempotency Keys

Generate a fresh idempotency key at the start of a write attempt classified as WRITE_IDEMPOTENT_REQUIRED.

Recommended format:

UUIDv4 or equivalent opaque collision-resistant identifier.
11.3 Reuse Rules

The client may reuse an idempotency key only when:

retrying the same logical attempt,
resending after an unknown outcome,
obeying retry / backoff / defer logic for that same attempt,
continuing a preserved pending attempt.
11.4 New-Key Rules

The client must mint a new key when:

the user intentionally starts a distinct action,
parameters change materially after validation failure or conflict,
the previous attempt is known complete and a second real action is desired,
support or tooling explicitly instructs a fresh attempt.
12. Retry Rules
12.1 Retry Is Not Blind Resend

The client must distinguish:

safe automatic retry,
safe but user-visible retry,
unsafe retry that requires a new attempt or human review.
12.2 Safe Automatic Retry Conditions

Automatic retry may occur for the same logical attempt when:

connection failed before response was received,
upstream or gateway timeout occurred,
transient network/TLS interruption occurred,
the server returned retryable defer semantics,
the server returned rate-limit with Retry-After.

Automatic retry must preserve the same idempotency key.

12.3 Unsafe Automatic Retry Conditions

Automatic retry must not occur blindly when:

deterministic validation failed,
authorization requires user action,
server returned idempotency conflict,
the caller materially changed intent,
the operation is known permanently failed.
12.4 Retry Budget

The client must implement bounded retry behavior.

No unbounded loops.
No silent churn storms.
No infinite agent resend behavior.

12.5 Backoff

Retry behavior must use bounded exponential backoff with jitter.

12.6 Retry-After

When the server provides Retry-After, the client must respect it or surface it explicitly.

13. Unknown-Outcome Handling

One of the most important states in public SDK behavior is:

"I do not know whether the server executed this."

Examples:

request sent, then connection dropped,
timeout while waiting for response,
process interruption after transmission,
ambiguous upstream failure after body send.

In this state, the client must:

preserve the same idempotency key,
preserve request metadata where feasible,
avoid minting a fresh key for the same attempt,
retry safely only under the same attempt identity,
surface the ambiguity honestly if final state remains unresolved.

Transport ambiguity is where idempotency matters most.

14. Command-Level Requirements
14.1 keyhole register

Treat as WRITE_IDEMPOTENT_REQUIRED.

Requirements:

mint idempotency key at submit start,
preserve it across safe retry,
treat replayed success as success,
record replay metadata in proof when returned.
14.2 keyhole verify

May begin as NATURALLY_CONVERGENT_EXEMPT only if the server contract explicitly says so.

The client must still be structured so explicit idempotency can be added without redesign.

14.3 keyhole login

Must always use X-Request-Id.

Where login/session creation becomes a write-bearing public mutation under server contract, it must follow classified idempotency rules without collapsing intentionally distinct sessions.

14.4 keyhole run

Read-only runs may remain READ_ONLY if the boundary contract says so.

Write-bearing runs must be WRITE_IDEMPOTENT_REQUIRED.

The classification must be explicit and not guessed from command name alone.

14.5 keyhole ingest

Submission-style ingestion starts must be treated as WRITE_IDEMPOTENT_REQUIRED when they initiate write-bearing server work.

14.6 Future Commands

Future commands such as:

repo registration,
contract submission,
capability publication,
mutation-bearing runtime execution,

must declare an operation class and inherit this transport discipline by default.

15. Client API Surface Requirements
15.1 Base Transport Client

The base transport layer must own:

request-id injection,
idempotency-key injection for classified operations,
retry logic,
backoff handling,
Retry-After handling,
replay/defer/conflict normalization,
support metadata capture.
15.2 Higher-Level Clients

Higher-level clients must declare operation class rather than implementing retry/idempotency ad hoc.

15.3 Central Operation Registry

The SDK must maintain a central registry mapping public methods/routes to:

operation class,
idempotency requirement,
retry policy,
proof requirements.

This prevents route-by-route drift.

15.4 Suggested Internal Shape

A reasonable implementation shape is:

keyhole_sdk/transport/
  client.py
  retry.py
  idempotency.py
  operation_registry.py
  errors.py

The exact layout may vary, but the discipline must be centralized.

16. Proof Requirements

Client-side proof artifacts for write-bearing operations must include replay-relevant transport metadata.

16.1 Minimum Fields
request_id
idempotency_key where applicable
operation_class
command_name
attempt_count
final_client_observation
server_request_id if returned
original_request_id if replay metadata is returned
per-attempt timestamps
retry reason(s)
16.2 Allowed Final Client Observations

At minimum:

executed
replayed
deferred
conflict
transport_unknown
not_sent
16.3 Proof Continuity Rule

If the server returns replay metadata, the proof core must not present the result as a fresh mutation.

16.4 Hot vs Extended Evidence

Replay-critical metadata belongs in the proof hot core.

Verbose transport logs may live in extended evidence.

17. Error and Outcome Handling
17.1 Missing Idempotency Key

If a WRITE_IDEMPOTENT_REQUIRED operation is attempted without an idempotency key, that is a client bug or noncompliant code path.

The SDK must raise a typed error.

17.2 Idempotency Conflict

If the server reports the same idempotency key was reused with materially different semantics, the client must:

stop automatic retry,
preserve proof metadata,
surface deterministic repair guidance,
instruct the caller to mint a new attempt when appropriate.
17.3 Replay-In-Progress / Retry Later

If the server indicates in-progress or deferred semantics, the client must:

preserve the same key,
retry later only under the same attempt identity,
surface defer state clearly.
17.4 Rate Limit / Overload

If the server rate-limits or defers due to overload, the client must:

keep the same idempotency key,
obey backoff and Retry-After,
avoid churn storms.
17.5 Transport Failure

Transport failure after send is not proof of non-execution.

The SDK must say so explicitly.

18. CLI UX Principles

The CLI should make duplicate safety feel automatic, not burdensome.

18.1 Default UX

The CLI should:

inject transport identity automatically,
retry safely where allowed,
tell the user what happened,
avoid exposing raw protocol detail unless necessary.
18.2 Honest UX

When final execution state is unknown, the CLI must say so clearly.

18.3 Repair UX

Failure output should include:

reason class,
whether same-attempt retry is safe,
whether a fresh attempt is required,
request/proof references where helpful.
18.4 Future Inspection UX

Future inspection commands may expose request and replay behavior, for example:

keyhole inspect <request-id>
keyhole proof <operation-id>
keyhole doctor

This story should preserve the metadata those later surfaces will need.

19. Local State and Persistence
19.1 Minimum Requirement

The client must preserve attempt identity for the lifetime of the active retry flow.

19.2 Optional Extended Persistence

Selected commands may persist pending operation metadata long enough to support:

crash recovery,
replay continuation,
support inspection.
19.3 Forbidden Behavior

The client must not silently persist and later reuse old idempotency keys across unrelated actions.

Persistence must preserve attempt continuity, not create hidden coupling across future user intent.

20. Config Surface

The SDK config surface should explicitly support safe transport behavior.

Recommended fields:

request_id_enabled: true
idempotency_enabled: true
retry_enabled: true
max_retries: 3
retry_backoff_base_ms: 250
retry_backoff_max_ms: 5000
respect_retry_after: true
persist_pending_operations: false
Rules
defaults must favor safe public SDK behavior,
advanced users may tune retry behavior,
official write-bearing command paths must not accidentally disable essential duplicate protection without explicit opt-out and warning.
21. Boundary Alignment

The client must align to the live public boundary contract, not invent a parallel one.

21.1 Public Transport

This story is defined for the public MCP REST/HTTP boundary.

21.2 Server Authority

The client must treat server replay/conflict/defer outcomes as authoritative.

21.3 No Tombstoned Transport Assumptions

The client must not design this story around tombstoned transports.

If older text references transport parity with inactive transports, that text must not override current REST/HTTP boundary posture.

22. Implementation Scope
P0 - Required for Story Closure
Inject X-Request-Id on every request.
Inject X-Idempotency-Key on all WRITE_IDEMPOTENT_REQUIRED operations.
Add centralized operation-class declaration and enforcement.
Make registration replay-safe at the client transport layer.
Publish clear contributor-facing protocol guidance.
P1 - Retry and Error Normalization
Implement bounded retry with backoff and jitter.
Respect Retry-After.
Normalize replay / conflict / defer / missing-key conditions into typed SDK errors.
P2 - Proof and Support Hardening
Capture replay metadata in proof cores.
Preserve request/attempt metadata for future inspection tooling.
Add optional crash-recovery continuity where justified.
P3 - Ecosystem Discipline
Enforce operation-class declaration for new public write-bearing methods.
Publish examples showing safe retry behavior for SDK users and agents.
23. Testing Requirements
23.1 Unit Tests

Must cover:

request-id generation,
idempotency-key generation,
same-attempt retry preserves same key,
distinct attempt gets new key,
missing-key bug detection,
conflict handling,
defer handling,
transport-unknown handling.
23.2 Integration / Smoke Tests

Must prove:

same-attempt registration retry replays safely,
write-bearing run retry preserves same key,
server conflict is surfaced correctly,
Retry-After is obeyed,
proof captures replay metadata.
23.3 Negative Tests

Must cover:

accidental new key on retry,
accidental key reuse across distinct attempts,
unbounded retry prevention,
malformed replay/conflict response handling,
operation-class drift for new write-bearing surfaces.
24. Metrics and Observability

Where feasible, the client layer should make these measurable:

retry count by command,
replay success rate,
conflict rate,
transport-unknown incidence,
route coverage drift for operation-class declaration.

These metrics are for support and hardening, not for replacing server truth.

25. Invariants
INV-SDK-CLIENT-REQUEST-ID-ALWAYS

Every SDK request must carry a request identifier.

INV-SDK-CLIENT-WRITE-KEY-REQUIRED

Every public operation classified as WRITE_IDEMPOTENT_REQUIRED must carry an idempotency key.

INV-SDK-CLIENT-SAME-ATTEMPT-SAME-KEY

Retries of the same logical write attempt must reuse the same idempotency key.

INV-SDK-CLIENT-DIFFERENT-ATTEMPT-DIFFERENT-KEY

Intentionally distinct write attempts must use distinct idempotency keys even when payloads are identical.

INV-SDK-CLIENT-PAYLOAD-HASH-NOT-KEY

Payload hashing may not serve as the sole idempotency-key generation rule.

INV-SDK-CLIENT-PROOF-CAPTURES-REPLAY

Replay-relevant metadata must be captured in proof for write-bearing operations.

INV-SDK-CLIENT-NO-BLIND-RETRY-WRITES

Write retries must not occur without stable operation identity.

INV-SDK-CLIENT-ERRORS-REPAIRABLE

Duplicate-protection failures must produce deterministic repair guidance.

26. Non-Goals

This story does not:

replace server duplicate protection,
guarantee exactly-once delivery,
define all future command semantics in full,
make read-only operations carry unnecessary idempotency protocol,
implement governed context binding,
expose direct memory primitives,
simulate control-plane decisions locally,
expose server secret fingerprinting logic.
27. Story Closure Criteria

This story is complete only when:

every public client method has a declared operation class,
every request automatically sends X-Request-Id,
every WRITE_IDEMPOTENT_REQUIRED operation automatically sends X-Idempotency-Key,
retry logic preserves operation-attempt identity,
replay / defer / conflict / missing-key states are normalized into typed SDK outcomes,
proof captures replay-aware transport metadata for write-bearing operations,
new write-bearing client stories inherit this transport discipline by default.
28. Strategic Statement

SDK-CLIENT-00, 01, and 02 proved that builders can onboard, authenticate, and begin from a lawful local workspace.

SDK-CLIENT-15 proves that builders can interact with Keyhole safely once the network becomes imperfect and public write-bearing behavior begins to scale.

It closes the gap between:

"the client can call the platform"

and

"the client can call the platform repeatedly, imperfectly, and still behave lawfully."

That is the minimum transport-safety posture required before broad write-bearing SDK expansion.

29. One-Line Summary

Turn Keyhole idempotency from a server-side protection the client happens to benefit from into a client transport discipline where request identity is universal, idempotency is classified and explicit, retries are safe by default, proof remains replay-aware, and builders never have to guess whether "retry" will duplicate reality.