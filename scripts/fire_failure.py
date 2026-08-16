#!/usr/bin/env python3
"""Fire a simulated dbt failure event at Sentinel's triage webhook.

Usage:
    python scripts/fire_failure.py

Reads the webhook endpoint and auth key from environment variables:
    SENTINEL_WEBHOOK_URL  - printed in the RocketRide Project Log when
                             sentinel-triage.pipe starts (form:
                             {host}/webhook/{project_id}/{source})
    SENTINEL_API_KEY      - RocketRide API key, sent as Authorization: Bearer

Posts the raw contents of demo/failure_payload.json as text/plain — the
webhook routes text/* bodies to the `text` lane, which feeds the `question`
node ahead of the triage agent. (A JSON content-type lands on a lane
nothing downstream is wired to and silently produces no answer.)
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request


def main() -> int:
    url = os.environ.get("SENTINEL_WEBHOOK_URL")
    key = os.environ.get("SENTINEL_API_KEY")
    if not url or not key:
        print("Set SENTINEL_WEBHOOK_URL and SENTINEL_API_KEY.", file=sys.stderr)
        return 1

    payload_path = pathlib.Path(__file__).resolve().parent.parent / "demo" / "failure_payload.json"
    body = payload_path.read_bytes()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "text/plain",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            print(f"HTTP {resp.status} {resp.reason}")
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.reason}", file=sys.stderr)
        print(e.read().decode(), file=sys.stderr)
        return 1

    try:
        answers = result["data"]["objects"]["body"]["answers"]
    except (KeyError, TypeError):
        print(json.dumps(result, indent=2))
        return 0

    for answer in answers:
        print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
