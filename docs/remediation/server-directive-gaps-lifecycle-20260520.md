# Server-Side Directive - Gap Lifecycle Materialization and Async Run Contract

**Date:** 2026-05-20
**Raised by:** SDK-CLIENT live path execution (SDK-CLIENT-PUBLIC-REPAIR-01)
**Severity:** BLOCKER - write-bearing CLI path stalls after gaps.submit; no gap materializes
**Status:** Awaiting server-side remediation
**Companion client story:** CE-V5-S47-02 (referenced in server error detail)

---

## 1. Executive Summary

The client-side live path was advanced to the point where `gaps.submit` reaches
the server, is authenticated, carries a valid `ctxpack_digest`, and receives
HTTP 202 ACCEPTED. However, three server-side contract failures prevent the
live path from advancing further:

1. **`gaps.submit` accepted -> no gap in `gaps.list`** - the submitted gap does
   not materialize as a queryable record.

2. **`run_id: null` on accepted async runs** - the acceptance receipt carries no
   trackable identifier; polling is impossible.

3. **`context.compile` does not emit `ctxpack_digest` in the `data` payload** -
   the digest is only present in the `keyhole` passport envelope, requiring
   non-standard client extraction.

Items 1 and 2 are hard blockers. Item 3 was worked around client-side but is a
contract gap.

---

## 2. Observed Boundary Behavior

All observations are from live production boundary (`https://mcp.keyholesolution.com`).

### 2.1 `gaps.submit` - ACCEPTED with no materialization

**Request:**
```json
POST /mcp/v1/runs/start
{
  "run_type": "gaps.submit",
  "repo": "my-first-app",
  "ctxpack_digest": "59ca86b116220f9091daf9638421648781bfdd7b975b90f0433767d834a44b77",
  "input": {
    "capability": "my-first-app.greet.user.v1",
    "description": "Register greet capability"
  }
}
```

**Response (HTTP 202):**
```json
{
  "command": "keyhole gaps create",
  "success": true,
  "status": "ACCEPTED",
  "run_id": null,
  "run_type": "gaps.submit",
  "summary": "Accepted. run_id=None"
}
```

**Follow-up `gaps.list` result (1 minute later):**
```json
{
  "gaps": [],
  "total": 0
}
```

**Expected:** `gaps.list` must return the submitted gap with a `gap_id`, `state:
"open"`, `capability`, `description`, and all fields needed for `gaps.claim`.

**Actual:** Zero gaps. The submission is silently discarded after acceptance.

### 2.2 `run_id: null` on all ACCEPTED async responses

Every accepted async run from `gaps.submit` and `gaps.next_open_canonical` returns
`"run_id": null`. There is no handle for the client to poll for completion or
query the result.

**Required:** All ACCEPTED responses must carry a non-null, stable `run_id` that
the client can use with a polling endpoint (e.g., `GET /mcp/v1/runs/{run_id}`).

### 2.3 `context.compile` does not emit digest in `data` payload

**Response (HTTP 202):**
```json
{
  "data": {
    "run_id": "run_5e2ceca19abe",
    "status": "accepted",
    "poll_url": "/mcp/v1/runs/run_5e2ceca19abe"
  },
  "keyhole": {
    "ctx_ref_sha256": "88aad6a128fbf405e2e7b92b0389c11208f1b0d77b48a437ab35e96709c54067"
  }
}
```

The `ctxpack_digest` / `ctx_ref_sha256` is present in the `keyhole` passport
envelope but absent from `data`. The client SDK's `_classify_compile_result`
has been patched client-side to fall back to `keyhole.ctx_ref_sha256`. However,
the contract should emit the digest in `data` directly so no envelope-parsing
workaround is needed.

---

## 3. Required Server-Side Changes

### 3.1 CRITICAL: `gaps.submit` must materialize a queryable gap record

**Story reference:** CE-V5-S47-02 (already linked in server error body)

The `gaps.submit` run handler must, upon successful execution:

1. Create a gap record in the gap registry with:
   - `gap_id` - stable, unique identifier (UUID or namespaced slug)
   - `state` - `"open"` on creation
   - `capability` - from the input payload
   - `description` - from the input payload
   - `submitter` - from the authenticated actor (`sub` from passport)
   - `tenant_id`, `org_id`, `cohort_id`, `binding_id` - from the passport
   - `ctxpack_digest` - the digest from the request (for provenance)
   - `created_at` - ISO timestamp
   - `correlation_id` - from the request

2. The gap record must be queryable by `gaps.list` immediately after the run
   completes (or, if execution is truly async, within the lifecycle window
   defined by the run's budget envelope).

3. The `gaps.submit` run completion result must include `gap_id` in the output
   so clients that poll by `run_id` can retrieve it.

**Acceptance test (client will verify):**
```
POST /mcp/v1/runs/start { run_type: "gaps.submit", ctxpack_digest: ..., input: {capability, description} }
-> HTTP 202, run_id non-null

GET /mcp/v1/runs/{run_id}   (or POST runs/start with run_type=gaps.status)
-> status: succeeded, output: { gap_id: "gap-...", state: "open" }

POST /mcp/v1/runs/start { run_type: "gaps.list" }
-> gaps: [{ gap_id: "gap-...", state: "open", capability: "...", ... }]
```

### 3.2 CRITICAL: All ACCEPTED async runs must return a non-null `run_id`

The `run_id` field in the acceptance receipt must never be null. It must be:

- stable across the full async execution lifecycle
- usable as a path parameter or query key for status polling
- emitted in the Event Spine under the run's correlation chain

**Affected run types observed returning `run_id: null`:**
- `gaps.submit`
- `gaps.next_open_canonical`

This is likely systemic. Audit all async run types for null `run_id` responses.

**Required contract for ALL accepted async runs:**
```json
{
  "ok": true,
  "data": {
    "run_id": "run_<stable_identifier>",
    "status": "accepted",
    "poll_url": "/mcp/v1/runs/run_<stable_identifier>",
    "message": "Run <run_type> accepted for background execution."
  }
}
```

`run_id` must never be null for accepted runs. If run tracking is not yet
implemented for a given run type, return a synthetic but stable handle scoped
to the request's `X-Request-Id` rather than null.

### 3.3 CONTRACT: `context.compile` must emit `ctxpack_digest` in `data`

The `context.compile` run (HTTP 202 accepted) must include the context digest
in the standard `data` payload:

```json
{
  "data": {
    "run_id": "run_...",
    "status": "accepted",
    "ctxpack_digest": "<sha256>",
    "poll_url": "/mcp/v1/runs/run_..."
  }
}
```

This allows clients to extract the digest without parsing the `keyhole` passport
envelope. The client-side workaround (`keyhole.ctx_ref_sha256` fallback) will
remain as a defensive layer, but the primary path must be `data.ctxpack_digest`.

---

## 4. Token Lifetime - Configuration Note

**Observed:** kh-prod access tokens have a ~5-minute TTL. The device flow
completion (browser authentication) can take 1-3 minutes, leaving a 2-4 minute
usable window. Write-bearing CLI operations (compile + submit + verify) take
15-30 seconds each; a single live path traversal consumes most of the window.

**Recommendation:** Increase the kh-prod access token TTL to 30 minutes for
builder-class sessions, or enable refresh token rotation so the client can
silently refresh without re-prompting the user.

This is not a blocker but will become a UX regression as the live path expands.

---

## 5. Causal Chain: What the Client Tried and Where Each Failure Occurred

```
keyhole login --force --flow device
  -> OK kh-prod token issued, credential_persisted: True

keyhole context compile
  -> OK HTTP 202, ctxpack_digest extracted from keyhole.ctx_ref_sha256
  -> client-side patch: compile.py fallback added

keyhole gaps list
  -> OK HTTP 200, lifecycle_closed: true, gaps: []

keyhole gaps create --capability my-first-app.greet.user.v1
  -> OK HTTP 202, status: ACCEPTED
  -> NO run_id: null (no polling possible)

keyhole gaps list  (1 minute later)
  -> NO gaps: [], total: 0  ? gap was NOT materialized
  -> BLOCKED: no gap_id to pass to gaps.claim

keyhole gaps claim  (cannot proceed - no gap_id)
keyhole workspace provision  (cannot proceed)
keyhole proof submit  (cannot proceed)
keyhole receipt verify  (cannot proceed)
keyhole capability register  (cannot proceed)
```

---

## 6. Pre-Patch Proof Conditions

The server-side fix for item 3.1 is confirmed complete when ALL of the
following are true, verifiable by the client in a single live path run:

| # | Condition | Verification |
|---|-----------|--------------|
| 1 | `gaps.submit` HTTP 202 carries non-null `run_id` | `response.data.run_id != null` |
| 2 | `gaps.submit` run completes and materializes a gap | `gaps.list` returns `total >= 1` after completion |
| 3 | Materialized gap has `gap_id`, `state: "open"`, `capability` | `gaps.list[0].gap_id` is non-null |
| 4 | `gaps.claim` accepts the `gap_id` from the materialized gap | `gaps.claim` returns ACCEPTED or SUCCESS |
| 5 | `context.compile` emits `ctxpack_digest` in `data` payload | `response.data.ctxpack_digest != null` |

---

## 7. Proof Delivery Format

Deliver a handoff document to this directory:

```
docs/remediation/evidence/server-gaps-lifecycle-<YYYYMMDD>/
  backend-handoff-<YYYYMMDD>.txt
```

Format consistent with:
`docs/remediation/evidence/auth-convergence-client-20260515/backend-handoff-20260515.txt`

The handoff must include:
- Event Spine event ID for the fix deployment
- Git commit SHA of the server-side change
- Confirmation of each of the 5 proof conditions above
- Statement that `run_id: null` is resolved for `gaps.submit` and `gaps.next_open_canonical`
