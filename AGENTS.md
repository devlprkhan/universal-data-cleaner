# AGENTS.md

This file is the canonical operating guide for AI coding agents working in this
repository. `opencode.jsonc` enforces the security boundaries; this file explains
the workflow and the invariants that are not obvious from the code. If the two
ever conflict, follow the stricter rule and ask the maintainer.

## Project

Universal Data Cleaner is a production-ready, scikit-learn-compatible data
cleaning transformer for pandas. The import package is `data_cleaner` under
`src/data_cleaner/`. The distribution is published to PyPI as
`universal-data-cleaner`.

Key paths:

- `src/data_cleaner/` — library code.
- `tests/` — test suite (pytest, unittest-style assertions).
- `pyproject.toml` — packaging, dependencies, ruff, mypy, and pytest config.
- `.github/workflows/ci.yml` — required CI checks.
- `.github/workflows/publish.yml` — release-triggered PyPI publishing.
- `CHANGELOG.md`, `README.md`, `ROADMAP.md` — user-facing documentation.
- `opencode.jsonc`, `.opencode/` — agent permissions, agents, and commands.
- `AGENTS.md` — this file.

## Toolchain

Use `uv` for everything. Do not use pip, poetry, conda, or a manually managed
virtual environment.

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
uv run pre-commit run --all-files
```

Supported Python versions are 3.10–3.13. The library supports pandas 2.x and
3.x; keep behavior compatible with both.

## Quality gate

Before committing or opening a pull request, run the full local gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

The `/check` command runs this sequence. Do not bypass hooks with `--no-verify`
and do not suppress a failing check. If a check fails, fix the cause or explain
why the check itself is wrong.

## Safety and security

- Never read, print, commit, or transmit secrets, tokens, passwords, private
  keys, `.env` files, or local credentials. Do not create a `.env` file in this
  repository; use environment variables supplied by the user.
- Secret files and `.git/` are blocked by permissions and policies. Do not try
  to bypass a block with another command, shell metacharacter, encoded payload,
  or script. Stop and ask the maintainer.
- Do not run `sudo`, destructive filesystem commands, history rewrites, force
  pushes, hook bypasses, or commands that delete GitHub or PyPI releases. These
  are hard-denied by policy.
- Network access (`webfetch`, `websearch`) requires approval. Never put secrets,
  credentials, or private source code in URLs or search queries.
- Code Mode (`execute`) is disabled because its built-in `fetch` can bypass web
  approvals. Use the normal `read`, `grep`, `glob`, `edit`, and `shell` tools.
- MCP servers and unknown skills are blocked. Do not add MCP servers, plugins,
  skills, or agents without explicit maintainer approval.
- Do not edit guardrail files (`opencode.jsonc`, `AGENTS.md`, `.opencode/**`).
  They are human-maintained; ask the maintainer to change them.
- If a command is blocked or asks for approval, explain what you need and why.
  Never use `opencode --auto`.

## Data-leakage invariants

Leak-safe preprocessing is the library's core promise. Preserve these invariants:

- Fit learned parameters on training data only. Never use validation or test data
  during `fit`.
- `transform` must not learn from or mutate the input data. Do not drop rows or
  modify the caller's DataFrame in place.
- Handle unseen categories at transform time according to the documented policy;
  do not crash unless the documented contract says to.
- Preserve column order, documented dtypes, and the public API. Avoid silent
  behavior changes.
- Keep transforms deterministic and reproducible. Do not introduce randomness
  without an explicit `random_state`.
- Do not log, serialize, or persist raw user data. Redact examples in tests and
  documentation.
- Keep pandas 2.x/3.x compatibility and avoid unnecessary runtime dependencies.

## Code conventions

- Python 3.10+; use `from __future__ import annotations`.
- Add type annotations to public functions and keep mypy clean.
- Follow the existing style: ruff, line length 88, double quotes, sorted imports.
- Add tests in `tests/` for every bug fix and behavior change. Use the existing
  unittest-style structure.
- Keep public APIs backwards-compatible unless the change is intentional and
  documented.
- Update `CHANGELOG.md` for user-facing changes and `README.md` when behavior or
  documentation changes.
- Do not hand-edit `uv.lock`; use `uv lock` or `uv sync`.
- Do not edit generated or ignored paths (`dist/`, `build/`, `.venv/`, caches,
  `*.egg-info/`).
- Keep diffs focused; avoid drive-by refactors.

## Git and pull request workflow

1. Create a branch from `main`: `git switch -c feat/short-description`.
2. Make focused changes and add tests.
3. Run the full quality gate.
4. Commit with a conventional message (`feat:`, `fix:`, `docs:`, `test:`,
   `chore:`).
5. Push the branch and open a pull request.
6. Wait for `lint`, `typecheck`, `test`, `build`, and `ci-success` to pass.
7. Merge only when green, up to date, and the conversation is resolved. Do not
   push directly to `main`, force-push, or bypass branch protection.
8. Do not create tags or GitHub releases without explicit maintainer approval.

## Release process

Publishing is triggered by a published GitHub release, which runs
`.github/workflows/publish.yml` with PyPI trusted publishing. Never publish or
trigger publishing without explicit maintainer approval.

- Use `/release-check` to prepare and verify a release.
- Confirm the version in `pyproject.toml`, update `CHANGELOG.md`, and make sure
  CI is green.
- Build and inspect the artifacts.
- Ask the maintainer for explicit approval before creating the tag or release.
- Never run `gh release create`, `gh workflow run publish.yml`, `uv publish`, or
  `twine upload` on your own.
- After publishing, verify the artifact on PyPI only if asked.

## OpenCode commands

- `/check` — run the full local quality gate.
- `/review` — read-only review of current changes for correctness, security,
  data leakage, and missing tests.
- `/release-check` — prepare a release checklist; stop before publishing.

## When in doubt

Stop and ask. A blocked command is a signal to explain the need, not to find a
workaround.
