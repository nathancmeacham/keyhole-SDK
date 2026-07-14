"""SDK-CLIENT-23 — Local host attestation storage (§B).

Reads and writes host identity attestation files under
``~/.keyhole/host_attestations/``.

Each host writes one attestation file per logical host binding.
Filename pattern: ``<host_kind>__<integration_name>__<machine_scope>.json``

Rules:
  - attestation files are local workstation facts
  - they are not server truth
  - they are advisory for local bind policy
  - freshness is TTL-based (10-minute default for confirmed)
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import List, Optional

from keyhole_sdk.doctor.models import (
    HostIdentityAttestation,
    IdentityPolicyOverride,
)

_FILE_PERMISSIONS = stat.S_IRUSR | stat.S_IWUSR  # 0600
_DIR_PERMISSIONS = stat.S_IRWXU  # 0700
_ATTESTATION_SUBDIR = "host_attestations"
_IDENTITY_POLICY_FILE = "identity_policy.json"
_PRINCIPAL_HINT_FILE = "principal_hint.json"


def _chmod_open_file(fd: int, path: str, mode: int) -> None:
    """Apply restrictive permissions to an open file on POSIX and Windows."""
    if hasattr(os, "fchmod"):
        os.fchmod(fd, mode)
    else:
        os.chmod(path, mode)


def _close_fd(fd: int) -> None:
    with suppress(OSError):
        os.close(fd)


def _resolve_keyhole_home() -> Path:
    """Resolve the Keyhole state root, respecting KEYHOLE_HOME."""
    keyhole_home = os.environ.get("KEYHOLE_HOME")
    if keyhole_home:
        return Path(keyhole_home)
    return Path.home() / ".keyhole"


def _attestation_dir(keyhole_home: Optional[Path] = None) -> Path:
    """Return the attestation directory path."""
    base = keyhole_home or _resolve_keyhole_home()
    return base / _ATTESTATION_SUBDIR


def _attestation_filename(attestation: HostIdentityAttestation) -> str:
    """Build canonical filename for an attestation."""
    host_kind = attestation.host_kind or "unknown"
    integration = attestation.integration_name or "keyhole"
    scope = attestation.machine_scope or "default"
    # Sanitise components for filesystem safety
    safe = lambda s: s.replace("/", "_").replace("\\", "_").replace("..", "_")
    return f"{safe(host_kind)}__{safe(integration)}__{safe(scope)}.json"


def write_attestation(
    attestation: HostIdentityAttestation,
    *,
    keyhole_home: Optional[Path] = None,
) -> Path:
    """Atomically write an attestation file. Returns the written path."""
    dest_dir = _attestation_dir(keyhole_home)
    dest_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(dest_dir, _DIR_PERMISSIONS)

    filename = _attestation_filename(attestation)
    dest_path = dest_dir / filename

    data = json.dumps(attestation.to_dict(), indent=2, sort_keys=False)

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dest_dir), prefix=".attest_", suffix=".tmp"
    )
    try:
        os.write(fd, data.encode("utf-8"))
        _chmod_open_file(fd, tmp_path, _FILE_PERMISSIONS)
        _close_fd(fd)
        os.replace(tmp_path, str(dest_path))
        os.chmod(dest_path, _FILE_PERMISSIONS)
    except BaseException:
        _close_fd(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return dest_path


def load_attestations(
    *,
    keyhole_home: Optional[Path] = None,
) -> List[HostIdentityAttestation]:
    """Load all valid attestation files. Skips malformed entries."""
    dest_dir = _attestation_dir(keyhole_home)
    if not dest_dir.is_dir():
        return []

    results: List[HostIdentityAttestation] = []
    for entry in sorted(dest_dir.iterdir()):
        if not entry.is_file() or not entry.name.endswith(".json"):
            continue
        try:
            raw = json.loads(entry.read_text(encoding="utf-8"))
            results.append(HostIdentityAttestation(**raw))
        except Exception:
            # Skip malformed attestation files
            continue
    return results


def load_identity_policy(
    *,
    keyhole_home: Optional[Path] = None,
) -> Optional[IdentityPolicyOverride]:
    """Load the local identity policy override, if it exists."""
    base = keyhole_home or _resolve_keyhole_home()
    policy_path = base / _IDENTITY_POLICY_FILE
    if not policy_path.is_file():
        return None
    try:
        raw = json.loads(policy_path.read_text(encoding="utf-8"))
        return IdentityPolicyOverride(**raw)
    except Exception:
        return None


def save_identity_policy(
    override: IdentityPolicyOverride,
    *,
    keyhole_home: Optional[Path] = None,
) -> Path:
    """Atomically write the identity policy override. Returns the path."""
    base = keyhole_home or _resolve_keyhole_home()
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, _DIR_PERMISSIONS)

    dest_path = base / _IDENTITY_POLICY_FILE
    data = json.dumps(override.to_dict(), indent=2, sort_keys=False)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(base), prefix=".policy_", suffix=".tmp"
    )
    try:
        os.write(fd, data.encode("utf-8"))
        _chmod_open_file(fd, tmp_path, _FILE_PERMISSIONS)
        _close_fd(fd)
        os.replace(tmp_path, str(dest_path))
        os.chmod(dest_path, _FILE_PERMISSIONS)
    except BaseException:
        _close_fd(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return dest_path


def clear_identity_policy(
    *,
    keyhole_home: Optional[Path] = None,
) -> bool:
    """Remove the identity policy override file. Returns True if removed."""
    base = keyhole_home or _resolve_keyhole_home()
    policy_path = base / _IDENTITY_POLICY_FILE
    if policy_path.is_file():
        policy_path.unlink()
        return True
    return False


def save_principal_hint(
    *,
    principal: str,
    user_id: str = "",
    realm: str = "",
    keyhole_home: Optional[Path] = None,
) -> None:
    """Save the CLI's known principal after a successful login/whoami.

    This is purely advisory — used by doctor to show the CLI identity
    in the coherence report without decoding JWT tokens.
    """
    base = keyhole_home or _resolve_keyhole_home()
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, _DIR_PERMISSIONS)

    hint_path = base / _PRINCIPAL_HINT_FILE
    data = json.dumps(
        {"principal": principal, "user_id": user_id, "realm": realm},
        indent=2,
    )
    fd, tmp_path = tempfile.mkstemp(
        dir=str(base), prefix=".hint_", suffix=".tmp"
    )
    try:
        os.write(fd, data.encode("utf-8"))
        _chmod_open_file(fd, tmp_path, _FILE_PERMISSIONS)
        _close_fd(fd)
        os.replace(tmp_path, str(hint_path))
        os.chmod(hint_path, _FILE_PERMISSIONS)
    except BaseException:
        _close_fd(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_principal_hint(
    *,
    keyhole_home: Optional[Path] = None,
) -> str:
    """Load the last known CLI principal. Returns empty string if unknown."""
    base = keyhole_home or _resolve_keyhole_home()
    hint_path = base / _PRINCIPAL_HINT_FILE
    if not hint_path.is_file():
        return ""
    try:
        raw = json.loads(hint_path.read_text(encoding="utf-8"))
        return raw.get("principal", "")
    except Exception:
        return ""
