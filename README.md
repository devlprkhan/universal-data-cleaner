# Universal Data Cleaner

[![CI](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Managed with uv](https://img.shields.io/badge/managed%20with-uv-6f42c1.svg)](https://docs.astral.sh/uv/)

A small, production-oriented tabular cleaning transformer for pandas + scikit-learn.

It is designed for the part of an ML pipeline that is easy to get wrong: cleaning
training data and inference data with **exactly the same learned rules**.

## Why this exists

A common notebook pattern is:

```python
df["Age"] = df["Age"].fillna(df["Age"].median())
```

That leaks information when it is run before the train/test split, and it silently
breaks at inference time because the median is recomputed on the new batch.

`DataCleaner` fits on training data, stores the learned values, and reuses them in
`transform()` and in saved artifacts.

## What it handles

- numeric coercion and median / mean / constant imputation
- optional IQR outlier capping (learned from training data only)
- categorical mode / constant imputation
- optional unseen-category policy: keep or replace
- boolean coercion and imputation
- datetime parsing plus calendar feature extraction
- optional missing-value indicator columns
- optional constant-column dropping
- stable output schema and column order
- joblib save / load with artifact versioning
- scikit-learn `Pipeline`, `clone`, and `get_feature_names_out` compatibility

The cleaner never mutates the input DataFrame and never drops inference rows.

## Setup with uv

```bash
git clone https://github.com/devlprkhan/universal-data-cleaner.git
cd universal-data-cleaner
uv sync
```

Run the test suite:

```bash
uv run pytest -q
```

Open the reference notebook:

```bash
uv run jupyter lab Universal_Data_Cleaner.ipynb
```

The notebook is also verified headlessly in CI-style environments with
`nbclient`; both tools are in the `dev` dependency group.

### Install directly from GitHub

```bash
uv add "git+https://github.com/devlprkhan/universal-data-cleaner.git"
# or
pip install "git+https://github.com/devlprkhan/universal-data-cleaner.git"
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
print(cleaner.cleaning_summary())
print(cleaner.outlier_summary())
```

For a column that should be numeric even though it arrived as dirty strings:

```python
config = CleanerConfig(
    numeric_columns=("salary",),          # force numeric parsing
    datetime_columns=("joined",),        # parse dates instead of treating them as categories
    unseen_category="keep",              # or "fill" to replace unseen labels
)
```

## Leak-safe workflow

```python
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

cleaner = DataCleaner(config).fit(X_train)

X_train_clean = cleaner.transform(X_train)
X_test_clean = cleaner.transform(X_test)   # uses train statistics only
```

Save the fitted cleaner with the model artifact:

```python
cleaner.save("artifacts/data_cleaner.joblib")
restored = DataCleaner.load("artifacts/data_cleaner.joblib")
```

## scikit-learn Pipeline

```python
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric = ["age", "salary", "joined__year"]
categorical = ["dept"]
boolean = []

preprocess = ColumnTransformer(
    [
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("bool", "passthrough", boolean),
    ],
    remainder="drop",
)

pipeline = Pipeline(
    [
        ("cleaner", DataCleaner(config)),
        ("features", preprocess),
        ("model", Ridge(alpha=1.0)),
    ]
)
pipeline.fit(X_train, y_train)
predictions = pipeline.predict(X_test)
```

## Public API

| Name | Purpose |
| --- | --- |
| `CleanerConfig` | Validated cleaning configuration |
| `DataCleaner` | Fit/transform cleaner with save/load |
| `profile_dataframe` | Column-level missing/type/cardinality profile |
| `dataset_summary` | Row/column/missing/duplicate summary |
| `drop_duplicate_rows` | Explicit duplicate removal helper |
| `assert_frame_clean` | Guard against missing/infinite output values |

## Important production notes

- Fit the cleaner **after** splitting and **only** on training data.
- Do not pass IDs, free-text notes, or the target column to the cleaner.
- Keep `DataSource`-style constant columns out of the model, or let
  `drop_constant_columns=True` remove them.
- `unseen_category="keep"` is the default because one-hot encoders with
  `handle_unknown="ignore"` can handle an unseen label safely.
- Datetime columns are replaced by calendar features. Their missing values are
  represented by the generated feature NaNs plus an optional missing indicator.
- IQR capping is skipped automatically when the IQR is zero, so constant or
  near-constant numeric columns are not accidentally destroyed.

## Project layout

```text
.
├── data_cleaner.py                    # reusable library module
├── Universal_Data_Cleaner.ipynb       # end-to-end reference workflow
├── tests/test_data_cleaner.py         # unit and integration tests
├── pyproject.toml                     # package metadata and dev tooling
├── uv.lock                            # reproducible dependency lock
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the local
setup, test command, and pull-request expectations.

## License

Released under the [MIT License](LICENSE).
