# API reference

This page is generated from the package docstrings. All names are importable
directly from `data_cleaner`.

```python
from data_cleaner import DataCleaner, audit_split, validate
```

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
