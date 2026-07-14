sdk-client-01 Client Hardening for Server-Aligned Identity Governance
Assignment

Harden the existing sdk-client-01 implementation so the client strictly conforms to the newly clarified server-side identity and authentication contract for SDK-CLIENT-01 - Authentication Bootstrap.

This is not a rebuild and not a new story. The client implementation already works functionally. The task is to tighten behavior so the client acts as a governed observer of server-issued truth rather than a partially interpretive participant.

The server side has now clarified and sealed several critical invariants around identity issuance, /whoami, attribution, mode visibility, event emission, and zipper closure. The client must now align exactly with those rules.

The target outcome is that the client side remains easy to use, but becomes stricter in these areas:

identity comes only from the server boundary,

/whoami is treated as required identity acquisition, not optional post-login validation,

tokens are opaque transport credentials only,

mode is server-determined and client-read-only,

correlation is stable across the full auth lifecycle,

proof bundles reflect server truth exactly,

successful login is not accepted unless the server identity surface and auth event chain confirm closure.

Why This Work Exists

The client half of sdk-client-01 is already strong. It has:

PKCE and device flow support,

secure credential storage,

keyhole login,

keyhole whoami,

proof bundle generation,

shadow vs real visibility,

deterministic repair guidance.

However, the server side has now hardened the story into a stricter governed identity model. The main architectural consequence is this:

The client must no longer behave as though identity can be inferred, partially trusted, or locally reconstructed.

The server is now the sole issuer and resolver of governed identity. That means the client must shift from:

"I completed auth and then checked identity"

to:

"I only accept auth as complete when the governed server has issued identity and exposed it through /whoami."

This hardening work ensures the first SDK zipper is not merely convenient, but constitutionally correct.

Current State Summary

The existing client implementation already includes:

typed models for auth session and whoami response,

orchestration of login flows,

secure persistence in ~/.keyhole/credentials.json,

proof bundle writing,

CLI commands for login and whoami,

error handling and repair suggestions.

The existing client report indicates the feature is functionally complete. That remains true.

The hardening task should therefore be treated as:

a behavior tightening pass,

a proof alignment pass,

a contract compliance pass.

Do not redesign the user journey. Do not add unrelated features. Do not create a parallel architecture.

Core Principle for This Handoff

The single most important rule is:

The client must treat server-issued identity as the only identity truth.

That principle should shape every change in this handoff.

Required Architectural Shift

The client currently orchestrates login and then verifies identity. After hardening, the client must instead follow this mental model:

auth flow initiated
-> auth completion artifact exchanged
-> provisional token/session received
-> client calls /whoami
-> server returns governed identity context
-> client accepts session only if governed identity is returned successfully
-> client records proof using server-issued truth

This means:

the token/session is not enough by itself,

/whoami is mandatory to complete login,

identity acquisition happens through /whoami,

local inference is forbidden,

proof closure depends on server confirmation.

Scope of Work
In scope

hardening AuthBootstrapClient.login() and related orchestration

tightening identity handling rules

tightening correlation handling

tightening mode handling

tightening proof bundle generation semantics

tightening session persistence rules

tightening failure semantics after login but before valid whoami confirmation

updating client tests

updating client story documentation if needed

updating proof expectations where required

Out of scope

redesigning PKCE or device flow mechanics

replacing the credential store architecture

inventing new auth flows

adding unrelated CLI commands

implementing server-side behavior

introducing client-side token claim parsing for convenience

relaxing existing security properties

Hard Requirements
1. Identity Must Come Only From /whoami

The client must not construct, infer, or trust identity from any other source.

This means:

no fallback to token claims for canonical identity,

no local reconstruction of tenant_id, org_id, user_id, cohort_id, worker_id, workspace_id, or mode,

no "best effort" identity object when /whoami is missing or incomplete,

no partial acceptance of login.

The governed identity used by the client for display, session confirmation, and proof must come from the server /whoami response.

Required implementation consequence

The login flow should treat /whoami as part of the successful login path, not a separate optional validation step.

2. Tokens Must Be Treated as Opaque

The client must treat the access token, refresh token, and ID token as transport credentials only.

The client may:

store them securely,

send them in auth headers,

use expiry metadata for session freshness decisions.

The client must not:

decode token contents to recover identity,

derive mode from token contents,

recover org or tenant binding from claims,

use token internals as fallback truth if /whoami fails.

If the current code decodes or inspects JWT payloads for identity or mode, remove that behavior.

3. /whoami Is Mandatory for Login Completion

A login flow is not considered successful merely because a token exchange succeeded.

A login flow is successful only when:

a usable token/session is received, and

/whoami returns a valid governed identity context.

If /whoami fails after token exchange, the login must be treated as failed.

Required behavior

do not persist the session as valid if /whoami fails,

do not print a final success message if /whoami fails,

do not emit a local proof bundle marked complete if /whoami fails,

return a deterministic error and repair guidance.

4. Correlation ID Must Span the Full Lifecycle

A single correlation ID must be used across the entire auth lifecycle:

auth start,

auth complete,

/whoami,

proof bundle,

event chain references.

The client must not generate a fresh correlation ID midway through the flow.

If the current code creates separate lifecycle IDs for substeps, normalize that behavior so there is one primary correlation anchor per login attempt.

Required proof consequence

The proof bundle must make it easy to show that all lifecycle steps belong to the same auth zipper closure.

5. Mode Is Server-Determined and Read-Only on the Client

The client may express user intent related to mode, such as requesting shadow behavior if that is part of the public workflow, but it must not decide final mode.

The final mode shown to the user and written into proof must come from the server identity response.

This means:

the CLI must display the mode returned by /whoami,

the proof bundle must reflect the mode returned by /whoami,

any client-side request flag is merely an input, not final truth.

Do not allow local logic to override or reinterpret the final mode.

6. Proof Bundle Must Reflect Server Truth Exactly

The proof bundle is already good, but it now needs stricter semantics.

The canonical identity_context.json should reflect the server-issued identity response exactly, or a direct normalized projection of it if the bundle format requires specific shape constraints. It must not include locally inferred augmentations that could drift from server truth.

Likewise, the event chain data used in proof should align to server-emitted auth events, especially AUTH_SUCCESS on the happy path.

Required proof semantics

A successful proof bundle must show:

auth flow initiated,

auth flow completed,

usable session/token received,

/whoami returned governed identity,

visible mode preserved from server,

server-side auth success event linked by correlation,

final verification marked successful.

7. Zipper Closure Requires Server Event Confirmation

The client currently knows that the flow succeeded from its own perspective. That is no longer sufficient by itself.

A fully closed successful auth proof should require confirmation that the server emitted the expected auth success event, or that the response data contains an authoritative event reference chain sufficient to prove server acceptance.

The client should not pretend the zipper is fully closed merely because the client received tokens.

This does not necessarily require waiting on a separate event query call if the server already provides authoritative references during the flow. But the client-side proof semantics must recognize that event-spine truth matters.

8. Failure After Token Exchange Must Be Treated as Real Failure

The hardest edge case here is:

token exchange succeeds
but /whoami fails

That is not a partial success. It is a failed authentication bootstrap.

Required behavior:

reject the login attempt,

avoid persisting the session as complete,

produce deterministic repair guidance,

avoid misleading the user.

The same principle applies if the server-issued identity is incomplete or invalid.

Implementation Tasks
Task 1 - Review AuthBootstrapClient.login() Flow

Inspect the orchestration sequence in client.py.

Confirm whether the current flow does any of the following:

treats token receipt as full success before /whoami,

persists credentials before /whoami,

allows identity fallback if /whoami fails,

constructs proof before server identity is confirmed.

Refactor the flow so success ordering is:

initiate auth,

complete auth,

receive provisional session/token,

call /whoami,

validate returned identity shape,

persist session,

finalize proof,

return success.

The client should not invert or loosen this order.

Task 2 - Audit Token Usage

Inspect all auth/bootstrap modules for any usage of token internals beyond transport/storage/expiry handling.

Specifically inspect for:

JWT decoding,

claim extraction,

mode derivation from claims,

user/org/tenant reconstruction from token payloads.

If present, remove or quarantine that behavior so the client is not using tokens as identity truth.

Task 3 - Strengthen Identity Validation

Ensure the client validates that the /whoami response includes all required fields expected by the current story contract.

At minimum, the client should fail deterministically if critical required fields are absent, malformed, or empty.

The exact required fields should reflect your current client/server contract, but must include the server-governed identity basics and mode visibility.

This validation should happen before session persistence and before proof finalization.

Task 4 - Make Correlation Stable

Audit how correlation IDs are generated and stored across:

request metadata,

event chain recording,

proof files,

whoami calls.

Ensure one lifecycle correlation ID is carried from initiation through proof closure.

If the code currently creates sub-correlation IDs, keep them only if useful as secondary detail, but ensure one primary correlation ID anchors the entire flow.

Task 5 - Tighten Proof Bundle Semantics

Review proof.py and any bundle-writing helpers.

Update proof rules so that:

identity_context.json is derived from /whoami,

verification_result.json marks success only when /whoami succeeded and required identity fields were validated,

event_chain.json reflects the authoritative auth lifecycle and, where available, server auth event confirmation,

summary.md describes closure in terms of governed identity confirmation, not just token receipt,

any mode field shown in proof is sourced from server response,

no token secrets appear anywhere in proof.

Be conservative. The proof bundle should be a trustworthy replay surface, not a convenience summary.

Task 6 - Tighten Credential Persistence Rules

Review credential_store.py usage and the orchestration around save/load.

Ensure that saving only happens after:

token/session acquisition, and

valid governed identity acquisition via /whoami.

A provisional session object may exist in memory during flow execution, but persistent storage should only happen after governed identity success.

Task 7 - Tighten CLI Success/Failure Messaging

Review keyhole login command behavior.

Ensure the CLI does not report success until:

the server-issued identity is returned by /whoami,

the session is persisted successfully,

the proof lifecycle is complete enough to represent governed closure.

If /whoami fails, the CLI must communicate failure clearly and provide repair guidance.

Task 8 - Update Error Semantics Where Needed

You already have a strong error hierarchy.

Extend or adjust it only where necessary so the following distinctions are crisp:

token acquisition failure,

whoami verification failure,

incomplete server identity,

proof finalization failure after valid identity,

credential persistence failure after valid identity.

Do not bloat the hierarchy. Preserve determinism and actionable repair guidance.

Task 9 - Update Tests

Add or update tests to verify the hardened contract.

At minimum, ensure the following are covered.

Positive behavior

login success requires successful /whoami

identity context used by client matches /whoami

correlation remains stable through full lifecycle

proof bundle uses server-issued identity and mode

session persistence happens only after whoami success

Negative behavior

token exchange succeeds but /whoami fails -> login fails

token exchange succeeds but returned identity is incomplete -> login fails

session is not persisted when /whoami fails

proof is not marked complete when server confirmation is missing

client does not decode token for identity fallback

Security behavior

proof still excludes secrets

token remains opaque

mode shown to user is exactly what server returned

Desired Acceptance Outcomes

This hardening pass is successful when the client can truthfully claim all of the following:

it never constructs canonical identity locally,

it accepts login success only after governed identity is returned by the server,

it treats tokens as opaque credentials,

it preserves one lifecycle correlation ID,

it reflects server-issued mode exactly,

it persists credentials only after valid identity confirmation,

it produces proof anchored in server truth,

it refuses floating execution.

Expected Deliverables

The implementing agent should produce:

updated client auth orchestration code,

any required model or validator adjustments,

tightened proof bundle generation behavior,

updated CLI success/failure handling if needed,

expanded or adjusted tests,

a concise completion report explaining:

what changed,

why it changed,

how the client now aligns with server law,

what tests prove that alignment.

If story docs are updated, the edits should be small and directly tied to this hardening pass.

Non-Negotiable Behavioral Rules

The implementing agent must preserve the following:

no secret leakage,

no weakening of secure credential storage,

no local identity synthesis,

no false success,

no mode inference,

no replayless proof closure,

no silent acceptance of incomplete server identity.

Good End State

When this work is complete, the auth zipper should behave like this:

keyhole login
-> auth challenge initiated
-> auth completed
-> provisional token/session received
-> /whoami called
-> governed identity returned
-> identity validated
-> credentials persisted
-> proof bundle written from server truth
-> AUTH_SUCCESS confirmed in chain
-> login reported successful

And if that chain breaks anywhere after token exchange, the user should receive a deterministic failure, not a fake success.

Final Guidance to the Implementing Agent

This is a precision hardening task, not a creative rewrite.

Stay disciplined.

Keep the existing architecture where it is already good. Tighten only what is necessary to align the client with server-governed identity truth.

The purpose of this pass is to make the first SDK zipper not only pleasant to use, but constitutionally correct, replayable, and safe as the foundation for every subsequent SDK story.