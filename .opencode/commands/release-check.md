---
description: Prepare a release checklist without publishing
agent: build
---

Prepare a release checklist for $ARGUMENTS. Do not create a tag, GitHub release,
or PyPI publish.

1. Confirm the current branch and working tree state with `git status`.
2. Check that the version in `pyproject.toml` and `CHANGELOG.md` agree.
3. Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
   `uv run pytest`, and `uv build`.
4. If `twine` is available, run `uvx --from twine twine check dist/*`; otherwise
   note that it was skipped.
5. Summarize the release notes and list the exact tag/release commands a
   maintainer would run.
6. Stop and ask the maintainer for explicit approval before creating a tag or
   release.

Never run `gh release create`, `gh workflow run publish.yml`, `uv publish`, or
`twine upload` without explicit approval.
