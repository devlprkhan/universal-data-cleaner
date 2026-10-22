# Quickstart

Get from a messy DataFrame to a fitted, reusable cleaner in a few minutes.
{: .lead }

## Install

=== "pip"

    ```bash
    pip install universal-data-cleaner
    ```

=== "uv"

    ```bash
    uv add universal-data-cleaner
    ```

=== "From source"

    ```bash
    git clone https://github.com/devlprkhan/universal-data-cleaner.git
    cd universal-data-cleaner
    uv sync
    ```

The distribution is `universal-data-cleaner`; the import is `data_cleaner`.

```python
from data_cleaner import CleanerConfig, DataCleaner
```

## Your first cleaner

```python
import pandas as pd
from data_cleaner import CleanerConfig, DataCleaner

train = pd.DataFrame(
    {
        "age": [34, 41, None, 29],
        "salary": [70_000, 82_000, 91_000, 55_000],
        "dept": ["IT", "HR", "IT", None],
        "joined": pd.to_datetime(
            ["2022-01-03", "2021-11-20", "2023-04-01", "bad-date"],
            format="mixed",
            errors="coerce",
        ),
    }
)

config = CleanerConfig(
    datetime_columns=("joined",),
    add_missing_indicators=True,
    drop_constant_columns=True,
)

cleaner = DataCleaner(config).fit(train)
train_clean = cleaner.transform(train)
```

`train_clean` now has:

- numeric columns imputed with the training median
- categorical columns imputed with the training mode
- `joined` replaced by calendar features
- missing indicators for `age`, `dept`, and `joined`
- the same column order every time

`train_clean` is a new DataFrame; `train` itself is not modified.

## What `fit` and `transform` mean

| Method | What it does | Should it see test data? |
| --- | --- | --- |
| `fit(X_train)` | Learns medians, modes, bounds, categories, and schema | **No** |
| `transform(X)` | Applies the stored rules without learning | Yes, any batch |
| `fit_transform(X_train)` | `fit(X_train).transform(X_train)` | Training only |

The central rule: **call `fit` once on training data, then only call
`transform` everywhere else.**

## Reuse it in a scikit-learn pipeline

```python
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

preprocess = ColumnTransformer(
    [
        ("num", StandardScaler(), ["age", "salary", "joined__year"]),
        ("cat", OneHotEncoder(handle_unknown="ignore"), ["dept"]),
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

Because `DataCleaner` implements the scikit-learn estimator interface,
`Pipeline`, `clone`, and cross-validation work as expected.

!!! note "Constant columns and cross-validation"

    With `drop_constant_columns=True`, a generated calendar feature can be
    constant inside a training fold and get dropped. If a downstream step
    hard-codes that feature, set `drop_constant_columns=False` or select the
    cleaner's output columns dynamically.

## Save the fitted cleaner

```python
cleaner.save("artifacts/data_cleaner.joblib")
restored = DataCleaner.load("artifacts/data_cleaner.joblib")

X_new_clean = restored.transform(X_new)
```

The artifact includes the fitted configuration, learned state, manifest, and
training fingerprint. Version checks catch incompatible artifacts.

## Inspect what happened

```python
cleaner.cleaning_summary()  # per-column before/after summary
cleaner.outlier_summary()  # IQR bounds and clipped counts
cleaner.decision_log()  # every learned or configured decision
cleaner.drift_report()  # findings from the last transform
```

## Where to go next

<div class="doc-links" markdown>
<div markdown>
<p class="doc-links__title">Understand the contract</p>

- [Leak-safe workflow](leak-safe-workflow.md): the fit/transform contract and the mistakes it prevents.
- [Cleaning data](cleaning.md): every configuration option and what it changes.
</div>
<div markdown>
<p class="doc-links__title">Check the inputs</p>

- [ML split audit](ml-split-audit.md): duplicates, group leakage, temporal leakage, and target leakage.
- [Validation, joins & dedup](validation-joins.md): expectations, join diagnostics, and business-key dedup.
</div>
<div markdown>
<p class="doc-links__title">Ship the rules</p>

- [Artifacts & reproducibility](artifacts.md): decisions, manifests, fingerprints, and save/load.
- [Production guide](production.md): strict contracts, drift policies, and a deployment checklist.
</div>
</div>
