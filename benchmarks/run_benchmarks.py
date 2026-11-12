"""Reproducible benchmarks for Universal Data Cleaner.

Run the default matrix (writes JSON and prints a Markdown table):

```bash
uv run python benchmarks/run_benchmarks.py --output benchmarks/results/local.json
```

Run a fast smoke matrix, as CI does:

```bash
uv run python benchmarks/run_benchmarks.py --quick
```

Each measurement runs in a fresh subprocess so import state and allocator
caches do not leak between cases. Runtime and peak memory are measured in
separate phases: runtime with ``perf_counter`` and no tracing, memory with
``tracemalloc`` after a ``gc.collect()``. The JSON records the dependency and
platform versions needed to interpret the numbers.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import data_cleaner
from data_cleaner import (
    CleanerConfig,
    DataCleaner,
    DataContract,
    combine_drift_reports,
    not_null,
    read_csv_safe,
    row_count_between,
    validate,
)

ROOT = Path(__file__).resolve().parent.parent

CASES = (
    "ingest",
    "fit",
    "transform",
    "transform_with_report",
    "transform_chunks",
    "contract_check",
    "validate",
)

SHAPES = ("narrow", "wide", "high_cardinality")

#: Default (shape, rows) matrix. Wide frames are benchmarked at a smaller row
#: count because 120 columns at 1M rows is a deliberate memory stress test, not a
#: routine workload.
DEFAULT_PLAN = (
    ("narrow", 100_000),
    ("narrow", 1_000_000),
    ("narrow", 2_000_000),
    ("wide", 100_000),
    ("high_cardinality", 100_000),
    ("high_cardinality", 1_000_000),
)

#: Ingest is repeated once because the text-first parse dominates large runs.
REPEATS = {
    "ingest": 1,
    "fit": 2,
    "transform": 2,
    "transform_with_report": 2,
    "transform_chunks": 2,
    "contract_check": 2,
    "validate": 2,
}


def _string_ids(rows: int, prefix: str) -> pd.Series:
    """Return ``rows`` distinct text identifiers, generated vectorially."""
    values = np.char.add(prefix, np.arange(rows).astype("U10"))
    return pd.Series(values, dtype=object)


def _numeric_frame(
    rows: int,
    *,
    seed: int,
    numeric_columns: int,
) -> dict[str, pd.Series]:
    rng = np.random.default_rng(seed)
    data: dict[str, pd.Series] = {}
    for index in range(numeric_columns):
        values = rng.normal(100.0, 25.0, rows)
        if index % 3 == 0:
            missing = rng.random(rows) < 0.03
            values = values.astype("float64")
            values[missing] = np.nan
        data[f"value_{index:03d}"] = pd.Series(values)
    return data


def make_frame(rows: int, shape: str, seed: int = 7) -> pd.DataFrame:
    """Build a deterministic dataset for a named shape.

    The generator is seeded and uses only NumPy/pandas operations, so the same
    arguments produce the same frame on every machine.
    """
    if rows <= 0:
        raise ValueError("rows must be positive")
    rng = np.random.default_rng(seed)
    if shape == "narrow":
        missing = rng.random(rows) < 0.04
        salary = rng.normal(70_000, 18_000, rows)
        salary[missing] = np.nan
        frame = pd.DataFrame(
            {
                "customer_id": _string_ids(rows, "C"),
                "age": pd.Series(rng.normal(40, 12, rows)),
                "salary": pd.Series(salary),
                "score": pd.Series(rng.random(rows)),
                "orders": pd.Series(rng.integers(0, 100, rows)),
                "plan": pd.Series(
                    rng.choice(["free", "pro", "team"], rows), dtype=object
                ),
                "region": pd.Series(
                    rng.choice(["north", "south", "east", "west"], rows),
                    dtype=object,
                ),
                "active": pd.Series(rng.random(rows) > 0.3),
                "signup": pd.Series(
                    pd.Timestamp("2020-01-01")
                    + pd.to_timedelta(rng.integers(0, 2000, rows), unit="D")
                ),
                "notes": pd.Series(rng.choice(["", "ok", "check"], rows), dtype=object),
            }
        )
        return frame

    if shape == "wide":
        data = {"customer_id": _string_ids(rows, "C")}
        data.update(_numeric_frame(rows, seed=seed, numeric_columns=60))
        for index in range(59):
            data[f"category_{index:03d}"] = pd.Series(
                rng.choice([f"level_{level}" for level in range(5)], rows),
                dtype=object,
            )
        return pd.DataFrame(data)

    if shape == "high_cardinality":
        return pd.DataFrame(
            {
                "session_id": _string_ids(rows, "S"),
                "user_id": pd.Series(np.arange(rows, dtype=np.int64) + 1_000_000),
                "region": pd.Series(
                    rng.choice([f"region_{i}" for i in range(20)], rows),
                    dtype=object,
                ),
                "amount": pd.Series(rng.gamma(2.0, 30.0, rows)),
                "events": pd.Series(rng.integers(1, 50, rows)),
                "event_date": pd.Series(
                    pd.Timestamp("2021-01-01")
                    + pd.to_timedelta(rng.integers(0, 1000, rows), unit="D")
                ),
            }
        )

    raise ValueError(f"Unknown shape: {shape}. Expected one of {SHAPES}")


def _expectations(frame: pd.DataFrame) -> list[Any]:
    first = str(frame.columns[0])
    return [
        not_null(first),
        row_count_between(min_rows=1),
    ]


def _config_for(frame: pd.DataFrame) -> CleanerConfig:
    datetime_columns = tuple(
        str(name)
        for name in frame.columns
        if pd.api.types.is_datetime64_any_dtype(frame[name])
    )
    return CleanerConfig(cap_outliers=True, datetime_columns=datetime_columns)


def build_operation(
    case: str,
    frame: pd.DataFrame,
    *,
    rows: int,
    shape: str,
    seed: int,
) -> tuple[Callable[[], Any], list[Path]]:
    """Return a zero-argument callable plus temp files it needs cleaned up."""
    temp_paths: list[Path] = []

    if case == "ingest":
        contract = DataContract.infer_from(frame, strict=True)
        directory = Path(tempfile.mkdtemp(prefix="udc-bench-"))
        path = directory / f"{shape}-{rows}.csv"
        frame.to_csv(path, index=False)
        temp_paths.append(path)

        def ingest() -> Any:
            return read_csv_safe(path, contract=contract, on_error="ignore")

        return ingest, temp_paths

    if case == "contract_check":
        contract = DataContract.infer_from(frame, strict=True)
        return (lambda: contract.check(frame)), temp_paths

    if case == "validate":
        expectations = _expectations(frame)
        return (lambda: validate(frame, expectations)), temp_paths

    if case == "fit":
        return (lambda: DataCleaner(_config_for(frame)).fit(frame)), temp_paths

    cleaner = DataCleaner(_config_for(frame)).fit(frame)

    if case == "transform":
        return (lambda: cleaner.transform(frame)), temp_paths

    if case == "transform_with_report":
        return (lambda: cleaner.transform_with_report(frame)), temp_paths

    if case == "transform_chunks":
        chunk_size = max(1, len(frame) // 8)
        chunks = [
            frame.iloc[start : start + chunk_size]
            for start in range(0, len(frame), chunk_size)
        ]

        def transform_chunks() -> Any:
            return combine_drift_reports(
                report for _, report in cleaner.transform_chunks(chunks)
            )

        return transform_chunks, temp_paths

    raise ValueError(f"Unknown case: {case}. Expected one of {CASES}")


def _run_worker(args: argparse.Namespace, rows: int) -> int:
    """Measure one (case, shape, rows) combination and print JSON."""
    case = args.case
    shape = args.shape
    if case is None or shape is None:  # narrowed by ``main``; keep mypy honest
        raise ValueError("worker requires a case and a shape")
    frame = make_frame(rows, shape, seed=args.seed)
    operation, temp_paths = build_operation(
        case,
        frame,
        rows=rows,
        shape=shape,
        seed=args.seed,
    )
    try:
        # Warm-up keeps first-call import/lazy-init costs out of the timing.
        operation()
        gc.collect()

        timings: list[float] = []
        for _ in range(REPEATS[case]):
            started = time.perf_counter()
            operation()
            timings.append(time.perf_counter() - started)

        gc.collect()
        tracemalloc.start()
        operation()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        result = {
            "case": case,
            "shape": shape,
            "rows": rows,
            "runtime_s": min(timings),
            "runtime_median_s": float(np.median(timings)),
            "peak_traced_mb": peak / (1024 * 1024),
            "max_rss_mb": _max_rss_mb(),
            "input_frame_mb": float(frame.memory_usage(deep=True).sum())
            / (1024 * 1024),
        }
    finally:
        for path in temp_paths:
            path.unlink(missing_ok=True)
            with suppress(OSError):
                path.parent.rmdir()
    print(json.dumps(result, sort_keys=True))
    return 0


def _max_rss_mb() -> float:
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    platform_name: str = sys.platform
    if platform_name == "darwin":
        return usage / (1024 * 1024)
    return usage / 1024


def _metadata() -> dict[str, object]:
    import sklearn

    commit = ""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        commit = ""
    return {
        "library": "universal-data-cleaner",
        "version": data_cleaner.__version__,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "git_commit": commit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _run_case(case: str, shape: str, rows: int, seed: int) -> dict[str, Any]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--case",
        case,
        "--shape",
        shape,
        "--rows",
        str(rows),
        "--seed",
        str(seed),
    ]
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    source_path = str(ROOT / "src")
    environment["PYTHONPATH"] = (
        f"{source_path}{os.pathsep}{existing}" if existing else source_path
    )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"benchmark worker failed for {case}/{shape}/{rows}:\n"
            f"{completed.stderr.strip()}"
        )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"benchmark worker produced no output for {case}")
    return json.loads(lines[-1])


def _markdown(results: list[dict[str, Any]]) -> str:
    header = (
        "| Case | Shape | Rows | Runtime (s) | Peak traced (MB) "
        "| Max RSS (MB) | Input frame (MB) |\n"
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |"
    )
    rows = [
        "| {case} | {shape} | {rows:,} | {runtime_s:.3f} | {peak_traced_mb:.1f} "
        "| {max_rss_mb:.1f} | {input_frame_mb:.1f} |".format(**result)
        for result in results
    ]
    return "\n".join([header, *rows])


def _parse_plan(args: argparse.Namespace) -> list[tuple[str, int]]:
    if args.quick:
        return [("narrow", 10_000)]
    if args.rows:
        shapes = [args.shape] if args.shape else list(SHAPES)
        return [(shape, rows) for shape in shapes for rows in args.rows]
    if args.shape:
        return [(shape, rows) for shape, rows in DEFAULT_PLAN if shape == args.shape]
    return list(DEFAULT_PLAN)


def _write_payload(
    target: Path,
    plan: list[tuple[str, int]],
    cases: tuple[str, ...],
    results: list[dict[str, Any]],
    *,
    complete: bool,
) -> None:
    """Persist the run so far, so a crash does not lose hours of measurement."""
    payload = {
        "metadata": _metadata(),
        "plan": [{"shape": shape, "rows": rows} for shape, rows in plan],
        "cases": list(cases),
        "complete": complete,
        "results": results,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_parent(args: argparse.Namespace) -> int:
    plan = _parse_plan(args)
    cases = (args.case,) if args.case else CASES
    results: list[dict[str, Any]] = []
    total = len(plan) * len(cases)
    completed = 0
    target = Path(args.output) if args.output else None
    for shape, rows in plan:
        for case in cases:
            completed += 1
            print(
                f"[{completed}/{total}] {case} {shape} {rows:,} ...",
                file=sys.stderr,
                flush=True,
            )
            results.append(_run_case(case, shape, rows, args.seed))
            if target is not None:
                _write_payload(target, plan, cases, results, complete=False)

    if target is not None:
        _write_payload(target, plan, cases, results, complete=True)
        print(f"Wrote {target}", file=sys.stderr)
    print(_markdown(results))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--shape", choices=SHAPES)
    parser.add_argument("--rows", type=int, nargs="+")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", help="Write the JSON payload to this path")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a 10K-row narrow smoke matrix (used by CI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.worker:
        if args.case is None or args.shape is None or args.rows is None:
            parser.error("--worker requires --case, --shape, and --rows")
        return _run_worker(args, args.rows[0])
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
