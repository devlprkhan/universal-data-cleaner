from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from data_cleaner import (
    CleanerReport,
    DataContract,
    JsonlReportSink,
    compare_distributions,
)


class JsonlReportSinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "reports" / "history.jsonl"
        self.sink = JsonlReportSink(self.path)
        self.frame = pd.DataFrame(
            {
                "amount": np.linspace(0.0, 100.0, 100),
                "plan": ["free", "pro"] * 50,
            }
        )

    def test_missing_file_reads_as_empty(self) -> None:
        self.assertEqual(self.sink.read(), [])
        self.assertTrue(self.sink.history().empty)
        self.assertIsNone(self.sink.latest())
        self.assertTrue(self.path.parent.exists())

    def test_write_and_read_cleaner_report(self) -> None:
        contract = DataContract.from_frame(self.frame)
        report = CleanerReport.from_frame(
            self.frame, source="batch-1", contract=contract
        )
        record = self.sink.write(report)
        self.assertEqual(record["kind"], "cleaner_report")
        self.assertEqual(record["source"], "batch-1")
        self.assertEqual(record["rows"], 100)
        self.assertTrue(record["success"])

        records = self.sink.read()
        self.assertEqual(len(records), 1)
        payload = records[0]["report"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["source"], "batch-1")
        history = self.sink.history()
        self.assertEqual(history.iloc[0]["rows"], 100)
        self.assertEqual(history.iloc[0]["kind"], "cleaner_report")

        latest = self.sink.latest(kind="cleaner_report", source="batch-1")
        self.assertIsNotNone(latest)
        self.assertIsNone(self.sink.latest(kind="drift_report"))

    def test_append_keeps_history_in_order(self) -> None:
        self.sink.write({"kind": "custom", "source": "a", "rows": 1})
        self.sink.write({"kind": "custom", "source": "b", "rows": 2})
        history = self.sink.history()
        self.assertEqual(history["source"].tolist(), ["a", "b"])
        self.assertEqual(history["rows"].tolist(), [1, 2])
        latest = self.sink.latest(kind="custom")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest["source"], "b")
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 2)

    def test_metadata_and_recorded_at(self) -> None:
        record = self.sink.write(
            {"kind": "custom", "rows": 2},
            recorded_at="2026-11-19T00:00:00+00:00",
            metadata={"job": "nightly", "attempt": 2},
        )
        self.assertEqual(record["recorded_at"], "2026-11-19T00:00:00+00:00")
        stored = self.sink.read()[0]
        self.assertEqual(stored["metadata"], {"job": "nightly", "attempt": 2})

    def test_drift_report_and_historical_comparison(self) -> None:
        reference = self.frame
        current = reference.copy()
        current.loc[:9, "amount"] = None
        report = compare_distributions(reference, current)
        stored = self.sink.write(report, source="daily")
        self.assertEqual(stored["kind"], "drift_report")
        self.assertEqual(stored["source"], "daily")
        self.assertTrue(stored["drifted_columns"])
        stored_payload = stored["report"]
        assert isinstance(stored_payload, dict)
        self.assertIsNotNone(stored_payload["reference"])

        later = reference.copy()
        later["amount"] = later["amount"] + 20.0
        historical = self.sink.drift_against_previous(later, source="daily")
        self.assertEqual(historical.reference_rows, len(reference))
        self.assertEqual(historical.current_rows, len(later))
        self.assertEqual(historical.policy, report.policy)
        self.assertTrue(historical.has_drift)

    def test_historical_comparison_requires_a_drift_report(self) -> None:
        with self.assertRaises(LookupError):
            self.sink.drift_against_previous(self.frame)
        self.sink.write({"kind": "cleaner_report", "rows": 1})
        with self.assertRaises(LookupError):
            self.sink.drift_against_previous(self.frame)

    def test_corrupt_line_raises_with_location(self) -> None:
        self.sink.write({"kind": "custom", "rows": 1})
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write("not json\n")
        with self.assertRaises(ValueError) as context:
            self.sink.read()
        self.assertIn("line 2", str(context.exception))

    def test_invalid_report_type(self) -> None:
        with self.assertRaises(TypeError):
            self.sink.write(object())  # type: ignore[arg-type]

    def test_json_lines_are_individually_valid(self) -> None:
        self.sink.write({"kind": "custom", "rows": 1})
        self.sink.write({"kind": "custom", "rows": 2})
        for line in self.path.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            self.assertEqual(payload["schema_version"], 1)

    def test_numpy_scalars_and_string_booleans(self) -> None:
        record = self.sink.write(
            {
                "kind": "custom",
                "rows": np.int64(7),
                "success": "false",
                "errors": np.int64(2),
            }
        )
        self.assertEqual(record["rows"], 7)
        self.assertIs(record["success"], False)
        self.assertEqual(record["errors"], 2)

    def test_unicode_line_separators_do_not_split_records(self) -> None:
        note = "a\u2028b\u0085c"
        self.sink.write({"kind": "custom", "rows": 1}, metadata={"note": note})
        self.sink.write({"kind": "custom", "rows": 2})
        records = self.sink.read()
        self.assertEqual(len(records), 2)
        metadata = records[0]["metadata"]
        assert isinstance(metadata, dict)
        self.assertEqual(metadata["note"], note)

    def test_fsync_file_is_owner_only(self) -> None:
        sink = JsonlReportSink(self.path, fsync=True)
        sink.write({"kind": "custom", "rows": 1})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(sink.read()), 1)


if __name__ == "__main__":
    unittest.main()
