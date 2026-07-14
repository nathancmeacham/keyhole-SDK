"""Keyhole SDK - Hello World / Health Check example.

CE-V5-S41-05 section17: Executable Example Discipline.
Canonical example class: hello world / health check.

Usage:
    python hello_world.py [BASE_URL]
"""

from __future__ import annotations

import sys

from keyhole_sdk import KeyholeClient, KeyholeConfig, TransportError


def main(base_url: str = "http://localhost:8080") -> None:
    config = KeyholeConfig(base_url=base_url)
    with KeyholeClient.from_config(config) as client:
        health = client.get_health()
        print(f"OK Keyhole runtime is alive: status={health.status}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    try:
        main(url)
    except TransportError as exc:
        print(f"NO Cannot reach runtime: {exc}", file=sys.stderr)
        print("   Is the runtime running? Try: docker compose up", file=sys.stderr)
        sys.exit(1)
