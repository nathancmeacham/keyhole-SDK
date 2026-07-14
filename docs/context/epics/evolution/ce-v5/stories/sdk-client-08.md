# sdk-client-08.md

# SDK-CLIENT-08 - Capability Discovery and Resolution

**Story ID:** SDK-CLIENT-08 / sdk-client-08  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Capability Discovery and Resolution  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-08.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-10.md`, `sdk-client-07.md`, `sdk-client-15.md`, `sdk-client-17.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** `sdk-client-11.md` and later alignment/remediation flows  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-08 defines the client-side contract for **governed capability discovery and deterministic dependency resolution**.

Its purpose is to let a builder:

- search the Keyhole ecosystem for reusable capabilities,
- inspect candidate providers,
- understand whether a capability is relevant to the current repo,
- resolve a capability request into a deterministic provider selection when lawful,
- preserve proof of how and why that selection occurred,
- and materialize the result safely without pretending inference or discovery is already declared truth.

This story must work for both:

- Keyhole-native repos that already have governed dependency artifacts,
- and foreign repos that arrived through ingestion and registration with little or no Keyhole-native structure.

The client's job is not to invent resolution truth.

The client's job is to:

- shape discovery and resolution requests correctly,
- present results clearly,
- preserve enough context for deterministic reuse,
- fail closed when ambiguity remains,
- and materialize outcomes only in explicitly allowed ways.

---

## 2. Why This Story Exists

A governed platform is only useful as an ecosystem if builders can discover and reuse capabilities safely.

Without this story, builders fall back to bad patterns:

- manual guessing of capability names,
- ad hoc provider selection,
- copy/paste of dependency strings,
- local drift from platform truth,
- and no replayable explanation of why a dependency resolved the way it did.

This story exists so builders can ask questions like:

- "What providers implement `payment.stripe.integration.v1`?"
- "Which one would be selected under current policy and local repo context?"
- "Why did this provider win?"
- "Why did this fail?"
- "What should I write locally, if anything?"
- "What should I do when my repo is foreign and not yet Keyhole-aligned?"

This is especially important for foreign repos, because many builders will not start with a clean `dependencies.yaml` and lawful native dependency model.

They will start with:

- ingested topology,
- compatibility posture,
- inferred needs,
- and partial alignment.

This story must support that reality without pretending the repo is already native.

---

## 3. Core Thesis

Capability discovery and resolution must preserve four distinct layers of truth:

1. **Observed repo reality**  
   What the client knows about the current repo from local files and/or prior ingestion.

2. **Inferred needs or opportunities**  
   What the system suspects the repo may benefit from, based on observed structure or builder request.

3. **Capability registry truth**  
   What the platform exposes through governed capability discovery.

4. **Resolved dependency selection**  
   A deterministic, attributable provider choice under current policy and context.

The client must never blur these boundaries.

In particular, it must not pretend that:

- search results are already resolved dependencies,
- inference equals declaration,
- or a suggested provider is already accepted local truth.

---

## 4. Strategic Role

SDK-CLIENT-08 is the story where a repo begins consuming ecosystem capabilities safely.

It sits after:

- identity and auth,
- ingestion of foreign repos,
- registration with MCP,
- transport discipline,
- and accepted/deferred lifecycle readiness.

Its place in the flow is now better modeled as:

```text id="sfg8gx"
login
  ↓
ingest / observe repo
  ↓
register repo
  ↓
discover capabilities
  ↓
resolve dependency
  ↓
materialize or suggest alignment   ? THIS STORY
  ↓
alignment guidance / explainability / governed reuse

For Keyhole-native repos, this path may be more direct.

For foreign repos, discovery and resolution often begin as advisory and alignment-supporting, not immediate file mutation.

5. Scope
Included
keyhole search
deterministic capability discovery request shaping
deterministic dependency resolution request shaping
clear ambiguity and incompatibility handling
capability/provider result rendering
optional local materialization of resolution results
proof artifacts for search and resolution
fail-closed behavior
zipper expectations against sdk-server-08.md
Excluded
server-side registry implementation
server-side resolver algorithm
marketplace ranking or economics
opaque recommendation systems
direct canonical memory search
automatic code installation
silent repo mutation
final explainability/remediation UX

Those belong elsewhere.

6. Supported Repo Realities

This story must explicitly support two common repo realities.

6.1 Native governed repo

The repo already has Keyhole-native local dependency artifacts, such as:

dependencies.yaml
other local declaration files that shape dependency intent

For these repos, successful resolution may be materialized directly into governed local artifacts when explicitly requested.

6.2 Foreign / ingestion-backed repo

The repo was built outside Keyhole and may have:

no dependencies.yaml,
no governed contract files,
unclear boundaries,
inferred rather than declared dependency needs.

For these repos, discovery and resolution often begin in advisory mode.

That means the client may:

search,
resolve,
explain,
and generate out-of-tree suggestions or proof artifacts,

without writing Keyhole-native dependency files into the repo by default.

This is a hard distinction.

7. Constitutional Anchors

This story must preserve all of the following:

the SDK is not the control plane,
the MCP boundary is the sole public authority for capability registry truth,
builders consume governed artifacts; they do not mutate platform truth directly,
dependency resolution must be deterministic and explainable,
ambiguous cases must fail closed,
capability selection must be attributable and replayable,
no direct canonical memory access is introduced through discovery UX,
proof must exist for write-bearing resolution actions,
foreign repos must not be silently "Keyholified" during discovery/resolution.
8. Client Responsibilities

The client must:

8.1 Search

Provide a builder-friendly search surface:

keyhole search <query>

This command must support at minimum:

exact capability search,
namespace-prefix search,
provider-filtered search,
version-aware query shaping,
machine-readable output modes.
8.2 Resolve

Provide a deterministic resolution helper.

Preferred canonical form:

keyhole dependency resolve <capability>

Optional alias, if adopted:

keyhole resolve <capability>

The helper must:

accept a capability request,
gather lawful local repo context,
shape a governed resolution request,
render the result clearly,
optionally materialize the result in an explicitly allowed way.
8.3 Fail closed

If multiple valid providers exist and no lawful tie-breaker exists, the client must not silently pick one.

8.4 Preserve proof

Search may be lightweight, but write-bearing resolution and materialization actions must be replayable and proof-producing.

8.5 Avoid silent mutation

The client must never mutate repo files unless the builder explicitly asked for write behavior and the repo is in a mode where that write target is lawful.

9. Canonical Commands
9.1 Search
keyhole search <query>

Examples:

keyhole search payment.stripe.integration.v1
keyhole search payment.stripe
keyhole search --provider workorder-platform payment.stripe.integration.v1
keyhole search --json payment.stripe.integration.v1
9.2 Resolve

Preferred canonical form:

keyhole dependency resolve <capability>

Examples:

keyhole dependency resolve payment.stripe.integration.v1
keyhole dependency resolve crm.salesforce.sync.v2 --provider crm-platform
keyhole dependency resolve payment.stripe.integration.v1 --write
keyhole dependency resolve payment.stripe.integration.v1 --advisory
9.3 Materialization modes

Reasonable modes include:

--advisory
Resolve and produce proof/suggestions only.
--write
Materialize resolution into a lawful local artifact target.

For foreign repos, --advisory should often be the safe default.

10. Local Inputs

The client may use the following local inputs when shaping a discovery or resolution request:

repo identity
current builder identity / tenant context
ingestion summary or compatibility posture where applicable
dependencies.yaml when present
keyhole.yaml when present
local repo metadata
command flags such as --provider, --version, --json, --write, --advisory

The client must not invent hidden provider pins, hidden repo policy, or missing dependency truth.

11. Search UX Requirements
11.1 Human-readable result shape

Search results should present:

capability name
provider
major version
visibility
optional summary
optional trust/proof signals if available
optional indication that the result matches an inferred need from prior ingestion
optional indication that the result already appears pinned locally
11.2 Empty results

If search returns no results, the client must say so explicitly and suggest next steps such as:

check namespace spelling
relax provider/version filters
create a new capability instead
inspect local inferred needs from ingestion
11.3 Multiple close matches

The client may group or order results for readability, but it must not imply deterministic resolution unless one actually exists.

12. Resolution UX Requirements
12.1 Successful resolution

A successful resolution must show:

requested capability
resolved provider
resolved version
immutable digest if returned
reason for selection
whether the result was advisory-only or materialized locally
which local target, if any, was updated
12.2 Ambiguity failure

If ambiguity remains unresolved, the client must fail closed and include repair guidance such as:

add --provider <name>
pin provider explicitly
inspect candidate providers with keyhole search
refine compatibility intent before writing
12.3 Incompatibility failure

If no provider is compatible, the client must surface:

requested capability
reason code
incompatible candidates if safe and useful to show
next steps
12.4 Foreign repo caution

For foreign repos, successful resolution must not imply that the repo is now fully aligned.

It may only mean:

a provider choice is now explainable,
and a suggested alignment or materialization target is available.
13. Materialization Rules

When resolution succeeds, the client may materialize the result only in explicitly allowed ways.

13.1 Native repo case

If the repo is Keyhole-native and --write is explicitly provided, the client may update:

dependencies.yaml

with a deterministic dependency entry such as:

capability
provider
optional digest
optional resolution metadata
13.2 Foreign repo case

If the repo is foreign or ingestion-backed, the client must not create Keyhole-native dependency files inside the repo by default.

Instead, the client may:

emit an out-of-tree suggested dependency record,
emit a proof-backed advisory artifact,
present a patch preview or recommended next step,
wait for an explicit later alignment action.
13.3 No silent mutation

If --write is not provided, the client must not mutate dependency files.

If the repo is foreign, even --write should remain constrained to lawful and clearly communicated targets.

14. Suggested Materialization Targets
14.1 Native repo proof/in-repo mode

If the repo is Keyhole-native and explicitly opted in, the client may update in-repo dependency artifacts and mirror proof into canonical proof paths.

14.2 Foreign repo default mode

For foreign repos, default artifacts should live in a tool-owned local state path rather than inside the target repo.

A reasonable out-of-tree shape is:

<tool-owned-state>/
  resolution/
    <request-id-or-resolution-ref>/
      request.json
      response.json
      summary.md
      suggested-dependency.json
      diff.json

This preserves replayability without mutating the target repo by default.

15. Transport and Boundary Discipline

Discovery and resolution must inherit the transport discipline already established in SDK-CLIENT-15.

That means:

every request gets X-Request-Id,
write-bearing resolution actions use the correct idempotency behavior,
retries preserve same-attempt identity,
the client must not bypass the centralized transport layer.

If a write-bearing resolution/materialization action becomes accepted/deferred rather than terminal, the client must render that honestly and preserve follow-up identity rather than faking completion.

The client must preserve room for:

correlation IDs,
proof references,
accepted/deferred follow-up observation,
replay-safe local records.
16. Determinism Requirements

This story must preserve the following deterministic properties.

16.1 Same query, same result shape

If the same query is issued against the same registry state and same identity/policy context, the client must present the same result shape unless the boundary contract explicitly declares ordering unstable.

16.2 Same request, same resolution

If the same resolution request is issued against the same local and server context, the client must produce the same resolved result or the same fail-closed outcome.

16.3 Materialization determinism

If the same successful result is materialized in the same mode, the resulting local artifact structure must be equivalent except for approved volatile fields.

17. Failure Model

The client must handle these failure classes explicitly.

17.1 Empty search

No matches.

17.2 Ambiguous search / ambiguous resolution

Multiple candidates and no lawful tie-break.

17.3 Incompatible provider set

Capability exists but no provider satisfies the requested constraints.

17.4 Registry unreachable

Boundary unavailable or contract unreachable.

17.5 Invalid local dependency state

The local repo dependency model is malformed for the chosen mode.

17.6 Unsupported materialization target

The builder requested --write, but the repo is foreign or otherwise not in a lawful state for direct in-repo materialization.

17.7 Server reject

The boundary explicitly rejects the request.

Each class must produce deterministic repair guidance.

18. Repair Guidance Requirements

Every client-visible failure must include actionable next steps.

Examples:

"Use keyhole search <capability> to inspect candidates."
"Specify --provider because multiple lawful providers exist."
"Pin a provider in native dependency artifacts only after alignment."
"This repo is foreign; use advisory mode or complete alignment first."
"Run registration or alignment steps before writing dependency state."
"Inspect ingestion compatibility posture before materializing."

The client must not return opaque errors for routine resolution failure.

19. Proof Contract

Search may be lightweight, but resolution actions must preserve replayable proof.

19.1 Search proof

A lightweight search artifact is acceptable, especially in machine-readable or diagnostic modes.

19.2 Resolution proof

A replayable proof bundle for resolution should include at minimum:

command invoked
local repo identity
repo posture (native / foreign / ingestion-backed)
input capability request
effective local inputs
server response summary
final resolution decision
advisory vs write mode
resulting file diff or no-diff statement
deterministic summary
19.3 Suggested structure

For foreign repos by default, use a tool-owned path such as:

<tool-owned-state>/
  resolution/
    <request-id-or-resolution-ref>/
      core.json
      summary.md
      response.json
      diff.json

If the repo is Keyhole-native and explicit opt-in exists, the client may additionally mirror proof under canonical in-repo proof paths.

20. Tests
20.1 Search behavior
exact capability query returns expected candidates
namespace-prefix search returns grouped/ordered candidates
empty results handled deterministically
20.2 Deterministic resolution
same request resolves to same provider
provider pinning is honored
digest pinning is preserved
result materialization is deterministic
20.3 Fail-closed ambiguity
no silent winner selection when ambiguity remains
repair guidance points to lawful next steps
20.4 Materialization behavior
native repo write mode updates dependency artifacts deterministically
foreign repo advisory mode produces out-of-tree artifacts only
no-write mode emits proof without mutating repo files
unsupported write target fails clearly
20.5 Accepted/deferred honesty
non-terminal resolution/materialization does not render as completed
follow-up identity is preserved when returned by the server
21. Zipper Expectations with sdk-server-08.md
Client responsibilities
shape discovery and resolution requests correctly
fail closed locally when ambiguity remains
materialize results only in lawful targets
preserve deterministic local behavior
preserve proof and transport identity
Server responsibilities
expose capability registry/discovery surface
provide deterministic resolver behavior
reject unsafe or ambiguous resolution without hidden heuristics
emit attributable query/resolution evidence
Zipper completion condition

This zipper is closed only when:

search returns correct capabilities end to end
resolution deterministically maps to valid providers
ambiguous cases fail closed
resolution record is materialized in the correct local mode
attributable evidence is preserved across the boundary
22. Closure Criteria

SDK-CLIENT-08 is closed when all of the following are true:

keyhole search exists and returns deterministic results
a dependency resolution helper exists and behaves deterministically
ambiguous cases fail closed
successful resolutions can be materialized safely
foreign repos default to advisory / out-of-tree behavior rather than in-repo mutation
resolution proofs are replayable
write-bearing resolution actions inherit transport discipline correctly
the client half zippers cleanly with sdk-server-08.md
23. One-Line Summary

SDK-CLIENT-08 gives builders a governed way to discover reusable capabilities and deterministically resolve dependencies into replayable local artifacts or advisory alignment outputs-without hidden provider selection, silent repo mutation, or pretending a foreign repo is already Keyhole-native.