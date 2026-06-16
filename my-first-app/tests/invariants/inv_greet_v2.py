"""MY-FIRST-APP-INV-02 — GREET-USER-V2-CAPABILITY-SHAPE-STABLE

Anti-regression gate for my-first-app.greet.user.v2.

This gate is a LOCAL invariant: it runs inside this repo's CI / keyhole
gate runner and does NOT require MCP connectivity.

A Keyhole governed promotion may not advance past this gate unless
verdict == ACCEPT.

Rule
----
The greet_v2() function must return an object that:

  1. has attribute ``greeting`` of type str and non-empty
  2. has attribute ``name`` of type str and non-empty
  3. has attribute ``defaulted`` of type bool
  4. has attribute ``capability`` == "my-first-app.greet.user.v2"
  5. greeting contains the value of name
  6. passing None or blank string defaults name to "World" and defaulted=True
  7. passing a non-blank name preserves it and defaulted=False
  8. response is immutable (frozen dataclass)

Any regression in items 1-8 must produce verdict REJECT and block promotion.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from greet import GreetV2Response, greet_v2  # noqa: E402


INVARIANT_ID = "MY-FIRST-APP-INV-02"
INVARIANT_NAME = "GREET-USER-V2-CAPABILITY-SHAPE-STABLE"
CAPABILITY = "my-first-app.greet.user.v2"


class Verdict(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass
class CheckResult:
    check: str
    verdict: Verdict
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.ACCEPT


@dataclass
class InvariantResult:
    invariant_id: str = INVARIANT_ID
    invariant_name: str = INVARIANT_NAME
    capability: str = CAPABILITY
    verdict: Verdict = Verdict.ACCEPT
    checks: List[CheckResult] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.ACCEPT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "invariant_name": self.invariant_name,
            "capability": self.capability,
            "verdict": self.verdict.value,
            "timestamp": self.timestamp,
            "checks_total": len(self.checks),
            "checks_passed": sum(1 for c in self.checks if c.passed),
            "checks_failed": sum(1 for c in self.checks if not c.passed),
            "checks": [asdict(c) for c in self.checks],
        }


def _check_has_greeting_str(resp: GreetV2Response) -> CheckResult:
    ok = isinstance(getattr(resp, "greeting", None), str) and bool(resp.greeting)
    return CheckResult(
        check="has_greeting_str",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"greeting={resp.greeting!r}",
    )


def _check_has_name_str(resp: GreetV2Response) -> CheckResult:
    ok = isinstance(getattr(resp, "name", None), str) and bool(resp.name)
    return CheckResult(
        check="has_name_str",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"name={resp.name!r}",
    )


def _check_has_defaulted_bool(resp: GreetV2Response) -> CheckResult:
    ok = isinstance(getattr(resp, "defaulted", None), bool)
    return CheckResult(
        check="has_defaulted_bool",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"defaulted={resp.defaulted!r}",
    )


def _check_capability_field(resp: GreetV2Response) -> CheckResult:
    ok = getattr(resp, "capability", None) == CAPABILITY
    return CheckResult(
        check="capability_field_correct",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"capability={resp.capability!r}",
    )


def _check_name_in_greeting(resp: GreetV2Response) -> CheckResult:
    ok = resp.name in resp.greeting
    return CheckResult(
        check="name_in_greeting",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"name={resp.name!r} not in greeting={resp.greeting!r}",
    )


def _check_defaulted_response(resp: GreetV2Response) -> CheckResult:
    ok = resp.name == "World" and resp.defaulted is True
    return CheckResult(
        check="defaulted_response",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"name={resp.name!r}, defaulted={resp.defaulted!r}",
    )


def _check_supplied_response(resp: GreetV2Response) -> CheckResult:
    ok = resp.name == "Alice" and resp.defaulted is False
    return CheckResult(
        check="supplied_response",
        verdict=Verdict.ACCEPT if ok else Verdict.REJECT,
        detail="" if ok else f"name={resp.name!r}, defaulted={resp.defaulted!r}",
    )


def _check_immutable(resp: GreetV2Response) -> CheckResult:
    try:
        resp.greeting = "mutated"  # type: ignore[misc]
        return CheckResult(
            check="response_immutable",
            verdict=Verdict.REJECT,
            detail="mutation succeeded; response must be frozen",
        )
    except (AttributeError, TypeError):
        return CheckResult(check="response_immutable", verdict=Verdict.ACCEPT)


def run_gate() -> InvariantResult:
    """Execute all checks and return the aggregate InvariantResult."""
    resp_named = greet_v2("Alice")
    resp_default = greet_v2(None)
    resp_blank = greet_v2("   ")

    raw_checks: List[CheckResult] = [
        _check_has_greeting_str(resp_named),
        _check_has_name_str(resp_named),
        _check_has_defaulted_bool(resp_named),
        _check_capability_field(resp_named),
        _check_name_in_greeting(resp_named),
        _check_defaulted_response(resp_default),
        _check_defaulted_response(resp_blank),
        _check_supplied_response(resp_named),
        _check_immutable(resp_named),
    ]

    any_fail = any(not c.passed for c in raw_checks)
    return InvariantResult(
        verdict=Verdict.REJECT if any_fail else Verdict.ACCEPT,
        checks=raw_checks,
    )


if __name__ == "__main__":
    import json

    result = run_gate()
    print(json.dumps(result.to_dict(), indent=2))
    sys.exit(0 if result.passed else 1)
