# Contributing

Thanks for considering a contribution to Universal Data Cleaner.

## Development workflow

This project uses a standard branch → pull request → CI → merge flow.

1. Create a branch off `main`:
   ```bash
   git checkout -b feat/short-description
   ```
2. Make focused changes and add tests.
3. Run the full quality gate locally:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy
   uv run pytest
   uv build
   ```
4. Commit with a conventional message, e.g. `feat: add X`, `fix: correct Y`,
   `docs: ...`, `chore: ...`.
5. Push the branch and open a pull request.
6. Wait for CI (`lint`, `typecheck`, `test`, `build`, `ci-success`) to pass.
7. Merge once the PR is green.

Direct pushes to `main` are restricted; all changes go through a pull request.

## Local setup

```bash
git clone https://github.com/devlprkhan/universal-data-cleaner.git
cd universal-data-cleaner
uv sync --dev
uv run pre-commit install
```

`pre-commit` runs ruff, formatting, and mypy on every commit.

## Agent-assisted contributions (OpenCode)

This repository ships an OpenCode V2 configuration in `opencode.jsonc`, project
instructions in `AGENTS.md`, and reusable commands in `.opencode/`. The
configuration defaults shell commands to approval, blocks secret reads and
destructive operations, requires approval for network access, and disables Code
Mode so its built-in `fetch` cannot bypass web approvals.

Use `/check` to run the full quality gate and `/review` for a read-only review.
Do not weaken the configuration or bypass an approval; see `AGENTS.md` for the
full safety and data-leakage rules. Do not run OpenCode with `--auto`, which
auto-approves permission prompts.

## Before opening a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

Please keep changes focused and include tests for new cleaning behavior.

## Guidelines

- Keep the public API backwards-compatible unless the change is intentional and documented.
- Add or update tests in `tests/test_data_cleaner.py`.
- Update `README.md` and `CHANGELOG.md` for user-facing changes.
- Do not commit generated artifacts, virtual environments, or notebook outputs.
- Keep data cleaning behavior deterministic and leak-safe: learned parameters must come from training data only.
- Keep type annotations real: `mypy` must pass, and new public functions should be fully annotated.

## Reporting issues

Use the GitHub issue tracker and include:

- the installed package and pandas/scikit-learn versions;
- a minimal reproducible DataFrame;
- the expected and actual output;
- the full traceback, if applicable.
