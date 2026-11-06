from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from openpyxl import Workbook
from pandas.api import types as ptypes

from data_cleaner import (
    CleanerReport,
    ColumnSpec,
    DataContract,
    IngestionError,
    IngestionReport,
    read_excel_safe,
)
from data_cleaner.__main__ import main


def _write_orders(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Orders"
    sheet.append(["customer_id", "amount", "signup", "active", "plan", "notes"])
    sheet.append(["00123", 1234.5, datetime(2024, 1, 2), True, "pro", "hello"])
    sheet.append(["00456", "$1,234.50", datetime(2024, 2, 3), "N", "free", None])
    sheet["C2"].number_format = "yyyy-mm-dd"
    sheet["C3"].number_format = "yyyy-mm-dd"

    alt = workbook.create_sheet("Alt")
    alt.append(["customer_id", "amount"])
    alt.append(["00999", 5])

    workbook.save(path)


def _write_dates(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Dates"
    sheet.append(["compact", "serial", "custom", "native", "ambiguous"])
    sheet.append(["20240101", 45292, "31/12/2024", datetime(2024, 1, 2), "01/02/2024"])
    sheet.append(["20240102", 45293, "01/01/2025", datetime(2024, 1, 3), "02/03/2024"])
    sheet["D2"].number_format = "yyyy-mm-dd"
    sheet["D3"].number_format = "yyyy-mm-dd"
    workbook.save(path)


def _write_bad_values(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Bad"
    sheet.append(["amount", "event"])
    sheet.append([None, "2024-01-01"])
    sheet.append(["N/A", "bad-date"])
    workbook.save(path)


def _write_numeric_ids(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ids"
    sheet.append(["customer_id", "qty"])
    sheet.append([123, 1])
    sheet.append([456, 2])
    workbook.save(path)


def _write_mixed_dates(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Mixed"
    sheet.append(["event"])
    sheet.append(["20240101"])
    sheet.append([45292])
    sheet.append([datetime(2024, 1, 2)])
    sheet.append(["2024-01-03"])
    workbook.save(path)


def _write_duplicate_headers(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Duplicates"
    sheet.append([1, "1", "value"])
    sheet.append(["a", "b", 1])
    workbook.save(path)


def _orders_contract() -> DataContract:
    return DataContract(
        columns=(
            ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
            ColumnSpec("amount", role="numeric"),
            ColumnSpec("signup", role="datetime"),
            ColumnSpec("active", role="boolean"),
            ColumnSpec("plan", role="category"),
            ColumnSpec("notes", role="text"),
        )
    )


class SafeExcelIngestionTests(unittest.TestCase):
    def test_contract_controls_coercion_and_reports_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.xlsx"
            _write_orders(path)

            frame, report = read_excel_safe(path, contract=_orders_contract())

        self.assertIsInstance(report, IngestionReport)
        self.assertEqual(report.source, str(path))
        self.assertEqual(report.sheet, "Orders")
        self.assertEqual(report.rows, 2)
        self.assertTrue(report.success)
        self.assertTrue(report.has_warnings)
        self.assertEqual(frame["customer_id"].tolist(), ["00123", "00456"])
        self.assertTrue(ptypes.is_object_dtype(frame["customer_id"]))
        self.assertEqual(frame["amount"].tolist(), [1234.5, 1234.5])
        self.assertEqual(
            frame["signup"].tolist(),
            [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-03")],
        )
        self.assertEqual(frame["active"].tolist(), [True, False])
        self.assertEqual(frame["plan"].tolist(), ["pro", "free"])
        self.assertTrue(pd.isna(frame["notes"].iloc[1]))

        checks = set(report.findings["check"])
        self.assertIn("leading_zeros_preserved", checks)
        self.assertIn("currency_symbol", checks)
        self.assertIn("thousands_separator", checks)
        self.assertIn("boolean_tokens", checks)
        self.assertNotIn("numeric_identifier", checks)
        self.assertNotIn("00123", report.findings.to_string())
        self.assertIn("PASS", report.to_markdown())
        self.assertIn("Orders", report.to_markdown())
        payload = report.to_dict()
        self.assertEqual(payload["rows"], 2)
        self.assertEqual(payload["sheet"], "Orders")

    def test_numeric_identifiers_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.xlsx"
            _write_numeric_ids(path)
            contract = DataContract(
                columns=(
                    ColumnSpec("customer_id", role="id"),
                    ColumnSpec("qty", role="numeric"),
                )
            )

            frame, report = read_excel_safe(path, contract=contract)

        self.assertEqual(frame["customer_id"].tolist(), ["123", "456"])
        self.assertTrue(ptypes.is_object_dtype(frame["customer_id"]))
        finding = report.findings.set_index("check").loc["numeric_identifier"]
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(int(finding["count"]), 2)
        self.assertIn("store identifiers as text", finding["message"])
        self.assertTrue(report.success)
        self.assertNotIn("123", report.findings.to_string())

    def test_date_guards_and_explicit_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dates.xlsx"
            _write_dates(path)
            contract = DataContract(
                columns=(
                    ColumnSpec("compact", role="datetime"),
                    ColumnSpec("serial", role="datetime"),
                    ColumnSpec("custom", role="datetime", date_format="%d/%m/%Y"),
                    ColumnSpec("native", role="datetime", date_format="%d/%m/%Y"),
                    ColumnSpec("ambiguous", role="datetime"),
                )
            )

            frame, report = read_excel_safe(path, contract=contract, on_error="ignore")

        self.assertEqual(frame["compact"].iloc[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(frame["serial"].iloc[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(frame["custom"].iloc[0], pd.Timestamp("2024-12-31"))
        self.assertEqual(frame["native"].iloc[0], pd.Timestamp("2024-01-02"))
        self.assertEqual(frame["ambiguous"].iloc[0], pd.Timestamp("2024-01-02"))
        checks = set(report.findings["check"])
        self.assertIn("compact_date", checks)
        self.assertIn("excel_serial_date", checks)
        self.assertIn("ambiguous_date_format", checks)

    def test_mixed_date_representations_in_one_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.xlsx"
            _write_mixed_dates(path)

            frame, report = read_excel_safe(
                path,
                contract=DataContract(columns=(ColumnSpec("event", role="datetime"),)),
                on_error="ignore",
            )
            self.assertEqual(report.rows, 4)
            self.assertEqual(
                frame["event"].tolist(),
                [
                    pd.Timestamp("2024-01-01"),
                    pd.Timestamp("2024-01-01"),
                    pd.Timestamp("2024-01-02"),
                    pd.Timestamp("2024-01-03"),
                ],
            )
            self.assertTrue(report.success)
            checks = set(report.findings["check"])
            self.assertIn("compact_date", checks)
            self.assertIn("excel_serial_date", checks)

            formatted, formatted_report = read_excel_safe(
                path,
                contract=DataContract(
                    columns=(
                        ColumnSpec("event", role="datetime", date_format="%Y-%m-%d"),
                    )
                ),
                on_error="ignore",
            )
            self.assertEqual(formatted["event"].tolist(), frame["event"].tolist())
            self.assertTrue(formatted_report.success)

    def test_undeclared_columns_are_inferred_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ids.xlsx"
            _write_numeric_ids(path)
            contract = DataContract(columns=(ColumnSpec("customer_id", role="id"),))

            frame, report = read_excel_safe(path, contract=contract)

        self.assertEqual(frame["customer_id"].tolist(), ["123", "456"])
        self.assertEqual(frame["qty"].tolist(), [1, 2])
        finding = report.findings.set_index("check").loc["undeclared_column"]
        self.assertIn("typed by inference", finding["message"])
        column = report.columns.set_index("column").loc["qty"]
        self.assertEqual(column["detected_kind"], "numeric")
        self.assertEqual(column["output_kind"], "numeric")

    def test_sheet_selection_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.xlsx"
            _write_orders(path)

            by_name, report = read_excel_safe(path, sheet_name="Alt")
            self.assertEqual(by_name["customer_id"].tolist(), ["00999"])
            self.assertEqual(report.sheet, "Alt")

            by_index, report = read_excel_safe(path, sheet_name=1)
            self.assertEqual(by_index["customer_id"].tolist(), ["00999"])
            self.assertEqual(report.sheet, "Alt")

            with self.assertRaises(ValueError) as caught:
                read_excel_safe(path, sheet_name="Missing")
            self.assertIn("available sheets", str(caught.exception))

            with self.assertRaises(ValueError):
                read_excel_safe(path, sheet_name=10)
            with self.assertRaises(ValueError) as negative:
                read_excel_safe(path, sheet_name=-1)
            self.assertIn("zero or greater", str(negative.exception))
            with self.assertRaises(TypeError):
                read_excel_safe(path, sheet_name=None)  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                read_excel_safe(path, sheet_name=True)

    def test_duplicate_headers_after_stringification_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicates.xlsx"
            _write_duplicate_headers(path)

            with self.assertRaises(ValueError) as caught:
                read_excel_safe(path)

        message = str(caught.exception)
        self.assertIn("duplicate column headers", message)
        self.assertIn("Duplicates", message)

    def test_source_labels_redact_url_credentials_and_query(self) -> None:
        from data_cleaner.ingestion import _source_label

        label = _source_label(
            "https://user:pass@example.com/data/orders.xlsx?token=abc#fragment"
        )
        self.assertEqual(label, "https://example.com/data/orders.xlsx")
        self.assertEqual(
            _source_label("s3://key:secret@bucket/orders.xlsx?signature=abc"),
            "s3://bucket/orders.xlsx",
        )
        self.assertEqual(_source_label(Path("orders.xlsx")), "orders.xlsx")

    def test_unparseable_values_become_missing_and_can_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.xlsx"
            _write_bad_values(path)
            contract = DataContract(
                columns=(
                    ColumnSpec("amount", role="numeric"),
                    ColumnSpec("event", role="datetime"),
                )
            )

            frame, report = read_excel_safe(path, contract=contract, on_error="ignore")

            self.assertFalse(report.success)
            self.assertEqual(len(report.errors), 2)
            self.assertTrue(pd.isna(frame["amount"].iloc[1]))
            self.assertTrue(pd.isna(frame["event"].iloc[1]))

            with self.assertRaises(IngestionError) as caught:
                read_excel_safe(path, contract=contract, on_error="raise")
            self.assertIsInstance(caught.exception.report, IngestionReport)
            self.assertFalse(caught.exception.report.success)
            self.assertIn("Bad", str(caught.exception))
            self.assertEqual(caught.exception.report.location, f"{path} (sheet: Bad)")

            with self.assertLogs("data_cleaner.ingestion", level="WARNING") as captured:
                read_excel_safe(path, contract=contract)
            self.assertTrue(
                any("Excel ingestion" in message for message in captured.output)
            )
            self.assertTrue(any("sheet: Bad" in message for message in captured.output))

    def test_reserved_options_and_type_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.xlsx"
            _write_orders(path)

            with self.assertRaises(TypeError):
                read_excel_safe(path, dtype="int64")
            with self.assertRaises(TypeError):
                read_excel_safe(path, dtype_backend="pyarrow")
            with self.assertRaises(TypeError):
                read_excel_safe(path, parse_dates=["signup"])
            with self.assertRaises(TypeError):
                read_excel_safe(path, true_values=["Y"])
            with self.assertRaises(TypeError):
                read_excel_safe(path, false_values=["N"])
            with self.assertRaises(ValueError):
                read_excel_safe(path, on_error="unknown")  # type: ignore[arg-type]
            with self.assertRaises(TypeError):
                read_excel_safe(path, contract=object())  # type: ignore[arg-type]

    def test_missing_optional_engine_has_a_helpful_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.xlsx"
            _write_orders(path)

            with (
                patch("pandas.ExcelFile", side_effect=ImportError("missing")),
                self.assertRaises(ImportError) as caught,
            ):
                read_excel_safe(path)

        message = str(caught.exception)
        self.assertIn("openpyxl", message)
        self.assertIn("universal-data-cleaner[excel]", message)

    def test_stream_input_is_labelled(self) -> None:
        buffer = io.BytesIO()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Stream"
        sheet.append(["id", "value"])
        sheet.append(["001", 1])
        workbook.save(buffer)
        buffer.seek(0)

        frame, report = read_excel_safe(buffer, on_error="ignore")

        self.assertEqual(report.source, "<stream>")
        self.assertEqual(report.sheet, "Stream")
        self.assertEqual(frame["id"].tolist(), ["001"])

    def test_cleaner_report_from_excel_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.xlsx"
            _write_orders(path)

            report = CleanerReport.from_excel(path, contract=_orders_contract())
            self.assertEqual(report.source, str(path))
            self.assertIsNotNone(report.ingestion)
            assert report.ingestion is not None
            self.assertEqual(report.ingestion.sheet, "Orders")
            self.assertEqual(report.overview["rows"], 2)
            self.assertIn("ingestion", set(report.findings["source"]))
            payload = report.to_dict()
            ingestion_payload = payload["ingestion"]
            assert isinstance(ingestion_payload, dict)
            self.assertEqual(ingestion_payload["sheet"], "Orders")

            output = StringIO()
            with redirect_stdout(output):
                status = main(["audit", str(path), "--format", "json"])
            self.assertEqual(status, 0)
            cli_payload = json.loads(output.getvalue())
            self.assertEqual(cli_payload["ingestion"]["sheet"], "Orders")
            self.assertEqual(cli_payload["source"], str(path))

            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["audit", str(path), "--sheet", "Alt", "--format", "json"]
                )
            self.assertEqual(status, 0)
            cli_payload = json.loads(output.getvalue())
            self.assertEqual(cli_payload["ingestion"]["sheet"], "Alt")
            self.assertEqual(cli_payload["overview"]["rows"], 1)

            output = StringIO()
            with redirect_stdout(output):
                status = main(
                    ["audit", str(path), "--sheet-index", "1", "--format", "json"]
                )
            self.assertEqual(status, 0)
            cli_payload = json.loads(output.getvalue())
            self.assertEqual(cli_payload["ingestion"]["sheet"], "Alt")

            csv_path = Path(directory) / "data.csv"
            csv_path.write_text("a\n1\n", encoding="utf-8")
            error = StringIO()
            with redirect_stderr(error), redirect_stdout(StringIO()):
                status = main(["audit", str(csv_path), "--sheet", "0"])
            self.assertEqual(status, 2)
            self.assertIn("only valid for Excel input", error.getvalue())

            corrupt = Path(directory) / "corrupt.xlsx"
            corrupt.write_bytes(b"not a workbook")
            error = StringIO()
            with redirect_stderr(error), redirect_stdout(StringIO()):
                status = main(["audit", str(corrupt)])
            self.assertEqual(status, 2)
            self.assertIn("error:", error.getvalue())
