# Launch Readiness Checklist

**Story:** CE-V5-S42-10  
**Purpose:** Concrete, reviewable launch gate for the developer kit  
**Last Updated:** 2026-07-06

---

## How to Use This Checklist

Each item is a specific, verifiable condition. A condition is either
**met** or **not met**. The developer kit is launch-grade only when every
required condition is met.

Items marked with `[S]` are scaffolded — they exist in shape but await
platform-side surface stabilization. Scaffolded items are not launch
blockers; they are tracked separately.

## Current Product Gate

The client repository is ready for public technical preview when the local
release gate and live blessed-path proof both pass. It should not be marketed
as a complete governed repo product until the outer product envelope is also
stable: clean-clone proof on supported operating systems, package install and
launcher smoke, generated-state sanitation, deterministic support guidance,
and server-advertised optional surfaces for explainability, support bundles,
run tail, budget visibility, and async accept.

Use the local gate before release:

```powershell
.\scripts\public-release-gate.ps1
```

If Windows script policy blocks direct execution:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\public-release-gate.ps1
```

After device login, use the live gate for a release-candidate proof:

```powershell
.\scripts\public-release-gate.ps1 -IncludeLiveProof
```

Only add `-RunGoverned` when a new live governed receipt is intentionally being
created. Generated `.keyhole/` and `proof_bundle/` artifacts are local runtime
state and must stay out of commits.

---

## 1. Repository Posture

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 1.1 | Boundary constitution exists | [boundary-constitution.md](boundary-constitution.md) is present and describes repo separation | MET |
| 1.2 | Repo is separate from keyhole_platform | No imports of private platform modules exist in SDK/CLI source | MET |
| 1.3 | Agent instructions are current | [.github/copilot-instructions.md](../.github/copilot-instructions.md) covers S42-06 dispatch safety, capabilities-first discovery, exact run-type discipline | MET |
| 1.4 | Contributing guidance exists | [CONTRIBUTING.md](../CONTRIBUTING.md) is present and current | MET |
| 1.5 | License is in place | [LICENSE](../LICENSE) exists (Apache-2.0) | MET |
| 1.6 | Security policy exists | [SECURITY.md](../SECURITY.md) exists | MET |

## 2. SDK and CLI Posture

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 2.1 | SDK is installable | `pip install -e packages/python/keyhole-sdk` succeeds | MET |
| 2.2 | CLI is installable | `pip install -e packages/python/keyhole-cli` succeeds | MET |
| 2.3 | SDK version is declared | `keyhole_sdk.__version__` returns `0.3.0` | MET |
| 2.4 | SDK requires Python >=3.9 | pyproject.toml declares `requires-python = ">=3.9"` | MET |
| 2.5 | SDK dependencies are minimal | Only `requests>=2.25` and `pydantic>=2.0` | MET |
| 2.6 | Public surface contract is documented | [public_surface_contract.md](specs/developer_ecosystem/public_surface_contract.md) exists | MET |

## 3. Connection Posture — Capabilities Discovery

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 3.1 | CapabilitiesClient exists | `from keyhole_sdk import CapabilitiesClient` succeeds | MET |
| 3.2 | Discovery is unauthenticated | `GET /mcp/v1/capabilities` does not require a bearer token | MET |
| 3.3 | Discovery returns contract version | `CapabilitiesResult.get_contract_version()` returns `mcp/v1` | MET |
| 3.4 | Discovery returns auth posture | `CapabilitiesResult.get_auth_flow()` returns auth flow type | MET |
| 3.5 | Discovery guidance is documented | [quickstart.md](quickstart.md) and [architecture.md](architecture.md) both reference discovery | MET |

## 4. Identity Posture — Auth and Identity Bootstrap

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 4.1 | Auth bootstrap guidance exists | [auth-bootstrap.md](auth-bootstrap.md) covers OIDC/PKCE for `keyhole-mcp` realm | MET |
| 4.2 | Identity inspection is documented | `GET /mcp/v1/whoami` is described as the first authenticated action | MET |
| 4.3 | Auth providers exist in SDK | `BearerTokenProvider`, `EnvironmentTokenProvider`, `CallbackTokenProvider` are importable | MET |
| 4.4 | Discovery comes before auth | Docs/instructions state discovery is unauthenticated and precedes authentication | MET |

## 5. Context Posture — Governed Context Retrieval

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 5.1 | ContextClient exists | `from keyhole_sdk import ContextClient` succeeds | MET |
| 5.2 | context.compile is supported | `ContextClient.compile_context()` dispatches `context.compile` run type | MET |
| 5.3 | Context-before-assumption is documented | Agent instructions and architecture docs require context retrieval before acting | MET |
| 5.4 | Context snapshot has accessors | `ContextSnapshot` provides `get_platform_name()`, `get_governance_model()`, etc. | MET |

## 6. Dispatch Safety Posture

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 6.1 | RunTypeValidator exists | `from keyhole_sdk import RunTypeValidator` succeeds | MET |
| 6.2 | SchemaHelper exists | `from keyhole_sdk import SchemaHelper` succeeds | MET |
| 6.3 | DispatchPreflight exists | `from keyhole_sdk import DispatchPreflight` succeeds | MET |
| 6.4 | Exact run-type discipline is documented | Agent instructions forbid guessing/pluralizing run-type names | MET |

## 7. Smoke Posture — Read-Only Smoke Path

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 7.1 | ReadOnlySmokeRunner exists | `from keyhole_sdk import ReadOnlySmokeRunner` succeeds | MET |
| 7.2 | Smoke path is 4-phase | Discovery, Identity, Context, ReadOnly Run | MET |
| 7.3 | Smoke path is read-only | Runner does not perform any mutations | MET |
| 7.4 | Smoke path usage is documented | [smoke.md](smoke.md) and `examples/python-client/smoke_readonly.py` exist | MET |
| 7.5 | SmokeResult provides all_passed | `SmokeResult.all_passed` and `SmokeResult.summary()` exist | MET |

## 8. Proof-Ready Scaffolding [S]

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 8.1 | Proof package exists | `keyhole_sdk.proof` is importable | MET |
| 8.2 | ParticipantContractPlaceholder exists | Model with participant identity shape is importable | MET |
| 8.3 | ProofBundlePlaceholder exists | Model with proof bundle shape is importable | MET |
| 8.4 | VerificationRunner exists | Runner with collector pattern is importable | MET |
| 8.5 | Adapter boundaries exist | `ContractRegistrationAdapter`, `ProofSubmissionAdapter`, `VerdictRetrievalAdapter` ABCs are importable | MET |
| 8.6 | All adapters return not-yet-available | Local adapters return `supported=False` | MET |
| 8.7 | Posture is clearly scaffolded | All proof models declare `SupportStatus.SCAFFOLDED` | MET |

## 9. Recursive Demo Readiness [S]

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 9.1 | DemoFlowRunner exists | `from keyhole_sdk import DemoFlowRunner` succeeds | MET |
| 9.2 | Demo workflow is documented | [recursive-demo.md](recursive-demo.md) describes 8-phase flow | MET |
| 9.3 | Operator runbook exists | [recursive-demo-operator-notes.md](recursive-demo-operator-notes.md) has step-by-step instructions | MET |
| 9.4 | Evidence map exists | [recursive-demo-evidence-map.md](recursive-demo-evidence-map.md) maps actions to evidence | MET |
| 9.5 | Handoff boundary is clearly marked | Handoff returns `scaffolded=True`, `supported=False` | MET |

## 10. Documentation Currentness

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 10.1 | README.md is current | Overview, quickstart steps, SDK examples, repo structure are accurate | MET |
| 10.2 | Quickstart is reproducible | Clone → compose up → curl identity/healthz/realize works | MET |
| 10.3 | Architecture docs are current | [architecture.md](architecture.md) describes public architecture | MET |
| 10.4 | Bridge contract is documented | [bridge-contract.md](bridge-contract.md) covers runtime bridge | MET |
| 10.5 | No legacy nested-SDK references | No docs reference the repo as a submodule of keyhole_platform | MET |
| 10.6 | Correct two-tier transport doctrine | VS Code MCP SSE transport (canonical main) and SDK/CLI REST/HTTP transport both documented; old SDK-internal SSE deprecated (not VS Code MCP SSE) | MET |

## 11. Test Coverage

| # | Condition | How to Verify | Status |
|---|-----------|---------------|--------|
| 11.1 | S42-03 capabilities tests pass | `test_s42_03_capabilities_discovery.py` | MET |
| 11.2 | S42-04 auth bootstrap tests pass | `test_s42_04_auth_bootstrap.py` | MET |
| 11.3 | S42-05 context retrieval tests pass | `test_s42_05_context_retrieval.py` | MET |
| 11.4 | S42-06 run-type safety tests pass | `test_s42_06_run_type_safety.py` | MET |
| 11.5 | S42-07 read-only smoke tests pass | `test_s42_07_read_only_smoke.py` | MET |
| 11.6 | S42-08 proof scaffolding tests pass | `test_s42_08_proof_ready_scaffolding.py` (73 tests) | MET |
| 11.7 | S42-09 demo readiness tests pass | `test_s42_09_recursive_demo_readiness.py` (94 tests) | MET |

---

## Checklist Summary

| Category | Items | Met | Scaffolded |
|----------|-------|-----|------------|
| Repository Posture | 6 | 6 | 0 |
| SDK and CLI | 6 | 6 | 0 |
| Capabilities Discovery | 5 | 5 | 0 |
| Auth and Identity | 4 | 4 | 0 |
| Context Retrieval | 4 | 4 | 0 |
| Dispatch Safety | 4 | 4 | 0 |
| Smoke Path | 5 | 5 | 0 |
| Proof Scaffolding | 7 | 7 | 7 |
| Demo Readiness | 5 | 5 | 5 |
| Documentation | 6 | 6 | 0 |
| Test Coverage | 7 | 7 | 0 |
| **Total** | **59** | **59** | **12** |

All 59 client launch-readiness conditions are met. 12 of those are scaffolded
features that exist in shape but await platform-side DEV-UX surface
stabilization.

**Client launch gate: PASSED.**

**Complete product marketing gate: TECHNICAL PREVIEW / EARLY ACCESS until the
server-side optional surfaces and clean-clone release proof are complete.**
