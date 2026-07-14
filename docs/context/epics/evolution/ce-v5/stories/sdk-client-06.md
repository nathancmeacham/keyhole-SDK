# sdk-client-06.md

# SDK-CLIENT-06 - Local Validation Pipeline

**Story ID:** SDK-CLIENT-06 / sdk-client-06  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Surface:** Client / CLI / SDK Local Validation Boundary  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-06.md`  
**Depends On:** `sdk-client-02.md`, `sdk-client-03.md`, `sdk-client-04.md`, `sdk-client-10.md`, SDK-CLIENT master guidance  
**Precedes:** registration, capability resolution, alignment guidance, governed run submission, and other later flows that depend on trustworthy local readiness  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-06 establishes `keyhole validate` as the canonical **local validation and readiness gate** for repo participation.

Its purpose is to let a builder validate a repo locally before it attempts:

- registration,
- governed execution,
- capability resolution,
- or later remote participation flows.

This story must support two repo realities:

### 1.1 Native governed repo validation

For a Keyhole-native repo, the client must validate canonical governance files, dependency declarations, namespace correctness, compatibility declarations, and required scaffold shape.

### 1.2 Foreign repo advisory validation

For a foreign repo, the client must still provide deterministic, useful local readiness assessment without pretending the repo already failed a Keyhole contract it never claimed to implement.

This story exists to make validation:

- local-first,
- deterministic,
- repair-oriented,
- and honest about repo posture.

---

## 2. Core Thesis

Validation must not assume that every repo is already scaffolded and fully Keyhole-native.

The client must distinguish clearly between:

1. **Native governed validation**  
   A repo claims Keyhole structure and should be validated against native governance expectations.

2. **Foreign/advisory validation**  
   A repo does not yet claim native Keyhole structure and should be assessed for readiness and next steps without misleading "missing file = invalid governed repo" semantics.

3. **Readiness for later participation**  
   The client should say whether the repo is ready for:
   - native registration,
   - ingestion/alignment first,
   - governed runs,
   - or further repair.

The client must not flatten these into one generic fail state.

---

## 3. Why This Story Exists

Earlier stories establish:

- repo scaffold shape,
- namespace discipline,
- local governance/dependency schema validation rules.

This story turns those pieces into a coherent **local governance gate**.

Without SDK-CLIENT-06:

- malformed contracts reach the boundary too late,
- foreign repos get unhelpful hard-fail feedback,
- builders get slower and weaker feedback loops,
- proof starts too late in the lifecycle,
- and the SDK feels like a thin transport shell instead of a serious local governance tool.

This story makes validation the place where the builder can answer:

```text id="kk0qv2"
Is this repo structurally fit for the next governed step?

before touching the server.

4. Strategic Role

SDK-CLIENT-06 sits after local repo structure and naming law exist, and before meaningful remote participation.

Greenfield path
login
  ↓
init vertical
  ↓
validate   ? this story
  ↓
passport / registration / run / other governed flows
Foreign repo path
login
  ↓
ingest / observe repo
  ↓
validate current local posture   ? this story
  ↓
alignment / registration readiness / capability work

This story is local-first and must not depend on a live MCP server for its core value.

5. Scope

This client story covers:

the keyhole validate command,
local validation of native governance artifacts,
advisory readiness assessment for foreign repos,
local validation of required artifact files where applicable,
schema validation for governance contract and dependency declarations,
capability namespace validation,
compatibility and version rule checks,
deterministic error reporting,
repair suggestion generation,
validation artifact generation,
zipper alignment with optional remote validation/invariant enforcement later.

This story does not cover:

server persistence,
final server invariant enforcement,
registration,
governed run execution,
context compilation,
memory access,
marketplace or billing behavior,
automatic repo mutation.
6. User-Facing Command Contract
Canonical command
keyhole validate
Supported forms
keyhole validate
keyhole validate <path>
keyhole validate --json
keyhole validate --strict
keyhole validate --proof
keyhole validate --quiet
keyhole validate --mode native
keyhole validate --mode advisory
Command behavior

The command must:

locate the repo root,
determine or honor validation posture (native or advisory),
load relevant local artifacts and manifests,
run deterministic local checks,
summarize errors, warnings, and readiness posture,
emit repair guidance,
return a non-zero exit code on failure or not-ready states as policy defines,
optionally emit a validation artifact.
Recommended exit codes
0 - validation passed / acceptable advisory result
1 - validation failed / not ready
2 - repo root or required file resolution failure
3 - internal CLI/tooling failure
7. Validation Domains

The local validation pipeline must cover four mandatory domains.

7.1 Schema validation

For native repos, validate canonical Keyhole files such as:

keyhole.yaml
governance_contract.yaml
dependencies.yaml
capability_passport.yaml when present or required by repo posture

Checks include:

file presence where required,
parseable YAML/JSON,
required fields present,
required field types correct,
unsupported fields flagged per policy,
canonical schema version handling.
7.2 Dependency validation

Validate declared dependencies and dependency-like local inputs, including:

dependency object shape,
capability field presence,
provider field rules,
version / major-line expectations,
digest format when pinned,
duplicate dependency conflicts,
invalid provider or empty capability references.
7.3 Namespace validation

Validate capability names using the namespace rules established in sdk-client-03.md, including:

<domain>.<category>.<capability>.v<major> shape,
no illegal characters,
version suffix required,
deterministic rejection of malformed names.
7.4 Compatibility validation

Validate local compatibility posture and declarations, including:

incompatible major-line references,
missing compatibility metadata where required,
deprecated or conflicting version combinations,
invalid or contradictory compatibility declarations,
declared capability/dependency mismatches.
8. Repo Posture Awareness

The validator must understand both native scaffold rules and foreign-repo reality.

8.1 Native posture

For native repos, the validator should verify scaffold-aware expectations such as:

repo/
 --- keyhole.yaml
 --- governance_contract.yaml
 --- capability_passport.yaml   (required in some flows, optional in others)
 --- dependencies.yaml
 --- capabilities/
 --- src/
 --- tests/
 --- docs/
 --- proof_bundle/

It must know when missing artifacts are true validation failures.

8.2 Foreign posture

For foreign repos, the validator must not pretend native files are required merely because they do not exist.

Instead, it should report:

no native governance files present,
what local manifests and declarations were found,
what can be validated now,
what the readiness posture is,
what the next alignment step should be.
8.3 Important rule

The client must distinguish:

"missing required native file in a native repo"
from
"foreign repo not yet in native governed shape."
9. Validation Result Model

The client must produce a deterministic structured result.

Result classes
PASS
WARN
FAIL
Recommended posture/readiness fields
repo_posture
readiness
Example result shape
{
  "status": "FAIL",
  "repo_posture": "native",
  "readiness": "not_ready",
  "repo_root": "/path/to/repo",
  "checks": {
    "schema": "PASS",
    "dependencies": "FAIL",
    "namespace": "PASS",
    "compatibility": "WARN"
  },
  "errors": [
    {
      "code": "DEPENDENCY_PROVIDER_MISSING",
      "file": "dependencies.yaml",
      "path": "dependencies[1]",
      "message": "provider is required for this dependency class",
      "repair": [
        "add provider for crm.salesforce.sync.v2",
        "re-run keyhole validate"
      ]
    }
  ],
  "warnings": [],
  "proof_ref": null
}

Advisory example:

{
  "status": "WARN",
  "repo_posture": "foreign",
  "readiness": "partially_aligned",
  "checks": {
    "schema": "WARN",
    "dependencies": "PASS",
    "namespace": "WARN",
    "compatibility": "WARN"
  },
  "errors": [],
  "warnings": [
    {
      "code": "NATIVE_GOVERNANCE_FILES_ABSENT",
      "message": "Repo is not yet in native governed shape.",
      "repair": [
        "Run keyhole ingest .",
        "Review alignment guidance before native registration."
      ]
    }
  ]
}

The result model must be stable enough for:

CLI output,
JSON mode,
CI integration,
proof artifact inclusion,
later alignment flows.
10. Repair Guidance Contract

Validation failures and readiness blocks must not dead-end.

Every deterministic issue should, where possible, include:

a short reason,
exact file and field path when known,
a stable error code,
a suggested next action,
optional command-level follow-up guidance.
Example
{
  "code": "CAPABILITY_NAMESPACE_INVALID",
  "message": "Capability name must end in .v<major>",
  "repair": [
    "rename workorder.assignment.engine to workorder.assignment.engine.v1",
    "run keyhole validate again"
  ]
}

For foreign repos, guidance may instead be:

This repo is not yet in native governed shape.
Next steps:
- keyhole ingest .
- review compatibility posture
- follow alignment guidance

Repair guidance must always be concrete.

11. Strict vs Standard Validation
Standard mode

Standard mode should fail on deterministic structural violations and surface warnings for softer issues.

Strict mode

--strict elevates selected warnings into failures, for example:

strongly recommended metadata missing
unresolved compatibility hints
weak dependency declarations
proof folder missing in native posture
readiness conditions that policy wants to enforce more aggressively

Strict mode must remain deterministic and documented.

12. Artifact and Proof Output

On successful validation, and where appropriate on advisory runs, the client must be able to emit a local validation artifact.

Minimum deliverables

A validation artifact should contain:

validation timestamp
repo posture
readiness summary
repo root
checked files or sources
normalized check summary
final status
optional digest/correlation reference
Default artifact location

Because many repos may be foreign or not yet Keyhole-native, validation artifacts must not assume in-repo proof placement by default.

A reasonable default location is:

<tool-owned-state>/
  validation/
    validation_result.json
    validation_summary.md
    normalization_preview.json
Optional native mirror

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror validation artifacts into canonical in-repo proof locations.

13. Server Zipper Expectations (sdk-server-06.md)

This is the client half of a zipper.

Client responsibilities
catch deterministic local issues before network calls
reject malformed native repo state early
assess foreign repo posture honestly
emit a local validation artifact
normalize local output shape
Server responsibilities
optional remote validation
invariant enforcement hooks
final boundary truth when remote participation occurs
Closure principle

A repo that passes local validation may still fail remote validation if the server enforces stronger or newer invariants.

The client must not claim final authority.

14. Acceptance Criteria

This story is complete only when all of the following are true:

keyhole validate exists and runs locally without a live MCP server
schema validation catches malformed governed files deterministically
dependency validation catches malformed dependency/provider declarations deterministically
namespace validation applies canonical capability naming rules
compatibility checks detect invalid or contradictory compatibility posture
native repo failures block locally with non-zero exit code
foreign repos can receive honest advisory/readiness output instead of misleading native-only failure
validation failures include deterministic repair guidance
JSON output mode is stable and machine-readable
a passing or advisory run can emit a validation artifact
the client story aligns cleanly with sdk-server-06.md for later remote validation and invariant enforcement
15. Local Test Strategy
15.1 Positive tests
valid governed repo passes validation
valid scaffold from sdk-client-02 passes base checks
valid namespace and dependencies pass consistently
success artifact is written when requested or by default policy
15.2 Negative tests
malformed governance_contract.yaml rejected
malformed dependencies.yaml rejected
invalid capability namespace rejected
invalid compatibility declaration rejected
missing required file rejected in native mode
duplicate conflicting dependency declarations rejected
15.3 Foreign/advisory tests
foreign repo with no Keyhole files yields advisory posture rather than misleading hard failure
foreign repo dependency manifests are detected deterministically
advisory readiness output is stable across reruns
15.4 Output tests
JSON output shape remains stable
strict mode elevates selected warnings correctly
repair suggestions appear for supported failure classes
15.5 Determinism tests
same repo state and mode -> same validation outcome
same repo state and mode -> same normalized result structure
16. Error Classes (Minimum)

Suggested stable error codes include:

REPO_ROOT_NOT_FOUND
KEYHOLE_FILE_MISSING
SCHEMA_PARSE_ERROR
SCHEMA_REQUIRED_FIELD_MISSING
DEPENDENCY_PROVIDER_MISSING
DEPENDENCY_DUPLICATE_CONFLICT
CAPABILITY_NAMESPACE_INVALID
COMPATIBILITY_CONTRACT_INVALID
STRICT_MODE_WARNING_ESCALATED
NATIVE_GOVERNANCE_FILES_ABSENT
REPO_NOT_NATIVE_READY

These codes must be deterministic and suitable for CI, proof, and later explainability surfaces.

17. Non-Goals

This story does not:

perform server registration
perform remote invariant enforcement
compile context
execute governed runs
query or mutate memory
verify live registry/provider existence
silently mutate repo contracts
convert a foreign repo into a native repo automatically

This is a local-first validation and readiness gate.

18. Strategic Statement

SDK-CLIENT-06 is where the client stops being a scaffold generator and becomes a local governance tool.

It ensures the builder can answer, before touching the server:

Is this repo structurally fit for the next governed step?

That is the correct role of keyhole validate.

19. One-Line Summary

Implement keyhole validate as a deterministic local governance and readiness gate that enforces schema, dependency, namespace, and compatibility rules for native repos while giving foreign repos honest advisory posture and repair-oriented next steps before later MCP-bound flows.