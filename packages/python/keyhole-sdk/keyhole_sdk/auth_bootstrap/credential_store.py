"""Secure local credential store — CLI-owned session persistence.

Implements §9 of SDK-CLIENT-01: Local Credential Store Requirements.

The store:
  - is created automatically
  - does not rely on .env
  - stores minimum necessary token/session metadata
  - is readable by subsequent SDK commands
  - avoids printing secrets to logs/stdout/proof artifacts
  - supports clear invalidation/refresh
  - uses restrictive file permissions (0600)
"""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from keyhole_sdk.auth_bootstrap.errors import CredentialStoreError
from keyhole_sdk.auth_bootstrap.models import AuthSession


def _resolve_default_store_dir() -> Path:
    """Resolve the default store directory, respecting KEYHOLE_HOME if set."""
    keyhole_home = os.environ.get("KEYHOLE_HOME")
    if keyhole_home:
        return Path(keyhole_home)
    return Path.home() / ".keyhole"


_CREDENTIALS_FILE = "credentials.json"
_FILE_PERMISSIONS = stat.S_IRUSR | stat.S_IWUSR  # 0600


class CredentialStore:
    """Secure local credential store for Keyhole authentication sessions.

    Stores credentials in ``credentials.json`` with restrictive file
    permissions (0600).  Never logs or prints token values.

    **Store directory resolution order:**

    1. Explicit ``store_dir`` argument passed to ``__init__`` — wins always.
    2. ``KEYHOLE_HOME`` environment variable — evaluated once at
       construction time so that test fixtures can inject an isolated
       directory before opening the store.
    3. ``~/.keyhole`` — the default.
    """

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or _resolve_default_store_dir()
        self._credentials_path = self._store_dir / _CREDENTIALS_FILE

    @property
    def store_dir(self) -> Path:
        return self._store_dir

    @property
    def credentials_path(self) -> Path:
        return self._credentials_path

    def _ensure_dir(self) -> None:
        """Create the store directory if it doesn't exist."""
        try:
            parent = self._store_dir.parent
            if (
                not self._store_dir.exists()
                and parent.exists()
                and not (parent.stat().st_mode & stat.S_IWUSR)
            ):
                raise OSError(f"Parent directory is not writable: {parent}")
            self._store_dir.mkdir(parents=True, exist_ok=True)
            # Restrict directory permissions
            os.chmod(self._store_dir, stat.S_IRWXU)  # 0700
        except OSError as exc:
            raise CredentialStoreError(
                f"Could not create credential store directory: {exc}"
            ) from exc

    def save(self, session: AuthSession) -> None:
        """Persist an auth session to the local store.

        File is written atomically and permissions are restricted.
        """
        self._ensure_dir()
        try:
            data = session.model_dump(mode="json")
            # Convert datetime objects to ISO strings for JSON
            for key in ("expires_at", "created_at", "last_verified_at"):
                if data.get(key) is not None and isinstance(data[key], datetime):
                    data[key] = data[key].isoformat()

            tmp_path = self._credentials_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
            os.chmod(tmp_path, _FILE_PERMISSIONS)
            tmp_path.replace(self._credentials_path)
        except OSError as exc:
            # Clean up temp file on failure
            tmp_path = self._credentials_path.with_suffix(".tmp")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise CredentialStoreError(
                f"Could not write credentials: {exc}"
            ) from exc

    def load(self) -> Optional[AuthSession]:
        """Load the stored auth session, or None if not present.

        Returns None (not an error) if no credentials exist yet.
        """
        if not self._credentials_path.exists():
            return None
        try:
            data = json.loads(
                self._credentials_path.read_text(encoding="utf-8")
            )
            return AuthSession.model_validate(data)
        except (json.JSONDecodeError, OSError) as exc:
            raise CredentialStoreError(
                f"Could not read credentials: {exc}"
            ) from exc

    def clear(self) -> None:
        """Remove stored credentials."""
        try:
            if self._credentials_path.exists():
                self._credentials_path.unlink()
        except OSError as exc:
            raise CredentialStoreError(
                f"Could not clear credentials: {exc}"
            ) from exc

    def exists(self) -> bool:
        """Check if credentials are stored."""
        return self._credentials_path.exists()

    def is_authenticated(self) -> bool:
        """Check if a valid (non-expired) session exists."""
        session = self.load()
        if session is None:
            return False
        return not session.is_expired
