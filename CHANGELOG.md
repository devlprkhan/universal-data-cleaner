# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Documentation

- Add a MkDocs Material documentation site with task guides, an API reference,
  and GitHub Pages deployment.
- Expose the documentation site in the package project URLs and README so PyPI
  and GitHub point to the same central reference.

## [2.5.0] - 2026-10-22

### Added

- `audit_split()` and `SplitAudit`: a pure-function train/test split audit that
  reports exact duplicate overlap, near-duplicate overlap, group leakage,
  temporal leakage, target-leakage heuristics, constant and near-constant
  columns, high-cardinality identifiers, missingness shift, numeric and
  categorical distribution shift, unseen target classes, and target shift.
- Findings carry a `check`, `column`, `severity`, `message`, and train/test
  values. Schema problems, empty splits, exact duplicates, group leakage,
  temporal leakage, and unparseable or numeric timestamps are errors;
  statistical and heuristic checks are warnings. High-cardinality declared
  identifiers are reported separately as `high_cardinality_identifier`.
- `SplitAudit` exposes `findings`, `valid`, `errors`, `warnings`, `summary()`,
  `to_markdown()`, `to_dict()`, and `raise_if_invalid()`.
- Findings never include raw cell values; messages contain column names,
  counts, rates, and statistics only.

### Changed

- None. Tier 4 is additive and the artifact format remains `2`.

### Notes

- The audit never mutates inputs, never fits anything, and never repairs a
  split. Duplicate checks exclude declared `id_cols` and `time_col`.
- Near-duplicates use a deterministic rounded-feature hash rather than a
  nearest-neighbour search, so the result is reproducible without extra
  dependencies. Exact duplicate hashing is dtype-independent, so `1` and
  `1.0` compare equal while object numbers and strings stay distinct.
- `groups` may cover both splits or training rows only when `groups_test` is
  supplied.

## [2.4.0] - 2026-10-22

### Added

- Lightweight expectations API: `not_null()`, `unique()`, `in_set()`,
  `between()`, `matches_pattern()`, `has_dtype()`, and
  `row_count_between()`, plus `Expectation`, `ValidationResult`,
  `ValidationReport`, and `validate()`. Reports expose `success`, `results`,
  `failures`, `to_markdown()`, and `raise_if_failed()`.
- `DataContract.from_frame()` and `DataContract.validate()`; `Contract` is a
  shorthand alias for `DataContract`.
- `diagnose_join()` and `JoinDiagnosis`: left/right duplicate keys, cardinality
  class, output row multiplier, unmatched counts, null keys, warnings, and
  `raise_if_unsafe()`.
- `check_referential_integrity()` and `ReferentialIntegrityReport`: orphan
  rows and keys, null keys, duplicate parent keys, and `raise_if_invalid()`.
- `deduplicate_by_business_key()` and `DeduplicationReport`: audited removal
  with the actual removed rows, duplicate-key counts, null-key warnings, and
  tie-breaker details.

### Changed

- None. Tier 3 is additive and the artifact format remains `2`.

### Notes

- All new helpers are pure functions: they never mutate their inputs and do
  not require fitting.
- `ValidationReport.success` ignores warning-severity failures;
  `raise_if_failed()` raises only for error-severity failures.

## [2.3.0] - 2026-10-20

### Added

- `CleaningDecision` and `DataCleaner.decision_log()`: a tidy audit trail of
  every learned or configured cleaning decision (`column`, `action`, `reason`,
  `source`, `before`, `after`).
- `DataCleaner.to_manifest()` and `artifact_manifest()`: JSON-serializable
  manifests with library/artifact versions, Python/pandas/numpy/scikit-learn
  versions, config, contract, input schema, output columns, fit summary,
  decisions, and an optional data fingerprint.
- `fingerprint_dataframe()`, `compare_fingerprints()`, and
  `assert_schema_stable()`: stable SHA-256 fingerprints of schema plus summary
  statistics for lineage checks. Raw values are never hashed.
- `DataCleaner.fingerprint(X)` for on-demand fingerprints and
  `CleanerConfig.fingerprint_on_fit` to compute the training fingerprint during
  `fit()`.

### Changed

- `save()` now embeds the manifest and fingerprint in the artifact; `load()`
  restores them and warns when an artifact predates audit metadata.
- Older artifacts are backfilled on load: `decision_log()` returns an empty,
  correctly-shaped DataFrame instead of failing.
- Artifact format version bumped to `2`.

### Notes

- Fully backwards compatible: existing configuration, public imports, and
  v2.0.0–v2.2.0 joblib artifacts continue to work.

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
