# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [2.2.0] - 2026-10-20

### Added

- Typed public package: the library now ships as `src/data_cleaner/` with a
  PEP 561 `py.typed` marker, so type checkers and IDEs pick up the annotations.
- Continuous integration now runs `ruff` (lint + format), `mypy` (type checking),
  and the test matrix on Python 3.10–3.13, plus a build/`twine check` job.
- `pre-commit` configuration for local linting, formatting, and type checking.
- A cross-version artifact compatibility test that reproduces the pre-package
  (flat module) pickle layout and verifies the artifact still loads and cleans.

### Changed

- Internal structure split from a single module into a package
  (`_version`, `_roles`, `contract`, `config`, `cleaner`, `profiling`). The
  public API and `import data_cleaner` are unchanged.
- Project tooling now enforces linting, formatting, and typing on every change.

### Notes

- Fully backwards compatible: `import data_cleaner` and all public names are
  re-exported from the package root, and v2.0.0/v2.1.0 joblib artifacts still
  load.

## [2.1.0] - 2026-10-20

### Added

- `ColumnSpec` for declarative per-column expectations: role, dtype kind,
  nullability, uniqueness, allowed values, numeric range, regex pattern, date
  format, leading-zero preservation, and severity.
- `DataContract` for grouping column specs, with `infer_from()`, `check()` /
  `diff()`, and `to_dict()` / `from_dict()` / `to_json()` / `from_json()`
  serialization. Optional `to_yaml()` / `from_yaml()` when PyYAML is installed.
- `DriftReport` with `has_drift`, `errors`, `warnings`, `summary()`,
  `to_markdown()`, and `raise_if_errors()`.
- Transform-time schema/type/nullability/range/category drift detection,
  available through `DataCleaner.drift_report()`.
- Semantic roles, including `id` and `text` columns that are never numeric
  coerced, median-imputed, or IQR-capped, and `ignore` columns that are dropped.
- `CleanerConfig.contract`, `CleanerConfig.on_drift` (`raise`/`warn`/`ignore`),
  and `CleanerConfig.infer_contract` to control drift handling.
- `DataCleaner.fitted_contract()` to inspect the contract in use.

### Changed

- `transform()` now records a drift report and applies the configured
  `on_drift` policy. Conservative contracts are inferred automatically from the
  training schema by default, so drift is reported without any configuration.
- Missing required columns raise a `ValueError` that includes drift details.

### Notes

- Fully backwards compatible: existing `CleanerConfig` / `DataCleaner` usage and
  v2.0.0 joblib artifacts continue to work. All new behavior is opt-in except
  drift reporting, which only logs by default.

## [2.0.0] - 2026-10-19

### Added

- `CleanerConfig` for explicit, validated cleaning configuration.
- `DataCleaner` transformer with scikit-learn `clone` and `Pipeline` support.
- Train-only learning for numeric imputation, categorical modes, and IQR outlier bounds.
- Numeric coercion for dirty string columns.
- Boolean and datetime handling, including configurable calendar features.
- Optional missing-value indicator columns.
- Optional constant-column removal.
- Unseen-category policy: keep or replace.
- Stable output schema and column ordering.
- `cleaning_summary()` and `outlier_summary()` audit helpers.
- Joblib `save()` / `load()` with artifact version metadata.
- `profile_dataframe`, `dataset_summary`, `drop_duplicate_rows`, and `assert_frame_clean` utilities.
- End-to-end notebook with a leak-safe train/test workflow.
- Unit and integration test suite.
- uv-managed packaging, development dependencies, and CI workflow.

[2.1.0]: https://github.com/devlprkhan/universal-data-cleaner/releases/tag/v2.1.0
[2.0.0]: https://github.com/devlprkhan/universal-data-cleaner/releases/tag/v2.0.0
