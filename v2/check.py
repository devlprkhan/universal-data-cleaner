"""Smoke-check the v2 preview served from the repository root.

Usage: python3 v2/check.py   (with `python3 -m http.server 8000` running)
"""

from __future__ import annotations

import urllib.error
import urllib.request

BASE = "http://localhost:8000"
PAGES = (
    "/v2/site/",
    "/v2/site/quickstart/",
    "/v2/site/leak-safe-workflow/",
    "/v2/site/cleaning/",
    "/v2/site/api/",
    "/v2/site/changelog/",
    "/v2/site/adr/index/",
    "/v2/site/assets/v2.css",
    "/v2/site/assets/v2.js",
    "/v2/site/assets/search-index.js",
    "/site/",
)

failures = 0
for path in PAGES:
    try:
        with urllib.request.urlopen(BASE + path, timeout=5) as response:
            body = response.read()
        print(f"{response.status}  {len(body):>8}  {path}")
    except (urllib.error.URLError, TimeoutError) as exc:
        failures += 1
        print(f"FAIL      {path}  {exc}")

print("\nok" if not failures else f"\n{failures} failure(s)")
