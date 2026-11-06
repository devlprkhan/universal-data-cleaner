# Safe ingestion

CSV and Excel type inference is where many silent data bugs begin: an ID loses
its leading zeros, a currency field becomes text, or a date column arrives as an
integer. `read_csv_safe()` and `read_excel_safe()` read every field as text
first, apply an explicit contract or a conservative inference pass, and return an
audit report with the frame.
{: .lead }

## Why read as text first

`pandas.read_csv()` infers types independently for every file. That is convenient
for exploration and dangerous for a training pipeline:

- `00123` becomes `123`, so the identifier no longer joins correctly.
- `$1,234.50` becomes an object column instead of a number.
- `20240101` becomes an integer, not a date.
- a mixed column becomes `object` with no explanation.

The safe readers make the conversion decision visible. They never change a value
without recording a finding.

## A contract-driven read

Declare the columns whose type matters, then read:

```python
from data_cleaner import ColumnSpec, DataContract, read_csv_safe

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
        ColumnSpec("amount", role="numeric"),
        ColumnSpec("signup_date", role="datetime"),
        ColumnSpec("active", role="boolean"),
        ColumnSpec("plan", role="category"),
        ColumnSpec("notes", role="text"),
    ],
)

frame, report = read_csv_safe(
    "export.csv",
    contract=contract,
    on_error="warn",
)

print(report.findings)
```

Declared columns use their contract role and date format. Undeclared columns are
inferred conservatively and reported as `undeclared_column`, with their detected
and output kinds in `report.columns`, so a new upstream column is always visible
in the audit.

## Excel input

Excel support is optional so the core install stays dependency-light. Install the
extra, which adds `openpyxl` for `.xlsx` and `.xlsm` files:

```bash
pip install "universal-data-cleaner[excel]"
```

```bash
uv add "universal-data-cleaner[excel]"
```

Then use the same contract with `read_excel_safe()`:

```python
from data_cleaner import read_excel_safe

frame, report = read_excel_safe(
    "export.xlsx",
    contract=contract,
    sheet_name="Orders",
    on_error="warn",
)

report.sheet  # "Orders"
print(report.findings)
```

`sheet_name` accepts a worksheet name or a non-negative zero-based index and
defaults to the first sheet. The report records the resolved sheet name. The
reader applies the same identifier, date, numeric, and boolean guards as
`read_csv_safe()`.

Excel stores cell types, not just text, so a few behaviors differ:

- Date guards run per cell. A single datetime column can mix real date cells,
  compact `YYYYMMDD` values, and numeric serials; each cell is parsed and the
  matching finding is recorded.
- A real date cell is parsed directly even when the contract declares a
  `date_format`; the format is applied to text and compact cells in that column.
- A number in a datetime column is treated as an Excel serial date and flagged
  with `excel_serial_date`.
- A contract ID column whose cells are numbers emits `numeric_identifier`.
  Excel has already discarded the leading zeros, so the warning tells you to
  store identifiers as **text** in the workbook.
- Duplicate column headers after string conversion are rejected with a clear
  error instead of silently collapsing columns.

Other workbook formats need the matching pandas engine: `xlrd` for `.xls`,
`pyxlsb` for `.xlsb`, and `odfpy` for `.ods`. Install one of those if you use
legacy files; `read_excel_safe()` raises a clear error when the engine is
missing.

## Inspect the report

`IngestionReport` has two tables and the source location:

```python
report.source  # file path or <stream>
report.sheet  # resolved Excel worksheet, or None for CSV
report.success  # False when an error-severity finding exists
report.findings  # column, check, severity, message, count
report.columns  # detected kind, output kind, dtype, non-null, missing
report.errors
report.warnings
report.summary()
report.to_markdown()
report.to_dict()
report.raise_if_failed()
```

The report deliberately contains counts and column names, not raw cell values.
That makes it safe to log or attach to a build artifact. URL source labels are
stored without credentials or query strings, so a signed or authenticated URL is
not copied into logs.

## Error policy

```python
frame, report = read_csv_safe("export.csv", contract=contract, on_error="warn")
frame, report = read_excel_safe("export.xlsx", contract=contract, on_error="warn")
```

| Value | Behavior |
| --- | --- |
| `"warn"` | Log findings and return the typed frame (default) |
| `"raise"` | Raise `IngestionError` when an error-severity finding exists |
| `"ignore"` | Return the report without logging |

Values that cannot be parsed in a declared numeric, datetime, or boolean column
become missing values and produce an error finding. Use `"raise"` when a failed
conversion should stop the job; the exception carries the full report:

```python
from data_cleaner import IngestionError

try:
    frame, report = read_csv_safe("export.csv", contract=contract, on_error="raise")
except IngestionError as exc:
    print(exc.report.findings)
    raise
```

## What gets normalized

| Input | Result | Report check |
| --- | --- | --- |
| Empty or whitespace-only field | Missing value | `report.columns.missing` |
| `1,234.50` | `1234.5` | `thousands_separator` |
| `$1,234.50` | `1234.5` | `currency_symbol` |
| `12%` | `0.12` | `percent_symbol` |
| `(42)` | `-42.0` | `parentheses_negative` |
| `1.234,56` | `1234.56` | `decimal_comma` |
| `Y` / `N` | `True` / `False` | `boolean_tokens` |
| `20240101` in a datetime column | a parsed date | `compact_date` |
| Excel serial `45292` in a datetime column | a parsed date | `excel_serial_date` |
| A real Excel date cell | a parsed date | none (already a date) |
| `00123` in an ID column | text `"00123"` | `leading_zeros_preserved` |
| Numeric cells in a contract ID column | kept as text, zeros unrecoverable | `numeric_identifier` |
| `01/02/2024` without a format | parsed, but flagged | `ambiguous_date_format` |

For ambiguous dates, pass the format explicitly:

```python
ColumnSpec("signup_date", role="datetime", date_format="%d/%m/%Y")
```

## Inference without a contract

A contract is recommended, but it is optional. Without one, the reader uses a
conservative inference pass:

| Detected | Output |
| --- | --- |
| Digits with a leading zero | Text (identifier) |
| Every value parses as a number | `float64` |
| Every value is a text boolean token | `boolean` |
| Every value has a date structure and parses | `datetime64` |
| Anything mixed or unparseable | Text |

`YYYYMMDD` and Excel serial dates are **not** inferred as dates without a
contract; they stay numeric to avoid turning identifiers into timestamps. Declare
the column as `role="datetime"` when those values are dates.

A mixed text/number column stays text and emits `mixed_types`. This is a
warning, not a data loss: the original strings remain available for review.

## Limitations

- Excel support requires the optional `excel` extra (or another pandas engine).
- Excel discards leading zeros when an identifier is stored as a number. The
  reader can warn with `numeric_identifier`, but it cannot recover the lost
  characters. Store identifiers as text in the workbook.
- Date inference is deliberately conservative. Use `ColumnSpec.date_format` for
  ambiguous day/month orders.
- A contract describes the destination schema; it does not repair values. Invalid
  values become missing and are reported so the cleaner or a validation step can
  handle them intentionally.

## Related guides

- [Contracts & drift](contracts.md): roles, allowed values, ranges, and formats.
- [Batch reporting](reporting.md): combine ingestion, contracts, and decisions.
- [Quickstart](quickstart.md): fit a cleaner on the ingested frame.
- [Production guide](production.md): error policies and deployment checks.
- [API reference](api.md#safe-ingestion): generated signatures and docstrings.
