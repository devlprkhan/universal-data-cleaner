---
description: API reference for Universal Data Cleaner.
---

# API reference

This page is generated from the package docstrings. Every public name is
importable directly from `data_cleaner`.
{: .lead }

```python
from data_cleaner import DataCleaner, audit_split, validate
```

## Start here

| Object | Use it for |
| --- | --- |
| [`DataCleaner`](#data_cleaner.DataCleaner) | Fit cleaning rules on training data and transform later batches |
| [`CleanerConfig`](#data_cleaner.CleanerConfig) | Configure imputation, outliers, datetime features, contracts, and drift policy |
| [`DataContract`](#data_cleaner.DataContract) | Declare column roles, allowed values, ranges, patterns, and uniqueness |
| [`read_csv_safe`](#data_cleaner.read_csv_safe) | Read CSV as text, coerce under a contract, and audit the conversion |
| [`iter_csv_safe`](#data_cleaner.iter_csv_safe) | Stream a large CSV in typed chunks with one audit report per chunk |
| [`combine_ingestion_reports`](#data_cleaner.combine_ingestion_reports) | Roll per-chunk ingestion reports into one whole-file report |
| [`read_excel_safe`](#data_cleaner.read_excel_safe) | Read one Excel sheet with the same guards and audit report |
| [`read_parquet_safe`](#data_cleaner.read_parquet_safe) | Read Parquet under a contract with the same audit report (PyArrow extra) |
| [`iter_parquet_safe`](#data_cleaner.iter_parquet_safe) | Stream a large Parquet file in audited record batches |
| [`combine_drift_reports`](#data_cleaner.combine_drift_reports) | Roll per-chunk drift reports into one run-level `TransformReport` |
| [`CleanerReport`](#data_cleaner.CleanerReport) | Combine profile, contract, validation, ingestion, and decisions for one batch |
| [`validate`](#data_cleaner.validate) | Evaluate reusable expectations against a DataFrame |
| [`audit_split`](#data_cleaner.audit_split) | Check a train/test split for leakage before training |

The usual path is `CleanerConfig` → `DataCleaner.fit()` → `DataCleaner.transform()`.
Contracts, validation, and the split audit are independent tools you can adopt
incrementally.

## Cleaning

::: data_cleaner.DataCleaner

::: data_cleaner.CleanerConfig

::: data_cleaner.CleaningDecision

## Contracts

::: data_cleaner.ColumnSpec

::: data_cleaner.DataContract

::: data_cleaner.DriftReport

::: data_cleaner.TransformReport

::: data_cleaner.combine_drift_reports

`Contract` is a shorthand alias for `DataContract`.

## Safe ingestion

`read_excel_safe` requires the optional `excel` extra (`openpyxl` for `.xlsx` and
`.xlsm`). `read_parquet_safe` and `iter_parquet_safe` require the optional
`parquet` extra (`pyarrow`). `read_csv_safe` and `iter_csv_safe` have no extra
dependency.

::: data_cleaner.IngestionReport

::: data_cleaner.IngestionError

::: data_cleaner.read_csv_safe

::: data_cleaner.iter_csv_safe

::: data_cleaner.combine_ingestion_reports

::: data_cleaner.read_excel_safe

::: data_cleaner.read_parquet_safe

::: data_cleaner.iter_parquet_safe

## Reporting

::: data_cleaner.CleanerReport

## Expectations and validation

::: data_cleaner.Expectation

::: data_cleaner.ValidationResult

::: data_cleaner.ValidationReport

::: data_cleaner.validate

::: data_cleaner.not_null

::: data_cleaner.unique

::: data_cleaner.in_set

::: data_cleaner.between

::: data_cleaner.matches_pattern

::: data_cleaner.has_dtype

::: data_cleaner.row_count_between

## Joins and integrity

::: data_cleaner.JoinDiagnosis

::: data_cleaner.diagnose_join

::: data_cleaner.ReferentialIntegrityReport

::: data_cleaner.check_referential_integrity

::: data_cleaner.DeduplicationReport

::: data_cleaner.deduplicate_by_business_key

## ML split audit

::: data_cleaner.SplitAudit

::: data_cleaner.audit_split

## Artifacts and fingerprints

::: data_cleaner.ArtifactCompatibilityError

::: data_cleaner.fingerprint_dataframe

::: data_cleaner.compare_fingerprints

::: data_cleaner.assert_schema_stable

## Profiling and output guards

::: data_cleaner.profile_dataframe

::: data_cleaner.dataset_summary

::: data_cleaner.drop_duplicate_rows

::: data_cleaner.assert_frame_clean

## API stability

The package follows semantic versioning for its public API.

| Tier | What it covers | Guarantee |
| --- | --- | --- |
| **Stable** | Every name in `data_cleaner.__all__` | No breaking change in the 2.x line |
| **Experimental** | Names documented as experimental | May change in a minor release; keep usage isolated |
| **Internal** | Modules prefixed with `_` and attributes ending in `_` | Not part of the public API; do not import or rely on them |

`data_cleaner.__all__` is the canonical public surface. If a name is not listed
there, it is not supported for direct import. The current release has no
experimental public names.

### Deprecation policy

- A public name is deprecated with a `DeprecationWarning` and a documented
  replacement.
- Deprecated names remain available for at least one minor release.
- Removals happen only in a major release, with a changelog entry and a migration
  note.
- Additive changes (new optional parameters, new reports, new helpers) ship in a
  minor release and keep existing calls working.

## API conventions

- All public names are re-exported from the package root, so `from data_cleaner
  import ...` is the supported import style.
- Configuration objects are immutable dataclasses; create a new one when options
  change.
- Learned state lives on the fitted `DataCleaner`, not on the input DataFrame.
- Reports expose structured attributes plus `to_markdown()` where available, so
  they can be logged or attached to a model review.
- The generated signatures show the exact accepted types. The guides include
  complete, runnable examples for the common paths.
