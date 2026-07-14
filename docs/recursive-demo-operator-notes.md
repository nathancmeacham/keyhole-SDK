# Recursive Demo - Operator Runbook

**Story:** CE-V5-S42-09  
**Audience:** Human operator running the external-side recursive demo  
**Last Updated:** 2026-03-14

---

## Before You Begin

### Preconditions Checklist

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | MCP boundary reachable | `curl -s $MCP_URL/mcp/v1/capabilities \| head -1` | JSON response with `contract` field |
| 2 | Auth token available | `echo $TOKEN \| cut -c1-10` | Non-empty token prefix |
| 3 | Repo cloned and on correct branch | `git branch --show-current` | `demo/governance-posture-flag` or `main` |
| 4 | SDK installed | `python -c "import keyhole_sdk; print(keyhole_sdk.__version__)"` | `0.3.0` or later |
| 5 | CLI installed | `keyhole version` | Version output |
| 6 | Python version supported | `python --version` | 3.9 through 3.12 |
| 7 | Tests currently pass | `python -m pytest tests/unit/ -q` | All relevant tests pass |

If any precondition fails, resolve it before proceeding.

---

## Demo Execution Steps

### Step 1 - Discover Boundary Capabilities

**What you are doing:** Retrieving live boundary truth before any action.

```bash
python -c "
from keyhole_sdk import CapabilitiesClient
with CapabilitiesClient('$MCP_URL') as client:
    caps = client.fetch()
    print('=== Capabilities Discovery ===')
    print(f'Contract: {caps.get_contract_version()}')
    print(f'Auth: {caps.get_auth_flow()}')
    print(f'Transport: {caps.get_transport()}')
    print(f'Surfaces: {caps.get_implemented_context_surfaces()}')
    print('DISCOVERY: OK')
"
```

**Checkpoint:** You should see `DISCOVERY: OK` with contract version `mcp/v1`.

**If it fails:**
- Connection refused -> Check `$MCP_URL` and network access
- Malformed response -> Boundary version mismatch; check compatibility
- Timeout -> Network latency; increase timeout or check connectivity

---

### Step 2 - Inspect Identity

**What you are doing:** Confirming authenticated participant identity.

```bash
python -c "
import requests
resp = requests.get(
    '$MCP_URL/mcp/v1/whoami',
    headers={'Authorization': 'Bearer $TOKEN'},
    timeout=15,
)
print(f'Status: {resp.status_code}')
if resp.status_code == 200:
    print(f'Identity: {resp.json()}')
    print('IDENTITY: OK')
else:
    print(f'Error: {resp.text}')
    print('IDENTITY: FAILED')
"
```

**Checkpoint:** Status 200, participant identity returned, `IDENTITY: OK`.

**If it fails:**
- 401 -> Token expired or invalid; re-authenticate via OIDC/PKCE
- 403 -> Token valid but insufficient authority; check charter posture
- Connection error -> Network issue; retry Step 1 first

---

### Step 3 - Retrieve Governed Context

**What you are doing:** Getting platform truth to inform the change.

```bash
python -c "
from keyhole_sdk import ContextClient
with ContextClient('$MCP_URL', token='$TOKEN') as ctx:
    snapshot = ctx.compile_context()
    print('=== Governed Context ===')
    print(f'Platform: {snapshot.get_platform_name()}')
    print(f'Model: {snapshot.get_governance_model()}')
    print(f'Contract: {snapshot.get_mcp_contract()}')
    print(f'Surfaces: {snapshot.get_implemented_surfaces()}')
    print('CONTEXT: OK')
"
```

**Checkpoint:** Platform name and governance model returned, `CONTEXT: OK`.

**If it fails:**
- Auth error -> Token expired between steps; re-authenticate
- Schema error -> Boundary version mismatch; check SDK compatibility
- Transport error -> Network issue

---

### Step 4 - Confirm Participant Posture

**What you are doing:** Verifying the participant's identity and readiness.

```bash
python -c "
from keyhole_sdk.proof import ParticipantContractPlaceholder
contract = ParticipantContractPlaceholder()
print('=== Participant Posture ===')
print(f'Name: {contract.participant_name}')
print(f'Type: {contract.participant_type}')
print(f'Posture: {contract.compatibility_posture}')
print(f'Status: {contract.support_status.value}')
print(f'Verification classes: {contract.verification_classes}')
print('POSTURE: OK')
"
```

**Checkpoint:** Participant name is `keyhole-developer-kit`,
posture is `boundary-consuming`, `POSTURE: OK`.

---

### Step 5 - Apply the Demo-Safe Change

**What you are doing:** Creating and committing the demo change.

```bash
# Ensure you are on the demo branch
git checkout -b demo/governance-posture-flag 2>/dev/null || git checkout demo/governance-posture-flag

# The demo change: adding --governance flag to keyhole version
# (This step applies the specific code change for the demo)

git add -A
git commit -m "feat: add --governance flag to keyhole version

Adds a governance posture display to the version command.
Shows participant identity, boundary-consuming posture,
and proof-ready support status.

Story: CE-V5-S42-09"
```

**Checkpoint:** Clean commit on `demo/governance-posture-flag` branch.

**If it fails:**
- Nothing to commit -> Change not applied; verify the code modification
- Merge conflict -> Wrong branch; start fresh from `main`

---

### Step 6 - Run Local Verification

**What you are doing:** Executing verification collectors and assembling results.

```bash
python -c "
from keyhole_sdk.demo import DemoFlowRunner

demo = DemoFlowRunner(base_url='$MCP_URL', token='$TOKEN')
result = demo.run_verification()

print('=== Verification Results ===')
for v in result.verification_outputs:
    status = 'PASS' if v.passed else 'FAIL'
    print(f'  [{status}] {v.verification_class}: {v.passed_tests}/{v.total_tests}')
print(f'All passed: {result.all_passed}')
print(f'VERIFICATION: {\"OK\" if result.all_passed else \"FAILED\"}'  )
"
```

**Checkpoint:** All verification classes pass, `VERIFICATION: OK`.

**If it fails:**
- Test failures -> Inspect error summaries; fix before proceeding
- Collector exception -> Check runner registration; see error_summary field

---

### Step 7 - Assemble Proof Bundle

**What you are doing:** Packaging verification results into a proof-ready artifact.

```bash
python -c "
from keyhole_sdk.demo import DemoFlowRunner

demo = DemoFlowRunner(base_url='$MCP_URL', token='$TOKEN')
bundle = demo.assemble_proof_bundle()

print('=== Proof Bundle ===')
print(f'Participant: {bundle.participant_name}')
print(f'Commit: {bundle.source_commit[:12]}...')
print(f'Ref: {bundle.source_ref}')
print(f'Environment: {bundle.environment}')
print(f'SDK: {bundle.sdk_version}')
print(f'Python: {bundle.python_version}')
print(f'Assembled at: {bundle.assembled_at}')
print(f'Verifications: {bundle.verification_summary}')
print(f'Status: {bundle.support_status.value}')
print('BUNDLE: OK')
"
```

**Checkpoint:** Bundle contains commit SHA, verification summary,
participant metadata. `BUNDLE: OK`.

---

### Step 8 - Attempt Handoff (Scaffolded)

**What you are doing:** Demonstrating the handoff boundary to platform-side
governance flows.

> **This step is scaffolded.** The adapter returns `supported=False` until
> DEV-UX surfaces stabilize.

```bash
python -c "
from keyhole_sdk.demo import DemoFlowRunner

demo = DemoFlowRunner(base_url='$MCP_URL', token='$TOKEN')
result = demo.submit_proof()

print('=== Handoff Attempt ===')
print(f'Supported: {result.supported}')
print(f'Reason: {result.reason}')
print()
print('--- PARTICIPANT SIDE COMPLETE ---')
print('The external participant has completed its workflow.')
print('When DEV-UX surfaces stabilize, this handoff will')
print('submit to the platform proof pipeline.')
"
```

**Checkpoint:** `supported=False` with clear explanation. This is correct
behavior for the current stage.

---

## Where the Participant Stops

After Step 8, the external participant side is complete.

**Everything from here requires platform-side DEV-UX surfaces.**

The handoff boundary is:

```
---------------------------------------------------
-                                                 -
-   PARTICIPANT SIDE (developer kit)              -
-   Steps 1-8: All executable now                 -
-                                                 -
-   Discovery -> Context -> Posture -> Change ->      -
-   Verify -> Bundle -> Handoff Attempt             -
-                                                 -
-------- HANDOFF BOUNDARY -------------------------
-                                                 -
-   PLATFORM SIDE (DEV-UX)                        -
-   Steps 9+: Awaiting surface stabilization      -
-                                                 -
-   Contract intake -> Proof intake ->              -
-   Verification graph -> Verdict ->                -
-   Promotion/Rejection -> Console visibility      -
-                                                 -
---------------------------------------------------
```

---

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Connection refused` | Wrong MCP_URL or boundary down | Verify URL and boundary health |
| `401 Unauthorized` | Token expired or wrong realm | Re-authenticate via OIDC/PKCE for `keyhole-mcp` |
| `403 Forbidden` | Valid token, insufficient authority | Check charter posture |
| `SchemaError` | SDK/boundary version mismatch | Update SDK or check boundary version |
| `supported=False` on handoff | Expected - DEV-UX not yet stable | This is correct current behavior |
| Tests fail in Step 6 | Code change introduced regression | Review test output, fix change |
| Git commit fails | No changes or wrong branch | Verify demo change was applied |
| `ModuleNotFoundError` | SDK not installed | Run `pip install -e packages/python/keyhole-sdk` |

---

## After the Demo

1. Record which steps succeeded and which were scaffolded
2. Save the proof bundle output for later submission when DEV-UX stabilizes
3. Note the commit SHA for provenance tracking
4. Return to `main` branch: `git checkout main`

---

## Evidence Expectations

See [recursive-demo-evidence-map.md](recursive-demo-evidence-map.md) for
the full mapping from participant actions to expected platform-side evidence.
