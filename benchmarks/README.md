# Benchmarks

Reproducible measurements for Universal Data Cleaner. Results feed
[docs/performance.md](../docs/performance.md); no performance claim is published
without a committed run.

## Run

```bash
uv sync --dev
uv run python benchmarks/run_benchmarks.py --output benchmarks/results/local.json
```

Fast smoke run (CI):

```bash
uv run python benchmarks/run_benchmarks.py --quick
```

Subset:

```bash
uv run python benchmarks/run_benchmarks.py --shape narrow --rows 100000 1000000
uv run python benchmarks/run_benchmarks.py --case transform --rows 1000000
```

`--help` lists the cases and shapes.

## Design

- `make_frame()` is seeded and vectorized, so the same arguments produce the
  same frame everywhere.
- Each `(case, shape, rows)` runs in a fresh subprocess to avoid allocator and
  import caches leaking between measurements.
- Runtime is the minimum of repeated `perf_counter` runs without tracing.
- Peak memory is measured separately with `tracemalloc` after `gc.collect()`.
- The JSON payload records the library version, Python, pandas, NumPy,
  scikit-learn, platform, CPU count, and git commit.
- The parent writes the JSON after every case, so a long run that fails partway
  keeps the measurements it already finished. `"complete": false` marks a
  partial file.

## Cases

| Case | Measures |
| --- | --- |
| `ingest` | `read_csv_safe()` under an inferred contract |
| `fit` | `DataCleaner.fit()` |
| `transform` | `DataCleaner.transform()` |
| `transform_with_report` | `DataCleaner.transform_with_report()` |
| `transform_chunks` | `transform_chunks()` plus `combine_drift_reports()` |
| `contract_check` | `DataContract.check()` |
| `validate` | `validate()` with two expectations |

## Shapes

- `narrow`: 10 columns, mixed numeric, categorical, boolean, datetime, and text.
- `wide`: 120 columns (60 numeric, 59 categorical).
- `high_cardinality`: unique text and numeric identifiers plus a 20-level
  category.

## Committed results

`results/2.11.0-darwin-x86_64.json` is the reference run recorded for the
`2.11.0` release (Python 3.13.5, pandas 3.0.6, 16 logical CPUs). Treat it as a
baseline, not a promise; re-run on your own hardware.
