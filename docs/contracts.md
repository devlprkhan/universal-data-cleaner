# Contracts & drift

A contract makes the assumptions about your data explicit. The cleaner can then
check those assumptions on every transform and report drift instead of silently
producing a different schema.
{: .lead }

## A small contract

```python
from data_cleaner import CleanerConfig, ColumnSpec, DataCleaner, DataContract

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id"),
        ColumnSpec("age", role="numeric", min_value=0, max_value=120),
        ColumnSpec("plan", role="category", allowed_values=("free", "pro", "team")),
        ColumnSpec("email", role="text", pattern=r"[^@]+@[^@]+\.[^@]+"),
        ColumnSpec("notes", role="ignore"),
    ],
    strict=True,
)

cleaner = DataCleaner(CleanerConfig(contract=contract, on_drift="warn"))
cleaner.fit(X_train)

X_test_clean = cleaner.transform(X_test)
print(cleaner.drift_report())
```

The input frame is still cleaned. Drift is **reported**, not repaired.

## Column roles

| Role | Meaning |
| --- | --- |
| `numeric` | A measurement; numeric coercion, imputation, and outlier capping |
| `category` | A categorical value; mode/constant imputation and unseen policy |
| `boolean` | A boolean value; boolean coercion and imputation |
| `datetime` | A timestamp; parsed and expanded into calendar features |
| `id` | An identifier; treated as text, never numeric-imputed or capped |
| `text` | Free text; treated as categorical text and protected from unseen replacement |
| `ignore` | Dropped from the output and skipped by contract checks |

`None` means “infer from the dtype.” Roles accept common aliases such as
`measure`, `categorical`, `string`, `bool`, `date`, `identifier`, and `drop`.

## `ColumnSpec` reference

| Field | Default | Purpose |
| --- | --- | --- |
| `name` | required | Column name |
| `role` | `None` | Semantic role from the table above |
| `dtype` | `None` | Broad kind or exact dtype to expect |
| `nullable` | `True` | Whether missing values are allowed |
| `unique` | `False` | Whether non-null values must be unique |
| `allowed_values` | `None` | Allowed category values |
| `min_value` | `None` | Inclusive lower bound for numeric values |
| `max_value` | `None` | Inclusive upper bound for numeric values |
| `pattern` | `None` | Full-match regular expression for string values |
| `date_format` | `None` | Optional date format hint |
| `preserve_leading_zeros` | `False` | Keep identifier values as strings |
| `severity` | `"error"` | Severity of this spec's contract findings |

## Drift checks

| Check | Severity | Trigger |
| --- | --- | --- |
| `missing_column` | spec severity | A declared column is absent |
| `unexpected_column` | warning | `strict=True` and the frame has an undeclared column |
| `dtype_change` | spec severity | The column's broad kind changed |
| `unexpected_missing` | spec severity | A non-nullable column has missing values |
| `unexpected_category` | spec severity | A value falls outside `allowed_values` |
| `value_out_of_range` | spec severity | A numeric value falls outside the declared bounds |
| `pattern_mismatch` | spec severity | A string does not fully match `pattern` |
| `duplicate_values` | spec severity | `unique=True` and duplicate non-null values exist |

Identifier and text columns are allowed to arrive as either numeric-looking or
object dtype; that is not reported as `dtype_change`.

## Drift policy

```python
CleanerConfig(on_drift="warn")
```

| Value | Behavior |
| --- | --- |
| `"warn"` | Log the report and continue (default) |
| `"raise"` | Raise `ValueError` when any error-severity finding exists |
| `"ignore"` | Record findings in `drift_report()` without logging |

```python
report = cleaner.drift_report()

if not report.empty:
    print(report[["column", "check", "severity", "message"]])
```

`DriftReport` exposes `findings`, `has_drift`, `errors`, `warnings`, `summary()`,
`to_markdown()`, and `raise_if_invalid()`.

## Infer a contract automatically

If you do not pass a contract and `infer_contract=True` (the default), the
cleaner infers a conservative contract from the training schema:

```python
cleaner = DataCleaner()
cleaner.fit(X_train)

contract = cleaner.fitted_contract()
```

You can also infer one explicitly:

```python
contract = DataContract.from_frame(X_train, strict=True)
```

Inference captures column names, broad kinds, and nullability. Add explicit
specs when you need allowed values, ranges, patterns, or uniqueness checks.

## Validate a batch directly

`DataContract.validate()` returns the same report type used by the expectations
API:

```python
result = contract.validate(X_new)

result.success
result.failures
result.to_markdown()
result.raise_if_failed()
```

Use `contract.check(X_new)` when you specifically want the `DriftReport` with
its `expected` / `actual` columns.

## Serialize the contract

Contracts are JSON-serializable and can be versioned with the model:

```python
payload = contract.to_json()
restored = DataContract.from_json(payload)
```

YAML support is optional and requires `pyyaml`:

```bash
pip install pyyaml
```

```python
contract.to_yaml()
DataContract.from_yaml(payload)
```

Store the contract next to the fitted cleaner so training and serving agree on
roles, bounds, and allowed values.

## Production tips

- Set `on_drift="raise"` when an unexpected schema change should stop the job.
- Use `role="id"` for identifiers so they are never treated as measurements.
- Use `role="ignore"` for operational columns you do not want in the output.
- Keep `strict=False` if upstream systems may add harmless columns; otherwise
  `strict=True` surfaces them as warnings.
- Prefer explicit specs for anything a model depends on: ranges, categories,
  regexes, and uniqueness.
