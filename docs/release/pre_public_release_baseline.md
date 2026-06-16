# Pre-Public Release Baseline

Date of preservation: 2026-06-12

This document records the accepted SDK state before public-release audit and cleanup work. No cleanup, deletion, refactoring, or repository audit is authorized by this preservation record.

## Repository Identity

- Current branch: `main`
- Current commit SHA: `5cf075c62137e4abd8cbb35a2c0736d290f1f034`
- Current commit subject: `about to copy`
- Remote: `origin https://github.com/Keyhole-Solution/keyhole-SDK.git`
- Working tree at preservation capture: clean

An earlier first capture during this preservation session observed `b0631bd25bb77c46df0f68dcbdd2766a089a7f19` with local uncommitted artifacts. Before tags were created, the repository advanced to `5cf075c62137e4abd8cbb35a2c0736d290f1f034` and became clean. The immutable recovery tags for this preservation phase are intended to mark `5cf075c62137e4abd8cbb35a2c0736d290f1f034`.

## Version

- `keyhole-sdk`: `0.4.1`
- `keyhole-cli`: `0.3.1`
- CLI entry point: `keyhole = "keyhole_cli.cli:app"`

## Current CLI Commands

Top-level command surface captured from `python -m keyhole_cli.cli --help`:

- `version`
- `register`
- `verify`
- `registration-status`
- `deregister`
- `login`
- `whoami`
- `logout`
- `run`
- `ingest`
- `align`
- `doctor`
- `smoke`
- `inspect`
- `support-bundle`
- `search`
- `validate`
- `surfaces`
- `connections`
- `mcp-proxy`
- `runtime`
- `init`
- `context`
- `runs`
- `repo`
- `dependency`
- `explain`
- `capability`
- `passport`
- `connection`
- `host`
- `auth`
- `gaps`
- `workspace`
- `governance-context`
- `proof`
- `receipt`
- `governed`
- `memory`

## Current Test Counts

- Test files under `tests/`: `59`
- Test/class declarations under `tests/`: `4295`
- Test/class declarations across repository `test_*.py` files: `4301`

Counts were captured with ripgrep patterns for `def test_` and `class Test`.

## Current Example Applications

- `examples/bridge-smoke-test`
- `examples/python-client`
- `examples/second-governed-app`
- `my-first-app`

## Capture Commands

The preservation phase recorded:

```bash
git status
git branch --show-current
git rev-parse HEAD
git log --oneline -n 20
```

The current accepted baseline identity for recovery purposes is:

```text
5cf075c62137e4abd8cbb35a2c0736d290f1f034
```
