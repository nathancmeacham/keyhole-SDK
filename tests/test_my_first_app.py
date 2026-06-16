from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "my-first-app"
sys.path.insert(0, str(APP / "src"))
sys.path.insert(0, str(APP / "tests" / "invariants"))


def test_greet_response_shape() -> None:
    from greet import greet

    response = greet("Public Developer")

    assert response.name == "Public Developer"
    assert response.greeting == "Hello, Public Developer!"
    assert response.capability == "my-first-app.greet.user.v1"


def test_greet_v2_response_shape() -> None:
    from greet import greet_v2

    response = greet_v2("Public Developer")

    assert response.name == "Public Developer"
    assert response.greeting == "Hello, Public Developer!"
    assert response.defaulted is False
    assert response.capability == "my-first-app.greet.user.v2"


def test_local_invariant_accepts() -> None:
    from inv_greet import Verdict, run_gate

    result = run_gate()

    assert result.verdict == Verdict.ACCEPT


def test_local_v2_invariant_accepts() -> None:
    from inv_greet_v2 import Verdict, run_gate

    result = run_gate()

    assert result.verdict == Verdict.ACCEPT
