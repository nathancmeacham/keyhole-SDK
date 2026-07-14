# Transport Doctrine Regression Audit
**Date:** 2026-04-27  
**Severity:** CRITICAL - Doctrine Error / Propagated Misinstruction  
**Trigger:** VS Code MCP server failed to trigger browser/device auth flow; `initialize` timed out while URL `https://mcp.keyholesolution.com/sse` was correct  
**Discoverer:** User (natha)  
**Correct Statement:** SSE is the canonical MAIN transport. REST/HTTP is a backup/legacy transport.

---

## 1. Executive Summary

A critical transport doctrine error was introduced on **2026-03-13** by story **CE-V5-S42-02** and was further structural-enforced by story **CE-V5-S41-01** (surface governance). The error states that SSE and JSON-RPC are "tombstoned" and must never be used. This is factually incorrect for the VS Code MCP integration path and has propagated into every major instruction document, agent alignment file, and automated release-gate enforcement in the repository.

The immediate consequence was:
1. When the VS Code MCP client connected to `https://mcp.keyholesolution.com/sse` (the **correct** endpoint), the AI agent (GitHub Copilot) diagnosed this as a broken URL and suggested changing it to `/mcp/v1` - which would have destroyed the VS Code MCP connection.
2. The governance enforcement tooling (`public_surface_inventory.yaml` forbidden patterns) would REJECT any file that references `/mcp/sse`, meaning no author or agent could correctly document the VS Code integration path without triggering a release gate failure.

---

## 2. Origin: When and Where

### Primary Origin - CE-V5-S42-02

**File:** `docs/context/epics/evolution/ce-v5/stories/ce-v5-s42-02.md`  
**Created / Completed:** 2026-03-13  
**Story Title:** "Copilot / Agent Instruction Rehydration"

The story's "Current Boundary Truth This Story Must Encode" section, subsection F, states:

> **F) Legacy Transport Rule**
> Legacy SSE and JSON-RPC are tombstoned and must not be used.

This was encoded as an authoritative "current boundary truth" sourced from the live capabilities contract. The story's Deliverable 5 further specifies `transport: REST/HTTP` as the canonical connection guidance with no mention of the VS Code MCP integration path.

### Secondary Origin - CE-V5-S41-01

**File:** `docs/specs/developer_ecosystem/public_surface_inventory.yaml`  
**Story:** CE-V5-S41-01  
**Date:** ~2026-03-10

The surface inventory's `forbidden_patterns` section classifies `/mcp/sse` as a **private API reference** that must not appear in any governed public surface file:

```yaml
private_api_refs:
  - "/mcp/v1/runs/"
  - "/mcp/v1/events/"
  - "/mcp/v1/memory/"
  - "/mcp/sse"         ? WRONG: this is the canonical VS Code MCP connection path
```

The automated release gate (`services/shared/developer_surface_contract/release_gate.py`) enforces this. Any future documentation of the correct VS Code MCP integration endpoint would be rejected as a governance violation. This is the deepest structural embedding of the error.

---

## 3. The Root Cause: A Conflation of Two Distinct SSE Usages

The tombstoning error was caused by conflating two architecturally separate "SSE" concepts:

### Concept A - Old Keyhole SDK/CLI Internal Transport (Legitimately Deprecated)

Before the REST/HTTP migration, the Keyhole SDK and CLI used SSE/JSON-RPC as the transport protocol for calling Keyhole's own governed API operations (runs, events, capabilities, etc.). This was a private SDK implementation detail. Migrating this layer to REST/HTTP was legitimate and intentional. When S42-02 says "SSE tombstoned," it is (possibly correctly) referring to this old SDK-internal integration pattern.

### Concept B - VS Code Model Context Protocol (MCP) Standard Transport (CANONICAL)

The VS Code MCP integration protocol (Model Context Protocol) is an industry standard that uses **SSE + JSON-RPC** as its transport layer. This is not a Keyhole-specific legacy - it is how VS Code communicates with any MCP server. The Keyhole platform correctly exposes a VS Code MCP server at:

```
https://mcp.keyholesolution.com/sse
```

The `.vscode/mcp.json` with `"url": "https://mcp.keyholesolution.com/sse"` is the **correct** configuration. This endpoint is:
- The VS Code/agent tooling entry point into the Keyhole governed boundary
- SSE-based by MCP protocol specification
- The canonical MAIN transport for AI agent ↔ Keyhole MCP integration

### How the Conflation Happened

Story S42-02 was a documentation/instruction story, not a platform implementation story. It consumed "boundary truth" from the capabilities contract. The capabilities contract legitimately reports `transport: rest-http` for the **SDK/CLI REST API** layer. The story author interpreted this as a global tombstoning of SSE for all Keyhole connectivity - missing that the MCP SSE server endpoint is a separate, orthogonal transport used exclusively by VS Code and other MCP-speaking clients.

In other words: REST/HTTP is the transport for `GET /mcp/v1/capabilities`, `POST /mcp/v1/runs/start`, etc. SSE is the transport for VS Code's connection to the MCP server. These are parallel paths, not competing alternatives.

---

## 4. Propagation Map - All Contaminated Locations

| File | Error | Severity |
|------|-------|----------|
| `.github/copilot-instructions.md` | "Legacy SSE and JSON-RPC are tombstoned. Do not use them." (line 178, 597) | **CRITICAL** - Primary AI agent instruction source; causes incorrect agent diagnosis |
| `docs/AGENT.md` | "Legacy SSE and JSON-RPC are tombstoned. Do not use them." | **CRITICAL** - Agent alignment doc |
| `docs/supported-environments.md` | "SSE: Tombstoned / Do not use" in transport table | **HIGH** - Builder-facing environment matrix |
| `docs/boundary-constitution.md` | "the MCP boundary operates over REST/HTTP" (no SSE mention) | **HIGH** - Constitutional document |
| `docs/auth-bootstrap.md` | `transport: REST/HTTP` in posture table; `get_transport() -> "rest-http"` | **HIGH** - Bootstrap guidance |
| `docs/launch-readiness.md` | Item 10.6: "SSE and JSON-RPC are tombstoned; only REST/HTTP is documented - MET" | **HIGH** - Passes incorrect condition as a readiness gate |
| `docs/specs/developer_ecosystem/public_surface_inventory.yaml` | `/mcp/sse` in `forbidden_patterns.private_api_refs` | **CRITICAL** - Automated enforcement; blocks correct documentation at release gate |
| `docs/context/epics/evolution/ce-v5/stories/ce-v5-s42-02.md` | Section F - source of the doctrine | **HIGH** - Story-level origin; historical record |

### Secondary Damage

The AI agent (GitHub Copilot) session on 2026-04-27 produced the following incorrect diagnosis, directly caused by the poisoned instructions:

> "Two issues here: 1. URL points to the tombstoned SSE endpoint - `/sse` is deprecated..."

This was wrong. The URL was correct. The agent suggested editing `mcp.json` to change the URL from `/sse` to `/mcp/v1` - which would have broken VS Code MCP connectivity. The user correctly cancelled this action.

---

## 5. The Actual VS Code Connection Failure Root Cause

The VS Code connection failure described in the log was:

```
2026-04-27 12:22:46.177 [info] Waiting for server to respond to `initialize` request...
[repeated 5 times]
2026-04-27 12:23:06.754 [info] Stopping server keyhole
```

This is **NOT** caused by the wrong URL. The URL `https://mcp.keyholesolution.com/sse` is correct.

The failure pattern - auth metadata discovered correctly, then `initialize` times out - indicates the OAuth PKCE/device flow never completed. VS Code initiated the MCP connection, discovered the OAuth metadata correctly, but no browser redirect occurred to complete the token acquisition. Without a valid token, the `initialize` handshake with the MCP server could not complete.

**Probable causes of the auth failure (to be diagnosed separately):**
- Cached VS Code credential expired but VS Code did not re-trigger the browser flow
- PKCE code challenge/verifier mismatch in the token exchange
- VS Code MCP OAuth handler not detecting the need for re-auth
- Network/CORS issue blocking the token endpoint during the silent re-auth attempt

The correct resolution path is to clear VS Code's cached MCP credentials for the `keyhole` server and restart the server to force a fresh PKCE flow - NOT to change the URL.

---

## 6. Correct Transport Doctrine

The following replaces the incorrect tombstoning doctrine:

### Tier 1 - VS Code / MCP Client Transport (CANONICAL MAIN)

- **Protocol:** SSE + JSON-RPC (Model Context Protocol standard)
- **Endpoint:** `https://mcp.keyholesolution.com/sse`
- **Used by:** VS Code MCP integration (`.vscode/mcp.json`), any MCP-speaking client or agent host
- **Auth:** OIDC/PKCE token acquired by VS Code on behalf of the user
- **Status:** OK CANONICAL - this is the primary governed AI agent integration path

### Tier 2 - SDK/CLI REST API Transport (GOVERNED OPERATIONS)

- **Protocol:** REST/HTTP
- **Base path:** `https://mcp.keyholesolution.com/mcp/v1/`
- **Used by:** `keyhole-sdk`, `keyhole-cli` for governed operations:
  - `GET /mcp/v1/capabilities`
  - `GET /mcp/v1/whoami`
  - `POST /mcp/v1/runs/start`
  - `POST /mcp/v1/events/query`
- **Auth:** Bearer token via `Authorization` header
- **Status:** OK CANONICAL for SDK/CLI operations

### Deprecated / Tombstoned

- **Old SDK internal SSE transport:** SSE used by pre-S42 SDK code for calling Keyhole API operations. Replaced by REST/HTTP in the SDK transport layer. TOMBSTONED for SDK API calls. (**Does not apply to VS Code MCP SSE**)
- **Old JSON-RPC API protocol:** JSON-RPC used directly against Keyhole API endpoints (not the VS Code MCP protocol). TOMBSTONED for direct API calls.

The VS Code MCP protocol (SSE + JSON-RPC between VS Code and MCP server) is not the same thing as the old Keyhole SDK SSE transport. These must never be conflated.

---

## 7. Required Corrections

The following changes are required to abolish the misunderstanding. They must be treated as a coordinated correction, not piecemeal edits.

### 7.1 - `docs/specs/developer_ecosystem/public_surface_inventory.yaml` (HIGHEST PRIORITY)

Remove `/mcp/sse` from `forbidden_patterns.private_api_refs`. The forbidden pattern enforcement is the deepest structural embedding of the error and will block all other corrections from being documented.

**Current:**
```yaml
private_api_refs:
  - "/mcp/v1/runs/"
  - "/mcp/v1/events/"
  - "/mcp/v1/memory/"
  - "/mcp/sse"
```

**Required:**
```yaml
private_api_refs:
  - "/mcp/v1/runs/"
  - "/mcp/v1/events/"
  - "/mcp/v1/memory/"
  # /mcp/sse is the canonical VS Code MCP integration endpoint - NOT forbidden
```

Add `.vscode/mcp.json` to the public surface inventory so it is governed as a valid, documented surface.

### 7.2 - `.github/copilot-instructions.md`

Replace the "Tombstoned Transports" section (lines 176-180) and the anti-pattern entry (line 597) with the correct two-tier transport doctrine from section6 above.

The `Transport | REST/HTTP` row in the "Current Transport and Auth Posture" table must be expanded to distinguish:
- VS Code MCP protocol: SSE (canonical main)
- SDK/CLI API transport: REST/HTTP

### 7.3 - `docs/AGENT.md`

Replace "Legacy SSE and JSON-RPC are tombstoned. Do not use them." with the correct two-tier doctrine. Add explicit guidance that `.vscode/mcp.json` pointing to `/sse` is the correct VS Code MCP configuration.

### 7.4 - `docs/supported-environments.md`

Replace the transport table row:
```
| SSE | Tombstoned | Do not use |
```
with:
```
| SSE (VS Code MCP) | Canonical | Primary VS Code / MCP client integration path |
| SSE (old SDK API) | Deprecated | Old SDK internal transport; replaced by REST/HTTP in SDK |
```

### 7.5 - `docs/boundary-constitution.md`

The statement "the MCP boundary operates over REST/HTTP with OIDC/PKCE auth" must be qualified to note that the VS Code MCP integration layer uses SSE. REST/HTTP refers to the SDK/CLI API transport specifically.

### 7.6 - `docs/auth-bootstrap.md`

The transport posture table `| Transport | REST/HTTP |` must be scoped to "SDK/CLI API transport" to distinguish from the VS Code MCP SSE transport.

### 7.7 - `docs/launch-readiness.md`

Item 10.6: "No stale transport references" must be reworded. The current condition "SSE and JSON-RPC are tombstoned; only REST/HTTP is documented - MET" is itself the stale incorrect reference. The condition should instead verify that the two-tier transport doctrine is correctly documented.

### 7.8 - `.vscode/mcp.json`

No change required. `"url": "https://mcp.keyholesolution.com/sse"` is correct.

### 7.9 - `docs/context/epics/evolution/ce-v5/stories/ce-v5-s42-02.md`

This is the historical story document. It should receive an addendum noting that Section F's "Legacy Transport Rule" was over-broad: the tombstoning applies only to the pre-S42 SDK internal SSE transport, not to the VS Code MCP SSE protocol. The story's conclusion remains valid for its intended scope; the error was in application.

---

## 8. Enforcement Posture Going Forward

Once the forbidden pattern is removed and the two-tier doctrine is documented:

- `.vscode/mcp.json` should be added to the public surface inventory
- Agent instructions must explicitly distinguish "VS Code MCP transport" (SSE) from "SDK/CLI API transport" (REST)
- Any future story that modifies transport posture must include a section explicitly addressing both tiers
- The launch readiness checklist item 10.6 must be updated to test for the correct two-tier doctrine, not the incorrect single-transport doctrine

---

## 10. Server-Side Remediation

The root cause of this regression is server-side: `GET /mcp/v1/capabilities` returns
`transport: rest-http` with no field documenting the VS Code MCP SSE transport tier.
A future story author reading only the capabilities response will make the same
incorrect inference again.

A separate audit report for the server team has been produced:

**`docs/evidence/sse-transport-doctrine-server-audit-2026-04-27.md`**

That report covers:

- The capabilities contract gap and required `client_transports` amendment
- Story addenda required for CE-V5-S42-01, CE-V5-S42-02, and CE-V5-S42-INDEX
- Server-side investigation checklist
- Going-forward story authorship guard
- Priority action table for the server team

## 11. Impact on This Session

1. User reported VS Code MCP connection failure (correct `/sse` URL, hung `initialize`)
2. Agent read `.vscode/mcp.json` and saw `"url": ".../sse"`
3. Agent checked `copilot-instructions.md` (implicit, in-context) and applied the "SSE tombstoned" rule
4. Agent incorrectly diagnosed the URL as the problem
5. Agent attempted to edit `mcp.json` to change `/sse` -> `/mcp/v1`
6. User cancelled the edit (correct action)
7. User identified the root cause as doctrine regression, requested full audit

The actual connection failure root cause (OAuth re-auth not triggered) was masked by the incorrect transport diagnosis. The URL is correct. The auth flow needs to be re-initialized.

**Immediate action for the VS Code connection:** Clear the cached credentials for the `keyhole` MCP server in VS Code (Settings -> MCP -> keyhole -> clear cached token / restart server) to force a fresh PKCE browser flow.

---

## Audit Complete

This regression is fully traceable to a single story (CE-V5-S42-02, 2026-03-13) that overgeneralized a legitimate SDK transport deprecation into a global tombstoning of SSE. The error was then structurally embedded by the surface governance forbidden-patterns enforcement (CE-V5-S41-01). Seven distinct files must be corrected, starting with the forbidden-patterns enforcement which gates all other corrections.
