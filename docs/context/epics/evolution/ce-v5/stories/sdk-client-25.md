# SDK-CLIENT-25 - VS Code MCP Passwordless Auth Client: Device Flow, Logout Recovery, and Auth State Hygiene

**Status:** READY  
**Story Stream:** SDK-CLIENT  
**Owner:** Keyhole Solution Foundation  
**Author:** Keyhole Solution Foundation  
**Companion Story:** SDK-SERVER-25  
**Depends On:** SDK-SERVER-25  
**Related Stories:** SDK-CLIENT-24, SDK-SERVER-24  
**Constitutional Layer:** MCP boundary / client identity / auth lifecycle  
**Risk Level:** CRITICAL  
**Primary Surface:** VS Code MCP client / Keyhole SDK client tooling  
**Validation Runtime:** kh-dev  
**Production Runtime:** kh-prod  

---

## 1. Summary

SDK-CLIENT-25 implements the client-side half of the passwordless MCP auth convergence defined by SDK-SERVER-25.

SDK-SERVER-25 establishes the server-side truth:

- Authorization Code + PKCE remains supported.
- OAuth 2.0 Device Authorization Grant becomes the portable magic-link path.
- Magic links are based on `verification_uri_complete`.
- No custom MCP-side magic-link completion queue is allowed.
- `/mcp/v1/capabilities` advertises supported auth flows.
- SSE and `initialize` auth behavior must fail fast instead of hanging.

This client story consumes that contract.

The client must:

- discover server-supported auth flows,
- prefer `device_authorization` when available for VS Code-style interactive login,
- preserve PKCE fallback where needed,
- clear stale auth state on sign-out,
- prevent poisoned sessions from blocking re-auth,
- poll the standard OAuth token endpoint during device flow,
- never decode JWTs for authority decisions,
- treat tokens as opaque credentials,
- reconnect the MCP server only after authenticated credentials are available,
- provide clear UX for pending, approved, expired, denied, and failed auth states.

---

## 2. Problem Statement

The current VS Code MCP login flow mostly works on first connection:

```text
VS Code starts Keyhole MCP server
  ↓
No account connected
  ↓
OAuth metadata discovered
  ↓
Browser opens Keycloak email capture form
  ↓
Email sends code + magic link
  ↓
User verifies
  ↓
VS Code session authenticates
  ↓
Keyhole MCP tools become available

Two client-visible failures remain.

2.1 Bug 1 - Re-auth after sign-out hangs

After signing out:

Signing out stops the Keyhole MCP server.
Starting the server again does not reliably restart auth.
Reloading the VS Code developer window does not help.
Restarting VS Code does not help.

Observed behavior:

Starting server keyhole
Connection state: Running
Discovered resource metadata
Discovered authorization server metadata
Waiting for server to respond to initialize request...
Waiting for server to respond to initialize request...
Stopping server keyhole
Connection state: Stopped

Root client-side issue:

The client can retain stale OAuth/session state after sign-out.
It then skips fresh login and attempts initialize without a valid usable auth context.

The server can fail fast if it receives a bad request, but the client owns clearing stale state and restarting the correct auth flow.

2.2 Bug 2 - Magic link starts a new flow

Under PKCE loopback, a magic link clicked from another browser or mobile device cannot reliably complete the original VS Code flow.

Why:

VS Code holds the PKCE verifier locally.
The browser must return the auth code to VS Code's local callback listener.
A different browser or phone cannot deliver that code to the waiting VS Code session.

Therefore, client-side behavior must change:

Portable magic-link login must use OAuth Device Authorization Grant.
The client must poll the standard token endpoint instead of waiting for a loopback redirect.
3. Goal

Implement client-side passwordless MCP auth convergence for VS Code and Keyhole SDK client tooling.

The target behavior:

User starts Keyhole MCP server in VS Code
  ↓
Client fetches /mcp/v1/capabilities
  ↓
Client sees device_authorization supported
  ↓
Client starts OAuth Device Authorization Grant
  ↓
User receives email with magic link
  ↓
User clicks link from any browser/device
  ↓
Client polls token endpoint until approved
  ↓
Client stores credentials securely
  ↓
Client starts authenticated MCP session
  ↓
initialize succeeds
  ↓
whoami resolves identity
  ↓
Keyhole MCP tools become available

Logout target behavior:

User signs out
  ↓
Client revokes token where supported
  ↓
Client clears all local auth/session/cache state
  ↓
Client stops MCP server
  ↓
Next server start begins a fresh auth transaction
  ↓
No stale initialize hang
4. Non-Goals

This story does not:

modify SDK-SERVER-25,
create custom MCP auth endpoints,
create /mcp/v1/auth/magic-link/start,
create /mcp/v1/auth/magic-link/poll,
deliver tokens through custom MCP polling,
decode JWTs client-side for authority decisions,
embed server governance logic in the client,
grant operational authority to the client,
bypass Keycloak,
remove PKCE,
remove CLI auth,
require direct cluster access,
require Docker/Kubernetes access,
assume VS Code native MCP already supports RFC 8628 without verification.
5. Final Client Auth Model
5.1 Flow Selection

The client must select auth flow based on server capabilities.

Preferred logic:

Fetch /mcp/v1/capabilities
  ↓
If device_authorization supported:
    use device authorization for VS Code interactive login
Else if authorization_code_pkce supported:
    use PKCE fallback
Else:
    fail with clear unsupported-auth error
5.2 Supported Flows
Flow	Client Support	Purpose
Device Authorization Grant	Required	Portable magic-link auth
Authorization Code + PKCE	Preserved	Same-browser fallback
Custom magic-link queue	Forbidden	Rejected by SDK-SERVER-25
Password grant	Forbidden unless separately authorized	Not appropriate for VS Code MCP login
5.3 Magic-Link Meaning

In SDK-CLIENT-25, "magic link" means:

A verification_uri_complete link for an OAuth Device Authorization transaction.

It does not mean:

a token in email
a custom MCP auth callback
a PKCE loopback workaround
a client-side credential handoff
6. Client Compatibility Modes

Because VS Code MCP runtime support for OAuth Device Authorization Grant must be verified, this story supports three implementation paths.

6.1 Mode A - Native VS Code MCP Device Flow

Use this if the VS Code MCP runtime natively supports RFC 8628.

Client responsibilities:

discover device_authorization_endpoint,
request device_code,
display pending UX,
rely on email magic link for approval,
poll token endpoint,
store credentials securely,
start MCP session after token acquisition.

This is the preferred mode.

6.2 Mode B - Keyhole VS Code Auth Wrapper

Use this if VS Code MCP does not natively support RFC 8628 but allows extension-level auth mediation.

The Keyhole VS Code extension or wrapper may:

initiate standard RFC 8628 device flow,
handle token polling,
store credentials in VS Code SecretStorage,
provide the token to the MCP connection through supported VS Code APIs,
clear credentials on sign-out.

Constraints:

must still use standard OAuth device authorization,
must not use custom MCP magic-link polling,
must not decode JWTs for authority,
must not bypass the MCP boundary.
6.3 Mode C - CLI-Assisted Auth Bridge

Use this only if native VS Code support and extension-level mediation are not immediately available.

The CLI may:

initiate standard device authorization,
complete polling,
store credentials in a local Keyhole credential store,
expose credentials to the client through a controlled local contract.

Constraints:

no raw token printing,
no credential leakage to shell history,
no direct server-side custom auth queue,
no client JWT authority decisions,
credential store must be OS-secure where possible,
VS Code identity must not silently mismatch CLI identity.

This mode must include identity mismatch detection.

7. Required Client Behavior
7.1 Capability Discovery

Before starting auth, the client must retrieve capabilities:

GET /mcp/v1/capabilities

The client must inspect:

{
  "auth": {
    "supported_flows": [
      "authorization_code_pkce",
      "device_authorization"
    ],
    "preferred_interactive_flow": "device_authorization"
  }
}

If device_authorization is present and preferred, use it.

If capabilities are unavailable, client may fallback to existing PKCE only if configured to do so.

7.2 Device Authorization Start

The client must call the standard OAuth device authorization endpoint discovered from metadata.

Required returned fields:

{
  "device_code": "...",
  "user_code": "...",
  "verification_uri": "...",
  "verification_uri_complete": "...",
  "expires_in": 900,
  "interval": 5
}

Client must not log raw device_code.

Client may display a safe pending message:

Check your email and click the Keyhole sign-in link.
Waiting for approval...

The client does not need to prominently display the user_code unless fallback mode is enabled.

7.3 Polling

The client must poll the standard OAuth token endpoint using:

grant_type=urn:ietf:params:oauth:grant-type:device_code

The client must handle standard responses:

Response	Client Behavior
authorization_pending	Continue polling
slow_down	Increase polling interval
access_denied	Stop and show denied message
expired_token / expired device code	Stop and offer restart
success	Store credentials and start MCP session
network error	Retry with bounded backoff
server error	Retry with bounded backoff, then fail clearly

The client must obey the server-provided polling interval.

The client must stop polling when:

approved,
expired,
denied,
user cancels,
MCP server is stopped,
auth session is superseded by a newer login attempt.
7.4 Auth Session Supersession

The client must maintain a local auth attempt ID.

If the user starts a new login while an old device flow is pending:

old attempt -> superseded
new attempt -> active

Only the active attempt may store credentials.

Late success from an old attempt must be ignored.

7.5 Credential Storage

The client must store credentials securely.

Preferred locations:

Environment	Storage
VS Code extension	VS Code SecretStorage
Desktop CLI	OS keychain where available
Headless/dev fallback	restricted file with explicit warning
CI	injected secret / no interactive storage

The client must never store tokens in:

workspace settings
repo files
plain logs
shell history
MCP server config JSON
extension gallery metadata
7.6 Token Treatment

The client must treat tokens as opaque credentials.

The client must not:

decode JWTs for authorization,
infer tenant/org/cohort from token claims,
decide tool availability locally,
override server-resolved identity,
synthesize worker bindings.

After authentication, the client must call:

whoami

or the canonical MCP identity endpoint/tool to confirm server-resolved identity.

7.7 MCP Start Ordering

The client must not open an authenticated MCP session until usable credentials exist.

Correct order:

discover capabilities
  ↓
complete auth
  ↓
store token
  ↓
start MCP connection
  ↓
initialize
  ↓
whoami

If the VS Code runtime requires the server process to start before auth discovery, the client must still avoid an unauthenticated initialize hang by restarting/reconnecting after auth completes.

8. Logout / Re-Auth Recovery
8.1 Sign-Out Requirements

On sign-out, client must:

stop MCP server/session,
revoke token where supported,
delete access token,
delete refresh token,
delete device flow state,
delete PKCE verifier/state,
delete cached auth server metadata if marked session-bound,
delete pending auth attempt IDs,
delete stale MCP connection state,
clear any extension-level account binding,
emit local diagnostic event/log,
show signed-out status.
8.2 Re-Auth Requirements

After sign-out, starting Keyhole MCP again must behave like first run.

Expected behavior:

No valid credential found
  ↓
fresh capabilities discovery
  ↓
fresh device authorization request
  ↓
fresh email magic link
  ↓
fresh token polling
  ↓
new authenticated MCP session

Forbidden behavior:

reuse old pending auth attempt
reuse revoked token
reuse expired refresh token without handling failure
skip login and call initialize
hang waiting for initialize
require full VS Code reinstall
require manual secret deletion
8.3 Stale Token Handling

If an existing token fails:

401 / invalid_token / revoked / expired

Client must:

mark credential invalid,
clear local auth session state,
stop MCP connection,
start fresh auth if user requested connection,
avoid retrying the same bad token indefinitely.
8.4 Refresh Token Handling

If refresh token exists:

attempt refresh before interactive login,
if refresh succeeds, continue,
if refresh fails with invalid/expired/revoked, clear credentials,
then start device auth.

No failed refresh may poison the next login.

9. Identity Mismatch Detection

The client must detect identity mismatch across surfaces where possible.

Examples:

VS Code extension account differs from CLI account.
MCP server config references stale account.
SecretStorage token subject differs from server whoami.
Workspace expected account differs from connected account.

Required behavior:

Detected Keyhole identity mismatch.

VS Code is connected as: <server-resolved identity>
CLI appears connected as: <other identity>

Choose one:
- Use VS Code identity
- Re-authenticate VS Code
- Re-authenticate CLI

Do not silently merge identities.

Do not silently overwrite credentials.

Do not infer identity from JWT alone. Use server-resolved whoami for confirmation.

10. User Experience Requirements
10.1 First Login

Display:

Connecting Keyhole...

Check your email and click the sign-in link.
This window will continue automatically after approval.

Optional fallback:

If the link does not work, return here and restart sign-in.
10.2 Pending

Display:

Waiting for email approval...

Show safe countdown if available:

Sign-in link expires in 14:32.
10.3 Success

Display:

Keyhole connected.
MCP tools are now available.

Then call whoami and display server-resolved identity.

10.4 Expired

Display:

This sign-in link expired.
Start sign-in again.

Client must provide restart action.

10.5 Denied

Display:

Sign-in was denied or canceled.
No Keyhole account is connected.
10.6 Network Failure

Display:

Could not reach Keyhole authentication service.
Check your connection and try again.

Do not loop forever.

10.7 Re-Auth Required

Display:

Your Keyhole session expired.
Sign in again to reconnect MCP tools.
11. Client Diagnostics

Add local diagnostic output for:

capabilities fetched,
selected auth flow,
device auth started,
polling pending,
polling slowed down,
polling approved,
polling expired,
token stored,
token refresh attempted,
token refresh failed,
credentials cleared,
MCP server stopped,
MCP server restarted,
initialize started,
initialize succeeded,
initialize rejected,
whoami succeeded,
identity mismatch detected.

Diagnostics must redact:

access_token
refresh_token
device_code
authorization header
magic link
raw email address

Safe example:

{
  "event": "auth.flow.selected",
  "flow": "device_authorization",
  "realm": "kh-prod",
  "client_id": "keyhole-vscode",
  "correlation_id": "...",
  "decision": "ACCEPT"
}
12. Client-Side Event / Evidence Model

The client may not write canonical Event Spine records directly unless using approved MCP tools.

However, it must produce local evidence files/logs for promotion validation.

Required local evidence:

client-auth-flow-selected.json
client-device-started.redacted.json
client-polling-pending.redacted.json
client-polling-success.redacted.json
client-credential-store-proof.redacted.json
client-whoami-after-auth.redacted.json
client-logout-cleared-state.json
client-reauth-success.json
client-identity-mismatch-test.json

All evidence must be redacted.

13. Required Tests
13.1 Unit Tests

Add tests for:

capabilities parsing,
device flow selected when advertised,
PKCE fallback when device flow unavailable,
unsupported auth flow error,
device authorization response parsing,
polling authorization_pending,
polling slow_down,
polling success,
polling expiry,
polling denied,
network retry with bounded backoff,
auth attempt supersession,
stale token clearing,
refresh failure clearing,
logout deletes all auth state,
re-auth starts fresh transaction,
identity mismatch detection,
redaction of secrets in logs.
13.2 Integration Tests

Required flows:

first login:
capabilities -> device auth -> polling success -> token stored -> MCP initialize -> whoami
logout and re-auth:
login -> whoami -> logout -> credentials cleared -> restart -> new device auth -> whoami
expired link:
device auth start -> no approval -> expiry -> restart available
denied auth:
device auth start -> denial -> no token stored
stale token:
stored invalid token -> MCP rejects -> client clears token -> fresh device auth
identity mismatch:
CLI identity A + VS Code identity B -> warning -> no silent overwrite
13.3 Manual QA

Manual QA must verify:

first-time VS Code login,
logout,
restart login without reloading developer window,
restart login after full VS Code restart,
email link clicked in same browser,
email link clicked in different browser,
email link clicked from mobile,
expired link,
reused link,
invalid link,
network interruption during polling,
server unavailable during polling,
user cancels pending login.
14. Acceptance Criteria
14.1 Flow Selection
 Client reads /mcp/v1/capabilities.
 Client selects device_authorization when advertised and preferred.
 Client preserves PKCE fallback.
 Client never selects custom magic-link queue.
 Client produces clear unsupported-flow error if no supported flow exists.
14.2 Device Authorization
 Client starts standard OAuth device authorization.
 Client handles device_code, user_code, verification_uri, verification_uri_complete, expires_in, and interval.
 Client polls standard token endpoint.
 Client handles authorization_pending.
 Client handles slow_down.
 Client handles success.
 Client handles expiry.
 Client handles denial.
 Client handles bounded network retry.
 Client stops polling on cancellation or supersession.
14.3 Logout / Re-Auth
 Sign-out stops MCP connection.
 Sign-out clears access token.
 Sign-out clears refresh token.
 Sign-out clears pending device auth state.
 Sign-out clears PKCE state.
 Sign-out clears stale connection state.
 Restart after sign-out begins a fresh auth transaction.
 Restart after sign-out does not hang on initialize.
 Re-auth succeeds without reinstalling VS Code.
 Re-auth succeeds without manually deleting extension storage.
14.4 Credential Safety
 Tokens are stored only in approved secure storage.
 Tokens are never logged.
 Device codes are never logged raw.
 Magic links are never logged raw.
 Authorization headers are never logged.
 Client treats JWTs as opaque credentials.
 Client confirms identity through server whoami.
14.5 Identity Safety
 Client detects VS Code / CLI identity mismatch where observable.
 Client does not silently merge identities.
 Client does not silently overwrite credentials.
 Client does not infer authority from token claims.
 Client displays server-resolved identity after auth.
14.6 UX
 First login UX is clear.
 Pending approval UX is clear.
 Expired link UX is clear.
 Denied auth UX is clear.
 Re-auth required UX is clear.
 Network failure UX is clear.
 User can restart sign-in cleanly.
15. Required Evidence

Evidence path:

docs/context/epics/sdk/client/sdk-client-25/evidence/sdk-client-25/

or the current canonical client evidence path.

Required evidence tree:

evidence/sdk-client-25/
  decision/
    client-auth-mode-selection.md
    vscode-device-flow-support.md
    fallback-path.md
  capabilities/
    capabilities-response.redacted.json
    selected-auth-flow.json
  device-flow/
    device-authorization-response.redacted.json
    polling-pending.redacted.json
    polling-slow-down.redacted.json
    polling-success.redacted.json
    polling-expired.redacted.json
    polling-denied.redacted.json
  credentials/
    credential-storage-proof.redacted.md
    credential-redaction-proof.log
    token-refresh-failure-clears-state.log
  mcp/
    initialize-after-auth.log
    whoami-after-auth.redacted.json
    stale-token-recovery.log
  logout-reauth/
    logout-state-before.redacted.json
    logout-state-after.redacted.json
    reauth-fresh-transaction.log
    reauth-success-whoami.redacted.json
  identity/
    identity-match.redacted.json
    identity-mismatch-warning.redacted.txt
  tests/
    unit.log
    integration.log
    manual-qa.md
  promotion/
    client-verification-report.md

All token-bearing evidence must be redacted.

16. Required Make Targets

Use existing client validation targets where available.

Minimum expected:

make clean-code
make sdk.client.test
make sdk.client.auth.verify
make sdk.client.integration

Add if missing:

make sdk.client.device-auth.verify
make sdk.client.logout-reauth.verify
make sdk.client.identity-mismatch.verify
make sdk.client.redaction.verify

If target names differ, evidence must map this story's requirements to current canonical targets.

17. Implementation Notes

Likely client-side areas to inspect:

packages/keyhole-cli/
packages/keyhole-sdk/
vscode extension auth adapter, if present
MCP server configuration generator
credential storage utilities
auth/device flow client
capabilities client
whoami client
doctor command
logout/signout command

Exact paths must be verified in the SDK repo.

18. Rollout Plan
Phase 1 - Compatibility Discovery
Confirm whether VS Code MCP runtime supports RFC 8628.
Record result in vscode-device-flow-support.md.
Select Mode A, B, or C.
Phase 2 - Client Flow Selection
Parse /mcp/v1/capabilities.
Select device authorization when available.
Preserve PKCE fallback.
Phase 3 - Device Flow Implementation
Start device authorization.
Poll token endpoint.
Handle standard OAuth device responses.
Store credentials securely.
Start MCP session only after auth.
Phase 4 - Logout/Re-Auth Hardening
Clear all auth/session state on sign-out.
Stop MCP server.
Restart with fresh auth transaction.
Prove no stale initialize hang.
Phase 5 - Identity Safety
Call whoami after auth.
Display server-resolved identity.
Detect mismatch where possible.
Add warning and remediation path.
Phase 6 - Evidence and Promotion
Run tests.
Capture redacted evidence.
Coordinate with SDK-SERVER-25 production verification.
19. Rollback Plan

Rollback must restore the previous client auth behavior without corrupting user credentials.

Rollback requirements:

preserve existing valid credentials where safe,
avoid deleting unrelated accounts,
disable device-flow preference if necessary,
restore PKCE fallback,
document how users recover from partial auth state.

Required rollback evidence:

rollback/
  previous-auth-mode-restored.md
  pkce-fallback-works.log
  credential-store-integrity.md
  post-rollback-whoami.redacted.json
20. Security Requirements
No token logging.
No raw device-code logging.
No raw magic-link logging.
No authorization-header logging.
No token storage in repo/workspace files.
No client-side JWT authority decisions.
No silent identity switching.
No custom auth completion queue.
No direct operational access.
Tokens are opaque.
Identity is server-resolved.
Tool access depends on MCP server authorization.
21. Doctrine Requirements
21.1 MCP Boundary

The client authenticates to MCP.

The client does not become the control plane.

21.2 Builders Out, Declarations In

The client may request auth and submit declarations through approved MCP tools.

The client may not execute deterministic platform control logic locally.

21.3 Server-Resolved Identity

The client must call server identity endpoints/tools.

The client must not infer governance identity from token claims.

21.4 Standards-First Auth

Allowed:

OAuth Device Authorization Grant
OAuth Authorization Code + PKCE
OIDC discovery
OAuth token refresh/revocation

Disallowed:

custom magic-link token queues
tokens in email
client-side token introspection as authority
21.5 Credential Hygiene

Logout means credential and session cleanup.

A signed-out client must not retain hidden state that prevents fresh login.

22. Open Questions
Does current VS Code MCP runtime support RFC 8628 natively?
If not, do we implement a Keyhole VS Code auth wrapper or CLI-assisted bridge first?
What is the canonical secure credential store for each supported OS?
Should the code fallback be exposed in the client UI or hidden behind advanced troubleshooting?
How should identity mismatch be surfaced across VS Code, CLI, Cursor, JetBrains, and future gallery-installed MCP clients?
Should keyhole doctor be extended to report auth surface identity alignment?
Should sign-out revoke refresh tokens immediately or only clear local credentials if revocation is unavailable?
23. Done Definition

SDK-CLIENT-25 is complete when:

client reads server capabilities,
client selects device authorization when available,
client preserves PKCE fallback,
device-flow polling succeeds,
portable email magic link works with the server-side contract,
logout clears all local auth/session state,
re-auth after logout starts fresh,
stale tokens are cleared automatically,
initialize does not hang because of poisoned client auth state,
identity is confirmed through whoami,
identity mismatch is detected where observable,
credentials are stored securely,
secrets are redacted from logs/evidence,
unit/integration/manual QA passes,
evidence is captured.
24. Agent Handoff

Implement SDK-CLIENT-25 as the client-side companion to SDK-SERVER-25.

Do not build custom MCP magic-link polling.

Do not consume custom completion-queue endpoints.

Use standard OAuth Device Authorization Grant when the server advertises it.

Preserve Authorization Code + PKCE fallback.

Clear all auth state on sign-out.

Treat tokens as opaque.

Use server whoami for identity.

Prevent stale auth from causing initialize hangs.

Capture redacted evidence and coordinate final verification with SDK-SERVER-25.