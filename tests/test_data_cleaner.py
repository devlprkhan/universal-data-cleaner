from __future__ import annotations

import json
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

import data_cleaner
from data_cleaner import (
    CleanerConfig,
    CleaningDecision,
    ColumnSpec,
    DataCleaner,
    DataContract,
    DriftReport,
    assert_frame_clean,
    assert_schema_stable,
    compare_fingerprints,
    dataset_summary,
    drop_duplicate_rows,
    fingerprint_dataframe,
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


def sample_config(**kwargs: Any) -> CleanerConfig:
    defaults: dict[str, Any] = {
        "numeric_columns": ("Salary",),
        "datetime_columns": ("SignupDate",),
        "add_missing_indicators": True,
        "drop_constant_columns": True,
    }
    defaults.update(kwargs)
    return CleanerConfig(**defaults)


class DataCleanerTests(unittest.TestCase):
    def setUp(self) -> None:
        frame = sample_data()
        self.features = frame.drop(columns=["Target"])
        self.target = frame["Target"]

    def config(self, **kwargs: Any) -> CleanerConfig:
        return sample_config(**kwargs)

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


class AuditTests(unittest.TestCase):
    """Decision log and artifact manifest behavior."""

    def setUp(self) -> None:
        frame = sample_data()
        self.features = frame.drop(columns=["Target"])
        self.cleaner = DataCleaner(sample_config()).fit(self.features)

    def test_cleaning_decision_to_dict(self) -> None:
        decision = CleaningDecision(
            column="age",
            action="impute",
            reason="median imputation",
            source="learned",
            before=2,
            after=30.0,
        )
        self.assertEqual(
            decision.to_dict(),
            {
                "column": "age",
                "action": "impute",
                "reason": "median imputation",
                "source": "learned",
                "before": 2,
                "after": 30.0,
            },
        )

    def test_decision_log_has_expected_shape_and_actions(self) -> None:
        log = self.cleaner.decision_log()
        self.assertEqual(
            list(log.columns),
            ["column", "action", "reason", "source", "before", "after"],
        )
        self.assertFalse(log.empty)
        actions = set(log["action"])
        for expected in {
            "infer_contract",
            "impute",
            "cap_outliers",
            "expand_datetime",
            "add_missing_indicator",
            "drop_column",
            "finalize_schema",
        }:
            self.assertIn(expected, actions, expected)
        self.assertTrue((log["reason"].astype(str).str.len() > 0).all())
        self.assertTrue(
            set(log["source"]).issubset(
                {"learned", "config", "contract", "default", "inferred"}
            )
        )
        constant_rows = log[log["column"] == "Constant"]
        self.assertIn("drop_column", set(constant_rows["action"]))

    def test_decision_log_marks_contract_sources(self) -> None:
        frame = pd.DataFrame(
            {
                "customer_id": [1001, 1002],
                "amount": [10.0, 20.0],
                "notes": ["a", "b"],
            }
        )
        contract = DataContract(
            columns=(
                ColumnSpec("customer_id", role="id"),
                ColumnSpec("notes", role="ignore"),
            )
        )
        cleaner = DataCleaner(CleanerConfig(contract=contract)).fit(frame)
        log = cleaner.decision_log()

        use_contract = log[log["action"] == "use_contract"]
        self.assertEqual(len(use_contract), 1)

        id_rows = log[
            (log["column"] == "customer_id") & (log["action"] == "stringify_identifier")
        ]
        self.assertEqual(len(id_rows), 1)
        self.assertEqual(id_rows.iloc[0]["source"], "contract")

        ignored = log[(log["column"] == "notes") & (log["action"] == "drop_column")]
        self.assertEqual(len(ignored), 1)
        self.assertEqual(ignored.iloc[0]["source"], "contract")

    def test_manifest_is_json_serializable_and_complete(self) -> None:
        manifest: dict[str, Any] = self.cleaner.to_manifest(
            self.features, include_fingerprint=True
        )
        json.dumps(manifest)

        self.assertEqual(manifest["library_version"], data_cleaner.__version__)
        self.assertEqual(manifest["artifact_version"], 2)
        self.assertEqual(
            manifest["environment"]["universal_data_cleaner"],
            data_cleaner.__version__,
        )
        self.assertIsInstance(manifest["config"], dict)
        self.assertIsNotNone(manifest["contract"])
        self.assertTrue(manifest["input_schema"])
        self.assertEqual(
            manifest["output_columns"],
            list(self.cleaner.get_feature_names_out()),
        )
        self.assertEqual(manifest["fitted"]["n_features_in"], self.features.shape[1])
        self.assertEqual(len(manifest["fingerprint"]), 64)
        self.assertTrue(manifest["decisions"])
        self.assertEqual(
            self.cleaner.artifact_manifest()["output_columns"],
            list(self.cleaner.get_feature_names_out()),
        )

    def test_manifest_fingerprint_requires_source(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0]})
        config = sample_config(numeric_columns=("a",), datetime_columns=())
        cleaner = DataCleaner(config).fit(frame)
        with self.assertRaises(ValueError):
            cleaner.to_manifest(include_fingerprint=True)

        fingerprinted = DataCleaner(
            sample_config(
                numeric_columns=("a",),
                datetime_columns=(),
                fingerprint_on_fit=True,
            )
        ).fit(frame)
        manifest: dict[str, Any] = fingerprinted.to_manifest(include_fingerprint=True)
        self.assertEqual(manifest["fingerprint"], fingerprinted.training_fingerprint_)
        self.assertEqual(len(fingerprinted.fingerprint(frame)), 64)

    def test_artifact_manifest_roundtrip_and_backfill(self) -> None:
        frame = sample_data().drop(columns=["Target"])
        cleaner = DataCleaner(sample_config(fingerprint_on_fit=True)).fit(frame)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cleaner.joblib"
            cleaner.save(path)
            payload = joblib.load(path)
            saved_manifest = payload["manifest"]

            restored = DataCleaner.load(path)
            self.assertEqual(restored.artifact_manifest(), saved_manifest)
            self.assertEqual(
                restored.training_fingerprint_, cleaner.training_fingerprint_
            )
            self.assertFalse(restored.decision_log().empty)

            legacy_cleaner = payload["cleaner"]
            for attribute in ("decisions_", "input_schema_", "training_fingerprint_"):
                legacy_cleaner.__dict__.pop(attribute, None)
            payload.pop("manifest")
            payload["artifact_version"] = 1
            payload["library_version"] = "2.2.0"
            joblib.dump(payload, path, compress=3)

            with self.assertLogs("data_cleaner.cleaner", level="WARNING") as logs:
                legacy = DataCleaner.load(path)
        messages = "\n".join(logs.output)
        self.assertIn("no manifest", messages)
        self.assertIn("no decision log", messages)
        self.assertIn("Artifact version", messages)
        self.assertTrue(legacy.decision_log().empty)
        self.assertIsNotNone(legacy.artifact_manifest())


class FingerprintTests(unittest.TestCase):
    """Stable lineage fingerprints and schema-stability assertions."""

    def test_fingerprint_is_stable_and_sensitive(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": ["x", "y", "x"]})
        first = fingerprint_dataframe(frame)
        self.assertEqual(first, fingerprint_dataframe(frame.copy()))
        self.assertEqual(len(first), 64)
        self.assertNotEqual(
            first, fingerprint_dataframe(frame.assign(a=[1.0, 2.0, 4.0]))
        )
        self.assertNotEqual(first, fingerprint_dataframe(frame[["b", "a"]]))
        self.assertNotEqual(first, fingerprint_dataframe(frame, columns=["a"]))

    def test_fingerprint_validation(self) -> None:
        frame = pd.DataFrame({"a": [1.0]})
        with self.assertRaises(TypeError):
            fingerprint_dataframe([1, 2])  # type: ignore[arg-type]
        with self.assertRaises(KeyError):
            fingerprint_dataframe(frame, columns=["missing"])
        duplicates = pd.DataFrame([[1, 2]], columns=["a", "a"])
        with self.assertRaises(ValueError):
            fingerprint_dataframe(duplicates)

    def test_compare_and_assert_schema_stable(self) -> None:
        frame = pd.DataFrame({"a": [1.0, 2.0]})
        expected = fingerprint_dataframe(frame)
        self.assertTrue(compare_fingerprints(expected, expected))
        self.assertFalse(compare_fingerprints(expected, "0" * 64))

        assert_schema_stable(frame, expected)
        with self.assertRaises(ValueError):
            assert_schema_stable(frame.assign(a=[9.0, 2.0]), expected)


class PackageTests(unittest.TestCase):
    """Guardrails for the packaged (multi-module) layout."""

    def test_public_api_is_complete(self) -> None:
        for name in (
            "CleanerConfig",
            "CleaningDecision",
            "ColumnSpec",
            "DataCleaner",
            "DataContract",
            "DriftReport",
            "assert_frame_clean",
            "assert_schema_stable",
            "compare_fingerprints",
            "dataset_summary",
            "drop_duplicate_rows",
            "fingerprint_dataframe",
            "profile_dataframe",
        ):
            self.assertTrue(hasattr(data_cleaner, name), name)
        self.assertRegex(data_cleaner.__version__, r"^\d+\.\d+\.\d+")

    def test_typed_marker_is_installed(self) -> None:
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
            CleaningDecision,
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
