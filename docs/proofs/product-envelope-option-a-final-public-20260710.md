# Product Envelope Option A Final Public Acceptance - 2026-07-10

## Verdict

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```

Failure classification:

```text
SERVER TERMINAL IDENTITY PROJECTION: FAIL
```

The repaired production fixture now passes public alias resolution and all six
Option A product operations. A new post-repair governed execution did not reach
terminal realization through the public SDK: it remained at
`governance.context.create` with status `running` until the CLI timeout and an
additional explicit wait timeout.

No backend filesystem, database, Kubernetes access, backend evidence files,
service tokens, or local alias mappings were used.

## Deployment Context

| Field | Value |
| --- | --- |
| Promotion UUID | `265a2dd8-1a7f-48e3-8505-4f24056c6642` |
| Production digest | `sha256:a5dee23315c1e5cc9e214f2e80498183300e30cb42b5e96aa5a8ad60a21404b6` |
| Public boundary | `https://mcp.keyholesolution.com` |
| Capabilities | `surfaces --json --refresh` returned compatible, `required_missing=[]`, `optional_missing=[]` |
| Product features | `explainability=true`, `support_bundle=true`, `run_tail=true`, `budget_visibility=true` |

## Repository State

| Field | Value |
| --- | --- |
| Branch | `main` |
| HEAD before this proof doc | `20862bc837999a2436f96a2f8b9f649b0f86c2f0` |
| `origin/main` | `47c896bb17b8aa8b86f3e1a63fbafdff4473ba3c` |
| Upstream | `origin/main` |
| Starting working tree | clean, `main...origin/main [ahead 17]` |

## Human Authentication

The stale local session was cleared with `keyhole logout --json`, then a fresh
human device-flow login was completed through the public SDK CLI.

| Field | Safe Evidence |
| --- | --- |
| Device flow completed | yes |
| Fresh token confirmed | yes |
| Client | `keyhole-cli` |
| Subject | `c2a432d8-0164-499b-ad84-b662e1f174ec` |
| Tenant | `tenant-6f4f45b96f64` |
| Org | `org-bf06d8b73238` |
| Workspace | `ws:tenant-6f4f45b96f64:cohort-0:default` |
| Issued at | `2026-07-10T09:28:14Z` |
| Expires at | `2026-07-10T09:43:14Z` |
| `run:read` | present |
| `request:read` | present |
| `run:support` | present |

Recorded safe scope names:

```text
email
openid
profile
request:read
run:read
run:support
```

## Repaired Fixture

Previously failed fixture:

| Field | Value |
| --- | --- |
| `request_id` | `req_74f97c69516e` |
| `run_id` | `run_37dd7df5699f` |
| `governance_context_id` | `gctx_74d37cdc6a9d7de72a173288b7936c28` |
| `mcp_event_id` | `run.complete:090ddd86-82d0-4bcd-9bac-5104be43d48f` |
| Bare event UUID | `090ddd86-82d0-4bcd-9bac-5104be43d48f` |
| `proof_id` | `gproof_fc56c34e132180f4a4306768` |
| `receipt_id` | `grcpt_7c9e26a13faaffa25238c4da` |

Seven-alias `run.status` resolution:

| Alias | Input | Resolved Request | Resolved Run | Verdict | Result |
| --- | --- | --- | --- | --- | --- |
| canonical run ID | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| canonical request ID | `req_74f97c69516e` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| full MCP event ID | `run.complete:090ddd86-82d0-4bcd-9bac-5104be43d48f` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| bare event UUID | `090ddd86-82d0-4bcd-9bac-5104be43d48f` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| proof ID | `gproof_fc56c34e132180f4a4306768` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| receipt ID | `grcpt_7c9e26a13faaffa25238c4da` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |
| governance context ID | `gctx_74d37cdc6a9d7de72a173288b7936c28` | `req_74f97c69516e` | `run_37dd7df5699f` | `ACCEPT` | PASS |

Fixture product operations:

| Operation | Input | Resolved Request | Resolved Run | Assertion | Result |
| --- | --- | --- | --- | --- | --- |
| `run.status` | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | terminal `succeeded`, verdict `ACCEPT` | PASS |
| `run.explain` | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | `server_backed=true`, decision verdict `ACCEPT`, explanation present | PASS |
| `run.tail` | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | `server_tail`, terminal, observations present | PASS |
| `run.budget` | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | `instrumentation_status=AVAILABLE`, `pressure_status=NO_PRESSURE` | PASS |
| `request.inspect` | `req_74f97c69516e` | `req_74f97c69516e` | `run_37dd7df5699f` | `server_backed=true`, `executed=true`, terminal | PASS |
| `support.bundle` | `run_37dd7df5699f` | `req_74f97c69516e` | `run_37dd7df5699f` | context, events, proof refs, receipt ref present | PASS |

## Fresh Post-Repair Execution

The stale gap was reopened through public SDK behavior:

```text
gaps create -> accepted
run_id = run_a318cf02402a
request_id = req_c5d6ffbc2eb2
```

`gaps list` then returned `gap_8488f30fb4e1ef82` as `OPEN`,
`claimable=true`, and revalidated on the promoted digest
`sha256:a5dee23315c1e5cc9e214f2e80498183300e30cb42b5e96aa5a8ad60a21404b6`.

`doctor launch --repo-dir examples/second-governed-app --json` passed and
resolved `gap_8488f30fb4e1ef82`.

Fresh governed execution attempt:

| Field | Value |
| --- | --- |
| Run record | `20260710T093149781633Z` |
| Step | `context_create` |
| Status | `running` |
| Terminal | `false` |
| `run_id` | `run_73c3fe93019b` |
| `request_id` | `req_58b5d3f2181d` |
| Correlation | `b995ce8d-8ad5-4f64-923f-51981693797b` |
| Gap | `gap_8488f30fb4e1ef82` |
| Claim | `22eb15af22c4db64771b067f65818469` |
| Run type | `governance.context.create` |
| Started at | `2026-07-10T09:31:52.838601+00:00` |

The initial `keyhole governed run` failed with:

```text
repo registration did not reach a terminal run status before timeout
```

An explicit wait also failed:

```text
keyhole runs wait run_73c3fe93019b --poll-interval 5 --max-polls 24
-> wait_timeout after 24 polls, 127.16 seconds
```

Final status snapshot:

```text
run_id = run_73c3fe93019b
request_id = req_58b5d3f2181d
status = running
is_terminal = false
run_type = governance.context.create
resolved = true
server_backed = true
```

Because the fresh run did not produce a terminal governed `ACCEPT`, there is no
fresh final `governance_context_id`, `mcp_event_id`, `proof_id`, `receipt_id`,
or terminal product-envelope correlation set to validate.

## Fresh Product Flight

Not run. The directive requires a fresh governed terminal `ACCEPT` with
non-empty canonical `run_id` and `request_id` before the six product operations
can be validated for that execution.

| Operation | Result |
| --- | --- |
| `run.status` | NOT RUN for fresh terminal execution |
| `run.explain` | NOT RUN for fresh terminal execution |
| `run.tail` | NOT RUN for fresh terminal execution |
| `run.budget` | NOT RUN for fresh terminal execution |
| `request.inspect` | NOT RUN for fresh terminal execution |
| `support.bundle` | NOT RUN for fresh terminal execution |

## Verification

| Check | Result |
| --- | --- |
| `validate examples/second-governed-app --json` | PASS |
| `validate my-first-app --json` | PASS |
| Focused lifecycle/product tests | PASS, `447 passed` |
| Full SDK unit tests | PASS, `3680 passed` |
| `git diff --check` | PASS |
| Hygiene scan | PASS, no hits |
| Generated proof-bundle tracking check | PASS, no tracked `.keyhole` or `proof_bundle` paths |
| Working-tree status | only this evidence document was untracked before commit |

## Summary

The final public proof improved from the prior failure:

```text
repaired fixture aliases: 7/7 PASS
repaired fixture product operations: 6/6 PASS
fresh human device-flow scopes: PASS
fresh governed post-repair execution: FAIL, non-terminal context_create timeout
```

Option A is therefore not fully accepted from the public SDK boundary yet.
