# CE-V5-S51-CUTOVER-C-04 - Governed Reproducible Build: Normalize COPY and RUN Layer Timestamps

**Status:** BLOCKED - governance chain incomplete at server-side scope grant  
**Story Stream:** CUTOVER-C (Track C - Governed Reproducible Build Identity Through SDK Fork)  
**Owner:** Keyhole Solution Foundation  
**Author:** Keyhole Solution Foundation  
**Track:** C - Governed Reproducible Build Identity  
**Depends On:** CE-V5-S51-CUTOVER-C-03 (ACCEPTED - SOURCE_DATE_EPOCH partial effectiveness proven)  
**Gap:** `gap_75e03597382924e2` - `keyhole-SDK.cutover.normalize-copy-run-timestamps.v1`  
**Constitutional Layer:** Build identity / COPY layer provenance / governed verification  
**Risk Level:** MEDIUM  
**Primary Surface:** `services/test-runtime/Dockerfile` + CI build workflow + MCP governance chain  
**Opened:** 2026-06-05  

---

## 1. Purpose - What Track C Is Actually Proving

Track C is **not** a standalone Docker reproducibility campaign.

Track C is proving that the **forkable SDK repo** can:

1. Declare an intent/invariant through the SDK
2. Bind that intent to a governed repo commit via MCP
3. Create a governance context for the repo state (`governance.context.create`)
4. Run verification through a governed path (ToolRunner / server-side verifier)
5. Emit evidence into the server-side Event Spine
6. Close gaps through a governed result - not a local assertion

**Docker reproducibility is the test subject. Keyhole governance is the thing being proven.**

A downstream/forkable repo (this SDK repo) should be able to use the Keyhole MCP server to govern change. C-04 proves whether the complete loop closes.

---

## 2. Why this story exists

CE-V5-S51-CUTOVER-C-03 confirmed that `SOURCE_DATE_EPOCH` stabilizes the image config and WORKDIR layer but does not stabilize COPY or RUN layers. The local-only fix is known (Change A: normalize source file mtimes; Change B: pass epoch into container). But that fix must be **verified through the governed path**, not just proven locally.

The test invariant for this story:

```text
INVARIANT: keyhole-SDK.cutover.normalize-copy-run-timestamps.v1

Given:
  - Dockerfile pins base image to sha256:a3ab0b96...
  - ARG SOURCE_DATE_EPOCH=0 / ENV SOURCE_DATE_EPOCH declared in Dockerfile
  - Source file mtimes normalized to SOURCE_DATE_EPOCH before docker build
  - docker build --build-arg SOURCE_DATE_EPOCH=$epoch

Then:
  Two consecutive --no-cache builds on the same commit produce identical image IDs.
  All 9 RootFS layers match.
```

---

## 3. Governance chain probe results (2026-06-05)

### Step 1 - Repo attach
```
Status: OK
repo_remote: https://github.com/Keyhole-Solution/keyhole-SDK.git
workspace_model: repo-as-workspace
persistent_workspace_created: false
commit_sha: 58c79c3259712abc32e2ae033c0cd82c2d0f7b19
```

### Step 2 - Gap state
```
gap_id: gap_75e03597382924e2
status: CLAIMED
governance_context: null  ? NOT BOUND
workspace: null
```

### Step 3 - governance.context.create
```
Result: BLOCKED
Error: EXECUTION_SCOPE_NOT_GRANTED
Missing: governance:context
Allowed: connection:read, context:compile, gaps:claim, gaps:evidence,
         gaps:read, gaps:submit, intent:submit, workspace:provision,
         workspace:close
```

### Step 4 - intent.submit
```
HTTP: 202 ACCEPTED
run_id: run_468650fb6ccf
Poll result: not_found (within 10s)
Conclusion: accepted but execution not persisted
```

### Step 5 - gaps.evidence.submit
```
HTTP: 202 ACCEPTED
Evidence reaches Event Spine. OK
```

### Chain verdict
```
GOVERNANCE_CHAIN_BLOCKED_AT_SCOPE_GRANT

The SDK correctly attempts the governed path.
The server blocks at governance:context scope.
intent.submit accepted but not persisted.
Evidence submission (gaps.evidence) is the only working server path.
```

---

## 4. What works vs what is blocked

| Step | Status | Notes |
|------|--------|-------|
| `keyhole repo attach` | OK WORKS | repo-as-workspace confirmed |
| `gaps.create` / `gaps.claim` | OK WORKS | gap lifecycle operational |
| `gaps.evidence.submit` | OK WORKS | evidence reaches Event Spine |
| `intent.submit` | ⚠? ACCEPTED/EPHEMERAL | accepted, not persisted |
| `governance.context.create` | NO BLOCKED | `governance:context` scope not granted |
| Governed verification run | NO BLOCKED | depends on governance context |
| Event Spine evidence from server-side verifier | NO BLOCKED | depends on verification run |
| Gap closure through governed result | NO BLOCKED | depends on all above |

---

## 5. Local verification artifact (PAUSED - not the proof)

The Docker implementation is known and correct:

**Change A** (fixes COPY layers 6, 8):
```bash
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
# Normalize in isolated temp context - do not permanently mutate working tree
cp -r services/test-runtime /tmp/build-context
git ls-files -z services/test-runtime | while IFS= read -rd '' f; do
  touch -d "@${SOURCE_DATE_EPOCH}" "/tmp/build-context/${f#services/test-runtime/}"
done
docker build ... /tmp/build-context
```

**Change B** (fixes RUN layers 7, 9):
```dockerfile
ARG SOURCE_DATE_EPOCH=0
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
```
```bash
docker build --build-arg SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} ...
```

**This implementation is PAUSED.** It will not be committed until the governance chain is unblocked and verification can run through the governed MCP path.

---

## 6. Server-side actions required to unblock

1. **Grant `governance:context` scope** to cohort `cohort-0` / binding `dbe742bf-0a49-443f-8eef-1073305039ae`  
   -> Unblocks `governance.context.create` -> gap gets `governance_context` populated

2. **Persist `intent.submit` run output** - run IDs should be queryable via `/mcp/v1/runs/{run_id}`  
   -> Enables SDK to confirm intent declaration was recorded

3. **ToolRunner / governed verification** for `reproducible_build` verification class  
   -> Runs the two-build comparison as a server-side governed operation

4. **Event Spine evidence from verifier output**  
   -> Server emits verification result into the spine

Once unblocked, the sequence is:
```
keyhole governance-context create --gap-id gap_75e03597382924e2
  -> governance_context_id bound to gap
  -> SDK submits intent via intent.submit
  -> server schedules verification run
  -> server emits result to Event Spine
  -> SDK polls gap for governed verdict
  -> gap closes through governed result only
```

---

## 7. Acceptance criterion

C-04 is accepted when ALL of the following are true:

- [ ] `governance.context.create` succeeds - `governance_context` field populated on gap
- [ ] `intent.submit` produces persisted run output (queryable)
- [ ] Dockerfile change (ARG/ENV) is implemented and committed
- [ ] Source file mtimes normalized via isolated temp context (no permanent working-tree mutation)
- [ ] Two consecutive `--no-cache` builds with same `SOURCE_DATE_EPOCH` produce identical image IDs
- [ ] All 9 RootFS layers match across both builds
- [ ] Verification evidence emitted to server-side Event Spine
- [ ] Gap closes through governed result
- [ ] No pip hash verification or dependency changes in this story


**Status:** OPEN  
**Story Stream:** CUTOVER-C (Track C - Reproducible Build Identity)  
**Owner:** Keyhole Solution Foundation  
**Author:** Keyhole Solution Foundation  
**Track:** C - Reproducible Build Identity  
**Depends On:** CE-V5-S51-CUTOVER-C-03 (ACCEPTED - SOURCE_DATE_EPOCH partially effective)  
**Gap:** `gap_75e03597382924e2` - `keyhole-SDK.cutover.normalize-copy-run-timestamps.v1`  
**Constitutional Layer:** Build identity / COPY layer provenance / RUN layer timestamps  
**Risk Level:** MEDIUM  
**Primary Surface:** `services/test-runtime/Dockerfile` + CI build workflow  
**Opened:** 2026-06-05  

---

## 1. Why this story exists

CE-V5-S51-CUTOVER-C-03 confirmed:

```
SOURCE_DATE_EPOCH=1780644503 (commit timestamp)
Layers 1-5 (base + WORKDIR): IDENTICAL across builds OK
Layers 6-9 (COPY and RUN):   DIFFERENT across builds NO

Root cause split into two distinct mechanisms:

  A. COPY layers (6, 8): BuildKit embeds SOURCE file mtimes in the
     layer tar. SOURCE_DATE_EPOCH is not applied to these - the host
     file's actual mtime is used as the tar entry timestamp.

  B. RUN layers (7, 9): pip and addgroup/adduser write files with
     wall-clock timestamps from within the container. SOURCE_DATE_EPOCH
     is only respected by tools that explicitly read it, and only if
     it is passed INTO the container at build time.
```

C-04 applies both fixes together. They are a single coherent change set:
normalizing timestamps at every layer that still drifts.

---

## 2. Changes

### Change A - Normalize source file mtimes (fixes COPY layers 6, 8)

In the CI build script / Makefile, before `docker build`:

```bash
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
git ls-files -z services/test-runtime | xargs -0 touch -d @${SOURCE_DATE_EPOCH}
```

This sets all tracked file modification times to the commit timestamp, making
COPY layer tars bit-identical across builds on the same commit.

**Constraints:**
- Must run on files inside the Docker build context only (`services/test-runtime/`)
- Must not alter files outside the build context
- Must not permanently mutate file mtimes in the working tree for non-build purposes

### Change B - Pass SOURCE_DATE_EPOCH into container (fixes RUN layers 7, 9)

Add to Dockerfile, immediately after the `FROM` line:

```dockerfile
ARG SOURCE_DATE_EPOCH=0
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}
```

Build command becomes:

```bash
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)
docker build \
  --no-cache \
  --build-arg SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
  -t keyhole-test-runtime:latest \
  services/test-runtime
```

This passes the epoch into pip (which respects it for `.dist-info` metadata since pip ≥ 21.3)
and into the system tools used by `addgroup`/`adduser`.

**Constraints:**
- `ARG` must appear before any `ENV` or `RUN` that uses it
- Default of `0` (Unix epoch) ensures the build is safe without the argument
- `ENV SOURCE_DATE_EPOCH` makes it available to all subsequent RUN commands

---

## 3. Acceptance criterion

C-04 is accepted when ALL of the following are true:

1. Dockerfile adds `ARG SOURCE_DATE_EPOCH=0` and `ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}`
2. Build workflow normalizes source file mtimes before docker build
3. `docker build --build-arg SOURCE_DATE_EPOCH=$epoch` is the canonical build command
4. Two consecutive `--no-cache` builds with the same `SOURCE_DATE_EPOCH` produce **identical image IDs**
5. All 9 layers match between builds
6. Matching digest is recorded as the new reproducible baseline
7. No requirements.txt changes, no pip hash verification in this story
8. Follow-up gap (C-05) opened only if pip content still varies after timestamps are fixed

### The verification sequence

```bash
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)

# Normalize source file mtimes
git ls-files -z services/test-runtime | xargs -0 touch -d @${SOURCE_DATE_EPOCH}

# Build 1
docker build --no-cache \
  --build-arg SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
  --quiet -t cutover-c04-build5:latest services/test-runtime

# Build 2 (from same normalized state)
docker build --no-cache \
  --build-arg SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
  --quiet -t cutover-c04-build6:latest services/test-runtime

# Compare
docker inspect --format '{{.Id}}' cutover-c04-build5:latest
docker inspect --format '{{.Id}}' cutover-c04-build6:latest
# Must be identical
```

---

## 4. Evidence trail

Evidence under `docs/evidence/cutover-c-04/` and mirrored to
`docs/context/epics/evolution/ce-v5/evidence/cutover-c-04/`.

Required:
- `dockerfile_diff.txt` - added ARG/ENV lines
- `build_result.json` - both build digests, full layer comparison
- `determinism_verdict.json` - DETERMINISTIC or NEXT_DELTA_IDENTIFIED
