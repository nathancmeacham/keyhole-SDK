# Supported Environments — Keyhole Developer Kit

**Story:** CE-V5-S42-10  
**Purpose:** Make environment support expectations explicit for external builders  
**Last Updated:** 2026-03-14

---

## Environment Matrix

### Runtime Environments

| Environment | Posture | Tested | Notes |
|-------------|---------|--------|-------|
| Linux (Ubuntu 22.04+) | Primary | Yes | Primary development and CI target |
| macOS (13+) | Supported | Yes | Homebrew-based Python supported |
| Windows (WSL2) | Supported | Yes | Via WSL2 with Ubuntu; native Windows not tested |
| Windows (native) | Supported | Yes | PowerShell-based governed CLI smoke verified in June 2026 |

### Python Versions

| Version | Status | Notes |
|---------|--------|-------|
| Python 3.9 | Supported | Minimum required version |
| Python 3.10 | Supported | |
| Python 3.11 | Supported | |
| Python 3.12 | Supported | Recommended |
| Python 3.13+ | Not tested | May work but not validated |
| Python 3.8 or earlier | Not supported | Below minimum requirement |

### Docker Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| Docker Engine | 20.10+ | Required for local test runtime |
| Docker Compose | v2+ | Required for `docker compose up` |
| Docker Desktop | Optional | Common on macOS/Windows |

### Editor / IDE Posture

| Environment | Posture | Notes |
|-------------|---------|-------|
| VS Code (folder-based) | Primary | Agent instructions optimized for VS Code Copilot |
| VS Code (remote SSH) | Supported | e.g., connected to Linux VM |
| VS Code (Dev Containers) | Supported | Standard Docker-based dev containers |
| PyCharm / other IDEs | Compatible | SDK is standard Python; IDE-specific features not tested |
| Terminal-only | Fully supported | All operations work from CLI |

---

## SDK and CLI Installation

### SDK (keyhole-sdk)

| Method | Command | Status |
|--------|---------|--------|
| Editable install | `pip install -e packages/python/keyhole-sdk` | Recommended for development |
| From PyPI | `pip install keyhole-sdk` | When published |

**Dependencies:**
- `requests>=2.25`
- `pydantic>=2.0`
- `PyYAML` recommended; the governed quickstart also has a built-in fallback parser for declared Keyhole artifacts

No other runtime dependencies are required.

### CLI (keyhole-cli)

| Method | Command | Status |
|--------|---------|--------|
| Editable install | `pip install -e packages/python/keyhole-cli` | Recommended for development |
| From PyPI | `pip install keyhole-cli` | When published |

---

## MCP Boundary Connection Posture

### Transport

| Aspect | Value | Notes |
|--------|-------|-------|
| Protocol (VS Code MCP) | **SSE** | **Canonical main transport** — VS Code / MCP client integration via `.vscode/mcp.json` pointing to `/sse` |
| Protocol (SDK / CLI API) | REST/HTTP | SDK and CLI operations against `/mcp/v1/` endpoints |
| Base path (SDK/CLI) | `/mcp/v1/` | All SDK/CLI MCP API endpoints |
| TLS | Required for production | Local development may use HTTP |
| Old SDK-internal SSE | Deprecated | Pre-S42 SDK transport for API calls; replaced by REST/HTTP in SDK layer |
| Old SDK-internal JSON-RPC | Deprecated | Pre-S42 SDK transport for API calls; replaced by REST/HTTP in SDK layer |

### Authentication

| Aspect | Value | Notes |
|--------|-------|-------|
| Flow | OIDC/PKCE | Standard OAuth2 with PKCE |
| Realm | `keyhole-mcp` | Keycloak realm |
| Token type | Bearer | Passed via `Authorization` header |
| Discovery auth | Not required | `GET /mcp/v1/capabilities` is unauthenticated |
| Identity auth | Required | `GET /mcp/v1/whoami` requires bearer token |
| Context auth | Required | All run dispatches require bearer token |

### Contract

| Aspect | Value | Notes |
|--------|-------|-------|
| Contract version | `mcp/v1` | Current stable contract |
| Server min SDK version | `0.4.1` | Minimum compatible SDK advertised for the governed first-app flow |
| Current SDK version | `0.4.1` | Current package version in this repository |

---

## Local Test Runtime

### What It Provides

A local Docker container running the Keyhole test runtime:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/healthz` | GET | No | Health check |
| `/identity` | GET | No | Runtime identity |
| `/state` | GET | No | Runtime state |
| `/realize` | POST | No | Realization endpoint |

### How to Start

```bash
git clone https://github.com/Keyhole-Solution/keyhole-developer-kit.git
cd keyhole-developer-kit
docker compose up --build -d
curl http://localhost:8080/identity
```

### Mode

The local test runtime defaults to **local-only** mode:

- Realization requests execute immediately
- No MCP governance gating
- No Event Spine evidence
- Suitable for development and smoke testing

It can run in **governed** mode only when both `KEYHOLE_MCP_URL` and
`KEYHOLE_MCP_TOKEN` are configured before startup. A realization request with
`require_governed=true` fails closed when MCP configuration is missing or when
the upstream governance call does not approve the candidate. Local-only
realization remains available, but its receipt reports `governed=false` and
`event_spine_evidence=false`.

---

## Runtime Modes

| Mode | Description | Evidence |
|------|-------------|----------|
| local-only | No MCP connection; immediate realization | Not upstream-auditable |
| governed | Connected to MCP boundary; governance gating applies | Platform-side evidence |

The developer kit supports both modes. Local-only is the default for
development. Governed mode requires MCP boundary configuration.

For `my-first-app`, local-only mode may validate declarations and local
invariants, but it cannot claim governance or Event Spine evidence. That
directory is retained for legacy first-app and server-boundary evidence work,
not as the public launch quickstart.

The focused unit tests for CE-V5-S51-C02 exercise a fake-boundary governed path
so the SDK, CLI, runtime bridge, and local invariant input can prove the
client-side wiring without mutating live MCP, Event Spine, ATP, or controller
state. Live governed proof still requires an actual MCP receipt and event
reference returned by the boundary.

The blessed public external-builder launch path is:

```bash
keyhole validate examples/second-governed-app
keyhole governed run --repo-dir examples/second-governed-app --json
keyhole governed status --repo-dir examples/second-governed-app --last --json
keyhole governed receipt --repo-dir examples/second-governed-app --last --json
```

The final receipt must include `governed=true`, `event_spine_evidence=true`,
`governance_verdict`, `drift_state`, `governance_context_id`, and an
`mcp_event_id` or event pointer. Secret values are never printed.

On Windows, verify that `keyhole` resolves to the active virtual environment
instead of an older global launcher:

```powershell
Get-Command keyhole -All
where.exe keyhole
keyhole version
python -m pip show keyhole-cli keyhole-sdk PyYAML
.\.venv\Scripts\keyhole.exe version
```

---

## Known Limitations

| Limitation | Explanation |
|------------|-------------|
| Proof submission not operational | Scaffolded; awaits DEV-UX-04 |
| Participant contract placeholders | Scaffolded; proof submission awaits DEV-UX-04 |
| Verdict retrieval not operational | Scaffolded; awaits DEV-UX-06 |
| Recursive demo handoff scaffolded | Participant side ready; platform side pending |
| Windows native not tested | Use WSL2 |
| No async SDK client | `AsyncKeyholeClient` is a placeholder (sync wrapper) |

---

## Network Requirements

| Scenario | Network Access Needed |
|----------|----------------------|
| Local-only development | None (all local Docker) |
| Governed mode | Outbound HTTPS to MCP boundary |
| PyPI installation | Outbound HTTPS to pypi.org |
| Docker image pull | Outbound HTTPS to ghcr.io |

---

## Quick Compatibility Check

Run this to verify your environment is ready:

```bash
python --version          # Must be 3.9+
docker --version          # Must be 20.10+
docker compose version    # Must be v2+
pip install -e packages/python/keyhole-sdk
python -c "import keyhole_sdk; print(f'SDK {keyhole_sdk.__version__} ready')"
```

Expected output:

```
Python 3.12.x
Docker version 2x.x.x
Docker Compose version v2.x.x
SDK 0.4.1 ready
```
