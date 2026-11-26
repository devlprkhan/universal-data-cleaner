---
title: "Upcoming"
description: "The full plan, checklists, and release gates are in the roadmap. The decision to prioritise hardening over new features is recorded in ADR 0001."
---

<p class="lead">Universal Data Cleaner is built in scoped, verified releases. This page records what ships next, the order of the production-hardening work, and what is intentionally out of scope.</p>

The full plan, checklists, and release gates are in the
[roadmap](https://github.com/devlprkhan/universal-data-cleaner/blob/main/ROADMAP.md).
The decision to prioritise hardening over new features is recorded in
[ADR 0001](/adr/0001-production-hardening-strategy/).

## Current focus

**`2.12.0` — validation and statistical drift.** This release extends the
validation layer with cross-column, conditional, and grouped rules, adds PSI and
Wasserstein drift against a reusable reference profile, keeps failing-row
diagnostics bounded and privacy-safe, and adds a JSON Lines report sink for
historical batch comparison.

`2.11.0` shipped on 2026-11-13 with provenance for both the wheel and the sdist;
`gh attestation verify` passes against `publish.yml@refs/tags/v2.11.0`, and a
clean install from PyPI works. `2.10.0` shipped the same way on 2026-11-12.
`2.9.1` was the first attested release. `2.9.0` predates the attestation
workflow, so it correctly has no provenance.

## Version sequence

| Version | Theme | Status |
| --- | --- | --- |
| `2.10.0` | Production correctness | Shipped |
| `2.11.0` | Large data and performance | Shipped |
| `2.12.0` | Validation and statistical drift | Next |
| `2.13.0` | Reproducibility and operations | Planned |
| `2.14.0` | Testing and security | Planned |
| `3.0.0` | Ecosystem readiness | Conditional |

## `2.12.0` — Validation and statistical drift

The `2.12.0` release closes the validation and quality-engineering phase:

- `col()` conditions, `row_rule()`, `conditional()`, `grouped()`,
  `unique_combination()`, and `sum_equals()` for cross-column, scoped, grouped,
  and arithmetic rules;
- the public `Validatable` protocol, so custom rules mix with built-in
  expectations in one `validate()` call;
- `DriftProfile`, `DriftPolicy`, and `compare_distributions()` with PSI,
  Wasserstein distance, missingness deltas, category deltas, and an `other`
  bucket for levels outside the retained reference categories;
- `ValidationReport.diagnose()` and `RowDiagnostics` for bounded failing-row
  samples that omit cell values by default;
- `JsonlReportSink` for append-only batch history and reproducible drift
  comparisons against a stored reference.

The guide is [Statistical drift](/drift/); rule and diagnostic examples are in
[Validation, joins & dedup](/validation-joins/).

## `2.11.0` — Large data and performance

The `2.11.0` release made scale behavior measurable and testable:

- a seeded, subprocess-isolated benchmark suite covering ingestion, fit,
  transform, chunked transform, reporting, and validation;
- runtime and peak memory reported separately for 100K, 1M, and 2M rows across
  narrow, wide, and high-cardinality frames;
- `transform_chunks()` and `combine_drift_reports()` for bounded-memory batch
  jobs with one aggregated `TransformReport`;
- optional Parquet ingestion through `read_parquet_safe()` and
  `iter_parquet_safe()`;
- removal of an unnecessary input deep copy in `transform()`;
- a documented supported workload in
  [Performance and large data](/performance/), derived from the committed
  reference run.

## `2.10.0` — Production correctness

The `2.10.0` release fixed the highest-risk gaps in the existing surface:

- concurrency-safe transformation reporting, so parallel batches cannot
  overwrite each other's drift reports;
- numeric precision detection and explicit policies, with preserved integer
  dtypes where safe;
- atomic artifact saves and runtime dependency compatibility enforcement;
- bounded or disk-backed cross-chunk uniqueness tracking;
- aggregated chunk reports and documented streaming semantics;
- post-publication provenance verification as a release gate.

No new cleaning primitive was added in this phase.

## Later phases

- **Validation integrations:** optional Pandera and Evidently adapters. The core
  validation protocol, rules, and drift metrics ship in `2.12.0`.
- **Reproducibility and operations:** contract versions and migrations, exact
  content fingerprints, artifact integrity, structured logging, serving guidance.
- **Testing and security:** property-based and fuzz testing, dtype and timezone
  edge cases, estimator checks, cross-platform CI, dependency auditing,
  supply-chain review.
- **Ecosystem readiness:** migration guides, reviewed examples, benchmark
  datasets, case studies, and additional maintainers.

## Recently shipped

| Version | Theme | Status |
| --- | --- | --- |
| `2.11.0` | Large data and performance: chunked transforms, Parquet, benchmark suite | Shipped |
| `2.10.0` | Production correctness: concurrency-safe reports, precision policies, atomic artifacts, chunked uniqueness | Shipped |
| `2.9.1` | Ship merged hardening; prove PyPI and GitHub provenance | Shipped |
| `2.9.0` | Reliability hardening across contracts, joins, artifacts, clipping, ingestion, and API docs | Shipped |
| `2.8.0` | Excel ingestion on the same `IngestionReport` model | Shipped |
| `2.7.0` | One batch report: `CleanerReport` and the `data-cleaner audit` CLI | Shipped |
| `2.6.0` | Safe CSV ingestion with contract-driven coercion and an audit report | Shipped |
| `2.5.0` | Train/test split and leakage audit | Shipped |
| `2.4.0` | Expectations, join diagnostics, integrity, and audited dedup | Shipped |

## What we are not building

These are explicit non-goals, not a backlog:

- an orchestrator or scheduler;
- a data-observability platform;
- a governance or ownership system;
- a distributed compute engine or a new dataframe engine;
- an auto-ML tool that chooses business rules for you;
- a replacement for dbt, Great Expectations, Soda, Pandera, or OpenRefine.

Integrate with established tools through optional extras and report sinks rather
than rebuilding them.

## How priorities are chosen

A change moves up when it does at least one of these:

1. Prevents silent data corruption, leakage, or schema drift.
2. Makes a learned or configured decision inspectable and reproducible.
3. Improves behaviour under production conditions: concurrency, memory,
   precision, failure, or scale.
4. Makes a release or artifact verifiable.
5. Keeps the core dependency-light and the public API backwards compatible.

A change moves down or out when it expands into orchestration, observability,
distributed compute, or enterprise governance.
