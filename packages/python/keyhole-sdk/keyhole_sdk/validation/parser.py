"""Safe YAML/JSON parsing for governance contract validation — SDK-CLIENT-04.

§8.3: Parse YAML or JSON safely and deterministically.
      Reject invalid syntax, report exact file/field path, distinguish
      missing vs malformed vs empty.

PyYAML is a declared SDK dependency. We still lazy-import it so direct source
checkout failures produce a clear install instruction instead of a traceback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from keyhole_sdk.validation.models import ValidationIssue


def _try_import_yaml() -> Any:
    """Lazy import of pyyaml — returns the yaml module or None."""
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml
    except ImportError:
        return None


def load_yaml_safe(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """§8.3 — Load a YAML file safely.

    Returns ``(data, None)`` on success, or ``(None, error_message)`` on failure.

    Distinguishes:
    - File not found
    - YAML parse error
    - Non-mapping top level (list, scalar)
    - Empty file (treated as empty dict, not an error)
    - pyyaml unavailable
    """
    if not path.exists():
        return None, f"File not found: {path.name}"

    yaml = _try_import_yaml()
    if yaml is None:
        # Fall back to JSON if file is .json; otherwise error
        if path.suffix == ".json":
            return _load_json_safe(path)
        return None, (
            f"Cannot parse {path.name}: pyyaml is not installed. "
            "Install with: pip install pyyaml"
        )

    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return {}, None  # Empty file → empty dict, not an error

        data = yaml.safe_load(content)

        if data is None:
            return {}, None  # YAML null / blank → empty

        if not isinstance(data, dict):
            return None, (
                f"Expected a YAML mapping at top level of {path.name}, "
                f"got {type(data).__name__}. Ensure the file is a key-value document."
            )

        return data, None

    except Exception as exc:  # noqa: BLE001
        return None, f"YAML parse error in {path.name}: {exc}"


def _load_json_safe(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Load a JSON file safely for foreign manifest inspection."""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data, None
        return None, f"Expected a JSON object in {path.name}"
    except Exception as exc:  # noqa: BLE001
        return None, f"JSON parse error in {path.name}: {exc}"


def parse_dependencies_list(
    data: Dict[str, Any],
    file_label: str,
) -> Tuple[List[Dict[str, Any]], List[ValidationIssue]]:
    """§8.5 — Extract and sanity-check the dependencies list from parsed YAML.

    Returns ``(raw_deps, issues)`` where ``raw_deps`` is the list of dependency
    dicts even if some are malformed, and ``issues`` describes structural problems.
    """
    issues: List[ValidationIssue] = []
    deps_raw = data.get("dependencies")

    if deps_raw is None:
        return [], []  # Missing key is acceptable (optional file)

    if not isinstance(deps_raw, list):
        issues.append(ValidationIssue(
            file=file_label,
            field="dependencies",
            reason="dependencies_must_be_list",
            repair=[
                f"The 'dependencies' key in {file_label} must be a YAML list.",
                "Example:\n  dependencies:\n    - capability: payment.stripe.integration.v1\n      provider: stripe-adapter",
            ],
        ))
        return [], issues

    raw_entries: List[Dict[str, Any]] = []
    for idx, item in enumerate(deps_raw):
        if not isinstance(item, dict):
            issues.append(ValidationIssue(
                file=file_label,
                field=f"dependencies[{idx}]",
                reason="dependency_must_be_mapping",
                repair=[
                    f"dependencies[{idx}] must be a YAML mapping with at least a 'capability' key.",
                ],
            ))
        else:
            raw_entries.append(item)

    return raw_entries, issues
