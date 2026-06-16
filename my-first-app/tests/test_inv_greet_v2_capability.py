"""pytest wrapper for MY-FIRST-APP-INV-02.

This test is the required_test declared in governance_contract.yaml.
It runs the v2 invariant gate and asserts ACCEPT.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent / "invariants"))
from inv_greet_v2 import Verdict, run_gate  # noqa: E402


def test_inv_greet_v2_verdict_is_accept() -> None:
    """MY-FIRST-APP-INV-02 must return ACCEPT."""
    result = run_gate()
    failed = [c for c in result.checks if not c.passed]
    assert result.verdict == Verdict.ACCEPT, (
        f"INV-02 REJECT: {len(failed)} check(s) failed:\n"
        + "\n".join(f"  {c.check}: {c.detail}" for c in failed)
    )


def test_inv_greet_v2_all_checks_present() -> None:
    """All defined v2 checks must be present in the result."""
    result = run_gate()
    expected = {
        "has_greeting_str",
        "has_name_str",
        "has_defaulted_bool",
        "capability_field_correct",
        "name_in_greeting",
        "defaulted_response",
        "supplied_response",
        "response_immutable",
    }
    found = {c.check for c in result.checks}
    missing = expected - found
    assert not missing, f"Missing checks: {missing}"


def test_inv_greet_v2_named_greeting() -> None:
    """greet_v2('Alice') must preserve the supplied name."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from greet import greet_v2

    resp = greet_v2("Alice")

    assert resp.name == "Alice"
    assert resp.greeting == "Hello, Alice!"
    assert resp.defaulted is False
    assert resp.capability == "my-first-app.greet.user.v2"


def test_inv_greet_v2_default_metadata() -> None:
    """greet_v2(None) and greet_v2('  ') must report defaulted=True."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from greet import greet_v2

    assert greet_v2(None).name == "World"
    assert greet_v2(None).defaulted is True
    assert greet_v2("   ").name == "World"
    assert greet_v2("   ").defaulted is True


def test_inv_greet_v2_response_immutable() -> None:
    """GreetV2Response must be frozen."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from greet import greet_v2

    resp = greet_v2("Bob")
    with pytest.raises((AttributeError, TypeError)):
        resp.defaulted = True  # type: ignore[misc]
