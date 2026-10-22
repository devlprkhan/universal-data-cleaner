---
description: Leak-safe data cleaning for pandas and scikit-learn.
---

<div class="hero" markdown>

# Clean data. Keep the leak out.

Universal Data Cleaner is a scikit-learn-compatible transformer that learns
cleaning rules from training data only — then applies them consistently to test
data and production batches.

[Get started](quickstart.md){ .md-button .md-button--primary }
[Audit a split](ml-split-audit.md){ .md-button }

</div>

## Two ways to stop leakage

<div class="grid cards" markdown>

-   :material-shield-check:{ .lg .middle } **Leak-safe cleaning**

    ---

    Fit imputers, outlier bounds, category rules, and datetime expansion on
    training data. Reuse those exact rules forever.

    [:octicons-arrow-right-24: Leak-safe workflow](leak-safe-workflow.md)

-   :material-magnify-scan:{ .lg .middle } **Train/test split audit**

    ---

    Catch duplicate rows, shared groups, temporal overlap, target leakage, and
    distribution shift before you train a model.

    [:octicons-arrow-right-24: ML split audit](ml-split-audit.md)

-   :material-clipboard-check-outline:{ .lg .middle } **Contracts & drift**

    ---

    Declare schema expectations, infer a contract from training data, and get a
    drift report on every transform.

    [:octicons-arrow-right-24: Contracts & drift](contracts.md)

-   :material-link-variant:{ .lg .middle } **Joins & validation**

    ---

    Diagnose key cardinality, orphan rows, duplicate business keys, and
    expectation failures without surprises.

    [:octicons-arrow-right-24: Validation, joins & dedup](validation-joins.md)

</div>

## Install

=== "pip"

    ```bash
    pip install universal-data-cleaner
    ```

=== "uv"

    ```bash
    uv add universal-data-cleaner
    ```

The distribution name is `universal-data-cleaner`; the import name is
`data_cleaner`.

## A first cleaner

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
```

`fit()` learns medians, modes, outlier bounds, category values, and datetime
rules from `train`. `transform()` applies the stored rules — it never re-learns
from the frame you pass in.

## Why not just use pandas?

Pandas is excellent at expressing a cleaning operation once. The hard part is
doing it **twice with the same parameters**: once for training and once for
inference. This library keeps those parameters in a fitted object, serializes
them, and exposes the decisions it made.

<div class="grid cards" markdown>

-   :material-lock-check-outline:{ .lg .middle } **No test-set peeking**

    ---

    Medians, modes, and bounds come from training data only.

-   :material-clipboard-list-outline:{ .lg .middle } **Auditable by default**

    ---

    `decision_log()`, manifests, and fingerprints explain what changed and why.

-   :material-pipe:{ .lg .middle } **Pipeline-native**

    ---

    Works with scikit-learn `Pipeline`, `clone`, and `get_feature_names_out`.

-   :material-database-check-outline:{ .lg .middle } **Artifact-safe**

    ---

    Save and load fitted cleaners with version checks and embedded metadata.

</div>

## What's inside

- Numeric coercion, median / mean / constant imputation, and IQR capping
- Categorical mode / constant imputation with a keep-or-fill unseen policy
- Boolean coercion and imputation
- Datetime parsing plus calendar feature extraction
- Optional missing-value indicators and constant-column dropping
- Declarative contracts, inferred contracts, and drift reports
- Expectations, join diagnostics, referential integrity, and business-key dedup
- Train/test split audits for duplicate, group, temporal, and target leakage
- Stable fingerprints and JSON-serializable manifests

Ready to try it? Start with the [quickstart](quickstart.md), or read the
[leak-safe workflow](leak-safe-workflow.md) first.
