from __future__ import annotations

import unittest
from typing import Any

import numpy as np
import pandas as pd

from data_cleaner import SplitAudit, audit_split


def clean_split(
    n: int = 30,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    index = np.arange(n)
    train = pd.DataFrame(
        {
            "x": index,
            "y": (index * 7) % n,
            "segment": [("a", "b", "c")[int(value) % 3] for value in index],
        }
    )
    test = pd.DataFrame(
        {
            "x": index,
            "y": (index * 7 + 15) % n,
            "segment": [("a", "b", "c")[int(value) % 3] for value in index],
        }
    )
    y_train = pd.Series([int(value) % 2 for value in index])
    y_test = pd.Series([int(value) % 2 for value in index])
    return train, test, y_train, y_test


def checks(report: SplitAudit) -> set[str]:
    return set(report.findings["check"])


def findings_for(report: SplitAudit, check: str) -> pd.DataFrame:
    return report.findings[report.findings["check"] == check]


class CleanSplitTests(unittest.TestCase):
    def test_clean_split_has_no_findings(self) -> None:
        train, test, y_train, y_test = clean_split()
        report = audit_split(train, test, y_train, y_test)

        self.assertIsInstance(report, SplitAudit)
        self.assertTrue(report.valid)
        self.assertTrue(report.findings.empty)
        self.assertTrue(report.errors.empty)
        self.assertTrue(report.warnings.empty)
        self.assertFalse(report.has_errors)
        self.assertFalse(report.has_warnings)
        self.assertEqual(report.train_rows, 30)
        self.assertEqual(report.test_rows, 30)
        self.assertEqual(report.task, "classification")
        self.assertEqual(report.duplicate_overlap_rows, 0)
        self.assertEqual(report.near_duplicate_overlap_rows, 0)
        self.assertEqual(report.group_overlap, 0)
        self.assertEqual(report.time_overlap_rows, 0)

        self.assertEqual(report.summary(), "no split issues detected")
        self.assertIn("PASS", report.to_markdown())
        self.assertIn("no split issues detected", report.to_markdown())
        report.raise_if_invalid()

        as_dict = report.to_dict()
        self.assertTrue(as_dict["valid"])
        self.assertEqual(as_dict["task"], "classification")
        self.assertEqual(as_dict["findings"], [])

    def test_report_helpers_on_warning_only(self) -> None:
        train = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        test = pd.DataFrame({"x": [1.04, 20.0, 30.0]})
        report = audit_split(
            train, test, near_duplicate_decimals=1, constant_threshold=1.0
        )

        self.assertTrue(report.valid)
        self.assertFalse(report.has_errors)
        self.assertTrue(report.has_warnings)
        self.assertEqual(report.near_duplicate_overlap_rows, 1)
        self.assertIn("near_duplicate_rows", checks(report))
        self.assertIn("PASS", report.to_markdown())
        self.assertIn("[warning]", report.summary())
        report.raise_if_invalid()

    def test_report_helpers_on_error(self) -> None:
        train = pd.DataFrame({"x": [1, 2, 3]})
        test = pd.DataFrame({"x": [3, 4, 5]})
        report = audit_split(train, test)

        self.assertFalse(report.valid)
        self.assertTrue(report.has_errors)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("duplicate_rows", checks(report))
        self.assertIn("FAIL", report.to_markdown())
        self.assertIn("[error]", report.summary())
        self.assertEqual(report.to_dict()["duplicate_overlap_rows"], 1)
        with self.assertRaises(ValueError):
            report.raise_if_invalid()


class DuplicateLeakageTests(unittest.TestCase):
    def test_exact_overlap_is_an_error(self) -> None:
        train = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        test = pd.DataFrame({"a": [3, 4, 5], "b": ["z", "q", "r"]})
        report = audit_split(train, test)

        self.assertFalse(report.valid)
        self.assertEqual(report.duplicate_overlap_rows, 1)
        self.assertEqual(
            findings_for(report, "duplicate_rows").iloc[0]["severity"], "error"
        )

    def test_near_duplicate_uses_rounding(self) -> None:
        train = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        test = pd.DataFrame({"x": [1.04, 20.0, 30.0]})

        report = audit_split(train, test, near_duplicate_decimals=1)
        self.assertEqual(report.duplicate_overlap_rows, 0)
        self.assertEqual(report.near_duplicate_overlap_rows, 1)
        self.assertIn("near_duplicate_rows", checks(report))

        report = audit_split(train, test, near_duplicate_decimals=2)
        self.assertEqual(report.near_duplicate_overlap_rows, 0)

        report = audit_split(train, test, near_duplicate_decimals=None)
        self.assertEqual(report.near_duplicate_overlap_rows, 0)

    def test_id_columns_are_excluded_from_duplicate_checks(self) -> None:
        train = pd.DataFrame({"id": ["a", "b"], "x": [1, 2]})
        test = pd.DataFrame({"id": ["c", "d"], "x": [1, 2]})

        report = audit_split(train, test, id_cols="id")
        self.assertEqual(report.duplicate_overlap_rows, 2)
        self.assertFalse(report.valid)

        report = audit_split(train, test)
        self.assertEqual(report.duplicate_overlap_rows, 0)


class GroupLeakageTests(unittest.TestCase):
    def test_combined_group_labels_are_split(self) -> None:
        train = pd.DataFrame({"x": [1, 2, 3]})
        test = pd.DataFrame({"x": [4, 5]})
        report = audit_split(train, test, groups=[10, 20, 30, 30, 40])

        self.assertFalse(report.valid)
        self.assertEqual(report.group_overlap, 1)
        self.assertIn("group_leakage", checks(report))
        self.assertEqual(
            findings_for(report, "group_leakage").iloc[0]["severity"], "error"
        )

    def test_separate_group_labels_and_no_leakage(self) -> None:
        train = pd.DataFrame({"x": [1, 2, 3]})
        test = pd.DataFrame({"x": [4, 5]})

        report = audit_split(train, test, groups=[10, 20, 30], groups_test=[30, 40])
        self.assertEqual(report.group_overlap, 1)
        self.assertFalse(report.valid)

        report = audit_split(train, test, groups=[10, 20, 30], groups_test=[40, 50])
        self.assertEqual(report.group_overlap, 0)
        self.assertNotIn("group_leakage", checks(report))

    def test_null_group_labels_are_reported(self) -> None:
        train = pd.DataFrame({"x": [1, 2, 3]})
        test = pd.DataFrame({"x": [4, 5]})
        report = audit_split(train, test, groups=[10, None, 30], groups_test=[40, None])

        self.assertIn("group_nulls", checks(report))
        self.assertEqual(report.group_overlap, 0)
        self.assertTrue(report.valid)


class TemporalLeakageTests(unittest.TestCase):
    def test_train_after_test_is_an_error(self) -> None:
        train = pd.DataFrame(
            {
                "event_time": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03"]
                ),
                "x": [1, 2, 3],
            }
        )
        test = pd.DataFrame(
            {
                "event_time": pd.to_datetime(["2024-01-02", "2024-01-04"]),
                "x": [4, 5],
            }
        )
        report = audit_split(train, test, time_col="event_time")

        self.assertFalse(report.valid)
        self.assertEqual(report.time_overlap_rows, 1)
        self.assertIn("temporal_leakage", checks(report))
        self.assertIn("train max", report.summary())

    def test_temporal_split_without_overlap(self) -> None:
        train = pd.DataFrame(
            {
                "event_time": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03"]
                ),
                "x": [1, 2, 3],
            }
        )
        test = pd.DataFrame(
            {
                "event_time": pd.to_datetime(["2024-01-04", "2024-01-05"]),
                "x": [4, 5],
            }
        )
        report = audit_split(train, test, time_col="event_time")

        self.assertTrue(report.valid)
        self.assertEqual(report.time_overlap_rows, 0)
        self.assertNotIn("temporal_leakage", checks(report))

    def test_unparseable_timestamps_are_warnings(self) -> None:
        train = pd.DataFrame({"event_time": ["not-a-date"], "x": [1]})
        test = pd.DataFrame({"event_time": ["2024-01-01"], "x": [2]})
        report = audit_split(train, test, time_col="event_time")

        self.assertIn("time_parse_error", checks(report))
        self.assertTrue(report.valid)


class ColumnQualityTests(unittest.TestCase):
    def test_constant_and_near_constant_columns(self) -> None:
        n = 100
        train = pd.DataFrame(
            {
                "row_id": [f"tr{index}" for index in range(n)],
                "const": [5] * n,
                "almost": [1] * 99 + [2],
                "value": np.arange(n),
            }
        )
        test = pd.DataFrame(
            {
                "row_id": [f"te{index}" for index in range(n)],
                "const": [5] * n,
                "almost": [1] * 99 + [2],
                "value": np.arange(n) + 1000,
            }
        )
        report = audit_split(train, test)

        self.assertEqual(
            findings_for(report, "constant_column").iloc[0]["column"], "const"
        )
        self.assertEqual(
            findings_for(report, "near_constant_column").iloc[0]["column"], "almost"
        )
        self.assertTrue(report.valid)

    def test_high_cardinality_identifiers(self) -> None:
        n = 30
        train = pd.DataFrame(
            {
                "user": [f"u{index}" for index in range(n)],
                "numeric_id": np.arange(n),
                "value": [index % 3 for index in range(n)],
            }
        )
        test = pd.DataFrame(
            {
                "user": [f"v{index}" for index in range(n)],
                "numeric_id": np.arange(n) + 100,
                "value": [index % 3 for index in range(n)],
            }
        )
        report = audit_split(train, test, id_cols=["numeric_id"])

        flagged = set(findings_for(report, "high_cardinality")["column"])
        self.assertEqual(flagged, {"user", "numeric_id"})
        messages = " ".join(findings_for(report, "high_cardinality")["message"])
        self.assertIn("declared identifier", messages)

    def test_unique_numeric_features_are_not_high_cardinality(self) -> None:
        train, test, _, _ = clean_split()
        report = audit_split(train, test)

        self.assertNotIn("high_cardinality", checks(report))


class ShiftTests(unittest.TestCase):
    def _frames(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        index = np.arange(30)
        train = pd.DataFrame(
            {
                "row": index,
                "value": index,
                "a": [1.0] * 30,
            }
        )
        test = pd.DataFrame(
            {
                "row": index + 30,
                "value": index + 100,
                "a": [1.0] * 15 + [None] * 15,
            }
        )
        return train, test

    def test_missingness_shift(self) -> None:
        train, test = self._frames()
        report = audit_split(train, test, id_cols=["row"])

        finding = findings_for(report, "missingness_shift")
        self.assertEqual(len(finding), 1)
        self.assertEqual(finding.iloc[0]["column"], "a")
        self.assertIn("50.0%", finding.iloc[0]["message"])

    def test_numeric_and_categorical_distribution_shift(self) -> None:
        index = np.arange(30)
        train = pd.DataFrame(
            {
                "row": index,
                "num": index,
                "cat": ["a"] * 27 + ["b"] * 3,
            }
        )
        test = pd.DataFrame(
            {
                "row": index + 30,
                "num": index + 100,
                "cat": ["a"] * 3 + ["b"] * 27,
            }
        )
        report = audit_split(train, test, id_cols=["row"])

        shifted = set(findings_for(report, "distribution_shift")["column"])
        self.assertEqual(shifted, {"num", "cat"})
        self.assertTrue(report.valid)


class TargetLeakageTests(unittest.TestCase):
    def test_regression_feature_correlation(self) -> None:
        n = 30
        train = pd.DataFrame({"row": np.arange(n), "x": np.arange(n)})
        test = pd.DataFrame({"row": np.arange(n, 2 * n), "x": np.arange(n) + 100})
        y_train = pd.Series(np.arange(n))
        y_test = pd.Series(np.arange(n))

        report = audit_split(train, test, y_train, y_test, id_cols=["row"])

        self.assertEqual(report.task, "regression")
        finding = findings_for(report, "target_leakage")
        self.assertEqual(len(finding), 1)
        self.assertEqual(finding.iloc[0]["column"], "x")
        self.assertIn("correlates", finding.iloc[0]["message"])

    def test_categorical_feature_near_perfect_prediction(self) -> None:
        n = 30
        labels = ["a"] * 10 + ["b"] * 10 + ["c"] * 10
        train = pd.DataFrame(
            {"row": np.arange(n), "leak": labels, "noise": np.arange(n)}
        )
        test = pd.DataFrame(
            {"row": np.arange(n, 2 * n), "leak": labels, "noise": np.arange(n) + 100}
        )
        y_train = pd.Series(labels)
        y_test = pd.Series(labels)

        report = audit_split(train, test, y_train, y_test, id_cols=["row"])

        self.assertEqual(report.task, "classification")
        finding = findings_for(report, "target_leakage")
        self.assertIn("leak", set(finding["column"]))
        self.assertIn("normalized mutual information", finding.iloc[0]["message"])

    def test_low_cardinality_noise_is_not_flagged(self) -> None:
        train, test, y_train, y_test = clean_split()
        report = audit_split(train, test, y_train, y_test)

        self.assertNotIn("target_leakage", checks(report))


class TargetShiftTests(unittest.TestCase):
    def test_class_shift_and_unseen_classes(self) -> None:
        n = 100
        train = pd.DataFrame({"row": np.arange(n), "x": np.arange(n)})
        test = pd.DataFrame({"row": np.arange(n, 2 * n), "x": np.arange(n)})
        y_train = pd.Series(["a"] * 90 + ["b"] * 10)
        y_test = pd.Series(["a"] * 10 + ["b"] * 80 + ["c"] * 10)

        report = audit_split(train, test, y_train, y_test, id_cols=["row"])

        self.assertEqual(report.task, "classification")
        self.assertIn("target_shift", checks(report))
        self.assertIn("unseen_target_class", checks(report))
        self.assertIn(
            "c", findings_for(report, "unseen_target_class").iloc[0]["message"]
        )

    def test_regression_target_shift(self) -> None:
        n = 30
        train = pd.DataFrame({"row": np.arange(n), "x": np.arange(n)})
        test = pd.DataFrame({"row": np.arange(n, 2 * n), "x": np.arange(n)})
        y_train = pd.Series(np.arange(n))
        y_test = pd.Series(np.arange(n) + 100)

        report = audit_split(train, test, y_train, y_test, id_cols=["row"])

        self.assertEqual(report.task, "regression")
        finding = findings_for(report, "target_shift")
        self.assertEqual(len(finding), 1)
        self.assertIn("standardized mean difference", finding.iloc[0]["message"])


class SchemaAndEmptySplitTests(unittest.TestCase):
    def test_missing_extra_and_dtype_change(self) -> None:
        train = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        test = pd.DataFrame({"a": ["x", "y", "z"], "c": [7, 8, 9]})
        report = audit_split(train, test)

        self.assertFalse(report.valid)
        self.assertIn("missing_column", checks(report))
        self.assertIn("extra_column", checks(report))
        self.assertIn("dtype_change", checks(report))
        self.assertEqual(findings_for(report, "missing_column").iloc[0]["column"], "b")

    def test_empty_split_is_a_warning(self) -> None:
        train = pd.DataFrame({"x": pd.Series(dtype="float64")})
        test = pd.DataFrame({"x": [1.0, 2.0]})
        report = audit_split(train, test)

        self.assertTrue(report.valid)
        self.assertIn("empty_split", checks(report))
        self.assertEqual(report.train_rows, 0)


class TaskInferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.train = pd.DataFrame({"x": np.arange(30)})
        self.test = pd.DataFrame({"x": np.arange(30) + 100})

    def _task(self, y_train: Any, y_test: Any, **kwargs: Any) -> str | None:
        return audit_split(self.train, self.test, y_train, y_test, **kwargs).task

    def test_auto_inference(self) -> None:
        self.assertEqual(self._task(["a"] * 30, ["a"] * 30), "classification")
        self.assertEqual(self._task([True] * 30, [True] * 30), "classification")
        self.assertEqual(self._task([0] * 10 + [1] * 20, [0] * 30), "classification")
        self.assertEqual(
            self._task(np.arange(30).tolist(), np.arange(30).tolist()), "regression"
        )
        self.assertEqual(self._task([0.0, 1.0] * 15, [0.0, 1.0] * 15), "classification")
        self.assertEqual(
            self._task(np.linspace(0, 1, 30).tolist(), np.linspace(0, 1, 30).tolist()),
            "regression",
        )

    def test_explicit_task_and_missing_target(self) -> None:
        self.assertEqual(
            self._task(["a"] * 30, ["a"] * 30, task="regression"), "regression"
        )
        report = audit_split(self.train, self.test)
        self.assertIsNone(report.task)


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.train = pd.DataFrame({"a": [1, 2, 3]})
        self.test = pd.DataFrame({"a": [4, 5, 6]})

    def test_frame_validation(self) -> None:
        with self.assertRaises(TypeError):
            audit_split([], self.test)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            audit_split(self.train, [])  # type: ignore[arg-type]

        duplicate = pd.DataFrame([[1, 2]], columns=["a", "a"])
        with self.assertRaises(ValueError):
            audit_split(duplicate, duplicate)

    def test_target_validation(self) -> None:
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, y_train=[1, 2, 3])
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, y_train=[1, 2, 3], y_test=[1, 2])
        with self.assertRaises(TypeError):
            audit_split(
                self.train,
                self.test,
                pd.DataFrame({"y": [1, 2, 3]}),
                pd.Series([1, 2, 3]),
            )
        with self.assertRaises(ValueError):
            audit_split(
                self.train,
                self.test,
                np.ones((3, 2)),
                np.ones((3, 2)),
            )

    def test_group_validation(self) -> None:
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, groups_test=[1, 2, 3])
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, groups=[1, 2, 3])
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, groups=[1, 2, 3], groups_test=[4])
        with self.assertRaises(TypeError):
            audit_split(
                self.train,
                self.test,
                groups=pd.DataFrame({"g": [1, 2, 3]}),
            )

    def test_column_validation(self) -> None:
        with self.assertRaises(KeyError):
            audit_split(self.train, self.test, time_col="missing")
        with self.assertRaises(TypeError):
            audit_split(self.train, self.test, time_col=1)  # type: ignore[arg-type]
        with self.assertRaises(KeyError):
            audit_split(self.train, self.test, id_cols=["missing"])
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, id_cols=[])
        with self.assertRaises(ValueError):
            audit_split(self.train, self.test, id_cols=["a", "a"])

    def test_threshold_validation(self) -> None:
        invalid: list[dict[str, object]] = [
            {"task": "sideways"},
            {"near_duplicate_decimals": -1},
            {"constant_threshold": 0},
            {"constant_threshold": 1.5},
            {"high_cardinality_threshold": 0},
            {"high_cardinality_min_unique": 1},
            {"missingness_shift_threshold": -0.1},
            {"missingness_shift_threshold": 1.1},
            {"distribution_shift_threshold": 0},
            {"categorical_shift_threshold": 0},
            {"target_correlation_threshold": 0},
            {"target_nmi_threshold": 0},
            {"target_shift_threshold": 0},
            {"classification_max_classes": 1},
            {"max_target_leak_categories": 1},
        ]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                audit_split(self.train, self.test, **kwargs)  # type: ignore[arg-type]


class NoMutationTests(unittest.TestCase):
    def test_inputs_are_not_mutated(self) -> None:
        train, test, y_train, y_test = clean_split()
        groups = [index % 5 for index in range(30)] + [index % 5 for index in range(30)]
        train_before = train.copy(deep=True)
        test_before = test.copy(deep=True)
        y_train_before = y_train.copy(deep=True)
        y_test_before = y_test.copy(deep=True)
        groups_before = list(groups)

        audit_split(train, test, y_train, y_test, groups=groups)

        pd.testing.assert_frame_equal(train, train_before)
        pd.testing.assert_frame_equal(test, test_before)
        pd.testing.assert_series_equal(y_train, y_train_before)
        pd.testing.assert_series_equal(y_test, y_test_before)
        self.assertEqual(groups, groups_before)


if __name__ == "__main__":
    unittest.main()
