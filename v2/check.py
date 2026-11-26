"""Smoke-check the site served from the repository root.

Usage: uv run python v2/check.py   (with `uv run python v2/dev.py` running)
"""

from __future__ import annotations

import urllib.error
import urllib.request

BASE = "http://localhost:8000"
PAGES = (
    "/",
    "/quickstart/",
    "/leak-safe-workflow/",
    "/cleaning/",
    "/api/",
    "/changelog/",
    "/adr/",
    "/assets/v2.css",
    "/assets/v2.js",
    "/assets/search-index.js",
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
