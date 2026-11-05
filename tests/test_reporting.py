from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from data_cleaner import (
    CleanerConfig,
    CleanerReport,
    ColumnSpec,
    DataCleaner,
    DataContract,
    not_null,
)
from data_cleaner.__main__ import main


def audit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "empty": [None, None, None, None],
            "constant": ["x", "x", "x", "x"],
            "sparse": [1.0, None, None, None],
            "value": [1, 2, 3, 4],
        }
    )


class CleanerReportTests(unittest.TestCase):
    def test_profile_findings_and_warning_only_report(self) -> None:
        frame = pd.concat([audit_frame(), audit_frame().iloc[[0]]], ignore_index=True)

        report = CleanerReport.from_frame(frame, source="batch")

        self.assertEqual(report.overview["rows"], 5)
        self.assertEqual(report.overview["columns"], 4)
        self.assertTrue(report.success)
        self.assertTrue(report.has_warnings)
        self.assertFalse(report.has_errors)
        checks = set(report.findings["check"])
        for check in {
            "empty_column",
            "constant_column",
            "high_missing",
            "duplicate_rows",
        }:
            self.assertIn(check, checks)
        self.assertIn("PASS", report.summary())
        self.assertIn("# Cleaner report: batch", report.to_markdown())
        self.assertIn("CleanerReport", repr(report))

        payload: dict[str, Any] = report.to_dict()
        self.assertEqual(payload["source"], "batch")
        self.assertTrue(payload["success"])
        self.assertEqual(payload["library_version"], report.library_version)
        self.assertEqual(payload["overview"]["rows"], 5)
        self.assertTrue(payload["profile"])
        self.assertTrue(payload["findings"])
        json.loads(report.to_json())

    def test_contract_errors_fail_the_report(self) -> None:
        contract = DataContract(
            columns=(
                ColumnSpec("age", role="numeric", min_value=0, max_value=120),
                ColumnSpec("plan", role="category", allowed_values=("free", "pro")),
            )
        )
        frame = pd.DataFrame({"age": [30, 200], "plan": ["free", "enterprise"]})

        report = CleanerReport.from_frame(frame, contract=contract)

        self.assertFalse(report.success)
        self.assertTrue(report.has_errors)
        self.assertIsNotNone(report.drift)
        assert report.drift is not None
        self.assertTrue(report.drift.has_errors)
        checks = set(report.findings["check"])
        self.assertIn("value_out_of_range", checks)
        self.assertIn("unexpected_category", checks)
        self.assertEqual(set(report.errors["source"]), {"contract"})
        with self.assertRaises(ValueError):
            report.raise_if_failed()
        self.assertIn("FAIL", report.to_markdown())
        payload: dict[str, Any] = report.to_dict()
        contract_payload: dict[str, Any] = payload["contract"]
        self.assertTrue(contract_payload["has_errors"])

    def test_validation_results_fail_the_report(self) -> None:
        frame = pd.DataFrame({"age": [1, None], "name": ["a", "b"]})

        report = CleanerReport.from_frame(frame, expectations=not_null("age"))

        self.assertFalse(report.success)
        self.assertIsNotNone(report.validation)
        assert report.validation is not None
        self.assertFalse(report.validation.success)
        self.assertIn("not_null", set(report.findings["check"]))
        self.assertEqual(set(report.errors["source"]), {"validation"})
        payload: dict[str, Any] = report.to_dict()
        validation_payload: dict[str, Any] = payload["validation"]
        self.assertFalse(validation_payload["success"])

    def test_empty_frame_is_reported(self) -> None:
        frame = pd.DataFrame(
            {
                "a": pd.Series([], dtype=object),
                "b": pd.Series([], dtype=float),
            }
        )

        report = CleanerReport.from_frame(frame)

        self.assertEqual(report.overview["rows"], 0)
        self.assertIn("empty_dataset", set(report.findings["check"]))
        self.assertTrue(report.success)
        self.assertNotIn("empty_column", set(report.findings["check"]))

    def test_high_missing_threshold_can_be_adjusted(self) -> None:
        frame = pd.DataFrame({"sparse": [1.0, None, None, None]})

        disabled = CleanerReport.from_frame(frame, high_missing_threshold=None)
        self.assertNotIn("high_missing", set(disabled.findings["check"]))

        strict = CleanerReport.from_frame(frame, high_missing_threshold=10)
        self.assertIn("high_missing", set(strict.findings["check"]))

        with self.assertRaises(ValueError):
            CleanerReport.from_frame(frame, high_missing_threshold=101)

    def test_from_csv_attaches_ingestion_and_profile(self) -> None:
        contract = DataContract(
            columns=(
                ColumnSpec("customer_id", role="id", preserve_leading_zeros=True),
                ColumnSpec("amount", role="numeric"),
            )
        )
        csv = 'customer_id,amount\n001,"$1,234.50"\n002,12\n'

        report = CleanerReport.from_csv(io.StringIO(csv), contract=contract)

        self.assertIsNotNone(report.ingestion)
        self.assertEqual(report.overview["rows"], 2)
        checks = set(report.findings["check"])
        self.assertIn("leading_zeros_preserved", checks)
        self.assertIn("currency_symbol", checks)
        self.assertTrue(report.success)
        payload: dict[str, Any] = report.to_dict()
        self.assertIsNotNone(payload["ingestion"])
        ingestion_payload: dict[str, Any] = payload["ingestion"]
        self.assertEqual(ingestion_payload["rows"], 2)
        self.assertIn("## Ingestion", report.to_markdown())

    def test_from_cleaner_uses_contract_and_decisions(self) -> None:
        train = pd.DataFrame(
            {
                "age": [20, 30, 40, 50, 60],
                "dept": ["a", "b", "a", "b", "a"],
            }
        )
        cleaner = DataCleaner(CleanerConfig()).fit(train)
        batch = pd.DataFrame({"age": [25, 35], "dept": ["a", "b"]})

        report = CleanerReport.from_cleaner(cleaner, batch, source="batch")

        self.assertFalse(report.decisions.empty)
        self.assertIsNotNone(report.drift)
        self.assertEqual(report.overview["rows"], 2)
        self.assertIn("column", report.decisions.columns)
        self.assertIn("action", report.decisions.columns)
        payload: dict[str, Any] = report.to_dict()
        self.assertTrue(payload["decisions"])
        self.assertIsNotNone(payload["contract"])

    def test_to_dict_handles_timestamps_and_missing_values(self) -> None:
        frame = pd.DataFrame(
            {
                "when": pd.Series([pd.Timestamp("2024-01-01"), pd.NaT]),
                "value": [1.5, None],
            }
        )

        report = CleanerReport.from_frame(frame)
        payload = json.loads(report.to_json())

        self.assertEqual(payload["overview"]["rows"], 2)
        self.assertEqual(len(payload["profile"]), 2)
        self.assertTrue(all(isinstance(item, dict) for item in payload["profile"]))


class AuditCliTests(unittest.TestCase):
    def test_audit_markdown_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("value\n1\n2\n", encoding="utf-8")
            stdout = StringIO()

            with redirect_stdout(stdout), redirect_stderr(StringIO()):
                code = main(["audit", str(path)])

            self.assertEqual(code, 0)
            output = stdout.getvalue()
            self.assertIn("# Cleaner report", output)
            self.assertIn("PASS", output)

    def test_audit_json_output_reports_ingestion_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("amount\nN/A\n1\n", encoding="utf-8")
            contract_path = Path(directory) / "contract.json"
            contract = DataContract(columns=(ColumnSpec("amount", role="numeric"),))
            contract_path.write_text(contract.to_json(), encoding="utf-8")
            output_path = Path(directory) / "report.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = main(
                    [
                        "audit",
                        str(path),
                        "--contract",
                        str(contract_path),
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                        "--no-profile",
                    ]
                )

            self.assertEqual(code, 1)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["success"])
            self.assertTrue(
                any(
                    finding["check"] == "unparseable_values"
                    for finding in payload["findings"]
                )
            )

    def test_audit_with_fitted_cleaner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            train = pd.DataFrame(
                {
                    "age": [20, 30, 40, 50, 60],
                    "dept": ["a", "b", "a", "b", "a"],
                }
            )
            cleaner = DataCleaner(CleanerConfig()).fit(train)
            artifact = Path(directory) / "cleaner.joblib"
            cleaner.save(artifact)

            path = Path(directory) / "batch.csv"
            path.write_text("age,dept\n25,a\n35,b\n", encoding="utf-8")
            output_path = Path(directory) / "report.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = main(
                    [
                        "audit",
                        str(path),
                        "--cleaner",
                        str(artifact),
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                        "--no-profile",
                    ]
                )

            self.assertEqual(code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["decisions"])
            self.assertIsNotNone(payload["contract"])

    def test_fail_on_warning_changes_the_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("value\n1\n1\n", encoding="utf-8")
            output_path = Path(directory) / "report.json"

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = main(
                    [
                        "audit",
                        str(path),
                        "--fail-on-warning",
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(code, 1)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["success"])
            self.assertTrue(
                any(finding["severity"] == "warning" for finding in payload["findings"])
            )

    def test_cli_returns_2_for_missing_input_or_bad_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.csv"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(["audit", str(missing)]), 2)

            path = Path(directory) / "data.csv"
            path.write_text("value\n1\n", encoding="utf-8")
            bad = Path(directory) / "contract.json"
            bad.write_text("{not json", encoding="utf-8")
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(["audit", str(path), "--contract", str(bad)]), 2)
