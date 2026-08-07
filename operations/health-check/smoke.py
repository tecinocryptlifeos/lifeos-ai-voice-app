#!/usr/bin/env python3
"""Read-only post-deployment health probe; prints no response bodies or secrets."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def exact_origin(name):
    value = os.environ.get(name, "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query:
        raise SystemExit(f"{name} must be an exact HTTPS origin")
    return value


def probe(label, url):
    request = urllib.request.Request(url, headers={"User-Agent": "LifeOS-Smoke/1"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except Exception as error:
        print(f"{label}=FAIL kind={type(error).__name__}")
        return False
    passed = 200 <= status < 300
    print(f"{label}={'PASS' if passed else 'FAIL'} status={status}")
    return passed


def main():
    site = exact_origin("LIFEOS_PUBLIC_SITE_ORIGIN")
    api = exact_origin("LIFEOS_API_ORIGIN")
    results = [
        probe("PUBLIC_HOME", site + "/"),
        probe("PUBLIC_CHAT", site + "/chat"),
        probe("PUBLIC_VOICE", site + "/voice"),
        probe("PUBLIC_ACCOUNT", site + "/account"),
        probe("PUBLIC_ADMIN", site + "/admin"),
        probe("EDGE_HEALTH", api + "/health"),
        probe("EDGE_CONFIG", api + "/config"),
    ]
    print("SMOKE=PASS" if all(results) else "SMOKE=FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
