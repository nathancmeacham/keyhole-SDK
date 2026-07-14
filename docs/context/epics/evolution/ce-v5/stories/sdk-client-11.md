# sdk-client-11.md

# SDK-CLIENT-11 - Alignment Guidance

**Story ID:** SDK-CLIENT-11 / sdk-client-11  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** COMPLETE  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Alignment Guidance  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-11.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-10.md`, `sdk-client-07.md`, `sdk-client-08.md`, `sdk-client-15.md`, `sdk-client-17.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** deeper explainability, trust hardening, and optional explicit patch/proposal workflows  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-11 turns analysis results into **actionable builder guidance**.

Its purpose is to answer a practical question:

```text
what should I do next to move this repo toward stronger governed alignment?

This story must work for both:

foreign repos that arrived through ingestion,
and more aligned repos that already have some governed structure.

The client must be able to:

consume analysis results,
distinguish observed facts from inferred structure,
distinguish verified gaps from lower-confidence suggestions,
rank next-best actions deterministically,
render guidance clearly without mutating the repo,
persist replayable guidance artifacts,
and help the builder move forward without guessing.

This is not a mutation story.

It is a deterministic guidance and next-step story.

2. Why This Story Exists

A governed platform that can only say "invalid" is not usable at scale.

Builders need the platform to do more than detect gaps.
They need it to tell them:

what the gap means,
how serious it is,
how certain the platform is,
what concrete action would improve alignment,
what should happen first,
what remains inferred rather than verified,
and when the repo is still too foreign for stronger participation.

This matters even more for foreign repos, because most existing repos will not arrive with:

Keyhole scaffold files,
clean dependency declarations,
capability passports,
or obvious governance posture.

Without this story:

ingestion yields diagnostics without direction,
foreign repos feel "judged" but not helped,
builders cannot prioritize repair work,
inferred findings get mistaken for truth,
and the platform feels like a scanner instead of a governed assistant.

This story turns repo analysis into guided movement.

3. Core Thesis

Alignment guidance must preserve four distinct layers of truth:

Observed facts
Directly observed repo structure, manifests, files, and deterministic validation findings.
Inferred structure
Graph-derived interpretations, probable capabilities, likely gaps, and compatibility suggestions.
Verified gaps
Deterministic failures or missing conditions grounded in schema, contracts, or server-side analysis.
Recommended actions
Ranked next steps the builder can take to improve governed alignment.

The client must never blur these layers.

In particular, it must not present:

inferred findings as verified truth,
suggestions as already applied,
or analysis as if it already changed the repo.
4. Strategic Role

SDK-CLIENT-11 sits after the client can already:

ingest and observe repos,
register repos when appropriate,
discover and resolve ecosystem capabilities,
preserve transport identity and replay-aware proof,
and observe accepted/deferred lifecycle honestly.

Its place in the flow is now best understood as:

login
  ↓
ingest / observe repo
  ↓
register if appropriate
  ↓
discover / resolve dependencies if helpful
  ↓
alignment guidance   ? THIS STORY
  ↓
explicit builder action

For foreign repos, this story is often the first place Keyhole feels genuinely helpful.

5. Scope
Included
client-side rendering of alignment/remediation guidance
deterministic ranking and grouping of guidance
explicit verified-vs-inferred labeling
compatibility/readiness summary rendering
next-best-action selection
human-readable and machine-readable guidance artifacts
replayable proof of what guidance was shown
honest handling of terminal vs accepted/deferred analysis outcomes
zipper expectations against sdk-server-11.md
Excluded
silent repo mutation
automatic contract rewriting
automatic dependency application
automatic capability registration
final support-bundle UX
final explainability UX across all surfaces
direct canonical memory access

Those belong elsewhere.

6. Supported Input Sources

The client may render alignment guidance from one or more of:

server-side ingestion analysis output
compatibility posture results
repo registration outcomes
capability discovery/resolution results
local validation result packages
saved guidance artifacts from prior runs
combined local + remote analysis inputs when the contract supports it

The client must preserve provenance for every recommendation source.

It must not blur:

server-verified findings,
local deterministic validation findings,
inferred capability suggestions,
builder-authored declarations,
or prior advisory outputs.
7. Guidance Object Model

The client must support at minimum these categories:

gap - a missing or noncompliant governed condition
warning - a notable risk or ambiguity that may block later progress
suggestion - a recommended improvement not yet required
next_best_action - the top-ranked action the builder should take next
inference - a proposed structure/capability/dependency interpretation not yet verified
readiness - a summary posture such as foreign, partially_aligned, registration_ready, run_ready
Required fields

A rendered guidance item should support fields like:

{
  "id": "gap.contract.missing_provider_pin",
  "class": "gap",
  "severity": "high",
  "confidence": 0.98,
  "state": "verified",
  "title": "Provider pin missing",
  "detail": "Dependency payment.stripe.integration.v1 has no provider pin.",
  "repair": [
    "Pin the provider explicitly.",
    "Use keyhole search payment.stripe.integration.v1 to inspect providers."
  ],
  "source": "server_gap_analysis",
  "artifact_ref": "..."
}
Verified vs inferred

This story requires an explicit distinction between:

verified findings - grounded in deterministic evidence
inferred findings - plausible suggestions derived from graphing, heuristics, or confidence-scored analysis

The client must never render inferred findings as if they are already verified truth.

8. Foreign Repo Posture

This story must explicitly assume that many alignment targets are foreign repos.

That means:

low alignment is normal,
foreign posture is not failure,
the guidance surface must help the builder move from "foreign" toward "aligned,"
and the client must not shame or overstate certainty when the repo is still early in that journey.

A foreign repo should receive guidance like:

Current posture: foreign
Top next step: review inferred boundaries and complete registration readiness

not:

Repo invalid

unless a deterministic contract truly requires that statement.

9. Deterministic Ordering Rules

The client must render guidance in a stable, predictable order.

Recommended precedence:

blocking verified gaps
high-severity verified warnings
medium/low verified issues
high-confidence inferred suggestions
lower-confidence optional improvements

Within a class, ordering should use a stable sort key such as:

severity
confidence
canonical gap ID
artifact path
title

The same guidance input must not appear in random order across repeated invocations.

10. Readiness and Compatibility Rendering

The client should render a top-level alignment posture summary.

Reasonable top-level states include:

foreign
partially_aligned
registration_ready
run_ready
blocked

This is a builder-facing summary, not a replacement for underlying evidence.

The summary should explain:

what the current posture means,
what the top blocker is,
and what the most useful next action would be.
11. Next-Best Action Contract

The client must compute and display a next-best action when possible.

A next-best action must be:

concrete,
local to the builder's current state,
consistent with deterministic ordering,
and non-ambiguous.

Examples:

Run keyhole validate after fixing governance_contract.yaml.
Review inferred capability workorder.assignment.engine.v1 before registration.
Pin a provider for payment.stripe.integration.v1.
Use --shadow until high-severity verified gaps are reduced.
This repo is still foreign. Complete registration readiness before governed run attempts.

If multiple actions are equally valid, the client must either:

rank them deterministically, or
present a clearly labeled ordered shortlist.
12. Rendering Requirements
12.1 Terminal rendering

The CLI must show at minimum:

alignment/readiness posture
total verified gap count
total inferred suggestion count
top next-best action
grouped issues
repair guidance for actionable items
explicit note that nothing was changed automatically
12.2 Machine-readable output

The client must materialize machine-readable artifacts for the same guidance set.

12.3 Human-readable summary

The client must generate a concise summary explaining:

current alignment posture
highest-priority remediation steps
what remains inferred
whether the repo is ready for registration, governed runs, or should remain in advisory/shadow posture
13. Terminal vs Accepted/Deferred Analysis

This story must handle both:

terminal analysis/guidance responses
accepted/deferred analysis responses

If guidance generation is accepted/deferred rather than completed inline, the client must render that honestly and preserve follow-up identity.

It must never fake immediate final guidance when the boundary only accepted analysis work.

Where accepted/deferred behavior exists, the client should preserve:

request identity
analysis/run reference
proof continuity
next-step observation guidance

This story therefore inherits the observation honesty established in the async lifecycle work.

14. No Silent Repo Mutation Rule

This story must preserve a hard platform law:

guidance may suggest
but it may not silently mutate

The client must not:

rewrite contracts automatically
add dependencies automatically
register inferred capabilities automatically
rename or delete files automatically
present a suggestion as applied when it is not

If future stories add patch/proposal generation, those changes must still remain explicit and reviewable.

15. Proof and Artifact Placement

Because many target repos will be foreign or only partially aligned, guidance artifacts must not be written into the target repo by default.

Default proof and guidance artifacts should live in a tool-owned local state path.

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror guidance artifacts into canonical in-repo proof locations.

Recommended structure
<tool-owned-state>/
  alignment/
    <analysis-id-or-request-id>/
      gap_analysis.json
      next_actions.json
      summary.md
      correlation.json
Required semantics
artifacts must be generated for success and partial-failure cases when usable analysis exists
verified vs inferred state must remain explicit
summary text must not overclaim certainty
deterministic enough for fixture/golden-file testing
no-silent-mutation claim must be supportable from artifacts
16. Error Handling and Repair Guidance

If alignment guidance cannot be rendered cleanly, the client must explain why.

Possible failure classes include:

no analysis artifact present
malformed server response
corrupted saved artifact
unsupported schema version
missing repo context
render failure
accepted/deferred analysis not yet ready for final rendering

In all such cases, the client must provide repair guidance such as:

rerun keyhole ingest .
rerun repo registration or validation
update the CLI version
inspect the saved analysis artifact
wait for accepted/deferred analysis to complete
use shadow/advisory mode if appropriate
17. Local Test Strategy
17.1 Local client tests

The client must support tests for:

deterministic rendering order
verified vs inferred labeling
readiness posture rendering
next-best-action selection
summary generation
machine-readable artifact creation
no silent repo mutation
repair guidance on malformed or missing inputs
accepted/deferred analysis rendered honestly
17.2 Zipper / boundary tests

The paired server story must prove:

gaps identified deterministically
suggestions reproducible
verified vs inferred state clearly distinguished
alignment evidence emitted under the paired contract

The client proof must demonstrate that those outputs are rendered faithfully and deterministically.

17.3 Negative tests

The client must reject or clearly surface:

ambiguous guidance records
missing required fields
inferred items incorrectly marked verified
non-deterministic ordering
any attempted auto-apply behavior
false terminal rendering for non-terminal analysis
18. Acceptance Criteria

This story is complete only when all of the following are true:

remediation suggestions render clearly in the client
next-best actions are produced deterministically when possible
inferred vs verified state is explicitly distinguished in terminal and artifact output
readiness/compatibility posture is rendered clearly
the same guidance input yields the same ordering and semantics
local guidance artifacts are materialized
no silent repo mutation occurs
repair guidance is provided when rendering fails or inputs are invalid
accepted/deferred analysis is rendered honestly when applicable
zipper proof shows deterministic server analysis and reproducible suggestion generation
the builder can tell what to do next without guessing
19. Zipper Expectations Against sdk-server-11.md

The paired server story must provide:

deterministic gap analysis
deterministic suggestion generation
explicit verified vs inferred distinctions
compatibility/readiness posture or enough evidence to derive it
stable analysis payload shape
alignment evidence emission under the paired server contract

SDK-CLIENT-11 closes only when the paired zipper proves:

gaps identified deterministically
suggestions reproducible
inferred vs verified state clearly distinguished
readiness posture available
alignment evidence emitted
20. Forward-Compatibility Notes

This story must remain compatible with later stories for:

explainability and support bundles
async run inspection
budget visibility
trust enforcement
explicit patch/proposal workflows
deeper context-bound remediation

The implementation must avoid assumptions such as:

all findings are server-verified
all suggestions are immediately actionable
every repo is already Keyhole-native
guidance implies applied change
one analysis artifact permanently covers every future surface
21. Non-Goals

SDK-CLIENT-11 does not:

auto-fix the repo
modify contracts silently
register capabilities automatically
replace local validation
replace ingestion
expose direct canonical memory access
provide full support-bundle functionality
overstate inferred analysis as canonical truth
22. Story Closure Statement

SDK-CLIENT-11 is the story that makes the platform useful after it has inspected or observed a repo.

When this story closes, a builder must be able to:

analyze a repo
see what is verified
see what is inferred
understand current readiness
know what to do next
and keep full control of the codebase