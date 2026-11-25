---
title: "Validation, joins & dedup"
description: "Expectations are small, reusable checks. validate evaluates them and returns a ValidationReport."
---

<p class="lead">Cleaning a frame is only part of data quality. These helpers check values, diagnose joins, verify references, and deduplicate business keys without surprises.</p>

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

## Cross-column, conditional, and grouped rules

Expectations check one column or the frame size. The rule layer covers the rest:
row predicates over several columns, rules that apply only when a condition
holds, and per-group checks. Rules implement the same `Validatable` protocol as
expectations, so they mix freely in one `validate()` call.

```python
from data_cleaner import (
    col,
    conditional,
    grouped,
    row_rule,
    sum_equals,
    unique_combination,
    validate,
)

report = validate(
    orders,
    [
        row_rule(
            col("shipped_at").ge(col("ordered_at")),
            name="shipped_after_ordered",
        ),
        conditional(col("status").eq("shipped"), not_null("shipped_at")),
        grouped("region", row_rule(col("total").gt(0))),
        unique_combination(["customer_id", "order_date"]),
        sum_equals(["subtotal", "tax"], "total", tolerance=0.01),
    ],
)
```

| Helper | Checks |
| --- | --- |
| `row_rule(condition)` | Every row satisfies the condition |
| `conditional(condition, rule)` | `rule` holds for the rows matching `condition`; other rows are not evaluated |
| `grouped(by, rule)` | `rule` holds independently inside each group |
| `unique_combination(columns)` | The combination of non-null keys is unique |
| `sum_equals(columns, target, tolerance=1e-9)` | The numeric sum of `columns` equals `target` per row |

Build conditions from `col(name)` with explicit methods:

```python
col("amount").gt(0)
col("status").isin(["new", "paid", "shipped"])
col("amount").between(0, 100_000, inclusive=False)
col("email").matches(r"[^@]+@[^@]+\.[^@]+")
col("shipped_at").isna()
```

Combine them with `&`, `|`, and `~`:

```python
condition = col("status").isin(["shipped", "delivered"]) & ~col("carrier").isna()
```

The comparison methods are `.eq`, `.ne`, `.lt`, `.le`, `.gt`, and `.ge`. Both
sides may be values or another `col(...)`. Using `==` or `!=` on `col()` raises
`TypeError` with a pointer to `.eq()` / `.ne()`; Python cannot intercept `and`,
`or`, and `not`, so use `&`, `|`, and `~`.

Rows where either operand is missing are skipped by comparisons, so missing data
does not fail a predicate unless you ask for it with `col(...).isna()`.
Membership, bounds, and pattern rules follow the same rule: non-null values are
checked.

`conditional()` passes when no row matches the condition and reports that
nothing was checked. `grouped()` reports the number of failing groups; group
labels are omitted by default, and `include_groups=True` lists up to `max_groups`
of them (default `10`) because labels can contain personal data.

### Write your own rule

`validate()` accepts any object with `name`, `column`, `severity`, and
`check(frame)`. `check()` returns one `ValidationResult` or a list of them, which
lets a custom rule emit several findings from one pass:

```python
import pandas as pd

from data_cleaner import ValidationResult, validate


class NoFutureDates:
    name = "no_future_dates"
    column = "created_at"
    severity = "error"

    def check(self, frame):
        later = frame["created_at"] > pd.Timestamp.now()
        return ValidationResult(
            self.name,
            self.column,
            not later.any(),
            self.severity,
            f"{int(later.sum())} row(s) are in the future",
            int(later.sum()),
        )


validate(orders, NoFutureDates())
```

`Expectation` and the built-in rules implement this protocol, so typed custom
rules and built-ins can be stored in the same list.

## Row diagnostics

When a rule fails, `ValidationReport.diagnose()` samples a bounded set of failing
rows. It is opt-in, per-rule bounded, and omits cell values by default.

```python
report = validate(orders, [not_null("email"), unique("order_id")])

diagnostics = report.diagnose(orders, limit=5)
diagnostics.rows  # expectation, column, row_position, index, value
diagnostics.truncated  # True when a rule had more failures than `limit`
diagnostics.skipped  # failing rules that cannot be attributed to individual rows
diagnostics.to_markdown()
```

| Option | Default | Effect |
| --- | --- | --- |
| `limit` | `5` | Maximum sampled rows per failing rule |
| `include_values` | `False` | Include the failing value for single-column rules |
| `include_index` | `True` | Include the frame index label for sampled rows |
| `max_value_length` | `32` | Truncate included values to this many characters |

Cell values are off by default because they may contain personal data, and even
when enabled they are truncated. Index labels are treated separately: they are
included by default because they point at the failing row, but pass
`include_index=False` when the index can contain identifiers. `row_position` is
the positional row number; `index` is the frame's index label or `None`.

Only failing rules are sampled. Frame-level checks (`has_dtype`,
`row_count_between`) and grouped rules cannot be attributed to individual rows,
so they are listed in `skipped` instead of being guessed at.

`diagnose()` does not modify the frame. A report produced from contract findings
has no rule sources, so `diagnose()` returns an empty sample for it.

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
materializing the full join. Work is bounded by the number of distinct key
combinations, so heavily duplicated keys cannot trigger a many-to-many
expansion or a memory spike.

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
