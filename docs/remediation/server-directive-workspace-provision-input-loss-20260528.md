# Server Directive - workspace.provision Input Loss in Two-Plane Executor (2026-05-28)

**Priority:** CRITICAL  
**Status:** RESOLVED - fixed in commit to main on 2026-06-03  
**Realm:** `kh-prod`  
**Platform:** `https://mcp.keyholesolution.com`  
**Raised by:** SDK client investigation - session `982489b3-e0d2-470e-858f-0cac6e22c04f`  
**Raised:** 2026-05-28T09:55Z  
**Blocking:** Full gap->claim->workspace->proof chain (final server-side blocker)  
**Related:** `server-directive-workspace-provision-result-ttl-20260527.md` (closed - v295 fixed result visibility)

---

## Summary

The `workspace.provision` two-plane executor does **not forward the `input` field** from the dispatch payload to the `WorkspaceProvisionParams` Pydantic validator. The validator always receives `{}` (empty dict) regardless of what was sent in the `input` field at dispatch time.

`gaps.claim` uses the same two-plane executor and correctly forwards `input` to its handler - so this is isolated to the `workspace.provision` handler.

---

## Evidence

### Run IDs showing input_value={}

| Run ID | Shape | Exact JSON sent | Server received | Result |
|---|---|---|---|---|
| `run_f44dcc443ab9` | with repo | `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"repo": "...", "gap_id": "..."}}` | `{}` | NO `INVALID_PARAMETERS` |
| `run_76702bb7b859` | with repo | `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"repo": "...", "gap_id": "..."}}` | `{}` | NO `INVALID_PARAMETERS` |
| `run_57e07a3a2cb8` | with repo | `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"gap_id": "..."}}` | `{}` | NO `INVALID_PARAMETERS` |
| `run_d6578f865415` | with repo | `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"gap_id": "...", "claim_token": "7c8630..."}}` | `{}` | NO `INVALID_PARAMETERS` |
| `run_f72621fd7181` | **no top-level repo** | `{"run_type": "workspace.provision", "input": {"gap_id": "...", "claim_token": "427901ba..."}}` | `{}` | NO `INVALID_PARAMETERS` |
| `run_2318e3313f67` | **with top-level repo** | `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"gap_id": "...", "claim_token": "427901ba..."}}` | `{}` | NO `INVALID_PARAMETERS` |

Runs `run_f72621fd7181` and `run_2318e3313f67` were dispatched on 2026-05-28T14:33Z with:
- **Fresh login** immediately before
- **Fresh claim_token** (`427901ba251f07de2de4cbb847ac9956`) extracted live from `gaps.claim` result in the same session
- **Logged wire format** (see `probe-live-20260528.txt`) confirming the exact bytes sent
- **Both shapes tested**: with and without top-level `"repo"` - both return `input_value={}`

This rules out all probe-side issues:
- OK claim_token is live and correct (not hardcoded, not expired)
- OK gap_id is present in input
- OK Both payload shapes tested
- OK Wire format logged and verified
- NO Server always calls `WorkspaceProvisionParams(**{})` regardless of input

### Exact pydantic error from every workspace.provision dispatch

```
2 validation errors for WorkspaceProvisionParams
gap_id
  Field required [type=missing, input_value={}, input_type=dict]
repo
  Field required [type=missing, input_value={}, input_type=dict]
```

The `input_value={}` is the dict that Pydantic received - always empty.

### Dispatch wire format (confirmed correct)

```json
POST /mcp/v1/runs/start
{
  "run_type": "workspace.provision",
  "repo": "my-first-app",
  "input": {
    "gap_id": "gap_810669d1c41e2041",
    "claim_token": "7c8630a3d1d888611a8690b90a6a55db"
  }
}
```

### Contrast: gaps.claim works correctly

```json
POST /mcp/v1/runs/start
{
  "run_type": "gaps.claim",
  "repo": "my-first-app",
  "ctxpack_digest": "7b8c7543...",
  "input": {
    "gap_id": "gap_810669d1c41e2041"
  }
}
```

-> Returns `gap_id`, `claim_token`, `ticket_packet`, `claim_expires_ts` correctly. `input` forwarding works.

### Active claim context

At time of investigation:
- Gap: `gap_810669d1c41e2041` (capability `my-first-app.greet.user.v1`)
- Status: `CLAIMED` - confirmed by `GAP_NOT_CLAIMABLE (CURRENTLY_CLAIMED by c2a432d8-...)` error on re-claim
- `claim_token`: `7c8630a3d1d888611a8690b90a6a55db`
- `claim_expires_ts`: `2026-05-28T10:02:34.584884+00:00`

---

## Root Cause Hypothesis

The `workspace.provision` run-type handler reads its parameters from the wrong source.

Compare the likely code path for the two run types:

**gaps.claim (working):**
```python
# handler reads from run.input or run_context.input
params = GapsClaimParams(**(run.input or {}))
```

**workspace.provision (broken):**
```python
# handler accidentally reads from run.context, run.params, or a missing field
params = WorkspaceProvisionParams(**(run.context or {}))  # bug: always {}
# should be:
params = WorkspaceProvisionParams(**(run.input or {}))    # correct
```

**Likely root cause:** The `workspace.provision` handler uses a different variable name or attribute path to access `input` compared to `gaps.claim`. The variable resolves to `None`/`{}` at runtime, so Pydantic sees an empty dict.

**Where to look in platform source:**
- The `workspace.provision` run-type handler class or function
- The two-plane executor's worker dispatch - how it extracts and passes `input` to the handler
- Any difference in how `workspace.provision` was registered vs `gaps.claim`

---

## Impact

Without this fix:
- `workspace.provision` cannot be executed by any external client
- The gap->claim->workspace->proof chain is completely blocked at the workspace step
- The claim expires after 15 minutes, after which a new claim is needed

`gaps.claim` is now working correctly (v295 fix confirmed OK). This is the **only remaining server-side blocker**.

---

## What the Backend Team Must Do

### Action (CRITICAL) - Fix workspace.provision handler to read from `input`

In the `workspace.provision` handler, ensure parameters are extracted from `run.input` (or whatever field stores the user-supplied `input` dict from the dispatch payload):

```python
# Correct pattern (matching gaps.claim)
params = WorkspaceProvisionParams(**(run.input or {}))

# The broken pattern (likely current code for workspace.provision)
params = WorkspaceProvisionParams(**(run.context or {}))  # or run.params, run.data, etc.
```

The fix should take <5 minutes once the incorrect field name is identified.

---

## Acceptance Criteria

1. `POST /mcp/v1/runs/start` with `{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"gap_id": "gap_810669d1c41e2041", "claim_token": "<token>"}}` returns `status: "completed"` (not `INVALID_PARAMETERS`)
2. `GET /mcp/v1/runs/<run_id>` returns a successful result within 5s
3. After successful provision, `keyhole whoami` shows a non-neutral `workspace_id`

---

## Reproduction Steps

```bash
# 1. Claim the gap (working)
keyhole gaps claim --gap-id gap_810669d1c41e2041 --json
# -> claim_token: <token>

# 2. Provision workspace (BROKEN - always INVALID_PARAMETERS)
keyhole workspace provision --repo my-first-app --gap-id gap_810669d1c41e2041 --claim-token <token> --json
# -> INVALID_PARAMETERS: input_value={}
```

Or directly via API:
```bash
curl -X POST https://mcp.keyholesolution.com/mcp/v1/runs/start \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"run_type": "workspace.provision", "repo": "my-first-app", "input": {"gap_id": "gap_810669d1c41e2041", "claim_token": "<claim_token>"}}'
# -> accepted run_id
# Poll -> INVALID_PARAMETERS: input_value={}
```
