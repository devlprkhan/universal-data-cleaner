from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.api import types as ptypes

from data_cleaner import (
    ColumnSpec,
    DataContract,
    IngestionError,
    IngestionReport,
    combine_ingestion_reports,
    iter_csv_safe,
    read_csv_safe,
)


class SafeCsvIngestionTests(unittest.TestCase):
    def test_contract_controls_coercion_and_reports_normalization(self) -> None:
        csv = (
            "customer_id,amount,signup,active,plan,notes\n"
            '00123,"$1,234.50",2024-01-02,Y,pro,hello\n'
            "00456,12%,2024-02-03,N,free,\n"
        )
        contract = DataContract(
            columns=(
                ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
                ColumnSpec("amount", role="numeric"),
                ColumnSpec("signup", role="datetime"),
                ColumnSpec("active", role="boolean"),
                ColumnSpec("plan", role="category"),
                ColumnSpec("notes", role="text"),
            )
        )

        frame, report = read_csv_safe(io.StringIO(csv), contract=contract)

        self.assertIsInstance(report, IngestionReport)
        self.assertEqual(report.rows, 2)
        self.assertTrue(report.success)
        self.assertFalse(report.has_errors)
        self.assertTrue(report.has_warnings)
        self.assertEqual(frame["customer_id"].tolist(), ["00123", "00456"])
        self.assertTrue(ptypes.is_object_dtype(frame["customer_id"]))
        self.assertEqual(frame["amount"].tolist(), [1234.5, 0.12])
        self.assertTrue(ptypes.is_datetime64_any_dtype(frame["signup"]))
        self.assertEqual(frame["active"].tolist(), [True, False])
        self.assertTrue(ptypes.is_bool_dtype(frame["active"]))
        self.assertEqual(frame["plan"].tolist(), ["pro", "free"])
        self.assertEqual(frame["notes"].iloc[0], "hello")
        self.assertTrue(pd.isna(frame["notes"].iloc[1]))

        checks = set(report.findings["check"])
        self.assertIn("leading_zeros_preserved", checks)
        self.assertIn("currency_symbol", checks)
        self.assertIn("thousands_separator", checks)
        self.assertIn("percent_symbol", checks)
        self.assertIn("boolean_tokens", checks)
        self.assertNotIn("00123", report.findings.to_string())
        self.assertIn("PASS", report.to_markdown())
        self.assertEqual(report.to_dict()["rows"], 2)

    def test_infers_types_without_a_contract(self) -> None:
        csv = (
            "id,qty,when,flag,note,mixed\n"
            "001,1,2024-01-01,yes,alpha,1\n"
            "002,2,2024-02-01,no,beta,two\n"
        )

        frame, report = read_csv_safe(io.StringIO(csv), on_error="ignore")

        self.assertTrue(ptypes.is_object_dtype(frame["id"]))
        self.assertTrue(ptypes.is_numeric_dtype(frame["qty"]))
        self.assertTrue(ptypes.is_datetime64_any_dtype(frame["when"]))
        self.assertTrue(ptypes.is_bool_dtype(frame["flag"]))
        self.assertTrue(ptypes.is_object_dtype(frame["note"]))
        self.assertTrue(ptypes.is_object_dtype(frame["mixed"]))
        self.assertTrue(report.success)
        self.assertIn("leading_zeros_preserved", set(report.findings["check"]))
        self.assertIn("boolean_tokens", set(report.findings["check"]))
        self.assertIn("mixed_types", set(report.findings["check"]))

        detected = report.columns.set_index("column")["detected_kind"].to_dict()
        self.assertEqual(detected["id"], "identifier")
        self.assertEqual(detected["qty"], "numeric")
        self.assertEqual(detected["when"], "datetime")
        self.assertEqual(detected["flag"], "boolean")
        self.assertEqual(detected["mixed"], "text")

    def test_unparseable_contract_values_become_missing_and_can_raise(self) -> None:
        csv = "amount,event\nN/A,2024-01-01\n1,bad-date\n"
        contract = DataContract(
            columns=(
                ColumnSpec("amount", role="numeric"),
                ColumnSpec("event", role="datetime"),
            )
        )

        frame, report = read_csv_safe(
            io.StringIO(csv), contract=contract, on_error="ignore"
        )

        self.assertFalse(report.success)
        self.assertEqual(len(report.errors), 2)
        self.assertTrue(pd.isna(frame["amount"].iloc[0]))
        self.assertTrue(pd.isna(frame["event"].iloc[1]))
        self.assertEqual(int(report.findings["count"].sum()), 2)
        with self.assertRaises(IngestionError) as caught:
            read_csv_safe(io.StringIO(csv), contract=contract, on_error="raise")
        self.assertIsInstance(caught.exception.report, IngestionReport)
        self.assertFalse(caught.exception.report.success)
        with self.assertRaises(IngestionError):
            report.raise_if_failed()

    def test_date_guards_and_explicit_formats(self) -> None:
        csv = (
            "compact,excel,custom,ambiguous\n"
            "20240101,45292,31/12/2024,01/02/2024\n"
            "20240102,45293,01/01/2025,02/03/2024\n"
        )
        contract = DataContract(
            columns=(
                ColumnSpec("compact", role="datetime"),
                ColumnSpec("excel", role="datetime"),
                ColumnSpec("custom", role="datetime", date_format="%d/%m/%Y"),
                ColumnSpec("ambiguous", role="datetime"),
            )
        )

        frame, report = read_csv_safe(
            io.StringIO(csv), contract=contract, on_error="ignore"
        )

        self.assertEqual(frame["compact"].iloc[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(frame["excel"].iloc[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(frame["custom"].iloc[0], pd.Timestamp("2024-12-31"))
        self.assertEqual(frame["ambiguous"].iloc[0], pd.Timestamp("2024-01-02"))
        checks = set(report.findings["check"])
        self.assertIn("compact_date", checks)
        self.assertIn("excel_serial_date", checks)
        self.assertIn("ambiguous_date_format", checks)

    def test_numeric_spellings_are_normalized(self) -> None:
        csv = 'amount\n"$1,234.50"\n(42)\n12.5%\n"1.234,56"\n'

        frame, report = read_csv_safe(io.StringIO(csv), on_error="ignore")

        self.assertEqual(frame["amount"].tolist(), [1234.5, -42.0, 0.125, 1234.56])
        checks = set(report.findings["check"])
        self.assertIn("currency_symbol", checks)
        self.assertIn("thousands_separator", checks)
        self.assertIn("parentheses_negative", checks)
        self.assertIn("percent_symbol", checks)
        self.assertIn("decimal_comma", checks)

    def test_blank_fields_are_missing_but_na_text_is_preserved(self) -> None:
        csv = "notes,amount\nNA,1\n,2\n"

        frame, report = read_csv_safe(io.StringIO(csv), on_error="ignore")

        self.assertEqual(frame["notes"].iloc[0], "NA")
        self.assertTrue(pd.isna(frame["notes"].iloc[1]))
        self.assertEqual(frame["amount"].tolist(), [1.0, 2.0])
        self.assertTrue(report.success)

    def test_empty_column_and_empty_file_are_reported(self) -> None:
        csv = "empty,value\n,\n,\n"

        frame, report = read_csv_safe(io.StringIO(csv), on_error="ignore")

        self.assertTrue(frame["empty"].isna().all())
        self.assertIn("empty_column", set(report.findings["check"]))
        self.assertEqual(report.rows, 2)

        empty_frame, empty_report = read_csv_safe(
            io.StringIO("a,b\n"), on_error="ignore"
        )
        self.assertTrue(empty_frame.empty)
        self.assertEqual(empty_report.rows, 0)
        self.assertEqual(list(empty_frame.columns), ["a", "b"])

    def test_path_input_and_reserved_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("id,value\n001,1\n002,2\n", encoding="utf-8")

            frame, report = read_csv_safe(path, on_error="ignore")

            self.assertEqual(report.source, str(path))
            self.assertEqual(frame["id"].tolist(), ["001", "002"])

        with self.assertRaises(TypeError):
            read_csv_safe(io.StringIO("a\n1\n"), dtype="int64")
        with self.assertRaises(TypeError):
            read_csv_safe(io.StringIO("a\n1\n"), parse_dates=["a"])
        with self.assertRaises(ValueError):
            read_csv_safe(io.StringIO("a\n1\n"), on_error="unknown")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            read_csv_safe(io.StringIO("a\n1\n"), contract=object())  # type: ignore[arg-type]

    def test_contract_reports_missing_and_undeclared_columns(self) -> None:
        csv = "id,extra\n001,x\n"
        contract = DataContract(columns=(ColumnSpec("id", role="id"),))

        frame, report = read_csv_safe(
            io.StringIO(csv), contract=contract, on_error="ignore"
        )

        self.assertEqual(frame["id"].tolist(), ["001"])
        checks = set(report.findings["check"])
        self.assertIn("undeclared_column", checks)
        self.assertNotIn("missing_column", checks)

        contract = DataContract(
            columns=(ColumnSpec("id", role="id"), ColumnSpec("missing"))
        )
        _, report = read_csv_safe(
            io.StringIO("id\n001\n"), contract=contract, on_error="ignore"
        )
        self.assertIn("missing_column", set(report.findings["check"]))
        self.assertFalse(report.success)

    def test_preserve_leading_zeros_without_an_id_role(self) -> None:
        csv = "code\n001\n002\n"
        contract = DataContract(
            columns=(ColumnSpec("code", role="numeric", preserve_leading_zeros=True),)
        )

        frame, report = read_csv_safe(
            io.StringIO(csv), contract=contract, on_error="ignore"
        )

        self.assertEqual(frame["code"].tolist(), ["001", "002"])
        self.assertTrue(ptypes.is_object_dtype(frame["code"]))
        self.assertIn("leading_zeros_preserved", set(report.findings["check"]))

    def test_on_error_warn_logs_but_returns_frame(self) -> None:
        csv = "amount\nnot-a-number\n"
        contract = DataContract(columns=(ColumnSpec("amount", role="numeric"),))
        with self.assertLogs("data_cleaner.ingestion", level="WARNING") as captured:
            frame, report = read_csv_safe(io.StringIO(csv), contract=contract)
        self.assertTrue(pd.isna(frame["amount"].iloc[0]))
        self.assertFalse(report.success)
        self.assertTrue(any("ingestion" in message for message in captured.output))

    def test_iter_csv_safe_matches_full_read(self) -> None:
        csv = "customer_id,amount,signup\n" + "".join(
            f"{index:03d},{index * 1.5},2024-01-{index:02d}\n" for index in range(1, 11)
        )
        contract = DataContract(
            columns=(
                ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
                ColumnSpec("amount", role="numeric"),
                ColumnSpec("signup", role="datetime"),
            )
        )
        full, full_report = read_csv_safe(io.StringIO(csv), contract=contract)
        chunks = list(iter_csv_safe(io.StringIO(csv), contract=contract, chunksize=3))
        self.assertEqual(len(chunks), 4)
        pd.testing.assert_frame_equal(
            pd.concat([frame for frame, _ in chunks], ignore_index=True), full
        )
        self.assertEqual(sum(report.rows for _, report in chunks), full_report.rows)
        self.assertTrue(all(report.rows == 3 for _, report in chunks[:-1]))

    def test_iter_csv_safe_reuses_first_chunk_schema(self) -> None:
        csv = "id,amount\n1,10\n2,20\n3,thirty\n"

        chunks = list(iter_csv_safe(io.StringIO(csv), chunksize=2, on_error="ignore"))

        self.assertEqual(len(chunks), 2)
        first_frame, first_report = chunks[0]
        second_frame, second_report = chunks[1]
        self.assertTrue(ptypes.is_numeric_dtype(first_frame["amount"]))
        self.assertTrue(ptypes.is_numeric_dtype(second_frame["amount"]))
        self.assertTrue(pd.isna(second_frame["amount"].iloc[0]))
        self.assertTrue(first_report.success)
        self.assertIn("unparseable_values", set(second_report.findings["check"]))
        self.assertFalse(second_report.success)

    def test_iter_csv_safe_detects_cross_chunk_duplicates(self) -> None:
        csv = "id,value\n1,a\n2,b\n3,c\n1,d\n"
        contract = DataContract(
            columns=(
                ColumnSpec("id", role="numeric", unique=True),
                ColumnSpec("value", role="text"),
            )
        )

        chunks = list(
            iter_csv_safe(
                io.StringIO(csv), contract=contract, chunksize=2, on_error="ignore"
            )
        )

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0][1].success)
        findings = chunks[1][1].findings
        duplicates = findings[findings["check"] == "duplicate_values"]
        self.assertEqual(int(duplicates["count"].sum()), 1)
        self.assertEqual(duplicates["column"].tolist(), ["id"])
        self.assertIn("earlier chunks", duplicates["message"].iloc[0])

    def test_iter_csv_safe_detects_duplicates_within_a_chunk(self) -> None:
        csv = "id,value\n1,a\n1,b\n2,c\n"
        contract = DataContract(
            columns=(
                ColumnSpec("id", role="numeric", unique=True),
                ColumnSpec("value", role="text"),
            )
        )

        chunks = list(
            iter_csv_safe(
                io.StringIO(csv), contract=contract, chunksize=3, on_error="ignore"
            )
        )

        self.assertEqual(len(chunks), 1)
        duplicates = chunks[0][1].findings
        duplicates = duplicates[duplicates["check"] == "duplicate_values"]
        self.assertEqual(int(duplicates["count"].sum()), 1)
        self.assertNotIn("earlier chunks", duplicates["message"].iloc[0])

    def test_iter_csv_safe_does_not_double_count_cross_chunk_duplicates(self) -> None:
        csv = "id\n1\n1\n1\n"
        contract = DataContract(
            columns=(ColumnSpec("id", role="numeric", unique=True),)
        )

        chunks = list(
            iter_csv_safe(
                io.StringIO(csv), contract=contract, chunksize=2, on_error="ignore"
            )
        )

        first = chunks[0][1].findings
        first = first[first["check"] == "duplicate_values"]
        second = chunks[1][1].findings
        second = second[second["check"] == "duplicate_values"]
        self.assertEqual(int(first["count"].sum()), 1)
        self.assertEqual(int(second["count"].sum()), 1)

    def test_read_csv_safe_enforces_unique_columns_and_ignores_nulls(self) -> None:
        contract = DataContract(
            columns=(ColumnSpec("id", role="numeric", unique=True),)
        )

        duplicated = read_csv_safe(
            io.StringIO("id\n1\n1\n2\n"), contract=contract, on_error="ignore"
        )[1]
        self.assertIn("duplicate_values", set(duplicated.findings["check"]))

        with_nulls = read_csv_safe(
            io.StringIO("id\n1\n\n2\n"), contract=contract, on_error="ignore"
        )[1]
        self.assertNotIn("duplicate_values", set(with_nulls.findings["check"]))

    def test_iter_csv_safe_validates_chunksize(self) -> None:
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                list(
                    iter_csv_safe(
                        io.StringIO("a\n1\n"),
                        chunksize=value,  # type: ignore[arg-type]
                    )
                )

    def test_large_integer_precision_is_reported(self) -> None:
        csv = "big\n9007199254740993\n"
        frame, report = read_csv_safe(io.StringIO(csv), on_error="ignore")
        self.assertTrue(pd.api.types.is_float_dtype(frame["big"]))
        self.assertIn("integer_precision", set(report.findings["check"]))


class StreamingUniquenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = DataContract(
            columns=(ColumnSpec("id", role="numeric", unique=True),)
        )
        self.csv = "id\n1\n2\n1\n3\n"

    def _duplicate_counts(self, **kwargs: object) -> list[int]:
        chunks = list(
            iter_csv_safe(
                io.StringIO(self.csv),
                contract=self.contract,
                chunksize=2,
                on_error="ignore",
                **kwargs,  # type: ignore[arg-type]
            )
        )
        counts = []
        for _, report in chunks:
            findings = report.findings
            duplicates = findings[findings["check"] == "duplicate_values"]
            counts.append(int(duplicates["count"].sum()))
        return counts

    def test_disk_tracking_detects_cross_chunk_duplicates(self) -> None:
        self.assertEqual(self._duplicate_counts(unique_tracking="disk"), [0, 1])

    def test_auto_tracking_migrates_and_still_detects_duplicates(self) -> None:
        self.assertEqual(
            self._duplicate_counts(unique_tracking="auto", unique_tracking_limit=1),
            [0, 1],
        )

    def test_disk_tracking_uses_the_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nested" / "seen.sqlite3"
            counts = self._duplicate_counts(
                unique_tracking="disk", unique_tracking_path=database
            )
            self.assertEqual(counts, [0, 1])
            self.assertTrue(database.exists())

    def test_invalid_tracking_options_are_rejected(self) -> None:
        for kwargs in (
            {"unique_tracking": "bogus"},
            {"unique_tracking_limit": 0},
            {"unique_tracking_limit": True},
        ):
            with self.assertRaises(ValueError):
                list(
                    iter_csv_safe(
                        io.StringIO(self.csv),
                        contract=self.contract,
                        **kwargs,
                    )
                )

    def test_combine_ingestion_reports_rolls_up_chunks(self) -> None:
        reports = [
            report
            for _, report in iter_csv_safe(
                io.StringIO(self.csv),
                contract=self.contract,
                chunksize=2,
                on_error="ignore",
            )
        ]

        combined = combine_ingestion_reports(reports)

        self.assertEqual(combined.rows, 4)
        self.assertEqual(combined.source, reports[0].source)
        self.assertEqual(
            len(combined.findings),
            sum(len(report.findings) for report in reports),
        )
        self.assertIn("duplicate_values", set(combined.findings["check"]))
        self.assertEqual(list(combined.columns["column"]), ["id"])

    def test_combine_ingestion_reports_handles_an_empty_batch(self) -> None:
        combined = combine_ingestion_reports([], source="empty.csv")
        self.assertEqual(combined.rows, 0)
        self.assertEqual(combined.source, "empty.csv")
        self.assertTrue(combined.findings.empty)
        self.assertTrue(combined.columns.empty)
        self.assertTrue(combined.success)
