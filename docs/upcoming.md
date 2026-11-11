# Upcoming

Universal Data Cleaner is built in scoped, verified releases. This page records
what ships next, the order of the production-hardening work, and what is
intentionally out of scope.
{: .lead }

The full plan, checklists, and release gates are in the
[roadmap](https://github.com/devlprkhan/universal-data-cleaner/blob/main/ROADMAP.md).
The decision to prioritise hardening over new features is recorded in
[ADR 0001](adr/0001-production-hardening-strategy.md).

## Current focus

**`2.9.1` — ship merged hardening and prove provenance.** (Release in review.)

The chunked-schema, uniqueness, missing-column, CI-matrix, and installed-wheel
work is already on `main`. This patch release ships it and verifies the release
pipeline end to end.

Why a patch release first: `2.9.0` was published before the attestation workflow
existed, so PyPI correctly shows no provenance for it. `2.9.1` is the first
release that can demonstrate PyPI and GitHub provenance, and it acts as the
release-gate rehearsal before `2.10.0`.

## Version sequence

| Version | Theme | Status |
| --- | --- | --- |
| `2.9.1` | Ship merged hardening; verify provenance | In review |
| `2.10.0` | Production correctness | Planned |
| `2.11.0` | Large data and performance | Planned |
| `2.12.0` | Validation and statistical drift | Planned |
| `2.13.0` | Reproducibility and operations | Planned |
| `2.14.0` | Testing and security | Planned |
| `3.0.0` | Ecosystem readiness | Conditional |

## `2.10.0` — Production correctness

The next development release fixes the highest-risk gaps in the existing
surface:

- concurrency-safe transformation reporting, so parallel batches cannot
  overwrite each other's drift reports;
- numeric precision detection and explicit policies, with preserved integer
  dtypes where safe;
- atomic artifact saves and runtime dependency compatibility enforcement;
- bounded or disk-backed cross-chunk uniqueness tracking;
- aggregated chunk reports and documented streaming semantics;
- post-publication provenance verification as a release gate.

No new cleaning primitive is planned until this phase is complete.

## Later phases

- **Large data and performance:** benchmark suite, peak-RAM measurement, chunked
  transformation, supported-workload documentation, optional Parquet ingestion.
- **Validation and drift:** custom and cross-column validation, conditional and
  grouped rules, PSI and Wasserstein drift, reference comparisons, privacy-safe
  row diagnostics.
- **Reproducibility and operations:** contract versions and migrations, exact
  content fingerprints, artifact integrity, report sinks, structured logging,
  serving guidance.
- **Testing and security:** property-based and fuzz testing, dtype and timezone
  edge cases, estimator checks, cross-platform CI, dependency auditing,
  supply-chain review.
- **Ecosystem readiness:** migration guides, reviewed examples, benchmark
  datasets, case studies, and additional maintainers.

## Recently shipped

| Version | Theme | Status |
| --- | --- | --- |
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
