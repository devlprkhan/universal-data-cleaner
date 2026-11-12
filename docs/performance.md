---
description: Measured performance, memory behavior, and supported workloads for Universal Data Cleaner.
---

# Performance and large data

This page records what was measured, how to reproduce it, and which workload the
library supports. It deliberately avoids unverified speed claims: every number
here comes from the committed benchmark suite.
{: .lead }

## What is measured

The suite benchmarks seven operations separately, because they have different
cost profiles:

| Case | Operation |
| --- | --- |
| `ingest` | `read_csv_safe()` over a written CSV, under an inferred contract |
| `fit` | `DataCleaner.fit()` including inference and contract construction |
| `transform` | `DataCleaner.transform()` on a fitted cleaner |
| `transform_with_report` | `DataCleaner.transform_with_report()` |
| `transform_chunks` | `transform_chunks()` over eight chunks plus `combine_drift_reports()` |
| `contract_check` | `DataContract.check()` alone (schema drift reporting) |
| `validate` | `validate()` with two expectations |

Each case runs in a fresh subprocess. Runtime is the minimum of repeated runs
measured with `perf_counter`; memory is measured separately with `tracemalloc`
after a garbage collection, so the timing run is not distorted by the allocator
instrumentation. The JSON also records the process high-water RSS and the
in-memory size of the input frame.

## How to reproduce

```bash
uv sync --dev
uv run python benchmarks/run_benchmarks.py --output benchmarks/results/local.json
```

Use `--quick` for a 10K-row smoke run, or `--shape` and `--rows` to run a
subset:

```bash
uv run python benchmarks/run_benchmarks.py --shape narrow --rows 100000 1000000
```

The workload generator is seeded and vectorized, so the same command produces
the same data on every machine. Results are only comparable on the same hardware
and dependency versions; the JSON records both.

## Reference results

Recorded on 2026-11-12 from the `2.11.0` working tree, one case at a time on an
otherwise idle machine:

| | |
| --- | --- |
| Python | 3.13.5 (x86_64) |
| pandas / NumPy / scikit-learn | 3.0.6 / 2.5.4 / 1.9.1 |
| Platform | macOS (`platform` reports `macOS-10.16-x86_64`), 16 logical CPUs |
| Library version | `2.11.0` |
| Base commit | `0b50dbf` (the release changes were uncommitted, so the JSON's `git_commit` records the base) |

`Peak traced` is the `tracemalloc` peak of the operation itself: the input frame
is built before tracing starts, so this column is the allocation cost of the
call, including the returned frame. `Max RSS` is the whole-process high-water
mark, which includes the interpreter (~180–200 MB), the input frame, and the
output. `Input frame` is deep memory (`memory_usage(deep=True)`).

| Case | Shape | Rows | Runtime (s) | Peak traced (MB) | Max RSS (MB) | Input frame (MB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `ingest` | `narrow` | 100,000 | 6.55 | 36 | 312 | 24 |
| `fit` | `narrow` | 100,000 | 0.45 | 31 | 210 | 24 |
| `transform` | `narrow` | 100,000 | 0.18 | 31 | 212 | 24 |
| `transform_with_report` | `narrow` | 100,000 | 0.18 | 31 | 212 | 24 |
| `transform_chunks` | `narrow` | 100,000 | 0.39 | 6 | 209 | 24 |
| `contract_check` | `narrow` | 100,000 | 0.02 | 0 | 185 | 24 |
| `validate` | `narrow` | 100,000 | 0.00 | 0 | 185 | 24 |
| `ingest` | `narrow` | 1,000,000 | 79.76 | 362 | 1448 | 243 |
| `fit` | `narrow` | 1,000,000 | 3.44 | 310 | 803 | 243 |
| `transform` | `narrow` | 1,000,000 | 1.14 | 310 | 817 | 243 |
| `transform_with_report` | `narrow` | 1,000,000 | 1.13 | 310 | 817 | 243 |
| `transform_chunks` | `narrow` | 1,000,000 | 1.28 | 53 | 802 | 243 |
| `contract_check` | `narrow` | 1,000,000 | 0.11 | 1 | 559 | 243 |
| `validate` | `narrow` | 1,000,000 | 0.03 | 1 | 559 | 243 |
| `ingest` | `narrow` | 2,000,000 | 123.30 | 725 | 2687 | 486 |
| `fit` | `narrow` | 2,000,000 | 7.69 | 620 | 1522 | 486 |
| `transform` | `narrow` | 2,000,000 | 2.32 | 620 | 1568 | 486 |
| `transform_with_report` | `narrow` | 2,000,000 | 2.29 | 620 | 1568 | 486 |
| `transform_chunks` | `narrow` | 2,000,000 | 2.26 | 107 | 1521 | 486 |
| `contract_check` | `narrow` | 2,000,000 | 0.22 | 2 | 990 | 486 |
| `validate` | `narrow` | 2,000,000 | 0.06 | 2 | 989 | 486 |
| `ingest` | `wide` | 100,000 | 73.34 | 550 | 1864 | 366 |
| `fit` | `wide` | 100,000 | 2.47 | 241 | 751 | 366 |
| `transform` | `wide` | 100,000 | 1.09 | 241 | 751 | 366 |
| `transform_with_report` | `wide` | 100,000 | 1.08 | 241 | 751 | 366 |
| `transform_chunks` | `wide` | 100,000 | 1.94 | 42 | 749 | 366 |
| `contract_check` | `wide` | 100,000 | 0.17 | 0 | 701 | 366 |
| `validate` | `wide` | 100,000 | 0.00 | 0 | 701 | 366 |
| `ingest` | `high_cardinality` | 100,000 | 3.85 | 30 | 254 | 14 |
| `fit` | `high_cardinality` | 100,000 | 0.20 | 24 | 192 | 14 |
| `transform` | `high_cardinality` | 100,000 | 0.09 | 24 | 194 | 14 |
| `transform_with_report` | `high_cardinality` | 100,000 | 0.09 | 24 | 193 | 14 |
| `transform_chunks` | `high_cardinality` | 100,000 | 0.20 | 4 | 190 | 14 |
| `contract_check` | `high_cardinality` | 100,000 | 0.01 | 0 | 177 | 14 |
| `validate` | `high_cardinality` | 100,000 | 0.00 | 0 | 178 | 14 |
| `ingest` | `high_cardinality` | 1,000,000 | 39.86 | 300 | 1274 | 139 |
| `fit` | `high_cardinality` | 1,000,000 | 2.81 | 242 | 618 | 139 |
| `transform` | `high_cardinality` | 1,000,000 | 0.87 | 242 | 638 | 139 |
| `transform_with_report` | `high_cardinality` | 1,000,000 | 0.84 | 242 | 638 | 139 |
| `transform_chunks` | `high_cardinality` | 1,000,000 | 0.98 | 41 | 617 | 139 |
| `contract_check` | `high_cardinality` | 1,000,000 | 0.07 | 1 | 470 | 139 |
| `validate` | `high_cardinality` | 1,000,000 | 0.03 | 1 | 471 | 139 |

The shape of the results matters more than any single cell:

- **Ingestion is cell-bound.** Across every shape and size, `read_csv_safe()`
  sustains 150K–164K cells/s (~6–7 µs per cell). It is the slowest operation by
  far: 10M cells take ~80 s, and 20M cells take ~2 min.
- **Transform is cheap and linear.** 8.6–8.8M cells/s at 1M and 2M rows on the
  narrow shape, 11M cells/s on the wide shape. Doubling rows doubles runtime.
- **Fit costs about a third of a transform** on the narrow shape (2.1–2.9M
  cells/s) and includes contract inference.
- **Auditing is effectively free at these sizes.** `contract_check` runs at
  8.9M rows/s and `validate` at 31–36M rows/s on narrow data at 1M–2M rows.
- **Chunking buys memory, not time.** Eight chunks cut the traced peak by
  5.5×–5.9× in every measurement, while runtime stayed within ±15% and was
  slightly faster at 2M rows.

## Supported workload

These are the workloads the `2.11.0` measurements support on hardware comparable
to the table above. They are the basis for the sizing rule that follows; they are
not a promise for different hardware, pandas versions, or dtypes.

| Workload | Measured result |
| --- | --- |
| Single-batch `fit` + `transform`, 2M rows × 10 columns | 7.7 s + 2.3 s, 620 MB traced peak, 1.6 GB process peak |
| Single-batch `fit` + `transform`, 100K rows × 120 columns | 2.5 s + 1.1 s, 241 MB traced peak, 751 MB process peak |
| Single-batch `fit` + `transform`, 1M rows × 6 columns with unique ids | 2.8 s + 0.9 s, 242 MB traced peak, 638 MB process peak |
| Contract check + validation, 2M rows | 0.22 s + 0.06 s |
| Ingesting 20M cells (2M rows × 10 columns) as CSV | 123 s, 725 MB traced peak, 2.7 GB process peak |
| Chunked transform, 2M rows in 8 chunks | 2.3 s, 107 MB traced peak |

Sizing rule derived from the measurements:

- Budget roughly **200 MB + 3× the deep size of the frame you pass to `fit()` or
  `transform()`**. The measured ratio was 2.5–2.8× on narrow and high-cardinality
  data and 1.5× on wide data, where object columns share more references.
- Budget roughly **200 MB + 5–8× the deep size of the frame a single
  `read_csv_safe()` / `read_parquet_safe()` call returns**. Ingestion holds the
  text frame and the typed frame at the same time, so it costs more than cleaning.
- A 2 GB worker can hold 2M rows × 10 columns, but with little headroom. Above
  that, or whenever the input frame's deep size exceeds ~25% of available RAM,
  switch to `transform_chunks()` with bounded chunks.

Ingestion, not cleaning, is the operation that decides whether a single-batch
workflow fits. For large raw files, stream them with `iter_csv_safe()` or
`iter_parquet_safe()` and hand the batches to `transform_chunks()`; peak memory
then tracks the batch size rather than the file size.

## What is not measured

- pandas 2.x. The reference run used pandas 3.0.6; the library supports both, but
  no pandas 2.x timings are published.
- Multi-process or multi-machine throughput. All numbers come from a single
  process with no parallelism; the cleaner itself is single-threaded, and
  parallelism comes from processing chunks in separate workers.
- Other hardware. The reference host is a 16-logical-CPU x86_64 macOS machine, not
  the CI runners, and the run was not isolated from a desktop environment.
- Any comparison with other libraries, or any claim that the cleaner is fast
  relative to plain pandas or Polars. The suite measures this library against
  itself across workloads.

## Chunked transformation

`transform_with_report()` keeps one batch in memory. For files that do not fit,
stream chunks and aggregate the reports instead of the frames:

```python
import pandas as pd

from data_cleaner import (
    combine_drift_reports,
    combine_ingestion_reports,
    iter_csv_safe,
)

ingestion_reports = []
clean_reports = []
for chunk, ingestion_report in iter_csv_safe(
    "events.csv", contract=contract, chunksize=100_000
):
    ingestion_reports.append(ingestion_report)
    cleaned, drift = cleaner.transform_with_report(chunk)
    clean_reports.append(drift)
    write_batch(cleaned)

ingestion = combine_ingestion_reports(ingestion_reports)
transform = combine_drift_reports(clean_reports)

print(ingestion.rows, transform.rows, transform.chunks)
transform.raise_if_errors()
```

`transform_chunks()` is the same loop without the manual bookkeeping:

```python
for cleaned, drift in cleaner.transform_chunks(
    frame for frame, _ in iter_csv_safe("events.csv", contract=contract)
):
    write_batch(cleaned)
```

Both approaches keep the frame bounded by `chunksize`. The aggregated
`TransformReport` stores findings, not rows, so its memory grows with the number
of findings rather than with the size of the data.

Chunked transformation is leak-safe in the same way as a single batch: the
cleaner applies the parameters learned on the training data and never refits.
Missing fitted columns remain fatal per chunk.

## Memory guidance

- A single `transform()` allocates the cleaned output in addition to the input
  frame. Measured peak was 1.5–2.8× the input frame's deep size, plus the
  ~200 MB interpreter baseline; the sizing rule above turns that into a budget.
- `add_missing_indicators=True` adds one boolean column per column that had
  missing values during fit; on wide frames that materially increases the output.
- `drop_constant_columns=True` (the default) reduces the output when columns are
  constant after cleaning.
- `transform_chunks()` and `iter_csv_safe()` bound the live frame by the chunk
  or batch size. Eight chunks cut the traced peak by ~5.7× in every measured
  case.
- Disk-backed uniqueness tracking (`unique_tracking="disk"`) keeps peak memory
  flat for high-cardinality identifiers; see [Safe ingestion](ingestion.md).
