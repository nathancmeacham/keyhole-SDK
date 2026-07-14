# Product Envelope Proof - 2026-07-09

## Verdict

**PASS_WITH_LIMITATION - Public technical preview accepted, complete product-envelope launch blocked.**

The public SDK path produced a fresh governed `ACCEPT` receipt with Event Spine, proof, receipt, and governance-context evidence. The complete product-envelope gate did **not** pass because the fresh governed run did not expose a durable `run_id` or `request_id`, and the optional observability surfaces could not bind to the accepted chain.

Latest retest after backend registry promotion narrows the blocker: product
run types are no longer rejected as `UNKNOWN_RUN_TYPE`, but public SDK
end-to-end product-envelope proof still fails because the fresh governed
receipt/status do not expose durable run/request identity and direct product
run-type dispatch is denied by missing public binding scopes.

## Scope

| Field | Value |
| --- | --- |
| Proof time | 2026-07-09T09:31:24Z through 2026-07-09T09:40:38Z |
| SDK commit | `37f69e6ef314e7050552c18a495fd3b4704352b8` |
| MCP URL | `https://mcp.keyholesolution.com` |
| Realm | `kh-prod` |
| Identity class | Public device-login builder |
| Repo | Public Keyhole SDK / developer kit |
| Proof checkout | `<TEMP>/keyhole-sdk-product-envelope-proof` |
| Blessed example | `examples/second-governed-app` |
| Capability | `second-governed-app.echo.user.v1` |

Proof checkout limitation: the final proof checkout was refreshed from the local SDK repo because commits through `37f69e6` were not yet present on `origin/main`. The checkout remote was set to `https://github.com/Keyhole-Solution/keyhole-SDK.git`, and live repo facts used that GitHub remote. No private platform source, private database access, manual Event Spine mutation, or proof-store mutation was used.

## Fresh Governed Chain

| Field | Value |
| --- | --- |
| Gap ID | `gap_8488f30fb4e1ef82` |
| Gap pre-run state | `OPEN`, `claimable=true`, `blocked=false` |
| Governed run status | `succeeded` |
| Governance verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event Spine evidence | `true` |
| Run ID | Empty / not returned |
| Request ID | Not returned |
| Correlation ID | `1df1cdcb-ab22-476b-8127-a8b0e3e30d30` |
| Governance context ID | `gctx_217433e9ca3f30e40c1cf430dee3430d` |
| MCP event ID | `run.complete:1df1cdcb-ab22-476b-8127-a8b0e3e30d30` |
| Proof ID | `gproof_ee9031fb6b40f436f72308d5` |
| Receipt ID | `grcpt_37161dff800ed2299845d771` |

## Surface Evidence

| Surface | Required Result | Actual Result |
| --- | --- | --- |
| whoami | `mode=real` | PASS: `success=true`, `mode=real`, public identity visible, no tokens printed. |
| surfaces | compatible, no missing | PASS as advertised: `compatibility.status=compatible`, `required_missing=[]`, `optional_missing=[]`; flags true for async runs, explain, support bundle, tail, budget, context requirement, and idempotency. |
| gaps list | `claimable=true`, `blocked=false` | PASS before final run and after release: `gap_8488f30fb4e1ef82`, `OPEN`, `claimable=true`, `blocked=false`. |
| validate | PASS | PASS for `examples/second-governed-app`; schema, dependencies, namespace, compatibility all PASS. |
| doctor launch | PASS | PASS at commit `37f69e6`, live MCP URL, GitHub remote, actionable gap availability. |
| governed run/resume | ACCEPT | PASS: fresh `governed run` reached `ACCEPT`, `event_spine_evidence=true`, `drift_state=non_drifted`. |
| governed status | terminal, same ID chain | PARTIAL: local status is terminal/succeeded and live-confirmed, but `run_id` is empty and no `request_id` is present. |
| governed receipt | proof/event/receipt evidence | PASS for receipt evidence: `proof_id`, `receipt_id`, `mcp_event_id`, context ID, verdict, and drift state present. Missing durable run/request identity. |
| run.explain | server-backed, not unknown | FAIL: probing the fresh correlation/event UUID returned `outcome_class=unknown`, `is_terminal=false`, empty context/event/proof refs, and inferred reason. |
| request.inspect | linked request/run/proof/receipt | FAIL: returned `outcome_class=unknown`, empty `run_id`, `executed=false`, and no link to proof/receipt. |
| support.bundle | redacted manifest, required refs | FAIL: local bundle assembled but missing `context`, `events`, and `proof_refs`; not sufficient as server-backed support bundle evidence. |
| runs tail | server-backed ordered observations | FAIL: `observation_method=status_poll`, one `unknown` entry, no terminal observation or server-backed ordering/cursor proof. |
| runs budget | structured run-level budget posture | FAIL: `limit_outcome=no_pressure_data`, empty request/correlation/status linkage, empty budget snapshot. |
| unit tests | pass | PASS: clean proof checkout `tests/unit` returned `3678 passed in 73.70s`; release gate repeated unit suite with `3678 passed in 75.05s`. |
| release gate | pass | PASS: `scripts/public-release-gate.ps1 -IncludeLiveProof` completed with live identity, surfaces, doctor, status, and receipt. It warned only about ignored local generated artifacts. |
| git safety | no generated state tracked | PASS: `git ls-files` returned no `.keyhole` or `proof_bundle` paths; `git diff --check` passed. |

## Capability Advertisement

`keyhole surfaces --json --refresh` advertised the complete envelope as compatible. Raw capabilities also reported:

| Field | Value |
| --- | --- |
| `operations_count` | `30` |
| `operations_declared` | `30` |
| `operations_implemented` | `12` |
| Product run types | `run.status`, `run.budget`, `run.explain`, `request.inspect`, `support.bundle`, `run.tail` |
| Product transport | All listed as `POST /mcp/v1/runs/start`, `transport=runs_start`, `status=live`, `read_only=true` |

The advertisement and behavior do not agree for this fresh accepted governed chain.

## Commands Run

```powershell
git status --short
git diff --stat
git diff --check
git log --oneline origin/main..main
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e packages/python/keyhole-sdk -e packages/python/keyhole-cli pytest
.\.venv\Scripts\python.exe -m keyhole_cli.cli login --help
.\.venv\Scripts\python.exe -m keyhole_cli.cli whoami --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli surfaces --json --refresh
curl.exe -s https://mcp.keyholesolution.com/mcp/v1/capabilities
.\.venv\Scripts\python.exe -m keyhole_cli.cli gaps list --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli validate examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli doctor launch --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli governed run --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli governed status --repo-dir examples\second-governed-app --last --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli governed receipt --repo-dir examples\second-governed-app --last --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli runs status 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli explain run 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli inspect 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli support-bundle 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli runs tail 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --poll-interval 0.2 --max-entries 3 --json
.\.venv\Scripts\python.exe -m keyhole_cli.cli runs budget 1df1cdcb-ab22-476b-8127-a8b0e3e30d30 --repo-dir examples\second-governed-app --json
.\.venv\Scripts\python.exe -m pytest tests\unit -q --basetemp .pytest-tmp
.\.venv\Scripts\python.exe -m pytest tests -q --basetemp .pytest-tmp
powershell -ExecutionPolicy Bypass -File .\scripts\public-release-gate.ps1 -IncludeLiveProof
git ls-files -- .keyhole proof_bundle examples/second-governed-app/.keyhole examples/second-governed-app/proof_bundle my-first-app/.keyhole my-first-app/proof_bundle
```

Interactive forced login was not rerun during this proof because an active public device-login session was already verified by `whoami`. CLI help at this commit shows `--flow` defaulting to `device`, and `--mcp-url` defaulting to `https://mcp.keyholesolution.com`; the login/default-flow behavior is covered by the unit suite.

## Test Results

| Check | Result |
| --- | --- |
| Focused public release-gate unit coverage | PASS: `3 passed` before committing gate fixes. |
| Clean proof `tests/unit` | PASS: `3678 passed in 73.70s`. |
| Clean proof broader `tests` | FAIL: `3684 passed, 92 skipped, 1 failed`; only failure was smoke prerequisite `jq not found in PATH`. |
| Public release gate with live proof | PASS: completed after unit tests, validation, sanitation scan, generated-state tracking scan, live identity, surfaces, doctor, status, and receipt. |

## Changes Made During Proof

Two public release-gate fixes were committed after the governed-flow fix:

1. `545d115` - install `setuptools` and `services/test-runtime/requirements.txt` in the release gate so a clean venv can build wheels and run unit tests.
2. `37f69e6` - check generated governance artifacts with `git ls-files`; ignored local proof state now warns instead of failing the live proof gate.

These fixes keep generated `.keyhole` and `proof_bundle` artifacts untracked while allowing `-IncludeLiveProof` to read the local status/receipt created by the live proof run.

## Retry After Server Advance

Retried after the server advanced, from the same public SDK path.

| Field | Value |
| --- | --- |
| Retry time | 2026-07-09T12:07:22Z through 2026-07-09T12:19:18Z |
| Starting SDK commit | `91dd27f5b419e511c26cee63b1c025a87ef729ec` |
| SDK preflight fix commit | `ce8fc073c097315f833b889be7e5febb764c8da6` |
| MCP URL | `https://mcp.keyholesolution.com` |
| Realm | `kh-prod` |
| Device login | PASS after reauth; no localhost callback was forced. |

Server-side improvements observed:

- `gaps.list` now returns durable read-surface `run_id` and `request_id` fields.
- `gaps.submit` accepted materialize/reopen for the stale blessed gap with `run_id=run_def7ed934c56` and `request_id=req_69a70dd485d1`.
- After `gaps.submit`, the blessed gap returned to `OPEN`, `claimable=true`, `blocked=false`.
- A fresh governed run then reached `ACCEPT` again.

Fresh retry governed chain:

| Field | Value |
| --- | --- |
| Governed run commit | `91dd27f5b419e511c26cee63b1c025a87ef729ec` |
| Gap ID | `gap_8488f30fb4e1ef82` |
| Governance verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event Spine evidence | `true` |
| Run ID | Empty / not returned by governed status |
| Request ID | Not returned by governed status |
| Correlation ID | `fabab34d-711d-47fe-bad6-26bec1a009de` |
| Governance context ID | `gctx_f9e4fe64efbce2f42207b2658e7693d0` |
| MCP event ID | `run.complete:fabab34d-711d-47fe-bad6-26bec1a009de` |
| Proof ID | `gproof_2fe7122e98be17632d38b34c` |
| Receipt ID | `grcpt_c7fff31e5ce32b73a68261f9` |

High-level optional surface retry against `fabab34d-711d-47fe-bad6-26bec1a009de`:

| Surface | Retry Result |
| --- | --- |
| `runs status` | Still `status=unknown`, `is_terminal=false`. |
| `run.explain` | Still `outcome_class=unknown`, empty event/proof refs, inferred reason. |
| `request.inspect` | Still `outcome_class=unknown`, empty `run_id`, `executed=false`. |
| `support.bundle` | Still missing `context`, `events`, and `proof_refs`. |
| `runs tail` | Still `observation_method=status_poll`, terminal state absent. |
| `runs budget` | Still `limit_outcome=no_pressure_data` with empty request/correlation/status linkage. |

SDK fix made during retry:

- `ce8fc07` adds `run.status`, `run.explain`, `request.inspect`, `support.bundle`, `run.tail`, and `run.budget` to dispatch preflight and schema hints.
- Focused test passed: `tests/unit/test_s42_06_run_type_safety.py` returned `77 passed`.

Generic `/runs/start` product run-type retry after SDK preflight fix:

| Run Type | Retry Result |
| --- | --- |
| `run.status` | Server returned `UNKNOWN_RUN_TYPE: run.status (not in scope mapping)`. |
| `run.explain` | Server returned `UNKNOWN_RUN_TYPE: run.explain (not in scope mapping)`. |
| `request.inspect` | Server returned `UNKNOWN_RUN_TYPE: request.inspect (not in scope mapping)`. |
| `support.bundle` | Server returned `UNKNOWN_RUN_TYPE: support.bundle (not in scope mapping)`. |
| `run.tail` | Server returned `UNKNOWN_RUN_TYPE: run.tail (not in scope mapping)`. |
| `run.budget` | Server returned `UNKNOWN_RUN_TYPE: run.budget (not in scope mapping)`. |

Updated retry verdict: **PASS_WITH_LIMITATION remains.** The server advanced gap materialization and read-run identity, but complete product-envelope launch is still blocked because capabilities advertise product run types as live while `/runs/start` rejects them as unknown, and the accepted `governed.realize` receipt still does not expose a durable run/request identity.

## Retest After Backend Registry Promotion

Retested again after the backend registry/scope fix was promoted. This run
started from clean local generated proof state for `examples/second-governed-app`
by removing ignored `.keyhole/` and `proof_bundle/` artifacts under that example
repo before rerunning the authenticated sequence.

| Field | Value |
| --- | --- |
| Retest time | 2026-07-09T13:20:51Z through 2026-07-09T13:31:59Z |
| SDK commit | `4f7ccfd284cb8ecf316083b1f1062812ffdf8258` |
| MCP URL | `https://mcp.keyholesolution.com` |
| Realm | `kh-prod` |
| Device login | PASS after forced device reauth. |
| Identity | `whoami` PASS, `mode=real`, actor envelope present. |
| Surfaces | PASS as advertised: `compatibility.status=compatible`, no required or optional misses. |

Fresh setup and launch evidence:

| Surface | Result |
| --- | --- |
| `gaps list` before materialization | `gap_8488f30fb4e1ef82` was `STALE`, `claimable=false`, required `materialize_or_reopen_gap`; read surface returned `run_id=run_1ebbc82a79af`, `request_id=req_a14288bf061a`. |
| `gaps create` | PASS/ACCEPTED: materialize/reopen accepted with `run_id=run_437113c02b93`, `request_id=req_d51335b6c56d`. |
| `gaps list` after materialization | PASS: gap became `OPEN`, `claimable=true`, `blocked=false`; read surface returned `run_id=run_6fb5edfc7fd1`, `request_id=req_d5e2e93e9b59`. |
| Clean-state `gaps list` | PASS after removing generated proof state: gap remained `OPEN`, `claimable=true`, `blocked=false`; read surface returned `run_id=run_8ef000fb6a82`, `request_id=req_a936da8949dd`. |
| `validate` | PASS for `examples/second-governed-app`. |
| `doctor launch` | PASS from clean state with `resolved_gap_id=gap_8488f30fb4e1ef82`. |

Fresh governed chain from clean state:

| Field | Value |
| --- | --- |
| Governed run commit | `4f7ccfd284cb8ecf316083b1f1062812ffdf8258` |
| Run record ID | `20260709T132936813467Z` |
| Created at | `2026-07-09T13:29:36.813467+00:00` |
| Realized at | `2026-07-09T13:31:12.570920Z` |
| Gap ID | `gap_8488f30fb4e1ef82` |
| Claim ID | `e3b6617e0ccc188cdc86fbf153bd9dee` |
| Registration ID | `repo_1da56cceb637de1f0195466c` |
| Governance verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event Spine evidence | `true` |
| Run ID | Empty / not returned by governed status or receipt |
| Request ID | Not returned by governed status or receipt |
| Correlation/event UUID | `5457a499-df1c-443d-8b56-610e944db642` |
| Governance context ID | `gctx_fbc475b861fdedf05aafb7c68ecc99c4` |
| MCP event ID | `run.complete:5457a499-df1c-443d-8b56-610e944db642` |
| Proof ID | `gproof_b2e0d107fd03cb9a9bce24f1` |
| Receipt ID | `grcpt_9a894ba42b847bab9d14eaf2` |

High-level optional surface retry against the fresh event UUID
`5457a499-df1c-443d-8b56-610e944db642`:

| Surface | Result |
| --- | --- |
| `runs status` | `status=unknown`, `is_terminal=false`. |
| `run.explain` | `outcome_class=unknown`, no event/proof refs, inferred reason. |
| `request.inspect` | `outcome_class=unknown`, empty `run_id`, `executed=false`. |
| `support.bundle` | Missing `context`, `events`, and `proof_refs`. |
| `runs tail` | `observation_method=status_poll`, one `unknown` entry, no terminal status. |
| `runs budget` | `limit_outcome=no_pressure_data`, empty request/correlation/status linkage. |

Direct `/runs/start` product run-type smoke after the backend promotion:

| Run Type | Result |
| --- | --- |
| `run.status` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.explain` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `request.inspect` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `request:read`. |
| `support.bundle` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:support`. |
| `run.tail` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.budget` | No longer `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |

Updated post-promotion verdict:

```text
SERVER-SIDE REGISTRY FIX: PASS
FULL OPTION A PRODUCT ENVELOPE: FAIL / STILL BLOCKED ON SDK END-TO-END PROOF
```

The original registry split-brain is closed: advertised product run types now
reach server authorization instead of failing as unknown run types. Complete
product-envelope launch is still blocked because the same public SDK identity
cannot execute the advertised product run types with the current binding scopes,
and the fresh governed `ACCEPT` chain still does not expose a durable `run_id`
or `request_id` for the optional product surfaces to bind.

## Retest After Promotion Contract Fix

Retested after the server-side promotion contract fix landed on `main` through
PR `#437` with promotion UUID `0e94d1b3-af99-4d39-a884-98fbc3760be6`.
The server-side landing is accepted as promotion-complete, but the public SDK
end-to-end product-envelope proof remains blocked.

Capability and negotiation evidence:

| Field | Value |
| --- | --- |
| Retest time | 2026-07-09T14:34:12Z through 2026-07-09T14:38:22Z |
| SDK commit | `78a3926d2930e3e0ea511232944beb64206b46ee` |
| MCP URL | `https://mcp.keyholesolution.com` |
| `whoami` | PASS: `success=true`, `mode=real`, actor envelope present. |
| SDK surfaces | PASS: `compatibility.status=compatible`, no required or optional misses. |
| Raw capabilities | `operations_count=30`, `operations_declared=30`, `operations_implemented=12`. |
| Product flags | `explainability=true`, `support_bundle=true`, `run_tail=true`, `budget_visibility=true`. |
| Product run types found | `request.inspect`, `run.budget`, `run.explain`, `run.status`, `run.tail`, `support.bundle`. |

Fresh setup evidence:

| Surface | Result |
| --- | --- |
| Clean state | Removed ignored `.keyhole/` and `proof_bundle/` under `examples/second-governed-app` before retest. |
| `gaps list` before materialization | Gap was `STALE`, `claimable=false`, `STATUS_NOT_CLAIMABLE`; read surface returned `run_id=run_01f2262a8edc`, `request_id=req_5954464e0539`. |
| `gaps create` | PASS/ACCEPTED with `run_id=run_fe735dfad2c3`, `request_id=req_b9294acdff7d`. |
| `gaps list` after materialization | PASS: gap became `OPEN`, `claimable=true`, `blocked=false`; read surface returned `run_id=run_b4cb0ceff253`, `request_id=req_5407d822e686`. |
| `validate` | PASS for `examples/second-governed-app`. |
| `doctor launch` | PASS with `resolved_gap_id=gap_8488f30fb4e1ef82`. |

Fresh governed chain:

| Field | Value |
| --- | --- |
| Governed run commit | `78a3926d2930e3e0ea511232944beb64206b46ee` |
| Run record ID | `20260709T143518507625Z` |
| Created at | `2026-07-09T14:35:18.507625+00:00` |
| Realized at | `2026-07-09T14:36:58.479707Z` |
| Gap ID | `gap_8488f30fb4e1ef82` |
| Claim ID | `a35754d3ab4beac6c2c38805c6ad6063` |
| Registration ID | `repo_1da56cceb637de1f0195466c` |
| Governance verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event Spine evidence | `true` |
| Run ID | Empty / not returned by governed status or receipt |
| Request ID | Not returned by governed status or receipt |
| Correlation/event UUID | `f72eb447-450d-4b5e-aae8-c67bee9e0160` |
| Governance context ID | `gctx_cd2948f45d0f9241c1fd23ba48d2d2a6` |
| MCP event ID | `run.complete:f72eb447-450d-4b5e-aae8-c67bee9e0160` |
| Proof ID | `gproof_a0ffec367cc866f4ad362f3a` |
| Receipt ID | `grcpt_be1480d6ebaca69cbb59366a` |

High-level product surface retry against fresh event UUID
`f72eb447-450d-4b5e-aae8-c67bee9e0160`:

| Surface | Result |
| --- | --- |
| `runs status` | `status=unknown`, `is_terminal=false`. |
| `run.explain` | `outcome_class=unknown`, no event/proof refs, inferred reason. |
| `request.inspect` | `outcome_class=unknown`, empty `run_id`, `executed=false`. |
| `support.bundle` | Missing `context`, `events`, and `proof_refs`. |
| `runs tail` | `observation_method=status_poll`, one `unknown` entry, no terminal status. |
| `runs budget` | `limit_outcome=no_pressure_data`, empty request/correlation/status linkage. |

Direct `/runs/start` product run-type smoke:

| Run Type | Result |
| --- | --- |
| `run.status` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.explain` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `request.inspect` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `request:read`. |
| `support.bundle` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:support`. |
| `run.tail` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.budget` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |

Updated verdict after PR `#437`:

```text
SERVER-SIDE PROMOTION CONTRACT FIX: PASS
FULL OPTION A PRODUCT ENVELOPE: FAIL / STILL BLOCKED ON SDK END-TO-END PROOF
```

The promotion path is now canonical and the product run-type registry remains
closed. The public SDK launch proof still cannot be claimed complete because
fresh governed `ACCEPT` status/receipt do not expose a durable `run_id` or
`request_id`, and the public builder binding still lacks product scopes
required to execute the advertised run-type surfaces.

## Retest After 2026-07-10 Backend Progress

Retested after the backend progressed again. The public SDK path still proves
fresh governed `ACCEPT`, but full Option A product-envelope proof remains
blocked for the same two reasons: no durable governed run/request identity is
surfaced, and advertised product run types still require scopes absent from the
public builder binding.

Capability and identity evidence:

| Field | Value |
| --- | --- |
| Retest time | 2026-07-10T07:01:13Z through 2026-07-10T07:04:50Z |
| SDK commit | `caeae7aed80330b9d3b0fe6e0e19728298bd4566` |
| MCP URL | `https://mcp.keyholesolution.com` |
| `whoami` | PASS: `success=true`, `mode=real`, actor envelope present. |
| SDK surfaces | PASS: `compatibility.status=compatible`, no required or optional misses. |
| Raw capabilities | `operations_count=30`, `operations_declared=30`, `operations_implemented=12`. |
| Product flags | `explainability=true`, `support_bundle=true`, `run_tail=true`, `budget_visibility=true`. |
| Product run types found | `request.inspect`, `run.budget`, `run.explain`, `run.status`, `run.tail`, `support.bundle`. |

Fresh setup evidence:

| Surface | Result |
| --- | --- |
| Clean state | Removed ignored `.keyhole/` and `proof_bundle/` under `examples/second-governed-app` before retest. |
| `validate` | PASS for `examples/second-governed-app`. |
| `gaps list` | PASS: gap `gap_8488f30fb4e1ef82` was `OPEN`, `claimable=true`, `blocked=false`; read surface returned `run_id=run_d15ac3dc0c89`, `request_id=req_8512fa56895e`. |
| `doctor launch` | PASS with `resolved_gap_id=gap_8488f30fb4e1ef82`. |

Fresh governed chain:

| Field | Value |
| --- | --- |
| Governed run commit | `caeae7aed80330b9d3b0fe6e0e19728298bd4566` |
| Run record ID | `20260710T070153294886Z` |
| Created at | `2026-07-10T07:01:53.294886+00:00` |
| Realized at | `2026-07-10T07:03:31.077987Z` |
| Gap ID | `gap_8488f30fb4e1ef82` |
| Claim ID | `7d2ca145a79e05d0091c58ce9666cb07` |
| Registration ID | `repo_1da56cceb637de1f0195466c` |
| Governance verdict | `ACCEPT` |
| Drift state | `non_drifted` |
| Event Spine evidence | `true` |
| Run ID | Empty / not returned by governed status or receipt |
| Request ID | Not returned by governed status or receipt |
| Correlation/event UUID | `cb754216-1813-4239-a345-4ae8a9b6601d` |
| Governance context ID | `gctx_90a508fc5e7d0832b70755bd1c9b56fd` |
| MCP event ID | `run.complete:cb754216-1813-4239-a345-4ae8a9b6601d` |
| Proof ID | `gproof_14bc03fed1601334a08bdb7a` |
| Receipt ID | `grcpt_6096518577e2f2f01d932fca` |

High-level product surface retry against fresh event UUID
`cb754216-1813-4239-a345-4ae8a9b6601d`:

| Surface | Result |
| --- | --- |
| `runs status` | `status=unknown`, `is_terminal=false`. |
| `run.explain` | `outcome_class=unknown`, no event/proof refs, inferred reason. |
| `request.inspect` | `outcome_class=unknown`, empty `run_id`, `executed=false`. |
| `support.bundle` | Missing `context`, `events`, and `proof_refs`. |
| `runs tail` | `observation_method=status_poll`, one `unknown` entry, no terminal status. |
| `runs budget` | `limit_outcome=no_pressure_data`, empty request/correlation/status linkage. |

Direct `/runs/start` product run-type smoke:

| Run Type | Result |
| --- | --- |
| `run.status` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.explain` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `request.inspect` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `request:read`. |
| `support.bundle` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:support`. |
| `run.tail` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |
| `run.budget` | No `UNKNOWN_RUN_TYPE`; blocked with `SCOPE_DENIED` for missing `run:read`. |

Updated verdict after 2026-07-10 backend progress:

```text
SERVER-SIDE PRODUCT RUN-TYPE REGISTRY: PASS
FULL OPTION A PRODUCT ENVELOPE: FAIL / STILL BLOCKED ON SDK END-TO-END PROOF
```

The backend no longer rejects advertised product run types as unknown. The
remaining launch blockers are still backend-owned product-envelope contracts:
fresh governed `ACCEPT` status/receipt must expose durable `run_id` or
`request_id`, and the public builder binding must include the advertised
product scopes or the server must stop advertising those features as live.

## Failure Classification

Latest primary classification: **Backend product-envelope launch blocker,
narrowed to durable identity plus public binding authorization.**

Reasons:

- The fresh governed chain reached `ACCEPT` but did not expose `run_id` or `request_id`.
- Capabilities advertised `run.explain`, `request.inspect`, `support.bundle`, `run.tail`, and `run.budget` as live public product surfaces.
- Those surfaces could not bind to the fresh accepted correlation/event chain and returned fallback-like or unknown results.
- Direct product run-type dispatch no longer fails with `UNKNOWN_RUN_TYPE`, but it is denied by missing public binding scopes such as `run:read`, `request:read`, and `run:support`.
- `run.tail` explicitly used `status_poll`, which the launch gate says is not sufficient for full `run_tail=true`.
- `runs budget` returned hollow `no_pressure_data` without identity/request/correlation linkage.

Secondary SDK follow-up:

- Optional-surface commands currently return `success=true` for unknown/fallback-only output. For launch safety, the SDK should make this degradation unmistakable or fail closed when a surface cannot prove server-backed truth.

## Known Limitations

- Final proof commits were local and not yet on `origin/main`; the proof checkout was refreshed from the local repo while retaining the public GitHub remote for live repo facts.
- Forced interactive login was not rerun; active auth was proven with `whoami`, and login defaults were checked through CLI help and unit coverage.
- The broader `tests` command requires `jq` for a smoke prerequisite on this host; unit tests and the public release gate passed.
- Support bundle output was not accepted as complete envelope proof because it omitted required context, event, and proof references for the fresh identifier.

## Final Decision

Core governed repo proof is live and acceptable for technical preview:

- Fresh governed run reached `ACCEPT`.
- Receipt evidence includes Event Spine evidence, proof ID, receipt ID, governance context, and non-drifted verdict.
- Public release gate passes with live proof.
- Generated governance state remains untracked.

Complete governed repo product launch remains blocked until the server and SDK expose a durable run/request identity for the accepted governed chain and the advertised optional product surfaces bind to that same identity with non-unknown, server-backed results.
