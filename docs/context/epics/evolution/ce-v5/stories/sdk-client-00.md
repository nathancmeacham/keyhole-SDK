# sdk-client-00.md

# SDK-CLIENT-00 - Identity Creation & Verification (Client)

**Story ID:** SDK-CLIENT-00 / sdk-client-00  
**Epic:** SDK-CLIENT - Governed Developer SDK, Onboarding, and Repository Ingestion  
**Status:** COMPLETE  
**Owner / Author:** Keyhole Solution Foundation  
**Lane:** Dev (implementation + validation), Prod (promotion only)  
**System:** Keyhole CLI / SDK / Builder Onboarding Surface  
**Story Type:** Client-side zipper story  
**Paired Server Story:** `sdk-server-00.md`  
**Precedes:** `sdk-client-01.md`

---

## 1. Story Purpose

Implement the **client-side identity creation and verification flow** that allows a brand new builder to enter the Keyhole ecosystem through a governed onboarding experience before authentication bootstrap begins.

This story must provide the client functionality required to deliver:

- `keyhole register`
- guided verification flow
- verification status polling or inspection
- clear pending/verified/failed onboarding UX
- explicit dev/test onboarding into `kh-dev`
- explicit test `origin` and `purpose` stamping for smoke and validation
- replayable onboarding proof bundle closure

This story closes the **client half of the pre-auth zipper** for builder onboarding.

---

## 2. Why This Story Exists

The SDK currently assumes a builder identity already exists and can authenticate.

That is not enough to prove true onboarding.

A governed builder boundary must prove that a brand new human can:

1. register,
2. verify,
3. become an active identity,
4. and only then proceed to authentication bootstrap.

Without this story:

- smoke tests depend on shortcuts,
- pre-seeded tokens become normalized,
- the "10-minute first value" promise is incomplete,
- onboarding is implied rather than demonstrated.

This story makes onboarding visible, guided, attributable, and testable from the builder side.

---

## 3. Story Outcome

When this story is complete, the client must be able to:

1. initiate a new builder registration against the governed boundary,
2. collect and submit required onboarding fields,
3. explicitly declare dev/test origin and purpose when creating `kh-dev` test identities,
4. present verification next steps clearly,
5. support verification completion or verification-safe polling,
6. show registration/verification/activation status deterministically,
7. guide the user through success and failure paths with repair suggestions,
8. generate a replayable onboarding proof bundle,
9. hand off a verified active identity cleanly to `SDK-CLIENT-01`.

---

## 4. Scope

### In scope

- `keyhole register`
- registration request shaping and submission
- verification UX
- verification completion UX
- verification status inspection/polling
- explicit `kh-dev` test onboarding support
- explicit `origin` and `purpose` stamping for test/dev onboarding
- Mailhog-compatible dev verification UX
- onboarding proof bundle generation
- deterministic error handling and repair guidance
- clean handoff to login after successful onboarding

### Out of scope

- server-side identity creation logic
- Keycloak realm configuration
- local credential/session persistence for login
- PKCE/device login flows
- marketplace/billing onboarding
- machine-user onboarding in `keyhole-mcp`
- advanced admin IAM workflows

---

## 5. Constitutional Requirements

This story must preserve the following platform truths:

- the SDK is not the control plane,
- the MCP boundary is the only approved public participation surface,
- no floating execution is allowed,
- no identity is treated as active until the server says so,
- Event Spine is canonical truth,
- a zipper is not closed until it produces a replayable proof bundle,
- test/dev users must be explicitly identifiable and filterable,
- failure must produce repair guidance rather than dead ends.

---

## 6. Client Responsibilities

The client-side implementation must provide the following capabilities.

### 6.1 Registration command

The client must expose a clear onboarding entry command.

Minimum command:

```text
keyhole register

This command must:

collect or accept required registration inputs,

submit them to the governed server boundary,

show next-step guidance clearly,

return structured output for scripts and smoke tests.

6.2 Verification completion UX

The client must support the completion of verification through an approved mechanism.

This may include:

entering a verification code,

following a verification URL and polling for result,

using a dev/test verification mode compatible with Mailhog or equivalent.

6.3 Verification status inspection

The client must provide a clear status surface that tells the builder whether they are:

pending verification,

verified,

activation-ready,

active,

failed,

blocked or rate-limited.

6.4 Dev/test onboarding support

The client must support explicit creation of test/dev users in kh-dev with explicit classification fields.

For smoke and validation flows, the client must not silently create ambiguous users.

6.5 Proof bundle generation

The client must generate the client-side half of a replayable onboarding proof bundle, capturing:

request metadata,

response metadata,

verification state,

correlation,

identity metadata returned by the server,

summary-ready artifacts,

deterministic digest anchors.

7. Realm-Aware Onboarding UX

This story must respect the locked realm model:

kh-prod - human production users

keyhole-mcp - machine users

kh-dev - test and dev users

7.1 Dev/test onboarding default for validation

For smoke, integration, and test onboarding under this story, the client must support explicit onboarding into kh-dev.

7.2 No machine-user confusion

The client must not present this story's flow as a machine-user enrollment path.

7.3 Explicit test identity stamping

For dev/test onboarding, the client must require or clearly expose explicit fields for:

origin

purpose

Example values include:

origin=test

origin=smoke

origin=integration

purpose=sdk_onboarding

purpose=sdk_smoke

purpose=verification_test

7.4 Filtering support

The client must make it easy to understand that these values are not cosmetic; they exist so identities can be filtered and audited deterministically.

8. Command / UX Surface Requirements

This story does not force final syntax beyond platform conventions, but the client implementation must expose the following logical surfaces.

8.1 keyhole register

Purpose:

create a new builder identity through the governed boundary,

collect registration data,

trigger verification initiation.

Expected UX responsibilities:

prompt for required fields where not provided,

support fully non-interactive flags for automation,

support JSON output,

print clear next-step instructions,

show the target realm and classification fields.

8.2 keyhole verify

Purpose:

complete verification using a code, token, or equivalent safe artifact.

Expected UX responsibilities:

accept verification artifact directly or via flags,

support non-interactive use for smoke tests,

return deterministic structured output,

never claim activation before server confirmation.

8.3 keyhole registration-status

Purpose:

inspect current onboarding state.

Expected UX responsibilities:

return pending/verified/active/failed state,

show realm, origin, purpose,

show next-best action,

support polling in test/dev workflows.

8.4 Optional keyhole resend-verification

If implemented, this must be rate-limit aware and provide safe operator guidance.

9. Registration Flow Requirements
9.1 Minimum input fields

The client must support submission of the minimum logical registration fields needed by the server, including:

username or equivalent builder-facing identifier

email

display name or equivalent

requested tenant/org context where applicable

origin

purpose

9.2 Dev/test requirement

For kh-dev smoke or test onboarding, the client must require or strongly enforce explicit origin and purpose.

The client must not allow a dev/test onboarding path that leaves these fields blank or ambiguous.

9.3 Non-interactive support

The client must support fully non-interactive registration invocation for automation and smoke tests.

Example shape:

keyhole register \
  --email test-user@example.com \
  --username test-user \
  --display-name "Test User" \
  --realm kh-dev \
  --origin smoke \
  --purpose sdk_onboarding \
  --json
9.4 Guided output

On successful registration, the client must clearly show:

registration accepted,

realm assigned,

verification pending,

next step to complete verification.

10. Verification Flow Requirements
10.1 Verification is mandatory

The client must not treat registration as equivalent to activation.

10.2 Verification completion support

The client must support an approved verification completion path, such as:

keyhole verify --code ...

keyhole verify --token ...

a polling-based completion after browser/mail action

Mailhog-compatible dev verification flow

10.3 Test-safe verification UX

For dev/test onboarding, the client must support a verification path suitable for controlled testing environments.

This must allow smoke tests to complete verification without production email infrastructure.

10.4 No false success

The client must not report that the identity is active until the server confirms verified/active status.

11. Status and Handoff Requirements
11.1 Registration status surface

The client must let a builder inspect current onboarding state clearly.

At minimum, it must expose:

registration state

verification state

activation state

realm

origin

purpose

next-best action

11.2 Handoff to SDK-CLIENT-01

Once the onboarding flow has completed and the identity is active, the client must give a clear next step:

next: keyhole login
11.3 No implicit login

This story does not itself authenticate the user. It prepares a valid identity for authentication.

12. Data Handling and Local State
12.1 No auth credential persistence

This story must not persist login credentials or sessions. That belongs to SDK-CLIENT-01.

12.2 Allowed local state

The client may persist minimal non-secret onboarding state where necessary for UX continuity, such as:

registration correlation id

pending verification state

non-secret registration metadata

proof artifacts

12.3 Secret safety

Verification artifacts, raw tokens, or equivalent secret-bearing material must not be leaked into proof bundles, logs, or user-facing summaries.

13. Origin and Purpose UX
13.1 Why this matters

This story is the first true builder entry point. Test onboarding must remain clearly marked, filterable, and auditable.

13.2 Required client behavior

For dev/test onboarding in kh-dev, the client must make the following explicit:

target realm

origin

purpose

13.3 Good UX principle

The CLI should make it easy to do the right thing and hard to create ambiguous test identities.

13.4 Examples
keyhole register \
  --realm kh-dev \
  --origin smoke \
  --purpose sdk_onboarding
keyhole register \
  --realm kh-dev \
  --origin integration \
  --purpose verification_test
14. Failure and Repair UX

A governed onboarding flow that only says "no" will fail adoption.

14.1 Every reject/failure path must include

reject class

deterministic reason

affected field or lifecycle step where applicable

next-best repair suggestions

14.2 Example
{
  "success": false,
  "error_class": "verification_expired",
  "reason": "Verification token expired before completion.",
  "repair_suggestions": [
    "Run keyhole resend-verification",
    "Complete verification promptly after receiving the new code"
  ]
}
14.3 Principle

Failure must produce repair guidance, not a dead end.

15. Event and Proof Expectations
15.1 Event expectation

The client must assume the server is the source of event truth.

The client may reference onboarding lifecycle events in proof, but must not invent or infer them.

Minimum expected lifecycle events on the happy path:

IDENTITY_CREATED

IDENTITY_VERIFIED

15.2 Proof bundle expectation

The client must generate the client-side half of a replayable onboarding proof bundle.

The proof must make it clear that:

onboarding was initiated,

verification was required,

verification completed,

the resulting identity is activation-ready or active,

the identity is classified correctly for dev/test flows,

the next step is keyhole login.

16. Proof Bundle Requirements
16.1 Minimum proof bundle shape
proof_bundle/
  --- core.json
  --- request.json
  --- response.json
  --- event_chain.json
  --- registration_context.json
  --- verification_result.json
  --- identity_context.json
  --- correlation.json
  --- summary.md
  --- diff.json
  --- digest.txt
  --- extended/
16.2 Story-specific requirements

For client-side onboarding, the proof bundle must show:

registration request intent

realm target

origin and purpose

verification pending state

verification completion result

activation-ready or active status

server-sourced identity context where available

next-step handoff to login

16.3 Replay sufficiency

The hot proof core must be sufficient to verify that:

the client initiated a new identity creation flow,

the correct realm and classification were requested,

verification completed,

the identity became eligible for SDK-CLIENT-01,

the onboarding zipper closed.

17. Dependencies

This story depends on, or assumes availability of:

sdk-server-00.md

governed registration endpoint(s)

governed verification endpoint(s)

status inspection endpoint(s)

Mailhog-compatible or equivalent dev verification transport

proof bundle support utilities in SDK/CLI

18. Acceptance Criteria

This story is complete only when all of the following are true:

keyhole register can initiate a valid identity creation flow,

the client can submit the required onboarding fields,

dev/test onboarding can explicitly target kh-dev,

origin and purpose are explicitly provided for kh-dev test users,

the client clearly reports pending verification state,

the client can complete verification through an approved mechanism,

the client can inspect or poll onboarding status deterministically,

the client does not claim activation before the server confirms it,

the client generates a replayable onboarding proof bundle,

proof artifacts preserve realm, origin, and purpose classification,

failure paths return deterministic reasons and repair guidance,

successful onboarding gives a clear next step into SDK-CLIENT-01,

no auth credentials are persisted by this story,

no secret-bearing verification material leaks into proof artifacts.

19. Test Plan
19.1 Positive tests
Test A - Dev/test registration succeeds

run keyhole register with explicit kh-dev, origin, and purpose

verify client reports registration accepted

verify verification is pending

verify proof bundle captures classification fields

Test B - Verification completes successfully

run keyhole verify with valid artifact

verify client reports verified/active state

verify proof bundle captures verification completion

Test C - Registration status works

run keyhole registration-status

verify current lifecycle state is shown correctly

verify realm, origin, and purpose are visible

Test D - Mailhog-compatible verification works

perform test/dev verification through approved dev mechanism

verify no production-mail dependency is required

Test E - Handoff to login is clear

complete onboarding

verify client outputs next step: keyhole login

19.2 Negative tests
Test F - Missing origin/purpose rejected for kh-dev

attempt dev/test registration without explicit classification

verify deterministic failure and repair guidance

Test G - Invalid verification artifact rejected

run keyhole verify with malformed or mismatched artifact

verify deterministic failure

verify no false active state

Test H - Expired verification rejected

simulate or trigger expiry

verify deterministic failure and repair guidance

Test I - Duplicate registration rejected cleanly

submit duplicate registration

verify deterministic failure messaging

verify no false success

Test J - No secret leakage in proof

inspect generated proof bundle

verify no raw verification secret material is leaked

19.3 Proof tests
Test K - Onboarding proof replay sufficiency

generate proof bundle from successful registration + verification

verify hot proof core is sufficient to reconstruct onboarding closure

Test L - Classification proof correctness

verify realm, origin, and purpose are present and accurate in proof artifacts

20. Expected Proof Artifacts

At minimum this story must produce proof material sufficient to confirm:

registration initiated,

correct realm requested,

explicit dev/test classification provided where required,

verification completed,

activation-ready or active state reached,

onboarding proof bundle closed,

next step is login.

Expected key artifacts:

registration request/response

verification request/response

registration_context.json

identity_context.json

verification_result.json

summary.md

21. Completion Proof

This story is zipper-closed only when the paired server story and this client story together prove:

keyhole register
-> pending identity created
-> verification initiated
-> verification completed
-> identity activated
-> IDENTITY_CREATED emitted
-> IDENTITY_VERIFIED emitted
-> proof bundle generated
-> next: keyhole login

No half-feature is acceptable.

22. Final Story Summary

SDK-CLIENT-00 client-side identity creation and verification is the first builder-facing onboarding surface in Keyhole.

If it is weak:

smoke tests require shortcuts,

real onboarding is not proven,

the first external boundary remains assumed rather than demonstrated.

If it is strong:

a brand new builder can enter through governed onboarding,

kh-dev test users remain explicit and filterable,

verification is visible and deterministic,

authentication begins from a lawful identity foundation,

SDK-CLIENT-01 becomes provable from real onboarding rather than seeded state.