# Public Cleanup Start

Date/time: 2026-06-12T18:17:55.3528671+04:00

## Baseline

- Workspace path: `C:\Users\natha\Keyhole-SDK\keyhole-sdk-public-cleanup`
- Branch: `public-release-cleanup`
- HEAD commit: `5cf075c62137e4abd8cbb35a2c0736d290f1f034`
- Tags on HEAD:
  - `sdk-governed-baseline-accepted`
  - `sdk-pre-public-release`

## Current Git Status

```text
## public-release-cleanup
```

## Current Test Command

The repository currently has package-level Python projects rather than a root Python package. The cleanup verification target is:

```powershell
pytest
```

Package install checks should use the package paths directly unless a root packaging entry point is added during cleanup:

```powershell
pip install -e .\packages\python\keyhole-sdk
pip install -e .\packages\python\keyhole-cli
```

## Expected Public Purpose

The public SDK repository should be a clean, forkable starting point for downstream developers. It should provide client SDK behavior, public CLI workflows, local governance contract validation, capability passport validation, governed request submission to a configured server, receipt handling, and safe fail-closed behavior when no governed server is configured.

The SDK must not act as the Keyhole server, embed private infrastructure assumptions, ship local run evidence as production proof, or require internal Keyhole history to understand.
