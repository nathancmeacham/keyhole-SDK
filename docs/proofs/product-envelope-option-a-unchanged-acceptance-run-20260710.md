# Product Envelope Option A Unchanged Acceptance Run - 2026-07-10

## Verdict

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```

This was a final unchanged public SDK acceptance run against
`https://mcp.keyholesolution.com`. No SDK acceptance logic was changed, no
backend filesystem/database/Kubernetes access was used, and no service token was
used.

The run improved the fresh proof surface:

- Fresh human `keyhole-cli` device-flow authentication succeeded.
- Required token scopes were present: `run:read`, `request:read`,
  `run:support`.
- A brand-new governed execution reached terminal `ACCEPT`.
- Fresh alias resolution passed `7/7`.
- Fresh product operations passed `6/6` when operation-envelope run IDs were
  kept separate from the governed subject run ID.

Strict acceptance still fails because two requested confirmations did not pass:

1. `run_9ea274bca429` and expected request `req_6996c4b7f0dd` still return
   `PRODUCT_SUBJECT_NOT_FOUND`, not terminal `timed_out` with
   `GOVERNED_EXECUTION_TIMEOUT`.
2. Prior accepted run `run_44b628c7c8d4` still does not expose matching
   top-level and nested canonical IDs. Its nested `result` and `receipt` point
   to `run_44b628c7c8d4` / `req_5de7eff0e75e`, but the top-level product status
   envelope returns a different operation run ID.

## Repository State

| Field | Value |
| --- | --- |
| Branch | `main` |
| Starting HEAD | `f65f044411bec59f7e5d42aad69e4d0c0da74951` |
| `origin/main` | `47c896bb17b8aa8b86f3e1a63fbafdff4473ba3c` |
| Starting status | `main...origin/main [ahead 19]`, clean |
| SDK logic changes | none |

## Human Authentication

The local auth session was cleared with `keyhole logout --json`, then a fresh
human device-flow login was completed with `keyhole login --flow device --force
--json`.

Safe token metadata:

| Field | Value |
| --- | --- |
| Client | `keyhole-cli` |
| Subject | `c2a432d8-0164-499b-ad84-b662e1f174ec` |
| Tenant | `tenant-6f4f45b96f64` |
| Org | `org-bf06d8b73238` |
| Workspace | `ws:tenant-6f4f45b96f64:cohort-0:default` |
| Issued at | `2026-07-10T13:09:25Z` |
| Expires at | `2026-07-10T13:24:25Z` |
| Scopes | `email`, `openid`, `profile`, `request:read`, `run:read`, `run:support` |
| `run:read` | present |
| `request:read` | present |
| `run:support` | present |

`keyhole whoami --json` confirmed `mode=real` for the same human subject.

## Historical Timeout Check

Requested expectation:

```text
run_9ea274bca429 -> timed_out
request_id = req_6996c4b7f0dd
reason/code = GOVERNED_EXECUTION_TIMEOUT
```

Observed public status:

| Identifier | Expected | Observed | Result |
| --- | --- | --- | --- |
| `run_9ea274bca429` | terminal `timed_out`, `req_6996c4b7f0dd`, `GOVERNED_EXECUTION_TIMEOUT` | `PRODUCT_SUBJECT_NOT_FOUND`, no run/request identity | FAIL |
| `req_6996c4b7f0dd` | terminal `timed_out`, `run_9ea274bca429`, `GOVERNED_EXECUTION_TIMEOUT` | `PRODUCT_SUBJECT_NOT_FOUND`, no run/request identity | FAIL |

CLI confirmation also failed:

```text
keyhole runs status run_9ea274bca429 -> PRODUCT_SUBJECT_NOT_FOUND
keyhole runs status req_6996c4b7f0dd -> PRODUCT_SUBJECT_NOT_FOUND
```

## Prior Accepted Run Projection

Requested accepted run:

```text
run_id = run_44b628c7c8d4
request_id = req_5de7eff0e75e
```

Observed through public `run.status`:

| Surface | Run ID | Request ID | Result |
| --- | --- | --- | --- |
| Top-level product status data | `run_b36898803e72` | `req_5de7eff0e75e` | FAIL: run ID is product-operation envelope, not `run_44b628c7c8d4` |
| Nested `result` | `run_44b628c7c8d4` | `req_5de7eff0e75e` | PASS |
| Nested `receipt` | `run_44b628c7c8d4` | `req_5de7eff0e75e` | PASS |
| Nested `output` | `run_44b628c7c8d4` | `req_5de7eff0e75e` | PASS |
| Nested `run.result` | `run_44b628c7c8d4` | `req_5de7eff0e75e` | PASS |

The accepted run still has an accepted governed result:

| Field | Value |
| --- | --- |
| Status | `succeeded` |
| Verdict | `ACCEPT` |
| Proof | `gproof_a4dd582f70864c5085f7ccb8` |
| Receipt | `grcpt_7c9e26a13faaffa25238c4da` |

However, the requested top-level/nested canonical identity equality is not met.

## Fresh Governed Execution

The blessed example gap was stale at the start of the run. It was reopened
through the public SDK:

| Field | Value |
| --- | --- |
| Gap | `gap_8488f30fb4e1ef82` |
| `gaps create` run | `run_c35c225c308a` |
| `gaps create` request | `req_6dc57c54e43b` |
| `gaps create` correlation | `c92cfa66-eec6-49b8-835b-8a6afb4ed9f4` |
| Reopened state | `OPEN`, `claimable=true` |

One launch attempt failed closed at the server event persistence gate:

```text
CANONICAL_EVENT_PERSIST_FAILED:
Cannot start run - authoritative lifecycle record could not be established
```

The unchanged governed flow was retried with the explicit canonical
`--gap-id gap_8488f30fb4e1ef82`, and the retry completed successfully.

Fresh governed execution:

| Field | Value |
| --- | --- |
| Repo commit | `f65f044411bec59f7e5d42aad69e4d0c0da74951` |
| Gap | `gap_8488f30fb4e1ef82` |
| Claim | `30b62ac2934ceeedb1a9a1ed5faaf1c8` |
| Registration | `repo_1da56cceb637de1f0195466c` |
| Governance context | `gctx_052a66ee3808b6d61d14f6bb65bf8cd2` |
| MCP event ID | `run.complete:45b1fede-38ae-4e14-bdba-11a6f79c423a` |
| Event UUID | `45b1fede-38ae-4e14-bdba-11a6f79c423a` |
| Proof | `gproof_2389e8276d44bfff7bd57d37` |
| Receipt | `grcpt_0cf31c0d2f181c0ac4bce081` |
| Realized at | `2026-07-10T13:15:05.838586Z` |
| Verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event spine evidence | true |

Public product status resolved the fresh governed subject as:

| Field | Value |
| --- | --- |
| Governed subject run | `run_6b16f5e2c477` |
| Governed subject request | `req_1ad99a0cbfe2` |
| Product status top-level run | `run_46dc5a7646e7` / `run_522856ad9d03` on repeated reads |
| Product status top-level request | `req_1ad99a0cbfe2` |

As with the prior accepted run, the product status command's top-level `run_id`
is an observation/envelope run ID, while the terminal summary identifies the
governed subject run.

## Fresh Alias Resolution

Target governed subject:

```text
run_id = run_6b16f5e2c477
request_id = req_1ad99a0cbfe2
```

Alias checks:

| Alias | Supplied value | Resolved subject request | Resolved subject run | Result |
| --- | --- | --- | --- | --- |
| canonical run ID | `run_6b16f5e2c477` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| canonical request ID | `req_1ad99a0cbfe2` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| full MCP event ID | `run.complete:45b1fede-38ae-4e14-bdba-11a6f79c423a` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| bare event UUID | `45b1fede-38ae-4e14-bdba-11a6f79c423a` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| proof ID | `gproof_2389e8276d44bfff7bd57d37` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| receipt ID | `grcpt_0cf31c0d2f181c0ac4bce081` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |
| governance context ID | `gctx_052a66ee3808b6d61d14f6bb65bf8cd2` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | PASS |

Fresh alias result:

```text
aliases resolved = 7/7
```

## Fresh Product Operations

All six operations were invoked through public SDK transport against
`POST /mcp/v1/runs/start`. The product responses now distinguish the
operation/envelope run ID from the governed subject run ID. This document treats
`operation_run_id` as the read operation's own run and `subject_run_id` as the
governed execution under inspection.

| Operation | Subject request | Subject run | Operation run | Evidence | Result |
| --- | --- | --- | --- | --- | --- |
| `run.status` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_6b59e9acdeb3` | resolved, terminal, verdict `ACCEPT`, receipt ref present | PASS |
| `run.explain` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_42bc238e3a62` | resolved, explanation present, verdict `ACCEPT`, proof refs present | PASS |
| `run.tail` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_374b00c0e25b` | resolved, server-backed terminal observations present | PASS |
| `run.budget` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_9dee7e659799` | resolved, `instrumentation_status=AVAILABLE`, `pressure_status=NO_PRESSURE` | PASS |
| `request.inspect` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_be9de456b4d1` | resolved, server-backed, executed, terminal, proof/receipt refs present | PASS |
| `support.bundle` | `req_1ad99a0cbfe2` | `run_6b16f5e2c477` | `run_0d605d7e22d7` | resolved, server-backed, context/events/proof refs/receipt ref present | PASS |

Fresh product result:

```text
product operations passed = 6/6
```

## Verification

| Check | Result |
| --- | --- |
| `keyhole validate examples/second-governed-app --json` | PASS |
| `keyhole whoami --json` | PASS, `mode=real` |
| `keyhole surfaces --json --refresh` | PASS, compatible |
| Historical timeout check | FAIL |
| Prior accepted run top-level/nested identity check | FAIL |
| Fresh governed execution | PASS, terminal `ACCEPT` |
| Fresh aliases | PASS, `7/7` |
| Fresh product operations | PASS, `6/6` |

## Final Assessment

The final unchanged acceptance run proves that fresh governed execution and the
fresh product envelope are now working from the public SDK boundary.

It does not prove complete final acceptance because the requested historical
timeout and prior accepted-run top-level projection checks still fail.

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```
