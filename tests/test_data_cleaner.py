from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from data_cleaner import (
    CleanerConfig,
    DataCleaner,
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
    target = (
        50
        + 0.2 * (age - 40)
        + 0.08 * (experience - 10)
        + rng.normal(0, 3, rows)
    )
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

    def config(self, **kwargs) -> CleanerConfig:
        defaults = {
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

        numeric = [c for c in cloned.config.numeric_columns]
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


if __name__ == "__main__":
    unittest.main()
