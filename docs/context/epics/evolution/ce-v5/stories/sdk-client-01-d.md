SDK-CLIENT-01-D - Host Credential Installation, Extension Reconciliation, and Live Principal Alignment

Status: COMPLETE
Epic: SDK-CLIENT
Priority: High
Type: Client environment reconciliation / host provisioning / identity alignment
Paired Story: SDK-SERVER-01-C - Governed Connection Identity Surfaces, Scope Binding, and Reconciliation Truth

Goal

Make keyhole login and keyhole doctor govern the identity actually used by local MCP-capable hosts.

After this story, a human signs in once through the CLI, the CLI provisions the appropriate host/runtime configuration for VS Code, JetBrains, Cloud Code, and other supported local MCP hosts, the host reconnects directly to the Keyhole MCP boundary using that provisioned identity, and doctor can prove whether the live host connection is aligned or split from the CLI principal.

This story closes the gap between:

CLI-authenticated identity
locally configured host identity
live MCP connection identity on the server

The CLI remains a provisioning and reconciliation authority, not a long-lived request proxy.

Why This Story Exists

SDK-SERVER-01-C closed the server-side truth surfaces. The platform can now inspect connection identity, list connections, inspect status, trace lineage, and eventually rebind or invalidate live connections. That solved the server half.

But the local environment is still only partially set up.

Today, a user can successfully run:

keyhole doctor

and receive an ACCEPT verdict in local_only mode even while the actual MCP host process may still be authenticated as the wrong principal. In practical terms:

Nathan may still be the principal used by the active VS Code MCP host
Paul may or may not be signed in via CLI
doctor does not clearly show the split
the CLI does not yet provision the IDE/plugin/agent host so that the host reconnects using the intended principal

That means the system still has an operational gap: the human can log in locally, but the actual north-south host connection may continue using a different cached credential source.

This story closes that gap by making the CLI the credential installer and host reconciler for local MCP-capable environments.

Problem Statement

The SDK currently authenticates the user locally, but it does not yet reliably install or reconcile that identity into the local MCP host runtime that makes north-south requests to the Keyhole server.

As a result:

local CLI identity may differ from live host connection identity
the host may continue using stale credentials or a different credential store
keyhole doctor may report a local-only ACCEPT without proving that the live host is aligned
the user cannot confidently know whether the active IDE/agent runtime is acting as Paul, Nathan, or some prior principal

The architecture must not solve this by routing all traffic through the CLI. The correct architecture is:

CLI acquires and refreshes auth material
CLI discovers supported hosts
CLI installs or updates the host-side Keyhole auth/config
host reconnects directly to the MCP boundary
server-side connection truth confirms the resulting live principal
Constitutional Fit

This story supports:

MCP Boundary Discipline - host runtimes continue to connect directly to the boundary
Split Identity Must Be Visible - doctor must reveal live host-vs-CLI divergence
Login Is Not Rebind - local login does not silently mutate server-side connection identity without reconnect/rebind semantics
Publish the Laws, Not the Locks - users get clear outcome and repair guidance without exposing internal enforcement logic
Rule 00 - deterministic provisioning and verification, no agentic hidden behavior
Single Spine / Dual Lens / One Mint - the local environment must not create shadow identity paths outside the governed boundary
Scope

This story includes:

local discovery of supported MCP-capable hosts
host-specific Keyhole credential/config installation
detection of local credential source mismatches
doctor output that distinguishes CLI identity, configured host identity source, and live connection identity
reconnect/reload guidance or automation where feasible
verification of live alignment using server-side connection surfaces

This story does not include:

turning the CLI into a long-lived traffic proxy
replacing native host extension/plugin authentication behavior with a separate transport plane
redesigning server-side connection surfaces
adding non-local remote workstation management
building every host integration at once if phased rollout is needed
User Outcome

After this story:

The user signs in through the CLI as the intended principal.
The CLI discovers installed supported hosts.
The CLI provisions each selected host with the correct Keyhole auth/config.
The host reconnects directly to the Keyhole MCP server.
keyhole doctor verifies whether:
the CLI principal,
the configured host principal source,
and the live connection principal
are aligned.

If they are not aligned, doctor emits a precise repair plan.

Delivers
1. Host Discovery Layer

Implement a local host discovery subsystem that inventories installed MCP-capable environments and reports whether they appear provisionable for Keyhole.

Initial supported host families:

VS Code / VS Code-compatible environments
JetBrains IDE family
Cloud Code or equivalent cloud/dev runtime where local config is accessible
Native agent/runtime environments supported by the SDK's local tooling model

For each discovered host, collect and normalize:

host type
install presence
config path or integration point
Keyhole MCP server registration presence
auth source location or mode if detectable
reload/reconnect requirements
support status: supported / partial / unsupported / unknown

This discovery must be safe and read-only until the user explicitly installs or repairs.

2. Host Credential Installation Layer

Implement CLI-driven provisioning so the CLI can install or update the Keyhole auth/config that the host runtime will actually use.

This layer must:

take the authenticated CLI session as the source of truth for the intended principal
write the appropriate host-side Keyhole auth/config
avoid duplicating secrets into uncontrolled locations unnecessarily
support environment-variable-driven portability
preserve direct host-to-server north-south connections

The installation layer may use host-specific templates/adapters, but the user-facing flow must be uniform.

Minimum supported actions:

install credentials/config for a newly detected host
update/repair stale host config
switch a host from one principal context to another
clear or invalidate broken local host auth material where supported
3. Principal Source Inspection

Doctor must show the difference between three distinct identity layers:

CLI principal - who the local CLI is authenticated as
Configured host principal source - what identity source the host appears configured to use
Live connection principal - who the host is actually bound as on the server

This is the central deliverable.

Doctor must stop pretending "environment okay" when only the CLI layer is okay.

4. Live Reconciliation Workflow

Add a governed local reconciliation flow that:

compares CLI principal vs configured host source vs live connection principal
classifies the result
offers a deterministic repair action
re-checks after repair

Minimum verdict classes:

ALIGNED
SPLIT_IDENTITY
STALE_HOST_AUTH
HOST_NOT_CONFIGURED
HOST_CONFIG_UNREADABLE
LIVE_CONNECTION_MISSING
SURFACE_UNAVAILABLE
SCOPE_DENIED
RECONNECT_REQUIRED
UNSUPPORTED_HOST

The CLI must explain what is wrong in concrete terms.

5. Host Reconnect / Reload Guidance

After credential installation or repair, the CLI must guide the user to the next required action so the host actually picks up the new auth source.

Support one of the following per host:

automatic reconnect/reload, where feasible and safe
deterministic reload instructions
explicit indication that a full IDE restart is required
explicit indication that the user must restart the MCP extension/plugin

The story is not complete if the CLI writes config but leaves the user unclear on how to make the live host pick it up.

6. Doctor Mode Upgrade

Extend keyhole doctor beyond local_only so it can run a true host-aware reconciliation pass.

Minimum modes:

local_only
host_inventory
live_reconciliation

live_reconciliation must use server-side connection identity surfaces to verify actual live host truth.

If live verification is unavailable, doctor must degrade honestly, not falsely ACCEPT.

7. Server Verification Integration

Integrate the existing server-side connection surfaces into doctor and host reconciliation flows:

connection.identity.inspect
connection.list.inspect
connection.status.inspect
connection.lineage.inspect

Doctor should use these to answer:

is there a live connection for this host,
who is it bound as,
is it fresh,
and does it match the intended principal

This is how the local environment becomes truly governable.

8. Non-Proxy Architecture Guarantee

Explicitly preserve the correct architecture:

CLI is for login, configuration, repair, and diagnostics
IDE/plugin/agent hosts connect directly to the MCP server
CLI is not inserted as a permanent transport intermediary

This must be visible in code structure, docs, and user behavior.

CLI Surface Additions
keyhole host list

Lists discovered hosts and their configuration status.

Example output shape:

host type
found / not found
Keyhole configured / not configured
configured principal source
reconnect requirement
support status
keyhole host inspect

Inspects a specific host in detail.

Must show:

config location
auth source mode
detected principal source if inferable
CLI principal
last-known live principal if retrievable
reconciliation verdict
keyhole host install

Installs or updates Keyhole credentials/config into the selected host.

Supports:

host selection
optional non-interactive mode
safe overwrite confirmation
dry-run mode
keyhole host repair

Applies a deterministic repair plan for a selected host.

Examples:

replace stale credential source
rewrite Keyhole MCP server config
re-point host to CLI-auth-installed auth source
clear broken prior Keyhole auth material if safe
keyhole doctor --mode live_reconciliation

Performs end-to-end alignment checks and reports the live principal used by the host connection.

Detailed Behavior
Discovery behavior

The SDK must discover and classify host environments without assuming a single IDE or filesystem layout. Discovery must tolerate:

host installed but no Keyhole config
Keyhole config present but unreadable
multiple supported hosts installed
multiple configs for the same host family
stale or conflicting host registrations

The discovery layer must be adapter-driven so new hosts can be added without rewriting doctor.

Install behavior

keyhole host install must:

confirm current CLI principal
identify target host
determine appropriate config/auth integration point
install/update Keyhole auth/config for that host
report whether reconnect is required
offer verification next step

It must never claim success unless it can prove the install step actually wrote the intended host configuration.

Reconciliation behavior

A full reconciliation pass must check:

intended principal from CLI
host's configured auth source
live server-side connection identity
freshness/staleness of the live connection
whether reload/reconnect is needed

It must produce an outcome grounded in actual state, not assumptions.

Verification behavior

After installation or repair, the SDK should attempt live verification using the server's connection surfaces.

Success condition:

live connection principal matches intended CLI principal
connection is fresh enough to be trusted
doctor returns ALIGNED

Failure conditions must explain exactly which layer is still divergent.

Acceptance Criteria
A. Host discovery
The SDK can inventory supported local host environments.
Discovery identifies whether a host is installed and whether Keyhole appears configured for it.
Discovery does not mutate the environment.
Discovery results are normalized into a shared host model.
B. Host installation
The CLI can install or update Keyhole auth/config for at least one supported host family end-to-end.
Installation uses the current CLI-authenticated principal as the intended identity.
Installation reports the target config/auth location actually modified.
Installation supports non-interactive and dry-run behavior.
Installation does not convert the CLI into a persistent request proxy.
C. Reconciliation truth
Doctor reports CLI principal separately from host-configured principal source and live connection principal.
Doctor can detect SPLIT_IDENTITY.
Doctor can detect HOST_NOT_CONFIGURED.
Doctor can detect LIVE_CONNECTION_MISSING.
Doctor can detect RECONNECT_REQUIRED.
Doctor no longer returns a misleading local ACCEPT when the live host is still acting as a different principal.
D. Live verification
After successful install and reconnect, connection.identity.inspect confirms the intended principal.
connection.list.inspect or equivalent confirms the connection exists.
connection.status.inspect confirms the connection is live/fresh.
Lineage or equivalent evidence shows the resulting connection lifecycle when available.
A repaired environment can be re-verified in a second pass without false positives.
E. UX and repair
Doctor emits deterministic repair guidance for each reconciliation failure mode.
The user is told exactly what action is required when automatic reconnect is unavailable.
The CLI does not hide unsupported or partially supported hosts; it reports them honestly.
Host-specific failures remain bounded to that host and do not corrupt other local environments.
F. Portability and structure
All host provisioning logic remains environment-overridable and portable.
Host adapters are isolated and testable.
Config path assumptions are centralized, not scattered.
The architecture remains direct-host-to-server.
Invariants
INV-SDK-CLIENT-01-D-001 - CLI Is Provisioner, Not Proxy

The CLI may acquire, refresh, install, repair, and verify auth/config, but it must not become the permanent transport path for MCP host traffic.

INV-SDK-CLIENT-01-D-002 - Split Identity Must Be Explicit

If the CLI principal and live host principal differ, doctor must report the split explicitly.

INV-SDK-CLIENT-01-D-003 - Host Config Must Be Observable

The SDK must be able to tell the user where the relevant host config/auth source lives or honestly report that it cannot determine it.

INV-SDK-CLIENT-01-D-004 - Repair Must Be Deterministic

Every doctor repair plan must map to a concrete local action or an explicit manual step.

INV-SDK-CLIENT-01-D-005 - Local Success Is Not Live Success

A local auth/config success must not be reported as full success unless live host alignment is verified or the verification limitation is clearly disclosed.

INV-SDK-CLIENT-01-D-006 - Live Truth Comes From Server Surfaces

The SDK must use governed connection identity surfaces to verify the live host principal.

INV-SDK-CLIENT-01-D-007 - Multi-Host Environments Remain Safe

Actions taken for one host must not silently rewrite or invalidate another host's Keyhole configuration unless explicitly requested.

Dependencies

Depends on:

SDK-SERVER-01-C live connection surfaces
working CLI login/auth flows
centralized config portability work already completed
host-specific config access patterns for supported environments
Unlocks

This story unlocks:

trustworthy local onboarding
true principal alignment across CLI and IDE/agent hosts
usable multi-user local development on the same machine
accurate doctor diagnostics for host identity drift
deterministic handoff from login to live host operation
safer enterprise/local workstation deployment patterns
Evidence Required for Closure

Closure evidence must include:

host discovery output showing at least one supported host
install or repair output for at least one supported host
doctor output showing:
CLI principal
configured host principal source
live connection principal
final reconciliation verdict
a split-identity test case that is correctly detected
an aligned-identity test case that is correctly detected
server-side proof from connection.identity.inspect
test counts and passing results for discovery/install/reconciliation flows
Test Plan
Unit tests
host discovery adapter tests
config path normalization tests
install dry-run tests
install write-path tests
repair-plan generation tests
doctor verdict classification tests
multi-host isolation tests
unsupported-host behavior tests
Integration tests
CLI login followed by host install
doctor host inventory mode
doctor live reconciliation mode
mismatch between CLI principal and live host principal
post-repair re-verification to aligned state
reconnect-required behavior
Live proof

At least one real supported host must show:

host discovered
Keyhole installed or repaired
host reconnected
live connection present
live principal aligned with intended CLI principal
doctor returns ALIGNED
Suggested Phase Breakdown
Phase 1 - Discovery

Build host adapters and normalized discovery inventory.

Phase 2 - Install

Implement host credential/config install for the first supported host family.

Phase 3 - Doctor upgrade

Teach doctor to show CLI principal vs host-configured source vs live principal.

Phase 4 - Repair

Add deterministic repair flows and reconnect guidance.

Phase 5 - Multi-host hardening

Handle multiple installed hosts, stale configs, unsupported environments, and safe isolation.

Definition of Done

This story is done when:

a user can authenticate as Paul through the CLI,
provision a supported host through the CLI,
reconnect the host directly to the Keyhole MCP boundary,
and use doctor to prove that the live host connection is acting as Paul rather than Nathan or some stale prior principal.

Until that end-to-end alignment is visible and repairable, the environment is not fully set up.

Short Rationale

SDK-SERVER-01-C gave the platform truth.
SDK-CLIENT-01-D makes local environments actually use that truth.

Without this story, users can log in successfully and still operate the wrong live principal. With this story, login, host config, live connection identity, and doctor all converge into a single governed outcome.