# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

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

[2.0.0]: https://github.com/devlprkhan/universal-data-cleaner/releases/tag/v2.0.0
