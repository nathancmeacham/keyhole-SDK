"""Keyhole SDK - Submit Declaration example.

CE-V5-S41-05 section17: Executable Example Discipline.
Canonical example class: submit declaration.

Usage:
    python submit_declaration.py [BASE_URL]
"""

from __future__ import annotations

import json
import sys

from keyhole_sdk import (
    KeyholeClient,
    KeyholeConfig,
    PublicEndpointError,
    SchemaError,
    TransportError,
)


def main(base_url: str = "http://localhost:8080") -> None:
    config = KeyholeConfig(base_url=base_url)
    with KeyholeClient.from_config(config) as client:
        print("== Submit Declaration ==")
        try:
            receipt = client.declarations.submit(
                candidate_digest="sha256:example-declaration",
                payload={"source": "submit_declaration.py", "intent": "example"},
            )
            print(f"  Digest:      {receipt.digest}")
            print(f"  Status:      {receipt.status}")
            print(f"  Message:     {receipt.message}")
            print(f"  Realized at: {receipt.realized_at}")
        except PublicEndpointError as exc:
            print(f"  Server rejected: {exc} (status={exc.status_code})")
        except SchemaError as exc:
            print(f"  Schema error: {exc}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    try:
        main(url)
    except TransportError as exc:
        print(f"NO Cannot reach runtime: {exc}", file=sys.stderr)
        sys.exit(1)
