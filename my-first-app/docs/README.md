# my-first-app

This repository was scaffolded by `keyhole init vertical`.

## Generated Declaration Files

| File | Purpose |
|------|---------|
| `keyhole.yaml` | Local repo identity, scaffold metadata, and registration anchor |
| `governance_contract.yaml` | Local governance rules, produced capabilities, required tests, and invariants |
| `capability_passport.yaml` | Portable capability identity plus generated or pending proof references |
| `dependencies.yaml` | Runtime, governance-boundary, and evidence-reference dependencies for the demo |

## Runtime Posture

This app has two explicit postures:

- **Local scaffold**: declaration files and local invariant tests exist, but no MCP registration, governed context, or upstream Event Spine evidence is implied.
- **Governed MCP-connected run**: the app is registered through the MCP boundary, context is compiled, and realization is submitted to the runtime with `require_governed=true`.

Local invariant proof is useful input to the governed flow. Canonical governance
evidence must come from MCP/Event Spine references returned by the live boundary.

`my-first-app` is not the public launch quickstart. For the blessed external
builder path, use `examples/second-governed-app` with `keyhole governed run`.

## Next Steps

1. `keyhole validate` - validate local declaration files.
2. Edit `governance_contract.yaml` - declare capabilities and invariants.
3. Edit `capability_passport.yaml` - declare generated and pending proof references.
4. For public launch validation, switch to `examples/second-governed-app`.
5. `keyhole validate examples/second-governed-app`
6. `keyhole doctor launch --repo-dir examples/second-governed-app --json`
7. `keyhole governed run --repo-dir examples/second-governed-app --json`

The older repo-registration/context-compile/run commands are lower-level
debugging surfaces for legacy first-app work. They are not the generic public
builder happy path.

## Governed Runtime Receipt

When the runtime is started with both `KEYHOLE_MCP_URL` and
`KEYHOLE_MCP_TOKEN`, `POST /realize` can require governed execution:

```json
{
  "candidate_digest": "sha256:<candidate>",
  "require_governed": true,
  "governance_context_id": "<from keyhole context compile>",
  "local_invariant_result": {
    "invariant_id": "MY-FIRST-APP-INV-01",
    "verdict": "ACCEPT"
  }
}
```

The response records `governed`, `event_spine_evidence`,
`governance_verdict`, `drift_state`, `governance_context_id`, and available
MCP evidence references. Without MCP configuration, the same governed request
fails closed; local-only realization remains available but reports
`governed=false` and `event_spine_evidence=false`.

The repository tests include a fake-boundary governed path that proves SDK,
CLI, runtime bridge, local invariant input, and receipt handling. That test is
not live MCP/Event Spine proof.

## Live Verification

With credentials present, the live verifier runs the same path and prints only
redacted receipt fields:

```bash
python scripts/verify_s51_c02_live_boundary.py
```

If `KEYHOLE_MCP_URL` or `KEYHOLE_MCP_TOKEN` is missing, the verifier reports
`live proof not performed`. A live proof is accepted only when the runtime
receipt includes `governed=true`, `event_spine_evidence=true`,
`governance_verdict`, `drift_state`, `governance_context_id`, and an
`mcp_event_id` or event pointer returned by MCP.
