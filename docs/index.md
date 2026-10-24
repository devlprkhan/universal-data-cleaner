---
description: Leak-safe data cleaning for pandas and scikit-learn.
hide:
  - toc
---

<div class="hero" markdown>
<div class="hero__copy" markdown>

# Same cleaning rules.<br>Every batch.

A scikit-learn transformer for pandas. It fits imputation, outlier, category,
and schema rules on X_train, then reuses them unchanged for validation, test,
and production.

No test-set peeking, no re-learning, and no silent schema drift. Every learned
or configured decision stays inspectable.

<div class="hero__install" data-copy-text="pip install universal-data-cleaner">
<code>pip install universal-data-cleaner</code>
<button class="hero__install-copy" type="button" aria-label="Copy install command">Copy</button>
</div>

<div class="hero__actions">
<a class="md-button md-button--primary" href="quickstart/">Start the quickstart <span aria-hidden="true">→</span></a>
</div>

<div class="hero__secondary">
<a href="leak-safe-workflow/">See the leak-safe workflow</a>
</div>

</div>
<div class="hero__code" markdown>
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
</div>
</div>

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
| Safety | Declarative and inferred contracts, drift reports, expectations, join diagnostics, referential integrity, business-key dedup, and train/test split audits |
| Operations | Decision logs, manifests, stable fingerprints, joblib save / load, and scikit-learn `Pipeline`, `clone`, and `get_feature_names_out` compatibility |

## Built for the part after the notebook

<div class="feature-grid" markdown>
<div class="feature" markdown>
### Leak-safe by construction

Medians, modes, bounds, and category values come from training data only. The
same fitted object serves every later batch.
</div>
<div class="feature" markdown>
### Auditable decisions

`decision_log()` records what changed and why. Manifests and fingerprints make
the fitted rules reviewable and reproducible.
</div>
<div class="feature" markdown>
### Pipeline-native

`DataCleaner` implements the scikit-learn estimator interface, so it composes
with `Pipeline`, `clone`, and cross-validation.
</div>
<div class="feature" markdown>
### Artifact-safe

Save and load fitted cleaners with version checks and embedded metadata. Keep
the contract and manifest next to the model.
</div>
</div>

## Documentation map

<div class="doc-links" markdown>
<div markdown>
<p class="doc-links__title">Start here</p>

- [Quickstart](quickstart.md): install, fit, and transform.
- [Leak-safe workflow](leak-safe-workflow.md): the fit/transform contract.
</div>
<div markdown>
<p class="doc-links__title">Guides</p>

- [Cleaning data](cleaning.md): every configuration option.
- [Contracts & drift](contracts.md): make schema assumptions explicit.
- [Validation, joins & dedup](validation-joins.md): check batches and keys.
- [ML split audit](ml-split-audit.md): find contaminated splits.
- [Production guide](production.md): deploy the same rules safely.
</div>
<div markdown>
<p class="doc-links__title">Reference</p>

- [API reference](api.md): generated from the package docstrings.
- [Artifacts & reproducibility](artifacts.md): logs, manifests, fingerprints.
- [Changelog](changelog.md): release notes and behavior changes.
</div>
</div>

<div class="home-cta" markdown>
<div class="home-cta__copy" markdown>

## Start with the quickstart

Install the package, fit one cleaner, and transform a test batch without
re-learning. The quickstart is the shortest path from a messy DataFrame to a
reusable preprocessing step.

</div>
<div class="home-cta__action" markdown>
[Open the quickstart](quickstart.md){ .md-button .md-button--primary }
</div>
</div>
