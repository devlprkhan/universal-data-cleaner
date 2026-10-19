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
from .cleaner import DataCleaner
from .config import CleanerConfig
from .contract import ColumnSpec, DataContract, DriftReport
from .profiling import (
    assert_frame_clean,
    dataset_summary,
    drop_duplicate_rows,
    profile_dataframe,
)

__all__ = [
    "CleanerConfig",
    "ColumnSpec",
    "DataCleaner",
    "DataContract",
    "DriftReport",
    "__version__",
    "assert_frame_clean",
    "dataset_summary",
    "drop_duplicate_rows",
    "profile_dataframe",
]
