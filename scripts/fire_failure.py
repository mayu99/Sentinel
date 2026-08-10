#!/usr/bin/env python3
"""Fire a simulated dbt failure event at Sentinel's triage webhook.

Usage:
    python scripts/fire_failure.py <webhook_url>

The webhook URL is printed in the RocketRide Project Log when
sentinel-triage.pipe starts (form: {host}/webhook/{project_id}/{source}).
The failure payload is sent as the question text, so the triage agent
receives the full JSON event verbatim.
"""
import json
import pathlib
import sys
import urllib.request

def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    url = sys.argv[1]
    payload_path = pathlib.Path(__file__).resolve().parent.parent / "demo" / "failure_payload.json"
    payload = json.loads(payload_path.read_text())

    body = json.dumps({"question": json.dumps(payload, indent=2)}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        print(f"HTTP {resp.status}")
        print(resp.read().decode())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
