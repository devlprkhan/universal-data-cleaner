# Upcoming

Universal Data Cleaner is built in small, leak-safe releases. This page records
what is shipping next and what is intentionally out of scope.
{: .lead }

## Recently shipped

| Version | Theme | Status |
| --- | --- | --- |
| `2.7.0` | One batch report: `CleanerReport` and the `data-cleaner audit` CLI | Shipped |
| `2.6.0` | Safe CSV ingestion with contract-driven coercion and an audit report | Shipped |
| `2.5.0` | Train/test split and leakage audit | Shipped |
| `2.4.0` | Expectations, join diagnostics, integrity, and audited dedup | Shipped |

## Next up

### `2.8.0` — Spreadsheet input on the same report model

The next release extends the ingestion layer rather than adding another review
surface. The goal is to make Excel input as auditable as CSV without changing the
`IngestionReport` contract.

Planned work:

- Optional Excel ingestion using the same `IngestionReport` model.
- The same identifier, date, and boolean guards for spreadsheet columns.
- Shared ingestion and reporting examples across CSV and Excel.
- Continued pandas 2.x/3.x compatibility checks.

### Later

- Optional Excel ingestion using the same `IngestionReport` model.
- Notebook chapters for each major guide.
- Architecture decision records under `docs/adr/`.
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
