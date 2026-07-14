"""Token refresh helpers — transparent access-token lifecycle management.

Provides ``get_fresh_token()``: read the stored credentials, refresh via the
Keycloak ``refresh_token`` grant if the access token is near-expiry, persist
the updated credentials atomically, and return a valid bearer token.

Designed for long-running SDK consumers (daemons, proxies) that must maintain
a valid token without user interaction.

Rules enforced:
  - No control-plane logic — all final auth decisions belong to the MCP boundary.
  - No caching beyond what is already stored in the credentials file.
  - Atomic write (temp-file rename) to avoid partial-write corruption.
  - Thread-safe: concurrent calls are safe (last writer wins; both values valid).
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests as _http

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_EXPIRY_BUFFER_SECONDS: int = 60   # refresh if token expires within this window
_TOKEN_SUFFIX: str = "/protocol/openid-connect/token"
_DEFAULT_AUTH_SERVER: str = ""
_DEFAULT_CLIENT_ID: str = "keyhole-cli"


# ---------------------------------------------------------------------------
# Credential file helpers
# ---------------------------------------------------------------------------

def _cred_path(keyhole_home: str | Path | None = None) -> Path:
    home = (
        Path(keyhole_home)
        if keyhole_home
        else Path(os.environ.get("KEYHOLE_HOME", str(Path.home() / ".keyhole")))
    )
    return home / "credentials.json"


def _load_creds(keyhole_home: str | Path | None = None) -> dict:
    path = _cred_path(keyhole_home)
    if not path.exists():
        raise FileNotFoundError(
            f"No Keyhole credentials found at {path}. "
            "Run 'keyhole login' to authenticate."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _save_creds(creds: dict, keyhole_home: str | Path | None = None) -> None:
    """Atomically write credentials (temp-rename, preserves 0600 mode)."""
    path = _cred_path(keyhole_home)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# JWT helpers (no verification — only used to inspect expiry)
# ---------------------------------------------------------------------------

def _jwt_exp(token: str) -> Optional[int]:
    """Return the ``exp`` claim from a JWT without verifying the signature."""
    try:
        # JWT structure: header.payload.signature (base64url)
        payload_b64 = token.split(".")[1]
        # Restore base64 padding
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return int(payload["exp"])
    except Exception:
        return None


def _token_is_valid(token: str) -> bool:
    """True if the token has more than _EXPIRY_BUFFER_SECONDS of lifetime left."""
    exp = _jwt_exp(token)
    if exp is None:
        return False
    return time.time() < exp - _EXPIRY_BUFFER_SECONDS


# ---------------------------------------------------------------------------
# Keycloak refresh_token grant
# ---------------------------------------------------------------------------

def _do_refresh(creds: dict) -> dict:
    """Call Keycloak with the ``refresh_token`` grant and update *creds* in-place."""
    auth_server = creds.get("auth_server_url", _DEFAULT_AUTH_SERVER).rstrip("/")
    token_endpoint = auth_server + _TOKEN_SUFFIX
    client_id = os.environ.get("KEYHOLE_CLIENT_ID", _DEFAULT_CLIENT_ID)

    resp = _http.post(
        token_endpoint,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": creds["refresh_token"],
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    now = datetime.now(timezone.utc)
    expires_in: int = data.get("expires_in", 300)

    creds["access_token"] = data["access_token"]
    creds["token_type"] = data.get("token_type", "Bearer")
    creds["expires_at"] = (now + timedelta(seconds=expires_in)).isoformat()
    if "refresh_token" in data:
        # Servers may rotate the refresh token on each use
        creds["refresh_token"] = data["refresh_token"]

    return creds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_fresh_token(keyhole_home: str | Path | None = None) -> str:
    """Return a valid bearer token, refreshing transparently if near-expiry.

    1. Reads ``~/.keyhole/credentials.json`` (or the supplied ``keyhole_home``
       / ``$KEYHOLE_HOME`` credentials file).
    2. If the stored access token has > ``_EXPIRY_BUFFER_SECONDS`` of life left,
       returns it immediately without any network call.
    3. Otherwise uses the stored ``refresh_token`` to obtain a new access token
       from the Keycloak token endpoint, persists the update atomically, and
       returns the new token.

    Raises:
        FileNotFoundError: if no credentials file exists (user must ``keyhole login``).
        RuntimeError: if the token is expired and no ``refresh_token`` is available.
        requests.HTTPError: if the refresh grant call fails (e.g. refresh token
            revoked — user must ``keyhole login`` again).
    """
    creds = _load_creds(keyhole_home)
    access_token: str = creds.get("access_token", "")

    if _token_is_valid(access_token):
        return access_token

    refresh_token: Optional[str] = creds.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "Access token is expired and no refresh_token is available. "
            "Run 'keyhole login' to re-authenticate."
        )

    creds = _do_refresh(creds)
    _save_creds(creds, keyhole_home)
    return creds["access_token"]
