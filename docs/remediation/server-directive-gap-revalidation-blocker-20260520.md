# Server Directive: Gap Revalidation Blocker (SDK-CLIENT-PUBLIC-REPAIR-02)

**Date**: 2026-05-20 12:15 UTC  
**Status**: BLOCKING - Live path cannot continue  
**Session**: Fresh kh-prod login after server-side fixes  
**Tenant**: tenant-6f4f45b96f64 / org-bf06d8b73238 / cohort-0

## Promotion Recheck Update (2026-05-20 13:48 UTC)

Re-verified after server-side promotion in a fresh authenticated session.

### Confirmed During Recheck

- `gaps.submit` still returns `HTTP 202 ACCEPTED`.
- Submitted gaps now materialize in `gaps.list` after polling.
- `gaps.list` is explicitly an actionable view (`order_by: "actionable"`).

### New Current Blocker Shape

- `run_id` is still `null` on accepted async responses.
- Materialized gap is visible but remains non-claimable:
  - Example: `gap_e4218ed3dc612586`
  - `status: OPEN`
  - `claimable: false`
  - `blocked_reasons`: empty string/output in CLI polling script
- No claimable gap surfaced across 5 polls at 15-second intervals.

### First True Blocker After Promotion

`gaps.claim` remains blocked in practice because no claimable gap is available from `gaps.list` actionable output.

### Evidence Snippets (Post-Promotion)

```json
{
  "command": "keyhole gaps create",
  "success": true,
  "status": "ACCEPTED",
  "run_id": null,
  "run_type": "gaps.submit",
  "timestamp": "2026-05-20T13:48:53.218565+00:00"
}
```

```text
Poll #1..#5:
Total gaps: 1
Gap ID=gap_e4218ed3dc612586, Status=OPEN, Claimable=False, Blocked=
```

### Delta vs Earlier Blocker

- Earlier blocker explicitly reported `not_revalidated (revalidated_on_digest is null)`.
- Current promoted behavior shows non-claimable `OPEN` gap without a clear blocked reason in CLI output.
- Operational impact is unchanged: live path cannot proceed to workspace provisioning.

---

## Executive Summary

After server operator applied fixes to gaps lifecycle (2026-05-20):

OK **CONFIRMED FIXED**:
- gaps.submit materializes gaps (async ~15s delay)
- gaps.list returns materialized gaps with correct schema
- Gap record has all expected fields (gap_id, status, meta, etc.)

NO **NEW BLOCKER - CRITICAL**:
- All gaps returned by gaps.list have `claimable: false`
- All gaps have status `blocked: true` with reason `"not_revalidated (revalidated_on_digest is null)"`
- gaps.claim fails because gaps are not claimable
- Live path cannot proceed to workspace.provision

---

## Observed Server Behavior

### Gap Lifecycle Sequence

```
POST /mcp/v1/runs/start { run_type: "gaps.submit", ctxpack_digest: "..." }
  ↓ HTTP 202 ACCEPTED (run_id: null) [ISSUE #2]
  ↓ Wait ~15 seconds
GET /mcp/v1/runs/start { run_type: "gaps.list" }
  ↓ HTTP 200 OK
  ↓ Gap appears in list with:
    - status: "OPEN"
    - claimable: false [BLOCKER]
    - blocked: true
    - blocked_reasons: ["not_revalidated (revalidated_on_digest is null)"]
```

### Representative Gap Record (From gaps.list Response)

```json
{
  "gap_id": "gap_d5c7ed2d2933dba0",
  "domain": "default",
  "story_id": null,
  "status": "OPEN",
  "score": 0.5,
  "description": "Test gap materialization",
  "owner_hint": "c2a432d8-0164-499b-ad84-b662e1f174ec",
  "claimed_by": null,
  "claim_expires_ts": null,
  "is_regression": false,
  "regression_of": null,
  "recipe_key": null,
  "revalidated_on_digest": null,
  "revalidated_at": null,
  "closure_mode": null,
  "meta": {
    "capability": "test.v1",
    "description": "Test gap materialization",
    "repo": "keyhole-SDK",
    "ctxpack_digest": "da0cfa...",
    "submitter": "c2a432d8-0164-499b-ad84-b662e1f174ec",
    "tenant_id": "tenant-6f4f45b96f64",
    "org_id": "org-bf06d8b73238",
    "cohort_id": "cohort-0",
    "created_via": "sdk.gaps.submit",
    "created_at": "2026-05-20T12:10:15.123456+00:00"
  },
  "claimable": false,
  "blocked": true,
  "blocked_reasons": [
    "not_revalidated (revalidated_on_digest is null)"
  ],
  "claimability_reason": "not_revalidated (revalidated_on_digest is null)",
  "source": "my-first-app",
  "updated_at": "2026-05-20T12:10:15.123456+00:00",
  "explanation_summary": "Gap in 'my-first-app'.",
  "dominant_component": "my-first-app",
  "dominant_action": "unknown",
  "root_cause_class": "unknown",
  "explanation_status": "partial",
  "repair_class": "manual_decision",
  "explanation_stale": false,
  "explained_on_digest": null
}
```

### Attempt to Claim Blocked Gap

```
POST /mcp/v1/runs/start { run_type: "gaps.claim", gap_id: "gap_d5c7ed2d2933dba0", ctxpack_digest: "..." }
  ↓ HTTP 202 ACCEPTED (run_id: null)
  ↓ Result: Unknown - no run_id to check status
  ↓ Gap still appears in list with claimable: false (unchanged)
```

---

## Critical Questions for Server Operator

### Question 1: Gap Revalidation Trigger
What triggers gap revalidation to set `revalidated_on_digest` and `revalidated_at`?

**Possibilities to clarify**:
- [ ] Automatic: Server auto-validates gaps after fixed delay (e.g., 30 seconds)
- [ ] API call: Is there a `gaps.revalidate` endpoint?
- [ ] Workflow: Does context.verify or another call trigger revalidation?
- [ ] Manual: Does revalidation happen through a separate out-of-band process?

### Question 2: Expected Gap Lifecycle After Submit
What is the intended workflow after `gaps.submit` returns HTTP 202?

**Provide expected sequence**:
1. gaps.submit -> HTTP 202
2. [What happens next?]
3. gaps.list shows claimable: true
4. gaps.claim succeeds
5. [Continue...]

### Question 3: Current Revalidation Implementation Status
Is gap revalidation logic fully implemented in the server, or is it still pending development?

**If pending**: Provide ETA and interim workaround (if any)
**If implemented**: What is required to trigger it?

---

## Impact Analysis

### Blocked Operations
All operations downstream of gaps.claim are now blocked:

```
gaps.submit -> OK (materialized)
gaps.list -> OK (gaps appear)
gaps.claim -> BLOCKED (gaps not claimable) ? HERE
  -- workspace.provision -> unreachable
  -- proof.submit -> unreachable
  -- receipt.verify -> unreachable
  -- capability.register -> unreachable
```

### Live Path Halted
Cannot proceed with SDK-CLIENT-PUBLIC-REPAIR-01 live path validation beyond gaps materialization.

---

## Remaining Issues from Original Directive

### Issue #2: Async Responses Return run_id: null

**Observed**: 
```json
{
  "status": "ACCEPTED",
  "run_id": null,
  "run_type": "gaps.submit"
}
```

**Problem**: Without run_id, client cannot:
- Check async operation status
- Trace operation in Event Spine
- Verify operation completion

**Impact**: Clients must resort to polling (gaps.list) to detect materialization.

**Required Fix**: All ACCEPTED responses must include non-null run_id stable identifier.

---

## Acceptance Test

Once server implements revalidation:

```bash
# 1. Create gap
$ keyhole gaps create --capability test.v1 --description "test"
-> HTTP 202, run_id: XXX (or wait for materialization)

# 2. Wait for auto-revalidation (or call revalidate endpoint)
$ sleep 10  # (or call gaps.revalidate if manual)

# 3. Check gap is now claimable
$ keyhole gaps list --json | \
  python -c "import sys,json; d=json.load(sys.stdin); \
  g=d['data']['gaps'][0]; \
  assert g['claimable'] == True, 'Gap still not claimable'; \
  print('OK Gap claimable');"

# 4. Claim gap successfully
$ keyhole gaps claim --gap-id gap_XXX
-> HTTP 202, claim_token: <token>

# 5. Proceed with workspace.provision
$ keyhole workspace provision --claim-token <token>
-> HTTP 200, workspace_id: ws:...
```

---

## Blocking Criteria

Live path continuation requires server to implement AND demonstrate:

1. **Gap Revalidation Activation**: Clarify what makes gaps claimable
2. **Workspace Availability**: At least one gap must become claimable
3. **Claim Success**: gaps.claim must return HTTP 200 (or 202 with valid run_id) for claimable gap
4. **Claim Token**: Gap claim must return valid claim_token for workspace.provision

---

## Additional Observations

### auth_provider Integration
OK Client-side implementation verified working:
- GovernedTransport uses auth_provider parameter correctly
- BearerTokenProvider instantiation: `BearerTokenProvider(token=token)`
- All commands (gaps, workspace, proof) correctly initialized

### context.compile Digest Extraction
OK Workaround verified working:
- Digest extracted from keyhole.ctx_ref_sha256 in passport envelope
- Sent correctly to server as ctxpack_digest in request payload
- Server-side contract fix (emit in data payload) still pending but client-side workaround sufficient

### Transport and Identity
OK All verified:
- Device flow authentication working
- Credentials persistence (Windows atomic overwrite fix applied)
- X-Request-Id and X-Idempotency-Key headers auto-injected
- Tenant/Org/Cohort identity confirmed: tenant-6f4f45b96f64 / org-bf06d8b73238 / cohort-0

---

## Next Steps for Client

1. Await server operator response to clarification questions above
2. Once revalidation mechanism is clarified, implement corresponding client-side logic:
   - If auto-revalidation: add polling with retry + backoff to gaps.list
   - If manual API call: implement gaps.revalidate command
   - If workflow trigger: update gaps lifecycle documentation
3. Implement run_id polling for async operations (temporary until run_id is returned)
4. Resume live path: gaps.claim -> workspace.provision -> proof.submit -> receipt.verify -> capability.register

---

## Evidence Artifacts

### Test Session Metadata
- Timestamp: 2026-05-20 12:10-12:25 UTC
- Tenant: tenant-6f4f45b96f64
- Org: org-bf06d8b73238
- Cohort: cohort-0
- User: c2a432d8-0164-499b-ad84-b662e1f174ec
- Gaps created: gap_71a05afdcd4ad1ef (my-first-app.greet.user.v1), gap_d5c7ed2d2933dba0 (test.v1)

### Proof Conditions
1. [ ] Clarification: Server operator explains gap revalidation trigger
2. [ ] Implementation: Gap becomes claimable after revalidation
3. [ ] Validation: keyhole gaps claim succeeds for claimable gap
4. [ ] Progression: claim_token issued for workspace.provision
5. [ ] Live path: Can execute at least through workspace.provision step

---

## Document References

- Previous directive: [docs/remediation/server-directive-gaps-lifecycle-20260520.md](../docs/remediation/server-directive-gaps-lifecycle-20260520.md)
- SDK gaps command: [packages/python/keyhole-cli/keyhole_cli/commands/gaps_cmd.py](../../packages/python/keyhole-cli/keyhole_cli/commands/gaps_cmd.py)
- Test runtime capabilities: https://mcp.keyholesolution.com/mcp/v1/capabilities

---

**Status**: WAITING FOR SERVER OPERATOR CLARIFICATION  
**Requestor**: GitHub Copilot (SDK-CLIENT-PUBLIC-REPAIR-01 work)  
**Ticket**: SDK-CLIENT-PUBLIC-REPAIR-02
