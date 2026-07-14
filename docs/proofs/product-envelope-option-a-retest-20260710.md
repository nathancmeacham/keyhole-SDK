# Product Envelope Option A Retest - 2026-07-10

## Verdict

```text
PUBLIC SDK OPTION A PRODUCT ENVELOPE: FAIL
```

The fresh human device-flow token has the required product scopes, and the
backend product operations are reachable through the public SDK boundary. The
acceptance flight still fails the Option A contract because the canonical
`run_id` and `request_id` returned through the fresh event correlation do not
resolve as canonical product subjects.

No private server repository, server filesystem, internal database, cluster
access, or backend promotion evidence was used as SDK proof.

## Repository State

| Field | Value |
| --- | --- |
| Branch | `main` |
| SDK HEAD before retest patch | `877a89f14dc0512253a226431c05b3d3a492fcd7` |
| Upstream `origin/main` during retest | `47c896bb17b8aa8b86f3e1a63fbafdff4473ba3c` |
| Public MCP boundary | `https://mcp.keyholesolution.com` |
| Server promotion context | `713916bd-7f06-4f1f-b3a9-4d59dbf38ef8` |
| Live digest context | `sha256:fde9e6bb1378370141c2991afa26668f6057f65cdffdd438dbeda2331096876d` |

## Human Device-Flow Proof

Fresh device authorization was completed through the public SDK CLI after the
Option A backend promotion. Raw tokens were not printed or committed.

| Field | Safe Evidence |
| --- | --- |
| Auth mode | `real` |
| Flow | `device` |
| Client | `keyhole-cli` |
| Subject | `c2a432d8-0164-499b-ad84-b662e1f174ec` |
| Tenant | `tenant-6f4f45b96f64` |
| Org | `org-bf06d8b73238` |
| Workspace | `ws:tenant-6f4f45b96f64:cohort-0:default` |
| Access token issued at | `2026-07-10T08:38:11Z` |
| Access token expires at | `2026-07-10T08:53:11Z` |
| `run:read` | present |
| `request:read` | present |
| `run:support` | present |

The granted safe scope names observed from the fresh token were:

```text
email
openid
profile
request:read
run:read
run:support
```

## Capabilities Observation

The public boundary advertises the Option A run types through
`/mcp/v1/runs/start`:

```text
run.status
run.explain
request.inspect
support.bundle
run.tail
run.budget
```

The public `keyhole surfaces --json --refresh` command returned
`success=true`, compatibility `compatible`, `required_missing=[]`, and
`optional_missing=[]`.

## Fresh Governed Execution

The fresh governed execution used the blessed public example:
`examples/second-governed-app`.

| Field | Value |
| --- | --- |
| Gap | `gap_8488f30fb4e1ef82` |
| Claim | `09598c07ea09d5a6f1b4da75af8eb997` |
| Repo registration | `repo_1da56cceb637de1f0195466c` |
| Governance context | `gctx_74d37cdc6a9d7de72a173288b7936c28` |
| MCP event | `run.complete:090ddd86-82d0-4bcd-9bac-5104be43d48f` |
| Proof | `gproof_fc56c34e132180f4a4306768` |
| Receipt | `grcpt_7c9e26a13faaffa25238c4da` |
| Realized at | `2026-07-10T08:32:09.251372Z` |
| Verdict | `ACCEPT` |
| Drift | `non_drifted` |

The initial `keyhole governed run`, `governed resume`, `governed status --last`,
and `governed receipt --last` outputs did not expose a non-empty top-level
`run_id` or `request_id`. That alone blocks full Option A acceptance under the
directive.

After the SDK status parser was corrected to consume server `identity_refs`,
`keyhole runs status 090ddd86-82d0-4bcd-9bac-5104be43d48f --json` exposed:

| Field | Value |
| --- | --- |
| Resolved | `true` |
| Server backed | `true` |
| Status | `success` |
| Terminal | `true` |
| Canonical run from `identity_refs` | `run_37dd7df5699f` |
| Canonical request from `identity_refs` | `req_74f97c69516e` |

## Product Operation Results

Primary flight requirement: every operation must succeed using the canonical
`run_id` and return the same canonical `run_id` and `request_id`.

| Operation | Primary input | Result | Evidence |
| --- | --- | --- | --- |
| `run.status` | `run_37dd7df5699f` | FAIL | `PRODUCT_SUBJECT_NOT_FOUND` |
| `run.explain` | `run_37dd7df5699f` | FAIL | `PRODUCT_SUBJECT_NOT_FOUND` |
| `run.tail` | `run_37dd7df5699f` | FAIL | `PRODUCT_SUBJECT_NOT_FOUND` |
| `run.budget` | `run_37dd7df5699f` | FAIL | `PRODUCT_SUBJECT_NOT_FOUND` |
| `request.inspect` | `req_74f97c69516e` | FAIL | `server_backed=false`, `executed=false`, `state=never_seen` |
| `support.bundle` | `run_37dd7df5699f` | FAIL | `PRODUCT_SUBJECT_NOT_FOUND` |

The same operations were probed with the bare event UUID. Those server-backed
probes reached product behavior and returned the expected identity references,
but this does not satisfy the directive because the canonical `run_id` and
`request_id` themselves are still not resolvable product subjects.

| Operation | Bare event UUID result |
| --- | --- |
| `run.status` | PASS, `status=succeeded`, `identity_refs.run_id=run_37dd7df5699f`, `identity_refs.request_id=req_74f97c69516e` |
| `run.explain` | PASS, `server_backed=true`, `outcome_class=accepted`, `status=succeeded` |
| `run.tail` | PASS, `server_backed=true`, `observation_method=server_tail`, `terminal=true` |
| `run.budget` | PASS, `server_backed=true`, `limit_outcome=success_with_budget_visibility` |
| `request.inspect` | PASS only when invoked with the bare event UUID, not the canonical `request_id` |
| `support.bundle` | PASS, `server_backed=true`, `redacted=true`, manifest present |

## Alias Resolution Matrix

`run.status` was invoked against every required alias.

| Alias | Input | Result |
| --- | --- | --- |
| Canonical run ID | `run_37dd7df5699f` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |
| Canonical request ID | `req_74f97c69516e` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |
| Full MCP event ID | `run.complete:090ddd86-82d0-4bcd-9bac-5104be43d48f` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |
| Bare event UUID | `090ddd86-82d0-4bcd-9bac-5104be43d48f` | PASS, resolves identity refs |
| Proof ID | `gproof_fc56c34e132180f4a4306768` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |
| Receipt ID | `grcpt_7c9e26a13faaffa25238c4da` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |
| Governance context ID | `gctx_74d37cdc6a9d7de72a173288b7936c28` | FAIL, `PRODUCT_SUBJECT_NOT_FOUND` |

## SDK Change Made During Retest

The SDK status parser was updated so it no longer masks this shape as a
successful `UNKNOWN` status:

- `succeeded` is classified as terminal success.
- Server `identity_refs` and receipt references are surfaced as the canonical
  `run_id`, `request_id`, and correlation fields.
- Product `ok=false` responses now return a failed command result with the
  server error code, including `PRODUCT_SUBJECT_NOT_FOUND`.
- `keyhole runs status --json` now emits `request_id`, `resolved`, and
  `server_backed` fields.

This is an honesty fix, not a client-side alias workaround.

## Verification

| Check | Result |
| --- | --- |
| Fresh `whoami --json` | PASS, `mode=real` |
| `surfaces --json --refresh` | PASS, compatible |
| `validate examples/second-governed-app --json` | PASS |
| `doctor launch --repo-dir examples/second-governed-app --json` | PASS before fresh run |
| Fresh `governed run` | PASS, verdict `ACCEPT` |
| Focused unit tests | PASS, `85 passed` in `test_sdk_client_17_run_lifecycle.py` |
| Full unit tests | PASS, `3680 passed` |
| `git diff --check` | PASS |
| Hygiene scan | PASS, no hits |
| Generated proof-bundle tracking check | PASS, no tracked `.keyhole` or `proof_bundle` paths |

## Blocking Defect

The remaining blocker is not missing human scopes. It is product subject
resolution for the canonical identifiers:

```text
run.status(canonical run_id) -> PRODUCT_SUBJECT_NOT_FOUND
run.status(canonical request_id) -> PRODUCT_SUBJECT_NOT_FOUND
request.inspect(canonical request_id) -> server_backed=false, executed=false
full event/proof/receipt/governance aliases -> PRODUCT_SUBJECT_NOT_FOUND
```

The SDK must not convert the bare event UUID into a fake primary `run_id`, and
it must not reconstruct the alias graph locally. The server resolver remains
authoritative, so full Option A acceptance stays blocked until canonical
`run_id`, canonical `request_id`, and the required aliases resolve to the same
server-backed product subject.
