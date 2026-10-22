# Leak-safe workflow

The library exists because of one deceptively simple bug.

## The bug

```python
# Do this before splitting and you have already leaked.
df["age"] = df["age"].fillna(df["age"].median())
```

That median was computed from every row — including the rows that later become
the test set. The model gets a small peek at the evaluation data. The score looks
better than it should.

The same code also breaks at inference time. When a new batch arrives, calling
`fillna(df["age"].median())` again learns a **different** median from that batch.
The training preprocessing and the serving preprocessing are no longer the same
transformation.

## The fix

Split first. Fit the cleaner on training data only. Transform every batch with
the stored rules.

```python
from sklearn.model_selection import train_test_split
from data_cleaner import DataCleaner, CleanerConfig

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

cleaner = DataCleaner(CleanerConfig()).fit(X_train)

X_train_clean = cleaner.transform(X_train)
X_test_clean = cleaner.transform(X_test)
```

`transform(X_test)` does **not** compute a new median. It uses the median learned
during `fit(X_train)`.

## Fit once, transform forever

| Stage | Call | Learned from | Safe for test data? |
| --- | --- | --- | --- |
| Training | `cleaner.fit(X_train)` | `X_train` only | — |
| Training output | `cleaner.transform(X_train)` | Stored training state | — |
| Evaluation | `cleaner.transform(X_test)` | Stored training state | Yes |
| Serving | `cleaner.transform(X_new)` | Stored training state | Yes |

The same fitted object must be used for every batch. Do not create a new
`DataCleaner` for test data or production data.

## What gets learned

- numeric medians or means, and constant fill values
- categorical modes or constant fill values
- IQR outlier bounds and clipping thresholds
- boolean fill values
- which columns were constant during training
- datetime feature expansion rules
- category values used by the unseen-category policy
- the training schema and contract

All of it is stored in the fitted object and in saved artifacts.

## What `transform` guarantees

- It never fits or re-learns from the input.
- It never mutates the caller's DataFrame.
- It never drops inference rows.
- It preserves the documented output column order.
- It raises a clear error when required columns are missing.
- It records drift findings instead of silently changing the schema.

## Common mistakes

!!! danger "Fitting before splitting"

    ```python
    cleaner = DataCleaner().fit(df)  # sees test rows
    X_train, X_test = train_test_split(df)  # too late
    ```

    Split first, then fit on `X_train`.

!!! danger "Re-fitting on test data"

    ```python
    cleaner = DataCleaner().fit(X_test)  # wrong
    X_test_clean = cleaner.transform(X_test)
    ```

    Use the cleaner fitted on `X_train`, or load the saved training artifact.

!!! warning "Using the target as a feature"

    Do not pass the target column to the cleaner. It will happily learn
    statistics from it and put it in the output.

!!! warning "Forgetting identifiers"

    Mark IDs and free-text columns with a contract role so they are not treated
    as numeric measurements. See [Contracts & drift](contracts.md).

## Save and restore the whole preprocessing step

```python
cleaner.save("artifacts/data_cleaner.joblib")

# Later, in a different process:
restored = DataCleaner.load("artifacts/data_cleaner.joblib")
X_new_clean = restored.transform(X_new)
```

The artifact contains the fitted state and a manifest. `load(verify_version=True)`
is the default and refuses artifacts written by an incompatible version.

## Add a split audit before training

Cleaning correctly is only half of leak safety. The split itself can be
contaminated: duplicate rows, the same customer on both sides, future rows in
training, or a feature that is a copy of the target.

```python
from data_cleaner import audit_split

audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    groups=customer_ids,  # combined train + test labels
    time_col="event_time",
    id_cols=["customer_id"],
)

if not audit.valid:
    print(audit.summary())
    audit.raise_if_invalid()
```

Run this **before** training and fix the split, not the model. See the
[ML split audit guide](ml-split-audit.md).
