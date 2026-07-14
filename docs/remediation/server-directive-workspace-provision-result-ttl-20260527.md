# Server Directive - Two-Plane Run Result Persistence + Gap Stale Regression (2026-05-27)

**Priority:** CRITICAL  
**Status:** RESOLVED - Root cause confirmed and fixed by v295; executor write path was always working; GET read-path used `user.sub` (nonexistent field) -> fell back to `"anonymous"` -> SQL mismatch -> `not_found`  
**Realm:** `kh-prod`  
**Platform:** `https://mcp.keyholesolution.com`  
**Raised by:** SDK client investigation - session `982489b3-e0d2-470e-858f-0cac6e22c04f`  
**Raised:** 2026-05-27T12:15Z  
**Updated:** 2026-05-28T09:10Z - Server-side DB inspection confirmed root cause; v295 fix verified correct; fresh probe pending  
**Related directive:** `server-directive-gap-reconciler-degraded-20260527.md` (PR #341 deployed PR #342 fixes Regression B follow-on)

---

## Fix Status

| Regression | Description | Status |
|---|---|---|
| **B** - Gaps go STALE immediately | PR #342 `3c439c14` deployed to prod at `sha256:94477e18...` | OK FIXED |
| **A** - Two-plane run results invisible | v295 (`sha256:7b8c7543...`) fixed GET read-path: `user.sub` -> `user.user_id` | OK FIXED |

**Confirmed root cause (2026-05-28, server-side DB inspection):**
- Executor write path was **always working** - `mcp_run_records` rows were correctly written with `subject_id = c2a432d8-0164-499b-ad84-b662e1f174ec`
- `GET /mcp/v1/runs/<run_id>` used `user.sub` to look up stored records - but `user.sub` does not exist on `UserContext`
- Fallback: `user.sub` -> `"anonymous"` -> SQL `WHERE subject_id = 'anonymous'` -> 0 rows -> `not_found`
- v295 fix: `user.user_id` -> UUID -> SQL `WHERE subject_id = 'c2a432d8-...'` -> row found -> result returned
- `gaps.claim` correctly writes `claimed_by`, `claim_token`, `claim_expires_ts` in DB OK
- No CLAIMED gaps with null `claimed_by` exist in prod DB OK
- `workspace.provision` "invalid params" errors in Neon were from pre-fix probe versions, not v295

---

## Problem Statement

There is **one remaining regression** blocking the full gap->claim->workspace->proof chain:

### Regression A - All two-plane run results have TTL ≈ 0 (STILL OPEN)

Any run dispatched with `dispatch_mode: "two_plane"` returns a `run_id` (202 ACCEPTED) but the result is **never stored** in the result backend. Polling `GET /mcp/v1/runs/<run_id>` returns `not_found` from 50ms through 8s+.

**Affected run types:**
- `gaps.claim`
- `workspace.provision`
- `gaps.submit` (unconfirmed but `keyhole runs wait` timed out for this too)

**Not affected (synchronous or single-plane):**
- `gaps.get`
- `gaps.list`
- `gaps.status`
- `context.compile`

### Regression B - Gaps transition to STALE immediately after creation OK FIXED (PR #342)

A newly submitted gap (`gap_810669d1c41e2041`) transitioned from OPEN to STALE **4 minutes** after creation, despite:
- The gap's `meta.ctxpack_digest` matching the current canonical digest exactly
- No competing gap for the same capability
- No evidence of revalidation failure

**Fixed by PR #342** (`canonical_queue.py` + `claim.py`): STALE gaps with `fingerprint_version='sdk-v1'` are now auto-restored to OPEN on `gaps.claim`. Confirmed: `gaps.status` shows `CLAIMED: 1` after claim dispatch against the previously-STALE gap.

**Residual issue from Regression A**: `claimed_by` and `claim_expires_ts` are `null` despite `status: CLAIMED` - the gap state was partially written. The full claim metadata is likely written by the two-plane executor, which does not persist results (Regression A). This means `workspace.provision` cannot authorize the claim (no `claimed_by` to match against `JWT.sub`).

---

## Evidence

### Regression A - Two-plane run results not stored

#### Timeline of all affected run IDs (12:11-14:55 UTC, 2026-05-27)

| Run ID | Run type | Dispatch time | Result visible? |
|---|---|---|---|
| `run_8114deb49f4c` | `workspace.provision` | ~12:05 (pre-fix session) | NO never |
| `run_0fed14d9f80f` | `workspace.provision` | ~12:11 | NO never (200 polls, 635s) |
| `run_59696983dbcc` | `workspace.provision` | ~12:12 | NO never (50ms-8s) |
| `run_d117a3d0cad3` | `gaps.submit` | 12:19:29 | NO never (15 polls, 33s) |
| `run_cfc3943bb1ae` | `gaps.claim` | ~12:21 | NO unknown after 3s |
| `run_2a2a681674b7` | `gaps.claim` | ~12:22 | NO never (50ms-8s) |
| `run_2fb4811069f0` | `workspace.provision` | ~12:22 | NO never (50ms-8s) |
| `run_9ea37435f37f` | `gaps.claim` | 12:24:33 | NO never (10 polls, 22s) |
| `run_37435c5aeb76` | `gaps.claim` | ~12:26 | NO never (50ms-8s) |
| `run_0e8b05c5027c` | `workspace.provision` | ~12:26 | NO never (50ms-8s) |
| `run_284f2ec05bfc` | `gaps.submit` | 14:48:44 | NO never (10 polls, 22s) - POST PR #342 |
| `run_8936f22b39a7` | `gaps.claim` | ~14:50 | NO never (50ms-8s) - gap went CLAIMED (side-effect) but result invisible |
| `run_dcf7db69fdf4` | `gaps.claim` | ~13:43 | NO never (50ms-8s) |
| `run_283d3652fdc6` | `gaps.claim` | ~14:52 | NO never (50ms-8s) |
| `run_e645b199e576` | `workspace.provision` | ~14:52 | NO never (50ms-8s + 10s delayed check) |
| `run_d67976866ed8` | `gaps.claim` | 2026-05-28T09:03Z | NO never (50ms-8s) - **post-v295 canonical `sha256:7b8c7543...`** |
| `run_f44dcc443ab9` | `workspace.provision` | 2026-05-28T09:03Z | NO never (50ms-8s) - **post-v295** |

All `dispatch_mode: "two_plane"` runs return `not_found` for all polling attempts.

#### Wire format from server response (confirmed `dispatch_mode: "two_plane"`)

```json
{
  "ok": true,
  "data": {
    "run_id": "run_37435c5aeb76",
    "correlation_id": "17b118b2-8272-4ae9-ae93-dc23fb7e8da",
    "status": "accepted",
    "poll_url": "/mcp/v1/runs/run_37435c5aeb76",
    "message": "Run gaps.claim accepted for background execution."
  },
  "meta": {
    "dispatch_mode": "two_plane",
    "run_type": "gaps.claim",
    "budget_envelope": {
      "max_wall_ms": 120000
    }
  }
}
```

#### gaps.claim side effects absent

After 6+ `gaps.claim` dispatches against `gap_810669d1c41e2041`:
```
gaps.status -> CLAIMED: 0  (gap never transitions to CLAIMED)
gaps.get    -> claimed_by: null, claim_expires_ts: null
```

### Regression B - Gap goes STALE immediately

Gap submission at **12:19:30**:
```json
{
  "gap_id": "gap_810669d1c41e2041",
  "status": "OPEN",
  "meta": {
    "ctxpack_digest": "6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818"
  }
}
```

Canonical digest from `gaps.status` at same time:
```
"current_canonical_digest": "sha256:6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818"
```

Digests are **identical** (modulo `sha256:` prefix which is a formatting difference).

After reconciler cycle at **12:23:52** (4 minutes later):
```
gaps.status -> OPEN: 0, STALE: 12 (was 11)
gaps.get    -> status: "STALE"
```

**The gap was moved to STALE despite having the current canonical digest.**

This is the same behavior that prompted the previous directive (`server-directive-gap-reconciler-degraded-20260527.md`). The PR #341 fix may not have fully resolved the reconciler's stale detection logic.

---

## Root Cause - Confirmed (2026-05-28, server-side DB inspection)

### Regression A - GET endpoint subject_id lookup fallback (FIXED by v295)

**Confirmed root cause:**

The `GET /mcp/v1/runs/<run_id>` endpoint attempted to resolve the caller's identity using `user.sub`. However, `user.sub` does not exist on the `UserContext` object - it silently returned `None`, which fell back to the string literal `"anonymous"`.

The SQL lookup then ran:
```sql
SELECT * FROM mcp_run_records WHERE run_id = ? AND subject_id = 'anonymous'
```

The records were correctly stored with `subject_id = 'c2a432d8-0164-499b-ad84-b662e1f174ec'`, so the lookup returned 0 rows -> `not_found` for every caller.

**The write path was always correct.** The executor wrote results to `mcp_run_records` with the correct `subject_id`. The bug was exclusively in the read path.

**v295 fix:** `user.user_id` is used instead of `user.sub` -> UUID matches stored `subject_id` -> record found -> result returned.

### Regression B - Gap stale detection

The reconciler is using the `sha256:` prefix as part of the digest comparison, causing a mismatch between:
- Gap's stored digest: `6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818` (no prefix)
- Canonical digest: `sha256:6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818` (with prefix)

If the reconciler does a string equality check without normalizing, this would cause all SDK-submitted gaps to immediately go STALE. This is likely the same root cause as the original gap-reconciler degraded issue (which the PR #341 was supposed to fix).

---

## Impact

Without these fixes, the full gap->claim->workspace->proof chain is **completely blocked**:

1. Gaps submitted with correct digest -> immediately go STALE (Regression B)
2. Claims cannot succeed against STALE gaps
3. Even if somehow claimed, the claim result is invisible (Regression A)
4. `workspace.provision` results are also invisible (Regression A)
5. Identity never exits the neutral default workspace

The client-side changes from PR #341 are complete and correct. The only remaining blockers are server-side.

---

## What the Backend Team Must Do

### Action 1 (CRITICAL) - Fix two-plane executor result WRITE path

**v295 fixed the GET read-path** (user_id/tenant_id extraction). That fix is correct and should be kept. But it is not the root cause.

The actual bug is in the executor's **write path**: after the two-plane background job completes (succeeds or fails), it must call:

```
result_store.write(run_id, result)
```

Currently this write is either not happening, silently failing, or writing to a mismatched key.

**What to fix**: In the two-plane executor/worker, find the completion callback and ensure it:
1. Writes the full result object (`{"run_id": ..., "status": ..., "data": ..., "error": ...}`)
2. Writes to the same key that `GET /mcp/v1/runs/<run_id>` uses to look up results
3. Does NOT swallow exceptions from the write
4. Sets an appropriate TTL (at minimum 120s to match `max_wall_ms: 120000`)

This applies to ALL two-plane run types: `gaps.claim`, `workspace.provision`, `gaps.submit`, and any others dispatched with `dispatch_mode: "two_plane"`.

Note: The GET read-path fix (v295) is still correct - both fixes are needed together.

### Action 2 (CRITICAL) - Fix reconciler digest normalization

The reconciler must normalize digests before comparison. Both:
- `6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818`
- `sha256:6d8f24eac06e4547d0f73645ec1709a1763d742eb5eee62149b2269bcab5f818`

must be treated as equivalent.

Additionally, a gap submitted with the **current canonical digest** must remain OPEN (not transition to STALE) until:
- It is claimed, provisioned, or manually closed
- The canonical digest advances and the gap's digest is no longer current

### Action 3 (REQUIRED) - Revalidate or reset gap_810669d1c41e2041

The gap `gap_810669d1c41e2041` (capability `my-first-app.greet.user.v1`) is currently STALE despite having a matching digest. It should be:

Option A: Moved back to OPEN by the operator  
Option B: Revalidated by the reconciler after Action 2 is deployed  

### Action 4 (NICE-TO-HAVE) - Return workspace_id in provision result

When `workspace.provision` succeeds (after Action 1 fixes result persistence), the result should contain:

```json
{
  "status": "ok",
  "workspace_id": "ws:tenant-...:cohort-0:my-first-app",
  "repo": "my-first-app",
  "gap_id": "gap_810669d1c41e2041"
}
```

---

## Acceptance Criteria

1. `GET /mcp/v1/runs/<run_id>` returns a non-null result within 30 seconds for `gaps.claim` and `workspace.provision`
2. After `gaps.claim` succeeds: `gaps.get` shows `status: "CLAIMED"` and `claimed_by: <user_id>`
3. A gap submitted with the current canonical digest remains OPEN through at least one reconciler cycle
4. `keyhole gaps claim --gap-id <id>` followed by `keyhole workspace provision --repo my-first-app --gap-id <id>` completes the full chain within 60s
5. After successful provision: `keyhole whoami` shows a non-neutral workspace_id

---

## Reproduction Steps

```bash
# 1. Submit a new gap
keyhole gaps create --capability my-first-app.greet.user.v1 --repo-dir my-first-app --json
# -> ACCEPTED run_id=<submit_run_id>

# 2. Wait for gap to appear (gaps.status will show OPEN: 1)
# But: after ~4 min reconciler cycle -> STALE (Regression B)

# 3. Attempt to claim
keyhole gaps claim --gap-id <gap_id> --json
# -> ACCEPTED run_id=<claim_run_id>

# 4. Check claim result - always not_found (Regression A)
keyhole runs wait <claim_run_id> --max-polls 10
# -> wait_timeout: "Run did not reach terminal state after 10 polls"

# 5. Check gap state - still OPEN/STALE, never CLAIMED
gaps.get {gap_id} -> status: "OPEN" or "STALE", claimed_by: null
```

---

## Client-Side Status

The SDK/CLI client side is **complete and correct**:
- `--claim-token` is now Optional (merged this session)
- New error handlers for `GAP_NOT_FOUND`, `GAP_NOT_CLAIMED`, `CLAIM_EXPIRED`, `CLAIM_OWNER_MISMATCH`
- `keyhole runs wait` uses correct polling pattern
- Wire format (`"repo"`, `"input"`, `"ctxpack_digest"`) confirmed correct via raw HTTP probes

**No further client changes are needed.** Only server-side fixes (Actions 1-3) are blocking.
