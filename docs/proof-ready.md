# Proof-Ready Participant Scaffolding

**Story:** CE-V5-S42-08  
**Status:** Scaffolded - not yet live  
**Last Updated:** 2026-03-14

---

## Overview

The developer kit is now proof-ready: it contains structured scaffolding
for future recursive-governance participation without prematurely coupling
to unstable platform internals.

This document explains what is supported today, what is scaffolded for
later, and why the separation matters.

---

## What Is Supported Now

These flows are live, tested, and safe for production use:

| Flow | SDK Surface | Status |
|------|-------------|--------|
| Capabilities discovery | `CapabilitiesClient`, `CapabilitiesResult` | **Supported** |
| Auth / identity bootstrap | `AuthProvider`, `KeyholeClient`, `GET /mcp/v1/whoami` | **Supported** |
| Governed context retrieval | `ContextClient`, `ContextSnapshot` | **Supported** |
| Run-type safety | `RunTypeValidator`, `DispatchPreflight`, `SchemaHelper` | **Supported** |
| Read-only smoke path | `ReadOnlySmokeRunner`, `SmokeResult` | **Supported** |

These are the current operational capabilities of the developer kit as
an external participant.

---

## What Is Scaffolded for Later

These surfaces exist in `keyhole_sdk.proof` as provisional placeholders.
They define the *shape* of future participation without claiming that the
platform-side surfaces they depend on are already stable.

| Surface | Module | Depends On | Status |
|---------|--------|-----------|--------|
| Participant contract posture | `ParticipantContractPlaceholder` | DEV-UX-03 | **Scaffolded** |
| Verification runner | `VerificationRunner` | DEV-UX-04 | **Scaffolded** |
| Proof-bundle assembly | `ProofBundlePlaceholder` | DEV-UX-04 | **Scaffolded** |
| Contract registration adapter | `ContractRegistrationAdapter` | DEV-UX-03 | **Scaffolded** |
| Proof submission adapter | `ProofSubmissionAdapter` | DEV-UX-04 | **Scaffolded** |
| Verdict retrieval adapter | `VerdictRetrievalAdapter` | DEV-UX-06 | **Scaffolded** |

### What "Scaffolded" Means

- The module shape exists and is deliberate
- Extension points and adapter boundaries are defined
- No live platform integration is attempted
- No unstable platform internals are hardcoded
- The scaffold will evolve when the platform surface it depends on stabilizes

---

## What Is Not Yet Claimed

The scaffolding does **not** mean:

- Live contract registration is complete
- Live proof submission is operational
- Promotion participation is live
- Verdict/repair handling is finalized
- Final proof schemas are locked
- Final participant contract schemas are locked

These remain downstream and platform-dependent.

---

## Architecture: Why Adapters Exist

Future integration points are isolated behind adapter interfaces:

```
----------------------------
-   VerificationRunner     -  ? local-only operations
-   (collect, normalize)   -
----------------------------
           -
           ▼
----------------------------
-   ProofBundlePlaceholder -  ? local assembly
-   (provisional shape)    -
----------------------------
           -
     --------------
     ▼            ▼
-----------  ------------  ----------------
- Contract-  -  Proof   -  -   Verdict    -
- Regist. -  - Submis.  -  -  Retrieval   -
- Adapter -  - Adapter  -  -   Adapter    -
-----------  ------------  ----------------
     -            -               -
     ▼            ▼               ▼
  DEV-UX-03    DEV-UX-04       DEV-UX-06
  (planned)    (planned)       (planned)
```

The adapters isolate platform integration so that:

1. Current supported flows remain clean and honest
2. When DEV-UX surfaces stabilize, only the adapter implementations
   need to change - not the runner, models, or rest of the SDK
3. The developer kit remains boundary-consuming, not boundary-defining

This is a sign of correct architecture, not incompleteness.

---

## Boundary Posture

All proof-ready scaffolding follows these rules:

- **Boundary-consuming:** The developer kit prepares to *consume*
  future platform surfaces. It does not *define* them.
- **No private-source coupling:** No unstable platform internals,
  private request contracts, or volatile source-level assumptions
  are hardcoded.
- **Provisional shapes:** All placeholder models are explicitly
  marked as provisional and will evolve with platform stabilization.
- **Adapter isolation:** Future integration is isolated behind
  narrow adapter interfaces to minimize coupling.

---

## SDK Usage (Local-Only)

### Participant Contract Placeholder

```python
from keyhole_sdk.proof import ParticipantContractPlaceholder

contract = ParticipantContractPlaceholder()
print(contract.participant_name)       # "keyhole-developer-kit"
print(contract.support_status)         # SupportStatus.SCAFFOLDED
print(contract.verification_classes)   # ["unit-tests", ...]
```

### Verification Runner

```python
from keyhole_sdk.proof import VerificationRunner, VerificationOutput

def my_test_collector():
    # Run your tests, return normalized output
    return VerificationOutput(
        verification_class="unit-tests",
        passed=True,
        total_tests=42,
        passed_tests=42,
    )

runner = VerificationRunner()
runner.register_collector("unit-tests", my_test_collector)
bundle = runner.run()

print(bundle.verification_summary)    # {"total_verifications": 1, ...}
print(bundle.support_status)          # SupportStatus.SCAFFOLDED
```

### Adapter Status Check

```python
from keyhole_sdk.proof.adapters import (
    LocalProofSubmissionAdapter,
    LocalContractRegistrationAdapter,
)

adapter = LocalProofSubmissionAdapter()
result = adapter.submit(bundle)
print(result.supported)   # False
print(result.reason)      # "Proof submission is not yet available..."
```

---

## For Future Builders

When platform-side surfaces stabilize, integration proceeds by:

1. Implementing concrete adapter classes that talk to the live surfaces
2. Updating placeholder models if the platform publishes final schemas
3. Connecting the verification runner to the submission adapter
4. Replacing `SupportStatus.SCAFFOLDED` with `SupportStatus.SUPPORTED`
   on surfaces that become fully operational

The scaffolding is designed to make this transition local and safe.

---

## Related Stories

| Story | Title | Relationship |
|-------|-------|-------------|
| CE-V5-S42-01 | Boundary Constitution | Foundation doctrine |
| CE-V5-S42-03 | Capabilities Discovery | Supported now |
| CE-V5-S42-04 | Auth & Identity Bootstrap | Supported now |
| CE-V5-S42-05 | Context Retrieval Bootstrap | Supported now |
| CE-V5-S42-06 | Run-Type Safety | Supported now |
| CE-V5-S42-07 | Read-Only Smoke Path | Supported now |
| **CE-V5-S42-08** | **Proof-Ready Scaffolding** | **This story** |
| DEV-UX-03 | Participant Contract Registry | Future - consumes scaffold |
| DEV-UX-04 | Proof Submission Pipeline | Future - consumes scaffold |
| DEV-UX-06 | Structured Verdict & Repair | Future - consumes scaffold |
