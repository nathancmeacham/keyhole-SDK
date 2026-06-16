# First Governed App Start Point

This document records the sealed local verified start point for the first
governed app in this fork.

## Repository State

- Repository: `nathancmeacham/keyhole-SDK`
- Branch: `first-governed-app`
- Tag: `first-governed-app-local-verified`
- Commit: `37aee6a1ed79ce3c0bdd711863b87e6e6c80de56`
- App boundary: `my-first-app`
- Current capability: `my-first-app.greet.user.v1`

## Local Verification

The start point is locally verified as an SDK/app boundary:

- `keyhole validate my-first-app` passed.
- `pytest` passed with 11 tests.
- `keyhole governed run --repo-dir my-first-app --no-live --json` passed.
- Governed dry-run reported `would_mutate_mcp=false`.

## Governance Status

This is a local verified SDK/app start point. It is not yet a
server-governed event-spine receipt.

`server_governed=false` remains true until MCP registration, governance context
compile, governed run, governed status, and governed receipt are completed
against a configured Keyhole server.

Until those live governed steps complete, the capability passport trust state
and governed receipt fields remain pending local declarations rather than
server-confirmed authority.
