# Server Directive - Gap Reconciler Degraded / STALE_REVALIDATION (2026-05-27)

**Priority:** CRITICAL  
**Status:** PARTIALLY RESOLVED - reconciler fixed OK; claim_token Optional deployed OK; workspace.provision result persistence still OPEN NO  
**Realm:** `kh-prod`  
**Platform:** `https://mcp.keyholesolution.com`  
**Raised by:** SDK client investigation - session `982489b3-e0d2-470e-858f-0cac6e22c04f`  
**Raised:** 2026-05-27  
**Server fix deployed:** 2026-05-27 - Option D (JWT auth, claim_token Optional) - PR #341 `78bb1cf1`  
**Remaining blocker:** See `server-directive-workspace-provision-result-ttl-20260527.md`  
**Gap:** `gap_7cde6c0a3a116eb3` closed by operator; new gap required

---

## Problem Statement

All gaps - new and existing - immediately enter `STALE_REVALIDATION` state and
cannot be claimed. The gap reconciler is in DEGRADED state due to 4 failing
Keycloak constitutional invariants introduced by the May 20 Keycloak TTL
configuration changes.

`gaps.revalidate` (the run type referenced in every `STALE_REVALIDATION` error
message) does not exist in the server's operation registry. The client has no
path to resolve this.

---

## Root Causes

### Root Cause 1 - Four Failing Keycloak Constitutional Invariants

Evidence from `readiness.explain` (live - 2026-05-27T07:09Z and confirmed again
at 2026-05-27T07:40Z):

| Invariant ID | Fingerprint Component |
|---|---|
| `INV-SDK-SERVER-01D-KEYCLOAK-DIGEST-PINNED` | `sha256:707d57b9029203c6a69851efa5f2dd6c8396f40306f3cdc73c19685a86fc6d55` |
| `INV-SDK-SERVER-01D-KEYCLOAK-PROVIDERS-PRESENT` | `sha256:2a4b380dd208608d4d0389e9dab5089b7c252f40d295adc0e686ffe19a9907f7` |
| `INV-SDK-SERVER-01D-KEYCLOAK-BROWSER-FLOW-CANONICAL` | `sha256:40e82b0649862c06e0dd3130e51bf081c7c6e85a07f943cc353474b8f5e59c5f` |
| `INV-SDK-SERVER-01D-KEYCLOAK-FLOW-EXECUTIONS-REQUIRED` | `sha256:d607a32fb41579d61d8311009953f87d508712cfc34ec8581b20467425c1b2c9` |

Total invariants: 472 - passing: 188, **failing: 4**, skipped: 280.

Constitutional evidence file on server:
```
/opt/keyhole_evidence/runtime/system/constitutional/prod/unknown/constitutional_45fc816d2bf409f4.json
```

### Root Cause 2 - Causal Chain from May 20 Keycloak Changes

On **2026-05-20**, the `kh-prod` Keycloak realm was reconfigured to fix client
token TTL issues (see `server-directive-token-ttl-reauth-20260520.md`):

| Setting | Before | After |
|---|---|---|
| Access token lifespan | 300s | 900s |
| SSO session idle | 1800s | 86400s |
| SSO session max | 36000s | 604800s |
| Refresh token rotation | disabled | enabled |
| `offline_access` scope | present | removed |

These changes modified the actual Keycloak configuration state. The 4
constitutional invariants pin specific Keycloak configuration digests. The
pinned values now describe pre-change configuration that no longer exists.
The reconciler computes `readiness_cache_mismatch`, marks itself degraded,
and all gaps become `STALE_REVALIDATION`.

### Root Cause 3 - Reconciler Degraded State

Evidence from `gaps.status` (live - 2026-05-27T07:40Z):

```json
{
  "last_reconcile_result": "degraded",
  "last_reconcile_reason": "readiness_cache_mismatch",
  "last_readiness_source": "cache",
  "last_readiness_source_reason": "readiness_cache_mismatch",
  "open_unrevalidated_count": 1,
  "stale_count": 11,
  "event_spine_replay": {
    "pending_count": 3843,
    "status": "ok"
  },
  "reconcile_lock": {
    "owner": "mcp-server-6894784968-j8g4l:1"
  }
}
```

### Root Cause 4 - Missing `gaps.revalidate` Run Type

Every gap's `STALE_REVALIDATION` error body contains:
```json
"required_action": { "run_type": "gaps.revalidate" }
```

This run type does not exist on the server - calling it returns `UNKNOWN_RUN_TYPE`.
There is no valid client-side path to revalidate a stale gap.

---

## Client-Side Status (Complete - No Further Action Possible)

All remediations that could be applied client-side have been applied:

| Fix | File | Status |
|-----|------|--------|
| Use server canonical digest (not per-request hash) in all gap dispatches | `gaps_cmd.py` - `_get_canonical_digest()` | OK Done |
| Extract `run_id` from nested `data.data.run_id` in server responses | `dispatcher.py` - `_classify_outcome()` | OK Done |
| Use `get_fresh_token()` in all CLI commands | `workspace_cmd.py` + 9 others | OK Done |
| Schema stubs for all canonical run types | `schema.py` | OK Done |

**UPDATE 2026-05-27T09:15Z:** The reconciler IS now healthy. `gaps.claim` now
transitions the gap to CLAIMED state (confirmed: `gap_7cde6c0a3a116eb3` ->
`CLAIMED` by `c2a432d8-0164-499b-ad84-b662e1f174ec`, expiry
`2026-05-27T09:25:46`). Action 1 and Action 4 are RESOLVED.

However run results are still not persisted - polling returns `not_found`
within seconds of dispatch. The `claim_token` is not included in the 202
body and is unreachable via any client-side mechanism. Action 3 is OPEN and
is now THE ONLY BLOCKER.

---

## What the Backend Team Must Do

### Action 1 - Re-pin Keycloak Constitutional Invariants (REQUIRED - Root Fix)

The 4 failing invariants hold pinned digests of the Keycloak `kh-prod` realm
configuration. The May 20 changes invalidated those pins. The operator must
update the pins to reflect current Keycloak state.

**Step 1:** Inspect the constitutional evidence file on the platform server:

```
/opt/keyhole_evidence/runtime/system/constitutional/prod/unknown/constitutional_45fc816d2bf409f4.json
```

**Step 2:** For each of the 4 failing invariants, locate the expected pinned
value and update it to match the current actual Keycloak configuration:

| Invariant | What it pins | Operator action |
|---|---|---|
| `INV-SDK-SERVER-01D-KEYCLOAK-DIGEST-PINNED` | SHA-256 of the serialized Keycloak realm export | Re-export the realm, compute the digest, update the pin |
| `INV-SDK-SERVER-01D-KEYCLOAK-PROVIDERS-PRESENT` | List of identity providers present in the realm | Update the expected providers list to current state |
| `INV-SDK-SERVER-01D-KEYCLOAK-BROWSER-FLOW-CANONICAL` | Browser authentication flow execution structure | Update the expected flow spec to current configured flow |
| `INV-SDK-SERVER-01D-KEYCLOAK-FLOW-EXECUTIONS-REQUIRED` | Required flow execution entries | Update expected executions to current configured entries |

**Step 3:** After updating pins, force a readiness cache refresh - the
reconciler must re-evaluate invariants against the updated pins. If the
reconciler does not re-run automatically, trigger a reconcile cycle manually.

**Step 4:** Confirm via `GET /mcp/v1/readiness.explain` that all 4 invariants
move to `passing`. Reconciler state should exit `degraded` and enter `ok`.

**Step 5:** Confirm via `gaps.status` that `last_reconcile_result` is no
longer `degraded` and `stale_count` drops to 0.

**Expected outcome:** Reconciler exits degraded state. All pending gaps
(including `gap_7cde6c0a3a116eb3`) transition from `STALE_REVALIDATION` to
claimable. `gaps.claim` with canonical digest `sha256:6bbb6f5727...` will
produce a claim_token.

---

### Action 2 - Implement `gaps.revalidate` Run Type (REQUIRED - prevent future recurrence)

The server emits `"required_action": { "run_type": "gaps.revalidate" }` in
every STALE_REVALIDATION error, but the run type does not exist. This is a
broken contract that leaves clients with no recovery path.

The run type must be implemented with the following contract:

**Input:**
```json
{
  "run_type": "gaps.revalidate",
  "params": {
    "gap_id": "gap_<id>",
    "ctxpack_digest": "sha256:<hex>"
  }
}
```

**Behavior:**
1. Verify the provided `ctxpack_digest` matches `current_canonical_digest`
   from `gaps.status`
2. If the reconciler is healthy: update the gap's `revalidated_on_digest`,
   re-check claimability, return new gap state
3. If the reconciler is still degraded: return a clear error explaining the
   degraded state is blocking revalidation (do not silently accept and stall)

**Required scope:** `gaps:claim` (already granted to cohort-0 - no new scope
grant needed)

**Priority:** This prevents clients from being permanently stuck when the
server emits an action key it cannot fulfil.

---

### Action 3 - Deliver `claim_token` to the Client (REQUIRED - SOLE REMAINING BLOCKER)

**Status: OPEN**

`gaps.claim` returns HTTP 202 ACCEPTED with a `run_id` (e.g.,
`run_85fb4284f941`). Polling that `run_id` immediately returns `not_found`
(run result TTL is effectively 0s). The `claim_token` is not included
anywhere in the 202 body.

`workspace.provision` has been confirmed (via live Pydantic validation error)
to require `claim_token` as a **server-required field**:

```
3 validation errors for WorkspaceProvisionParams
claim_token
  Field required [type=missing, input_value={...}, input_type=dict]
```

The client cannot call `workspace.provision` without a `claim_token`. The
`claim_token` has no accessible retrieval path:

| Retrieval attempt | Result |
|---|---|
| 202 ACCEPTED body from `gaps.claim` | Not present |
| `GET /mcp/v1/runs/{run_id}` (immediate poll) | `not_found` (TTL ~0) |
| `gaps.get` response `meta.keyhole_claim` | `claimed_by` + `claim_expires_ts` only - no `claim_token` |
| `gaps.claim` with `action: token` | 202 ACCEPTED again - result also `not_found` |
| MCP SSE transport `gaps.claim` | Internal error: `'NoneType' object has no attribute 'status_code'` |
| Event spine query for gap claim events | 0 events returned |

The server must choose one of the following resolutions:

**Option A (preferred - simplest):** Return `claim_token` in the `gaps.get`
response when the caller's JWT `sub` matches `claimed_by`. Add a
`keyhole_claim.claim_token` field that is only populated when the authenticated
caller is the current claim holder. No polling needed.

**Option B:** Return `claim_token` synchronously in the 202 ACCEPTED body
under `data.claim_token`. The `gaps.claim` operation is fast enough to
complete inline.

**Option C:** Persist run results for ≥ 60 seconds so the SDK polling loop
(5 × 2s) can retrieve the result. `not_found` within seconds of a 202 is
an async contract violation.

**Option D (server-side auth relaxation):** Accept `workspace.provision`
requests without `claim_token` by verifying the JWT caller is the current
claim holder via the gap's `claimed_by` field. This eliminates the need to
transmit a claim_token over the wire entirely.

**Recommended:** Option A (gaps.get claim_token field) + Option D (JWT
authorization) together provide a fully secure, no-polling path.

---

### Action 4 - Manual Gap Advance (IMMEDIATE WORKAROUND - unblocks development)

**Status: PARTIALLY RESOLVED - gap is now CLAIMED. Only the claim_token value is missing.**

The reconciler fix (Action 1) is complete. The gap transitions to CLAIMED state
when `gaps.claim` is dispatched. However, the client still cannot retrieve the
`claim_token` value (see Action 3 above).

To unblock `workspace.provision` immediately, the operator can:
1. Retrieve the `claim_token` value from the server-side gap store for
   `gap_7cde6c0a3a116eb3`
2. Return the `claim_token` value out-of-band (e.g., via this issue thread)

This allows the client to call `workspace.provision --claim-token <value>`
immediately without waiting for Actions 3's structural fix.

**Gap details:**
| Field | Value |
|---|---|
| `gap_id` | `gap_7cde6c0a3a116eb3` |
| `capability` | `my-first-app.greet.user.v1` |
| `repo_name` | `my-first-app` |
| `workspace` | `ws:tenant-6f4f45b96f64:cohort-0:default` |
| `canonical_digest` | `sha256:6bbb6f5727a7f76ea26d875ce8780439abfd71d4f45838ca3f2a2e57f77b25bc` |
| `claimed_by` | `c2a432d8-0164-499b-ad84-b662e1f174ec` |
| `last_claim_run_id` | `run_85fb4284f941` |

---

## Remaining Governance Chain (Ready to Execute After Server Fix)

Once the operator completes any of Actions 1-4:

```bash
# Step 1 - Claim the gap (will return claim_token once reconciler is healthy)
keyhole gaps claim --gap-id gap_7cde6c0a3a116eb3 --repo-dir my-first-app

# Step 2 - Provision workspace
keyhole workspace provision \
  --repo my-first-app \
  --gap-id gap_7cde6c0a3a116eb3 \
  --claim-token <token_from_claim>

# Step 3 - Submit proof
# (downstream steps follow workspace.provision)
```

---

## Acceptance Criteria

1. `readiness.explain` shows 0 failing invariants - all 4 `INV-SDK-SERVER-01D-KEYCLOAK-*` invariants pass - **CONFIRMED RESOLVED** OK
2. `gaps.status` shows `last_reconcile_result: "ok"` (not `"degraded"`) - **CONFIRMED RESOLVED** OK
3. `gaps.status` shows `stale_count: 0` - **CONFIRMED RESOLVED** OK
4. `keyhole gaps claim --gap-id gap_7cde6c0a3a116eb3` transitions gap to CLAIMED - **CONFIRMED WORKING** OK
5. `claim_token` is accessible to the authenticated claim holder via one of the Action 3 options - **RESOLVED via Option D** OK
6. `keyhole workspace provision` succeeds with JWT-only authorization - **DEPLOYED** OK
7. `gaps.revalidate` exists in server operations registry and returns well-formed output - **OPEN** (non-blocking)
8. Polling a `run_id` from `gaps.claim` returns the run result within 60 seconds of issuance - **OPEN** (non-blocking)

---

## Resolution Evidence

**Server fix deployed: 2026-05-27**

| Item | Value |
|---|---|
| Branch | `sdk-server-workspace-provision-repair` (`3e2e6b9a`) |
| Merged to main | `78bb1cf1` (PR #341) |
| Promoted digest | `sha256:6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818` |
| Promotion UUID | `dff60a69-cdf4-49ba-92cf-036d217cb3fb` |
| Pointers | dev v293 / staging v288 / prod v293 - all on new digest |
| Prod verification | livez, readyz, capabilities, integration 5/5 PASS |
| Staging attestation | `sha256:8013f5b9...` (11/11 PASS, 472/472 gates) |
| Capability preservation | 21 unchanged, 0 regressions |
| Gap closed | `gap_7cde6c0a3a116eb3` (1 closed, 0 remaining) |

**Code shipped server-side:**
- `WorkspaceProvisionParams.claim_token` is now optional
- Authorization: `JWT.sub == gap.claimed_by` (Option D from this directive)
- New error classes: `GAP_NOT_FOUND` / `GAP_NOT_CLAIMED` / `CLAIM_EXPIRED` / `CLAIM_OWNER_MISMATCH`
- New Event Spine events: `ev.gate.gap.claim.accepted/rejected` + `ev.gate.workspace.provision.completed/rejected`

**Client-side changes applied (this session):**
- `workspace_cmd.py`: `claim_token` parameter made optional (`Optional[str] = None`); only included in request body when non-empty
- `workspace_cmd.py`: Added error handling for all 4 new server error classes with repair guidance
- `cli.py`: `--claim-token` flag changed from required (`...`) to optional (`None`)
- Server directive updated to RESOLVED
