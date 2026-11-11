# ADR 0001: Prioritize production hardening over new data primitives

- **Status:** Accepted
- **Date:** 2026-11-11
- **Deciders:** Maintainers
- **Supersedes:** None
- **Related:** [Roadmap](../roadmap.md), [Upcoming](../upcoming.md)

## Context

By `v2.9.0` the library already covers the intended lifecycle: safe CSV/Excel
ingestion, contracts and drift, cleaning and transformation, validation, join and
split audits, reporting, fingerprints, artifacts, and scikit-learn integration.

A production-readiness review identified that the remaining risk is not missing
cleaning features. It is the behaviour of existing features under demanding
conditions:

- `transform()` stores the latest drift findings in mutable instance state, so
  concurrent batches can overwrite each other's reports.
- Numeric conversion can silently lose precision above `2^53`.
- Artifact writes are not atomic and runtime dependency compatibility is not
  enforced.
- Cross-chunk uniqueness tracking grows with cardinality, so chunked ingestion is
  not strictly bounded-memory.
- Validation is useful but not extensible.
- Drift detection covers schema, not statistical distributions.
- Reports are per batch, with no supported way to persist or compare history.
- `v2.9.0` was published before the provenance workflow existed, so PyPI
  correctly shows no provenance for it. Verified on 2026-11-11 through the PyPI
  Integrity API for both the wheel and the sdist.

Adding more cleaning primitives would increase surface area without reducing
these risks.

## Decision

1. **Target maturity Level 2 first.** The next releases harden correctness,
   large-data behaviour, validation, reproducibility, testing, and release
   verification before adding new data primitives.
2. **Adopt the version train in the roadmap.** `2.9.1` proves the release gate;
   `2.10.0` through `2.14.0` execute Phases 1 through 5; `3.0.0` is reserved for
   ecosystem readiness and breaking changes only.
3. **Make every claim evidence-based.** Each behaviour change ships with tests;
   each performance claim ships with benchmarks; each release is verified after
   publication.
4. **Keep the boundary.** Do not rebuild orchestration, observability,
   distributed compute, or enterprise governance. Integrate through reports,
   sinks, and optional extras.
5. **Preserve the existing safety contract.** Fit on training data only, never
   mutate input, never drop inference rows, and keep the public API backwards
   compatible within the 2.x line.

## Consequences

### Positive

- Users get predictable concurrency, numeric, memory, and artifact behaviour
  instead of new surface area.
- Every release has an explicit exit criterion and a post-publish verification
  step.
- The roadmap becomes an auditable plan that can be reviewed and revised per
  version.
- The project stays dependency-light and composable with established tools.

### Negative

- New cleaning features are deliberately deferred.
- Some work, such as concurrency-safe reporting, requires a new opt-in API in
  addition to the existing `transform()` method.
- Performance and security work will take multiple releases to complete.

### Neutral

- Optional integrations (Pandera, Evidently, PyArrow, skops) remain extras.
- `digest` and exact-content fingerprinting will coexist with the existing
  summary fingerprint rather than replacing it.

## Implementation notes

- `transform()` stays backward compatible. A new method returns the frame and
  its drift report together, and the shared last-report state is documented as
  not concurrency-safe.
- Precision policies are explicit and opt-in where a default change could alter
  output dtypes or values.
- Artifact writes use a temporary file in the destination directory, validate
  the write, then call `os.replace()`, cleaning up on failure.
- Chunked uniqueness tracking gets a disk-backed mode rather than unbounded
  in-memory growth.
- Provenance verification is a release gate, not a local file check.

## Verification

This decision is successful when:

- Phases 1 through 5 are complete with evidence in the repository.
- `2.9.1` and later releases show verified PyPI and GitHub provenance.
- A clean install from PyPI passes the same smoke workflow as the wheel built in
  CI.
- The supported workload and limits are documented from benchmarks.
