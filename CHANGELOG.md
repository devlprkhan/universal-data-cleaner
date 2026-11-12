# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.10.0] - 2026-11-12

### Added

- `DataCleaner.transform_with_report(X)` returns `(cleaned_frame, drift_report)`
  for one batch and does not read or write the shared `drift_report_` state, so
  a fitted cleaner can safely serve concurrent batches. `transform()` remains
  backward compatible and documents `drift_report_` as last-call state.
- `CleanerConfig.preserve_integer_dtypes` (default `True`) keeps integral
  numeric columns as `int64` after imputation and clipping when the learned fill
  value and outlier bounds are integral. Otherwise the column falls back to
  `float64` and logs the fallback.
- `CleanerConfig.on_precision_loss` selects `"coerce"` (default), `"warn"`, or
  `"raise"` when `float64` cannot represent an integer exactly. Detection is
  exact at the `2^53` boundary rather than a blanket threshold.
- `iter_csv_safe()` gained `unique_tracking` (`"memory"`, `"disk"`, or `"auto"`),
  `unique_tracking_limit`, and `unique_tracking_path`. Disk tracking uses a
  temporary SQLite database, and `"auto"` migrates from memory once the limit is
  exceeded.
- `combine_ingestion_reports(reports, source=None)` rolls per-chunk reports into
  one whole-file report with the summed row count and concatenated findings.
- `DataCleaner.load(..., strict_environment=True)` raises
  `ArtifactCompatibilityError` when the recorded pandas, NumPy, or scikit-learn
  major version differs from the current runtime. The default logs a warning.

### Changed

- `DataCleaner.save()` now writes to a temporary file, validates the written
  artifact, and atomically replaces the target with `os.replace`. A failed or
  interrupted save keeps the previous artifact and removes partial files.
- `DataCleaner.load()` wraps unreadable artifacts in a `ValueError` with the
  underlying cause instead of leaking an arbitrary unpickling exception.

### Fixed

- Integer columns are no longer silently rounded through `float64` during
  cleaning. Values above `2^53` are preserved exactly by default.
- Cross-chunk uniqueness tracking no longer stores an ever-growing pandas index
  per column; the default `"auto"` mode is bounded and switches to disk.

## [2.9.1] - 2026-11-11

### Added

- CI now tests the minimum supported dependency versions on Python 3.10, the
  latest stable dependency set, and pandas 3.x.
- CI installs the built wheel in a clean environment and checks imports, public
  exports, the CLI, and a small end-to-end cleaning workflow.
- Release builds generate PEP 740 attestations for PyPI and GitHub
  build-provenance attestations, so published artifacts can be verified against
  the workflow that built them.

### Changed

- `iter_csv_safe()` now infers the schema from the first chunk and reuses it for
  every later chunk. A later value that does not fit the inferred type is
  reported as `unparseable_values` instead of silently changing the column dtype.
  Pass an explicit contract when the first chunk may not be representative.
- Safe ingestion now enforces `ColumnSpec(unique=True)` and reports
  `duplicate_values`. Duplicates are detected within a frame and, for
  `iter_csv_safe()`, across chunks. Missing values are ignored.
- `DataContract.check()` now ignores missing values for `unique=True`, matching
  the documented "non-null values must be unique" behavior and the validation
  helper.
- `DataCleaner.transform()` now states that a missing fitted input column is
  always fatal, regardless of `on_drift`, because the cleaner cannot safely
  reconstruct it. The documentation matches the behavior.

### Release

- `2.9.1` is the first release built with the attestation workflow. Verify its
  provenance with the commands in the production guide; `2.9.0` predates the
  workflow and has no PyPI provenance.

## [2.9.0] - 2026-11-10

### Added

- `ColumnSpec(required=...)` marks a contract column as required or optional.
- `ArtifactCompatibilityError` is raised by `DataCleaner.load()` when a saved
  artifact has an incompatible artifact format or library major version.
  `allow_incompatible=True` loads it with a warning, and `verify_version=False`
  skips the check entirely. The docs now state the pickle trust boundary.
- `iter_csv_safe()` streams a large CSV in typed chunks and yields one
  `(frame, IngestionReport)` pair per chunk, using bounded memory.
- `CleanerConfig.outlier_columns` names the numeric columns that may be capped.
  When set it acts as an allowlist and overrides `cap_outliers`.
- `read_csv_safe()` emits an `integer_precision` warning for integer values
  beyond `2^53` that are coerced to `float64`, because they may already have lost
  precision.

### Changed

- Contracts: `DataCleaner.fit()` now validates an explicit contract before
  learning and raises `ValueError` when a required training column is missing,
  instead of deferring the failure to `transform()`. Columns with
  `required=False` or `role="ignore"` may be absent.
- `diagnose_join()` now computes matched and unmatched rows from grouped key
  frequencies, so duplicated keys no longer expand into a many-to-many join or
  risk exhausting memory. Reported row counts are unchanged.
- Outlier clipping is now opt-in: `CleanerConfig.cap_outliers` defaults to
  `False`. Set it to `True`, or list `outlier_columns`, to keep the previous
  clipping behavior.
- CSV ingestion now normalizes blank cells in place instead of copying the whole
  frame, reducing peak memory for large inputs.
- Docs: the public API is documented in stable, experimental, and internal tiers
  with a deprecation policy. `data_cleaner.__all__` is the canonical surface.
- Docs: refined the documentation site chrome with a light header, quieter
  navigation and active states, a calmer type scale, and consistent spacing,
  radii, and motion. The "Where to go next" and "Documentation map" sections now
  render as one joined, rounded table with aligned columns and link-only hover.

## [2.8.0] - 2026-11-06

### Added

- `read_excel_safe()`: read one Excel worksheet as values, normalize every cell
  to text, apply the same contract-driven guards as `read_csv_safe()`, and return
  the typed frame with an `IngestionReport`.
- Worksheet selection with `sheet_name`, accepting either a name or a zero-based
  index. The resolved sheet is recorded on `IngestionReport.sheet`.
- `CleanerReport.from_excel()`: attach Excel ingestion findings to the same
  profile, contract, validation, and decision report as CSV input.
- `read_excel_safe()` keeps native cell types long enough to detect numeric IDs,
  then applies per-cell date guards, so a column can mix real dates, `YYYYMMDD`
  text, and Excel serials.
- Worksheet selection is by name or non-negative zero-based index; duplicate
  headers after string conversion are rejected rather than collapsed.
- `data-cleaner audit` now detects `.xlsx`, `.xlsm`, `.xls`, `.xlsb`, and `.ods`
  input and accepts `--sheet NAME` or `--sheet-index N`.
- `numeric_identifier` warning when a contract ID column is stored as numbers in
  the spreadsheet and has already lost its leading zeros.
- Optional `excel` extra (`openpyxl>=3.1`) for `.xlsx` and `.xlsm` workbooks.
  `read_csv_safe()` remains dependency-free.
- Docs: Excel sections across the ingestion, reporting, quickstart, production,
  and API guides.

### Changed

- `IngestionReport` gains a `sheet` field (default `None`) and includes it in
  `to_dict()`. `to_markdown()` now names the source and sheet.
- `IngestionReport.location` combines the source and resolved sheet, and both
  warning logs and `IngestionError` messages use it.
- URL-shaped source labels are stored without credentials or query strings, so
  signed or authenticated URLs do not leak into reports or logs.
- Undeclared-column findings now say the column was typed by inference and point
  to the detected/output kinds in `report.columns`, rather than claiming the
  column was kept as text.
- `IngestionReport.raise_if_failed()` defaults to the format-neutral message
  `"Ingestion failed"`. The exception raised by `read_csv_safe()` still names CSV.

### Notes

- The artifact format remains `2`; this release is additive.
- Real Excel date cells are parsed directly. Numbers in a datetime column are
  treated as Excel serial dates and flagged with `excel_serial_date`.
- Excel cannot preserve leading zeros in a cell stored as a number. The reader
  warns with `numeric_identifier`, but store identifiers as text to avoid the
  loss in the first place.
- `.xls`, `.xlsb`, and `.ods` files need the matching pandas engine (`xlrd`,
  `pyxlsb`, or `odfpy`); the `excel` extra covers `.xlsx` and `.xlsm`.

## [2.7.0] - 2026-11-05

### Added

- `CleanerReport`: one review object per batch combining the dataset profile,
  contract drift, validation results, ingestion findings, and the fitted
  cleaner's decision log.
- `CleanerReport.from_frame()`, `from_csv()`, and `from_cleaner()` entry points.
  None of them transform the input frame or re-fit the cleaner.
- A tidy `findings` table with `source`, `column`, `check`, `severity`, `message`,
  and `count`, plus `errors`, `warnings`, `success`, `summary()`,
  `to_markdown()`, `to_dict()`, `to_json()`, and `raise_if_failed()`.
- Profile warnings for empty datasets, empty columns, constant columns, high
  missingness (configurable via `high_missing_threshold`), and duplicate rows.
- `python -m data_cleaner audit data.csv` and the `data-cleaner` console script,
  with `--contract`, `--cleaner`, `--name`, `--format markdown|json`, `--output`,
  `--no-profile`, and `--fail-on-warning`.
- Stable CLI exit codes: `0` success, `1` error findings (or warnings with
  `--fail-on-warning`), `2` input or configuration errors.
- Docs: batch reporting guide and cross-links from ingestion, quickstart, and the
  production guide.

### Changed

- None. Tier 6 is additive and the artifact format remains `2`.

### Notes

- `CleanerReport.from_csv()` defaults to `on_error="ignore"` so a report is
  always returned; error-severity findings still make `success` false.
- Reports contain column names, counts, and messages only; they never include raw
  cell values, so they are safe to log or attach to an artifact.
- The CLI reads with `on_error="ignore"` and derives failure from the report
  instead of raising during ingestion.

## [2.6.0] - 2026-11-03

### Added

- `read_csv_safe()`: string-first CSV ingestion with contract-driven coercion and
  an `IngestionReport` covering per-column detection, output dtypes, missing
  counts, and every normalization performed.
- Identifier protection: ID columns and values with leading zeros stay text, and
  the report records `leading_zeros_preserved`.
- Spreadsheet artifact handling for numeric fields: thousands separators,
  currency symbols, percent signs, accounting parentheses, and decimal commas
  are normalized with one finding per transformation.
- Date guards for compact `YYYYMMDD` values and Excel serial dates when the
  contract declares `role="datetime"`, plus explicit `date_format` support and an
  `ambiguous_date_format` warning for day/month ambiguity.
- Boolean normalization for Y/N-style tokens with `boolean_tokens` findings.
- `IngestionError` and the `on_error="warn" | "raise" | "ignore"` policy. Error
  findings make the report fail without hiding the frame when policy is `"warn"`.
- `mixed_types` and `empty_column` findings; mixed columns stay text instead of
  silently losing values.
- Docs: safe ingestion guide and an Upcoming page for release planning.

### Changed

- None. Tier 5 is additive and the artifact format remains `2`.

### Notes

- The ingestion report contains column names, counts, and messages only; it never
  includes raw cell values, so it is safe to log or attach to an artifact.
- Without a contract, `YYYYMMDD` and Excel serial values remain numeric. Declare
  a datetime role when they are dates.
- CSV is the supported input for this release; the report model is designed to
  extend to other tabular readers later.

## [2.5.2] - 2026-10-22

### Documentation

- Make the documentation site the single source of truth. The README is now a
  concise entry point with install, quick start, and a guide index.
- Add artifacts/reproducibility and production guides to the docs site.

### Notes

- Documentation-only release; no runtime behavior changes and the artifact
  format remains `2`.

## [2.5.1] - 2026-10-22

### Documentation

- Add a MkDocs Material documentation site with task guides, an API reference,
  and GitHub Pages deployment.
- Expose the documentation site in the package project URLs and README so PyPI
  and GitHub point to the same central reference.

### Notes

- Documentation-only release; no runtime behavior changes and the artifact
  format remains `2`.

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
