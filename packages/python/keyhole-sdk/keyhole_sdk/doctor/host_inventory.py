"""SDK-CLIENT-01-D — Pluggable host inventory for MCP host discovery (§11).

Detects local Keyhole-relevant hosts via file/config heuristics.
All detection is advisory — server truth outranks local hints.

Host families supported:
  - VS Code / VS Code-compatible environments
  - JetBrains IDE family
  - Cloud Code or equivalent cloud/dev runtime
  - SDK local credential context
"""
from __future__ import annotations

import json
import os
import platform
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from keyhole_sdk.doctor.models import (
    DoctorHostRecord,
    HostDiagnosis,
    HostFamily,
    HostSupportStatus,
    HostType,
    ReconnectRequirement,
    StalenessState,
)


from keyhole_sdk.config import DEFAULT_BASE_URL

# ── Abstract Detector ────────────────────────────────────


class HostDetector(ABC):
    """Base class for pluggable host detection (§11)."""

    @abstractmethod
    def detect(self) -> Optional[DoctorHostRecord]:
        """Attempt to detect a host. Return None if not found."""


# ── VS Code Detector ─────────────────────────────────────


_VSCODE_SETTINGS_PATHS: List[str] = [
    # Linux desktop
    "~/.config/Code/User/settings.json",
    # Linux VS Code Server (remote SSH)
    "~/.vscode-server/data/User/settings.json",
    # macOS
    "~/Library/Application Support/Code/User/settings.json",
    # VS Code Insiders (Linux)
    "~/.config/Code - Insiders/User/settings.json",
    "~/.vscode-server-insiders/data/User/settings.json",
]

_VSCODE_MCP_PATHS: List[str] = [
    "~/.config/Code/User/globalStorage/mcp.json",
    "~/.vscode-server/data/User/globalStorage/mcp.json",
]

_KEYHOLE_INDICATORS = ("keyhole", DEFAULT_BASE_URL)


class VSCodeHostDetector(HostDetector):
    """Detect VS Code IDE with Keyhole MCP server entry (§11.1)."""

    def detect(self) -> Optional[DoctorHostRecord]:
        record = DoctorHostRecord(
            host_id="vscode",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.VSCODE,
            display_name="Visual Studio Code",
            support_status=HostSupportStatus.SUPPORTED,
            reconnect_requirement=ReconnectRequirement.RELOAD_WINDOW,
        )

        # Check if VS Code is installed
        settings_path = self._find_settings_file()
        if settings_path is None:
            return record  # detected=False by default

        record.detected = True
        record.config_detected = True
        record.config_path = str(settings_path)

        # Look for Keyhole MCP entry in settings
        keyhole_entry = self._find_keyhole_entry(settings_path)
        if keyhole_entry is not None:
            record.keyhole_server_entry_detected = True
            record.server_url = keyhole_entry.get("url", "")
            record.auth_source_mode = self._detect_auth_mode(keyhole_entry)
            record.configured_principal_source = self._detect_principal_source(
                keyhole_entry, settings_path,
            )

        # Check MCP-specific config files
        if not record.keyhole_server_entry_detected:
            mcp_path, mcp_entry = self._check_mcp_config_files()
            if mcp_entry is not None:
                record.keyhole_server_entry_detected = True
                record.server_url = mcp_entry.get("url", "")
                record.config_path = str(mcp_path) if mcp_path else record.config_path
                record.auth_source_mode = self._detect_auth_mode(mcp_entry)
                record.configured_principal_source = self._detect_principal_source(
                    mcp_entry, mcp_path,
                )

        return record

    def _find_settings_file(self) -> Optional[Path]:
        for raw in _VSCODE_SETTINGS_PATHS:
            p = Path(os.path.expanduser(raw))
            if p.is_file():
                return p
        return None

    def _find_keyhole_entry(self, settings_path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # VS Code MCP servers can be under various keys
        for key in ("mcp.servers", "mcpServers", "mcp"):
            servers = data.get(key)
            if isinstance(servers, dict):
                for name, entry in servers.items():
                    if self._is_keyhole_entry(name, entry):
                        return entry if isinstance(entry, dict) else {"name": name}

        return None

    def _check_mcp_config_files(self) -> tuple[Optional[Path], Optional[Dict[str, Any]]]:
        for raw in _VSCODE_MCP_PATHS:
            p = Path(os.path.expanduser(raw))
            if not p.is_file():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, dict):
                servers = data.get("servers", data)
                if isinstance(servers, dict):
                    for name, entry in servers.items():
                        if self._is_keyhole_entry(name, entry):
                            return p, (entry if isinstance(entry, dict) else {"name": name})
        return None, None

    @staticmethod
    def _is_keyhole_entry(name: str, entry: Any) -> bool:
        name_lower = name.lower()
        if any(ind in name_lower for ind in _KEYHOLE_INDICATORS):
            return True
        if isinstance(entry, dict):
            url = str(entry.get("url", "")).lower()
            command = str(entry.get("command", "")).lower()
            if any(ind in url for ind in _KEYHOLE_INDICATORS):
                return True
            if any(ind in command for ind in _KEYHOLE_INDICATORS):
                return True
        return False

    @staticmethod
    def _detect_auth_mode(entry: Dict[str, Any]) -> str:
        """Detect how the MCP entry authenticates.

        Returns a label: 'env_bearer_token', 'header_token', 'oauth_session', or 'unknown'.
        """
        env = entry.get("env", {})
        if isinstance(env, dict):
            for key in env:
                if "token" in key.lower() or "auth" in key.lower():
                    return "env_bearer_token"

        headers = entry.get("headers", {})
        if isinstance(headers, dict):
            for key in headers:
                if "authorization" in key.lower():
                    return "header_token"

        if entry.get("oauth") or entry.get("auth"):
            return "oauth_session"

        return "unknown"

    @staticmethod
    def _detect_principal_source(
        entry: Dict[str, Any],
        config_path: Optional[Path] = None,
    ) -> str:
        """Attempt to extract a principal hint from the config.

        Returns the env var name, a partial descriptor, or empty string.
        """
        env = entry.get("env", {})
        if isinstance(env, dict):
            for key, val in env.items():
                if "token" in key.lower() or "auth" in key.lower():
                    # Value might reference another env var or be a path
                    val_str = str(val)
                    if val_str.startswith("${") or val_str.startswith("$"):
                        return f"env:{val_str}"
                    if "/" in val_str or "\\" in val_str:
                        return f"file:{val_str}"
                    return f"env:{key}"
        return ""


# ── JetBrains Detector ───────────────────────────────────


_JETBRAINS_CONFIG_DIRS: List[str] = [
    # IntelliJ IDEA
    "~/.config/JetBrains/IntelliJIdea*/",
    # PyCharm
    "~/.config/JetBrains/PyCharm*/",
    # WebStorm
    "~/.config/JetBrains/WebStorm*/",
    # GoLand
    "~/.config/JetBrains/GoLand*/",
    # Generic fallback
    "~/.config/JetBrains/*/",
]

_JETBRAINS_MCP_CONFIG_NAME = "mcp.json"


class JetBrainsHostDetector(HostDetector):
    """Detect JetBrains IDE family with Keyhole MCP server entry (SDK-CLIENT-01-D §1)."""

    def detect(self) -> Optional[DoctorHostRecord]:
        record = DoctorHostRecord(
            host_id="jetbrains",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.JETBRAINS,
            display_name="JetBrains IDE",
            support_status=HostSupportStatus.PARTIAL,
            reconnect_requirement=ReconnectRequirement.RESTART_IDE,
        )

        config_dir = self._find_config_dir()
        if config_dir is None:
            return record

        record.detected = True
        record.config_detected = True
        record.config_path = str(config_dir)

        mcp_file = config_dir / _JETBRAINS_MCP_CONFIG_NAME
        if mcp_file.is_file():
            entry = self._find_keyhole_entry(mcp_file)
            if entry is not None:
                record.keyhole_server_entry_detected = True
                record.server_url = entry.get("url", "")

        return record

    def _find_config_dir(self) -> Optional[Path]:
        import glob
        for pattern in _JETBRAINS_CONFIG_DIRS:
            expanded = os.path.expanduser(pattern)
            matches = sorted(glob.glob(expanded), reverse=True)
            for m in matches:
                p = Path(m)
                if p.is_dir():
                    return p
        return None

    @staticmethod
    def _find_keyhole_entry(mcp_file: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(mcp_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if isinstance(data, dict):
            servers = data.get("mcpServers", data.get("servers", data))
            if isinstance(servers, dict):
                for name, entry in servers.items():
                    name_lower = name.lower()
                    if any(ind in name_lower for ind in _KEYHOLE_INDICATORS):
                        return entry if isinstance(entry, dict) else {"name": name}
                    if isinstance(entry, dict):
                        url = str(entry.get("url", "")).lower()
                        if any(ind in url for ind in _KEYHOLE_INDICATORS):
                            return entry
        return None


# ── Cloud Code Detector ──────────────────────────────────


_CLOUD_CODE_CONFIG_PATHS: List[str] = [
    "~/.config/cloud-code/mcp.json",
    "~/.config/google-cloud-tools-java/mcp.json",
]


class CloudCodeHostDetector(HostDetector):
    """Detect Cloud Code or equivalent cloud/dev runtime (SDK-CLIENT-01-D §1)."""

    def detect(self) -> Optional[DoctorHostRecord]:
        record = DoctorHostRecord(
            host_id="cloud_code",
            host_type=HostType.IDE_MCP_CLIENT,
            host_family=HostFamily.CLOUD_CODE,
            display_name="Cloud Code",
            support_status=HostSupportStatus.PARTIAL,
            reconnect_requirement=ReconnectRequirement.MANUAL,
        )

        config_path = self._find_config_file()
        if config_path is None:
            return record

        record.detected = True
        record.config_detected = True
        record.config_path = str(config_path)

        entry = self._find_keyhole_entry(config_path)
        if entry is not None:
            record.keyhole_server_entry_detected = True
            record.server_url = entry.get("url", "")

        return record

    def _find_config_file(self) -> Optional[Path]:
        for raw in _CLOUD_CODE_CONFIG_PATHS:
            p = Path(os.path.expanduser(raw))
            if p.is_file():
                return p
        return None

    @staticmethod
    def _find_keyhole_entry(config_path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if isinstance(data, dict):
            servers = data.get("mcpServers", data.get("servers", data))
            if isinstance(servers, dict):
                for name, entry in servers.items():
                    name_lower = name.lower()
                    if any(ind in name_lower for ind in _KEYHOLE_INDICATORS):
                        return entry if isinstance(entry, dict) else {"name": name}
        return None


# ── SDK Credential Context Detector ──────────────────────


class SDKCredentialDetector(HostDetector):
    """Detect local SDK credential context (§11.1)."""

    def detect(self) -> Optional[DoctorHostRecord]:
        record = DoctorHostRecord(
            host_id="sdk_local",
            host_type=HostType.SDK_RUNTIME,
            host_family=HostFamily.SDK_LOCAL,
            display_name="Keyhole SDK (local credentials)",
            detected=True,
            support_status=HostSupportStatus.SUPPORTED,
            reconnect_requirement=ReconnectRequirement.NONE,
        )

        cred_path = self._find_credential_file()
        if cred_path is not None and cred_path.is_file():
            record.config_detected = True
            record.config_path = str(cred_path)
            record.local_auth_hints_present = True
            record.configured_principal_source = self._extract_principal(cred_path)
        else:
            record.config_detected = False

        return record

    @staticmethod
    def _find_credential_file() -> Optional[Path]:
        home = os.environ.get("KEYHOLE_HOME")
        if home:
            return Path(home) / "credentials.json"
        return Path.home() / ".keyhole" / "credentials.json"

    @staticmethod
    def _extract_principal(cred_path: Path) -> str:
        """Extract the user_id from the credential store if readable."""
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data.get("user_id", "")
        except (json.JSONDecodeError, OSError):
            pass
        return ""


# ── Registry ─────────────────────────────────────────────


_DEFAULT_DETECTORS: List[HostDetector] = [
    VSCodeHostDetector(),
    JetBrainsHostDetector(),
    CloudCodeHostDetector(),
    SDKCredentialDetector(),
]


def detect_hosts(
    *,
    detectors: Optional[List[HostDetector]] = None,
) -> List[DoctorHostRecord]:
    """Run all host detectors and return discovered records (§11).

    Never raises — individual detector failures are caught and
    the host is reported as unsupported rather than crashing the scan.
    """
    active = detectors if detectors is not None else _DEFAULT_DETECTORS
    results: List[DoctorHostRecord] = []

    for detector in active:
        try:
            record = detector.detect()
            if record is not None:
                results.append(record)
        except Exception:
            # §11.3 — no hard failure on unknown hosts
            results.append(
                DoctorHostRecord(
                    host_id=type(detector).__name__,
                    host_type=HostType.UNKNOWN,
                    host_family=HostFamily.UNKNOWN,
                    display_name=f"Unknown ({type(detector).__name__})",
                    detected=False,
                    diagnosis=HostDiagnosis.UNSUPPORTED_HOST,
                    support_status=HostSupportStatus.UNSUPPORTED,
                )
            )

    return results
