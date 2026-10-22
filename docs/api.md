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

`Contract` is a shorthand alias for `DataContract`.

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

::: data_cleaner.fingerprint_dataframe

::: data_cleaner.compare_fingerprints

::: data_cleaner.assert_schema_stable

## Profiling and output guards

::: data_cleaner.profile_dataframe

::: data_cleaner.dataset_summary

::: data_cleaner.drop_duplicate_rows

::: data_cleaner.assert_frame_clean

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
