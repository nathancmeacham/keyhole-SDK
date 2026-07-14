# sdk-client-10.md

# SDK-CLIENT-10 - Repository Ingestion and Graph

**Story ID:** SDK-CLIENT-10 / sdk-client-10  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Repository Ingestion  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-10.md`  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, `sdk-client-15.md`, `sdk-client-17.md`, SDK-CLIENT master guidance, official MCP ingress contract  
**Precedes:** `sdk-client-07.md`, `sdk-client-08.md`, `sdk-client-11.md`, later alignment and explainability stories  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-10 defines how an **existing non-Keyhole repository** enters the Keyhole ecosystem safely.

This story exists for the common real-world case where the target repo:

- was not created with `keyhole init vertical`,
- has no Keyhole scaffold,
- has no Keyhole declarations,
- is structurally inconsistent,
- may mix languages, frameworks, and tooling,
- may contain weak or missing tests,
- and is highly unlikely to be fully compatible on first contact.

This story must make the following true:

- a builder can point the SDK at an existing repo,
- the client can inspect it locally without mutating it,
- the client can package a privacy-safe ingestion request,
- the platform can return graph and inference results,
- inferred structure is clearly marked as inference rather than declared truth,
- low compatibility is treated as normal,
- proof artifacts exist for the ingestion attempt,
- the builder can see concrete next-step alignment guidance.

This story is not a rewrite path.

It is an **observation, packaging, graphing, and guided alignment path** for foreign repositories.

---

## 2. Why This Story Exists

Many of the most valuable future builders will not arrive with Keyhole-native repos.

They will arrive with legacy or foreign repos that contain:

- ad hoc structure,
- mixed dependency systems,
- implicit boundaries,
- partial documentation,
- unclear capability surfaces,
- and little or no governance metadata.

If the SDK only supports greenfield Keyhole scaffolds, adoption becomes replacement-first instead of alignment-first.

This story lets Keyhole say:

```text id="vtlid9"
bring the repo you already have
we will observe it safely
help you understand it
and propose alignment without silently rewriting it

This is also the adoption wedge for skeptical builders, because ingestion is the first place the platform can produce a concrete "wow" outcome for an existing codebase:

observed topology,
graph summary,
inferred capabilities,
confidence scores,
compatibility posture,
suggested next actions.
3. Core Thesis

Repository ingestion must assume foreign repo reality.

That means the client must behave as though the target repo is:

structurally untrusted,
not yet governed,
not yet scaffolded,
not yet validated,
not yet aligned,
and not safe to mutate implicitly.

The ingestion path must therefore preserve four distinctions at all times:

Observed facts
File structure, manifests, dependency files, docs, build files, test locations, and other directly observed signals.
Inferred structure
Graph edges, architectural guesses, likely capabilities, probable dependency boundaries, and compatibility posture.
Suggested alignment
Recommended next steps to make the repo more governable.
Declared Keyhole truth
This story does not mint it.

Ingestion is a safe observation boundary, not automatic governance acceptance.

4. Scope
Included
keyhole ingest
keyhole ingest --shadow
deterministic local repository scan
deterministic packaging of ingestion inputs
explicit include / exclude controls
privacy-safe and secret-safe packaging defaults
graph-ready artifact submission
confidence-aware inference rendering
compatibility posture rendering
proof artifact emission
strict no-silent-mutation guarantees
zipper expectations against sdk-server-10.md
Excluded
silent modification of the target repo
automatic scaffold insertion
automatic acceptance of inferred capabilities as declared truth
automatic contract generation into the repo
automatic promotion or registration
direct canonical memory access
final explainability/support-bundle UX
automatic remediation edits

Those belong to later stories.

5. Command Contract
5.1 Primary command
keyhole ingest

The command scans the current repo or a specified local path, builds a deterministic ingestion package, submits it to the server ingestion surface, and returns a governed ingestion outcome.

5.2 Shadow command
keyhole ingest --shadow

This performs the same local scan and packaging flow while explicitly marking the request as exploratory / low-risk participation.

Shadow mode must be visible in:

request metadata,
terminal output,
proof artifacts,
local ingestion records.
5.3 Path forms

At minimum, support:

keyhole ingest .
keyhole ingest <path>

Optional future extensions may support remote URLs or VCS references, but this story only requires local path ingestion.

5.4 Optional bounded controls

A reasonable bounded CLI surface may include:

keyhole ingest <path> --shadow
keyhole ingest <path> --include <glob>
keyhole ingest <path> --exclude <glob>
keyhole ingest <path> --max-bytes <n>
keyhole ingest <path> --summary-only
keyhole ingest <path> --proof <mode>

These controls must remain subordinate to the no-silent-mutation and secret-safe packaging rules.

6. Foreign Repo Posture

This story must explicitly assume the ingested repo is not Keyhole-compatible by default.

That means the client must not assume:

presence of keyhole.yaml,
presence of governance_contract.yaml,
presence of capability_passport.yaml,
presence of a canonical proof bundle structure,
valid governance metadata,
prior repo registration,
prior run history,
or clean architectural boundaries.

Incompatibility is not failure.

It is expected input.

The purpose of ingestion is to turn that reality into structured understanding and actionable alignment guidance.

7. Repo Safety Contract

The client must not silently rewrite the target repository.

This is a hard rule.

Forbidden behavior
editing source files without explicit builder action,
generating contracts directly into the repo by default,
renaming files,
deleting files,
inserting hidden markers,
auto-committing inferred changes,
mutating dependency manifests implicitly,
creating hidden Keyhole state inside the repo unless the builder explicitly opts in later.
Allowed behavior
reading repo files,
classifying files,
computing deterministic package manifests,
generating out-of-tree artifacts,
generating proof artifacts,
presenting suggested changes,
writing temporary packaging artifacts only to explicit tool-owned safe paths.

The builder must always be able to trust:

ingestion observes first
it does not rewrite first
8. Local Scan Responsibilities

Before submission, the client must inspect the repository locally.

Minimum scan responsibilities
identify repo root,
identify likely language and framework signals,
identify project manifests,
identify likely source directories,
identify likely test directories,
identify likely docs and design materials,
identify dependency files,
identify build, CI, and deployment files where relevant,
identify files to include or exclude,
detect obvious repo-level topology signals,
gather enough evidence to support graphing and inference.
Examples of scan signals
pyproject.toml
requirements.txt
package.json
pom.xml
go.mod
Cargo.toml
Dockerfile
compose manifests
CI workflows
README.md
architecture docs
src/, app/, lib/, tests/, docs/
infra/config manifests
Important rule

The scan result must be deterministic for the same repo state and configuration.

9. Compatibility Posture Assessment

Because the target repo is unlikely to be Keyhole-compatible on first contact, the client should present a compatibility posture assessment.

This is not declared truth.
It is a client/server assessment aid.

Reasonable categories include:

foreign
partially_aligned
keyhole_ready

For most first-contact repos, foreign should be expected and should not be rendered as a failure.

Compatibility posture exists to help builders understand how far the repo is from governed participation readiness.

10. Packaging Contract

The client must transform local scan results into a deterministic ingestion package.

The package must include, at minimum
target repo identity metadata
local path context
language/framework signals
included file manifest
excluded file manifest or exclusion rules
dependency manifest snapshots or summaries
scan summary
compatibility posture inputs
shadow mode flag
proof correlation metadata
builder-supplied hints, if any
The package must not include by default
arbitrary secret files
local credential stores
.env files
Git internals
editor temp files
OS junk
build caches
giant binary artifacts not needed for structural understanding
Packaging principle

Package only what is necessary for governed graphing and inference.

No indiscriminate "upload the whole machine" behavior.

11. Include / Exclude Rules

The client must implement deterministic include / exclude behavior.

Exclude by default
.git/
virtual environments
node_modules/
build output directories
cache directories
local secret/config files such as .env
editor temp files
OS junk
large binary artifacts not required for topology inference
Include by default
source files
test files
docs and READMEs
dependency manifests
build/config manifests relevant to topology
CI configuration where it reveals workflow structure
Builder control

The builder may refine inclusion/exclusion, but unsafe defaults must remain conservative.

12. Transport and Submission Discipline

Ingestion is a public client submission surface and must inherit the transport discipline already established in SDK-CLIENT-15.

That means:

every request gets X-Request-Id,
write-bearing ingestion submissions use the correct operation-class handling,
retries preserve the same logical operation identity,
the client must not bypass the centralized transport layer.

Because ingestion may be fast or may become accepted/deferred under load, this story must also remain compatible with the accepted/deferred run observation model introduced later in the lifecycle.

The client must therefore be able to render either:

terminal ingestion completion, or
accepted/deferred ingestion state with next-step observation guidance.

It must never fake final completion when the boundary only accepted the work.

13. Shadow Mode Contract

In shadow mode, the client must:

mark the request as exploratory / shadow participation,
stamp shadow status into proof and local ingestion record metadata,
render outcomes as observational rather than committed,
avoid implying that inferred capabilities are now registered, canonical, or accepted.

Shadow mode exists specifically to make first ingestion of foreign repos safe.

14. Server-Facing Expectations

The paired server story is responsible for:

ingestion endpoint,
graph builder,
capability inference,
confidence scoring,
compatibility analysis,
persistence or indexing behavior,
event emission.

The client is responsible for shaping a lawful request and rendering the response honestly.

At minimum, the client should expect the server to return some combination of:

graph summary,
inferred capability list,
confidence scores,
compatibility posture,
warnings / caveats,
ingestion identifier or run reference,
proof/event correlation data,
suggested next actions.

The client must not act as the graph engine itself.

15. Output Contract

The client must render ingestion outcomes clearly.

Minimum success rendering
repo path or identity
mode (shadow / regular)
ingestion result status
graph creation status
compatibility posture
count of inferred capabilities
confidence summary
proof artifact location
suggested next step
Minimum failure rendering
failure class
local vs boundary distinction where possible
deterministic reason
repair guidance
proof artifact location if generated
Important rule

Inference results must never be rendered as declared truth.

The client must visually distinguish:

observed facts
inferred capabilities
compatibility posture
suggested alignment
accepted governed registrations

This story does not finalize registrations.

16. Graph and Inference Semantics

The client must support a response model where the server returns:

observed graph/topology output,
inferred capabilities,
confidence scores,
warnings / caveats,
and optional suggested alignment actions.
Required UX distinctions

Use explicit language such as:

observed
inferred
confidence: high|medium|low
compatibility: foreign|partially_aligned|keyhole_ready
suggested next step

This prevents a builder from mistaking ingestion for automatic governance acceptance.

Important rule

Low-confidence inference is not failure.
It is a signal that more alignment work is needed.

17. Local Artifact and Proof Contract

Every ingestion attempt must produce local proof artifacts sufficient to explain:

what path was targeted,
what was scanned,
what was included and excluded,
what mode was used,
what package summary was submitted,
what the boundary returned,
what graph / inference / compatibility outcomes were observed,
what repair guidance was shown if the attempt failed.
Default artifact location rule

Because the target repo is likely foreign and non-Keyhole, proof artifacts must not be written into the target repo by default.

Default proof and ingestion records should live in an explicit tool-owned local state path.

If the builder later ingests a repo that is already Keyhole-scaffolded and explicitly opts in, the client may additionally mirror artifacts into canonical in-repo proof locations.

Recommended structure

A reasonable out-of-tree structure is:

<tool-owned-state>/
  ingest/
    <ingest-id-or-request-id>/
      request.json
      package_manifest.json
      response.json
      summary.md
      correlation.json

If the target repo is already governed and explicit opt-in exists, the client may additionally integrate with canonical proof paths rooted at proof_bundle/core/ and proof_bundle/extended/.

Required semantics
proof artifacts exist for success and failure
shadow mode is visible
package manifest is inspectable
no-silent-mutation claims are supportable from proof
observed vs inferred distinctions are preserved
18. Local Test Strategy
18.1 Local client tests

Must cover:

keyhole ingest parsing
keyhole ingest --shadow parsing
repo root detection
include/exclude filtering correctness
secret-bearing files excluded by default
deterministic package manifest generation
compatibility posture rendering
no repo mutation during ingestion
proof artifacts generated on success
proof artifacts generated on failure
clear output rendering for inferred capabilities and confidence
18.2 Boundary / zipper tests

Must prove:

repo graph created
inferred capabilities returned with confidence scores
compatibility posture rendered
no silent repo mutation
event / ingestion completion evidence emitted under the paired server contract
18.3 Negative tests

Must cover:

invalid or missing repo path rejected locally
unreadable repo state fails clearly
unsupported packaging state surfaces repair guidance
client does not claim successful inference when the server rejected ingestion
accepted/deferred ingestion does not render as completed if it is not terminal
19. Acceptance Criteria

This story is complete only when all of the following are true:

the client exposes keyhole ingest
the client exposes keyhole ingest --shadow
local repo scan executes deterministically
packaging excludes obviously unsafe or irrelevant files by default
packaging is deterministic for the same repo state
shadow mode is visible in request, output, and proof
no silent repo mutation occurs
proof artifacts are emitted for both success and failure
the client renders inferred capabilities with confidence clearly
the client distinguishes observed facts from inferred structure
the client renders compatibility posture honestly
zipper proof shows graph creation end-to-end
zipper proof shows ingestion completion evidence under the paired contract
20. Zipper Expectations Against sdk-server-10.md

The paired server story must provide:

ingestion endpoint
graph builder
capability inference
confidence scoring
compatibility analysis
ingestion completion evidence

SDK-CLIENT-10 closes only when paired proof demonstrates:

repo graph created
inferred capabilities returned with confidence
compatibility posture available
no silent repo mutation
ingestion completion evidence emitted
21. Forward-Compatibility Notes

This story must be implemented in a way that supports later stories for:

repo registration,
capability resolution,
alignment guidance,
explainability/support bundles,
trust metadata enrichment,
explicit builder acceptance of inferred structures,
context-bound follow-up actions.

The client must not assume ingestion itself equals:

registration,
declaration,
compatibility,
or governance acceptance.
22. Non-Goals

SDK-CLIENT-10 does not:

auto-register inferred capabilities
auto-edit repo contracts
rewrite source files
insert scaffold files into foreign repos by default
expose direct canonical memory access
finalize capability acceptance on behalf of the builder
guarantee high-confidence inference for every repo
replace later remediation/alignment stories
23. Story Closure Statement

SDK-CLIENT-10 is the story that lets a foreign repository meet Keyhole safely.

When this story closes, a builder must be able to:

point the SDK at an existing repo
observe a governed ingestion result
see graph and topology output
see inferred capabilities with confidence
see compatibility posture
receive proof artifacts
and trust that the SDK did not silently mutate the codebase

That is the adoption-safe ingestion boundary this epic requires.