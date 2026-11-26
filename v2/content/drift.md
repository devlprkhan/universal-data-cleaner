---
title: "Statistical drift"
description: "policy = DriftPolicy reference = DriftProfile.from_frame"
---

<p class="lead">Schema drift asks whether the columns and dtypes still match. Statistical drift asks whether the *distribution* of the data changed. This layer compares a current batch against a stored reference summary using PSI, Wasserstein distance, missingness deltas, and category deltas, without keeping the reference rows.</p>

```python
from data_cleaner import DriftPolicy, DriftProfile

policy = DriftPolicy(psi_warning=0.10, psi_error=0.25, min_sample=200)
reference = DriftProfile.from_frame(X_train, policy=policy)

report = reference.compare(X_valid)
report.has_drift
report.drifted_columns
print(report.summary())
report.raise_if_drift()
```

Or compare two frames directly when you do not need a reusable profile:

```python
from data_cleaner import compare_distributions

report = compare_distributions(X_train, X_valid)
report.columns.to_markdown()
```

`compare_distributions()` is a thin wrapper around
`DriftProfile.from_frame()` and `DriftProfile.compare()`. Use the profile when
the same reference is compared with many batches: it is built once and can be
persisted.

## What is measured

Numeric and datetime columns get PSI and Wasserstein distance; categorical and
boolean columns get PSI plus per-category share deltas. Every column also gets a
missingness delta.

| Metric | Column types | Meaning |
| --- | --- | --- |
| PSI | all | Population Stability Index over reference quantile bins, including a missing bucket |
| Wasserstein | numeric, datetime | Approximate 1-D distance between the bounded reference quantiles and the current quantiles at the same probabilities |
| Wasserstein ratio | numeric, datetime | Distance divided by the reference standard deviation (or the value range when the deviation is zero), so thresholds are unit-free |
| Missingness delta | all | Current missing share minus reference missing share, in percentage points |
| Category delta | categorical, boolean | Largest absolute share change across retained reference levels and the `other` bucket |
| Other categories | categorical, boolean | Current levels outside the retained reference levels, folded into the `other` bucket |

Datetime columns are measured in seconds since the Unix epoch. Boolean columns
are treated as categorical (`True` / `False`).

A column is reported as:

- `stable` when no configured threshold is crossed;
- `warning` when a warning threshold is crossed;
- `error` when an error threshold is crossed, or when the column is missing from
  the current frame or changed kind.

`report.has_drift` is true for warnings and errors. `raise_if_drift()` raises
only when an error exists.

## Policy and thresholds

`DriftPolicy` holds the thresholds and the sampling controls. It is immutable and
JSON-serializable, so the thresholds travel with the report.

| Field | Default | Effect |
| --- | --- | --- |
| `psi_warning` | `0.10` | Moderate shift |
| `psi_error` | `0.25` | Major shift |
| `missing_delta_warning` | `5.0` | Missing share changed by 5 pp |
| `missing_delta_error` | `None` | Off unless configured |
| `category_delta_warning` | `10.0` | Largest category share changed by 10 pp |
| `category_delta_error` | `None` | Off unless configured |
| `wasserstein_warning` | `None` | Off; applies to the scale-free ratio |
| `wasserstein_error` | `None` | Off |
| `min_sample` | `20` | Downgrade errors to warnings below this many rows |
| `bins` | `10` | Reference quantile bins used by PSI |
| `max_categories` | `20` | Reference levels kept per categorical column |
| `max_columns` | `200` | Columns profiled when no explicit list is given |
| `wasserstein_points` | `512` | Quantile points stored per numeric column |

The PSI bands are the conventional ones: below `0.10` is stable, `0.10` up to
`0.25` is a moderate shift, and `0.25` or above is a major shift. Missingness and
category deltas are absolute percentage points. Wasserstein thresholds use the
ratio, not the raw distance, so the same policy works across columns with
different units; they are off by default because "how far is too far" depends on
the feature.

`min_sample` exists because every metric is unstable on tiny batches. With the
default of `20`, a comparison where either side has fewer than 20 rows downgrades
an error to a warning. Set `min_sample=0` to disable the downgrade. An empty
reference or current frame raises `ValueError` instead of producing a misleading
report, so check batch size before comparing.

Thresholds are validated when the policy is created: values must be finite and
non-negative, an error threshold cannot be below its warning threshold, and the
count fields must be integers. `DriftPolicy.to_json()` / `from_json()` round-trip
the policy.

## Build the profile once

`DriftProfile.from_frame()` stores a compact summary:

- numeric and datetime columns keep quantile bin edges, the reference bin shares,
  a scale, and a bounded sample for the Wasserstein distance;
- categorical columns keep the most common levels and their shares, plus an
  `other` bucket that absorbs the remaining reference levels;
- every column keeps its reference missing share.

By default it profiles every numeric, categorical, boolean, and datetime column,
up to `policy.max_columns` in frame order. Columns that were not profiled are
listed in `profile.skipped_columns`. Pass an explicit `columns` list to choose
your own set; an explicit list is never truncated, and a missing name raises
`KeyError`. Column labels must be unique strings, because the profile round-trips
through JSON.

```python
profile = DriftProfile.from_frame(
    X_train,
    columns=["amount", "plan", "created_at"],
    policy=policy,
)
profile.rows
profile.skipped_columns
```

The profile is a derived summary, not a copy of the reference rows. Numeric
columns store exactly `wasserstein_points` quantiles at midpoint probabilities,
so no sorted raw column is kept; categorical output is capped at
`max_categories` levels plus one `other` bucket. Quantile values and retained
category labels are still data, so treat the profile as you would treat a schema.
The default `repr` is redacted.

Because the numeric side is a bounded quantile summary, comparing identical
batches produces a near-zero Wasserstein distance rather than a bit-exact zero.

`DriftProfile.to_json()` / `DriftProfile.from_json()` round-trip the profile,
including its policy, so a reference can be stored with a model artifact or in a
report sink.

## Read the report

`DistributionDriftReport` holds two frames and the policy:

```python
report.columns  # one row per compared column
report.categories  # bounded per-category detail
report.reference_rows
report.current_rows
report.policy
report.reference  # the profile used, when available
```

Column row fields include `kind`, `psi`, `wasserstein`, `wasserstein_ratio`,
`missing_reference_pct`, `missing_current_pct`, `missing_delta_pp`,
`max_category_delta_pp`, `other_categories`, `severity`, `status`, and
`message`. The category detail uses an `other` boolean to mark the aggregated
bucket; its reference share is the reference `other` share, so a rare reference
level that reappears is measured against the right baseline.

```python
report.errors  # error-severity column rows
report.warnings  # warning-severity column rows
report.has_errors
report.has_warnings
report.summary()
report.to_markdown()
report.to_dict()
report.to_json()
```

`compare()` only uses the reference columns: columns that exist only in the
current frame are ignored, and reference columns that are absent from the current
frame become error rows. Both input frames are read-only; the caller's data is
never modified.

## Compare against batch history

`JsonlReportSink` keeps an append-only JSON Lines audit trail. It accepts a
`CleanerReport`, a `DistributionDriftReport`, or a mapping:

```python
from data_cleaner import JsonlReportSink

sink = JsonlReportSink("reports/history.jsonl", fsync=False)

profile = DriftProfile.from_frame(X_train, policy=policy)
report = profile.compare(X_today)
sink.write(
    report,
    source="nightly-scoring",
    metadata={"job": "scoring", "run": 42},
)

sink.history()  # one summary row per batch
sink.latest(kind="drift_report", source="nightly-scoring")
```

A stored drift report includes its reference profile and policy. That makes a
later comparison reproducible with the thresholds that were in force when the
reference was recorded:

```python
report = sink.drift_against_previous(X_tomorrow, source="nightly-scoring")
```

`drift_against_previous()` looks up the latest matching drift report and reuses
its recorded policy when no explicit `policy` is passed. Pass `policy=` to
re-threshold the comparison deliberately. If no matching drift report exists it
raises `LookupError`; corrupt JSON raises `ValueError` with the line number.

The sink writes one record per `write()` call in append mode and creates parent
directories by default. New files are created with owner-only permissions
(`0600`), but an existing file keeps its mode; check or set permissions when you
reuse a file. Set `fsync=True` when each record must survive a crash, at the cost
of throughput; the parent directory is synced when a new file is created. The
sink does not lock the file, so give each concurrent writer its own file or
serialize writes externally. The path is the only state.

A stored `CleanerReport` is written as its `to_dict()` output. That includes
column names, the most common value per column (`profile.top`), decision values
such as fill values and learned bounds, and category labels. It is a summary, not
a copy of the batch, but those fields can still be sensitive; redact them before
writing if needed.

## Privacy and scope

Drift reports contain no row values. They do contain derived summaries: quantile
values for numeric columns, retained category labels, and the `other` bucket
share. `RowDiagnostics` (see [Validation, joins & dedup](validation-joins.md))
omits cell values unless explicitly asked and includes the frame index label by
default; pass `include_index=False` when the index can contain identifiers.

Treat a profile as you would treat a schema: pass an explicit `columns` list and
lower `max_categories` when column names or levels are sensitive. The default
`repr` for profiles is redacted, but `to_dict()` / `to_json()` still contain the
summary.

This layer is deterministic and dependency-light (NumPy and pandas only). It
deliberately does not implement p-values, automatic root-cause attribution, or
alert routing. For richer dashboards and metric suites, pair the report with
Evidently or your monitoring stack; the JSON output is the integration point.

## Scope boundaries

- The reference decides the bins and the categorical levels. Comparing against a
  different reference is a new profile, not a policy change.
- A kind change (for example numeric to text) is reported as an error and the
  distribution metrics are skipped for that column.
- Current levels outside the retained reference levels are aggregated into the
  `other` bucket; a genuinely new level and a rare reference level are not
  distinguished, because the profile keeps only the top levels.
- Drift detection is not model monitoring: it tells you the inputs moved, not
  whether predictions got worse.
