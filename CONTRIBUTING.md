# Contributing

Thanks for considering a contribution to Universal Data Cleaner.

## Local setup

```bash
git clone https://github.com/devlprkhan/universal-data-cleaner.git
cd universal-data-cleaner
uv sync
```

## Before opening a pull request

```bash
uv run pytest -q
uv build
```

Please keep changes focused and include tests for new cleaning behavior.

## Guidelines

- Keep the public API backwards-compatible unless the change is intentional and documented.
- Add or update tests in `tests/test_data_cleaner.py`.
- Update `README.md` and `CHANGELOG.md` for user-facing changes.
- Do not commit generated artifacts, virtual environments, or notebook outputs.
- Keep data cleaning behavior deterministic and leak-safe: learned parameters must come from training data only.

## Reporting issues

Use the GitHub issue tracker and include:

- the installed package and pandas/scikit-learn versions;
- a minimal reproducible DataFrame;
- the expected and actual output;
- the full traceback, if applicable.
