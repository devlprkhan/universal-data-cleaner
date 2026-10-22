# Universal Data Cleaner

[![CI](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-4f46e5.svg)](https://devlprkhan.github.io/universal-data-cleaner/)
[![PyPI](https://img.shields.io/pypi/v/universal-data-cleaner.svg)](https://pypi.org/project/universal-data-cleaner/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://github.com/devlprkhan/universal-data-cleaner/blob/main/LICENSE)
[![Managed with uv](https://img.shields.io/badge/managed%20with-uv-6f42c1.svg)](https://docs.astral.sh/uv/)

A small, production-oriented tabular cleaning transformer for pandas + scikit-learn.

It is designed for the part of an ML pipeline that is easy to get wrong: cleaning
training data and inference data with **exactly the same learned rules**.

## Documentation

**[Full documentation →](https://devlprkhan.github.io/universal-data-cleaner/)**

The docs site is the central reference. This README is the short entry point.

| Guide | What it covers |
| --- | --- |
| [Quickstart](https://devlprkhan.github.io/universal-data-cleaner/quickstart/) | Install, first cleaner, scikit-learn pipeline |
| [Leak-safe workflow](https://devlprkhan.github.io/universal-data-cleaner/leak-safe-workflow/) | The fit/transform contract and common mistakes |
| [Cleaning data](https://devlprkhan.github.io/universal-data-cleaner/cleaning/) | Config, roles, imputation, outliers, datetimes |
| [Contracts & drift](https://devlprkhan.github.io/universal-data-cleaner/contracts/) | `ColumnSpec`, `DataContract`, drift checks |
| [Validation, joins & dedup](https://devlprkhan.github.io/universal-data-cleaner/validation-joins/) | Expectations, join diagnostics, integrity, dedup |
| [ML split audit](https://devlprkhan.github.io/universal-data-cleaner/ml-split-audit/) | Duplicate, group, temporal, and target leakage |
| [Artifacts & reproducibility](https://devlprkhan.github.io/universal-data-cleaner/artifacts/) | Decision log, manifests, fingerprints, save/load |
| [Production guide](https://devlprkhan.github.io/universal-data-cleaner/production/) | Deployment checklist and failure modes |
| [API reference](https://devlprkhan.github.io/universal-data-cleaner/api/) | Generated from the package docstrings |
| [Changelog](https://devlprkhan.github.io/universal-data-cleaner/changelog/) | Release notes |

## Install

```bash
pip install universal-data-cleaner
```

```bash
uv add universal-data-cleaner
```

The distribution name is `universal-data-cleaner`; the import name is
`data_cleaner`.

```python
from data_cleaner import CleanerConfig, DataCleaner
```

## Quick start

```python
import pandas as pd
from data_cleaner import CleanerConfig, DataCleaner

train = pd.DataFrame(
    {
        "age": [34, 41, None, 29],
        "salary": [70_000, 82_000, 91_000, 55_000],
        "dept": ["IT", "HR", "IT", None],
        "joined": ["2022-01-03", "2021-11-20", "2023-04-01", "bad-date"],
    }
)

config = CleanerConfig(
    datetime_columns=("joined",),
    add_missing_indicators=True,
    drop_constant_columns=True,
)

cleaner = DataCleaner(config).fit(train)
train_clean = cleaner.transform(train)
```

`fit()` learns medians, modes, outlier bounds, category values, and datetime
rules from `train`. `transform()` applies those stored rules without learning
from the frame you pass in.

## Leak-safe by construction

```python
cleaner = DataCleaner(config).fit(X_train)

X_train_clean = cleaner.transform(X_train)
X_test_clean = cleaner.transform(X_test)  # training rules only
```

Never fit before splitting, and never create a new cleaner for test or
production data. See the [leak-safe workflow](https://devlprkhan.github.io/universal-data-cleaner/leak-safe-workflow/)
for the full explanation.

## What it handles

- numeric coercion, median / mean / constant imputation, and IQR capping
- categorical mode / constant imputation and a keep-or-fill unseen policy
- boolean coercion and imputation
- datetime parsing plus calendar feature extraction
- optional missing-value indicators and constant-column dropping
- declarative contracts with roles, allowed values, ranges, patterns, and uniqueness
- automatic train-schema contract inference and transform-time drift reports
- expectation checks and validation reports
- join diagnostics, referential integrity, and audited business-key dedup
- train/test split audits for duplicate, group, temporal, and target leakage
- joblib save / load, manifests, and stable data fingerprints
- scikit-learn `Pipeline`, `clone`, and `get_feature_names_out` compatibility
- stable output schema and column order; inputs are never mutated and inference
  rows are never dropped

## Development

```bash
git clone https://github.com/devlprkhan/universal-data-cleaner.git
cd universal-data-cleaner
uv sync --dev
uv run pytest -q
```

Run the full quality gate:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

Build or preview the docs:

```bash
uv sync --group docs
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
```

The reference notebook is `Universal_Data_Cleaner.ipynb`. Open it with:

```bash
uv run jupyter lab Universal_Data_Cleaner.ipynb
```

## Project layout

```text
src/data_cleaner/                  # typed, pip-installable package
tests/                             # unit and integration tests
docs/                              # MkDocs guides, API page, and assets
mkdocs.yml                         # documentation site configuration
Universal_Data_Cleaner.ipynb       # end-to-end reference workflow
pyproject.toml                     # package metadata and tooling
uv.lock                            # reproducible dependency lock
CHANGELOG.md                       # release notes
CONTRIBUTING.md                    # development workflow
SECURITY.md                        # vulnerability reporting
LICENSE                            # MIT license
```

The package ships a `py.typed` marker, so `mypy`, `pyright`, and IDE tooling pick
up the type annotations automatically. Linting, formatting, type checking, tests,
the docs build, and package build run in CI.

## Contributing

Contributions are welcome. See
[CONTRIBUTING.md](https://github.com/devlprkhan/universal-data-cleaner/blob/main/CONTRIBUTING.md)
for the local setup, quality gate, and pull-request expectations.

## License

Released under the [MIT License](https://github.com/devlprkhan/universal-data-cleaner/blob/main/LICENSE).
