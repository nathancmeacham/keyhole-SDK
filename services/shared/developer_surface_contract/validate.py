"""S41-01 Validation Module.

Implements contract validation checks for the public developer surface.
Each function checks one or more invariants against the repo state.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from .invariants import (
    INV_CLI_SDK_RUNTIME_ALIGNED,
    INV_DOCS_EXAMPLES_TRUTHFUL,
    INV_MODE_TRUTHFULNESS,
    INV_PUBLIC_PRIVATE_BOUNDARY_CLOSED,
    INV_PUBLIC_SURFACE_CONTRACT_CLOSED,
    INV_PUBLISH_COMPATIBILITY_CLOSED,
    INVARIANT_NAMES,
    InvariantResult,
    Verdict,
)


def _repo_root() -> Path:
    """Walk up from this file to find the repo root (contains README.md)."""
    p = Path(__file__).resolve()
    for ancestor in [p] + list(p.parents):
        if (ancestor / "README.md").exists() and (ancestor / "docker-compose.yml").exists():
            return ancestor
    raise RuntimeError("Cannot locate repo root")


def load_inventory(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load the public surface inventory YAML."""
    root = repo_root or _repo_root()
    inventory_path = root / "docs" / "specs" / "developer_ecosystem" / "public_surface_inventory.yaml"
    with open(inventory_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── INV-01: Public Surface Contract Closed ──────────────────────────────────


def check_inventory_complete(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify that all declared public surface paths exist on disk."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    for surface_name, surface in inv.get("surfaces", {}).items():
        for path_str in surface.get("paths", []):
            full = root / path_str
            if not full.exists():
                reasons.append(f"[{surface_name}] missing: {path_str}")

    return InvariantResult(
        invariant_id=INV_PUBLIC_SURFACE_CONTRACT_CLOSED,
        name=INVARIANT_NAMES[INV_PUBLIC_SURFACE_CONTRACT_CLOSED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


def check_contract_spec_exists(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify that the public surface contract spec exists."""
    root = repo_root or _repo_root()
    reasons: List[str] = []
    spec = root / "docs" / "specs" / "developer_ecosystem" / "public_surface_contract.md"
    if not spec.exists():
        reasons.append("Public surface contract spec not found")
    inv_file = root / "docs" / "specs" / "developer_ecosystem" / "public_surface_inventory.yaml"
    if not inv_file.exists():
        reasons.append("Public surface inventory not found")

    return InvariantResult(
        invariant_id=INV_PUBLIC_SURFACE_CONTRACT_CLOSED,
        name=INVARIANT_NAMES[INV_PUBLIC_SURFACE_CONTRACT_CLOSED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


# ── INV-03: CLI/SDK/Runtime Aligned ─────────────────────────────────────────


def check_sdk_models_match_contract(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify SDK Pydantic models declare exactly the contract fields."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    sdk_models_path = root / "packages" / "python" / "keyhole-sdk" / "keyhole_sdk" / "models.py"
    if not sdk_models_path.exists():
        return InvariantResult(
            invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
            name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
            verdict=Verdict.REJECT,
            reasons=["SDK models.py not found"],
        )

    content = sdk_models_path.read_text(encoding="utf-8")
    contract = inv.get("runtime_contract", {})

    # Check identity fields
    for field_name in contract.get("identity_fields", []):
        if field_name not in content:
            reasons.append(f"SDK RuntimeIdentity missing field: {field_name}")

    # Check receipt fields
    for field_name in contract.get("receipt_fields", []):
        if field_name not in content:
            reasons.append(f"SDK RealizationReceipt missing field: {field_name}")

    # Check forbidden fields not present
    forbidden = inv.get("forbidden_response_fields", {})
    for field_name in forbidden.get("identity", []):
        # Look for field declaration pattern (not just mention in comments)
        pattern = rf"^\s+{field_name}\s*[:=]"
        if re.search(pattern, content, re.MULTILINE):
            reasons.append(f"SDK RuntimeIdentity has forbidden field: {field_name}")
    for field_name in forbidden.get("receipt", []):
        pattern = rf"^\s+{field_name}\s*[:=]"
        if re.search(pattern, content, re.MULTILINE):
            reasons.append(f"SDK RealizationReceipt has forbidden field: {field_name}")

    return InvariantResult(
        invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
        name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


def check_runtime_models_match_contract(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify runtime Pydantic models declare exactly the contract fields."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    models_path = root / "services" / "test-runtime" / "app" / "models.py"
    if not models_path.exists():
        return InvariantResult(
            invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
            name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
            verdict=Verdict.REJECT,
            reasons=["Runtime models.py not found"],
        )

    content = models_path.read_text(encoding="utf-8")

    # Check identity fields exist
    contract = inv.get("runtime_contract", {})
    for field_name in contract.get("identity_fields", []):
        if field_name not in content:
            reasons.append(f"Runtime IdentityResponse missing field: {field_name}")

    # Check receipt fields exist
    for field_name in contract.get("receipt_fields", []):
        if field_name not in content:
            reasons.append(f"Runtime RealizationReceipt missing field: {field_name}")

    # Check forbidden
    forbidden = inv.get("forbidden_response_fields", {})
    for field_name in forbidden.get("identity", []):
        pattern = rf"^\s+{field_name}\s*[:=]"
        if re.search(pattern, content, re.MULTILINE):
            reasons.append(f"Runtime IdentityResponse has forbidden field: {field_name}")
    for field_name in forbidden.get("receipt", []):
        pattern = rf"^\s+{field_name}\s*[:=]"
        if re.search(pattern, content, re.MULTILINE):
            reasons.append(f"Runtime RealizationReceipt has forbidden field: {field_name}")

    return InvariantResult(
        invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
        name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


def check_openapi_matches_contract(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify OpenAPI schema fields match the declared contract."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    openapi_path = root / "openapi" / "test-runtime.openapi.yaml"
    if not openapi_path.exists():
        return InvariantResult(
            invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
            name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
            verdict=Verdict.REJECT,
            reasons=["OpenAPI spec not found"],
        )

    spec = yaml.safe_load(openapi_path.read_text(encoding="utf-8"))
    schemas = spec.get("components", {}).get("schemas", {})
    contract = inv.get("runtime_contract", {})

    # Check IdentityResponse
    identity_schema = schemas.get("IdentityResponse", {})
    identity_props = set(identity_schema.get("properties", {}).keys())
    expected_identity = set(contract.get("identity_fields", []))
    if identity_props != expected_identity:
        extra = identity_props - expected_identity
        missing = expected_identity - identity_props
        if extra:
            reasons.append(f"OpenAPI IdentityResponse has extra fields: {extra}")
        if missing:
            reasons.append(f"OpenAPI IdentityResponse missing fields: {missing}")

    # Check RealizationReceipt
    receipt_schema = schemas.get("RealizationReceipt", {})
    receipt_props = set(receipt_schema.get("properties", {}).keys())
    expected_receipt = set(contract.get("receipt_fields", []))
    if receipt_props != expected_receipt:
        extra = receipt_props - expected_receipt
        missing = expected_receipt - receipt_props
        if extra:
            reasons.append(f"OpenAPI RealizationReceipt has extra fields: {extra}")
        if missing:
            reasons.append(f"OpenAPI RealizationReceipt missing fields: {missing}")

    return InvariantResult(
        invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
        name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


def check_json_schema_matches_contract(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify JSON schema receipt fields match the declared contract."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    receipt_schema_path = root / "schemas" / "runtime_realization_receipt.v1.schema.json"
    if not receipt_schema_path.exists():
        return InvariantResult(
            invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
            name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
            verdict=Verdict.REJECT,
            reasons=["Receipt JSON schema not found"],
        )

    with open(receipt_schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    schema_props = set(schema.get("properties", {}).keys())
    expected = set(inv.get("runtime_contract", {}).get("receipt_fields", []))
    if schema_props != expected:
        extra = schema_props - expected
        missing = expected - schema_props
        if extra:
            reasons.append(f"JSON schema has extra fields: {extra}")
        if missing:
            reasons.append(f"JSON schema missing fields: {missing}")

    return InvariantResult(
        invariant_id=INV_CLI_SDK_RUNTIME_ALIGNED,
        name=INVARIANT_NAMES[INV_CLI_SDK_RUNTIME_ALIGNED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


# ── INV-04: Docs/Examples Truthful ──────────────────────────────────────────


def check_docs_no_forbidden_response_fields(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify docs and examples don't reference forbidden response fields in JSON blocks."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    forbidden = inv.get("forbidden_response_fields", {})
    all_forbidden: Set[str] = set()
    for fields in forbidden.values():
        all_forbidden.update(fields)

    # Scan docs and examples
    doc_paths = (
        inv.get("surfaces", {}).get("docs", {}).get("paths", [])
        + inv.get("surfaces", {}).get("examples", {}).get("paths", [])
    )

    for rel_path in doc_paths:
        full = root / rel_path
        if not full.exists() or not full.suffix == ".md":
            continue
        content = full.read_text(encoding="utf-8")
        for field_name in all_forbidden:
            # Match JSON-style field references: "field_name": or "field_name" :
            pattern = rf'"\s*{re.escape(field_name)}\s*"\s*:'
            matches = list(re.finditer(pattern, content))
            if matches:
                for m in matches:
                    line_no = content[:m.start()].count("\n") + 1
                    reasons.append(
                        f"{rel_path}:{line_no} — forbidden field "
                        f'"{field_name}" in example response'
                    )

    return InvariantResult(
        invariant_id=INV_DOCS_EXAMPLES_TRUTHFUL,
        name=INVARIANT_NAMES[INV_DOCS_EXAMPLES_TRUTHFUL],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


# ── INV-05: Mode Truthfulness ───────────────────────────────────────────────


def check_mode_truthfulness(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify local-only docs don't claim governed evidence."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    forbidden_claims = inv.get("mode_truth", {}).get("local_only_forbidden_claims", [])

    # Only check docs that default to local-only context
    local_only_docs = [
        "README.md",
        "docs/quickstart.md",
        "examples/bridge-smoke-test/README.md",
        "examples/python-client/README.md",
    ]

    negation_keywords = [
        "not", "no ", "without", "does not", "governed mode",
        "governed)", "when configured", "may not", "must not",
        "do not", "cannot", "warning", "note:",
    ]

    for rel_path in local_only_docs:
        full = root / rel_path
        if not full.exists():
            continue
        content = full.read_text(encoding="utf-8")
        lines = content.split("\n")
        for claim in forbidden_claims:
            for i, line in enumerate(lines, 1):
                if claim not in line:
                    continue
                # Check a 3-line window (prev, current, next) for negation context
                window_start = max(0, i - 2)
                window_end = min(len(lines), i + 1)
                window_text = " ".join(lines[window_start:window_end]).lower()
                if any(kw in window_text for kw in negation_keywords):
                    continue
                reasons.append(
                    f"{rel_path}:{i} — local-only doc claims "
                    f'"{claim}" without governed context'
                )

    return InvariantResult(
        invariant_id=INV_MODE_TRUTHFULNESS,
        name=INVARIANT_NAMES[INV_MODE_TRUTHFULNESS],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


# ── INV-06: Public/Private Boundary Closed ──────────────────────────────────


def check_no_private_leakage(repo_root: Optional[Path] = None) -> InvariantResult:
    """Verify public surface files don't contain private platform references."""
    root = repo_root or _repo_root()
    inv = load_inventory(root)
    reasons: List[str] = []

    forbidden_patterns = inv.get("forbidden_patterns", {})

    # Build exemption map: path -> set of exempt categories
    exemptions: Dict[str, Set[str]] = {}
    for ex in inv.get("forbidden_pattern_exemptions", []):
        exemptions[ex["path"]] = set(ex.get("categories", []))

    # Scan all governed public surface files
    for surface_name, surface in inv.get("surfaces", {}).items():
        # Skip the governance surface itself (it legitimately references patterns)
        if surface_name == "governance":
            continue
        for rel_path in surface.get("paths", []):
            full = root / rel_path
            if not full.exists():
                continue
            content = full.read_text(encoding="utf-8")
            path_exempt = exemptions.get(rel_path, set())
            for category, patterns in forbidden_patterns.items():
                if category in path_exempt:
                    continue
                for pattern in patterns:
                    if re.search(re.escape(pattern), content):
                        reasons.append(
                            f"[{surface_name}] {rel_path} — forbidden private "
                            f'reference: "{pattern}"'
                        )

    return InvariantResult(
        invariant_id=INV_PUBLIC_PRIVATE_BOUNDARY_CLOSED,
        name=INVARIANT_NAMES[INV_PUBLIC_PRIVATE_BOUNDARY_CLOSED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )


# ── INV-07: Publish Compatibility Closed ────────────────────────────────────


def check_version_alignment(repo_root: Optional[Path] = None) -> InvariantResult:
    """Check that SDK and CLI pyproject.toml versions exist and are parseable."""
    root = repo_root or _repo_root()
    reasons: List[str] = []

    sdk_toml = root / "packages" / "python" / "keyhole-sdk" / "pyproject.toml"
    cli_toml = root / "packages" / "python" / "keyhole-cli" / "pyproject.toml"

    for name, path in [("SDK", sdk_toml), ("CLI", cli_toml)]:
        if not path.exists():
            reasons.append(f"{name} pyproject.toml not found")
            continue
        content = path.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if not match:
            reasons.append(f"{name} pyproject.toml missing version field")

    return InvariantResult(
        invariant_id=INV_PUBLISH_COMPATIBILITY_CLOSED,
        name=INVARIANT_NAMES[INV_PUBLISH_COMPATIBILITY_CLOSED],
        verdict=Verdict.REJECT if reasons else Verdict.ACCEPT,
        reasons=reasons,
    )
