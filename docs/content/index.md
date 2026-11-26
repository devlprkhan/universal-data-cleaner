---
title: "Intro"
description: "Leak-safe data cleaning for pandas and scikit-learn: rules fit once on training data and reused unchanged for validation, test, and production."
---

<p class="lead">Same cleaning rules. Every batch.</p>

A scikit-learn transformer for pandas. It fits imputation, outlier, category, and
schema rules on `X_train`, then reuses them unchanged for validation, test, and
production. No test-set peeking, no re-learning, and no silent schema drift.

=== "fit.py"

    ```python
    from data_cleaner import DataCleaner

    cleaner = DataCleaner()
    cleaner.fit(X_train)

    # Fitted on X_train only:
    # medians, categories, bounds, schema
    train_clean = cleaner.transform(X_train)
    test_clean = cleaner.transform(X_test)

    # Reuse the fitted rules in production.
    prod_clean = cleaner.transform(X_prod)

    cleaner.decision_log()
    ```

=== "transform.py"

    ```python
    # Reuse the cleaner fitted on train.
    # transform() never learns from data.
    test_clean = cleaner.transform(X_test)
    prod_clean = cleaner.transform(X_prod)

    # Review every learned decision.
    cleaner.decision_log()
    ```

`fit()` learns from training data. `transform()` returns a new frame and never
mutates the caller's DataFrame.

## Why this exists

Pandas is excellent at expressing a cleaning operation once. The hard part is
doing it **twice with the same parameters**: once for training and once for
inference.

```python title="leak_safe.py"
# This learns a different rule for every batch, including the test set.
df["age"] = df["age"].fillna(df["age"].median())

# This learns once on training data, then reuses the stored rule.
cleaner = DataCleaner(CleanerConfig()).fit(X_train)
X_test_clean = cleaner.transform(X_test)
```

The fitted cleaner holds the medians, modes, IQR bounds, category values, and
schema. `transform()` applies them without learning from the frame you pass in.

## Install

=== "pip"

    ```bash
    pip install universal-data-cleaner
    ```

=== "uv"

    ```bash
    uv add universal-data-cleaner
    ```

The distribution is `universal-data-cleaner`; the import is `data_cleaner`.

## A first cleaner

```python title="clean.py"
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
print(cleaner.cleaning_summary())
```

`fit()` learns from `train`. `transform()` returns a new frame and never mutates
the caller's DataFrame. The same fitted object is safe for validation, test, and
production batches.

## The fit/transform contract

| Stage | Call | Learned from | Safe for test data? |
| --- | --- | --- | --- |
| Training | `cleaner.fit(X_train)` | `X_train` only | — |
| Training output | `cleaner.transform(X_train)` | Stored training state | — |
| Evaluation | `cleaner.transform(X_test)` | Stored training state | Yes |
| Serving | `cleaner.transform(X_new)` | Stored training state | Yes |

The rule is simple: **fit once on training data, then only transform everywhere
else.** Do not create a second cleaner for test or production data.

## What it handles

| Area | Included |
| --- | --- |
| Cleaning | Numeric coercion, median / mean / constant imputation, IQR capping, categorical mode / constant imputation, boolean coercion, datetime parsing and calendar features, missing indicators, constant-column dropping |
| Ingestion | Safe CSV, Excel, and optional Parquet reads with contract-driven coercion, identifier protection, date/boolean guards, and an ingestion report |
| Reporting | `CleanerReport` combining profile, contract drift, validation, ingestion, and decisions, plus a `data-cleaner audit` CLI |
| Validation | Expectations plus cross-column, conditional, grouped, combination-uniqueness, and arithmetic rules with bounded, privacy-safe row diagnostics |
| Drift | Statistical drift against a reusable reference profile: PSI, Wasserstein distance, missingness and category deltas |
| Operations | Decision logs, manifests, stable fingerprints, joblib save / load, and scikit-learn `Pipeline`, `clone`, and `get_feature_names_out` compatibility |

## Built for the part after the notebook

<CardGroup cols={2}>
<Card title="Leak-safe by construction" href="/leak-safe-workflow/">Medians, modes, bounds, and category values come from training data only. The same fitted object serves every later batch.</Card>
<Card title="Auditable decisions" href="/artifacts/">`decision_log()` records what changed and why. Manifests and fingerprints make the fitted rules reviewable and reproducible.</Card>
<Card title="Pipeline-native" href="/quickstart/">`DataCleaner` implements the scikit-learn estimator interface, so it composes with `Pipeline`, `clone`, and cross-validation.</Card>
<Card title="Artifact-safe" href="/production/">Save and load fitted cleaners with version checks and embedded metadata. Keep the contract and manifest next to the model.</Card>
</CardGroup>

## Start with the quickstart

Install the package, fit one cleaner, and transform a test batch without
re-learning. The quickstart is the shortest path from a messy DataFrame to a
reusable preprocessing step: start with the [quickstart](/quickstart/).
