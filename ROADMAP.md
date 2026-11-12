# Universal Data Cleaner — Production Roadmap

> **Baseline:** `v2.9.1` (published and provenance-verified 2026-11-11).
> **Current target:** `v2.10.0` — production correctness (Phase 1).
>
> This roadmap is the working plan. Every version below is a scoped, tested,
> documented, and verified release — not a wish list.

Universal Data Cleaner is a **production-grade, auditable, reproducible tabular
data preparation and quality-assurance toolkit for Python and scikit-learn**.

It covers one lifecycle and does it end to end:

```text
raw data
  -> ingestion and normalization
  -> contract enforcement
  -> cleaning and transformation
  -> validation and quality assurance
  -> audit, reproducibility, and monitoring hooks
  -> trusted ML-ready dataset
```

The durable value is not another cleaning function. It is making the assumptions
behind a cleaning step **explicit**, **checkable**, **explainable**, and
**reusable on the next batch** — without becoming an orchestration or
observability platform.

---

## 1. Scope and boundary

### What this library is

- A **per-dataset, in-process transformer** for pandas and scikit-learn.
- **Leak-safe by construction:** fit on training data, reuse learned rules at
  inference, never mutate the input, never drop inference rows.
- **Auditable:** every learned or overridden decision has a reason and can be
  inspected, exported, versioned, and reloaded.
- **Quality-aware:** safe ingestion, contracts, expectations, drift reports,
  split audits, and reproducible fingerprints in one dependency-light package.

### What this library is not

Keep this boundary. Integrate with these systems; do not rebuild them.

| Do not build | Use or integrate instead |
| --- | --- |
| Another complete ML pipeline framework | scikit-learn |
| An enormous transformation catalogue | Feature-engine |
| A replacement for enterprise validation platforms | Great Expectations, Pandera |
| A distributed compute engine | Dask |
| Another high-performance dataframe engine | Polars, PyArrow |
| A complete data-monitoring dashboard | Evidently, Monte Carlo, Soda |
| An orchestration and scheduling framework | Airflow, Dagster, Prefect |
| An enterprise governance or ownership system | Existing catalog/governance tools |
| An auto-ML tool that chooses business rules | The user |

Also out of scope: scheduling, alerting, incident routing, a data catalog, and
automatic business-rule inference without user confirmation.

---

## 2. Baseline inventory (`v2.9.1`)

Having a capability is not the same as hardening it. This table separates the
two.

| Capability | Current state | Remaining gap |
| --- | --- | --- |
| CSV ingestion | Implemented | Performance and adversarial edge cases |
| Excel ingestion | Implemented | Large-workbook handling |
| Chunked CSV reading | Implemented | Bounded-memory unique tracking, aggregated reports |
| Type inference | Implemented | Ambiguity and precision policies |
| Identifier protection | Implemented | Broader numeric precision safeguards |
| Missing-value handling | Implemented | Specialized policies where justified |
| Outlier handling | Implemented | Additional carefully selected methods |
| Categorical cleaning | Implemented | Encoding integration depth |
| Datetime handling | Implemented | Timezone and DST edge-case validation |
| Data contracts | Implemented | Contract evolution and migrations |
| Schema drift | Implemented | Statistical distribution drift |
| Train/test leakage audit | Implemented | Broader adversarial validation |
| Join diagnostics | Implemented | Performance stress testing |
| Referential integrity | Implemented | More complex relationship checks |
| Deduplication | Implemented | Large-scale deduplication |
| Data validation | Implemented | Custom, conditional, and cross-column checks |
| Decision logging | Implemented | Batch-level historical tracking |
| Cleaning reports | Implemented | Report sinks and monitoring integrations |
| Artifact manifests | Implemented | Runtime dependency compatibility policy |
| Fingerprinting | Implemented | Exact content-integrity fingerprints |
| scikit-learn integration | Implemented | Full estimator compatibility testing |
| CLI | Implemented | Operational integration |
| CI and wheel tests | Implemented | Stress, property, fuzz, and security gates |
| Release provenance | Verified in `2.9.1` | Automated post-publication verification |

Shipped in `2.9.1` (previously merged to `main`):

- `iter_csv_safe()` infers the schema once and reuses it for later chunks.
- Safe ingestion enforces `ColumnSpec(unique=True)`, including across chunks.
- Missing fitted columns are always fatal, with matching documentation.
- Contract uniqueness ignores nulls consistently.
- CI tests minimum, latest, and pandas 3.x dependencies.
- CI installs and exercises the built wheel.
- Release builds generate PEP 740 and GitHub provenance attestations.

---

## 3. Maturity model

### Level 1 — Reliable pandas library

**Reached by `v2.9.0`.** Cleaning, contracts, ingestion, validation, reporting,
reproducibility, and CI are in place and documented. `v2.9.1` hardens the
ingestion and release paths on top of that foundation.

### Level 2 — Production-hardened library

**Next target.** Requires concurrency safety, numeric precision guarantees,
bounded memory, artifact reliability, performance evidence, stronger validation,
statistical drift, and verified releases.

### Level 3 — Ecosystem first choice

**Long-term.** Requires proven performance, stable APIs, integrations, external
users, trusted releases, reviewed examples, and multiple maintainers.

**Decision:** target Level 2 before adding any new data primitive.

---

## 4. Definition of done

This is the standard the library is measured against. A row is only "done" when
the named evidence exists in the repository and in a verified release.

| Standard | Definition of done | Proven by |
| --- | --- | --- |
| Correctness | No silent data corruption or unintended row loss | Invariant tests on every release |
| Input safety | Malformed inputs produce controlled, understandable failures | Adversarial/fuzz suites |
| Data contracts | Schema changes are explicitly detected and handled | Drift matrix tests |
| Transformations | Identical learned rules across training and inference | Leak-safety tests |
| Numerical safety | Precision loss is detected and handled by policy | Boundary-value tests around `2^53` |
| Performance | Workload limits are documented and benchmarked | Benchmark suite and docs |
| Memory | Processing behavior is predictable and tested | Peak-RAM benchmarks |
| Concurrency | Parallel batch operations produce independent results | Concurrent transform tests |
| Reproducibility | Transformations and environments can be inspected and verified | Manifest, fingerprints, artifact tests |
| Serialization | Atomic writes, compatibility policy, trust boundaries | Corruption/interrupt tests |
| Validation | Clear, extensible, reusable quality rules | Validation protocol tests |
| Monitoring | Reports can be retained and integrated externally | Report-sink tests |
| Testing | Adversarial, integration, property, compatibility tests | CI matrix |
| Security | Dependencies, builds, published artifacts verifiable | Audit + post-publish verification |
| DX | Stable, documented, intuitive APIs | API docs and deprecation policy |
| Maintenance | Release policy, deprecation strategy, contributions | Maintainer docs |

---

## 5. Version plan

Each version is a release train. Scope is frozen at the start; items move to the
next train rather than expanding the current one.

| Version | Theme | Backlog | Breaking? |
| --- | --- | --- | --- |
| `2.9.1` | Ship merged hardening; prove provenance | PR #38 fixes + first attested release | No |
| `2.10.0` | Production correctness | Phase 1 | No (new APIs opt-in) |
| `2.11.0` | Large data and performance | Phase 2 | No |
| `2.12.0` | Validation and statistical drift | Phase 3 | No |
| `2.13.0` | Reproducibility and operations | Phase 4 | No |
| `2.14.0` | Testing and security | Phase 5 | No |
| `3.0.0` | Ecosystem readiness | Phase 6 | Possibly |

If Phase 1 slips, split it into `2.10.0` and `2.10.1`. **Do not pull Phase 2
forward to hide incomplete correctness work.**

### `2.9.1` — Merged hardening and provenance proof

Ship what is already merged, then verify the release pipeline end to end.

Deliverables:

- [x] Version bump, changelog, and release documentation prepared for `2.9.1`.
- [x] Release the chunked-schema, uniqueness, missing-column, CI-matrix, and
      installed-wheel changes already on `main`.
- [x] Confirm PyPI shows provenance for both the wheel and the sdist.
- [x] Record the post-publication verification result in this roadmap.
- [x] Clean-install `2.9.1` from PyPI in a fresh environment and run the CLI.

Post-publication verification (2026-11-11, release [v2.9.1](https://github.com/devlprkhan/universal-data-cleaner/releases/tag/v2.9.1),
published from `main` at `aab2070`):

| Check | Result |
| --- | --- |
| PyPI artifacts | wheel `sha256:d02a1fb2…`, sdist `sha256:f7c50cb1…` |
| PyPI Integrity API (wheel) | Provenance present; publisher `GitHub / devlprkhan/universal-data-cleaner`, workflow `publish.yml` |
| PyPI Integrity API (sdist) | Provenance present; same publisher identity |
| `gh attestation verify` (wheel) | Passed; signer `publish.yml@refs/tags/v2.9.1`, source commit `aab2070` |
| `gh attestation verify` (sdist) | Passed; same builder identity |
| Clean install from PyPI | Published wheel installed in a fresh venv resolved from PyPI (pandas 3.1.1, NumPy 2.5.4, scikit-learn 1.9.1) |
| `data-cleaner --version` | Reports `data-cleaner 2.9.1` |
| Installed-wheel smoke test | Fit/transform preserved row count, did not mutate the input, and produced the missing indicators |

Why first: `2.9.0` predates the attestation workflow, so PyPI correctly shows
**no provenance** for it. Verified on 2026-11-11: the PyPI Integrity API returns
`404` for both the wheel and the sdist. This is expected, not a broken signature.
`2.9.1` is the first release that proves provenance and closes the release-gate
rehearsal before the larger `2.10.0`.

### `2.10.0` — Production correctness

Exit criteria:

- [x] All Phase 1 items complete.
- [x] Concurrent `transform()` calls return independent reports.
- [x] Numeric precision and infinity/NaN policies tested at boundaries.
- [x] Artifact writes are atomic and dependency compatibility is enforced.
- [x] Chunked uniqueness tracking has a bounded/disk-backed mode.
- [ ] Full gate, pandas 3.x, minimum dependencies, installed wheel, and docs pass.
- [ ] Post-publication provenance verification passes.

### `2.11.0` — Large data and performance

Exit criteria:

- [ ] A reproducible benchmark suite covers 100K, 1M, and larger datasets.
- [ ] Peak RAM is measured separately from runtime.
- [ ] Ingestion, fit, transform, reporting, and validation are benchmarked
      separately.
- [ ] A supported chunked transformation workflow and report aggregation exist.
- [ ] A documented supported workload is derived from measurements.
- [ ] No performance claim appears without benchmark evidence.

### `2.12.0` — Validation and statistical drift

Exit criteria:

- [ ] A custom validation protocol supports cross-column, conditional, and
      grouped rules.
- [ ] Reference-versus-current distribution comparison ships with PSI,
      Wasserstein distance, missingness deltas, and category deltas.
- [ ] Drift policies and thresholds are documented and reproducible.
- [ ] Failing-row diagnostics are bounded and privacy-safe.
- [ ] Historical batch comparison is available through a report sink.

### `2.13.0` — Reproducibility and operations

Exit criteria:

- [ ] Contracts have explicit versions and documented migration rules.
- [ ] An exact content-integrity fingerprint complements the summary fingerprint.
- [ ] Artifact integrity and runtime compatibility policies are verified.
- [ ] Structured logging and stable error categories exist.
- [ ] A report-sink interface ships with a JSON Lines implementation.
- [ ] Serving and scheduled batch-processing guidance is documented.

### `2.14.0` — Testing and security

Exit criteria:

- [ ] Property-based and fuzz tests cover malformed and adversarial input.
- [ ] Duplicate columns/indexes, unusual dtypes, timezones, and DST cases pass.
- [ ] Serialization corruption and interrupted-write tests pass.
- [ ] scikit-learn estimator checks pass or document deliberate differences.
- [ ] Cross-platform CI covers every claimed platform.
- [ ] Dependency audit and supply-chain review run in CI.

### `3.0.0` — Ecosystem readiness

Only when the work requires a breaking change. Requires:

- [ ] Stable public API and migration guides between releases.
- [ ] Independently reviewed example pipelines and benchmark datasets.
- [ ] Production case studies from real users.
- [ ] More than one active maintainer.
- [ ] A clear release, support, and deprecation policy.

---

## 6. Master backlog

Status legend: `[ ]` not started · `[~]` partially done · `[x]` done.

### Phase 1 — Production correctness (P0/P1)

**Execution tracker: implementation complete in `2.10.0`; release verification
in progress.** Several workstreams are partially addressed; the checkboxes below
are authoritative.

#### 1. Verify actual PyPI provenance

- [x] Add PEP 740 and GitHub provenance generation to the release workflow.
- [x] Verify the published wheel and sdist attestations.
- [x] Add post-publication verification as a release gate, not just a local file
      existence check.
- [x] Verify GitHub build provenance against the repository and release artifact.

Verified on `2.9.1` (2026-11-11): both artifacts carry provenance from
`publish.yml@refs/tags/v2.9.1` at commit `aab2070`, and `gh attestation verify`
passed for the wheel and sdist. Automating this check after publication remains
open.

`v2.9.0` has no provenance because it was published before the workflow existed.
Verified on 2026-11-11 via the PyPI Integrity API (`404` for both artifacts).
Do not claim otherwise; prove it on the next release.

#### 2. Make transformation reporting concurrency-safe

- [x] Introduce a request-specific transformation result that returns the output
      frame and its drift report together.
- [x] Eliminate reliance on the shared last-transform drift state for batch
      findings.
- [x] Keep `transform()` backward compatible and document the concurrency
      contract.
- [x] Add concurrent execution tests.

Target shape (name to be finalized in an ADR):

```python
cleaned, report = cleaner.transform_with_report(X_batch)
```

`drift_report()` remains available for the last call, but it is explicitly
documented as per-instance state, not a concurrency-safe batch result.

#### 3. Harden numerical correctness

- [x] Detect precision loss in numeric conversions.
- [x] Preserve integer and nullable integer dtypes where possible.
- [x] Add explicit `raise`, `warn`, and `coerce` precision policies.
- [x] Test infinity, NaN, very large integers, and boundary values around `2^53`.

#### 4. Harden artifact persistence

- [x] Enforce artifact format and library-major compatibility.
- [x] Implement atomic artifact writes: temp file, validation, `os.replace`,
      cleanup after failure.
- [x] Enforce compatibility with the recorded runtime dependency environment.
- [x] Define and document the compatibility policy.
- [x] Test corruption, truncation, and interrupted writes.
- [x] Keep the pickle trust boundary explicit; evaluate `skops.io` for untrusted
      artifacts. Evaluated for `2.10.0`; not adopted in the 2.x line, and the
      trust boundary is documented in [Artifacts](artifacts.md).

#### 5. Harden chunked ingestion

- [x] Infer the schema once and reuse it across chunks.
- [x] Check `ColumnSpec(unique=True)` within and across chunks.
- [x] Bound memory used by cross-chunk uniqueness tracking.
- [x] Add disk-backed tracking for high-cardinality identifiers.
- [x] Aggregate chunk reports correctly.
- [x] Define supported streaming semantics and their limits.

### Phase 2 — Large-data and performance engineering (P1/P2)

- [ ] Build a proper benchmark suite.
- [ ] Benchmark 100K, 1M, and larger realistic datasets.
- [ ] Test narrow and extremely wide DataFrames.
- [ ] Test high-cardinality categorical and identifier columns.
- [ ] Measure peak RAM, not just execution time.
- [ ] Benchmark ingestion, fit, transform, reporting, and validation separately.
- [ ] Identify unnecessary DataFrame copies.
- [ ] Add chunked transformation and aggregated reporting.
- [ ] Define a documented supported workload based on measured results.
- [ ] Add optional Parquet ingestion using PyArrow.

Do not publish speed claims until the benchmark results support them.
Do not add `partial_fit()` by averaging chunk statistics. Exact medians and
quantiles require a statistically correct global algorithm.

### Phase 3 — Validation and quality engineering (P2)

- [ ] Custom validation protocol.
- [ ] Cross-column expectations.
- [ ] Conditional rules.
- [ ] Grouped validations.
- [ ] Statistical distribution drift (PSI, Wasserstein, missingness, categories).
- [ ] Reference-data comparisons.
- [ ] Row-level diagnostics with bounded, privacy-safe sampling.
- [ ] Historical batch comparison.
- [ ] Optional integration with Pandera and Evidently.

This remains an extensible validation layer, not a Pandera replacement.

### Phase 4 — Reproducibility and operational integration (P2)

- [ ] Explicit contract versions and migration rules.
- [ ] Exact content fingerprints.
- [ ] Artifact integrity verification.
- [ ] Runtime compatibility policies (completed in Phase 1 where applicable).
- [ ] Atomic artifact persistence (completed in Phase 1 where applicable).
- [ ] Aggregated batch reports.
- [ ] Report-sink interface with JSON Lines as the reference implementation.
- [ ] Structured logging and stable error categories.
- [ ] Optional metrics integration.
- [ ] Serving and scheduled batch-processing documentation.

### Phase 5 — Testing and security hardening (P1/P2)

- [ ] Property-based testing with Hypothesis.
- [ ] Fuzz testing malformed and adversarial CSV inputs.
- [ ] Duplicate columns, duplicate indexes, and unusual pandas dtypes.
- [ ] Timezone, daylight-saving, and ambiguous datetime tests.
- [ ] Serialization compatibility and corruption tests.
- [ ] scikit-learn `check_estimator()` / `parametrize_with_checks()`.
- [ ] Cross-platform CI where support is claimed.
- [ ] Security scanning with tools such as `pip-audit`.
- [ ] GitHub Actions dependency pinning and supply-chain review.
- [ ] Test coverage reporting for critical modules.

### Phase 6 — Ecosystem readiness (P3)

- [ ] Stable public API and deprecation policy (largely in place).
- [ ] Migration guides between releases.
- [ ] Compatibility documentation.
- [ ] Independently reviewed example pipelines.
- [ ] External contributor reviews.
- [ ] Real-world benchmark datasets.
- [ ] Production case studies.
- [ ] More than one active maintainer.
- [ ] Clear release and support policies.

---

## 7. Release gates

Every release must pass these gates. A release is not "done" when the tag is
created; it is done when the published artifacts are verified.

### Before opening the release PR

- [ ] Scope matches the version in this roadmap.
- [ ] Every behavior change has tests, including failure and boundary cases.
- [ ] Performance work has benchmark evidence; no unsupported claims.
- [ ] Public API changes have an ADR and a migration note.
- [ ] Documentation matches behavior.

### Local quality gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
uv run --group docs mkdocs build --strict
```

Plus, where applicable:

- pandas 3.x suite;
- minimum-dependency suite;
- installed-wheel smoke test;
- concurrency, property, fuzz, and security checks.

### Before publishing

- [ ] `CHANGELOG.md` updated and version bumped.
- [ ] Distributions inspected.
- [ ] Release notes reviewed.
- [ ] Explicit maintainer approval.
- [ ] Provenance files present for every artifact.

### After publishing (required)

- [ ] Verify PyPI attestations for the wheel and sdist.
- [ ] Verify GitHub build provenance against this repository.
- [ ] Clean-install from PyPI in a fresh environment.
- [ ] Run `data-cleaner --version`, import checks, and a small workflow.
- [ ] Record the result in the release notes and this roadmap.
- [ ] Close the version's tracking issue.

Verification commands:

```bash
uvx "pypi-attestations==0.0.31" verify pypi \
  --repository https://github.com/devlprkhan/universal-data-cleaner \
  pypi:universal_data_cleaner-<version>-py3-none-any.whl

gh attestation verify universal_data_cleaner-<version>-py3-none-any.whl \
  --repo devlprkhan/universal-data-cleaner
```

---

## 8. How versions are executed

This is the operating loop for every version. No release skips a step.

1. **Open a tracking issue** from the version section and copy its checklist.
2. **Freeze scope.** Anything new goes to the next version.
3. **Write an ADR** for public API or behavior changes.
4. **Implement** one backlog item at a time, with tests.
5. **Prove it** with benchmarks, concurrency tests, or adversarial input as the
   item requires.
6. **Update docs and changelog** in the same PR.
7. **Run the full gate** locally and in CI.
8. **Merge only when green**, then prepare the release.
9. **Publish only with explicit approval**, then run the post-publish gate.
10. **Record the result** and close the tracking issue.

Rules:

- Do not mix unrelated feature work into a hardening release.
- Do not weaken a check to make a release pass; fix the cause.
- Do not claim production readiness without evidence in the repository.
- Keep the core dependency set light: pandas, NumPy, scikit-learn, joblib.
  Optional capabilities belong in extras.

---

## 9. Engineering references

Study these for their engineering standard; do not copy their scope.

| Project | What to learn from it | Use here as |
| --- | --- | --- |
| Pandera | Rich, extensible schemas and lazy validation | Validation API reference |
| Feature-engine | sklearn-compatible transformation design | Transformer conventions |
| scikit-learn | Estimator checks, pipelines, composition | Compatibility target |
| Great Expectations | Persistent results and checkpoints | Operational inspiration |
| Evidently | Statistical drift and data-quality metrics | Drift methodology |
| Polars | Lazy and streaming execution | Performance reference |
| Dask | Larger-than-memory execution | Boundary reference |
| skops.io | Safer model serialization | Artifact security option |

Optional integrations are opt-in extras, never core dependencies.

---

## 10. Shipped history

| Version | Theme | Status |
| --- | --- | --- |
| `2.9.1` | Ship merged hardening; prove PyPI and GitHub provenance | Shipped |
| `2.9.0` | Reliability hardening across contracts, joins, artifacts, clipping, ingestion, and API docs | Shipped |
| `2.8.0` | Excel ingestion on the same `IngestionReport` model | Shipped |
| `2.7.0` | `CleanerReport` and the `data-cleaner audit` CLI | Shipped |
| `2.6.0` | Safe CSV ingestion with contract-driven coercion | Shipped |
| `2.5.0` | Train/test split and leakage audit | Shipped |
| `2.4.0` | Expectations, join diagnostics, integrity, and audited dedup | Shipped |
| `2.3.0` | Decision log, manifest, and fingerprints | Shipped |
| `2.2.0` | Typed `src/` package, `py.typed`, CI quality gates | Shipped |
| `2.1.0` | Contracts, drift guard, and identifier protection | Shipped |

See the [changelog](https://github.com/devlprkhan/universal-data-cleaner/blob/main/CHANGELOG.md) for details.

---

## 11. Current step

**Current release: `2.9.1`** — shipped and provenance-verified on 2026-11-11. See
the verification table in section 5.

**Next release: `2.10.0`** — Phase 1, production correctness:
concurrency-safe reporting, numeric precision policies, atomic artifact writes,
dependency compatibility enforcement, and bounded chunk uniqueness tracking.

The strategic rule stands: **do not add another twenty cleaning capabilities.
Prove that the capabilities already shipped behave reliably under demanding
conditions.**

The standard to meet:

> A developer can feed Universal Data Cleaner an unfamiliar, messy tabular
> dataset, explicitly define its expectations, process it safely, inspect every
> important decision, reproduce the result, and confidently pass the cleaned
> output into an ML pipeline.
