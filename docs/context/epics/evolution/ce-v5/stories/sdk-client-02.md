# sdk-client-02.md

# SDK-CLIENT-02 - Governed Repo Scaffold

**Story ID:** SDK-CLIENT-02 / sdk-client-02  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (promotion only)  
**Surface:** Client / CLI / Local Repository Workspace  
**Story Type:** Client-only, offline-safe scaffold story  
**Paired Server Story:** None  
**Depends On:** `sdk-client-00.md`, `sdk-client-01.md`, `sdk-client-01-a.md`, SDK-CLIENT master guidance  
**Precedes:** `sdk-client-05.md`, `sdk-client-06.md`, `sdk-client-07.md`, `sdk-client-16.md`  
**Last Updated:** 2026-04-13

---

## 1. Purpose

Implement:

```text
keyhole init vertical

so a builder can create a canonical governed participant repository scaffold with the correct local structure, declaration artifacts, and future-ready placeholders for validation, governed context, and proof-aware workflows.

This story establishes the repo itself as a governance primitive.

The scaffold must:

generate a predictable local repository structure,
generate canonical declaration files,
generate proof-ready and context-ready placeholder areas,
remain deterministic and rerun-safe,
work without live MCP connectivity,
avoid pretending that local scaffold state is canonical platform truth.

This story is about creating the right local starting shape for future governed participation.

2. Why This Story Exists

The SDK cannot become a disciplined public builder surface if every repository begins with a different shape, different filenames, different declaration locations, and different assumptions about where proof, context, or internal tool state belong.

Without a scaffold story:

repository layout drifts immediately,
later validation stories inherit unnecessary complexity,
declaration artifacts become inconsistent,
proof support feels bolted on,
context-bound governed execution has no stable local foothold,
examples and onboarding become harder to trust.

This story is the first durable post-auth builder move. It is where Keyhole stops being "login works" and starts becoming a repeatable operating model for builders.

3. Story Thesis

A governed repo should not begin as an empty directory plus ad hoc conventions.

It should begin as a declared, inspectable, repeatable workspace with:

known entry-point files,
known local declaration locations,
known proof-ready paths,
known context-ready placeholders,
a deterministic initialization path,
and explicit separation between local workspace state and authoritative platform truth.

This story turns:

mkdir repo

into:

keyhole init vertical

where the result is not merely a folder tree, but a future-governable participant repo.

4. Scope

This story covers:

the keyhole init vertical CLI command,
local generation of canonical repo structure,
local generation of required declaration files,
local proof-ready placeholders,
local context-ready placeholders,
deterministic content generation,
rerun / overwrite safety,
local evidence sufficient to prove scaffold correctness.

This story does not cover:

repo registration with MCP,
governed validation against live server truth,
capability publishing,
governed run dispatch,
live context compilation,
server-backed proof bundle population,
ingestion of existing repositories,
direct memory access,
any direct mutation of the MCP boundary.

This is a local scaffold story only.

5. Command Contract
Primary command
keyhole init vertical
Supported intent

Create a governed participant scaffold in the current directory or a specified target directory.

Minimum supported forms
keyhole init vertical [name]
keyhole init vertical --path <dir>
keyhole init vertical --force
keyhole init vertical --dry-run
keyhole init vertical --template default
keyhole init vertical --non-interactive
Behavioral rules
default behavior may be interactive when useful,
--non-interactive must be deterministic,
--dry-run must show the exact managed changes,
--force must be required before overwriting managed scaffold files,
the command must never silently delete or overwrite unmanaged user content,
the command must not require network access.
6. Architectural Posture

This scaffold represents a local governed participant repo, not a local mirror of the Keyhole control plane.

Important rules:

the scaffold is local workspace preparation,
it is not proof of live governed participation,
it is not registration,
it is not governed execution,
it is not canonical truth,
it must not imply direct access to platform internals.

The generated repo should prepare a builder for later governed participation without pretending that the platform has already accepted, registered, validated, or proven anything.

7. Canonical Scaffold Output

The generated repository must include a stable governed shape.

Minimum repo tree
repo/
--- keyhole.yaml
--- governance_contract.yaml
--- capability_passport.yaml
--- dependencies.yaml
--- capabilities/
-   --- .gitkeep
--- src/
-   --- .gitkeep
--- tests/
-   --- .gitkeep
--- docs/
-   --- README.md
-   --- context/
-       --- .gitkeep
--- proof_bundle/
-   --- core/
-   -   --- .gitkeep
-   --- extended/
-   -   --- .gitkeep
-   --- README.md
--- context/
-   --- requests/
-   -   --- .gitkeep
-   --- resolved/
-   -   --- .gitkeep
-   --- README.md
--- .keyhole/
    --- state/
    -   --- .gitkeep
    --- cache/
    -   --- .gitkeep
    --- README.md

The exact tree may evolve in later stories, but this story must preserve these structural ideas:

root declarations,
capability surface directory,
implementation directory,
tests directory,
docs directory,
proof-ready structure,
context-ready structure,
local SDK/CLI managed state and cache area.
8. Required Generated Files
8.1 keyhole.yaml

Purpose:

local repo identity,
scaffold metadata,
repo kind,
future registration anchor.

Minimum placeholder shape:

schema_version: v0.1
repo:
  name: <repo-name>
  kind: vertical
  owner: Keyhole Solution Foundation
  visibility: private
sdk:
  initialized_by: keyhole init vertical
  initialized_at: <timestamp>
  template: default
context:
  mode: explicit
proof:
  enabled: true

Rules:

values must be deterministic except explicitly allowed volatile fields,
this file is local repo metadata, not proof of live registration.
8.2 governance_contract.yaml

Purpose:

local governance declaration entry point,
produced capabilities,
required tests,
local invariants,
compatibility references.

Minimum placeholder shape:

schema_version: v0.1
repo: <repo-name>
parent_repo: null
produces: []
required_tests: []
local_invariants: []
compatibility_contracts: []

Rules:

generated content must be stable,
empty lists are acceptable placeholders,
file must clearly invite later builder editing.
8.3 capability_passport.yaml

Purpose:

local placeholder for future portable capability / proof identity.

Minimum placeholder shape:

schema_version: v0.1
capabilities: []
owner_repo: <repo-name>
visibility: private
proofs: []
trust:
  sbom_digest: null
  attestation_digest: null
  transparency_ref: null

Rules:

this file is scaffolded as a future-ready placeholder,
it must not imply that any capability is already proven or published.
8.4 dependencies.yaml

Purpose:

local declaration point for upstream capability dependencies.

Minimum placeholder shape:

schema_version: v0.1
dependencies: []
8.5 docs/README.md

Purpose:

explain what was generated,
explain each root declaration file,
explain that the repo is local and not yet registered or governed upstream,
provide next-step guidance.

Must include:

generated file overview,
declaration meanings,
suggested next commands,
explicit statement that scaffold generation does not equal MCP registration or proof.
8.6 proof_bundle/README.md

Purpose:

explain local proof-ready structure,
explain hot core vs extended evidence,
explain that this story creates placeholders only.
8.7 context/README.md

Purpose:

explain local context request / resolved placeholder areas,
explain that governed execution will later require explicit governed context,
explain that this story does not perform context compilation.
8.8 .keyhole/README.md

Purpose:

explain tool-managed local state and cache,
warn that this directory is not authoritative platform truth,
discourage manual dependence on internal cache semantics.
9. Context-Ready Placeholder Requirements

This story must prepare the repo for later explicit governed context without pretending to compile or infer context now.

Required directories
context/requests/
context/resolved/
Required semantics
context/requests/ is the local staging area for human/tool-authored context request artifacts,
context/resolved/ is the local place where resolved context references or summaries may later be materialized,
these are placeholders for later governed workflows,
this story must not imply that context is optional for future governed runs.
Important rule

The scaffold must prepare for explicit context binding without:

performing live context retrieval,
inventing hidden context inference,
pretending a local folder is authoritative context truth.
10. Proof-Ready Placeholder Requirements

This story must prepare the repo for future proof-aware workflows from day one.

Required directories
proof_bundle/core/
proof_bundle/extended/
Required semantics
proof_bundle/core/ is reserved for replay-critical proof artifacts,
proof_bundle/extended/ is reserved for large or secondary evidence,
this split must be visible before the first live run exists.
Important rule

The scaffold must show proof structure without implying that local initialization itself is a server-backed proof event.

11. Determinism Requirements

This story is not complete unless scaffold generation is deterministic.

For the same:

repo name,
template,
flags,
story version,

the command must generate the same directory tree and normalized file content except for explicitly allowed volatile metadata.

Allowed volatility

Only explicitly permitted metadata may vary, such as:

initialization timestamp,
console-only correlation identifiers if any.
Forbidden nondeterminism
random placeholder text,
unstable YAML key or list ordering,
inconsistent README wording,
tree-shape drift for identical inputs.
12. Re-Run and Existing Directory Rules
Case A - empty target directory

Expected outcome:

scaffold succeeds,
all managed files are created.
Case B - already initialized governed repo

Expected outcome:

command detects existing scaffold,
exits safely,
explains what was found,
suggests --force only when appropriate.
Case C - partially initialized or conflicting directory

Expected outcome:

command identifies managed vs unmanaged conflicts,
refuses silent overwrite,
shows exact conflicts,
supports --dry-run for inspection.
Case D - --force

Expected outcome:

only managed scaffold files may be overwritten,
unmanaged content must not be silently deleted,
command output must make overwrite behavior explicit.
13. UX Requirements
13.1 Success output

A successful initialization should show:

target path,
managed files created,
whether the action was fresh or forced,
next steps.

Example:

✔ Governed repo scaffold created
Path: ./my-vertical
Files:
  - keyhole.yaml
  - governance_contract.yaml
  - capability_passport.yaml
  - dependencies.yaml

Next:
  1. keyhole validate
  2. edit governance_contract.yaml
  3. edit capability_passport.yaml
  4. later: keyhole repo register
13.2 Dry-run output

Must show the exact tree and managed file operations that would occur.

13.3 Error UX

Must clearly distinguish:

invalid path,
permission failure,
existing initialized repo,
conflicting unmanaged files,
invalid template selection.
13.4 Progressive disclosure

The command must feel simple for a first-time builder while still making the deeper governance model visible through generated files and README guidance.

14. Local Evidence Requirements

Even though this is an offline-safe story, it still requires replayable local evidence sufficient to prove correctness.

Minimum evidence expectations

Implementation should produce or be testable against:

generated tree snapshot,
normalized file contents,
stable digests for managed scaffold artifacts,
summary of created files,
deterministic golden fixtures.
Optional local artifact

A local summary may be written into .keyhole/state/, but this story does not require a live proof bundle or server evidence.

Rule

This story must be provable locally through deterministic outputs alone.

15. Acceptance Criteria

This story is complete only when all of the following are true:

keyhole init vertical creates the canonical governed participant repo structure.
Required root declaration files are generated.
Context-ready placeholders are present.
Proof-ready placeholders are present.
The scaffold is deterministic for the same inputs.
--dry-run shows exact intended changes.
Existing initialized repos are detected safely.
Unmanaged conflicting files are not silently overwritten.
Success output explains next steps clearly.
The scaffold works without live MCP connectivity.
The scaffold does not claim registration, governed execution, or upstream proof.
16. Test Plan
16.1 Unit tests

Must cover:

CLI argument parsing,
path resolution,
deterministic file rendering,
YAML serialization stability,
dry-run output,
initialized-repo detection,
managed vs unmanaged conflict detection.
16.2 Golden-file tests

Must cover:

keyhole.yaml,
governance_contract.yaml,
capability_passport.yaml,
dependencies.yaml,
README files,
tree snapshot.
16.3 Integration-style local tests

Must cover:

init into empty temp dir,
rerun against initialized dir,
init with --force,
init with --dry-run,
init into nested path.
16.4 Negative tests

Must cover:

invalid path,
permission denied,
conflicting unmanaged file,
malformed template selection,
accidental overwrite without --force.
17. Reference Tree
<repo-name>/
--- keyhole.yaml
--- governance_contract.yaml
--- capability_passport.yaml
--- dependencies.yaml
--- capabilities/
-   --- .gitkeep
--- src/
-   --- .gitkeep
--- tests/
-   --- .gitkeep
--- docs/
-   --- README.md
-   --- context/
-       --- .gitkeep
--- proof_bundle/
-   --- core/
-   -   --- .gitkeep
-   --- extended/
-   -   --- .gitkeep
-   --- README.md
--- context/
-   --- requests/
-   -   --- .gitkeep
-   --- resolved/
-   -   --- .gitkeep
-   --- README.md
--- .keyhole/
    --- state/
    -   --- .gitkeep
    --- cache/
    -   --- .gitkeep
    --- README.md

This reference tree is part of the story contract.

18. Future Compatibility Hooks

This scaffold must prepare for later client stories without forcing structural redesign.

It must remain compatible with future:

local validation workflows,
capability passport workflows,
repo registration,
governed context lifecycle,
proof hot/cold population,
explainability and support surfaces.
Principle

The scaffold should prepare later stories without pretending to implement them.

19. Non-Goals

This story does not:

register a repo with MCP,
call the network by default,
compile live context,
execute governed runs,
ingest existing repos,
populate proof bundles from live events,
infer capabilities automatically,
expose memory primitives,
create authoritative platform truth.

It only creates the correct local starting shape.

20. Completion Signal

This story is complete when a new builder can run:

keyhole init vertical my-vertical

and get a repo that is:

canonically shaped,
declaration-ready,
context-ready,
proof-ready,
deterministic,
rerun-safe,
useful before live MCP dependency,
and honest about what has not happened yet.