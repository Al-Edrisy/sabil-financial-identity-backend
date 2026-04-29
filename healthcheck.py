"""
healthcheck.py — Docker HEALTHCHECK script.

Performs a lightweight HTTP GET to /api/v1/health and exits 0 on success,
1 on failure. Used by the Dockerfile HEALTHCHECK instruction.
"""

import http.client
import json
import sys


def check_health(host: str = "localhost", port: int = 8000) -> None:
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/api/v1/health")
        response = conn.getresponse()

        if response.status == 200:
            body = response.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                status = data.get("status", "unknown")
            except json.JSONDecodeError:
                status = body.strip()

            print(f"Health check passed — status={status}")
            sys.exit(0)
        else:
            print(f"Health check failed — HTTP {response.status}")
            sys.exit(1)

    except Exception as exc:
        print(f"Health check failed — {exc}")
        sys.exit(1)


if __name__ == "__main__":
    check_health()
