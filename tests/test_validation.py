from __future__ import annotations

import unittest

import pandas as pd

from data_cleaner import (
    Contract,
    DataContract,
    Expectation,
    ValidationReport,
    between,
    check_referential_integrity,
    deduplicate_by_business_key,
    diagnose_join,
    has_dtype,
    in_set,
    matches_pattern,
    not_null,
    row_count_between,
    unique,
    validate,
)


class ExpectationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "name": ["a", "b", None, "d"],
                "amount": [10.0, 20.0, 30.0, 40.0],
                "status": ["new", "paid", "paid", "new"],
                "joined": pd.to_datetime(
                    ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]
                ),
            }
        )

    def test_not_null_and_unique(self) -> None:
        report = validate(self.frame, [not_null("id"), unique("id")])
        self.assertIsInstance(report, ValidationReport)
        self.assertTrue(report.success)
        self.assertTrue(report.failures.empty)
        self.assertFalse(report.has_warnings)
        self.assertIn("PASS", report.to_markdown())

        report = validate(self.frame, [not_null("name"), unique("name")])
        self.assertFalse(report.success)
        self.assertEqual(len(report.failures), 1)
        self.assertIn("missing", str(report.failures.iloc[0]["message"]))
        with self.assertRaises(ValueError):
            report.raise_if_failed()

    def test_unique_ignores_nulls_but_detects_duplicates(self) -> None:
        frame = pd.DataFrame({"k": [1, 1, 2, None, None]})
        report = validate(frame, unique("k"))
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 1)

    def test_in_set(self) -> None:
        self.assertTrue(validate(self.frame, in_set("status", ["new", "paid"])).success)
        report = validate(self.frame, in_set("status", ["new"]))
        self.assertFalse(report.success)
        self.assertIn("outside", str(report.failures.iloc[0]["message"]))

    def test_between_inclusive_and_exclusive(self) -> None:
        self.assertTrue(validate(self.frame, between("amount", 10, 40)).success)
        report = validate(self.frame, between("amount", 10, 40, inclusive=False))
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 2)

    def test_between_counts_non_numeric_values(self) -> None:
        frame = pd.DataFrame({"x": [1.0, "oops", None]})
        report = validate(frame, between("x", 0, 10))
        self.assertFalse(report.success)
        self.assertIn("non-numeric", str(report.failures.iloc[0]["message"]))

    def test_matches_pattern(self) -> None:
        self.assertTrue(validate(self.frame, matches_pattern("id", r"\d+")).success)
        self.assertTrue(validate(self.frame, matches_pattern("name", r"[a-z]")).success)
        self.assertFalse(
            validate(self.frame, matches_pattern("name", r"[a-z]{2}")).success
        )

    def test_has_dtype_broad_and_exact(self) -> None:
        self.assertTrue(validate(self.frame, has_dtype("amount", "numeric")).success)
        self.assertTrue(validate(self.frame, has_dtype("amount", "float64")).success)
        self.assertFalse(validate(self.frame, has_dtype("amount", "int64")).success)
        self.assertTrue(validate(self.frame, has_dtype("joined", "datetime")).success)
        self.assertTrue(
            validate(self.frame, has_dtype("status", "categorical")).success
        )
        with self.assertRaises(ValueError):
            validate(self.frame, has_dtype("amount", "not_a_dtype"))

    def test_row_count_between(self) -> None:
        self.assertTrue(validate(self.frame, row_count_between(1, 10)).success)
        report = validate(self.frame, row_count_between(5, 10))
        self.assertFalse(report.success)
        self.assertIn("expected between", str(report.failures.iloc[0]["message"]))
        with self.assertRaises(ValueError):
            row_count_between(10, 1)

    def test_missing_column_fails_without_raising(self) -> None:
        report = validate(self.frame, [not_null("missing"), unique("missing")])
        self.assertFalse(report.success)
        self.assertEqual(len(report.failures), 2)
        self.assertTrue(
            all("missing" in str(message) for message in report.failures["message"])
        )

    def test_warning_severity_does_not_fail(self) -> None:
        report = validate(self.frame, not_null("name", severity="warning"))
        self.assertTrue(report.success)
        self.assertTrue(report.has_warnings)
        self.assertEqual(len(report.failures), 1)
        report.raise_if_failed()
        markdown = report.to_markdown()
        self.assertIn("PASS", markdown)
        self.assertIn("WARNING", markdown.upper())

    def test_expectation_validation_and_serialization(self) -> None:
        expectation = not_null("id", severity="warning")
        self.assertEqual(expectation.to_dict()["name"], "not_null")
        self.assertEqual(expectation.to_dict()["severity"], "warning")
        with self.assertRaises(ValueError):
            Expectation(name="bogus", column="id")
        with self.assertRaises(ValueError):
            validate(self.frame, [])

    def test_validate_rejects_non_dataframe(self) -> None:
        with self.assertRaises(TypeError):
            validate([1, 2], not_null("a"))  # type: ignore[arg-type]


class ContractValidationTests(unittest.TestCase):
    def test_contract_validate_and_aliases(self) -> None:
        train = pd.DataFrame({"id": [1, 2, 3], "amount": [1.0, 2.0, 3.0]})
        contract = DataContract.from_frame(train)
        self.assertEqual(contract, DataContract.infer_from(train))
        self.assertIs(Contract, DataContract)

        report = contract.validate(train)
        self.assertIsInstance(report, ValidationReport)
        self.assertTrue(report.success)
        self.assertTrue(report.failures.empty)
        self.assertIn("no contract violations", report.to_markdown())

        bad = train.assign(amount=["x", 2.0, 3.0])
        report = contract.validate(bad)
        self.assertFalse(report.success)
        self.assertIn("dtype_change", set(report.failures["expectation"]))
        with self.assertRaises(ValueError):
            report.raise_if_failed()


class JoinDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.left = pd.DataFrame({"customer_id": [1, 2, 3], "amount": [10, 20, 30]})
        self.right = pd.DataFrame(
            {"customer_id": [1, 2, 2], "segment": ["a", "b", "c"]}
        )

    def test_one_to_many_join_is_unsafe(self) -> None:
        report = diagnose_join(self.left, self.right, on="customer_id", how="left")
        self.assertFalse(report.safe)
        self.assertEqual(report.right_duplicate_keys, 1)
        self.assertEqual(report.right_duplicate_rows, 2)
        self.assertEqual(report.left_cardinality, "1")
        self.assertEqual(report.right_cardinality, "m")
        self.assertEqual(report.cardinality, "1:m")
        self.assertEqual(report.output_rows, 4)
        self.assertAlmostEqual(report.row_multiplier, 4 / 3)
        self.assertEqual(report.unmatched_left, 1)
        self.assertEqual(report.unmatched_right, 0)
        self.assertTrue(any("right key is not unique" in w for w in report.warnings))
        with self.assertRaises(ValueError):
            report.raise_if_unsafe()
        self.assertIn("row multiplier", report.to_markdown())
        self.assertEqual(report.to_dict()["on"], ["customer_id"])

    def test_clean_one_to_one_join_is_safe(self) -> None:
        right = pd.DataFrame({"customer_id": [1, 2, 3], "segment": ["a", "b", "c"]})
        report = diagnose_join(self.left, right, on="customer_id", how="left")
        self.assertTrue(report.safe)
        self.assertEqual(report.output_rows, 3)
        self.assertEqual(report.row_multiplier, 1.0)
        self.assertEqual(report.unmatched_left, 0)
        self.assertFalse(report.warnings)
        report.raise_if_unsafe()

    def test_inner_join_reports_dropped_rows(self) -> None:
        right = pd.DataFrame({"customer_id": [1, 2], "segment": ["a", "b"]})
        report = diagnose_join(self.left, right, on="customer_id", how="inner")
        self.assertTrue(report.safe)
        self.assertEqual(report.output_rows, 2)
        self.assertEqual(report.unmatched_left, 1)
        self.assertAlmostEqual(report.row_multiplier, 2 / 3)
        self.assertTrue(any("dropped" in w for w in report.warnings))

    def test_outer_join(self) -> None:
        right = pd.DataFrame({"customer_id": [2, 4], "segment": ["b", "d"]})
        report = diagnose_join(
            self.left, right, on="customer_id", how="outer", validate="m:m"
        )
        self.assertTrue(report.safe)
        self.assertEqual(report.output_rows, 4)
        self.assertEqual(report.unmatched_left, 2)
        self.assertEqual(report.unmatched_right, 1)

    def test_null_keys_make_join_unsafe(self) -> None:
        left = pd.DataFrame({"k": [1, None]})
        right = pd.DataFrame({"k": [1, None]})
        report = diagnose_join(left, right, on="k")
        self.assertFalse(report.safe)
        self.assertEqual(report.left_null_keys, 1)
        self.assertEqual(report.right_null_keys, 1)
        self.assertTrue(any("null" in warning for warning in report.warnings))

    def test_multi_key_join_and_no_mutation(self) -> None:
        left = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "y", "x"], "v": [1, 2, 3]})
        right = pd.DataFrame({"a": [1, 2], "b": ["x", "x"], "w": [10, 20]})
        left_before = left.copy(deep=True)
        right_before = right.copy(deep=True)
        report = diagnose_join(left, right, on=["a", "b"], how="left")
        self.assertEqual(report.on, ("a", "b"))
        self.assertTrue(report.safe)
        self.assertEqual(report.output_rows, 3)
        pd.testing.assert_frame_equal(left, left_before)
        pd.testing.assert_frame_equal(right, right_before)

    def test_invalid_arguments(self) -> None:
        with self.assertRaises(ValueError):
            diagnose_join(
                self.left,
                self.right,
                on="customer_id",
                how="sideways",  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            diagnose_join(
                self.left,
                self.right,
                on="customer_id",
                validate="1:many",  # type: ignore[arg-type]
            )
        with self.assertRaises(KeyError):
            diagnose_join(self.left, self.right, on="missing")
        with self.assertRaises(TypeError):
            diagnose_join([], self.right, on="customer_id")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            diagnose_join(self.left, self.right, on=[])


class ReferentialIntegrityTests(unittest.TestCase):
    def test_valid_relationship(self) -> None:
        child = pd.DataFrame({"customer_id": [1, 2, 2]})
        parent = pd.DataFrame({"id": [1, 2], "name": ["a", "b"]})
        report = check_referential_integrity(child, parent, "customer_id", "id")
        self.assertTrue(report.valid)
        self.assertEqual(report.orphan_rows, 0)
        self.assertEqual(report.matched_rows, 3)
        self.assertEqual(report.parent_duplicate_keys, 0)
        report.raise_if_invalid()
        self.assertIn("valid", report.to_markdown())

    def test_orphans_and_duplicate_parents(self) -> None:
        child = pd.DataFrame({"customer_id": [1, 2, 99]})
        parent = pd.DataFrame({"id": [1, 1, 2]})
        report = check_referential_integrity(child, parent, "customer_id", "id")
        self.assertFalse(report.valid)
        self.assertEqual(report.orphan_rows, 1)
        self.assertEqual(report.orphan_key_count, 1)
        self.assertEqual(report.orphan_keys, ((99,),))
        self.assertEqual(report.parent_duplicate_keys, 1)
        self.assertTrue(any("missing parent" in w for w in report.warnings))
        self.assertTrue(any("parent key is not unique" in w for w in report.warnings))
        with self.assertRaises(ValueError):
            report.raise_if_invalid()
        self.assertEqual(report.to_dict()["orphan_keys"], [[99]])

    def test_null_child_keys(self) -> None:
        child = pd.DataFrame({"customer_id": [1, None]})
        parent = pd.DataFrame({"id": [1]})
        report = check_referential_integrity(child, parent, "customer_id", "id")
        self.assertTrue(report.valid)
        self.assertEqual(report.null_child_keys, 1)
        report = check_referential_integrity(
            child, parent, "customer_id", "id", allow_null_keys=False
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("not allowed" in w for w in report.warnings))

    def test_multi_key_and_empty_parent(self) -> None:
        child = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        parent = pd.DataFrame({"a": [1], "b": ["x"]})
        report = check_referential_integrity(child, parent, ["a", "b"])
        self.assertEqual(report.orphan_rows, 1)
        self.assertEqual(report.orphan_keys, ((2, "y"),))

        empty = parent.iloc[0:0]
        report = check_referential_integrity(child, empty, ["a", "b"])
        self.assertEqual(report.orphan_rows, 2)
        self.assertEqual(report.matched_rows, 0)
        self.assertFalse(report.valid)

    def test_key_length_mismatch_and_no_mutation(self) -> None:
        child = pd.DataFrame({"a": [1], "b": [2]})
        parent = pd.DataFrame({"a": [1], "b": [2]})
        before = child.copy(deep=True)
        with self.assertRaises(ValueError):
            check_referential_integrity(child, parent, ["a", "b"], ["a"])
        pd.testing.assert_frame_equal(child, before)


class DeduplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "customer_id": [1, 1, 2, 2, 3],
                "updated_at": pd.to_datetime(
                    [
                        "2024-01-01",
                        "2024-02-01",
                        "2024-01-01",
                        "2024-03-01",
                        "2024-01-01",
                    ]
                ),
                "value": ["old", "new", "a", "b", "c"],
            }
        )

    def test_keep_first_and_report(self) -> None:
        deduplicated, report = deduplicate_by_business_key(
            self.frame, "customer_id", keep="first"
        )
        self.assertEqual(len(deduplicated), 3)
        self.assertEqual(report.removed_rows, 2)
        self.assertEqual(report.duplicate_keys, 2)
        self.assertEqual(len(report.removed), 2)
        self.assertEqual(deduplicated["customer_id"].tolist(), [1, 2, 3])
        self.assertEqual(deduplicated["value"].tolist(), ["old", "a", "c"])
        self.assertIn("removed rows", report.to_markdown().lower())
        self.assertEqual(report.to_dict()["removed_rows"], 2)

    def test_keep_last_and_tie_breaker(self) -> None:
        deduplicated, report = deduplicate_by_business_key(
            self.frame,
            "customer_id",
            keep="last",
            tie_breaker="updated_at",
        )
        self.assertEqual(deduplicated["value"].tolist(), ["new", "b", "c"])
        self.assertEqual(report.tie_breaker, ("updated_at",))
        self.assertEqual(report.removed_rows, 2)

    def test_tie_breaker_prefers_non_null(self) -> None:
        frame = pd.DataFrame(
            {
                "id": [1, 1],
                "updated_at": [None, pd.Timestamp("2024-01-01")],
                "value": ["missing", "present"],
            }
        )
        deduplicated, _ = deduplicate_by_business_key(
            frame, "id", keep="first", tie_breaker="updated_at"
        )
        self.assertEqual(deduplicated["value"].tolist(), ["present"])
        deduplicated, _ = deduplicate_by_business_key(
            frame, "id", keep="last", tie_breaker="updated_at"
        )
        self.assertEqual(deduplicated["value"].tolist(), ["present"])

    def test_null_key_warning(self) -> None:
        frame = pd.DataFrame({"id": [None, None, 1], "value": ["a", "b", "c"]})
        deduplicated, report = deduplicate_by_business_key(frame, "id")
        self.assertEqual(len(deduplicated), 2)
        self.assertEqual(report.null_key_rows, 2)
        self.assertTrue(any("null" in warning for warning in report.warnings))

    def test_no_mutation_and_validation(self) -> None:
        before = self.frame.copy(deep=True)
        deduplicated, _ = deduplicate_by_business_key(self.frame, "customer_id")
        pd.testing.assert_frame_equal(self.frame, before)
        self.assertIsNot(deduplicated, self.frame)
        with self.assertRaises(ValueError):
            deduplicate_by_business_key(
                self.frame,
                "customer_id",
                keep="middle",  # type: ignore[arg-type]
            )
        with self.assertRaises(KeyError):
            deduplicate_by_business_key(self.frame, "missing")
        with self.assertRaises(KeyError):
            deduplicate_by_business_key(
                self.frame, "customer_id", tie_breaker="missing"
            )
