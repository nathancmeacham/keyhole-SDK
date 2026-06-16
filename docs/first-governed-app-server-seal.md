# First Governed App Server Seal

This document records the restored baseline and server-governed seal for the
first governed app in this fork.

## Restored Baseline

- Repository: `nathancmeacham/keyhole-SDK`
- Branch: `first-governed-app`
- Accepted governed SDK baseline: `5cf075c`
- Restored first-app dependency baseline: `76c6696`
- Governed v2 capability commit: `66babaf`
- App boundary: `my-first-app`

## Capability

- Preserved capability: `my-first-app.greet.user.v1`
- Added capability: `my-first-app.greet.user.v2`
- Local verification tag:
  `first-governed-capability-v2-restored-baseline-local-verified`
- Server-governed tag:
  `first-governed-capability-v2-server-governed`

## Server-Governed Receipt

The `my-first-app.greet.user.v2` capability received a governed server receipt
from the configured Keyhole MCP/event-spine flow.

- `receipt_id`: `grcpt_6afd8811a81663a0f36634de`
- `proof_id`: `gproof_c0c163e389c2efa5f6a944c9`
- `mcp_event_id`: `run.complete:200fd5cf-ba49-4767-9d4d-f537f6a75494`
- `governance_context_id`: `gctx_9a7b19aecc4a735b24ca5f53b60ef1a3`
- `governed`: `true`
- `event_spine_evidence`: `true`
- `governance_verdict`: `ACCEPT`
- `drift_state`: `non_drifted`

Receipt evidence was captured outside the repository at:

```text
/home/deploy/keyhole-startpoint-evidence/greet-v2-server-governed-receipt.json
```

## Local State Rule

Generated `.keyhole` state is local-only runtime evidence. It may be useful for
local inspection with commands such as `keyhole governed status` and
`keyhole governed receipt`, but it must not be committed to the repository.

Do not commit generated files under:

```text
my-first-app/.keyhole/
```

The repository seal is represented by committed source/declaration files plus
the pushed Git tags above. Server receipt artifacts remain external evidence
unless an explicit evidence-publication workflow is defined.
