"""Keyhole SDK - Get Evidence example.

CE-V5-S41-05 section17: Executable Example Discipline.
Canonical example class: retrieve evidence or outcome ref.

Usage:
    python get_evidence.py [DIGEST] [BASE_URL]
"""

from __future__ import annotations

import json
import sys

from keyhole_sdk import (
    KeyholeClient,
    KeyholeConfig,
    PublicEndpointError,
    TransportError,
)


def main(
    digest: str = "sha256:example",
    base_url: str = "http://localhost:8080",
) -> None:
    config = KeyholeConfig(base_url=base_url)
    with KeyholeClient.from_config(config) as client:
        print(f"== Evidence for {digest} ==")
        try:
            evidence = client.evidence.get_by_digest(digest)
            print(json.dumps(evidence, indent=2, default=str))
        except PublicEndpointError as exc:
            if exc.status_code == 404:
                print(f"  No evidence found for digest: {digest}")
            else:
                print(f"  Server error: {exc} (status={exc.status_code})")


if __name__ == "__main__":
    args = sys.argv[1:]
    digest = args[0] if len(args) > 0 else "sha256:example"
    base_url = args[1] if len(args) > 1 else "http://localhost:8080"
    try:
        main(digest, base_url)
    except TransportError as exc:
        print(f"NO Cannot reach runtime: {exc}", file=sys.stderr)
        sys.exit(1)
