# SDK-CLIENT-14 - Trust-Ready Metadata Hooks

**Status:** DRAFT  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (design + validation), Prod (governed promotion only; no uncontrolled canonical mutation)  
**Surface:** Client  
**Zipper Pair:** `sdk-server-14.md`  
**Purpose:** Define the client-side contract for optional trust-readiness metadata, including SBOM references, attestation references, transparency-log references, deterministic local validation when present, and preservation of those references across passports and proof bundles without making them mandatory for first-run success.

---

## 1. Story Purpose

SDK-CLIENT-14 establishes the client-side trust-readiness layer for the Keyhole SDK.

This story exists so that the SDK can carry the fields needed for future trust enforcement **now**, without turning first-run builder success into a compliance gauntlet.

The client must support:

- optional SBOM references,
- optional attestation references,
- optional transparency / Rekor-style references,
- deterministic validation when any of those fields are present,
- stable preservation of those references in generated client artifacts,
- transport-safe submission of those references to the server boundary,
- no regression to first-run adoption simplicity when those fields are absent.

This story is intentionally about **hooks and preservation**, not mandatory full trust enforcement.

---

## 2. Why This Story Exists

The revised SDK roadmap explicitly requires that trust metadata be schema-complete now even if hard enforcement is phased. The SDK must therefore be able to generate, carry, and validate trust-related references without forcing every builder to produce an SBOM or signed attestation before they can get value from Keyhole. fileciteturn0file0?

Without this story:

- passports and proof bundles would have no stable place to carry future trust references,
- later trust enforcement would require schema churn and migration pain,
- builders who already have SBOM / attestation pipelines would have no canonical way to attach those artifacts,
- the SDK would risk splitting into "simple now" and "serious later" shapes.

This story prevents that split.

It lets the platform say:

```text
trust metadata may be absent today
but the client contract is already ready for it
```

That is the correct adoption-first posture.

---

## 3. Story Goals

The client must provide:

- optional trust metadata placeholders in generated artifacts where appropriate,
- deterministic validation of trust fields when present,
- stable propagation of trust references into capability passports and proof bundles,
- digest/reference preservation without semantic drift,
- human-readable indication of whether trust metadata is present, absent, or malformed,
- no hard requirement that such metadata exist for first-run success.

This story does **not** require the client to generate a real SBOM, sign an attestation, or write to a transparency log on its own.

It only requires the client to be **trust-ready**.

---

## 4. Scope

### Included

- optional trust metadata fields in client-side artifacts
- local validation of trust metadata shape and digest/reference integrity when supplied
- propagation of trust metadata into:
  - `capability_passport.yaml`
  - proof bundle core and/or manifest references
  - request payloads where appropriate
- human-readable reporting of trust metadata presence
- zipper expectations against `sdk-server-14.md`

### Excluded

- mandatory SBOM generation
- mandatory signature generation
- mandatory transparency log submission
- platform-wide hard-gating on trust verification
- full trust policy enforcement at the client edge
- cryptographic attestation semantics beyond reference validation

---

## 5. Trust-Ready Design Principle

This story follows one critical adoption rule:

```text
trust readiness is required
trust completeness is not yet mandatory
```

That means:

- the fields must exist,
- the client must know how to validate them,
- the client must preserve them faithfully,
- the builder must be able to omit them for first-run success unless another story explicitly tightens that rule later.

---

## 6. Supported Trust Metadata Classes

The client must support the following trust metadata classes as optional references.

### 6.1 SBOM reference

Examples:

- digest of an SBOM artifact
- path reference to a generated SBOM file
- URI/reference to an external SBOM object

### 6.2 Attestation reference

Examples:

- signed attestation digest
- envelope reference
- predicate artifact digest/reference

### 6.3 Transparency / log reference

Examples:

- Rekor entry UUID
- transparency log record URI
- immutable external log record digest

### 6.4 Reserved future trust fields

The client contract may carry additional reserved fields for:

- provenance bundle references
- signature-set digests
- supply-chain policy results
- certification references

as long as they remain transport-safe and clearly optional.

---

## 7. Local Artifact Responsibilities

The client must ensure that trust-ready metadata can appear in the right places.

### 7.1 Capability passport

`capability_passport.yaml` must support trust reference fields or a dedicated trust section.

### 7.2 Proof bundles

Proof bundles must support preserving trust metadata references in one of the following forms:

- directly in `core.json` when replay-critical,
- in `manifest.json` / reference tables when large or auxiliary,
- in `extended/*` when the underlying evidence artifact itself is bundled locally.

### 7.3 Repo-level identity files

If repo-level files include trust metadata hooks, the client must preserve those fields without rewriting or losing them during generation/update flows.

---

## 8. Local Validation Contract

When trust metadata is present, the client must validate at minimum:

1. field presence under the canonical schema,
2. required field type,
3. digest format if a digest is supplied,
4. stable reference shape if a URI/path/entry id is supplied,
5. absence of silent truncation or mutation when written back to disk,
6. consistency across passport and proof references when the same artifact is referenced in both places.

If validation fails, the client must reject or flag the metadata deterministically.

If trust metadata is absent, the client must **not** fail the workflow solely on that basis at this stage.

---

## 9. Optionality Rules

### 9.1 Absent trust metadata

The absence of trust metadata must not block first-run success for this story line.

### 9.2 Present but invalid trust metadata

If a builder supplies trust metadata and it is malformed, the client must fail deterministically with repair guidance rather than silently dropping or normalizing it into garbage.

### 9.3 Present and valid trust metadata

If valid trust metadata is supplied, the client must preserve it exactly and propagate it into the correct downstream artifacts.

---

## 10. CLI / UX Expectations

The client may expose trust-related status through existing commands such as:

- `keyhole validate`
- `keyhole passport inspect`
- `keyhole proof inspect`

or later dedicated trust commands.

At minimum, the user must be able to see one of the following states:

- `trust: absent`
- `trust: present and valid`
- `trust: present but invalid`

The client must not imply that trust is "verified" merely because placeholder fields are present.

---

## 11. Example Trust Section Shape

An example trust section in a passport might look like:

```yaml
trust:
  sbom_digest: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  sbom_ref: ./proof_bundle/extended/sbom.cdx.json
  attestation_digest: sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  attestation_ref: ./proof_bundle/extended/attestation.json
  transparency_entry: rekor:123e4567-e89b-12d3-a456-426614174000
```

This is illustrative, not a frozen final schema, but the client story requires a canonical, tool-managed representation with deterministic validation semantics.

---

## 12. Propagation Rules

If trust metadata is present in local repo or builder inputs, the client must propagate it consistently.

### 12.1 Into capability passports

The passport must preserve the references without reinterpreting them semantically.

### 12.2 Into proof bundles

The proof bundle must preserve references so that downstream server surfaces can persist them or verify them later.

### 12.3 Into boundary payloads

Where the paired zipper story requires trust metadata transmission, the client must serialize those fields deterministically.

### 12.4 No silent dropping

The client must not silently omit present trust metadata because a downstream feature is not yet fully enforced.

---

## 13. Interaction With Other Stories

This story builds on and complements earlier client work:

- **SDK-CLIENT-02** scaffold must include trust-ready placeholder locations where required.
- **SDK-CLIENT-04** local schema validation must understand trust fields.
- **SDK-CLIENT-05** passport generation must preserve trust metadata.
- **SDK-CLIENT-06** validation pipeline must surface malformed trust fields.
- **SDK-CLIENT-13** proof hot/cold split must know where trust references live.

This story does not supersede those stories. It adds the trust-readiness layer across them.

---

## 14. Failure / Repair UX

If trust metadata validation fails, the client must emit repair guidance such as:

- invalid digest format,
- missing referenced artifact,
- conflicting digest/reference pair,
- unsupported field shape,
- transparency entry malformed.

Example failure shape:

```json
{
  "status": "REJECT",
  "reason": "invalid trust metadata",
  "repair": [
    "fix sbom_digest format",
    "ensure attestation_ref points to an existing artifact",
    "rerun keyhole validate"
  ]
}
```

The client must never collapse these into a generic "validation failed" without telling the builder what to fix.

---

## 15. Local Proof Contract

The client must emit enough local proof to show whether trust metadata was:

- absent,
- present and accepted,
- present and rejected.

### Minimum local proof outputs

Recommended additions to proof artifacts:

```text
proof_bundle/
  trust.json
  summary.md
```

Where `trust.json` contains:

- presence/absence state,
- validated digests/references,
- normalization outcome (if any),
- errors if rejected.

If integrated into broader proof artifacts instead, the same semantics must remain queryable.

---

## 16. Local Test Strategy

SDK-CLIENT-14 must support the following local tests.

### 16.1 Positive tests

- valid SBOM digest accepted
- valid attestation reference accepted
- valid transparency entry preserved
- valid trust metadata propagated into passport
- valid trust metadata preserved in proof bundle

### 16.2 Negative tests

- malformed digest rejected
- malformed transparency reference rejected
- missing referenced file rejected when validation requires existence
- conflicting duplicated trust fields rejected deterministically

### 16.3 Optionality tests

- no trust metadata present -> first-run flow still succeeds
- trust fields absent -> validation success artifact still emitted

### 16.4 Determinism tests

- same input trust metadata produces identical serialized output
- repeated generation does not mutate trust field ordering or values unexpectedly

---

## 17. Acceptance Criteria

This story is complete only when all of the following are true:

1. the client supports optional SBOM / attestation / transparency placeholders or references
2. trust-ready fields validate when present
3. malformed trust metadata is rejected deterministically with repair guidance
4. trust metadata remains optional for first-run success
5. digests / references are preserved in capability passports when supplied
6. digests / references are preserved in proof bundles when supplied
7. the client does not silently drop trust metadata
8. local proof artifacts can show absent vs valid vs invalid trust state
9. serialized trust metadata is deterministic for the same input
10. zipper expectations are satisfied for server-side acceptance and persistence

---

## 18. Zipper Expectations Against `sdk-server-14.md`

The paired server story must provide:

- acceptance of trust metadata references from the client,
- deterministic persistence of those references,
- no mutation of digest/reference values without explicit normalization rules,
- storage in the appropriate server-side record surfaces.

SDK-CLIENT-14 closes only when the paired server proof demonstrates:

- trust-ready fields validate when present,
- fields remain optional for first-run success,
- digests / references are preserved in passports and proof bundles.

---

## 19. Non-Goals

SDK-CLIENT-14 does **not**:

- require SBOM generation,
- require attestation signing,
- require transparency-log submission,
- declare trust verification complete,
- hard-gate first-run adoption on trust artifacts,
- replace later supply-chain or trust-enforcement work.

This is a schema/readiness story, not a full compliance story.

---

## 20. Story Closure Statement

SDK-CLIENT-14 closes when the client can truthfully say:

```text
if a builder already has trust artifacts
Keyhole can carry them lawfully today
```

and also:

```text
if a builder does not have trust artifacts yet
Keyhole still provides a successful first-run path
```

That is the correct trust-readiness posture for this phase of the SDK.
