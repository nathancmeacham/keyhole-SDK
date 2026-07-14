# sdk-client-18.md

# SDK-CLIENT-18 - Memory Boundary Enforcement

**Story ID:** SDK-CLIENT-18 / sdk-client-18  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Public Boundary Contract  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-18.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-09.md`, `sdk-client-15.md`, `sdk-client-16.md`, `sdk-client-17.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** later explainability and governed inspection surfaces that may reference memory-derived outcomes without exposing raw canonical memory  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-18 hardens the public client boundary around memory.

Its purpose is not to make memory more powerful.

Its purpose is to make the SDK **incapable of teaching the wrong architecture**.

This story makes the following true:

- the public SDK does **not** expose direct canonical memory query or write methods,
- the public CLI does **not** expose direct canonical memory query or write commands,
- lawful memory-relevant behavior is reached only through governed context, governed runs, proof, explainability, or other explicitly governed inspection surfaces,
- illegal direct-memory attempts fail early and clearly,
- the developer experience remains usable because lawful alternatives are visible and discoverable.

This story is not anti-memory.

It is anti-bypass.

---

## 2. Why This Story Exists

If the public SDK were to expose shapes like:

```python
client.memory.query(...)
client.memory.write(...)

or CLI commands like:

keyhole memory query
keyhole memory write

the SDK would immediately train builders to think of Keyhole memory as:

a generic vector database,
an application-owned semantic cache,
or a normal direct-read/write developer primitive.

That would be architecturally wrong.

Keyhole memory is not the public builder control plane.
It is not canonical truth.
It is not a free-form application database.
It is a governed, derived layer whose lawful access must remain mediated by:

governed context,
governed runs,
proof lineage,
explainability surfaces,
and server-side policy.

This story exists to ensure the public client boundary itself cannot quietly undo the memory-governance posture enforced elsewhere.

3. Core Thesis

The public SDK must not teach builders this mental model:

my app talks directly to memory

It must teach this mental model instead:

my app participates through governed context and governed runs
and memory is one governed derivative layer inside that system

That distinction is the entire purpose of this story.

4. Scope
Included
public SDK surface design for memory-related behavior
public CLI surface design for memory-related behavior
explicit prohibition of direct canonical memory query/write primitives
lawful context-mediated helper surfaces
lawful run-mediated helper surfaces
lawful proof/explain/inspection references where available
deterministic rejection behavior for illegal direct-memory attempts
help/docs/example posture that reinforces the governed memory model
zipper expectations against sdk-server-18.md
Excluded
server-side context gating internals
server-side removal of unsafe private/internal surfaces
direct Qdrant hardening
memory schema redesign
budgeting, deduplication, and traceability internals
context compilation semantics themselves
explainability semantics themselves

Those are handled in adjacent server or client stories. This story ensures the public client boundary does not undermine them.

5. Strategic Role

SDK-CLIENT-18 sits after the client already has lawful alternatives available:

sdk-client-09
  -> governed run entrypoint

sdk-client-15
  -> request identity, retry/idempotency safety, replay-aware transport

sdk-client-16
  -> explicit governed context lifecycle and no-floating-run enforcement

sdk-client-17
  -> accepted/deferred run observation and durable run UX

sdk-client-18
  -> no public direct-memory bypass; lawful alternatives only

That matters because this story should not merely say "no."

It must say "no" while preserving a clear lawful path.

6. Allowed Public Client Surfaces

The client may expose helper surfaces that are lawful because they are mediated through context, runs, proof, or explainability.

6.1 Context-mediated helpers

Examples of acceptable public shapes include:

client.context.compile(...)
client.context.inspect(...)
client.context.get(...)

These surfaces let builders work with governed context artifacts, not raw canonical memory.

6.2 Run-mediated helpers

Examples of acceptable public shapes include:

client.run(...)
client.run_with_context(...)

or CLI equivalents:

keyhole run --context <digest>
keyhole run --context auto

These surfaces allow memory-relevant behavior only as part of governed execution.

6.3 Proof / explain / inspection helpers

Where such surfaces exist, the client may expose read helpers for:

proof bundles
support bundles
explainability artifacts
run inspection
context inspection

These are lawful because they are not raw canonical memory primitives.

7. Forbidden Public Client Surfaces

The client must not expose public APIs or commands that imply canonical memory is directly queryable or directly mutable by the builder.

Forbidden SDK examples
client.memory.query(...)
client.memory.search(...)
client.memory.get(...)
client.memory.write(...)
client.memory.upsert(...)
client.memory.delete(...)
Forbidden CLI examples
keyhole memory query
keyhole memory get
keyhole memory write
keyhole memory delete

This story assumes the rule is:

no public direct canonical memory surface.

If a future story introduces tightly governed inspection-only capabilities, they must arrive under a new and narrower contract rather than weakening this one.

8. Helper UX Requirements

The absence of direct memory APIs must not make the SDK confusing.

The client must provide alternate paths that are:

clear,
discoverable,
repair-oriented,
and governance-aligned.
8.1 If a developer wants "memory access"

The client should guide them toward lawful surfaces such as:

keyhole context compile
keyhole context inspect
keyhole run --context <digest>
governed run inspection
proof inspection
explainability surfaces when available
8.2 If a developer attempts illegal direct access

The client must respond with a deterministic, helpful message such as:

Direct canonical memory access is not exposed by the public SDK.
Use governed context, governed runs, or proof/explain surfaces instead.

Suggested next steps:
- keyhole context compile
- keyhole context inspect
- keyhole run --context <digest>
8.3 Message quality rule

The client must always explain what to do instead, not only what is forbidden.

9. Public SDK API Contract
9.1 Public namespace shape

The public SDK should be shaped so that memory is not presented as a top-level builder primitive.

Preferred public shape:

client.auth.*
client.repo.*
client.context.*
client.run.*
client.proof.*
client.explain.*

Not preferred:

client.memory.*
9.2 Internal implementation freedom

Internal plumbing may still refer to memory as an implementation concern where needed, but those internals must not leak into the stable public SDK contract.

9.3 Export discipline

Public exports, autocomplete, docs, and examples must never imply that raw canonical memory access is part of the builder surface.

10. CLI Contract
10.1 No public direct memory commands

The CLI must not ship direct canonical memory commands as public builder commands.

10.2 Lawful alternatives

The CLI should steer builders toward:

keyhole context compile
keyhole context inspect
keyhole run --context <digest>
keyhole runs status <run-id>

and, where available in later stories, to proof or explainability commands.

10.3 Help and completion behavior

Help output, shell completion, examples, and command docs must reinforce the same boundary.

The client must not accidentally "discover" forbidden memory commands through help text or completion plumbing.

11. Deterministic Rejection Contract

Illegal direct-memory attempts must fail:

deterministically,
early,
with repair guidance,
and without ambiguity.
Required error content

A client-side rejection must include:

error class
short reason
boundary explanation
lawful alternatives
at least one concrete next step
Example SDK exception
DirectMemoryAccessNotAllowed
Example CLI output
REJECT - Direct canonical memory access is not exposed by the public SDK.
Why: memory is governed through context, run, proof, and explainability surfaces.
Try:
  keyhole context compile
  keyhole context inspect
  keyhole run --context <digest>
12. Relationship to Context and Runs

This story depends on the client already exposing better alternatives.

12.1 Context lifecycle alignment

SDK-CLIENT-16 provides:

explicit context compile
explicit context inspection
explicit context-bound run invocation

That means SDK-CLIENT-18 does not strand the builder. It redirects them to the correct execution boundary.

12.2 Run lifecycle alignment

SDK-CLIENT-09 and SDK-CLIENT-17 provide:

governed runtime execution
accepted/deferred run handling
durable run observation

That means the client can honestly say:

use the governed run surface
not a direct memory surface
12.3 Proof and explain alignment

Where proof or explain surfaces exist, they are lawful because they expose governed artifacts and outcomes, not raw canonical memory primitives.

13. Transport and Boundary Discipline

Even though this story is mostly about API and command shape, it must still inherit the client transport posture already sealed.

That means:

lawful helper surfaces continue to use the centralized transport layer,
request identity remains intact,
accepted/deferred observation continues to behave honestly,
the client must not create a shadow side-channel to memory outside the standard boundary.

This story is partly closed by absence:

absence of forbidden public exports,
absence of forbidden CLI commands,
absence of hidden bypass routes.

But it is also closed by positive lawful behavior through existing context/run/proof paths.

14. Proof Contract

This story must produce proof that the client boundary itself enforces the memory doctrine.

14.1 Proof placement rule

Because many target repos are foreign or not yet Keyhole-native, memory-boundary enforcement proof must not assume in-repo proof placement by default.

Default proof should live in a tool-owned local state path.

If a repo is already Keyhole-native and the builder explicitly opts in, proof may additionally be mirrored into canonical in-repo proof paths.

14.2 Recommended local proof shape

A reasonable tool-owned structure is:

<tool-owned-state>/
  memory_boundary/
    attempted-surface.json
    rejection.json
    summary.md
14.3 Positive-path proof

The client may also emit positive-path evidence that shows lawful alternatives remain available, such as:

successful context compile invocation
successful context inspection invocation
successful context-bound run invocation
14.4 What proof must demonstrate

The proof must be sufficient to show that:

no public direct canonical memory methods are exposed,
illegal direct attempts fail deterministically,
repair guidance is present,
lawful alternatives exist and are discoverable.
15. Local Test Strategy
15.1 Public SDK API tests

Must verify:

no public client.memory.query exists
no public client.memory.write exists
no public direct canonical memory namespace is exported
autocomplete/export surfaces do not leak a memory namespace
15.2 CLI tests

Must verify:

no keyhole memory query public command exists
no keyhole memory write public command exists
help text and command discovery point users to lawful alternatives
15.3 Negative tests

Must verify:

attempted direct memory helper import fails or is absent
attempted direct memory CLI command fails deterministically
error output includes repair guidance
15.4 Positive-path tests

Must verify:

keyhole context compile remains available
keyhole context inspect remains available
keyhole run --context <digest> remains available
lawful run observation or proof inspection surfaces remain available
15.5 Zipper tests

In the paired server proof, the combined zipper should demonstrate:

illegal direct client memory paths are rejected
the client cannot reach canonical memory outside lawful context/run/proof surfaces
no public SDK memory bypass remains
16. Acceptance Criteria

This story is complete only when all of the following are true:

the public SDK exposes no direct canonical memory query/write surface
the public CLI exposes no direct canonical memory query/write command
lawful alternatives exist through context or governed run surfaces
illegal direct attempts fail deterministically
illegal direct attempts include repair guidance
public help/docs/examples reinforce the governed memory model correctly
no public SDK canonical memory bypass remains
zipper proof shows paired server-side rejection of illegal client memory attempts
the client boundary aligns with memory containment doctrine instead of weakening it
17. Zipper Expectations Against sdk-server-18.md

The paired server story must provide:

context-gated lawful access paths
elimination or rejection of unsafe public direct memory surfaces
deterministic rejection of illegal client memory attempts

SDK-CLIENT-18 closes only when paired proof demonstrates:

the client cannot query canonical memory outside lawful context/run/proof paths
illegal direct-memory attempts fail deterministically
no public SDK canonical memory bypass remains
18. Forward-Compatibility Notes

This story does not forbid future richer governed memory inspection tooling.

It does require that any future tooling:

remain context-bound, run-bound, or governed-inspection-bound,
avoid presenting canonical memory as a generic builder database,
preserve proof, context, event, and run lineage.

If a future story adds memory-derived inspection capabilities, it must do so under a narrower and more governed contract rather than weakening this one.

19. Non-Goals

SDK-CLIENT-18 does not:

redesign the memory system
expose Qdrant directly
provide generic semantic search over canonical memory as a public builder API
replace context inspection, proof, or explainability surfaces
prevent all internal platform code from referencing memory as an implementation concern
eliminate server-side memory work by itself

It only defines the public client boundary.

20. Story Closure Statement

SDK-CLIENT-18 closes when the client can truthfully say:

The public SDK does not expose direct canonical memory access.
If you want memory-relevant behavior, you must come through governed context,
governed runs, or other governed proof/explain surfaces.

That is the client-side reflection of the memory containment doctrine.