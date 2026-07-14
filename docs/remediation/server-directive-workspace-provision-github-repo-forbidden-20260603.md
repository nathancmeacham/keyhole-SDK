# Server Directive - workspace.provision GITHUB_REPO_FORBIDDEN (2026-06-03)

**Priority:** HIGH - blocks end-to-end workspace provisioning for local test repos  
**Status:** RESOLVED - 2026-06-04 (production `sha256:b93c0ee3`, v300)  
**Realm:** `kh-prod`  
**Platform:** `https://mcp.keyholesolution.com`  
**Raised by:** SDK client investigation - session `982489b3-e0d2-470e-858f-0cac6e22c04f`  
**Raised:** 2026-06-03  
**Run:** `run_ca6f444ea819` (workspace.provision shape B)

---

## Problem Statement

`workspace.provision` now correctly receives and processes its inputs (the
`input_value={}` bug from `server-directive-workspace-provision-input-loss-20260528.md`
is RESOLVED). However, the provision handler fails with `GITHUB_REPO_FORBIDDEN`
when attempting to access the test repository.

**Exact error:**
```json
{
  "code": "GITHUB_REPO_FORBIDDEN",
  "message": "Repository or branch not found: Keyhole-Solution/my-first-app:main"
}
```

---

## Root Cause

The gap for `my-first-app.greet.user.v1` was submitted with `repo: my-first-app`.
The `workspace.provision` handler constructs the GitHub URL as
`Keyhole-Solution/my-first-app:main` using the `repo` name from the gap.

`my-first-app` is a local test directory within the `keyhole-SDK` workspace - it
is **not** a GitHub repository. The local directory's git remote is
`https://github.com/Keyhole-Solution/keyhole-SDK.git` (the parent repo).

Additionally, the claim `ticket_packet.repo_remote` shows
`https://github.com/Keyhole-Solution/keyhole_platform`, which is also not the
correct URL for this test. It is unclear where this value originated.

---

## Observed Chain State

```
gaps.claim     -> CLAIMED (claim_token: 561d66c176029c4537145c9d0ac8307c)  OK
workspace.provision (shape A, no repo) -> INVALID_PARAMETERS: repo required  OK (input received)
workspace.provision (shape B, repo=my-first-app) -> GITHUB_REPO_FORBIDDEN   NO
keyhole whoami  -> workspace_id: <neutral>  (not yet tested, provision failed)
```

---

## Questions for Platform Team

1. How does `workspace.provision` resolve the GitHub URL? Does it use:
   - `ticket_packet.repo_remote` from the claim result?
   - Constructed from `{github_org}/{repo_name}` using the gap's `repo` field?
   - Some other mapping?

2. Where does `ticket_packet.repo_remote = https://github.com/Keyhole-Solution/keyhole_platform`
   come from? This is not the local git remote (`keyhole-SDK`), and not `my-first-app`.

3. Is there a way to configure or override the GitHub repo URL at provision time?

---

## Current Protocol-Level Status

The `workspace.provision` protocol chain is working correctly:
- OK Input received and validated (not `input_value={}`)
- OK Handler executes and attempts GitHub access
- OK Two-plane execution and result polling working

The only remaining issue is the test repository not existing at the constructed URL.

---

## Required Actions

**Option A - Platform fix:** Use `ticket_packet.repo_remote` as the authoritative
GitHub URL for provisioning rather than constructing from `repo` name.

**Option B - Test setup:** Create a GitHub repo at `Keyhole-Solution/my-first-app`
accessible to the platform service account, or point the `my-first-app` gap submission
to a real accessible repo (`keyhole-SDK`).

---

## Status Updates

| Date | Update |
|------|--------|
| 2026-06-03 | Filed - workspace.provision input_loss resolved; GITHUB_REPO_FORBIDDEN is new blocker |
| 2026-06-04 | **RESOLVED** - PR #353 promoted `sha256:b93c0ee3` (v300) to production. `workspace.provision` now reads `ticket_packet.repo_remote` from the stored claim server-side. Client sends only `gap_id + claim_token`; server resolves the GitHub repo binding automatically. Verified: gap `gap_9a5034cacc3bd052` provisioned to `workspace_id=ws/gap/gap_9a50/ebcbc742-0155-4982-b329-bdeda6253ef4` on `Keyhole-Solution/keyhole_platform` branch `gap/gap_9a50/ebcbc742-0155-4982-b329-bdeda6253ef4` in 1 second. Full chain: `gaps.claim -> workspace.provision (shape A) -> completed` OK |
