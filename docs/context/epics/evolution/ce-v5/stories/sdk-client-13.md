# SDK-CLIENT-13 - Proof Bundle Hot/Cold Split

**Status:** DRAFT  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (design + validation), Prod (governed promotion only; no uncontrolled canonical mutation)  
**Surface:** Client  
**Zipper Pair:** `sdk-server-13.md`  
**Purpose:** Define the client-side proof bundle contract that separates replay-critical hot proof artifacts from large or auxiliary cold evidence, so governed runs, registration flows, ingestion flows, and future SDK operations remain replayable, explainable, and efficient without forcing every consumer to load full extended evidence.

---

## 1. Story Purpose

SDK-CLIENT-13 defines how the SDK emits proof bundles that are:

- **replayable from a compact hot core**,
- **human-readable at the summary layer**,
- **digest-addressed for all large evidence**,
- **stable enough for deterministic comparison**,
- **small enough to remain useful in hot query paths**,
- **structured enough for downstream storage and verification**.

This story turns proof output from a loose folder of artifacts into a governed packaging contract.

The client must generate a bundle where:

- `core.json` contains the minimum replay-critical truth,
- `summary.md` explains the outcome in human-readable language,
- `diff.json` captures meaningful delta semantics where applicable,
- `extended/*` contains non-essential or large supporting evidence,
- all extended artifacts are content-addressed and referenceable,
- replay does **not** depend on loading all cold artifacts.

This story is foundational because the entire SDK zipper model depends on the principle:

```text
A zipper is not closed until it produces a replayable proof bundle.
```

---

## 2. Why This Story Exists

Without a hot/cold split, proof bundles tend to collapse into one of two bad outcomes:

### Bad Outcome A - Everything is hot

If every artifact is treated as equally important:

- hot query paths get bloated,
- proof retrieval becomes slow,
- large evidence degrades UX,
- replay-critical truth gets buried inside noise,
- SDK flows become heavy and adoption-hostile.

### Bad Outcome B - Everything is cold

If proof is treated as a bag of optional files:

- replay becomes brittle,
- deterministic verification becomes difficult,
- summaries drift from authoritative truth,
- failure and success become harder to compare,
- downstream server storage has no clear contract for what must remain immediately queryable.

SDK-CLIENT-13 exists to prevent both failures.

The client must define a disciplined proof package where:

- the hot core is enough to verify and replay the important outcome,
- the cold layer holds bulk evidence without blocking normal interaction,
- digests connect the two layers cleanly.

---

## 3. Story Goals

This story must make the following true:

- the client generates `core.json`, `summary.md`, `diff.json`, and `extended/*` deterministically,
- replay succeeds from the hot core alone for supported zipper classes,
- extended evidence is referenced by digest rather than embedded blindly into hot artifacts,
- large evidence does not block the hot query path,
- proof artifacts remain easy for humans to inspect locally,
- proof structure is stable across commands and story lines,
- server-side hot storage and cold reference storage can consume the client bundle without ambiguity.

---

## 4. Scope

### Included

- local proof bundle structure
- `core.json` contract
- `summary.md` contract
- `diff.json` contract
- `extended/*` contract
- digesting and manifesting of extended artifacts
- deterministic local generation rules
- replay rules from hot proof only
- zipper expectations against server hot/cold storage

### Excluded

- full explainability / support bundle UX beyond the proof contract
- remote proof query API behavior
- trust attestation policy beyond placeholder compatibility
- final marketplace-facing publication packaging
- arbitrary user-defined proof layouts

---

## 5. Canonical Proof Bundle Layout

Minimum client-side structure:

```text
proof_bundle/
  --- core.json
  --- summary.md
  --- diff.json
  --- manifest.json
  --- extended/
      --- <artifact-1>
      --- <artifact-2>
      --- ...
```

The client may include additional helper files where useful, but the above must remain canonical and stable.

### 5.1 Required files

- `core.json` - replay-critical truth
- `summary.md` - human-readable proof summary
- `diff.json` - structured delta from prior comparable state when applicable
- `manifest.json` - digest/address map for bundle contents, especially `extended/*`
- `extended/*` - large or auxiliary evidence not required for replay-critical validation

---

## 6. Hot vs Cold Semantics

## 6.1 Hot artifacts

Hot artifacts are:

- immediately queryable,
- replay-critical,
- small enough to retrieve cheaply,
- authoritative for core verification.

At minimum, hot artifacts are:

- `core.json`
- `summary.md`
- `diff.json`
- `manifest.json`

## 6.2 Cold artifacts

Cold artifacts are:

- useful,
- often large,
- not required for core replay,
- retrieved by reference when needed.

These belong under `extended/*`.

Examples of cold artifacts may include:

- large logs,
- graph snapshots,
- full request/response bodies beyond the hot-core requirement,
- verbose analysis outputs,
- large ingestion inventories,
- auxiliary diagnostics,
- screenshots or generated diagrams if later introduced.

## 6.3 Governing rule

Hot must be sufficient for replay.
Cold must remain addressable without being required for ordinary proof lookup.

---

## 7. `core.json` Contract

`core.json` is the authoritative replay-critical proof artifact.

It must contain enough information to answer:

- what operation happened,
- under what identity and repo context,
- what inputs governed it,
- what outcome occurred,
- what correlations/event lineage references exist,
- what extended artifacts exist and how to find them.

### 7.1 Minimum fields

Recommended minimum structure:

```json
{
  "proof_schema_version": "v1",
  "proof_kind": "sdk_client_proof",
  "command": "keyhole ...",
  "story_id": "SDK-CLIENT-13",
  "timestamp": "...",
  "repo": {
    "name": "...",
    "path": "..."
  },
  "identity_context": {
    "tenant_id": "...",
    "org_id": "...",
    "user_id": "...",
    "cohort_id": "...",
    "worker_id": "...",
    "workspace_id": "...",
    "purpose": "...",
    "origin": "..."
  },
  "operation": {
    "type": "...",
    "mode": "standard|shadow",
    "status": "ACCEPT|REJECT|DEFER|SUCCESS|FAILURE"
  },
  "correlation": {
    "correlation_id": "...",
    "request_id": "...",
    "idempotency_key": null
  },
  "server_refs": {
    "run_id": null,
    "event_refs": []
  },
  "summary_ref": "summary.md",
  "diff_ref": "diff.json",
  "manifest_ref": "manifest.json",
  "extended_refs": []
}
```

### 7.2 Rules

- `core.json` must be sufficient for deterministic replay-oriented verification of the command outcome.
- `core.json` must not require loading `extended/*` just to understand the core outcome.
- `core.json` must contain stable references to any large auxiliary artifacts.
- `core.json` must be machine-friendly and deterministic enough for golden-file testing.

---

## 8. `summary.md` Contract

`summary.md` is the human-readable explanation layer.

It must answer, in plain language:

- what the client attempted,
- what happened,
- whether the run/operation succeeded or failed,
- whether shadow mode was used,
- what the user should look at next,
- where extended evidence lives if needed.

### 8.1 Required properties

- easy for humans to read in terminal/editor/Git diff
- must not contradict `core.json`
- may omit bulky detail that lives in `extended/*`
- should include references to correlation/run/proof identifiers when useful

### 8.2 Summary principle

Show the outcome clearly.
Do not bury the human in raw JSON.

---

## 9. `diff.json` Contract

`diff.json` captures structured change where applicable.

Not every proof bundle will have a meaningful diff, but the file must still exist in canonical form.

### 9.1 Uses

- compare previous vs current generated artifacts
- compare previous vs current inferred state
- show what changed during scaffold/validation/registration/ingestion/run
- support human and machine diff inspection

### 9.2 If no diff exists

The file must still be valid and explicit, for example:

```json
{
  "has_diff": false,
  "reason": "no prior comparable state"
}
```

### 9.3 Rules

- never omit `diff.json`
- do not encode all bundle semantics into diff alone
- keep the structure deterministic

---

## 10. `manifest.json` Contract

`manifest.json` is the addressing map for the bundle.

It must include digest and metadata for all hot and cold artifacts, especially everything in `extended/*`.

### 10.1 Minimum structure

```json
{
  "schema_version": "v1",
  "bundle_digest": "sha256:...",
  "artifacts": [
    {
      "path": "core.json",
      "digest": "sha256:...",
      "class": "hot"
    },
    {
      "path": "extended/log.txt",
      "digest": "sha256:...",
      "class": "cold"
    }
  ]
}
```

### 10.2 Rules

- every artifact must be listed
- digests must be deterministic for content
- hot/cold class must be explicit
- manifest must allow later server-side by-reference storage

---

## 11. `extended/*` Contract

The `extended/*` directory holds large or auxiliary evidence.

### 11.1 Allowed contents

Examples include:

- verbose logs
- raw server responses
- large inferred graph payloads
- registry search results
- local scan inventories
- validation traces
- auxiliary diagnostics

### 11.2 Rules

- files in `extended/*` must be referenceable by digest via `manifest.json`
- replay must not depend on them for ordinary core verification
- large evidence must be separated here rather than embedded into `core.json`
- clients must never assume server hot storage will keep all extended artifacts inline

---

## 12. Replay Contract

This story's most important technical rule is:

```text
replay succeeds from core bundle only
```

That means:

- the hot proof core must be sufficient to reconstruct the important semantics of the operation,
- a verifier must not need to fetch all of `extended/*` just to confirm the governed outcome,
- summaries and diff references must be stable,
- extended evidence may enrich inspection, but not define the outcome.

### 12.1 Important nuance

"Replay succeeds" here means replay-critical truth is present and verifiable.
It does **not** mean every large auxiliary artifact must be hot-loaded at query time.

---

## 13. Local Generation Rules

The client must generate proof bundles deterministically.

### 13.1 Deterministic rules

For the same effective input and outcome:

- file set must be stable,
- structural fields must be stable,
- digests must be content-driven,
- placeholder or absent values must be explicit rather than omitted arbitrarily.

### 13.2 No hidden omissions

If a piece of expected evidence is unavailable, the client must:

- record that explicitly,
- not silently skip the field,
- preserve enough structure for tests and downstream storage.

### 13.3 Failure is not proofless

Failure outcomes must still emit a proof bundle.

---

## 14. Client Responsibilities

The client is responsible for:

- creating the canonical proof bundle structure,
- splitting hot vs cold evidence correctly,
- generating digests,
- writing `manifest.json`,
- making `summary.md` readable,
- ensuring `core.json` is replay-sufficient,
- ensuring bundle layout is deterministic,
- passing a server-consumable artifact contract to `sdk-server-13.md`.

The client is **not** responsible for:

- deciding final hot storage policy in the server,
- replacing server-side evidence addressing,
- inventing runtime lineage that was never observed,
- turning cold evidence into mandatory hot data.

---

## 15. Server Zipper Expectations (`sdk-server-13.md`)

The paired server story must provide:

- storage of hot proof core in a query-friendly path,
- storage of extended artifacts by reference/digest,
- proof retrieval semantics that do not require large cold artifacts inline,
- a stable storage contract for hot/cold separation.

The zipper is closed only when client and server together prove:

- replay succeeds from core bundle only,
- extended artifacts are addressable by digest,
- large evidence does not block the hot query path.

---

## 16. Proof / Tests

### 16.1 Local client tests

- `core.json` generated for successful command
- `core.json` generated for failed command
- `summary.md` generated and human-readable
- `diff.json` always present
- `manifest.json` lists all artifacts
- all extended artifacts hashed and referenced
- deterministic bundle layout for same input
- hot/cold class tagging correct

### 16.2 Zipper tests

- replay succeeds using `core.json` + hot metadata only
- extended artifacts are retrievable by digest/reference
- server stores hot vs cold according to contract
- large extended artifacts do not appear in hot retrieval path

### 16.3 Negative tests

- missing extended artifact referenced in manifest is caught
- malformed manifest rejected
- oversized evidence placed into hot path is rejected or corrected
- empty core bundle rejected

---

## 17. Acceptance Criteria

This story is complete only when all of the following are true:

1. the client generates `core.json`
2. the client generates `summary.md`
3. the client generates `diff.json`
4. the client generates `manifest.json`
5. the client generates `extended/*` for large or auxiliary evidence where applicable
6. replay succeeds from `core.json` and hot proof references only
7. extended artifacts are addressable by digest
8. large evidence is separated from the hot path
9. bundle structure is deterministic
10. server zipper proof demonstrates hot storage + cold reference behavior cleanly

---

## 18. Non-Goals

SDK-CLIENT-13 does **not**:

- define final explainability UX
- replace later support-bundle stories
- force all artifacts into one file
- allow hot proof to become bloated with logs
- require all cold evidence to be loaded eagerly
- define every future proof field for all future stories

---

## 19. Story Closure Statement

SDK-CLIENT-13 closes when proof bundles stop being "whatever files happened to be around" and become a governed client contract.

At closure, the client must be able to produce a bundle where:

```text
hot proof tells the truth quickly
cold evidence tells the rest when needed
```

That is the standard required for a replayable, scalable, adoption-safe builder boundary.
