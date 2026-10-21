# Universal Data Cleaner — Product Roadmap

This roadmap turns the 2026 data-preparation research into features that fit a
small, leak-safe, scikit-learn-compatible cleaning library.

It is deliberately opinionated. The research shows that most *mechanical*
cleaning is already solved by pandas, OpenRefine, Great Expectations, dbt, and
friends. The durable opportunity for this library is narrower:

> Make the assumptions behind a cleaning step **explicit**, **checkable**,
> **explainable**, and **reusable on the next batch** — without turning the
> library into an orchestration or observability platform.

---

## 1. Positioning

### What this library is

- A **per-dataset, in-process transformer** for pandas + scikit-learn.
- **Leak-safe by construction**: fit on training data, reuse learned rules at
  inference, never mutate the input, never drop inference rows.
- **Auditable**: every learned/overridden decision has a reason and can be
  inspected, exported, versioned, and reloaded.

### What this library is not

- Not an orchestrator or scheduler (Airflow, Dagster, Prefect).
- Not a data-observability platform (Monte Carlo, Soda Cloud, Elementary).
- Not an enterprise governance/ownership system.
- Not a replacement for dbt, Great Expectations, or Soda.
- Not an auto-ML tool that decides business meaning for the user.

Those are real problems in the research, but they are **organizational or
platform-level** problems. Solving them in a pandas transformer would create a
worse, heavier version of tools that already exist.

---

## 2. Research → Feature Mapping

Scores are the research-priority scores from the landscape document.

| # | Pain point | Score | Fit for this library | Feature theme | Tier |
| --- | --- | --- | --- | --- | --- |
| 1 | Unexpected schema / type / format changes | 9.1 | High | Declarative column contracts + drift detection at `transform()` | **1** |
| 7 | Repeated missing / outlier / duplicate decisions | 7.8 | High (core already) | Record *why* each decision was made; decision log | **1** |
| 8 | Hard-to-reproduce transforms, weak lineage | 7.7 | High | Reproducible artifact manifest + data/schema fingerprint | **2** |
| 2 | Cross-source integration / entity matching | 8.9 | Medium–High (pure helpers) | Join-cardinality + key diagnostics; business-key dedup | **3** |
| 3 | Data-quality failures found too late | 8.9 | Medium | Lightweight expectation validation + human-readable report | **3** |
| 4 | ML leakage / contaminated evaluation | 8.3 | High | Train/test split audit (groups, time, duplicates, leakage) | **4** |
| 5 | Spreadsheet transformations, no audit trail | 8.2 | Medium | Safe CSV/Excel ingestion with type/format reporting | **5** |
| 6 | Inconsistent business definitions | 8.1 | Low–Medium | Contract exported as reviewable YAML/JSON (ownership artifact) | **2/6** |
| 9 | Large, nested, semi-structured, multi-modal data | 7.2 | Low | Explicit non-goal for v2.x; optional Polars backend later | — |

### Root causes the roadmap targets

| Root cause from research | How the roadmap addresses it |
| --- | --- |
| Data meaning is not fully specified | `ColumnSpec` / `DataContract` with semantic roles (`id`, `measure`, `category`, `datetime`) |
| Sources evolve independently | Drift report at `transform()` with an explicit `on_drift` policy |
| Quality rules are incomplete/disconnected | Reusable expectation checks + validation report, stored next to the cleaner |
| Transformations separated from justification | `CleaningDecision` records with reasons, exported in the artifact |
| Responsibility unclear | Contract as a reviewable, version-controlled file (helps, does not fully solve) |

---

## 3. Design principles

1. **Never break leak-safety.** Any new check must be computable at `fit()` or
   be a pure function of the frame passed to `transform()`.
2. **Warn by default, fail on request.** Drift and validation should not
   silently destroy data or crash a pipeline unless configured with
   `severity="error"` / `on_drift="raise"`.
3. **Explain every action.** No magic. Each decision has `column`, `action`,
   `reason`, `source`, `before`, `after`.
4. **Dependency-light.** pandas + numpy + scikit-learn + joblib stay the core.
   Optional extras (`polars`, `hypothesis`, `pyyaml`) go in dev/optional groups.
5. **Backwards compatible.** Existing `CleanerConfig` / `DataCleaner` behavior
   stays the default. New behavior is opt-in.
6. **Pure functions for audits.** Join/validation/split audits take DataFrames in
   and return reports; they never mutate and never fit anything.

---

## 4. Milestones

### Tier 1 — `v2.1.0`: Semantic contracts and drift guard

*Targets pain #1, #7 and root cause 1–3.*

Introduce the concept of an explicit column contract, inferred at `fit()` and
checked at `transform()`.

```python
from data_cleaner import ColumnSpec, DataContract, CleanerConfig, DataCleaner

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
        ColumnSpec("age", role="numeric", nullable=True, min_value=0, max_value=120),
        ColumnSpec("signup_date", role="datetime", date_format="%Y-%m-%d"),
        ColumnSpec("plan", role="category", allowed_values=("free", "pro", "team")),
    ],
    on_drift="warn",  # raise | warn | coerce | ignore
)

cleaner = DataCleaner(CleanerConfig(contract=contract)).fit(X_train)
X_test_clean = cleaner.transform(X_test)  # drift checked, never mutates
report = cleaner.drift_report()  # DataFrame of every difference found
```

Deliverables:

- `ColumnSpec` with `role`, `dtype`, `nullable`, `unique`, `allowed_values`,
  `min_value`, `max_value`, `pattern`, `date_format`,
  `preserve_leading_zeros`, `severity`.
- Semantic roles: `id`, `numeric`/`measure`, `category`, `boolean`,
  `datetime`, `text`, `ignore`.
- `DataContract` with `infer_from(frame)`, `validate(frame)`, `diff(frame)`,
  `to_yaml()` / `from_yaml()`.
- Drift report covering: missing columns, extra columns, dtype change,
  nullability change, new categories, range change, uniqueness change.
- Identifier protection: `role="id"` columns are never coerced to numeric and
  never imputed with a statistic.
- `ClearnerConfig.on_drift` policy honored in `transform()`.

Why first: it is the clearest unmet need in the research, it is the natural
extension of what `DataCleaner` already learns, and it is a prerequisite for
trustworthy validation and ML audits.

### Tier 2 — `v2.3.0`: Auditable decisions and reproducible artifacts

*Targets pain #8, #5, #6 and root cause 4.*

```python
cleaner.decision_log()  # DataFrame: column, action, reason, source, before, after
cleaner.to_manifest()  # JSON-serializable dict
cleaner.fingerprint(X)  # stable hash of schema + stats
manifest = cleaner.artifact_manifest()
```

Deliverables:

- `CleaningDecision` dataclass, recorded during `fit()` and manual overrides.
- `DataCleaner.decision_log()` returning a tidy DataFrame.
- Artifact manifest: library version, artifact version, pandas/numpy/sklearn
  versions, config, contract, input schema, optional data fingerprint,
  fitted param summary, UTC timestamp.
- `fingerprint_dataframe(frame, columns=None)` — stable hash for lineage.
- `compare_fingerprints(a, b)` and `assert_schema_stable`.
- `DataCleaner.load()` warns when artifact is from a different schema/version.

Why second: reproducibility is the other high-confidence, high-fit problem, and
it makes the Tier 1 drift reports trustworthy over time.

### Tier 3 — `v2.4.0`: Validation and integration diagnostics

*Targets pain #2, #3.*

```python
from data_cleaner import diagnose_join, check_referential_integrity

report = diagnose_join(orders, customers, on="customer_id", how="left")
report.safe  # False
report.row_multiplier  # 3.7
report.unmatched_right  # 412
report.warnings  # ["right key is not unique (m:m join)"]

from data_cleaner import Contract

result = Contract.from_frame(orders).validate(orders_new)
result.failures.to_markdown()
```

Deliverables (pure functions, no fitting):

- `diagnose_join(left, right, on, how, validate="1:1")` with left/right key
  duplication, cardinality class, output row multiplier, unmatched counts.
- `check_referential_integrity(child, parent, child_key, parent_key)`.
- `deduplicate_by_business_key(frame, key, keep, tie_breaker=None)` that reports
  what it removed and why — unlike raw `drop_duplicates`.
- Lightweight expectations API: `not_null`, `unique`, `in_set`, `between`,
  `matches_pattern`, `has_dtype`, `row_count_between`.
- `ValidationReport` with `success`, `results`, `failures`, `to_markdown()`,
  `raise_if_failed()`.

Why here: these problems are severe but mostly *diagnostic*, so pure helper
functions deliver most of the value without changing the transformer core.

### Tier 4 — `v2.5.0`: ML validity audit

*Targets pain #4.*

```python
audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    groups=groups,
    time_col="event_time",
    id_cols=["customer_id"],
)
audit.summary()  # DataFrame of findings + severity
audit.raise_if_invalid()  # optional
```

Deliverables:

- Duplicate / near-duplicate rows across splits.
- Group leakage (same group in train and test).
- Temporal leakage (train timestamps after test timestamps).
- Target-leakage heuristics (single feature predicts target unusually well).
- Constant / near-constant columns and high-cardinality identifiers.
- Missingness and distribution shift between splits.
- Severity per finding; never auto-fixes, only reports and explains.

Why fourth: high severity for ML users, but it is an audit on top of the
cleaner rather than part of it. Safer to ship after the contract/drift core is
solid.

### Tier 5 — `v2.6.0`: Safe ingestion

*Targets pain #1, #5, #9 (partially).*

```python
frame, report = read_csv_safe("export.csv", contract=contract, on_error="warn")
```

Deliverables:

- Read as strings first, then coerce under contract control.
- Detect and preserve leading zeros, mixed types, thousands separators,
  currency/percent symbols, and ambiguous date formats.
- Emit an ingestion report instead of silently inferring types.
- Guard against common spreadsheet failure modes (dates serialized as integers,
  IDs losing leading zeros, booleans inferred from `Y`/`N`).

Why fifth: it is a natural front door, but it is closer to a new I/O layer than
to the existing transformer, so it should not gate the core value.

### Tier 6 — ongoing: Reporting, docs, DX

- `CleanerReport` combining profile + contract + decisions + drift.
- `python -m data_cleaner audit data.csv` CLI for the above.
- Notebook chapter per tier; docs site later.
- `docs/adr/` architecture decision records.

---

## 5. Package structure

**Package shipped in `v2.2.0`; audit modules added in `v2.3.0`; validation and
integration modules added in `v2.4.0`.** The single `data_cleaner.py` module was
split into a typed `src/data_cleaner/` package with a PEP 561 `py.typed` marker,
while keeping the public import path and the pickled-artifact qualified name
stable.

```text
src/data_cleaner/
├── __init__.py        # public API re-exports (stable import path)
├── _version.py        # __version__, artifact version
├── _roles.py          # semantic roles, dtype/identifier helpers
├── artifacts.py       # fingerprints and runtime version metadata
├── contract.py        # ColumnSpec, DataContract, DriftReport
├── config.py          # CleanerConfig
├── cleaner.py         # DataCleaner
├── decisions.py       # CleaningDecision, decision log
├── integration.py     # join diagnostics, referential integrity, dedup
├── profiling.py       # profile_dataframe, dataset_summary, helpers
└── validation.py      # expectations, ValidationReport
```

Future tiers add modules alongside these: `ml_audit.py` and `ingestion.py`.

Compatibility rules:

- `import data_cleaner; data_cleaner.DataCleaner` keeps working.
- Existing pickled artifacts reference `data_cleaner.DataCleaner`. That
  qualified name stays stable, and a fixture test loads an artifact saved under
  the legacy flat-module layout after the restructure.
- The restructure stayed in the 2.x line because no public import path moved.

---

## 6. Testing strategy

- **Invariant tests**: no input mutation, no inference-row loss, fit-only-from-
  train, idempotent `transform`.
- **Drift matrix**: for each contract field, construct a frame that violates it
  and assert the exact report entry and policy behavior.
- **Artifact compatibility**: an artifact pickled under the legacy flat-module
  layout is loaded after the package restructure. The test remaps the classes'
  module names at runtime, so it is pandas-version independent and safe across
  the whole CI matrix.
- **Pure-function correctness**: compare `diagnose_join` against hand-computed
  pandas cardinalities on 1:1, 1:m, m:m, empty, and all-unmatched cases.
- **Property-based tests** (optional `hypothesis` dev dep) for dedup and
  fingerprint stability.
- **Golden notebook**: keep executing `Universal_Data_Cleaner.ipynb` headlessly
  in CI, extended with the new features.

---

## 7. Release and versioning plan

| Version | Scope | Breaking? |
| --- | --- | --- |
| `2.1.0` | Contracts + drift guard + id protection | No |
| `2.2.0` | Typed `src/` package, `py.typed`, CI quality gates | No |
| `2.3.0` | Decision log + manifest + fingerprints | No |
| `2.4.0` | Validation + join/integration diagnostics | No |
| `2.5.0` | ML split/leakage audit | No |
| `2.6.0` | Safe ingestion | No |
| `3.0.0` | Any future breaking import move | Possibly |

Each release: update `CHANGELOG.md`, bump `pyproject.toml`, push, create a
GitHub release, let `publish.yml` handle PyPI.

---

## 8. Non-goals (explicit)

- Scheduling, orchestration, alerting, incident routing.
- A data catalog or ownership/governance system.
- Automatic business-rule inference without user confirmation.
- Replacing Great Expectations / Soda / dbt / OpenRefine.
- Heavy ML or NLP dependencies in the core install.

---

## 9. Current step

Tier 1 (`v2.1.0`), the typed package restructure (`v2.2.0`), Tier 2
(`v2.3.0`: decision log, manifest, fingerprints), and Tier 3 (`v2.4.0`:
expectations, contract validation, join diagnostics, referential integrity, and
audited deduplication) are shipped.

Implement **Tier 4 (`v2.5.0`)**: ML split/leakage audit — `audit_split()` with
duplicate/near-duplicate overlap, group leakage, temporal leakage,
target-leakage heuristics, constant/high-cardinality columns, distribution
shift, and severity-tagged findings. It only reports; it never auto-fixes.
