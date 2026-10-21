---
description: Run the full local quality gate
agent: build
---

Run the full quality gate for this repository and report the results:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy`
4. `uv run pytest`
5. `uv build`

Do not commit, push, tag, or publish. If a command fails, show the failing
output and the likely cause. Do not skip or suppress checks.
