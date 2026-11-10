# Upcoming

Universal Data Cleaner is built in small, leak-safe releases. This page records
what is shipping next and what is intentionally out of scope.
{: .lead }

## Recently shipped

| Version | Theme | Status |
| --- | --- | --- |
| `2.8.0` | Excel ingestion on the same `IngestionReport` model | Shipped |
| `2.7.0` | One batch report: `CleanerReport` and the `data-cleaner audit` CLI | Shipped |
| `2.6.0` | Safe CSV ingestion with contract-driven coercion and an audit report | Shipped |
| `2.5.0` | Train/test split and leakage audit | Shipped |
| `2.4.0` | Expectations, join diagnostics, integrity, and audited dedup | Shipped |

## Next up

### `2.9.0` — Reliability hardening

The core ingestion and reporting path now covers CSV and Excel. This release
hardens the paths that already exist rather than adding another data primitive.

Planned work:

- Contract enforcement at `fit()`: explicit contracts fail fast when a required
  training column is missing. `ColumnSpec(required=False)` marks optional
  columns. **Shipped.**
- Scalable join diagnostics that do not expand many-to-many keys. **Shipped.**
- Artifact compatibility errors with a documented opt-out and pickle guidance.
  **Shipped.**
- Opt-in, per-column outlier clipping with recorded decisions. **Shipped.**
- Chunked CSV reading with an identifier-precision warning. **Shipped.**
- Public API stability tiers and a deprecation policy. **Shipped.**

### Later

- Notebook chapters for the ingestion, reporting, and ML audit guides.
- Architecture decision records under `docs/adr/`.
- Shared examples across CSV, Excel, contracts, and batch reports.
- Optional Polars backend exploration for large frames.
- Deeper spreadsheet features such as named ranges and multi-sheet batch reports.
- Continued compatibility work across pandas 2.x and 3.x.

## What we are not building

These are explicit non-goals, not a backlog:

- an orchestrator or scheduler;
- a data-observability platform;
- a governance or ownership system;
- an auto-ML tool that chooses business rules for you;
- a replacement for dbt, Great Expectations, Soda, or OpenRefine.

## How priorities are chosen

A feature moves up when it does at least one of these:

1. Makes leakage or schema drift harder to miss.
2. Makes a learned or configured decision inspectable.
3. Keeps the core dependency-light and the public API backwards compatible.
4. Fits the existing `fit` / `transform` contract without surprising behavior.

See the [roadmap](https://github.com/devlprkhan/universal-data-cleaner/blob/main/ROADMAP.md)
for the full research-to-feature mapping and release rationale.
