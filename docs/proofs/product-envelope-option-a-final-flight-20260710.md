# Product Envelope Option A Final Acceptance Flight - 2026-07-10

## Verdict

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```

The final public SDK flight made substantial progress:

- Fresh human device-flow authentication succeeded with `run:read`,
  `request:read`, and `run:support`.
- Production capabilities advertise the Option A product envelope as supported.
- A fresh governed execution reached terminal `ACCEPT`.
- Fresh product operations passed `6/6`.
- Fresh alias resolution passed `7/7`; required `run.explain` aliases passed
  `4/4`.

The strict final acceptance is still not claimable because two required checks
failed:

1. `run_9ea274bca429` still returns `PRODUCT_SUBJECT_NOT_FOUND` instead of the
   required terminal `timed_out` historical state.
2. The governed CLI serialization still omits canonical identities from the
   governed terminal surfaces: `governed status --last` returns `run_id=""` and
   no top-level `request_id`; `governed receipt --last` omits both `run_id` and
   `request_id`.

The public `runs status` product surface can resolve the fresh correlation to
the canonical run/request pair, but that does not erase the governed response
serialization failure. No local proof artifact, backend filesystem, database,
Kubernetes state, internal service credential, or promotion evidence was used
as a substitute for public SDK behavior.

## Deployment

| Field | Value |
| --- | --- |
| Promotion UUID under test | `aab809d4-f920-4d3f-b2ae-1b44dee5e4d1` |
| Canonical digest under test | `sha256:d00a3cdbdf7c172f2b00858006101e08db1a148beb6d91301babb2680fb36a08` |
| Backend `main` under test | `3303f10e2a6723efad52e5e5e14cbfb5b8fec88b` |
| Public boundary | `https://mcp.keyholesolution.com` |
| Capabilities observation | `operations_count=30`, product envelope `supported` |
| Product transport | `/mcp/v1/runs/start` |
| Product operation count impact | `none` |
| Product run types | `run.status`, `run.budget`, `run.explain`, `request.inspect`, `support.bundle`, `run.tail` |
| Surface negotiation | `compatible`, `required_missing=[]`, `optional_missing=[]` |

## Repository

| Field | Value |
| --- | --- |
| Branch | `main` |
| HEAD before this document | `d7f38ef7903eb5e34fc5d46ad65c1f365d642b2b` |
| `origin/main` | `47c896bb17b8aa8b86f3e1a63fbafdff4473ba3c` |
| Upstream | `origin/main` |
| Starting status | `main...origin/main [ahead 18]`, clean |
| SDK posture | Existing SDK honesty changes preserved |

## Human Authentication

The stale local session was cleared with `keyhole logout --json`, then a fresh
human device-flow login was completed through the normal public SDK credential
workflow. No device code, access token, refresh token, Authorization header, or
credential-file content is recorded here.

| Field | Safe Evidence |
| --- | --- |
| Device flow completed | yes |
| Fresh token confirmed | yes |
| Client | `keyhole-cli` |
| Subject | `c2a432d8-0164-499b-ad84-b662e1f174ec` |
| Tenant | `tenant-6f4f45b96f64` |
| Org | `org-bf06d8b73238` |
| Workspace | `ws:tenant-6f4f45b96f64:cohort-0:default` |
| Issued at | `2026-07-10T11:52:32Z` |
| Expires at | `2026-07-10T12:07:32Z` |
| Scope names | `email`, `openid`, `profile`, `request:read`, `run:read`, `run:support` |
| `run:read` | present |
| `request:read` | present |
| `run:support` | present |

`keyhole whoami --json` returned the same subject, tenant, org, workspace, and
`mode=real` at `2026-07-10T12:05:06Z`.

## Existing Repaired Fixture

Fixture under test:

| Field | Value |
| --- | --- |
| `request_id` | `req_74f97c69516e` |
| `run_id` | `run_37dd7df5699f` |
| `governance_context_id` | `gctx_74d37cdc6a9d7de72a173288b7936c28` |
| `mcp_event_id` | `run.complete:090ddd86-82d0-4bcd-9bac-5104be43d48f` |
| Bare event UUID | `090ddd86-82d0-4bcd-9bac-5104be43d48f` |
| `proof_id` | `gproof_fc56c34e132180f4a4306768` |
| `receipt_id` | `grcpt_7c9e26a13faaffa25238c4da` |

Result:

| Check | Result |
| --- | --- |
| Seven aliases resolved to `run_37dd7df5699f` / `req_74f97c69516e` | PASS, `7/7` |
| Product operations | PASS, `6/6` |

All repaired-fixture product operations were server-backed and matched the
canonical run/request pair.

## Historical Timeouts

| Historical run | Result |
| --- | --- |
| `run_73c3fe93019b` | PASS: resolved to `req_58b5d3f2181d`, status `timed_out`, terminal true, reason `server_watchdog_timeout`, terminal timestamp `2026-07-10T10:10:48.546334+00:00` |
| `run_9ea274bca429` | FAIL: `PRODUCT_SUBJECT_NOT_FOUND`, no canonical request/run identity returned |

The first historical run now has the correct terminal timeout posture. The
second historical run does not meet the directive's required behavior.

## Fresh Governed Execution

Before the fresh governed run, the blessed public example had a stale gap. The
gap was rematerialized through public SDK behavior:

| Field | Value |
| --- | --- |
| Command | `gaps create --repo-dir examples/second-governed-app` |
| Status | `ACCEPTED` |
| Gap | `gap_8488f30fb4e1ef82` |
| Gap state after refresh | `OPEN`, `claimable=true` |
| Gap revalidated on digest | `sha256:d00a3cdbdf7c172f2b00858006101e08db1a148beb6d91301babb2680fb36a08` |
| Gap submission run | `run_3446e5515c5c` |
| Gap submission request | `req_a57796407ac3` |
| Gap submission correlation | `8add6e32-7d0a-4441-b221-8e1b69e62aa8` |

`doctor launch --repo-dir examples/second-governed-app --json` then passed and
resolved the same gap.

Fresh governed realization:

| Field | Value |
| --- | --- |
| Repo | `examples/second-governed-app` |
| Repo commit | `d7f38ef7903eb5e34fc5d46ad65c1f365d642b2b` |
| Resolved gap | `gap_8488f30fb4e1ef82` |
| Claim | `a7ffa8d497a096ab61d37edb63b9b650` |
| Registration | `repo_1da56cceb637de1f0195466c` |
| Governance context | `gctx_726e9d51924cb4bf1a1c1b90e91f42f8` |
| MCP event ID | `run.complete:da53589e-5df2-4369-8a4b-28ca6c0dfcac` |
| Bare event UUID | `da53589e-5df2-4369-8a4b-28ca6c0dfcac` |
| Proof | `gproof_a4dd582f70864c5085f7ccb8` |
| Receipt | `grcpt_b8bf14374eab71157854d277` |
| Realized at | `2026-07-10T11:56:36.891176Z` |
| Verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event spine evidence | true |

Public product status for the fresh event UUID resolved the canonical identity:

| Field | Value |
| --- | --- |
| Canonical `run_id` | `run_44b628c7c8d4` |
| Canonical `request_id` | `req_5de7eff0e75e` |
| Status | `success` / server result `succeeded` |
| Terminal | true |
| Run type | `governed.realize` |
| Server backed | true |

## Governed Serialization

Strict serialization check:

| Surface | Result |
| --- | --- |
| `governed status --last --json` | FAIL: terminal `succeeded` and `ACCEPT`, but top-level `run_id=""` and no top-level `request_id` |
| `governed receipt --last --json` | FAIL: receipt present and live-confirmed, but no top-level or receipt-level `run_id` / `request_id` |
| `governed resume --json` | FAIL: receipt remains accepted but still omits `run_id` / `request_id` |
| `runs status da53589e-5df2-4369-8a4b-28ca6c0dfcac --json` | PASS as product lookup: top-level `run_44b628c7c8d4` / `req_5de7eff0e75e` |

The product lookup proves the backend can resolve the fresh correlation. It does
not satisfy the governed response serialization gate because the governed
surfaces themselves still omit the canonical top-level IDs.

## Fresh Product Operations

All six product operations were invoked through public SDK transport against
`POST /mcp/v1/runs/start`. The canonical subject under test was:

```text
run_id = run_44b628c7c8d4
request_id = req_5de7eff0e75e
```

The `envelope_run_id` values below are the individual product-operation runs.
The `subject_*` values are the canonical governed run/request identities that
the product surface resolved.

| Operation | Subject request | Subject run | Envelope run | Evidence | Result |
| --- | --- | --- | --- | --- | --- |
| `run.status` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_00edb62cdc74` | resolved, server-backed, terminal, verdict `ACCEPT`, status `succeeded` | PASS |
| `run.explain` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_ead5cf2ad83f` | resolved, explanation present, verdict `ACCEPT` | PASS |
| `run.tail` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_b1d1bf27c6ee` | resolved, terminal event present, server tail observations present | PASS |
| `run.budget` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_ae6533db5eb0` | resolved, `instrumentation_status=AVAILABLE`, `pressure_status=NO_PRESSURE` | PASS |
| `request.inspect` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_e72929112276` | resolved, server-backed, executed, terminal | PASS |
| `support.bundle` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `run_902831b2ac33` | resolved, server-backed, context/events/proof refs/receipt ref present | PASS |

Fresh product result:

```text
product operations passed = 6/6
```

## Alias Resolution

`run.status` alias checks:

| Alias | Supplied value | Canonical request | Canonical run | Status | Verdict | Result |
| --- | --- | --- | --- | --- | --- | --- |
| canonical run ID | `run_44b628c7c8d4` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| canonical request ID | `req_5de7eff0e75e` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| full MCP event ID | `run.complete:da53589e-5df2-4369-8a4b-28ca6c0dfcac` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| bare event UUID | `da53589e-5df2-4369-8a4b-28ca6c0dfcac` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| proof ID | `gproof_a4dd582f70864c5085f7ccb8` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| receipt ID | `grcpt_b8bf14374eab71157854d277` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |
| governance context ID | `gctx_726e9d51924cb4bf1a1c1b90e91f42f8` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | `succeeded` | `ACCEPT` | PASS |

Fresh alias result:

```text
aliases resolved = 7/7
```

Required `run.explain` aliases also passed:

| Alias | Supplied value | Canonical request | Canonical run | Result |
| --- | --- | --- | --- | --- |
| canonical run ID | `run_44b628c7c8d4` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | PASS |
| full MCP event ID | `run.complete:da53589e-5df2-4369-8a4b-28ca6c0dfcac` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | PASS |
| bare event UUID | `da53589e-5df2-4369-8a4b-28ca6c0dfcac` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | PASS |
| proof ID | `gproof_a4dd582f70864c5085f7ccb8` | `req_5de7eff0e75e` | `run_44b628c7c8d4` | PASS |

No supplied alias replaced the canonical returned `run_id`.

## Verification

| Check | Result |
| --- | --- |
| `validate examples/second-governed-app --json` | PASS |
| `validate my-first-app --json` | PASS |
| Focused lifecycle/product tests | PASS, `447 passed` |
| Full unit suite | PASS, `3680 passed` |
| `git diff --check` | PASS |
| Hygiene scan | PASS, no hits |
| Generated `.keyhole` / `proof_bundle` tracking check | PASS, no tracked paths |
| Generated local artifacts | Removed from `examples/second-governed-app` after evidence capture |

## Final Assessment

Fresh product-envelope behavior is now substantially proven from the public SDK
boundary:

```text
fresh human auth: PASS
fresh governed ACCEPT: PASS
fresh product operations: PASS, 6/6
fresh aliases: PASS, 7/7
```

Strict final acceptance remains blocked:

```text
historical timeout backfill: FAIL, run_9ea274bca429 unresolved
governed response serialization: FAIL, governed status/receipt omit run_id/request_id
```

Therefore:

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```
