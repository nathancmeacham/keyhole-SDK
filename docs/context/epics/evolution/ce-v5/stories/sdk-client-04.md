# sdk-client-04.md

# SDK-CLIENT-04 - Governance Contract + Dependency Schema

**Story ID:** SDK-CLIENT-04 / sdk-client-04  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, Repository Ingestion, and Scale-Safe Runtime UX  
**Status:** READY FOR IMPLEMENTATION  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (governed usage only; no uncontrolled canonical mutation)  
**Story Type:** Client-side zipper story  
**Surface:** Client / CLI / SDK Local Validation and Readiness Assessment  
**Paired Server Story:** `sdk-server-04.md`  
**Depends On:** `sdk-client-02.md`, `sdk-client-03.md`, `sdk-client-10.md`, SDK-CLIENT master guidance  
**Precedes:** registration, capability resolution, alignment guidance, and other flows that depend on deterministic local contract validation  
**Last Updated:** 2026-04-13

---

## 1. Purpose

SDK-CLIENT-04 establishes the client-side **governance contract and dependency schema validation layer**.

Its purpose is to let a builder run:

```text
keyhole validate

and receive a deterministic, repair-oriented answer about the repo's current governance readiness.

This story must support two different repo realities:

1.1 Keyhole-native repo validation

For a repo created through the governed scaffold path, the client must validate the canonical governance files and dependency declarations locally before later registration or governed execution flows.

1.2 Foreign repo advisory validation

For a repo that was built without Keyhole, the client must still provide useful local validation and readiness assessment without pretending the repo is already missing "required" Keyhole files in a failure sense.

In that case, validation should help answer:

what kind of repo is this,
whether it is Keyhole-native or foreign,
what contract/dependency structures are present,
what is missing,
what can be validated deterministically now,
and what the next alignment step should be.

This story exists to make the SDK responsible for first-pass structural correctness and readiness guidance rather than delegating all contract failure or all repo understanding to later server flows.

2. Core Thesis

Validation must not assume that every repo is already a scaffolded governed repo.

The client must distinguish clearly between:

Native governed validation
Validate canonical Keyhole declaration files against expected local schemas.
Foreign/advisory validation
Inspect and assess a non-Keyhole repo honestly without pretending it already failed a contract it never claimed to implement.
Readiness assessment
Report whether the repo is:
native-ready,
partially aligned,
foreign,
or not ready for the next governed step.

The client must never blur these categories.

3. Why This Story Exists

The scaffold story creates repo shape.
The namespace story creates stable naming law.

This story turns those pieces into a coherent local validation and readiness surface.

Without SDK-CLIENT-04:

a Keyhole-native repo may look valid but still contain malformed governance declarations,
a foreign repo may get only unhelpful "missing file" errors,
malformed dependencies are discovered too late,
provider ambiguity becomes harder to repair,
repair remains reactive instead of immediate,
the SDK feels brittle and server-dependent instead of disciplined and helpful.

This story makes keyhole validate the first real governance and readiness gate in the client experience.

4. Strategic Role

SDK-CLIENT-04 is foundational to both major paths.

4.1 Greenfield path
login
  ↓
init vertical
  ↓
validate governed contract + dependency schema   ? this story
  ↓
later registration / capability work / runs
4.2 Foreign repo path
login
  ↓
ingest / observe foreign repo
  ↓
validate current local contract/dependency posture   ? this story
  ↓
alignment guidance / registration readiness / capability work

This story is local-first and offline-capable.

The client owns first-pass validation UX and readiness reporting even though the server remains the final boundary authority later.

5. Scope

This client story covers:

local schema validation for native governance files,
advisory validation for foreign repos,
dependency declaration parsing,
normalization preview,
deterministic validation output,
readiness posture summary,
repair-oriented error reporting,
validation artifacts suitable for proof or later workflows,
preflight readiness for registration and other later actions.

This story does not cover:

server-side contract storage,
final boundary normalization authority,
remote policy checks,
actual registration,
governed run execution,
context compilation,
direct canonical memory access,
automatic repo mutation.

Those belong to later zipper or server stories.

6. Primary Client Deliverable

The client must implement:

keyhole validate

This command validates local repo governance and dependency shape according to the repo's current posture.

For Keyhole-native repos, it must validate files such as:
keyhole.yaml
governance_contract.yaml
capability_passport.yaml
dependencies.yaml
For foreign repos, it must still provide deterministic local assessment such as:
no native governance files present,
dependency manifests observed,
current readiness posture,
whether the repo should proceed through ingestion/alignment first,
what can be validated now versus later.

The command must produce a deterministic result with:

pass/warn/reject/readiness summary,
file-by-file or source-by-source status,
issue list,
repair guidance,
normalization preview where applicable.
7. Supported Validation Modes

The client should conceptually support these modes, even if surfaced through a single command.

7.1 Native governed validation

Use when the repo claims Keyhole-native structure.

Validate canonical governance and dependency files directly.

7.2 Foreign advisory validation

Use when the repo does not yet claim Keyhole-native structure.

Validate what is locally knowable without pretending missing Keyhole files are automatically hard failure.

7.3 Auto posture detection

The client may auto-detect posture from local files and repo state, as long as the selected posture is surfaced clearly.

For example:

Repo posture: foreign
Validation mode: advisory
Next step: keyhole ingest .

or:

Repo posture: native
Validation mode: governed
8. Client Responsibilities

The client implementation must provide the following capabilities.

8.1 Repo posture detection

The client must determine whether the repo is:

native
foreign
partially_aligned

This posture selection must be deterministic and visible in output.

8.2 File and source discovery

For native repos, locate canonical governance files.

For foreign repos, inspect local dependency and project structure sources without pretending the Keyhole files should already exist.

8.3 Schema parsing

Parse YAML or JSON safely and deterministically.

Required behavior:

reject invalid syntax
report exact file and field path where possible
distinguish missing vs malformed vs empty
distinguish unsupported schema from absent native structure
8.4 Governance contract validation

For native repos, validate governance_contract.yaml for:

required top-level keys
supported field types
valid local invariant list shape
valid required tests shape
valid produced capability declarations
valid compatibility contract declarations
8.5 Dependency schema validation

Validate dependencies.yaml when present, and/or equivalent dependency declaration surfaces when the repo is not fully native.

Checks include:

required dependency fields
canonical capability identifier format
provider field shape
optional digest shape
duplicate dependency handling
unsupported or ambiguous field combinations
8.6 Passport validation

Validate capability_passport.yaml for local structural correctness when it exists.

This story does not finalize trust or server lineage semantics, but it must ensure the file is structurally usable.

8.7 Normalization preview

The client must be able to preview how dependency/provider information will normalize before later boundary submission.

This matters for:

capability names
provider references
digest pinning
version/provider combinations
8.8 Repair-oriented output

Every validation failure or advisory readiness block must produce deterministic repair guidance.

9. Canonical Files and Validation Sources
9.1 keyhole.yaml

For native repos, validate minimal repo identity and SDK-managed metadata structure.

Expected checks include:

schema version
repo name
required repo metadata
file shape compliance
9.2 governance_contract.yaml

For native repos, validate relevant fields such as:

repo
parent_repo
produces
required_tests
local_invariants
compatibility_contracts
9.3 capability_passport.yaml

When present, validate:

capability identifier
owner repo
visibility
proof structure
delegated capability list shape
trust metadata placeholder structure
9.4 dependencies.yaml

When present, validate:

dependency list shape
capability identifiers
provider presence/optionality rules
digest formatting
deterministic field naming
9.5 Foreign repo dependency sources

For foreign repos, the client may also inspect dependency and topology sources such as:

package.json
requirements.txt
pyproject.toml
go.mod
pom.xml
and similar local manifests

This does not turn those into native Keyhole truth.
It only supports advisory validation and readiness reporting.

10. Command UX
10.1 Basic usage
keyhole validate
10.2 Possible posture-aware usage
keyhole validate .
keyhole validate --json
keyhole validate --mode advisory
keyhole validate --mode native

The exact flag set may evolve, but posture must remain explicit and deterministic.

10.3 Expected output classes

The command must support at least:

PASS
WARN
REJECT

and should also support a top-level posture/readiness summary such as:

native_ready
partially_aligned
foreign
not_ready
10.4 Human-readable summary example
Repo posture: native
✔ keyhole.yaml valid
✔ governance_contract.yaml valid
⚠ capability_passport.yaml missing optional trust metadata digests
✖ dependencies.yaml invalid: dependencies[0].provider missing

Foreign example:

Repo posture: foreign
ℹ No native Keyhole governance files detected
✔ Local dependency manifests detected
⚠ Repo not ready for native registration
Next step: keyhole ingest .
10.5 Machine-readable mode

The command should support a JSON output mode or equivalent structured result object suitable for:

CI
proof generation
local test assertions
later alignment workflows
10.6 Exit codes

Recommended behavior:

0 -> pass / acceptable advisory result
1 -> validation reject / not ready
2 -> internal CLI/runtime failure
11. Validation Semantics
11.1 Deterministic

The same repo contents and mode must produce the same validation result.

11.2 Local-first

The client must not require a live MCP server for baseline validation and readiness assessment.

11.3 Fail-closed where appropriate

Malformed or ambiguous contract data must not be silently corrected and treated as valid.

11.4 Advisory honesty

For foreign repos, missing native Keyhole files must be reported honestly without pretending that the repo "failed" a native contract it never claimed to implement.

11.5 Preview, not authority

The client may preview normalization, but the server remains the final normalization authority later.

12. Relationship to Server Pair (sdk-server-04.md)

This story is the client half of the zipper.

Client role
validate locally
catch malformed declarations early
preview normalized shapes
assess readiness honestly
prepare clean contract/dependency inputs for later server flows
Server role
ingest contracts
validate again at the boundary
normalize dependency/provider fields
persist accepted contracts
emit authoritative contract/registration events
Closure rule

This story is client-complete when local validation and readiness reporting are correct and replayable.

It is zipper-complete only when paired with sdk-server-04.md and proven end-to-end.

13. Suggested Structured Output Shape

Example result object:

{
  "status": "REJECT",
  "repo_posture": "native",
  "readiness": "not_ready",
  "repo": "workorder-platform",
  "files": {
    "keyhole.yaml": "PASS",
    "governance_contract.yaml": "PASS",
    "capability_passport.yaml": "WARN",
    "dependencies.yaml": "REJECT"
  },
  "issues": [
    {
      "file": "dependencies.yaml",
      "field": "dependencies[0].provider",
      "reason": "provider field missing",
      "repair": [
        "Add a provider for payment.stripe.integration.v1"
      ]
    }
  ],
  "normalization_preview": {
    "dependencies": []
  }
}

Foreign/advisory example:

{
  "status": "WARN",
  "repo_posture": "foreign",
  "readiness": "partially_aligned",
  "issues": [
    {
      "reason": "native_governance_files_absent",
      "repair": [
        "Run keyhole ingest .",
        "Review alignment guidance before native registration."
      ]
    }
  ]
}
14. Artifact and Proof Placement

Because many target repos will be foreign or not yet Keyhole-native, validation artifacts must not assume in-repo proof placement by default.

Default proof and validation artifacts should live in a tool-owned local state path.

If the repo is already Keyhole-native and the builder explicitly opts in, the client may additionally mirror validation artifacts into canonical in-repo proof locations.

Suggested local output shape
<tool-owned-state>/
  validation/
    validation_result.json
    validation_summary.md
    normalization_preview.json

These may be produced directly now or prepared as internal structures for later proof-bundle integration.

15. Repair Guidance Rules

The client must always fail with:

exact file or source when possible
exact field path when possible
deterministic reason
next-best repair guidance

Bad:

Validation failed.

Required shape:

{
  "status": "REJECT",
  "file": "dependencies.yaml",
  "field": "dependencies[1].provider",
  "reason": "provider field missing",
  "repair": [
    "Add a provider for crm.salesforce.sync.v2",
    "Use keyhole search crm.salesforce.sync.v2 to inspect eligible providers"
  ]
}

For foreign repos, repair guidance may instead be:

This repo is not yet in native governed shape.
Next steps:
- keyhole ingest .
- review compatibility posture
- follow alignment guidance
16. Local Test Strategy
16.1 Positive tests
valid keyhole.yaml passes
valid governance_contract.yaml passes
valid capability_passport.yaml passes structural validation
valid dependencies.yaml passes
complete scaffolded repo passes baseline native validation
16.2 Negative tests
missing required native file rejected in native mode
invalid YAML rejected
missing required top-level field rejected
invalid capability identifier rejected
invalid dependency/provider combination rejected
invalid digest shape rejected
16.3 Foreign/advisory tests
foreign repo with no Keyhole files yields advisory posture rather than misleading hard failure
foreign repo dependency manifests are detected deterministically
advisory readiness output is stable across reruns
16.4 Determinism tests
repeated validation of the same repo returns the same structured result
summary ordering is stable
normalization preview is stable
16.5 Proof-shape tests
structured validation result serializes cleanly
validation result and readiness posture can be embedded into later proof flows
16.6 Zipper tests

When paired later with sdk-server-04.md, the combined zipper must prove:

malformed contracts rejected
valid contracts accepted and stored
dependency/provider fields normalized
relevant contract evidence emitted
17. Acceptance Criteria

This story is complete only when all of the following are true:

keyhole validate parses and validates canonical governance files locally for native repos
the client can assess foreign repos honestly without pretending native failure by default
malformed contracts are rejected locally with deterministic reasons
valid contracts pass local validation
dependency/provider fields are parsed and presented in a normalization-friendly shape
capability identifiers inside contract files are validated using canonical namespace rules
the client surfaces repair guidance for every rejection or readiness-blocking outcome
validation output is deterministic and testable
the command can run fully without a live MCP server
validation results are available in structured form suitable for later proof generation
the client is ready to hand validated or assessed repo state to later ingestion, registration, and alignment flows
18. Non-Goals

This story does not:

perform server registration
persist contracts remotely
finalize provider resolution against the live registry
enforce trust metadata hard gates
compile governed context
execute governed runs
silently mutate repo contracts
convert a foreign repo into a native repo automatically
19. Completion Signal

SDK-CLIENT-04 is client-complete when a builder can run:

keyhole validate

and receive a deterministic, repair-oriented answer that correctly distinguishes between:

malformed contract
missing field
invalid namespace
bad dependency/provider shape
valid governed contract state
foreign repo advisory posture
next-best alignment step

It becomes zipper-complete when paired server validation proves that malformed contracts are rejected, valid ones are accepted, and dependency/provider fields normalize consistently.

20. One-Line Summary

Implement keyhole validate so builders can catch malformed governance and dependency contracts locally, get deterministic repair guidance, and receive honest readiness assessment for both scaffolded Keyhole-native repos and foreign repos before later MCP-bound flows.