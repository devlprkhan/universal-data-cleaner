# Batch reporting

`CleanerReport` answers three questions about one batch in a single object: what
does it look like, what changed, and should it reach the model? It composes
profiling, contract drift, validation, ingestion, and the cleaner's decision log
without transforming the data.
{: .lead }

## Build a report from a DataFrame

```python
from data_cleaner import CleanerReport

report = CleanerReport.from_frame(batch, source="validation_batch")

print(report.summary())
print(report.findings)
```

The frame is never modified. `from_frame()` reads the batch, records dataset and
column metrics, and emits warning-severity findings for common profile problems:

| Finding | Meaning |
| --- | --- |
| `empty_dataset` | The batch has no rows or no columns |
| `empty_column` | A column has no non-null values |
| `constant_column` | A column has a single distinct value |
| `high_missing` | Missingness is at or above `high_missing_threshold` (default `50%`) |
| `duplicate_rows` | The batch contains exact duplicate rows |

Disable profiling entirely for very large batches:

```python
report = CleanerReport.from_frame(batch, include_profile=False)
```

Or change the missingness threshold:

```python
report = CleanerReport.from_frame(batch, high_missing_threshold=20)
report = CleanerReport.from_frame(batch, high_missing_threshold=None)  # disable
```

## Add a contract and expectations

```python
report = CleanerReport.from_frame(
    batch,
    contract=contract,
    expectations=[not_null("customer_id"), between("age", 0, 120)],
)
```

Contract and expectation failures become error-severity findings. Warnings do not
fail the batch:

```python
report.success  # False only when an error-severity finding exists
report.errors  # DataFrame of error findings
report.warnings  # DataFrame of warning findings
report.raise_if_failed("Batch rejected")
```

## Audit a CSV or Excel file

```python
from data_cleaner import CleanerReport

report = CleanerReport.from_csv("incoming.csv", contract=contract)
report = CleanerReport.from_excel(
    "incoming.xlsx",
    contract=contract,
    sheet_name="Orders",
)
```

`from_csv()` and `from_excel()` read through
[`read_csv_safe()` and `read_excel_safe()`](ingestion.md) and attach the resulting
`IngestionReport`, so ingestion findings appear alongside contract and profile
findings. They default to `on_error="ignore"` so a report is always returned;
error findings still make `report.success` false. Pass `on_error="raise"` to stop
at the first unparseable value instead.

Excel support requires the optional `excel` extra:

```bash
pip install "universal-data-cleaner[excel]"
```

## Audit against a fitted cleaner

```python
report = CleanerReport.from_cleaner(cleaner, batch, source="production")
```

The fitted contract supplies the drift section and the cleaner's decision log is
attached. The cleaner is not re-fitted and the batch is not transformed.

## Findings and output

Every finding has the same columns:

| Column | Meaning |
| --- | --- |
| `source` | `profile`, `contract`, `validation`, or `ingestion` |
| `column` | Affected column, or `*` for dataset-level findings |
| `check` | Machine-readable check name, for example `missing_column` |
| `severity` | `error` or `warning` |
| `message` | Human-readable explanation |
| `count` | Rows or occurrences affected |

Findings are de-duplicated per `(column, check, severity)` and sorted by
severity. The whole report renders consistently:

```python
report.to_markdown()  # overview, findings, profile, contract, validation, ingestion, decisions
report.to_dict()  # JSON-friendly structure
report.to_json(indent=2)
```

Reports contain column names, counts, and messages, never raw cell values, so they
are safe to log or attach to a build artifact.

## Command-line audit

The same report is available from the terminal:

```bash
python -m data_cleaner audit incoming.csv
python -m data_cleaner audit incoming.xlsx --sheet Orders
```

The installed console script is equivalent:

```bash
data-cleaner audit incoming.xlsx --sheet Orders
```

The command detects CSV and Excel input from the file extension. Common options:

| Option | Effect |
| --- | --- |
| `--contract contract.json` | Read under `DataContract.from_json()` and check drift |
| `--cleaner cleaner.joblib` | Load a fitted cleaner and use its contract and decisions |
| `--sheet NAME` | Excel worksheet to audit by name (defaults to the first sheet) |
| `--sheet-index N` | Excel worksheet to audit by zero-based index |
| `--name NAME` | Dataset name in the profile (defaults to the file stem) |
| `--format markdown\|json` | Output format written to stdout or `--output` |
| `--output PATH` | Write the report to a file instead of stdout |
| `--no-profile` | Skip the column profile for faster large-file audits |
| `--fail-on-warning` | Treat warnings as a failing exit status |

`--contract` and `--cleaner` are mutually exclusive. `--sheet` and
`--sheet-index` are mutually exclusive, accept only non-negative indices, and are
valid only for Excel input.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The report succeeded |
| `1` | Error findings exist, or warnings exist with `--fail-on-warning` |
| `2` | The input could not be read, a contract/artifact could not be loaded, or a spreadsheet engine is missing |

Use the exit code in CI or a pre-model gate:

```bash
python -m data_cleaner audit incoming.csv \
  --contract artifacts/contract.json \
  --format json \
  --output artifacts/audit.json \
  --fail-on-warning
```

## What the report does not do

- It does not fit or transform. Call `cleaner.transform()` separately when the
  batch passes review.
- It does not install optional spreadsheet engines. Install the `excel` extra for
  `.xlsx` and `.xlsm`, or another pandas engine for legacy formats.
- It cannot recover leading zeros that Excel already discarded when an ID was
  stored as a number. Store identifiers as text in the workbook.
- It does not replace the cleaner's own drift policy. `on_drift` still controls
  `transform()`; the report is a review layer around it.

## Related guides

- [Safe ingestion](ingestion.md): the `IngestionReport` attached to CSV and Excel audits.
- [Contracts & drift](contracts.md): the checks reported in the contract section.
- [Validation, joins & dedup](validation-joins.md): expectations and integrity.
- [Production guide](production.md): wiring the audit into a deployment gate.
- [API reference](api.md#reporting): generated signatures and docstrings.
