from __future__ import annotations

import pickle
import tempfile
import unittest
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from data_cleaner import (
    CleanerConfig,
    ColumnSpec,
    DataCleaner,
    DataContract,
    DriftReport,
    assert_frame_clean,
    dataset_summary,
    drop_duplicate_rows,
    profile_dataframe,
)


def sample_data(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = 120
    age = rng.integers(22, 60, rows)
    salary = rng.normal(70_000, 18_000, rows)
    experience = rng.integers(0, 35, rows)
    department = rng.choice(["IT", "HR", "Finance"], rows)
    signup = pd.to_datetime("2023-01-01") + pd.to_timedelta(
        rng.integers(0, 365, rows), unit="D"
    )
    target = 50 + 0.2 * (age - 40) + 0.08 * (experience - 10) + rng.normal(0, 3, rows)
    frame = pd.DataFrame(
        {
            "Age": age,
            "Salary": salary,
            "Experience": experience,
            "Department": department,
            "IsActive": rng.choice([True, False], rows),
            "SignupDate": signup,
            "Constant": "same",
            "Target": np.clip(target, 0, 100),
        }
    )
    frame["IsActive"] = frame["IsActive"].astype("boolean")
    frame.loc[frame.sample(8, random_state=seed).index, "Age"] = np.nan
    frame.loc[frame.sample(8, random_state=seed + 1).index, "Salary"] = np.nan
    frame.loc[frame.sample(6, random_state=seed + 2).index, "Department"] = None
    frame.loc[frame.sample(5, random_state=seed + 3).index, "SignupDate"] = None
    missing_active = frame.sample(5, random_state=seed + 4).index
    frame.loc[missing_active, "IsActive"] = pd.NA
    frame.loc[0:2, "Salary"] = 5_000_000
    frame.loc[3, "Department"] = "Legal"
    return frame


class DataCleanerTests(unittest.TestCase):
    def setUp(self) -> None:
        frame = sample_data()
        self.features = frame.drop(columns=["Target"])
        self.target = frame["Target"]

    def config(self, **kwargs: Any) -> CleanerConfig:
        defaults: dict[str, Any] = {
            "numeric_columns": ("Salary",),
            "datetime_columns": ("SignupDate",),
            "add_missing_indicators": True,
            "drop_constant_columns": True,
        }
        defaults.update(kwargs)
        return CleanerConfig(**defaults)

    def test_fit_transform_has_no_missing_or_infinity(self) -> None:
        cleaner = DataCleaner(self.config())
        cleaned = cleaner.fit_transform(self.features)
        assert_frame_clean(cleaned)
        self.assertNotIn("SignupDate", cleaned.columns)
        self.assertIn("SignupDate__month", cleaned.columns)
        self.assertNotIn("Constant", cleaned.columns)
        self.assertTrue((cleaned["Salary"] < 1_000_000).all())

    def test_transform_does_not_mutate_input_and_is_idempotent(self) -> None:
        cleaner = DataCleaner(self.config()).fit(self.features)
        before = self.features.copy(deep=True)
        once = cleaner.transform(self.features)
        twice = cleaner.transform(self.features)
        pd.testing.assert_frame_equal(self.features, before)
        pd.testing.assert_frame_equal(once, twice)

    def test_outlier_bounds_are_fit_only(self) -> None:
        cleaner = DataCleaner(self.config(cap_outliers=False)).fit(self.features)
        cleaned = cleaner.transform(self.features)
        self.assertTrue((cleaned["Salary"] > 1_000_000).any())

    def test_fit_learns_only_from_training_data(self) -> None:
        train = self.features.iloc[:80].copy()
        test = self.features.iloc[80:].copy()
        cleaner = DataCleaner(self.config()).fit(train)
        salary_fill = cleaner.fill_values_["Salary"]

        probe = test.copy()
        probe["Salary"] = 9_999_999.0
        _ = cleaner.transform(probe)
        self.assertEqual(cleaner.fill_values_["Salary"], salary_fill)

    def test_unseen_columns_are_ignored_and_missing_columns_fail(self) -> None:
        cleaner = DataCleaner(self.config()).fit(self.features)
        with_extra = self.features.assign(Unplanned="yes")
        transformed = cleaner.transform(with_extra)
        self.assertNotIn("Unplanned", transformed.columns)

        with self.assertRaises(ValueError):
            cleaner.transform(self.features.drop(columns=["Age"]))

    def test_unseen_category_policy(self) -> None:
        cleaner = DataCleaner(self.config(unseen_category="fill")).fit(self.features)
        probe = self.features.copy()
        probe.loc[0, "Department"] = "NeverSeen"
        transformed = cleaner.transform(probe)
        self.assertEqual(
            transformed.loc[0, "Department"],
            cleaner.config.categorical_fill_value,
        )

    def test_save_load_roundtrip(self) -> None:
        cleaner = DataCleaner(self.config()).fit(self.features)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cleaner.joblib"
            cleaner.save(path)
            restored = DataCleaner.load(path)
            pd.testing.assert_frame_equal(
                cleaner.transform(self.features),
                restored.transform(self.features),
            )

    def test_sklearn_clone_and_pipeline(self) -> None:
        cleaner = DataCleaner(self.config())
        cloned = clone(cleaner)
        self.assertEqual(cloned.config, cleaner.config)

        numeric = list(cloned.config.numeric_columns)
        categorical = ["Department"]
        boolean = ["IsActive"]
        pipeline = Pipeline(
            [
                ("cleaner", cleaner),
                (
                    "features",
                    ColumnTransformer(
                        [
                            (
                                "num",
                                "passthrough",
                                numeric,
                            ),
                            ("bool", "passthrough", boolean),
                            (
                                "cat",
                                OneHotEncoder(
                                    handle_unknown="ignore", sparse_output=False
                                ),
                                categorical,
                            ),
                        ],
                        remainder="drop",
                    ),
                ),
                ("model", Ridge(alpha=1.0)),
            ]
        )
        pipeline.fit(self.features, self.target)
        predictions = pipeline.predict(self.features)
        self.assertEqual(len(predictions), len(self.features))

    def test_helpers(self) -> None:
        report = profile_dataframe(self.features)
        summary = dataset_summary(self.features)
        deduplicated, removed = drop_duplicate_rows(
            pd.concat([self.features, self.features.head(3)], ignore_index=True)
        )
        self.assertEqual(len(report), self.features.shape[1])
        self.assertEqual(summary["columns"], self.features.shape[1])
        self.assertEqual(removed, 3)
        self.assertEqual(len(deduplicated), len(self.features))


class ContractTests(unittest.TestCase):
    def test_inferred_contract_reports_extra_column(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": ["x", "y", "x"]})
        cleaner = DataCleaner(CleanerConfig()).fit(frame)
        self.assertIsNotNone(cleaner.fitted_contract())
        cleaner.transform(frame.assign(extra="e"))
        report = cleaner.drift_report()
        self.assertIn("unexpected_column", set(report["check"]))

    def test_id_role_is_not_numeric_imputed_or_capped(self) -> None:
        frame = pd.DataFrame(
            {"customer_id": [1001, 1002, 9_999_999], "amount": [10.0, 20.0, 30.0]}
        )
        contract = DataContract(columns=(ColumnSpec("customer_id", role="id"),))
        cleaner = DataCleaner(CleanerConfig(contract=contract)).fit(frame)
        self.assertNotIn("customer_id", cleaner.numeric_columns_)

        out = cleaner.transform(frame)
        self.assertEqual(set(out["customer_id"]), {"1001", "1002", "9999999"})
        self.assertTrue(
            out["customer_id"].map(lambda value: isinstance(value, str)).all()
        )
        self.assertTrue(cleaner.drift_report().empty)

        probe = frame.copy()
        probe.loc[0, "customer_id"] = None
        transformed = cleaner.transform(probe)
        self.assertEqual(transformed.loc[0, "customer_id"], "Unknown")

    def test_ignore_role_drops_column(self) -> None:
        frame = pd.DataFrame({"keep": [1.0, 2.0], "meta": ["a", "b"]})
        contract = DataContract(columns=(ColumnSpec("meta", role="ignore"),))
        cleaner = DataCleaner(CleanerConfig(contract=contract)).fit(frame)
        self.assertNotIn("meta", list(cleaner.get_feature_names_out()))
        out = cleaner.transform(frame.drop(columns=["meta"]))
        self.assertNotIn("meta", out.columns)

    def test_unexpected_category_is_reported(self) -> None:
        frame = pd.DataFrame({"plan": ["free", "pro", "free"]})
        contract = DataContract(
            columns=(
                ColumnSpec("plan", role="category", allowed_values=("free", "pro")),
            )
        )
        cleaner = DataCleaner(CleanerConfig(contract=contract)).fit(frame)
        probe = pd.DataFrame({"plan": ["free", "pro", "enterprise"]})
        cleaner.transform(probe)  # default on_drift="warn" must not raise
        report = cleaner.drift_report()
        self.assertIn("unexpected_category", set(report["check"]))

    def test_on_drift_raise_for_range_violation(self) -> None:
        frame = pd.DataFrame({"age": [10.0, 20.0, 30.0]})
        contract = DataContract(
            columns=(ColumnSpec("age", role="numeric", min_value=0, max_value=120),)
        )
        cleaner = DataCleaner(CleanerConfig(contract=contract, on_drift="raise")).fit(
            frame
        )
        with self.assertRaises(ValueError):
            cleaner.transform(pd.DataFrame({"age": [10.0, 500.0]}))

    def test_on_drift_ignore_does_not_raise(self) -> None:
        frame = pd.DataFrame({"age": [10.0, 20.0, 30.0]})
        contract = DataContract(
            columns=(ColumnSpec("age", role="numeric", min_value=0, max_value=120),)
        )
        cleaner = DataCleaner(CleanerConfig(contract=contract, on_drift="ignore")).fit(
            frame
        )
        out = cleaner.transform(pd.DataFrame({"age": [500.0]}))
        self.assertEqual(len(out), 1)
        self.assertGreaterEqual(cleaner.drift_report().shape[0], 1)

    def test_contract_serialization_roundtrip(self) -> None:
        contract = DataContract(
            columns=(
                ColumnSpec("id", role="id", preserve_leading_zeros=True),
                ColumnSpec("age", role="numeric", min_value=0, max_value=120),
                ColumnSpec("plan", role="category", allowed_values=("free", "pro")),
            ),
            strict=True,
        )
        restored = DataContract.from_json(contract.to_json())
        self.assertEqual(restored.to_dict(), contract.to_dict())
        self.assertTrue(restored.strict)
        self.assertEqual(restored.spec_for("age").role, "numeric")  # type: ignore[union-attr]

    def test_invalid_spec_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ColumnSpec("x", role="not-a-role")
        with self.assertRaises(ValueError):
            ColumnSpec("x", pattern="[unclosed")

    def test_missing_column_still_raises_with_drift_details(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        cleaner = DataCleaner(CleanerConfig()).fit(frame)
        with self.assertRaises(ValueError) as ctx:
            cleaner.transform(frame.drop(columns=["b"]))
        self.assertIn("missing required columns", str(ctx.exception))


class PackageTests(unittest.TestCase):
    """Guardrails for the packaged (multi-module) layout."""

    def test_public_api_is_complete(self) -> None:
        import data_cleaner

        for name in (
            "CleanerConfig",
            "ColumnSpec",
            "DataCleaner",
            "DataContract",
            "DriftReport",
            "assert_frame_clean",
            "dataset_summary",
            "drop_duplicate_rows",
            "profile_dataframe",
        ):
            self.assertTrue(hasattr(data_cleaner, name), name)
        self.assertRegex(data_cleaner.__version__, r"^\d+\.\d+\.\d+")

    def test_typed_marker_is_installed(self) -> None:
        import data_cleaner

        package_dir = Path(data_cleaner.__file__).parent
        self.assertTrue((package_dir / "py.typed").is_file())

    def test_legacy_flat_module_artifact_loads(self) -> None:
        """An artifact pickled by the pre-2.2.0 single-module layout still loads.

        Before the package split, every public class lived in a flat
        ``data_cleaner`` module, so pickles referenced ``data_cleaner.DataCleaner``
        and friends. We reproduce that layout by temporarily remapping the
        classes' ``__module__`` while saving, which keeps the test independent of
        the pandas version and therefore safe across the whole test matrix.
        """
        import data_cleaner

        train = pd.DataFrame(
            {
                "customer_id": [1, 2, 3, 4, 5],
                "age": [25.0, None, 35.0, 40.0, 29.0],
                "city": ["NY", "LA", "NY", None, "SF"],
                "active": [True, False, True, True, False],
                "joined": pd.to_datetime(
                    [
                        "2020-01-01",
                        "2020-06-15",
                        "2021-03-10",
                        "2021-12-31",
                        "2019-07-04",
                    ]
                ),
            }
        )
        cleaner = DataCleaner(CleanerConfig(datetime_columns=("joined",))).fit(train)

        legacy_classes = (
            CleanerConfig,
            ColumnSpec,
            DataContract,
            DataCleaner,
            DriftReport,
        )
        original_modules = {cls: cls.__module__ for cls in legacy_classes}
        try:
            for cls in legacy_classes:
                cls.__module__ = "data_cleaner"

            blob = pickle.dumps(cleaner)
            self.assertIn(b"data_cleaner", blob)
            self.assertNotIn(b"data_cleaner.cleaner", blob)

            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "legacy_flat.joblib"
                cleaner.save(path)

                payload = joblib.load(path)
                payload["library_version"] = "2.1.0"
                joblib.dump(payload, path, compress=3)

                with self.assertLogs("data_cleaner.cleaner", level="WARNING") as logs:
                    restored = DataCleaner.load(path)
        finally:
            for cls, module in original_modules.items():
                cls.__module__ = module

        self.assertTrue(any("2.1.0" in line for line in logs.output))
        self.assertNotEqual(data_cleaner.__version__, "2.1.0")

        frame = pd.DataFrame(
            {
                "customer_id": [10, 11],
                "age": [None, 41.0],
                "city": ["NY", "BOS"],
                "active": [True, False],
                "joined": pd.to_datetime(["2022-05-01", "2023-02-14"]),
            }
        )
        cleaned = restored.transform(frame)
        assert_frame_clean(cleaned)
        self.assertEqual(len(cleaned), len(frame))
        self.assertEqual(
            list(cleaned.columns),
            [
                "customer_id",
                "age",
                "city",
                "active",
                "joined__year",
                "joined__month",
                "joined__day",
                "joined__dayofweek",
            ],
        )
        self.assertFalse(cleaned["age"].isna().any())


if __name__ == "__main__":
    unittest.main()
