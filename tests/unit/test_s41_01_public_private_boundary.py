"""§13.5 — Public/Private Boundary Closure Tests.

Verifies that no governed public surface file contains private
platform references (cluster namespaces, internal APIs, credentials,
internal topology, etc.).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from developer_surface_contract.invariants import INV_PUBLIC_PRIVATE_BOUNDARY_CLOSED, Verdict
from developer_surface_contract.validate import check_no_private_leakage, load_inventory


class TestPublicPrivateBoundary:
    """Public surface files must not leak private platform internals."""

    def test_boundary_check_accepts(self, repo_root: Path) -> None:
        result = check_no_private_leakage(repo_root)
        assert result.passed, (
            f"Private leakage detected:\n" + "\n".join(f"  - {r}" for r in result.reasons)
        )
        assert result.invariant_id == INV_PUBLIC_PRIVATE_BOUNDARY_CLOSED

    def test_no_cluster_namespace_refs(self, repo_root: Path) -> None:
        """No public file should reference keyhole-system, keyhole-storage, etc."""
        inv = load_inventory(repo_root)
        cluster_refs = inv["forbidden_patterns"]["private_cluster_refs"]
        for surface_name, surface in inv["surfaces"].items():
            if surface_name == "governance":
                continue
            for rel_path in surface["paths"]:
                full = repo_root / rel_path
                if not full.exists():
                    continue
                content = full.read_text(encoding="utf-8")
                for ref in cluster_refs:
                    assert not re.search(
                        re.escape(ref), content
                    ), f"{rel_path} contains cluster ref '{ref}'"

    def test_no_private_api_refs(self, repo_root: Path) -> None:
        """No public file should reference internal MCP API paths (unless exempt)."""
        inv = load_inventory(repo_root)
        api_refs = inv["forbidden_patterns"]["private_api_refs"]
        # Build exemption set for private_api_refs
        exempt_paths: set[str] = set()
        for ex in inv.get("forbidden_pattern_exemptions", []):
            if "private_api_refs" in ex.get("categories", []):
                exempt_paths.add(ex["path"])
        for surface_name, surface in inv["surfaces"].items():
            if surface_name == "governance":
                continue
            for rel_path in surface["paths"]:
                if rel_path in exempt_paths:
                    continue
                full = repo_root / rel_path
                if not full.exists():
                    continue
                content = full.read_text(encoding="utf-8")
                for ref in api_refs:
                    assert not re.search(
                        re.escape(ref), content
                    ), f"{rel_path} contains private API ref '{ref}'"

    def test_no_credential_refs(self, repo_root: Path) -> None:
        """No public file should reference credentials or tokens."""
        inv = load_inventory(repo_root)
        cred_refs = inv["forbidden_patterns"]["credentials"]
        for surface_name, surface in inv["surfaces"].items():
            if surface_name == "governance":
                continue
            for rel_path in surface["paths"]:
                full = repo_root / rel_path
                if not full.exists():
                    continue
                content = full.read_text(encoding="utf-8")
                for ref in cred_refs:
                    assert not re.search(
                        re.escape(ref), content
                    ), f"{rel_path} contains credential ref '{ref}'"

    def test_no_internal_topology_refs(self, repo_root: Path) -> None:
        """No public file should reference internal topology."""
        inv = load_inventory(repo_root)
        topo_refs = inv["forbidden_patterns"]["internal_topology"]
        for surface_name, surface in inv["surfaces"].items():
            if surface_name == "governance":
                continue
            for rel_path in surface["paths"]:
                full = repo_root / rel_path
                if not full.exists():
                    continue
                content = full.read_text(encoding="utf-8")
                for ref in topo_refs:
                    assert not re.search(
                        re.escape(ref), content
                    ), f"{rel_path} contains internal topology ref '{ref}'"
