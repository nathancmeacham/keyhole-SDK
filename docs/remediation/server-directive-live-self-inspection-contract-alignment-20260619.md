# CE-V5-S52-LIVE-SELF-INSPECT-C02 - Live Self-Inspection Contract Alignment

## Executive Summary

The live MCP self-inspection work has landed architecturally.

Verified live on 2026-06-19:

- Live auth works via `keyhole login --flow device --force`.
- `keyhole whoami --json` succeeds in real mode.
- `GET /mcp/v1/capabilities` returns `ok=true`.
- `operations_count=30`.
- `governance.self.inspect.v1`, `capability.invariants.list.v1`, and `governance.memory.explain.v1` are discoverable.
- All three are advertised as run-invoked through `/mcp/v1/runs/start`.
- All three report no operation-count impact.
- Authenticated live `POST /mcp/v1/runs/start` calls succeed for all three.

Verdict split:

- Server landing: PASS.
- Operation-budget doctrine: PASS.
- Runs/start doctrine: PASS.
- Strict AI-answerability contract: PARTIAL.
- Live contract verification: REJECT, contract-alignment class.

Do not roll back the server work. The remaining issues are precision issues in live response semantics and verifier interpretation.

## Live Evidence

Local evidence was written to:

```text
.keyhole/live-self-inspection-verification/latest.json
```

This directory is local live verification evidence and must not be committed as SDK source.

## Required Server/SDK Alignment

### 1. Stale Gap Handling

The verifier must stop requiring `gap_97715e2cd48b08bc` to be `OPEN`.

Acceptance criteria:

- PASS if `gap_97715e2cd48b08bc` is reported as `STALE` with provenance.
- PASS if stale gaps are not claimable.
- PASS if the server can identify the current claimable `my-first-app` gap or clearly return machine-readable "none currently claimable".
- FAIL only if stale status is hidden, misclassified, or treated as claimable.

### 2. Classification Taxonomies

Separate fact durability classification from semantic field provenance classification.

Fact durability values:

```text
durable
computed
derived
stale
unknown
client_derived
not_modeled
not_modelled
not_exposed
```

Semantic field provenance values:

```text
field_exists_and_populated
field_exists_but_empty
field_exists_with_default_unknown
field_computed_not_persisted
field_not_modelled
field_not_modeled
field_modeled_elsewhere
ambiguous_needs_decision
```

Acceptance criteria:

- The SDK verifier applies the fact enum only to material governance facts.
- The SDK verifier applies the semantic enum to semantic-memory provenance fields.
- Server responses do not mix these domains without schema/version guidance.

### 3. Semantic Memory Shape

`governance.memory.explain.v1` must return or be normalized into structured provenance fields:

```text
dominant_action
root_cause_class
repair_class
lesson_learned
invariant_learned
confidence
summary
```

Each field must be an object with at least:

```text
value
classification
source
confidence
```

Acceptance criteria:

- If the server already returns this data nested, document the canonical path and add an SDK normalization adapter.
- If the server does not return these fields structurally, adjust the response shape.
- Flat strings like `"dominant_action": "unknown"` are not sufficient.

### 4. Unknown Gap Semantics

Clarify broad inspection versus explicit subject lookup.

Acceptance criteria:

- Explicit subject lookup with `gap_id=gap_live_contract_unknown_should_not_exist` returns:

```text
ok=false
error.code=SUBJECT_NOT_FOUND
error.subject.type=gap
error.subject.id=gap_live_contract_unknown_should_not_exist
read_only=true
mutated=false
```

- Broad self-inspection may return `ok=true` only if the missing gap is represented in structured `unknowns[]` and the request was not treated as an explicit subject lookup.

## Retest Commands

```powershell
keyhole login --flow device --force
keyhole whoami --json
```

Then rerun the live self-inspection verification using authenticated `/mcp/v1/runs/start` calls for:

```text
governance.self.inspect.v1
capability.invariants.list.v1
governance.memory.explain.v1
```

No mocked verifier path should be used for this acceptance pass.
