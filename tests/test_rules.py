from __future__ import annotations

import unittest
from typing import Literal

import pandas as pd

from data_cleaner import (
    PredicateRule,
    SumEqualsRule,
    UniqueCombinationRule,
    ValidationResult,
    between,
    col,
    conditional,
    grouped,
    not_null,
    row_count_between,
    row_rule,
    sum_equals,
    unique,
    unique_combination,
    validate,
)


class ConditionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "a": [1, 2, None, 4, 5],
                "b": [0, 3, 1, 4, 4],
                "status": ["new", "shipped", "shipped", "cancelled", "shipped"],
                "region": ["eu", "us", "eu", "us", None],
            }
        )

    def test_comparisons_and_missing_semantics(self) -> None:
        mask = col("a").gt(col("b")).mask(self.frame)
        self.assertEqual(mask.tolist(), [True, False, False, False, True])
        mask = col("a").ge(4).mask(self.frame)
        self.assertEqual(mask.tolist(), [False, False, False, True, True])
        self.assertEqual(col("status").eq("shipped").mask(self.frame).sum(), 3)
        self.assertEqual(col("status").ne("new").mask(self.frame).sum(), 4)
        self.assertEqual(col("a").lt(2).mask(self.frame).sum(), 1)
        self.assertEqual(col("a").le(2).mask(self.frame).sum(), 2)

    def test_membership_bounds_and_patterns(self) -> None:
        self.assertEqual(
            col("status").isin(["new", "cancelled"]).mask(self.frame).sum(), 2
        )
        self.assertEqual(col("status").not_in(["new"]).mask(self.frame).sum(), 4)
        self.assertEqual(
            col("a").between(2, 5, inclusive=False).mask(self.frame).sum(), 1
        )
        self.assertEqual(col("region").isna().mask(self.frame).sum(), 1)
        self.assertEqual(col("region").notna().mask(self.frame).sum(), 4)
        self.assertTrue(col("status").matches(r"[a-z]+").mask(self.frame).all())

    def test_logical_composition(self) -> None:
        mask = (col("status").eq("shipped") & col("a").gt(1)).mask(self.frame)
        self.assertEqual(mask.tolist(), [False, True, False, False, True])
        mask = (col("status").eq("new") | col("a").isna()).mask(self.frame)
        self.assertEqual(mask.tolist(), [True, False, True, False, False])
        mask = (~col("a").isna()).mask(self.frame)
        self.assertEqual(mask.sum(), 4)

    def test_descriptions_are_stable(self) -> None:
        self.assertEqual(col("a").gt(col("b")).describe(), "a > b")
        self.assertIn("status in", col("status").isin(["new"]).describe())
        self.assertIn("a in [2, 5]", col("a").between(2, 5).describe())
        self.assertIn("region is missing", col("region").isna().describe())

    def test_invalid_usage(self) -> None:
        with self.assertRaises(ValueError):
            col("")
        with self.assertRaises(ValueError):
            col("a").matches("[")
        with self.assertRaises(TypeError):
            col("a") == 1  # noqa: B015
        with self.assertRaises(TypeError):
            col("a") & "not a condition"  # type: ignore[operator]
        with self.assertRaises(TypeError):
            row_rule("not a condition")  # type: ignore[arg-type]


class RuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orders = pd.DataFrame(
            {
                "order_id": [1, 2, 3, 4],
                "customer_id": [10, 10, 11, 12],
                "status": ["new", "shipped", "shipped", "cancelled"],
                "ordered_at": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
                ),
                "shipped_at": pd.to_datetime(
                    ["2024-01-02", "2024-01-01", "2024-01-05", None]  # type: ignore[arg-type]
                ),
                "subtotal": [10.0, 20.0, 30.0, 40.0],
                "tax": [1.0, 2.0, 3.0, 4.0],
                "total": [11.0, 22.0, 33.0, 45.0],
            }
        )

    def test_predicate_rule_reports_failing_rows(self) -> None:
        report = validate(
            self.orders,
            row_rule(
                col("shipped_at").ge(col("ordered_at")),
                name="shipped_after_ordered",
            ),
        )
        self.assertFalse(report.success)
        self.assertEqual(len(report.failures), 1)
        failure = report.failures.iloc[0]
        self.assertEqual(failure["observed"], 1)
        self.assertIn("shipped_after_ordered", failure["expectation"])
        self.assertEqual(failure["column"], "shipped_at, ordered_at")

    def test_conditional_rule_scope(self) -> None:
        # Only shipped rows must have a shipped_at; the cancelled row may not.
        rule = conditional(col("status").eq("shipped"), not_null("shipped_at"))
        report = validate(self.orders, rule)
        self.assertTrue(report.success)
        self.assertIn("2 row(s)", report.results.iloc[0]["message"])

        broken = self.orders.copy()
        broken.loc[1, "shipped_at"] = None
        report = validate(broken, rule)
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 1)

    def test_conditional_no_matches_passes(self) -> None:
        rule = conditional(col("status").eq("refunded"), not_null("shipped_at"))
        report = validate(self.orders, rule)
        self.assertTrue(report.success)
        self.assertIn("no rows matched", report.results.iloc[0]["message"])

    def test_grouped_rule_counts_failing_groups(self) -> None:
        frame = pd.DataFrame(
            {
                "store": ["a", "a", "b", "b", "c"],
                "amount": [1.0, None, 2.0, None, 3.0],
            }
        )
        report = validate(frame, grouped("store", not_null("amount")))
        self.assertFalse(report.success)
        failure = report.failures.iloc[0]
        self.assertEqual(failure["observed"], 2)
        self.assertIn("2 of 3 group(s)", failure["message"])
        self.assertNotIn("first failing groups", failure["message"])

        detailed = validate(
            frame,
            grouped("store", not_null("amount"), include_groups=True, max_groups=1),
        )
        message = detailed.failures.iloc[0]["message"]
        self.assertIn("first failing groups", message)
        self.assertIn("a", message)
        self.assertNotIn("'b'", message)

    def test_grouped_missing_key_fails_cleanly(self) -> None:
        report = validate(self.orders, grouped("missing", not_null("order_id")))
        self.assertFalse(report.success)
        self.assertIn("is missing", report.failures.iloc[0]["message"])

    def test_unique_combination(self) -> None:
        frame = pd.DataFrame(
            {
                "a": [1, 1, 1, 2],
                "b": ["x", "x", "y", "z"],
                "c": [None, 1, 2, 3],
            }
        )
        report = validate(frame, unique_combination(["a", "b"]))
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 1)
        report = validate(frame, unique_combination(["a", "c"]))
        self.assertTrue(report.success)  # rows with a null key are ignored

    def test_sum_equals(self) -> None:
        report = validate(
            self.orders, sum_equals(["subtotal", "tax"], "total", tolerance=0.01)
        )
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 1)
        report = validate(
            self.orders,
            sum_equals(["subtotal", "tax"], "total", tolerance=2.0),
        )
        self.assertTrue(report.success)
        report = validate(
            self.orders,
            sum_equals(["subtotal", "tax"], "missing"),
        )
        self.assertFalse(report.success)

    def test_sum_equals_flags_non_numeric_values(self) -> None:
        frame = pd.DataFrame(
            {"a": ["oops", 1.0], "b": [1.0, 1.0], "total": [2.0, "nope"]}
        )
        report = validate(frame, sum_equals(["a", "b"], "total", tolerance=0.01))
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 2)

    def test_sum_equals_validates_tolerance(self) -> None:
        for value in (float("nan"), float("inf"), -1.0):
            with self.assertRaises(ValueError):
                sum_equals(["a"], "total", tolerance=value)
        with self.assertRaises(TypeError):
            sum_equals(["a"], "total", tolerance=True)

    def test_bare_string_columns_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            unique_combination("order_id")
        with self.assertRaises(TypeError):
            sum_equals("subtotal", "total")

    def test_exported_rule_dataclasses_validate_arguments(self) -> None:
        with self.assertRaises(ValueError):
            PredicateRule(
                condition=col("total").gt(0),
                name="x",
                severity="fatal",  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            UniqueCombinationRule(columns=())
        with self.assertRaises(ValueError):
            SumEqualsRule(columns=("a",), target="b", tolerance=-1.0)

    def test_all_condition_counts_definite_false_with_missing_operand(self) -> None:
        frame = pd.DataFrame({"a": [-1.0, 1.0], "b": [None, 2.0]})
        report = validate(
            frame,
            row_rule(col("a").gt(0) & col("b").gt(0), name="both_positive"),
        )
        self.assertFalse(report.success)
        self.assertEqual(report.failures.iloc[0]["observed"], 1)
        diagnostics = report.diagnose(frame)
        self.assertEqual(diagnostics.rows["row_position"].tolist(), [0])

    def test_mixed_expectations_and_rules(self) -> None:
        report = validate(
            self.orders,
            [
                not_null("order_id"),
                unique("order_id"),
                row_rule(col("total").gt(0), name="positive_total"),
                conditional(col("status").eq("shipped"), row_rule(col("total").gt(0))),
            ],
        )
        self.assertTrue(report.success)
        self.assertEqual(len(report.results), 4)

    def test_custom_validatable_rule(self) -> None:
        class AlwaysWarns:
            name = "always_warns"
            column = "order_id"
            severity: Literal["error", "warning"] = "warning"

            def check(self, frame: pd.DataFrame) -> list[ValidationResult]:
                return [
                    ValidationResult(
                        "always_warns", "order_id", False, "warning", "heads up", 1
                    )
                ]

        report = validate(self.orders, AlwaysWarns())
        self.assertTrue(report.success)
        self.assertTrue(report.has_warnings)


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "id": [1, 1, 2, 3],
                "email": [
                    "first.person@example.com",
                    "second.person@example.com",
                    "third.person@example.com",
                    None,
                ],
                "store": ["a", "a", "b", "b"],
            }
        )

    def test_default_sample_is_bounded_and_value_free(self) -> None:
        report = validate(
            self.frame,
            [
                not_null("email"),
                unique("id"),
                between("id", 100, 200),
                row_count_between(min_rows=10),
                grouped("store", not_null("email")),
            ],
        )
        diagnostics = report.diagnose(self.frame, limit=1)
        self.assertFalse(diagnostics.empty)
        self.assertTrue(diagnostics.truncated)
        self.assertTrue(diagnostics.rows["value"].isna().all())
        self.assertLessEqual(len(diagnostics.rows), 3)
        self.assertIn("row_count_between", diagnostics.skipped)
        self.assertIn("not_null by store", diagnostics.skipped)
        self.assertIn("row_position", diagnostics.rows.columns)
        self.assertIn("index", diagnostics.rows.columns)
        self.assertIn("omitted", diagnostics.to_markdown())

    def test_values_are_opt_in_and_truncated(self) -> None:
        report = validate(self.frame, not_null("email"))
        diagnostics = report.diagnose(
            self.frame, limit=1, include_values=True, max_value_length=10
        )
        value = diagnostics.rows.iloc[0]["value"]
        self.assertIsInstance(value, str)
        self.assertLessEqual(len(value), 10)

    def test_diagnostics_validate_arguments(self) -> None:
        report = validate(self.frame, not_null("email"))
        with self.assertRaises(ValueError):
            report.diagnose(self.frame, limit=0)
        with self.assertRaises(ValueError):
            report.diagnose(self.frame, max_value_length=0)
        with self.assertRaises(TypeError):
            report.diagnose([1, 2])  # type: ignore[arg-type]

    def test_contract_report_has_no_sources(self) -> None:
        from data_cleaner import DataContract

        contract = DataContract.from_frame(self.frame)
        diagnostics = contract.validate(self.frame).diagnose(self.frame)
        self.assertTrue(diagnostics.empty)

    def test_diagnose_does_not_mutate_the_frame(self) -> None:
        before = self.frame.copy(deep=True)
        report = validate(
            self.frame,
            row_rule(col("email").notna(), name="email_present"),
        )
        report.diagnose(self.frame, include_values=True)
        pd.testing.assert_frame_equal(self.frame, before)

    def test_diagnose_supports_duplicate_index_labels(self) -> None:
        frame = pd.DataFrame(
            {"email": ["a@example.com", None, None]},
            index=[7, 7, 7],
        )
        report = validate(frame, not_null("email"))
        diagnostics = report.diagnose(frame)
        self.assertEqual(len(diagnostics.rows), 2)
        self.assertEqual(diagnostics.rows["index"].tolist(), [7, 7])
        self.assertEqual(diagnostics.rows["row_position"].tolist(), [1, 2])

    def test_conditional_diagnostics_stay_inside_the_condition(self) -> None:
        frame = pd.DataFrame(
            {
                "status": ["shipped", "shipped", "new"],
                "key": ["a", "a", "a"],
            }
        )
        report = validate(
            frame,
            conditional(col("status").eq("shipped"), unique("key")),
        )
        self.assertFalse(report.success)
        diagnostics = report.diagnose(frame)
        self.assertEqual(diagnostics.rows["row_position"].tolist(), [1])

    def test_index_can_be_omitted(self) -> None:
        report = validate(self.frame, not_null("email"))
        diagnostics = report.diagnose(self.frame, include_index=False)
        self.assertTrue(diagnostics.rows["index"].isna().all())
        self.assertEqual(diagnostics.rows["row_position"].tolist(), [3])

    def test_passing_frame_level_rule_is_not_listed_as_skipped(self) -> None:
        report = validate(
            self.frame,
            [not_null("email"), row_count_between(min_rows=1)],
        )
        diagnostics = report.diagnose(self.frame)
        self.assertNotIn("row_count_between", diagnostics.skipped)

    def test_multi_column_rule_does_not_read_a_joined_label(self) -> None:
        frame = pd.DataFrame(
            {
                "a": [1.0],
                "b": [1.0],
                "a, b": ["joined label"],
            }
        )
        report = validate(
            frame,
            row_rule(col("a").gt(col("b")), name="must_exceed"),
        )
        diagnostics = report.diagnose(frame, include_values=True)
        self.assertTrue(diagnostics.rows["value"].isna().all())

    def test_custom_validatable_that_is_also_a_sequence(self) -> None:
        class SequenceRule(list[ValidationResult]):
            name = "sequence_rule"
            column = "id"
            severity: Literal["error", "warning"] = "warning"

            def check(self, frame: pd.DataFrame) -> ValidationResult:
                return ValidationResult(
                    self.name, self.column, False, self.severity, "checked", 1
                )

        report = validate(self.frame, SequenceRule())
        self.assertTrue(report.has_warnings)
        self.assertEqual(len(report.results), 1)


if __name__ == "__main__":
    unittest.main()
