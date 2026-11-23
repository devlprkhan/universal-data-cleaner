from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from data_cleaner import (
    DistributionDriftReport,
    DriftPolicy,
    DriftProfile,
    compare_distributions,
)


def _numeric_frame(start: float = 0.0, rows: int = 500) -> pd.DataFrame:
    return pd.DataFrame({"amount": np.linspace(start, start + 100, rows)})


class DriftPolicyTests(unittest.TestCase):
    def test_roundtrip_and_validation(self) -> None:
        policy = DriftPolicy(psi_warning=0.05, psi_error=0.2, min_sample=0)
        self.assertEqual(DriftPolicy.from_dict(policy.to_dict()), policy)
        self.assertEqual(policy.to_dict()["psi_error"], 0.2)
        self.assertEqual(DriftPolicy.from_json(policy.to_json()), policy)
        with self.assertRaises(ValueError):
            DriftPolicy(psi_warning=0.3, psi_error=0.2)
        with self.assertRaises(ValueError):
            DriftPolicy(missing_delta_warning=-1)
        with self.assertRaises(ValueError):
            DriftPolicy(bins=1)
        with self.assertRaises(ValueError):
            DriftPolicy.from_dict({"unknown": 1})
        for value in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                DriftPolicy(psi_warning=value)
        for name in ("bins", "max_categories", "max_columns", "wasserstein_points"):
            with self.assertRaises(TypeError):
                DriftPolicy(**{name: 2.5})  # type: ignore[arg-type]
        normalized = DriftPolicy(bins=np.int64(8))
        self.assertIsInstance(normalized.to_dict()["bins"], int)
        json.dumps(normalized.to_dict())


class NumericDriftTests(unittest.TestCase):
    def test_identical_distribution_is_stable(self) -> None:
        reference = _numeric_frame()
        report = compare_distributions(reference, reference.copy())
        self.assertIsInstance(report, DistributionDriftReport)
        self.assertFalse(report.has_drift)
        self.assertEqual(report.drifted_columns, ())
        self.assertAlmostEqual(float(report.columns.iloc[0]["psi"]), 0.0)
        self.assertIn("STABLE", report.to_markdown())
        report.raise_if_drift()

    def test_shifted_distribution_is_drift(self) -> None:
        report = compare_distributions(_numeric_frame(), _numeric_frame(30.0))
        self.assertTrue(report.has_drift)
        self.assertTrue(report.has_errors)
        self.assertEqual(report.drifted_columns, ("amount",))
        row = report.columns.iloc[0]
        self.assertGreater(float(row["psi"]), 0.25)
        self.assertEqual(row["status"], "error")
        self.assertIn("PSI", row["message"])
        with self.assertRaises(ValueError):
            report.raise_if_drift()

    def test_wasserstein_distance_and_ratio(self) -> None:
        reference = pd.DataFrame({"value": np.arange(100, dtype=float)})
        current = pd.DataFrame({"value": np.arange(100, dtype=float) + 10.0})
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertAlmostEqual(float(row["wasserstein"]), 10.0, places=6)
        self.assertIsNotNone(row["wasserstein_ratio"])

    def test_constant_reference_detects_shift(self) -> None:
        reference = pd.DataFrame({"value": [5.0] * 100})
        stable = compare_distributions(reference, reference.copy())
        self.assertFalse(stable.has_drift)
        shifted = compare_distributions(reference, pd.DataFrame({"value": [6.0] * 100}))
        self.assertTrue(shifted.has_drift)
        self.assertEqual(shifted.drifted_columns, ("value",))

    def test_two_edge_binary_reference_detects_full_flip(self) -> None:
        reference = pd.DataFrame({"flag": [0.0] * 50 + [1.0] * 51})
        current = pd.DataFrame({"flag": [1.0] * 101})
        report = compare_distributions(
            reference, current, policy=DriftPolicy(min_sample=0)
        )
        self.assertGreater(float(report.columns.iloc[0]["psi"]), 0.25)
        self.assertTrue(report.has_errors)

    def test_all_missing_current_leaves_wasserstein_unset(self) -> None:
        reference = _numeric_frame(rows=50)
        current = pd.DataFrame({"amount": [None] * 50})
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertIsNone(row["wasserstein"])
        self.assertIsNone(row["wasserstein_ratio"])
        self.assertTrue(report.has_drift)

    def test_infinite_values_are_treated_as_missing(self) -> None:
        reference = pd.DataFrame({"value": [1.0, 2.0, 3.0, np.inf]})
        current = pd.DataFrame({"value": [1.0, 2.0, 3.0, -np.inf]})
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertAlmostEqual(float(row["missing_reference_pct"]), 25.0)
        self.assertAlmostEqual(float(row["missing_current_pct"]), 25.0)
        self.assertAlmostEqual(float(row["psi"]), 0.0, places=9)

    def test_datetime_columns_use_seconds(self) -> None:
        reference = pd.DataFrame(
            {"seen_at": pd.date_range("2024-01-01", periods=200, freq="h")}
        )
        current = pd.DataFrame(
            {"seen_at": pd.date_range("2024-02-01", periods=200, freq="h")}
        )
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertEqual(row["kind"], "datetime")
        self.assertGreater(float(row["psi"]), 0.0)
        expected = (
            pd.Timestamp("2024-02-01") - pd.Timestamp("2024-01-01")
        ).total_seconds()
        # Both samples are quantiles at the same probabilities, so a uniform
        # shift is measured directly.
        self.assertAlmostEqual(float(row["wasserstein"]), expected, delta=1.0)

    def test_timezone_aware_datetimes_are_supported(self) -> None:
        reference = pd.DataFrame(
            {"seen_at": pd.date_range("2024-01-01", periods=100, freq="h", tz="UTC")}
        )
        current = reference.copy()
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertEqual(row["kind"], "datetime")
        self.assertAlmostEqual(float(row["psi"]), 0.0, places=9)
        # The profile stores a bounded quantile sample, so a comparison of
        # identical data is near zero rather than exactly zero.
        self.assertLessEqual(abs(float(row["wasserstein_ratio"])), 0.01)

    def test_missing_delta_is_reported(self) -> None:
        reference = _numeric_frame()
        current = _numeric_frame().copy()
        current.loc[:49, "amount"] = None
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertAlmostEqual(float(row["missing_reference_pct"]), 0.0)
        self.assertAlmostEqual(float(row["missing_current_pct"]), 10.0)
        self.assertAlmostEqual(float(row["missing_delta_pp"]), 10.0)
        self.assertTrue(report.has_drift)

    def test_policy_thresholds_control_severity(self) -> None:
        reference = _numeric_frame()
        current = _numeric_frame(30.0)
        lenient = compare_distributions(
            reference,
            current,
            policy=DriftPolicy(psi_warning=None, psi_error=None, min_sample=0),
        )
        self.assertFalse(lenient.has_drift)
        strict = compare_distributions(
            reference,
            current,
            policy=DriftPolicy(psi_warning=0.01, psi_error=0.02, min_sample=0),
        )
        self.assertTrue(strict.has_errors)

    def test_small_sample_downgrades_errors_to_warnings(self) -> None:
        reference = pd.DataFrame({"value": [float(value) for value in range(10)]})
        current = pd.DataFrame({"value": [float(value + 100) for value in range(10)]})
        downgraded = compare_distributions(
            reference,
            current,
            policy=DriftPolicy(psi_warning=0.01, psi_error=0.02, min_sample=20),
        )
        self.assertTrue(downgraded.has_warnings)
        self.assertFalse(downgraded.has_errors)
        strict = compare_distributions(
            reference,
            current,
            policy=DriftPolicy(psi_warning=0.01, psi_error=0.02, min_sample=0),
        )
        self.assertTrue(strict.has_errors)

    def test_kind_change_and_missing_column(self) -> None:
        reference = _numeric_frame()
        kind_changed = compare_distributions(
            reference, pd.DataFrame({"amount": ["x"] * 500})
        )
        self.assertTrue(kind_changed.has_errors)
        self.assertIn("kind changed", kind_changed.columns.iloc[0]["message"])

        missing = compare_distributions(reference, pd.DataFrame({"other": [1] * 10}))
        self.assertTrue(missing.has_errors)
        self.assertIn("missing", missing.columns.iloc[0]["message"])

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(TypeError):
            DriftProfile.from_frame([1, 2])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            DriftProfile.from_frame(pd.DataFrame())
        with self.assertRaises(KeyError):
            DriftProfile.from_frame(_numeric_frame(), columns=["nope"])
        profile = DriftProfile.from_frame(_numeric_frame())
        with self.assertRaises(ValueError):
            profile.compare(pd.DataFrame())
        with self.assertRaises(TypeError):
            profile.compare([1, 2])  # type: ignore[arg-type]

    def test_input_frames_are_not_mutated(self) -> None:
        reference = _numeric_frame()
        current = _numeric_frame(30.0)
        reference_before = reference.copy(deep=True)
        current_before = current.copy(deep=True)
        compare_distributions(reference, current)
        pd.testing.assert_frame_equal(reference, reference_before)
        pd.testing.assert_frame_equal(current, current_before)


class CategoricalDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reference = pd.DataFrame(
            {
                "plan": ["free"] * 250 + ["pro"] * 200 + ["team"] * 50,
            }
        )

    def test_category_deltas_and_unseen_levels(self) -> None:
        current = pd.DataFrame(
            {"plan": ["free"] * 100 + ["pro"] * 150 + ["team"] * 250}
        )
        report = compare_distributions(self.reference, current)
        self.assertTrue(report.has_drift)
        categories = report.categories
        self.assertFalse(categories.empty)
        team = categories[categories["category"] == "team"].iloc[0]
        self.assertAlmostEqual(float(team["reference_share_pct"]), 10.0)
        self.assertAlmostEqual(float(team["current_share_pct"]), 50.0)
        self.assertAlmostEqual(float(team["delta_pp"]), 40.0)

        unseen = pd.DataFrame({"plan": ["enterprise"] * 100 + ["free"] * 400})
        report = compare_distributions(self.reference, unseen)
        self.assertEqual(int(report.columns.iloc[0]["other_categories"]), 1)
        other = report.categories[report.categories["other"]].iloc[0]
        self.assertEqual(other["category"], "(other)")
        self.assertAlmostEqual(float(other["reference_share_pct"]), 0.0)
        self.assertAlmostEqual(float(other["current_share_pct"]), 20.0)
        self.assertAlmostEqual(float(other["delta_pp"]), 20.0)

    def test_rare_reference_levels_are_measured_against_other(self) -> None:
        reference = pd.DataFrame({"plan": ["a"] * 80 + ["b"] * 15 + ["c"] * 5})
        current = pd.DataFrame({"plan": ["a"] * 88 + ["c"] * 12})
        policy = DriftPolicy(max_categories=2, min_sample=0)
        report = compare_distributions(reference, current, policy=policy)
        other = report.categories[report.categories["other"]].iloc[0]
        self.assertAlmostEqual(float(other["reference_share_pct"]), 5.0)
        self.assertAlmostEqual(float(other["current_share_pct"]), 12.0)
        self.assertAlmostEqual(float(other["delta_pp"]), 7.0)

    def test_limited_categories_keep_report_bounded(self) -> None:
        reference = pd.DataFrame({"code": [f"c{index}" for index in range(100)]})
        current = pd.DataFrame({"code": [f"c{index}" for index in range(100, 200)]})
        policy = DriftPolicy(max_categories=5, min_sample=0)
        report = compare_distributions(reference, current, policy=policy)
        self.assertLessEqual(len(report.categories), 10)
        self.assertTrue(report.has_drift)

    def test_missing_bucket_does_not_shift_psi(self) -> None:
        values = ["free"] * 60 + ["pro"] * 30 + [None] * 10
        reference = pd.DataFrame({"plan": values})
        current = reference.copy()
        report = compare_distributions(reference, current)
        row = report.columns.iloc[0]
        self.assertAlmostEqual(float(row["psi"]), 0.0, places=9)
        self.assertAlmostEqual(float(row["missing_current_pct"]), 10.0)
        self.assertFalse(report.has_drift)


class ProfileRoundTripTests(unittest.TestCase):
    def test_profile_survives_json_and_compares_identically(self) -> None:
        reference = pd.DataFrame(
            {
                "amount": np.linspace(0, 100, 200),
                "plan": ["free", "pro"] * 100,
                "joined": pd.date_range("2024-01-01", periods=200, freq="D"),
                "flag": [True, False] * 100,
            }
        )
        current = reference.copy()
        current.loc[:10, "amount"] = np.nan
        profile = DriftProfile.from_frame(reference)
        direct = profile.compare(current)
        restored = DriftProfile.from_json(profile.to_json())
        round_trip = restored.compare(current)
        self.assertEqual(restored.to_dict(), profile.to_dict())
        self.assertEqual(
            json.loads(round_trip.to_json())["columns"],
            json.loads(direct.to_json())["columns"],
        )
        self.assertEqual(round_trip.policy, profile.policy)

    def test_profile_quantiles_are_bounded_and_mid_probability(self) -> None:
        frame = pd.DataFrame({"amount": [10.0, 20.0, 30.0, 40.0]})
        profile = DriftProfile.from_frame(frame)
        payload = profile.to_dict()
        columns = payload["columns"]
        assert isinstance(columns, dict)
        numeric = columns["amount"]
        assert isinstance(numeric, dict)
        quantiles = numeric["quantiles"]
        assert isinstance(quantiles, list)
        self.assertEqual(len(quantiles), 512)
        # The stored sample is a summary, not the raw sorted column.
        self.assertNotEqual(quantiles, [10.0, 20.0, 30.0, 40.0])

    def test_profile_repr_is_redacted(self) -> None:
        frame = pd.DataFrame({"amount": [10.0, 20.0, 30.0]})
        profile = DriftProfile.from_frame(frame)
        text = repr(profile)
        self.assertNotIn("quantiles", text)
        self.assertNotIn("10.0", text)
        report = profile.compare(frame)
        self.assertNotIn("quantiles", repr(report))

    def test_non_string_and_duplicate_labels_are_rejected(self) -> None:
        with self.assertRaises(TypeError):
            DriftProfile.from_frame(pd.DataFrame({1: [1.0, 2.0]}))
        with self.assertRaises(ValueError):
            DriftProfile.from_frame(pd.DataFrame([[1.0, 2.0]], columns=["a", "a"]))
        with self.assertRaises(TypeError):
            DriftProfile.from_frame(
                pd.DataFrame({"amount": [1.0]}),
                columns="amount",  # type: ignore[arg-type]
            )

    def test_report_is_json_serializable(self) -> None:
        reference = pd.DataFrame({"amount": [1.0, 2.0, 3.0, 4.0]})
        current = pd.DataFrame({"amount": [1.0, 2.0, 3.0, None]})
        report = compare_distributions(reference, current)
        payload = report.to_dict()
        text = json.dumps(payload)
        self.assertIn("columns", json.loads(text))
        self.assertEqual(payload["reference_rows"], 4)
        self.assertIsNotNone(payload["reference"])
        if report.has_drift:
            self.assertIn("drifted", report.summary())


if __name__ == "__main__":
    unittest.main()
