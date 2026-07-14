"""Keyhole SDK - Get Result example.

CE-V5-S41-05 section17: Executable Example Discipline.
Canonical example class: inspect result.

Usage:
    python get_result.py [BASE_URL]
"""

from __future__ import annotations

import json
import sys

from keyhole_sdk import KeyholeClient, KeyholeConfig, TransportError


def main(base_url: str = "http://localhost:8080") -> None:
    config = KeyholeConfig(base_url=base_url)
    with KeyholeClient.from_config(config) as client:
        state = client.runs.get_state()
        print("== Runtime State ==")
        print(f"  Current digest:   {state.current_digest}")
        print(f"  Realized digests: {state.realized_digests}")
        print(f"  Updated at:       {state.updated_at}")
        print()
        print("== JSON ==")
        print(json.dumps(state.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    try:
        main(url)
    except TransportError as exc:
        print(f"NO Cannot reach runtime: {exc}", file=sys.stderr)
        sys.exit(1)
