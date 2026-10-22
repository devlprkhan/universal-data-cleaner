# Validation, joins & dedup

Cleaning a frame is only part of data quality. These helpers check values,
diagnose joins, verify references, and deduplicate business keys without
surprises.

## Expectations

Expectations are small, reusable checks. `validate()` evaluates them and returns
a `ValidationReport`.

```python
from data_cleaner import (
    between,
    has_dtype,
    in_set,
    matches_pattern,
    not_null,
    row_count_between,
    unique,
    validate,
)

report = validate(
    orders_new,
    [
        not_null("order_id"),
        unique("order_id"),
        in_set("status", ["new", "paid", "shipped"]),
        between("amount", 0, 100_000),
        matches_pattern("email", r"[^@]+@[^@]+\.[^@]+"),
        has_dtype("created_at", "datetime"),
        row_count_between(min_rows=1),
    ],
)

print(report.to_markdown())
report.raise_if_failed()
```

| Factory | Checks |
| --- | --- |
| `not_null(column)` | No missing values |
| `unique(column)` | Non-null values are unique |
| `in_set(column, values)` | Non-null values belong to the allowed set |
| `between(column, lower, upper, inclusive=True)` | Numeric values fall inside the bounds |
| `matches_pattern(column, pattern)` | Non-null strings fully match a regex |
| `has_dtype(column, dtype)` | Broad kind or exact pandas dtype matches |
| `row_count_between(min_rows, max_rows)` | The frame has an acceptable number of rows |

Every factory accepts `severity="error"` or `severity="warning"`. Warning
failures are reported but do not make the report fail.

```python
report.success  # True when no error-severity expectation failed
report.failures  # every failed expectation, including warnings
report.results  # all evaluated expectations
report.has_warnings
report.to_markdown()
report.raise_if_failed()
```

`has_dtype()` accepts broad kinds (`numeric`, `categorical`, `boolean`,
`datetime`) or exact dtypes such as `float64`.

## Validate against a contract

Contracts can validate a batch directly and return the same report type:

```python
from data_cleaner import DataContract

contract = DataContract.from_frame(orders_train)
result = contract.validate(orders_new)

result.success
result.failures.to_markdown()
result.raise_if_failed()
```

See [Contracts & drift](contracts.md) for the full `ColumnSpec` reference.

## Join diagnostics

Joins go wrong quietly: a duplicate key multiplies rows, a null key drops a
match, or a “1:1” assumption turns out to be “1:m”.

```python
from data_cleaner import diagnose_join

report = diagnose_join(orders, customers, on="customer_id", how="left")

report.safe
report.cardinality  # e.g. "1:m"
report.row_multiplier  # output rows / left rows
report.unmatched_left
report.unmatched_right
report.warnings
report.raise_if_unsafe()
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `on` | required | Key column or columns |
| `how` | `"left"` | `left`, `right`, `inner`, or `outer` |
| `validate` | `"1:1"` | Expected maximum cardinality: `1:1`, `1:m`, `m:1`, `m:m`, or `None` |

`diagnose_join` inspects only key columns. It reports duplicate keys, null keys,
unmatched rows, cardinality, and the actual output row count without
materializing the full join.

`safe` is false when the join violates the requested cardinality, multiplies rows
on the preserved side of a left/right join, or has null keys.

## Referential integrity

Check that every non-null child key exists in the parent table:

```python
from data_cleaner import check_referential_integrity

report = check_referential_integrity(
    orders,
    customers,
    child_key="customer_id",
    parent_key="id",
)

report.orphan_rows
report.orphan_keys  # up to 10 distinct examples
report.orphan_key_count  # total distinct orphan keys
report.raise_if_invalid()
```

| Option | Default | Effect |
| --- | --- | --- |
| `allow_null_keys` | `True` | Null child keys are reported but allowed |
| `parent_key` | same as `child_key` | Parent key column(s) |

Duplicate parent keys make the relationship invalid because the parent key is not
a unique reference target.

## Business-key deduplication

Deduplicate by a meaningful key while keeping an audit trail of what was removed:

```python
from data_cleaner import deduplicate_by_business_key

deduped, report = deduplicate_by_business_key(
    orders,
    key="order_id",
    keep="last",
    tie_breaker="updated_at",
)

report.removed_rows
report.removed
report.duplicate_keys
report.null_key_rows
report.to_markdown()
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `key` | required | Business key column or columns |
| `keep` | `"first"` | Keep the first or last row per key |
| `tie_breaker` | `None` | Column(s) used to order rows within each key |

`tie_breaker` prefers non-null values. The returned frame preserves the input row
order and index, and the input frame is never mutated.

## Profiling and output guards

Quick inspection helpers:

```python
from data_cleaner import (
    assert_frame_clean,
    dataset_summary,
    drop_duplicate_rows,
    profile_dataframe,
)

profile_dataframe(df)  # per-column missing/type/cardinality profile
dataset_summary(df)  # row/column/missing/duplicate summary
drop_duplicate_rows(df)  # explicit duplicate removal
assert_frame_clean(df)  # guard against missing/infinite output values
```

`assert_frame_clean()` is useful at the end of a preprocessing pipeline: it
raises when the cleaned output still contains missing or infinite values.
