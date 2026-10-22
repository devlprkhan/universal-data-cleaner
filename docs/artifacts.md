# Artifacts & reproducibility

A fitted cleaner is only useful if the next process can prove it is using the
same rules. This page covers the audit trail, manifests, fingerprints, and saved
artifacts that make that possible.

## The decision log

Every learned or configured rule is recorded during `fit()`:

```python
log = cleaner.decision_log()
log[log["action"] == "cap_outliers"]
```

The columns are:

| Column | Meaning |
| --- | --- |
| `column` | The source column |
| `action` | What happened, such as `impute` or `cap_outliers` |
| `reason` | Why it happened |
| `source` | `learned`, `config`, `contract`, or `inferred` |
| `before` | The value before the decision, when relevant |
| `after` | The value after the decision, when relevant |

Typical actions include `impute`, `cap_outliers`, `expand_datetime`,
`add_missing_indicator`, `drop_column`, and `unseen_category_policy`.

The log is a tidy DataFrame, so it can be shipped to an experiment tracker or
compared between two model versions.

## The artifact manifest

`to_manifest()` builds a JSON-serializable description of the fitted cleaner:

```python
import json

manifest = cleaner.to_manifest(X_train, include_fingerprint=True)
print(json.dumps(manifest, indent=2))
```

The manifest contains:

- library and artifact versions
- pandas, numpy, and scikit-learn versions
- the cleaner configuration and contract
- the input schema and output columns
- fitted state and the decision log
- an optional training fingerprint
- a UTC timestamp

Use `include_fingerprint=True` when you want lineage without storing the data.
Set `CleanerConfig(fingerprint_on_fit=True)` to compute the training fingerprint
once during `fit()`, so `to_manifest()` needs no data later.

## Save and load

```python
cleaner.save("artifacts/data_cleaner.joblib")

restored = DataCleaner.load("artifacts/data_cleaner.joblib")
X_new_clean = restored.transform(X_new)
```

`save()` embeds the manifest and the training fingerprint in the artifact.
`load(verify_version=True)` is the default and refuses artifacts written by an
incompatible version. The artifact format for the 2.x line is `2`.

Use `artifact_manifest()` on a loaded cleaner to inspect what was stored:

```python
restored.artifact_manifest()
```

## Fingerprints

A fingerprint is a stable SHA-256 hash of the schema plus summary statistics.
It never hashes raw values, so it is safe to log and compare across systems.

```python
from data_cleaner import (
    assert_schema_stable,
    compare_fingerprints,
    fingerprint_dataframe,
)

expected = fingerprint_dataframe(X_train)
actual = fingerprint_dataframe(X_new)

same = compare_fingerprints(expected, actual)
assert_schema_stable(X_new, expected)  # raises ValueError on schema/stat drift
```

Use fingerprints to:

- verify a batch still has the expected schema and rough distribution
- detect accidental changes between training and serving
- store a compact lineage marker next to a model

Fingerprints are not a substitute for a contract. They summarize; a
[contract](contracts.md) states what is allowed.

## A practical artifact bundle

A reproducible model artifact usually contains:

```text
artifacts/
├── data_cleaner.joblib    # fitted cleaner + embedded manifest
├── contract.json          # reviewable schema and roles
└── manifest.json          # optional external copy for the model registry
```

```python
cleaner.save("artifacts/data_cleaner.joblib")
contract.to_json()  # write this to artifacts/contract.json
manifest = cleaner.to_manifest(X_train, include_fingerprint=True)
```

## Versioning notes

- The package version is exposed as `data_cleaner.__version__`.
- The artifact format version is separate and remains `2` for the 2.x line.
- `load()` checks the artifact version by default.
- A contract or configuration change can change the manifest without changing
  the artifact format.

## Next steps

- [Contracts & drift](contracts.md) for the schema rules referenced by manifests.
- [Production guide](production.md) for how to use these artifacts safely.
- [API reference](api.md) for the exact method signatures.
