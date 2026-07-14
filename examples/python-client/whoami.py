"""Keyhole SDK - WhoAmI example.

CE-V5-S41-05 section17: Executable Example Discipline.
Canonical example class: whoami.

Usage:
    python whoami.py [BASE_URL]
"""

from __future__ import annotations

import json
import sys

from keyhole_sdk import KeyholeClient, KeyholeConfig, TransportError


def main(base_url: str = "http://localhost:8080") -> None:
    config = KeyholeConfig(base_url=base_url)
    with KeyholeClient.from_config(config) as client:
        identity = client.get_identity()
        print("== WhoAmI ==")
        print(f"  ID:           {identity.runtime_id}")
        print(f"  Name:         {identity.runtime_name}")
        print(f"  Version:      {identity.runtime_version}")
        print(f"  Environment:  {identity.environment}")
        print(f"  Capabilities: {identity.capabilities}")
        print()
        print("== JSON ==")
        print(json.dumps(identity.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    try:
        main(url)
    except TransportError as exc:
        print(f"NO Cannot reach runtime: {exc}", file=sys.stderr)
        sys.exit(1)
