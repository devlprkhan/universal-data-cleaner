"""Universal Data Cleaner — production-oriented tabular cleaning toolkit.

The package is intentionally dependency-light:

- pandas + numpy for data handling
- scikit-learn base classes for Pipeline / clone compatibility
- joblib for artifact persistence

The public API is re-exported here so ``import data_cleaner`` keeps working
exactly as it did when the library shipped as a single module.
"""

from __future__ import annotations

from ._version import __version__
from .artifacts import (
    assert_schema_stable,
    compare_fingerprints,
    fingerprint_dataframe,
)
from .cleaner import ArtifactCompatibilityError, DataCleaner
from .config import CleanerConfig
from .contract import (
    ColumnSpec,
    Contract,
    DataContract,
    DriftReport,
    TransformReport,
    combine_drift_reports,
)
from .decisions import CleaningDecision
from .ingestion import (
    IngestionError,
    IngestionReport,
    combine_ingestion_reports,
    iter_csv_safe,
    iter_parquet_safe,
    read_csv_safe,
    read_excel_safe,
    read_parquet_safe,
)
from .integration import (
    DeduplicationReport,
    JoinDiagnosis,
    ReferentialIntegrityReport,
    check_referential_integrity,
    deduplicate_by_business_key,
    diagnose_join,
)
from .ml_audit import SplitAudit, audit_split
from .profiling import (
    assert_frame_clean,
    dataset_summary,
    drop_duplicate_rows,
    profile_dataframe,
)
from .reporting import CleanerReport
from .validation import (
    Expectation,
    ValidationReport,
    ValidationResult,
    between,
    has_dtype,
    in_set,
    matches_pattern,
    not_null,
    row_count_between,
    unique,
    validate,
)

__all__ = [
    "ArtifactCompatibilityError",
    "CleanerConfig",
    "CleanerReport",
    "CleaningDecision",
    "ColumnSpec",
    "Contract",
    "DataCleaner",
    "DataContract",
    "DeduplicationReport",
    "DriftReport",
    "Expectation",
    "IngestionError",
    "IngestionReport",
    "JoinDiagnosis",
    "ReferentialIntegrityReport",
    "SplitAudit",
    "TransformReport",
    "ValidationReport",
    "ValidationResult",
    "__version__",
    "assert_frame_clean",
    "assert_schema_stable",
    "audit_split",
    "between",
    "check_referential_integrity",
    "combine_drift_reports",
    "combine_ingestion_reports",
    "compare_fingerprints",
    "dataset_summary",
    "deduplicate_by_business_key",
    "diagnose_join",
    "drop_duplicate_rows",
    "fingerprint_dataframe",
    "has_dtype",
    "in_set",
    "iter_csv_safe",
    "iter_parquet_safe",
    "matches_pattern",
    "not_null",
    "profile_dataframe",
    "read_csv_safe",
    "read_excel_safe",
    "read_parquet_safe",
    "row_count_between",
    "unique",
    "validate",
]
